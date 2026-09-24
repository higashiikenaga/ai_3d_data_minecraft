# mc3d — AI 3D生成 → WorldEdit `.schem` 変換ツール

無料のAI APIでテキストや画像から3Dモデルを作り、それをボクセル化して
Minecraft の WorldEdit / FAWE で読み込める **Sponge Schematic (.schem)** を出力します。

```
テキスト ──(Pollinations / FLUX)──▶ 画像 ──(TRELLIS / Hunyuan3D-2)──▶ 3Dモデル(GLB)
                                                                      │
          .schem ◀── ブロック色マッチング(CIELAB) ◀── ボクセル化(テクスチャ色つき)
```

## 使用する無料API

| 工程 | バックエンド | 料金・キー |
|---|---|---|
| テキスト→画像 | [Pollinations.ai](https://pollinations.ai) | 無料・APIキー不要 |
| テキスト→画像 (予備) | Hugging Face Space `black-forest-labs/FLUX.1-schnell` | 無料 (HF_TOKEN任意) |
| 画像→3D | Hugging Face Space `trellis-community/TRELLIS` | 無料 (ZeroGPU) |
| 画像→3D (予備) | Hugging Face Space `tencent/Hunyuan3D-2` | 無料 (ZeroGPU) |

`auto`(既定)では上から順に試し、失敗すると次のバックエンドに切り替えます。
Hugging Face の ZeroGPU はログインなしだと1日あたりのGPU枠が小さいため、
無料アカウントで [アクセストークン](https://huggingface.co/settings/tokens) を作成して
`HF_TOKEN` 環境変数に設定すると安定します。

## インストール

```bash
pip install -e .          # Python 3.9+
# テストも実行する場合
pip install -e ".[dev]" && pytest
```

## 使い方

```bash
# テキストから (text → image → 3D → schem)
mc3d text "a cute red dragon" --size 64 -o output/dragon.schem

# 画像から (image → 3D → schem)
mc3d image my_character.png --size 48

# 手元の3Dモデルから (glb / gltf / obj / ply / stl)
mc3d model model.glb --size 100 --fill

# Spaceの現在のAPI仕様を確認 (Space側のAPIが変わった時のデバッグ用)
mc3d api-info trellis-community/TRELLIS
```

`python -m mc3d ...` でも実行できます。

出力されるファイル(`-o output/dragon.schem` の場合):

- `output/dragon.schem` — WorldEdit用スケマティック
- `output/dragon_preview.png` — 正面・側面・上面のプレビュー
- `output/dragon_image.png` / `output/dragon_model.glb` — 中間生成物(画像・3Dモデル)

### Minecraft での読み込み

1. `.schem` を `plugins/WorldEdit/schematics/`(Bukkit/Paper) または
   `config/worldedit/schematics/`(Fabric/Forge) にコピー
2. ゲーム内で
   ```
   //schem load dragon
   //paste
   ```
   既定ではプレイヤーの足元を中心に配置されます(`--no-center` で角基準)。

## 主なオプション

| オプション | 説明 |
|---|---|
| `-s, --size N` | 最長辺のブロック数 (既定 64) |
| `--fit height` | `--size` を高さ基準にする |
| `--fill` | 内部を埋める (既定は外殻のみ=ブロック数が少ない) |
| `--palette wool,concrete` | 使うブロック群: `concrete, wool, terracotta, natural, wood, building, mineral` |
| `--exclude diamond_block,gold_block` | 使わないブロック |
| `--mc-version 1.20.1` | 対象バージョン (1.13.2〜1.21.4)。そのバージョンに無いブロックは除外 |
| `--up z` | 入力モデルの上方向 (GLBは y、STL/OBJ は z のことが多い) |
| `--density 8` | 表面サンプル密度。殻に穴が空く場合は上げる |
| `--seed N` | 生成シード |
| `--model-backend trellis\|hunyuan3d\|hunyuan3d21\|custom` | 画像→3Dのバックエンド固定 |
| `--image-backend pollinations\|flux` | テキスト→画像のバックエンド固定 |
| `--raw-prompt` | プロンプトに「単体・白背景」等の補助語を付けない |
| `--hf-token` | Hugging Face トークン (既定は `$HF_TOKEN`) |

### 他の Space を使う

環境変数で Space を差し替えられます。

```bash
export MC3D_TRELLIS_SPACE=your-name/TRELLIS-duplicate   # 複製したSpaceなど
export MC3D_HUNYUAN_SPACE=tencent/Hunyuan3D-2
# 任意の「画像を入れて3Dファイルを返す」Space
export MC3D_CUSTOM_SPACE=someone/some-image-to-3d
export MC3D_CUSTOM_API=/predict
mc3d image photo.png --model-backend custom
```

Space のAPI引数は実行時に取得したスキーマで照合し、存在しない引数は自動で除外、
画像入力欄も自動検出します。

## 仕組み

1. **テキスト→画像**: 3D化しやすいよう「単体・中央・白背景」などをプロンプトに追加して生成
2. **画像→3D**: TRELLIS / Hunyuan3D-2 でテクスチャ付き GLB を生成
3. **ボクセル化** (`mc3d/voxelize.py`): メッシュ表面を面積比で大量にサンプリングし、
   UVテクスチャ・頂点色・面色・マテリアル色から各点の色を取得、ボクセル毎に平均。
   `--fill` 時は閉じた内部を埋め、最寄りの表面色で着色
4. **ブロック割り当て** (`mc3d/blocks.py`): 約100種の不透明ブロックの平均色と CIELAB 空間で最近傍マッチ
5. **書き出し** (`mc3d/schem.py`, `mc3d/nbt.py`): Sponge Schematic v2 (gzip NBT) を依存なしで出力。
   WorldEdit 7.x / FastAsyncWorldEdit で読み込み可能

## Python から使う

```python
from mc3d.pipeline import ConvertOptions, model_to_schem, text_to_schem

opts = ConvertOptions(size=48, fill=True, palette_groups=["wool", "concrete"])
text_to_schem("a small medieval house", "output/house.schem", opts)
model_to_schem("model.glb", "output/model.schem", opts)
```

## 注意

- 無料APIは混雑・レート制限・仕様変更があり得ます。失敗時は時間を置くか、別バックエンドを指定してください。
- 生成物の利用は各モデル/サービスのライセンスに従ってください。
