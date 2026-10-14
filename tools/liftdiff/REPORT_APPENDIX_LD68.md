# liftdiff REPORT 付録: LD-68 (#1907) wasm 側 IR block trace と native 1801c5e84 系の対応付け

親 issue #1854 (LD-64)。前提は `REPORT_APPENDIX_LD64.md` §3・§7 と `REPORT_APPENDIX_LD67.md` (#1906・PR #2020)。

## 結論

- 受入条件は**部分達成**。本 PR で達成したのは「計装版の block trace を既定 build と照合して判定に使える状態にする」と「wasm の block 列を実測で示す」まで。
- **命令単位の wasm trace (受入条件 1) は未達**。IR に元の VA が無いため、lifter 側の変更が要る。本 run では着手できず、子 issue に切り出す (§5)。
- 1801c5e84 vm0 の block 対応 (受入条件 2): native `1c0b6c`・`1c0b6f` は IR block `1c0b6c`、native `1c0b82` (HeapFree の call) は IR block `1c0b71` の範囲に入る。wasm の vm0 の block 列には `1c0b6c` → `1c0b71` → `1c0b8c` → `1c0ba8` が順に現れる。ただし「範囲に入る」は IR label の address 順による推定で、命令単位の一致は示していない。u16 は wasm が trap するため、block 列は `1c0b6c` → `1c0b71` で止まる。
- 残り 5 関数 (受入条件 3): 計装版 block 列は取れた (§3) が、native 命令との対応は未了。
- 測定結果 (計装版と既定版の 12 case 比較) は差 0。計装 build の block trace は判定に使ってよい状態 (LD-67 の結論を再確認)。

## 1. 測定条件

