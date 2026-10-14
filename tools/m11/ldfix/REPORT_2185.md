# REPORT_2185 — FRAME_IN_ESCAPED 残 46 関数の store 判定を CFG 逆向き探索に拡張 (#2185 / 親 #2144)

## 1. 測定条件

- 測定 commit: `a511e0c7` (判定を理由コード付きにした版)。
  コード変更の commit は `a73ec8b3` (CFG 逆向き探索) → `3e01f9b7` (call 越えの live-in を区別) → `a511e0c7` (理由コード `ONLY_ENTRY_AFTER_CALL` 追加)。
- 入力: `results/audit_undefload_564_full.json` (`frame_in_escaped` 56 行・53 関数)・`results/f4_564_post.json` (F4 修復関数を除外)。
- 判定対象: **48 関数・51 site** (`frame_in_escaped` から F4 修復の 5 関数を除いた残り)。
- PE: `fl-win64` の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`)。
- 判定 `audit_frame_store_verdict.py`: 0.15 秒、rc 0。load average 0.2 (4 vCPU)。
- 結果 JSON: `results/frame_store_verdict_2185.json`。判定は PE の機械語のみで、IR (`work-m11`) は使っていない。

## 2. 方式

- 読み命令の frame slot (rbp/rsp 基底・index なし) について、同じ関数の機械語 CFG を**逆向き**に辿る。
  分岐・合流の辺はブロック境界として越える (旧版は直前の straight-line 区間だけを見ていた)。
- 経路ごとの事象:
  - `STORE`: 同じ slot を覆う単純 store (DEF)。その経路は定義済み。
  - `CALL`: 関数内で frame がアドレス取得 (escaped) されている場合の call。store 探索は越える。
    call を越えて関数先頭 (ENTRY) に達した経路は `ENTRY_AFTER_CALL` (callee がポインタ経由で定義した可能性があるので live-in と断定しない)。
  - `BARRIER`: escaped 関数のポインタ経由 store、基底の異なる / 部分重なりの store、rbp/rsp 基底の RMW。
  - `ENTRY`: call を越えず関数先頭に達した (関数内に定義が無い)。
- 判定:
  - `DROP`: 全経路が STORE。機械語上は store があるのに IR の読みが undef (脱落候補)。
  - `LIVE-IN`: 全経路が ENTRY。
  - `UNDETERMINED`: それ以外。理由コード `BARRIER` / `ONLY_ENTRY_AFTER_CALL` / `MIXED_OR_UNREACHABLE` / `IJMP` で区別。
- 限界 (近似): `escaped` は `lea` と `mov reg, rbp|rsp` だけを見る。`mov [mem], rbp` のように frame アドレスをメモリへ書き出すケースは見ていない。今回の DROP / LIVE-IN の site は straight-line 区間内の store に依存する。この限界で結論は変わらないと確認した (指摘 4)。
- 関数内に関数外・不明な飛び先への jump があると CFG 不完全として `IJMP` で全 site を未判定にする (本測定では該当 0 件)。

## 3. 結果

### 3.1 受入条件 1・2: 48 関数の 3 値判定

| 判定 | 関数数 | site 数 (51 中) |
|---|---|---|
| DROP | 3 | 3 |
| LIVE-IN | 1 | 1 |
| UNDETERMINED | 44 | 46 |
| NOSLOT (読みが frame 基底でない) | — | 1 (7e45e0) |

- UNDETERMINED 44 関数の内訳 (関数単位): `ONLY_ENTRY_AFTER_CALL` のみ 25 関数 (call を越えて ENTRY に達するだけ)、`BARRIER` のみ 18 関数 (ポインタ経由 store・部分重なりで打ち切り)、両方が混在 1 関数。したがって「BARRIER 19」は混在 1 関数を BARRIER 側に数えた値 (25 + 19 = 44)。site 単位の理由は `ONLY_ENTRY_AFTER_CALL` 27・`BARRIER` 19 (`sites[*].why`)。
- 関数単位の判定は、site が全て DROP なら DROP、全て LIVE-IN なら LIVE-IN、それ以外は UNDETERMINED。
- 未判定 44 関数の一覧 (関数 / 判定 / 理由コード / 読み site)。理由コードは関数内の site から取った主因 (`BARRIER` を優先)。site 単位の理由は `results/frame_store_verdict_2185.json` の `sites[*].why` が正本。

| 関数 | 判定 | 理由コード (主) | 読み site |
|---|---|---|---|
| 1006ec0 | UNDETERMINED | BARRIER | 1006fb6, 1007021 |
| 103aa50 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 103ab59 |
| 11e6e20 | UNDETERMINED | BARRIER | 11e6fdb |
| 129df10 | UNDETERMINED | BARRIER | 129e1d6 |
| 12cb2e0 | UNDETERMINED | BARRIER | 12cb416 |
| 1354630 | UNDETERMINED | BARRIER | 1354784 |
| 4078c0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 40792b, 40791e |
| 418b40 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 418b57 |
| 441730 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 44178f |
| 4488f0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 44892d |
| 454090 | UNDETERMINED | BARRIER | 454637 |
| 45c170 | UNDETERMINED | BARRIER | 45c1b5 |
| 45cda0 | UNDETERMINED | BARRIER | 45cdd9 |
| 45d8b0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 45da5b |
| 45db40 | UNDETERMINED | BARRIER | 45db85 |
| 45dc20 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 45dc69 |
| 5c4dc0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 5c4e43 |
| 5cb210 | UNDETERMINED | BARRIER | 5cb4aa |
| 639c70 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 639c83 |
| 694c80 | UNDETERMINED | BARRIER | 6951c8 |
| 695640 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 6956f9 |
| 6c01a0 | UNDETERMINED | BARRIER | 6c0207 |
| 6c7610 | UNDETERMINED | BARRIER | 6c7665 |
| 6c7ca0 | UNDETERMINED | BARRIER | 6c7ccc |
| 6ca580 | UNDETERMINED | BARRIER | 6ca5c2 |
| 6ca6c0 | UNDETERMINED | BARRIER | 6ca702 |
| 6ced00 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 6ced14 |
| 7e45e0 | UNDETERMINED | BARRIER | 7e48d6, 7e47b6 (NOSLOT) |
| 808930 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 80896d |
| 808c80 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 808ca4 |
| 81bfd0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 81bff3 |
| 81c0d0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 81c118 |
| 820d60 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 820dba |
| 824020 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 824069 |
| 864f80 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 864f94 |
| 867220 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 867245 |
| 92ea90 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | 92eaaf |
| bf8b40 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | bf8b68 |
| c3b340 | UNDETERMINED | BARRIER | c3b46f |
| c9cf70 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | c9cf8f |
| da5400 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | da541f |
| da5510 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | da552f |
| e8fba0 | UNDETERMINED | ONLY_ENTRY_AFTER_CALL | e8fc08 |
| f61710 | UNDETERMINED | BARRIER | f61ce6 |

DROP (全経路で store が到達。読みと全経路の store を機械語で示す):

| 関数 | 読み (機械語) | 全経路の store (機械語) |
|---|---|---|
| 10628a0 | `10628c0 movzx rax, word [rbp+0x4e]` | `10628bc mov word [rbp+0x4e], ax` |
| 13105d0 | `1310837 add eax, dword [rbp+0x48]` | `1310826 mov qword [rbp+0x44], rax` (`[rbp+0x48]` の 4 バイトを覆う) |
| c38bd0 | `c38c08 cmp qword [rbp+0x78], 0` | `c38c04 mov qword [rbp+0x78], rax` |

LIVE-IN:

| 関数 | 読み (機械語) | 理由 |
|---|---|---|
| 412160 | `41217d cmp dword [rbp+0x170], 2` | 全経路で store に当たらず関数先頭に達する (call なし) |

### 3.2 受入条件 3: 機械語 read / store 単位の根拠

- DROP 3 関数と LIVE-IN 1 関数は上表の read / store を 1 site 以上示した。
- UNDETERMINED の各 site の read・経路の barrier 機械語 addr は `results/frame_store_verdict_2185.json` の `sites[*]` (`addr` / `slot` / `outcomes` / `barrier_addrs`) に残した。

### 3.3 ネガティブコントロール (WORKFLOW §5)

判定器本体 `audit_frame_store_verdict.py` は変更せず、`negctl_frame_store_2185.py` が `effect()` を 1 命令だけ差し替えて `main()` を再実行する。結果は `results/negctl_frame_store_2185.json`。PE・入力は本文 §1 と同じ。0.29 秒、rc 0。

| 条件 | 差し替え | 10628a0 | 412160 | 13105d0 | c38bd0 | 関数 DROP / LIVE-IN / UNDET |
|---|---|---|---|---|---|---|
| ctrl | なし | DROP | LIVE-IN | DROP | DROP | 3 / 1 / 44 |
| 壊す 1 | 10628a0 の store `10628bc` を無効化 | **UNDETERMINED** (`ONLY_ENTRY_AFTER_CALL`) | LIVE-IN | DROP | DROP | 2 / 1 / 45 |
| 壊す 2 | 412160 の読み `41217d` の直前 `412176` (`lea r13, ...`) を DEF 扱い | DROP | **DROP** (`ALL_PATHS_STORE`) | DROP | DROP | 4 / 0 / 44 |

- 壊す 1 で 10628a0 の DROP が消えること、壊す 2 で 412160 の LIVE-IN が DROP に変わることを確認した。DROP / LIVE-IN の判定は store 1 件の有無に依存する。
- 再現: `python3 tools/m11/ldfix/negctl_frame_store_2185.py <PE> results/audit_undefload_564_full.json results/f4_564_post.json <out>`。

### 3.4 受入条件 4: コード差分

- 測定 commit `a511e0c7` から HEAD までの `tools/m11/ldfix` の差分は、この REPORT と結果 JSON・negctl の追加のみ。判定器 `.py` の差分は 0 行 (`audit_frame_store_verdict.py`)。
- 差分出力は下記 §3.5 を参照。判定器の測定 commit は `a511e0c7` のまま (判定器 `.py` に差分が無いため再測定は不要)。negctl は HEAD で実行した (§3.3)。

### 3.5 差分の出力 (WORKFLOW §6)

コマンド: `git diff --stat a511e0c7 HEAD -- tools/m11/ldfix`、`git diff --name-status a511e0c7 HEAD -- tools/m11/ldfix`、`git diff a511e0c7 HEAD -- tools/m11/ldfix/audit_frame_store_verdict.py | wc -l`。測定 HEAD は `957215f1` (この節の出力を取った commit)。この後の commit で変わるのは `REPORT_2185.md` のみで、結果 JSON・negctl・判定器 `.py` は変わらない。最新 HEAD の差分は PR 本文の検証結果に載せる。

```
 tools/m11/ldfix/REPORT_2185.md                     |  165 +++
 tools/m11/ldfix/negctl_frame_store_2185.py         |   61 ++
 .../ldfix/results/frame_store_verdict_2185.json    | 1067 ++++++++++++++++++++
 .../m11/ldfix/results/negctl_frame_store_2185.json |  108 ++
 4 files changed, 1401 insertions(+)
