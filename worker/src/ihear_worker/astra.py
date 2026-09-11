from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal, ROUND_UP
import json
import math
from typing import Any

import httpx


MODEL = "gpt-6-astra"
PROMPT_VERSION = "ihear-event-v1"
MAX_OUTPUT_TOKENS = 1200
MAX_INPUT_TOKENS_RESERVED = 8000
MAXIMUM_COST_USD = Decimal("0.160000")
# The provider counts decoded request content rather than JSON transport escapes.
# Bounding the exact submitted JSON below 6,000 UTF-8 bytes leaves 2,000 tokens
# inside the 8,000-token reservation for provider framing. A tokenizer token
# cannot represent less than one byte of submitted UTF-8 content.
MAX_REQUEST_BODY_BYTES = 6000
INPUT_TOKEN_FRAMING_MARGIN = MAX_INPUT_TOKENS_RESERVED - MAX_REQUEST_BODY_BYTES

APPROVED_TIPS = {
    "face_speaker": "If it helps, face the person you are listening to.",
    "quieter_place": "If you can, move to a quieter place.",
    "take_break": "It is okay to take a short listening break.",
    "ask_repeat": "You can ask someone to repeat or rephrase.",
    "share_clinician": "Share this moment at your next appointment.",
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "maxLength": 400},
        "observations": {
            "type": "array",
            "maxItems": 4,
            "items": {"type": "string", "maxLength": 240},
        },
        "tip_ids": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string", "enum": sorted(APPROVED_TIPS)},
        },
        "limitations": {
            "type": "array",
            "maxItems": 4,
            "items": {"type": "string", "maxLength": 240},
        },
    },
    "required": ["summary", "observations", "tip_ids", "limitations"],
}


class AstraError(RuntimeError):
    pass


class AstraUnavailable(AstraError):
    pass


class AstraRejected(AstraError):
    """The provider definitively rejected the request before inference."""


class AmbiguousProviderFailure(AstraError):
    """The request may have reached the provider and must never be repeated automatically."""


class AstraCostExceeded(AstraError):
    """A completed provider call reported more cost than the reserved envelope."""

    def __init__(
        self, actual_cost_usd: Decimal, provider_request_id: str, usage: dict[str, int],
    ) -> None:
        super().__init__(f"Provider usage exceeded reserved maximum: {actual_cost_usd}")
        self.actual_cost_usd = actual_cost_usd
        self.provider_request_id = provider_request_id
        self.usage = usage


@dataclass(frozen=True)
class AstraResult:
    result: dict[str, Any]
    actual_cost_usd: Decimal
    provider_request_id: str
    usage: dict[str, int]


@dataclass(frozen=True)
class PreparedAstraRequest:
    body: dict[str, Any]
    encoded: bytes
    input_tokens: int


def _bounded_text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()[:maximum]


def _bounded_number(value: Any, digits: int = 6) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if isinstance(value, int):
        return value
    return round(number, digits)


