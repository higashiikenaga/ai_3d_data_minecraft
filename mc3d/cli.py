"""Command line interface: ``mc3d text|image|model|api-info``."""

from __future__ import annotations

import argparse
import os
import re
import sys

from .blocks import DATA_VERSIONS, DEFAULT_MC_VERSION, PALETTE_GROUPS
from .pipeline import ConvertOptions, image_to_schem, model_to_schem, text_to_schem


def _add_convert_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-o", "--output", help="output .schem path (default: derived from input)")
    p.add_argument("-s", "--size", type=int, default=64,
                   help="blocks along the longest side (or height with --fit height), default 64")
    p.add_argument("--fit", choices=("max", "height"), default="max")
    p.add_argument("--fill", action="store_true", help="fill the interior (default: hollow shell)")
    p.add_argument("--up", default="y", choices=("y", "z", "-z", "x", "-y"),
                   help="up axis of the 3D model (GLB is y; many STL/OBJ are z)")
    p.add_argument("--palette", default=",".join(PALETTE_GROUPS),
                   help=f"comma-separated block groups: {','.join(PALETTE_GROUPS)}")
    p.add_argument("--exclude", default="", help="comma-separated block ids to never use")
    p.add_argument("--mc-version", default=DEFAULT_MC_VERSION, choices=list(DATA_VERSIONS))
    p.add_argument("--density", type=float, default=8.0,
                   help="surface samples per voxel; raise if the shell has holes")
    p.add_argument("--no-center", action="store_true",
                   help="paste with the corner at the player instead of centered")
    p.add_argument("--no-preview", action="store_true")
    p.add_argument("--seed", type=int, default=0)


def _add_ai_args(p: argparse.ArgumentParser, text: bool) -> None:
    p.add_argument("--model-backend", default="auto",
                   choices=("auto", "trellis", "hunyuan3d", "hunyuan3d21", "custom"),
                   help="image-to-3D Hugging Face Space (auto tries them in this order)")
    if text:
        p.add_argument("--image-backend", default="auto", choices=("auto", "pollinations", "flux"))
        p.add_argument("--raw-prompt", action="store_true",
                       help="do not append the 'single object, white background' hints")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"),
                   help="Hugging Face token (free) for a larger GPU quota; default $HF_TOKEN")


def _options(args) -> ConvertOptions:
    return ConvertOptions(
        size=args.size,
        fit=args.fit,
        fill=args.fill,
        up_axis=args.up,
        palette_groups=[g.strip() for g in args.palette.split(",") if g.strip()],
        exclude=[b.strip() for b in args.exclude.split(",") if b.strip()],
        mc_version=args.mc_version,
        density=args.density,
        center=not args.no_center,
        preview=not args.no_preview,
        seed=args.seed,
    )


def _slug(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").lower()
    return (slug[:40] or "build")


def _output(args, default_stem: str) -> str:
    out = args.output or os.path.join("output", default_stem + ".schem")
    if not out.endswith(".schem"):
        out += ".schem"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mc3d",
        description="Generate WorldEdit .schem files from text, images or 3D models "
                    "using free AI APIs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_text = sub.add_parser("text", help="text prompt → image → 3D → .schem")
    p_text.add_argument("prompt")
    _add_convert_args(p_text)
    _add_ai_args(p_text, text=True)

    p_image = sub.add_parser("image", help="image → 3D → .schem")
    p_image.add_argument("image")
    _add_convert_args(p_image)
    _add_ai_args(p_image, text=False)

    p_model = sub.add_parser("model", help="existing 3D model (glb/gltf/obj/ply/stl) → .schem")
    p_model.add_argument("model")
    _add_convert_args(p_model)

    p_info = sub.add_parser("api-info", help="show the API of a Hugging Face Space")
    p_info.add_argument("space", help="e.g. trellis-community/TRELLIS")
    p_info.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"))

    args = parser.parse_args(argv)

    try:
        if args.command == "api-info":
            from .ai.gradio_util import describe_space
            print(describe_space(args.space, args.hf_token))
            return 0
        opts = _options(args)
        if args.command == "text":
            result = text_to_schem(args.prompt, _output(args, _slug(args.prompt)), opts,
                                   image_backend=args.image_backend,
                                   model_backend=args.model_backend,
                                   hf_token=args.hf_token, raw_prompt=args.raw_prompt)
        elif args.command == "image":
            stem = _slug(os.path.splitext(os.path.basename(args.image))[0])
            result = image_to_schem(args.image, _output(args, stem), opts,
                                    backend=args.model_backend, hf_token=args.hf_token)
        else:
            stem = _slug(os.path.splitext(os.path.basename(args.model))[0])
            result = model_to_schem(args.model, _output(args, stem), opts)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("\nDone!")
    print(f"  schematic : {result.schem_path}")
    if result.preview_path:
        print(f"  preview   : {result.preview_path}")
    x, y, z = result.shape
    print(f"  size      : {x} x {y} x {z} (W x H x L), {result.block_count} blocks")
    print("  top blocks: " + ", ".join(
        f"{name.removeprefix('minecraft:')}={n}" for name, n in list(result.block_usage.items())[:8]))
    name = os.path.splitext(os.path.basename(result.schem_path))[0]
    print(f"\nCopy it to plugins/WorldEdit/schematics/ (or config/worldedit/schematics/) and run:")
    print(f"  //schem load {name}\n  //paste")
    return 0
