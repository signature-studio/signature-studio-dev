# REPORT_APPENDIX_3352 (WIN-21 #3352)

#3352 (WIN-21) の S1 unit 差の特定と、現 HEAD の e2e 実測。REPORT §6k の全文 (本文は REPORT.md に短い参照のみ)。

## 6k. 現 HEAD の実測と S1 の unit 差の特定 (#3352 / WIN-21)

測定 commit `c3ee6daa7` (origin/main)。本節の PR はコードを変えていない (`git diff c3ee6daa7 HEAD -- tools/gui tools/m11 ':(exclude)tools/gui/flengine/REPORT.md'` は空)。`bash tools/gui/flengine/e2e.sh` を foreground で 1 回実行 (`FL_WIN64_DIR` = fl-win64 展開先、`EMSDK_ENV=[EMSDK] の emsdk_env.sh`、`RETDEC=[RETDEC] の retdec-decompiler`、`TMPDIR=$RUNNER_TEMP`。素材は fl-win64・work-m11・toolchain-emsdk・toolchain-retdec、`gcc-mingw-w64-x86-64` は apt で導入)。

| 項目 | 結果 |
|---|---|
| e2e | rc 1 / 322 s / load 1.15 → 1.03 |
| judge | **12/14** (FAIL は **B1** と **S1**) |
| B1 boot parity | FAIL。`units_run 109 (base 109)` は一致するが `dllmain_done False` (base `True`)。`GetMem 707 FreeMem 20`・`icall_miss 6` (base 7) |
| S1 survey parity (soft) | FAIL。soft `873/1/47/21/0` vs base `871/1/47/23/0` |
| 他 gate | L1 (ff・soft) PASS・A1 declare=193 adapter=193 impl=173 stub=20・R1 `LoadStringW`・R2 reach 33 ≥ 19・S2 PASS (soft fail-fast 無し)・P1 (RegisterClassW=3 CreateWindowExW=3)・P2・P3・P4 hwnd `0x1100010`・P5 hwnd `0x110000f`・W1 WNDCLASS 11 / fn WNDPROC 8 |
| ネガコン | N1〜N9 期待どおり FAIL (9/9) |
| native selftest | 506 passed / 0 failed |
| `__pe_image` parity (4b) | PASS |

### S1 の unit 別の差 (受入条件 1)

`GF_SURVEY_UNITS` で unit 別結果を取り、base (`m11_base.cjs`) と soft (`m11_gui_soft.cjs`) を 942 unit で突き合わせた。差は **2 unit のみ**:

| unit | base | soft |
|---|---|---|
| 304 | `memory access out of bounds` (trap) | ok |
| 555 | `memory access out of bounds` (trap) | ok |

ok/trap 以外の差は無い。soft の survey を 2 回、base を 2 回 (e2e 内と単独) 取り直し、いずれも同じ差 (soft `873/21` vs base `871/23`) を再現した。S1 の `+2 / -2` は unit 304・555 の 2 件で完全に説明される。

- 同じ 2 unit の OOB の向きは測定ごとに逆になってきた (§6i・REPORT_APPENDIX §7: `boot7 なし` の run は base OOB・soft ok が逆向き)。build 差 (`--base` と soft) ではなく、survey の順序依存・状態依存と見るのが妥当。ただし真因 (OOB の実アドレスと命令) は未採取で、特定していない。
- 判定式は変えていない。S1 の gate は FAIL のまま。

### B1 (本測定で FAIL)

`dllmain_done` が本 run の boot だけ `False` (baseline は `True`)。units・init は一致する。e2e は 1 回のみ実行したため、再現性と原因は未確認。判定式は変えていない。

### 製品 KPI (起動・GUI)

コード変更なし。前後は同値。`units_run` は 109 (base 109)。最初の GUI API は `LoadStringW` (自然到達)。自然起動の `RegisterClassW`/`CreateWindowExW` 到達は INFO 行のとおり (直接 probe で `TApplication` と `TLightweightLayeredControl` の窓 (P4/P5) が生成される)。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| S1 の unit 304・555 の OOB の真因 (実アドレス・命令) | judge S1 FAIL。JUDGE 14/14 の未達 | #1426 (既存・OPEN) |
| B1 `dllmain_done False` (本 run のみ。再現未確認) | judge B1 FAIL。JUDGE 14/14 の未達 | #3352 (本 issue に残す。次の再測定で再現を確認) |
