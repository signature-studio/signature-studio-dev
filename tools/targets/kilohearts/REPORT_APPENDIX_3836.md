# REPORT 付録 (#3836 KH-71): double のビット再解釈 `(ulonglong)dVarN` の書換え

#3802 (KH-66) の残件 (付録 `REPORT_APPENDIX_3802.md` §10-7u の「double のビット再解釈 98 行」) の付録。

#### 10-7v. #3836 (KH-71): `--fix dbitcast` を追加 (部分・行ごとの機械語分類は未完)
- 結論: Delay の `(ulonglong)dVarN` 98 行・`(ulonglong)dStack_N` 11 行 → **0 行**。書換えは `d2u()`/`u2d()` (memcpy) で、新しい fix フラグ `dbitcast` (既定は無効)。Gain/Haas/Gate の生成 C は本体が変わらない (ヘッダ行の fix 一覧だけ変わる)。Delay の emcc error は 409 件のまま (前後同数。コンパイル可否は変わらない)。
- 受入 1 (98 行の機械語との 1 件ずつの分類表) は**未達**。理由: Ghidra の `HighVariable` 経由で行と命令を対応づける probe を試したが、対応が安定しなかった (p-code 行の 2,765 件のうち命令が引けた行が一部)。残りは未解決表で子に移す。
- 受入 2 (`dbitcast` 規則を入れ、float の既存 fix と Gain/Haas/Gate の生成 C を変えない) は**達成** (下の表)。
- 受入 3 (1000 trial 突合) は #3073 [KH-41] の範囲。本 run では測定していない。

**① 環境 (repo 外。`$RUNNER_TEMP` のみ・`work/` は使わない)**
- 素材 `plugins-kilohearts`: `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。
- [GHIDRA] 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip` 569,649,598 B・sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。[JDK21] `temurin-21-jdk-amd64`。[EMSDK] emcc 6.0.12 (`toolchain-emsdk`)。
- decompile: Delay の `SNAPINS['delay']` の閉包 139 関数 → **139/139 OK** (`analyzeHeadless` wall 33 s)。Gain/Haas/Gate の閉包 9 関数 → **9/9 OK**。

**② 98 行の所在 (decompile 出力の実測)**
- `(ulonglong)dVarN` の出現は 98 行。`(ulonglong)dStack_N` は 11 行 (`dStack_88` の bit 演算)。
- 所在 (関数 → 行数): `180fc4590` 53・`180fcce40` 11・`180fcd690` 8・`180fce0d0` 7・`180fc6d70` 7・`180fc6870` 6・`180fcd400` 3・`1802ed7f0` 3。Gain/Haas/Gate の閉包には `(ulonglong)dVar` が 0 行。
- 行ごとの機械語 (`movq`・`movsd`・`cvt*`) との 1 件ずつの対応は**未完** (受入 1)。`CastProbe.java` (repo 外) で p-code の `CAST`/`COPY` と命令を引いたが、行への対応づけが安定しなかった。`CVT*` (数値変換) は全 2,765 行のうち 11 件のみで、`(ulonglong)` の bit 再解釈とは別経路。

**③ 書換えの規則 (`ghidra_to_c.py` の `dbitcast`・`ghidra_shim.h` の `u2d`)**
- `(ulonglong)X` (X は double 変数: 関数内で `double X` と宣言されたもの) → `d2u(X)` (shim 既存)。
- `(double)( … (ulonglong)X … )` → `u2d( … )` (ビット演算の結果を double として読む形)。
- `(double)(int)…`・`(double)(uint)…` は数値変換なので残す (`d2u` の対象外)。
- double でない `(ulonglong)param_N` (3 件・`FUN_180fc4590` 関数の uint64 引数) は触らない。

**④ 測定 (HEAD の生成 C と emcc)**

| 項目 | 前 (`origin/main` `cb1ca5e18`) | 後 (`dbitcast` 付き) |
|---|---|---|
| Delay の `(ulonglong)dVar`・`(ulonglong)dStack` | 98 | **0** |
| Delay の `d2u(` / `u2d(` | 0 / 0 | 147 / 32 |
| Delay の emcc `error:` (`emcc -c -ferror-limit=0`) | 409 | 409 |
| Gain の生成 C (本体) | 基準 | 同一 (ヘッダ行の fix 一覧のみ差分) |
| Haas の生成 C (本体) | 基準 | 同一 (同上) |
| Gate の生成 C (本体) | 基準 | 同一 (同上) |

- 基準の md5 (ヘッダ行込み・origin/main): gain `dda73a5f4a5cfca60ea833d3b00c370a`・haas `d3269137ddf7a46b4d9093dd118d7094`・gate `bffa651066a0364e2ade28e6fbeed700`。
- 注: Delay の emcc 件数 409 は、本 run の emcc 6.0.12 での値 (REPORT_APPENDIX_3802 の 534 件とは emcc と HEAD が異なるため直接比較しない)。
- **1000 trial 突合は未測定** (受入 3。#3073 [KH-41])。Gain/Haas/Gate の wasm の bit-exact は、本体が同一の C から出ているため変わらないと判断したが、`build_cmp.sh` は回していない (未確認)。

**⑤ 未解決 (起票先)**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 98 行の機械語 (`movq`・`movsd`・`cvt*`) との 1 件ずつの分類表 (受入 1) | 規則の正しさの根拠が未確定。現状は用途の文字列分類のみ | #3836 に残す (`Refs #3836`・次の run で行ごとの分類を続ける) |
| Delay の 1000 trial 突合 (受入 3) | Delay の bit-exact は未確認 | #3073 [KH-41] |
| Gain/Haas/Gate の `build_cmp.sh` 再測定 | 本体が同一なので差は出ない見込みだが未測定 | 本 PR の検証に含めず (必要なら #3073) |
