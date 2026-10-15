# liftdiff LD-154 (#3350): batch 判定の再現性と timeout の記録

結論: 受入 2 (上限秒数と実測秒の記録) は達成。受入 3 (件数の記録) は達成。受入 1 は未達 (units は今回 1 関数、hybrid は関数単位で 2 件判定が変わった)。受入 1 は子 issue #3423 (LD-157) に移した。
§2〜§6 の実測値は測定 commit `38e057dce` (HEAD) のもの。コードは `9e702fe45` と同一で、`38e057dce` 以降の commit は REPORT・DOC_MAP だけを変えた。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 実装 commit | `acbf28748` (timing の記録) |
| 測定 commit (§2〜§6 の値を測った commit) | `38e057dce` (コードは `9e702fe45` と同一) |
| 測定後のコード差分 | `git diff --stat 38e057dce HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt tools/liftdiff/tests` = 出力なし (0 行。この REPORT を含む commit で確認) |
| 前回の測定 commit | `3427318f1` (前回の §2〜§6。値は git 履歴に残し、本付録からは外した)。`git diff --stat 3427318f1 38e057dce -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt` = 7 files, 152 行追加・12 行削除。内訳は §9 |
| 入力 | `targets/m11.json`・`--set sample:800`・`--shards 12`・`--nobuild` |
| units state | `--state auto` (`bootstate targets/m11.json --nobuild` で作成。`units_run=22/942`・`precondition ok=False` は既存の状態 (LD-42)) |
| hybrid state | `--state work/m11/boot_state_hybrid.json` (`bootstate targets/m11.json --mode hybrid --nobuild` で作成。`units_run=928/942`・`first_fail=830`・`precondition ok=True`) |
| ビルド | `gcc ... rt/ld_native.c` と `liftdiff.py build targets/m11.json` を HEAD で実行 (`[build] OK`) |
| 機械 | 4 コア。run は直列 (並列にしない) |
| 素材 | fl-win64・work-m11・work-liftdiff を `$ARTIFACTS_DIR` から展開 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)。toolchain-* は展開せず、runner に既にある `[EMSDK]`・`[RETDEC]` (agent-setup 展開済み。`docs/REFERENCES.md` §4) を使った |

上限 (batch 冒頭の `[batch] limits` 行に出る値):

- native: ITIMER_REAL 1.5 s (`rt/ld_native.c` の `{1, 500000}`。`tests/test_ld154_timing.py` が C 側の値と一致を検査)、Python 側の recv 上限 10.0 s
- wasm: vm timeout 1.000 s (`wasm_timeout_ms` 既定)、Python 側の recv 上限 10.0 s

## 2. 各 run の結果 (測定 commit `38e057dce`)

load は `/proc/loadavg` の 1 分値 (run 開始時 → 終了時)。所要は batch ログの `done` 行。

| run | state | 一致 / 不一致 / 実行不能 | timing 付き case (関数) | batch 所要 | load 開始 → 終了 |
|---|---|---|---|---|---|
| units r1 | units | 361 / 233 / 206 | 297 (73) | 109 s | 0.62 → 6.49 |
| units r2 | units | 360 / 234 / 206 | 292 (70) | 112 s | 5.97 → 6.80 |
| hybrid h1 | hybrid | 352 / 271 / 177 | 298 (71) | 237 s | 5.09 → 8.12 |
| hybrid h2 | hybrid | 352 / 271 / 177 | 305 (72) | 230 s | 7.47 → 8.53 |

- 件数は各 run の `関数数 800: 一致 … / 不一致 … / 実行不能 …` 行による。ログ: `work/m11/ld154_*.log` (gitignore、commit しない)。生 JSONL は `work/m11/ld154_*.jsonl`。
- 前回 (`3427318f1`) の件数 (units 360/233/207、hybrid 352/268/180) とは一致しない。差の原因は切り分けていない (測定 commit 間の差分は §9)。

## 3. 同一入力 2 回の関数単位の突合 (`tests/ld154_repeat.py`)

| 比較 | 件数の変化 | 関数単位の判定変化 | timing 付き case が差に含まれた関数 |
|---|---|---|---|
| units r1 vs r2 | あり (361/233/206 → 360/234/206) | 1 (`0x959a40`) | 0 |
| hybrid h1 vs h2 | なし (352/271/177 で一致) | 2 (`0x10348b0`・`0x959a40`) | 1 (`0x10348b0`) |

- units `0x959a40`: match → mismatch。p1・pall・qall が r1 `equal`、r2 `diff` (native ok / wasm ok)。timing なし。
- hybrid `0x10348b0`: mismatch → match。p0 は h1 `both_fault` (native segv / wasm trap)、h2 `hang` (native segv / wasm timeout、timing 付き)。p01・p1・pall は h1 `wasm_trap` → h2 `equal` で timing なし。
- hybrid `0x959a40`: match → mismatch。p1・pall・qall が h1 `equal`、h2 `diff`。timing なし。units でも同じ関数が揺れた。原因は未特定。

