# liftdiff LD-154 (#3350): batch 判定の再現性と timeout の記録

結論: 受入 2 (上限秒数と実測秒の記録) は達成。受入 3 (件数の記録) は達成。受入 1 は未達 (hybrid で関数単位の判定が 2 件変わった)。受入 1 は子 issue #3423 (LD-157) に移した。units の 2 回一致は達成。
§2〜§6 の実測値は測定 commit `3427318f1` のもの。HEAD (`9e702fe45`) での再測定は未実施 (§8・§9)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 実装 commit | `acbf28748` (timing の記録) |
| 測定 commit (§2〜§6 の値を測った最後の commit) | `3427318f1` (既定 chunk を 1 に変更) |
| 測定後のコード差分 | `git diff --stat 3427318f1 HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt` = 7 files, 152 行追加・12 行削除 (差分 0 行ではない。内訳は §9) |
| 入力 | `targets/m11.json`・`--set sample:800`・`--shards 12`・`--nobuild` |
| units state | `--state auto` (`work/m11/boot_state.json`、`bootstate` の units モード) |
| hybrid state | `--state work/m11/boot_state_hybrid.json` (`bootstate --mode hybrid`) |
| 機械 | 4 コア・メモリ 15 GB。run は直列 (並列にしない) |
| 素材 | fl-win64・toolchain-emsdk・work-m11・work-liftdiff を展開 (`docs/WORKFLOW.md` §11) |

上限 (batch 冒頭の `[batch] limits` 行に出る値):

- native: ITIMER_REAL 1.5 s (`rt/ld_native.c` の `{1, 500000}`。`tests/test_ld154_timing.py` が C 側の値と一致を検査)、Python 側の recv 上限 10.0 s
- wasm: vm timeout 1.000 s (`wasm_timeout_ms` 既定)、Python 側の recv 上限 10.0 s

## 2. 各 run の結果 (測定 commit `3427318f1`)

load は `/proc/loadavg` の 1 分値 (run 開始時 → 終了時)。

| run | state | 一致 / 不一致 / 実行不能 | timing 付き case (関数) | batch 所要 | load 開始 → 終了 |
|---|---|---|---|---|---|
| units r1 | units | 360 / 233 / 207 | 288 (71) | 103 s | 1.13 → 5.03 |
| units r2 | units | 360 / 233 / 207 | 290 (70) | 104 s | 5.03 → 5.79 |
| hybrid h1 | hybrid | 352 / 268 / 180 | 296 (70) | 208 s | 5.33 → 8.45 |
| hybrid h2 | hybrid | 352 / 268 / 180 | 303 (71) | 206 s | 7.77 → 9.45 |

- 件数は各 run の `[batch] ... 関数数 800` 行による。ログ: `work/m11/ld154_*.log` (gitignore、commit しない)。
- 生 JSONL は `work/m11/ld154_*.jsonl` (gitignore)。`timing` の JSON を足した分は約 54〜57 KB (case 288〜303 件)。

## 3. 同一入力 2 回の関数単位の突合 (`tests/ld154_repeat.py`)

| 比較 | 件数の変化 | 関数単位の判定変化 | timing 付き case が差に含まれた関数 |
|---|---|---|---|
| units r1 vs r2 | なし | 0 | 0 |
| hybrid h1 vs h2 | なし | 2 | 1 (0x10348b0) |

- hybrid の 2 件 (判定変化):
  - `0x10348b0`: mismatch → match。h1 は p01・p1・pall が `wasm_trap`、h2 は `equal`。p0 は h1 が `both_fault` (native segv / wasm trap)、h2 が `hang` (native segv / wasm timeout、timing 付き)。timeout 系の case は p0 にだけ関与した。残りの p01・p1・pall の `wasm_trap` ↔ `equal` は timing なしで起きた (原因は未特定。wasm 側の持ち越し状態の候補)。
  - `0x959a40`: match → mismatch。p1・pall・qall が h1 `equal`、h2 `diff` (native ok / wasm ok)。timing 付き case はなく、timeout 系は関与しなかった。同じ関数は units r1 → r2 でも 1 件の揺れとして前回 (chunk 16 の予備測定) も出ており、原因は未特定。

## 4. 遷移件数 (units → hybrid、issue の 67 / 68 の再現)

| units | hybrid | 遷移件数 |
|---|---|---|
| r1 | h1 | 68 |
| r1 | h2 | 67 |
| r2 | h1 | 68 |
| r2 | h2 | 67 |

- 同じ入力を 2 回ずつ実行しても、遷移件数は 67 と 68 の間で変わった。hybrid 側の揺れ (h1 と h2 の 2 件) が遷移件数の差の源である。
- units → hybrid の 68 件のうち、差の case に timing が付いていた関数は 5 件 (r1 → h1 の参考値)。遷移は state の差も含むため、timeout 系の寄与の判定には使わない。

