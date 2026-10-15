# REPORT N190 — xmm 入力の読み幅を scalar double (`*sd`) に合わせる (#3641, 親 #2902)

既知類型との関係: D5 (`docs/DEFECTS.md`、既知 (F2): xmm 引数の落ち) の判定 (`p0c/k80abi.py` の `scan_function`) の修正。`fix_xmm_args.py` (`M11_XMM_ARGS=1`) が使う。新規類型は無し。

## 1. 結論

- `tools/plugins/p0c/k80abi.py` の xmm 入力の読み幅を機械語の命令に合わせた。`*sd` (addsd・sqrtsd 等) は 64 bit、`*ss` は 32 bit。cvt 系は変換元の幅で決める (cvtsd2ss・cvtsd2si・cvttsd2si は 64、cvtss2sd・cvtss2si は 32)。
- main 構成 (`M11_XMM_ARGS=1`、`NO_CONV` で `function_40c650` を除外) の survey (942 unit) を基準 (`M11_XMM_ARGS=0`) と比べ、**unit 別差 0 件**・ok 喪失 0 件・unit 838/882/885 は ok。survey JSON の sha256 は両 arm で一致。コミット済み HEAD で 2 回実測し、結果は同一 (表 2)。
- 判定の変更が IR に効くのは 3 callee の枠型だけ (表 1)。`function_40c650` は arity 不一致で skip のまま。
- issue 本文の「枠型が変わる 8 件」は、`*sd` を語尾だけで判定した場合の一覧と一致する。そのうち 4 件 (`63a690`・`664ac0`・`668110`・`63a6b0`) は先頭の read 命令が `cvtss2sd` (源は単精度) なので float が正しい。cvt の源幅で判定し、この 4 件は変えない (表 1)。
- 判定を誤ると落ちる検査: `tools/plugins/p0c/test_k80abi_width.py` (機械語 8 命令、PE 不要)。旧判定に差し替えると 3 件 FAIL (§5)。

## 2. 表 1: 枠型の変化 (同一 IR・`fix_xmm_args.py` の report)

| callee | 旧判定 (接頭辞のみ) | 語尾判定 (素朴な `*sd`) | 採用 (cvt は源幅) | 読み幅を決める最初の read |
|---|---|---|---|---|
| `function_1311f70` | float → **double** | double | **double** | `mulsd xmm0,xmm2` (xmm0) |
| `function_442420` | float → **double** | double | **double** | `mulsd xmm0,xmm1` (xmm0) |
| `function_66e5e0` | float → **double** (xmm2) | double | **double** | `subsd xmm0,xmm2` (xmm2) |
| `function_40c650` | float → double (skip) | double | skip (arity 不一致・NO_CONV) | `sqrtsd xmm0,xmm0` |
| `function_63a690` | float (変化なし) | double (誤り) | float | `cvtss2sd xmm0,xmm0` |
| `function_664ac0` | float (変化なし) | double (誤り) | float | `cvtss2sd xmm0,xmm0` |
| `function_668110` | float (変化なし、xmm1) | double (誤り) | float | `cvtss2sd xmm0,xmm1` |
| `function_63a6b0` | float (変化なし) | double (誤り) | float | `cvtss2sd xmm0,xmm0` |

- 語尾判定は issue の 8 件と一致した (`endswith('sd')` で `cvtss2sd` も 64 になる)。採用案は 4 件 (1311f70・442420・66e5e0・40c650) だけ変わる。
- `fix_xmm_args.py` の IR 差分 (`xa_before` と `xa_after` の `diff`) は、関数定義と call site で 3 callee (1311f70・442420・66e5e0) のみ。他の関数の IR は変わらない。

## 3. 測定条件

- PE: fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…` 一致)。`tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開。
- IR: `work-m11` の `tools/m11/work/boot_final.ll` (生成 commit 不明。tarball は `ir_conditions.json`・`qstore_report.json` を含まない)。build の qstore 適用後の `ir_sha256` は `a0f75f92…` (`m11_cond.py` が記録)。
- `work/ir_conditions.json` は手で作った (REPORT_N1479 §2 と同じ扱い)。内訳と根拠:
  - `ldfix=applied`: N1479 の記録を踏襲 (本測定では未検証)。
  - `ld108=disabled`・`ld115=disabled`・`r8b=disabled`: 3 pass (`fix_ld108`・`fix_ld115`・`fix_r8b815050`) を artifact の IR に再適用すると IR が変わった (適用されていないとみなす)。build は `M11_ALLOW_LD108_DISABLED=1` 等の opt-in で通した。
- 絶対値は使わない。判定に使うのは同一 IR 内の A/B だけ (REPORT_N1479 §5 と同じ)。canonical 基準との比較は未実施。
- toolchain: `[EMSDK]` (ランナー同梱、emcc 6.0.12) を使った。`toolchain-emsdk` 素材は展開していない (同梱の emsdk で代替)。`toolchain-retdec` は未使用。`work-liftdiff` は展開のみ (本測定では未使用。`tools/liftdiff/ldlib/pe.py` は変更していない)。
- 実行環境: 4 vCPU、load 0.5〜1.0。

