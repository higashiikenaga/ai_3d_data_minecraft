"""Local GPU generation: SDXL-Turbo (text→image) and TRELLIS (image→3D).

Tuned for a single 16 GB GPU such as a Tesla V100:
  * fp16 everywhere (V100 has no bf16)
  * TRELLIS attention via xformers (flash-attn 2 does not support V100 / sm70)
  * SDXL-Turbo is moved to CPU while TRELLIS runs so both fit in 16 GB

Install TRELLIS following https://github.com/microsoft/TRELLIS (Linux / WSL2
recommended) and make sure ``import trellis`` works in this environment.
"""

from __future__ import annotations

import os
import threading

import numpy as np

os.environ.setdefault("ATTN_BACKEND", "xformers")
os.environ.setdefault("SPCONV_ALGO", "native")

TRELLIS_MODEL = os.environ.get("MC3D_TRELLIS_MODEL", "microsoft/TRELLIS-image-large")
T2I_MODEL = os.environ.get("MC3D_T2I_MODEL", "stabilityai/sdxl-turbo")

_lock = threading.Lock()
_trellis = None
_t2i = None


def _torch():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not available")
    return torch


def trellis_pipeline():
    global _trellis
    if _trellis is None:
        _torch()
        from trellis.pipelines import TrellisImageTo3DPipeline
        pipe = TrellisImageTo3DPipeline.from_pretrained(TRELLIS_MODEL)
        pipe.cuda()
        _trellis = pipe
    return _trellis


def t2i_pipeline():
    global _t2i
    if _t2i is None:
        torch = _torch()
        from diffusers import AutoPipelineForText2Image
        _t2i = AutoPipelineForText2Image.from_pretrained(
            T2I_MODEL, torch_dtype=torch.float16, variant="fp16")
    return _t2i


def text_to_image(prompt: str, out_path: str, seed: int = 0, size: int = 512,
                  steps: int = 2) -> str:
    """SDXL-Turbo: ~1 s per image on a V100."""
    torch = _torch()
    with _lock:
        pipe = t2i_pipeline().to("cuda")
        gen = torch.Generator("cuda").manual_seed(seed)
        image = pipe(prompt=prompt, num_inference_steps=steps, guidance_scale=0.0,
                     width=size, height=size, generator=gen).images[0]
        pipe.to("cpu")  # free VRAM for TRELLIS
        torch.cuda.empty_cache()
    image.save(out_path)
    return out_path


def image_to_3d(image_path: str, out_path_stem: str, seed: int = 0, steps: int = 12,
                quality: bool = False, texture_size: int = 1024) -> tuple[str, str]:
    """Run TRELLIS. Returns (model path, up axis).

    fast (default): vertex-colored mesh straight from the decoder, no texture
                    baking. Plenty for Minecraft-scale voxels.
    quality:        bake a texture to a GLB (slower, a bit sharper colors).
    """
    torch = _torch()
    from PIL import Image

    with _lock:
        pipe = trellis_pipeline()
        image = Image.open(image_path)
        formats = ["mesh", "gaussian"] if quality else ["mesh"]
        outputs = pipe.run(
            image, seed=seed, formats=formats,
            sparse_structure_sampler_params={"steps": steps, "cfg_strength": 7.5},
            slat_sampler_params={"steps": steps, "cfg_strength": 3.0},
        )
        mesh = outputs["mesh"][0]
        if quality:
            from trellis.utils import postprocessing_utils
            glb = postprocessing_utils.to_glb(outputs["gaussian"][0], mesh, simplify=0.95,
                                              texture_size=texture_size, verbose=False)
            path = out_path_stem + ".glb"
            glb.export(path)
            up = "y"  # to_glb already converts to Y-up
        else:
            path = out_path_stem + ".ply"
            _export_vertex_colored(mesh, path)
            up = "z"  # TRELLIS native space is Z-up
        del outputs
        torch.cuda.empty_cache()
    return path, up


def _export_vertex_colored(mesh, path: str) -> None:
    import trimesh

    vertices = mesh.vertices.detach().float().cpu().numpy()
    faces = mesh.faces.detach().cpu().numpy()
    attrs = getattr(mesh, "vertex_attrs", None)
    colors = None
    if attrs is not None:
        rgb = attrs[:, :3].detach().float().cpu().numpy()
        colors = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    tm = trimesh.Trimesh(vertices, faces, vertex_colors=colors, process=False)
    tm.export(path)


def warmup(text: bool = True) -> None:
    """Load models up front so the first request is fast."""
    trellis_pipeline()
    if text:
        t2i_pipeline()
