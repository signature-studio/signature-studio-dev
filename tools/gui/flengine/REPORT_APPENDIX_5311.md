# REPORT 付録 — #5311 (GUI-27): boot の icall miss `0xfa9390` の呼出元・InitTable 添字・B1 への寄与

REPORT の §7 残件 (`0xfa9390`) の切り分け。判定式は変更していない。要約は [REPORT.md](REPORT.md) §6j・§7 を参照。

## 1. 呼出元 (コード)

- `tools/m11/m11_ov.c` 299 行: `ICALL_AT(0x412126, proc, ...)` (`function_4120c0` = System.InitUnits の strict ループ)。miss のとき `g_units_skipped` が 1 増え、unit の init は実行されない (300 行)。
- `tools/m11/m11_ov.c` 272 行: `m11_call_unit_at` (寛容起動の 1 unit)。同じ site `0x412126` を使う。
- 寛容起動の経路 (`g_tolerant`) では `m11_tolerant_hook` が JS 側 `Module.m11_tolerant_run` を呼ぶ。

## 2. InitTable 添字 (静的読解)

- InitTable: RVA `0xf768b0`、count `942`、units 配列 RVA `0xf768e0` (`tools/m11/work/m11_image.bin` の静的読解。再現: [inittable_find.py](inittable_find.py))。
- proc `0xfa9390` になる添字は全 46 件。boot の初期化範囲 (添字 `0`〜`110`) では **4 件 (`29`・`38`・`39`・`105`)**。これは静的読解の候補であり、実行計数と未照合。
- boot 実測の `icall_miss 4` は全 icall サイトの合計で、InitUnits ループの skip 件数とは別の計数。両者が同じ値になるかは確認していない。
- 実測の `units_run 110` と、111 件のループから skip 4 件を引いた 107 との整合も未確認 (付録末尾の未解決を参照)。

## 3. B1 への寄与 (実測・前 run の記録)

前 run (#4730、2026-10-15 17:52Z のコメント) の測定。commit `cfd295fa1`・`e2e.sh` foreground 1 回。

- miss 先は `0xfa9390` のみ (4 件)。GUI あり/なしで miss unit 集合は一致する。
- B1 の FAIL は `GetMem 774 (base 772)` のみ。寄与は 0。
- icall 比較は 4 = 4 で PASS。判定式は無変更。

注: 前 run の追記 commit `f864b8b1f` は push されておらず、この clone にも無い。上の値はコメントの実測値を再掲したもの。head `1fc8900b3` での再実行は未実施 (素材 `work-m11`・`toolchain-*`・`apt-mingw` が run の `ARTIFACTS_DIR` に無く、e2e を回せなかった)。したがってこの節は**未再現**であり、§3 は現 head の証拠ではない。

## 4. 範囲外・未測定

- skip された unit init が FL の出力 (起動後の状態) に与える**絶対の影響は未測定**。受入は起動・B1 判定への影響であり、B1 寄与は §3 で実測済み。絶対影響は本 issue の範囲外とする (PM 判断・#5311 コメント)。
- 添字 4 件と実際に skip された unit の対応 (§2 の注) は未確認。
