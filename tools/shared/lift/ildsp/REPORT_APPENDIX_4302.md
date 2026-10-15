# ildsp REPORT 付録: PSOLA slot 1・3 の復号鍵 (host 初期化) と native 落ちの原因 (#4302 / T-SH-114)

> **正本**: 本付録。親 #4237 (T-SH-105)・REPORT_APPENDIX_4169.md・REPORT_APPENDIX_3401.md §8-9 から参照。
> 前回 (#4334・測定 `55b201d9a`) の §1・§4 の結論は、実験器の引数の誤りと arena 不足が原因で、誤りだった (§5 で訂正)。

## 1. 結論

- 鍵 `[0x3f7ad0]` を設定する host 初期化関数は **RVA `0x1b7d80`** (受入 1・前回の結論を維持)。
- **slot 1 の native 落ち (SIGTRAP `0x1ad028`) は、実験器の arena (64 KiB) 不足が原因だった。** `0x1b6f4c` の `new` が `0xa72c` バイトの確保で失敗し、失敗経路の `int3` に入っていた。arena を 4 MiB にすると slot 1 は完走する。鍵の初期化とは無関係。
- **slot 3 の native 落ち は、`RDX ≠ 0` が原因だった。** slot 3 は `RDX = 0` が必要。`RDX = 入力` のままでは、`R9` の値によらず落ちる (`R9=入力`: SIGALRM で打ち切り・`R9=4`: SEGV addr 0x4)。`RDX = 0` なら `R9` によらず完走する。前回の `R9=4` は落ち方を変えるだけで、原因ではなかった。
- 受入 2 (初期化 → slot 1・3 を含む呼出し順で native が落ちない) は、**1 プロセスでの呼出し順 `0,1,2,3,4,5` で満たした** (§4)。
- 順次呼出しでも、slot 2 の戻り値は実行環境で変わる (§4)。落ちないことは確認したが、値は固定値として扱わない。
- 受入 3 (native 対 wasm 差分) は**未達**。harness は slot 別の引数を渡せるようにした (§7・§8)。native は slot 0〜5 を 64/64 完走するが、wasm は全 case が slot 1 で trap する (§7)。

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

引数 (`RDX R8 R9 STACK5`): slot 1 は `RDX=入力 (0x30508000)`・`R8=出力 (0x3050C000)`。slot 3 は `RDX=0`・`R8=要素数 (16)`・`R9=入力 (0x30508000)`・`STACK5=出力 (0x3050C000)`。probe の slot 3 行は、すべて `RDX=0` で呼んでいる (`RDX=入力` の対照行のみ例外で、落ちることを確かめる行)。

| 実験 | 結果 |
|---|---|
| no-init slot 1 | completed rax=0x400 |
| no-init slot 3 | completed rax=0x301ab6a0 |
| init slot 0 | completed rax=0x1 |
| init slot 1 | completed rax=0x400 |
| init slot 2 | completed rax=0x301ab690 (`RDX=入力` で呼んだ値。下記の順次呼出しは `RDX=0` のため別値) |
| init slot 3 | completed rax=0x301ab6a0 |
| init slot 4 | completed rax=0x301ab6b0 |
| init slot 5 | completed rax=0x0 |
| init slot 3 `R8=0` | completed rax=0x301ab6a0 |
| init slot 3 `RDX=0 R8=0` | completed rax=0x301ab6a0 |
| **init slot 3 `RDX=入力` (対照)** | **crashed sig=14 (SIGALRM 300 ms) rip=0x1809fa** |

slot 3 の引数別の対照 (同一 init・同一 `R8=16`・`S5=出力`):

| RDX | R9 | 結果 |
|---|---|---|
| 0 | 入力 | completed rax=0x301ab6a0 |
| 0 | 4 | completed rax=0x301ab6a0 |
| 入力 | 入力 | crashed sig=14 (SIGALRM) rip=0x1809fa |
| 入力 | 4 | crashed sig=11 addr=0x4 rip=0x180900 |
| 出力 | 入力 | crashed sig=14 (SIGALRM) rip=0x1809fa |
| 1 | 入力 | crashed sig=14 (SIGALRM) rip=0x1809fa |

- `sig=14` は SIGALRM (`ualarm` 300 ms) で、SEGV ではない。経過は 0.30 s。
- 結論: slot 3 は `RDX = 0` が必要。`RDX ≠ 0` では落ちる。`R9` は落ち方 (SIGALRM か SEGV か) を変えるだけで、落ちる条件ではない。

順次呼出し (1 プロセス・`RDX=0 R8=16 R9=入力 STACK5=出力`):

| 呼出し順 | 結果 |
|---|---|
| `0,1,2,3,4,5` | 6 slot すべて completed (`rax=0x1 / 0x400 / 0x0 / 0x301ab6a0 / 0x301ab6b0 / 0x0`・rc=0) |
| `0,1,2,3,4,5` を 12 回・20 回 | 全回完走。slot 2 の `rax` は `0x1fb5` (通常の実行) |
| 同上を `env -i` で 10 回 | 全回完走。slot 2 の `rax` は `0x0` |
| 同上を `setarch -R` で 10 回 | 全回完走。slot 2 の `rax` は `0x1fb5` |

- slot 2 の `rax` は、同じ引数・同じ image (md5 `0005ba4b…`) でも実行環境の環境変数で変わる。落ちないことは全実行で確認した。値は固定値として扱わない (原因は未調査)。
- `RDX=入力` で `0,1,2,3,4,5` を呼ぶと、slot 3 が `RDX≠0` で落ちる (`rip=0x181e5b` 付近・SEGV `addr=0xfffffffe30599320`)。このため受入 2 の呼出しは `RDX=0` で行う。
- 受入 2 の条件 (初期化の後に slot 1・3 を含む呼出し順で native が落ちない) は、`RDX=0` の順次呼出しで満たす。
- ただし、同じ slot 1・3 は no-init でも完走する。**鍵の初期化が slot 1・3 の完走に必要だったという前回の結論は、実験器の誤りに基づき撤回する。** 鍵の初期化が効くのは、slot 1 の復号結果が `call` 先になる経路 (`0x1b6f4c` の `rax`) であり、その効果は本実験の入力 (`.data` 不変・1 経路) では観測されない。

## 5. 前回 (#4334) の結論の訂正

| 前回の記述 | 訂正 |
|---|---|
| 初期化後も slot 1 は SIGTRAP (`0x1ad028`) | arena 不足 (`new` 失敗の経路)。arena 4 MiB で完走 |
| 初期化後も slot 3 は addr 0x4 (`0x180900`) | `RDX ≠ 0` が原因 (`R9=4` は落ち方を変えるだけ)。`RDX=0` で完走 |
| 初期化が slot 1・3 の完走に必要 | no-init でも完走 (§4) |

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 3: slot 1 を含む閉包の native 対 wasm 差分 (wasm が slot 1 で trap) | 差分 PASS は 0/64。閉包の全バイト差分が未確定 | #4302 (残件・Refs) |
| 鍵の初期化 `0x1b7d80` の効果 (復号結果 `call` 先の経路) を `.data` 入力で観測 | 初期化の必要性を実測で示せていない (§4) | #4302 (残件) |
| 初期化関数列の全体 (CRT か) | 「CRT 相当」の断定ができない | #4302 (残件) |

## 7. 受入 3 の差分 harness (未達・途中結果)

harness を拡張した (`WC_INIT_RVA`・`WC_ARENA_SZ`・`WC_CALL_ARGS` を slot ごとに指定・`wc_run5`)。既定値は従来どおり。測定の正本は §8。

- 結論: init `0x1b7d80` の後の slot 0〜5 を native で呼ぶと 64/64 完走する。wasm は全 64 case が slot 1 (`0x1ab680`) で trap する。受入 3 は未達。
- slot 0 は wasm でも完走する (rax=1)。slot 1 の thunk は `this+8` を読んで DSP 本体へ飛ぶ。wasm で `this+8` が native と同じ内部状態かは未確認 (trap のため `res_wasm.bin` が残らない)。
- lift 側は閉包 243 関数・unsup 0・unlifted 0。init・CreateInstance・slot 0 は wasm でも完走する (`WC_TRACE=1` で確認)。
- よって差分が取れない原因は、閉包の欠落ではなく、wasm 側の実行時状態 (slot 1 の入力 `this` の内部フィールド) と推測する。未確認。

未解決 (受入 3 の残件・#4302 に残す): slot 1 で wasm が trap する原因の特定 (native と wasm の `this` 内部状態の比較)。

## 9. slot 1 の wasm trap の原因 (受入 3 の残件・診断)

測定 commit: `7ace9f448` (段階 5 の後の診断・差分 harness の実測。§8 の値はこの commit)。再現コマンド (`lift_wc.sh` を直接呼ぶ。`WC_LOG_FD=1` で段階の trap を出す):

```
WC_ENTRY_RVA=0x1ab540 WC_VTABLE_RVA=0x3e0030 WC_WORK=ildsp-psola-s8 WC_INIT_RVA=0x1b7d80 WC_ARENA_SZ=0x400000 \
WC_ROOTS="0x1ab540 0x1ab590 0x1ab690 0x1ab6b0 0x1ab800 0x17f700 0x180830 0x1b7d80 0x1ab680 0x1ab6a0 0x112de0 0x115f00" \
WC_CALL_IDX="0 1 2 3 4 5" WC_RET_IDX="0 2 4 5" \
WC_CALL_ARGS="IN OUT 16 0;IN OUT 16 0;IN OUT 16 0;0 16 IN OUT;IN OUT 16 0;IN OUT 16 0" WC_LOG_FD=1 \
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/ildsp/lift_wc.sh ok
```

診断: `wc_run_wasm.mjs` に `WC_LOG_FD=1` を足した (既定は従来どおり throw)。import `fd_write` に来た runtime の `fprintf(stderr)` を出して続行する。

| 段階 | wasm の trap 内容 (slot 1 `0x1ab680`) | 対処 |
|---|---|---|
| 1 | `call to UNLIFTED function 0x301ab680` | slot 1・3 (`0x1ab680`・`0x1ab6a0`) を `WC_ROOTS` に入れていなかった |
| 2 | `call to UNLIFTED function 0x30112de0` | slot 1 の thunk が `[0x3f59a8]` 経由の間接 `jmp` で `0x112de0` へ飛ぶ。`0x112de0` を root に足す |
| 3 | `UNSUPPORTED instruction: cmpnlepd` | x64c に SSE2 `cmp*pd` (eq/lt/le/nle) が無かった。`cmppd_pred` を登録 (`x64c.py`) |
| 4 | `call to UNLIFTED function 0x30115f00` | `0x112de0` の閉包がさらに間接 call 先を持つ。`0x115f00` を root に足す |
| 5 | `UNSUPPORTED instruction: pmuludq` | x64c に `pmuludq` が無かった。`lane()` で追加 (`x64c.py`) |

- 段階 5 の後: unsup 0・unlifted 0・wasm trap 0 (`lift_wc.sh ok` の `WC_ROOTS` に `0x1ab680 0x1ab6a0 0x112de0 0x115f00` を足した版)。
- ただし差分は全 case FAIL (PASS 0・FAIL 64)。wasm は完走し、差分の中身はポインタ値。

差分の内訳 (case 0 と case 1 で同じ):

| 項目 | native | wasm |
|---|---|---|
| `rax` | `0x2a989efd3e63f` | `0xda2e887f5eb0745f` |
| arena `+0x278` (8 byte) | `0x30599320` | `0x30598de0` |
| arena の差バイト数 | — | 81137 (`0x278`・`0x2e0`・`0x301`… から始まる) |
| hits | 24 | 24 |

- 差は heap 上のポインタ値 (下位 32 bit のずれ) が主で、slot 1 が heap に書く内容が native と一致していない。
- 原因は未特定。heap の規約 (`wc_glue.c`・`wc_native_ref.c` とも bump heap・同じ開始位置) は一致しているので、slot 1 までの呼出し列で heap の確保順が native と違う可能性がある。未確認。
- `lift_psola.sh ok` (既定・slot 0・2・4・5) は本修正後も PASS=64 FAIL=0 (`WC_ROOTS` は変えていない)。

## 8. 検証

- 測定 commit: `7ace9f448` (コードを変えた最後の commit。現 head は `974f31260` で文書のみの差分: `git diff 7ace9f448 HEAD -- tools/shared/lift/ildsp tools/flelift` は REPORT_APPENDIX_4302.md のみ)。`c9c29634a` からの差分は `tools/shared/lift/ildsp/wc_run_wasm.mjs` の 1 行 (診断用 `WC_LOG_FD=1` の `??=`) のみで、その 1 行も測定経路に入るため、以下は `7ace9f448` で測り直した値。
- 素材: `fl-win64` の `extracted/block24360_PE.bin` (`work/fl` に展開)、emsdk は上流から 6.0.12 を導入して使った (`EMSDK_ENV` で指定)。
- 既定 `lift_psola.sh ok` (`7ace9f448`): PASS=64 FAIL=0 wasm trap 0・rc 0・elapsed 3.73 s (emcc 込み)・load 1.18→1.25。
- 差分 harness (`7ace9f448`・§9 の完全なコマンド): rc 1・elapsed 42.03 s・load 1.15→1.90。native 64/64 完走 (SEGV 0)、wasm traps 0・PASS 0・FAIL 64 (差分は `rax`・arena `+0x278`・`.data +0xb80` の 3 箇所)。
- 過去の測定 (旧 head `08fdc1db8`、x64c 修正の前): `lift_psola.sh ok` 2.42 s・load 1.23→1.22 (PASS=64)。差分 harness は wasm traps 64・PASS 0・FAIL 64 で 26.74 s・load 0.76→0.85 (§9 の段階 1〜5 の修正前)。
- `psola_init_probe.sh` (`08fdc1db8`): rc 0・0.547 s (1 回)・load 0.40。§4 の表と一致 (slot 2 の順次呼出し `rax` は環境依存で値は変わるが完走)。

再現コマンドは §9 (差分 harness) と下の `lift_psola.sh` の既定。`lift_psola.sh` は `WC_ROOTS`・`WC_CALL_IDX` を固定で export するため、差分 harness は `lift_wc.sh` を直接呼ぶ。`lift_psola.sh` の既定は変えていない。

- `WC_CALL_ARGS` の並びは slot 0〜5 の順 (`RDX R8 R9 S5`)。slot 3 だけ `RDX=0 R8=16 R9=入力 S5=出力` (probe §4 の規約)。
- `WC_RET_IDX` の slot 2 は、§4 のとおり環境で `rax` が変わる。native と wasm は同じ実行環境で比べるため、今の結果 (trap) には影響しない。ただし差分を PASS にする段階では、slot 2 を戻り値の畳み込みから外すことを検討する。
- trap の位置は `WC_TRACE=1 node tools/shared/lift/ildsp/wc_run_wasm.mjs <workdir>` で確認: `init-done`・`create-done`・slot 0 `done rax=1` の後、`slot=1 rva=1ab680` で `unknown import wasi_snapshot_preview1.fd_write`。

未解決 (受入 3 の残件・#4302 に残す): slot 1 で wasm が trap する原因の特定 (native と wasm の `this` 内部状態の比較)。
