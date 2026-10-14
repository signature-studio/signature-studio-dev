# 付録: icall #1402 — `jmp [mem]` 形 jump table の cmp/je 展開 (ICALL-26)

## 実装

- `icall_rewrite.py`: `jmp [base+idx*s+d]` (SIB memory 形) の jump table を `cmp qword [mem], target; je new_target` の列へ展開する `jtm` テンプレートを追加。REX.W を立て、ModRM の reg 欄を /7 (cmp) に差し替える (`jtm_head`)。表は元 VA のまま残す (`jt` と同じ)。
- 対象外: rip 相対 (`jmp [rip+d]`)・reg 形 (`jmp rax`)・target が 0x80000000 以上の表 (imm32 の符号拡張で表せないため)。
- 既存の `jt` (`jmp reg`) は無変更。`test_icall.py` に `jtm_head` の 4 件を追加 (PASS)。

## 実測

測定 commit `4708059e` (HEAD)。素材 `fl-win64` (`block00031_PE.bin`)・`toolchain-retdec`。`roundtrip.sh` を `.pdata` 範囲 `0x40d210--0x40d31b` で実行 (foreground、rc 0、所要 27 s (実測 00:04:15→00:04:42 UTC)、load 0.02)。

| 項目 | before | after |
|---|---|---|
| jump table site 数 | 1 (`jmp qword ptr [r10+rdx*8+0x40]`, 9 target) | 1 |
| `jt_dropped` | 0 (`jt_present=1`) | 0 (`jt_present=1`) |
| `rewrite.txt` の `jt-chain` | — | 1 (前回 #1206 は 0) |

- 展開は適用された (`jt-chain 1`) が、監査上の site の落ち (`dropped`) は before/after とも 0。この site は元から RetDec の IR に `jmp` が残っており、落ちていなかった。受入条件の「dropped 変化を数値で記載」は 0→0 で、変化は測れなかった。
- 効果の実証には、この表を実際に RetDec が取りこぼす関数が必要。現状の FLEngine 範囲では判定材料が無い。
- `test_icall.py`: RESULT PASS (0 failed)。
