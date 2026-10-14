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
    - **§7 で訂正**: 完走は unit 0〜144 (145 unit)。unit 145 は開始行 (`unit 145`) のみで、完走していない。
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

**判定 (#1869 の縮小後の受入 1)**: 計装なしの全 942 unit で `0x1ac308` の値変化を判定し、計装版の停止点を記録した。値が変わった unit は 0 件。計装版は unit 145 が timeout (1500 s) 内に終わらず、全 942 unit の `[aw]` 採取は未達。
§3 の番号 (1〜3) は #1783 の受入で、本節の番号とは別。移管: 旧 受入 1 (計装版で全 942 unit の `[aw]` を site 単位で採る) → #2769。旧 受入 2 (native 側 `0x5ac308` の書込み命令アドレスと値) → #2770。

### 7.1 測定の条件

- 測定 commit: `a10edf01` (`survey_units.mjs` に `SV_SLOT` を追加)。以降、`tools/m11` のうち REPORT を除くコードは変わっていない。
- 差分証跡: `git diff a10edf01 HEAD -- tools/m11 ':(exclude)*REPORT*'` の出力は 0 byte (本節の作成時点の HEAD で確認)。
- 素材: work-m11・toolchain-emsdk・fl-win64 (実装 run で展開)。PR 本文に `oc_artifacts: fl-win64 toolchain-emsdk work-m11` を記載。
- main との関係: 枝は `580dd294` 起点で、`origin/main` (`8693fd4b`、本節の作成時点) より 216 commit 古い。main 側は `tools/m11` のうち REPORT を除く 14 ファイルを変えているが、測定に使った 4 ファイル (`survey_units.mjs`・`m11_build.sh`・`m11_gen_ir2.sh`・`trap_triage/store_watch_1783.sh`) は含まれない。他の 14 ファイルがビルド結果を変えるかは未確認。merge 後の main とは測定対象が完全には一致しない。

### 7.2 再現コマンド

(a) 計装なし・全 942 unit (1 行):

```sh
export FL_WIN64_DIR=<fl-win64 の展開先> EMSDK_ENV=<emsdk_env.sh のパス> && cd tools/m11 && mkdir -p work/probe1869 && bash m11_gen_ir2.sh && bash m11_build.sh && SV_SLOT=0x1ac308 node trap_triage/survey_units.mjs work/probe1869/slot.json
```

- stdout の `SLOT_BOOT` 行は `survey_units.mjs` の 57 行目、`SURVEY_UNITS` 行は 103 行目で出る。JSON は `work/probe1869/slot.json`。

(b) 計装版 (停止点):

```sh
export FL_WIN64_DIR=<fl-win64 の展開先> EMSDK_ENV=<emsdk_env.sh のパス> && cd tools/m11 && bash m11_gen_ir2.sh && bash m11_build.sh && timeout 1500 bash trap_triage/store_watch_1783.sh run1
```

- 出力: `work/probe1783/run1.out` (`SURVEY_UNITS` 行)、`run1.err` (進捗 `unit N`)、`run1.aw` (`[aw]` 行)。

### 7.3 計装なし・全 942 unit (a)

- 実装 run の記録: `m11_gen_ir2.sh` rc 0 (45.7 s)、`m11_build.sh` rc 0 (21.6 s)、survey rc 0・11.4 s。boot_enter 後の `0x1ac308` の値は `0xf960`。値が変わった unit は 0 件 (`slot` 付きの unit が無い)。
- 942 unit の範囲: 反復は `for (i = 0; i < 942; i++)` (`survey_units.mjs` 61 行目)。`SV_ONLY`・`SV_SKIP` を指定しなければ、`SURVEY_UNITS` 行の kinds の合計は 942 になる (コードの性質であり、出力の引用ではない)。
- 値の判定: unit ごとに、実行前 (69 行目) と実行後 (94 行目) の 4 バイトを比べ、違えば `slot` を付ける。

### 7.4 原本の引用 (未了)

- 引用できないもの: (i) 7.2 (a) の `SURVEY_UNITS` 行 (kinds 合計 942 の確認用)、(ii) 7.2 (a) の `SLOT_BOOT` 行、(iii) 7.2 (b) の `run1.err` の最終行 (`unit 145`)。
- 理由: 測定時の stdout・stderr と `work/` を repo に残していない。この fix run の `$ARTIFACTS_DIR` には `fl-win64` しか無く、`work-m11`・`toolchain-emsdk` (emcc) が無いため再実行できない。実装 run の CI ログは取得できなかった。
- 扱い: 7.3 の数値は「実装 run の記録」として読む。repo 内の出力では再確認できない。`work-m11`・`toolchain-emsdk` を指定した run で 7.2 (a) を実行し、上の 3 行をここに引用する (起票先 #2769)。

### 7.5 計装版の停止点 (b)

- 実装 run の記録: `store_watch_1783.sh run1` (計装 54,041 store)。rc 124・25 分 19 秒 (timeout 1500 s の後の EXIT 時 restore を含む)。`[aw]` は 0 件。
- 進捗行 `unit N` は unit N の**開始**時に出る (`SV_PROG=1`、`survey_units.mjs` 72 行目)。最後の進捗行は `unit 145`。unit 146 の開始行は timeout までに出なかった。unit 145 の開始行があるので、unit 0〜144 は完了している (順次実行)。
- 計装なしでは、unit 145 を含む 942 unit 全体が 11.4 s で完走した (7.3)。
- 「停止」の意味: timeout 内に unit 145 が終わらなかったことだけを示す。処理が止まった (hang) のか、計装 store の分だけ遅いのかは区別していない。切り分けは #2769。

### 7.6 値変化 0 件の範囲と REPORT_1588 §4.5 との関係

- 判定の範囲: 基準値は各 unit の直前 (69 行目) と直後 (94 行目) で取る。最初の基準は `boot_enter` の後の値 (`0xf960`) なので、`boot_enter` 内の書込みは見ていない。unit 境界で比べるため、unit 内で一度変わって戻る書込みと、同じ値への書込みも見えない。よって 0 件は「各 unit の前後で 4 バイトが変わらなかった」ことだけを示す。「0x5ac308 は unit 中に書き換わらない」とは書けない。
- REPORT_1588 §4.5 との関係: §4.5 は wasm の 410320 入口で `[rax-0x30]` (= `0x1ac308`) の読み値が `0x5af3d0` だったことから、「このスロットは実行時に書き換えられる」と結論している。本節の boot 後の値 `0xf960` は、その `0x5af3d0` とも一致しない。考えられる説明は (i) boot_enter 内の書込み、(ii) unit 内で変わって戻る書込み、(iii) 同じ値への書込み、(iv) §4.5 の再現 (`repro_1588.sh`、p01) と survey の実行経路の違い。どれかは未確定。本節は §4.5 の結論を取り消さない。起票先 #2769。
- boot 後の `0xf960` と静的値 `0x40f960` (§4.5): 下位 16 bit は一致するが、同じ由来かは未確認 (差は `0x400000` で、イメージ基底の差に見えるが未検証)。起票先 #2769。

### 7.7 差分証跡と鮮度

- 測定 commit `a10edf01` から作成時 HEAD までの `tools/m11` のコード差分 (REPORT を除く) は 0 byte (7.1)。
- merge 後の main で再測定した結果は未確認 (7.1 の main 側の差分)。再測定は子を起票せず、PR 本文の未解決表で扱う。

### 7.8 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計装版の unit 145 が timeout 内に終わらない原因 (hang か遅さか)、全 942 unit の `0x1ac308` への `[aw]` 採取 | wasm 側の書込み元が未確定 | #2769 |
| native 側 `0x5ac308` の store 捕捉 (ld_native に監視が無い) | 両側の比較ができない | #2770 |
| 両側で書込み値が分かれる最初の地点と書込み元関数の記録 | 上 2 件の結果が要る | #2769・#2770 |
| 7.6 の判定範囲 (boot_enter 内・unit 内で戻る書込み・同値書込み) と REPORT_1588 §4.5 の関係 | 0 件を「書き換わらない」と読めない | #2769 |
| boot 後の `0xf960` と静的 `0x40f960` の由来 | スロットの初期値の出所が未確定 | #2769 |
| 7.4 の原本 (`SURVEY_UNITS` 行・`SLOT_BOOT` 行・`run1.err` 最終行) | repo 内の出力では 942 unit の完走を示せない | #2769 (同じ build・survey の再実行で引用) |
| merge 後の main での再測定 | 測定対象が main と一致しない | 本 PR 本文の未解決表 (再測定のみのため子は起票しない) |

## 8. #2770 (LD-129): native 側 0x5ac308 の書込み監視 (ld_native)

**判定**: 受入 1 は実装済み (`rt/ld_native.c` の `LD_WATCH_ADDR`・測定 commit `12982d74`)。受入 2 は部分的: 監視付き F の run では `0x5ac308` への書込みの記録は 0 件だった。ただし (a) 「監視が実行結果を変えない」は未確認 (§8.4)、(b) 942 unit のうち 14 unit は走っていない (§8.3)、(c) 生の出力を repo に残していないため、B・B2 の値と C の測定 commit は再検算できない (§8.2)。書込み元は未特定。

### 8.1 測定条件

- 測定 commit: `12982d74` (`tools/liftdiff/rt/ld_native.c` のみ変更)。`git diff 12982d74 104d6a0c -- tools/liftdiff` の出力は 0 byte。本 PR の fix で `rt/ld_native.c` を変えた。その後の HEAD では測定していない (§8.6)。
- 素材 (測定時): `fl-win64` を `FL_WIN64_DIR` に展開、`work-m11`・`work-liftdiff` を `tools/*/work/` に展開。`toolchain-emsdk` は native 側の測定に不要。
- 監視の仕組み: `LD_WATCH_ADDR=<VA hex>` と `LD_WATCH_OUT=<path>` (両方指定時のみ有効)。監視 page を `PROT_READ|PROT_EXEC` にし、書込みの SIGSEGV で書込み命令の RIP・書込み先を採る。TF で書込み 1 命令だけ実行してから新しい値を読み、page を戻す。書込みは通常どおり行われ、値は変えない。記録は書込み先の開始アドレスが va-15〜va+7 にあるもの (重ならない書込みを含む superset。取りこぼしは無い)。
- 行形式: `wp case=... rip_rva=... old=... new=... chg=... ins=...`。正常終了時の末尾に `wpsum faults=N timeouts=M` (watch fault 数・SIGALRM で打ち切った call 数)。`wpsum` は測定 commit `12982d74` には無い (§8.6)。
- 実行: `tools/liftdiff` で `FL_WIN64_DIR=... LD_WATCH_ADDR=5ac308 LD_WATCH_OUT=... python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild` (wall 21 s)。VA = ImageBase `0x400000` + RVA。`0x5ac308` は wasm の `0x1ac308` に対応する。

### 8.2 実測と定義

定義 (`tools/liftdiff/ldlib/boot.py` の `build_state` と `liftdiff.py bootstate` の出力):

- entry: `ep` case の status。k = entry 後の `System.InitCount` (`0x11eac98`)。
- 単位フェーズ: 対象は InitTable の添字 `start`〜`end` のうち `units[i]≠0` かつ `*proc≠0` の unit。ok+N = status ok の件数、fail M = 非 ok の件数、最初 P = 非 ok の最初の InitTable 添字。
- units_run = `k + ok+N` (boot.py の `covered`)。分母は InitTable の全件 942。
- img_runs = `len(st['img'])` (`bootstate` の STATE JSON の `img` 配列の要素数)。
- wp 件数 = `grep -c '^wp ' <LD_WATCH_OUT>`。

| run | 測定 commit | 監視 | entry | 単位フェーズ | units_run | img_runs | wp 件数 |
|---|---|---|---|---|---|---|---|
| F | `12982d74` | `5ac308` | segv (rva `0x26833d`)・k=246 | ok+682 / fail 3 / 最初 830 | 928/942 | 216 | 0 |
| C (陽性対照) | 未記録 (作業ツリーの run。`12982d74` と同一 code かは未確認) | `15eac98` (= `System.InitCount`) | 未記録 | 未記録 | 未記録 | 未記録 | 248 |
| B・B2 (対照) | 未記録 | 無し | 未記録 | 未記録 | 未記録 | 未記録 | — |

- 先行の作業ツリー run (A) は F と同じ値を記録したが、code の同一性を記録していないため表には入れない。
- B・B2 は生の出力を保存していない。値は再測定まで記録できない (§8.6 の未解決表)。

### 8.3 解釈

- 検出器が働いたことは、C の wp 行 248 件で記録されている。ただし C の測定 commit と出力は未保存のため、この数は再検算していない。
- F の記録 0 件は「この監視付き run で `0x5ac308` への書込みが記録されなかった」ことだけを示す。「native boot では書かれない」とは書かない (§8.4 の非摂動性が未確認のため)。
- 走らなかった unit: `units_run` 928 は 942 の一部。残り 14 件のうち fail 3 件 (最初 830) を除く 11 件は、呼ばれなかった unit (`units[i]==0` または `*proc==0`) と `start=k+1` で飛ばした分の内訳を分解していない。記録 0 件の範囲は、実際に走った 928 unit に限られる。
- wasm 側の 0 件の根拠は §2 run2 の `.aw` の `grep -c '\[aw\] '` = 0 だけ (`[aw]` 検出経路は確認済み)。これは grep 経路の確認であり、wasm 側の監視そのものの陽性対照ではない。survey の完走は unit 0〜144 (§7 で訂正)。§7.3 の「値変化 0 件」は unit 境界の比較で、書込みの証拠ではない。§7.5 の `[aw]` 0 件は run1 (`SV_ERR_LOG` 未指定) で、根拠にしない。
- 書込み元は未特定。wasm 側は #2769、native 側は #2770 で扱う。

### 8.4 未確認 (非摂動性)

- 「監視が実行結果を変えない」は**未確認**。
- 記録上の差 (生データ未保存のため再検算不可。本 REPORT の記述のみ): 監視なし B と B2 で img run 66 の 1 byte が異なった。監視付き A と監視なし B の差も 1 byte と記録されている。監視付き F と B2 の差は run 境界 (img_runs 216 と 215) と heap。原因は切り分けていない。
- 監視による分岐変化の候補: 各 call の時限 (`setitimer` 1.5 s) に対する時限切れの増加。`wpsum timeouts` で run ごとに数え、B・B2 と比べる (§8.6)。
- 次の再測定: `work-m11`・`work-liftdiff` を使う run で、B・B2 と F を §8.2 の指標で取り直し、`wpsum` を記録する。

### 8.5 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先>   # [WIN64] (docs/REFERENCES.md §4)
cd tools/liftdiff
gcc -O1 -g -Wall -Wno-unused-function -o work/ld_native rt/ld_native.c rt/ld_ms_call.S -lm
LD_WATCH_ADDR=5ac308 LD_WATCH_OUT=<出力ファイル> python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild
grep -c '^wp ' <出力ファイル>; tail -1 <出力ファイル>   # wp 件数・wpsum
# 陽性対照: LD_WATCH_ADDR=15eac98 (System.InitCount)
```

### 8.6 本 fix での変更と未解決 (測定は未実施)

- SIGALRM: TF 待ち (`g_wp_pend`) の間は SIGALRM を block する (`wp_fault` で `sigprocmask` と `uc_sigmask` を変え、`wp_finish` で `uc_sigmask` から外す)。timeout の `siglongjmp` で抜ける経路でも、pend が残っていれば page を戻す。
- コメントを実装に合わせた (記録条件は superset)。`wpsum` 集計行を追加した。
- 差分: `git diff 12982d74 5b077740 -- tools/liftdiff` の出力は `rt/ld_native.c` のみ (16 行追加・6 行削除)。
- 検証: `gcc -O1 -g -Wall` で `ld_native.c` の警告 0 件。SIGALRM の窓は読解のみで、e2e では確認していない (この fix run では `work-m11`・`work-liftdiff` が展開されていない)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後の HEAD で F・C・B・B2 を §8.2 の指標と `wpsum` 付きで取り直す | 非摂動性と 0 件の判定の根拠が未確定 | #2770 (本 issue に残す・再測定) |
| 残り 14 件のうち fail 3 件以外の 11 件の内訳 | 走らなかった範囲が未確定 | #2770 (再測定の出力で引用) |
| 全 942 unit と boot 後の書込み元の切り分け | 書込み元が未確定 | #2769 |
