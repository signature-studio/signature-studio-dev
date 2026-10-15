# REPORT_APPENDIX_4105 — x87 leaf 0x1000bf60 の ST(0) の NaN・ゼロの食い違いの分類 (PLG-G2-47)

既知類型との関係: 模型の限界 (無効演算の NaN 生成) の候補。 lowering の取り違えは、normal×normal の行に 1 件も出ないことで否定した (§2)。 `docs/DEFECTS.md` の既存 ID へは当てていない。
親: #4064 (付録 `REPORT_APPENDIX_4064.md` §1 の 0x1000bf60 行)。 子 #4105 (PLG-G2-47)。

- 測定 commit: `37ab14c3e` (`x87_fn_diff.py` に `f80pair` gen を追加した commit。 測定はこの commit の driver で行った)。
- 検証 HEAD: `37ab14c3e` (default gate と PROBE 付きの両方をこの commit で再現した)。
- 入力: fl-win64 の `block22434_PE.bin` (179,512 B・sha256 `84b64c43…e724a9`)。 乱数 seed 2989。 lift は `lift_text.py` の出力 (functions 479、被覆 86.18%)。
- 起動・GUI に関わらない (製品 KPI は対象外)。

## 1. 関数の構造

`0x1000bf60` は `fld tbyte [esp+0x10]` (X = a3..a5) と `fld tbyte [esp+4]` (Y = a0..a2) の後、次の 3 経路に分かれる。

- 経路 A (`jae` で抜ける): `mov eax,[esp+4]; or eax,[esp+8]; jne 0x1000c007` → Y の mantissa が 0 でなければ 0x1000c007 へ。 0 なら `0x1000c004: fdivp st(1)`。
- 経路 B: `0x1000c007` 以降で指数 (`[esp+0xc] & 0x7fff`) を見て、0 (denorm・zero) や 0x7fff (inf・nan) を分岐し、`fnstcw`・`fldcw` で丸め制御を書き換えて `fdivp` に抜ける。 丸め制御は一時的に変わる。
- `fdivp st(1)` の 1 命令だけが演算である (テーブル・整数演算は分岐の判定のみ)。 命令ごとの分類の対象は、この `fdivp` の入力 (X・Y の種類) と出力 (ST(0)) になる。

## 2. 測定 (4,000 行・seed 2989・`f80pair` gen)

入力の種類は X・Y それぞれ一様 (norm・denorm・unnorm・zero から選ぶ)。 `(X, Y)` の種類ごとの行数と、native と wasm の不一致の件数:

| X (`[esp+0x10]`) | Y (`[esp+4]`) | 行 | eax 不一致 | ST(0) 不一致 |
|---|---|---:|---:|---:|
| norm | norm | 631 | 0 | 0 |
| norm | zero | 297 | 0 | 0 |
| zero | norm | 334 | 0 | 0 |
| zero | zero | 156 | 0 | 0 |
| denorm | norm | 317 | 0 | 0 |
| denorm | zero | 152 | 0 | 152 |
| zero | unnorm | 156 | 0 | 80 |
| norm | unnorm | 321 | 0 | 321 |
| unnorm | norm | 332 | 0 | 332 |
| unnorm | unnorm | 160 | 0 | 72 |
| unnorm | zero | 160 | 0 | 85 |
| unnorm | denorm | 163 | 0 | 75 |
| denorm | unnorm | 157 | 0 | 88 |
| norm | denorm | 325 | 321 | 0 |
| zero | denorm | 167 | 157 | 167 |
| denorm | denorm | 172 | 162 | 172 |

- 合計: ST(0) 不一致 1,544 行・eax 不一致 640 行。 x87 深さ不一致 0 行。 OBJ 窓の不一致 0 行。
- ST(0) の不一致の中身 (float64 で `nan-num` 1,544 件 = NaN と非 NaN の食い違い。 float32 でも同じ)。 native → wasm の組: NaN→0・NaN→−0・0→NaN・−0→NaN・有限→NaN。 ±0 どうし・NaN どうしのビット差は 0 件。

## 3. 分類と切り分け

- **lowering の取り違え (演算の入れ替え) ではない**: 両オペランドが normal の行 (norm×norm 631 行) と、片方が zero で他方が normal の行 (norm×zero 297・zero×norm 334) では、ST(0) と eax が全件 bit 一致する。 除算の演算そのもの (`fdivp`) と符号・0 の扱いは模型と一致する。 この 3 つの組だけで 1,262 行の一致を確認した。
- **模型の限界 (非 normal オペランドでの例外処理)**: 不一致はすべて、X か Y が denorm・unnorm のいずれかの行に出る。 Intel の 80bit 実行で、非 normal オペランドの扱い (denormal・unsupported・無効演算の NaN 生成) は、`ott_x87.h` が持つ IE/DE/ZE 等の例外フラグ・C1 と結びつく。 `ott_x87.h` はこれらを持たないため、無効演算の NaN の生成を模型が再現できない。 これが ST(0) の NaN・ゼロの差の原因と判定する。
- **eax の不一致 (640 行) も同じ組に集中**: `(norm, denorm)`・`(zero, denorm)`・`(denorm, denorm)` の 3 組で、eax の不一致はこの 3 組だけに出る (321・157・162 行)。 denorm オペランドの例外フラグ (DE 等) が eax に出ると見る。 `docs/DEFECTS.md` の既存類型には当てない。
- **確定ではない点**: 「模型の限界」は、denorm・unnorm の例外処理が模型にないことの推定である。 フラグ単位 (IE・DE・ZE 等) の機械的な切り分けは、`ott_x87.h` の拡張 (#4103 の範囲) を要するため、本測定では行っていない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| denorm・unnorm の例外処理 (DE/IE 等のフラグ・NaN 生成) を模型に入れる。 フラグ単位の機械的な切り分け | ST(0) 1,544 行・eax 640 行の差 | #4103 (PLG-G2-46・子。 親 #4064) |
| 付録 `REPORT_APPENDIX_4064.md` §1 の 0x1000bf60 の行 (「eax は一致」「nan-num 2,022」) は、gen を変えた測定 (本付録) と食い違う | 親付録の数値が本測定と一致しない | PM 確認 (#4064 の付録の更新) |
