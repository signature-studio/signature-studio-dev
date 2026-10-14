# 付録: liftdiff LD-41 (#1238) — 型 C・D の P3 (未特定) の個別確認

> **正本**: `tools/liftdiff/REPORT.md`。本書は LD-41 の節を分割して置いたもの。集計の正本は `results/m11_unreachable_cd.md`。

#### 0x417b70 の静的確認 (受入条件 1 の一部・動的未確認)
- 測定 commit = 本 PR の commit (`trace_diverge_cd.py` 16.99 s・`PE=block00031_PE.bin` (fl-win64)・`batch_closure.jsonl`・`boot_final3.ll` (work-m11))。
- 機械語 `417c54` `cqo` → `417c56` `idiv qword ptr [rbp+0x60]` (符号付き)。IR の対応箇所は `boot_final3.ll` 125366 行目 `%29 = udiv i64 %28, %arg4` (符号なし)。`417c5a` の `cmp rax, [rbp+0x48]` → `417c5e` の `je` が IR の `icmp eq`・`br` に対応し、偽のとき `417c60` の `call 0x409730` が IR 125368〜125372 行の `unreachable` に対応する。
- 除算の入力: 被除数 = stride (`[rbp+0x48]`・32bit 符号拡張の値) × count (`[rbp+0x60]` = `*r9`)、除数 = count。count は `417bb8`〜`417bbd` で `> 0` が保証された後の値。
- 次 entry の組 (32 件のうち trace_head で L = 0x417b70 の件・`results/m11_unreachable_cd.md` の末尾表): native 側は 0x409470 (18)・0x409410 (11)・0x418190 (3)、wasm 側は 0x409410 (15)・0x409730 (17)。wasm 側で trap helper 0x409730 に直接入った件数は 17 件 (組で見ると (0x409410, 0x409730) 11 件・(0x409470, 0x409730) 4 件・(0x418190, 0x409730) 2 件)。
- **未確認**: stride の符号と trap 経路への実入場 (trace_head は関数入口 VA のみで、除算の入力値は記録されていない)。sdiv 修正後に食い違いが消えるかの再実行も未実施。
