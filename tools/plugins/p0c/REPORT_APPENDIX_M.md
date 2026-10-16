# tools/plugins/p0c REPORT 付録 M — #5832 (E7: x86_fp80 ↔ i80 bitcast の展開)

> 本体の索引は `tools/plugins/p0c/REPORT.md` §26。 PR #5858 の本文から、測定値・表をここへ移した (`docs/WORKFLOW.md` §5)。

## 1. 変換 bit 一致 (`f80b_rt/run.sh`)

方式: `expand_f80_bitcasts` (`f80_lower.py`) が出した IR を emcc (wasm32) でビルドし、host (x86-64) の `long double` (x87) を期待値として照合する。`gen_cases.c` が期待値を作る。

| 方向 | 件数 | 不一致 | 測定 commit |
|---|--:|--:|---|
| double → x87 像 | 200,000 | 0 | `2481d3a0e` |
| x87 像 → double (subnormal・tie 含む) | 200,000 | 0 | `2481d3a0e` |

### 1.1 修正 (指摘 #5858 round 1)

`_f80b_from_image` の carry かつ subnormal 結果の誤りを直した。`sn` と `low` が carry 後の指数 `E` を使っていたため、subnormal の丸め位置が 1 桁ずれた。`E0` (carry 前の指数) で計算するよう変えた。

固定ベクタ 3 件 (`gen_cases.c` の `fx_m` / `fx_e`) を追加した。`run.sh` が必ず検査する。

| 入力 (m, se) | 修正前 (`9418e1050`) | 修正後 (`842bc5ac3`) | native (x87→double) |
|---|---|---|---|
| `0xFFFFFFFFFFFFFFFF`, `0x3BFD` | `0x0.4p-1022` | `0x0.2p-1022` | `0x0.2p-1022` |
| `0xFFFFFFFFFFFFFFFF`, `0x3BFE` | `0x0.8p-1022` | `0x0.4p-1022` | `0x0.4p-1022` |
| `0xFFFFFFFFFFFFFD32`, `0x3BE5` | `0x0.0000004p-1022` | `0x0.0000002p-1022` | `0x0.0000002p-1022` |

修正前の `f80_lower.py` で同じ検査 (固定ベクタ込み) を実行すると `from: n=200003 fail=3` で rc 1。修正後は `from: n=200003 fail=0` で rc 0。

### 1.2 修正後の検査 (emcc 版)

