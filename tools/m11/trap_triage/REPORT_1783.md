# #1783 (LD-63): m11 0x5ac308 (410320 の間接 call スロット) の書き込み元 — 途中報告

**判定: 受入条件 1・2 は未達 (子 #1869 へ移管済み)。受入条件 3 は部分達成 (手順のスクリプトを commit、全 unit 完走は未実測)。完了単位は「書込み監視スクリプトと報告の追加」に縮小し、`Closes #1783`。**

親: #1588。前提の結論は `REPORT_1588.md` §4.5 を正とする (`0x5ac308` は実行時に書き換わり、静的参照 0 件)。

> #2770 (LD-129) の節 (ld_native の 0x5ac308 書込み監視・旧 §8) は付録 `tools/m11/trap_triage/REPORT_APPENDIX_2770.md` §8 に分割移動した (250 行上限)。本ファイルの §8 は #2769 の節。結論 (#2770): 監視付き F で `0x5ac308` への書込み 0 件。監視 page を arm した run でも boot 状態は監視なしと一致 (付録 §8.8)。

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

## 8. #2769: 計装版の停止原因と全 942 unit の `[aw]` 採取

**判定**: 受入 1 (停止の切り分け) は達成。受入 2 (全 942 unit の `0x1ac308` の `[aw]`) は、計装の範囲を「スタック slot への直接 store を除く全 store」にして **0 件** (run4)。0 件は次の範囲に限る。(i) 計装した `store` 命令による書込みだけを見ている。rep 系 helper 経由の書込みは計装外 (§8.4)。(ii) 計装版の挙動は計装なし版と 2 unit (158・283) で一致しない。(iii) スタック slot を外した run4 の 0 件は、スタック配置が `0x1ac308` と重ならないという未確認の前提に依る (§8.3)。全 store を計装した run5 も 0 件だが、3 unit は site 上限で打ち切られている (§8.3.1)。

### 8.1 測定条件

- 測定 commit: `32377077` (コードを変えた最後の commit。`store_watch_1783.sh` に `M11_WATCH_SRC`・`M11_SW_LIMIT` を足し、`SURVEY_UNITS` の grep を直し、`watch_store_682.py` の前提コメントを未確認と書き直した)。base・run4・run5 はいずれもこの commit で実施した。
- `git diff --stat 5940f848 32377077` は `trap_triage/store_watch_1783.sh` と `trap_triage/watch_store_682.py` の 2 件のみ。gen・build の入力 (`m11_gen_ir2.sh`・`m11_build.sh` 等) は変わっていない。gen・build は `5940f848` で実施した。
- 素材: `fl-win64` を [WIN64] (`FL_WIN64_DIR`) に展開。`work-m11`・`work-liftdiff` は tar の中身が `tools/...` 相対なので、リポジトリ直下に展開した (`tools/m11/work/`・`tools/liftdiff/work/`、gitignore)。`toolchain-emsdk` は展開していない (下の emcc の理由)。
- emcc: 基準の `m11_build.sh` は [EMSDK] の `emsdk_env.sh` を自分で source し、`store_watch_1783.sh` は `EMSDK_ENV` (同じ [EMSDK]) を source する。両方とも emcc **6.0.12** (`emcc --version`)。素材 `toolchain-emsdk` の `emscripten-version.txt` も 6.0.12 で、版は一致する。
- `m11_gen_ir2.sh` rc 0 (41.7 s、`boot_final.ll` 490,735 行)、`m11_build.sh` rc 0 (24.0 s、`wasm-ld signature mismatch: 0, undefined symbol: 0`)。

### 8.2 計装なし (基準)

- `SV_SLOT=0x1ac308 node trap_triage/survey_units.mjs` (32377077): stdout は `SLOT_BOOT 0x1ac308 0xf960`、`SURVEY_UNITS {"ok":872,"miss":47,"other":1,"halt0":7,"oob":14,"noproc":1}` (合計 942)。rc 0、10.4 s。

### 8.3 停止の切り分け (計装版)

| 条件 | 結果 (実測) | 再測 |
|---|---|---|
| 旧 script (全 store 計装、`ov.o` の `M11_FIX_682=0`) | unit 145 の開始行の直後で止まる。timeout 240 s で rc 124 | 前 run の実測 (`796507e9` 以前) |
| `SV_TRACE_AT=145` (20 s) | unit 145 の icall 行は入口 `0x25c9f0` の 1 件のみ。以後の icall なし | 前 run の実測 |
| 全 store 計装、`M11_FIX_682=1` (base と同じ ov) | unit 106 で止まる。timeout 240 s で rc 124 | 前 run の実測 |
| 上と同じ + 同一 site の呼出し回数上限 5,000,000 で該当 unit を trap (`watch_addr_2769.c`) | 942 unit 完走 (rc 0)。打ち切りは 3 unit: 106 (site 11832)・145 (site 11833)・830 (site 42115) | **run5 で再現** (§8.3.1) |
| 全 store 計装、hook の本体を空にする (`m11_sw` は何もしない) | timeout 200 s で rc 124 (**挿入そのものが停止の原因**) | 前 run の実測 |
| 空 hook + スタック slot への直接 store を計装から外す (`ALLOCA_SKIP=1`) | 942 unit 完走 (rc 0)。kind は `{"ok":870,"miss":47,"other":1,"halt0":8,"oob":15,"noproc":1}` | 本 hook の run4 が同じ kind (§8.4) |

- 停止点の正体: 打ち切りで得た 3 site は、いずれも同じ関数内で alloca された名前への store。site 11832・11833 は `function_407800` の IR 106693・106694 (store 先 `%r14.05.reg2mem`・`%r13.04.reg2mem`、alloca は IR 106645・106644)。site 42115 は `function_bf86f0` の IR 381155 (store 先 `%stack_var_-324.0.reg2mem`、alloca は IR 380952)。`function_407800` は decommit の loop で、歩幅が `%1 = xor i64 0, 0` (定数 0) のため、`VirtualFree` が成功を返す間は終わらない形になっている。計装なしでは抜けるのに、計装版では抜けない。
- 計装版の unit 145 は「遅い」のではなく「回り続ける」: 旧 script の進捗行は unit 0〜145 の開始が 0.15 s 以内に並ぶ (`unit 145` で止まる)。§7.5 の「20 分」は timeout までの時間であり、計装 store の遅さではない。
- 機構: スタック slot (`alloca`) の番地を `ptrtoint` で外に出すことが効くと見ている。`function_407800` の `VirtualFree` の結果がなぜ変わるかは**未確定**。
- 計装 site は 54,041 → 15,028 (39,013 は alloca の名前への store。`watch_store_682.py` の `ALLOCA_SKIP=1` で外す)。**スタック配置は未確認**: `0x1ac308` はイメージ内の番地 (SizeOfImage 0x18c0000 未満) なので shadow stack には届かないと見込んでいるが、これは前提であり実測していない (実行時の stack 範囲は未測定)。配置が重なれば、ALLOCA_SKIP=1 の 0 件は取りこぼしを含む。

### 8.3.1 再現 (`watch_addr_2769.c` の site 上限)

```sh
export FL_WIN64_DIR=<fl-win64 の展開先> EMSDK_ENV=<emsdk_env.sh のパス>   # [WIN64]・[EMSDK] (docs/REFERENCES.md §4)
cd tools/m11
bash m11_gen_ir2.sh && bash m11_build.sh
M11_WATCH_SRC=trap_triage/watch_addr_2769.c ALLOCA_SKIP=0 timeout 300 bash trap_triage/store_watch_1783.sh run5
grep -a "sw-limit" work/probe1783/run5.aw
```

- `ALLOCA_SKIP=0` で全 store (54,041 site) を計装する。site 番号はこの設定の番号で、`ALLOCA_SKIP=1` では番号がずれる。
- `M11_SW_LIMIT` (既定 5,000,000) で site ごとの呼出し上限を変える。上限を超えた unit だけ trap し、survey は次の unit へ進む。
- 期待される出力 (run5 の実測): `unit 106 [sw-limit] site=11832 n=5000001`・`unit 145 [sw-limit] site=11833 n=5000001`・`unit 830 [sw-limit] site=42115 n=5000001` の 3 行。
- site → IR は `work/probe1783/sites.json` で引く (`"11832": {"fn": "function_407800", "line": 106693, ...}`)。

run5 の実測 (32377077): rc 0、42.0 s (build と restore を含む)。`instrumented stores: 54041`、`SURVEY_UNITS {"ok":865,"miss":47,"other":4,"halt0":7,"oob":15,"abort":3,"noproc":1}` (合計 942)、`[aw] hits: 0`、上の 3 行を確認。

### 8.4 全 942 unit の `[aw]` 採取 (run4・run5)

- run4 (32377077・既定の `ALLOCA_SKIP=1`・`watch_addr_1046.c`・`timeout 300`): rc 0、52.8 s。
  - `instrumented stores: 15028`。`SURVEY_UNITS {"ok":870,"miss":47,"other":1,"halt0":8,"oob":15,"noproc":1}` (942 unit 完走)。
  - `[aw] hits: 0` (`run4.aw` の `[aw] ` 行 0 件)。
- run5 (32377077・`ALLOCA_SKIP=0`・`watch_addr_2769.c`): `[aw]` 0 件。3 unit は site 上限で打ち切られ、その後の store は見ていない (§8.3.1)。
- 計装なし基準との kind 差分 (run4): 158 (`ok`→`oob`)・283 (`ok`→`halt0`)。原因は未確認。
- 判定の範囲: 0 件は「計装した store 命令 (run4 は 15,028 site・run5 は 54,041 site) の実行で、`[W, W+8)` (W = 0x1ac308) に重なる書込みが無い」まで。計装版の挙動が基準と 2 unit 違うので、基準実行への直接の結論ではない。
- **計装外の書込み経路 (rep 系 helper)**: `[aw]` は IR の `store` 命令だけを計装する。`work/boot_final3.ll` は `__asm_rep_movsq_memcpy` (28 件)・`__asm_rep_movsb_memcpy` (1 件)・`__asm_rep_stosq_memset` (6 件) を外部宣言で呼ぶ。その実装 (`work/m11_simd.c` の rep 系 helper。`m11_simd2.py` で生成し `emcc -c` で wasm にリンク) は `m11_sw` を呼ばない (`grep -c m11_sw work/m11_simd.c` = 0)。したがって `0x1ac308` が rep movs/stos 経由で書かれても 0 件のままになる。**rep 系 helper 経由の書込みは計装外** (helper への監視の追加は未実施)。
- 判定関数の確認 (前 run・native・`watch_addr_1046.c` を `cc` で直接コンパイルした `sw_selftest`): 0x1ac308・0x1ac30a・0x1ac30c (幅 4) は hit、0x1ac304 (幅 4)・0x1ac300 (幅 8) は非 hit。判定範囲は `[W, W+8)`。
- wasm 実機での陽性対照 (既知の書込み番地で hit が出ること) は**未実施**。

### 8.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計装で `function_407800` の `VirtualFree` 結果が変わる機構 (スタック slot の `ptrtoint` が効く理由) | スタック slot を計装から外す前提が検証のみ | 本 PR 本文の未解決表 (追跡のみ・子は起票しない) |
| スタック配置 (shadow stack の範囲) の実測。alloca 直接 store (`ALLOCA_SKIP=1` で外した 39,013 site) が `0x1ac308` に届かないことは未確認 | run4 の 0 件に取りこぼしがあるかが未確定。run5 の 0 件は 3 unit 打ち切りの範囲に限る | 本 PR 本文の未解決表 (追跡のみ) |
| rep 系 helper (`__asm_rep_movsq_memcpy` 等) 経由の書込みは計装外 | `[aw]` 0 件は store 命令の範囲に限る | 本 PR 本文の未解決表 (追跡のみ) |
| 計装版と基準の kind 差分 (158・283) | 0 件の結論は計装版の実行に限る | 本 PR 本文の未解決表 (追跡のみ) |
| wasm 実機での陽性対照 (既知の書込み番地で `[aw]` が出る確認) | 0 件が「書込みなし」か「検出漏れ」か未確定 | 本 PR 本文の未解決表 (追跡のみ) |
| 0x1ac308 の値 `0xf960` と静的 `0x40f960` の由来 (§7.6) | スロットの初期値の出所が未確定 | #2769 のクローズ後も §7.8 と同じく未解決 |
| native 側 `0x5ac308` の store 捕捉 | 両側の比較ができない | #2770 |
