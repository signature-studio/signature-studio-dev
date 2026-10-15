# ildsp REPORT 付録: PSOLA slot 1・3 の復号鍵 (host 初期化) の特定 (#4302 / T-SH-114)

> **正本**: 本付録。親 #4237 (T-SH-105)・REPORT_APPENDIX_4169.md・REPORT_APPENDIX_3401.md §8-9 から参照。

## 1. 結論 (部分達成)

- 鍵 `[0x3f7ad0]` を設定する host 初期化関数は **RVA `0x1b7d80`** と特定した (受入 1)。`.rdata` の初期化関数ポインタ列 (abs64, file `0x3d2980` 付近) に載る。
- その初期化を元の機械語で先に呼ぶと、鍵は `[0x3f5d98]` の値になり、復号結果は 0 になる (§3)。
- しかし、初期化の後でも **slot 1 と slot 3 は native で落ちる** (受入 2 は未達)。wasm 差分 (受入 3) は未実施。
- issue 本文の「file 上の鍵 0 → 復号結果 0」は**誤り**。鍵 0 のままなら復号結果は `0x0ae64b77e88c8000` (非 0) になる (§3)。

## 2. 特定の根拠 (受入 1)

測定 commit: `55b201d9a` (`tools/shared/lift/ildsp/psola_init_native.c`・`psola_init_probe.sh` を追加した commit)。

| 項目 | 実測 |
|---|---|
| 素材 | `fl-win64` の `extracted/block24360_PE.bin` (`tar --zstd -xf` で `extracted/` のみ展開) |
| 鍵 `KEY = 0x3f7ad0` の参照 | RIP 相対で参照する命令は 2 件: `0x1b6f44` (`mov [KEY], rcx` = **書き込み**)・`0x1b6fa2` (`xor rbx, [KEY]` = 読み出し) |
| 鍵の書き込み関数 `0x1b6f44` の呼出元 | `0x1b7d98` のみ (`call 0x1b6f44`) |
| 呼出元 `0x1b7d80` の内容 | `rbx = [0x3f5d98]` (= A)。`call 0x1b3258`・`call 0x1b6f44 (rcx=rbx)`・`call 0x1bd1f0`・`call 0x1bd4b0`・`call 0x1b74ac` |
| `0x1b7d80` の登録 | `.rdata` の abs64 ポインタ列 (file `0x3d2980`・RVA `0x3d3b80`) と、`.pdata` 外の RVA 列 (file `0x3fb2a8`) に現れる |
| 暗号値 A の書き込み | RIP 相対参照 275 件 (読み出し中心)。A は `.data` 上で初期値を持つ |

- 上記の登録が CRT の初期化関数列かは未確認。関数ポインタの配列の先頭・終端を列挙していないため、「CRT 相当」とは断定しない。
- `0x1b7d80` 以外の呼出元 (`0x1b6f44` を直接呼ぶ箇所) は無い。鍵の設定は、この初期化経路に一本化されている。

## 3. 復号式の検算

`0x1b6f88` の復号は `rbx = ror(A ^ KEY, A & 0x3f)` (`A = [0x3f5d98]`・`KEY = [0x3f7ad0]`)。Python で検算した値:

| 鍵の状態 | 復号結果 |
|---|---|
| ファイル上 (`KEY = 0`・`.data` の生データ外) | `0x0ae64b77e88c8000` (非 0) |
| 初期化 `0x1b7d80` 実行後 (`KEY = A`) | `0x0` |

- 復号結果 0 の経路は `0x1bd4b8` で `test rdx, rdx; je` により「呼ばない」側へ入る。初期化は、この null 判定を通すための設定に見える。
- issue の「file 上の鍵 0 → 結果 0 → `jmp rax` が addr 0」は、この式では再現しない。0 でない値が call 先になる。

## 4. 初期化の後の native 差分 (受入 2)

実行器: `tools/shared/lift/ildsp/psola_init_native.c` (INIT → CreateInstance → 指定 slot の順)。`tools/shared/lift/ildsp/psola_init_probe.sh` で再現。

| 実験 | 結果 |
|---|---|
| 初期化なし・slot 1 (rdx=入力, r8=出力) | crash sig=11 addr=0x0 rip=0x1cb5e0 |
| 初期化なし・slot 3 | crash sig=11 addr=0x4 rip=0x180900 |
| 初期化あり・slot 0 | completed rax=0x1 |
| 初期化あり・slot 1 | **crash sig=5 (SIGTRAP) addr=0x0 rip=0x1ad028** |
| 初期化あり・slot 2 | completed rax=0x301ab690 |
| 初期化あり・slot 3 | crash sig=11 addr=0x4 rip=0x180900 |
| 初期化あり・slot 4 | completed rax=0x301ab6b0 |
| 初期化あり・slot 5 | completed rax=0x0 |
| 初期化あり・slot 3 (rdx=0) | completed rax=0x301ab6a0 |
| 初期化あり・slot 3 (rdx=0, r8=0) | completed rax=0x301ab6a0 |

- slot 3 は入力 `rdx` が 0 なら完走し、非 0 (`0x30508000`) では `0x180900` (`movss xmm1, [rdi+rbp-4]`) で addr 0x4 を踏む。入力の内部構造 (ポインタを含む) の前提が未確定。
- slot 1 は初期化の有無で落ちる位置が変わる (`0x1cb5e0` → `0x1ad028`)。`0x1ad028` の直前は `int3` (`0x1ad027`) で、SIGTRAP は assertion 系の経路と読める。原因は未特定。
- 初期化で「鍵の null 判定」は通るが、slot 1・3 の落ちる原因は鍵とは別。`this` のフィールド (+0x... の内部ポインタ) の前提が未設定と読める (REPORT_APPENDIX_3401.md §8-9 と同じ結論)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 初期化後の slot 1・3 の落ちる原因 (入力の内部構造・`this` の未設定フィールド) | 受入 2 未達。閉包の native 差分が取れない | 本 issue #4302 (部分達成のため残す。`Refs`) |
| 初期化関数列の全体 (先頭・終端・他の初期化) | 受入 1 の「host 初期化 (CRT 相当)」を確定できない | 本 issue #4302 の残件 |
| slot 1・3 を含む閉包の native 対 wasm 差分 (受入 3) | 差分の PASS/FAIL 件数が未取得。受入 2 が先に必要 | 本 issue #4302 (受入 2 の後) |

## 6. 検証

- 素材: `fl-win64` (`extracted/block24360_PE.bin`)・`toolchain-emsdk` (`emsdk/emsdk_env.sh` の実在を確認)。
- 実行: `FL_WIN64_DIR=<展開先> bash tools/shared/lift/ildsp/psola_init_probe.sh` (0.39 s・load 低・1 回)。
- 測定 commit `55b201d9a` 以降のコード差分: 本付録のみ (本 commit の後に変えたコードは無い)。
