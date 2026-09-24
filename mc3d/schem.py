"""Sponge Schematic (v2) writer, readable by WorldEdit 7+ and FAWE."""

from __future__ import annotations

import numpy as np

from . import nbt
from .blocks import DATA_VERSIONS, DEFAULT_MC_VERSION

AIR = "minecraft:air"


def encode_varints(values: np.ndarray) -> bytes:
    values = np.asarray(values, dtype=np.int64).ravel()
    if values.size == 0 or values.max() < 128:
        return values.astype(np.uint8).tobytes()
    out = bytearray()
    for v in values.tolist():
        while v >= 0x80:
            out.append((v & 0x7F) | 0x80)
            v >>= 7
        out.append(v)
    return bytes(out)


def build_schematic(block_ids: np.ndarray, block_names: list[str],
                    mc_version: str = DEFAULT_MC_VERSION, center: bool = True) -> dict:
    """Build the NBT structure of a Sponge schematic v2.

    block_ids: (X, Y, Z) int array, -1 = air, otherwise index into block_names.
    center: set the WorldEdit paste offset so the build is centered on the player
            horizontally and starts at the player's feet.
    """
    if block_ids.ndim != 3:
        raise ValueError("block_ids must be a 3D array (X, Y, Z)")
    width, height, length = block_ids.shape
    if max(width, height, length) > 65535:
        raise ValueError("Schematic dimensions must be <= 65535")

    used = np.unique(block_ids[block_ids >= 0])
    palette = {AIR: 0}
    remap = np.zeros(len(block_names) + 1, dtype=np.int64)  # index 0 is for -1 (air)
    for i, idx in enumerate(used.tolist(), start=1):
        palette[block_names[idx]] = i
        remap[idx + 1] = i
    ids = remap[block_ids + 1]
    # Sponge order: index = x + z * Width + y * Width * Length
    ordered = np.transpose(ids, (1, 2, 0))

    data_version = DATA_VERSIONS.get(mc_version)
    if data_version is None:
        raise ValueError(f"Unknown Minecraft version {mc_version}; "
                         f"choose one of {', '.join(DATA_VERSIONS)}")
    offset = [-(width // 2), 0, -(length // 2)] if center else [0, 0, 0]
    return {
        "Version": nbt.Int(2),
        "DataVersion": nbt.Int(data_version),
        "Width": nbt.Short(_u16(width)),
        "Height": nbt.Short(_u16(height)),
        "Length": nbt.Short(_u16(length)),
        "Offset": nbt.IntArray([0, 0, 0]),
        "PaletteMax": nbt.Int(len(palette)),
        "Palette": {name: nbt.Int(i) for name, i in palette.items()},
        "BlockData": nbt.ByteArray(encode_varints(ordered)),
        "BlockEntities": nbt.List(nbt.TAG_COMPOUND, []),
        "Metadata": {
            "WEOffsetX": nbt.Int(offset[0]),
            "WEOffsetY": nbt.Int(offset[1]),
            "WEOffsetZ": nbt.Int(offset[2]),
        },
    }


def _u16(v: int) -> int:
    """Store an unsigned 16-bit value in a signed TAG_Short."""
    return v - 65536 if v > 32767 else v


def write_schem(path: str, block_ids: np.ndarray, block_names: list[str],
                mc_version: str = DEFAULT_MC_VERSION, center: bool = True) -> None:
    root = build_schematic(block_ids, block_names, mc_version, center)
    nbt.write_gzip(path, "Schematic", root)
