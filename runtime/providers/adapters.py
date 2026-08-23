#!/usr/bin/env python3
"""Stdlib OpenAI-compatible provider adapters with safe header handling."""

import json
import math
import os
import urllib.error
import urllib.request

from .protocol import (
    ProviderFailure,
    ProviderRequest,
    ProviderResponse,
    normalize_usage,
    normalized_entry,
    parse_rate_limit_headers,
)

APPLICATION_VERSION = "1.0"
APPLICATION_USER_AGENT = "Morpheus-AutoDev/%s" % APPLICATION_VERSION
_SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "api-key"}
_RESPONSE_HEADERS = {
    "x-provider",
    "x-request-id",
    "retry-after",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
}


def _safe_headers(headers):
    return {
        str(key): str(value)
        for key, value in (headers or {}).items()
        if str(key).lower() not in _SECRET_HEADERS
    }


def _redact_response_headers(headers):
    return {
        str(key): str(value)
        for key, value in (headers or {}).items()
        if str(key).lower() in _RESPONSE_HEADERS
    }


class ProviderAdapter:
    def __init__(self, provider, base_url, credential_env, **options):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.credential_env = credential_env
        self.options = options

    @property
    def credential(self):
        return os.environ.get(self.credential_env, "").strip()

    def _request(self, method, path, payload=None, timeout=20, headers=None):
        url = (
            path if path.startswith("http") else self.base_url + "/" + path.lstrip("/")
        )
        body = json.dumps(payload).encode() if payload is not None else None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": APPLICATION_USER_AGENT,
        }
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(_safe_headers(headers))
        if self.credential:
            request_headers["Authorization"] = "Bearer " + self.credential
        else:
            request_headers.pop("Authorization", None)
        request = urllib.request.Request(
            url, data=body, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                return json.loads(raw or "{}"), _redact_response_headers(
                    response.headers
                )
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", "replace")[:300]
            retryable = exc.code in (408, 429, 500, 502, 503, 504)
            raise ProviderFailure(
                "provider HTTP %s" % exc.code,
                status=exc.code,
                retryable=retryable,
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderFailure("provider unavailable", retryable=True) from exc
        except TimeoutError as exc:
            raise ProviderFailure(
                "provider timeout", retryable=False, uncertain=True
            ) from exc
        except ValueError as exc:
            raise ProviderFailure("provider returned invalid JSON") from exc

    def discover_models(self):
        payload, headers = self._request(
            "GET", self.options.get("discovery_path", "/models"), timeout=15
        )
        raw_models = payload.get("data", payload.get("models", []))
        entries = []
        for model in raw_models if isinstance(raw_models, list) else []:
            model = {"id": model} if isinstance(model, str) else model
            model_id = model.get("id") or model.get("name")
            if not model_id:
                continue
            entries.append(
                normalized_entry(
                    self.provider,
                    model_id,
                    self.base_url,
                    availability=True,
                    context_length=model.get(
                        "context_length", model.get("context_window", 0)
                    ),
                    supports_tools=bool(model.get("supports_tools", False)),
                    provider_metadata={"raw_model_metadata": model},
                    rate_limits=parse_rate_limit_headers(headers),
                )
            )
        return entries

    def health(self):
        try:
            self._request(
                "GET", self.options.get("discovery_path", "/models"), timeout=5
            )
            return {"state": "HEALTHY", "detail": "discovery reachable"}
        except ProviderFailure as exc:
            if exc.status in (401, 403):
                return {
                    "state": "AUTH_INVALID",
                    "detail": "provider rejected credential",
                }
            if exc.status == 429:
                return {
                    "state": "RATE_LIMITED",
                    "detail": "provider rate limited discovery",
                }
            return {"state": "UNAVAILABLE", "detail": str(exc)[:120]}

    def invoke(self, request, timeout=60):
        payload = {
            "model": request.model,
            "messages": request.messages,
            "stream": False,
        }
        response, headers = self._request(
            "POST",
            self.options.get("chat_path", "/chat/completions"),
            payload,
            timeout,
            headers={"Idempotency-Key": request.outbound_request_id}
            if request.outbound_request_id
            else None,
        )
        choices = response.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        text = message.get("content", "") if isinstance(message, dict) else ""
        actual_model = response.get("model") or ""
        usage = normalize_usage(response)
        raw_cost = response.get("cost")
        if raw_cost is None:
            actual_cost = None
        else:
            try:
                actual_cost = float(raw_cost)
            except (TypeError, ValueError):
                raise ProviderFailure("provider returned invalid cost")
            if not math.isfinite(actual_cost) or actual_cost < 0:
                raise ProviderFailure("provider returned invalid cost")
        return ProviderResponse(
            text=text if isinstance(text, str) else json.dumps(text),
            provider=self.provider,
            requested_model=request.model,
            resolved_model=actual_model,
            actual_provider=self.provider,
            actual_model=actual_model,
            provider_request_id=response.get("id") or headers.get("x-request-id", ""),
            usage=usage,
            actual_cost=actual_cost,
            response_headers=headers,
        )


class OpenRouterAdapter(ProviderAdapter):
    def discover_models(self):
        entries = super().discover_models()
        entries.append(normalized_entry(
            "openrouter", "openrouter/free", self.base_url,
            availability=True, health="HEALTHY", cost_class="FREE_HARD_STOP",
            input_price=0, output_price=0, route_exists=True,
            route_cost_proven=True, privacy_class="ALLOWED",
            usage_terms_permit=True, automatic_paid_fallback=False,
            capabilities={"RESEARCH_CAPABLE": True},
        ))
        return entries


def build_adapters():
    configs = {
        "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", {}),
        "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", {}),
        "lmstudio": (
            os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
            "",
            {},
        ),
    }
    return {
        name: (OpenRouterAdapter(name, base, env, **options)
               if name == "openrouter" else ProviderAdapter(name, base, env, **options))
        for name, (base, env, options) in configs.items()
    }
