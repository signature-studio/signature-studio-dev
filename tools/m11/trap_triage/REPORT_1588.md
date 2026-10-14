# #1588 (LD-55): m11 wasm_trap OOB 残 2 件の原因切り分け — tools/m11/trap_triage/

**判定: 部分達成。受入条件 1 は「分岐点の特定まで」、受入条件 2 は「不再現の再現」の結論が前回記録と逆。受入条件 3 は達成。受入条件 4 は本 PR 後に #307 へコメント。**

親: #307 / 関連: #865 (`tools/liftdiff/REPORT_APPENDIX_865.md`)、#1463 (`REPORT_1463.md`)。

## 0. 検証環境

- 測定 base: `origin/main` `3f9f1fda` (worktree `ws-1588`、branch `1588-m11-trap-oob-residual`)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/` と `flstudio_win64_26.1.7.5653.exe`)。`work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/` に展開 (gitignore)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/repro_1588.sh` (19.4 s、load 低、n=1 + 0x66ea90 は 2 回)。
- 注意: `disasm_fn.py` は `LD_M11_PE` 未設定時に `/home/ubuntu/...` を見るため、`LD_M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin` を明示する。

## 1. 受入条件 1: 0x6525b0 の非到達原因

`liftdiff.py run targets/m11.json --fn 0x6525b0 --pattern p01 --nobuild --state auto -v` (`repro_1588.sh`)。

- 判定: `mismatch`。native = ok、wasm = trap (OOB)。wasm 最上位 frame は `function_4133f0`、呼出列は `6525b0 → 652830 → 414c70 → 4133f0`。
- trace_head (先頭 35 件): native 66 件 / wasm 35 件 (trace_len)。**最初の分岐は index 5** (`410320` の直後)。
  - native: `410320 → 409410 (GetMem) → 407a50 → 40d210 → 5af3d0 …`
  - wasm: `410320 → 5af3d0 → 5af390 → 412d60 → 410360 …`
  - 差: native は `410320` の間接 call 先が `409410` (GetMem)、wasm は `5af3d0`。
- 対応する機械語: `410320` は `call qword ptr [rax-0x30]` (`disasm_fn.py 410320`、22 byte)。呼出先は `rax` の vtable に依存。
- **確定した事実**: wasm の image で該当 vtable 付近の値 (`0x1ac308`) は PE の DIR64 補正 (ImageBase 0x400000 を引いた値) と一致する。PE 側は DIR64 対象 (278,531 件) に含まれ、補正は適用済み。**このスロットは補正漏れではない**。
- **未確定**: `rax` の値 (vtable 先頭) が native と wasm で違う理由。`410320` の入口で `rax` が異なるのか、`410320` の呼び元 `6525b0` 側の引数 `rcx` (= `&slot`) が違うのかは未切り分け。REPORT_1463 §2 の `6525b0 → 4133f0` の `&slot` 転送と同じ経路で、`[rbp+0x28]` の保存と再読みを追う必要がある。

よって、0x6525b0 が 414ad0 に到達しない原因は「`410320` の間接 call 先が native (GetMem) と wasm (`5af3d0`) で分かれ、wasm 側が 414ad0 系へ行かず `414c70 → 4133f0` で OOB する」ところまでは特定。分岐の入力値 (`rax`/`rcx`) の差は未特定。

## 2. 受入条件 2: 0x66ea90 の不再現

- 既存記録 (`tools/liftdiff/results/m11_oob_414ad0_27.md`・`REPORT_APPENDIX_865.md`) は「`both_fault`、再走で trap せず」。
- **本 run の再現 (2 回) と batch 記録 (`work/m11/batch_closure.jsonl`) はいずれも wasm 側が OOB trap (`function_414ad0 < 414bb0 < 652500 < 653660 < 6539e0 < 66ea10 < 66ea90`)**。native は segv。判定は `unexec`/`native_null_deref_all_patterns`。
- 「trap せず」の記録は `oob_414ad0_27.py` の `NO_TRAP:` 表示 (`tests/oob_414ad0_27.py:27`) の誤読。`compare.py:212` の定義では `both_fault` は「native fault かつ wasm trap」で、wasm trap を含む。よって 0x66ea90 は **不再現ではなく、再走で同じ OOB が出る**。
- 結論: 「再走で trap 不再現」は前回記録の誤り。原因は入力差・実行順・素材差のいずれでもなく、記録側 (表示の誤読) の問題。ただし「いずれも OOB」は `trap 種別` の一致確認のみで、wasm の trap 位置 (最上位 frame) は batch と再走で一致した。

## 3. 受入条件 3: 再現手順

- `tools/m11/trap_triage/repro_1588.sh`: 0x6525b0 (p01) と 0x66ea90 (z) を単体再走し JSON を `tools/liftdiff/work/m11_1588/` に出す (gitignore)。
- `tools/m11/trap_triage/diverge_1588.py`: liftdiff の JSON から native / wasm の trace_head を比べ、最初の分岐 index と両側の呼出列、414c70 / 4133f0 / 414ad0 の有無を出す。
- 実行結果 (本 PR のコミット HEAD で実測): 0x6525b0 は `first divergence index=5`、0x66ea90 は 2 回とも `native_null_deref_all_patterns`。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `410320` の `rax` (vtable) が native と wasm で異なる理由 (入口値 / `6525b0` の `&slot` 経路) | 0x6525b0 の非到達原因の確定 | 本 issue #1588 の残り (本 PR で未達) |
| `REPORT_APPENDIX_865.md` の「0x66ea90 再走で trap 無し」の訂正 | 記録の正確性 | 本 PR で REPORT_APPENDIX_865 に訂正を入れる (§5) |

