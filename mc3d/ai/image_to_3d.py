"""Image-to-3D with free Hugging Face Spaces (ZeroGPU).

Backends:
  trellis     microsoft TRELLIS  (textured GLB)
  hunyuan3d   tencent Hunyuan3D-2 (textured GLB)
  hunyuan3d21 tencent Hunyuan3D-2.1 (textured GLB)
  custom      any Space: MC3D_CUSTOM_SPACE + MC3D_CUSTOM_API (image in, 3D file out)

Anonymous use works but has a small daily GPU quota; setting HF_TOKEN
(free Hugging Face account) raises it.
"""

from __future__ import annotations

import os
import shutil

from .gradio_util import (MODEL_EXTS, call_endpoint, find_files, get_client, list_endpoints,
                          pick_endpoint)

TRELLIS_SPACE = os.environ.get("MC3D_TRELLIS_SPACE", "trellis-community/TRELLIS")
HUNYUAN_SPACE = os.environ.get("MC3D_HUNYUAN_SPACE", "tencent/Hunyuan3D-2")
HUNYUAN21_SPACE = os.environ.get("MC3D_HUNYUAN21_SPACE", "tencent/Hunyuan3D-2.1")

BACKENDS = ("trellis", "hunyuan3d", "hunyuan3d21")


def _handle(path: str):
    from gradio_client import handle_file
    return handle_file(path)


def _pick_model(result, prefer_textured: bool = True) -> str:
    files = find_files(result, MODEL_EXTS)
    if not files:
        raise RuntimeError(f"Space returned no 3D model file: {result!r}")
    if prefer_textured:
        textured = [f for f in files if "textured" in os.path.basename(f).lower()]
        if textured:
            return textured[0]
    glbs = [f for f in files if f.lower().endswith(".glb")]
    return (glbs or files)[0]


_TRELLIS_GEN = {
    "multiimages": [],
    "is_multiimage": False,
    "seed": 0,
    "ss_guidance_strength": 7.5,
    "ss_sampling_steps": 12,
    "slat_guidance_strength": 3.0,
    "slat_sampling_steps": 12,
    "multiimage_algo": "stochastic",
}
_TRELLIS_GLB = {"mesh_simplify": 0.95, "texture_size": 1024}


def trellis(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    client = get_client(TRELLIS_SPACE, hf_token)
    available = list_endpoints(client) or []
    if "/start_session" in available:
        try:
            client.predict(api_name="/start_session")
        except Exception:
            pass
    image = _handle(image_path)
    if "/preprocess_image" in available:
        log("[image→3D] trellis: preprocessing image")
        processed = call_endpoint(client, "/preprocess_image", {}, image=image)
        files = [processed] if isinstance(processed, str) else find_files(
            processed, (".png", ".jpg", ".jpeg", ".webp"))
        if files:
            image = _handle(files[0])

    gen_kwargs = dict(_TRELLIS_GEN, seed=seed)
    # Newer versions expose a single API endpoint doing generation + GLB export.
    one_shot = pick_endpoint(client, ("/generate_and_extract_glb", "/image_to_3d"))
    log(f"[image→3D] trellis: generating 3D via {one_shot} (may queue for a while)")
    if one_shot == "/generate_and_extract_glb":
        result = call_endpoint(client, one_shot, dict(gen_kwargs, **_TRELLIS_GLB), image=image)
        return _pick_model(result)
    call_endpoint(client, one_shot, gen_kwargs, image=image)
    log("[image→3D] trellis: extracting textured GLB")
    result = call_endpoint(client, pick_endpoint(client, ("/extract_glb",)), _TRELLIS_GLB)
    return _pick_model(result)


_HUNYUAN_KWARGS = {
    "caption": None,
    "steps": 30,
    "guidance_scale": 5.0,
    "octree_resolution": 256,
    "check_box_rembg": True,
    "num_chunks": 8000,
    "randomize_seed": False,
}


def _hunyuan(space: str, image_path: str, seed: int, hf_token: str | None, log) -> str:
    client = get_client(space, hf_token)
    kwargs = dict(_HUNYUAN_KWARGS, seed=seed)
    errors = []
    # Textured generation first; fall back to the (untextured) shape-only endpoint.
    for api in ("/generation_all", "/shape_generation"):
        try:
            pick_endpoint(client, (api,))
            log(f"[image→3D] {space} {api} (may queue for a while)")
            return _pick_model(call_endpoint(client, api, kwargs, image=_handle(image_path)))
        except Exception as e:
            log(f"[image→3D] {space} {api} failed: {_err(e)}")
            errors.append(f"{api}: {_err(e)}")
    raise RuntimeError("; ".join(errors))


def hunyuan3d(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    return _hunyuan(HUNYUAN_SPACE, image_path, seed, hf_token, log)


def hunyuan3d21(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    return _hunyuan(HUNYUAN21_SPACE, image_path, seed, hf_token, log)


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def custom(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    space = os.environ.get("MC3D_CUSTOM_SPACE")
    api = os.environ.get("MC3D_CUSTOM_API", "/predict")
    if not space:
        raise RuntimeError("Set MC3D_CUSTOM_SPACE (and MC3D_CUSTOM_API) to use the custom backend")
    log(f"[image→3D] custom: {space} {api}")
    client = get_client(space, hf_token)
    return _pick_model(call_endpoint(client, api, {"seed": seed}, image=_handle(image_path)))


_FUNCS = {"trellis": trellis, "hunyuan3d": hunyuan3d, "hunyuan3d21": hunyuan3d21,
          "custom": custom}


def generate_model(image_path: str, out_path_stem: str, backend: str = "auto", seed: int = 0,
                   hf_token: str | None = None, log=print) -> str:
    """Generate a 3D model from an image and copy it next to ``out_path_stem``."""
    order = BACKENDS if backend == "auto" else (backend,)
    errors = []
    for name in order:
        func = _FUNCS.get(name)
        if func is None:
            raise ValueError(f"Unknown image-to-3D backend: {name}")
        try:
            model = func(image_path, seed=seed, hf_token=hf_token, log=log)
        except Exception as e:  # try the next free backend
            log(f"[image→3D] {name} failed: {_err(e)}")
            errors.append(f"{name}: {_err(e)}")
            continue
        ext = os.path.splitext(model)[1].lower()
        out_path = out_path_stem + ext
        shutil.copyfile(model, out_path)
        return out_path
    raise RuntimeError("All image-to-3D backends failed:\n  " + "\n  ".join(errors))
