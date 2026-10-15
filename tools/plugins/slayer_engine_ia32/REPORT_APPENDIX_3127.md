# REPORT_APPENDIX_3127 — Slayer_Engine.dll の export main (0x10007ca0) の native vs wasm 差分試験と KERNEL32 import の ia32 方針 (#3127 PLG-G2-26)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。 前提の harness は #1223 (`REPORT_APPENDIX_1223.md`)。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない。 本件は実行結果の突合と import の ABI モデル)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。
- 測定 commit: `dadf4ea18` (main `1cda538f5` の取り込み後。 コードを変えた最後の commit)。 そこから HEAD (`1258391e1`、main `ba0f22fb0` の取り込み) までの測定範囲のコード差分は 0 行 (§6 の鮮度証跡)。

## 1. 結論と範囲

- export `main` (0x10007ca0) を入口に加え、 native と wasm の eax・OBJ 領域 128 B・heap 先頭 64 B を bit 単位で突合した。 一致件数とネガコンの結果は §4 が正本。
- **main の 64 行は KERNEL32 import を 1 回も呼ばない** (§4 の計数)。 main の行で確認できたのは eax=0 と OBJ 領域が変わらないことまで。 import モデルは、 この入口では検証されていない。
- **範囲は縮めた**: main の callback が **0 を返す経路のみ**。 callback が非 0 を返すと main は定数 `0x8298d8` を `f_10009f64` に渡す。 これは PE の外の host オブジェクトで、 0 埋めでは連結 list の null 参照になり native が SIGSEGV する (wasm は linear memory の 0 を読んで続行するため分岐する)。 この経路は未モデル化で、 子 [PLG-G2-38] #3917 に移した (§7)。
- issue の題名・本文の「38 種」は pass1 (`REPORT_APPENDIX_1098.md` §2) の数。 現在の lift (#2814 の pass2 後) は **41 件**。 いずれも KERNEL32.dll の import (PE の import directory に CRT の DLL は無い)。 §3 の表は 41 件すべて。

## 2. 入口と方式

| 項目 | 内容 |
|---|---|
| 入口 (diff_entry.py `ENTRIES`) | leaf 4 本 (#1223) + `0x10007ca0` export main (callback 0 経路。 KERNEL32 import は通らない) + `0x1000e1b7` (HeapAlloc・VirtualAlloc・HeapReAlloc を通る。 HeapFree は通らない。 fs: を使わない) + `0x1000ea7d` (LeaveCriticalSection を 1 回。 stdcall の pop の確認) |
| 行数 | 7 入口 × 64 = 448 行 (seed 1223) |
| main の callback | `MAIN_CB = [0x10001b10, 0x10001b70]` (cdecl・返り値 0 の ret のみ)。 stdcall の `ret N` は main の esp 規約と合わないため使わない |
| native import | `native_entry.c` が PE の import directory を読み、 IAT slot を ia32 model の stdcall stub に書き換える。 表に無い名前は `n_missing` (exit 9 = fail-fast) |
| wasm import | `rt32_glue.c` に ia32 規約 (引数は `esp+4〜`、 callee が pop) の `imp_*` を置く。 表に無い名前は x64c の weak stub (`ott_missing_import` で abort = fail-fast) |
| 規約の衝突 | `rt/ott_cpu.c` の `imp_HeapAlloc`・`imp_HeapFree`・`imp_GetLastError`・`imp_SetLastError`・`imp_EnterCriticalSection`・`imp_LeaveCriticalSection` は x64 規約 (`R[RCX]`・`IMP_RET` = +8)。 ia32 では誤る。 wasm の link を `rt32_glue.c` 先・`--allow-multiple-definition` にして先勝ちで上書きする (`ott_cpu.c` は変更しない) |
| 共有の状態 | 毎行 reset: heap 先頭 4 KiB (0x10800000〜、 0 埋め)・bump の先頭 0x10800000 (bump・8 B 境界・ヘッダ 8 B に size)、 host 領域 0x00828000〜0x00838000 (0 埋め)、 LastError・TLS 64 slot |
| 出力 | `idx va eax mem(OBJ 128 B) heap(64 B)`。 native と wasm の書式を揃えた |
| PE ヘッダ | `image.bin` に SizeOfHeaders 分のヘッダを敷く (import directory を native が読むため。 #3127 で追加) |

## 3. KERNEL32 import の方針表 (41 件・ lift = `work/lift_text/lift_meta.json` の `imports_used`)

区分: **実装** = 状態を持つ ia32 モデル (native と wasm が同じ値)。 **stub** = 固定値を返す (両側同じ)。 **fail-fast** = 両側とも呼ばれた時点で止める (wasm: weak stub の abort / native: exit 9)。 「main 静的」は `x64c --closure 999` を main 1 本から辿った closure (79 関数・18 import) に含まれるか。

| import | 区分 | モデルの中身・理由 | main 静的 |
|---|---|---|---|
| CloseHandle | fail-fast | 本入口は呼ばない | |
| DeleteCriticalSection | fail-fast | 本入口は呼ばない | |
| EnterCriticalSection | 実装 | 単一スレッド前提で no-op (eax=0) | ○ |
| ExitProcess | fail-fast | 戻らない API。 本入口は呼ばない | |
| FlushFileBuffers | fail-fast | 本入口は呼ばない | |
| GetACP | fail-fast | 本入口は呼ばない | |
| GetCPInfo | fail-fast | 本入口は呼ばない | |
| GetCurrentProcess | fail-fast | 本入口は呼ばない | |
| GetCurrentThreadId | stub | 定数 0x1000 | ○ |
| GetFileType | fail-fast | 本入口は呼ばない | |
| GetLastError | 実装 | 状態 g_lasterr (毎行 0) | ○ |
| GetModuleFileNameA | stub | 0 (失敗) | ○ |
| GetModuleHandleA | fail-fast | 本入口は呼ばない | |
| GetOEMCP | fail-fast | 本入口は呼ばない | |
| GetProcAddress | fail-fast | 本入口は呼ばない | |
| GetStartupInfoA | fail-fast | 本入口は呼ばない | |
| GetStdHandle | stub | 0x00020000 \| (n & 0xffff) | ○ |
| GetStringTypeA | fail-fast | 本入口は呼ばない | |
| GetStringTypeW | fail-fast | 本入口は呼ばない | |
| HeapAlloc | 実装 | bump (ハンドル無視・常に 0 埋め・8 B 境界)。 ヘッダ 8 B に size | ○ |
| HeapFree | 実装 | no-op (戻り 1) | ○ |
| HeapReAlloc | 実装 | 新規 alloc + 旧 size 分の copy (旧 size はヘッダから) | ○ |
| InitializeCriticalSection | 実装 | no-op (eax=0) | ○ |
| InterlockedIncrement | fail-fast | 本入口は呼ばない | |
| LCMapStringA | fail-fast | 本入口は呼ばない | |
| LCMapStringW | fail-fast | 本入口は呼ばない | |
| LeaveCriticalSection | 実装 | no-op (eax=0)。 `1000ea7d` で通る | ○ |
| LoadLibraryA | stub | 0 (見つからない) | ○ |
| MultiByteToWideChar | fail-fast | 本入口は呼ばない | |
| RaiseException | fail-fast | 例外は止める (native と同じ fail-fast)。 main 静的に含まれるが callback 0 経路では呼ばれない | ○ |
| SetFilePointer | fail-fast | 本入口は呼ばない | |
| SetHandleCount | fail-fast | 本入口は呼ばない | |
| SetLastError | 実装 | 状態 g_lasterr | ○ |
| SetStdHandle | fail-fast | 本入口は呼ばない | |
| TerminateProcess | fail-fast | 本入口は呼ばない | |
| TlsGetValue | 実装 | 64 slot の表 (index & 63) | ○ |
| TlsSetValue | 実装 | 同上・戻り 1 | ○ |
| VirtualAlloc | 実装 | 4 KiB 境界の bump・0 埋め | ○ |
| VirtualFree | 実装 | no-op (戻り 1) | ○ |
| WideCharToMultiByte | fail-fast | 本入口は呼ばない | |
| WriteFile | stub | 出力はしない。 `*lpNumberOfBytesWritten = nBytes` (戻り 1) | ○ |

- 集計: 実装 12 / stub 5 / fail-fast 24 (計 41)。 main 静的 18 件のうち fail-fast は RaiseException の 1 件のみ。
- **突合で呼ばれたのは 4 件だけ**: 実装の HeapAlloc・VirtualAlloc・HeapReAlloc・LeaveCriticalSection (§4 の計数)。 残りの実装 8 件 (EnterCriticalSection・InitializeCriticalSection・GetLastError・SetLastError・TlsGetValue・TlsSetValue・HeapFree・VirtualFree) と stub 5 件は、 突合で 1 回も呼ばれていない (未通過。 §7)。
- fail-fast の 24 件は 448 行の実行で 1 件も呼ばれていない (両側とも rc=0)。 呼ばれると weak stub が abort し、 native は exit 9 で終わるため、 rc=0 がその証跡になる。 呼ばれた時点で止まる動作は設計 (weak stub・`n_missing`) による。 **実行での検証は未実施** (§7)。
- stub の値はすべて Win32 の実挙動ではなく、 両側で揃えた仮定。 この突合が検証するのは「同じ仮定の下で lift と ia32 規約が一致する」ことだけ。

## 4. 実測 (測定 commit `dadf4ea18`・n=3)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_entry.py`) | `[compare] PASS: 448 / 448 件が bit 一致、不一致 0 件`・`[diff_entry] PASS`・exit 0 (3 回とも同一) |
| ネガティブコントロール (`--nega`) | `[compare] FAIL: 447 / 448 件が bit 一致、不一致 1 件`・`[nega] 1 bit 壊した出力を検出 (FAIL, exit 1)。 ネガコン OK`・exit 0 (方法は §5) |
| import 呼出し数 (wasm 側・計数用の一時ビルド) | `1000e1b7`: HeapAlloc 64・VirtualAlloc 64・HeapReAlloc 4・HeapFree 0 (64 行で計 132 件)。 `1000ea7d`: LeaveCriticalSection 64。 `10007ca0` (main): 0 件 (64 行とも)。 leaf 4 本: 0 件。 合計 196 件。 計数は `dadf4ea18` で再現 (一致)。 HEAD `1258391e1` では再計数していない (測定範囲のコード差分 0 行) |
| 計数の方式 | 一時コピー (`git archive`) の `rt32_glue.c` の `imp_*` 入口と `ott_call32` に stderr 出力 (`ROW`・`IMP`) を入れ、 行ごとに数えた。 計数なしのビルドと出力 (`wasm_out.txt`) は `cmp` で一致。 リポジトリにはコードを入れていない。 上の 4 名以外の import は 0 件 |
| 非自明性 | native 実行で OBJ 領域が変わった行 256 / 448 (leaf 4 本の 256 行。 main・heap・LeaveCS の行は OBJ を変えない)。 heap 先頭 64 B が非 0 なのは `1000e1b7` の 64 行のみ (毎行の reset で heap 先頭 4 KiB を 0 に戻すため、 他の入口の行に前行の残りは出ない)。 `1000e1b7` は `eax=108004f4` などの heap アドレスを返す |
| 戻り値の内訳 | `10007ca0` (main) は 64 行とも eax=0 (callback 0 経路)。 `1000ea7d` (LeaveCriticalSection) は 64 行とも eax=0。 `1000e1b7` は eax が heap のアドレス (`108004f4`・`108004e0`・…) |
| ビルド (min–max, n=3) | native build 0.04–0.20 s (0.20 s は 1 回目)、 wasm emcc 3.12–11.83 s (11.83 s は 1 回目。 2 回目以降は 3.12–3.14 s) |
| 実行 (min–max, n=3) | native 0.024–0.026 s、 wasm (node) 0.041–0.073 s (0.073 s は 1 回目) |
| load1 (run 直前、 n=3) | 1.90・1.91・1.91 |
| 件数 | 入口 7 本 × 64 = 448 行 (期待値と一致) |

## 5. ネガティブコントロール (測定 commit `dadf4ea18`)

- `python3 diff_entry.py --nega`: wasm 出力の 1 行目 (leaf `10001b40`) の eax の 1 bit を壊し、 判定器に通す。 FAIL を検出して exit 1 になれば OK。 数値は §4。
- ネガコンは leaf の 1 行で行う (既存の仕組みのまま)。 import を通る行でも同じ判定器を通るため、 判定器の効き自体は変わらない。

## 6. 再現手順と鮮度の証跡

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64          # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst (--wildcards '*block22434_PE.bin' で可)
export EMSDK=$RUNNER_TEMP/emsdk PATH=$RUNNER_TEMP/emsdk:$RUNNER_TEMP/emsdk/upstream/emscripten:$PATH   # tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst (emcc 6.0.12)
python3 tools/plugins/slayer_engine_ia32/lift_text.py     # work/lift_text/ott_lifted.c (472 関数・41 import)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py    # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py --nega
```

- 鮮度: 測定 commit は `dadf4ea18` (コードを変えた最後の commit)。 そこから HEAD `1258391e1` までのコード差分は `git diff dadf4ea18 HEAD -- tools/plugins/slayer_engine_ia32/{diff_entry.py,native_entry.c,rt32_glue.c,entry_wasm.mjs,lift_text.py} tools/ott/rt tools/ott/lift` の出力が 0 行 (PR 本文の『検証 HEAD』欄が正)。
- 補足: `lift_text.py` の結果は `imports 41`・`functions 472` (pass2)。 pass1 の `38` は REPORT_APPENDIX_1098 §2 の値。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| export main の callback 非 0 経路 (`f_10009f64` → `f_1000a402`。 定数 `0x8298d8` は PE 外の host オブジェクト) | main の CRT 初期化・残りの import の経路が未突合。 0 埋めでは native が null 参照で SIGSEGV するため、 host オブジェクトのモデル化が要る | [PLG-G2-38] #3917 (本 PR で起票) |
| 突合で未通過の KERNEL32 import 13 件: 実装 8 件 (EnterCriticalSection・InitializeCriticalSection・GetLastError・SetLastError・TlsGetValue・TlsSetValue・HeapFree・VirtualFree) と stub 5 件 (GetCurrentThreadId・GetModuleFileNameA・GetStdHandle・LoadLibraryA・WriteFile) | 既存の入口は 1 回も呼ばない。 実行で未検証で、 方針表の値は両側の仮定が一致することしか示していない | [PLG-G2-39] #3960 (本 PR で起票) |
| fail-fast の 24 import の実行検証 | 呼ばれた時の止まり方を実行で確認していない (448 行では 1 件も呼ばれない) | [PLG-G2-39] #3960 (本 PR で起票) |
| `0x100106a5` (SEH: `mov eax, fs:[0]`・`mov fs:[0], esp`) を通る経路 (`0x1000d791` 等) | native に fs 基底が無く fs:[0] への書込みで落ちる。 wasm は `ott_teb_blk` (0 埋め)。 本入口からは外した | [PLG-G2-37] #3905 (fs: TEB を含む 8 関数) |
| 間接 call 先 (`ott_dispatch`)・sahf の AF・fs: TEB の 0 埋め | #3128 で測定済み (結果は `REPORT_APPENDIX_3128.md`)。 fs: TEB の native 未達は上の `0x100106a5` の行 (子 [PLG-G2-37] #3905) | 測定済み (#3128・CLOSED) |
