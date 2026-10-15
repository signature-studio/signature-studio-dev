# REPORT_APPENDIX_3849 — KH-80 (#3849): Delay の型不一致 残件 (Win API 戻り値)

`REPORT_APPENDIX_3801.md` §10-7x の残件 119 件のうち、本 issue が対象とした 32 件の分類と処理。

## 結論

- Win API 戻り値 9 件 (`HeapAlloc`・`GetCurrentProcess`・`RtlLookupFunctionEntry`・`RtlPcToFileHeader`) は、`ghidra_shim.h` の fail-fast macro の戻り型を `void *` から `longlong` に直して解消した。abort の挙動と引数の評価抑止は変えていない。
- 型不一致は 119 → **110** (emcc error 行 374 → 365)。Gain/Haas/Gate の `.o` は 3 本とも変更前と `cmp` 一致。
- 残り 23 件 (関数ポインタ 9・void 戻り値 7・BINOP 7) は未処理。本 run では機械語の確認まで行わず、子 issue に分けた (下の表)。
- 受入条件「Delay の型不一致 0 件」は未達。

## 測定

- 測定 commit: 本 PR の HEAD (`ghidra_shim.h` の型変更を含む commit)。
- 環境: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (zip sha256 `ddac49f9…d2db` 一致)・JDK 21 (temurin-21)。すべて repo 外 (`$RUNNER_TEMP/kh`)。n=1。
- 実行: `FX=bitcast,intload,stackpair,assoc,concat,gtype bash tools/targets/kilohearts/ghidra_route/gtype_census.sh $RUNNER_TEMP/kh`・decompile 151/151 OK・実行時間 real 47.9 s (census 全体。Ghidra の解析を含む。load は未記録)。

| 測定 | 型不一致 | 合計 (emcc error 行) |
|---|---|---|
| 変更前 (`origin/main` 7cf51a6bd・gtype 単独) | 119 | 374 |
| 変更後 (本 PR・gtype 単独) | **110** | 365 |

| 項目 | 変更前 | 変更後 |
|---|---|---|
| gain.o | 1,435 B | 1,435 B (`cmp` 一致) |
| haas.o | 3,217 B | 3,217 B (`cmp` 一致) |
| gate.o | 3,756 B | 3,756 B (`cmp` 一致) |

## 処理した規則 (Win API 戻り値・型のみ)

| 対象 | 変更前 | 変更後 | 根拠 |
|---|---|---|---|
| `HeapAlloc` (delay 3524・5298・5832 の 3 件) | `(void *)` | `(longlong)` | 呼出元が `lVar2 = HeapAlloc(...)` で整数へ代入 |
| `GetCurrentProcess` (delay 2575・4706・7199 の 3 件) | `(void *)` | `(longlong)` | `uVar2`・`uVar1` (整数) へ代入 |
| `RtlLookupFunctionEntry` (2437・7259 の 2 件) | `(void *)` | `(longlong)` | `lVar3`・`lVar2` へ代入 |
| `RtlPcToFileHeader` (2307 の 1 件) | `(void *)` | `(longlong)` | `lStack_38 = RtlPcToFileHeader(...)` |

- 戻り値の幅は x64 の `rax` (64bit) に合わせた。`HeapAlloc` の戻り値は実機で 64bit の値として呼出元の変数へ入る。
- 戻り値の値そのものは意味を実装しない。到達時は `kh_api_fail()` が abort する。
- 機械語の確認は本 run では未実施 (規則の型幅は呼出元 C の代入先の型による。命令での突合は子 issue で行う)。

## 未処理の 23 件と起票先

| 分類 | 件数 | 状態 | 起票先 |
|---|---|---|---|
| P1 関数ポインタ global `(*_DAT_1813a1d40)(...)` | 9 | 未処理。`_DAT_1813a1d40` の PE 値は画像内の番地 (0x1813e3850) で、実行時に設定される可能性がある。型と意味は未検証 | 子 issue (下) |
| P2 void 戻り値の値扱い (`FUN_180f87cac`・`FUN_180fc4590` 等) | 7 | 未処理。戻り値は呼出元の機械語 (`rax`) で確認が必要 | 子 issue (下) |
| P4 BINOP 残件 (`(uint)fVar26 ^ _DAT_1813d1a80` 等) | 7 | 未処理。`(uint)` が float のビット再解釈か数値変換かを機械語で確認。`#3836` [KH-71] と重なる行がある | 子 issue (下) |

## 再現

`bash tools/targets/kilohearts/ghidra_route/gtype_census.sh $RUNNER_TEMP/kh` (`$RUNNER_TEMP/kh` は素材を展開したディレクトリ)。`git diff 7cf51a6bd HEAD -- tools/targets/kilohearts/ghidra_route` の出力は `ghidra_shim.h` の 4 行のみ。
