# liftdiff REPORT 付録: LD-44 (#1313) OTT 旧 chain 8 関数の trace と m11 sample:800 の再測定

親 issue #1070 (LD-32) の残り。前提の記録は `REPORT_APPENDIX_LD16.md` §7・§8。

## 結論

- 受入条件は**未達**。命令単位 trace は今回の run でも届かなかった。残りは子 issue に分けた (§5)。
- `1801c67a0` の `m8_fail`: 発火経路を訂正した。前節 §8.3 は `function_1801c721c` 経由としていたが、本 run の trace では `function_1801c67a0` 本体から直接 `m8_fail` に入る。`m8_rt.c` の入口ガード (rcx が `[0x30000000, 0x36000000)` の外なら fail) が arena ポインタ (wasm 上 `0x220f1000` 台) を弾いている、という**仮説**。ガードを外した再 build による確認は未実施。
- m11 sample:800 は、測定 commit `be017fb1` (HEAD) で e2e 条件 (`--shards 12 --state auto`) を 3 回測り、件数は **360 / 230 / 210 で 3 回一致**。verdict の変化は 0 件。
- 92a145a5 で観測した揺れ (361 / 360 / 360 と `0x959a40` の verdict 変化) は、HEAD の 3 回では再現しなかった。差分 (`session.py` 1 行) の影響は、HEAD の測定で fvm 由来の diff / wasm_trap が 0 件だったことから、この測定の範囲では出ていない (§4)。92a145a5 と HEAD を同一セッションで並べた比較は未実施なので、揺れの原因は確定しない。

## 1. 測定条件

- 測定 commit: `be017fb1` (PR head。コードは `92a145a5` から変えていない。差分は §4 の `session.py` 1 行のみ)。
- 測定 runner: 4 vCPU・メモリ 15 GiB。load は測定中 0.3 → 5.7 の範囲 (`uptime`)。
- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)・`toolchain-emsdk` (`/opt/emsdk`, emscripten 6.0.12) を展開して使用。
- 生データ:
  - batch の stdout: `results/ld44_e2e_head_r{1,2,3}_be017fb1.log`
  - 件数: `results/ld44_m11_sample800_counts_be017fb1.tsv`
  - 関数単位の突合: `results/ld44_m11_sample800_verdict_n3_e2econd_be017fb1.tsv` (`tests/ld32_verdict_cmp.py` の出力)
  - 92a145a5 の測定 (比較用): `results/ld44_*_92a145a5.log`・`results/ld44_m11_sample800_*_92a145a5.tsv`

## 2. `1801c67a0` の再確認 (`liftdiff.py run --nobuild`、測定 commit `92a145a5`)

- HEAD では再実行していない (`ott_old` の素材 `work-m6-ott` が本 run に無い)。下記は 92a145a5 での結果。
- 再確認したのは `1801c67a0` の 1 関数のみ。`1801c67a0` を全 pattern で再実行: z/s/p0/p1/p01/pall/qall は `both_fault` (native segv・wasm trap)、u16/vm0 は `wasm_trap` (native ok・wasm abort)。LD-16 §8.3 の観測と一致する。
- 他 7 関数 (`1801ab1d0` / `1801ab258` / `1801ab3ec` / `1801c5e84` / `1801c621c` / `1801c682c` / `1801c69cc`) は**未実施**。OTT 8 関数の再確認は未達。

## 3. sample:800 の再測定

e2e 条件 (`liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto`) の件数:

| 条件 | run | 一致 | 不一致 | 実行不能 | 所要 |
|---|---|---|---|---|---|
| HEAD `be017fb1` | r1 | 360 | 230 | 210 | 107 s |
| 同上 | r2 | 360 | 230 | 210 | 107 s |
| 同上 | r3 | 360 | 230 | 210 | 108 s |
| 92a145a5 (参考) | r1 | 361 | 229 | 210 | 111 s |
| 同上 | r2 | 360 | 230 | 210 | 107 s |
| 同上 | r3 | 360 | 230 | 210 | 109 s |

