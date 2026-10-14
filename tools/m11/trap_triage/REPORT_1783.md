# #1783 (LD-63): m11 0x5ac308 (410320 の間接 call スロット) の書き込み元 — 途中報告

**判定: 受入条件 1・2 は未達 (子 #1869 へ移管済み)。受入条件 3 は部分達成 (手順のスクリプトを commit、全 unit 完走は未実測)。完了単位は「書込み監視スクリプトと報告の追加」に縮小し、`Closes #1783`。**

親: #1588。前提の結論は `REPORT_1588.md` §4.5 を正とする (`0x5ac308` は実行時に書き換わり、静的参照 0 件)。

## 0. 検証環境

- 測定 base: `origin/main` `6e001233` (worktree `ws-1783`、branch `1783-m11-slot-5ac308-writer`)。
- 測定 commit (実測した code): `8ba5017d`。その後 `store_watch_1783.sh` を修正 (§6)。修正後の HEAD では未測定。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (6.2 s)。`work-m11` / `work-liftdiff` は repo 直下に展開 (gitignore)。`toolchain-emsdk` は `[EMSDK]` (`docs/REFERENCES.md`) で `emcc 6.0.12` を確認。
- 注意: `toolchain-emsdk` の `tar --zstd -xf ... -C /` は rc=2 だったが、`[EMSDK]` (`docs/REFERENCES.md`) の `emsdk_env.sh` と `emcc` は動作を確認した。展開先の差は未調査。
- `m11_gen_ir2.sh`: rc 0、34.7 s、`boot_final.ll` 490,733 行、`ldfix=applied`。`ir_conditions.json` を生成。
- `m11_build.sh`: rc 0、17.5 s、`wasm-ld signature mismatch: 0, undefined symbol: 0`。

## 1. 計装 (追加したもの)

- `tools/m11/trap_triage/store_watch_1783.sh`: `watch_store_682.py` の全 store 計装と、既存の `watch_addr_1046.c` (固定番地版) を流用する。監視番地は `M11_WATCH_1783` (既定 `0x1ac308` = wasm 側の `0x5ac308` に対応)。survey は `survey_units.mjs` を使う。
- 計装 IR は `boot_sw.ll` (54,041 store を計装)。IR の値と分岐は変えない。

## 2. 実測 (run1)

- `store_watch_1783.sh run1` を foreground で実行したが、survey が **unit 145 で打ち切られ完走しなかった** (run 上限 900 s の tool timeout)。
- `[aw]` 行 (書込み検出) は **0 件と記録したが、これは計測値ではない**。旧 script は `$tag.err` の `^\[aw\]` を数えていたが、`survey_units.mjs` は `TRACE_RE` に合わない行を stderr に出さず (`SV_ERR_LOG` 未指定)、`[aw]` は `$tag.err` に届かない。書込みがあっても 0 になる構造だった。
- 修正 (§6): `SV_ERR_LOG=work/probe1783/$tag.aw` を設定し、`[aw]` は `.aw` ファイルから `\[aw\] ` で数える (unit 番号は `unit N ` の接頭辞で付く)。接頭辞付きの合成入力で、旧 grep が 0・新 grep が 1 を返すことを確認した。
- unit 0〜145 の範囲のみ実行 (旧 script)。全 942 unit を見ていない。
- 修正後の再実行は本 run では未実施: `emcc` (`[EMSDK]`)・`work-m11`・`work-liftdiff` が runner に無い (取得済みは `fl-win64` のみ)。再実行には `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff` が要る。
- 完走には survey の所要 (全 unit) を別 run で測る必要がある。本 run では所要時間を実測できていない。

## 3. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | `0x5ac308` へのストアを実行時に捕まえる (書込み命令アドレスと値を native / wasm で採取) | **未達**。wasm 側は計装済みだが完走せず。native 側の書込み捕捉方式は未実装 (`rt/ld_native.c` に store 監視は無い) |
| 2 | 書込み元関数と、両側で値が分かれる最初の地点を実測で記録 | **未達** |
| 3 | 手順を repo 内スクリプトで実行可能にし commit | **部分達成**。`store_watch_1783.sh` を commit。全 unit の完走は未確認 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の全 unit survey の完走と、`[aw]` の書込み元 (site → fn・IR 行) の特定 | 書込み元の一方の側が未確定 | #1869 (起票済み・受入 1) |
| native 側の `0x5ac308` 書込み捕捉 (ld_native の store 監視が無い) | 両側の比較ができない | #1869 (起票済み・受入 2) |
| 修正後 `store_watch_1783.sh` の再実行 (unit 0〜145 の件数と全 942 unit) | `[aw]` の実測値が無い | #1869 (受入 1 の実行に含む) |
| 修正後 HEAD (`d46838cc` 以降) の再測定 (`tools/m11` は main 取込みで変化) | 本 REPORT の数値は `8ba5017d` 時点 | 再測定は素材 (`toolchain-emsdk`・`work-m11`・`work-liftdiff`) を付けた次回 run。#1869 の受入 1 実行に含める |

## 5. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
bash tools/m11/m11_gen_ir2.sh
bash tools/m11/m11_build.sh
bash tools/m11/trap_triage/store_watch_1783.sh run1   # 全 unit 完走まで要時間 (本 run では unit 145 で打ち切り)
```

`[aw]` の件数: `work/probe1783/run1.aw` (`unit N [aw] ...`) から `grep -c '\[aw\] ' work/probe1783/run1.aw`。

## 6. 検証の鮮度 (WORKFLOW §6)

- 測定 commit: `8ba5017d` (コードを変えた最後の commit。`store_watch_1783.sh` の実測はこの時点)。
- 修正 commit: `e124f367` (`store_watch_1783.sh` の `[aw]` 経路・dead code 削除)。`2c0c8f4d` は REPORT のみ。`eb55aef7` は main (`3624a5fc`) の取り込み merge。
- **差分は 0 ではない**: `8ba5017d..HEAD` の `tools/m11` には、本 PR の script 修正のほか、main 取り込みで入った他 PR の code 変更が含まれる (`m11_build.sh` の `M11_TRACE_ISOLATE` 追加など)。この差分の下では `8ba5017d` の実測値は HEAD の値とみなせない。**修正後 HEAD の再測定は未実施**: `emcc`・`work-m11`・`work-liftdiff`・`toolchain-emsdk` が runner に無く、取得済みは `fl-win64` のみ。
- `git diff --stat 8ba5017d HEAD -- tools/m11` (`d46838cc` 時点、14 files, +576 −21):

```
 tools/m11/REPORT_APPENDIX_960.md                   |  20 +++
 tools/m11/REPORT_N15.md                            |  33 ++++
 tools/m11/REPORT_N1598.md                          | 133 +++++++++++++++++
 tools/m11/ldfix/REPORT_1647.md                     |  19 +++
 tools/m11/ldfix/REPORT_564.md                      |  47 ++++++
 tools/m11/ldfix/audit_undefload_dest.py            | 166 +++++++++++++++++++++
 .../ldfix/results/candidate_verdicts_1161.jsonl    |  31 ++++
 tools/m11/ldfix/results/f4_liftdiff_1646.tsv       |  11 ++
 tools/m11/m11_build.sh                             |   5 +-
 tools/m11/trap_triage/REPORT_1046.md               |   9 ++
 tools/m11/trap_triage/REPORT_1317.md               |  19 +++
 tools/m11/trap_triage/REPORT_1783.md               |  45 +++++-
 tools/m11/trap_triage/REPORT_718.md                |  27 +++-
 tools/m11/trap_triage/store_watch_1783.sh          |  10 +-
```
- 本 PR 自身の差分 (`8ba5017d..e124f367`、`store_watch_1783.sh` のみ) は上記 diff の `store_watch_1783.sh` 行。`git diff 8ba5017d e124f367 -- tools/m11/trap_triage/store_watch_1783.sh` で再現できる。
- `git diff 6e001233 8ba5017d -- tools/m11` は追加 2 ファイル (REPORT_1783.md・store_watch_1783.sh) のみ。
- `git diff 8ba5017d HEAD -- tools/m11` (修正 commit の差分。`store_watch_1783.sh` のみ):

```diff
diff --git a/tools/m11/trap_triage/store_watch_1783.sh b/tools/m11/trap_triage/store_watch_1783.sh
--- a/tools/m11/trap_triage/store_watch_1783.sh
+++ b/tools/m11/trap_triage/store_watch_1783.sh
@@ -2,7 +2,7 @@
-#   出力: work/probe1783/<tag>.err (`unit N` 行と `[aw]` 行), work/probe1783/sites.json, work/probe1783/<tag>.out (survey 結果)
+#   出力: work/probe1783/<tag>.aw (`unit N [aw] ...` 行 = 書込み検出), work/probe1783/<tag>.err (進捗 `unit N` 行), work/probe1783/sites.json, work/probe1783/<tag>.out (survey 結果)
 #   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し sw1783.o / ov.o を消す (trap で必ず復元).
@@ -19,10 +19,6 @@ emcc -c work/probe1783/boot_sw.ll -o work/obj/boot.o $CF || exit 1
 bash m11_build.sh > work/probe1783/build_$tag.log 2>&1 || { tail -5 work/probe1783/build_$tag.log; exit 1; }
-sed -e ... m11_survey.mjs > work/probe1783/survey_sv.mjs
-SV_PROG=1 node trap_triage/survey_units.mjs work/probe1783/$tag.json > work/probe1783/$tag.out 2> work/probe1783/$tag.err || { ... }
+SV_PROG=1 SV_ERR_LOG=work/probe1783/$tag.aw node trap_triage/survey_units.mjs work/probe1783/$tag.json > work/probe1783/$tag.out 2> work/probe1783/$tag.err || { ... }
 grep -a -o "^M11_SURVEY .\{0,120\}" work/probe1783/$tag.out
-grep -a -c "^\[aw\]" work/probe1783/$tag.err | sed 's/^/[aw] hits: /'
+grep -a -c "\[aw\] " work/probe1783/$tag.aw | sed 's/^/[aw] hits: /'
```

- `git diff 6e001233 8ba5017d -- tools/m11` の差分: 追加 2 ファイル (REPORT_1783.md・store_watch_1783.sh) のみ。`tools/m11` の既存コードは変更なし。
