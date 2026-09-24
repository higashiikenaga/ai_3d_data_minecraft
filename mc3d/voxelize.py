"""Convert a (textured) 3D mesh into a colored voxel grid.

The mesh surface is densely sampled; every sample carries a color taken from
the texture, vertex colors, face colors or material. Samples are binned into
voxels and their colors averaged, which yields the surface shell. Optionally
the enclosed interior is filled as well.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from PIL import Image

DEFAULT_COLOR = np.array([180.0, 180.0, 180.0])


@dataclass
class VoxelGrid:
    occupancy: np.ndarray  # (X, Y, Z) bool, Y is up
    colors: np.ndarray  # (X, Y, Z, 3) float RGB 0-255

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.occupancy.shape  # type: ignore[return-value]

    @property
    def count(self) -> int:
        return int(self.occupancy.sum())


def load_meshes(path: str, up_axis: str = "y") -> list[trimesh.Trimesh]:
    """Load all meshes of a file with scene transforms applied, rotated so +Y is up."""
    loaded = trimesh.load(path, process=False)
    meshes: list[trimesh.Trimesh] = []
    if isinstance(loaded, trimesh.Scene):
        for node in loaded.graph.nodes_geometry:
            transform, geom_name = loaded.graph[node]
            geom = loaded.geometry[geom_name]
            if not isinstance(geom, trimesh.Trimesh) or len(geom.faces) == 0:
                continue
            mesh = geom.copy()
            mesh.apply_transform(transform)
            meshes.append(mesh)
    elif isinstance(loaded, trimesh.Trimesh):
        meshes.append(loaded)
    if not meshes:
        raise ValueError(f"No triangle meshes found in {path}")

    rotation = _up_axis_rotation(up_axis)
    if rotation is not None:
        for mesh in meshes:
            mesh.apply_transform(rotation)
    return meshes


def _up_axis_rotation(up_axis: str) -> np.ndarray | None:
    up = up_axis.lower()
    if up == "y":
        return None
    if up == "z":  # Z-up (Blender/STL style) -> Y-up
        return trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    if up == "-z":
        return trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    if up == "x":
        return trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1])
    if up == "-y":
        return trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    raise ValueError(f"Unsupported up axis: {up_axis}")


def _material_texture(material) -> tuple[np.ndarray | None, np.ndarray]:
    """Return (texture RGBA array or None, color factor RGBA 0-1) for a trimesh material."""
    image = None
    factor = np.ones(4)
    if material is None:
        return image, factor
    tex = getattr(material, "baseColorTexture", None)
    if tex is None:
        tex = getattr(material, "image", None)
    if isinstance(tex, Image.Image):
        image = np.asarray(tex.convert("RGBA"), dtype=np.float64)
    base = getattr(material, "baseColorFactor", None)
    if base is None and image is None:
        base = getattr(material, "diffuse", None)
    if base is not None:
        base = np.asarray(base, dtype=np.float64).ravel()
        if base.max() > 1.0:
            base = base / 255.0
        factor[: len(base)] = base[:4]
    return image, factor


def _sample_colors(mesh: trimesh.Trimesh, face_idx: np.ndarray, bary: np.ndarray) -> np.ndarray:
    visual = mesh.visual
    n = len(face_idx)
    if isinstance(visual, trimesh.visual.TextureVisuals):
        image, factor = _material_texture(visual.material)
        uv = visual.uv
        if image is not None and uv is not None and len(uv) == len(mesh.vertices):
            face_uv = np.asarray(uv, dtype=np.float64)[mesh.faces[face_idx]]  # (n, 3, 2)
            p = (bary[:, :, None] * face_uv).sum(axis=1)
            h, w = image.shape[:2]
            u = np.mod(p[:, 0], 1.0)
            v = np.mod(p[:, 1], 1.0)
            x = np.clip((u * w).astype(np.int64), 0, w - 1)
            y = np.clip(((1.0 - v) * h).astype(np.int64), 0, h - 1)
            return image[y, x, :3] * factor[:3]
        return np.tile(factor[:3] * 255.0, (n, 1))
    if isinstance(visual, trimesh.visual.ColorVisuals):
        if visual.kind == "vertex":
            vc = np.asarray(visual.vertex_colors, dtype=np.float64)[:, :3]
            return (bary[:, :, None] * vc[mesh.faces[face_idx]]).sum(axis=1)
        if visual.kind == "face":
            return np.asarray(visual.face_colors, dtype=np.float64)[face_idx, :3]
    return np.tile(DEFAULT_COLOR, (n, 1))


def sample_surface(mesh: trimesh.Trimesh, count: int, rng: np.random.Generator
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Uniformly sample points on the mesh surface together with their colors."""
    areas = mesh.area_faces
    total = areas.sum()
    if count <= 0 or total <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    face_idx = rng.choice(len(areas), size=count, p=areas / total)
    r1 = np.sqrt(rng.random(count))
    r2 = rng.random(count)
    bary = np.stack([1.0 - r1, r1 * (1.0 - r2), r1 * r2], axis=1)
    tri = mesh.triangles[face_idx]
    points = (bary[:, :, None] * tri).sum(axis=1)
    return points, _sample_colors(mesh, face_idx, bary)


