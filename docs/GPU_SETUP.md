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
- TRELLIS は Linux 向けです。**Windows の場合は WSL2 (Ubuntu 22.04) を推奨**します

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

# 5. 起動 (初回はモデルのダウンロードで数分かかります)
export PYTHONPATH=~/TRELLIS
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
