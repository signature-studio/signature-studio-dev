# REPORT #3752 — spill 宛 UNDETERMINED の間接 call 2 site (128cad6・128d007) の判定 (LD-174)

親: #2253 (LD-95・分割元) / 上位: #1161 (LD-35)。#2253 の子 A。残り 5 site は子 B (#3753)、反映と spill178 の最終 audit は子 C (#3754)。

## 1. 測定

- 測定 commit: `f592bd2aa` (コードを変えた最後の commit。判定 2 行と `spill178_1161.tsv` の 2 行を更新)。作業 worktree `ws-3752` (branch `3752-ld174-indirect-call`、origin/main `bb0f61949` から作成)。
- 素材: `work-m11` / `work-liftdiff` を worktree 直下に `tar --zstd -xf` で展開 (gitignore 対象)。fl-win64 は本判定に使わない (IR と機械語のみ)。
- e2e: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`RUNNER_TEMP` 配下に出力)。コミット済み HEAD `f592bd2aa` で rc=0、real 3m00.4s、uptime load 0.63 → 0.98、7/7 完走。`drops_510.tsv`・`spill178_1161.tsv` (修復後 IR の再生成を含む) が results/ と一致。
- 判定データの更新前は step 7・8 の `spill178` 照合が 2 行不一致 (rc=1) だった。その後 TSV を script の出力どおり再生成し、コミット後に再測定した。
- 状態の差 (`spill178_1161.tsv` の status 列、HEAD~1 → `f592bd2aa`): 確定 148 → 150、判定不能 29 → 27、未判定 1 のまま。差分は 2 行のみ (155・156 行目、128cad6・128d007)。

## 2. 判定 (2 site → TRUE_DROP)

| 関数 | site | 機械語 (二段参照) | 消費者 (機械語) | IR 側 |
|---|---|---|---|---|
| 128c320 | 128cad6 | 128cacd `mov rax,[rip+0x35780c]` (セル 0x15e42e0) → 128cad4 `mov eax,[rax]` → 128cad6 `mov [rsp+0x20],eax` | 128cade `call qword ptr [rsi+0x188]` (vtable 呼出し・第5引数) | 対応する間接 call なし。セル読みは生 `load i32 @0x11e42e0` のみ (74580・74729・74736 行) |
| 128c320 | 128d007 | 128cffe `mov rax,[rip+0x352da3]` (セル 0x15dfda8) → 128d005 `mov eax,[rax]` → 128d007 `mov [rsp+0x20],eax` | 128d00f `call qword ptr [rsi+0x188]` (同上) | 対応する間接 call なし。セル読みは生 `load i32 @0x11dfda8` のみ (74505・74727・74737 行 ほか) |

セルの内容 (`ldfix/results/audit_510_ssa.json`): 0x15e42e0 → 0x153fb34、0x15dfda8 → 0x153fb30。どちらもポインタ値で、機械語は `mov eax,[rax]` により二段で読む。

行番号は `tools/m11/work/boot_final3.ll` の絶対行。

### 2.1 IR に対応する間接 call が無いことの確認

- `function_128c320` (74166〜76136 行) の call は全て `@function_*` / `@__asm_*` の直接参照。値を呼ぶ形 (`call ... %`) は 0 件。
- `boot_final3.ll` 全体でも、非グローバル呼出先の call は 0 件 (`grep -c -E 'call [^@]*\('` → 0)。
- 機械語 128c320〜128d600 の memory-indirect call は 14 件 (128c570・128c62b・128c777・128c883・128c989・128cade・128cafc・128cb09・128cd65・128cd76・128cdd8・128cec7・128cee5・128d00f)。IR の対応は 0 件。
- 直接 call 列は機械語と IR で 1 対 1 に対応する (例: 機械語 128ca1f `call 0x40c660` ↔ 74724 行 `%309 = call function_40c660`、機械語 128caee `call 0x60a490` ↔ 74755 行)。間接 call だけが IR に現れない。
- 128d00f の前後: 機械語 128cf4f `call 0x414c70` ↔ 74955 行 `%452 = call function_414c70`、機械語 128d051 `call 0x40c660` ↔ 75021 行 `%499 = call function_40c660`。その間に IR の call は 0 件。

機構は `docs/DEFECTS.md` D15 (stage-0 が memory-indirect call `call qword ptr [reg+N]` を丸ごと欠落させる) と一致する。

### 2.2 判定の根拠 (型の定義は REPORT_2438 §2 に従う)

- TRUE_DROP: 機械語は二段参照の値を消費者 (vtable 呼出しの第5引数) に渡すが、IR には消費者が無く、セルは一段の `load i32` のみで deref の段が無い。消費者の欠落と deref の欠落が同時に起きている。先例: 41a5d0 41a618 (`call qword ptr [rbx+8]` の vtable 呼出しが IR に無く消費者が脱落、REPORT_2264 §8.1)、47b260 (D15 の notify call、REPORT_510 §5.3)、1046a30 系 (セル直読みで deref 脱落、results/candidate_verdicts_1161.jsonl)。
- OK_LOAD 不成立: IR に `load ptr` によるセル→ポインタの段が無い。
- NO_CONSUMER 不成立: 機械語に消費者 (間接 call) がある。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| memory-indirect call の IR 欠落 (D15) の lift 段での修復 | 128c320 の間接 call 14 件の消費者が IR に無い。他関数の同型 site も同じ欠落に依存しうる。本 PR は判定のみで IR は変えていない | 既存の D15 (`docs/DEFECTS.md`)。修復の起票は PM 判断 |
| 残り 5 site (128d495・1284dab・dcdeee・c3460e・12900c4) の判定 | #2253 から分割された残り 5 site。spill 宛の判定不能 27 件に含まれる | #3753 (子 B) |
| 判定不能 0 件の達成と spill178 の最終 audit | 子 B の判定後に確定する | #3754 (子 C) |

## 4. 再現

```sh
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh      # rc=0 (7/7・drops_510 と spill178 が results/ と一致)
grep -c -E 'call [^@]*\(' tools/m11/work/boot_final3.ll   # 0
sed -n '74724p;74955p;75021p' tools/m11/work/boot_final3.ll
```
