# REPORT_4238 — 407a50 の戻り値の別名判定と 5cb210 `5cb4aa` の rdi 経路 (#4238 / 親 #4204)

## 1. 結論

- 受入 1 (`407a50` の戻り値 `rax` の全経路) は**示せなかった**。`ret` の `rax` は、関数内の最後の代入 (`407df9`・`407c04` 系) とメモリ読み・呼び出し先の戻り値から来る。呼び出し先のうち `4073c0`・`4073d0`・`4073e0`・`4073f0` は `.pdata` に無い import thunk (`jmp qword ptr [rip+X]`) で、先の実装が `block00031_PE.bin` の外にあるため戻り値を機械語で追えない (§3.2)。
- 受入 2 を実装できなかった理由は、受入 1 (`407a50` の戻り値) が示せないこと。`5cb210` `5cb4aa` の読みが issue 前提と違う点は下の §3.3 に書く (issue 本文には受入条件が 2 件のみ)。
- `5cb210` `5cb4aa` の読みは `cmp qword ptr [rbp+0xc0], 0` で、`rdi` を基底にしない。issue 本文の前提 (`rdi` が `409410` の戻り値から来る) は当たらない。`409410` の戻り値は `[rbp+0x148]` に入り、`rdi` は `5cb443` でそこから読まれるが、その値は `movsq` の複写先にしか使われない (§3.3)。つまり `5cb4aa` の判定は `407a50` の戻り値に依存しない。
- 受入 2 (NONFRAME 規則の call 戻り値への拡張) は実装していない。前提の 407a50 が示せないため。子 issue へ移す (§5)。
- 判定器 `audit_frame_store_callee_3228.py` は main で起動時に落ちていた (`a2.leak_site` が改名済み)。1 行直した (§2)。直す前は結果を出せなかった。

## 2. 測定条件・コード変更

- 測定 commit: `59fcb23bb` (判定器の修正と HEAD 結果を含む commit)。この commit 以降に `tools/m11/ldfix` を変えたのは本 REPORT のみ。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211・#3228 と同じ)。PE は fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2211 と同じ)。
- 変更: `audit_frame_store_callee_3228.py` の `main()` が `a2.leak_site` (存在しない) を呼んでいたのを `a2.leak_sites` の先頭要素に置き換えた (2 行)。
- 判定器の再現 (修正後 HEAD):
  - `audit_frame_store_alias_2211.py` の出力は `results/frame_store_verdict_4090.json` と byte 一致 (#4090 の結果と同じ)。
  - `--negctl-glk` の出力 (`results/negctl_alias_2211_glk_4238.json`) と `results/negctl_alias_2211_glk.json` は、関数判定 (verdict) と `functions` が一致。site 10 件 (`129e1d6`・`5cb4aa`・`6c0207`・`6c7665`・`6c7ccc`・`6ca5c2`・`6ca702`・`7e48d6`・`c3b46f`・`f61ce6`) は `why` と barrier が `BARRIER(LEAK_STORE)` → `BARRIER(ALIAS_FRAME_PTR)` に変わった。`fn_info` は 48 関数で `leak` (34)・`leaks` (48)・`derived` (47) の欄が増減した (#4090 で漏出判定の欄が増えたため)。

## 3. 結果

### 3.1 判定器 3228 の HEAD 結果 (受入 4 の一部)

| 条件 | DROP | LIVE-IN | UNDETERMINED | 実行 |
|---|---|---|---|---|
| HEAD (`results/frame_store_callee_3228_head_4238.json`) | 3 | 1 | 44 | 0.19 s (load 0.40、再実行時。レビュー環境では 0.28 s) |
| ネガコン `--negctl-transparent` (`results/negctl_callee_3228_transparent_4238.json`) | 3 | 18 | 27 | — |
| 旧 JSON `frame_store_callee_3228.json` (commit `b765aa322` で追加) | 3 | 35 | 10 | 再現せず |

- HEAD の値は #4090 の `lea` 修正後の判定。旧 JSON は #4090 以前に生成された値 (生成 commit は `b765aa322`。`028bbd9fb` は判定器の追加 commit で、JSON は含まない)。旧値の再現は試していない。旧 JSON は書き換えず、本 REPORT の表に残す。
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

### 3.3 `5cb210` `5cb4aa` (issue 前提の訂正)

- `5cb4aa cmp qword ptr [rbp+0xc0], 0`: 読みは `rbp` 基底の frame slot。`rdi` は使わない。
- `5cb47d mov dword ptr [rax+8], ecx` (LEAK_STORE の位置): `rax` は `[rbp+0x198]` (呼出し元の引数の値)。
- `5cb3d3 call 0x409410` の戻り値は `5cb3d8 mov [rbp+0x148], rax` で保存される。`rdi` は `5cb43c mov rdi, [rbp+0x148]` で読まれ (`5cb443` は `mov rax, [rbp+0x198]`)、`movsq` の複写先 (`5cb44e`〜`5cb456`) だけに使われる。`[rbp+0xc0]` には届かない。
- したがって `5cb4aa` の判定は `407a50` の戻り値に依らない。issue の受入 1〜2 の目的 (5cb4aa の判定) は、この前提の訂正で別経路になる。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `407a50` の戻り値の全経路 (import thunk `4073c0`/`4073e0` の先を含む) | 受入 1・2 が未達。NONFRAME 規則の call 戻り値への拡張も未実施 | 子 issue (§5) |
| 3228 の旧 JSON と現行 HEAD の不一致 (#4090 の影響) | `REPORT_3228.md` の 35/10 と `frame_store_callee_3228.json` は現行 HEAD と一致しない | 本 PR では書き換えない。起票先は子 issue の本文 (§5) |

## 5. 子 issue

子 issue #4288 (LD-208): 407a50 の戻り値の全経路と NONFRAME の call 戻り値への拡張 (親 #4238)。旧 JSON `frame_store_callee_3228.json` の扱いも #4288 に含める。

## 6. 差分 (WORKFLOW §6)

測定 commit `59fcb23bb` から HEAD (`main` 取り込み後) までの `tools/m11/ldfix` の差分は次のとおり (`git diff --stat 59fcb23bb HEAD -- tools/m11/ldfix`、11 files)。

- PR 自身の差分: `REPORT_4238.md`・`results/negctl_callee_3228_transparent_4238.json` (1417 行)。
- `main` 取り込みで入った差分: `REPORT_1325.md`・`REPORT_3328.md`・`REPORT_3418.md`・`REPORT_4167.md`・`alias_evidence_4167.py`・`fix_site_3418.py`・`ldfix_509_e2e.sh`・`ldfix_e2e.sh`・`results/alias_evidence_4167.json`。
- 判定器の依存は差分 0: `git diff --stat 59fcb23bb HEAD -- audit_frame_store_callee_3228.py ldmach.py audit_frame_store_verdict.py audit_frame_store_alias_2211.py results/audit_undefload_564_full.json results/f4_564_post.json` は空。
