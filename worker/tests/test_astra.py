from decimal import Decimal
import json

import httpx
import pytest

from ihear_worker.astra import (
    APPROVED_TIPS, MAX_REQUEST_BODY_BYTES, AstraClient, AstraCostExceeded, AstraError,
    AstraRejected, AstraUnavailable, AmbiguousProviderFailure, OUTPUT_SCHEMA, PROMPT_VERSION,
    build_event_input, calculate_cost, expand_device_actions, prepare_request,
)


def _v2_output(**overrides):
    result = {
        "summary": "Measured evidence only.",
        "observations": [],
        "tip_ids": [],
        "limitations": [],
        "recommendations": [],
        "frequency_notes": [],
        "patient_summary": "This listening moment can be reviewed with your clinician.",
        "device_action_ids": [],
    }
    result.update(overrides)
    return result


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
    assert set(payload) >= {"reported_event", "phone_audio_measurements", "model_estimates"}
    assert "deterministic_analysis" not in payload
    assert payload["allowed_device_actions"] == []


def _catalog() -> dict:
    return {
        "device": "Widex ALLURE BTE R D",
        "illustrativeTiers": ["110", "220", "330", "440"],
        "appActions": [{
            "id": "allure_equalizer",
            "title": "Compare sound with the equalizer",
            "instruction": "Use the catalog instruction, not provider text.",
            "source": "https://www.widex.com/example",
            "checkedAt": "2026-09-13",
            "supportedModels": ["Widex ALLURE BTE R D"],
            "verificationStatus": "verified_app_control_requires_confirmation",
        }],
    }


def _supported_event() -> dict:
    return {
        "kind": "difficult",
        "difficulty": "Following one person",
        "environment": "Background conversation",
        "captured_at": "2026-09-13T08:00:00Z",
        "profile_snapshot": {
            "aids": {
                "side": "bilateral",
                "left": {"model": "Widex ALLURE BTE R D", "tier": "220"},
                "right": {"model": "Widex ALLURE BTE R D", "tier": "220"},
                "app": {
                    "name": "Widex Allure",
                    "version": "1.2.3",
                    "confirmedActions": ["allure_equalizer"],
                },
            },
        },
    }


