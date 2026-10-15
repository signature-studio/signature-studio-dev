# liftdiff LD-157 (#3423): hybrid batch の判定の再現性

親: #3350 (LD-154)。#3423 の本文は「#3350 で JSONL に `timing` を残した」と書くが、main では確認できなかった。#3350 は OPEN で、`timing` フィールドは出力されていない。切り分けは各 case の `native_status`・`wasm_status` で行った。

## 結論

- **測定 commit `94c133e12` (origin/main・HEAD)**: hybrid state で `--set sample:800` を 2 回連続で実行した。判定 (一致 352 / 不一致 259 / 実行不能 189) は 2 回とも同じで、関数単位の判定の変化は **0 件**。ケース単位では 1 関数 (0xa9ece0) の wasm 側 status が 1 case だけ揺れた (判定は変わらない)。
- **旧測定 `5ed1552bc` (LD-153 #3349 の修正前)**: 判定が 2 件変わった (0x10348b0 match→mismatch・0x959a40 mismatch→match)。ケース単位では 8 関数が変わった。全件を説明できた (§3・§4)。
- 旧測定の揺れの原因: 負荷で 1 秒の wasm vm timeout に掛かった case (own) と、同じ shard で先に実行された関数の wasm 状態の持ち越し (chain)。起点は shard 4 の 0x50abe0 `q0` で、r2 だけが timeout した。単独実行 (fresh・無負荷) では 0x50abe0 `q0` は timeout せず `both_fault` で返る。
- HEAD で揺れが消えたのは、LD-153 の thunk 敷設 (`ld_core.h`) で hybrid の native 側の結果が変わったため (352/258/190 → 352/259/189)。持ち越し機構への対処ではない。機構は #3384 (LD-155) の対象で残る。

## 1. 測定条件

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`)。`work-m11` と `work-liftdiff` は runner の既存展開を worktree から symlink。`toolchain-emsdk` は `/opt/emsdk`。
- build: `python3 liftdiff.py build targets/m11.json` (`wasm_size` 4459339 @ HEAD・4459215 @ 旧 `5ed1552bc`)。
- hybrid state: `python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild` → `units_run=928/942 first_fail=830`、`precondition ok=True` (LD-42 と一致)。
- batch: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state work/m11/boot_state_hybrid.json --out work/m11/batch_<名>.jsonl` を 2 回。
- 機: 4 vCPU。1 分 load は HEAD の r1 開始 0.27 → 終了 8.41、r2 終了 9.26。旧 `5ed1552bc` の r1 開始 0.51 → 終了 7.96、r2 終了 7.95。
- 所要: HEAD r1 2m50s・r2 2m50s (`[batch] done 168s`)。旧 r1 2m55s・r2 2m51s。

## 2. 判定の突合 (HEAD `94c133e12`)

突合は `tests/ld157_batch_diff.py` (`--chunk 400 --shards 12`)。出力そのまま:

```
functions 800
run1 verdict match 352 / mismatch 259 / unexec 189
run1 wasm timeout/hang/crash cases 299 (functions 70)
run2 verdict match 352 / mismatch 259 / unexec 189
run2 wasm timeout/hang/crash cases 300 (functions 70)
verdict changes 0: -
case-level changes 1 functions
- 0xa9ece0 chunk 1 shard 2 pos 290 | verdict mismatch->mismatch | chain(先行の差分) - | own wasm-to r1 ['z', 'pall', 'pall2', 'qall'] r2 ['z', 'pall', 'pall2', 'q0', 'qall']
```

## 3. 判定の突合 (旧 `5ed1552bc`)

```
functions 800
run1 verdict match 352 / mismatch 258 / unexec 190
run1 wasm timeout/hang/crash cases 299 (functions 70)
run2 verdict match 352 / mismatch 258 / unexec 190
run2 wasm timeout/hang/crash cases 294 (functions 69)
verdict changes 2: 0x959a40 mismatch->match, 0x10348b0 match->mismatch
case-level changes 8 functions
- 0x47d450 chunk 1 shard 8 pos 68 | verdict match->match | chain - | own wasm-to r1 ['p0','q0','qall','u16'] r2 ['p0','pall','q0','qall','u16']
- 0xd2c5a0 chunk 1 shard 2 pos 218 | verdict mismatch->mismatch | chain - | own wasm-to r1 ['p01'] r2 -
- 0xa9ece0 chunk 1 shard 2 pos 290 | verdict mismatch->mismatch | chain 0xd2c5a0 | own wasm-to r1 ['z','pall','pall2','qall'] r2 ['z','pall','pall2','qall']
- 0x50abe0 chunk 1 shard 4 pos 316 | verdict unexec->unexec | chain - | own wasm-to r1 - r2 ['q0']
- 0x43a3f0 chunk 1 shard 4 pos 328 | verdict mismatch->mismatch | chain 0x50abe0 | own wasm-to r1 - r2 -
- 0x959a40 chunk 1 shard 4 pos 340 | verdict mismatch->match | chain 0x50abe0,0x43a3f0 | own wasm-to r1 - r2 -
- 0xff0d70 chunk 1 shard 4 pos 352 | verdict unexec->unexec | chain 0x50abe0,0x43a3f0,0x959a40 | own wasm-to r1 - r2 -
- 0x10348b0 chunk 1 shard 4 pos 376 | verdict match->mismatch | chain 0x50abe0,0x43a3f0,0x959a40,0xff0d70 | own wasm-to r1 ['s','p0','pall2','q0','vm0','u16'] r2 -
```

`own wasm-to` は case の `wasm_status` が timeout / hang / crash のもの。`chain` は同じ chunk・同じ shard で先に実行され、case 結果が両 run で違った関数。

## 4. 原因の切り分け (旧 `5ed1552bc`)

| 関数 | 変化の種類 | 原因 | 単独 (fresh・無負荷) との照合 |
|---|---|---|---|
| 0x50abe0 | own (`q0`) | r2 だけ wasm timeout (`hang`)。r1 は `trap` | 単独 `q0` = `both_fault` (trap)。timeout は負荷起因 |
| 0xd2c5a0 | own (`p01`) | r1 だけ wasm timeout | 単独 `p01` = `native_fault`・wasm `ok` (r2 と一致) |
| 0x47d450 | own (`pall`) | r2 だけ wasm timeout | 判定は両 run `match` のまま |
| 0xa9ece0 | own (`pall` の crash/hang 区別) + chain (0xd2c5a0) | runner 段の status の違い | 判定は両 run `mismatch` のまま |
| 0x43a3f0 | chain (0x50abe0) | 自身の timeout なし。先行 shard の状態に依存 | 単独 = `mismatch` (r1・r2 と同じ判定) |
| 0x959a40 | chain (0x50abe0 → 0x43a3f0) | 判定が変わった (mismatch→match) | 単独 = `match` (p1・pall・qall が `equal`)。**r2 と一致** |
| 0xff0d70 | chain | 自身の timeout なし | 単独 = `unexec` (native_fault_all_patterns)。両 run と一致 |
| 0x10348b0 | own (s・p0・pall2・q0・vm0・u16 の timeout、r1 のみ) + chain | 判定が変わった (match→mismatch) | 単独 = `mismatch` (z・p1・p01・pall・qall は `wasm_trap`、残りは `both_fault`)。**r2 と一致** |

- 2 件の判定変化 (0x10348b0・0x959a40) は、単独の結果と r2 が一致し、r1 が一致しなかった。r1 の結果は先行 shard の状態に依存していた。
- r1 を汚したものは未特定。候補は 0x50abe0 の `q0` の trap 経路の副作用 (r1 は `trap`、r2 は timeout)。
- 単独の結果は fresh 1 回ずつで、無負荷 (1 分 load 0.49)。決定性は確認していない (0x10348b0 は 2 回実行して同じ `mismatch`)。

## 5. 持ち越しの仕組み (コードの読み)

- `ldlib/session.py::run_functions`: 400 件 chunk ごとに、関数を `part[k::shards]` で shard へ割る。shard 内は同じ wasm instance を関数をまたいで使う (`make_runners` は chunk の開始時だけ)。
- `rt/ld_runner.mjs::runCase`: 1 秒 (`wasmTimeoutMs`) の vm timeout は `status=timeout` を返すだけで、ランナを再起動しない。instance の状態は残る。
- `ldlib/runners.py::run_cases`: ランナ応答が 10 秒返らないときだけ `hang`/`crash` として再起動する。
- 両 run の wasm timeout/hang/crash は 299/300 case (70 関数)。負荷で 1 秒の vm 制限に掛かる case が多い。
- ランナの作り直しは hybrid state (69.5 MB) で 1 回 約 1.1 秒 (`make_runners` を 2 回計測: 1.12・1.11 秒、shards=1、無負荷)。

## 6. 判定ロジックと timeout 既定値

`ldlib/classify.py`・`ldlib/compare.py` の outcome の決め方、wasm 1000 ms・native 10 秒の既定値は変えていない。本付録は測定と突合の追加だけ。

## 7. 検証 (コード差分)

- 測定 commit: `94c133e12` (HEAD の batch 測定時点)。旧 `5ed1552bc` からの差分は LD-153 (#3349) の変更:
  `git diff --stat 5ed1552bc 94c133e12 -- tools/liftdiff` → `REPORT_APPENDIX_LD153.md` 78 行、`rt/ld_core.h` 7 行、`tests/check_initunits.py` 7 行 (追加 90・削除 2)。
- 本 PR の追加: `tests/ld157_batch_diff.py` (新規・突合ツール) と本付録。batch の測定には使っていない。

## 8. 再現

```
cd tools/liftdiff
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP
python3 liftdiff.py build targets/m11.json
python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild
python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state work/m11/boot_state_hybrid.json --out work/m11/batch_r1.jsonl
python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state work/m11/boot_state_hybrid.json --out work/m11/batch_r2.jsonl
python3 tests/ld157_batch_diff.py work/m11/batch_r1.jsonl work/m11/batch_r2.jsonl
python3 liftdiff.py run targets/m11.json --fn 0x10348b0 --nobuild --state work/m11/boot_state_hybrid.json
```

`work/` は gitignore のため、batch の jsonl は commit しない。
