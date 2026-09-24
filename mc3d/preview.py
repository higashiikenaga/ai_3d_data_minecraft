"""Render simple orthographic previews (front / side / top) of a block grid."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _project(ids: np.ndarray, colors: np.ndarray, axis: int, reverse: bool) -> np.ndarray:
    """Color of the first visible block looking along ``axis``; returns (A, B, 4)."""
    occ = ids >= 0
    if reverse:
        occ = np.flip(occ, axis)
        ids = np.flip(ids, axis)
    first = occ.argmax(axis=axis)
    visible = occ.any(axis=axis)
    picked = np.take_along_axis(ids, np.expand_dims(first, axis), axis).squeeze(axis)
    rgba = np.zeros(picked.shape + (4,), dtype=np.uint8)
    rgba[visible, :3] = colors[picked[visible]]
    rgba[visible, 3] = 255
    return rgba


def render_preview(block_ids: np.ndarray, palette_rgb: np.ndarray, path: str,
                   scale: int | None = None) -> None:
    x, y, z = block_ids.shape
    # front: look along +Z -> image (Y, X); side: along +X -> (Y, Z); top: along -Y -> (Z, X)
    front = _project(block_ids, palette_rgb, 2, False).transpose(1, 0, 2)[::-1]
    side = _project(block_ids, palette_rgb, 0, False)[::-1]
    top = _project(block_ids, palette_rgb, 1, True).transpose(1, 0, 2)
    views = [front, side, top]
    if scale is None:
        scale = max(1, 256 // max(x, y, z))
    gap = 4
    height = max(v.shape[0] for v in views) * scale
    width = sum(v.shape[1] * scale for v in views) + gap * (len(views) - 1)
    canvas = Image.new("RGBA", (width, height), (40, 40, 48, 255))
    cursor = 0
    for view in views:
        img = Image.fromarray(view, "RGBA").resize(
            (view.shape[1] * scale, view.shape[0] * scale), Image.NEAREST)
        canvas.alpha_composite(img, (cursor, height - img.height))
        cursor += img.width + gap
    canvas.save(path)
