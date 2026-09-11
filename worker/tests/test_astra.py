from decimal import Decimal

import httpx
import pytest

from ihear_worker.astra import (
    APPROVED_TIPS, MAX_REQUEST_BODY_BYTES, AstraClient, AstraCostExceeded, AstraError,
    AstraRejected, AstraUnavailable, AmbiguousProviderFailure, build_event_input,
    calculate_cost, prepare_request,
)


def test_input_is_bounded_and_marks_device_capabilities_unknown() -> None:
    event = {
        "kind": "difficult",
        "difficulty": "speech in noise",
        "environment": "cafe",
        "captured_at": "2026-09-11T10:00:00Z",
        "profile_snapshot": {
            "note": "x" * 2_000,
            "aids": {"side": "bilateral", "left": {"model": "ALLURE", "tier": "220"}, "right": None},
            "audiogram": {"frequencies": [250, 500], "left": [20, 30], "right": [25, 35]},
        },
    }
    payload = build_event_input(
        event, {"duration_seconds": 10, "silent": False}, [{}] * 50,
        {"device": "ALLURE", "facts": [{"fact": "Verified family fact.", "verificationStatus": "verified_manufacturer_description"}]},
    )
    assert len(payload["prior_events"]) == 20
    assert len(payload["profile"]["note"]) == 500
    assert payload["profile"]["hearing_aids"]["left"]["tier_specific_differences"] == "unknown"
    assert payload["profile"]["hearing_aids"]["left"]["verified_family_facts"] == ["Verified family fact."]


def test_missing_key_is_explicitly_unavailable() -> None:
    with pytest.raises(AstraUnavailable, match="OPENAI_API_KEY"):
        AstraClient(None).prepare({})


def test_responses_request_is_low_reasoning_toolless_and_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []

    def fake_post(url, **kwargs):
        captured.append({"url": url, **kwargs})
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 321})
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "status": "completed",
                "output_text": '{"summary":"Measured evidence only.","observations":[],"tip_ids":["quieter_place"],"limitations":[]}',
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 20},
                    "output_tokens": 50,
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("test-key")
    prepared = client.prepare({"bounded": True})
    result = client.interpret(prepared, "event:test:v1")
    body = __import__("json").loads(captured[1]["content"])
    assert body["model"] == "gpt-6-astra"
    assert body["reasoning"] == {"effort": "low"}
    assert body["tools"] == []
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["max_output_tokens"] == 1_200
    assert result.result["tips"] == [APPROVED_TIPS["quieter_place"]]
    assert result.actual_cost_usd == Decimal("0.003460")
    assert result.usage["request_body_bytes"] <= MAX_REQUEST_BODY_BYTES
    assert result.usage["preflight_input_tokens"] == 321
    assert captured[0]["url"].endswith("/responses/input_tokens")
    assert captured[1]["url"].endswith("/responses")
    assert captured[0]["content"] == captured[1]["content"]


def test_exact_http_body_is_bounded_and_old_history_is_trimmed() -> None:
    payload = {
        "event": {"kind": "difficult"},
        "prior_events": [{"environment": "x" * 400} for _ in range(20)],
    }
    body, encoded = prepare_request(payload)
    submitted = __import__("json").loads(encoded)
    submitted_input = __import__("json").loads(submitted["input"])
    assert body == submitted
    assert len(encoded) <= MAX_REQUEST_BODY_BYTES
    assert 0 < len(submitted_input["prior_events"]) < 20


def test_oversized_current_event_is_rejected_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(httpx, "post", fail_if_called)
    with pytest.raises(AstraRejected, match="reserved input envelope"):
        AstraClient("test-key").prepare({"event": {"note": "x" * 10_000}})
    assert called is False


def test_ambiguous_network_result_forbids_automatic_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fail(url, **kwargs):
        nonlocal calls
        calls += 1
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        raise httpx.ReadTimeout("unknown provider outcome")

    monkeypatch.setattr(httpx, "post", fail)
    client = AstraClient("test-key")
    prepared = client.prepare({})
    with pytest.raises(AmbiguousProviderFailure, match="retry is forbidden"):
        client.interpret(prepared, "event:test:v1")
    assert calls == 2


@pytest.mark.parametrize(
    "response_json",
    [
        {},
        {"object": "wrong", "input_tokens": 100},
        {"object": "response.input_tokens", "input_tokens": True},
    ],
)
def test_bad_token_count_fails_closed_without_generation(
    monkeypatch: pytest.MonkeyPatch, response_json: dict,
) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json=response_json)

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(AstraUnavailable, match="generation was not attempted"):
        AstraClient("test-key").prepare({})
    assert len(calls) == 1
    assert calls[0].endswith("/input_tokens")


def test_over_limit_token_count_fails_closed_without_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 8_001})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(AstraRejected, match="reserved limit"):
        AstraClient("test-key").prepare({})
    assert len(calls) == 1


def test_cost_cannot_exceed_reservation() -> None:
    with pytest.raises(AstraError, match="reserved maximum"):
        calculate_cost({
            "input_tokens": 8_000,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 8_000},
            "output_tokens": 1_201,
        })


def test_completed_overage_has_cost_and_request_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 8_000})
        return httpx.Response(
            200,
            json={
                "id": "resp_overage",
                "status": "completed",
                "output_text": '{"summary":"Measured evidence only.","observations":[],"tip_ids":[],"limitations":[]}',
                "usage": {
                    "input_tokens": 8_001,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 8_001},
                    "output_tokens": 1_200,
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("test-key")
    prepared = client.prepare({})
    with pytest.raises(AstraCostExceeded) as caught:
        client.interpret(prepared, "event:test:v1")
    assert caught.value.actual_cost_usd > Decimal("0.160000")
    assert caught.value.provider_request_id == "resp_overage"
    assert caught.value.usage["input_tokens"] == 8_001


def test_completed_response_with_missing_usage_is_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        return httpx.Response(
            200,
            json={
                "id": "resp_missing_usage",
                "status": "completed",
                "output_text": '{"summary":"Measured evidence only.","observations":[],"tip_ids":[],"limitations":[]}',
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("test-key")
    prepared = client.prepare({})
    with pytest.raises(AmbiguousProviderFailure, match="invalid usage accounting"):
        client.interpret(prepared, "event:test:v1")
