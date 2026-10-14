# #1783 (LD-63): m11 0x5ac308 (410320 の間接 call スロット) の書き込み元 — 途中報告

**判定: 受入条件 1・2 は未達 (子 #1869 へ移管済み)。受入条件 3 は部分達成 (手順のスクリプトを commit、全 unit 完走は未実測)。完了単位は「書込み監視スクリプトと報告の追加」に縮小し、`Closes #1783`。**

親: #1588。前提の結論は `REPORT_1588.md` §4.5 を正とする (`0x5ac308` は実行時に書き換わり、静的参照 0 件)。

## 0. 検証環境

- 測定 base: `origin/main` `6e001233` (branch `1783-m11-slot-5ac308-writer`)。
- 測定 commit (実測した code): `80d011cc` (`tools/m11` のコードは `22eb21be` と同一)。修正 HEAD: `e07ca760` (`store_watch_1783.sh` の `EMSDK_ENV` 必須化のみ。survey の経路は不変)。
- 再測定 (run2) は `80d011cc` の script で実施。修正 HEAD `e07ca760` の script 全体は未実行 (変更は source 行のみ・`bash -n` と未設定時の fail を確認)。
- 素材 (fix run で取得): `fl-win64` を `$HOME/analysis/win64` (`FL_WIN64_DIR`) に展開 (5.5 s)。`toolchain-emsdk` は agent-setup が `/opt/emsdk` に展開、`emcc 6.0.12` を確認。`work-m11` / `work-liftdiff` は worktree 直下に展開 (gitignore)。
- `m11_gen_ir2.sh` (`80d011cc`): rc 0、49.9 s、`boot_final.ll` 490,733 行、`ldfix=applied`。`ir_conditions.json` を生成。
- `m11_build.sh` (`80d011cc`): rc 0、25.9 s、`wasm-ld signature mismatch: 0, undefined symbol: 0`。

## 1. 計装 (追加したもの)

- `tools/m11/trap_triage/store_watch_1783.sh`: `watch_store_682.py` の全 store 計装と、既存の `watch_addr_1046.c` (固定番地版) を流用する。監視番地は `M11_WATCH_1783` (既定 `0x1ac308` = wasm 側の `0x5ac308` に対応)。survey は `survey_units.mjs` を使う。
- 計装 IR は `boot_sw.ll` (54,041 store を計装)。IR の値と分岐は変えない。

## 2. 実測

- **run1 (`8ba5017d`、前 run)**: 計装 54,041 store。survey は unit 145 で打ち切り。旧 script の `[aw]` 0 件は計測値ではない (`SV_ERR_LOG` 未指定で `[aw]` が `.err` に届かない構造欠陥。§6 で修正)。
- **run2 (`80d011cc`、この run)**: `FL_WIN64_DIR=$HOME/analysis/win64 bash trap_triage/store_watch_1783.sh run2`、foreground・`timeout 1200` (20 分)。
  - rc **124** (timeout で打ち切り)。計装 54,041 store (run1 と同一)。実行時間 20 分 22 秒 (07:37:47〜07:58:10)。
  - survey は **unit 0〜145 (146 unit) を完走**し、unit 146 以降は未実行。全 942 unit のうち 146 unit が完走 (15.5%)。
  - `[aw]` 件数: `grep -c '\[aw\] ' work/probe1783/run2.aw` = **0** (`.aw` は 2,595 byte。`unit -1`・`unit 15`・`unit 17` 等の `[m11]` 行のみ)。`[aw] ` 検出経路は `.aw` に届く (`m11_sw` の `fprintf` → `SV_ERR_LOG`)。接頭辞付きの合成入力で旧 grep 0・新 grep 1 は §6 の通り確認済み。
  - 終了時の restore trap で `m11_boot.wasm` は元に戻った (`m11_build.sh` rc 0 を確認)。
- 結論: unit 0〜145 の範囲では書込み監視 (`0x1ac308`) の hit は 0。unit 146 以降は未確認。`0x5ac308` の書込み元はこの run では特定できていない。
- 修正後 `e07ca760` の script 全体の再実行は未実施 (時間上限)。修正は `EMSDK_ENV` の source 行のみ。`bash -n` 合格、未設定時に `exit 1` を確認。
- 全 942 unit の完走は #1869 (受入 1) で扱う。

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
| 全 942 unit の survey 完走 (実測は unit 0〜145 まで・20 分 timeout) | unit 146 以降の `[aw]` が未確認 | #1869 (受入 1) |
| 修正 HEAD `e07ca760` の script 全体の再実行 (変更は source 行のみ) | 実行経路の確認は run2 (`80d011cc`) まで | #1869 (受入 1 の実行に含む) |

## 5. 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先> EMSDK_ENV=<emsdk_env.sh のパス> # [WIN64]・[EMSDK] (docs/REFERENCES.md §4)
cd tools/m11
bash m11_gen_ir2.sh
bash m11_build.sh
bash trap_triage/store_watch_1783.sh run1   # 全 unit 完走まで要時間 (run2 は 20 分 timeout で unit 145 まで)
```

`[aw]` の件数: `work/probe1783/run1.aw` (`unit N [aw] ...`) から `grep -c '\[aw\] ' work/probe1783/run1.aw`。

## 6. 検証の鮮度 (WORKFLOW §6)

- 測定 commit: `80d011cc` (run2 の実測時点。`tools/m11` のコードは `22eb21be` と同一)。run1 の測定 commit は `8ba5017d` (旧値)。修正 HEAD は `e07ca760`。
- 修正 commit: `e124f367` (`store_watch_1783.sh` の `[aw]` 経路・dead code 削除)。`2c0c8f4d` は REPORT のみ。`eb55aef7` は main (`3624a5fc`) の取り込み merge。
- **差分は 0 ではない**: `8ba5017d..HEAD` の `tools/m11` には、本 PR の script 修正のほか、main 取り込みで入った他 PR の code 変更が含まれる (`m11_build.sh` の `M11_TRACE_ISOLATE` 追加など)。run2 は `80d011cc` (= `22eb21be` と `tools/m11` が同一) で実施した。修正 HEAD `e07ca760` との差は `store_watch_1783.sh` の source 行のみ。
- `git diff --stat 8ba5017d HEAD -- tools/m11` (修正 HEAD `e07ca760` 時点):

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
 tools/m11/trap_triage/REPORT_1783.md               |  67 ++++++++-
 tools/m11/trap_triage/REPORT_718.md                |  27 +++-
 tools/m11/trap_triage/store_watch_1783.sh          |  13 +-
 14 files changed, 578 insertions(+), 22 deletions(-)
```
- 本 PR 自身の差分 (`8ba5017d..e124f367`、`store_watch_1783.sh` のみ) は上記 diff の `store_watch_1783.sh` 行。`git diff 8ba5017d e124f367 -- tools/m11/trap_triage/store_watch_1783.sh` で再現できる。
- `git diff 6e001233 8ba5017d -- tools/m11` は追加 2 ファイル (REPORT_1783.md・store_watch_1783.sh) のみ。
- 測定 commit `80d011cc` から修正 HEAD までの差分 (WORKFLOW §6。`git diff 80d011cc HEAD -- tools/m11`):

```diff
diff --git a/tools/m11/trap_triage/store_watch_1783.sh b/tools/m11/trap_triage/store_watch_1783.sh
index 76c88a1a..2c4fa5a9 100755
--- a/tools/m11/trap_triage/store_watch_1783.sh
+++ b/tools/m11/trap_triage/store_watch_1783.sh
@@ -6,7 +6,8 @@
 #   終了時に work/obj/boot.o を元の boot_final3.ll から再生成し sw1783.o / ov.o を消す (trap で必ず復元).
 set -uo pipefail
 HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"; cd "$HERE"
-source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" > /dev/null 2>&1
+: "${EMSDK_ENV:?EMSDK_ENV を設定してください ([EMSDK]・docs/REFERENCES.md §4)}"
+source "$EMSDK_ENV" > /dev/null 2>&1
 W=${M11_WATCH_1783:-0x1ac308}
 FIX=${M11_FIX_682:-0}
 CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -O0 -g1 -DM11_LB_BASE=${M11_LB_BASE:-0} -DM11_OV_CLASSCREATE=${M11_OV_CLASSCREATE:-0} -I."
```

- `git diff 6e001233 8ba5017d -- tools/m11` の差分: 追加 2 ファイル (REPORT_1783.md・store_watch_1783.sh) のみ。`tools/m11` の既存コードは変更なし。
