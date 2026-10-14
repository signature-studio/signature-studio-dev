# 付録: liftdiff LD-41 (#1238) — 型 C・D の P3 (未特定) のうち 0x417b70 の静的確認

> **正本**: `tools/liftdiff/REPORT.md`。次 entry 組の件数の正本は `results/m11_unreachable_diverge.md` (0x417b70 の 3 行)。本書は LD-28 付録 (`REPORT_APPENDIX_LD28.md`) の 0x417b70 節を補足する新規追記で、件数は再掲しない。

#### 0x417b70 の静的確認 (受入条件 1 の一部・動的未確認)
- 機械語 (`block00031_PE.bin`・fl-win64・ImageBase `0x400000`): `417c54` `cqo` → `417c56` `idiv qword ptr [rbp+0x60]` (符号付き) → `417c5a` `cmp rax,[rbp+0x48]` → `417c5e` `je 0x417c67`。偽のとき `417c60` `mov cl,4` → `417c62` `call 0x409730` (trap helper)。
- IR: `boot_final3.ll` の `%29 = udiv i64 %28, %arg4` (符号なし・前回 run の記録では 125366 行)、続く `icmp eq`・`br`、偽側の `unreachable` (前回 run の記録では 125368〜125372 行)。
- 除算の入力: 被除数 = stride (`[rbp+0x48]`) × count (`[rbp+0x60]`)、除数 = count。count は `417bb8`〜`417bbd` で正の値が保証された後の値。
- 符号付きと符号なしで結果が一致するのは count = 1 のとき。count ≥ 2 かつ積が負なら、符号なし除算は stride を返さない (例: stride −16・count 2)。
- **未確認** (#1576 の受入条件): trap 経路 (0x409730) へ実際に入る入力の実測 (trace_head は関数入口 VA のみで除算入力を記録していない)、sdiv 修正後に食い違いが消えるかの再実行。
