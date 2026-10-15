# REPORT 付録 (#4685 KH-108): Delay の型不一致 残件のうち #3837・#4672・#4671 に当たらない分の規則

#3835 (KH-70) の付録 `REPORT_APPENDIX_3835.md` ⑤ の「型の不一致 → #4685 (残り)」の分。

## ①. 結論

- issue 本文の「残り 8 件」は現行 main の census と合わない。origin/main `b28128e48` で同じ fix 集合を流すと、型不一致は **110 行** で、#3837 (ptr⇔int 75)・#4672 (void 14・BINOP 9)・#4671 (関数ポインタ 9) の 107 行に当たる。当たらないのは **3 行** のみ。
- 3 行を機械語で確定し、`ghidra_to_c.py` の `DELAY_RULES` に 1 行 1 規則で入れた (件数 assert 付き)。
- 現 HEAD `40e8af6de` (origin/main `6519db32a` を取り込んだ後) で再測定した。Delay の emcc error 行は **322** (比較先 origin/main `6519db32a` は 325)、型不一致 (`演算・代入・ポインタ`) は **101** (同 104)。3 規則ぶん (-3・-3) が効いている。
- Gain/Haas/Gate の生成 C は origin/main `6519db32a` と byte 一致 (`cmp`・3 本)。突合 1000 trial は 3 本とも 1000/1000。

## ②. 3 行の分類と機械語による確定

| 行 (`delay.c` の emcc 行) | 元の式 | 機械語 (HeartCore.core_64) | 規則 (`ghidra_to_c.py`) |
|---|---|---|---|
| 7195・7248 | `_DAT_18436cd18 = puVar3 + 0x40;` (`FUN_181327120`・`FUN_181327348`) | `181327388: mov qword ptr [rip+..], rax` と `181327470` の同形。8 byte の整数書込み。値は `puVar3+0x40` のアドレス | `_DAT_18436cd18` の GTYPE を `longlong` にし、代入を `(longlong)(puVar3 + 0x40)` に (件数 2) |
| 3047 | `auVar2._4_12_ = _UNK_182280e04;` (`FUN_180fc4590`) | 16 byte 定数 `e00` を `psubd`/`vpsubd` で読む (`180fc4ae6`・`180fc5656`)。`e04` は `e00` の 4〜15 byte に当たる。`e04` を直接指す命令は無い | `memcpy(&auVar2._4_12_, gd_182280e04, 12);` (件数 1) |

- `_DAT_18436cd18` の読出しは closure 内に無い (`181327120`・`181327348` の書込みのみ)。GS 失敗経路の値で、通常経路では到達しない。
- 件数 assert は表ごとの `n` (LAB 1・PTR__ 1・`_DAT_18436cd18` 2・`_UNK_182280e04` 1)。外れると converter が停止する。

## ③. 残り 101 行の起票先

- 現 HEAD の残りは `emcc_census.py` の 1 分類 (演算・代入・ポインタの型不一致) で 101 行。
- 旧 `c682f1185` 時点の分類は ptr⇔int 75・void 14・BINOP 9・関数ポインタ 9 (計 107)。起票先は旧分類で、ptr⇔int → #3837 [KH-72] (issue 本文の対象。87 件の子集合)、void・BINOP → #4672 [KH-107]、関数ポインタ global `(*_DAT_1813a1d40)(...)` → #4671 [KH-106]。
- 現 HEAD の 101 行への行単位の再分配は**未実施** (行本文の目視が要る)。

## ④. 測定

測定 commit: `40e8af6de` (`ghidra_route` の最後のコード変更。origin/main `6519db32a` の取り込み merge)。比較先 (base): origin/main `6519db32a` (worktree で同じ手順を実行)。

- 環境: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (zip sha256 全 64 桁 `ddac49f9…d2db` 一致)・JDK 21 (temurin-21)。素材の所在は `[DOWNLOADS]`・`[EMSDK]`・`[GHIDRA]` (`docs/REFERENCES.md`)。n=1。load は測定開始時 0.26 0.74 0.54 (`/proc/loadavg`)。

| 測定 | base origin/main `6519db32a` | HEAD `40e8af6de` |
|---|---|---|
| Delay emcc error 行 (`emcc -c -ferror-limit=0`・fix `bitcast,intload,stackpair,assoc,concat,gtype,lanes`) | 325 | **322** |
| 型不一致 (`演算・代入・ポインタ`) | 104 | **101** |
| Delay closure を含む lift 集合 (`gtype_census.sh`) | — | 151 関数 OK |
| Gain / Haas / Gate の生成 C (`cmp`・同じ fix) | — | origin/main と **byte 一致** (3 本) |
| 突合 (`build_cmp.sh`・1000 trial・seed 7) | — | Gain **1000/1000** (4999/4999・wasm 15,161 B)・Haas **1000/1000** (5500/5500・16,878 B)・Gate **1000/1000** (4999/4999・17,367 B) |

- 現 HEAD の emcc census (`emcc_census.py`・322 行): 128bit レーン型 135・引数数不一致 86・演算・代入・ポインタの型不一致 101。他の分類は 0。
- 所要 (実測 wall): `gtype_census.sh` (Ghidra decompile 151 関数・g2c・Delay と Gain/Haas/Gate の emcc) 全体 36.1 s。`build_cmp.sh` は gain・haas・gate とも 1 本 1 秒未満 (emcc 0.2 s・突合は 1 秒前後)。
- `DELAY_RULES` の件数は 4 規則すべて hit (converter は停止せず終了)。

### ④-2. HEAD までのコード差分 (`c682f1185` → `40e8af6de`)

`git diff --stat c682f1185 40e8af6de -- tools/targets/kilohearts/ghidra_route` = 4 ファイル・+227/-9。main 取り込みで入った変更で、本 PR の 3 行の規則とは別物。

| ファイル | 出所 |
|---|---|
| `ghidra_to_c.py` (+5) | FNPTR 規則 (#4671 KH-106) |
| `patches.py` (+7) | `1813a1d40: FNPTR` (#4671)・xmm0 規則 (#3885 KH-77) |
| `kh_xmm0.h` (+189 新規) | xmm0 helper (#3885) |
| `xmm0_check.c` (+35/-9) | xmm0 規則 (#3885) |

- 測定 commit (`40e8af6de`) 以降の `ghidra_route` の差分: `git diff --stat 40e8af6de HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行。
- 旧測定 (`c682f1185`・base `b28128e48`): Delay emcc error 328・型不一致 107 (未割当 0)・Gain/Haas/Gate 1000/1000。この値は main 取り込み前のもので、現 HEAD では読まない。

## ⑤. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 型不一致の残り 101 行 (現 HEAD の実測)。起票先の旧分類 (#3837 75・#4672 23・#4671 9 = 107) は現 HEAD へ再分配していない | Delay の wasm 化が未完 | #3837・#4672・#4671。既存 open。行単位の再分配は未確認 |
| Delay の突合 (1000 trial) | emcc が通らないため未実施 (#3073 が正本) | #3073 [KH-41] (既存) |
| 既存 shim (`dint`・`fint`) を使うか | 現状は fail-fast stub | PM 判断 (`REPORT_APPENDIX_3802.md` §⑦) |
