<#
  Native Windows install of the local GPU backend (TRELLIS + SDXL-Turbo).

  Requirements (install these first):
    * NVIDIA driver (nvidia-smi works)
    * CUDA Toolkit 12.4  https://developer.nvidia.com/cuda-12-4-0-download-archive
    * Visual Studio 2022 Build Tools with "Desktop development with C++"
    * Git for Windows, Python 3.10 or 3.11 (64-bit)

  Usage:  scripts\windows\setup_gpu.bat [-Quality] [-Arch 7.0]
    -Quality  also build nvdiffrast / diff-gaussian-rasterization / diffoctreerast
              (needed only for `mc3d serve --quality`, texture baking)
    -Arch     CUDA compute capability to build for (V100 = 7.0)
#>
param(
    [switch]$Quality,
    [string]$Arch = "7.0"
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root
$ThirdParty = Join-Path $Root "third_party"
$TrellisDir = Join-Path $ThirdParty "TRELLIS"

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Run($exe, [string[]]$argv) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { throw "failed: $exe $($argv -join ' ')" }
}
function TryRun($label, $exe, [string[]]$argv) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { Write-Warning "$label failed (continuing)" }
}

Step "Checking prerequisites"
foreach ($cmd in @("nvidia-smi", "git", "nvcc")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "$cmd not found. See the requirements at the top of this script."
    }
}
& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
& nvcc --version | Select-String "release"

# Load the MSVC build environment so CUDA extensions can compile.
if (-not (Get-Command cl -ErrorAction SilentlyContinue)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { throw "Visual Studio 2022 Build Tools not found" }
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw "MSVC (Desktop development with C++) not installed" }
    $vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
    cmd /c "`"$vcvars`" >nul && set" | ForEach-Object {
        if ($_ -match "^([^=]+)=(.*)$") { Set-Item -Path "env:$($matches[1])" -Value $matches[2] }
    }
    Write-Host "MSVC environment loaded from $vs"
}
$env:DISTUTILS_USE_SDK = "1"
$env:TORCH_CUDA_ARCH_LIST = $Arch
$env:FORCE_CUDA = "1"

Step "Python virtual environment (.venv)"
if (-not (Test-Path ".venv")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { Run "py" @("-3", "-m", "venv", ".venv") }
    else { Run "python" @("-m", "venv", ".venv") }
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"
Run $Py @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools", "ninja")
Run $Py @("-m", "pip", "install", "-e", ".")

Step "PyTorch 2.5.1 (CUDA 12.4) + xformers"
Run $Py @("-m", "pip", "install", "torch==2.5.1", "torchvision==0.20.1",
          "--index-url", "https://download.pytorch.org/whl/cu124")
Run $Py @("-m", "pip", "install", "xformers==0.0.28.post3",
          "--index-url", "https://download.pytorch.org/whl/cu124")

Step "TRELLIS source"
New-Item -ItemType Directory -Force -Path $ThirdParty | Out-Null
if (-not (Test-Path $TrellisDir)) {
    Run "git" @("clone", "--recurse-submodules", "https://github.com/microsoft/TRELLIS.git", $TrellisDir)
}

Step "TRELLIS dependencies"
Run $Py @("-m", "pip", "install", "pillow", "imageio", "imageio-ffmpeg", "tqdm", "easydict",
          "opencv-python-headless", "scipy", "rembg", "onnxruntime", "trimesh", "xatlas",
          "pyvista", "pymeshfix", "igraph", "transformers", "safetensors", "huggingface_hub",
          "spconv-cu120",
          "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8")
TryRun "kaolin" $Py @("-m", "pip", "install", "kaolin==0.17.0", "-f",
                     "https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu124.html")

Step "Text-to-image (SDXL-Turbo via diffusers)"
Run $Py @("-m", "pip", "install", "diffusers>=0.30", "accelerate")

if ($Quality) {
    Step "Texture baking extras (compiling CUDA extensions, takes a while)"
    TryRun "nvdiffrast" $Py @("-m", "pip", "install", "--no-build-isolation",
                             "git+https://github.com/NVlabs/nvdiffrast.git")
    $mip = Join-Path $ThirdParty "mip-splatting"
    if (-not (Test-Path $mip)) {
        Run "git" @("clone", "https://github.com/autonomousvision/mip-splatting.git", $mip)
    }
    TryRun "diff-gaussian-rasterization" $Py @("-m", "pip", "install", "--no-build-isolation",
        (Join-Path $mip "submodules\diff-gaussian-rasterization"))
    $doct = Join-Path $ThirdParty "diffoctreerast"
    if (-not (Test-Path $doct)) {
        Run "git" @("clone", "--recurse-submodules", "https://github.com/JeffreyXiang/diffoctreerast.git", $doct)
    }
    TryRun "diffoctreerast" $Py @("-m", "pip", "install", "--no-build-isolation", $doct)
}

Step "Checking the installation"
$env:MC3D_TRELLIS_DIR = $TrellisDir
& $Py -m mc3d doctor --trellis-dir $TrellisDir
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDone. Start the server with:  scripts\windows\start_server.bat" -ForegroundColor Green
} else {
    Write-Warning "Some checks failed (see [NG] above). The cloud backend still works: start_server.bat cloud"
}