## 4. 遷移件数 (units → hybrid、`tests/ld42_transition.py` の changed)

| units | hybrid | 遷移件数 | match→mismatch | unexec→mismatch | mismatch→match | unexec→match |
|---|---|---|---|---|---|---|
| r1 | h1 | 68 | 26 | 25 | 13 | 4 |
| r1 | h2 | 69 | 27 | 24 | 13 | 5 |
| r2 | h1 | 69 | 26 | 25 | 14 | 4 |
| r2 | h2 | 68 | 26 | 24 | 13 | 5 |

- 前回 (`3427318f1`) の 67 / 68 は再現しなかった。今回は 68 / 69。同じ units に対して hybrid の run によって 1 件違う。
- 遷移は state の差も含むため、timeout 系の寄与の判定には使わない。

## 5. 受入条件の判定

| # | 受入条件 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 同じ入力を 2 回連続で実行したとき、遷移件数と判定が一致する | 未達 (子 #3423 へ移管) | units: 件数 361/233/206 → 360/234/206、判定 1 関数 (`0x959a40`)。hybrid: 件数 352/271/177 は一致、関数単位で 2 件 (`0x10348b0`・`0x959a40`)。遷移件数は 68 / 69 (§4) |
| 2 | hang / timeout の判定に使った上限秒数と実測秒を batch 出力に残す | 達成 | HEAD (`38e057dce`) の実測で確認 (§6): timeout 系の case に上限 (`limit_s`)・実測 `elapsed_s`・`cause` (`runner_timeout`) が付き、EOF・終了の case には上限を付けず `cause` (`eof`・`exited`) と実測秒が付く。`deadline` (応答待ちの期限切れ) は本測定では 0 件で、この経路は単体テスト `tests/test_ld154_timing.py` で確認した |
| 3 | units / hybrid の件数を `liftdiff_e2e.sh` [4/4] の基準として記録できる状態にする (値は変えない) | 達成 (記録のみ。スクリプトの値は未変更) | HEAD で測った件数: units 361/233/206 と 360/234/206、hybrid 352/271/177 (2 回)。§2 |

## 6. timing の実測 (測定 commit `38e057dce`)

timing の `elapsed_s` は、CASE 送信から応答行を読み終えるまでの Python 側の壁時計。wasm の elapsed は vm timeout の後の runner 側の後処理 (`sp_restore`・`putStr`・`_ld_w_case_end` = メモリ差分の収集と応答 JSON の組み立て) を含む。後処理の内訳は未計測。

主表 (cause 別、wasm 側。括弧内は elapsed の範囲):

| run | runner_timeout (上限 1.0 s) | deadline | eof | exited | skipped |
|---|---|---|---|---|---|
| units r1 | 280 (0.988〜1.831 s) | 0 | 3 (1.085〜1.949 s) | 0 | 14 |
| units r2 | 275 (1.003〜1.993 s) | 0 | 3 (1.055〜1.196 s) | 0 | 14 |
| hybrid h1 | 271 (1.014〜2.092 s) | 0 | 3 (1.151〜3.954 s) | 0 | 24 |
| hybrid h2 | 278 (1.014〜2.045 s) | 0 | 2 (1.120〜3.794 s) | 1 (2.183 s) | 24 |

native 側 (cause 別。括弧内は elapsed の範囲):

| run | runner_timeout (上限 1.5 s) | deadline | eof / exited | ok | segv |
|---|---|---|---|---|---|
| units r1 | 14 (1.500〜1.698 s) | 0 | 0 | 24 | 259 |
| units r2 | 14 (1.502〜1.641 s) | 0 | 0 | 24 | 254 |
| hybrid h1 | 24 (1.532〜1.797 s) | 0 | 0 | 38 | 236 |
| hybrid h2 | 24 (1.525〜1.818 s) | 0 | 0 | 38 | 243 |

補助 (status 別。`native_status`・`wasm_status` の値そのもの): wasm の status は timeout 280 / 275 / 271 / 278、crash 3 / 3 / 3 / 3 (うち exited 1 は h2)、hang 0、skipped 14 / 14 / 24 / 24。native の timeout は 14 / 14 / 24 / 24。wasm が応答しない case の status (hang か crash) は、プロセスの終了を見るタイミングで揺れ得る (前回の検収で模擬 runner により確認)。そのため主表は cause にした。

