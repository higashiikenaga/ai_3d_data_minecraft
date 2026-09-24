import gzip
import io

import nbtlib
import numpy as np
import pytest
import trimesh
from PIL import Image

from mc3d import nbt
from mc3d.blocks import build_palette
from mc3d.cli import main
from mc3d.schem import build_schematic, encode_varints, write_schem
from mc3d.voxelize import load_meshes, voxelize


def decode_varints(data: bytes) -> list[int]:
    out, value, shift = [], 0, 0
    for b in data:
        value |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
        else:
            out.append(value)
            value, shift = 0, 0
    return out


def read_schem(path):
    with gzip.open(path, "rb") as f:
        return nbtlib.File.parse(io.BytesIO(f.read()))


def test_varints_roundtrip():
    values = np.array([0, 1, 127, 128, 300, 16384, 5])
    assert decode_varints(encode_varints(values)) == values.tolist()


def test_nbt_readable_by_nbtlib():
    data = nbt.encode("Root", {"a": nbt.Short(-3), "b": "hé", "c": nbt.IntArray([1, 2]),
                               "d": nbt.List(nbt.TAG_COMPOUND, []), "e": {"f": 1.5}})
    root = nbtlib.File.parse(io.BytesIO(data))
    assert root["a"] == -3 and root["b"] == "hé" and list(root["c"]) == [1, 2]
    assert len(root["d"]) == 0 and root["e"]["f"] == 1.5


def test_schematic_layout(tmp_path):
    ids = -np.ones((3, 2, 4), dtype=np.int64)
    ids[2, 1, 3] = 0  # x=2, y=1, z=3
    ids[0, 0, 0] = 1
    path = tmp_path / "t.schem"
    write_schem(str(path), ids, ["minecraft:stone", "minecraft:dirt"])
    root = read_schem(path)
    assert (root["Width"], root["Height"], root["Length"]) == (3, 2, 4)
    assert root["Version"] == 2
    palette = {str(k): int(v) for k, v in root["Palette"].items()}
    assert palette["minecraft:air"] == 0
    data = decode_varints(bytes(np.asarray(root["BlockData"], dtype=np.int8).tobytes()))
    assert len(data) == 3 * 2 * 4
    w, l = 3, 4
    assert data[2 + 3 * w + 1 * w * l] == palette["minecraft:stone"]
    assert data[0] == palette["minecraft:dirt"]
    assert sum(1 for v in data if v != 0) == 2
    assert int(root["Metadata"]["WEOffsetX"]) == -1


def test_palette_match_and_version_filter():
    pal = build_palette(["wool"])
    idx = pal.match(np.array([[250, 250, 250], [160, 40, 35]]))
    assert pal.names[idx[0]] == "minecraft:white_wool"
    assert pal.names[idx[1]] == "minecraft:red_wool"
    old = build_palette(mc_version="1.13.2")
    assert "minecraft:cherry_planks" not in old.names
    assert "minecraft:cherry_planks" in build_palette(mc_version="1.20.1").names


def test_voxelize_box_face_colors_and_fill():
    box = trimesh.creation.box(extents=(2, 1, 1))
    box.visual.face_colors = [200, 30, 30, 255]
    grid = voxelize([box], size=16)
    assert grid.shape == (16, 8, 8)
    # hollow: shell only
    assert not grid.occupancy[8, 4, 4]
    assert grid.occupancy[0, 4, 4]
    assert np.allclose(grid.colors[grid.occupancy].mean(0), [200, 30, 30])
    filled = voxelize([box], size=16, fill=True)
    assert filled.occupancy.all()


def _textured_glb(path):
    # left half red, right half blue texture on a plane-ish box
    tex = np.zeros((8, 8, 3), dtype=np.uint8)
    tex[:, :4] = [161, 39, 35]
    tex[:, 4:] = [50, 57, 157]
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    uv = np.zeros((len(mesh.vertices), 2))
    uv[:, 0] = np.where(mesh.vertices[:, 0] > 0, 0.99, 0.01)
    uv[:, 1] = 0.5
    material = trimesh.visual.material.PBRMaterial(baseColorTexture=Image.fromarray(tex))
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
    mesh.export(path)


def test_textured_glb_roundtrip(tmp_path):
    glb = tmp_path / "cube.glb"
    _textured_glb(str(glb))
    grid = voxelize(load_meshes(str(glb)), size=10)
    # face at x=+0.5 has all vertices with u=0.99 -> blue; x=-0.5 -> red
    assert grid.colors[-1, 5, 5, 2] > 140 and grid.colors[-1, 5, 5, 0] < 70
    assert grid.colors[0, 5, 5, 0] > 140 and grid.colors[0, 5, 5, 2] < 70


def test_cli_model(tmp_path, capsys):
    glb = tmp_path / "cube.glb"
    _textured_glb(str(glb))
    out = tmp_path / "out.schem"
    assert main(["model", str(glb), "-o", str(out), "--size", "12", "--fill"]) == 0
    root = read_schem(out)
    assert (root["Width"], root["Height"], root["Length"]) == (12, 12, 12)
    assert (tmp_path / "out_preview.png").exists()
    names = set(map(str, root["Palette"].keys()))
    assert any("red" in n for n in names) and any("blue" in n for n in names)


def test_z_up(tmp_path):
    box = trimesh.creation.box(extents=(1, 1, 3))  # tall along Z
    path = tmp_path / "tall.stl"
    box.export(str(path))
    grid = voxelize(load_meshes(str(path), up_axis="z"), size=9)
    assert grid.shape == (3, 9, 3)


class FakeClient:
    def __init__(self, params):
        self.params = params
        self.calls = []

    def view_api(self, return_format=None, print_info=True):
        return {"named_endpoints": {"/gen": {"parameters": self.params}}}

    def predict(self, api_name, **kwargs):
        self.calls.append((api_name, kwargs))
        return kwargs


def test_call_endpoint_filters_params_and_finds_image_slot(tmp_path):
    from mc3d.ai.gradio_util import call_endpoint, find_files

    client = FakeClient([
        {"parameter_name": "caption", "component": "Textbox"},
        {"parameter_name": "input_img", "component": "Image"},
        {"parameter_name": "seed", "component": "Slider"},
    ])
    out = call_endpoint(client, "/gen", {"seed": 3, "steps": 30}, image="IMG")
    assert out == {"seed": 3, "input_img": "IMG"}

    model = tmp_path / "white_mesh.glb"
    textured = tmp_path / "textured_mesh.glb"
    model.write_bytes(b"x")
    textured.write_bytes(b"x")
    files = find_files((str(model), {"value": str(textured)}, "<html>"), (".glb",))
    assert files == [str(model), str(textured)]

    from mc3d.ai.image_to_3d import _pick_model
    assert _pick_model((str(model), {"value": str(textured)})) == str(textured)
