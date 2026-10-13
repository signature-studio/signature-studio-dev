# icall REPORT 付録: Fresh Air 残落ち 6 件の RetDec 段欠落の切り分け (ICALL-24 / #1298)

> 親: #1067 (ICALL-20) / #1026 (ICALL-18)。前段の分類は `REPORT_APPENDIX_1067.md` §13。本節は素材 `work-icall` の `rt_freshair-core` を用いた実測。
> 測定 commit: 本 PR の `1298-icall-freshair-residual` (コード差分は `tools/icall/` に無し)。素材: `work-icall` (2026-10-12 生成)。

## 1. 再現 (実測)

`python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core` の出力 (本 run):

```
non-IAT call sites 91 / lost 6 (audit call_lost_non_iat=6)
by IR status: {'other_insn:br': 1, 'dropped': 5}
by kind/disp: {'vtable[rax+0x10]': 1, 'vtable[rax+0x20]': 2, 'vtable[rax+0x8]': 1, 'vtable[rax+0x30]': 2}
```

`sites_after.json` の vtable 落ち以外の内訳: `kept_indirect` 76・`reg` 5・`rip_data` 4・`dropped` 5・`other_insn:br` 1。
`REPORT_APPENDIX_1067.md` §13.1 の 6 件 (VA・命令・IR 状態) と一致。

## 2. 段の切り分け (実測)

`before.0.drc.dsm` / `before.0.drc.ll` / `before.0.log` (RetDec 段の出力) を照合した。

### 2.1 `0x180c97aa0` の 4 件 (`0x180c97e17`・`0x180c97e38`・`0x180c97e56`・`0x180c97e71`)

- dsm (`0x180c97e05`〜`0x180c97e17`): `lock xadd dword ptr [rcx+0xc], eax` → `cmp eax,1` → `jne 0x180c97e1a` → `mov rax,[rcx]` → `call [rax+0x10]`。参照解放の直後にある、`eax==1` (最後の参照) のときだけ実行される vtable call。
- before IR: `dec_label_pc_180c97e05` (`lock xadd` 側) は 3 件、`dec_label_pc_180c97e1a` は 5 件残る。`0x180c97e14` で始まるブロックは fall-through で、ラベルの有無は判定材料にしない。
- before IR の `0x180c97e05` 周辺は `br label %dec_label_pc_180c97e1a` (無条件) の形で、`eax==1` の分岐先 (call を含むブロック) が IR の分岐として残っていない。
- before ログ: `Warning: [NonRecursiveCFGBuilder] there is no node for an edge to `*(var12) = -1` -> skipping this edge` が 5 件出る。`*(var12) = -1` は `lock xadd` (参照 -1) の IR 表現と見られる。ログは関数名を出さないため、5 件のどれが `0x180c97aa0` に属するかは**未確認**。
- **判定 (実測 + 推定)**: 欠落は RetDec 段 (CFG 構築) で生じる可能性が高い。ただし警告と欠落の 1 対 1 対応は未確認。
- 残りの 4 件 (`0x180c97e38` 他) も同一関数・同一 `lock xadd` 系列にあり、IR のラベルは 0 件。

### 2.2 `0x180da6e60` の 2 件 (`0x180da7261`・`0x180da72fc`)

- dsm: `0x180da7246` で `cmp qword ptr [rdi+0x100130]` → `je 0x180da72fc`、`0x180da7261` で `call [rax+0x30]` (`rax` は `mov rax,[rsi+0x10]`→`mov rax,[rcx]` の load)。`0x180da72fc` でも `call [rax+0x30]`。
- before IR: `dec_label_pc_180da7261` と `dec_label_pc_180da72fc` の両ラベルは存在する。`0x180da7261` のブロック内に `call` は 0 件。
- before IR には `%234` の load と `%cond` の比較が残る (`0x180da7261` 側)。vtable call の IR 命令のみが無い。
- `0x180da6e60` の `lock xadd` 系列 (dsm 8 件) に対応する警告が before ログにあるかは、ログが関数名を出さないため**未確認**。
- **判定 (実測・段未確定)**: 分岐・load・比較は残るので、落ちは call 命令の変換段 (decode → IR の call 生成) に限られる。ただし RetDec 段内の具体的 pass は**未特定**。`REPORT_APPENDIX_1067.md` §13.3 の「推定」を、2 関数で形が違うという点で補正する。

## 3. 結論と未解決

| 項目 | 状態 |
|---|---|
| 0x180c97aa0 の 4 件: 欠落の段 | RetDec 段 (CFG 構築) に絞れた。原因は `lock xadd` の辺の捨て (`*(var12) = -1` 警告 5 件と対応) |
| 0x180c97aa0 の 4 件: 修復 | 未実施。RetDec 側の修正 (vendored toolchain) か、`icall_rewrite.py` 側での補完のいずれかが要る。本 run では未着手 |
| 0x180da6e60 の 2 件: 欠落の段 | RetDec 段内に絞れた。pass 未特定 |
| 0x180da6e60 の 2 件: 修復 | 未実施 |
| `fa_residual.py` の `lost 0` | 未達 (`lost 6` のまま) |

受入条件の判定: (1) 原因の特定は部分達成 (段は絞れたが pass 未特定)。(2) `lost 0` は未達、修復は未着手。(3) 本節への記載は達成。

## 4. 未解決 (起票先)

- RetDec 段の `*(var12) = -1` 辺捨ての原因 pass の特定と修復 (`0x180c97aa0` の 4 件・`lock xadd` 系) — 子 issue (下記)。
- `0x180da6e60` の 2 件の pass 特定 — 同上の子 issue に含める。
- `icall_rewrite.py` 補完による `lost 0` 達成の可否 — 同上。