## 5. 受入条件の判定

| # | 受入条件 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 同じ入力を 2 回連続で実行したとき、遷移件数と判定が一致する | 未達 (子 #3423 へ移管) | units は 2 回とも件数・判定が一致 (変化 0)。hybrid は件数 352/268/180 が一致するが関数単位で 2 件変化 |
| 2 | hang / timeout の判定に使った上限秒数と実測秒を batch 出力に残す | 達成 | 各 timing 付き case に `elapsed_s` と、判定を決めた上限 (`limit_s` または `recv_limit_s`)・`cause` を記録 (`9e702fe45` で規則を整理。§6)。batch 冒頭に `[batch] limits` 行 |
| 3 | units / hybrid の件数を `liftdiff_e2e.sh` [4/4] の基準として記録できる状態にする (値は変えない) | 達成 (本付録に記録、スクリプトの値は未変更) | units 360/233/207 (2 回)、hybrid 352/268/180 (2 回)。関数単位の変化は §3 |

## 6. timing の実測 (測定 commit `3427318f1`)

timing の `elapsed_s` は、直前の応答 (1 件ずつ送るため送信時刻) から応答を読むまでの Python 側の壁時計。
wasm timeout の elapsed は、vm timeout (1.000 s) の後の runner 側の後処理 (`sp_restore`・`putStr`・`_ld_w_case_end` = メモリ差分の収集と応答 JSON の組み立て) を含む。後処理の内訳は未計測 (レビュー m2)。

| run | native timeout (limit 1.5 s) | wasm timeout (limit 1.0 s) | wasm crash | wasm hang (実測) | wasm hang (skipped) |
|---|---|---|---|---|---|
| units r1 | 14 (1.501〜2.004 s) | 270 (1.000〜2.003 s) | 3 (1.020〜1.125 s) | 1 (0.918 s) | 14 |
| units r2 | 14 (1.501〜2.000 s) | 272 (1.002〜1.728 s) | 4 (0.769〜2.131 s) | 0 | 14 |
| hybrid h1 | 24 (1.518〜1.813 s) | 268 (1.012〜2.685 s) | 4 (1.093〜3.057 s) | 0 | 24 |
| hybrid h2 | 24 (1.521〜1.835 s) | 275 (1.002〜2.949 s) | 2 (1.095〜1.332 s) | 2 (1.236〜3.471 s) | 24 |

- 「skipped」は native が timeout したため wasm を実行しなかった case (`elapsed_s` = null)。3427318f1 の JSON では wasm の status が `hang` (detail `skipped (native timeout)`) で、wasm hang と区別できない。`9e702fe45` 以降は timing の wasm.status が `skipped` になり、`tests/ld154_repeat.py` は wasm hang と別に数える (§7)。
- native timeout の最小実測は 1.501 s、wasm timeout の最小は 1.000 s で、いずれも上限と整合する。wasm timeout の最大 2.949 s は上限 1.0 s を超えるが、§6 冒頭の後処理を含む壁時計である。
- wasm hang の実測 0.918 s (units r1) と 1.236 s・3.471 s (hybrid h2 の 2 件) は、recv 上限 10 s より前に `_recv` が None を返した経路と読める。その経路は EOF (stdout が閉じた) かプロセス終了のどちらか。
  - この case の判定根拠は上限ではない。`limit_s` 1.0 / `recv_limit_s` 10.0 は 3427318f1 の JSON に入っていたが、判定 (outcome は hang のまま) を決めたのは終了の経路。
  - 3427318f1 の JSON は終了理由 (cause) を持たないため、EOF かプロセス終了かは未確認。
  - `9e702fe45` 以降は timing に `cause` を付ける (`eof` / `exited` / `deadline` / `runner_timeout`)。EOF・終了の case には上限を付けず (`ldlib/session.py` の `side_timing`)、応答待ちの期限切れ (`deadline`) の case だけ `recv_limit_s` を付ける。status は変えていない。

### 予備測定 (chunk 16、`acbf28748` 時点) を棄却した理由

測定 1 回目は既定 chunk 16 で行った。結果は units 360/233/207・361/232/207、hybrid 352/268/180 ×2 で、件数は今回と同程度だった (作業ディレクトリに残し、本付録の値には使わない)。ただし native timeout の実測が 0.868〜2.163 s と上限 1.5 s を下回った。原因は、先行 case の応答がパイプに溜まり、その待ち時間が隣の case の応答間隔に計上されたこと。このため `run_cases` の既定 chunk を 1 に変更し (`3427318f1`)、全 run を測り直した。送信順・判定ロジック・timeout の既定値は変えていない。

chunk 16 の batch 所要 (秒) は予備測定で記録していない。§2 の所要 103 s・208 s は chunk 1 の値で、chunk 16 との速度比較はできない。chunk 1 にしたのは timeout の実測を正しく記録するためで、速度の主張はしない (レビュー m3)。

