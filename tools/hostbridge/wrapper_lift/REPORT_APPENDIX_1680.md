# REPORT 付録 — #1680 (HB-H36): 引数型不一致 (`incompatible pointer types passing`) の方式判定と修復

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §11。本付録は §11 の詳細 (測定表・判定・再現手順) を分割移動したもの。
> 結論 1 行: 宣言側 (`int16_t *`) は正しく、呼出側の `L"..."` (wasm32 で 4B 単位) を `(int16_t *)u"..."` に直す。`--wide` で 1,245 + 1,251 件を機械的に修復し、両 block で該当 error は 0 件になった。

測定 commit: `f6913004` (`retdec_repair.py --wide` を入れた最後の commit)。環境: `[RETDEC]` v5.0 (`toolchain-retdec`)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`$RUNNER_TEMP` に展開)。

## 1. 症状の内訳 (修復前, `--int-ptr` のみ, §9 と同条件)

`emcc -c` の `incompatible pointer types passing` を、引数の型と宣言の型で数えた (block19091, 40 ファイル, error 行 1,377 のうち):

| 引数型 → 宣言型 | 件数 |
|---|---|
| `int[N]` → `int16_t *` (N = 文字数 + 1、`L"..."` の文字列リテラル) | 1,245 (全件) |

- 1,245 件の全てが `L"..."` の文字列リテラル。リテラルの種類は 982 (`kernel32.dll` 12 回、`Software\\Image-Line\\Shared\\General` 15 回 等)。
- 宣言 `int16_t *` の関数は 107 種。IAT thunk (`jmp [rip+…]`) の先は `GetModuleHandleW` (LPCWSTR)・`RegisterClipboardFormatW` (LPCWSTR)・`RegQueryValueExW` (LPCWSTR) など。

## 2. 判定 (受入条件 1・2)

**判定対象の 3 種 (代表例)**:

| # | 呼出 (RetDec 出力・修復前) | 宣言側 (`int16_t *`) | 実引数 (`L"..."`) | 判定根拠 |
|---|---|---|---|---|
| 1 | `function_406ff0(L"kernel32.dll")` | `function_406ff0` は IAT thunk → `kernel32!GetModuleHandleW` (LPCWSTR) | `L"kernel32.dll"` | Win32 API の第 1 引数は UTF-16 の `LPCWSTR`。宣言が正 |
| 2 | `function_423640(L"Preferred DropEffect")` | IAT thunk → `user32!RegisterClipboardFormatW` (LPCWSTR) | `L"..."` | 同上 |
| 3 | `function_4219c0(v5, L"DisplayVersion", 0, 0, 0, &v6)` | IAT thunk → `advapi32!RegQueryValueExW` (第 2 引数 LPCWSTR) | `L"..."` | 同上 |

**全 1,245 リテラルの裏取り**: 各リテラルを UTF-16LE にしたバイト列が `block19091_PE.bin` 内に存在することを確認 (1,245 / 1,245)。よってバイト列は 2B 単位の UTF-16LE であり、宣言側の `int16_t *` と整合する。

**判定**: 宣言側 (`int16_t *`) は正しい。呼出側の `L"..."` が誤り。

- 根拠: `wchar_t` は Win64 で 2B だが、wasm32 (emcc) では 4B。`L"kernel32.dll"` は 4B 単位の `int[13]` になり、2B 単位の `int16_t *` 宣言と一致しない。宣言を `int32_t *` 等へ変えると、Win32 側が期待する UTF-16 のバイト列が変わる (宣言を直す案は不採用)。
- 機械語の PE バイト列が UTF-16LE であることを、全リテラルで確認した (上記)。

**方式 (受入条件 2)**: 呼出側を直す。具体的には、emcc が `incompatible pointer types passing 'int[N]' to parameter of type 'int16_t *'` と報告した位置だけ、`L"..."` を `(int16_t *)u"..."` に置換する (`retdec_repair.py --wide`)。
- 宣言は触らない (`int16_t *` は残す)。
- 全コードポイントが 1 単位 (BMP・非代理・ASCII 制御でない) の literal だけ直す。それ以外は skip して件数を出す。本測定では skip 0。
- 診断位置だけを見るので、型を推測しない (`--int-ptr` と同じ方針)。
- `break`・goto・label は触らない (DEFECTS D19 型)。

**未検証 (受入条件 1 の範囲外)**:
- 内部関数 (`function_5c9550`・`function_413e60` 等) の引数が実際に UTF-16 として読まれるかは、IAT thunk 3 件のようには裏取りしていない。宣言 `int16_t *` と PE 内の UTF-16LE バイト列が一致するので、整合はしている。
- 修復後の関数が機械語どおりに動くかは未検証 (wasm 実行系が無い)。

