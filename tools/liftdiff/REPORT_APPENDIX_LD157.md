# liftdiff LD-157 (#3423): hybrid batch の判定の再現性

親: #3350 (LD-154)。#3423 の本文は「#3350 で JSONL に `timing` を残した」と書くが、main では確認できなかった。#3350 は OPEN で、`timing` フィールドは出力されていない。切り分けは各 case の `native_status`・`wasm_status` で行う (突合ツールは wasm 側の打切りを 3 種に分ける。§0)。

## 0. 結論

- **測定 commit `94c133e12` (PR の基点)**: hybrid state で `--set sample:800` を 2 回連続で実行した。判定 (一致 352 / 不一致 259 / 実行不能 189) は 2 回とも同じで、判定の変化は 0 件。ケース単位では 1 関数 (0xa9ece0) の wasm 側 status が 1 case だけ変わった (判定は変わらない)。
- **旧測定 `5ed1552bc` (LD-153 #3349 の修正前)**: 判定が 2 件変わった (0x10348b0 match→mismatch・0x959a40 mismatch→match)。ケース単位では 8 関数が変わった。判定の変化と case 単位の関数名は、verdict と case の outcome・native_status・wasm_status から出ている。
- **原因は確定していない**。候補は §4 に並べた (wasm の vm timeout・shard 内の wasm 状態の持ち越し・runner の再起動・native の timeout 後の残留)。単独 (fresh・1 回ずつ) の結果は 2 件とも r2 と一致したが、決定性は未確認。
- **撤回した値**: 前版 (`54443becb`) の「wasm timeout/hang/crash cases 299/300・294」と §3・§4・§5 の own 列は、wasm 側の集計が native skip (native が timeout/hang/crash の case で、wasm を実行せず合成の `hang` を入れたもの) を含んでいた。本版では出していない。
- **wasm 側 3 種の分離値は未算出**: vm timeout・wasm 無応答・native skip の件数は batch の jsonl から出せる。ただし測定時の jsonl は本 runner に残っておらず (`work/` は gitignore)、再測定もしていない。突合ツールは 3 種を出すように直した (§7)。
- **HEAD の判定 (352/259/189)**: 旧 (352/258/190) から 1 件ずつ動いた。LD-153 の thunk 敷設 (`ld_core.h`) の時期と重なるが、因果は未検証。HEAD の n=2 では判定は動かなかったが、ケース単位の変化は 1 関数 (0xa9ece0) に残った。

## 1. 測定条件

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`)。`work-m11` と `work-liftdiff` は runner の既存展開を worktree から symlink。`toolchain-emsdk` は `[EMSDK]` (`docs/REFERENCES.md` §4)。
- build: `python3 liftdiff.py build targets/m11.json` (`wasm_size` 4459339 @ `94c133e12`・4459215 @ 旧 `5ed1552bc`)。
- hybrid state: `python3 liftdiff.py bootstate targets/m11.json --mode hybrid --nobuild` → `units_run=928/942 first_fail=830`、`precondition ok=True` (LD-42 と一致)。
- batch: `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state work/m11/boot_state_hybrid.json --out work/m11/batch_<名>.jsonl` を 2 回。
- 機: 4 vCPU。1 分 load は `94c133e12` の r1 開始 0.27 → 終了 8.41、r2 終了 9.26。旧 `5ed1552bc` の r1 開始 0.51 → 終了 7.96、r2 終了 7.95。
- 所要: `94c133e12` の r1 2m50s・r2 2m50s (`[batch] done 168s`)。旧 r1 2m55s・r2 2m51s。
- 注: 旧 `54443becb` の付録で使った jsonl は本 runner に無い。以下の判定・case 単位の値は、その付録の出力に書かれた値を転記している。

## 2. 判定の突合 (測定 commit `94c133e12`)

突合は `tests/ld157_batch_diff.py` (`--chunk 400 --shards 12`)。判定と case 単位の行のみ。wasm 側の件数は §0 のとおり撤回。

```
functions 800
run1 verdict match 352 / mismatch 259 / unexec 189
run2 verdict match 352 / mismatch 259 / unexec 189
verdict changes 0: -
case-level changes 1 functions
- 0xa9ece0 chunk 1 shard 2 pos 290 | verdict mismatch->mismatch | chain - | own 未算出
```

## 3. 判定の突合 (旧 `5ed1552bc`)

判定と case 単位の行。`chain` は、同じ shard で先行し、case 単位で r1/r2 が違った関数 (同時性の相関のみ。因果ではない)。`own` (自 case の wasm 側の打切り) は未算出。

```
functions 800
run1 verdict match 352 / mismatch 258 / unexec 190
run2 verdict match 352 / mismatch 258 / unexec 190
verdict changes 2: 0x959a40 mismatch->match, 0x10348b0 match->mismatch
case-level changes 8 functions
- 0x47d450 chunk 1 shard 8 pos 68 | verdict match->match | chain - | own 未算出
- 0xd2c5a0 chunk 1 shard 2 pos 218 | verdict mismatch->mismatch | chain - | own 未算出
- 0xa9ece0 chunk 1 shard 2 pos 290 | verdict mismatch->mismatch | chain 0xd2c5a0 | own 未算出
- 0x50abe0 chunk 1 shard 4 pos 316 | verdict unexec->unexec | chain - | own 未算出
- 0x43a3f0 chunk 1 shard 4 pos 328 | verdict mismatch->mismatch | chain 0x50abe0 | own 未算出
- 0x959a40 chunk 1 shard 4 pos 340 | verdict mismatch->match | chain 0x50abe0,0x43a3f0 | own 未算出
- 0xff0d70 chunk 1 shard 4 pos 352 | verdict unexec->unexec | chain 0x50abe0,0x43a3f0,0x959a40 | own 未算出
- 0x10348b0 chunk 1 shard 4 pos 376 | verdict match->mismatch | chain 0x50abe0,0x43a3f0,0x959a40,0xff0d70 | own 未算出
```

## 4. 原因の候補 (旧 `5ed1552bc`)

| 関数 | 変化 | 判定の変化 | 単独 (fresh・無負荷・1 回) との照合 |
|---|---|---|---|
| 0x50abe0 | case `q0` の wasm 側が r1 は `trap`、r2 は打切り (vm timeout・無応答・native skip の合成 hang のいずれかは未確定) | なし (`unexec`) | 単独 `q0` = `both_fault` (trap) |
| 0xd2c5a0 | `p01` のみ r1 で wasm 側が打切り (種別未確定) | なし (`mismatch`) | 単独 `p01` = `native_fault`・wasm `ok` (r2 と一致) |
| 0x47d450 | `pall` のみ r2 で wasm 側が打切り (種別未確定) | なし (`match`) | — |
| 0xa9ece0 | case の wasm 側 status (chain: 0xd2c5a0) | なし (`mismatch`) | — |
| 0x43a3f0 | 自身の case に差分なし (chain: 0x50abe0) | なし (`mismatch`) | 単独 = `mismatch` (両 run と一致) |
| 0x959a40 | chain (0x50abe0 → 0x43a3f0) | `mismatch`→`match` | 単独 = `match` (r2 と一致、r1 と不一致)。単独で `p1`・`pall`・`qall` が `equal` |
| 0xff0d70 | chain のみ | なし (`unexec`) | 単独 = `unexec` (両 run と一致) |
| 0x10348b0 | chain (0x50abe0・0x43a3f0・0x959a40・0xff0d70) | `match`→`mismatch` | 単独 = `mismatch` (r2 と一致、r1 と不一致)。単独で `z`・`p1`・`p01`・`pall`・`qall` は `wasm_trap`、残りは `both_fault` |

- 判定が変わった 2 件 (0x10348b0・0x959a40) は、単独 1 回の判定が r2 と一致し、r1 と一致しなかった。r1 の判定を変えた要因は特定できていない。決定性は未確認 (0x10348b0 は 2 回実行して同じ `mismatch`)。
- 候補 (どれも未検証。証拠は chain の相関と単独照合だけ):
  - ① **負荷による wasm vm timeout** (1 秒)。`rt/ld_runner.mjs` は `status=timeout` を返すだけでランナを再起動しない。r1/r2 で case の wasm status が変わったことは sig から分かるが、その case が vm timeout・無応答・native skip の合成 hang のどれかは jsonl が無く未確定。
  - ② **shard 内の wasm 状態の持ち越し**。`ldlib/session.py::run_functions` は shard 内で同じ wasm instance を関数をまたいで使う。`_run_one` の `with_refine` (l1/l2 の追加実行) と `_fvm_cases` の追加 case も同じ instance を使う。
  - ③ **runner の再起動**。`ldlib/runners.py::run_cases` は、応答が timeout (`self.timeout`、既定 10 秒) 内に返らないとき (hang/crash)、と応答行が壊れていたとき (badjson、再起動して 1 回再試行) に runner を再起動する。`start()` は init と SNAPSHOT を再送するので、boot 状態に戻る。再起動の回数は jsonl に残らない。
  - ④ **native の timeout 後の残留**。native は SIGALRM で case を `timeout` にし、同じプロセスで次の case を続ける (`rt/ld_native.c`)。166 行付近のコメントは watch 機能 (`LD_WATCH_ADDR`、既定は無効) の page 残留に関するもので、既定の batch に効くかは未確認。
- 次に確かめること (未実施): batch の jsonl を保存し、`tests/ld157_batch_diff.py` の 3 種の件数を出す。①と③は jsonl の wasm status の内訳と、再起動の回数の記録で分けられる。

## 5. 持ち越しの仕組み (コードの読み)

- `liftdiff.py::cmd_batch`: 400 件 chunk ごとに `sess.run_functions` を呼ぶ。
- `ldlib/session.py::run_functions`: chunk 内の関数を `vas[i::shards]` で shard に割り、shard ごとに `make_runners` で native・wasm の Runner を 1 組作る。shard 内では関数を順に実行し、同じ wasm instance を関数をまたいで使う。
- `ldlib/session.py::_run_one`: native の status が timeout/hang/crash の case は wasm を実行せず、`{'status': 'hang', 'detail': 'skipped (native timeout)'}` を入れる。wasm 側の `hang` は、このとき合成の値。
- `rt/ld_runner.mjs::runCase`: wasm の vm timeout (`--timeout-ms`、既定 1000 ms) は `status=timeout` を返すだけで、ランナを再起動しない。instance の状態は残る。
- `ldlib/runners.py::run_cases`: 応答が `self.timeout` 内に返らない (hang/crash) ときと、応答行が壊れていた (badjson) ときに再起動する。wasm runner の timeout は `max(self.timeout, wasm_timeout_ms / 1000 + 5)` = 10 秒。
- ランナの作り直しは hybrid state (69.5 MB) で 1 回 約 1.1 秒 (`make_runners` を 2 回計測: 1.12・1.11 秒、shards=1、無負荷)。

## 6. 判定ロジックと timeout 既定値

`ldlib/classify.py`・`ldlib/compare.py` の outcome の決め方、wasm 1000 ms・native 10 秒の既定値は変えていない。本付録は測定と突合の追加だけ。

## 7. 検証 (コード差分)

- 測定 commit: `94c133e12` (PR の基点)。origin/main は後に進んでいるが、測定はこの commit のコードで行った。
- 本 PR の変更: `tests/ld157_batch_diff.py` (突合ツール。wasm 側の打切りを vm / 無応答 / native skip の 3 種に分けた) と本付録。batch の実行経路は変えていない。`git diff --stat 94c133e12 HEAD -- ldlib rt liftdiff.py` の出力は空。
- 突合ツールの検証: 合成 jsonl (2 run・6 関数・shards=3。repo の外に置き、commit しない) で、native skip → `native[q0]`、wasm vm timeout → `vm[q0]`、無応答 → `noresp[p0]`、chain (同 shard の先行 0x1000) と判定の変化 (0x5000) が期待どおり出ることを確認した。
- 旧 commit との差分: `git diff --stat 5ed1552bc 94c133e12 -- tools/liftdiff` → `REPORT_APPENDIX_LD153.md` 78 行、`rt/ld_core.h` 7 行、`tests/check_initunits.py` 7 行 (追加 90・削除 2)。

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

`work/` は gitignore のため、batch の jsonl は commit しない。§3・§4 の wasm 側 3 種の値は、この jsonl を残して突合ツールを回すと出せる。