## 7. 検証

- 測定 commit `3427318f1` の時点: `python3 -m py_compile` (ldlib/runners.py・ldlib/session.py・liftdiff.py)、`Runner.run_cases` の固定応答の確認 (hang の `_elapsed_s` = 1.001)、`Session._mark_timing` の 3 パターン、`liftdiff.py run --fn 0x959a40,0x4133f0` (通常の case に timing が付かない)、`liftdiff_e2e.sh` の手順の手動実行のうち [0/4]・[1/4]・[3/4]・[4/4] (§2)。[2/4] (OTT)・[3/4] の `check_unit18`・[3b] の `check_initunits` は今回の対象外。
- `9e702fe45` の時点 (単体のみ。e2e は未実施):
  - `python3 tests/test_ld154_timing.py`: 9 件 OK。NATIVE_ITIMER_S と `rt/ld_native.c` の `{1, 500000}` の一致、`side_timing` の上限の付け方 (runner timeout → limit_s、deadline → recv_limit_s、EOF・終了・skipped → 上限なし)、`Runner.run_cases` の cause (終了する runner → eof/exited、応答なし → deadline)、skipped の wasm が wasm hang と別に集計されること。
  - `python3 tests/test_compare_ld11.py`: 23 件 OK。
  - `py_compile` OK。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| hybrid の関数単位の判定が 2 回の間で変わる (`0x10348b0` の p0 は timeout 系が関与、p01・p1・pall は timing なし) | 受入 1 未達。件数 352/268/180 は一致しても個別判定は一致しない | #3423 (LD-157) |
| `0x959a40` の判定変化 (timing 無関係、units でも揺れた実績あり) | 原因未特定。wasm / native のどちらの状態かは未確認 | #3423 (LD-157) |
| units / hybrid のどちらを `liftdiff_e2e.sh` [4/4] の基準にするか | 本付録は件数を記録するのみ。基準値は変えていない | #1464 (親) |
| units state の precondition が ok=False (`units_run=22/942`) | 既存の状態 (LD-42 で記録済み)。本 PR では変えていない | #1464 (親) |
| HEAD (`9e702fe45`) での再測定 (units 2 回・hybrid 2 回、bootstate の再生成を含む) が未実施。§2〜§6 の値は `3427318f1` のもの。main 取り込みの rt/ 差分 (LD-153・LD-126・LD-129) と 9e702fe45 の変更が入っており、hybrid の件数は LD-153 で変わりうる | 測定値が HEAD と一致する保証がない | 本 PR の次の検収 run (未起票。本 run は時間切れで未実施) |
| wasm hang 3 件の経路 (EOF か プロセス終了か) が未確認 (3427318f1 の JSON に cause が無い) | §6 の経路は推定の域を出ない | 上と同じ再測定で `cause` を確認 |

## 9. 測定 commit からの差分 (main 取り込み + 9e702fe45)

測定 commit `3427318f1` 以降に次の差分が入った。§1〜§6 の値はこの差分の前のコードで測った値で、HEAD の値ではない。

- `35e49a1e0`: origin/main (`f44264ebe`) を取り込んだ (DOC_MAP の衝突のみ解消)。runner 側に LD-153 (仮 proc の thunk の敷設)・LD-126 (wasm の RESET)・LD-129 (書込み監視) の差分が入った。
- `9e702fe45`: `ldlib/runners.py` (応答待ちの終了理由 `_cause`)・`ldlib/session.py` (`side_timing`、skipped の status、refine_timing の cause)・`tests/ld154_repeat.py` (cause 別の集計) を変えた。`tests/test_ld154_timing.py` を追加した。判定ロジック (`classify.py`・`compare.py`) と timeout の既定値は変えていない。

```
git diff --stat 3427318f1 HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt
 tools/liftdiff/ldlib/build_wasm.py |  2 +-
 tools/liftdiff/ldlib/runners.py    | 10 +++++++-
 tools/liftdiff/ldlib/session.py    | 42 ++++++++++++++++++++++++------
 tools/liftdiff/rt/ld_core.h        |  7 +++++
 tools/liftdiff/rt/ld_native.c      | 52 ++++++++++++++++++++++++++++++++++++++
 tools/liftdiff/rt/ld_runner.mjs    |  7 ++++-
 tools/liftdiff/rt/ld_wasm.c        | 44 +++++++++++++++++++++++++++++++-
 7 files changed, 152 insertions(+), 12 deletions(-)
```

HEAD の再測定 (units 2 回・hybrid 2 回) は本 run では未実施。bootstate も再生成していない。次の検収 run で `liftdiff_e2e.sh` の手順に沿って行い、測定 commit をその HEAD に更新する。
