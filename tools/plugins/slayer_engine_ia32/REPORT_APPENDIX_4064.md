# REPORT_APPENDIX_4064 — x87 leaf 3 本の eax 差の切り分け (PLG-G2-40)

既知類型との関係: 模型の限界 (例外フラグ IE/OE/PE/SF と C1 を持たない `ott_x87.h`) に当たる見込み。 `docs/DEFECTS.md` の既存 ID へは当てていない。 方式は `docs/DECISIONS.md` D28 (f80→f64)。

- 親: #3715 (PLG-G2-31・ただし本 repo に付録 `REPORT_APPENDIX_3715.md` は無い。issue 本文の実測値は照合できていない)。 試験の本体は `REPORT_APPENDIX_2989.md`。
- 測定 commit: `e18c9020c` (main 取り込み後の HEAD。 `x87_fn_diff.py` は #3716 の取り込みで `gen_special_rows`・`nan-num` 分類を含む)。 検証 HEAD: `e18c9020c` (§4 の再測定はこの commit の driver で行った)。 前の測定 commit `5583418dd` の値は、現在の分類と入力では再現していない (§4 参照)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と乱数 (seed 2989・`x87_fn_diff.py` の既定の生成)。

## 1. 結論

- 3 本とも PE 上に実在し、lift 出力 (`ott_lifted.c`) に入り、x87 命令を含む。 `lift_text.py` の pass2 の被覆は 85.37% (未被覆 10,682 B)。
- 測定 (各 4,000 行・seed 2989) の結果:

| 関数 | eax 不一致 | ST(0) の差 | 主な差の中身 | 切り分け |
|---|---:|---:|---|---|
| `0x10009eb5` | 4,000 / 4,000 | 4,000 / 4,000 (全行 NaN と 0) | native `eax` の差 `0x541` = `IE+SF+C0+C2+C3` を wasm が立てない。 ST(0) は native が NaN、wasm が 0 | **模型の限界**。 `fcomp` の例外フラグ・eax の IE/SF が模型に無い。 ST(0) の NaN は `frndint` ではなく空スタックの読み (underflow) による。 切り分けは REPORT_APPENDIX_4185 |
| `0x1000b526` | 2,003 / 4,000 | 0 | native のみ `OE+PE+C1` (と IE) を立て、wasm は 0 (`0x228`・`0x229`) | **模型の限界**。 PE/OE/C1 が模型に無い。 ST(0) は一致 |
| `0x1000bf60` | 0 / 4,000 | 2,022 / 4,000 | ST(0) が NaN と ±0 の食い違い (native NaN・wasm 0/-0 など) | **模型の限界の候補** (確定ではない)。 無効演算の NaN 生成 (IE 系) が模型と違う見込み。 eax は今回の入力では一致 |

- ネガコンは TARGETS 5 本の構成でも通る: `--nega` (11,270 → 11,269)、`--nega-lower` (4,000 / 4,000 不一致)。

## 2. 対象と方法

- 対象は `x87_fn_diff.py` の `PROBE` (環境変数 `X87_PROBE=1` で TARGETS に加える)。 **既定のゲートは既存 2 本 (`0x10002ee0`・`0x10005400`) のまま**。 既存 2 本の結果は `REPORT_APPENDIX_2989.md` §3 と一致 (3,890 / 3,405)。
- 引数は `generic` (float a0..a4 を ±100、eax 系の引数は乱数)。 この関数群の引数の意味は未確認で、測定結果はその仮定に依存する。
- 判定: 構造 (eax・x87 深さ) の一致を見る。 切り分けは eax の xor パターンと、ST(0) の NaN・ゼロの分類で行った。

## 3. 試験の driver の修正

- 5 本分のシナリオ (20,000 行・55 MB) は native の入力バッファ (`IBUF_SZ` 32 MiB) を超えた (`rc 5`)。
- `IBUF_SZ`/`OBUF_SZ` を 128 MiB に広げると、native の bss が image の VA `0x10000000` に重なり、SIGSEGV した。 この変更は取り消した。
- 代わりに driver (`x87_fn_diff.py`) がシナリオを 8,000 行ずつ (`CHUNK`) に分けて native と wasm の両方を実行し、出力を連結する。 乱数の列と行の順は変わらない。

## 4. 測定

検証 HEAD `e18c9020c` (main 取り込み後)。 `emsdk` 6.0.12 を上流から導入し、`fl-win64` の `block22434_PE.bin` (179,512 B) を展開して `lift_text.py` を実行した (functions 472、被覆 85.37%、未被覆 10,682 B。 §1 と一致)。 各コマンドは順番に 1 本ずつ実行した (並行で走らせると出力ファイルが混ざる)。

- `X87_PROBE=1 python3 x87_fn_diff.py` → FAIL・exit 1 (3 本の構造が一致しないため。 期待どおり)。 実測:
  - `0x10009eb5`: eax 不一致 4,000 行 (NaN どうし 0 行)、x87 深さ不一致 0、ST(0) (float64) は `nan-num` 4,000。
  - `0x1000b526`: eax 不一致 2,003 行、x87 深さ不一致 0、ST(0) は全行 bit 一致 4,000。
  - `0x1000bf60`: eax 不一致 0 行、x87 深さ不一致 0、ST(0) は `eq` 1,978・`nan-num` 2,022。 `nan-num` 2,022 の内訳 (native → wasm): NaN → ±0 が 1,090、±0 → NaN が 927、finite → NaN が 5。 `eq` 1,978 は NaN どうし (bit 一致) 927 と ±0 どうし (bit 一致) 1,051。 `nan` (両方 NaN で bit 不一致) は 0 件。
  - OBJ 窓は 3 本とも `nan-num` 0 件。
- 既定 `python3 x87_fn_diff.py` → PASS・exit 0 (wall 7.00 s、user 6.19 s)。 `0x10002ee0` 3,890 / 4,000、`0x10005400` 3,405 / 4,000 (REPORT_APPENDIX_2989 §3 と一致)。
- `python3 x87_fn_diff.py --nega` → 検出・exit 0 (`bit 一致 7,295 → 7,294`)。
- `python3 x87_fn_diff.py --nega-lower` → 検出・exit 0 (`fn_10002ee0` の float32 不一致 4,000 / 4,000)。
- `X87_PROBE=1 python3 x87_fn_diff.py --nega` → 検出・exit 0 (`bit 一致 11,270 → 11,269`、5 本 = 20,000 行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ott_x87.h` が例外フラグ (IE/DE/ZE/OE/UE/PE/SF) と C1 を持たない。 eax の差 (`0x541`・`0x228`/`0x229`) の模型側の実装 | 3 本の構造 gate を通せない。 模型の限界の記録は本付録で満たし、模型の拡張は未着手 | #4103 (PLG-G2-46・子。親 #4064) |
| `0x1000bf60` の NaN 生成の差 (無効演算の結果) | 原因の機械的な分類が未了 | #4105 (PLG-G2-47・子。親 #4064) |
| `0x10009eb5` の ST(0) の NaN (訂正: `frndint` が作るのではなく、空スタックの読みが native で default NaN になる) | 模型は空レジスタを 0 で読む (underflow の制限 (4))。 #4146 の方針の再判断が要る | #4185 (PLG-G2-51・子。親 #4064)。 測定は REPORT_APPENDIX_4185 |
| issue 本文の前提 (`REPORT_APPENDIX_3715.md`) が repo に無い | 前提の実測値を照合できない | PM 確認 (#3715) |
