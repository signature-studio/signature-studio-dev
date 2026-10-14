# REPORT_942_TRAPSITE — stage4 survey の trap 9 件の発生箇所と直接の引き金 (#942 受入 1・2)

既知類型との関係: 新規類型は判定しない。unit 158 の引き金は「文字列の中身 (UTF-16 文字) が pointer の位置に値として渡る」形で、DEFECTS の既存類型 (D4: 引数の deref 脱落) と同じ方向の候補。`docs/DEFECTS.md` は変更しない。

## 0. 結論

- survey の trap 9 件 (OOB 8・halt0 1。halt0 は unit 114 で trap ではない) は、**全件で最内 frame と wasm 位置を確定**した。OOB 8 件は 6 箇所に分かれ、`function_418190` (C 版) @0x350ea4 は unit 53・87・138 の共通箇所。
- **実行されるのは C 版の 2 関数**: `function_4133f0` と `function_418190` は `tools/m11/m11_ov.c` の C 転記で置換されている (IR 版は実行されない)。前 run までの IR 本体の読みは、この 2 関数については実行経路ではない。
- 直接の引き金 (probe で読めたもの):
  - **unit 158 (VA 0)**: `function_409c80` (IR) が `dst=0`・`n=0x1a904afc` で呼ばれて trap。`n = len*2` で、`len = 0x8d48257e` は `function_412c20` の引数。`src` (第 1 引数) は `0x0063006100630074` = UTF-16 の文字 "tcac" の中身で、pointer ではない。上流は `function_4133f0` ← `function_414c70` (IR)。
  - **unit 17**: `412c20(3)` が 6 を返した (`409c80` の最後の呼出し dst=6・n=6 から推定)。その 6 が `Q(dest)` (旧値) に残り、次の呼出しの `D(old−8)` (old = 6) で trap したと推定 (推定。trap した呼出しの値は未記録)。
  - **unit 56**: `function_8c6530` (IR) の記録で、第 2・第 3 引数が UTF-16 "g"/"o" の中身 (`0x670067`・`0x67006f`) と一致。文字列の中身が値として渡っている可能性がある。
  - unit 144・149 (`function_407e20__lifted`・`function_412e40`) と unit 53・87・138 (`function_418190` C 版): 記録に引き金の値が出ていない (下表)。
- 受入 2 (boot threw): 通常 boot の trap (§14-2 の wasm 0x350d1b・`function_4133f0`) は unit 17 と同一箇所。boot と survey は同じ経路を踏む。

## 1. 9 unit の trap 位置

測定: `S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs` (base = 修復前 IR・HEAD `686fb627`)。最内 wasm 位置は `chain` の先頭。IR 名は `tools/m11/m11_wasmnames.py`、命令は `wasm-objdump -d` (wabt 1.0.39)。

| unit | VA | 種別 | 最内 frame | 実行体 | wasm 位置 | 命令形 | chain (最内から) |
|---|---|---|---|---|---|---|---|
| 17 | 0x55790 | OOB | `function_4133f0` | C (m11_ov.c) | 0x350d1b | `i32.load` の番地 = 旧値 −8 | ← `function_446400` (0x16f6eb) ← `function_44bb70` ← `function_455790` ← `m11_icall` |
| 53 | 0x158e20 | OOB | `function_418190` | C (m11_ov.c) | 0x350ea4 | `i32.load` の番地 = `*dest − 12` (refcnt 読み) | ← `function_418210` (0x775eb) ← `function_8cbb00` ← `function_8cbcb0` ← `function_8cc190` ← `function_8c7a10` ← `function_8c5cc0` ← `function_558e20` |
| 56 | 0x16fde0 | OOB | `function_8c6530` | IR | 0x26e75e | `i32.store` の番地 = IR の計算値 | ← `function_8c5eb0` ← `function_56fde0` ← `m11_tr_function_56fde0` ← `m11_icall` |
| 87 | 0x19f9a0 | OOB | `function_418190` | C | 0x350ea4 | 53 と同じ | ← `function_59f9a0` ← `m11_tr_function_59f9a0` ← `m11_icall` |
| 114 | 0x223840 | halt0 | — | — | — | Halt 呼出し (trap ではない) | — |
| 138 | 0x243270 | OOB | `function_418190` | C | 0x350ea4 | 53 と同じ | ← `function_418210` (0x775eb) ← `function_646130` ← `function_6462e0` ← `function_646a80` ← `function_643410` ← `function_643270` ← `m11_tr_function_643270` |
| 144 | 0x25c540 | OOB | `function_407e20__lifted` | IR | 0x13cbf7 | `i32.store8` の番地 = IR の計算値 (1 byte 書込み) | ← `function_407e20` (0x13be0e) ← `function_409440__lifted` ← `function_409440` ← `function_412d60` ← `function_413060` ← `function_414ec0` ← `function_652500` |
| 149 | 0x264260 | OOB | `function_412e40` | IR | 0x06b473 | `i32.load` の番地 = `local6 − 8` (ヘッダ読み) | ← `function_653660` ← `function_6539e0` ← `function_664190` ← `function_664260` ← `m11_tr_function_664260` ← `m11_icall` |
| 158 | 0x0 | OOB | `function_409c80` | IR | 0x0ba4f5 | `i64.store` の番地 = IR の計算値 (dst = 0 の Move) | ← `function_4133f0` (0x350ca8・C) ← `function_414c70` (0x74e8a) ← `function_43c4c0` ← `function_653660` ← `function_6539e0` ← `function_665bd0` ← `function_66d050` |

