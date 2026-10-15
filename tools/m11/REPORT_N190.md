# REPORT N190 — xmm 入力の読み幅を scalar double (`*sd`) に合わせる (#3641, 親 #2902)

既知類型との関係: D5 (`docs/DEFECTS.md`、既知 (F2): xmm 引数の落ち) の判定 (`p0c/k80abi.py` の `scan_function`) の修正。`fix_xmm_args.py` (`M11_XMM_ARGS=1`) が使う。新規類型は無し。

## 1. 結論

- `tools/plugins/p0c/k80abi.py` の xmm 入力の読み幅を機械語の命令に合わせた。`*sd` (addsd・sqrtsd 等) は 64 bit、`*ss` は 32 bit。cvt 系は変換元の幅で決める (cvtsd2ss・cvtsd2si・cvttsd2si は 64、cvtss2sd・cvtss2si は 32)。packed 整数の `*sd` (pmaxsd・vpmaxsd 等) は語尾が sd でも 128 bit 演算なので 32 bit のまま (除外)。
- main 構成 (`M11_XMM_ARGS=1`、`NO_CONV` で `function_40c650` を除外) の survey (942 unit) を基準 (`M11_XMM_ARGS=0`) と比べ、**unit 別差 0 件**・ok 喪失 0 件・unit 838/882/885 は ok。survey JSON の sha256 は両 arm で一致。測定 commit `4e54d0000` で 3 回実測し、結果は同一 (表 2)。
- 判定の変更が IR に効くのは 3 callee の枠型だけ (表 1)。`function_40c650` は arity 不一致で skip のまま。
- 判定を誤ると落ちる検査: `tools/plugins/p0c/test_k80abi_width.py` (機械語 10 ケース、PE 不要)。旧判定に差し替えると 3 件、packed の除外を外すと 2 件 FAIL (§5)。CI では回らない (手動実行のみ)。
- issue 本文の「枠型が変わる 8 件」は、`*sd` を語尾だけで判定した場合の一覧と一致する。そのうち 4 件 (`63a690`・`664ac0`・`668110`・`63a6b0`) は先頭の read 命令が `cvtss2sd` (源は単精度) なので float が正しい。cvt の源幅で判定し、この 4 件は変えない (表 1)。

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

- PE: fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…` を実測で確認)。`tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開。
- IR: `work-m11` の `tools/m11/work/boot_final.ll` (生成 commit 不明。tarball は `ir_conditions.json`・`qstore_report.json` を含まない)。build の qstore 適用後の `ir_sha256` は `a0f75f92…` (`m11_cond.py` が記録。本測定でも一致)。
- `work/ir_conditions.json` は手で作った (REPORT_N1479 §2 と同じ扱い)。内訳と根拠:
  - `ldfix=applied`: N1479 の記録を踏襲 (本測定では未検証)。
  - `ld108=disabled`・`ld115=disabled`・`r8b=disabled`: 3 pass (`fix_ld108`・`fix_ld115`・`fix_r8b815050`) を artifact の IR に再適用すると IR が変わった (適用されていないとみなす)。build は `M11_ALLOW_LD108_DISABLED=1` 等の opt-in で通した。
- 絶対値は使わない。判定に使うのは同一 IR 内の A/B だけ (REPORT_N1479 §5 と同じ)。canonical 基準との比較は未実施。
- toolchain: `[EMSDK]` (ランナー同梱、emcc 6.0.12) を使った。`toolchain-emsdk`・`toolchain-retdec`・`work-liftdiff` は指定せず、本測定では使っていない (oc_artifacts は `fl-win64` と `work-m11` のみ)。
- 実行環境: 4 vCPU。1 分 load は表 2 の下の表に記す。

## 4. 表 2: survey A/B (測定 commit `4e54d0000`、`bash tools/m11/m11_xmm_ab.sh`)

| 測定 | ok | trap | miss | noproc | oom | clobber | build 時の report |
|---|---:|---:|---:|---:|---:|---:|---|
| 基準 `M11_XMM_ARGS=0` | 872 | 21 | 47 | 1 | 1 | 0 | — |
| 最終 `M11_XMM_ARGS=1` | 872 | 21 | 47 | 1 | 1 | 0 | fixed 48 / skipped 704 / callsite_zero_args 105 |

- **unit 別差 0 件 (942 本)**。ok 喪失 0 件・ok 獲得 0 件。unit 838/882/885 は両 arm で ok。判定器は `[negctl]` で 838 の改変写しを検出 (`loss [838] / watch [838]`)。以上は 3 回の測定すべてで同一。
- survey JSON の sha256 は両 arm・3 回すべてで一致: `cb1ba82321c5bd111e53f785e3ae55f106dde3d9019300ca5e37d594e0dc73e4`。
- 空振りでないこと: `boot_final3.ll` の sha256 は両 arm で異なる (基準 `82424799…`、最終 `32df2d3d…`)。opt-in が IR を変えている。3 回とも同一値。
- 所要 (実測。wall は `date +%s` の差、load は `/proc/loadavg` の 1 分平均):

| 測定 | commit | 所要 (wall) | load 1 分平均 (開始 → 終了) |
|---|---|---:|---|
| 1 | `4e54d0000` | 1 分 30 秒 | 0.41 → 0.90 |
| 2 | `4e54d0000` | 1 分 28 秒 | 0.70 → 0.93 |
| 3 | `4e54d0000` | 1 分 27 秒 | 0.93 → 0.99 |
| 参考 (初回) | `fd03fb1b0` | 1 分 49 秒 | 未記録 |
| 参考 (自己再実行) | `0066a3ade` | 1 分 48 秒 | 未記録 |
| 参考 (レビュワー再実行) | `0066a3ade` | 2 分 00 秒 | 未記録 |

