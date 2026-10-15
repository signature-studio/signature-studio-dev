# REPORT 付録 (#4685 KH-108): Delay の型不一致 残件のうち #3837・#4672・#4671 に当たらない分の規則

#3835 (KH-70) の付録 `REPORT_APPENDIX_3835.md` ⑤ の「型の不一致 → #4685 (残り)」の分。

## ①. 結論

- issue 本文の「残り 8 件」は現行 main の census と合わない。origin/main `b28128e48` で同じ fix 集合を流すと、型不一致は **110 行** で、#3837 (ptr⇔int 75)・#4672 (void 14・BINOP 9)・#4671 (関数ポインタ 9) の 107 行に当たる。当たらないのは **3 行** のみ。
- 3 行を機械語で確定し、`ghidra_to_c.py` の `DELAY_RULES` に 1 行 1 規則で入れた (件数 assert 付き)。型不一致は 110 → **107** (emcc error 行 331 → 328)。残り 107 行は既存の子 issue が担う (表 ③)。
- Gain/Haas/Gate の生成 C と 1000/1000 bit-exact は測定 commit `c682f1185` の値。現 HEAD `e427f9fa3` では未再測定 (④ 参照)。

## ②. 3 行の分類と機械語による確定

| 行 (`delay.c` の emcc 行) | 元の式 | 機械語 (HeartCore.core_64) | 規則 (`ghidra_to_c.py`) |
|---|---|---|---|
| 7195・7248 | `_DAT_18436cd18 = puVar3 + 0x40;` (`FUN_181327120`・`FUN_181327348`) | `181327388: mov qword ptr [rip+..], rax` と `181327470` の同形。8 byte の整数書込み。値は `puVar3+0x40` のアドレス | `_DAT_18436cd18` の GTYPE を `longlong` にし、代入を `(longlong)(puVar3 + 0x40)` に (件数 2) |
| 3047 | `auVar2._4_12_ = _UNK_182280e04;` (`FUN_180fc4590`) | 16 byte 定数 `e00` を `psubd`/`vpsubd` で読む (`180fc4ae6`・`180fc5656`)。`e04` は `e00` の 4〜15 byte に当たる。`e04` を直接指す命令は無い | `memcpy(&auVar2._4_12_, gd_182280e04, 12);` (件数 1) |

- `_DAT_18436cd18` の読出しは closure 内に無い (`181327120`・`181327348` の書込みのみ)。GS 失敗経路の値で、通常経路では到達しない。
- 件数 assert は表ごとの `n` (LAB 1・PTR__ 1・`_DAT_18436cd18` 2・`_UNK_182280e04` 1)。外れると converter が停止する。

## ③. 残り 107 行の起票先 (現行 HEAD の census・行の本文で分類)

| 分類 | 件数 | 起票先 | 根拠 |
|---|---|---|---|
| pointer⇔整数 (引数・代入の `int`/`longlong` ⇔ `undefined8 *` 等) | 75 | #3837 [KH-72] | issue 本文の対象 (87 件の子集合。現行 census は 75) |
| void 戻り値・BINOP (`(uint)` / `V128` 演算) | 14 + 9 | #4672 [KH-107] | issue 本文の対象 (本文は 7+7 と書くが、現行は 14+9 に増えている) |
| 関数ポインタ global `(*_DAT_1813a1d40)(...)` | 9 | #4671 [KH-106] | 本文の対象 9 行と一致 |

分類は行の本文 (`emcc_census.py` の RULES と、`delay.c` の該当行) で決めた。行番号の対応は `work/` に置いた (repo 外に出さない)。

## ④. 測定

測定 commit: `c682f1185` (`ghidra_route` の変更を含む HEAD)。base は `b28128e48` (origin/main)。

- 環境: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)・JDK 21 (temurin-21)。すべて repo 外 (`/tmp/opencode`)。n=1。load は未記録。

| 測定 | base `b28128e48` | HEAD `c682f1185` |
|---|---|---|
| Delay emcc error 行 (`emcc -c -ferror-limit=0`・fix `bitcast,intload,stackpair,assoc,concat,gtype,lanes`) | 331 | **328** |
| 型不一致 (`演算・代入・ポインタ`) | 110 (うち未割当 3) | **107** (未割当 0) |
| Delay closure | 139 関数 (decompile 139/139 OK・33.0 s wall) | 同 |
| Gain / Haas / Gate の生成 C | — | origin/main と **byte 一致** (`cmp`・3 本) |
| 突合 (`build_cmp.sh`・1000 trial・seed 7) | — | Gain **1000/1000** (4999/4999・wasm 15,161 B)・Haas **1000/1000** (5500/5500・16,878 B)・Gate **1000/1000** (4999/4999・17,367 B) |

- 所要 (実測 wall): Ghidra の closure 33.0 s・Delay の emcc (census・`-ferror-limit=0`) 15.8 s・`build_cmp.sh gain` 1.002 s (haas・gate は未計時)。
- `DELAY_RULES` の件数は 4 規則すべて hit (converter は停止せず終了)。

### ④-2. HEAD までのコード差分 (`c682f1185` → `e427f9fa3`)

`git diff --stat c682f1185 e427f9fa3 -- tools/targets/kilohearts/ghidra_route` = 4 ファイル・+118/-8。main 取り込みで入った変更で、本 PR の 3 行の規則とは別物。

| ファイル | 変更 | 出所 |
|---|---|---|
| `ghidra_to_c.py` | +5 | FNPTR 規則 (#4671 KH-106) |
| `patches.py` | +7 | `1813a1d40: FNPTR` (#4671)・xmm0 規則 (#3885 KH-77) |
| `kh_xmm0.h` | +90 (新規) | xmm0 helper (#3885) |
| `xmm0_check.c` | +24/-8 | xmm0 規則 (#3885) |

- この差分に対する再測定 (Delay emcc error 行・型不一致の内訳・Gain/Haas/Gate の byte 一致 (比較先は origin/main)・1000 trial 突合) は**未実施**。
- 理由: `$HOME/artifacts` に `fl-win64.tar.zst` のみあり、`plugins-kilohearts`・`toolchain-emsdk` が実在しない。PR 本文に `oc_artifacts: plugins-kilohearts toolchain-emsdk` を書いて再起動すれば測定できる。

## ⑤. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 型不一致の残り 107 行 (ptr⇔int 75・void 14・BINOP 9・関数ポインタ 9) | Delay の wasm 化が未完 | #3837 (75)・#4672 (23)・#4671 (9)。既存 open |
| Delay の突合 (1000 trial) | emcc が通らないため未実施 (#3073 が正本) | #3073 [KH-41] (既存) |
| 既存 shim (`dint`・`fint`) を使うか | 現状は fail-fast stub | PM 判断 (`REPORT_APPENDIX_3802.md` §⑦) |
