# liftlib #3145 — `ott_outhash` の JSON 失敗の切り分け (原因特定・受入 1)

- 親: #3067 (元の症状は `REPORT_APPENDIX_3067.md` §3.2)。担当 dir: `tools/liftlib/`。
- 基点: `origin/main` `0f283e9b` (#3098・#3156 は merge 済み)。
- **測定 commit (コードを変えた最後の commit)**: `6fe09885d` (`test(liftlib): pin ott_outhash failure when .wasm is missing (#3145)`)。
  差分確認: `git diff 6fe09885d HEAD -- tools/liftlib/liftlib tools/liftlib/tests` (本 PR で以後 code は変えていない)。

## 0. 結論 (原因の特定)

- **`Expecting value` の原因は `ott_m10.cjs.wasm` の欠落** (#3067 §3.2 の未切り分けを解消)。node は `.wasm` を読めないと stdout を出さずに `rc=1` で終わる。
  実測: `ott_m10.cjs` だけを置いた場所で `ott_outhash.mjs` を実行 → `rc=1`・stdout 0 byte・stderr `ENOENT: ... ott_m10.cjs.wasm`。`outhash_json` は stderr を例外に残す (T27b で固定)。
- 素材 `work-m6-ott` の tar には `tools/m10/work/ott_m10.cjs` と `ott_m10.cjs.wasm` の両方が入っている。#3067 issue 本文の「`.wasm` は未展開」が前回の原因と推定される (前回 run の展開内容は未確認)。両方を展開した今回は再現しなかった。
- 「約 7 分/module」は誤り。参照 module の outhash (42 組) は **0.47〜0.65 s** で終わる (下表)。

## 1. 環境 (実測)

- `$ARTIFACTS_DIR` の 3 素材を展開: `work-m6-ott` → worktree 直下 (`tools/m6/work/`・`tools/m10/work/` ほか)、`analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/` (`OTT_vst2_win64.dll`)、`toolchain-emsdk` → `$HOME/emsdk/` (`emcc` 有り)。
- 実行: `EMSDK_DIR=$HOME/emsdk OTT_DLL=$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll python3 -m liftlib ott --auto none`。
- `work-liftlib-targets` は無し (T4・T6 が未検証。§3)。

## 2. 切り分けの結果 (実測)

| 試行 | rc | 時間 | stdout | 結果 |
|---|---|---|---|---|
| 参照 `tools/m10/work/ott_m10.cjs` (+ `.wasm`) で `ott_outhash.mjs` (n=3) | 0 | 0.47 / 0.48 / 0.48 s | JSON 1 行・42 組 | 正常 |
| 生成 `tools/liftlib/work/ott/ott_gen.cjs` (+ `.wasm`) で同 (n=2) | 0 | 0.65 s / 同一出力 | JSON 1 行・42 組 | 正常 |
| 参照 `ott_m10.cjs` のみ (`.wasm` 欠落) | 1 | — | 0 byte | `ENOENT ... ott_m10.cjs.wasm` (`outhash_json` が例外に残す) |
| 存在しない cjs を `OTT_CJS` に渡す (前回) | 1 | — | 0 byte | `ERR_MODULE_NOT_FOUND` |

## 3. 受入 1 の判定と HEAD の e2e 実測 (`6fe09885d`)

- `python3 -m liftlib ott --auto none` (実測 **10.51 s**・maxrss 332,512 KB・load avg 0.28〜1.04): rc=1 (FAIL)
  - e2e: checks 8 / broken 0 / maxdev 0.0 / nbad 0 / trap rc 0 (PASS 相当)
  - outhash: `combos 42`・`distinct 34`・`f0_equal 3 / f0_total 21`・`equal false` → **JSON は読めた。SHA は不一致**。
  - IR 一致 (O1 は true。O2a〜O4 は false)。#3067 §3.2 の「`@ 81adaffa` 修正後 f0 3/21」と同じ値。
- **残る不一致の性質 (未判定)**: 修正後の `p1_legacy` 出力 (`%pc` 行の repmap 18 行) が参照 IR と違う。SHA 基準 (`--auto none` の 42/42) は修正前の P1 出力に依る。修正後の出力が正しいかは native 実機と未照合 (`REPORT_APPENDIX_3067.md` §6)。**基準差し替えは PM 判断・本件では行わない** (issue 本文の受入条件 3)。
- 全 unit (`python3 tests/test_unit.py`・`6fe09885d`・所要 323.6 s): **32 PASS / FAIL 2 (t4・t6)**。
  - t4・t6 は `work-liftlib-targets` 素材 (`liftlib/work/fa_gain/fa_gain.drc.ll`・FA の PE) が無いための FileNotFoundError。コードの不一致ではない。
  - 残件: #1270 由来の T6 / T9 / T26 は素材追加で実施 (`REPORT_APPENDIX_1270.md` §5・§6)。

## 4. 変更 (本 PR)

- `tools/liftlib/liftlib/recipes/ott.py` の `outhash_json`: #3156 で入れた版をそのまま使う (成功経路の値は変えない)。
- `tools/liftlib/tests/test_unit.py`: T27b を追加 (`.wasm` 欠落の再現: stdout 空・rc=1・stderr の ENOENT が例外に残ることを固定)。実行: `python3 -c "import sys; sys.path.insert(0,'tests'); import test_unit as T; T.t27(); T.t27b()"` → T27 ok・T27b ok。
- 旧記述の「約 7 分/module」「stdout の JSON 失敗の原因未特定」は §0 の実測で置き換えた。

## 5. 旧版の記録

- `eb4ce08f` 時点の旧記録 (参照 module の outhash 0.47 s・存在しない cjs の `ERR_MODULE_NOT_FOUND`・素材不足の 8 FAIL) は Git 履歴 (`git show eb4ce08f:tools/liftlib/REPORT_APPENDIX_3145.md`) に残す。本文には再掲しない。
- 旧記録の「T9・T26 FAIL」は素材を揃えた §3 の実測で PASS (32/34 PASS・残りは T4・T6)。
