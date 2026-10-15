# REPORT_APPENDIX_5046 — x87 例外フラグ (IE/DE/ZE/OE/UE/PE/SF) と C1 の native 突合 (PLG-G2-70)

既知類型との関係: 模型の限界 (`ott_x87.h` が例外フラグを持たず、C1 を比較・fxam の後だけ持つ)。 `docs/DEFECTS.md` の既存 ID へは当てていない。 方式は `docs/DECISIONS.md` D28 (f80→f64)。

- 親: #4103 (PLG-G2-46)。 issue 本文の受入条件 (例外フラグ IE/OE/PE/SF と C1 の突合) は本付録で満たす。 模型の拡張は本 issue の範囲外 (下の §4)。
- 試験: `tools/plugins/slayer_engine_ia32/x87_flags_diff.c`。 素材 (fl-win64) は使わない。 ホストの gcc と `tools/ott/rt` の模型だけで動く。
- 測定 commit: 本付録を含む PR の commit (コードを変えた最後の commit は下の §5 の表)。 再現コマンドは §3。
- 起動・GUI に関わらない (製品 KPI は対象外)。

## 1. 結論

- 演算ごとの突合で、**模型が立てて native が立てないフラグ bit は 0 件** (FCW 0x037f・0x027f の両方)。 模型の誤りは見つからなかった。
- 逆に、**native が立てて模型が立てないフラグは多数** (IE・DE・ZE・OE・UE・PE)。 模型はこれらを持たない (ott_x87.h 制限 4 と flag 未モデル) ので、模型の限界として確定する。
- C1 は、比較・fxam 以外の算術命令で native が立てる (丸め方向) が、模型は持たない (ott_x87.h 制限 6・ADR D28 制限 6 と同じ)。 fxam の C1 (符号) は native と模型が 19 行全部で一致 (正の対照)。
- ゼロ除算 (`1/0`) で native が ZE を立てる (負の対照。 読みが機能していることの確認)。

## 2. 方法

- 入力: `0.0, -0.0, ±1, 3, 0.1, ±1e300, ±1e-300, 1e-310, 最小 denorm, 2^53+1, 1e308, DBL_MIN` の 14 値と、`±inf`・`qNaN`・`-qNaN`・`sNaN` の 5 値 (計 19 値)。 2 項演算は 19×19 = 361 行。
- native: `fninit` と `fldcw` で FCW を決め、入力を `fldl` で積み、`fnclex` で読み込みのフラグを消してから演算し、`fnstsw` で FSW を読む。 読込みの IE/DE (sNaN・denorm の読み) を演算の結果と混ぜないため。
- 模型: `x87_fadd` 相当の `x87_arith`・`x87_fcom`・`x87_fxam`・`x87_fist32`・`sqrt` を呼び、`ott_fsw` を読む。 模型は読込みのフラグを持たない。
- 観測対象: FSW の IE・DE・ZE・OE・UE・PE・SF (bit 0..6) と C1 (bit 9)。 C0/C2/C3 と ES (bit 7) は外す (C0/C2/C3 は既存の `x87_crosscheck.py`・`x87_branch_nan.py` が見る)。
- FCW: `0x037f` (拡張 64bit = fninit 既定) と `0x027f` (f64 = 模型の精度)。 模型は精度を f64 に固定する (制限 1) ので、`0x027f` の表が模型との比較の本命。
- 値の突合: 演算の結果 (f64 の bit) も比べる。 `value bit-diff` は全演算で 0 (`fistp`・`fstp m32` は整数・float の値、比較・fxam は値なし)。

## 3. 実測

コマンド (ws-5046 の worktree):

```
cd tools/plugins/slayer_engine_ia32
gcc -O0 -Wall -Wno-unused-function -I ../../ott/rt -o work/x87flags/x87_flags_diff x87_flags_diff.c ../../ott/rt/ott_cpu.c -lm
./work/x87flags/x87_flags_diff
```

結果 (exit 0 = PASS。 対照が崩れたら exit 1)。 「行数」は試行の総数、「native が立てた行」は観測 bit (IE DE ZE OE UE PE SF C1) を 1 つ以上立てた行の数、「模型のみの bit」は模型が立て native が立てない bit の件数:

| 演算 | 行数 | FCW | native が立てた行 | 模型が立てた行 | native のみの bit (件数) | 模型のみの bit |
|---|---:|---|---:|---:|---|---:|
| fadd | 361 | 0x037f | 182 | 0 | IE 39・DE 66・OE 1・PE 115・C1 11 | 0 |
| fadd | 361 | 0x027f | 182 | 0 | IE 39・DE 66・OE 1・PE 115・C1 1 | 0 |
| fsub | 361 | 0x037f | 179 | 0 | IE 39・DE 66・PE 112・C1 6 | 0 |
| fsub | 361 | 0x027f | 179 | 0 | IE 39・DE 66・PE 112 | 0 |
| fmul | 361 | 0x037f | 151 | 0 | IE 45・DE 66・OE 17・UE 22・PE 64・C1 26 | 0 |
| fmul | 361 | 0x027f | 151 | 0 | IE 45・DE 66・OE 17・UE 22・PE 64・C1 19 | 0 |
| fdiv | 361 | 0x037f | 184 | 0 | IE 45・DE 66・ZE 24・OE 25・UE 24・PE 88・C1 52 | 0 |
| fdiv | 361 | 0x027f | 184 | 0 | IE 45・DE 66・ZE 24・OE 25・UE 22・PE 88・C1 26 | 0 |
| fsqrt | 19 | 0x037f | 10 | 0 | IE 3・PE 7・C1 3 | 0 |
| fsqrt | 19 | 0x027f | 10 | 0 | IE 3・PE 7 | 0 |
| fcompp | 361 | 0x037f | 105 | 0 | IE 105 | 0 |
| fcompp | 361 | 0x027f | 105 | 0 | IE 105 | 0 |
| fxam | 19 | 0x037f | 5 | 5 | なし (C1 は 0 行の差) | 0 |
| fxam | 19 | 0x027f | 5 | 5 | なし (C1 は 0 行の差) | 0 |
| fistp m32 | 19 | 0x037f | 14 | 0 | IE 9・PE 5 | 0 |
| fistp m32 | 19 | 0x027f | 14 | 0 | IE 9・PE 5 | 0 |
| fstp m32 | 19 | 0x037f | 8 | 0 | OE 3・UE 4・PE 8・C1 4 | 0 |
| fstp m32 | 19 | 0x027f | 8 | 0 | OE 3・UE 4・PE 8・C1 4 | 0 |

- 注: `fnclex` 後の読みで、fadd の表は PE・IE・DE などが native のみ。 fcompp の IE 105 は sNaN 入力の比較による。
- 正の対照: `fxam` の C1 (符号) は両 FCW で 19 行全部一致 (C1 mismatch 0)。
- 負の対照: `1/0` で native が ZE (`fsw 0004`) を立てる。
- 模型のみの bit 合計: 0 (両 FCW)。 PASS。
- 値 (f64 の bit): 全演算で差 0。

## 4. 解釈と未解決

- **受入条件の答え**: IE/OE/PE/SF と C1 は、native と模型の突合で「模型は native の立てた bit を一切立てない」(模型のみの bit 0) ことを機械的に確かめた。 逆に、native のみの bit は模型の限界として数えた。 模型がフラグを持つかどうかは、この表が正本。
- 演算の結果 (値) は全行一致。 フラグだけが模型の限界。 つまり「値は合う・フラグは立たない」の型。
- PE (精度例外) は f64 の FCW (0x027f) でも残る (表の 0x027f の行)。 模型が丸めの例外を持たないことと整合する (推定。 丸めの原因は未切り分け)。
- `fistp m32` の IE・PE、`fstp m32` の OE・UE・PE は、模型の `x87_fist32` と `(float)` の変換が例外を立てないことと整合する (推定。 未切り分け)。
- C1 は、算術命令で native が立てる値 (丸め方向) を模型が持たない。 ADR D28 制限 6 と同じで、新しい限界ではない。
- **模型を直す場合 (#4103 の子・未測定)**: フラグを `ott_fsw` に持たせれば表の native のみの bit が一致しうるが、これは未測定の推定。 f64 と f80 の範囲差 (ADR 制限) が残るので、一致は部分的と見込む。 本付録は模型を変えていない。
- 未解決: 模型の拡張は未着手。 eax の差 (`0x541`・`0x228`/`0x229`) を模型で説明できるかは #4103 の範囲。 `0x1000bf60` の NaN 生成の差は #4105。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 模型が IE/DE/ZE/OE/UE/PE/SF を持たない (本付録 §3 の native のみの bit 全件) | 3 本の構造 gate を通せない (#4064) | #4103 (親 #4064) |
| 模型が算術命令の C1 (丸め方向) を持たない | fadd 等の C1 が模型と違う (本付録 §3) | ADR D28 制限 6・#3749 (既存) |

## 5. 測定の commit と検証

- 変更は新規 2 ファイル (`x87_flags_diff.c`・`REPORT_APPENDIX_5046.md`) と `docs/DOC_MAP.md` の登録だけ。 既存の x87 試験 (`x87_fn_diff.py`・`x87_trans_direct.c`・`x87_branch_nan.py`) は触らない。
- 測定 commit と検証 HEAD は PR 本文に書く (commit 後に確定するため)。