def test_v2_accepts_exact_request_actions_and_expands_only_catalog_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _supported_event()
    payload = build_event_input(
        event,
        {"bands": [{"low_hz": 250, "high_hz": 500, "relative_energy": 0.25}]},
        [],
        _catalog(),
    )
    assert payload["allowed_device_actions"] == [{
        "id": "allure_equalizer", "title": "Compare sound with the equalizer",
    }]
    provider_result = _v2_output(
        observations=["SNR cannot be estimated from the supplied phone recording."],
        recommendations=[
            {
                "text": "Ask whether a program comparison changes the reported difficulty.",
                "evidence_refs": ["reported_event", "band:0"],
            },
            {
                "text": "Consider a speech assessment for the reported difficulty.",
                "evidence_refs": ["reported_event"],
            },
        ],
        frequency_notes=[{
            "band_index": 0,
            "explanation": "This uncalibrated recording has relative energy in this band.",
            "review_question": "Does the reported difficulty recur with similar sounds?",
        }],
        patient_summary="The recording gives your clinician context, but it is not a hearing test.",
        device_action_ids=["allure_equalizer"],
    )

    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 700})
        return httpx.Response(200, json={
            "id": "resp_v2",
            "status": "completed",
            "service_tier": "default",
            "output_text": json.dumps(provider_result),
            "usage": {
                "input_tokens": 700,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens": 120,
            },
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    result = client.interpret(client.prepare(payload), "event:test:v2")
    expanded = expand_device_actions(result.result, event, _catalog())
    assert expanded["device_actions"] == [{
        "id": "allure_equalizer",
        "title": "Compare sound with the equalizer",
        "instruction": "Use the catalog instruction, not provider text.",
        "source": "https://www.widex.com/example",
        "checkedAt": "2026-09-13",
    }]


@pytest.mark.parametrize(
    "event_change",
    [
        {"side": "bilateral", "right": {"model": "Unknown model", "tier": "220"}},
        {"side": "left", "left_tier": "999"},
        {"side": "left", "app_version": ""},
        {"side": "left", "confirmed": ["not_catalogued"]},
    ],
)
def test_unknown_mixed_or_unconfirmed_device_configuration_has_no_actions(event_change: dict) -> None:
    event = _supported_event()
    aids = event["profile_snapshot"]["aids"]
    aids["side"] = event_change["side"]
    if "right" in event_change:
        aids["right"] = event_change["right"]
    if "left_tier" in event_change:
        aids["left"]["tier"] = event_change["left_tier"]
    if "app_version" in event_change:
        aids["app"]["version"] = event_change["app_version"]
    if "confirmed" in event_change:
        aids["app"]["confirmedActions"] = event_change["confirmed"]
    payload = build_event_input(event, {"bands": []}, [], _catalog())
    assert payload["allowed_device_actions"] == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"device_action_ids": ["not_catalogued"]},
        {"device_action_ids": ["allure_equalizer", "allure_equalizer"]},
        {"summary": ""},
        {"patient_summary": "   "},
        {"observations": ["   "]},
        {"recommendations": ["Ask about the reported event."]},
        {"recommendations": [{"text": "   ", "evidence_refs": ["reported_event"]}]},
        {"recommendations": [{"text": "Ask about the event.", "evidence_refs": []}]},
        {"recommendations": [{
            "text": "Increase gain by two decibels.",
            "evidence_refs": ["reported_event"],
        }]},
        {"recommendations": [{
            "text": "Ask about the reported event.",
            "evidence_refs": ["not_available"],
        }]},
        {"recommendations": [{
            "text": "Review the two thousand hertz region.",
            "evidence_refs": ["band:0", "band:0"],
        }]},
        {"recommendations": [{
            "text": "Review the 2 kHz region.",
            "evidence_refs": ["band:0"],
        }]},
        {"limitations": ["Speech estimate was 80%"]},
        {"limitations": ["Speech estimate was ٢"]},
        {"observations": ["Estimated SNR was poor and intelligibility was low."]},
        {"summary": "The professional fitting settings should be adjusted."},
        {"frequency_notes": [{"band_index": 0, "explanation": " ", "review_question": "Useful?"}]},
        {"frequency_notes": [{"band_index": 0, "explanation": "Useful?", "review_question": " "}]},
        {"frequency_notes": [{"band_index": 1, "explanation": "x", "review_question": "y"}]},
        {"frequency_notes": [
            {"band_index": 0, "explanation": "x", "review_question": "y"},
            {"band_index": 0, "explanation": "z", "review_question": "q"},
        ]},
    ],
)
def test_unknown_actions_and_impossible_or_duplicate_band_indices_fail_closed(
    monkeypatch: pytest.MonkeyPatch, overrides: dict,
) -> None:
    payload = build_event_input(
        _supported_event(),
        {"bands": [{"low_hz": 250, "high_hz": 500, "relative_energy": 0.25}]},
        [],
        _catalog(),
    )

    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 500})
        return httpx.Response(200, json={
            "id": "resp_bad",
            "status": "completed",
            "service_tier": "default",
            "output_text": json.dumps(_v2_output(**overrides)),
            "usage": {
                "input_tokens": 500,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens": 100,
            },
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    with pytest.raises(AmbiguousProviderFailure, match="invalid structured result"):
        client.interpret(client.prepare(payload), "event:test:v2")


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
                "service_tier": "default",
                "output_text": json.dumps(_v2_output(tip_ids=["quieter_place"])),
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 20},
                    "output_tokens": 50,
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("test-key")
    prepared = client.prepare({
        "bounded": True,
        "allowed_device_actions": [],
        "phone_audio_measurements": {},
    })
    result = client.interpret(prepared, "event:test:v2")
    body = __import__("json").loads(captured[1]["content"])
    assert body["model"] == "gpt-6-astra"
    assert body["service_tier"] == "default"
    assert body["reasoning"] == {"effort": "low"}
    assert body["tools"] == []
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["max_output_tokens"] == 1_200
    assert result.result["tip_ids"] == ["quieter_place"]
    assert result.actual_cost_usd == Decimal("0.003460")
    assert result.usage["request_body_bytes"] <= MAX_REQUEST_BODY_BYTES
    assert result.usage["preflight_input_tokens"] == 321
    assert captured[0]["url"].endswith("/responses/input_tokens")
    assert captured[1]["url"].endswith("/responses")
    assert captured[0]["content"] == captured[1]["content"]
    assert PROMPT_VERSION == "ihear-event-v2"
    assert set(OUTPUT_SCHEMA["required"]) == set(OUTPUT_SCHEMA["properties"])
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    assert OUTPUT_SCHEMA["properties"]["frequency_notes"]["items"]["additionalProperties"] is False
    assert OUTPUT_SCHEMA["properties"]["recommendations"]["items"]["additionalProperties"] is False
    for prose_schema in (
        OUTPUT_SCHEMA["properties"]["summary"],
        OUTPUT_SCHEMA["properties"]["observations"]["items"],
        OUTPUT_SCHEMA["properties"]["limitations"]["items"],
        OUTPUT_SCHEMA["properties"]["recommendations"]["items"]["properties"]["text"],
        OUTPUT_SCHEMA["properties"]["frequency_notes"]["items"]["properties"]["explanation"],
        OUTPUT_SCHEMA["properties"]["frequency_notes"]["items"]["properties"]["review_question"],
        OUTPUT_SCHEMA["properties"]["patient_summary"],
    ):
        assert prose_schema["minLength"] == 1
        assert prose_schema["pattern"] == "^[^0-9%]*$"


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
    prepared = client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}})
    with pytest.raises(AmbiguousProviderFailure, match="retry is forbidden"):
        client.interpret(prepared, "event:test:v2")
    assert calls == 2


