# 付録: icall #3940 (ICALL-91) — 直接 entry の heap 引数指定 (受入 2 途中経過)

> 親: #3940 (ICALL-91)。PR #6070 の本文から移送した (review round 1 の指摘 2)。
> 測定 commit: `763cba53e`。現 head の再測定は §4 (review round 3 の指摘 1 に対応)。
> 再測定の結果、移送元 (§3 旧記載) の `SLOT_SET_R1=b58` の挙動は現 head でも測定 commit でも再現しなかった。

## 1. 結論

- **受入 2 は未達。** `SLOT_SET_R1=b58` を付けて直接 entry `1806dbc10` を単体で走らせると、
  `RaiseException` (C++ 例外, 0xe06d7363) の時点で fail-fast (rc=97) になる。
  `__CxxFrameHandler` の dispatch が未実装のためで、`1806dbcf4` (mode==2 の枝) に到達しない。
- 既定の heap 引数 (無指定) では、`1806dbc10` は rc=0 で終わり、集合判定が偽になって `1806dbfa7` に 1 回抜ける。
- 旧記載 (`1806dbcf4` に入る・`1810806a0` で SIGSEGV (rc=95)・`SLOT_ENC_INIT=1` で解消しない) は、
  本再測定では確認できなかった。付録から外し、§4.2 の実測で置き換える。

## 2. 直接 entry の引数 (`slot_trace.c` の環境変数)

| 環境変数 | 役割 | 必須の対 |
|---|---|---|
| `SLOT_U32_R0=<off>` | heap[0] の `off` に u32 を書く | `SLOT_U32_R0_VAL=<値>` (無いと exit 2) |
| `SLOT_F32_R0=<off>` | heap[0] の `off` に f32 を書く | `SLOT_F32_R0_VAL=<値>` (無いと exit 2) |
| `SLOT_PTR_R1=<off>` | heap[1] の `off` に heap[2] の値を書く | なし |
| `SLOT_SET_R1=<hex>` | heap[1] を 1 件の集合にし、要素を `heap[0]+<hex>` にする | なし |
| `SLOT_ENC_INIT=1` | `enc(NULL)=cookie` の 12 slot を事前に敷く | なし |

- 上の変数のどれかを指定すると heap は 0x1000 バイト、無指定なら従来どおり 0x400 バイト。
- 直接 entry (`1806dbc10`・`1806f71e0`) の単体再現: `SLOT_SET_R1=b58 SLOT_ENC_INIT=1 <build>/slot_trace "<SlateCore.core_64>" 1806dbc10`。`<build>` は `tools/icall/work/slot_trace` (`gcc -O1 -g -o tools/icall/work/slot_trace tools/icall/diff/slot_trace.c tools/ott/native/ms_call.S -lm` で作る)。`slot_trace.sh` は 131 関数すべてを回すため、単体の確認には使わない。
- 単歩トレースは `SLOT_TRACE_FN=<FN_VA hex>` を付け、`SLOT_TRACE_OUT` で出力先を指定する。

## 3. 移送元の旧記載 (現 head で再現せず・撤回)

PR 本文 (round 1 時点) に書かれていた次の記述は、§4.2 の再測定で再現しなかった。撤回する。

| 旧記載 | 再測定の結果 (§4.2) |
|---|---|
| `SLOT_SET_R1=b58` で `1806dbcf4` (mode==2 の枝) に入る | 入らない (0 hit。rc=97 で fail-fast) |
| `SLOT_SET_R1=b58` の後 `1810806a0` で SIGSEGV (rc=95) | 再現せず (`1810806a0` に 0 hit) |
| `181065928` の暗号化 slot の復号結果 `rax` が不正 | 到達せず、確認できない |
| `1806dbc10` 既定で 3,415 命令 | 3,474 行 (現 head)。`1806dbfa7` に 1 回入る |
| sweep: real 12.492 s・rc 分布 70/44/6/8/2/1 | 現 head で一致 (§4.2 (a))。rc 分布は一致 |

## 4. 再測定 (現 head `4496499a0`・素材 `plugins-freshair`・`work-icall`)

### 4.1 測定 commit から現 head までの差分 (実出力)

`git diff 763cba53e 4496499a0 -- tools/icall/diff tools/ott tools/targets/freshair` の要約:

- `tools/icall/diff/slot_trace.c`: 追加 4 行・変更 1 行 (用法コメントと `SLOT_*_VAL` の引数検査。closure 131 の既定経路は変えない)
- `tools/ott/native/ott_native.c`: 11 行 (`k_HeapAlloc` が `xmm0` を退避・復元する。`OTT_KEEP_XMM0=0` で従来経路。既定は ON。#6050 由来)

### 4.2 実測

環境: `tools/icall/work/slot_trace` を現 head で build。素材は `plugins-freshair` を `tools/targets/freshair/fetch.sh` で展開、`work-icall` を `tools/icall/work/` に展開。`SlateCore.core_64` は 36,285,952 B。

(a) `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (n=1・foreground)

- real 12.567 s・user 11.162 s・sys 1.927 s
- `funcs 131 exit {rc=0: 70, rc=124: 1, rc=95: 44, rc=97: 6, rc=98: 8, rc=99: 2}`
- `known 12 hit 3 miss 9`・`distinct zero-fill addrs 10`
- `T1 static entry 20 distinct read 0`・`T2 static entry 34 distinct read 2 max read 6 gap 27`
- 付録 §3 の旧記載 (real 12.492 s) と同等。rc 分布は一致。

(b) `SLOT_SET_R1=b58 SLOT_ENC_INIT=1 <build>/slot_trace "<SlateCore.core_64>" 1806dbc10`

| 条件 | rc | 単歩トレース行数 | `1806dbcf4` | `1806dbfa7` | `1810806a0` | stderr |
|---|---|---|---|---|---|---|
| 現 head `4496499a0` | 97 | 17,622 | 0 | 0 | 0 | `RaiseException(0xe06d7363)`: frame #3 に handler あり。`__CxxFrameHandler` の dispatch は未実装 — fail-fast |
| 現 head・`OTT_KEEP_XMM0=0` | 97 | 15,928 | 0 | — | — | 同上 |
| 測定 commit `763cba53e` (別 worktree・別ビルド) | 97 | 15,811 | 0 | — | — | 同上 |

- 既定 (`SET` なし・`SLOT_ENC_INIT` なし) の `1806dbc10`: rc=0・3,474 行、`1806dbfa7` に 1 回入る、`1806dbcf4` には入らない。

結論: `SLOT_SET_R1=b58` の単体再現は、現 head でも測定 commit でも、`1806dbcf4` に入らず、C++ EH の fail-fast (rc=97) で止まる。`1810806a0` の SIGSEGV は再現しなかった。`OTT_KEEP_XMM0` の ON/OFF で結果は変わらない。

### 4.3 次の作業

- 受入 2 を進めるには、`1806dbcf4` に入る前に通る C++ EH の経路 (`RaiseException` → `__CxxFrameHandler` の dispatch) を実装するか、その経路を迂回する条件を見つける必要がある。この作業は #3940 に残す。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2: `SLOT_SET_R1=b58` の単体再現が `RaiseException` (C++ EH の dispatch 未実装) で rc=97 になり、`1806dbcf4` に届かない | 受入 2・3 が未達 | #3940 (本 issue に残す) |
| 受入 1: int3 を使わない 4 命令の動的採取方式 | 受入 1 が未達 | #3940 (本 issue に残す) |
| 受入 3: 届く添字との差 | 受入 3 が未達 | #3940 (受入 2 の後) |
