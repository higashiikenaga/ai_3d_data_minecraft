"""Text-to-image with free APIs.

Backends:
  pollinations  https://pollinations.ai  (no account or API key required)
  flux          FLUX.1-schnell Hugging Face Space via gradio_client (HF_TOKEN optional)
"""

from __future__ import annotations

import os
import shutil
import urllib.parse

import requests

from .gradio_util import call_space, find_files

POLLINATIONS_URL = os.environ.get("MC3D_POLLINATIONS_URL", "https://image.pollinations.ai/prompt/")
FLUX_SPACE = os.environ.get("MC3D_FLUX_SPACE", "black-forest-labs/FLUX.1-schnell")

# Image-to-3D models work best with a single, centered object on a plain background.
PROMPT_SUFFIX = (", single object, centered, full body, isometric 3D render, "
                 "plain white background, soft lighting, no shadow, high detail")

BACKENDS = ("pollinations", "flux")


def build_prompt(prompt: str, raw: bool = False) -> str:
    return prompt if raw else prompt.strip() + PROMPT_SUFFIX


def pollinations(prompt: str, out_path: str, seed: int = 0, size: int = 1024,
                 timeout: float = 180) -> str:
    url = POLLINATIONS_URL + urllib.parse.quote(prompt, safe="")
    params = {"width": size, "height": size, "seed": seed, "nologo": "true"}
    resp = requests.get(url, params=params, timeout=timeout,
                        headers={"User-Agent": "mc3d/0.1"})
    resp.raise_for_status()
    if not resp.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"Pollinations returned non-image content: {resp.text[:200]}")
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return out_path


def flux(prompt: str, out_path: str, seed: int = 0, size: int = 1024,
         hf_token: str | None = None) -> str:
    result = call_space(FLUX_SPACE, "/infer", {
        "prompt": prompt,
        "seed": seed,
        "randomize_seed": False,
        "width": size,
        "height": size,
        "num_inference_steps": 4,
    }, hf_token=hf_token)
    files = find_files(result, (".png", ".jpg", ".jpeg", ".webp"))
    if not files:
        raise RuntimeError(f"FLUX Space returned no image: {result!r}")
    shutil.copyfile(files[0], out_path)
    return out_path


def generate_image(prompt: str, out_path: str, backend: str = "auto", seed: int = 0,
                   hf_token: str | None = None, raw_prompt: bool = False,
                   log=print) -> str:
    full_prompt = build_prompt(prompt, raw_prompt)
    order = BACKENDS if backend == "auto" else (backend,)
    errors = []
    for name in order:
        log(f"[text→image] {name}: {full_prompt!r}")
        try:
            if name == "pollinations":
                return pollinations(full_prompt, out_path, seed=seed)
            if name == "flux":
                return flux(full_prompt, out_path, seed=seed, hf_token=hf_token)
            raise ValueError(f"Unknown text-to-image backend: {name}")
        except Exception as e:  # try the next free backend
            log(f"[text→image] {name} failed: {e}")
            errors.append(f"{name}: {e}")
    raise RuntimeError("All text-to-image backends failed:\n  " + "\n  ".join(errors))