- unit 158 の VA はテーブル値 0 (`m11_unit_va` が 0 を返す)。前 run の「unit 0x0」と同じ unit。
- 「命令形」の IR 計算値は、IR 版の関数で wasm 命令の番地計算を確認したもの。C 版 (4133f0・418190) は m11_ov.c の該当行で読みを確認した (4133f0: `D(s−8)`・`D(hdr+8)`、418190: `Q(dest)` 読み → `D(old−0xc)`)。

## 2. probe による引き金の値 (変種 `probe_942`: IR 版 5 関数の entry 引数と 412c20 の戻り値)

`probe_942.py` で IR 版の関数に記録を入れ、`trap_probe_942.mjs` で trap の瞬間に読んだ。記録は **unit 内で各関数の最後の entry** (後の呼出しで上書きされる) なので、trap した呼出しと一致しない場合がある。

| unit | 関数 (最後の entry) | a1 | a2 | a3 | 戻り値 |
|---|---|---|---|---|---|
| 17 | `409c80` | 0x482cc | 0x6 | 0x6 | — |
| 17 | `412c20` | 0x0 | — | — | 0x0 (最後の呼出し。a2=6 の呼出しとは別) |
| 56 | `409c80` | 0x1703f0 | 0x10bdb090 | 0xc | — |
| 56 | `8c6530` | 0x10b72420 | 0x670067 | 0x67006f | — |
| 144 | `407e20__lifted` | 0x10a9f860 | 0x0 | 0x0 | — |
| 144 | `409c80` | 0x10a9f870 | 0x10be4e90 | 0x2 | — |
| 149 | `407e20__lifted` | 0x10bdbe00 | 0x0 | 0x0 | — |
| 149 | `412e40` | 0x10a9f8f8 | 0x2 | — | — |
| 158 | `409c80` | 0x63006100630074 | 0x0 | 0x1a904afc | — |
| 158 | `412c20` | 0x8d48257e | — | — | 0x0 |

- unit 158: `409c80` の a3 = `0x1a904afc` = `0x8d48257e * 2` (32bit)。`412c20` は `0x8d48257e` を受けて 0 を返し、`dst = 0` になった。`src` は UTF-16 の中身。
- 記録域は `0x11FFF000` 以降 (SP は trap 時 0x10a9f5xx〜0x10a9f8xx で、衝突しない)。probe 変種は build rc 0・units_run 17・threw OOB (base と同一)。

## 3. 受入への反映

- 受入 1 (trap 9 件の原因): **部分**。発生箇所は全件確定。直接の引き金は unit 158 (文字列の中身が値として渡る) と unit 17 (412c20 が 6 を返す) で、他は未確定。
- 受入 2 (boot threw): **部分**。通常 boot の trap は unit 17 と同一。上流の引き金は unit 17 の 412c20 の戻り値 (6) と、unit 158 の上流 `function_414c70` が渡す `src` の値。
- 受入 3: 変更なし (#1469 の判定を維持)。

## 4. 測定

- 測定 commit: `686fb627` (`trap_units.mjs` の chain 出力追加)。e2e の経路コードは origin/main `a8c02d48` と同一 (`git diff a8c02d48 686fb627 -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_450560.py tools/m11/m11_ov.c | wc -l` → `0`)。
- e2e (HEAD `686fb627`): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` → **57.6 秒 (real)・rc 0・judge PASS**。load 0.89 / 0.60 / 0.33 (実行直後)。stage4 units 17/942・icall 24・threw OOB (base = fix)。survey ok 136 / trap 9 (base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。
- probe 変種 (`probe_942.py` → `stage4.sh work/probe_942.ll probe`): build rc 0・units_run 17・threw OOB。`trap_probe_942.mjs` の出力は §2。
- 追加ツール (本 PR): `probe_942.py` (記録の挿入)・`trap_probe_942.mjs` (読出し)・`trap_units.mjs` (chain)。e2e 経路には入らない。

## 5. 次の入口

1. `function_414c70` (IR) の引数の作り (`src` に文字列の中身が入る経路) を確認する。unit 158 の上流。
2. `function_412c20` (IR) の戻り値 6 の由来を確認する。unit 17 の上流。`412c20` は `%rax.0.reg2mem` 経由で、`(len)` の分岐を持つ。
3. C 版 `function_4133f0`・`function_418190` の引数は、IR probe では記録できない。m11_ov.c の該当関数の entry に記録を入れる変種が要る (次 run)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 158 の上流 (`function_414c70` が `src` に文字列の中身を渡す経路) | 受入 1・2 | #942 (次 run) |
| unit 17 の `412c20` が 6 を返す経路 | 受入 1・2 | #942 (次 run) |
| C 版 4133f0・418190 の引数の実測 (C 側の probe 変種) | 受入 1 (53・87・138 と 17 の直接の値) | #942 (次 run) |
| unit 56・144・149 の引き金の値 | 受入 1 | #942 (次 run) |
| work-m11 の IR と現 main の不一致 | 測定の母体が現 main と違う | 既存 #680 |

## 7. 再現

```sh
cd <worktree>                      # branch 942-trap-unit-attrib
tar --zstd -xf <素材>/work-m11.tar.zst -C .        # <素材> = 素材の置き場 (ARTIFACTS_DIR)
tar --zstd -xf <素材>/work-liftdiff.tar.zst -C .
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs
python3 tools/m11/ldfix/probe_942.py tools/m11/work/boot_final3.ll tools/m11/ldfix/work/probe_942.ll
(cd tools/m11/ldfix && bash stage4.sh work/probe_942.ll probe)
S4_NAME=probe S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_probe_942.mjs
python3 tools/m11/m11_wasmnames.py tools/m11/ldfix/work/stage4/base/m11_boot.cjs.wasm 14871 14873 725
```
