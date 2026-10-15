# REPORT_5141 — 407a50 の戻り値 rax の全経路と import thunk の「未確定 (外部)」扱い (#5141 / 親 #4288 / #4238)

## 1. 結論

- 受入 1 を達成した。`407a50` から `ret` (`407e10`) へ入る exit は 9 本。内訳は `407e08` へ飛ぶ分岐命令 (`jmp`/`js`) 8 本 + `407e03` の fall through 1 本。exit は site 単位で 1 本と数え、同じ site に複数の経路があっても 1 本とする。各 exit の `rax` の出どころを §3 に示す。
- 判定の基準は **exit の `rax` の値が `4073c0` (外部) の戻り値に依存するか** の 1 つだけ。到達性 (どの経路を通るか) は基準に使わない (§5)。
- 方式: import thunk の先が PE 外のとき、その戻り値は**「未確定 (外部)」**として扱う。対象は `4073c0` (kernel32 `VirtualAlloc`) だけ。`4073c0` の戻り値に依存する `rax` は、frame 派生かどうかを機械語では判定せず「未確定 (外部)」と記す。
- `rax` の依存は 3 種類ある (§3)。(a) メモリ読み (大域リストの `[rdx+0x18]`・`[rdi+8]`)、(b) 定数 0、(c) 引数 (`ecx` = サイズ) と大域値の算術。(c) は `4073c0` の戻り値 (`rcx`) とも算術で混ざる。そのため `407a50` の exit の一部は「未確定 (外部)」に依存する。
- 判定器 `audit_frame_store_callee_3228.py` を HEAD で実行した。出力は `results/frame_store_callee_3228_head_4238.json` と byte 一致した (§2)。判定器の入力・出力は変わらないので、受入の「対象 1 site 以外の判定が変わらないこと」は満たす。

## 2. 測定条件

