# REPORT 付録 — #5311 (GUI-27): boot の icall miss `0xfa9390` の呼出元・InitTable 添字・B1 への寄与

REPORT の §7 残件 (`0xfa9390`) の切り分け。判定式は変更していない。要約は [REPORT.md](REPORT.md) §6j・§7 を参照。

## 1. 呼出元 (コード)

- `tools/m11/m11_ov.c` 299 行: `ICALL_AT(0x412126, proc, ...)` (`function_4120c0` = System.InitUnits の strict ループ)。miss のとき `g_units_skipped` が 1 増え、unit の init は実行されない (300 行)。
- `tools/m11/m11_ov.c` 272 行: `m11_call_unit_at` (寛容起動の 1 unit)。同じ site `0x412126` を使う。
- 寛容起動の経路 (`g_tolerant`) では `m11_tolerant_hook` が JS 側 `Module.m11_tolerant_run` を呼ぶ。

## 2. InitTable 添字 (静的読解)

- InitTable: RVA `0xf768b0`、count `942`、units 配列 RVA `0xf768e0` (`tools/m11/work/m11_image.bin` の静的読解。再現: [inittable_find.py](inittable_find.py))。
- proc `0xfa9390` になる添字は全 46 件。boot の初期化範囲 (添字 `0`〜`110`) では **4 件 (`29`・`38`・`39`・`105`)**。これは静的読解の候補であり、実行計数と未照合。
- 再実行 (head `32c42dd7d`・素材 `work/m11_image.bin` あり): `python3 tools/gui/flengine/inittable_find.py` は **rc 0**・count 942・全 46 件・boot 範囲 4 件。出力は上と同じ。
- boot 実測の `icall_miss 4` は全 icall サイトの合計で、InitUnits ループの skip 件数とは別の計数。両者が同じ値になるかは確認していない。
- 実測の `units_run 110` (`init_count 111`) との整合は未確認。コード上 `units_run` は miss の無かった unit、`g_units_skipped` は miss のあった unit を数える (`m11_ov.c` 299〜301 行)。`icall_miss` は全 icall サイトの miss 合計で、loop の skip とは計数が別。Halt0 が 1 件あるため、ループが途中で打ち切られた可能性もあり、`111 − n` の単純な計算が成り立つかは未確認。
- 静的候補 4 件 (添字 29・38・39・105) が全て loop で呼ばれるなら skip は 4 件になり、`units_run 110` と合わない。この不整合は未解決 (下の表)。

## 3. B1 への寄与 (現 head の実測)

測定 commit `32c42dd7d` (本 PR の head)・`e2e.sh` foreground 1 回・real 8 分 54 秒。詳細は [REPORT.md](REPORT.md) §6j。

| 経路 | GetMem | icall_miss 対象 | 備考 |
|---|---|---|---|
| baseline (shim 無し・`-pthread`) | 772 | `0xfa9390` | `units_run 110`・`icall_miss 4` |
| boot_ff (GUI あり) | 774 | `0xfa9390` | `reached 26` (impl 26 / stub 0) |
| boot_plain (到達ログ無し) | 774 | `0xfa9390` | 到達ログ無し (`reach` 欄なし) |

- miss 集合は GUI あり/なしで一致し、`0xfa9390` の 1 件 (GUI に依存しない)。
- B1 の FAIL は `GetMem 774 (base 772)` のみ。plain も 774 のため、差は到達ログの有無では出ない。shim が増やす 2 件の原因は未切り分け (GUI-25 の未解決)。
- 「B1 寄与 0」は、この実測が示す範囲 (miss 集合が GUI で変わらない) でのみ言える。B1 の GetMem 差そのものを GUI 起因と切り分けたわけではない。
- judge の判定式は無変更。

前 run (#4730、commit `cfd295fa1`) のコメント値は現 head の証拠として使わない。

## 4. 範囲外・未測定

- skip された unit init が FL の出力 (起動後の状態) に与える**絶対の影響は未測定**。受入は起動・B1 判定への影響であり、B1 寄与は §3 で実測済み。絶対影響は本 issue の範囲外とする (PM 判断・#5311 コメント)。
- 添字 4 件と実際に skip された unit の対応 (§2 の注) は未確認。
