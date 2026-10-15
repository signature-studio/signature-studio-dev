# REPORT_3520 — e2e rc=1 の期待値と実測の不一致 (#3520) の原因特定

**結論 (3 行)**
- (c) ptrcheck 71005 は **`M11_FIX_50A830=1` の clean build で再現**した値。既定 (clean) は 71001。既定で 71005 が出るのは `work/obj/ov.o` が古い (ON 側の build で作った) 状態のときだけで、**build キャッシュの取り違え**が原因。`M11_FIX_50A830` に stamp が無かった。修正は main の `68b9de191` (#3592・PR #3645 merge `e4c52eadd`) で入った (`work/ov_50a830.stamp`)。本 PR が一度入れた `fix_ov.stamp` は同じ flag の 2 系統目になるため外した。
- (b) survey exact: 既定の clean 実測は 873、872 は ON 状態 (`M11_FIX_50A830=1`) の値。既定で 872 が出るのも同じ取り違え。pin 872 の出所 (#2714 時の環境) は未切り分けで、survey の ok は環境 (IR・work 状態) で 872〜874 に動く。
- (a) tolerant 完了数 101 (= 通常起動 units_run 98 + skipped 3): clean・ON・既定のどれでも 101 で、`M11_FIX_*` の切替えでは動かない。pin 56 は #2714 時点の値で、その後の commit で通常起動が unit 57 を超えて進んだ。**進んだ commit は未二分** (未解決)。

期待値 (`e2e_expect.env`・`m11_tolerant_gate.py`) は変えていない。

## 1. 測定条件

- PE: `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。素材 `work-m11` は #516 以前の snapshot で、`ir_conditions.json`・`lift_pe.sha256`・`functions_dll.csv` が無い。
- 素材の lift (`boot0〜4.lift.ll`) は snapshot を使い、`boot5.lift.ll` は `m11_lift.sh m11_extra_ranges5.txt boot5` (RetDec・8 秒) で作った。`m11_image_gen.py` の出力は snapshot の `m11_image.bin` と **バイト一致** (LB=0)。よって snapshot の lift は現 PE 由来と見てよい。
- IR は `m11_gen_ir2.sh` で作り直した (ldfix・ld108・ld115 applied)。全再生成 (Ghidra CSV・RetDec 4 chunk) は行っていない。`lift_pe.sha256` は手書きしていない。
- 測定は `m11_e2e.sh` の 97〜111 行 (run・survey・tolerant・judge・gate) と同じ順・同じ環境変数で行った。
- 測定の base は origin/main `8a852f69a` (修正前の `tools/m11`)。origin/main (`e99fe343c` 時点) では `tools/m11` が 8a852f69a 以降 24 files 変わっていた。同時点で `m11_build.sh`・`m11_ov.c`・`m11_gen_ir2.sh` は変わっていなかった。現 origin/main (`60eeccc33`・2026-10-15 確認) では `tools/m11` が 26 files 変わっており、`m11_build.sh` は `68b9de191` (#3592) で変わった (`ov_50a830.stamp` を追加)。`m11_ov.c`・`m11_gen_ir2.sh` は変わっていない。**数値は現 main で再測定していない** (§6)。

## 2. 実測 (clean = 直前に `work/obj/*.o` を全削除してから build)

| 構成 | 測定 tree | IR sha256 (先頭) | strict 完了 (units_run + skipped) | survey ok / trap / miss / noproc | survey ptr (max 71001) | run ptr (max 69359) |
|---|---|---|---|---|---|---|
| 既定・clean (参考・旧 base) | f8867e72e (旧 base の作業ツリー。本 commit 系列の測定 commit ではない。根拠に使わない) | `bcfda317` | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 (pass) | 69669 (**FAIL**) |
| `M11_FIX_50A830=1`・clean | a0d9722fe (記録のみ。tree の個別確認は無い) | `bcfda317` | 98 + 3 = 101 | 872 / 23 / 46 / 1 | **71005 (FAIL)** | 69669 (FAIL) |
| 既定だが直前が ON build (`obj` 削除なし・取り違え) | 修正前の `m11_build.sh` (stamp 無し)・tree 不明 (前 session) | `bcfda317` | — | 872 / 23 / 46 / 1 | **71005** | 69669 |
| 既定・最初の IR (初回 gen) | 未記録 | `36079b29` | 101 | 873 / 22 / 46 / 1 | 71001 | 未記録 |
| origin/main `8a852f69a` の worktree・既定・clean (修正前) | 8a852f69a | `158b2a8b` | 98 + 3 | (未記録) | 71001 | 69669 |
| 同・ON build (`obj` 削除なし・取り違え・修正前) | 8a852f69a | `158b2a8b` | — | (未記録) | **71001 (既定と同値 = 古い ov.o)** | 69669 |
| 同・修正後 (8a852f69a + a0d9722fe の `m11_build.sh`)・既定 → ON → 既定 (`obj` 削除なし) | 8a852f69a + m11_build.sh (a0d9722fe の tools/m11 と同一) | `158b2a8b` | 98 + 3 | 873 / 22 / 46 / 1 → 872 / 23 / 46 / 1 → 873 / 22 / 46 / 1 | 71001 → **71005** → 71001 | 69669 |

- 行 1〜3 の IR は同じ `bcfda317`。tree の記録は行 1 (f8867e72e) と行 2 (前 session の記録 a0d9722fe。個別の確認は無いが、clean build なので stamp の有無に依らない)。行 3 は stamp の無い script で測られた行 (a0d9722fe の script では ON の後の既定 build が ov.o を作り直すため、71005 は出ない)。tree は不明 (前 session)。**tree を確認できるのは行 5〜7** で、§3 の結論の主根拠はこの並び。
- `M11_FIX_535BF2=0` の参考値は 71001 / run 69668 (前 session の記録。修正前の script で測り、直前 build の状態は未記録)。535BF2 の切替えは既存の `ov_535bf2.stamp` (`1ee68101c`・#714) で `ov.o` が作り直されるため、50A830 の取り違えの対象ではない。
- IR 生成の出力 hash は `36079b29`・`bcfda317`・`158b2a8b` の 3 通りになった。`36079b29` と `bcfda317` は同じ入力での差で、hash seed (未指定・1・2) では `bcfda317` に揃う。`158b2a8b` は 8a852f69a 基点の IR で tree が違うため、上の 2 通りの差とは別に扱う。差の原因は未切り分け (§4)。run ptr 68938 の記録は snapshot の古い wasm (units 17) のもので、基準の判定には使わない。
- survey ptr は、既定 clean で IR の版によらず 71001 だった。

## 3. 原因

### (c) image_va_words_new 71005 / 上限 71001

- `M11_FIX_50A830=1` の clean build で 71005 が出る (+4 語)。既定 clean は 71001。主根拠は §2 の行 5〜7 (a0d9722fe の stamp 入り script: 既定 71001 → ON 71005 → 既定 71001)。
- 既定で 71005 が出た条件は、`m11_build.sh` が `M11_FIX_50A830` を stamp で管理しておらず (base `8a852f69a` の状態。`M11_FIX_535BF2` は既存の `work/ov_535bf2.stamp` で管理済み。main は `68b9de191` で `work/ov_50a830.stamp` を入れた)、`work/obj/ov.o` が mtime だけで再利用されることだった (ov.o は `m11_ov.c` の `#if` でこの 2 フラグを切り替える)。ON build の後に既定 build を流すと、既定の測定が ON の ov.o で行われた。
- PR #3485 の表で既定の行も 71005 になっているのは、同じ取り違えで説明できる (推定。その run のログは repo に無い)。
- 期待値 71001 は既定の値として正しい。gate は正しく動いている。

### (b) survey ok 873 ≠ 期待 872

- 既定 clean の ok は 873。ON (50A830=1) の clean は 872。
- pin 872 は `REPORT_N2714.md` (#2714 時点・既定 0/0・IR `de46cada`・手書きの `lift_pe.sha256`) の値。既定 0/0 は `a7d59a478` (#2714) 時点の既定。535BF2 の既定 0→1 は `d80e9909f` (#2521) で、`a7d59a478` はその前 (祖先) にある。同 `REPORT_N2768.md` の別環境では同じ範囲で 874 が出ている。survey の ok は環境で 872〜874 に動き、pin が環境に依存して安定しない。
- 既定で 872 が出るのは、ON build の後に `ov.o` を消さずに既定 build を流したときだけ (取り違え)。

### (a) tolerant 完了数 101 ≠ 期待 56

- 101 (= units_run 98 + skipped 3) は clean・既定・ON のすべてで出た。`M11_FIX_*` の切替えでは動かない。
- pin 56 は #2714 時点の値 (`REPORT_N2714.md` §: 53 + 3)。`REPORT_N2768.md` でも 56 だった。`REPORT_APPENDIX_2521.md` の表では、PR #3485 の base (`44a7f4465`) で既に 98 (+ skip 3)。
- 停止位置の変化: REPORT §14 では unit 57 (0x16fde0) の後に Halt0。今回は unit 約 101 の `function_535c11` (OOB) で止まる。**停止点が後ろへ動いた**。改善方向の変化で、survey の数値は (b) の範囲で変わっていない。
- 56 → 98 を生んだ commit は**未二分**。候補は `tools/m11/ldfix`・`m11_ov.c`・`m11_gen_ir2.sh` を変えた commit 群 (#3372・#3419・#3426・#2833 など)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 通常起動の完了数 56 → 98 (+3) を生んだ commit の二分 (未了) | pin 56 が古い。期待値を上げるには根拠が要る | #3647 (#3520 の受入 (a) を原文のまま移管) |
| (b) survey ok の環境差 (872〜874) と pin 872 の出所 (#2714 時の build 状態・推定) | 既定の期待値が環境で動く | #3647 (#3520 の受入 (b) を原文のまま移管) |
| 通常起動の ptr 基準 69359 超過 (既定 clean で 69669) | `m11_e2e.sh` の rc=1 の別要因 (#3520 の受入外) | #3647 (追加分として転記) |
| IR 生成が同じ入力で別出力 (`36079b29` と `bcfda317`。hash seed は無関係) | run ptr の基準が IR の状態で変わり得る | #3129 (IR 来歴の記録) に合流 |
| origin/main の `m11_gen_ir2.sh` は qstore を適用しない (`ir_conditions.json` が `qstore=not-applied`) | 旧 main と IR の内容が違う可能性。未確認 | #3129 (IR 来歴の記録) に合流 |
| 全再生成 (Ghidra CSV・RetDec 4 chunk) を行っていない | snapshot の lift と全再生成の IR の一致は未確認 | #3122 (全再生成 IR の survey) に合流 |
| 現 main (`60eeccc33`) で §2 の数値を再測定していない。測定 tree は `a0d9722fe` で、main は `tools/m11` が 26 files 違う (§1) | main の stamp (`68b9de191`) を入れた tree で §2 の値がどう動くかは未確認 | 既存 issue #3520 へのコメント (e2e の再測定は素材 `tools/m11/work`・emsdk・retdec が要るため本 PR の範囲外) |

## 5. 修正

- 修正は main の `68b9de191` (fix(m11): invalidate ov.o when M11_FIX_50A830 changes (#3592)・PR #3645 merge `e4c52eadd`) で入った。`tools/m11/m11_build.sh` の 254〜255 行で `work/ov_50a830.stamp` を使い、`M11_FIX_50A830` が変わったら `work/obj/ov.o` を作り直す。`M11_FIX_535BF2` は既存の `work/ov_535bf2.stamp` (236〜237 行・252 行) で管理済み。
- 本 PR は一度、同じ flag を `work/fix_ov.stamp` (組 `<535BF2>-<50A830>`) で管理する修正を入れた (`a0d9722fe`)。main の 2 つの stamp と判定が同じで、同じ flag を 2 系統で管理することになるため、`tools/m11/m11_build.sh` を base `8a852f69a` と同一に戻した (commit `1adfe2039`)。
- 既定の値・期待値・C 側の転記内容は変えていない。

## 6. 検証

- 測定 commit: `a0d9722fe` (測定時の tree。`work/fix_ov.stamp` 入りの `m11_build.sh`)。以後の PR の変更は `m11_build.sh` を base に戻す commit (`1adfe2039`) と本 REPORT の更新だけで、差分は §7。
- **本 fix run では e2e を再実行していない**。素材 (`tools/m11/work`・emsdk・retdec) が run 上に無く、`fl-win64` の展開だけでは lift・IR・build が再現できないため。§2 の数値は前 session の記録で、現 main (`60eeccc33`) では再測定していない (§4)。
- stamp 行の分離テスト: main (`60eeccc33`) の `m11_build.sh` の 236〜237 行 (`ov_535bf2.stamp`)・252〜255 行 (`ov_50a830.stamp`) を切り出して `$RUNNER_TEMP` 下で実行 (作業ツリー外)。8 通りすべて期待どおり: 初回 (stamp 無し) REBUILD / 同設定 REUSE / 50A830 0→1 REBUILD / 同設定 REUSE / 50A830 1→0 REBUILD / 535BF2 1→0 REBUILD / 同設定 REUSE / 535BF2 0→1 REBUILD。
- 負例: 50A830 の 2 行 (254〜255 行) を外すと、50A830 0→1 と 1→0 が REUSE になった (前回 build の `ov.o` を再利用)。main の行がこの取り違えを防いでいる。
- `m11_e2e.sh` 全体は未実行 (素材 snapshot の全再生成が要り、時間上限に収まらない)。run・survey・tolerant・judge・gate は前 session が個別に実行した (§2)。gate の結果: strict (101 ≠ 56) と survey (873 ≠ 872) は FAIL のまま (期待値は変えていない)。

## 7. 差分

測定 commit `a0d9722fe` から HEAD までの `m11_build.sh` の差分 (`git diff a0d9722fe HEAD -- tools/m11/m11_build.sh` の出力。stamp の 3 行 = コメント 1 行・if 1 行・echo 1 行を外した):

```diff
@@ -142,9 +142,6 @@ echo "${M11_PROBE_2400:-0}" > work/instr_2400.stamp
 # #2407: function_e3ef60 観測 probe の ON/OFF で post 結果と ov.o を作り直す (stamp)
 if [ "$(cat work/instr_e3ef60.stamp 2>/dev/null || echo 0)" != "${M11_INSTR_E3EF60:-0}" ]; then rm -f work/boot_final3.ll work/obj/ov.o; fi
 echo "${M11_INSTR_E3EF60:-0}" > work/instr_e3ef60.stamp
-# #3520: M11_FIX_535BF2・M11_FIX_50A830 は m11_ov.c の転記を切り替える。stamp が無いと前回 build の ov.o を再利用し、切替え後の測定が前の設定の値になる
-if [ "$(cat work/fix_ov.stamp 2>/dev/null || echo none)" != "$M11_FIX_535BF2-$M11_FIX_50A830" ]; then rm -f work/obj/ov.o; fi
-echo "$M11_FIX_535BF2-$M11_FIX_50A830" > work/fix_ov.stamp
 S_P134="${M11_PROBE_134:-0}"   # #134: 1 = 計測用 IR probe (8c5eb0 の arg2・R・list; trap_triage/probe134_ir.py) を boot_final3.ll に入れる。既定 0 では入れない
if [ "$(cat work/instr_134.stamp 2>/dev/null || echo 0)" != "$S_P134" ]; then rm -f work/boot_final3.ll; fi
echo "$S_P134" > work/instr_134.stamp
```

`tools/m11` の残りの差分は本 REPORT だけ。