def voxelize(meshes: list[trimesh.Trimesh], size: int = 64, fit: str = "max",
             fill: bool = False, density: float = 8.0, seed: int = 0,
             max_samples: int = 20_000_000) -> VoxelGrid:
    """Voxelize meshes so that the chosen dimension spans ``size`` blocks.

    fit: "max" scales the longest side to ``size``; "height" scales the Y extent.
    density: surface samples per voxel face area (higher = fewer holes, slower).
    """
    if size < 1:
        raise ValueError("size must be >= 1")
    lo = np.min([m.bounds[0] for m in meshes], axis=0)
    hi = np.max([m.bounds[1] for m in meshes], axis=0)
    extent = hi - lo
    ref = extent[1] if fit == "height" else extent.max()
    if ref <= 0:
        ref = extent.max()
    if ref <= 0:
        raise ValueError("Mesh has zero extent")
    voxel = ref / size
    dims = np.maximum(np.ceil(extent / voxel - 1e-9).astype(np.int64), 1)
    n_cells = int(np.prod(dims))

    rng = np.random.default_rng(seed)
    counts = np.zeros(n_cells, dtype=np.float64)
    sums = np.zeros((n_cells, 3), dtype=np.float64)
    total_area = sum(m.area for m in meshes)
    budget = min(max_samples, max(200_000, int(total_area / voxel**2 * density)))
    chunk = 1_000_000

    for mesh in meshes:
        if mesh.area <= 0:
            continue
        n_mesh = max(1, int(budget * mesh.area / total_area))
        for start in range(0, n_mesh, chunk):
            pts, cols = sample_surface(mesh, min(chunk, n_mesh - start), rng)
            idx = np.clip(np.floor((pts - lo) / voxel).astype(np.int64), 0, dims - 1)
            flat = np.ravel_multi_index(idx.T, dims)
            counts += np.bincount(flat, minlength=n_cells)
            for c in range(3):
                sums[:, c] += np.bincount(flat, weights=cols[:, c], minlength=n_cells)

    occupancy = (counts > 0).reshape(dims)
    colors = np.zeros((n_cells, 3))
    hit = counts > 0
    colors[hit] = sums[hit] / counts[hit, None]
    colors = colors.reshape(*dims, 3)

    if fill:
        occupancy, colors = fill_interior(occupancy, colors)
    return VoxelGrid(occupancy, colors)


def fill_interior(occupancy: np.ndarray, colors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fill enclosed cavities; new voxels copy the color of the nearest surface voxel."""
    from scipy import ndimage

    filled = ndimage.binary_fill_holes(occupancy)
    added = filled & ~occupancy
    if added.any():
        _, nearest = ndimage.distance_transform_edt(~occupancy, return_indices=True)
        colors = colors.copy()
        src = tuple(nearest[i][added] for i in range(3))
        colors[added] = colors[src]
    return filled, colors


def mesh_to_voxels(path: str, size: int = 64, fit: str = "max", fill: bool = False,
                   up_axis: str = "y", density: float = 8.0, seed: int = 0) -> VoxelGrid:
    return voxelize(load_meshes(path, up_axis), size=size, fit=fit, fill=fill,
                    density=density, seed=seed)
