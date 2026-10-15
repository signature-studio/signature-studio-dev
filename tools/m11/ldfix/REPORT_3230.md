# REPORT_3230 — 7e48d6 (部分定義 site, DEF と ENTRY の混在) の機械語・IR 確認 (#3230 / 親 #2211)

## 1. 測定条件

- 測定 commit: `32925d7f` (判定器 `audit_frame_store_alias_2211.py` と結果 JSON を含む commit)。この commit から `origin/main` (`de2aa64f7`) までで判定器に差分は無い。判定器・入力 JSON は本 issue で変更していない。
- PE: fl-win64 の `extracted/block00031_PE.bin` (`FL_WIN64_DIR` の展開先。ImageBase `0x400000`、`.text` RVA `0x1000`)。
- IR: `bash tools/m11/m11_gen_ir2.sh` (`FL_WIN64_DIR` 指定、rc 0、`work/boot_final.ll` 491108 行)。`work/ir_conditions.json` 生成。
- 判定器の再現: `audit_frame_store_alias_2211.py` を HEAD で再実行し、`results/frame_store_verdict_2211.json` と `cmp` で byte 一致 (0.27 秒、load average 0.10)。

## 2. 機械語 (受入 1)

関数 `7e45e0` の `7e4659` (store) と `7e48d6` (読み) の経路。アドレスは PE の逆アセンブル (capstone) の値。

| 経路 | 機械語 | 意味 |
|---|---|---|
| store 経路 | `7e4636 jne 0x7e465c` が成立しなければ `7e4659 mov dword ptr [rbp + 0x6c], eax` で定義 | `[rbp+0x6c]` を定義する (分岐を取ると飛ばす) |
| 先頭経路 | `7e4603 call 0x8203b0` → `7e460f lea rdx, [rbp + 0x60]` → `7e4613 call 0x820c80` | 7e4613 の call が `[rbp+0x6c]` を書く |
| 読み | `7e48d6 cvtsi2ss xmm0, dword ptr [rbp + 0x6c]` | 読み |

- `0x820c80` は分岐の無い 8 命令の関数: `mov rax, rdx` の後、`[rax]`・`[rax+4]`・`[rax+8]`・`[rax+0xc]` へ dword を書いて `ret`。rdx = `&[rbp+0x60]` なので、`[rbp+0x60]`・`+0x64`・`+0x68`・`+0x6c` を書く。よって `7e4613` の call が返ると `[rbp+0x6c]` は必ず定義されている。
- `7e4613` から `7e48d6` の間に、この範囲へ飛び込む分岐は無い (分岐の飛び先を全て確認)。`7e48d6` に届く経路は必ず `7e4613` の call を通る。
- よって、関数先頭から未定義のまま `7e48d6` に届く経路は機械語上は無い。`7e4659` の store を通る経路と、通らない経路 (定義は call) がある。

## 3. 判定器の結果と、そこからの読み違い

判定器 (`audit_frame_store_alias_2211.py`) の 7e48d6 の結果は `outcomes = [ENTRY, STORE]`・`UNDETERMINED (MIXED_OR_UNREACHABLE)`。このとき `ENTRY` は「関数先頭に未定義で届く」の意味だが、§2 のとおり機械語上は届かない。判定器が ENTRY を残す原因は 2 つある。

1. `frame_derived` は `lea` の書き先を派生レジスタに入れない (`writes_dst` が `lea` を除外するため)。よって `lea rdx, [rbp+0x60]` の rdx が F に入らず、`7e45e0` は `glk=false`・`leak=null`・`derived=[]`。7e4613 の call は引数の漏出として数えられず、透過扱いになる。
2. `call` は `glk=false` のとき透過 (CALL にしない)。そのため `0x820c80` が `[rbp+0x6c]` を書くことを見ない。

影響範囲 (測定): `frame_derived` の F が `rbp`・`rsp` のみ (`derived=[]`) で、関数内に `lea` で作った frame 派生値がある関数は、判定結果 JSON の 48 関数のうち 43 関数。ただし派生値が実際に漏出 (call 引数・store・ret) するかは関数ごとに別で、この REPORT では未確定。判定器の修正は本 issue の範囲外 (他 43 関数の判定に波及する) で、子 issue で扱う (§6)。

## 4. IR での読み (受入 2)

IR (`work/boot_final.ll`・`@function_7e45e0`) の 7e48d6 相当:

- 読みは `%194 = call i128 @__asm_cvtsi2ss(i32 %stack_var_-92.0.reload)`。
- `%stack_var_-92.0.reload = xor i32 0, 0` (定数 0)。`stack_var_-92` への store は関数内に無い。
- つまり IR では undef ではなく、**定数 0 に固定された読み**になる。store 7e4659 の IR 相当も無い (`stack_var_-92` を書く命令が無い)。
- 原因: `%stack_var_-104 = alloca i32, align 4` (1 要素・4 バイト) を `function_820c80` に渡している。`function_820c80(i64 %arg1, ptr %arg2)` は `%arg2` に `+0`・`+4`・`+8`・`+12` の 4 つの dword を書くが、alloca は 4 バイトしか無く、`+4` 以降は frame の外。`[rbp+0x6c]` (= `stack_var_-92`) は、この call の副作用を受けない。
- 判定への影響: IR では 7e48d6 の読みは「定数 0」で、機械語の「7e4613 の call が定義する」と一致しない (IR の値が実機で何になるかは未測定)。

## 5. 差分 (WORKFLOW §6)

- 測定 commit: `32925d7f` (§1 と同じ)。判定器・結果 JSON は本 issue で変更していない。
- `git diff --stat 32925d7f HEAD -- tools/m11/ldfix/audit_frame_store_alias_2211.py tools/m11/ldfix/results/frame_store_verdict_2211.json` は出力なし (0 行)。判定器と結果 JSON は変わっていない。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `frame_derived` が `lea` の派生を拾わず、漏出と call 副作用を見ない (判定器の欠陥) | 判定器の 43 関数で、call 副作用を見ないまま判定が出ている。個別の正否は未確認 | #4090 [LD-192] |
| IR の alloca が call 引数の書き込み範囲 (4 バイト超) を覆わない (lift の stack 変数推定の欠陥) | `7e45e0` の `[rbp+0x6c]` が定数 0 になる。他の call 引数の関数も同型の可能性 (未確認) | #3932 [M11-N201]・#3933 [M11-N202] の範囲 (既存の子。新規起票なし) |

## 7. 結論

- 受入 1: 達成 (§2)。7e4659 の store と先頭経路 (7e4613 の call) を機械語で示し、7e48d6 の読みに届く経路は必ず 7e4613 を通ることを確認した。
- 受入 2: 達成 (§4)。IR では読みが undef でなく定数 0 に固定されること、その原因 (alloca の範囲不足) を確認した。
- 受入 3: 達成 (§5)。測定 commit と差分の出力を PR 本文に載せる。