HEAD の 3 回で、verdict の変化は 0 件 (`ld32_verdict_cmp.py`)。`0x959a40` は 3 回とも `mismatch`。case outcome が変わった関数は 5 件 (下表)。

| 関数 | verdict (r1/r2/r3) | case outcome が変わった pattern |
|---|---|---|
| `0x1060950` | mismatch ×3 | s: both_fault \| hang \| hang |
| `0x5c14d0` | match ×3 | p0・p01・p1・pall・pall2・q0・s・u16・vm0・z: both_fault \| native_fault \| native_fault |
| `0x5c5500` | unexec ×3 | p01・pall・qall: hang \| both_fault 系の入れ替わり |
| `0x6b94b0` | unexec ×3 | q0: hang \| native_fault \| native_fault |
| `0xf824b0` | mismatch ×3 | p1・s: both_fault \| native_fault \| native_fault |

- 92a145a5 の 3 回で変化した `0x43a3f0`・`0x50abe0`・`0x959a40` は HEAD の 3 回では変化しなかった。`0x5c5500`・`0x1060950` も pattern の内訳が前回と違う。case outcome の揺れは run 間で続いている。
- §8.2 の 3 関数 (`0x5c5500`・`0x67e2b0`・`0x903d50`) は HEAD の 3 回で verdict が安定している。`0x5c5500` は case outcome が揺れ (unexec)、`0x67e2b0` は mismatch・`0x903d50` は match で固定。

## 4. 測定経路の差分 (`92a145a5` → `HEAD`)

- `git diff 92a145a5 HEAD -- tools/liftdiff/ldlib` の出力 (ae802a4c の 1 行):
  ```
  diff --git a/tools/liftdiff/ldlib/session.py b/tools/liftdiff/ldlib/session.py
  @@ -174,7 +174,7 @@ class Session:
  -                if c['outcome'] in ('diff', 'wasm_trap') and not refined and c.get('wasm_status') != 'timeout':
  +                if c['outcome'] in ('diff', 'wasm_trap') and not refined and c.get('wasm_status') != 'timeout' and c['pattern'] in patterns:
  ```
  この差分は `ae802a4c` (fvm pattern の refine を除外する修正) に由来する。
- 差分が効く条件: 新条件は、`pattern` が `patterns` に無い case (fvm 由来) を refine の対象から外す。旧コードでは、fvm 由来の case が diff / wasm_trap だと `patterns.index('fvm')` が ValueError を出し batch が落ちる。
- HEAD の測定で、fvm 由来の case で `outcome` が diff / wasm_trap (timeout 除く) のものは **0 件** (3 回とも。`work/m11/batch_head_r{1,2,3}.jsonl` を集計)。したがって HEAD の 3 回では、新条件は旧条件と同じ refine 判定になる。
- ただし、これは HEAD の測定データからの確認で、旧コード (`92a145a5`) を同じ HEAD の素材で走らせた比較ではない。92a145a5 の r1 (361) と HEAD の r1 (360) の 1 件差が差分由来かどうかは、この測定では確定しない (run 間の揺れの範囲内に見える)。
- 差分の集計 (`git diff --stat 92a145a5 HEAD -- tools/liftdiff tools/m8 tools/ott tools/m11`): **24 files changed, 660 insertions(+), 41 deletions(-)**。`be017fb1` 時点でも同じ値。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8 関数の命令単位 trace (native と wasm の各 step) | §8.3 は entry・call 単位のまま | LD-57 (#1636) |
| `1801c67a0` の `m8_fail` 発火条件の確認 (入口ガードの範囲と arena の不一致が原因か) | 仮説のみ。ガードを外した再 build で確認が必要 | LD-58 (#1637) |
| sample:800 の件数揺れ (92a145a5 の 361 / 360 / 360, `0x959a40` の verdict 変化) の原因。HEAD では再現せず | 同一セッションで 92a145a5 と HEAD を並べた比較が無い | LD-58 (#1637) |
| OTT 8 関数のうち 7 関数の再確認 | 未実施 | 本 PR の受入 5 で未達として記録 (次の run 以降) |

注: 子 issue の番号は `gh issue list` の最大値 (LD-56) + 1・+2 で取り、重複 0 件を確認した。
