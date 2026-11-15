"""Configurable, capability-checked image analysis through OpenCode Go only.

The public model catalog is metadata, not an inference request. Generation never
falls back to another endpoint, provider, or pay-as-you-go API automatically.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GO_MODELS_URL = "https://opencode.ai/inference/go/v1/models"
GO_CHAT_BASE_URL = "https://opencode.ai/inference/go/openai/v1"
DEFAULT_PHOTO_PROVIDER = "mimo"
DEFAULT_MODELS = {
    "kimi": "kimi-k3.1-pro",
    "mimo": "mimo-v2.6-flash",
    "minimax": "minimax-m3.1-flash",
    "deepseek": "deepseek-v4.1-flash",
}
CATALOG_MAX_AGE = 24 * 60 * 60


class PhotoProviderError(ValueError):
    """An actionable configuration, capability, or generation failure."""


def load_photo_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhotoProviderError(f"Could not read photo settings at {path}: {exc}") from exc
    if not isinstance(config, dict) or not isinstance(config.get("models", {}), dict):
        raise PhotoProviderError("Photo settings must be an object with an optional models object.")
    return config


def load_model_catalog(cache_path: Path, refresh: bool = False) -> Dict[str, Any]:
    if not refresh and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                isinstance(cache, dict)
                and isinstance(cache.get("data"), list)
                and 0 <= time.time() - float(cache.get("fetched_at", 0)) < CATALOG_MAX_AGE
            ):
                return cache
        except (OSError, ValueError, TypeError):
            pass
    request = Request(GO_MODELS_URL, headers={
        "User-Agent": "cue-crate/0.1 (local vinyl DJ assistant)",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=30) as response:
            catalog = json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise PhotoProviderError(
            "Could not verify the current OpenCode Go models. No photos were sent. "
            "Check your connection and run `photo-models --refresh` again."
        ) from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise PhotoProviderError("OpenCode Go returned an invalid model catalog. No photos were sent.")
    catalog["fetched_at"] = time.time()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    temporary.replace(cache_path)
    return catalog


def supports_images(model: Dict[str, Any]) -> bool:
    return any(str(kind).startswith("image/") for kind in model.get("modalities", {}).get("input", []))


def photo_model_settings(
    catalog: Dict[str, Any], config: Dict[str, Any],
    provider: Optional[str] = None, model_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    if provider is None:
        provider = config.get("provider", DEFAULT_PHOTO_PROVIDER)
    if not isinstance(provider, str) or provider not in DEFAULT_MODELS:
        raise PhotoProviderError(f"Unknown photo provider {provider!r}; choose {', '.join(DEFAULT_MODELS)}.")
    model_id = model_id or config.get("models", {}).get(provider) or DEFAULT_MODELS[provider]
    if not isinstance(model_id, str):
        raise PhotoProviderError("The photo model ID must be a string.")
    model = next((row for row in catalog.get("data", []) if isinstance(row, dict) and row.get("id") == model_id), None)
    if not model:
        raise PhotoProviderError(
            f"{model_id} is not in the current Go catalog. No photos were sent. "
            "Run `photo-models --refresh` and choose an available image model."
        )
    if not supports_images(model):
        raise PhotoProviderError(f"{model_id} does not advertise image input. No photos were sent.")
    transport = model.get("api", {}).get("chat-completions", {})
    if transport.get("base_url", "").rstrip("/") != GO_CHAT_BASE_URL:
        raise PhotoProviderError(
            f"{model_id} does not advertise the supported Go image chat endpoint. "
            "Choose another model; Cue Crate will not silently change routes."
        )
    try:
        token_limit = int(max_tokens if max_tokens is not None else config.get("max_tokens", 8192))
        dimension = int(config.get("max_image_dimension", 2048))
    except (TypeError, ValueError) as exc:
        raise PhotoProviderError("Photo max_tokens and max_image_dimension must be integers.") from exc
    if not 256 <= token_limit <= int(model.get("limit", {}).get("output") or 131072):
        raise PhotoProviderError("Photo max_tokens must be at least 256 and within the model's output limit.")
    if not 512 <= dimension <= 4096:
        raise PhotoProviderError("max_image_dimension must be between 512 and 4096 pixels.")
    return {
        "provider": provider, "model": model_id, "base_url": GO_CHAT_BASE_URL,
        "max_tokens": token_limit, "max_image_dimension": dimension,
        "capabilities": model.get("capabilities", {}),
        "session_id": str(uuid.uuid4()),
    }


def completion_options(settings: Dict[str, Any], prompt: str, content: list) -> Dict[str, Any]:
    capabilities = settings["capabilities"]
    options = {
        "model": settings["model"], "max_tokens": settings["max_tokens"],
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": content}],
    }
    # Recent reasoning models reject temperature even though older models used it.
    if capabilities.get("temperature"):
        options["temperature"] = 0
    if capabilities.get("structured_output"):
        options["response_format"] = {"type": "json_object"}
    if "low" in capabilities.get("reasoning", {}).get("effort", []):
        options["reasoning_effort"] = "low"
    return options


def complete_photo(api_key: str, settings: Dict[str, Any], prompt: str, content: list) -> str:
    try:
        from openai import APIError, APITimeoutError, OpenAI
    except ImportError as exc:
        raise PhotoProviderError("Install photo support with `python3 -m pip install -r requirements.txt`.") from exc
    client = OpenAI(
        api_key=api_key, base_url=settings["base_url"], timeout=120.0, max_retries=0,
        default_headers={
            "User-Agent": "cue-crate/0.1 (local vinyl DJ assistant)",
            "x-opencode-session": settings["session_id"],
        },
    )
    try:
        response = client.chat.completions.create(**completion_options(settings, prompt, content))
    except APITimeoutError as exc:
        raise PhotoProviderError(f"{settings['model']} timed out. No candidate was saved; retry or explicitly choose another Go model.") from exc
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        body = getattr(exc, "body", {})
        if isinstance(body, dict) and body.get("code") == "api_key_expired":
            raise PhotoProviderError(
                "The stored OpenCode Go API key has expired. Create a replacement key in OpenCode Console "
                "and update the dedicated Cue Crate Keychain item or local key file. Signing in again "
                "does not renew an expired key. No candidate was saved."
            ) from exc
        if status in {401, 402, 403, 429}:
            raise PhotoProviderError(
                f"OpenCode Go rejected the request (HTTP {status}). Check the subscription, key, model access, "
                "and allowance. Cue Crate did not switch to another API."
            ) from exc
        raise PhotoProviderError(f"{settings['model']} could not analyse the photo: {exc}") from exc
    if not response.choices or not response.choices[0].message.content:
        finish = response.choices[0].finish_reason if response.choices else "no choices"
        raise PhotoProviderError(
            f"{settings['model']} returned no final JSON ({finish}). No candidate was saved. "
            "If reasoning used the output allowance, increase --max-tokens."
        )
    return response.choices[0].message.content.strip()
