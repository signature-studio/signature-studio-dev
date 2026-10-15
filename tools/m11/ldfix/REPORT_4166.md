# REPORT_4166 — 1006ec0・5cb210 の漏出 store の別名判定 (#4166 / 親 #3225)

## 1. 測定条件

- 測定 commit: `c159cf7fe` (結果 JSON と negctl 3 種を現 head の判定器で再生成した commit)。判定器 (`audit_frame_store_alias_2211.py`) は `9881e597b` (main の #4090 `lea` 伝播を含む) から 0 行しか変えていない。同じ判定器で 2 回実行し `cmp` 一致 (byte 同一)。
- 判定器の由来: `b1b8aee45` (main, #4090) が `frame_derived` に `lea` の派生を、`leak_sites` に全件返却を入れた。#4166 の branch 独自の判定器変更は規則 6 (`nonframe_store_addrs` 側) だけ。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211 と同じ)。
- PE: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 実行時間: 0.19 秒 (head で再実行、`real 0m0.192s`)。load average 0.48 (4 vCPU)。

## 2. 方式 (規則 6 NONFRAME)

#2211 の規則 (CFG 逆向き探索・3 値判定・glk・rsp/rbp 区間) は変えない。追加は規則 6 の 1 点。

- **NONFRAME**: glk 関数のポインタ経由 store は、基底レジスタが入口の引数値 (rcx・rdx・r8・r9 で、その前に定義が無い値) から、無改変の 8 バイト slot (`mov [rbp+D], reg`) を経て来るとき、LEAK_STORE と数えない。
  - 根拠: 入口の引数値は呼び出し元の生きたポインタで、この関数の frame (戻り番地より下) を指さない。
  - 成立条件: slot の書きが全て frame 派生でない値の 8 バイト store で、入口まで未定義の経路が無いこと。
  - 仮定 (#2211 と同じ、未検証): call は caller の frame slot を書かない。NONFRAME の判定は call を越える経路も透過する。

ネガティブコントロール: `--negctl-noprov` (規則 6 を外す)、`--negctl-glk` (全関数の漏出を True)、`--negctl-nosync` (rsp/rbp 区間を無効)。

### 2.1 head の判定器の変化と判定の変化

head の判定器は main の #4090 修正を含む。その修正の前後で結果が変わるので、比較の基準を分けて書く。

- 判定器を戻さない理由: `lea` の派生 (`lea reg, [rbp+D]`) は frame を指すポインタそのもの。`6e8a67464` の `frame_derived` は `lea` を伝播させないため、`lea` で作った frame ポインタを F に入れず、その経由の store を漏出として数えない。規則 6 は「非 frame の基底だけを NONFRAME とする」ので、F が過小だと規則 6 の前提 (F の外にある基底) が偽の根拠で成り立つ。head の判定器 (#4090) はこの過小を直しており、規則 6 の意図 (frame を指さない基底だけを NONFRAME にする) に合う。
- `frame_derived` が `lea` の派生を F に入れる。`glk` 対象の関数が 11 → 45 に増える (`glk=True` の関数)。
- 関数単位の判定: #2211 の記録 (DROP 3・LIVE-IN 35・UNDETERMINED 10) から、head では DROP 3・LIVE-IN 1・UNDETERMINED 44 になる。34 関数が LIVE-IN → UNDETERMINED (32 件は `glk` が False → True に変わった関数)。
- 規則 6 の効きは head でも確認できる (`--negctl-noprov` の site 単位の判定が head 本体と 1 件 (`1006ec0 1007021`) だけ異なる)。

## 3. 結果 (測定 commit `c159cf7fe` の判定器)

### 3.1 関数単位 (受入 2)

| 判定 | #2211 の記録 | 測定 commit (head) |
|---|---|---|
| DROP | 3 | 3 |
| LIVE-IN | 35 | 1 |
| UNDETERMINED | 10 | 44 |

### 3.2 対象 2 関数の site 判定 (受入 2)

| 関数 | 読み | head の判定 | 根拠 (機械語) |
|---|---|---|---|
| 1006ec0 | `1006fb6 cmp dword ptr [rbp+0x2c], 1` | UNDETERMINED (ONLY_ENTRY_AFTER_CALL) | 残る経路は call 越えの ENTRY (#3228) |
| 1006ec0 | `1007021 cmp byte ptr [rbp+0x2b], 0` | UNDETERMINED (ONLY_ENTRY_AFTER_CALL) | `1006fe8 mov [rax+0x64], 0` は NONFRAME。`rax` は `1006fe4` の `mov rax, [rbp+0x40]`、`[rbp+0x40]` は入口 `1006ec8 mov [rbp+0x40], rcx` だけで書かれる。残る経路は call 越えの ENTRY |
| 5cb210 | `5cb4aa cmp qword ptr [rbp+0xc0], 0` | UNDETERMINED (BARRIER(ALIAS_FRAME_PTR)) | 打ち切りの store `5cb47d mov [rax+8], ecx` は head で ALIAS_FRAME_PTR。`rax` が frame 派生になる経路は `5cb578 xor eax, ecx` (`ecx` ← `rdx` ← `r8` ← `lea r8, [rbp+0xa8]`)。`[rbp+0x198]` は入口 `5cb237 mov [rbp+0x198], r9` だけで書かれるが、`rax` の値そのものは `xor` 結果で、規則 6 の成立条件 (無改変の入口引数 slot) を満たさない |

- 1006ec0 の起点 `1006ec8 mov [rbp+0x40], rcx` は leak として残る (`rcx` は入口の引数)。

### 3.3 site 単位の判定 (受入 2)

- 51 site の合計: DROP 3・LIVE-IN 1・UNDETERMINED 46・PTR_READ 1。
- #2211 の記録からの site 差分: 38 件 (`results/frame_store_verdict_2211.json` と head の `--negctl-noprov` を site 単位で比較)。主因は §2.1 の `lea` 伝播。

### 3.4 ネガティブコントロール (受入 3)

ctrl は head 本体 (測定 commit の判定器)。

| 条件 | 差し替え | DROP / LIVE-IN / UNDETERMINED (関数) | 変わった site (対 ctrl) |
|---|---|---|---|
| ctrl | なし | 3 / 1 / 44 | — |
| 壊す 1 (`--negctl-noprov`) | 規則 6 を外す | 3 / 1 / 44 | 1 (1006ec0 1007021: ONLY_ENTRY_AFTER_CALL → BARRIER(LEAK_STORE)) |
| 壊す 2 (`--negctl-glk`) | 全関数の漏出を True にする | 3 / 1 / 44 | 0 |
| 壊す 3 (`--negctl-nosync`) | rsp/rbp 区間を無効にする | 3 / 1 / 44 | 9 (1354630・454090・45c170・45cda0・45db40・694c80・6c01a0・81bfd0・867220 の判定理由が MIXED_BASE 等に変わる) |

- 壊す 1 は規則 6 が効いていることの証拠 (1006ec0 1007021 だけが変わる)。
- 壊す 2 は関数単位・site 単位ともに変化なし。全関数の漏出を True にしても、head では判定に効かない (`leak` の対象が既に広い)。
- 壊す 3 は関数単位では変化なし・site 単位で 9 件変わる。
- 結果 JSON: `results/negctl_alias_4166_{noprov,glk,nosync}.json`。

### 3.5 差分 (WORKFLOW §6)

- 測定 commit: `c159cf7fe`。結果 JSON・ネガティブコントロールはこの commit の判定器で再生成した。
- 判定器 `audit_frame_store_alias_2211.py`・入力 JSON (`audit_undefload_564_full.json`・`f4_564_post.json`)・PE は `c159cf7fe` から HEAD まで変更なし (`git diff c159cf7fe HEAD -- <これらのファイル>` の出力 0 行)。
- `tools/m11/ldfix` 内の他の差分は main 取り込みで入った他 issue のファイル (`REPORT_3382.md`・`REPORT_3418.md`・`REPORT_4167.md` など) で、本判定の入力・判定器には入らない。
- 本 PR で変更したのは `REPORT_4166.md`・`results/` 4 本・`docs/DOC_MAP.md` の登録行。
- main 取り込み (merge `ddae000b2`) 後に同じ判定器で再実行し、`frame_store_verdict_4166.json` と `cmp` 一致。

## 4. 受入条件の達成状況

| 受入 (Issue の範囲を 1006ec0 に縮小後) | 状態 | 根拠 |
|---|---|---|
| 1. 1006ec0 の store 先ポインタ (`rax`) の由来を機械語で追い、frame を指すかを判定 | 達成 | §3.2 (`rax` ← `[rbp+0x40]` ← 入口 `rcx`。frame を指さない) |
| 2. DROP / LIVE-IN / UNDETERMINED を再判定 (機械語単位の根拠を残す) | 部分 | §3.2・§3.3。1006ec0 の `1007021` は ONLY_ENTRY_AFTER_CALL (#3228)。5cb210 の `5cb4aa` は ALIAS_FRAME_PTR (#4204)。関数単位の判定は head で DROP 3・LIVE-IN 1・UNDETERMINED 44 |
| 3. 測定 commit と HEAD までのコード差分を書く | 達成 | §3.5 |
| 4. 規則を壊すネガティブコントロールを 1 つ以上実行 | 達成 | §3.4 (3 種) |

判定の結論: 1006ec0 の site `1007021` は head で UNDETERMINED (call 越えの ENTRY が残る → #3228)。5cb210 の `5cb4aa` は head で ALIAS_FRAME_PTR により UNDETERMINED。規則 6 は 1006ec0 の `1007021` だけを動かす。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1006ec0 の `1007021` の call 越え ENTRY (呼出し先 `1006ce0`・`1006dd0` が `[rbx+0x40]` の書換えをするかの確認) | 関数 1006ec0 が UNDETERMINED | #3228 [LD-151] (既存) |
| 5cb210 の `rax` (`5cb578 xor eax, ecx`) が frame 派生になる経路。規則 6 の対象外 | 関数 5cb210 が UNDETERMINED | #4204 [LD-204] |
| 呼出し先が caller の frame slot を書く経路 (規則 6 と #2211 の共通仮定) | 規則 6 が成り立つ前提 | #3225 [LD-150] (既存) |
