"""Minecraft block palette and color matching.

Colors are approximate average texture colors of full, opaque blocks.
Each entry: (block state, (r, g, b), groups, minimum Minecraft version).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_V113 = (1, 13)

# fmt: off
_BLOCKS: list[tuple[str, tuple[int, int, int], tuple[str, ...], tuple[int, int]]] = [
    # Concrete
    ("minecraft:white_concrete", (207, 213, 214), ("concrete",), _V113),
    ("minecraft:orange_concrete", (224, 97, 1), ("concrete",), _V113),
    ("minecraft:magenta_concrete", (169, 48, 159), ("concrete",), _V113),
    ("minecraft:light_blue_concrete", (36, 137, 199), ("concrete",), _V113),
    ("minecraft:yellow_concrete", (241, 175, 21), ("concrete",), _V113),
    ("minecraft:lime_concrete", (94, 169, 24), ("concrete",), _V113),
    ("minecraft:pink_concrete", (214, 101, 143), ("concrete",), _V113),
    ("minecraft:gray_concrete", (55, 58, 62), ("concrete",), _V113),
    ("minecraft:light_gray_concrete", (125, 125, 115), ("concrete",), _V113),
    ("minecraft:cyan_concrete", (21, 119, 136), ("concrete",), _V113),
    ("minecraft:purple_concrete", (100, 32, 156), ("concrete",), _V113),
    ("minecraft:blue_concrete", (45, 47, 143), ("concrete",), _V113),
    ("minecraft:brown_concrete", (96, 60, 32), ("concrete",), _V113),
    ("minecraft:green_concrete", (73, 91, 36), ("concrete",), _V113),
    ("minecraft:red_concrete", (142, 33, 33), ("concrete",), _V113),
    ("minecraft:black_concrete", (8, 10, 15), ("concrete",), _V113),
    # Wool
    ("minecraft:white_wool", (234, 236, 237), ("wool",), _V113),
    ("minecraft:orange_wool", (241, 118, 20), ("wool",), _V113),
    ("minecraft:magenta_wool", (190, 69, 180), ("wool",), _V113),
    ("minecraft:light_blue_wool", (58, 175, 217), ("wool",), _V113),
    ("minecraft:yellow_wool", (249, 198, 40), ("wool",), _V113),
    ("minecraft:lime_wool", (112, 185, 26), ("wool",), _V113),
    ("minecraft:pink_wool", (238, 141, 172), ("wool",), _V113),
    ("minecraft:gray_wool", (63, 68, 72), ("wool",), _V113),
    ("minecraft:light_gray_wool", (142, 142, 135), ("wool",), _V113),
    ("minecraft:cyan_wool", (21, 138, 145), ("wool",), _V113),
    ("minecraft:purple_wool", (122, 42, 173), ("wool",), _V113),
    ("minecraft:blue_wool", (53, 57, 157), ("wool",), _V113),
    ("minecraft:brown_wool", (114, 72, 41), ("wool",), _V113),
    ("minecraft:green_wool", (85, 110, 28), ("wool",), _V113),
    ("minecraft:red_wool", (161, 39, 35), ("wool",), _V113),
    ("minecraft:black_wool", (21, 21, 26), ("wool",), _V113),
    # Terracotta
    ("minecraft:terracotta", (152, 94, 68), ("terracotta",), _V113),
    ("minecraft:white_terracotta", (210, 178, 161), ("terracotta",), _V113),
    ("minecraft:orange_terracotta", (162, 84, 38), ("terracotta",), _V113),
    ("minecraft:magenta_terracotta", (150, 88, 109), ("terracotta",), _V113),
    ("minecraft:light_blue_terracotta", (113, 109, 138), ("terracotta",), _V113),
    ("minecraft:yellow_terracotta", (186, 133, 35), ("terracotta",), _V113),
    ("minecraft:lime_terracotta", (104, 118, 53), ("terracotta",), _V113),
    ("minecraft:pink_terracotta", (162, 78, 79), ("terracotta",), _V113),
    ("minecraft:gray_terracotta", (58, 42, 36), ("terracotta",), _V113),
    ("minecraft:light_gray_terracotta", (135, 107, 98), ("terracotta",), _V113),
    ("minecraft:cyan_terracotta", (87, 91, 91), ("terracotta",), _V113),
    ("minecraft:purple_terracotta", (118, 70, 86), ("terracotta",), _V113),
    ("minecraft:blue_terracotta", (74, 60, 91), ("terracotta",), _V113),
    ("minecraft:brown_terracotta", (77, 51, 36), ("terracotta",), _V113),
    ("minecraft:green_terracotta", (76, 83, 42), ("terracotta",), _V113),
    ("minecraft:red_terracotta", (143, 61, 47), ("terracotta",), _V113),
    ("minecraft:black_terracotta", (37, 23, 17), ("terracotta",), _V113),
    # Stone & natural
    ("minecraft:stone", (126, 126, 126), ("natural",), _V113),
    ("minecraft:smooth_stone", (159, 159, 159), ("natural",), _V113),
    ("minecraft:cobblestone", (128, 127, 128), ("natural",), _V113),
    ("minecraft:andesite", (136, 136, 137), ("natural",), _V113),
    ("minecraft:diorite", (189, 188, 189), ("natural",), _V113),
    ("minecraft:granite", (149, 103, 86), ("natural",), _V113),
    ("minecraft:deepslate[axis=y]", (80, 80, 82), ("natural",), (1, 17)),
    ("minecraft:blackstone", (42, 36, 41), ("natural",), (1, 16)),
    ("minecraft:obsidian", (15, 11, 25), ("natural",), _V113),
    ("minecraft:sandstone", (216, 203, 155), ("natural",), _V113),
    ("minecraft:red_sandstone", (186, 99, 29), ("natural",), _V113),
    ("minecraft:end_stone", (219, 222, 158), ("natural",), _V113),
    ("minecraft:dirt", (134, 96, 67), ("natural",), _V113),
    ("minecraft:packed_mud", (142, 106, 79), ("natural",), (1, 19)),
    ("minecraft:clay", (160, 166, 179), ("natural",), _V113),
    ("minecraft:snow_block", (249, 254, 254), ("natural",), _V113),
    ("minecraft:moss_block", (89, 109, 45), ("natural",), (1, 17)),
    ("minecraft:pumpkin", (198, 118, 24), ("natural",), _V113),
    ("minecraft:melon", (111, 145, 31), ("natural",), _V113),
    ("minecraft:hay_block[axis=y]", (166, 136, 38), ("natural",), _V113),
    ("minecraft:bone_block[axis=y]", (229, 225, 207), ("natural",), _V113),
    ("minecraft:prismarine", (99, 156, 151), ("natural",), _V113),
    ("minecraft:dark_prismarine", (52, 92, 76), ("natural",), _V113),
    # Planks
    ("minecraft:oak_planks", (162, 131, 79), ("wood",), _V113),
    ("minecraft:spruce_planks", (115, 85, 49), ("wood",), _V113),
    ("minecraft:birch_planks", (193, 175, 121), ("wood",), _V113),
    ("minecraft:jungle_planks", (160, 115, 81), ("wood",), _V113),
    ("minecraft:acacia_planks", (168, 90, 50), ("wood",), _V113),
    ("minecraft:dark_oak_planks", (67, 43, 20), ("wood",), _V113),
    ("minecraft:crimson_planks", (101, 49, 71), ("wood",), (1, 16)),
    ("minecraft:warped_planks", (43, 105, 99), ("wood",), (1, 16)),
    ("minecraft:mangrove_planks", (118, 54, 49), ("wood",), (1, 19)),
    ("minecraft:cherry_planks", (227, 179, 173), ("wood",), (1, 20)),
    # Building
    ("minecraft:bricks", (151, 98, 83), ("building",), _V113),
    ("minecraft:nether_bricks", (44, 21, 26), ("building",), _V113),
    ("minecraft:mud_bricks", (137, 104, 79), ("building",), (1, 19)),
    ("minecraft:quartz_block", (236, 230, 223), ("building",), _V113),
    ("minecraft:purpur_block", (170, 126, 170), ("building",), _V113),
    # Mineral
    ("minecraft:gold_block", (246, 208, 62), ("mineral",), _V113),
    ("minecraft:iron_block", (220, 220, 220), ("mineral",), _V113),
    ("minecraft:diamond_block", (98, 237, 228), ("mineral",), _V113),
    ("minecraft:emerald_block", (42, 203, 88), ("mineral",), _V113),
    ("minecraft:lapis_block", (31, 67, 140), ("mineral",), _V113),
    ("minecraft:redstone_block", (175, 24, 5), ("mineral",), _V113),
    ("minecraft:coal_block", (16, 16, 16), ("mineral",), _V113),
    ("minecraft:netherite_block", (66, 61, 63), ("mineral",), (1, 16)),
    ("minecraft:copper_block", (192, 107, 79), ("mineral",), (1, 17)),
]
# fmt: on

PALETTE_GROUPS = ("concrete", "wool", "terracotta", "natural", "wood", "building", "mineral")

# Data versions of representative Minecraft releases.
DATA_VERSIONS = {
    "1.13.2": 1631,
    "1.14.4": 1976,
    "1.15.2": 2230,
    "1.16.5": 2586,
    "1.17.1": 2730,
    "1.18.2": 2975,
    "1.19.4": 3337,
    "1.20.1": 3465,
    "1.20.4": 3700,
    "1.20.6": 3839,
    "1.21.1": 3955,
    "1.21.4": 4189,
}
DEFAULT_MC_VERSION = "1.20.1"


def parse_version(version: str) -> tuple[int, int]:
    parts = version.split(".")
    return int(parts[0]), int(parts[1])


@dataclass
class Palette:
    names: list[str]
    rgb: np.ndarray  # (N, 3) uint8

    def __post_init__(self) -> None:
        self._lab = rgb_to_lab(self.rgb.astype(np.float64))

    def match(self, colors: np.ndarray, chunk: int = 65536) -> np.ndarray:
        """Return the palette index of the nearest block for each RGB color (0-255)."""
        colors = np.asarray(colors, dtype=np.float64).reshape(-1, 3)
        result = np.empty(len(colors), dtype=np.int64)
        for start in range(0, len(colors), chunk):
            lab = rgb_to_lab(colors[start:start + chunk])
            dist = ((lab[:, None, :] - self._lab[None, :, :]) ** 2).sum(-1)
            result[start:start + chunk] = dist.argmin(1)
        return result


def build_palette(groups: list[str] | None = None, mc_version: str = DEFAULT_MC_VERSION,
                  exclude: list[str] | None = None) -> Palette:
    wanted = set(groups or PALETTE_GROUPS)
    unknown = wanted - set(PALETTE_GROUPS)
    if unknown:
        raise ValueError(f"Unknown palette group(s): {', '.join(sorted(unknown))}")
    version = parse_version(mc_version)
    excluded = {_normalize(n) for n in (exclude or [])}
    names, rgb = [], []
    for name, color, block_groups, since in _BLOCKS:
        if since > version or not wanted.intersection(block_groups):
            continue
        if _normalize(name) in excluded:
            continue
        names.append(name)
        rgb.append(color)
    if not names:
        raise ValueError("Palette is empty")
    return Palette(names, np.array(rgb, dtype=np.uint8))


def _normalize(name: str) -> str:
    name = name.split("[")[0]
    return name if ":" in name else f"minecraft:{name}"


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB colors (0-255) to CIE L*a*b* (D65)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    l = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([l, a, b], axis=-1)
