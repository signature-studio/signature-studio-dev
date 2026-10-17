# 付録: icall #3940 (ICALL-91) — 直接 entry の heap 引数指定 (受入 2 途中経過)

> 親: #3940 (ICALL-91)。PR #6070 の本文から移送した (review round 1 の指摘 2)。
> 測定 commit: `763cba53e`。現 head (`65891fa32`) での再測定は §4 (review round 3・4 の指摘 1 に対応)。
> 単体再現 (`SLOT_SET_R1=b58`) の結果は、測定した環境によって分かれた (§4.2 (b))。原因は未特定。

## 1. 結論

- **受入 2 は未達。** `1806dbcf4` (mode==2 の枝) に届く経路は、どの環境でも確認できていない。
- `SLOT_SET_R1=b58` の単体再現 (`1806dbc10`) は、環境で結果が分かれた。
  - 実装者環境 (§4.2 (b) の「実装者」): rc=97 (`RaiseException` の fail-fast) が 3 回とも再現。`1806dbcf4`・`1810806a0` に 0 hit。
  - reviewer 環境 (round 4 の報告): rc=0 が 3 回とも再現。`1806dbcf4`・`1810806a0` に 0 hit。
  - 同じ head (`65891fa32`) で結果が割れた。ASLR の有無・`OTT_KEEP_XMM0`・build フラグ (`-O0`/`-O1`/`-g`) では変わらなかった (§4.2 (c))。
- 既定の heap 引数 (無指定) の `1806dbc10` は、両環境とも rc=0 で、`1806dbfa7` に 1 回入る。単歩行数は環境で違う (3,468 / 3,415)。
- 旧記載 (`1810806a0` の SIGSEGV (rc=95)・`181065928` の復号結果 `rax` が不正) は、どちらの環境でも再現しなかった。撤回する。

## 2. 直接 entry の引数 (`slot_trace.c` の環境変数)

| 環境変数 | 役割 | 必須の対 |
|---|---|---|
| `SLOT_U32_R0=<off>` | heap[0] の `off` に u32 を書く | `SLOT_U32_R0_VAL=<値>` (無いと exit 2) |
| `SLOT_F32_R0=<off>` | heap[0] の `off` に f32 を書く | `SLOT_F32_R0_VAL=<値>` (無いと exit 2) |
| `SLOT_PTR_R1=<off>` | heap[1] の `off` に heap[2] の値を書く | なし |
| `SLOT_SET_R1=<hex>` | heap[1] を 1 件の集合にし、要素を `heap[0]+<hex>` にする | なし |
| `SLOT_ENC_INIT=1` | `enc(NULL)=cookie` の 12 slot を事前に敷く | なし |

- 上の変数のどれかを指定すると heap は 0x1000 バイト、無指定なら従来どおり 0x400 バイト。
- 直接 entry (`1806dbc10`・`1806f71e0`) の単体再現: `SLOT_SET_R1=b58 SLOT_ENC_INIT=1 <build>/slot_trace "<SlateCore.core_64>" 1806dbc10`。`<build>` は `tools/icall/work/slot_trace`。ビルドは `gcc -O1 -g -o tools/icall/work/slot_trace tools/icall/diff/slot_trace.c tools/ott/native/ms_call.S -lm`。
  `tools/icall/diff/slot_trace.sh` を実行すると、このビルドを上書きする (同じ式で作られるが、バイナリの sha256 は一致しなかった。§4.2 (b))。
- `SlateCore.core_64` は `tools/targets/freshair/fetch.sh` で作る。sha256 は `2cf759f712adf955a56684df4b24454690ac878105d4433de16c88626a45dd3b` (36,285,952 B)。
- 単歩トレースは `SLOT_TRACE_FN=<FN_VA hex>` を付け、`SLOT_TRACE_OUT` で出力先を指定する。

## 3. 移送元の旧記載 (撤回)

PR 本文 (round 1 時点) に書かれていた次の記述は、§4.2 の再測定で再現しなかった。撤回する。

| 旧記載 | 実装者環境 (§4.2 (b)) | reviewer 環境 (round 4) |
|---|---|---|
| `SLOT_SET_R1=b58` で `1806dbcf4` (mode==2 の枝) に入る | 入らない (0 hit。rc=97) | 入らない (0 hit。rc=0) |
| `SLOT_SET_R1=b58` の後 `1810806a0` で SIGSEGV (rc=95) | 再現せず (0 hit) | 再現せず (0 hit) |
| `181065928` の暗号化 slot の復号結果 `rax` が不正 | 到達せず、確認できない | 到達せず、確認できない |
| 既定で `1806dbc10` が 3,474 行 | 3,468 行 (`1806dbfa7` 1 hit) | 3,415 行 (`1806dbfa7` 1 hit) |
| sweep: real 12.492 s・rc 分布 70/44/6/8/2/1 | rc 分布は一致 (§4.2 (a)) | rc 分布は一致 |

## 4. 再測定 (現 head `65891fa32`)

### 4.1 測定 commit から現 head までの差分 (実出力)

`git diff 763cba53e 65891fa32 -- tools/icall/diff tools/ott tools/targets/freshair` の要約:

