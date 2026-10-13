# icall REPORT 付録 (#1067 ICALL-20): Fresh Air 残落ち 6 件の段別分類

`REPORT_APPENDIX.md` は 250 行上限 (257 行) のため、本節は別置き。親: `REPORT.md` §13 (#1026)。

測定 HEAD: `c4e93550` (`tools/icall` は `origin/main` `ca0f59a1` まで差分 0)。
素材: `work-icall` (`tools/icall/work/rt_freshair-core/`)・`plugins-freshair` (`fetch.sh` で win 17 files・factory .epf 8)。

## 1. 結論

- 残落ち 6 件 (非 IAT・`call [rax+disp]`) は**復元 pass ではなく RetDec 段の出力で既に欠落**している。
- 2 関数で欠落の形が異なる。
  - `0x180c97aa0` (4 件): 制御分岐が `br i1 undef` になり、call を含むブロックが before IR に残っていない。
  - `0x180da6e60` (2 件): 該当ブロックの load・比較・分岐は残るが、vtable call の IR 命令が無い。
- 原因は未確定 (推定を含む)。RetDec の undef 化の条件は未特定。wasm 実行と native 差分は未実施。

## 2. 実測

| 指標 | 復元前 `audit_before.json` | 復元後 `audit_after.json` |
|---|--:|--:|
| `call_total` | 123 | 123 |
| `call_lost_non_iat` | 87 | 6 |
| `call_dropped` | 80 | 5 |
| `call_other` (`other_insn`) | 7 | 1 |

再現コマンド: `python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core` (即時)。
出力: `non-IAT call sites 91 / lost 6 (audit call_lost_non_iat=6)`、`by IR status: {'other_insn:br': 1, 'dropped': 5}`。

| 関数 | VA | 命令 | IR 状態 | 段別の所見 |
|---|---|---|---|---|
| `0x180c97aa0` | `0x180c97e17` | `call [rax+0x10]` | other_insn:br | RetDec dsm に存在。before.ll の `dec_label_pc_180c97e1a` は `br i1 undef` (call を含むブロックは IR に無い) |
| 同 | `0x180c97e38` | `call [rax+0x20]` | dropped | before.ll の `dec_label_pc_180c97e27`・`e2f` が `br i1 undef` 由来の分岐。call 命令は無い |
| 同 | `0x180c97e56` | `call [rax+0x8]` | dropped | before.ll の `dec_label_pc_180c97e4e`・`e53` が `br i1 undef` 由来の分岐。call 命令は無い |
| 同 | `0x180c97e71` | `call [rax+0x20]` | dropped | before.ll の `dec_label_pc_180c97e53`・`e7c` が `br i1 undef` 由来の分岐。call 命令は無い |
| `0x180da6e60` | `0x180da7261` | `call [rax+0x30]` | dropped | `dec_label_pc_180da7261` に load・icmp・`store i128` あり。call の IR 命令が無い |
| 同 | `0x180da72fc` | `call [rax+0x30]` | dropped | `dec_label_pc_180da72fc` に `store`・`br` あり。call の IR 命令が無い |

## 3. 切り分けの根拠

- RetDec dsm (`before.0.drc.dsm`) に 6 件とも `call qword ptr [rax+disp]` が存在する (`0x180c97e17`・`0x180c97e38`・`0x180c97e56`・`0x180c97e71`・`0x180da7261`・`0x180da72fc`)。命令の読み落としではない。
- `before.0.drc.ll` 内の `dec_label_pc_180c97de0`〜`e7c` の範囲では、分岐条件が `br i1 undef` のブロックが並ぶ (2885〜2921 行)。`0x180da6e60` 側の該当ブロック (5114〜5165 行) は `undef` ではなく具体的な比較を持つ。
- 復元 pass の `rewrote 131 funcs, 98 sites` は 6 件を含まない (`rewrite.txt`)。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x180c97aa0` の `br i1 undef` 化の原因 (RetDec 段) | 4 件の欠落 | 子 issue ICALL-24 (#1067 の子) |
| `0x180da6e60` の vtable call IR 落ち (IR 命令の欠落) の原因 | 2 件の欠落 | 子 issue ICALL-24 (#1067 の子) |
| Fresh Air SlateCore closure の wasm 実行と native 差分・native ハーネス新設 | 出力 bit 一致は未確認 | 子 issue ICALL-25 (#1067 の子) |
