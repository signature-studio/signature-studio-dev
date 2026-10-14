# REPORT_942_TRAPSITE — stage4 survey の trap 9 件の発生箇所と直接の引き金 (#942 受入 1・2)

既知類型との関係: 該当なし (新規類型は判定しない。引き金の形は DEFECTS の D4 (引数・slot の幅や deref の誤り) と同じ方向の候補)。類型名の割当てと `docs/DEFECTS.md` の変更は PM 判断。

## 0. 結論

- survey の trap 9 件 (OOB 8・halt0 1。halt0 は unit 114 で trap ではない) は、**全件で最内 frame と wasm 位置を確定**した。OOB 8 件は 6 箇所に分かれる。
- **実行されるのは C 版の 2 関数**: `function_4133f0` と `function_418190` は `tools/m11/m11_ov.c` の C 転記で置換されている (IR 版は実行されない)。
- 直接の引き金 (C 版・IR 版の probe で実測):
  - **unit 53・87・138** (C 版 `function_418190` @0x350ea4 の共通箇所): 参照カウントの読み `wrap(old)−12` の old (= `*dest`) が **0x100000000・0x76800000000・0x1ce900000000**。下位 32bit が 0 で、上位 32bit に小さい値 (1・0x768・0x1ce9) が入っている。32bit 値が 32bit ずれた形に見える。書込み元は未特定 (上流 `function_418210`・`function_59f9a0`)。
  - **unit 158 (VA 0)**: C 版 `function_4133f0` の `src` = `0x0063006100630074` (UTF-16 の "tcac" の中身)。これを `function_409c80` (IR) が `dst = 0`・`n = 0x1a904afc` で受けて trap。`n` は `function_412c20(0x8d48257e)` 由来。上流は `function_414c70` (IR)。
  - **unit 17** (C 版 `function_4133f0` の末尾 `old = Q(dest)` → `D(old−8)`): `412c20(3)` が 6 を返し、それが `*dest` に残ったと推定 (推定。trap した呼出しの値は未記録)。
  - unit 56・144・149 (IR 版 `function_8c6530`・`function_407e20__lifted`・`function_412e40`): 引き金は §2 の IR 版の記録だけでは確定しない。
- 受入 2 (boot threw): 通常 boot の trap (§14-2 の wasm 0x350d1b・`function_4133f0`) は unit 17 と同一箇所。上流は同じ。

## 1. 9 unit の trap 位置

測定: `S4_NAME=base S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_units.mjs` (base = 修復前 IR・HEAD `686fb627`)。最内 wasm 位置は `chain` の先頭。IR 名は `tools/m11/m11_wasmnames.py`、命令は `wasm-objdump -d` (wabt 1.0.39)。

| unit | VA | 種別 | 最内 frame | 実行体 | wasm 位置 | 命令形 | chain (最内から) |
|---|---|---|---|---|---|---|---|
| 17 | 0x55790 | OOB | `function_4133f0` | C | 0x350d1b | `i32.load` の番地 = 旧値 −8 | ← `function_446400` (0x16f6eb) ← `function_44bb70` ← `function_455790` ← `m11_icall` |
| 53 | 0x158e20 | OOB | `function_418190` | C | 0x350ea4 | `i32.load` の番地 = `*dest − 12` (refcnt) | ← `function_418210` (0x775eb) ← `function_8cbb00` ← `function_8cbcb0` ← `function_8cc190` ← `function_8c7a10` ← `function_8c5cc0` ← `function_558e20` |
| 56 | 0x16fde0 | OOB | `function_8c6530` | IR | 0x26e75e | `i32.store` の番地 = IR の計算値 | ← `function_8c5eb0` ← `function_56fde0` ← `m11_tr_function_56fde0` ← `m11_icall` |
| 87 | 0x19f9a0 | OOB | `function_418190` | C | 0x350ea4 | 53 と同じ | ← `function_59f9a0` ← `m11_tr_function_59f9a0` ← `m11_icall` |
| 114 | 0x223840 | halt0 | — | — | — | Halt 呼出し (trap ではない) | — |
| 138 | 0x243270 | OOB | `function_418190` | C | 0x350ea4 | 53 と同じ | ← `function_418210` (0x775eb) ← `function_646130` ← `function_6462e0` ← `function_646a80` ← `function_643410` ← `function_643270` ← `m11_tr_function_643270` |
| 144 | 0x25c540 | OOB | `function_407e20__lifted` | IR | 0x13cbf7 | `i32.store8` の番地 = IR の計算値 | ← `function_407e20` (0x13be0e) ← `function_409440__lifted` ← `function_409440` ← `function_412d60` ← `function_413060` ← `function_414ec0` ← `function_652500` |
| 149 | 0x264260 | OOB | `function_412e40` | IR | 0x06b473 | `i32.load` の番地 = `local6 − 8` | ← `function_653660` ← `function_6539e0` ← `function_664190` ← `function_664260` ← `m11_tr_function_664260` ← `m11_icall` |
| 158 | 0x0 | OOB | `function_409c80` | IR | 0x0ba4f5 | `i64.store` の番地 = IR の計算値 (dst = 0 の Move) | ← `function_4133f0` (0x350ca8・C) ← `function_414c70` (0x74e8a) ← `function_43c4c0` ← `function_653660` ← `function_6539e0` ← `function_665bd0` ← `function_66d050` |