@pytest.mark.parametrize("status_code", [408, 409, 418, 425])
def test_generation_uncertain_http_status_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch, status_code: int,
) -> None:
    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        return httpx.Response(status_code)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    prepared = client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}})
    with pytest.raises(AmbiguousProviderFailure, match="outcome is unknown"):
        client.interpret(prepared, "event:test:v2")


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 413, 422])
def test_known_pre_inference_generation_rejections_are_definitive(
    monkeypatch: pytest.MonkeyPatch, status_code: int,
) -> None:
    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        return httpx.Response(status_code)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    prepared = client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}})
    with pytest.raises(AstraRejected, match=f"HTTP {status_code}"):
        client.interpret(prepared, "event:test:v2")


@pytest.mark.parametrize(
    "provider_response",
    [
        {"id": "resp_incomplete", "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
        {
            "id": "resp_refusal",
            "status": "completed",
            "service_tier": "default",
            "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "Cannot help."}]}],
        },
        {"id": "resp_malformed", "status": "completed", "service_tier": "default", "output_text": "{"},
    ],
)
def test_incomplete_refusal_and_malformed_output_fail_closed(
    monkeypatch: pytest.MonkeyPatch, provider_response: dict,
) -> None:
    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        return httpx.Response(200, json=provider_response)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    with pytest.raises(AmbiguousProviderFailure):
        client.interpret(client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}}), "event:test:v2")


def test_nonstandard_or_unconfirmed_service_tier_fails_cost_accounting_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 100})
        return httpx.Response(200, json={
            "id": "resp_priority",
            "status": "completed",
            "service_tier": "priority",
            "output_text": json.dumps(_v2_output()),
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    with pytest.raises(AmbiguousProviderFailure, match="standard service tier"):
        client.interpret(client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}}), "event:test:v2")


def test_complete_six_band_request_preserves_normal_evidence_inside_exact_envelope() -> None:
    event = _supported_event()
    event["profile_snapshot"].update({
        "audiogram": {
            "frequencies": [250, 500, 1000, 2000, 4000, 8000],
            "left": [20, 25, 35, 40, 50, 55],
            "right": [20, 25, 30, 40, 45, 50],
        },
        "note": (
            "Synthetic hearing evaluation: difficulty following television dialogue; "
            "no speech recognition test supplied."
        ),
    })
    event["profile_snapshot"]["aids"]["app"]["confirmedActions"] = [
        "allure_equalizer", "allure_programs",
    ]
    analysis = {
        "duration_seconds": 10.0,
        "sample_rate": 48_000,
        "rms_dbfs": -24.5,
        "peak_dbfs": -8.0,
        "clipping_fraction": 0.0,
        "silent": False,
        "quality_flags": [],
        "spectral_centroid_hz": 1800,
        "bands": [
            {"low_hz": low, "high_hz": high, "relative_energy": energy}
            for low, high, energy in (
                (80, 250, 0.04), (250, 500, 0.08), (500, 1000, 0.18),
                (1000, 2000, 0.28), (2000, 4000, 0.32), (4000, 8000, 0.10),
            )
        ],
        "speech_activity": {
            "status": "ready", "fraction": 0.7, "model": "silero-vad", "version": "fixture",
        },
        "acoustic_categories": {
            "status": "ready", "model": "yamnet", "version": "fixture",
            "categories": [{"label": "Speech", "score": 0.6}, {"label": "Music", "score": 0.3}],
        },
    }
    catalog = _catalog()
    catalog["facts"] = [{
        "fact": "The manufacturer identifies ALLURE BTE R D as a rechargeable behind-the-ear hearing aid.",
        "verificationStatus": "verified_manufacturer_description",
    }]
    catalog["appActions"].append({
        "id": "allure_programs",
        "title": "Compare available listening programs",
        "instruction": "Use only programs already available in the patient's app.",
        "source": "https://www.widex.com/example",
        "checkedAt": "2026-09-13",
        "supportedModels": ["Widex ALLURE BTE R D"],
        "verificationStatus": "verified_app_control_requires_confirmation",
    })

    payload = build_event_input(event, analysis, [], catalog)
    body, encoded = prepare_request(payload)
    submitted = json.loads(body["input"])

    assert len(encoded) <= MAX_REQUEST_BODY_BYTES
    assert submitted["profile"]["note"] == event["profile_snapshot"]["note"]
    assert submitted["profile"]["audiogram"] == event["profile_snapshot"]["audiogram"]
    assert len(submitted["phone_audio_measurements"]["bands"]) == 6
    assert [item["id"] for item in submitted["allowed_device_actions"]] == [
        "allure_equalizer", "allure_programs",
    ]
    assert submitted["input_coverage"]["profile_note"] == {
        "source_characters": len(event["profile_snapshot"]["note"]),
        "sent_characters": len(event["profile_snapshot"]["note"]),
    }
    assert {
        "reported_event", "audiogram", "clinician_note", "phone_audio",
        "speech_estimate", "sound_categories", "band:0", "band:5",
    } <= set(submitted["available_evidence_refs"])