## 4.5 追加調査 (受入条件 1 の続き、run 2)

測定 commit: `60932d35` (origin/main 起点の worktree `ws-1588`、本 PR で追加するのは `scan_1588_slot.py` と本節のみ)。

- 再現 (`repro_1588.sh`、実測): p01 = mismatch、`first divergence index=5`、wasm OOB (最上位 `function_4133f0`)。0x66ea90 は 2 回とも `native_null_deref_all_patterns`。
- `410320` 入口 (index 4): `rcx` = `rax` = `0x5ac338` (native) / `0x1ac338` (wasm、wasm 空間) で一致。`rdx` も一致 (`0x1`)。よって入口引数は分岐の原因ではない。
- 分岐は `[rax-0x30]` = `0x5ac308` の読み値。native は `0x409410` (GetMem)、wasm は `0x5af3d0`。
- 静的 PE (`block00031_PE.bin`, file off `0x1ab708`) の `0x5ac308` の値は `0x40f960`。実行時の `0x409410` とも wasm の `0x5af3d0` とも一致しない。よって**このスロットは実行時に書き換えられる**。
- `scan_1588_slot.py` で `.text` 全体を capstone 走査: `[rip+disp]` と即値で `0x5ac308` / `0x5ac338` / `0x409410` / `0x40f960` / `0x5af3d0` を指す命令は **0 件**。書き込みは `rax` 等を経由した間接参照と推定され、静的には見えない。
- 未解決のまま残る: 書き込み元の特定 (実行時 watch が必要。`tools/m11/trap_triage/` の既存 `watch_store_682.c` 系の方式を流用候補)。

## 5. 記録の訂正

- `tools/liftdiff/REPORT_APPENDIX_865.md` §冒頭: 「0x66ea90 は再走で trap せず both_fault」→ 「both_fault (native segv・wasm OOB trap)。再走 2 回とも wasm OOB を再現」。
- `tools/liftdiff/results/m11_oob_414ad0_27.md` は自動生成 (`oob_414ad0_27.py`) のため人手で編集しない。生成元の `tests/oob_414ad0_27.py:27` の `NO_TRAP:` 表示を直すのは別コミットで行う (本 PR では扱わない)。

## 6. run 4: 現 HEAD での再現と生成物の修正 (LD-55)

- 測定 commit (再現・27 件再走): `26f90ada` (origin/main)。worktree `ws-1588`、branch `1588-m11-trap-oob-residual-3`。素材は `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`work-m11`・`work-liftdiff` を展開 (`toolchain-*` は本節では未使用)。
- `repro_1588.sh` (18.2 s、開始時 load 0.97): p01 = mismatch、`first divergence index=5`、wasm 最上位 `function_4133f0` (`6525b0 → 652830 → 414c70 → 4133f0`)。0x66ea90 は z・2 回とも `unexec` (`native_null_deref_all_patterns`)、case outcome は `both_fault`、wasm 最上位 `function_414ad0`。§1・§2 と一致。
- 27 件再走 (`tests/rerun_414ad0_27.sh`、2 分 40 秒、全 rc 0) の出力を、既存の生成元 (`tests/oob_414ad0_27.py`) にそのまま通すと commit 済み md と完全一致した。
- 生成元の誤り: 同スクリプトは `outcome == 'wasm_trap'` だけを集計し、`both_fault` (native fault かつ wasm trap、`ldlib/compare.py:212`) を `NO_TRAP:both_fault` と表示していた。`wasm_trap` と `both_fault` を集計するよう 1 行修正。
- 修正後の再生成: 0x66ea90 の行は `function_414ad0 | 有 | 21`、集計は 26/27 (修正前 25/27)。`results/m11_oob_414ad0_27.md` は修正後の生成元で再生成し、差分は該当行と集計行のみ。`REPORT_APPENDIX_865.md`・`REPORT_APPENDIX.md`・`docs/DOC_MAP.md` の 25/27 を 26/27 に揃えた。
- コード差分 (測定 commit `26f90ada` から HEAD まで、REPORT と results を除く): `git diff 26f90ada HEAD -- tools/liftdiff tools/m11 ':(exclude)*REPORT*' ':(exclude)*results*'` の出力は次の 1 行 (`tests/oob_414ad0_27.py`)。

```diff
-    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
+    cs = [c for c in r['cases'] if c['outcome'] in ('wasm_trap', 'both_fault')]
```

- `results/m11_oob_414ad0_27.md` の差分は 0x66ea90 の行と集計行の 2 箇所のみ (`diff` の出力: 行 20 と行 36)。
- 受入条件の判定: 1 = 最上位 frame・入口経路・分岐点 (index 5) は実測済み。分岐の上流 (`0x5ac308` の書込み元) は #2769 (wasm 側) と #2770 (native 側) が担当し、本 issue は部分達成のまま。2 = 達成 (不再現ではなく wasm OOB を再現。表示の誤りを本節で修正)。3 = 達成。4 = 対象の #307 は CLOSED のため、結果は #1588 の issue コメントに記載。
