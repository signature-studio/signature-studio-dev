# REPORT_4166 — 1006ec0・5cb210 の漏出 store の別名判定 (#4166 / 親 #3225)

## 1. 測定条件

- 測定 commit: `6e8a67464` (判定器の規則 (6) NONFRAME を入れた commit)。この commit で `results/frame_store_verdict_4166.json` を生成し、HEAD で再実行して `cmp` 一致 (byte 同一)。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211 と同じ)。
- PE: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 判定器 `audit_frame_store_alias_2211.py` (規則 6 を追加)。実行時間 0.22 秒 (HEAD での再実行)。
- 前提の再現: 変更前の判定器 (`--negctl-noprov`) の出力が `results/frame_store_verdict_2211.json` と site・関数単位で一致 (DROP 3・LIVE-IN 35・UNDETERMINED 10 / site 単位 DROP 3・LIVE-IN 36・UNDETERMINED 11・PTR_READ 1)。

## 2. 方式 (#2211 からの変更点: 規則 6)

#2211 の規則 (CFG 逆向き探索・3 値判定・glk・rsp/rbp 区間) は変えない。追加するのは次の 1 点。

- **NONFRAME**: glk 関数のポインタ経由 store は、基底レジスタが入口の引数値 (rcx・rdx・r8・r9 で、その前に定義が無い値) から、無改変の 8 バイト slot (`mov [rbp+D], reg`) を経て来るとき、LEAK_STORE と数えない。
  - 根拠: 入口の引数値は呼び出し元の生きたポインタで、この関数の frame (戻り番地より下) を指さない。
  - 成立条件: slot の書きが全て frame 派生でない値の 8 バイト store で、入口まで未定義の経路が無いこと。
  - 仮定 (#2211 と同じ、未検証): call は caller の frame slot を書かない。NONFRAME の判定は call を越える経路も透過する。

ネガティブコントロール用の切替: `--negctl-noprov` (規則 6 を外す)。

## 3. 結果

### 3.1 関数単位 (受入 2)

| 判定 | #2211 | #4166 |
|---|---|---|
| DROP | 3 | 3 |
| LIVE-IN | 35 | 35 |
| UNDETERMINED | 10 | 10 |

関数の判定は変わらない。site の変化は 1 件だけ。

### 3.2 対象 2 関数の site 判定 (受入 2)

| 関数 | 読み | #2211 | #4166 | 根拠 (機械語) |
|---|---|---|---|---|
| 1006ec0 | `1006fb6 cmp dword ptr [rbp+0x2c], 1` | ONLY_ENTRY_AFTER_CALL | 同左 | 変化なし。残る経路は call 越えの ENTRY (#3228) |
| 1006ec0 | `1007021 cmp byte ptr [rbp+0x2b], 0` | BARRIER(LEAK_STORE) | ONLY_ENTRY_AFTER_CALL | 打ち切りの store `1006fe8 mov [rax+0x64], 0` は NONFRAME。`rax` は `1006fe4` の `mov rax, [rbp+0x40]`、`[rbp+0x40]` は入口 `1006ec8 mov [rbp+0x40], rcx` だけで書かれる (`rcx` は入口の引数)。残る経路は call 越えの ENTRY (`1006f21` `call 0x1006ce0`、`1006ff5` `call 0x1006dd0` を越える) |
| 5cb210 | `5cb4aa cmp qword ptr [rbp+0xc0], 0` | BARRIER(LEAK_STORE) | 同左 (打ち切り先が変化) | 打ち切りの store `5cb47d mov [rax+8], ecx` は NONFRAME (`rax` は `[rbp+0x198]`、入口 `5cb237 mov [rbp+0x198], r9` だけで書かれる)。新しい打ち切りは `5cb456 movsq qword ptr [rdi], qword ptr [rsi]` (LEAK_STORE)。`rdi` は `5cb43c mov rdi, [rbp+0x148]`、`[rbp+0x148]` は `5cb3d8` で `call 0x409410` の戻り値 (`5cb3d3`) から書かれる |

- 1006ec0 の漏出 (glk) の起点 `1006ec8 mov [rbp+0x40], rcx` は残る (`rcx` は入口の引数)。これだけでは store 先の別名は示せない。
- 5cb210 の漏出 (glk) の起点 `5cb21e mov [rbp+0x68], rbp` は残る。frame 自身を指す store。

### 3.3 site 単位の変化 (受入 2)

- #2211 からの変化は `1006ec0 1007021` の 1 件だけ (`BARRIER(LEAK_STORE)` → `ONLY_ENTRY_AFTER_CALL`)。
- 51 site の合計: DROP 3・LIVE-IN 36・UNDETERMINED 11・PTR_READ 1 (#2211 と同じ)。

### 3.4 ネガティブコントロール (受入 3)

| 条件 | 差し替え | DROP / LIVE-IN / UNDETERMINED (関数) | 変わった site (対 ctrl) |
|---|---|---|---|
| ctrl | なし | 3 / 35 / 10 | — |
| 壊す 1 (`--negctl-noprov`) | 規則 6 を外す | 3 / 35 / 10 | 0 (#2211 の記録と site 単位で完全一致) |
| 壊す 2 (`--negctl-glk`) | 全関数の漏出を True にする | 3 / 1 / 44 | 1 (1006ec0 1007021 が BARRIER(LEAK_STORE) に戻る) |
| 壊す 3 (`--negctl-nosync`) | rsp/rbp 区間を無効にする | 3 / 28 / 17 | 2 (1006ec0 1007021 と 694c80 6951c8) |

- 壊す 1 の site 単位の結果は #2211 の記録 (`results/frame_store_verdict_2211.json`) と完全に一致する。規則 6 が効いていることの証拠。
- 壊す 2・壊す 3 の結果 JSON は `results/negctl_alias_4166_glk.json`・`results/negctl_alias_4166_nosync.json`。#2211 の同名の記録 (`negctl_alias_2211_*.json`) との差は上の変わった site と同じ 1〜2 件 (規則 6 の追加による)。

### 3.5 差分 (WORKFLOW §6)

- 測定 commit: `6e8a67464`。判定器・結果 JSON・ネガティブコントロールはこの commit で生成した。
- この commit から HEAD までの `tools/m11/ldfix` の差分: 本 REPORT (`REPORT_4166.md`) と DOC_MAP の登録だけ。判定器・結果 JSON は変えていない。

## 4. 受入条件の達成状況

| 受入 (Issue の範囲を 1006ec0 に縮小後) | 状態 | 根拠 |
|---|---|---|
| 1. 1006ec0 の store 先ポインタ (`rax`) の由来を機械語で追い、frame を指すかを判定 | 達成 | §3.2 (`rax` ← `[rbp+0x40]` ← 入口 `rcx`。frame を指さない) |
| 2. 機械語単位の根拠を REPORT に残す | 達成 | §3.2 |
| 3. 測定 commit と HEAD までのコード差分を書く | 達成 | §3.5 |
| 4. 規則を壊すネガティブコントロールを 1 つ以上実行 | 達成 | §3.4 (3 種) |

関数 1006ec0 の判定そのもの (DROP / LIVE-IN / UNDETERMINED) は未確定 (`1007021` は call 越えの ENTRY が残る → #3228)。5cb210 は #4204 へ移した。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1006ec0 の `1007021` の call 越え ENTRY (呼出し先 `1006ce0`・`1006dd0` が `[rbx+0x40]` の書換えをするかの確認) | 関数 1006ec0 が UNDETERMINED | #3228 [LD-151] (既存) |
| 5cb210 の `5cb456 movsq [rdi]` の基底 `rdi` (call `409410` の戻り値) | 関数 5cb210 が UNDETERMINED | #4204 [LD-204] |
| 呼出し先が caller の frame slot を書く経路 (規則 6 と #2211 の共通仮定) | 規則 6 が成り立つ前提 | #3225 の範囲 (既存) |
