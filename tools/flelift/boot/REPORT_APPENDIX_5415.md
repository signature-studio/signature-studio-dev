# REPORT_APPENDIX_5415 — FLE-45 (#5415): InitContext.InitTable (0x15eac90) の 0 化の時点

測定 commit: `b0c6e835a` (`fle_boot.c` の `py_watch` に `0x15eac90` と `ippsZero_8u` 直後 (site 9) を足した。挙動は変えず記録だけ増やした)。
コード差分: `fle_boot.c` は `git diff 3a3a1f152 b0c6e835a -- tools/flelift/boot/fle_boot.c` で監視 slot 2 本 (`0x13e7628`・`0x15eac90`) と site 9 の 1 件。`0x13e7628` は `4fc1472ff` (#5216)、`0x15eac90` と site 9 は `b0c6e835a`。`tools/flelift` 全体の差分 (10 ファイル・419 行) は他 commit の変更を含む。
素材: `fl-win64` (`extracted/block00031_PE.bin`)・`toolchain-emsdk` ([EMSDK] の pin 6.0.12)。
実測: `boot_e2e.sh --fast` (lift 再利用・build 4 variant・run 4 variant) `real 4m11s`・`user 7m39s`・`sys 1m02s`・RC 0。load 開始 1.74。

## 1. 結論

- `InitContext.InitTable` (0x15eac90) は unit 1 で `0 → 0x13768b0` (`proc 0x41e7e0`)、unit 895 の ExitProcess 直前 (site 4・`proc 0x412a12`) で `0x13768b0 → 0` に変わる。
- `ippsZero_8u` の memset 直後 (site 9) と `imp_memset` (site 3) では変化が無い。よって 0 化の書込み元は `imp_memset` と `ippsZero_8u` の経路ではない。
- 0 化は unit 895 の中で起きる (site 2 の unit 後の監視点では値はまだ 0x13768b0)。ST* 以外の書込みか、unit 内で一度書かれて戻った値の可能性を含め、書込み命令は未特定。
- 補修なしの survey の判定 (unit 280 / 659 / 895 の unlifted / ok の差) はこの run では測っていない。補修なしの survey は `InitTable == 0` で開始できないため (REPORT §12)、判定の差を出すには 0 化の書込みを特定してその経路を直す必要がある。

## 2. 変化点 (plain・`FLEBOOT_PY123`)

| unit | site | slot | proc | old | new |
|---|---|---|---|---|---|
| 0 | 0 (fle_run 直前) | 0x15eac90 | 0x0 | 0x0 | 0x0 |
| 1 | 1 (unit 前) | 0x15eac90 | 0x41e7e0 | 0x0 | 0x13768b0 |
| 895 | 4 (ExitProcess) | 0x15eac90 | 0x412a12 | 0x13768b0 | 0x0 |

site 9 (`ippsZero_8u` 直後) は 0 件。`py_events` は n 24・over 0。

## 3. 結果 (plain)

`units_run 895 / 942`・`boot_threw exit`・`exit 1`・`getmem 3680 / freemem 1499`・`ipp_ptr_15F34A0 0x7f10001c`。監視 slot 追加前 (#4854 / 前 run) と一致する。比較元は `REPORT.md` §12 の測定 commit `a64aa3aab` (boot 既定 units 895・`exit`)。`FLE_SURVEY_NOREPAIR` の survey は実行していない (補修なしは `InitTable == 0` で開始できないため、§1 のとおり判定の差は未測定)。
