# #662: unit 56 — 8c7710 の D4 型 deref 脱落の転記と、その先の 8c5eb0 の欠陥 (件数 0 のループ先頭ガード脱落) の特定

**判定: 受入 1・2 を達成。** `8c7710` を `m11_ov.c` に転記し (commit `ec513e0`)、unit 56 の次の欠陥 `8c5eb0` の原因を実測で特定した。
unit 56 は Halt0 (`Error`) → OOB (memory access out of bounds) に進むが、`8c5eb0` 本体の修復は本 PR に含めない (後続 issue、§5)。
他 unit のラベル差は 0 件 (`main` 基準、942 unit 全件比較)。

既知類型との関係 (DEFECTS.md): `8c7710` は **D4 型** (引数 `obj` の 1 段 deref 脱落。機械語は spill 経由で arg を読む)。
`8c5eb0` は **DEFECTS.md 未収録の新類型候補** (ループ先頭の件数判定 `cmp i,count-1; jg exit` の脱落, §6)。番号は (DEFECTS.md) 体系。

検証起点: `8d883c3` (main。#552 qstore・#446 を含む)。コード commit: `ec513e0`。

## 1. 結論と実測

`bash tools/m11/trap_triage/negctl_662.sh` (base / cur / guard / ng の 4 構成を build + survey)。判定 G1〜G5 は全 PASS, exit 0。

| 構成 | ok / trap / miss / noproc | trap 内訳 | unit 56 | 基準 (base) との unit 差 |
|---|---|---|---|---|
| base = `8d883c3` の `m11_ov.c` (8c7710 無し) | 864 / 31 / 46 / 1 (oom 1) | oob ほか | Halt0 (`Error`) | — |
| cur = `ec513e0` (8c7710 転記) | 864 / 31 / 46 / 1 | oob ほか | **OOB** (最上位 `function_8c6530` ← `8c5eb0` ← `56fde0`) | **0 件** (回帰無し) |
| guard = cur + IR 実験 (8c5eb0 の件数 ≤ 0 で本体を飛ばす) | 865 / 30 / 46 / 1 | — | **ok** | **1 件** (56 のみ trap→ok) |
| ng = cur + 偽ガード (`icmp eq 123456789`, 常に不成立) | 864 / 31 / 46 / 1 | — | trap (cur と同じ) | cur 比 **0 件** (ネガコン) |

- 同一構成の再実行で一致: base は 2 回 (単体 survey と negctl)、cur は 2 回 (単体 survey と negctl)、guard は 2 回 (単体 survey と negctl。865/30 が再現)。negctl 全体は 1 分 59 秒 (n=1)。
- ラベル全件比較は `work/v662/units_*.json` (`trap_triage/negctl_662.sh` 内で `diff` 判定)。

## 2. 8c7710 (D4 型): 1 段 deref の脱落

機械語 (`trap_triage/disasm_fn.py 8c7710`, capstone):

```
8c7731: mov rax, [rbp+0x30]      ; arg2 (obj) を spill から読む
8c7735: mov rax, [rax]           ; obj の VMT = TClass (1 段 deref)
8c773c: mov rcx, [rcx+0x410]     ; 辞書 = self.[0x410]
8c7743: mov rdx, rax             ; key = [obj]
8c7746: call 0x8cbde0            ; TDictionary.GetItem(dict, key)
```

IR (`work/boot_final3.ll`): `load [arg1+1040]` → `call @function_8cbde0(%2, %arg2)`。`arg2` (obj) を deref せずに key に渡している。
8c7710 は 8c7c80 から呼ばれ (8c67a0 経由で 8c5eb0 の入力を作る)、`8c7c80` は GetItem の値 (`rdi`) の `[rdi+8]` を戻す。

転記 (`m11_ov.c`, 6 行): `u64 function_8c7710(u64 self, u64 obj) { return function_8cbde0(Q(self + 0x410), Q(obj)); }`
REPORT_594 §3 の予測 (56 が halt0→oob) と一致。

## 3. 8c5eb0 (unit 56 の次の欠陥): 件数 0 のループ先頭ガードの脱落

**機械語** (`disasm_fn.py 8c5eb0`):

```
8c5f0c: mov ebx, [rcx+0x14]      ; ebx = 件数 (rcx = 8c67a0 の戻り)
8c5f0f: sub ebx, 1
8c5f12: mov [rbp+0x4c], eax      ; i = 0
8c5f15: cmp [rbp+0x4c], ebx      ; i > 件数-1 なら本体を飛ばす
8c5f18: jg 0x8c6066
```

**IR** (`boot_final3.ll` の `dec_label_pc_8c5ef5`): `store i32 0 → i`, `store %10 → rbx`, そして **無条件** に `br label %dec_label_pc_8c5f23`。
先頭の `cmp/jg` に対応する分岐が無い。ループ末尾 `dec_label_pc_8c6057` の判定 (`trunc` 後 `icmp eq 0`) だけが残り、ループは do-while 形になっている。

**実測** (一時 probe, unit 56 だけ出力。probe は IR に `call @m11_probe_662` を挿入し C 側の `m11_probe_662` を一時追加。commit には含めていない):

| probe | 位置 | 観測値 | 読み |
|---|---|---|---|
| probe2 | `8c5eb0` の `8c67a0` 直後 | `list=0x10bd34e0`, `[list+0x14]=0` (件数 0), `[list+8]=0` (Items NULL) | 空リスト。機械語なら本体は実行されない |
| probe1 (1 回目) | `8c6530` 入口 | `rec=0x4bdb50` (image 内のテキスト由来), `rec+0x3c=115` | 不正レコード (推定: Items が NULL のため i=0 の読みはメモリ 0 番地の内容) |
| probe1 (2 回目) | `8c6530` 入口 | `rec=0x670067` (UTF-16 断片), `rec+0x3c=0` | 不正レコード (i=1) → 直後に OOB trap |

→ 件数 0 のとき、IR 版は本体を 1 回以上実行する (i=0 で `Items[0]`, i=1 で `Items[1]` を `8c6530` に渡す)。機械語版はガードで抜ける。
`8c5eb0` の入口 (`8c5ef5`) に機械語どおりのガード (件数 ≤ 0 なら `dec_label_pc_8c6066` へ) を入れた実験 (guard 構成) で、unit 56 は ok になり、他 unit は 0 件変化 (§1)。
偽ガード (ng) では 0 件変化 → 効果はガードの条件 (件数 ≤ 0) に由来する。

**原因の範囲**: 「RetDec が `cmp dword [rbp+0x4c], ebx; jg` を IR に落とした」ことは IR と機械語の突合で確定。
なぜ落ちたか (RetDec の分岐復元の機構) と、同型の脱落が他関数にもあるかは **未調査** (§5)。

## 4. 検証

- 再現: `bash tools/m11/trap_triage/negctl_662.sh` (前提: `tools/m11/work/` に work-m11 が展開済み。`FL_WIN64_DIR` の `extracted/block00031_PE.bin` は build の qstore 用)。
  判定 G1〜G5 が 1 つでも外れると exit 1。終了時に `m11_ov.c` と `work/boot_final3.ll` を復元する。
- e2e (コミット済み HEAD `ec513e0`, `bash tools/m11/m11_e2e.sh`, n=1): `reached_stage 4/6`, `units_run 22`, survey `ok 864 / trap 31 / oom 1 / clobber 0 / miss 46`, `wasm_bytes 6027634`。
  所要 42.6 秒、load 0.67→0.85 (4 vCPU)。変更前 (`8d883c3`, 同じ work スナップショット) の e2e は 69.2 秒、survey 864/31/1/0/46 で一致。
  wasm の増分 (+62 B) は `function_8c7710` の追加。
- 範囲: `git diff 8d883c3 ec513e0 --stat` は `tools/m11/m11_ov.c` と `tools/m11/trap_triage/negctl_662.sh` のみ。
- 範囲外: unit 56 の最終到達 (ok) は本 PR では達成しない (guard は IR 実験のみで commit していない)。`survey_units.mjs` の `.slice(1)` 問題 (REPORT_594 §4) は未修正 (#663)。
- 20 MiB 超の blob: 追加なし。`work/` は gitignore。
- PE パス: `m11_e2e.sh` は `/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin` を固定で参照する。runner では `/home/ubuntu` が無いため、展開した `block00031_PE.bin` への symlink を sudo で作成した (runner 上の環境操作。repo には含めない。固定パスの扱いは #680 の範囲)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `8c5eb0` の件数 0 ガード復元 (IR pass、または `8c5eb0` の C 転記。guard 実験で ok・退行 0 を確認済み) | unit 56 は OOB のまま (trap) | 新規 #699 (`[M11-N31]`) (本 run で起票) |
| RetDec が先頭 `cmp/jg` を落とす機構と、同型の脱落の有無 | 他 unit の trap 30 本の内訳は未切り分け | #699 (`[M11-N31]`) の調査項目 |
| `8c6530` (値コピー関数) の他経路の正しさ | 今回の入力は件数 0 由来の不正レコードで、経路自体の検証は未実施 | #699 (`[M11-N31]`) |
| REPORT_594 (PR #664, 未 merge) との関係 | 本 PR は #664 に依存しない (8c7710 の転記だけを入れた) | #664 (merge 時に REPORT_594 §3 の「採用せず」を更新) |
| survey の基準 (IR 生成条件でのずれ・PE パス固定) | 数値の再現性 | #680 |

## 6. DEFECTS.md 行案 (PM 判断。直接編集はしない)

| ID | 分類 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| (新規・番号は PM 採番) | opt (制御フロー) | 件数 0 のループで本体が 1 回以上実行される。空リストの `Items[0]` を読み、後続反復で不正レコードを OOB に渡す | ループ先頭の `cmp i,count-1; jg exit` が IR から脱落し、do-while 形になる | `8c5eb0` (unit 56, #662): `8c5f15-8c5f18` ↔ `dec_label_pc_8c5ef5` の無条件 `br` | ループ head の `jcc` に対応する IR 分岐が無い (機械語と IR の分岐数の突合) | 先頭に `icmp sle i32 count, 0` → exit の分岐を復元 (guard 実験で ok・退行 0) |

D4 (`8c7710`) は既知類型の再発例として扱う (DEFECTS.md D4 の「再発例」欄に追記できる内容)。

## 7. 次タスク提案

- #699 (`[M11-N31]`) `8c5eb0` の件数 0 ガードを IR pass または C 転記で復元し、unit 56 を ok にする。受入: survey で unit 56 が ok、他 unit の退行 0、guard 構成と同じ数値 (865/30/46/1) を再現。
- 同型の「ループ先頭ガード脱落」を IR と機械語の分岐突合で全 942 unit 走査し、件数を測る (trap 30 本との突合を含む)。
