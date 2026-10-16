# tools/flelift/boot — FLE-16 (#3771) 付録: 0x6bbc20 を `[obj+0x118]` へ書く命令の動的特定

> 親 REPORT: `tools/flelift/boot/REPORT.md` (§0・§1・§5 から参照)。本付録は #3771 の測定の全文。
> 既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 を照合。書込み元の特定のみで、類型の追加は行わない)。

## A. 結論

- (REPORT.md §0 から分割移動 #5897) FLE-16 (#3771): `0x6bbc20` を `[obj+0x118]` へ書く命令は `f_6bc010` の `0x6bc1af` (4・8・16 byte の store の監視で実行時 1 件・obj = `0x12d6a090`。1・2 byte の store は未監視)。役割は画素の store/blend 関数の登録 (推定)。呼出しは `f_6c9280` の `0x6c937a`。
- **書込み命令 = `0x6bc1af`** (`f_6bc010` 内): `mov qword ptr [rcx+0x118], rax`。`rax` は直前の `0x6bc1a8: lea rax,[rip-0x58f]` で `0x6bbc20` (= 0x6bc1af − 0x58f)。4・8・16 byte の store の監視で観測した書込みは **1 件** (診断 route・shim 有・停止まで。1・2 byte の store は監視していない・§F)。
- **obj** = `rcx` = `0x12d6a090`。宛先 `0x12d6a1a8` = obj + 0x118 (一致)。
- **後段の呼出し** = `0x6c937a` (`f_6c9280`) の `call qword ptr [rbx+0x118]`。target `0x6bbc20`、`R1 = R3 = 0x12d6a090` (同じ obj)。その後 unlifted で停止 (既知の停止点)。
- **戻り番地** (store 時点の `[RSP]`) = `0x6cd5d6`。`f_6bc010` は push なしで入るため、これは `f_6cd520` 内 `0x6cd5d1: call 0x6bc010` の戻り先。
- **役割 (推定を含む)**: `f_6bc010(obj=rcx, mode=dl)` は、obj の画素の書込み関数 (store) と合成関数 (blend) の対を選んで登録する設定関数。`[obj+0xc4] = dl` を保存し、`dl` (mode) で大分類 (1・2・3・その他) した上で `[obj+0x70] == 0x18` かどうかで 24bit 系と 32bit 系を選び、`(fn, ctx=obj)` を `obj+0x118/0x120` (store) と `obj+0x128/0x130` (blend) に書く。`0x18` = 24 を bpp と見るのは推定。

## B. 測定 (工程と実測)

| 項目 | 値 |
|---|---|
| 測定 commit | `236d83c87` (監視スクリプトを追加した `2c011b70c` に `origin/main` `e03d588ee` を merge した commit)。main 側の FLE-15 (#3770) が `fle_boot.c`・`fle_boot.mjs`・`fle6_measure.sh`・`fle_cpu.c` を変えたため、コードを変えた最後の commit は `236d83c87`。以降の commit は REPORT・DOC_MAP・本付録・結果 JSON のみ |
| コード差分 (測定 commit → HEAD) | `git diff --stat 236d83c87 HEAD -- tools/flelift/rt tools/flelift/x64c.py tools/flelift/boot/fle_boot.c tools/flelift/boot/fle_boot.mjs tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh tools/flelift/boot/wval_lift.py tools/flelift/boot/wval_measure.sh` は出力なし (差分 0) |
| 再現 (HEAD) | `236d83c87` 上で再測定 (ベースライン → 監視版 → ネガコン): 監視版は units 209・停止点 同じ・`[wval]` 1 件 (`va=0x6bc1af`)・`[wval-call]` 1 件 (`va=0x6c937a`)。取り込み前の `2c011b70c` と同じ値 |
| ベースライン | `FL_WIN64_DIR=<fl-win64> FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work> FLE_BOOT_TAG=wv0 FLE_BOOT_RUNS=diag_shim bash tools/flelift/boot/fle6_measure.sh` (`236d83c87` での値。fle6 全体 3 m 9.3 s: lift 73 s / clang-plain 88 s / boot 21 s、load 0.16→1.73) |
| 監視版 | `FLE_BOOT_WORK=<work> bash tools/flelift/boot/wval_measure.sh` (`236d83c87` での値: patch 4 s / build 86 s。boot の所要は未計時) |
| 結果 (ベースライン) | units_run **209** / stopped_at 209 / `unlifted` (`[fleboot][ff] unlifted 0x6bbc20 (call site ret=0x6c9380)`) / getmem 2314 / freemem 1200 / ipp_ok true (`results/boot_summary_wv0_diag_shim.json`) |
| 結果 (監視版, 書込み監視) | units_run **209** / stopped_at 209 / 停止点 同じ / getmem 2314 / freemem 1200 / ipp_ok true (差 0) |
| 結果 (ネガコン: 監視値 0x6bbc21) | `[wval]` 一致 **0 件** (0x6bbc20 の 1 件に対して特異的。`236d83c87` の再測定でも 0 件) |

KPI (起動に関わる PR。`docs/WORKFLOW.md` §7): FLEngine 起動の units_run は **前 209 / 後 209** (診断 route・shim 有)。最初のウィンドウ: **無し** (停止は `unlifted 0x6bbc20`)。既定経路 (root `0x6a7b70` 有) は**動かしていない** (既定の build・lift 経路は変えていない)。

## C. 書込みと呼出しの実測ログ (監視版・`run_wval.log` から抜粋)

```
[wval] va=0x6bc1af a=0x12d6a1a8 n=8 v=0x6bbc20 R0=0x6bbc20 R1=0x12d6a090 R2=0 R3=0x12d6a090 R5=0x1158b368 R6=0x12d6af40 R7=0x12d6a150 ret=0x6cd5d6
[wval-call] va=0x6c937a target=0x6bbc20 R1=0x12d6a090 R3=0x12d6a090 R5=0x1158b438
[fleboot][ff] unlifted 0x6bbc20 (call site ret=0x6c9380)
```

- 監視の仕組み: `lift` 出力の store 文を、guest VA を添えた監視版マクロに書き換えた copy (`wval_lift.py`、出力先 `work/boot/lift_wv/`) で置換。監視するのは 4・8・16 byte の store (`ST32`・`ST64`・`STF32`・`STF64`・`STX`・`STY`) で、値 (4 byte・8 byte・16 byte の上位/下位) が監視値に一致した store だけ出す。`ST8`・`ST16` は値を比較せず素通し (§F)。間接呼出し (`ott_dispatch`) の target が監視値のときは `[wval-call]`。`rt/` と `x64c.py` は変えていない。
- 既存の `FLE_WWATCH` (#3028) が使えなかった理由: 監視 slot が `rt/fle_cpu.c` の `0x15e1c78`・`0x15e4790` に固定で、任意の宛先 (ここでは obj 依存の `obj+0x118`) を監視できないため。
- 注釈の対応: 書込みの VA は lift 出力の `/* 6bc1af: mov qword ptr [rcx + 0x118], rax */` の行と一致する (`fle_lifted_s7.c`)。
- 件数: 監視値への一致 store は 1 件、間接呼出しの一致は 1 件。

## D. 書込み命令の逆アセンブル (PE, capstone で照合)

- `0x6bc1a1: mov qword ptr [rcx+0x120], rcx` / `0x6bc1a8: lea rax,[rip-0x58f]` / `0x6bc1af: mov qword ptr [rcx+0x118], rax` / `0x6bc1b6: mov qword ptr [rcx+0x130], rcx` / `0x6bc1bd: lea rax,[rip-0x514]` / `0x6bc1c4: mov qword ptr [rcx+0x128], rax` / `0x6bc1cb: ret`
- **#3771 本文の「PE 内の rip 相対 lea 参照では 0x6bbc20 を書く箇所が見つからない」は、この `0x6bc1a8` の lea により誤り** (rip 相対で 0x6bbc20 を指す)。4 byte 即値は PE 全体で 0 件 (同じ走査)。静的走査が見落とした理由は未確認 (推定: 関数内の lea の解決漏れ。#3491 の走査条件の確認が要る)。
- `f_6bc010` の分岐 (lift 出力の注釈から。`mode` = `[obj+0xc4]` = 入口の `dl`):
  - `mode == 1` → `[obj+0x70] == 0x18` で 24bit 系 (`0x6bc079`) / それ以外 (`0x6bc0a8`)
  - `mode == 2` → 同様に 24bit (`0x6bc0e1`) / それ以外 (`0x6bc110`)
  - `mode == 3` → `0x6bc13f` (`0x6bbf80`・`0x6bbfc0` 系の対)
  - それ以外 → `0x6bc16b`: `[obj+0x70] == 0x18` で `0x6bbbf0` 系 (`0x6bc175`)、それ以外で `0x6bc1a1` (**観測経路**: store `0x6bbc20` + blend `0x6bbcb0`)
- 各分岐の `(fn, ctx)` は `[obj+0x110]`・`[obj+0x108]` を含む一部の差があり、本付録は観測経路と 4 候補の役割のみ検証した (他経路は未測定)。
- 候補先の役割 (capstone で確認。いずれも lift 対象外 = unlifted):
  - `0x6bbc20` = **32bit 画素ストア**: `r8 = y*[obj+0x78](pitch) + [obj+0x50](buf) + 4*x` へ `mov dword ptr [r8], r9d` (r9d = colour)。issue 本文の「画素ストア」と一致。
  - `0x6bbbf0` = 24bit 画素ストア (3 byte、`x*3`)。
  - `0x6bbc40` = 24bit のアルファ合成 (`pmulhw` / `psubsw`)。
  - `0x6bbcb0` = 32bit のアルファ合成。
- 呼出元 `f_6c9280` (`0x6c937a`): `rdx = x` (esi)・`r8 = y` (edi)・`r9d = colour` ([rbp+0x3c])・`rcx = [obj+0x110]` を渡して `call [rbx+0x118]`。`f_6c9280` は矩形の画素を走査する塗り関数 (推定)。

## E. 呼出しの連鎖 (実行時と静的)

| 段 | 関数・VA | 根拠 |
|---|---|---|
| 書込み | `f_6bc010` @ `0x6bc1af` | 実行時 1 件 (C) |
| 呼出元 (実行時) | `f_6cd520` @ `0x6cd5d1` (`movzx rdx, [rbx+0xc4]`・`rcx = rbx` で `call f_6bc010`) | `ret=0x6cd5d6` (C) |
| 呼出元の呼出元 | 静的のみ: `f_6cd5f0` (`0x6cd639`) と `f_6ba1f0` (`0x6ba38f`)。実行時の判別は未実施 | lift 出力の `f_6cd520();` 呼出し |
| 後段の呼出し | `f_6c9280` @ `0x6c937a` `call [rbx+0x118]` | `[wval-call]` (C) |
| 親の呼出し | 静的: `f_815050` (`0x815bc7`)。実行時の戻り番地は未取得 | lift 出力の `f_6c9280();` 呼出し |

## F. 検証範囲と限界

- **範囲内**: 診断 route (`FLE_EXTRA_ROOTS=` + `FLE_DIAG_NULLFILL=1`・`FLE_IPP=1`・plain)。lifted C の 4・8・16 byte の store (`ST32`・`ST64`・`STF32`・`STF64`・`STX`・`STY`) と間接呼出し。「実行時の書込みは 1 件」は、この範囲の store に限った件数。
- **範囲外 (監視していない)**: 1 byte・2 byte の store (`ST8`・`ST16`)。`WV_ST8`・`WV_ST16` は値の比較なしで `ST8(a, v)`・`ST16(a, v)` に素通しし、`wv_chk_` は `n < 4` で即 return する。
- **範囲外 (未観測)**: (1) ホスト側 C (`fle_boot.c`・shimx・`rt/fle_glue.c`) からの書込み (memcpy 等) は監視していない。(2) 既定経路 (root `0x6a7b70` 有) での書込みは未測定。(3) `mode` (`[obj+0xc4]`) の値と `[obj+0x70]` の値は未記録 (本文の経路判定は分岐の構造からの推定)。
- 1 run・n=1 の結果。変動 (min–max) は未測定 (決定的な boot なので、同一 commit の再実行は同値と見る)。ネガコンは監視値を 1 ずらした 1 件で、値への特異性のみを示す。

## G. 再現

```sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<work> FLE_BOOT_TAG=wv0 FLE_BOOT_RUNS=diag_shim bash tools/flelift/boot/fle6_measure.sh
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> bash tools/flelift/boot/wval_measure.sh               # 0x6bbc20
FL_WIN64_DIR=<fl-win64 展開先> FLE_BOOT_WORK=<work> WVAL_VALUE=0x6bbc21 bash tools/flelift/boot/wval_measure.sh # ネガコン
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk`。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `f_6cd520` の実行時の呼出元 (静的候補: `f_6cd5f0`・`f_6ba1f0`) と `[obj+0xc4]` (mode) の設定元 | `0x6bc1af` の経路の上流。obj の書込み方式の決まり方 | #3868 [FLE-17] |
| 既定経路での書込みの有無・`[obj+0x70]`・`[obj+0xc4]` の値 | 既定経路の書込み元の確定 | #3868 [FLE-17] |
| ホスト側 C の書込みは未監視 | 監視の網羅性 (今回の 1 件は lifted C 側の 4・8・16 byte の store) | #3868 [FLE-17] (本付録 F) |
| 静的走査が `0x6bc1a8` の rip 相対 lea を見落とした理由 | 静的解析の信頼性 (走査条件) | #3868 [FLE-17] |
| 本修復 (buf = 0 の上流原因) | 範囲外 | #3112 (既存) |
