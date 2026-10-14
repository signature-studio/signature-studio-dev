# #1783 (LD-63): m11 0x5ac308 (410320 の間接 call スロット) の書き込み元 — 途中報告

**判定: 受入条件 1・2 は未達 (子 #1869 へ移管済み)。受入条件 3 は部分達成 (手順のスクリプトを commit、全 unit 完走は未実測)。完了単位は「書込み監視スクリプトと報告の追加」に縮小し、`Closes #1783`。**

親: #1588。前提の結論は `REPORT_1588.md` §4.5 を正とする (`0x5ac308` は実行時に書き換わり、静的参照 0 件)。

## 0. 検証環境

- 測定 base: `origin/main` `6e001233` (branch `1783-m11-slot-5ac308-writer`)。
- 測定 commit (実測した code): `80d011cc` (`tools/m11` のコードは `22eb21be` と同一)。測定 commit 以降の差分は `store_watch_1783.sh` の source 行 1 件 (`EMSDK_ENV` 必須化のみ。survey の経路は不変。§6)。
- 再測定 (run2) は `80d011cc` の script で実施。測定 commit 以降の変更を含む script 全体の再実行は未実施 (`bash -n` と未設定時の fail を確認)。
- 素材 (この run で取得・展開): `fl-win64` を [WIN64] (`FL_WIN64_DIR`) に展開 (6.6 s)。`toolchain-emsdk` は [EMSDK] として `emcc 6.0.12` を確認。`work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/` に展開 (gitignore)。

## 1. 計装 (追加したもの)

- `tools/m11/trap_triage/store_watch_1783.sh`: `watch_store_682.py` の全 store 計装と、既存の `watch_addr_1046.c` (固定番地版) を流用する。監視番地は `M11_WATCH_1783` (既定 `0x1ac308` = wasm 側の `0x5ac308` に対応)。survey は `survey_units.mjs` を使う。
- 計装 IR は `boot_sw.ll` (54,041 store を計装)。IR の値と分岐は変えない。

## 2. 実測

- **現 head の gen/build (この run)**: `m11_gen_ir2.sh` rc 0 (34.5 s、`boot_final.ll` 490,733 行、`ldfix=applied`)。`m11_build.sh` rc 0 (17.4 s、`wasm-ld signature mismatch: 0, undefined symbol: 0`)。出力の wasm 本体は `work/m11_boot.cjs.wasm` (旧表記 `m11_boot.wasm` は誤り)。
- **`[aw]` 書式の件数確認**: `grep -a -c 'site=%u addr=%x' work/m11_boot.cjs.wasm` = **0** (通常ビルド。計装なし)。store_watch と同じ手順で `sw1783.o` をリンクした計装ビルドでは **1**。survey は実行していない。件数 1 は `[aw]` 書式の文字列が計装ビルドに入ったことを示すだけで、store hit の証拠ではない。計装ビルドは復元済み (`m11_build.sh` rc 0、件数 0 に戻ることを確認)。
- **run1 (`8ba5017d`、前 run)**: 計装 54,041 store。survey は unit 145 で打ち切り。旧 script の `[aw]` 0 件は計測値ではない (`SV_ERR_LOG` 未指定で `[aw]` が `.err` に届かない構造欠陥。§6 で修正)。
- **run2 (`80d011cc`)**: `FL_WIN64_DIR` に [WIN64] の展開先を指定して `bash trap_triage/store_watch_1783.sh run2`、foreground・`timeout 1200` (20 分)。
  - rc **124** (timeout で打ち切り)。計装 54,041 store (run1 と同一)。実行時間 20 分 22 秒 (07:37:47〜07:58:10)。
  - survey は **unit 0〜145 (146 unit) を完走**し、unit 146 以降は未実行。全 942 unit のうち 146 unit が完走 (15.5%)。
  - `[aw]` 件数: `grep -c '\[aw\] ' work/probe1783/run2.aw` = **0** (`.aw` は 2,595 byte。`unit -1`・`unit 15`・`unit 17` 等の `[m11]` 行のみ)。`[aw] ` 検出経路は `.aw` に届く (`m11_sw` の `fprintf` → `SV_ERR_LOG`)。接頭辞付きの合成入力で旧 grep 0・新 grep 1 は §6 の通り確認済み。
  - 終了時の restore trap で `m11_boot.cjs.wasm` は元に戻った (`m11_build.sh` rc 0 を確認)。
- 結論: unit 0〜145 の範囲では書込み監視 (`0x1ac308`) の hit は 0。unit 146 以降は未確認。`0x5ac308` の書込み元はこの run では特定できていない。
- 測定 commit 以降の変更 (`EMSDK_ENV` 必須化の source 行) を含む script 全体の再実行は未実施 (時間上限)。`bash -n` 合格、未設定時に `exit 1` を確認。
- 全 942 unit の完走は #1869 (受入 1) で扱う。

## 3. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | `0x5ac308` へのストアを実行時に捕まえる (書込み命令アドレスと値を native / wasm で採取) | **未達**。wasm 側は計装済みだが完走せず。native 側の書込み捕捉方式は未実装 (`rt/ld_native.c` に store 監視は無い) |
| 2 | 書込み元関数と、両側で値が分かれる最初の地点を実測で記録 | **未達** |
| 3 | 手順を repo 内スクリプトで実行可能にし commit | **部分達成**。`store_watch_1783.sh` を commit。80d011cc で unit 0〜145 まで実行 (rc 124、timeout)。全 unit の完走は未確認 |

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm 側の全 unit survey の完走と、`[aw]` の書込み元 (site → fn・IR 行) の特定 | 書込み元の一方の側が未確定 | #1869 (起票済み・受入 1) |
| native 側の `0x5ac308` 書込み捕捉 (ld_native の store 監視が無い) | 両側の比較ができない | #1869 (起票済み・受入 2) |
| 全 942 unit の survey 完走 (実測は unit 0〜145 まで・20 分 timeout) | unit 146 以降の `[aw]` が未確認 | #1869 (受入 1) |
| 測定 commit 以降の source 行変更を含む script 全体の再実行 | 実行経路の確認は run2 (`80d011cc`) まで | #1869 (受入 1 の実行に含む) |

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

- 測定 commit: `80d011cc` (run2 の実測時点。`tools/m11` のコードは `22eb21be` と同一)。run1 の測定 commit は `8ba5017d` (旧値)。
- 測定 commit 以降の差分 (`tools/m11` のうち REPORT を除く): `store_watch_1783.sh` の source 行 1 件 (`EMSDK_ENV` 必須化)。`m11_gen_ir2.sh`・`m11_build.sh` は測定 commit から変更なし。
- `git diff --shortstat 80d011cc HEAD -- tools/m11 ':(exclude)*REPORT*'` の出力: `1 file changed, 2 insertions(+), 1 deletion(-)`
- `git diff --stat 8ba5017d HEAD -- tools/m11 ':(exclude)*REPORT*'` の出力 (REPORT を除く):

```
 tools/m11/ldfix/audit_undefload_dest.py            | 166 +++++++++++++++++++++
 .../ldfix/results/candidate_verdicts_1161.jsonl    |  31 ++++
 tools/m11/ldfix/results/f4_liftdiff_1646.tsv       |  11 ++
 tools/m11/m11_build.sh                             |   5 +-
 tools/m11/trap_triage/store_watch_1783.sh          |  13 +-
 5 files changed, 217 insertions(+), 9 deletions(-)
```

- 旧測定 commit `8ba5017d` からの差分には、本 PR の script 修正のほか、main 取り込みで入った他 PR の code 変更が含まれる (`m11_build.sh` の `M11_TRACE_ISOLATE` 追加など)。run2 は `80d011cc` (= `22eb21be` と `tools/m11` が同一) で実施した。
- 本 PR 自身の差分 (`8ba5017d..e124f367`、`store_watch_1783.sh` のみ) は上記 diff の `store_watch_1783.sh` 行。`git diff 8ba5017d e124f367 -- tools/m11/trap_triage/store_watch_1783.sh` で再現できる。
- 修正 commit: `e124f367` (`store_watch_1783.sh` の `[aw]` 経路・dead code 削除)。`2c0c8f4d` は REPORT のみ。`eb55aef7` は main (`3624a5fc`) の取り込み merge。
- `git diff 6e001233 8ba5017d -- tools/m11` は追加 2 ファイル (REPORT_1783.md・store_watch_1783.sh) のみ。`tools/m11` の既存コードは変更なし。

## 7. #1869 追記: 全 942 unit の値判定と計装版の停止点 (2026-10-14)

- 測定 commit: `a10edf01` (`survey_units.mjs` に `SV_SLOT` を追加。以降 `tools/m11` のコードは同一)。
- 素材: work-m11・toolchain-emsdk・fl-win64 を `$HOME/artifacts` から展開 (fl-win64 は `$RUNNER_TEMP`)。`m11_gen_ir2.sh` rc 0 (45.7 s)、`m11_build.sh` rc 0 (21.6 s)。
- (a) 計装なし build・全 942 unit (`SV_SLOT=0x1ac308`): rc 0・11.4 s。boot_enter 後の `0x1ac308` の値は `0xf960`。**値が変わった unit は 0 件** (`work/probe1869/slot.json` に `slot` 付きの unit 無し)。値が同じままの書込みは、この方法では見えない。
- (b) 計装版 `store_watch_1783.sh run1` (計装 54,041 store・`timeout 1500`): rc 124・25 分 19 秒。進捗行 `unit N` は unit N の**開始**を示す。完走は unit 0〜144 (145 unit)、`[aw]` は 0 件。**unit 145 が 25 分以上完走せず** (`run1.err` の最終行 `unit 145`)。計装なし版は同じ unit を含めて 11.4 s で完走する。
- 前節 §2 の run2 の「unit 0〜145 (146 unit) を完走」は、進捗行を完走と読み違えた記述。完走は 0〜144 が正しい。
- 受入条件の判定: 1 (全 942 unit の `[aw]` 採取) は未達 (計装版が unit 145 で停止)。2 (native 側の `0x5ac308` 捕捉) は未着手。3 (REPORT_1783 への実測記録) は本節で部分達成。
- 未解決 (起票先):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計装版の unit 145 の停止原因と、停止を避けた全 942 unit の `[aw]` 採取 | wasm 側の書込み元が未確定 | 子 issue (本 PR 本文の表) |
| native 側 `0x5ac308` の store 捕捉 (ld_native に監視が無い) | 両側の比較ができない | 子 issue (本 PR 本文の表) |