## 3. 修復後の再測定 (受入条件 3)

`retdec_repair.py --wide --int-ptr` → `emcc_per_function.py` (測定 commit `f6913004`):

| 項目 | block19091 修復前 (§9 同条件) | block19091 修復後 | block23676 修復前 | block23676 修復後 |
|---|---|---|---|---|
| 関数数 (pdata 併合後) | 19,816 | 19,816 | 19,826 | 19,826 |
| RetDec 定義あり | 19,812 | 19,812 | 19,822 | 19,822 |
| `--wide` で直した `L"..."` | — | 1,245 | — | 1,251 |
| `--int-ptr` で包んだ `&` | — | 1,993 | — | 1,986 |
| emcc `-c` 通過 (関数単位) | 18,932 | 19,718 | 18,939 | 19,728 |
| error 行 | 1,377 | 132 | 1,383 | 132 |
| `incompatible pointer types passing` | 1,245 | **0** | 1,251 | **0** |
| emcc exit 0 (ファイル数 / 40) | 1 | **11** | 1 | **11** |
| emcc 所要 (合計) | 6.12 s | 6.39 s | 6.05 s | 6.39 s |

- block19091 修復後 `unattributed_error_lines`・`failclosed_files` は 0 (修復前は 1・1)。

**残り error 132 件の内訳** (block19091, 修復後): `'break' statement not in loop` 78、`incompatible pointer types assigning` 17・`initializing` 13・`assigning ... from incompatible type` 3、`use of undeclared label` 16、未分類 5 (`undeclared identifier` 2・`member reference base type` 2・`integer literal too large` 1)。
- goto/break・label (94 件) は C の制御構造を変える修復になるため、#1679 (HB-H35) の範囲。
- 代入・初期化の型不一致 (33 件) は型推定を伴うため、本 issue の範囲外。今回の修復では触っていない。

## 4. 受入条件の判定

- 受入条件 1 (代表例 3 種以上の判定): 達成。IAT thunk 経由の Win32 API 3 件で、宣言 (LPCWSTR) と実引数の型を機械語・PE バイト列で判定した (§2)。
- 受入条件 2 (方式 1 つと根拠): 達成。呼出側を直す。根拠は wasm32 の `wchar_t` 4B と PE 内の UTF-16LE (§2)。
- 受入条件 3 (修復後の件数): 達成。両 block で `incompatible pointer types passing` 0 件、emcc exit 0 は 40 件中 11 件 (修復前 1 件)。

**未達 (起票先)**: 残り 132 件の goto/break・label・代入型不一致 → #1679 (HB-H35) の範囲。emcc exit 0 の残り 29 件は、これらの残り error が原因 (引数型の不一致は 0 件)。

## 5. 再現手順

```sh
export RETDEC=$RUNNER_TEMP/retdec/retdec/bin/retdec-decompiler FL_WIN64_DIR=$RUNNER_TEMP/fl-win64/extracted
export EM_CONFIG=$RUNNER_TEMP/emsdk/emsdk/.emscripten PATH=$RUNNER_TEMP/emsdk/emsdk/upstream/emscripten:$PATH
KEEP_DIR=$RUNNER_TEMP/r1680/raw python3 tools/hostbridge/wrapper_lift/retdec_batch.py block19091_PE.bin
python3 tools/hostbridge/wrapper_lift/retdec_repair.py --wide --int-ptr $RUNNER_TEMP/r1680/raw $RUNNER_TEMP/r1680/head19091
python3 tools/hostbridge/wrapper_lift/emcc_per_function.py $RUNNER_TEMP/r1680/head19091 --targets $FL_WIN64_DIR/block19091_PE.bin --out $RUNNER_TEMP/r1680/head19091.json
```

- `retdec_batch.py` (実測 250 s / 240 s)。lift 19,815 / 19,816 (no_definition 1)、block23676 は 19,825 / 19,826。`KEEP_DIR` で raw C を残す (`work/` 外・commit しない)。
- `--wide --int-ptr` は emcc を 40 回呼ぶ (合計数秒)。
- 検証の大物 (raw C・修復後 C) は `$RUNNER_TEMP` に置き、commit しない。

## 6. 未検証・注意

- 修復は `int16_t *` 引数に限る。他の型 (`int64_t *` 等) への `L"..."` は対象外。
- `(int16_t *)u"..."` の値が RetDec の意図と一致するかは wasm 実行系が無いため未検証 (§2)。
- 修復後の関数の挙動 (bit 一致・CreatePlugInstance 到達) は未検証。wasm link は本 issue の範囲外。