- unit 158 の VA はテーブル値 0 (`m11_unit_va` が 0 を返す)。前 run の「unit 0x0」と同じ unit。
- C 版の命令形は m11_ov.c の該当行で確認 (4133f0: `s = src`・`D(s−8)`・末尾 `old = Q(dest)`・`D(hdr+8)`、418190: `old = Q(dest)`・`Q(dest) = 0`・`D(old−0xc)`)。

## 2. probe による引き金の値

変種は 2 種類。IR 版の関数は `probe_942.py` (entry と ret に記録)、C 版の 2 関数は `probe_c_942.py` (m11_ov.c の複製に記録)。`trap_probe_942.mjs` が trap の瞬間に読む。**記録は unit 内で各関数の最後の entry** (後の呼出しで上書きされる) なので、trap した呼出しと一致しない場合がある。

| unit | 関数 (最後の entry) | 引数・値 | 読み |
|---|---|---|---|
| 53 | C `418190` | dest=0x10a9f8a0・**old=0x100000000** | refcnt の番地が wrap で範囲外 |
| 87 | C `418190` | dest=0x10a9f948・**old=0x76800000000** | 同上 |
| 138 | C `418190` | dest=0x10a9f8c0・**old=0x1ce900000000** | 同上 |
| 158 | C `4133f0` | dest=0x10a9f8d8・**src=0x63006100630074** | src は UTF-16 の文字の中身 |
| 158 | IR `409c80` | a1=0x63006100630074・a2=0 (dst)・a3=0x1a904afc (n) | dst=0 への Move で trap |
| 158 | IR `412c20` | a1=0x8d48257e・ret=0 | n = 2·len の len |
| 17 | C `4133f0` | dest=0x10a9f7d8・src=0 | 末尾 `D(old−8)` の old は直前の呼出しの `*dest` |
| 17 | IR `409c80` | a1=0x482cc・a2=6 (dst)・a3=6 (n) | dst=6 は 412c20 の戻り値 (§0 の推定) |
| 149 | C `4133f0` | dest=0x10a9f918・src=0 | trap は IR `412e40` |
| 56 | C `4133f0` | dest=0x10bbf264・src=0x1703f0 | trap は IR `8c6530` |
| 56 | IR `8c6530` | a1=0x10b72420・a2=0x670067・a3=0x67006f | a2 は UTF-16LE の "gg"、a3 は "og" (2 文字分の中身が値として渡る形。1 文字ずつの一致ではない) |
| 144 | IR `407e20__lifted` | a1=0x10a9f860・a2=0 | 記録に引き金の値なし |
| 149 | IR `407e20__lifted`・`412e40` | 407e20: a1=0x10bdbe00 / 412e40: a1=0x10a9f8f8・a2=2 | 同上 |

- 記録域は `0x11FFF000`〜 (C 版は `0x11FFF400`・`0x11FFF420`)。SP は trap 時 0x10a9f5xx〜0x10a9f8xx で衝突しない。
- 53・87・138 の old は全て下位 32bit が 0。値の由来 (`<< 32` が入る経路) は未特定。
- 導出 (実測ではない): C 版 `function_418190` は `old != 0` のとき `D(old−0xc)` を読む (`m11_ov.c`)。old の下位 32bit が 0〜11 だと、32bit の番地が wrap して範囲外になり trap する。実測の 3 件は下位 32bit が 0 で、この条件に当たる。次の probe では、この条件を満たす値を書く上流 (`function_418210`・`function_59f9a0`) を追う。