def test_unicode_rich_profile_and_history_remain_inside_exact_six_kilobyte_body() -> None:
    event = _supported_event()
    event["profile_snapshot"]["note"] = "Žluťoučký pacient 🦻 " * 80
    analysis = {
        "duration_seconds": 10,
        "sample_rate": 48_000,
        "rms_dbfs": -24.0,
        "peak_dbfs": -5.0,
        "clipping_fraction": 0.01,
        "spectral_centroid_hz": 1800,
        "quality_flags": ["weak_digital_signal"],
        "bands": [
            {"low_hz": index * 250, "high_hz": (index + 1) * 250, "relative_energy": 0.125}
            for index in range(8)
        ],
        "speech_activity": {"status": "ready", "fraction": 0.5, "model": "Silero", "version": "6.2.1"},
        "acoustic_categories": {
            "status": "ready", "model": "YAMNet", "version": "1",
            "categories": [{"label": "Speech", "score": 0.8}],
        },
    }
    history = [{
        "kind": "difficult",
        "difficulty": "Řeč v hluku 🦻 " * 10,
        "environment": "Kavárna",
        "captured_at": "2026-09-13T08:00:00Z",
        "analysis": analysis,
    } for _ in range(20)]
    payload = build_event_input(event, analysis, history, _catalog())
    body, encoded = prepare_request(payload)
    submitted_input = json.loads(body["input"])
    assert len(encoded) <= MAX_REQUEST_BODY_BYTES
    assert submitted_input["reported_event"]["difficulty"] == "Following one person"
    assert submitted_input["phone_audio_measurements"]["bands"]
    assert len(submitted_input["prior_events"]) < 20
    coverage = submitted_input["input_coverage"]
    assert coverage["profile_note"]["sent_characters"] < coverage["profile_note"]["source_characters"]
    assert coverage["prior_events"] == {"source_events": 20, "sent_events": 0}
    refs = set(submitted_input["available_evidence_refs"])
    assert {"reported_event", "phone_audio", "speech_estimate", "sound_categories", "band:0", "band:7"} <= refs
    assert "prior_events" not in refs
    assert ("clinician_note" in refs) is (coverage["profile_note"]["sent_characters"] > 0)


def test_input_reduction_adds_deterministic_limitation_after_valid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _supported_event()
    event["profile_snapshot"]["note"] = "Clinical context " * 100
    payload = build_event_input(event, {"bands": []}, [], _catalog())

    def fake_post(url, **kwargs):
        if url.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 500})
        return httpx.Response(200, json={
            "id": "resp_bounded",
            "status": "completed",
            "service_tier": "default",
            "output_text": json.dumps(_v2_output(limitations=["One", "Two", "Three", "Four"])),
            "usage": {
                "input_tokens": 500,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens": 100,
            },
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("fixture-key")
    result = client.interpret(client.prepare(payload), "event:test:v2")
    assert len(result.result["limitations"]) == 4
    assert result.result["limitations"][-1].startswith("Input coverage was bounded")
    assert "clinician-note characters" in result.result["limitations"][-1]


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
                "service_tier": "default",
                "output_text": json.dumps(_v2_output()),
                "usage": {
                    "input_tokens": 8_001,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 8_001},
                    "output_tokens": 1_200,
                },
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("test-key")
    prepared = client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}})
    with pytest.raises(AstraCostExceeded) as caught:
        client.interpret(prepared, "event:test:v2")
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
                "service_tier": "default",
                "output_text": json.dumps(_v2_output()),
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AstraClient("test-key")
    prepared = client.prepare({"allowed_device_actions": [], "phone_audio_measurements": {}})
    with pytest.raises(AmbiguousProviderFailure, match="invalid usage accounting"):
        client.interpret(prepared, "event:test:v2")
