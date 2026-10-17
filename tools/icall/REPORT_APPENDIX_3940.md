# 付録: icall #3940 (ICALL-91) — 直接 entry の heap 引数指定 (受入 2 途中経過)

> 親: #3940 (ICALL-91)。PR #6070 の本文から移送した (review round 1 の指摘 2)。
> 測定 commit: `763cba53e` (コードを変えた最後の commit)。以後のコード差分は `tools/icall/diff/slot_trace.c` の用法コメントと引数検査のみ (`git diff 763cba53e HEAD -- tools/icall/diff/slot_trace.c`)。
> **注意**: 本付録の数値は PR 本文の記載を移したもので、移送時点では素材 (`freshair` の作業ディレクトリ・`icall/work`) が手元に無く再測定していない。再測定の結果は下の §4 に別途書く。

## 1. 結論

- **受入 2 は未達。** mode==2 の枝 `1806dbcf4` までは入る。ループ本体 `1806dbe5a` には未到達。
- 既定の heap 引数では集合判定 `180d215e0` が偽になり、`1806dbfa7` に抜けてループに入らない。
- `SLOT_SET_R1=b58` で 1 件入れると `1806dbcf4` に入るが、その後 `1810806a0` (`jmp rax`) で SIGSEGV (rc=95) になる。
- **`SLOT_ENC_INIT=1` を付けても SIGSEGV は解消しない。原因は未確認。**

## 2. 直接 entry の引数 (`slot_trace.c` の環境変数)

| 環境変数 | 役割 | 必須の対 |
|---|---|---|
| `SLOT_U32_R0=<off>` | heap[0] の `off` に u32 を書く | `SLOT_U32_R0_VAL=<値>` (無いと exit 2) |
| `SLOT_F32_R0=<off>` | heap[0] の `off` に f32 を書く | `SLOT_F32_R0_VAL=<値>` (無いと exit 2) |
| `SLOT_PTR_R1=<off>` | heap[1] の `off` に heap[2] の値を書く | なし |
| `SLOT_SET_R1=<hex>` | heap[1] を 1 件の集合にし、要素を `heap[0]+<hex>` にする | なし |
| `SLOT_ENC_INIT=1` | `enc(NULL)=cookie` の 12 slot を事前に敷く | なし |

- 上の変数のどれかを指定すると heap は 0x1000 バイト、無指定なら従来どおり 0x400 バイト。
- 直接 entry (`1806dbc10`・`1806f71e0`) の単体再現: `SLOT_SET_R1=b58 SLOT_ENC_INIT=1 <build>/slot_trace "<SlateCore.core_64>" 1806dbc10`。`<build>` は `gcc -O1 -g -o slot_trace tools/icall/diff/slot_trace.c tools/ott/native/ms_call.S -lm` で作る。`slot_trace.sh` は 131 関数すべてを回すため、単体の確認には使わない。
- 単歩トレースは `SLOT_TRACE_FN=<FN_VA hex>` を付け、`SLOT_TRACE_OUT` で出力先を指定する。

## 3. PR 本文に記載されていた実測 (移送分・未再測定)

| 項目 | 値 (PR 本文の記載) |
|---|---|
| `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (foreground・n=1) | real 12.492 s・user 11.126 s・sys 1.866 s・load 0.17 → 0.36 |
| 結果 | `funcs 131`・rc=0: 70・rc=95: 44・rc=97: 6・rc=98: 8・rc=99: 2・rc=124: 1 |
| 既定動作との一致 | main の `REPORT.md` §9.2 と一致 (既定動作が変わっていない確認) |
| `1806dbc10` の単歩トレース (既定の heap 引数) | 3,415 命令。集合判定が偽で `1806dbfa7` に抜ける |
| `SLOT_SET_R1=b58` | `1806dbcf4` (mode==2 の枝) に入る |
| `SLOT_SET_R1=b58` の後 | `1810806a0` (`jmp rax`) で SIGSEGV (rc=95)。`181065928` の暗号化 slot の復号結果 `rax` が不正 |

## 4. 再測定 (未実施)

- 本 run では素材不足 (`freshair` 作業ディレクトリ・`icall/work` が無い) のため再測定していない。
- 未解決: `1810806a0` の SIGSEGV の原因。`1806dbd25` 以降の `0x1810492b0`・`0x1810483f4` 等の呼出しが `rax`/`rcx` を変える、という仮説は未確認。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `1810806a0` の SIGSEGV を越え、`1806dbe5a` (ループ本体) まで届く heap の中身 | 受入 2・3 が未達 | #3940 (本 issue に残す) |
| `SLOT_ENC_INIT=1` でも解消しない SIGSEGV の原因 | 同上 | #3940 |
