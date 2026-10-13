# #662: unit 56 — 8c7710 の D4 型 deref 脱落の転記と、その先の 8c5eb0 の欠陥 (件数 0 のループ先頭ガード脱落) の特定

**判定: 受入 1・2 を達成。** `8c7710` を `m11_ov.c` に転記し (commit `ec513e0`)、unit 56 の次の欠陥 `8c5eb0` の原因を実測で特定した。
unit 56 は Halt0 (`Error`) → OOB (memory access out of bounds) に進むが、`8c5eb0` 本体の修復は本 PR に含めない (後続 issue、§5)。
他 unit のラベル差は 0 件 (`main` 基準、942 unit 全件比較)。

既知類型との関係 (DEFECTS.md): `8c7710` は **D4 型** (引数 `obj` の 1 段 deref 脱落。機械語は spill 経由で arg を読む)。
`8c5eb0` は **DEFECTS.md 未収録の新類型候補** (ループ先頭の件数判定 `cmp i,count-1; jg exit` の脱落, §6)。番号は (DEFECTS.md) 体系。

検証起点: `8d883c3` (main。#552 qstore・#446 を含む)。コード commit: `ec513e0`。検証スクリプト commit: `0775abb` (IR 状態の固定・survey 失敗検出)。

## 1. 結論と実測

**判定: 受入 1・2 を達成。** 「回帰 0」は、下記 IR 状態 Q で n=3 安定して再現した範囲の主張。
`bash tools/m11/trap_triage/negctl_662.sh` (base / cur / guard / ng の 4 構成を build + survey)。判定 G1〜G5 は n=3 の全 run で PASS, exit 0。

| 構成 | ok / trap / miss / noproc (n=3 min–max) | clobber | trap 内訳 (n=3 同一) | unit 56 | 基準 (base) との unit 差 (n=3) |
|---|---|---|---|---|---|
| base = `8d883c3` の `m11_ov.c` (8c7710 無し) | 864 / 31 / 46 / 1 (oom 1) | 0 | halt0 8・oob 23 | Halt0 (`Error`) | — |
| cur = `ec513e0` (8c7710 転記) | 864 / 31 / 46 / 1 | 0 | halt0 7・oob 24 | **OOB** (最上位 `function_8c6530` ← `8c5eb0` ← `56fde0`) | **0 件** |
| guard = cur + IR 実験 (8c5eb0 の件数 ≤ 0 で本体を飛ばす) | 865 / 30 / 46 / 1 | 0 | halt0 7・oob 23 | **ok** | **1 件** (56 のみ trap→ok) |
| ng = cur + 偽ガード (`icmp eq 123456789`, 常に不成立) | 864 / 31 / 46 / 1 | 0 | halt0 7・oob 24 | trap (cur と同じ) | cur 比 **0 件** (ネガコン) |

- 範囲: min–max は n=3 (検証スクリプト commit `0775abb`、逐次実行) で全 run 一致 (幅 0)。run ごとの wall と load は §4。
- 数値は IR 状態に依存する (§1-2)。上表は IR 状態 Q の値。
- ラベル全件比較は `work/v662/units_*.json` (`trap_triage/negctl_662.sh` 内で `diff` 判定)。

### 1-2. IR 状態で数値が変わる (#680)

survey の入力 IR (`work/boot_final3.ll`) は qstore (#516) の適用有無で変わる。artifact の `boot_final3.ll` は qstore 前の IR。`boot_final.ll` に qstore を当てると 140 site が書き換わり (`work/qstore.log`: `ir_narrow_machine_narrow=140`)、post で `boot_final3.ll` を再生成すると survey が変わる。

| IR 状態 | base | cur | guard | ng | 観測 |
|---|---|---|---|---|---|
| Q: qstore 適用後に再生成 (上表, n=3) | 864/31 | 864/31 | 865/30 | 864/31 | 4 構成とも同一入力 |
| A: artifact の `boot_final3.ll` (qstore 前, 旧 negctl, n=2) | 859/36 | 859/36 | 860/35 | 859/36 | 4 構成とも同一入力。base→cur 0 件 |
| 混在: 旧 negctl run 1 (base だけ Q, 他は A, n=1) | 864/31 | 859/36 | 860/35 | 859/36 | base→cur **6 件** (17・53・87・138・898 が ok→trap, 101 が oom→trap) |

- 混在は旧 negctl の欠陥 (base だけ初回 build で `boot_final3.ll` が再生成された)。検証スクリプト commit `0775abb` で 4 構成の入力を Q に固定した。
- レビュワー実測 (別 worktree, 本 runner とは別): base 859/36 (clobber 0) ×4、base 856/38 (clobber 1) ×1。859/36 は状態 A と一致。856/38 (clobber 1) は本 runner で再現せず、原因未特定 (#680)。

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

- 再現: `bash tools/m11/trap_triage/negctl_662.sh` (検証スクリプト commit `0775abb`)。前提:
  - `tools/m11/work/` に work-m11 が展開済み。`FL_WIN64_DIR` は fl-win64 の展開先 (`docs/REFERENCES.md` の `[WIN64]`。build の qstore が `extracted/block00031_PE.bin` を読む)。
  - `capstone`・`pefile` が import できること (無ければ FAIL。qstore が skip されると IR 状態が変わる)。
  - 初回のみ前段 build (qstore → post) を通した `work/v662/boot_final3.orig.ll` を作る。以後の 4 構成はこの IR を入力にする。
  - 判定 G1〜G5 が 1 つでも外れると exit 1。終了時に `m11_ov.c` と `work/boot_final3.ll` を復元する。
- 環境 (本 runner): AMD EPYC 9V74 (4 vCPU)。node v22.23.3 (既定)、node v24.21.0 (hostedtoolcache)、python 3.14.8 (venv: capstone 5.0.7, pefile 2024.8.26)、emcc 6.0.12 (`[EMSDK]`)。REPORT 旧版の前提 node v26 は runner に無く未検証。
- n=3 (逐次実行): wall は run 1 121.6 秒 (前段 build を含む)・run 2 102.2 秒・run 3 102.0 秒。load average (1 分値) の開始→終了は 0.83→0.98・0.98→1.12・1.12→1.02。
- コミット済み HEAD `f77c97e` での追加 1 run (n=4): rc=0、G1〜G5 PASS、survey は base 864/31/46/1・cur 864/31/46/1・guard 865/30/46/1・ng 864/31/46/1 (clobber 0 は全構成)。wall 101.8 秒、load 0.07→0.83。
- node 版: 同じ base build (IR 状態 Q、ネガコン後に残った build) の survey を node v22.23.3 と v24.21.0 で各 n=1 実行し、どちらも 864/31/46/1 (clobber 0)。node 版による差は今回の範囲では出なかった (n=1 のため範囲は限定的)。
- ネガコン (修正 3): `work/m11_image.bin` を退避して negctl を実行 → `FAIL: survey (base) rc!=0` (`Error: ENOENT`)、exit 1、`units_*.json` は残らない。画像は cmp で復元。
- e2e (作成者環境の単発記録, コミット `ec513e0`, `bash tools/m11/m11_e2e.sh`, n=1。**本 runner では未再現・未実施**: `m11_e2e.sh` の PE 参照は `[ANALYSIS-DIR]` 配下の固定パスで、14 script が同じ前提を持つ (#680)): `reached_stage 4/6`, `units_run 22`, survey `ok 864 / trap 31 / oom 1 / clobber 0 / miss 46`, `wasm_bytes 6027634`。
  所要 42.6 秒、load 0.67→0.85 (4 vCPU)。変更前 (`8d883c3`, 同じ work スナップショット) の e2e は 69.2 秒、survey 864/31/1/0/46 で一致。
  wasm の増分 (+62 B) は `function_8c7710` の追加。
- 範囲: `git diff 8d883c3 ec513e0 --stat` は `tools/m11/m11_ov.c` と `tools/m11/trap_triage/negctl_662.sh` のみ。
- 範囲外: unit 56 の最終到達 (ok) は本 PR では達成しない (guard は IR 実験のみで commit していない)。`survey_units.mjs` の `.slice(1)` 問題 (REPORT_594 §4) は未修正 (#663)。
- 20 MiB 超の blob: 追加なし。`work/` は gitignore。
- PE: `negctl_662.sh` の build は `FL_WIN64_DIR` 経由で `extracted/block00031_PE.bin` を読む (`docs/REFERENCES.md` の `[WIN64]`)。`m11_e2e.sh` 側の PE 参照の固定化と runner 上の扱いは #680 の範囲で、本 PR では触れない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `8c5eb0` の件数 0 ガード復元 (IR pass、または `8c5eb0` の C 転記。guard 実験で ok・退行 0 を確認済み) | unit 56 は OOB のまま (trap) | 新規 #699 (`[M11-N31]`) (本 run で起票) |
| RetDec が先頭 `cmp/jg` を落とす機構と、同型の脱落の有無 | 他 unit の trap 30 本の内訳は未切り分け | #699 (`[M11-N31]`) の調査項目 |
| `8c6530` (値コピー関数) の他経路の正しさ | 今回の入力は件数 0 由来の不正レコードで、経路自体の検証は未実施 | #699 (`[M11-N31]`) |
| REPORT_594 (PR #664, 未 merge) との関係 | 本 PR は #664 に依存しない (8c7710 の転記だけを入れた) | #664 (merge 時に REPORT_594 §3 の「採用せず」を更新) |
| survey の IR 状態依存 (§1-2: qstore 適用の有無で 864/31 ↔ 859/36)。artifact の `boot_final3.ll` は qstore 前 IR のまま | survey の基準 (本 PR は入力を Q に固定して回避) | #680 (コメント追記) |
| レビュワー実測の base 856/38 (clobber 1) の原因 | 本 runner で再現せず。未説明 | #680 (コメント追記) |
| node v26 (旧版の前提) の未検証 (v22.23.3 と v24.21.0 で同一)・`m11_e2e.sh` の `[ANALYSIS-DIR]` 固定 PE 参照 (runner 上での扱い) | e2e の再現が本 runner で未実施 | #680 |

## 6. DEFECTS.md 行案 (PM 判断。直接編集はしない)

| ID | 分類 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| (新規・番号は PM 採番) | opt (制御フロー) | 件数 0 のループで本体が 1 回以上実行される。空リストの `Items[0]` を読み、後続反復で不正レコードを OOB に渡す | ループ先頭の `cmp i,count-1; jg exit` が IR から脱落し、do-while 形になる | `8c5eb0` (unit 56, #662): `8c5f15-8c5f18` ↔ `dec_label_pc_8c5ef5` の無条件 `br` | ループ head の `jcc` に対応する IR 分岐が無い (機械語と IR の分岐数の突合) | 先頭に `icmp sle i32 count, 0` → exit の分岐を復元 (guard 実験で ok・退行 0) |

D4 (`8c7710`) は既知類型の再発例として扱う (DEFECTS.md D4 の「再発例」欄に追記できる内容)。

## 7. 次タスク提案

- #699 (`[M11-N31]`) `8c5eb0` の件数 0 ガードを IR pass または C 転記で復元し、unit 56 を ok にする。受入: survey で unit 56 が ok、他 unit の退行 0、guard 構成と同じ数値 (865/30/46/1) を再現。
- 同型の「ループ先頭ガード脱落」を IR と機械語の分岐突合で全 942 unit 走査し、件数を測る (trap 30 本との突合を含む)。
