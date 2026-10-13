# liftdiff LD-39 (#1194) — i128 引数・%tagPOINT 値渡し 11 関数の ABI 確認 (途中報告)

> 親: #976 (LD-24)。子 issue 本体: #1194。本節は 1 run で得た**部分達成**の記録 (case 生成・runner 変更は未実装)。
> 既知類型との関係: 該当なし (DEFECTS.md の類型に当てはめる前の観測。IR 署名と機械語入口の不一致は未分類)。

## 1. 対象の確定 (実測)

`tools/m11/work/boot_final3.ll` (素材 work-m11 由来) と `results/m11_closure_verdicts.tsv` で
`ld24_sig_breakdown.py` を実行 (rc=0、入力 50 件 / IR 解決 50 件 / 未解決 0 件)。

| 振り分け | 件数 | 関数 |
|---|---|---|
| #1194 (引数に i128 / %tagPOINT) | **11** | i64(i128) ×8, i64(i64,i128,i64) ×1, i64(i64,i64,i128) ×1, ptr(%tagPOINT) ×1 |

- 受入条件の「i128 を含む 10 関数 + %tagPOINT 1 関数」と一致する。
- 対象 VA: `40c660` `40c750` `4256c0` `664890` `6649b0` `6649c0` `664a80` `442a50` `442b90` `653c80` `691dd0`。

## 2. 機械語入口の確認 (ABI) — 実測

コマンド (commit 対象の script):

```
python3 tools/liftdiff/tests/ld39_abi_dump.py <FL_WIN64_DIR>/extracted/block00031_PE.bin tools/m11/work/boot_final3.ll
```

fl-win64 素材 (`block00031_PE.bin`、image base 0x400000) の `.text` を capstone で逆アセンブルした結果:

| VA | IR 署名 | 機械語入口 (実測) | 読み |
|---|---|---|---|
| `40c660` | `i64 (i128)` | `cvtsd2si rax, xmm0; ret` | **IR 署名と合わない**。入力は xmm0 の double。i128 を読んでいない |
| `40c750` | `i64 (i128)` | `cvttsd2si rax, xmm0; ret` | **IR 署名と合わない** (同上) |
| `4256c0` | `ptr (%tagPOINT)` | `jmp [rip+0x154b732]` → IAT slot `0x1970df8` | import thunk。本体の ABI は呼び先依存で、この VA からは判定できない |
| `664890` | `i64 (i128)` | `sub rsp,0x28; call 0x476930` (tail 相当) | 呼び先 `0x476930` の署名確認が必要 (未実施) |
| `6649b0` / `6649c0` / `664a80` | `i64 (i128)` | `sub rsp,0x28; call <fn>` の薄い wrapper | 呼び先の署名確認が必要 (未実施) |
| `442a50` | `i64 (i128)` | `lea rax,[rbp+0x3e]` を stack に置いて `call 0x4428c0` | 戻り/引数の一部を stack 経由で渡す形。i128 の 2 レジスタ分解とは別の形の可能性 |
| `442b90` | `i64 (i128)` | `call 0x442420` 後に rax の上位 32bit を使う | 呼び先の戻り値 (rax) を読む wrapper。i128 引数は未確認 |
| `653c80` | `i64 (i64,i64,i128)` | `cmp r8,0x7fffffff` → `shl r8,2` | 第 3 引数 (r8) を整数として読む。i128 の上位 64bit 位置 (r9) は読まれていない |
| `691dd0` | `i64 (i64,i128,i64)` | `mov [rbp+0x68],rdx` / `mov byte [rbp+0x70],r8b` | 第 2 引数 (rdx) を 8 バイトで保存し、第 3 は r8b (下位 1 byte) だけ読む。i128 の 2 レジスタ分解と合わない |

### 観測の要点

1. **IR の署名と機械語の入口が一致しない関数がある** (`40c660` `40c750` 等)。case 生成を IR 署名から
   自動で組むと、読まれない引数を投入して比較するだけになり、判定が無意味になる。
2. `i128` 引数の 2 レジスタ (rcx:rdx / rdx:r8 等) に分かれて入る形は、この 11 関数の入口では**確認できなかった**。
   受入条件の「i128 を 2 レジスタ分に分解して投入する ABI を機械語で確認」は未達。
3. `%tagPOINT` の値渡しは、対象 VA が import thunk のため本体の確認に至らない。

## 3. 未達の受入条件 (本 PR では達成していない)

| 受入条件 | 状態 | 起票先 |
|---|---|---|
| case 生成 (`ldlib/cases.py`) で i128 / %tagPOINT を扱う | 未実装 | #1194 (本 issue に残す) |
| native / wasm 実行器で i128 2 レジスタ投入・tagPOINT 投入 | 未実装 | #1194 |
| ABI を機械語で確認 (i128 2 レジスタ・tagPOINT) | 部分 (§2)。呼び先の署名確認と IR/機械語不一致の切り分けが残る | #1194 (本 PR の script を使う) |
| 対象のうち実行可能になった件数を実測し REPORT_LD*.md に記録 | 未実施 (実行器が無いため 0 件) | #1194 |
| 既存 pattern の判定を壊していないこと (e2e `liftdiff_e2e.sh --m11-only`) | **未実行**。本 PR は実行器・case を変えていないため、e2e 対象の挙動は変わらない | #1194 |

## 4. 検証

- 測定 commit: 本 PR の commit (script 追加のみ)。`git diff <測定 commit> HEAD -- tools/liftdiff` は 0 行 (同 commit 内で確定)。
- ld24_sig_breakdown.py の実行 rc=0 (§1)。ld39_abi_dump.py の実行 rc=0 (§2)。
- 再現: `tools/liftdiff/tests/ld39_abi_dump.py` は PE と IR を引数で受ける (`work/` 由来、commit しない)。
- 範囲外: 実行器・case 生成の挙動、e2e の PASS/FAIL は本 PR では測っていない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `40c660` `40c750` の IR 署名 (i128) と機械語 (double) の不一致 | case 生成を IR 署名から組むと誤った引数で比較する | #1194 (IR 側の切り分けは #976 の残件として PM 判断) |
| 呼び先 (`476930` `476980` `476500` `4764c0` `476020` `476480` `442420` `4428c0` `653c80` 等) の署名確認 | i128 を取る呼び先の ABI が未確定 | #1194 |
| `4256c0` の import 先の %tagPOINT 署名 | tagPOINT 値渡しの ABI が未確定 | #1194 |
| case 生成・runner 実装・e2e 実測 | 受入条件の大半 | #1194 |
