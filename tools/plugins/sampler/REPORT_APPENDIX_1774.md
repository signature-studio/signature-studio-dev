# sampler REPORT 付録 (#1774 [PLG-F3-14])

> 正本: `tools/plugins/sampler/REPORT.md` §7。 本書は VEX comis/ucomis の flag 反映 (#1774) の実測。 方式の決定は DECISIONS D15 (続き)。

### 7c. [PLG-F3-14] VEX comis/ucomis の flag 反映 (測定 commit `8168426f`)

- **実装**: `tools/plugins/lift/passes/vex_comis_flags.py` を `lift_ranges.sh` の `fix_avx256` の後・`m11_simd2` の前に追加。 同一ブロック内で呼び出し後に読まれる `%cf/zf/pf.N.reload` (ブロック先頭の load = 古い値) を、呼び出し直後の fcmp 由来の flag (CF = lt∨uno, ZF = eq∨uno, PF = uno) に差し替える。 呼び出し自体は残す (helper は未実装 stub のまま unimpl に出る)。 対象は `vcomis*`/`vucomis*` のみ (非 VEX は範囲外)。
- **fail-open の修正** (`16a8af8f`): `625be6bb` までの `lift_ranges.sh` は `vex_comis_flags.py ... && mv ...` だった。 `set -e` は `&&` の左辺の失敗を止めないため、pass が落ちても未反映の `final.ll` が黙って後段へ渡っていた。 2 行に分けて停止するようにした。 確認は §7c.4。
- **測定** (`bash tools/plugins/sampler/engine_lift.sh <block>`、コミット済み `8168426f`。 summary.csv の列順は `engine_lift.sh` 49 行目 (列 6 = unimpl、列 10 = lift_s)):

| engine | summary.csv | unimpl | emcc -c rc (素 / fixcmp 後 / f80 後) | pass の件数 | lift 時間 |
|---|---|---|---|---|---|
| 19252 | `19252,522,0,551,1,4,1,0,1,11,2,165,0,29,549,0` | 4 (vcomisd・vmovsd・vucomisd・vucomiss) | 1 / 1 / 0 | calls 11, sites 1, replaced_uses 1 | 12.6 s |
| 19048 | `19048,1658,0,1712,0,4,0,0,0,46,2,97,0,54,1710,0` | 4 (vcomisd・vcomisd__22・vucomisd・vucomiss) | 0 / 0 / 0 | calls 9, sites 0 | 48.4 s |

- **pass の stderr 統計 (6 項目)**: 行の形式は `[vex_comis_flags] calls … sites … replaced_uses … xblk_uses … other_flag_refs … skip …`。 `calls` / `sites` / `replaced_uses` は `8168426f` の測定の転記 (本 run では再測定していない)。 `uses` と `xblk` は sites=0 のとき数えない (コード上、差し替えの経路の中でだけ加算) ので 0。

| engine | calls | sites | replaced_uses | xblk_uses | other_flag_refs | skip |
|---|---|---|---|---|---|---|
| 19252 | 11 | 1 | 1 | 未測定 | 未測定 | 未測定 |
| 19048 | 9 | 0 | 0 (sites=0) | 0 (sites=0) | 未測定 | 未測定 |

  - 19252 の残り 10 件 (flag 参照の差し替え外) と 19048 の残り 9 件の内訳 (`xblk` と `other` の件数) は未測定。 子 [PLG-F3-33] の前提なので、次の再測定で埋める。
- **変更前 (base) との比較は未了**。 本 run では base の summary を取れなかった (RetDec・emsdk が runner に無く、素材は `fl-win64` のみ)。 既存の基準行 `tools/plugins/sampler/REPORT_APPENDIX_1834.md` 24 行 (測定 commit `425d40c8`) の 19252 は `19252,522,0,551,1,5,1,0,1,16,2,165,0,29,549,0` で、列 6 (unimpl) が 5 → 4 と異なる。 main 側の変更か本 pass の影響かは切り分けていない。 よって「変更前と同一」とは書けない。 19048 は sites=0 で pass が IR を変えない (差し替えも挿入もしない) ため、summary の比較は省略する。
- **測定の鮮度 (未了)**: `8168426f` の後に lift 経路のコード変更が 2 件ある。 `625be6bb` (テスト追加。 実行経路の外) と `16a8af8f` (fail-open 修正。 実行コードの変更)。 `docs/WORKFLOW.md` §6 により後者は再測定が要るが、本 run では実施できなかった。 差分 (`git diff --stat 8168426f HEAD -- tools/plugins/lift tools/plugins/sampler/engine_lift.sh`):

```
 tools/plugins/lift/lift_ranges.sh                 |  5 ++-
 tools/plugins/lift/passes/test_vex_comis_flags.py | 45 +++++++++++++++++++++++
 2 files changed, 48 insertions(+), 2 deletions(-)
```

- **差し替えの実例** (19252, `0x18001a934` の `vcomisd xmm6, [rip+..]` → `je`): IR の `br i1 %zf.0.reload` を `br i1 %vc42654zf` に変更。 機械語の `je` (ZF=1 で分岐) と一致。 emcc は rc 変わらず。
- **受入条件の対応** (`8168426f` の測定時点): (1) unimpl から `vcomisd`・`vucomisd`・`vucomiss` は消えず (呼び出しを残したため)、未達。 (2) DECISIONS D15 に反映方式を記録 — 達成。 (3) `emcc -c` rc 0 の確認 — 19048 は全段 0 (#1834 CLOSED で `%arg2` の型不整合は解消済み)、19252 は f80 後 0。 `8168426f` の測定での達成。 修正後の再確認は未了。 (4) engine_lift の実測を本書に残す — 達成。

### 7c.1 機械語の消費命令と IR の参照 (方式の根拠)

- 機械語 (`tools/plugins/sampler/vex_comis_consumers.py`、ranges 全関数): 19252 は VEX comis 14 箇所、19048 は 12 箇所。 呼び出し直後に flag を読む命令は全箇所にある。 内訳 (19252): `vcomisd→je` 3・`jb` 2・`jbe` 1・`ja` 1・`jae` 1・`cmovae` 1 / `vucomisd→ja` 1・`jbe` 1 / `vucomiss→cmovne` 2・`jne` 1。 (19048): `vcomisd→je` 3・`jbe` 2・`jae` 1・`jb` 1 / `vucomisd→ja` 1・`jbe` 1 / `vucomiss→cmovne` 2・`jne` 1。
- IR (`e.final.ll`) の呼び出し: 19252 は 11 件、19048 は 9 件。 機械語の件数との差 (3 件・3 件) は欠落 range (`missing_define`) の外とみられるが、アドレスの対応は取っていない (未確認)。 原因も未確認。
- IR の消費側: 同一ブロック内に flag 名 (`%cf/zf/pf.N.reload`) の参照があるのは 19252 の 1 件 (差し替え済み)。 19048 は 0 件。 残りは `br i1 %479` (`icmp eq i64 %478, 0`)・`br i1 %539` (`icmp eq i64 %524, 4611686018427387904`) 等の値比較で、flag と無関係に見える。 よって flag の差し替えでは反映できず、消費条件を機械語から再導出する必要がある (子 [PLG-F3-33])。

### 7c.2 別案の実測 (不採用)

- icall の stub+sahf 経路 (`PLUG_ICALL=1 bash tools/plugins/sampler/engine_lift.sh 19252`): summary `19252,522,0,497,1,1,1,0,1,25,32,4200,0,0,497,0`。 unimpl 4→1 (残 `vmovsd__26`)、`defines` 551→497、`missing_define` 2→32、`missing_bytes` 165→4200、emcc 素 rc 1 (f80 後 0)。 `icall_rewrite.py` は 522 関数中 490 関数を memory-ABI に書き換える (`rewrote 490 funcs ... abi dcall 1160`)。 comis だけの差し替えにならないため不採用。

### 7c.3 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| VEX comis の残り (19252: 10 件、19048: 9 件) の消費側が flag 名を読まない | unimpl 3 種が残る。 stub は 0 返却で silent な flag 欠落 | 子 [PLG-F3-33] |
| IR に出ていない VEX comis (19252: 3 件、19048: 3 件、欠落 range の外とみられる。 アドレス未確認) | 同上 | 子 [PLG-F3-33] (受入に含める) |
| 非 VEX の comiss/comisd/ucomiss/ucomisd (19252: 52 呼び出し) は stub のまま unimpl にも出ない | silent な flag 欠落 (unimpl 検出に掛からない) | 子 [PLG-F3-34] |
| `lift_ranges.sh` 経由の他 plugin の lift 結果 | 同一ブロック内の VEX comis flag 読みを持つ plugin は IR が変わり得る。 本 PR では 2 engine しか測っていない | 子 [PLG-F3-33] の受入 (再測定) に含める |
| `16a8af8f` 以降の再測定 (19252 / 19048 の summary・base との比較・stats 6 項目の残り) | 測定の鮮度が切れている。 base との同一性は未確認 | 本 PR の次の review run (PR 本文の `oc_artifacts` で素材を取得して実施) |

### 7c.4 fail-open の修正の確認と限界 (review 指摘への対応)

- **fail-open の確認** (RetDec を使わない。 `PLUG_REUSE_DRC=1` で合成の `drc.ll` から後段だけを実行。 pass を rc 3 で失敗させる stub を入れて比較):
  - `625be6bb` の `lift_ranges.sh`: rc 0 で続行し、`_simd.c` まで出力された (fail-open の再現)。
  - `16a8af8f` の `lift_ranges.sh`: rc 3 で停止し、`_simd.c` は出力されない。
  - `16a8af8f` + 本物の pass: rc 0。 stderr は `calls 1 sites 0 replaced_uses 0 xblk_uses 0 other_flag_refs 1 skip 0`。 合成入力では上流の pass が reload を `xor i1 0, 0` に畳んだため差し替えは起きなかった。 実 IR での形は未確認。
  - 注: 合成入力での確認であり、19252 / 19048 の e2e 実測ではない。
- **テスト**: `python3 tools/plugins/lift/passes/test_vex_comis_flags.py` (成功時 `ok: test_vex_comis_flags`)。 CI のどのワークフローからも呼ばれていない (`.github` 内に参照は無い)。 テストは「reload がブロック先頭にある」前提で書かれている。 実 IR での配置は未確認。
- **限界**:
  - (a) SF/OF は反映しない。 comis の結果は CF/ZF/PF のみで、SF/OF は comis の定義どおり 0 になる。 現データで SF/OF を読む箇所は未確認。
  - (b) 同一ブロック内で VEX comis の後に別の flag 書込み (非 VEX の comis など、void 呼び出し) を挟むと、後段の読みを VEX 側の値で誤って置換しうる。 現データでは未確認。
  - (c) 実 IR での reload の形は未確認 (上の合成入力では畳まれた)。
