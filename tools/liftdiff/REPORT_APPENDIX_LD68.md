# liftdiff REPORT 付録: LD-68 (#1907) wasm 側 IR block trace と native 1801c5e84 系の対応付け

親 issue #1854 (LD-64)。前提は `REPORT_APPENDIX_LD64.md` §3・§7 と `REPORT_APPENDIX_LD67.md` (#1906・PR #2020)。

## 結論

- 受入条件は**部分達成**。本 PR で達成したのは「計装版の block trace を既定 build と照合して判定に使える状態にする」まで。
- **命令単位の wasm trace (受入条件 1) は未達**。IR に元の VA が無いため、lifter 側の変更が要る。子 #2192 (LD-83) に切り出す (§5)。
- native `1c0b6f` (je) と `1c0b82` (HeapFree の call) の並びは `results/ld57/insn_1801c5e84_u16.txt` で確認した (§4)。IR block との対応は IR 無しのため本 run で再検証しておらず、未検証。
- 残り 5 関数 (受入条件 3): 計装版 block 列は測定時に取れた (§3) が、native 命令との対応は未了。子 #2193 (LD-84)。
- 測定結果 (計装版と既定版の 12 case 比較) は差 0 (測定時の記録。§2)。

## 1. 測定条件

- 測定 commit: `0e5b184c` (`fix(liftdiff): record IR block trace by store, not call`。コード差分の最終 commit。`main` の `98c5f8ca` に含まれる)。
- 測定 runner: 4 vCPU・メモリ 15 GiB。load average (測定時) 0.71 / 0.51 / 0.23 (`uptime` 09:47:59Z)。
- 素材 (測定時): `work-m6-ott`・`work-liftdiff`・`plugins-ott`・`analysis-ott-binaries` を worktree (`ws-1907`) に展開。`fl-win64` は `FL_WIN64_DIR` ([WIN64]) に展開。`toolchain-emsdk` は [EMSDK] (emcc 6.0.12)。`work-liftlib`・`work-m11`・`toolchain-retdec` は測定時には使っていない。
- build: `ott_old_blk` は `work/ott_old_blk/` が素材に無かったため、`liftdiff.py run targets/ott_old_blk.json` (build あり) で再 build。`ott_old` は素材の `work/ott_old/` をそのまま使用 (`--nobuild`)。
- 実行コマンド (測定時):
  - 計装版: `python3 liftdiff.py run targets/ott_old_blk.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --json work/ld68/blk_all.json`
  - 既定版: 同上、`targets/ott_old.json`・`work/ld68/def_all.json`
  - 比較: `python3 results/ld67/compare_blk.py work/ld68/def_all.json work/ld68/blk_all.json`
- 所要 (n=1・結論には使わない): 計装版 `--nobuild --notrace` の run は 09:47:17 → 09:47:23 UTC (6 s 程度・秒単位の計測)。既定版の所要は未計測。
- **fix モード (本 run) での再測定: 不可**。`tools/ott/work/ott.ll` と `work-m6-ott` 素材が本 run の runner に無く、`work/ld68/*.json` も gitignore 対象で commit していない。よって §2・§3 の数値は測定時の記録で、本 run では再検証していない。

## 2. 既定版と計装版の比較 (測定時の記録・本 run では未再検証)

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

## 3. wasm の block 列 (1801c5e84 vm0・測定時の記録)

`blk` (計装版の記録) の先頭 16 件 (1801c5e84 vm0・27 件):

`1c5e84 → 1c5eb8 → 1c0b6c → 1c0b71 → 1c0b8c → 1bafb0 → 1c20c8 → 1c2109 → 1c3dc8 → 1c38c8 → 1c3a81 → 1c3e00 → 1c3e0e → 1c0ba8 → 1c5eb8 → 1c0b6c …`

- `1c0b6c` → `1c0b71` → `1c0b8c` → `1c0ba8` が vm0 で反復して現れる。
- u16 の block 列は `1c5e84 → 1c5eb8 → 1c0b6c → 1c0b71` で trap する (`wasm_trap`)。

## 4. native 命令と IR block の対応 (未検証)

- native 側の事実 (本 run で確認): `results/ld57/insn_1801c5e84_u16.txt` で `1c0b6f` は je、`1c0b82` は HeapFree の call で、この順に並ぶ。
- IR block との対応 (`1c0b6f` を block `1c0b6c`、`1c0b82` を block `1c0b71` の範囲に入るとする推定) は IR label の address 順による推定であり、**本 run では IR (`tools/ott/work/ott.ll`) が無いため再検証していない。結論・判定の根拠にしない**。
- `results/ld64/block_coverage.py` による native rva と IR block label の一致率は、本 PR では再現していない。`REPORT_APPENDIX_LD64.md` §4 の注記 (再現可能な出力として残っていない) を引き継ぐ。一致率の表は本 PR から外した。
- 再現に必要なもの: `blk_all.json` (6 関数 × vm0/u16 の raw)・IR `ott.ll` (`work-m6-ott` 素材で展開)・`block_coverage.py` の出力。子 #2192 (LD-83) で扱う。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 命令単位の wasm trace (IR に元の VA を残す lifter 側の変更、または rva 対応表) | native `1c0b6f`・`1c0b82` の wasm 側の位置を命令単位で示せない (受入条件 1・2 の残り) | #2192 (LD-83) |
| 残り 5 関数 (1ab1d0・1ab258・1c621c・1c682c・1c69cc) の native 命令との対応 | block 列は取れたが分岐点の特定は未了 (受入条件 3) | #2193 (LD-84) |
| u16 の trap (`wasm_trap`) の block 列 | u16 は `1c0b71` で止まるため、後続の block 対応が取れない | #2192 (LD-83)。vm0/u16 の受入条件に含める |
| §2・§3・§4 の IR 由来の検証 (`ott.ll` 無し) | 本 run で再検証不可 | 素材 `work-m6-ott` のある run で再測定 (#2192 の受入で実施) |

## 6. 測定 commit と差分

- 測定 commit: `0e5b184c`。
- 測定ビルドの入力・計測コードの差分 (本 run で確認):
  `git diff 0e5b184c HEAD -- tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt tools/liftdiff/ldlib tools/liftdiff/results/ld67/compare_blk.py tools/ott/rt tools/m6 tools/m8 tools/m9 tools/shim` は **0 件** (出力なし)。
- 本 PR の変更は `tools/liftdiff/REPORT_APPENDIX_LD68.md` と `docs/` のみ。
