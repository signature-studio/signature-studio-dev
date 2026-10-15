# liftdiff LD-154 (#3350): batch 判定の再現性と timeout の記録

結論: 受入 2 (上限秒数と実測秒の記録) は達成。受入 3 (件数の記録) は達成。受入 1 は未達 (hybrid で関数単位の判定が 2 件変わった)。受入 1 は子 issue #3423 (LD-157) に移した。units の 2 回一致は達成。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 実装 commit | `acbf28748` (timing の記録) |
| 測定 commit (コードを変えた最後の commit) | `3427318f1` (既定 chunk を 1 に変更) |
| コード差分の確認 | `git diff 3427318f1 HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt` = 0 行 (REPORT の commit 後に確認) |
| 入力 | `targets/m11.json`・`--set sample:800`・`--shards 12`・`--nobuild` |
| units state | `--state auto` (`work/m11/boot_state.json`、`bootstate` の units モード) |
| hybrid state | `--state work/m11/boot_state_hybrid.json` (`bootstate --mode hybrid`) |
| 機械 | 4 コア・メモリ 15 GB。run は直列 (並列にしない) |
| 素材 | fl-win64・toolchain-emsdk・work-m11・work-liftdiff を展開 (`docs/WORKFLOW.md` §11) |

上限 (batch 冒頭の `[batch] limits` 行に出る値):

- native: ITIMER_REAL 1.5 s (`rt/ld_native.c` の `{1, 500000}`)、Python 側の recv 上限 10.0 s
- wasm: vm timeout 1.000 s (`wasm_timeout_ms` 既定)、Python 側の recv 上限 10.0 s

## 2. 各 run の結果

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
| 2 | hang / timeout の判定に使った上限秒数と実測秒を batch 出力に残す | 達成 | 各 timing 付き case に `limit_s`・`recv_limit_s`・`elapsed_s` を記録。batch 冒頭に `[batch] limits` 行 |
| 3 | units / hybrid の件数を `liftdiff_e2e.sh` [4/4] の基準として記録できる状態にする (値は変えない) | 達成 (本付録に記録、スクリプトの値は未変更) | units 360/233/207 (2 回)、hybrid 352/268/180 (2 回)。関数単位の変化は §3 |

## 6. timing の実測 (HEAD `3427318f1`)

timing の `elapsed_s` は、直前の応答 (1 件ずつ送るため送信時刻) から応答を読むまでの Python 側の壁時計。

| run | native timeout (limit 1.5 s) | wasm timeout (limit 1.0 s) | wasm crash | wasm hang (実測) | wasm hang (skipped) |
|---|---|---|---|---|---|
| units r1 | 14 (1.501〜2.004 s) | 270 (1.000〜2.003 s) | 3 (1.020〜1.125 s) | 1 (0.918 s) | 14 |
| units r2 | 14 (1.501〜2.000 s) | 272 (1.002〜1.728 s) | 4 (0.769〜2.131 s) | 0 | 14 |
| hybrid h1 | 24 (1.518〜1.813 s) | 268 (1.012〜2.685 s) | 4 (1.093〜3.057 s) | 0 | 24 |
| hybrid h2 | 24 (1.521〜1.835 s) | 275 (1.002〜2.949 s) | 2 (1.095〜1.332 s) | 2 (1.236〜3.471 s) | 24 |

- 「skipped」は native が timeout したため wasm を実行しなかった case (`elapsed_s` = null)。
- native timeout の最小実測は 1.501 s、wasm timeout の最小は 1.000 s で、いずれも上限と整合する。
- wasm hang の実測 0.918 s (units r1) と 1.236 s・3.471 s (hybrid h2 の 2 件) は、recv 上限 10 s より短い場合がある。`_recv` が EOF またはプロセス終了で None を返す経路で、待ちが早く終わったと読める。個別の原因は未確認。

### 予備測定 (chunk 16、`acbf28748` 時点) を棄却した理由

測定 1 回目は既定 chunk 16 で行った。結果は units 360/233/207・361/232/207、hybrid 352/268/180 ×2 で、件数は今回と同程度だった (作業ディレクトリに残し、本付録の値には使わない)。ただし native timeout の実測が 0.868〜2.163 s と上限 1.5 s を下回った。原因は、先行 case の応答がパイプに溜まり、その待ち時間が隣の case の応答間隔に計上されたこと。このため `run_cases` の既定 chunk を 1 に変更し (`3427318f1`)、全 run を HEAD で測り直した。送信順・判定ロジック・timeout の既定値は変えていない。

## 7. 検証

- `python3 -m py_compile` (ldlib/runners.py・ldlib/session.py・liftdiff.py)
- `Runner.run_cases`: 固定の応答スクリプトで、timeout 応答と hang (recv 上限 1.0 s) の経過秒を確認 (hang の `_elapsed_s` = 1.001)
- `Session._mark_timing`: ok・native timeout (wasm skipped)・wasm timeout の 3 パターンで `timing` の形を確認
- `liftdiff.py run --fn 0x959a40,0x4133f0` が通り、`timing` は通常の case に付かないことを確認
- `liftdiff_e2e.sh` の手順を手動で実行: [0/4] `tests/test_compare_ld11.py` (23 件 OK)、[1/4] (`gcc` で `work/ld_native`、`build targets/m11.json`)、[3/4] `bootstate` (units・hybrid)、[4/4] `batch` ×4 (§2)。[2/4] (OTT)・[3/4] の `check_unit18`・[3b] の `check_initunits` は今回の対象外

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| hybrid の関数単位の判定が 2 回の間で変わる (`0x10348b0` の p0 は timeout 系が関与、p01・p1・pall は timing なし) | 受入 1 未達。件数 352/268/180 は一致しても個別判定は一致しない | #3423 (LD-157) |
| `0x959a40` の判定変化 (timing 無関係、units でも揺れた実績あり) | 原因未特定。wasm / native のどちらの状態かは未確認 | #3423 (LD-157) |
| units / hybrid のどちらを `liftdiff_e2e.sh` [4/4] の基準にするか | 本付録は件数を記録するのみ。基準値は変えていない | #1464 (親) |
| units state の precondition が ok=False (`units_run=22/942`) | 既存の状態 (LD-42 で記録済み)。本 PR では変えていない | #1464 (親) |

## 9. main 取り込み後の差分 (測定 commit からの差)

測定 commit は `3427318f1` のまま。その後 `35e49a1e0` で origin/main (`f44264ebe`) を取り込んだ (DOC_MAP の衝突のみ解消)。取り込みで測定対象の runner 側に次の差分が入った:

```
git diff 3427318f1 HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt tools/liftdiff/targets tools/liftdiff/liftdiff_e2e.sh
 tools/liftdiff/ldlib/build_wasm.py |  2 +-
 tools/liftdiff/rt/ld_core.h        |  7 +++++
 tools/liftdiff/rt/ld_native.c      | 52 +++++++++++++++++++++++++++++++++++++++
 tools/liftdiff/rt/ld_runner.mjs    |  7 ++++-
 tools/liftdiff/rt/ld_wasm.c        | 44 +++++++++++++++++++++++++++++++-
 5 files changed, 109 insertions(+), 3 deletions(-)
```

よって §1〜§4 の件数は `3427318f1` の値であり、HEAD (`35e49a1e0`) の値ではない。HEAD での再測定は時間切れで未実施。再測定の担い手は検収 run (本付録の units/hybrid 各 2 回の手順を再実行する)。
