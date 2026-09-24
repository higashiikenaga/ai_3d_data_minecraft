"""End-to-end pipeline: text → image → 3D model → voxels → .schem."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from .blocks import DEFAULT_MC_VERSION, build_palette
from .preview import render_preview
from .schem import write_schem
from .voxelize import mesh_to_voxels


@dataclass
class ConvertOptions:
    size: int = 64
    fit: str = "max"  # "max" or "height"
    fill: bool = False
    up_axis: str = "y"
    palette_groups: list[str] | None = None
    exclude: list[str] = field(default_factory=list)
    mc_version: str = DEFAULT_MC_VERSION
    density: float = 8.0
    center: bool = True
    preview: bool = True
    seed: int = 0


@dataclass
class ConvertResult:
    schem_path: str
    preview_path: str | None
    shape: tuple[int, int, int]
    block_count: int
    block_usage: dict[str, int]


def model_to_schem(model_path: str, schem_path: str, opts: ConvertOptions,
                   log=print) -> ConvertResult:
    log(f"[voxelize] {model_path} → size {opts.size} ({opts.fit})")
    grid = mesh_to_voxels(model_path, size=opts.size, fit=opts.fit, fill=opts.fill,
                          up_axis=opts.up_axis, density=opts.density, seed=opts.seed)
    palette = build_palette(opts.palette_groups, opts.mc_version, opts.exclude)
    block_ids = np.full(grid.shape, -1, dtype=np.int64)
    block_ids[grid.occupancy] = palette.match(grid.colors[grid.occupancy])

    write_schem(schem_path, block_ids, palette.names, opts.mc_version, opts.center)
    x, y, z = grid.shape
    log(f"[schem] {schem_path}: {x}x{y}x{z}, {grid.count} blocks")

    preview_path = None
    if opts.preview:
        preview_path = os.path.splitext(schem_path)[0] + "_preview.png"
        render_preview(block_ids, palette.rgb, preview_path)
        log(f"[preview] {preview_path}")

    ids, counts = np.unique(block_ids[block_ids >= 0], return_counts=True)
    usage = {palette.names[i]: int(c) for i, c in sorted(zip(ids, counts), key=lambda t: -t[1])}
    return ConvertResult(schem_path, preview_path, grid.shape, grid.count, usage)


def image_to_schem(image_path: str, schem_path: str, opts: ConvertOptions,
                   backend: str = "auto", hf_token: str | None = None, log=print) -> ConvertResult:
    from .ai.image_to_3d import generate_model

    stem = os.path.splitext(schem_path)[0]
    model = generate_model(image_path, stem + "_model", backend=backend, seed=opts.seed,
                           hf_token=hf_token, log=log)
    log(f"[image→3D] saved {model}")
    return model_to_schem(model, schem_path, opts, log=log)


def text_to_schem(prompt: str, schem_path: str, opts: ConvertOptions,
                  image_backend: str = "auto", model_backend: str = "auto",
                  hf_token: str | None = None, raw_prompt: bool = False,
                  log=print) -> ConvertResult:
    from .ai.text_to_image import generate_image

    stem = os.path.splitext(schem_path)[0]
    image = generate_image(prompt, stem + "_image.png", backend=image_backend, seed=opts.seed,
                           hf_token=hf_token, raw_prompt=raw_prompt, log=log)
    log(f"[text→image] saved {image}")
    return image_to_schem(image, schem_path, opts, backend=model_backend,
                          hf_token=hf_token, log=log)
