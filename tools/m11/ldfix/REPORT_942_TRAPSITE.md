# REPORT_942_TRAPSITE — stage4 survey の trap 9 件の発生箇所 (unit 別・wasm 位置・命令) (#942 受入 1・2)

既知類型との関係: 新規類型の判定はしない。trap は「i32 に wrap した pointer を定数オフセットで読む/書く」形で、DEFECTS の既存類型 (D4: 引数経由の deref 脱落) との同一性は未判定。`docs/DEFECTS.md` は変更しない。

## 0. 結論

- survey の trap 9 件 (unit #) は、**全件で発生 frame (IR 関数・wasm バイト位置・命令) を確定**した。内訳は OOB 8 件・halt0 1 件 (unit 114。Halt 呼出しで trap ではない)。
- OOB 8 件は **6 箇所** に分かれる。unit 53・87・138 は同一箇所 (`function_418190` @ wasm 0x350ea4) で、1 箇所の不正値が 3 unit に出る。
- 6 箇所は全て「pointer 値 (i64 → i32 wrap) を基に小さい定数オフセットで読む/書く」形。linear memory (`HEAPU8.length` = 0x12000000 = 288MB) の外を指している。
- **不正な pointer 値そのもの (どこで作られたか) は未特定**。値の実測は、IR への probe を入れた変種が要る (次 run・§6)。
- 受入 2 (boot threw): 通常 boot の threw (REPORT_942_APPENDIX §14-2) と survey の unit 17 は同一命令 (wasm 0x350d1b・`function_4133f0`)。boot と survey で同じ trap 箇所を踏む。

## 1. 9 unit の trap 位置

測定: `S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs` (base = 修復前 IR)。wasm 位置は `chain` の先頭 (最内) の `wasm-function[N]:0xOFF`。IR 名は `tools/m11/m11_wasmnames.py` で引いた。命令は `wasm-objdump -d` (wabt 1.0.39) の逆アセンブル。

| unit | VA | 種別 | 最内 frame (IR 関数) | wasm 位置 | 命令 (アドレスの作り) | 呼び出し chain (最内から) |
|---|---|---|---|---|---|---|
| 17 | 0x55790 | OOB | `function_4133f0` | 0x350d1b | `i32.load` の番地 = `[frame+32]+8` (= 元の値 −8 の読み) | ← `function_446400` (0x16f6eb) ← `function_44bb70` ← `function_455790` ← `m11_icall` |
| 53 | 0x158e20 | OOB | `function_418190` | 0x350ea4 | `i32.load` の番地 = `[frame+32]−12` (参照カウント読み) | ← `function_418210` (0x775eb) ← `function_8cbb00` ← `function_8cbcb0` ← `function_8cc190` ← `function_8c7a10` ← `function_8c5cc0` ← `function_558e20` |
| 56 | 0x16fde0 | OOB | `function_8c6530` | 0x26e75e | `i32.store` の番地 = `wrap(local9)` (値は `[local2+24]` の `i32.load`) | ← `function_8c5eb0` ← `function_56fde0` ← `m11_tr_function_56fde0` ← `m11_icall` |
| 87 | 0x19f9a0 | OOB | `function_418190` | 0x350ea4 | 53 と同じ | ← `function_59f9a0` ← `m11_tr_function_59f9a0` ← `m11_icall` |
| 114 | 0x223840 | halt0 | — | — | Halt 呼出し (trap ではない) | — |
| 138 | 0x243270 | OOB | `function_418190` | 0x350ea4 | 53 と同じ | ← `function_418210` (0x775eb) ← `function_646130` ← `function_6462e0` ← `function_646a80` ← `function_643410` ← `function_643270` ← `m11_tr_function_643270` |
| 144 | 0x25c540 | OOB | `function_407e20__lifted` | 0x13cbf7 | `i32.store8` の番地 = `wrap(local9)` (1 byte 書込み。`local36&1==0` の分岐の下) | ← `function_407e20` (0x13be0e) ← `function_409440__lifted` ← `function_409440` ← `function_412d60` ← `function_413060` ← `function_414ec0` ← `function_652500` |
| 149 | 0x264260 | OOB | `function_412e40` | 0x06b473 | `i32.load` の番地 = `local6−8` (ヘッダ読み) | ← `function_653660` ← `function_6539e0` ← `function_664190` ← `function_664260` ← `m11_tr_function_664260` ← `m11_icall` |
| 158 | 0x0 | OOB | `function_409c80` | 0x0ba4f5 | `i64.store` の番地 = `wrap(local90)+8` | ← `function_4133f0` (0x350ca8) ← `function_414c70` ← `function_43c4c0` ← `function_653660` ← `function_6539e0` ← `function_665bd0` ← `function_66d050` |

- unit 158 の VA はテーブル値 0 (`m11_unit_va` が 0 を返す)。由来は未確認。前 run の「unit 0x0」と同じ unit。
- unit 17 の `function_4133f0` は、§14-2 (通常 boot の trap) と同じ wasm 位置 0x350d1b。

## 2. 命令形の読み

- `function_418190` (IR 本体): `arg1 == 0` なら何もしない。`arg1 != 0` なら `*arg1 = 0` の書込みの後に `[arg1−12]` (i32) を読み、`[arg1−8]` を見る。文字列・動的配列の解放 (参照カウント減算) の形。
- wasm の trap 命令 (0x350ea4) は `i32.load` で、番地は「frame+32 の i64 値 − 12」を i32 に wrap したもの。同じ関数の 0x350e96 の `i64.store` (`*arg1 = 0` 相当の書込み) は trap せず通過している。よって trap は「書込みが通る番地」の後の参照カウント読みで起きた。frame+32 の値と IR の `arg1` の対応は、wasm の prologue を追っていないため未確定。
- `function_4133f0` (§14-2 と同じ): `[arg−8]` の読み (文字列ヘッダ)。
- `function_409c80` / `function_407e20__lifted` / `function_8c6530` / `function_412e40`: IR 側の対応 (どの変数が pointer か) は未確認。命令形 (番地の作り) のみ確定。

## 3. 同一箇所の unit

- wasm 0x350ea4 (`function_418190` の参照カウント読み) は unit 53・87・138 の 3 件で同一。呼び出し元は 53・138 が `function_418210`、87 が `function_59f9a0`。**呼び出し側が違っても、解放関数に渡る pointer が同じ不正値を持つ**ことを示す。
- 同一箇所の unit が 3 件あるので、6 箇所の不正値を特定すれば、OOB の 8 件のうち少なくとも 3 件の由来が決まる。

## 4. 範囲の判定

- base の linear memory: `HEAPU8.length` = 0x12000000 (288MB・`ALLOW_MEMORY_GROWTH` 有効・`m11_boot.cjs` の初期化直後の実測)。
- trap は「i32 に wrap したアドレス + アクセス幅 > メモリ長」で起きる。よって不正 pointer は 0x12000000 以上か、i64 → i32 wrap で負側に出た値。0x40xxxx 台の値はこのメモリ内に入るので、範囲外アクセスの値としては当たらない。

## 5. 測定

- 測定 commit: `686fb627` (`feat(m11): trap_units に wasm frame チェーンと位置を出力`。e2e 経路のコードは origin/main `a8c02d48` と同一)。
- e2e: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` → **57.6 秒 (real)・rc 0・judge PASS**。stage4 units 17/942・icall 24・threw `memory access out of bounds` (base = fix)。survey ok 136 / trap 9 (base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。load 0.89 / 0.60 / 0.33 (実行直後)。
- 上記 §1 の表は HEAD `686fb627` で `trap_units.mjs` を再実行して得た値 (base・9 件。最内 wasm 位置と chain が一致)。
- 差分確認: `git diff a8c02d48 686fb627 -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_450560.py tools/m11/m11_ov.c | wc -l` → `0` (e2e 経路の差分 0)。変更は `tools/m11/ldfix/trap_units.mjs` (chain の出力を追加) のみ。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 6 箇所 (418190@0x350ea4・4133f0@0x350d1b・409c80@0xba4f5・407e20@0x13cbf7・412e40@0x6b473・8c6530@0x26e75e) それぞれの不正 pointer 値と、その値を作った箇所 | 受入 1 (OOB 8 件)・受入 2 (boot threw) | #942 (次 run)。方法: 各 IR 関数の entry に引数の記録 call を入れた probe 変種を stage4.sh で作り、trap 時の「最後の entry 値」を読む |
| 409c80・407e20・8c6530・412e40 の wasm 命令と IR 文の対応 | 同上 | #942 (次 run) |
| work-m11 の IR と現 main の不一致 | 測定の母体が現 main と違う | 既存 #680 |

## 7. 再現

```sh
cd <worktree>                      # branch 942-trap-unit-attrib
tar --zstd -xf $HOME/artifacts/work-m11.tar.zst -C .
tar --zstd -xf $HOME/artifacts/work-liftdiff.tar.zst -C .
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs
python3 tools/m11/m11_wasmnames.py tools/m11/ldfix/work/stage4/base/m11_boot.cjs.wasm 14871 14873 5263 1875 75 725
wasm-objdump -d tools/m11/ldfix/work/stage4/base/m11_boot.cjs.wasm   # wabt 1.0.39 (release tarball・sha256 照合)
```
