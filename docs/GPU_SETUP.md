# V100 16GB でローカル生成する (mc3d serve --backend local)

ローカルでは次の2つのモデルを動かします。

| 工程 | モデル | V100での目安 | VRAM |
|---|---|---|---|
| テキスト→画像 | SDXL-Turbo (fp16, 2ステップ) | 約1〜2秒 | 約7GB (TRELLIS 実行中はCPUへ退避) |
| 画像→3D | TRELLIS-image-large (fp16) | 約15〜30秒 (fastモード) | 約8〜12GB |
| 3D→schem | mc3d (CPU) | 数秒 | – |

> 時間は目安で、実測ではありません。

## V100 での注意点

- **flash-attn は使えません**(V100 は sm70 で非対応)。`ATTN_BACKEND=xformers` を使います(mc3d が自動で設定します)
- **bf16 非対応**のため fp16 で動かします
- CUDA 拡張をビルドするときは `TORCH_CUDA_ARCH_LIST="7.0"` を指定します
- TRELLIS 公式は Linux 向けですが、下の **Windows ネイティブ手順** でも動かせるようにしています

## 手順 (Windows ネイティブ)

### 事前に入れるもの

| ソフト | 備考 |
|---|---|
| NVIDIA ドライバ | `nvidia-smi` が動けばOK |
| [CUDA Toolkit 12.4](https://developer.nvidia.com/cuda-12-4-0-download-archive) | `nvcc --version` で 12.4 と出ること |
| [Visual Studio 2022 Build Tools](https://visualstudio.microsoft.com/ja/visual-cpp-build-tools/) | 「C++ によるデスクトップ開発」を選択 |
| [Git for Windows](https://git-scm.com/download/win) | |
| [Python 3.11 (64bit)](https://www.python.org/downloads/windows/) | インストール時に「Add python.exe to PATH」をチェック |

### インストールと起動 (コマンドプロンプト)

```bat
cd ai_3d_data_minecraft
scripts\windows\setup_gpu.bat
rem テクスチャ焼き込み (--quality) も使う場合
scripts\windows\setup_gpu.bat -Quality

scripts\windows\start_server.bat              rem ローカルGPU (既定)
scripts\windows\start_server.bat local --quality
scripts\windows\start_server.bat cloud        rem 無料クラウドAPI
```

`setup_gpu.bat` がやること:

- `.venv` を作り、PyTorch 2.5.1 (CUDA 12.4) / xformers / spconv をインストール
- TRELLIS を `third_party\TRELLIS` に取得して、依存パッケージをインストール
- Visual Studio のビルド環境を自動で読み込み、`TORCH_CUDA_ARCH_LIST=7.0` (V100) で CUDA 拡張をビルド
- 最後に `mc3d doctor` で動作確認

`mc3d doctor` で `[NG]` が出た項目が原因です。
GPU が来る前やうまく入らないときも、`start_server.bat cloud` なら動きます。

> Windows ネイティブの TRELLIS は公式サポート外のため、パッケージの組み合わせ次第で
> ビルドに失敗することがあります。その場合は `[NG]` の行を教えてもらえれば対応します。
> どうしても動かない場合は、下の WSL2 手順が確実です。

## 手順 (Ubuntu / WSL2)

```bash
# 0. NVIDIA ドライバ (WSL2 の場合は Windows 側にインストール) を入れて確認
nvidia-smi

# 1. Python 環境
conda create -n mc3d python=3.10 -y
conda activate mc3d

# 2. PyTorch (CUDA 12.1)
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121

# 3. TRELLIS
git clone --recurse-submodules https://github.com/microsoft/TRELLIS.git ~/TRELLIS
cd ~/TRELLIS
export TORCH_CUDA_ARCH_LIST="7.0"
. ./setup.sh --basic --xformers --spconv --kaolin --nvdiffrast --diffoctreerast --mipgaussian
cd -

# 4. mc3d とローカル用の追加パッケージ
cd ai_3d_data_minecraft
pip install -e .
pip install -r requirements-gpu.txt

# 5. 確認と起動 (初回はモデルのダウンロードで数分かかります)
export MC3D_TRELLIS_DIR=~/TRELLIS
mc3d doctor
mc3d serve --backend local
```

`[serve] backend=local listening on http://127.0.0.1:8765` と出れば準備完了です。

## オプション

| オプション | 説明 |
|---|---|
| `--quality` | TRELLIS の結果からテクスチャを焼き込んだ GLB を作る(遅くなる代わりに色が少しシャープ)。既定は頂点色をそのまま使う高速モード |
| `--steps 12` | TRELLIS のサンプリングステップ数。減らすと速く、増やすと高品質 |
| `--host 0.0.0.0` | Minecraft サーバーが別PCの場合 (このときは `--api-key` を必ず設定) |
| `--api-key 秘密の文字列` | プラグインの `config.yml` の `api-key` と同じ値にする |
| `--backend cloud` | GPU が無い間は、これまでの無料 Hugging Face Space を使う |

モデルは環境変数で差し替えられます。

```bash
export MC3D_TRELLIS_MODEL=microsoft/TRELLIS-image-large
export MC3D_T2I_MODEL=stabilityai/sdxl-turbo
```

`diffusers` が入っていない場合、テキスト→画像は自動で無料の Pollinations API を使います。