- skipped は、native が timeout したため wasm を実行しなかった case (`elapsed_s` = null)。件数は native timeout と一致する (14 / 14 / 24 / 24)。timing の wasm.status は `skipped` で、`tests/ld154_repeat.py` は wasm hang と別に数える。
- native timeout の最小は 1.500 s、wasm timeout の最大は 2.092 s (後処理を含む壁時計)。wasm timeout の最小 0.988 s (units r1) は上限 1.000 s を 12 ms 下回る。計時の起点の差と推定するが、未確認。判定 (outcome) は timeout のまま。
- 前回 (`3427318f1`) の wasm hang 3 件 (0.918 s・1.236 s・3.471 s) の経路は、本測定で置き換えた。本測定では wasm hang は 0 件で、応答なしの wasm case は eof 3 件 (units r1・r2・hybrid h1) と eof 2 件 + exited 1 件 (hybrid h2) だった。前回の JSON には cause が無く、case 単位の対応は取れない。
- 応答待ちの期限切れ (`deadline`) は本測定で 0 件。上限 10 s の経路は単体テストで確認した (`recv_limit_s` は `deadline` の case にだけ付く)。

### 予備測定 (chunk 16、`acbf28748` 時点) を棄却した理由

測定 1 回目は既定 chunk 16 で行った。結果は units 360/233/207・361/232/207、hybrid 352/268/180 ×2 で、件数は今回と同程度だった (作業ディレクトリに残し、本付録の値には使わない)。ただし native timeout の実測が 0.868〜2.163 s と上限 1.5 s を下回った。原因は、先行 case の応答がパイプに溜まり、その待ち時間が隣の case の応答間隔に計上されたこと。このため `run_cases` の既定 chunk を 1 に変更し (`3427318f1`)、全 run を測り直した。送信順・判定ロジック・timeout の既定値は変えていない。

chunk 16 の batch 所要 (秒) は予備測定で記録していない。§2 の所要は chunk 1 の値で、chunk 16 との速度比較はできない。chunk 1 にしたのは timeout の実測を正しく記録するためで、速度の主張はしない。

## 7. 検証

- HEAD (`38e057dce`) で、単体: `python3 tools/liftdiff/tests/test_ld154_timing.py` 9 件 OK、`python3 tools/liftdiff/tests/test_compare_ld11.py` 23 件 OK。
- e2e の手順 (`liftdiff_e2e.sh`) のうち、[1/4] (gcc と `liftdiff.py build targets/m11.json`: `[build] OK`)、[3/4] の bootstate (units: `units_run=22/942`、hybrid: `units_run=928/942`・`precondition ok=True`)、[4/4] の batch を §2 の 4 回で実行した。[0/4] の `test_compare_ld11.py` は上の単体と同じ。[2/4] (OTT 旧 chain) と [3/4] の `check_unit18`・[3b] の `check_initunits` は対象外 (素材 work-m6-ott・analysis-ott-binaries を取得していない)。
- 突合: `tests/ld154_repeat.py` (units r1/r2、hybrid h1/h2) と `tests/ld42_transition.py` (4 組)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| units・hybrid の関数単位の判定が 2 回の間で変わる (units: `0x959a40`。hybrid: `0x10348b0` の p0 は timeout 系が関与、p01・p1・pall は timing なし。`0x959a40` は timing なし、原因未特定) | 受入 1 未達。件数は units で 1 件差 (361 / 360)、hybrid は一致 (352 / 352) だが、個別判定は一致しない | #3423 (LD-157) |
| units state の precondition が ok=False (`units_run=22/942`) | 既存の状態 (LD-42 で記録済み)。本 PR では変えていない | #1464 (親) |
| units / hybrid のどちらを `liftdiff_e2e.sh` [4/4] の基準にするか | 本付録は件数を記録するのみ。基準値は変えていない | #1464 (親) |

## 9. 測定 commit からの差分 (前回測定 `3427318f1` 以降)

前回の測定 commit `3427318f1` 以降に次の差分が入った。§2〜§6 の値はこの差分を含む `38e057dce` で測った値。

- `35e49a1e0`: origin/main (`f44264ebe`) を取り込んだ (DOC_MAP の衝突のみ解消)。runner 側に LD-153 (仮 proc の thunk の敷設)・LD-126 (wasm の RESET)・LD-129 (書込み監視) の差分が入った。
- `9e702fe45`: `ldlib/runners.py` (応答待ちの終了理由 `_cause`)・`ldlib/session.py` (`side_timing`、skipped の status、refine_timing の cause)・`tests/ld154_repeat.py` (cause 別の集計) を変えた。`tests/test_ld154_timing.py` を追加した。判定ロジック (`classify.py`・`compare.py`) と timeout の既定値は変えていない。
- `65e8cd56c`・`c67ed2065`・`38e057dce`: REPORT・DOC_MAP だけを変えた (コードは変えていない)。
- `git diff --stat 3427318f1 38e057dce -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt` = 7 files, 152 行追加・12 行削除。
