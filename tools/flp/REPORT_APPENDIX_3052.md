# FLP (#3052) WFBox / DitherBox の読取り関数の静的調査 (REPORT §18 の全文)

`REPORT.md` の索引から参照する付録。`REPORT_APPENDIX.md` が 250 行上限を超えるため、§18 を分割移動した (内容の削除はない)。

## 18. #3052 WFBox / DitherBox の読取り関数の静的調査 (受入 1 の VA)

測定 commit: **`f2fd830f`** (`tools/flp/s3_regread_xref.py` を追加した commit。以後のコード変更なし)。対象: 素材 `block00031_PE.bin` (FLEngine_x64.dll, 22,227,016 B)。再現: `uv run --with pefile --with capstone python3 tools/flp/s3_regread_xref.py $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` (実測 13.5 s、単一プロセス)。

**結論: 受入 1 の「読取り関数の VA」は未特定 (未達のまま)。** 静的に言えるのは次の 3 点。
1. `WFBox`・`DitherBox`・`WAVRenderForm` の **UTF-16 リテラルは FLEngine に無い** (ASCII の出現だけ)。よって、この値名を文字列リテラルで読む関数は無い。読取りは部品名を実行時に得る汎用経路と見られる (推定)。
2. レジストリ読取りは `RegQueryValueExW`・`RegOpenKeyExW` の thunk (`jmp [IAT]`) を経由する。直接呼出し 60 箇所・33 関数。
3. 汎用経路の候補は絞れたが、確定していない (下記 18.4)。

**18.1 文字列の出現** (script §1。対照: 既知の UTF-16 リテラル `Software\Image-Line\FL Studio 26\General` は script §6 で 2 関数の参照を検出 → 検出方法は UTF-16 リテラルを拾える)

| 文字列 | ASCII 出現 | UTF-16 出現 |
|---|--:|--:|
| `WFBox` | 14 | 0 |
| `DitherBox` | 6 | 0 |
| `QualityBox` | 4 | 0 |
| `FormatBox` | 10 | 0 |
| `WAVRenderForm` | 6 | 0 |

`WFBox` の VA `0xd1339d` は、直前に長さ接頭 `\x05` (`\x04\x00\x05WFBox`)、直後に同じ形式の部品名 `MP3BitrateSlider` (長さ接頭 `\x10`) が続く。`WAVRenderForm` の ASCII 出現 (`0xd12d64`〜`0xd13b63`) と同じ領域のため、TWAVRenderForm のフォーム定義 (DFM) と推定する。

**18.2 レジストリ API の thunk** (script §2。`jmp [IAT]` のバイト列 `ff 25` を IAT スロットで照合)

| thunk VA | API |
|---|---|
| `0x407200` | RegOpenKeyExW |
| `0x407210` | RegQueryValueExW |
| `0x4230d0` | RegOpenKeyExW |
| `0x423100` | RegQueryValueExW |

**18.3 直接呼出し** (script §4・§5。call/jmp rel32 の先が thunk のもの。間接呼出し `call [reg]`・vtable は数えていない)
- `Reg{Query,Open}` thunk への直接呼出し: **60 箇所・33 関数** (`functions=57816`、`insns=2566540` を関数単位で逆アセンブル)。
- うち `RegQueryValueExW` を直接呼ぶ関数は **30 件**。呼出し元が 1 件以上ある主な関数: `0x5b0bd0` (size 0xb0・呼出し元 8)、`0x5b02a0` (0x72・7)、`0x11d9340` (0x1d85・10)、`0xf40840` (0x401d・3・プロジェクト保存)、`0x121d7e0` (0x17c1・3・`General` / `Last SER`)、`0x117f850` (0xd0a・2・`Shared\General`)。
- `0x11a57c0` (size 0x81e8・`ReadIniFile`・`General\` 系) は主要オプションを**リテラル名**で読む (`SmootherUpdateBox`・`SyncType` 等が UTF-16 リテラル)。`WFBox` はリテラルに無いので、この関数では読まれない (推定)。

**18.4 キー組立ての候補 (未検証)**
- `Software\Image-Line\FL Studio 26\General` (UTF-16 リテラル) は `0x111bce0` (TRegistry を生成し `OpenKey` (`0x5af5e0`) を呼び、リテラル名 1 件を処理) と `0x1175480` から参照される。
- `Software\Image-Line\FL Studio 26\General\` (末尾 `\` 付き) は `0xfe0710` (コンストラクタ。`0xfe0750` の lea で参照し、サブオブジェクトの `+0x1654` へ代入) だけが参照する。
- 仮説 (推定、未確認): フォームの設定キーは「基底キー `General\` + フォーム名」で、`WAVRenderForm` は `General\WAVRenderForm`。その汎用ローダが部品名 (`WFBox`) を値名に使う。

**18.5 読取りラッパ層 (RTL 相当、名称は未確認)**
- `0x5b02a0`・`0x5b0bd0`: `RegQueryValueExW` を直接呼ぶ読取り層 (呼出し元 7 / 8)。`0x5af7c0`: `RegOpenKeyExW` を呼ぶ `OpenKey` 相当 (呼出し元は一意の関数で 26)。
- 上記の呼出し元の中に、部品名を実行時に受け取って読む関数があるはず (推定)。その特定が次の一手。

**未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `WFBox` を読む汎用ローダ (部品名を実行時に値名にする関数) の VA と、読んだ値の書式引数 (`0x670fd0` の第 6 引数) への渡し先 | 受入 1 未達 (VA 未特定) | #3052 |
| 18.4・18.5 の候補の真偽 (静的のみ)。動的確認 (S1 で install 木を作り、候補の戻り値を `S2_PATCH` で変える) は未実施 | 候補が経路上かは未確認 | #3052 |
| 間接呼出し (`call [reg]`・vtable) 経由の読取りは未計数 | 静的な網羅性は直接呼出しの範囲まで | #3052 |
| 別 wineprefix・別 run での SHA 一致、Render tests 全数の書き出し | 本節の対象外 | #3053 (依存 #3052) |

**差分の証跡**: `git diff f2fd830f HEAD -- tools/flp/s3_regread_xref.py` の出力は 0 行 (文書の変更のみ)。製品 KPI (flelift の起動 dispatch 数・通過 unit 数): 動かしていない (静的解析のみ、起動なし)。
