# PLG-F2-5 (#613) 付録: REPORT §10 全文 (ldfix の接続)

`REPORT.md` の 250 行上限のため、§10 を無変更で分割移動した (#2726、内容は削除しない)。§10.1 は `REPORT_APPENDIX_871.md`。

## 10. PLG-F2-5 (#613): #232 (LD-1) `ldfix` の接続 (opt-in `PLUG_LDFIX=1`)

受入条件 1 は**未達** (不一致 6 のまま)。受入条件 3 は**部分判定**: #232 の F2 (`spill_slot_deref`) 修復は適用できる。

- 接続: `lift_ranges.sh` に opt-in `PLUG_LDFIX=1` (既定 0) を追加。`tools/m11/ldfix/ldfix.py` を `fix_xmm_args` の前段に挿入。既定鎖は不変。
- 対照 (同一鎖・同一 6 block・`leaf_diff.sh` 1 回ずつ。A = `PLUG_XMMARG=1`、B = A + `PLUG_LDFIX=1`):

| arm | 最終判定 (23 関数) | 最終 mismatch のタグ | `leaf_diff` real |
|---|---|---|--:|
| A (LDFIX=0) | 一致 15 / 不一致 8 / 実行不能 0 | xmm_arg_drop 7・fp_flag_unreflected 4・arg_drop 4・spill_slot_deref 4・ret_only 1 | 137 s |
| B (LDFIX=1) | 一致 17 / 不一致 6 / 実行不能 0 | xmm_arg_drop 5・fp_flag_unreflected 4・arg_drop 2・spill_slot_deref 2・ret_only 1 | 137 s |

- A と B の差は 2 関数のみ: 0x6b0ef0 (18982) と 0x6ca5c0 (19013) が mismatch → match。両者は同一コード (`REPORT_APPENDIX.md` §8 の重複表記)。他 21 関数の判定は不変。A が対照 (pass 無し) として機能している。
- B は `ldfix` の `F2` が 4 関数 (0x6b0ef0・0x6c8c90・0x6cc2e0・0x6ca5c0) に当たり、そのうち 2 が一致に変わった。残る 0x6c8c90・0x6cc2e0 は同一コードで不一致のまま。
- 残 6 不一致: 0x6bfec0・0x6c8fc0・0x6c9b60 (no_placeholder)、0x6c8c90・0x6cc2e0 (slot_occupied + spill_slot_deref)、0x6f1650 (署名は一致だが値が届かない)。起票先は #871 ([PLG-F2-6])。
- 再現: `source tools/shared/env.sh; source tools/plugins/f2/env.sh; cd tools/plugins && PLUG_XMMARG=1 PLUG_LDFIX=1 PLUG_ICALL=0 bash lift/batch_lift.sh 18975 18982 19005 19006 19013 19059; cd ../..; bash tools/plugins/f2/leaf_diff.sh`
- 既定化 (`PLUG_LDFIX` ON 化) は未実施。全 block・全 closure での回帰は範囲外。

## 追補 (#2726): #613 の一致 2 件の再確認

- #613 B arm の一致 2 件 (0x6b0ef0・0x6ca5c0) は、現行の V1 (測定 commit 26f90ada、`PLUG_XMMARG=1 PLUG_LDFIX=1 PLUG_ICALL=0`、`leaf_diff.sh` 1 回) で再現しない。最終判定は 15/8 で、両方とも不一致。
- #871 付録 `REPORT_APPENDIX_871.md` §10.11・§10.12 (2b84c6f5・3b38f81d、LDFIX 既定 OFF) でも両方とも不一致 (残 6 に含まれる)。
- #613 B arm の測定 commit は未記録 (本付録の表に commit の欄が無く、再現コマンドは環境変数の指定のみ)。そのため、#613 の 17/6 を再現できない。
- 現行の結論: LDFIX による最終判定の変化は 0 件 (V0 15/8 = V1 15/8)。受入条件 3 の「F2 の修復は適用可」は本測定では根拠が無く、未達とする。