## 4. 表 2: survey A/B (コミット済み HEAD `fd03fb1b0`、`bash tools/m11/m11_xmm_ab.sh`)

| 測定 | ok | trap | miss | noproc | oom | clobber | build 時の report |
|---|---:|---:|---:|---:|---:|---:|---|
| 基準 `M11_XMM_ARGS=0` | 872 | 21 | 47 | 1 | 1 | 0 | — |
| 最終 `M11_XMM_ARGS=1` | 872 | 21 | 47 | 1 | 1 | 0 | fixed 48 / skipped 704 / callsite_zero_args 105 |

- **unit 別差 0 件 (942 本)**。ok 喪失 0 件・ok 獲得 0 件。unit 838/882/885 は両 arm で ok。判定器は `[negctl]` で 838 の改変写しを検出 (`loss [838] / watch [838]`)。
- survey JSON の sha256 は両 arm で一致: `cb1ba82321c5bd111e53f785e3ae55f106dde3d9019300ca5e37d594e0dc73e4`。
- 空振りでないこと: `boot_final3.ll` の sha256 は両 arm で異なる (基準 `82424799…`、最終 `32df2d3d…`)。opt-in が IR を変えている。
- 所要: スクリプト全体の wall time 1 m 49 s (1 回目) と 1 m 48 s (HEAD での再実行)。n=2 の参考値。

## 5. 判定の検査 (`test_k80abi_width.py`)

- `python3 tools/plugins/p0c/test_k80abi_width.py` → OK (`addsd`・`sqrtsd`・`movsd`・`movq`・`cvtsd2ss` が 64、`mulss`・`movss`・`cvtss2sd` が 32)。
- ネガティブコントロール: 旧判定 (接頭辞のみ) に差し替えると `addsd`・`sqrtsd`・`cvtsd2ss` の 3 件が FAIL。

## 6. 他の consumer への効き

- M11 経路 (`fix_xmm_args.py`): 表 1 の 3 callee だけ。`fix_xmm_args.py` は `k80_argfix.py` の `fix_movd_from_zero` / `fix_helper_operand_xmm` にも同じ `xmm_width` を渡すが、その効きは IR 差分に含まれる (上記 3 callee 以外に変化なし)。
- PE 全体 (`block18983_PE.bin`、関数 11,736 本、xmm 入力を持つ 226 本): 読み幅が変わる関数は 34 本 (旧 32 → 新 64)。読む xmm の集合 (`xmm_slots`) は 0 本で変化なし。
- p0c の kernel 側 (`k80_diff.py` が `xmm_width` を読む、`k80_argfix.py` の `__asm_movaps` 分岐 `xw.get(xmm,32)==32`): p0c の kernel 一覧 (`work/f80_classes.json`) が素材に無く、p0c e2e は未実行。kernel への効きは未測定 (§7)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_40c650` の変換で unit 149・158 が退行する原因 | 40c650 は skip のまま。変換は戻していない | 親 #2902 (open のまま残る) |
| p0c kernel の e2e (`k80_diff.py`・`k80_argfix.py`) の再測定。34 関数の読み幅変化が kernel に当たるか | kernel 側の結果が変わる可能性は未確認 | PR 本文の未解決 (測定のみのため子は起票しない) |
| `work-m11` の IR 条件 (ldfix 手記録、ld108・ld115・r8b 未適用、生成 commit 不明) | 絶対値は使えない。A/B の判定だけ有効 | #1479 (canonical 基準・OPEN) |
| 既定 `M11_XMM_ARGS` は OFF のまま | 既定 ON 化は本 PR の範囲外 | PM 判断 |

## 8. 差分 (WORKFLOW §6)

- 測定 commit: `fd03fb1b0` (コードを変えた最後の commit。`k80abi.py` と `test_k80abi_width.py`)。
- `git diff fd03fb1b0 HEAD -- tools/m11 tools/plugins/p0c tools/plugins/lift/passes ':!tools/m11/REPORT_N190.md'` → 出力なし (差分 0)。本 REPORT と `docs/DOC_MAP.md` だけが後から増える。

## 9. 再現

```
export FL_WIN64_DIR=<fl-win64 展開先> M11_ALLOW_LD108_DISABLED=1 M11_ALLOW_LD115_DISABLED=1 M11_ALLOW_R8B_DISABLED=1
cd tools/m11
python3 m11_cond.py --reset pe="$FL_WIN64_DIR/extracted/block00031_PE.bin" ldfix=applied ld108=disabled ld115=disabled r8b=disabled && python3 m11_cond.py --bind work/boot_final.ll
rm -f work/boot_final.xa.ll work/boot_final3.ll
bash m11_xmm_ab.sh
python3 ../plugins/p0c/test_k80abi_width.py
```
