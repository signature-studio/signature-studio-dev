# REPORT 付録 (#4911 KH-134): Stereo 閉包の型不一致を機械語で確定して GTYPE で書き換える (部分)

#### 結論

- **結論**: Stereo 閉包の型不一致 (build_cmp 条件) は **12 → 2** に減った (emcc error 10 件の解消。`stereo` の GTYPE 4 行が効く C の行は 6 箇所)。受入 1 は**部分** (2 件残り)。受入 2 (emcc 0) は**未達**。受入 3 (Gain/Haas/Gate 1000/1000) は **達成**。
- 本 PR は受入 1 の一部だけを完了単位にする。`Refs #4911` (未 close)。
- 単位: 件数は emcc の error 件数。行数は生成 C の行 (stereo.c 1300 等)。両者は別物 (GTYPE 1 行が複数の error 行に効く)。

#### 測定 commit

- 測定 commit (コードを変えた最後の commit): `7070e4f75` (`fix(kilohearts): stereo 閉包の型不一致を GTYPE で確定 (KH-134, #4911)`)。
- `git diff 7070e4f75 HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行 (本節の commit は REPORT のみ)。
- 検証起点: `origin/main` = `86e713de5`。

#### 素材・環境

- `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip` → `HeartCore.core_64` (sha256 は REPORT_APPENDIX_4871.md と同じ素材)。
- [GHIDRA] 12.1.4 (公式 release zip・sha256 先頭 `ddac49f9` 一致。展開先は [GHIDRA] の `$OPT` 直下)。JDK 21。[EMSDK] 6.0.12。n=1。

#### emcc 件数 (`emcc_census.py`・`emcc -c -w -O1 -ferror-limit=0`)

| 条件 | 引数数不一致 | 型不一致 | 合計 |
|---|---|---|---|
| 既定 (`-Wno-error` なし) | 8 | 32 | 42 |
| build_cmp と同じ (`-Wno-error=int-conversion` 等) | 8 | **2** | **10** |
| 前 (#4871 HEAD `678386211` 相当・build_cmp 条件) | 8 | 12 | 20 |

- 既定条件の型不一致 32 件は、`int-conversion` の error (ポインタ・整数の混同。Stereo 全体の既存の癖) を含む。REPORT の前回の 12 件は `-Wno-error` 条件での計数だった。
- 残り型不一致 2 件 (`stereo.c` 1300・1888): `(*_DAT_1813a1d40)(param_1)` の間接呼出しの結果を `float` 扱いで `*` している (`indirection requires pointer operand ('float' invalid)`)。FNPTR (`void (*)()`) にすると戻り値の代入が `void` 代入の error になるため、型を入れていない。
- 試行 (不採用): GTYPE `1813a1d40 = FNPTR` を入れると、件数は同じ 10 のまま、error が「`void` の代入」に変わった (1301・1889)。戻り値の型 (`int`/`undefined8`) を確定しない限り解けない。

#### 書換えた規則 (`patches.py` の `GTYPE['stereo']`・4 行)

| VA | 型 | 根拠 |
|---|---|---|
| `182989380` | `ulonglong` | delay 表 (REPORT_APPENDIX_3801.md) と同一 VA。stereo の xor/shift 行 1318・1869・1870 で被演算子 |
| `184162118` | `ulonglong` | delay 表と同一 VA。stereo の xor 行 1318 (`_DAT_182989380 ^ _DAT_184162118`) |
| `184162a98` | `ulonglong` | delay 表と同一 VA。stereo の xor/shift 行 1884・1885 |
| `18436cd18` | `longlong` | delay 表と同一 VA。stereo の代入行 2290 (`_DAT_18436cd18 = puVar3 + 0x40`) |

- **命令幅の確認 (逆アセンブル・確認済み)**: 素材 `plugins-kilohearts` の `HeartCore.core_64` (sha256 先頭 `d55ce8b4`) を `objdump -d -M intel` で全逆アセンブルし、4 VA を RIP 相対で指す命令を全件数えた。

  | VA | 型 | 参照命令数 | 命令 (内訳) | 幅 |
  |---|---|---|---|---|
  | `182989380` | ulonglong | 3,708 | mov 3,707・cmp 1 | `QWORD PTR` 全件 |
  | `184162118` | ulonglong | 2 | mov 1・xor 1 | `QWORD PTR` 全件 |
  | `184162a98` | ulonglong | 3 | mov 1・xor 2 | `QWORD PTR` 全件 |
  | `18436cd18` | longlong | 2 | mov 2 | `QWORD PTR` 全件 |

  - 確認方法: 逆アセンブル全体で `# 0x<VA>` の注釈を持つ行を抽出し、RIP 相対以外の参照は 0 件、幅指定は `QWORD PTR` のみ (BYTE・WORD・DWORD・XMMWORD は 0 件)。
  - 結論: 4 件の幅はすべて 8 byte。`GTYPE['stereo']` の 4 件は正しい。
- 突合 (Stereo の 1000 trial) は未実施 (下記)。
- `GTYPE` は `stereo` キーにだけ効く (gain・haas・gate の GTYPE は空)。gain・haas・gate の突合は本 HEAD で再実行し、REPORT 記載値と一致 (下記)。

#### 実測

- 閉包 (`closure.py stereo`): 49 関数・反復 1・FAIL 0・除外参照 3 件。wall 約 18 秒 (前回 REPORT の 5 分 22 秒は別の初期化を含む)。
- Gain **1000/1000** bit-exact (calls 4999/4999・wasm 15,161 B)。Haas **1000/1000** (calls 5500/5500・wasm 16,878 B)。Gate **1000/1000** (calls 4999/4999・wasm 17,367 B)。`build_cmp.sh <name> 1000 7 bitcast,intload,stackpair,assoc,concat`。emcc wall 0.3〜0.4 s。
- load (突合時): 0.53〜0.56 (4 vCPU)。

#### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数数不一致 8 件 (`FUN_180fd4f30()` 以外の callee の引数不足・arity) | Stereo の emcc が通らない | 親 #4911 のチェックリスト (本 PR で追記) |
| 型不一致 2 件 (1300・1888・間接呼出しの戻り値型) | 同上 | 親 #4911 のチェックリスト |
| Stereo の数値突合 (1000 trial) | 型の流用が正しいかは未検証 | 親 #4911 のチェックリスト |
| 生成 C の `int-conversion` 35 件 (既定条件のみ) | build_cmp 条件では無視される | 既存の KH-124 系 (#4871 の未解決表に記載) |
