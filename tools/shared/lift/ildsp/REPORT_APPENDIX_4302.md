# ildsp REPORT 付録: PSOLA slot 1・3 の復号鍵 (host 初期化) と native 落ちの原因 (#4302 / T-SH-114)

> **正本**: 本付録。親 #4237 (T-SH-105)・REPORT_APPENDIX_4169.md・REPORT_APPENDIX_3401.md §8-9 から参照。
> 前回 (#4334・測定 `55b201d9a`) の §1・§4 の結論は、実験器の引数の誤りと arena 不足が原因で、誤りだった (§5 で訂正)。

## 1. 結論

- 鍵 `[0x3f7ad0]` を設定する host 初期化関数は **RVA `0x1b7d80`** (受入 1・前回の結論を維持)。
- **slot 1 の native 落ち (SIGTRAP `0x1ad028`) は、実験器の arena (64 KiB) 不足が原因だった。** `0x1b6f4c` の `new` が `0xa72c` バイトの確保で失敗し、失敗経路の `int3` に入っていた。arena を 4 MiB にすると slot 1 は完走する。鍵の初期化とは無関係。
- **slot 3 の native 落ち (addr 0x4) は、引数の割り当ての誤りが原因だった。** slot 3 は `R8` = 要素数・`R9` = 入力配列・5 番目 = 出力。前回の実験器は `R9=4` を入力として渡していた。正しく与えると完走する。
- 受入 2 (初期化 → slot 1・3 を含む呼出しで native が落ちない) は、**個別の slot 呼出しで満たした** (§4)。
- 受入 3 (native 対 wasm 差分) は**未実施**。差分 harness (`wc_native_ref.c`) は全 slot に同じ引数 (`RDX=作業バッファ`・`R8=R9=0`) を渡すため、slot 1・3 は早期 return する。slot 別の引数を渡せるよう harness を直す作業が要る (§6 の未解決)。

## 2. 特定の根拠 (受入 1)

測定 commit: `55b201d9a` (前回の付録の実測)。

| 項目 | 実測 |
|---|---|
| 素材 | `fl-win64` の `extracted/block24360_PE.bin` (`tar --zstd -xf` で `extracted/` のみ展開) |
| 鍵 `KEY = 0x3f7ad0` の参照 | RIP 相対で参照する命令は 2 件: `0x1b6f44` (`mov [KEY], rcx` = **書き込み**)・`0x1b6fa2` (`xor rbx, [KEY]` = 読み出し) |
| 鍵の書き込み関数 `0x1b6f44` の呼出元 | `0x1b7d98` のみ (`call 0x1b6f44`) |
| 呼出元 `0x1b7d80` の内容 | `rbx = [0x3f5d98]` (= A)。`call 0x1b3258`・`call 0x1b6f44 (rcx=rbx)`・`call 0x1bd1f0`・`call 0x1bd4b0`・`call 0x1b74ac` |
| `0x1b7d80` の登録 | `.rdata` の abs64 ポインタ列 (file `0x3d2980`・RVA `0x3d3b80`) と、`.pdata` 外の RVA 列 (file `0x3fb2a8`) に現れる |

- 上記の登録が CRT の初期化関数列かは未確認。「CRT 相当」とは断定しない。

## 3. 復号式の検算

`0x1b6f88` の復号は `rbx = ror(A ^ KEY, A & 0x3f)` (`A = [0x3f5d98]`・`KEY = [0x3f7ad0]`)。

| 鍵の状態 | 復号結果 |
|---|---|
| ファイル上 (`KEY = 0`) | `0x0ae64b77e88c8000` (非 0) |
| 初期化 `0x1b7d80` 実行後 (`KEY = A`) | `0x0` |

- 復号結果 0 の経路は `0x1bd4b8` の `test rdx, rdx; je` で、呼ばない側へ入る。
- issue の「file 上の鍵 0 → 結果 0 → `jmp rax` が addr 0」は再現しない。鍵 0 のとき call 先は非 0 の値になる。

## 4. 初期化の後の native 呼出し (受入 2)

実験器: `tools/shared/lift/ildsp/psola_init_native.c` (INIT → CreateInstance → 指定 slot)。再現: `FL_WIN64_DIR=<展開先> bash tools/shared/lift/ildsp/psola_init_probe.sh`。

引数 (`RDX R8 R9 STACK5`): slot 1 は `RDX=入力 (0x30508000)`・`R8=出力 (0x3050C000)`。slot 3 は `R8=要素数 (16)`・`R9=入力 (0x30508000)`・`STACK5=出力 (0x3050C000)`。

| 実験 | 結果 |
|---|---|
| no-init slot 1 | completed rax=0x400 |
| no-init slot 3 | completed rax=0x301ab6a0 |
| init slot 0 | completed rax=0x1 |
| init slot 1 | completed rax=0x400 |
| init slot 2 | completed rax=0x301ab690 |
| init slot 3 | completed rax=0x301ab6a0 |
| init slot 4 | completed rax=0x301ab6b0 |
| init slot 5 | completed rax=0x0 |
| init slot 3 `R8=0` | completed rax=0x301ab6a0 |

- 受入 2 の条件 (初期化の後に slot 1・3 を含む呼出しで native が落ちない) は個別の呼出しで満たす。
- ただし、同じ slot 1・3 は no-init でも完走する。**鍵の初期化が slot 1・3 の完走に必要だったという前回の結論は、実験器の誤りに基づき撤回する。** 鍵の初期化が効くのは、slot 1 の復号結果が `call` 先になる経路 (`0x1b6f4c` の `rax`) であり、その効果は本実験の入力 (`.data` 不変・1 経路) では観測されない。

## 5. 前回 (#4334) の結論の訂正

| 前回の記述 | 訂正 |
|---|---|
| 初期化後も slot 1 は SIGTRAP (`0x1ad028`) | arena 不足 (`new` 失敗の経路)。arena 4 MiB で完走 |
| 初期化後も slot 3 は addr 0x4 (`0x180900`) | 引数の割り当ての誤り (`R9=4` を入力にした)。正しい引数で完走 |
| 初期化が slot 1・3 の完走に必要 | no-init でも完走 (§4) |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 3: slot 1・3 を含む閉包の native 対 wasm 差分 (差分 harness の引数規約を slot 別にする) | 差分の PASS/FAIL 件数が未取得。閉包の全バイト差分が未確定 | #4302 (残件・Refs) |
| 鍵の初期化 `0x1b7d80` の効果 (復号結果 `call` 先の経路) を `.data` 入力で観測 | 初期化の必要性を実測で示せていない (§4) | #4302 (残件) |
| 初期化関数列の全体 (CRT か) | 「CRT 相当」の断定ができない | #4302 (残件) |

## 7. 検証

- 測定 commit: 本 PR の code commit (`git log -1 -- tools/shared/lift/ildsp` で確認)。素材 `fl-win64` を `work/fl` に展開して実行。
- `psola_init_probe.sh` (10 実験): 0.6 s・1 回。全実験が完走 (rc=0)。
- 差分テスト (`lift_psola.sh`) は未実施 (受入 3)。