def build_event_input(
    event: dict[str, Any], analysis: dict[str, Any], history: list[dict[str, Any]],
    device_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = event.get("profile_snapshot") or {}
    aids = snapshot.get("aids") if isinstance(snapshot.get("aids"), dict) else {}
    safe_aids: dict[str, Any] = {"side": _bounded_text(aids.get("side"), 16)}
    catalog_name = device_catalog.get("device") if isinstance(device_catalog, dict) else None
    for side in ("left", "right"):
        device = aids.get(side)
        safe_aids[side] = (
            {
                "model": _bounded_text(device.get("model"), 80),
                "tier": _bounded_text(device.get("tier"), 32),
                "verified_family_facts": [
                    _bounded_text(fact.get("fact"), 240)
                    for fact in (device_catalog.get("facts", []) if isinstance(device_catalog, dict) else [])[:4]
                    if isinstance(fact, dict) and fact.get("verificationStatus") == "verified_manufacturer_description"
                ] if device.get("model") == catalog_name else [],
                "tier_specific_differences": "unknown",
                "routing_with_connected_phone": "unknown",
            }
            if isinstance(device, dict)
            else None
        )
    safe_history = []
    for prior in history[-20:]:
        safe_history.append(
            {
                "kind": prior.get("kind") if prior.get("kind") in ("understood", "difficult") else None,
                "difficulty": _bounded_text(prior.get("difficulty"), 80),
                "environment": _bounded_text(prior.get("environment"), 80),
                "captured_at": _bounded_text(prior.get("captured_at"), 40),
                "analysis": _bounded_analysis(prior.get("analysis") or {}),
            }
        )
    payload = {
        "event": {
            "kind": event.get("kind"),
            "difficulty": _bounded_text(event.get("difficulty"), 80),
            "environment": _bounded_text(event.get("environment"), 80),
            "captured_at": _bounded_text(event.get("captured_at"), 40),
        },
        "profile": {
            "audiogram": _bounded_audiogram(snapshot.get("audiogram")),
            "hearing_aids": safe_aids,
            "note": _bounded_text(snapshot.get("note"), 500),
        },
        "deterministic_analysis": _bounded_analysis(analysis),
        "prior_events": safe_history,
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if len(encoded) > 32_000:
        raise ValueError("Bounded Astra input unexpectedly exceeds 32 KB")
    return payload


def _bounded_audiogram(value: Any) -> dict[str, list[float]] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, list[float]] = {}
    for key in ("frequencies", "left", "right"):
        numbers = value.get(key)
        if not isinstance(numbers, list):
            return None
        result[key] = [round(float(item), 2) for item in numbers[:16] if isinstance(item, (int, float))]
    return result


def _bounded_analysis(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "duration_seconds", "sample_rate", "rms_dbfs", "peak_dbfs",
        "clipping_fraction", "spectral_centroid_hz",
    ):
        number = _bounded_number(value.get(key))
        if number is not None:
            result[key] = number
    if isinstance(value.get("silent"), bool):
        result["silent"] = value["silent"]
    flags = value.get("quality_flags")
    if isinstance(flags, list):
        result["quality_flags"] = [
            text for item in flags[:8] if (text := _bounded_text(item, 64))
        ]
    bands = value.get("bands")
    if isinstance(bands, list):
        result["bands"] = [
            {
                key: number
                for key in ("low_hz", "high_hz", "relative_energy")
                if (number := _bounded_number(item.get(key))) is not None
            }
            for item in bands[:8] if isinstance(item, dict)
        ]
    speech = value.get("speech_activity")
    if isinstance(speech, dict):
        result["speech_activity"] = {
            **{
                key: text
                for key, limit in (("status", 32), ("model", 40), ("version", 24))
                if (text := _bounded_text(speech.get(key), limit))
            },
            **{
                key: number
                for key in ("fraction", "mean_probability", "threshold", "sample_rate")
                if (number := _bounded_number(speech.get(key))) is not None
            },
        }
    categories = value.get("acoustic_categories")
    if isinstance(categories, dict):
        safe_categories = []
        for item in (categories.get("categories") or [])[:5]:
            if not isinstance(item, dict):
                continue
            label = _bounded_text(item.get("label"), 80)
            score = _bounded_number(item.get("score"))
            if label and score is not None:
                safe_categories.append({"label": label, "score": score})
        result["acoustic_categories"] = {
            **{
                key: text
                for key, limit in (("status", 32), ("model", 40), ("version", 24))
                if (text := _bounded_text(categories.get(key), limit))
            },
            "categories": safe_categories,
        }
    return result


def _request_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "reasoning": {"effort": "low"},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
        "tools": [],
        "instructions": (
            "You summarize bounded listening-event evidence for a clinician. "
            "Never diagnose, prescribe settings, infer transcripts or speaker identity, compare dBFS with dB HL, "
            "invent device capabilities, or claim calibrated loudness. Distinguish measurements, model estimates, "
            "and patient feedback. Return only the supplied schema."
        ),
        "input": json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ihear_event_interpretation",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    }


def prepare_request(payload: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """Build the exact HTTP body and keep it inside the pre-reserved cost envelope."""
    bounded_payload = copy.deepcopy(payload)
    while True:
        body = _request_body(bounded_payload)
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(encoded) <= MAX_REQUEST_BODY_BYTES:
            return body, encoded
        history = bounded_payload.get("prior_events")
        if isinstance(history, list) and history:
            del history[0]
            continue
        raise AstraRejected(
            f"Astra request exceeds the {MAX_REQUEST_BODY_BYTES}-byte reserved input envelope"
        )


def _calculate_cost_unchecked(usage: dict[str, Any]) -> tuple[Decimal, dict[str, int]]:
    if not isinstance(usage, dict):
        raise ValueError("usage must be an object")
    input_tokens = _required_usage_integer(usage, "input_tokens")
    output_tokens = _required_usage_integer(usage, "output_tokens")
    details = usage.get("input_tokens_details")
    if not isinstance(details, dict):
        raise ValueError("input_tokens_details must be an object")
    cached_tokens = _required_usage_integer(details, "cached_tokens")
    cache_write_tokens = _required_usage_integer(details, "cache_write_tokens")
    if cached_tokens + cache_write_tokens > input_tokens:
        raise ValueError("cached and cache-write input tokens exceed total input tokens")
    uncached_tokens = input_tokens - cached_tokens - cache_write_tokens
    cost = (
        Decimal(uncached_tokens) * Decimal("10")
        + Decimal(cached_tokens) * Decimal("1")
        + Decimal(cache_write_tokens) * Decimal("12.5")
        + Decimal(output_tokens) * Decimal("50")
    ) / Decimal(1_000_000)
    rounded = cost.quantize(Decimal("0.000001"), rounding=ROUND_UP)
    return rounded, {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "cache_write_input_tokens": cache_write_tokens,
        "output_tokens_including_reasoning": output_tokens,
    }


def _required_usage_integer(value: dict[str, Any], key: str) -> int:
    number = value.get(key)
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return number


def calculate_cost(usage: dict[str, Any]) -> tuple[Decimal, dict[str, int]]:
    try:
        rounded, normalized = _calculate_cost_unchecked(usage)
    except (TypeError, ValueError) as exc:
        raise AstraError("Provider usage accounting is invalid") from exc
    if rounded > MAXIMUM_COST_USD:
        raise AstraError(f"Provider usage exceeded reserved maximum: {rounded}")
    return rounded, normalized


class AstraClient:
    def __init__(self, api_key: str | None, base_url: str = "https://api.openai.com/v1"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def prepare(
        self, payload: dict[str, Any],
        prepared_request: tuple[dict[str, Any], bytes] | None = None,
    ) -> PreparedAstraRequest:
        if not self._api_key:
            raise AstraUnavailable("OPENAI_API_KEY is not configured")
        body, request_bytes = prepared_request or prepare_request(payload)
        try:
            response = httpx.post(
                f"{self._base_url}/responses/input_tokens",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                content=request_bytes,
                timeout=30.0,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AstraUnavailable("Astra input-token count is unavailable; generation was not attempted") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise AstraUnavailable(
                f"Astra input-token count returned HTTP {response.status_code}; generation was not attempted"
            )
        if response.status_code >= 400:
            raise AstraRejected(
                f"Astra input-token count rejected the request with HTTP {response.status_code}"
            )
        try:
            count_data = response.json()
            input_tokens = count_data["input_tokens"]
            if count_data.get("object") != "response.input_tokens":
                raise ValueError("unexpected token-count object")
            if isinstance(input_tokens, bool) or not isinstance(input_tokens, int) or input_tokens < 0:
                raise ValueError("invalid input token count")
        except (KeyError, TypeError, ValueError) as exc:
            raise AstraUnavailable("Astra input-token count response was invalid; generation was not attempted") from exc
        if input_tokens > MAX_INPUT_TOKENS_RESERVED:
            raise AstraRejected(
                f"Astra input requires {input_tokens} tokens; reserved limit is {MAX_INPUT_TOKENS_RESERVED}"
            )
        return PreparedAstraRequest(body, request_bytes, input_tokens)

    def interpret(self, request: PreparedAstraRequest, idempotency_key: str) -> AstraResult:
        if not self._api_key:
            raise AstraUnavailable("OPENAI_API_KEY is not configured")
        try:
            response = httpx.post(
                f"{self._base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                content=request.encoded,
                timeout=60.0,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AmbiguousProviderFailure("Astra request outcome is unknown; automatic retry is forbidden") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise AmbiguousProviderFailure(
                f"Astra returned {response.status_code}; reservation remains conservative and retry is forbidden"
            )
        if response.status_code >= 400:
            raise AstraRejected(f"Astra rejected the request with HTTP {response.status_code}")
        data = response.json()
        if data.get("status") != "completed":
            raise AmbiguousProviderFailure("Astra response was not completed; automatic retry is forbidden")
        output_text = data.get("output_text")
        if not output_text:
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        output_text = content.get("text")
                        break
        try:
            parsed = json.loads(output_text)
            _validate_result(parsed)
        except Exception as exc:
            raise AmbiguousProviderFailure("Astra returned an invalid structured result") from exc
        provider_request_id = data.get("id")
        if not isinstance(provider_request_id, str) or not provider_request_id.strip():
            raise AmbiguousProviderFailure(
                "Astra completed without a provider request ID; reservation remains conservative"
            )
        try:
            actual_cost, normalized_usage = _calculate_cost_unchecked(data.get("usage"))
        except (TypeError, ValueError) as exc:
            raise AmbiguousProviderFailure(
                "Astra completed with invalid usage accounting; reservation remains conservative"
            ) from exc
        normalized_usage["request_body_bytes"] = len(request.encoded)
        normalized_usage["request_body_limit_bytes"] = MAX_REQUEST_BODY_BYTES
        normalized_usage["input_tokens_reserved"] = MAX_INPUT_TOKENS_RESERVED
        normalized_usage["preflight_input_tokens"] = request.input_tokens
        if actual_cost > MAXIMUM_COST_USD:
            raise AstraCostExceeded(actual_cost, provider_request_id, normalized_usage)
        expanded = dict(parsed)
        expanded["tips"] = [APPROVED_TIPS[tip_id] for tip_id in parsed["tip_ids"]]
        return AstraResult(expanded, actual_cost, provider_request_id, normalized_usage)


def _validate_result(result: Any) -> None:
    if not isinstance(result, dict) or set(result) != set(OUTPUT_SCHEMA["required"]):
        raise ValueError("Unexpected structured output keys")
    if not isinstance(result["summary"], str) or len(result["summary"]) > 400:
        raise ValueError("Invalid summary")
    for key, maximum in (("observations", 4), ("tip_ids", 3), ("limitations", 4)):
        if not isinstance(result[key], list) or len(result[key]) > maximum:
            raise ValueError(f"Invalid {key}")
    if any(item not in APPROVED_TIPS for item in result["tip_ids"]):
        raise ValueError("Unapproved tip")