emsdk を導入し (`git clone --depth 1 https://github.com/emscripten-core/emsdk.git` → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12`。`tools/m1/flags.sh` の pin と同じ版)、`EMSDK` を設定して `run.sh` を実行した。

- 測定 commit: `2481d3a0e` (HEAD。`EMSDK=<[EMSDK] のルート> bash tools/plugins/p0c/f80b_rt/run.sh` を今回の run で実行)
- `to: n=200000 fail=0`
- `from: n=200003 fail=0`
- rc 0・所要 3.2 s real (load 1.1 前後、4 core)

## 2. 共有鎖の退行 (T0 / T1, `batch_lift.sh --tier T0/T1`)

測定 commit: `2481d3a0e` (HEAD。`842bc5ac3` 以降のコードを含む)。 素材: `fl-win64` (展開先は `$RUNNER_TEMP/analysis/win64`・`FL_WIN64_DIR` で指定)・`toolchain-retdec` (`[RETDEC]`)・`toolchain-emsdk` (`[EMSDK]`)。

入力の再構成 (`fl-win64` tarball に `block_manifest.json` / `nsis_blockmap.json` が無いため): `python3 tools/plugins/f2/mk_blockmap.py` (PLUGIN_MATRIX.json から block 対応表を作る。`docs/REFERENCES.md` の Actions 用代替) → `inventory/win_scan.py`・`win_funcs.py`・`win_unique.py`・`win_abi.py` → `lift/plugin_closure.py --all`。 inventory 全体は 8 分 24 秒 (foreground)。

- T0: `batch_lift.sh --tier T0` の実行 3 分 28 秒 (foreground、rc 0)。 41 blocks。 `lift_rc` 0 が 41/41・`emcc_c_rc` 0 が 41/41。 `f80_funcs` は 41 件すべて 0。
- T1: `batch_lift.sh --tier T1` の実行 7 分 47 秒 (rc 0)。 45 blocks。 closure 関数 2,835。 `lift_rc` 0 が 45/45。 `emcc_c_rc` 0 が 44/45。 唯一の不通過は 24161 ReWired (`emcc_c_rc` 1・`f80_funcs` 2)。 REPORT §4.3 の既存の結果と同じ。
- 退行 0。 `emcc_c_rc` の不通過は既存の 24161 のみで、本 PR による増減は無い。
- 所要と load: T0 の起動直後の load は 10 台 (inventory 直後)、T1 の終了時 load は 1.0。 4 core。

注: `842bc5ac3` の修正 (subnormal の丸め位置) の効果は、この再測定で新コードの値として取った。 旧値 (`ce3872372`) は付録 M 自体からは外した (§4 の鮮度の証跡で差分を示す)。

## 3. 19165 engine (`engine_lift.sh 19165 900` → `engine_f80_subset.sh`)

測定 commit: `2481d3a0e` (HEAD)。 測定の入力は §2 と同じ (`fl-win64` 展開物・`toolchain-retdec`)。 範囲ファイルは `avx_bad_ranges.py 19165` が出した 78 件 (`tools/plugins/work/reverb_delay/bad19165.out`、gitignore)。

| 項目 | 今回の実測 (`2481d3a0e`) |
|---|---|
| `engine_lift.sh 19165 900` (`ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <78 件>" ENGINE_TAG=_noipp_nobad`) | rc 0・wall 10 分 23 秒 |
| summary (`pdata_funcs,lift_rc,defines,f80,unimpl,emcc_c_rc,fixcmp,emcc_c_rc_after_fixcmp,lift_s`) | `2000,0,2608,6,136,139,0,139,608` |
| `emcc -c` (`e.final.ll`) の最初の error | `do not know how to soften fp_extend` |
| `emcc -c` (`e.final.ll`) rc | 139 (segfault) |
| `emcc -c` (`e.fixcmp.ll`) の最初の error | `do not know how to soften fp_extend` (rc 139) |
| 部分集合 (`engine_f80_subset.sh 19165`): f80 関数を除外 | `f80_excluded=5`・`f80_body_full=5`・`f80_body_sub=0`・除外集合 = f80 本体 (`same`) |
| 部分集合の `emcc -c` rc | 0 (gate PASS) |
| 同じ入力の無改変 `emcc -c` rc (NC) | 139 |

- 補足: summary の f80 は 6、gate の `f80_body_full` は 5。 差の原因は未確認。 部分集合の検査 (除外 5 件と本体の f80 集合の一致) は PASS。
- 19165 の segfault の起点 (`function_1800ceec0`) は、今回は未確認 (`engine_lift.sh` の出力に含まれない)。
- 本 PR による `emcc -c` の最初の error は、旧 (`ce3872372`) の `invalid cast opcode ... 'double' to 'i80'` (E7) から `do not know how to soften fp_extend` に変わった。 segfault (rc 139) は既存の経路で残る。 この 19165 の残る欠陥 (f80 関数 5 件) は本 PR の範囲外で、部分集合 gate で到達性のみ確認する。

## 4. 鮮度: 旧測定からの差分

測定 commit `2481d3a0e` のコード差分 (`git diff 2481d3a0e HEAD -- tools/plugins/p0c ':!tools/plugins/p0c/REPORT*'`) は 0 行 (測定 commit = HEAD)。 以下は旧測定 (`ce3872372`) からの差分の要点。 `ce3872372` → `8e263e380` の差分の全文は `REPORT_APPENDIX_M2.md` にある (`8e263e380` 以降の差分は下の要点で扱う):

- `f80b_rt/run.sh` の 1 行 (`EMCC` の解決を `$EMSDK` 必須にする変更)。 `EMCC` 変数は `command -v emcc` が先なので、 測定値は影響を受けない (`run.sh` の検査内容は変わらない)。 harness の変更であり、 測定対象の変換は変わらない。
- 続けて `842bc5ac3` の修正 (`f80_lower.py` の `sn` / `low` と `gen_cases.c` の固定ベクタ)。 これは測定対象の変換を変える。 §1 と §2・§3 は測定 commit `2481d3a0e` で再測定した。
- 旧差分の全文: `REPORT_APPENDIX_M2.md` (`ce3872372` → `8e263e380`)。 測定 commit から HEAD までの差分は空 (上の注)。
