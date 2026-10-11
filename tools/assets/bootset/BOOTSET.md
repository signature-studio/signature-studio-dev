# 自動生成: `python3 tools/assets/bootset/classify_bootset.py` (`bootset/bootset.json`・`work/tiers.json` と同時生成)

> **人手編集禁止** (生成元の `classify_bootset.py` を直す)。推定 tier の記載ここが正本。
> 起動 tier の解釈・配信順への反映は `tools/assets/MANIFEST.md`、実施記録は `tools/assets/REPORT.md`。
> tier の確度は「推定」(実機トレース未取得。根拠は FLEngine 文字列 + ツリー構造規則)。

# BOOTSET — 起動時ファイル階層 (推定)

| tier | files | bytes | MB | unique-content files | unique-content MB |
|---|---:|---:|---:|---:|---:|
| T0 | 142 | 2212908 | 2.21 | 138 | 2.21 |
| T0p | 258 | 5595646 | 5.60 | 116 | 5.58 |
| T1 | 1700 | 76414481 | 76.41 | 649 | 53.37 |
| T2 | 24990 | 1001026635 | 1001.03 | 23924 | 986.25 |
| X-lift | 196 | 771827960 | 771.83 | 195 | 768.23 |
| X-rebuild | 43 | 99622456 | 99.62 | 43 | 99.62 |
| X-skip | 72 | 189736312 | 189.74 | 65 | 189.36 |

## 規則と証拠 (FLEngine_x64.dll の UTF-16/ASCII 文字列に存在するか)

