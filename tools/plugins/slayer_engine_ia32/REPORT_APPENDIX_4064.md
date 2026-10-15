# REPORT_APPENDIX_4064 — x87 leaf 3 本の eax 差の切り分け (PLG-G2-40)

既知類型との関係: 模型の限界 (例外フラグ IE/OE/PE/SF と C1 を持たない `ott_x87.h`) に当たる見込み。 `docs/DEFECTS.md` の既存 ID へは当てていない。 方式は `docs/DECISIONS.md` D28 (f80→f64)。

- 親: #3715 (PLG-G2-31・ただし本 repo に付録 `REPORT_APPENDIX_3715.md` は無い。issue 本文の実測値は照合できていない)。 試験の本体は `REPORT_APPENDIX_2989.md`。
- 測定 commit: `5583418dd` (PROBE を加えた最後のコード commit)。 検証 HEAD: `5583418dd`。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` と乱数 (seed 2989・`x87_fn_diff.py` の既定の生成)。

## 1. 結論

- 3 本とも PE 上に実在し、lift 出力 (`ott_lifted.c`) に入り、x87 命令を含む。 `lift_text.py` の pass2 の被覆は 85.37% (未被覆 10,682 B)。
- 測定 (各 4,000 行・seed 2989) の結果:

| 関数 | eax 不一致 | ST(0) の差 | 主な差の中身 | 切り分け |
|---|---:|---:|---|---|
| `0x10009eb5` | 4,000 / 4,000 | 4,000 / 4,000 (全行 NaN と 0) | native `eax` の差 `0x541` = `IE+SF+C0+C2+C3` を wasm が立てない。 ST(0) は native が NaN、wasm が 0 | **模型の限界**。 `frndint`・`fcomp` の例外フラグ・NaN 生成が模型に無い |
| `0x1000b526` | 2,003 / 4,000 | 0 | native のみ `OE+PE+C1` (と IE) を立て、wasm は 0 (`0x228`・`0x229`) | **模型の限界**。 PE/OE/C1 が模型に無い。 ST(0) は一致 |
| `0x1000bf60` | 0 / 4,000 | 2,022 / 4,000 | ST(0) が NaN と ±0 の食い違い (native NaN・wasm 0/-0 など) | **模型の限界の候補**。 無効演算の NaN 生成 (IE 系) が模型と違う。 eax は今回の入力では一致 |

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

- `X87_PROBE=1 python3 x87_fn_diff.py` → exit 1 (3 本の構造が一致しないため。 期待どおり)。
- 既定 `python3 x87_fn_diff.py` → PASS (exit 0、wall 8.698 s、user 8.270 s)。 既存 2 本の値は §1 と REPORT_APPENDIX_2989 §3 のとおり。
- `--nega` → 検出 (exit 0)。 `--nega-lower` → 検出 (exit 0)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ott_x87.h` が例外フラグ (IE/DE/ZE/OE/UE/PE/SF) と C1 を持たない。 eax の差 (`0x541`・`0x228`/`0x229`) の模型側の実装 | 3 本の構造 gate を通せない。 模型の限界の記録は本付録で満たし、模型の拡張は未着手 | #4103 (PLG-G2-46・子。親 #4064) |
| `0x1000bf60` の NaN 生成の差 (無効演算の結果) | 原因の機械的な分類が未了 | #4105 (PLG-G2-47・子。親 #4064) |
| `0x10009eb5` の `frndint` 後の NaN | `frndint` の模型は PLG-G2-23 (#2966) の範囲 | #2966 (PLG-G2-23) |
| issue 本文の前提 (`REPORT_APPENDIX_3715.md`) が repo に無い | 前提の実測値を照合できない | PM 確認 (#3715) |
