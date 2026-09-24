"""Image-to-3D with free Hugging Face Spaces (ZeroGPU).

Backends:
  trellis     microsoft TRELLIS  (textured GLB)
  hunyuan3d   tencent Hunyuan3D-2 (textured GLB)
  custom      any Space: MC3D_CUSTOM_SPACE + MC3D_CUSTOM_API (image in, 3D file out)

Anonymous use works but has a small daily GPU quota; setting HF_TOKEN
(free Hugging Face account) raises it.
"""

from __future__ import annotations

import os
import shutil

from .gradio_util import MODEL_EXTS, call_endpoint, find_files, get_client

TRELLIS_SPACE = os.environ.get("MC3D_TRELLIS_SPACE", "trellis-community/TRELLIS")
HUNYUAN_SPACE = os.environ.get("MC3D_HUNYUAN_SPACE", "tencent/Hunyuan3D-2")

BACKENDS = ("trellis", "hunyuan3d")


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


def trellis(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    client = get_client(TRELLIS_SPACE, hf_token)
    try:
        client.predict(api_name="/start_session")
    except Exception:
        pass  # older versions have no explicit session start
    log("[image→3D] trellis: preprocessing image")
    processed = call_endpoint(client, "/preprocess_image", {}, image=_handle(image_path))
    processed_path = processed if isinstance(processed, str) else find_files(
        processed, (".png", ".jpg", ".jpeg", ".webp"))[0]
    log("[image→3D] trellis: generating 3D (may queue for a while)")
    call_endpoint(client, "/image_to_3d", {
        "multiimages": [],
        "seed": seed,
        "ss_guidance_strength": 7.5,
        "ss_sampling_steps": 12,
        "slat_guidance_strength": 3.0,
        "slat_sampling_steps": 12,
        "multiimage_algo": "stochastic",
    }, image=_handle(processed_path))
    log("[image→3D] trellis: extracting textured GLB")
    result = client.predict(mesh_simplify=0.95, texture_size=1024, api_name="/extract_glb")
    return _pick_model(result)


def hunyuan3d(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    client = get_client(HUNYUAN_SPACE, hf_token)
    log("[image→3D] hunyuan3d: generating textured mesh (may queue for a while)")
    result = call_endpoint(client, "/generation_all", {
        "steps": 30,
        "guidance_scale": 5.0,
        "seed": seed,
        "octree_resolution": 256,
        "check_box_rembg": True,
        "num_chunks": 8000,
        "randomize_seed": False,
    }, image=_handle(image_path))
    return _pick_model(result)


def custom(image_path: str, seed: int = 0, hf_token: str | None = None, log=print) -> str:
    space = os.environ.get("MC3D_CUSTOM_SPACE")
    api = os.environ.get("MC3D_CUSTOM_API", "/predict")
    if not space:
        raise RuntimeError("Set MC3D_CUSTOM_SPACE (and MC3D_CUSTOM_API) to use the custom backend")
    log(f"[image→3D] custom: {space} {api}")
    client = get_client(space, hf_token)
    return _pick_model(call_endpoint(client, api, {"seed": seed}, image=_handle(image_path)))


_FUNCS = {"trellis": trellis, "hunyuan3d": hunyuan3d, "custom": custom}


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
            log(f"[image→3D] {name} failed: {e}")
            errors.append(f"{name}: {e}")
            continue
        ext = os.path.splitext(model)[1].lower()
        out_path = out_path_stem + ext
        shutil.copyfile(model, out_path)
        return out_path
    raise RuntimeError("All image-to-3D backends failed:\n  " + "\n  ".join(errors))