## 3. 受入への反映

- 受入 1 (trap 9 件の原因): **部分**。発生箇所は全件確定。直接の引き金は unit 53・87・138 (`*dest` の上位 32bit 値)、unit 158 (文字列の中身が値として渡る) で値まで確認。unit 17 は推定。56・144・149 は未確定。
- 受入 2 (boot threw): **部分**。通常 boot の trap は unit 17 と同一箇所。上流の引き金は unit 17 の推定 (412c20 の戻り値 6)。
- 受入 3: 変更なし。#1469 (PR・MERGED) で達成済み。#1292 (issue) は CLOSED。

## 4. 測定

- §1 の測定 commit: `686fb627` (`trap_units.mjs` の chain 出力追加)。差分 0 の証跡: `git diff 686fb627 HEAD -- tools/m11/ldfix/trap_units.mjs | wc -l` → `0`。
- e2e の測定 commit: `dd6ec9ec` (main `46c92356` の取り込み後の HEAD)。e2e の経路は `686fb627` から変わっていない: `git diff 686fb627 HEAD -- tools/m11/ldfix/ldfix_e2e.sh tools/m11/ldfix/stage4.sh tools/m11/ldfix/survey_stage4.mjs tools/m11/ldfix/ldfix.py tools/m11/ldfix/fix_450560.py tools/m11/m11_ov.c | wc -l` → `0`。
- e2e (n=3・同一 HEAD): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` → **58・58・68 秒 (min–max 58–68 秒)・rc 0 (3/3)・judge PASS (3/3)**。実行直前の 1 分 load 0.33 / 1.76 / 1.34。stage4 units 17/942・icall 24・threw `memory access out of bounds` (base = fix)。survey ok 136 / trap 9 (base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。
- 参考 (n=1 の別 run): 57.6 秒 (`686fb627`)・67.8 秒 (review の再実行 `2df6909f`)。
- probe 変種 (IR 版 + C 版の複製): build rc 0・units_run 17・threw OOB (base と同一)。§2 の値はこの変種の survey 実行による。

## 5. 次の入口

1. 53・87・138 の `*dest` に `value << 32` の値が入る経路。→ unit 53 は解決: 書込みは `alloca ptr` への 4 byte 格納で、上位 4 byte の残骸が 8 byte 読みで入っていた (REPORT_942_PTRSLOT.md)。87・138 は未確定。
2. unit 158: `function_414c70` (IR) が `function_4133f0` の `src` に文字列の中身を渡す経路。
3. unit 17: `function_412c20` (IR) が `len = 3` に対して 6 を返す経路。
4. unit 56・144・149: IR 版 `8c6530`・`407e20__lifted`・`412e40` の引き金の値 (記録の対象を広げる)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `*dest` に `value << 32` が入る経路 (unit 53・87・138 の上流 `function_418210`・`function_59f9a0`) | 受入 1 (OOB 3 件) | #942 (次 run) |
| unit 158 の上流 (`function_414c70` が `src` に文字列の中身を渡す経路) | 受入 1・2 | #942 (次 run) |
| unit 17 の `function_412c20` が 6 を返す経路 (推定の確定) | 受入 1・2 | #942 (次 run) |
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
python3 tools/m11/m11_wasmnames.py tools/m11/ldfix/work/stage4/base/m11_boot.cjs.wasm 14871 14873 725
```

C 版 (`probe_c_942.py`・§2 の 53・87・138・158・17 の値) の再現は**本 fix では未実行** (review の m7)。review が行った手順: `cp tools/m11/m11_ov.c <退避先>` → `python3 tools/m11/ldfix/probe_c_942.py <退避先> tools/m11/m11_ov.c` で差し替え → `(cd tools/m11/ldfix && bash stage4.sh work/probe_942.ll probe)` と `S4_NAME=probe S4_IMAGE=tools/m11/work/m11_image.bin node tools/m11/ldfix/trap_probe_942.mjs` を実行 → `cp <退避先> tools/m11/m11_ov.c` で戻す (`git checkout` は使わない)。戻した後、`git diff --stat -- tools/m11/m11_ov.c` が空であることを確認する。
