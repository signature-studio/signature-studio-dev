# liftdiff REPORT 付録: LD-44 (#1313) OTT 旧 chain 8 関数の trace と m11 sample:800 の再測定

親 issue #1070 (LD-32) の残り。前提の記録は `REPORT_APPENDIX_LD16.md` §7・§8。本書は測定 commit `92a145a5` (main 取り込み時点) での再測定。

## 結論

- 受入条件は**未達**。今回の run では命令単位 trace まで届かなかった。残りは子 issue に分けた (§6)。
- `1801c67a0` の `m8_fail`: 発火経路を訂正した。前節 §8.3 は `function_1801c721c` 経由としていたが、本 run の trace では `function_1801c67a0` 本体から直接 `m8_fail` に入る。`m8_rt.c` の入口ガード (rcx が `[0x30000000, 0x36000000)` の外なら fail) が arena ポインタ (wasm 上 `0x220f1000` 台) を弾いている、という**仮説**。ガードを外した再 build による確認は未実施。
- m11 sample:800 は、e2e と同じ条件 (`--shards 12 --state auto`) で 3 回測った結果、**件数が揺れた** (361 / 360 / 360 の一致、229 / 230 / 230 の不一致)。前節 §8.2 の「件数 3 回一致」は本 run では再現しない。関数単位では `0x959a40` の verdict が 1 件変わった (§3)。
- `--state` を省いた条件 (`--shards 4`) では 3 回とも 352 / 170 / 278 で安定。e2e 条件と件数が大きく違うため、揺れの要因の候補は shard 数と state 指定。

## 1. 測定条件

