# 付録: liftdiff LD-183 (#3935): case 単位の揺れの切り分け (負荷 A・履歴 B)

親: #3881 (LD-182)。前段: `REPORT_APPENDIX_LD182.md`。本付録は `Refs #3935` (受入 3 は部分達成)。

## 結論

- **(A) 追加の CPU 競合 (busy 4 本) の有無では、件数・関数判定は動かなかった (本測定の範囲で)**: 「負荷 0」は無負荷ではない (batch 自体が 12 shard で 4 vCPU を飽和させ、開始時 1 分 load は 0.3〜10.0 とばらつく)。比較しているのは「batch だけ」と「batch + busy 4 本」の 2 条件で、無負荷ベースラインではない。また busy 4 本が run 中に実際に効いていたことは未測定 (run 後の `pgrep` 0 件のみ)。case 単位の差 (3〜10 case) は同じ条件の反復の差 (3〜8 case) と同程度。
- **(B) 履歴 (case の並び) は揺れを作る**: shards 12 のまま並びだけ shuffle すると、件数は 360/234/206 → 351〜354/240〜243/206 に動き、関数の判定が 14〜23 変わる。case 単位の差は 494〜683 件 (反復の差の約 100 倍)。
- **(C) V8 階層化とは切り分けていない**: 並びを変えると、同じ V8 process 内で先に走る case (履歴) と JIT の温まり (階層化) が同時に変わる。今回の run では B と C を分けられない。残りは未解決 (§6)。
- **前回 (LD-182) の units 230/210 は今回の commit では再現しなかった**: 並び sorted の units は 4 回とも 360/234/206 (LD-182 §8 の `ac7ca0637` と同じ値)。`34f1bb26e` と本測定 commit の間で `ldlib`・`rt` は 578 行変わっており、件数の差はその変更か runner の状態かのどちらか (未切り分け)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `2b2c59bea` (`origin/main` `4c9fbea16` の上に、harness `tests/ld183_order_load.py` だけを積んだ commit)。`git diff 4c9fbea16 2b2c59bea -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets` = 出力なし (0 行)。build・bootstate・batch は全てこの commit のコードで行った |
| 測定後のコード差分 | REPORT commit (本付録と DOC_MAP の 1 行) の直前 HEAD は `2b2c59bea`。`git diff 2b2c59bea HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets` = 出力なし (0 行)。判定ロジック・timeout 既定値は変えていない |
| 入力 | `targets/m11.json`・`--set sample:800`・`--shards 12`・`--nobuild` (build は `liftdiff.py build targets/m11.json`: `[build] OK`・`wasm_size` 4463245) |
| units state | `--state auto` (`work/m11/boot_state.json`) |
| hybrid state | `work/m11/boot_state_hybrid.json` (`bootstate --mode hybrid --nobuild`: `units_run=928/942`・`first_fail=830`・`precondition ok=True`。LD-182 と一致) |
| 素材 | `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)。`work-m11` → `tools/m11/work/`・`work-liftdiff` → `tools/liftdiff/work/` (展開)。`toolchain-emsdk` は `[EMSDK]` (`docs/REFERENCES.md` §4) を使用 |
| 機 | 4 vCPU・15 GiB。run は直列 |
| limits | native ITIMER 1.5 s (recv 10.0 s)・wasm vm 1.000 s (recv 10.0 s) (`[batch] limits` 行) |
| 追加負荷 (表の「負荷」列) | `0` = 追加の busy なし (batch だけ。ただし batch 自体が 12 shard で 4 vCPU を飽和させる)。`4` = `tests/ld183_order_load.py --load 4` が `sh -c 'while :; do :; done'` を 4 本追加起動。batch 後に `Popen.kill()` (PID 指定) で止め、`pgrep` で 0 件を確認。run 中の CPU 利用率は未記録 |
| 並び | `sorted` = `liftdiff.py` の既定 (`order_key` の昇順)。`shuffle:S` = 同じ 800 件を `random.Random(S).shuffle` (並びだけ変え、件数・内容は同じ) |

harness (`tests/ld183_order_load.py`) は `liftdiff.py` の `select_set`・`run_functions`・`make_record`・`cmd_summary` をそのまま使い、並びと負荷の指定だけを足す。`cmd_batch` と同じく 400 件ずつの chunk で実行する。判定 (`ldlib/classify.py`・`compare.py`) は変えていない。

## 2. 各 run の結果 (測定 commit `2b2c59bea`)

load は `/proc/loadavg` の 1 分値の開始時。harness は開始時だけを記録する (終了時は未取得)。所要は harness の `wall`。「負荷」列は追加の busy 本数であり、無負荷の run ではない (§1 の注)。負荷 0 の L0_r2 は開始 load 6.05、負荷 4 の L4_r1 は 1.51 で、開始 load は負荷の本数と対応しない。

| run | state | 並び | 負荷 | 一致 / 不一致 / 実行不能 | 所要 |
|---|---|---|---|---|---|
| units b1 | units | sorted | 0 | 360 / 234 / 206 | 98 s (liftdiff.py batch・load 0.32 → 4.48) |
| units L0_r2 | units | sorted | 0 | 360 / 234 / 206 | 98 s (load 開始 6.05) |
| units L4_r1 | units | sorted | 4 | 360 / 234 / 206 | 105 s (load 開始 1.51) |
| units L4_r2 | units | sorted | 4 | 360 / 234 / 206 | 105 s (load 開始 5.23) |
| units SH1_r1 | units | shuffle:1 | 0 | 354 / 240 / 206 | 98 s (load 開始 8.31) |
| units SH1_r2 | units | shuffle:1 | 0 | 354 / 240 / 206 | 98 s (load 開始 5.68) |
| units SH2_r1 | units | shuffle:2 | 0 | 351 / 243 / 206 | 106 s (load 開始 5.34) |
| units SH2_r2 | units | shuffle:2 | 0 | 351 / 243 / 206 | 104 s (load 開始 1.37) |
| hybrid HY_L0_r1 | hybrid | sorted | 0 | 352 / 271 / 177 | 174 s (load 開始 1.31) |
| hybrid HY_L0_r2 | hybrid | sorted | 0 | 352 / 271 / 177 | 166 s (load 開始 10.04) |
| hybrid HY_L4_r1 | hybrid | sorted | 4 | 352 / 271 / 177 | 218 s (load 開始 6.90) |
| hybrid HY_L4_r2 | hybrid | sorted | 4 | 352 / 271 / 177 | 217 s (load 開始 2.30) |

- 件数は全 run で、同じ並び・同じ state なら一致した (units sorted 4 回・units SH1 2 回・SH2 2 回・hybrid 4 回)。
- 負荷の開始 load は run ごとに大きく違う (0.3〜10.0)。1 分値は直前の run の影響を受けるため、負荷の強さの指標としては粗い。busy 4 本の追加で所要時間が hybrid 166〜174 s → 217〜218 s に延びたのは観測されたが、これは run 後の所要時間からの推定で、run 中の CPU 利用率は測っていない。

## 3. 突合 (case 単位・関数単位)

関数単位: `tests/ld154_repeat.py`。case 単位: `tests/ld182_casediff.py` (共通 8,812 case のうち `(outcome, native_status, wasm_status)` が異なる case 数 / 差のある関数数)。

| 比較 | 変えた条件 | case 差 | 差のある関数 | 関数判定変化 |
|---|---|---|---|---|
| units SH1_r1 vs SH1_r2 | 反復 (並びは同じ) | 3 | 3 | 0 |
| units SH2_r1 vs SH2_r2 | 反復 (並びは同じ) | 8 | 4 | 0 |
| units L4_r1 vs L4_r2 | 反復 (負荷 4) | 7 | 2 | 0 |
| units b1 vs L0_r2 | 反復 (負荷 0) | 5 | 3 | 0 |
| units b1 vs L4_r2 | 負荷 0 → 4 | 10 | 3 | 0 |
| units L0_r2 vs L4_r1 | 負荷 0 → 4 | 6 | 3 | 0 |
| hybrid HY_L0_r1 vs HY_L0_r2 | 反復 (負荷 0) | 3 | 3 | 0 |
| hybrid HY_L4_r1 vs HY_L4_r2 | 反復 (負荷 4) | 5 | 3 | 0 |
| hybrid HY_L0_r1 vs HY_L4_r1 | 負荷 0 → 4 | 5 | 3 | 0 |
| hybrid HY_L0_r2 vs HY_L4_r2 | 負荷 0 → 4 | 7 | 5 | 0 |
| **units L0_r2 vs SH1_r1** | **並び sorted → shuffle:1** | **494** | **112** | **14** |
| **units L0_r2 vs SH2_r1** | **並び sorted → shuffle:2** | **562** | **126** | **17** |
| **units SH1_r1 vs SH2_r1** | **並び shuffle:1 → shuffle:2** | **683** | **123** | **23** |

- busy 4 本の追加の比較 (5〜10 case) は反復の比較 (3〜8 case) と同じ範囲。関数判定の変化は 0。ただし「負荷 0」が無負荷ではないため、これは「追加の busy 競合の有無」の比較であり、無負荷との比較ではない。
- 並びの比較 (494〜683 case) は反復より 2 桁大きく、関数判定も 14〜23 変わる。
- 差の内訳 (wasm status 対) は、並びの比較で `ok ↔ trap`・`timeout ↔ trap`・`crash ↔ hang` などが混じる (`ld182_casediff.py` の出力全体は `work/m11/` の JSONL から再生成できる。JSONL は gitignore のため commit しない)。

関数判定の変化例 (並び sorted vs shuffle:1): `0xda09f0 pall` が `match → mismatch` (A=equal/ok/ok、B=diff/ok/ok)。sorted vs shuffle:2 では `0xf8e3f0 s` が `native_fault/segv/ok → both_fault/segv/trap`。

## 4. 切り分けの判定

| 候補 | 判定 | 根拠 |
|---|---|---|
| (A) 追加の CPU 競合 | **動かさなかった** (本測定の範囲・無負荷ベースラインではない) | busy 4 本を追加した run と追加なしの run で件数・関数判定が一致。case 差は反復と同程度 (§3)。batch 自体が 4 vCPU を飽和させるため、「負荷なし」の条件は作れていない。busy 4 本が run 中に効いていたことは未測定 |
| (B) runner 履歴 (case の並び) | **揺れを作る** | 並びだけ変えると件数・関数判定が動く。同じ並びの反復では関数判定が動かない |
| (C) V8 階層化 | **未切り分け** | 並びの変更は B と C を同時に動かす (同じ process 内の履歴と JIT の温まり)。今回の run では分けられない |
| (D) native ms の 50 ms 閾値 | 未検証 | 今回の run で `0x620cd0` は判定の対象に含めて確認していない (LD-182 §4 D) |

受入 3 の「揺れの起点と原因を説明する」は、A を外し B を起点とするところまで。B の中身 (V8 の温まりか、process 内の履歴か) は未切り分け。

## 5. 受入条件の判定

| # | 受入条件 (#3935) | 判定 | 根拠 |
|---|---|---|---|
| 1 | shards 12 のまま追加の busy 本数だけを変えた run を units・hybrid で各 2 回 | **達成** (ただし「負荷 0」は無負荷ではない) | units: 追加 0 の b1・L0_r2、追加 4 の L4_r1・L4_r2 (§2)。hybrid: HY_L0_r1・r2、HY_L4_r1・r2 (§2)。case 数は §3 |
| 2 | shards 12 のまま履歴 (並び) だけを変えた run を units で 2 回 | **達成** (2 組) | 並び shuffle:1 (r1・r2)、shuffle:2 (r1・r2) (§2)。反復の差 3・8 case |
| 3 | (A) 負荷・(B) 履歴・(C) V8 階層化のどれが揺れを作るかを REPORT に書く | **部分達成** | A は外れた、B は揺れを作る。C は未切り分け (§4) |
| 4 | 判定ロジックと timeout 既定値を変えない | **達成** | `git diff 4c9fbea16 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/liftdiff.py tools/liftdiff/targets` = 0 行 |
| 5 | 測定 commit と `git diff <測定 commit> HEAD -- tools/liftdiff` の出力を REPORT に書く | **達成** | §1 (測定 commit `2b2c59bea`・測定後の code 差分 0 行)・§8 (stat) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (C) V8 階層化と (B) process 内の履歴を分ける。例: 同じ並びで shards を 1 にして process 内の履歴だけを変える、または 1 case ごとに process を作り直す | 受入 3 の残り。揺れの修復方針が決まらない | #3935 (本 issue を open のまま次の run で行う。子は起票しない: 再測定のため) |
| 件数の基準: units sorted は今回 4 回とも 360/234/206、LD-182 の `34f1bb26e` は 360/230/210。`34f1bb26e` → `2b2c59bea` の `ldlib`・`rt` の変更 (578 行) か runner 状態かは未切り分け | 件数の前後比較は測定 commit を揃えてからでないと言えない | #3935 |
| (D) native ms の 50 ms 閾値 | 揺れの候補として未検証 | #3935 |
| 負荷の 1 分 load は開始時だけ記録 (終了時と負荷の強さは未取得)。run 中の CPU 利用率も未記録。busy 4 本が run 中に効いていたかは未測定 | 負荷の強さの指標として粗い。今回の A は「追加 busy 競合の有無では動かなかった」という条件での結果で、無負荷ベースラインの結論ではない | #3935 |

## 7. 検証

- 関数単位: `python3 tests/ld154_repeat.py <A> <B>` (§3 の表)。
- case 単位: `python3 tests/ld182_casediff.py <A> <B>` (§3 の表)。
- 再現コマンド (units sorted 負荷 4): `FL_WIN64_DIR=<fl-win64> python3 tests/ld183_order_load.py targets/m11.json --state auto --order sorted --load 4 --out work/m11/ld183_units_L4_r1.jsonl`。並びは `--order shuffle:S`。hybrid は `--state work/m11/boot_state_hybrid.json`。
- 負荷プロセスの停止は `Popen.kill()` (PID 指定)。run 後の `pgrep -f "while :; do :; done"` は 0 件。
- `tests/ld183_order_load.py` の py_compile 確認済み。harness の並び・負荷の指定は `liftdiff.py` と同じ関数を通るため、判定の経路は変えていない。

## 8. git diff (測定 commit → REPORT commit 直前)

`git diff --stat 2b2c59bea HEAD -- tools/liftdiff` の出力 (REPORT commit `58cd19c4c` 時点):

```
 tools/liftdiff/REPORT_APPENDIX_LD183.md | 117 ++++++++++++++++++++++++++++++++
 1 file changed, 117 insertions(+)
```

判定の経路 (`ldlib`・`rt`・`liftdiff.py`・`targets`) の差は 0 行。
