"""Helpers for calling Hugging Face Spaces through gradio_client.

Space APIs change over time, so parameters are filtered against the live API
schema: unknown keyword arguments are dropped and missing ones keep defaults.
"""

from __future__ import annotations

import os
from typing import Any

MODEL_EXTS = (".glb", ".gltf", ".obj", ".ply", ".stl", ".off")


def get_client(space: str, hf_token: str | None = None):
    try:
        from gradio_client import Client
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("gradio_client is required: pip install gradio_client") from e
    token = hf_token or os.environ.get("HF_TOKEN") or None
    try:
        return Client(space, token=token, verbose=False)
    except TypeError:  # older gradio_client uses hf_token
        return Client(space, hf_token=token, verbose=False)


def _api_info(client) -> dict | None:
    try:
        return client.view_api(return_format="dict", print_info=False) or {}
    except Exception:
        return None


def list_endpoints(client) -> list[str] | None:
    """Names of the Space's named endpoints, or None if the schema is unavailable."""
    info = _api_info(client)
    if info is None:
        return None
    return list(info.get("named_endpoints", {}))


def pick_endpoint(client, candidates: tuple[str, ...]) -> str:
    """Return the first candidate endpoint the Space actually exposes."""
    available = list_endpoints(client)
    if available is None:
        return candidates[0]
    for name in candidates:
        if name in available:
            return name
    raise RuntimeError(f"none of {', '.join(candidates)} found; "
                       f"Space exposes: {', '.join(available) or '(nothing)'}")


def endpoint_params(client, api_name: str) -> list[dict] | None:
    """Return the parameter descriptions of an endpoint, or None if unavailable."""
    info = _api_info(client)
    if info is None:
        return None
    endpoint = info.get("named_endpoints", {}).get(api_name)
    if endpoint is None:
        return None
    return endpoint.get("parameters", [])


def _is_image_param(param: dict) -> bool:
    component = str(param.get("component", "")).lower()
    return component == "image"


def call_endpoint(client, api_name: str, kwargs: dict[str, Any],
                  image: Any = None) -> Any:
    params = endpoint_params(client, api_name)
    call_kwargs = dict(kwargs)
    if params is not None:
        names = [p.get("parameter_name") for p in params]
        call_kwargs = {k: v for k, v in kwargs.items() if k in names}
        if image is not None:
            image_params = [p["parameter_name"] for p in params if _is_image_param(p)]
            target = next((n for n in ("image", "input_image") if n in names), None)
            target = target or (image_params[0] if image_params else None)
            if target is None:
                raise RuntimeError(f"{api_name} has no image parameter: {names}")
            call_kwargs[target] = image
    elif image is not None:
        call_kwargs.setdefault("image", image)
    return client.predict(api_name=api_name, **call_kwargs)


def call_space(space: str, api_name: str, kwargs: dict[str, Any],
               hf_token: str | None = None, image: Any = None) -> Any:
    return call_endpoint(get_client(space, hf_token), api_name, kwargs, image)


def find_files(result: Any, exts: tuple[str, ...]) -> list[str]:
    """Recursively collect existing file paths with the given extensions from a result."""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if value.lower().endswith(exts) and os.path.exists(value):
                found.append(value)
        elif isinstance(value, dict):
            for key in ("value", "path", "name"):
                if key in value:
                    walk(value[key])
            for v in value.values():
                if isinstance(v, (list, tuple, dict)):
                    walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    walk(result)
    return list(dict.fromkeys(found))


def describe_space(space: str, hf_token: str | None = None) -> str:
    client = get_client(space, hf_token)
    return str(client.view_api(print_info=False))