- commit: `92a145a5` (main の HEAD のうち `tools/liftdiff`・`tools/m8`・`tools/ott`・`tools/m11` の変更を含む)
- 測定 runner: 4 vCPU。`uptime` の load 1 分平均は測定中 0.0 → 7.3 の範囲
- 素材: `fl-win64` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11`・`work-liftdiff`・`work-m6-ott`・`analysis-ott-binaries` (`ANALYSIS_DIR=$HOME/analysis`)・`toolchain-emsdk` を展開して使用
- 生データ: `tools/liftdiff/results/ld44_*`。batch の stdout は `ld44_*_92a145a5.log`、件数は `ld44_m11_sample800_counts_92a145a5.tsv`、関数単位の突合は `ld44_m11_sample800_verdict_n3_e2econd_92a145a5.tsv`

## 2. `1801c67a0` の再確認 (`liftdiff.py run --nobuild`)

- 再確認したのは `1801c67a0` の 1 関数のみ。`1801c67a0` を全 pattern で再実行: z/s/p0/p1/p01/pall/qall は `both_fault` (native segv・wasm trap)、u16/vm0 は `wasm_trap` (native ok・wasm abort)。LD-16 §8.3 の観測と一致する。
- 他 7 関数 (`1801ab1d0` / `1801ab258` / `1801ab3ec` / `1801c5e84` / `1801c621c` / `1801c682c` / `1801c69cc`) は**未実施**。OTT 8 関数の再確認は未達。

## 3. sample:800 の再測定

| 条件 | run | 一致 | 不一致 | 実行不能 |
|---|---|---|---|---|
| e2e 条件 (`--shards 12 --state auto`) | r1 | 361 | 229 | 210 |
| 同上 | r2 | 360 | 230 | 210 |
| 同上 | r3 | 360 | 230 | 210 |
| `--shards 4` (`--state` なし) | r1 | 352 | 170 | 278 |
| 同上 | r2 | 352 | 170 | 278 |
| 同上 | r3 | 352 | 170 | 278 |

関数単位 (`tests/ld32_verdict_cmp.py`, e2e 条件の 3 回):

| 関数 | verdict (r1/r2/r3) | case outcome が変わった pattern |
|---|---|---|
| `0x959a40` | **match / mismatch / mismatch** | p1・pall・qall: r1 `equal` → r2・r3 `diff` (r2・r3 のみ `callee_divergence` タグ) |
| `0x1060950` | mismatch ×3 | s: hang \| both_fault \| hang |
| `0x43a3f0` | mismatch ×3 | p0・p01・pall・pall2・q0・qall・u16・vm0 が native_fault / diff と wasm_trap の間で入れ替わる |
| `0x50abe0` | unexec ×3 | q0: hang \| both_fault \| both_fault |
| `0x5c5500` | unexec ×3 | fvm・p01・p1・pall・u16: hang / both_fault の入れ替わり |

- §8.2 の 3 関数 (`0x5c5500`・`0x67e2b0`・`0x903d50`) とは一致しない。`0x67e2b0`・`0x903d50` は今回の 3 回では変化していない。
- `0x959a40` は今回の run で初めて観測された verdict 変化。`callee_divergence` が出た r2・r3 の内訳は未確認 (命令単位 trace が要る)。

## 4. 測定の注意 (訂正)

- 測定 commit: `92a145a5`。HEAD までの測定経路の差分 (`git diff 92a145a5 HEAD -- tools/liftdiff/ldlib`) は次の 1 行のみ。
  ```
  tools/liftdiff/ldlib/session.py | 2 +-
  -                if c['outcome'] in ('diff', 'wasm_trap') and not refined and c.get('wasm_status') != 'timeout':
  +                if c['outcome'] in ('diff', 'wasm_trap') and not refined and c.get('wasm_status') != 'timeout' and c['pattern'] in patterns:
  ```
  この差分は `ae802a4c` (fvm pattern の refine を除外する修正) に由来する。batch は `patterns=None` で `PATTERN_NAMES` (fvm を含まない) を渡すため、batch の case 集合は変わらない見込みだが、**未検証**。
- 差分の集計 (`git diff --stat 92a145a5 HEAD -- tools/liftdiff tools/m8 tools/ott tools/m11`): 24 files changed, 646 insertions(+), 41 deletions(-)。
- 再測定 (差分の反映) は未実施。素材 `work-m11` と `toolchain-emsdk` が本 run に無いため (`targets/m11.json` が `tools/m11/work/` を要求)。次の run で `oc_artifacts: fl-win64 work-m11 toolchain-emsdk work-liftdiff` を指定して再測定する (子 issue 起票先は §6)。

- 最初に `--shards 4` (`--state` なし) で測った値 (352 / 170 / 278) を e2e 条件と取り違えないこと。e2e の [4/4] は `--shards 12 --state auto` で、こちらが基準。
- `ld44_*` の `.log` は batch の stdout のみで、ケース単位の `native_status`・`wasm_status` は含まれない。`case outcome` の hang の内訳 (native か wasm の timeout か) は依然として未確定。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8 関数の命令単位 trace (native と wasm の各 step) | §8.3 は entry・call 単位のまま | LD-57 (#1636) |
| `1801c67a0` の `m8_fail` 発火条件の確認 (入口ガードの範囲と arena の不一致が原因か) | 仮説のみ。ガードを外した再 build で確認が必要 | LD-58 (#1637) |
| sample:800 の件数揺れ (e2e 条件で 361/360) と `0x959a40` の verdict 変化の原因。shard 数・state 指定・負荷との関係 | 再現条件は一部確認のみ。内訳は未確定 | LD-58 (#1637) |
| 測定 commit `92a145a5` 以降の `session.py` 1 行差分 (§4) を反映した batch の再測定 | 差分込みの件数・verdict は未確認。`92a145a5` の値は差分前の結果 | 本 PR で `oc_artifacts: fl-win64 work-m11 toolchain-emsdk work-liftdiff` を指定して再実行 (未実施。次の run) |

注: 子 issue の番号は `gh issue list` の最大値 (LD-56) + 1・+2 で取り、重複 0 件を確認した。