- 測定 commit: `0e5b184c` (`fix(liftdiff): record IR block trace by store, not call`。コード差分の最終 commit。`main` の `98c5f8ca` に含まれる)。
- 測定 runner: 4 vCPU・メモリ 15 GiB。load average (測定時) 0.71 / 0.51 / 0.23 (`uptime` 09:47:59Z)。
- 素材: `work-m6-ott`・`work-liftdiff`・`plugins-ott`・`analysis-ott-binaries` を worktree (`ws-1907`) に展開。`fl-win64` は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` に展開。`toolchain-emsdk` は `/opt/emsdk` (emcc 6.0.12)。`work-liftlib`・`work-m11`・`toolchain-retdec` は本 run では使っていない。
- build: `ott_old_blk` は `work/ott_old_blk/` が素材に無かったため、`liftdiff.py run targets/ott_old_blk.json` (build あり) で再 build。`ott_old` は素材の `work/ott_old/` をそのまま使用 (`--nobuild`)。
- 実行コマンド:
  - 計装版: `python3 liftdiff.py run targets/ott_old_blk.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --json work/ld68/blk_all.json`
  - 既定版: 同上、`targets/ott_old.json`・`work/ld68/def_all.json`
  - 比較: `python3 results/ld67/compare_blk.py work/ld68/def_all.json work/ld68/blk_all.json`
- 所要 (n=1・結論には使わない): 計装版 `--nobuild --notrace` の run は 09:47:17 → 09:47:23 UTC (6 s 程度・秒単位の計測)。既定版の所要は未計測。

## 2. 既定版と計装版の比較

`compare_blk.py` の出力 (12 case):

| 関数 | pattern | 既定 outcome | 計装 outcome | 判定 | 計装 blk 件数 |
|---|---|---|---|---|---|
| 1ab1d0 | vm0 | equal | equal | SAME | 0 |
| 1ab1d0 | u16 | equal | equal | SAME | 0 |
| 1ab258 | vm0 | equal | equal | SAME | 0 |
| 1ab258 | u16 | equal | equal | SAME | 0 |
| 1c5e84 | vm0 | diff | diff | SAME | 27 |
| 1c5e84 | u16 | wasm_trap | wasm_trap | SAME | 4 |
| 1c621c | vm0 | diff | diff | SAME | 287 |
| 1c621c | u16 | wasm_trap | wasm_trap | SAME | 6 |
| 1c682c | vm0 | diff | diff | SAME | 42 |
| 1c682c | u16 | diff | diff | SAME | 43 |
| 1c69cc | vm0 | diff | diff | SAME | 304 |
| 1c69cc | u16 | wasm_trap | wasm_trap | SAME | 10 |

`cases=12 diff=0`。LD-67 §1 の blk 件数 (27・4・287・6・42・43・304・10) と一致。
計装 build は `1ab1d0`・`1ab258` で 0 件 (記録は block 入口にだけ効く) で、LD-67 の記録と同じ。

注: `diff` / `wasm_trap` は既定版でも同じで、これは native との比較結果であり、計装の影響ではない (計装の影響は差 0 で否定)。

## 3. wasm の block 列 (1801c5e84 vm0)

`blk` (計装版の記録) の先頭 16 件 (1801c5e84 vm0・27 件):

`1c5e84 → 1c5eb8 → 1c0b6c → 1c0b71 → 1c0b8c → 1bafb0 → 1c20c8 → 1c2109 → 1c3dc8 → 1c38c8 → 1c3a81 → 1c3e00 → 1c3e0e → 1c0ba8 → 1c5eb8 → 1c0b6c …`

- `1c0b6c` → `1c0b71` → `1c0b8c` → `1c0ba8` が vm0 で反復して現れる (`1c0b6c` は 1c0b6f の je を含む block)。
- u16 の block 列は `1c5e84 → 1c5eb8 → 1c0b6c → 1c0b71` で trap する (`wasm_trap`)。

## 4. native と IR block の対応 (block 単位)

`results/ld64/block_coverage.py` (入力: `tools/ott/work/ott.ll`・`results/ld57/insn_*.txt`) の出力は LD-64 と同じ値を再現した。

| 関数 | pattern | 命令 | distinct rva | block label 一致 | 一致率 |
|---|---|---|---|---|---|
| 1ab1d0 | vm0 | 40 | 35 | 4 | 11.4% |
| 1ab258 | vm0 | 41 | 36 | 4 | 11.1% |
| 1c5e84 | vm0 | 74 | 38 | 6 | 15.8% |
| 1c621c | vm0 | 998 | 95 | 9 | 9.5% |
| 1c682c | vm0 | 112 | 52 | 13 | 25.0% |
| 1c69cc | vm0 | 1028 | 112 | 14 | 12.5% |

(u16 も同じ傾向。LD-64 の「9.5〜25.5%」の範囲と一致。)

native `1c0b6f` (je) と `1c0b82` (HeapFree の call) の位置:
- IR に `dec_label_pc_1801c0b6c:` (ott.ll 11881 行) と `dec_label_pc_1801c0b71:` (11886 行)、次の label `1c0b8c` (11897 行) がある。
- `1c0b6f` は block `1c0b6c` の範囲 (label `1c0b6c` と `1c0b71` の間)。
- `1c0b82` は block `1c0b71` の範囲 (label `1c0b71` と `1c0b8c` の間)。
- 対応は **IR label の address 順による推定**。命令単位の wasm trace が無いので、block 内のどの命令かは示していない (受入条件 2 の残り)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 命令単位の wasm trace (IR に元の VA を残す lifter 側の変更、または rva 対応表) | native `1c0b6f`・`1c0b82` の wasm 側の位置を命令単位で示せない (受入条件 1・2 の残り) | 子 issue (本 PR で起票) |
| 残り 5 関数 (1ab1d0・1ab258・1c621c・1c682c・1c69cc) の native 命令との対応 | block 列は取れたが分岐点の特定は未了 (受入条件 3) | 子 issue (同上) |
| u16 の trap (`wasm_trap`) の block 列 | u16 は `1c0b71` で止まるため、後続の block 対応が取れない | LD-64 既存の未解決 (子 issue に含める) |

## 6. 測定 commit と差分

- 測定 commit: `0e5b184c`。
- `git diff 0e5b184c HEAD -- tools/liftdiff/rt tools/liftdiff/ldlib` は **0 件** (本 PR は REPORT のみ変更)。
