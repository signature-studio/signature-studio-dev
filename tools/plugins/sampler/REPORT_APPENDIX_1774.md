# sampler REPORT 付録 (#1774 [PLG-F3-14])

> 正本: `tools/plugins/sampler/REPORT.md` §7。 本書は VEX comis/ucomis の flag 反映 (#1774) の実測。 方式の決定は DECISIONS D15 (続き)。

### 7c. [PLG-F3-14] VEX comis/ucomis の flag 反映 (測定 commit `a4e22079`)

- **実装**: `tools/plugins/lift/passes/vex_comis_flags.py` を `lift_ranges.sh` の `fix_avx256` の後・`m11_simd2` の前に追加。 同一ブロック内で呼び出し後に読まれる `%cf/zf/pf.N.reload` (ブロック先頭の load = 古い値) を、呼び出し直後の fcmp 由来の flag (CF = lt∨uno, ZF = eq∨uno, PF = uno) に差し替える。 呼び出し自体は残す (helper は未実装 stub のまま unimpl に出る)。 対象は `vcomis*`/`vucomis*` のみ (非 VEX は範囲外)。
- **fail-open の修正** (`16a8af8f`): `625be6bb` までの `lift_ranges.sh` は `vex_comis_flags.py ... && mv ...` だった。 `set -e` は `&&` の左辺の失敗を止めないため、pass が落ちても未反映の `final.ll` が黙って後段へ渡っていた。 2 行に分けて停止するようにした (120–122 行目)。 合成入力での確認は §7c.4。
- **測定** (現 head `a4e22079`): `bash tools/plugins/sampler/engine_lift.sh <block>` を前景で実行。 base は `573a4697` (PR の merge-base) を detached worktree に展開し、同じ素材・同じ手順で実行。 素材は `fl-win64` (R2)。 RetDec は `/opt/retdec/bin/retdec-decompiler`、emsdk は `/opt/emsdk` (runner の既存。 `toolchain-retdec`・`toolchain-emsdk` は展開していない)。 summary.csv の列順は `engine_lift.sh` 49 行目 (列 6 = unimpl、列 10 = lift_s)。

| engine | 版 | summary.csv | unimpl (列 6) | emcc -c rc (素 / fixcmp 後 / f80 後) | lift_s (列 10) |
|---|---|---|---|---|---|
| 19252 | head `a4e22079` | `19252,522,0,551,1,4,1,0,1,16,2,165,0,29,549,0` | 4 | 1 / 1 / 0 | 16 |
| 19252 | base `573a4697` | `19252,522,0,551,1,4,1,0,1,16,2,165,0,29,549,0` | 4 | 1 / 1 / 0 | 16 |
| 19048 | head `a4e22079` | `19048,1658,0,1712,0,4,0,0,0,63,2,97,0,54,1710,0` | 4 | 0 / 0 / 0 | 63 |
| 19048 | base `573a4697` | `19048,1658,0,1712,0,4,0,0,0,63,2,97,0,54,1710,0` | 4 | 0 / 0 / 0 | 63 |

- 履歴: 旧 head `8168426f` の測定では 19252 が `19252,522,0,551,1,4,1,0,1,11,2,165,0,29,549,0` (lift_s 11)、19048 が `19048,1658,0,1712,0,4,0,0,0,46,2,97,0,54,1710,0` (lift_s 46)。 lift_s 以外の列は現 head と同一。 「現 head の値」としては使わない。
- head と base の summary は全列で一致。 19252 の unimpl 4 種は `vcomisd`・`vmovsd`・`vucomisd`・`vucomiss` (呼び出しを残したため `vcomisd` は消えない)。
- 19252 の unimpl は `REPORT_APPENDIX_1834.md` 24 行 (測定 `425d40c8`) では 5 だった。 base `573a4697` でも 4 のため、5 → 4 は本 PR の影響ではなく、`425d40c8` から `573a4697` までの main 側の変更による (変更の commit は未特定)。

- **pass の stderr (6 項目)**: 行の形式は `[vex_comis_flags] calls … sites … replaced_uses … xblk_uses … other_flag_refs … skip …` (`lift.log`)。

| engine | calls | sites | replaced_uses | xblk_uses | other_flag_refs | skip |
|---|---|---|---|---|---|---|
| 19252 | 11 | 1 | 1 | 0 | 0 | 0 |
| 19048 | 9 | 0 | 0 | 0 | 0 | 0 |

  - `xblk_uses` は差し替えた site の後続ブロックにある flag 名の参照数。 `other_flag_refs` は差し替えなかった参照 (差し替えなかった呼び出しの後ろの同一ブロック内の参照を含む)。
  - 19252 の残り 10 件、19048 の残り 9 件は、同一ブロック内の後ろに flag 名の参照が無い (`other_flag_refs` 0)。 `xblk_uses` は差し替えた site 分しか数えないため、残りの件の後続ブロックは stats では数えていない。 それは次の IR 上の確認で補う。
  - **IR 上の確認** (ad hoc。 コミットしていない。 規則: 各 `call void @__asm_v[u]comis[sd]` の後ろ (同じ関数内・テキスト順) に `%(cf|zf|pf).N.reload` の参照があるか): 19252 は head の 11 呼び出しのうち 0 件 (base `573a4697` では 1 件 = 差し替えた site)、19048 は 9 件中 0 件。 残りの呼び出しの消費側は flag 名を読まず、比較の結果 (`icmp` 等の値) を読む。 テキスト順なので、ループの back-edge で前に置かれた読みは数えていない。 子 [PLG-F3-33] の前提 (消費側が flag 名を読まない) と整合する。
- **IR の差分 (19252、base → head)**: `e.final.ll` は base 46162 行、head 46171 行。 差分は (1) pass の追加 9 行 (`%vc42654*`、comis の直後)、(2) `br i1 %zf.0.reload` → `br i1 %vc42654zf` の 1 行置換 (機械語 `0x18001a934` の `vcomisd` → `je` と一致)、(3) 36814–36819 行の `stack_var_24`/`stack_var_32` の bitcast の順 (6 行)。 (3) は pass より前の段でも出ており (`e.drc.ll` の `uselistorder` 行 820 行目などに差がある)、pass の変更ではない。 原因 (作業ディレクトリか RetDec の出力順の非決定性か) は未確認。 同じ worktree の 2 run は互いに一致 (head の 2 run: 差 0 行、base の 2 run: 差 0 行)。 reviewer が報告した「head の 2 run で 36814 行が異なる」は、この run では再現しなかった。
- **IR の差分 (19048)**: `e.final.ll` は base と `cmp` で一致 (IR 不変。 sites 0)。

**差分の証跡** (`docs/WORKFLOW.md` §6。 測定 commit `a4e22079`):

```
$ git diff --stat 8168426f a4e22079 -- tools/plugins/lift tools/plugins/sampler/engine_lift.sh
 tools/plugins/lift/lift_ranges.sh                 |  5 ++-
 tools/plugins/lift/passes/test_vex_comis_flags.py | 45 +++++++++++++++++++++++
 2 files changed, 48 insertions(+), 2 deletions(-)
```

実行経路の変更は `lift_ranges.sh` の 5 行 (`16a8af8f`、fail-open 修正) のみ。 `test_vex_comis_flags.py` は実行経路の外。 測定 commit `a4e22079` から HEAD までの後続 commit は REPORT と PR 本文のみで、コード差分は 0 (`git diff a4e22079 HEAD -- tools/plugins/lift tools/plugins/sampler/engine_lift.sh` は空)。

- **差し替えの実例** (19252, `0x18001a934` の `vcomisd xmm6, [rip+..]` → `je`): IR の `br i1 %zf.0.reload` を `br i1 %vc42654zf` に変更。 機械語の `je` (ZF=1 で分岐) と一致。 emcc は rc 変わらず。
- **受入条件の対応** (現 head): (1) unimpl から `vcomisd`・`vucomisd`・`vucomiss` は消えない (呼び出しを残したため)。 非達成。 残りは子 [PLG-F3-33] に移した。 (2) DECISIONS D15 に反映方式を記録 — 達成。 (3) `emcc -c` rc 0 の確認 — 19048 は全段 0、19252 は f80 後 0 (`a4e22079` で再確認)。 (4) engine_lift の実測を本書に残す — 達成 (現 head と base)。

### 7c.1 機械語の消費命令と IR の参照 (方式の根拠)

- 機械語 (`tools/plugins/sampler/vex_comis_consumers.py`、ranges 全関数): 19252 は VEX comis 14 箇所、19048 は 12 箇所。 呼び出し直後に flag を読む命令は全箇所にある。 内訳 (19252): `vcomisd→je` 3・`jb` 2・`jbe` 1・`ja` 1・`jae` 1・`cmovae` 1 / `vucomisd→ja` 1・`jbe` 1 / `vucomiss→cmovne` 2・`jne` 1。 (19048): `vcomisd→je` 3・`jbe` 2・`jae` 1・`jb` 1 / `vucomisd→ja` 1・`jbe` 1 / `vucomiss→cmovne` 2・`jne` 1。
- IR (`e.final.ll`) の呼び出し: 19252 は 11 件、19048 は 9 件。 機械語の件数との差 (3 件・3 件) は欠落 range (`missing_define`) の外とみられるが、アドレスの対応は取っていない (未確認)。 原因も未確認。
- IR の消費側: 同一ブロック内に flag 名 (`%cf/zf/pf.N.reload`) の参照があるのは 19252 の 1 件 (差し替え済み)。 19048 は 0 件。 残りは `br i1 %479` (`icmp eq i64 %478, 0`)・`br i1 %539` (`icmp eq i64 %524, 4611686018427387904`) 等の値比較で、flag と無関係に見える。 よって flag の差し替えでは反映できず、消費条件を機械語から再導出する必要がある (子 [PLG-F3-33])。

### 7c.2 別案の実測 (不採用)

- icall の stub+sahf 経路 (`PLUG_ICALL=1 bash tools/plugins/sampler/engine_lift.sh 19252`): summary `19252,522,0,497,1,1,1,0,1,25,32,4200,0,0,497,0`。 unimpl 4→1 (残 `vmovsd__26`)、`defines` 551→497、`missing_define` 2→32、`missing_bytes` 165→4200、emcc 素 rc 1 (f80 後 0)。 `icall_rewrite.py` は 522 関数中 490 関数を memory-ABI に書き換える (`rewrote 490 funcs ... abi dcall 1160`)。 comis だけの差し替えにならないため不採用。

### 7c.3 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| VEX comis の残り (19252: 10 件、19048: 9 件) の消費側が flag 名を読まない | unimpl 3 種 (`vcomisd`・`vucomisd`・`vucomiss`) が残る。 stub は 0 返却で silent な flag 欠落 | 子 [PLG-F3-33] |
| IR に出ていない VEX comis (19252: 3 件、19048: 3 件。 欠落 range の外とみられる。 アドレス未確認) | 同上 | 子 [PLG-F3-33] (受入に含める) |
| 残りの呼び出しの後続ブロックの flag 名の読み (`xblk_uses` は差し替えた site 分のみ数える) | テキスト順の確認では 0 件。 ループの back-edge で前に置かれた読みは未確認 | 子 [PLG-F3-33] |
| 非 VEX の comiss/comisd/ucomiss/ucomisd (19252: 52 呼び出し) は stub のまま unimpl にも出ない | silent な flag 欠落 (unimpl 検出に掛からない) | 子 [PLG-F3-34] |
| `lift_ranges.sh` 経由の他 plugin の lift 結果。 pass は `PLUG_AVX256` の if の外 (121 行目) にあり、`PLUG_AVX256=0` の経路 (`synth/cpp_lift.sh`・#534) でも走る。 同一ブロック内の VEX comis flag 読みを持つ plugin は IR が変わり得る。 本 PR で測ったのは 2 engine のみ。 他 plugin の REPORT の数値は未再測定 | 同上 | 子 [PLG-F3-33] (受入に他 plugin の再測定を含む) |

解消済み: `16a8af8f` 以降の再測定 (19252 / 19048 の summary・base との比較・stats 6 項目) は §7c の表で行った (現 head `a4e22079`)。

### 7c.4 fail-open の修正の確認と限界 (review 指摘への対応)

- **fail-open の確認** (RetDec を使わない。 `PLUG_REUSE_DRC=1` で合成の `drc.ll` から後段だけを実行。 pass を rc 3 で失敗させる stub を入れて比較):
  - `625be6bb` の `lift_ranges.sh`: rc 0 で続行し、`_simd.c` まで出力された (fail-open の再現)。
  - `16a8af8f` の `lift_ranges.sh`: rc 3 で停止し、`_simd.c` は出力されない。
  - `16a8af8f` + 本物の pass: rc 0。 stderr は `calls 1 sites 0 replaced_uses 0 xblk_uses 0 other_flag_refs 1 skip 0`。 合成入力では上流の pass が reload を `xor i1 0, 0` に畳んだため差し替えは起きなかった。
  - 注: 合成入力での確認であり、19252 / 19048 の e2e 実測ではない (e2e は §7c の表)。
- **テスト**: `python3 tools/plugins/lift/passes/test_vex_comis_flags.py` (成功時 `ok: test_vex_comis_flags`)。 CI のどのワークフローからも呼ばれていない (`.github` 内に参照は無い)。 テストは「reload がブロック先頭にある」前提で書かれている。 実 IR では、差し替えた 19252 の 1 site で reload がラベルと呼び出しの間にあった。 他の場合は未確認。
- **限界**:
  - (a) SF/OF は反映しない。 comis の結果は CF/ZF/PF のみで、SF/OF は comis の定義どおり 0 になる。 現データで SF/OF を読む箇所は未確認。
  - (b) 同一ブロック内で VEX comis の後に別の flag 書込み (非 VEX の comis など、void 呼び出し) を挟むと、後段の読みを VEX 側の値で誤って置換しうる。 現データでは未確認。
  - (c) 実 IR での reload の形: 19252 では実 IR に `br i1 %zf.0.reload` があり 1 箇所を差し替えた。 19048 は site 0 (ラベルから呼び出しまでに reload が無い)。 合成入力では上流の pass が reload を畳んだ。
