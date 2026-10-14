# 付録: liftdiff LD-41 (#1238) — 型 C・D の P3 (未特定) のうち 0x417b70 の静的確認

> **正本**: `tools/liftdiff/REPORT.md`。次 entry 組の件数の正本は `results/m11_unreachable_diverge.md` (0x417b70 の 3 行)。本書は LD-28 付録 (`REPORT_APPENDIX_LD28.md`) の 0x417b70 節を補足する新規追記で、件数は再掲しない。

#### 0x417b70 の静的確認 (受入条件 1 の一部・動的未確認)
- 機械語 (`block00031_PE.bin`・fl-win64・ImageBase `0x400000`): `417c54` `cqo` → `417c56` `idiv qword ptr [rbp+0x60]` (符号付き) → `417c5a` `cmp rax,[rbp+0x48]` → `417c5e` `je 0x417c67`。偽のとき `417c60` `mov cl,4` → `417c62` `call 0x409730` (trap helper)。
- IR: `boot_final3.ll` の `%29 = udiv i64 %28, %arg4` (符号なし・前回 run の記録では 125366 行)、続く `icmp eq`・`br`、偽側の `unreachable` (前回 run の記録では 125368〜125372 行)。
- 除算の入力: 被除数 = stride (`[rbp+0x48]`) × count (`[rbp+0x60]`)、除数 = count。count は `417bb8`〜`417bbd` で正の値が保証された後の値。
- 符号付きと符号なしで結果が一致するのは count = 1 のとき。count ≥ 2 かつ積が負なら、符号なし除算は stride を返さない (例: stride −16・count 2)。
- **未確認** (#1576 の受入条件): trap 経路 (0x409730) へ実際に入る入力の実測 (trace_head は関数入口 VA のみで除算入力を記録していない)、sdiv 修正後に食い違いが消えるかの再実行。動的確認は子 issue #1767 に切り出した (LD-62 の実測は [`REPORT_APPENDIX_LD62.md`](REPORT_APPENDIX_LD62.md))。

#### P3 の残り L の静的確認 (#1576・LD-54)
- 測定 commit: `d16d7f5d` (コード変更の最後の commit)。`git diff d16d7f5d HEAD -- tools/ ':!*.md'` は出力 0 行 (変更は本 md ファイルのみ)。
- 機械語の実測 (本 run・`fl-win64` の `extracted/block00031_PE.bin`・22227016 bytes・ImageBase `0x400000`)。走査範囲は各 entry VA から最初の `ret`/`int3` まで・最大 0x600 byte の線形走査 (capstone 5.0.7、`ldlib.pe.PE` で読む):
  - `0x476c30`: 55 命令・`div`/`idiv` 0 件
  - `0x462ed0`: 17 命令・`div`/`idiv` 0 件
  - (比較) `0x417b70`: 255 命令・`idiv` 1 件 (`0x417c56`・`idiv qword ptr [rbp+0x60]`)
- 上の機械語の否定は**この走査範囲内だけ**の結論。関数の後続ブロックや、範囲外から飛ぶ先は見ていない。
- **未検証 (本 run)**: IR 側 (`udiv`/`sdiv` の有無) と `trace_diverge_cd.py` の再実行 (`results/m11_unreachable_cd.md` との diff。前回 run の所要 13.3 s は本 run の値ではない)。入力の `tools/m11/work/boot_final3.ll` と `tools/liftdiff/work/m11/batch_closure.jsonl` が本 run の素材に無く、実行できなかった。前回 run の記録は再現できていない主張として扱う。
- 再実行の入力を揃える手順: PR 本文の `oc_artifacts: fl-win64 work-m11 work-liftdiff` で素材を取得し、`python3 tools/liftdiff/tests/trace_diverge_cd.py > tools/liftdiff/results/m11_unreachable_cd.md` を実行して `git diff --stat -- tools/liftdiff/results/m11_unreachable_cd.md` の結果を本節に記録する。
- 0x476c30・0x462ed0 の原因は未特定。件数は `results/m11_unreachable_cd.md` の P3 行を正本とする。
- 範囲の変更 (#1576 の本文を縮めて `Closes #1576`): 0x417b70 の動的確認・sdiv 再実行は #1767 へ移した。`results/` 再計算と P3 の原因特定は本 PR の範囲外となり、PR 本文の未解決表に残す (起票は PM)。
