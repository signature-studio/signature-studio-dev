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
- 関数内に関数外・不明な飛び先への jump があると CFG 不完全として `IJMP` で全 site を未判定にする (本測定では該当 0 件)。

## 3. 結果

### 3.1 受入条件 1・2: 48 関数の 3 値判定

| 判定 | 関数数 | site 数 (51 中) |
|---|---|---|
| DROP | 3 | 3 |
| LIVE-IN | 1 | 1 |
| UNDETERMINED | 44 | 46 |
| NOSLOT (読みが frame 基底でない) | — | 1 (7e45e0) |

- UNDETERMINED 44 関数の内訳 (関数単位): `ONLY_ENTRY_AFTER_CALL` 25 関数 (call を越えて ENTRY に達するだけ)、`BARRIER` 19 関数 (ポインタ経由 store・部分重なりで打ち切り)。
- 関数単位の判定は、site が全て DROP なら DROP、全て LIVE-IN なら LIVE-IN、それ以外は UNDETERMINED。

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

### 3.3 受入条件 4: コード差分

- 測定 commit `a511e0c7` から HEAD までの `tools/m11/ldfix` の差分は、この REPORT と結果 JSON の追加のみ。`.py` の差分は 0 行。

## 4. 旧版 (REPORT_2144) との差

- 旧版 (直前 straight-line のみ) の判定は DROP 2 (10628a0 / c38bd0)・未判定 46。
  新版 (CFG 逆向き) は DROP 3 (13105d0 が追加)・LIVE-IN 1 (412160)・未判定 44。
- 旧 DROP 2 件は新版でも DROP。
- 本 REPORT の数値は全て本 commit の結果 JSON から数えた値。REPORT_2144 の 48 関数・SUSPECT 件数とは定義が違うため比較しない。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| UNDETERMINED 44 関数 (ONLY_ENTRY_AFTER_CALL 25・BARRIER 19) の DROP / LIVE-IN 確定。7e45e0 の NOSLOT 1 site を含む | 脱落か live-in か未確定 | 子 issue (本 run で起票・番号は §6) |
| DROP 3 関数 (10628a0 / 13105d0 / c38bd0) の IR 側確認 | 機械語上の DROP 候補が IR で本当に undef か未確認 | #2186 [LD-82] |
| 入力 IR を `m11_gen_ir2.sh` で再生成して sites 2,737 と突き合わせる | 2,731 と 2,737 の差の原因未確認 | #2186 [LD-82] |

## 6. 子 issue

- 起票番号: (作成後に記入)