A	tools/m11/ldfix/REPORT_2185.md
A	tools/m11/ldfix/negctl_frame_store_2185.py
A	tools/m11/ldfix/results/frame_store_verdict_2185.json
A	tools/m11/ldfix/results/negctl_frame_store_2185.json
0
```

判定器 `audit_frame_store_verdict.py` の差分は 0 行。追加 4 件はいずれも判定の結果・検証スクリプト・REPORT。

## 4. 旧版 (REPORT_2144) との差

- 旧版 (直前 straight-line のみ) の判定は DROP 2 (10628a0 / c38bd0)・未判定 46。
  新版 (CFG 逆向き) は DROP 3 (13105d0 が追加)・LIVE-IN 1 (412160)・未判定 44。
- 旧 DROP 2 件は新版でも DROP。
- 本 REPORT の数値は全て本 commit の結果 JSON から数えた値。REPORT_2144 の 48 関数・SUSPECT 件数とは定義が違うため比較しない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| UNDETERMINED 44 関数 (ONLY_ENTRY_AFTER_CALL 25・BARRIER 19) の DROP / LIVE-IN 確定。7e45e0 の NOSLOT 1 site を含む | 脱落か live-in か未確定 | #2211 [LD-87] |
| DROP 3 関数のうち 13105d0 の IR 側確認 (10628a0 / c38bd0 は #2214 [LD-82] で確認済み: REPORT_2186 §2.1) | 機械語上の DROP 候補 13105d0 が IR で本当に undef か未確認 | #2235 [LD-90] |

## 6. 子 issue

- #2211 [LD-87] FRAME_IN_ESCAPED 未判定 44 関数の call 越え・ポインタ store の別名解析 (#2185 残件)
- #2235 [LD-90] DROP 候補 13105d0 の IR 側確認 (#2185 残件。10628a0 / c38bd0 は #2214 で確認済み)
