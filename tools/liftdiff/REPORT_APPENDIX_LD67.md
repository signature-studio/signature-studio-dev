# liftdiff REPORT 付録: LD-67 (#1906) ld_blk 計装が OTT 旧 chain の vm0 戻り値を変える件の切り分けと修正

親 issue #1854 (LD-64)。前提は `REPORT_APPENDIX_LD64.md` §4。

## 結論

- 受入条件 1 (計装 build と既定 build で 6 関数 × vm0/u16 の outcome と ret が一致) は **達成** (12 case 差 0・3 回再現)。
- 受入条件 2 (原因の切り分け) は **達成**。原因は `ld_blk` の **call 命令の挿入そのもの**。
  記録処理 (`blk=1`)・static 配置・`ld_blk` の中身 (空定義でも同じ差) のいずれでもない。
  stack fill (00/a5/ff) にも依存しない。LD-64 §4 の推定「未初期化 shadow stack」は**否定**された。
- 受入条件 3 (計装方式の修正) は **達成**。call を `ld_blk_arr` への volatile store に置き換えた。
  この方式では block 列を失わずに記録でき、既定 build と差 0。
- 受入条件 4 (測定 commit と差分を添える) は §5 に記載。
- LD-64 の block trace は、本 commit 以降は判定に使ってよい (計装版の戻り値が既定版と一致)。
  ただし LD-64 §3 の block 対応 (native との対応付け) は別問題で、本 PR では未検証のまま。

## 1. 測定条件

- 測定 commit: `0e5b184c` (`fix(liftdiff): record IR block trace by store, not call`。コード差分の最終 commit)。
- 測定 runner: 4 vCPU・メモリ 15 GiB。load average (測定時) 0.19〜0.38 (`/proc/loadavg`・`uptime`)。
- 素材: `work-liftdiff`・`work-m6-ott`・`work-liftlib`・`analysis-ott-binaries` (`ANALYSIS_DIR=$HOME/analysis`)・`plugins-ott`・`toolchain-emsdk` (emcc 6.0.12)。`fl-win64` は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` に展開。
- build: `build_wasm.py targets/ott_old.json --force` と `targets/ott_old_blk.json --force` (ともに rc=0・sig_mismatch 0・undefined 0)。
- 比較コマンド: `liftdiff.py run targets/<t>.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --json ...`
  続けて `python3 results/ld67/compare_blk.py <def.json> <blk.json>` (case 単位で outcome・diffs・wasm_status・wasm の rax/x0 を比べる)。
- 実測所要 (3 回・各 run の wall clock): 既定 5545〜5554 ms・計装 5547〜5558 ms。3 回とも load 0.2 前後。

## 2. 切り分け

| 試験 | 結果 (vm0 の wasm_rax。既定 `0x0`/`0x1801c5e84`) |
|---|---|
| 既定 build (`ott_old`) | `1c5e84`=`0x0`・`1c621c`=`0x1801c5e84` |
| 計装版・call 方式 (LD-64 の状態) | `1c5e84`=`0x1801c5eb8`・`1c621c`=`0x1801c5eb8` (**差あり**) |
| stkfill 00/a5/ff で計装版 call 方式 | 3 値とも `0x1801c5eb8` (stack fill に依存しない) |
| `ld_blk` を空定義 (呼出しは残す) | `0x1801c5eb8` のまま (**記録処理の中身ではなく呼出しが原因**) |
| call → `store @ld_blk_last` (1 変数) | 既定と一致 (`0x0`・`0x1801c5e84`) |
| call → `ld_blk_arr` への volatile store (採用) | 既定と一致・block 列も記録される |

差の値 `0x1801c5eb8` は、記録された block の VA (IR の `dec_label_pc_1801c5eb8`)。call の引数が
`rax` の値として戻り値に出ている。呼出しの挿入で IR の -O0 codegen が変わり、`rax` の扱いが変わったと読める。
(この codegen の詳細な機序は本 run では未確認。判定に必要な範囲は上の試験で閉じた。)

## 3. 修正

| 変更 | 内容 |
|---|---|
| `ldlib/irtool.py` | `blocks=True` のとき `dec_label_pc_<VA>:` の直後に `ld_blk_n` を読み `ld_blk_arr[n & 65535]` へ `volatile` store し `ld_blk_n` を増やす。`call @ld_blk` は使わない。既定 (`blocks=False`) は変更なし |
| `rt/ld_wasm.c` | `ld_blk_n`・`ld_blk_arr[65536]` (volatile) を定義。`ld_blk_sync()` が `ld_w_case_end` の先頭で `ld_blk_arr` を `ld_blk_rec` へ移し、`blk_over` を加算する。`ld_blk_on` でない case は記録しない |

上限超過 (1 case で 65536 block 超) は `blk_over` で検知する。マスクで古い要素が上書きされるため、超過時の block 列は末尾 65536 件になる。今回の最大は 304 block で上限に達していない。

## 4. ネガティブコントロール

- 比較スクリプトの検出力: 旧 call 方式の結果 (`work/ld67/def.json` vs `blk.json`) を `compare_blk.py` に通すと、
  **DIFF 2 件** (`1c5e84` vm0・`1c621c` vm0) を検出し rc=1。差 0 の判定が偽陰性でないことを確認した。
- 計装が効いていること: 修正後の計装版の `blk` 件数は 27・4・287・6・42・43・304・10 (case ごと)。
  計装していない関数 (`1ab1d0`・`1ab258`) は 0 件。記録は block 入口にだけ効く。

## 5. 測定 commit と差分

- 測定 commit: `0e5b184c`。
- `git diff 0e5b184c HEAD -- tools/liftdiff/rt tools/liftdiff/ldlib` は **0 件** (本 PR で `0e5b184c` より後に変えるのは REPORT のみ)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| LD-64 §3 の block ↔ native 命令の対応付け (`block_coverage.py` の入力・出力を本 PR で commit していない) | block 列を native の `1c0b6f`・`1c0b82` と結び付けられない。LD-64 §3 は未検証のまま | 本 PR の範囲外。LD-64 の残り (子 issue) |
| 残り 4 関数の native 対応 (LD-64 受入条件 3) | 分岐点の特定は未了 | 同上 |
| call 挿入で codegen が変わる機序 (IR の `rax` の扱い) の詳細 | 機序の説明は推定。判定には影響しない (store 方式で差 0 を確認済み) | 必要なら別 issue (低優先) |