- 測定 commit 上の n=3 の min–max は 1 分 27 秒〜1 分 30 秒。参考の 3 回 (旧版、load 未記録) を含めた 6 回の min–max は 1 分 27 秒〜2 分 00 秒。参考回と本測定の差の原因は未確定 (並列数は同じ 4 vCPU、load は測定ごとに記録できた分だけ)。survey の結果 (sha256・unit 別差) は参考回も全て一致。

## 5. 判定の検査 (`test_k80abi_width.py`)

- `python3 tools/plugins/p0c/test_k80abi_width.py` → OK (10 ケース: `addsd`・`sqrtsd`・`movsd`・`movq`・`cvtsd2ss`・`mulss`・`movss`・`cvtss2sd`・`pmaxsd`・`vpmaxsd`)。
- ネガティブコントロール (測定 commit `4e54d0000` で実施):
  - (a) 接頭辞だけで判定する旧版 (`*sd` を 32 とする) に差し替え → `addsd`・`sqrtsd`・`cvtsd2ss` の **3 件 FAIL**。
  - (b) packed の除外を外す (語尾 `sd` だけで 64 とする) → `pmaxsd`・`vpmaxsd` の **2 件 FAIL**。
- **手動実行のみ (CI 未登録)**。`.github/workflows/scripts-test.yaml` が拾うのは `.github/scripts/tests/test-*.sh`・`tools/pm/test_*.sh`・`tools/pm/test_*.py` だけで、本テストは対象外。本テストは capstone を要し、その job は capstone を入れていない。登録には依存の導入と workflow の変更が要るため、本 PR では行わない。

## 6. 他の consumer への効き

- M11 経路 (`fix_xmm_args.py`): 表 1 の 3 callee だけ。両 arm の `boot_final3.ll` の sha256 は、packed 除外を入れる前の版 (`fd03fb1b0`) の測定と同一 (`82424799…`・`32df2d3d…`)。packed 除外は IR を変えていない。
- PE 全体 (一時スクリプトで全関数 `scan_function` を走査し、旧版 `fd03fb1b0^`・`fd03fb1b0`・`4e54d0000` の読み幅 (`xmm_width`) と読む xmm の集合を比較。リポジトリには置いていない):

| PE | 関数数 | xmm 入力を持つ関数 | 読み幅が変わる (`fd03fb1b0^` → `4e54d0000`) | packed 除外の効果 (`fd03fb1b0` → `4e54d0000`) | 読む xmm 集合の変化 |
|---|---:|---:|---:|---:|---:|
| `block18983_PE.bin` (kernel 側) | 11,736 | 226 | 34 | 0 | 0 |
| `block00031_PE.bin` (m11 側) | 57,816 | 1,259 | 217 | 0 | 0 |

- p0c の kernel 側 (`k80_diff.py` が `xmm_width` を読む、`k80_argfix.py` の `__asm_movaps` 分岐 `xw.get(xmm,32)==32`): p0c の kernel 一覧 (`work/f80_classes.json`) が素材に無く、p0c e2e は未実行。kernel への効きは未測定 (§7)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_40c650` の変換で unit 149・158 が退行する原因 | 40c650 は skip のまま。変換は戻していない | 親 #2902 (open のまま残る) |
| p0c kernel の e2e (`k80_diff.py`・`k80_argfix.py`) の再測定。`block18983` の 34 関数の読み幅変化が kernel に当たるか | kernel 側の結果が変わる可能性は未確認 | 本 PR の未解決表で追跡 (測定のみのため子は起票しない) |
| `work-m11` の IR 条件 (ldfix 手記録、ld108・ld115・r8b 未適用、生成 commit 不明) | 絶対値は使えない。A/B の判定だけ有効 | 本 PR の未解決表で追跡 (追跡 issue は無し) |
| 既定 `M11_XMM_ARGS` は OFF のまま | 既定 ON 化は本 PR の範囲外 | PM 判断 |

## 8. 差分 (WORKFLOW §6)

- 測定 commit: `4e54d0000` (コードを変えた最後の commit。`tools/plugins/p0c/k80abi.py` と `test_k80abi_width.py`)。
- `git diff 4e54d0000 HEAD -- tools/m11 tools/plugins/p0c tools/plugins/lift/passes ':!tools/m11/REPORT_N190.md'` → 出力なし (差分 0)。本 REPORT と `docs/DOC_MAP.md` だけが後から増える。
- 測定 commit の前 (`fd03fb1b0`) からの差分は、`k80abi.py` の判定 1 行 (packed の除外) と docstring、テストの 2 ケース。

## 9. 再現

```
export FL_WIN64_DIR=<fl-win64 展開先> M11_ALLOW_LD108_DISABLED=1 M11_ALLOW_LD115_DISABLED=1 M11_ALLOW_R8B_DISABLED=1
cd tools/m11
python3 m11_cond.py --reset pe="$FL_WIN64_DIR/extracted/block00031_PE.bin" ldfix=applied ld108=disabled ld115=disabled r8b=disabled && python3 m11_cond.py --bind work/boot_final.ll
rm -f work/boot_final.xa.ll work/boot_final3.ll
bash m11_xmm_ab.sh
python3 ../plugins/p0c/test_k80abi_width.py
```
