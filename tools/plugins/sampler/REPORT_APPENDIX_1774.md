# sampler REPORT 付録 (#1774 [PLG-F3-14])

> 正本: `tools/plugins/sampler/REPORT.md` §7。 本書は VEX comis/ucomis の flag 反映 (#1774) の実測。 方式の決定は DECISIONS D15 (続き)。

### 7c. [PLG-F3-14] VEX comis/ucomis の flag 反映 (測定 commit `8168426f`)

- **実装**: `tools/plugins/lift/passes/vex_comis_flags.py` を `lift_ranges.sh` の `fix_avx256` の後・`m11_simd2` の前に追加。 同一ブロック内で呼び出し後に読まれる `%cf/zf/pf.N.reload` (ブロック先頭の load = 古い値) を、呼び出し直後の fcmp 由来の flag (CF = lt∨uno, ZF = eq∨uno, PF = uno) に差し替える。 呼び出し自体は残す (helper は未実装 stub のまま unimpl に出る)。 対象は `vcomis*`/`vucomis*` のみ (非 VEX は範囲外)。
- **測定** (`bash tools/plugins/sampler/engine_lift.sh <block>`、コミット済み `8168426f`。 summary.csv の列順):

| engine | summary.csv | unimpl | emcc -c rc (素 / fixcmp 後 / f80 後) | pass の件数 | lift 時間 |
|---|---|---|---|---|---|
| 19252 | `19252,522,0,551,1,4,1,0,1,11,2,165,0,29,549,0` | 4 (vcomisd・vmovsd・vucomisd・vucomiss) | 1 / 1 / 0 | calls 11, sites 1, replaced_uses 1 | 12.6 s |
| 19048 | `19048,1658,0,1712,0,4,0,0,0,46,2,97,0,54,1710,0` | 4 (vcomisd・vcomisd__22・vucomisd・vucomiss) | 0 / 0 / 0 | calls 9, sites 0 | 48.4 s |

- 変更前 (同じ summary 列) との差: 19252 は同一 (`19252,522,0,551,1,4,1,0,1,11,2,165,0,29,549,0`)。 19048 は同一 (lift_s のみ差)。 IR が変わったのは 19252 の 1 箇所だけ (下記)。
- **差し替えの実例** (19252, `0x18001a934` の `vcomisd xmm6, [rip+..]` → `je`): IR の `br i1 %zf.0.reload` を `br i1 %vc42654zf` に変更。 機械語の `je` (ZF=1 で分岐) と一致。 emcc は rc 変わらず。
- **受入条件の対応**: (1) unimpl から `vcomisd`・`vucomisd`・`vucomiss` は消えず (呼び出しを残したため)、未達。 (2) DECISIONS D15 に反映方式を記録 — 達成。 (3) `emcc -c` rc 0 の再確認 — 19048 は全段 0 (#1834 CLOSED で `%arg2` の型不整合は解消済み)、19252 は f80 後 0 (変更前と同じ)。 達成。 (4) engine_lift の実測を本書に残す — 達成。

### 7c.1 機械語の消費命令と IR の参照 (方式の根拠)

- 機械語 (`tools/plugins/sampler/vex_comis_consumers.py`、ranges 全関数): 19252 は VEX comis 14 箇所、19048 は 12 箇所。 呼び出し直後に flag を読む命令は全箇所にある。 内訳 (19252): `vcomisd→je` 3・`jb` 2・`jbe` 1・`ja` 1・`jae` 1・`cmovae` 1 / `vucomisd→ja` 1・`jbe` 1 / `vucomiss→cmovne` 2・`jne` 1。 (19048): `vcomisd→je` 3・`jbe` 2・`jae` 1・`jb` 1 / `vucomisd→ja` 1・`jbe` 1 / `vucomiss→cmovne` 2・`jne` 1。
- IR (`e.final.ll`) の呼び出し: 19252 は 11 件、19048 は 9 件。 機械語の件数との差 (3 件・3 件) は欠落 range (`missing_define`) の外にあり、RetDec 出力で呼び出しが落ちている箇所と見られる。 原因は未確認。
- IR の消費側: 同一ブロック内に flag 名 (`%cf/zf/pf.N.reload`) の参照があるのは 19252 の 1 件 (差し替え済み)。 19048 は 0 件。 残りは `br i1 %479` (`icmp eq i64 %478, 0`)・`br i1 %539` (`icmp eq i64 %524, 4611686018427387904`) 等の値比較で、flag と無関係に見える。 よって flag の差し替えでは反映できず、消費条件を機械語から再導出する必要がある (子 [PLG-F3-33])。

### 7c.2 別案の実測 (不採用)

- icall の stub+sahf 経路 (`PLUG_ICALL=1 bash tools/plugins/sampler/engine_lift.sh 19252`): summary `19252,522,0,497,1,1,1,0,1,25,32,4200,0,0,497,0`。 unimpl 4→1 (残 `vmovsd__26`)、`defines` 551→497、`missing_define` 2→32、`missing_bytes` 165→4200、emcc 素 rc 1 (f80 後 0)。 `icall_rewrite.py` は 522 関数中 490 関数を memory-ABI に書き換える (`rewrote 490 funcs ... abi dcall 1160`)。 comis だけの差し替えにならないため不採用。

### 7c.3 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| VEX comis の残り (19252: 10 件、19048: 9 件) の消費側が flag 名を読まない | unimpl 3 種が残る。 stub は 0 返却で silent な flag 欠落 | 子 [PLG-F3-33] |
| IR に出ていない VEX comis (19252: 3 件、19048: 3 件、欠落 range の外) | 同上 | 子 [PLG-F3-33] (受入に含める) |
| 非 VEX の comiss/comisd/ucomiss/ucomisd (19252: 52 呼び出し) は stub のまま unimpl にも出ない | silent な flag 欠落 (unimpl 検出に掛からない) | 子 [PLG-F3-34] |
| `lift_ranges.sh` 経由の他 plugin の lift 結果 | 同一ブロック内の VEX comis flag 読みを持つ plugin は IR が変わり得る。 本 PR では 2 engine しか測っていない | 子 [PLG-F3-33] の受入 (再測定) に含める |