- 入力: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`。#4238 §2 と同じ)。
- 逆アセンブル: `tools/m11/ldfix/pe_disasm_va.py` (capstone)。`407a50` から 260 命令。出力は `results/disasm_407a50_5141.txt` (260 行)。
- import 解決: IAT slot (`thunk + 6 + disp32`) を pefile の import 表と照合。

| thunk | IAT slot | import |
|---|---|---|
| `4073c0` | `0x19715d0` | kernel32 `VirtualAlloc` |
| `4073d0` | `0x19712f0` | kernel32 `VirtualFree` |
| `4073e0` | `0x1971520` | kernel32 `Sleep` |
| `4073f0` | `0x1971750` | kernel32 `WriteFile` |

- 判定器: `python3 tools/m11/ldfix/audit_frame_store_callee_3228.py <block00031_PE.bin> results/audit_undefload_564_full.json results/f4_564_post.json <out>`。実行 0.31 s・exit 0。出力は `results/frame_store_callee_3228_head_4238.json` と `cmp` で一致。
- 判定器のコードは変えていない (`git diff --stat origin/main HEAD -- tools/m11/ldfix/audit_frame_store_callee_3228.py` は空)。

## 3. 戻り値 rax の経路 (`407a50` → `407e10` ret)

exit 9 本 (`407e08` は `lea rsp,[rbp+0x28]` で、以後 `pop` のみ。`rax` は変わらない)。exit は `407e08` に入る site (分岐命令または fall through) を 1 本と数える。1 site に複数の経路があっても 1 本。

| exit | 経路 (主要行) | rax の出どころ | 分類 (値の基準) |
|---|---|---|---|
| `407abf` (jmp) | `407a97` で読み → `407abc` | `mov rax,[rdx+0x18]` (rdx = `[rbx+8]`、大域リスト) | 非外部 (メモリ読み) |
| `407ae8` (jmp) | `407ac4`〜`407ad3` → `407ae4` | 同上 (`407acc` は rcx のみ変更・`407ad3` の比較で rax 不変) | 非外部 (メモリ読み) |
| `407afc` (jmp) | `407aed` → `407af9` | 同上 (`407aae`〜`407ab6` は rcx/rdx のみ) | 非外部 (メモリ読み) |
| `407c67` (jmp) | `407c52` (call 407680) → `407c5a test rax,rax` → 0 のとき `407c5f`〜`407c67` | 0 (`test` の直後で rax = 0 が確定。`407c5f` の `mov byte` は rax を変えない) | 非外部 (定数 0)。到達条件は外部依存 (§5) |
| `407cb4` (jmp) | `407c14` 経路 (`407c22` のメモリ読み) または `407c4c` 経路 (`407c5d jne` → 407680 戻り値) → `407c71`〜`407c93` → `407cb4` | `lea rax,[rsi+0x30]` (`407c93`)。rsi = メモリ読み (`407c22`) または 407680 の戻り値 (`407c57 mov rsi,rax`) | **外部依存** (一部の経路が 407680 の戻り値) |
| `407d6a` (jmp) | 経路 A: `407d30`〜`407d59` → `407d62` → `407d6a` / 経路 B: `407d5d` (call 407680) → `407d62` → `407d6a` | 経路 A: `mov rax,[rip+X]` − `rbx` (大域値の算術。`rbx` は `ecx` (引数) 由来)。経路 B: 407680 の戻り値 (§4) | **外部依存** (経路 B。経路 A は非外部) |
| `407df9` (jmp) | `407dd2`〜`407df6` (`mov rax,rsi`) → `407df9` | rsi = `407d7e` の `mov rsi,[rdi+8]` (メモリ読み。`407d6f` は非外部経路からのみ到達) | 非外部 (メモリ読み) |
| `407e01` (js) | `407dfb xor rax,rax` → `407dfe test rcx,rcx` → `js` | 0 | 非外部 (定数 0) |
| `407e08` (fall) | `407e03 call 407770` → 戻り値 | 407770 の戻り値 (§4) | **外部依存** (407770 の戻り値) |

分類の集計: 外部依存 3 本 (`407cb4`・`407d6a`・`407e03`)、非外部 6 本 (`407abf`・`407ae8`・`407afc`・`407c67`・`407df9`・`407e01`)。

注:
- 死んだ戻り値: `407b65`・`4073e0` (Sleep)、`407b70`・`407cda`・`407dda` (`407570`/`4074d0`) の戻り値は、後続の代入 (`407a97`・`407c79`・`407df6`) で上書きされ、どの exit にも届かない。
- `407c0d call 407570` は `407c12 jmp 407c71` で rax を保つが、`407c79 xor eax,eax` で上書きされる。exit には届かない。

## 4. 呼出し先の戻り値

| 呼出し先 | 種類 | rax の出どころ |
|---|---|---|
| `407680` | 関数 (`call 4075e0`・`call 4073c0`・`ret`) | `4073c0` の戻り値 `rcx` を使う。0 なら `xor ecx,ecx`・`407711 xor eax,eax` で 0。非 0 なら `rdx = rcx − ebx + 0x13fff0` を返す (`407707`〜`407713`)。`ebx` は引数 `ecx` 由来 |
| `407770` | 関数 (`call 407720`・`call 4073c0`・`ret`) | `4073c0` の戻り値 `rsi`。0 なら 0、非 0 なら `rsi+0x20` (`4077e7`) |
| `4073c0` | import thunk (`jmp [rip+0x156a20a]`・`.pdata` 無し) → kernel32 `VirtualAlloc` | **未確定 (外部)**。PE 外。戻り値は本 PE から決まらない |

## 5. 方式 (受入 1 の後半)

- import thunk の戻り値は PE 内では決まらないので、「未確定 (外部)」と記す。対象は `4073c0` (`VirtualAlloc`) だけ。
- 判定の基準は「exit の `rax` の値が外部 (`4073c0`) の戻り値に依存するか」。到達性は基準にしない。
- 「未確定 (外部)」は `407680`・`407770` の非 0 の戻り値 (`4073c0` 由来) と、それを `rax`/`rsi` に持ち込む経路に伝わる。exit のうち外部依存は 3 本: `407cb4` (407c4c 経路)・`407d6a` (経路 B)・`407e08` (407770 経由)。
- 非外部は 6 本: `407abf`・`407ae8`・`407afc`・`407df9`・`407e01` (メモリ読み・定数 0) と `407c67` (定数 0)。`407c67` は `407680` の戻り値が 0 のときだけ到達するので、到達の条件は外部依存だが、値は 0 に確定している。
- `407d6a` は site 単位で外部依存 (経路 B が 407680 の戻り値を使う) と数える。経路 A は大域値 − `rbx` (`rbx` は引数 `ecx` 由来) で、frame 派生かどうかは機械語からは判定しない (本 issue の範囲外)。
- 判定器は変えない。HEAD 出力は #4238 と byte 一致 (§2)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `4073c0` (`VirtualAlloc`) の戻り値を PE 内で決めない | `407680`・`407770` 経由の `rax` は「未確定 (外部)」のまま。NONFRAME 規則の call 戻り値への拡張 (#4288 受入 2 相当) は未実施 | 親 #4288 の本文に残す (本 PR では扱わない) |
| 旧 JSON `frame_store_callee_3228.json` と HEAD の不一致 | #4238 §4 と同じ。本 PR は書き換えない | 親 #4288 |

## 7. 再現

- `python3 tools/m11/ldfix/pe_disasm_va.py <block00031_PE.bin> 0x407a50 260` の出力が `results/disasm_407a50_5141.txt` と一致する。
- 入力 PE の展開: 素材 `fl-win64` (`docs/REFERENCES.md` の素材エントリ) の `extracted/block00031_PE.bin` を `tar --zstd -xf` で取り出す (WORKFLOW §11)。