| tier | glob | files | KB | 証拠 found/total | 理由 |
|---|---|---:|---:|---|---|
| T0 | `Artwork/Skins/Default/*` | 7 | 506.3 | 7/7 | 既定スキン (起動画面/UI 素材, 起動音) |
| T0 | `Artwork/Themes/thmDefault.png` | 1 | 36.2 | 1/1 | 既定テーマ画像 |
| T0 | `Artwork/Themes/tweak_default.png` | 1 | 6.6 | 1/1 | 既定テーマ調整画像 |
| T0 | `Artwork/Fonts/Fruity microfont.ttf` | 1 | 19.6 | 2/2 | マイクロフォント |
| T0 | `Shared/Artwork/Fonts/PT_Sans-Web-Regular.ttf` | 1 | 432.6 | 1/1 | UI 既定フォント (リテラル名参照) |
| T0p | `Shared/Artwork/Fonts/*` | 50 | 4689.5 | 1/1 | フォントディレクトリ列挙 (QuickFontCache が登録): 他フォント |
| T0 | `System/Config/*.txt` | 6 | 3.9 | 4/4 | 設定/命名プリセット |
| T0 | `System/Config/Chords.map` | 1 | 2.7 | 1/1 | 設定 (コード map) |
| T0 | `System/Config/Master/*` | 1 | 470.0 | 1/1 | マスタ設定 |
| T0 | `System/Config/Mapping/*` | 14 | 170.6 | 1/1 | コントローラ mapping |
| T0 | `System/Config/Typing to piano/*` | 32 | 8.6 | 1/1 | キー→ピアノ |
| T0 | `System/Config/Toolbar presets/*` | 11 | 7.5 | 1/1 | ツールバープリセット |
| T0 | `System/Config/Touch keyboard/*` | 6 | 49.2 | 1/1 | タッチ鍵盤 |
| T0 | `System/Config/Note color presets/*` | 2 | 0.5 | 1/1 | ノート色 |
| T0 | `System/Config/Note name presets/*` | 0 | 0.0 | 1/1 | ノート名 |
| T0 | `System/Config/Browser/*` | 11 | 0.7 | 1/1 | ブラウザタブ構成 (.tabconfig) |
| T0p | `System/Config/Audio scripts/*` | 13 | 22.8 | 1/1 | スクリプト列挙 |
| T0p | `System/Config/Piano roll scripts/*` | 6 | 26.1 | 1/1 | スクリプト列挙 |
| T0p | `System/Config/FL Studio Remote Scripts/*` | 5 | 1.8 | 1/1 | リモートスクリプト列挙 |
| T1 | `System/Config/Thumbnails/*` | 163 | 6754.8 | 2/2 | ブラウザ/エディション サムネイル |
| T0 | `System/Plugin Formats/*` | 0 | 0.0 | 2/2 | プラグイン形式定義 |
| T0p | `System/Texts/*.txt` | 8 | 1.8 | 4/4 | エディション/案内文 |
| T1 | `System/Texts/*` | 16 | 105.8 | 1/1 | About/ライセンス文 |
| T0p | `System/Internet/*` | 8 | 468.1 | 2/2 | ニュース/オフライン案内 (外部通信は対象外, 既定ページのみ) |
| T1 | `System/Languages/*` | 15 | 6138.8 | 2/2 | 言語ファイル (英語は内蔵; 選択言語のみ 1 ファイル) |
| T1 | `System/Hardware specific/*` | 118 | 820.9 | 1/1 | MIDI コントローラ定義 (デバイス接続時) |
| T0 | `Data/System/*.fst` | 40 | 251.3 | 6/6 | チャンネル既定 state (.fst) |
| T0 | `Data/System/Empty.flp` | 1 | 45.3 | 2/2 | 空プロジェクト |
| T0 | `Data/System/Metronome*.wav` | 5 | 51.5 | 2/2 | メトロノーム音 |
| T0 | `Data/System/*.ico` | 1 | 97.9 | 1/1 | アイコン |
| T0p | `Data/System/Riff machine/*` | 8 | 16.9 | 1/1 | Riff machine 既定 |
| T0p | `Data/System/Default/*` | 13 | 4.1 | 2/2 | 既定インストール済みプラグイン定義 |
| T1 | `Data/System/Plugin databases/*` | 1310 | 25358.9 | 2/2 | プラグインデータベース (ブラウザ初回展開) |
| T2 | `Data/System/FL Mobile/*` | 341 | 41897.3 | 1/1 | FL Studio Mobile ラック内容 (プラグイン生成時) |
| T2 | `Data/System/Render tests/*` | 82 | 7496.8 | 0/0 | レンダーテスト (内部) |
| T0p | `Data/Templates/Minimal/Basic with limiter/*` | 2 | 52.1 | 2/2 | 既定テンプレート (起動時にロードされる推定) |
| T1 | `Data/Templates/*` | 68 | 30069.3 | 1/1 | テンプレート一覧 (New from template) |
| T0p | `Data/Patches/Packs/Legacy/Drums/Dance/Basic 808 *.wav` | 4 | 177.9 | 1/1 | 既定テンプレート参照サンプル (FLP 文字列から導出) |
| T0p | `Plugins/Fruity/*/*/Plugin.nfo` | 141 | 3.3 | 3/3 | プラグインスキャン用メタ |
| T0p | `Plugins/Fruity/*/*.nfo` | 0 | 0.0 | 2/2 | プラグインスキャン用メタ |
| T1 | `Help/index_offline.html` | 1 | 3.9 | 1/1 | オフラインヘルプ入口 |
| T1 | `Help/*.scr` | 2 | 10.7 | 2/2 | ヘルプ別名表 |
| T1 | `WhatsNew.rtf` | 1 | 1012.2 | 1/1 | 更新情報 |
| T1 | `Shared/Python/*` | 6 | 4348.2 | 1/1 | Python 3.12 標準ライブラリ (スクリプト実行時) |

## 既定テンプレート参照 (Data/Templates/Minimal/Basic with limiter/Basic with limiter.flp)
- `%FLStudioFactoryData%\Data\Patches\Packs\Legacy\Drums\Dance\Basic 808 Kick.wav` 実在=True
- `%FLStudioFactoryData%\Data\Patches\Packs\Legacy\Drums\Dance\Basic 808 Clap.wav` 実在=True
- `%FLStudioFactoryData%\Data\Patches\Packs\Legacy\Drums\Dance\Basic 808 HiHat.wav` 実在=True
- `%FLStudioFactoryData%\Data\Patches\Packs\Legacy\Drums\Dance\Basic 808 Snare.wav` 実在=True
