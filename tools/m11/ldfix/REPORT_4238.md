# REPORT_4238 — 407a50 の戻り値の別名判定と 5cb210 `5cb4aa` の rdi 経路 (#4238 / 親 #4204)

## 1. 結論

- 受入 1 (`407a50` の戻り値 `rax` の全経路) は**示せなかった**。`ret` の `rax` は、関数内の最後の代入 (`407df9`・`407c04` 系) とメモリ読み・呼び出し先の戻り値から来る。呼び出し先のうち `4073c0`・`4073d0`・`4073e0`・`4073f0` は `.pdata` に無い import thunk (`jmp qword ptr [rip+X]`) で、先の実装が `block00031_PE.bin` の外にあるため戻り値を機械語で追えない (§3.2)。
- 受入 3 の理由はこの 2 点。
- `5cb210` `5cb4aa` の読みは `cmp qword ptr [rbp+0xc0], 0` で、`rdi` を基底にしない。issue 本文の前提 (`rdi` が `409410` の戻り値から来る) は当たらない。`409410` の戻り値は `[rbp+0x148]` に入り、`rdi` は `5cb443` でそこから読まれるが、その値は `movsq` の複写先にしか使われない (§3.3)。つまり `5cb4aa` の判定は `407a50` の戻り値に依存しない。
- 受入 2 (NONFRAME 規則の call 戻り値への拡張) は実装していない。前提の 407a50 が示せないため。子 issue へ移す (§5)。
- 判定器 `audit_frame_store_callee_3228.py` は main で起動時に落ちていた (`a2.leak_site` が改名済み)。1 行直した (§2)。直す前は結果を出せなかった。

## 2. 測定条件・コード変更

- 測定 commit: `59fcb23bb` (判定器の修正と HEAD 結果を含む commit)。この commit 以降に `tools/m11/ldfix` を変えたのは本 REPORT のみ。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211・#3228 と同じ)。PE は fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 変更: `audit_frame_store_callee_3228.py` の `main()` が `a2.leak_site` (存在しない) を呼んでいたのを `a2.leak_sites` の先頭要素に置き換えた (2 行)。
- 判定器の再現 (修正後 HEAD):
  - `audit_frame_store_alias_2211.py` の出力は `results/frame_store_verdict_4090.json` と byte 一致 (#4090 の結果と同じ)。
  - `--negctl-glk` の出力は `results/negctl_alias_2211_glk.json` と関数・site 単位の判定が一致 (差は `fn_info.leaks` の欄だけ。#4090 でこの欄が増えたため)。

## 3. 結果

### 3.1 判定器 3228 の HEAD 結果 (受入 4 の一部)

| 条件 | DROP | LIVE-IN | UNDETERMINED | 実行 |
|---|---|---|---|---|
| HEAD (`results/frame_store_callee_3228_head_4238.json`) | 3 | 1 | 44 | 0.18 s (load 0.00) |
| ネガコン `--negctl-transparent` (`results/negctl_callee_3228_transparent_4238.json`) | 3 | 18 | 27 | — |
| 旧 commit `028bbd9fb` の JSON (`frame_store_callee_3228.json`) | 3 | 35 | 10 | 再現せず |

- HEAD の値は #4090 の `lea` 修正後の判定。旧 JSON (`028bbd9fb`) は #4090 より前の値で、#4090 以降はその JSON を再生成していなかった。旧 JSON は書き換えず、本 REPORT の表に残す。
- ネガコンで callee 判定を外すと 27 件が UNDETERMINED に戻る。callee 判定が効いている。

### 3.2 `407a50` の戻り値 (受入 1)

`407a50` (244 命令・ret 1 個 `407e10`) の `ret` 直前の `rax` は次のどれか (`407df9 mov rax, rsi` を含む経路):

- 関数内の代入: `407c79 xor eax, eax`・`407c81`・`407df6 mov rax, rsi`・`407dfb xor rax, rax`
- メモリ読み: `407a97 mov rax, [rdx+0x18]`・`407bba`・`407d82` 系の `rsi` (`[rdi+8]` の読み)
- 呼び出し先の戻り値: `407c52 call 0x407680` (`407c57 mov rsi, rax`)・`407d5d call 0x407680`・`407b65 call 0x4073e0` (ret 前に上書き)

呼び出し先の状態:

| 呼び出し先 | 種類 | 戻り値 |
|---|---|---|
| `4073e0` | import thunk (`jmp [rip+0x156a13a]`) | `.pdata` 無し・この PE 内に実装なし |
| `4073c0`・`4073d0`・`4073f0` | import thunk | 同上 |
| `4074d0`・`407570`・`407520`・`409730` | 関数 (`.pdata` あり) | 未追跡 |
| `407680` | 関数 (`call 0x4075e0`・`call 0x4073c0`・`ret`) | `4073c0` の戻り値を `rax` で返す経路あり |
| `407770` | 関数 (`call 0x4073c0`・`call 0x407720`・`ret`) | `rsi` (`4073c0` の戻り値) を返す |

`4073c0` の戻り値は PE の外 (import) なので、frame 派生でないことを機械語では示せない。よって受入 1 は示せず、未達。

### 3.3 `5cb210` `5cb4aa` (受入 3 の理由)

- `5cb4aa cmp qword ptr [rbp+0xc0], 0`: 読みは `rbp` 基底の frame slot。`rdi` は使わない。
- `5cb47d mov dword ptr [rax+8], ecx` (LEAK_STORE の位置): `rax` は `[rbp+0x198]` (呼出し元の引数の値)。
- `5cb3d3 call 0x409410` の戻り値は `5cb3d8 mov [rbp+0x148], rax` で保存される。`rdi` は `5cb443 mov rdi, [rbp+0x148]` で読まれ、`movsq` の複写先 (`5cb44e`〜`5cb456`) だけに使われる。`[rbp+0xc0]` には届かない。
- したがって `5cb4aa` の判定は `407a50` の戻り値に依らない。issue の受入 1〜2 の目的 (5cb4aa の判定) は、この前提の訂正で別経路になる。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `407a50` の戻り値の全経路 (import thunk `4073c0`/`4073e0` の先を含む) | 受入 1・2 が未達。NONFRAME 規則の call 戻り値への拡張も未実施 | 子 issue (§5) |
| 3228 の旧 JSON と現行 HEAD の不一致 (#4090 の影響) | `REPORT_3228.md` の 35/10 と `frame_store_callee_3228.json` は現行 HEAD と一致しない | 本 PR では書き換えない。起票先は子 issue の本文 (§5) |

## 5. 子 issue

子 issue (本 run で起票し、番号は最終回答と issue コメントに記す): 407a50 の戻り値の全経路と NONFRAME の call 戻り値への拡張 (親 #4238)。子の本文に、旧 JSON `frame_store_callee_3228.json` の書き換えの扱いを含める。

## 6. 差分 (WORKFLOW §6)

測定 commit `59fcb23bb` から REPORT を含む HEAD までで `tools/m11/ldfix` に変わるのは `REPORT_4238.md` のみ (`git diff --stat 59fcb23bb HEAD -- tools/m11/ldfix`)。
