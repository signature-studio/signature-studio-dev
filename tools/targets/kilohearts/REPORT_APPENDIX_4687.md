# REPORT 付録 (#4687 KH-110): Delay の BINOP 残件 (float と uint の XOR・比較) の規則

親 #4672 (KH-107) の残件のうち、Delay の BINOP 残件。上位の経緯は `REPORT_APPENDIX_3849.md` (KH-80・#3849 の残り 23 件の分類) が正本。

## 結論

- `GTYPE` に `_DAT_` グローバル 4 件 (`184162118`・`184162a88`・`184162a98`・`182989380`) を足した。機械語の参照幅がすべて `qword` (8 byte) なので、C の `float`/`uint` 推定を `ulonglong` に直した。
- 現 head (`4cee297c1`) で再測定した。PR の 4 行の効果は、外した値との差で示す: 型不一致 **104 → 98** (−6)、emcc error 行 **357 → 351** (−6)。
- Gain/Haas/Gate の `.o` は、規則あり・規則のみ外す・`FX` から `gtype` を外す の 3 状態で `cmp` 一致 (1435/3217/3756 B)。
- 受入 1 (7 件それぞれの機械語確認と表) は**一部達成**。残り 1 件 (3068・`float`/`int`) は未確認。詳細は下の表。

## 測定

- 測定 commit: `4cee297c1` (コードを変えた最後の commit。現 head と同じ)。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (公式 release の zip、sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)。すべて `$RUNNER_TEMP/kh` (repo 外)。n=1。
- 実行: `bash tools/targets/kilohearts/ghidra_route/gtype_census.sh $RUNNER_TEMP/kh` (既定 FX = `bitcast,intload,stackpair,assoc,concat,gtype`)。decompile 151/151 OK。
- 規則のみ外す: `patches.py` の PR の 4 行を一時的に削除して同じ手順で回し、測定後に元へ戻した (commit はしていない)。
- 所要 (real): 規則あり 49.2 s。load は未記録。

| 現 head `4cee297c1` | 型不一致 | emcc error 行 | gain / haas / gate `.o` |
|---|---|---|---|
| 規則あり (本 PR の 4 行あり) | **98** | **351** | 1435 / 3217 / 3756 B |
| 規則のみ外す (PR の 4 行を削除) | 104 | 357 | 1435 / 3217 / 3756 B |
| `FX` から `gtype` ごと外す | 178 | 431 | 1435 / 3217 / 3756 B |

- 3 状態の `gain.o`・`haas.o`・`gate.o` は、`cmp` で 3 状態とも一致 (規則あり = 規則のみ外す = `FX` から `gtype` を外す)。
- 規則あり状態の emcc ログに残る `invalid operands` の float/uint 系は 1 行 (`delay.c:3069`・`float` と `int`。下の表の行 3068 の残件)。

### 数値の出所 (旧 363・365 との関係)

- 旧 PR 本文の「規則なし 110 / 363」は、現 head では再現しない (`FX` から `gtype` ごと外すと 178 / 431)。`632d687f3` 時点の作業ツリーで測った値だが、その後の作業ツリーでは再測定していない。
- `REPORT_APPENDIX_3849.md` の emcc 365 (変更後・gtype 単独) は、#3849 時点の tree の値で、現 head とは一致しない。
- 現 head の 3 状態のいずれも 363 / 365 にはならない。したがって 363 / 365 は現 head の基準値として使わない。

## 現 HEAD までの差分

`git diff 4cee297c1 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は空 (0 行)。測定 commit と検証 HEAD は同じ。

## 残件 (BINOP) の分類

| 行 (emcc・現行) | C | 機械語 | 判定 | 処理 |
|---|---|---|---|---|
| 4934 | `uVar2 = _DAT_182989380 ^ _DAT_184162118` (`FUN_180fd1b00`) | `mov rbx,[182989380]`・`xor rbx,[184162118]` (qword) | 整数 xor (幅 8)。`float` 推定が誤り | `GTYPE` 2 件 |
| 6662 | `_DAT_182989380 ^ _DAT_184162a88` (`FUN_180fe2470`) | `xor rbx,[184162a88]` (qword)・`mov [184162a88],rcx` (qword) | 同上 | `GTYPE` |
| 6692・6693 | `(_DAT_182989380 ^ _DAT_184162a98) >> …` (`FUN_180fe2788`) | `xor rdx,[184162a98]` (qword) | 同上 | `GTYPE` |
| 6707・6708 | 同 (`FUN_180fe27b0`) | `xor rdx,[184162a98]` (qword) | 同上 | `GTYPE` |
| 1248 (1249) | `uVar21 = (uint)fVar26 ^ _DAT_1813d1a80` (`FUN_1802ed7f0`) | `xorps xmm2,[1813d1a80]` (符号マスク 0x80000000)。float の値を `movaps` で複製し `andps` | 符号反転・絶対値のビット操作。`(uint)` は float のビット再解釈 | 型は既存 `GTYPE` の `1813d1a80: uint` のまま (変更なし) |
| 3068 (現 emcc 3069) | `uVar19 = auVar20._0_4_ & 0x3f` の `float`/`int` 演算 | 未確認 | 本 PR では未確認 | 残件 |
| 2683 | `(float)((uint)_DAT_182286970 ^ _DAT_1813d1a80)` | 未確認 | 本 PR では未確認 (#3836 の `dbitcast` との重なりを要確認) | 残件 |

受入 1 の「7 件」は issue 本文の時点の行番号による。現行の emcc 行とは対応が一部ずれる。

## 規則の置き場

- 型の上書きなので ABI 表ではなく `patches.py` の `GTYPE`。`ghidra_to_c.py --fix gtype` を付けたときだけ効く (既定は OFF)。規則が使われなければ `assert` で停止する。
- `f2u()`/`u2f()` の書換えではなく、`GTYPE` (型の上書き) を採った。`_DAT_` グローバルは整数マスクとして読まれているので、型の上書きで足りる。

## 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 3068 (現 emcc 3069・`float`/`int`) の機械語確認 | 1 件 | 次の run・#4687 に残す |
| 行 2683 (`(uint)_DAT_182286970` と #3836 の重なり) | 1 件。#3836 の `dbitcast` の規則で解消されるか未確認 | #3836 |
| 受入 1 の「1 件ずつの表」(本付録の表は 7 件の大半を確認したが、行番号の対応は一部) | 規則の根拠の完全性 | #4687 |
| 1000 trial 突合 (Delay の bit-exact) | 未確認 | #3073 [KH-41] |
| 旧 363 / 365 の出所 (どの tree で測ったか) | 現 head では再現しない。基準値には使わない | 本 PR の範囲外。必要なら #4687 に残す |
