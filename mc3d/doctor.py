"""``mc3d doctor``: check that the local GPU backend can run."""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys


def _check(label: str, fn) -> bool:
    try:
        detail = fn()
        print(f"  [OK] {label}" + (f": {detail}" if detail else ""))
        return True
    except Exception as e:  # report and continue
        print(f"  [NG] {label}: {type(e).__name__}: {e}")
        return False


def _version(module: str):
    return lambda: getattr(importlib.import_module(module), "__version__", "installed")


def run(trellis_dir: str | None = None) -> int:
    if trellis_dir:
        os.environ["MC3D_TRELLIS_DIR"] = trellis_dir
    print(f"Python {sys.version.split()[0]} on {platform.system()} {platform.release()}")
    ok = True

    def torch_cuda():
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError(f"torch {torch.__version__} has no CUDA (CPU build?)")
        name = torch.cuda.get_device_name(0)
        major, minor = torch.cuda.get_device_capability(0)
        mem = torch.cuda.get_device_properties(0).total_memory / 2**30
        return f"torch {torch.__version__}, CUDA {torch.version.cuda}, {name} sm{major}{minor}, {mem:.1f} GB"

    print("GPU:")
    ok &= _check("PyTorch + CUDA", torch_cuda)
    ok &= _check("xformers", _version("xformers"))
    ok &= _check("spconv", _version("spconv"))
    print("TRELLIS (image→3D):")
    import mc3d.local.models  # noqa: F401  (applies MC3D_TRELLIS_DIR / env defaults)
    ok &= _check("trellis package", lambda: os.path.dirname(
        importlib.import_module("trellis").__file__))
    ok &= _check("TrellisImageTo3DPipeline", lambda: bool(
        importlib.import_module("trellis.pipelines").TrellisImageTo3DPipeline))
    _check("nvdiffrast (only for --quality)", _version("nvdiffrast"))
    _check("diff_gaussian_rasterization (only for --quality)",
           _version("diff_gaussian_rasterization"))
    print("Text→image (optional, otherwise the free API is used):")
    _check("diffusers", _version("diffusers"))
    print("Build tools (only needed while installing):")
    _check("nvcc", lambda: shutil.which("nvcc") or (_ for _ in ()).throw(FileNotFoundError("not on PATH")))
    if platform.system() == "Windows":
        _check("MSVC cl.exe", lambda: shutil.which("cl") or (_ for _ in ()).throw(
            FileNotFoundError("run from 'x64 Native Tools Command Prompt for VS 2022'")))
    print("\nResult: " + ("ready for `mc3d serve --backend local`" if ok
                          else "local backend NOT ready (`mc3d serve --backend cloud` still works)"))
    return 0 if ok else 1