- `tools/icall/diff/slot_trace.c`: 追加 4 行・変更 1 行 (用法コメントと `SLOT_*_VAL` の引数検査。closure 131 の既定経路は変えない)
- `tools/ott/native/ott_native.c`: 11 行 (`k_HeapAlloc` が `xmm0` を退避・復元する。`OTT_KEEP_XMM0=0` で従来経路。既定は ON。#6050 由来)

`65891fa32` と `4496499a0` の間では、この 2 ファイルは変わっていない (round 4 の指摘と同じ)。

### 4.2 実測

環境: 実装者環境は Intel Xeon Platinum 8370C (2.80 GHz・4 core)・gcc 13.3.0。`tools/icall/work/slot_trace` を head `65891fa32` から build。素材は `plugins-freshair` を `tools/targets/freshair/fetch.sh` で展開、`work-icall` を repo ルートに展開 (`tools/icall/work/` が入る)。

sha256 (実装者環境):
- `SlateCore.core_64`: `2cf759f712adf955…` (36,285,952 B)
- `ott_native.c`: `989a629868c4cf49…`・`ms_call.S`: `894370d8edf3a4c0…`・`slot_trace.c`: `e671055c9a78dcba…`
- `tools/icall/work/slot_trace`: 手動 build `f8afe6ac757122b8…` / `slot_trace.sh` の build `f74794f0f6276cd7…` (同じ式で build しても sha256 が違う。以降の (b) の rc=97 は両方の binary で出た)

(a) `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (n=1・foreground・実装者環境)

- real 12.730 s・user 11.295 s・sys 1.814 s
- `funcs 131 exit {rc=0: 70, rc=124: 1, rc=95: 44, rc=97: 6, rc=98: 8, rc=99: 2}`
- `known 12 hit 3 miss 9`・`distinct zero-fill addrs 10`
- `T1 static entry 20 distinct read 0`・`T2 static entry 34 distinct read 2 max read 6 gap 27`
- reviewer 環境の round 4 の報告 (real 12.567 s・user 11.162 s・sys 1.927 s・rc 分布 70/44/6/8/2/1・`known 12 hit 3 miss 9`・`distinct zero-fill addrs 10`・`T2 max read 6`) と rc 分布・アドレス数が一致する。

(b) `SLOT_SET_R1=b58 SLOT_ENC_INIT=1 <build>/slot_trace "<SlateCore.core_64>" 1806dbc10` (単歩トレース付き・`SLOT_TRACE_FN=1806dbc10`)

| 環境・条件 | rc | 単歩行数 | `1806dbcf4` | `1806dbfa7` | `1810806a0` | stderr |
|---|---|---|---|---|---|---|
| 実装者・手動 build (`f8afe6…`)・単歩付き 1 回 | 97 | 17,454 | 0 | 0 | 0 | `RaiseException(0xe06d7363)`: `__CxxFrameHandler` の dispatch は未実装 — fail-fast |
| 実装者・手動 build (`f8afe6…`)・単歩なし 3 回 | 97 / 97 / 97 | — | — | — | — | 同上 |
| 実装者・`slot_trace.sh` 後の build (`f74794…`)・単歩付き 3 回反復 | 97 / 97 / 97 | 17,454 (3 回とも) | 0 | 0 | 0 | 同上 |
| reviewer 環境 (round 4・head `65891fa32`・3 回反復) | 0 / 0 / 0 | 3,415 | 0 | 1 | 0 | 空 |
| reviewer 環境 (round 4・単歩トレース無し) | 0 | — | — | — | — | stdout は `DONE 1806dbc10` のみ |

(c) 実装者環境で試した条件 (`1806dbc10`・`SLOT_SET_R1=b58 SLOT_ENC_INIT=1`):

- `setarch -R` (ASLR 無効): rc=97 (fail-fast の位置は同じ)
- `OTT_KEEP_XMM0=0`: rc=97
- build フラグ `-O0 -g`・`-O1 -g -fno-omit-frame-pointer`: rc=97
- 既定 (`SET` なし・`SLOT_ENC_INIT=1`): rc=0・3,468 行・`1806dbfa7` に 1 回入る・`1806dbcf4` には入らない

(d) 食い違いの扱い: 同じ head `65891fa32` で、実装者環境は rc=97、reviewer 環境は rc=0 だった。round 3 の reviewer 測定 (head `4496499a0`) は rc=97 で、実装者環境と一致する。反復と条件を変えても、実装者環境の結果は変わらなかった。環境差の原因 (CPU・libc・RaiseException の経路・素材の展開元のいずれか) は未特定。reviewer 環境の正確な CPU・gcc 版は、こちらでは分からない。

### 4.3 次の作業

- 受入 2 を進めるには、`1806dbcf4` に届く経路が要る。`RaiseException` が出る経路 (`__CxxFrameHandler` の dispatch) を実装するか、その経路を迂回する条件を見つける必要がある。
- 食い違いの原因特定 (reviewer 環境の CPU・gcc 版・素材の sha256 の照合) は #3940 に残す。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 2: `1806dbcf4` に届く経路が未確定。単体再現 (`SLOT_SET_R1=b58`) は実装者環境で rc=97 (C++ EH の dispatch 未実装)、reviewer 環境で rc=0 と結果が分かれる | 受入 2・3 が未達 | #3940 (本 issue に残す) |
| 受入 1: int3 を使わない 4 命令の動的採取方式 | 受入 1 が未達 | #3940 (本 issue に残す) |
| 受入 3: 届く添字との差 | 受入 3 が未達 | #3940 (受入 2 の後) |
