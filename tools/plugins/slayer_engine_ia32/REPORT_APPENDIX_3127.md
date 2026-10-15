# REPORT_APPENDIX_3127 — Slayer_Engine.dll の export main (0x10007ca0) の native vs wasm 差分試験と KERNEL32 import の ia32 方針 (#3127 PLG-G2-26)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。 前提の harness は #1223 (`REPORT_APPENDIX_1223.md`)。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない。 本件は実行結果の突合と import の ABI モデル)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。
- 測定 commit: `c0898cc7a` (コードを変えた最後の commit)。 そこから HEAD までのコード差分は本付録と REPORT の文書のみ (§6 の鮮度証跡)。

## 1. 結論と範囲

- export `main` (0x10007ca0) を入口に加え、 native と wasm の eax・OBJ 領域 128 B・heap 先頭 64 B を bit 単位で突合した (448 / 448 一致)。 ネガコン (wasm 出力の 1 bit を壊す) は 447 / 448 で FAIL を検出。
- **範囲は縮めた**: main の callback が **0 を返す経路のみ**。 callback が非 0 を返すと main は定数 `0x8298d8` を `f_10009f64` に渡す。 これは PE の外の host オブジェクトで、 0 埋めでは連結 list の null 参照になり native が SIGSEGV する (wasm は linear memory の 0 を読んで続行するため分岐する)。 この経路は未モデル化で、 子 [PLG-G2-38] に移した (§7)。
- issue 本文の「CRT import 38 種」は pass1 (`REPORT_APPENDIX_1098.md` §2) の数。 現在の lift (#2814 の pass2 後) は **41 件**。 いずれも KERNEL32.dll の import (PE の import directory に CRT の DLL は無い)。 §3 の表は 41 件すべて。

## 2. 入口と方式

| 項目 | 内容 |
|---|---|
| 入口 (diff_entry.py `ENTRIES`) | leaf 4 本 (#1223) + `0x10007ca0` export main (callback 0 経路) + `0x1000e1b7` (HeapAlloc/VirtualAlloc/HeapFree を通る。 fs: を使わない) + `0x1000ea7d` (LeaveCriticalSection を 1 回。 stdcall の pop の確認) |
| 行数 | 7 入口 × 64 = 448 行 (seed 1223) |
| main の callback | `MAIN_CB = [0x10001b10, 0x10001b70]` (cdecl・返り値 0 の ret のみ)。 stdcall の `ret N` は main の esp 規約と合わないため使わない |
| native import | `native_entry.c` が PE の import directory を読み、 IAT slot を ia32 model の stdcall stub に書き換える。 表に無い名前は `n_missing` (exit 9 = fail-fast) |
| wasm import | `rt32_glue.c` に ia32 規約 (引数は `esp+4〜`、 callee が pop) の `imp_*` を置く。 表に無い名前は x64c の weak stub (`ott_missing_import` で abort = fail-fast) |
| 規約の衝突 | `rt/ott_cpu.c` の `imp_HeapAlloc`・`imp_HeapFree`・`imp_GetLastError`・`imp_SetLastError`・`imp_EnterCriticalSection`・`imp_LeaveCriticalSection` は x64 規約 (`R[RCX]`・`IMP_RET` = +8)。 ia32 では誤る。 wasm の link を `rt32_glue.c` 先・`--allow-multiple-definition` にして先勝ちで上書きする (`ott_cpu.c` は変更しない) |
| 共有の状態 | 毎行 reset: heap 先頭 0x10800000 (bump・8 B 境界・ヘッダ 8 B に size)、 host 領域 0x00828000〜0x00838000 (0 埋め)、 LastError・TLS 64 slot |
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
- fail-fast の 24 件は、 本付録の入口では呼ばれない。 呼ばれた時点で止まることは設計 (weak stub・`n_missing`) による。 **実行での検証は未実施**。
- stub の値はすべて Win32 の実挙動ではなく、 両側で揃えた仮定。 この突合が検証するのは「同じ仮定の下で lift と ia32 規約が一致する」ことだけ。

## 4. 実測 (測定 commit `c0898cc7a`・n=3)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_entry.py`) | `[compare] PASS: 448 / 448 件が bit 一致、不一致 0 件`・`[diff_entry] PASS`・exit 0 (3 回とも同一) |
| 非自明性 | native 実行で OBJ 領域が変わった行 256 / 448 (leaf 4 本の 256 行。 main・heap・LeaveCS の行は OBJ を変えない)。 heap 先頭 64 B は main 以外の行で非 0 (例: `1000e1b7` は `eax=10800008` を返し、 heap に書かれる) |
| 戻り値の内訳 | `10007ca0` (main) は全 64 行で eax=0 (callback 0 経路)。 `1000e1b7` は eax が heap のアドレス (`10800008`・`1080001c`・…) |
| ビルド (min–max) | native build 0.06 s、 wasm emcc 5.75–5.77 s |
| 実行 (min–max) | native 0.033 s、 wasm (node) 0.056–0.060 s |
| load1 (run 直前、 3 回) | 0.31・0.41・0.46 |
| 件数 | 入口 7 本 × 64 = 448 行 (期待値と一致) |

## 5. ネガティブコントロール (測定 commit `c0898cc7a`)

- `python3 diff_entry.py --nega`: wasm 出力の 1 行目 (leaf `10001b40`) の eax の 1 bit を壊す → `[compare] FAIL: 447 / 448 件が bit 一致、不一致 1 件` → `[nega] 1 bit 壊した出力を検出 (FAIL, exit 1)。 ネガコン OK`・exit 0。
- ネガコンは leaf の 1 行で行う (既存の仕組みのまま)。 import を通る行でも同じ判定器を通るため、 判定器の効き自体は変わらない。

## 6. 再現手順と鮮度の証跡

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64          # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst (--wildcards '*block22434_PE.bin' で可)
export EMSDK=$RUNNER_TEMP/emsdk PATH=$RUNNER_TEMP/emsdk:$RUNNER_TEMP/emsdk/upstream/emscripten:$PATH   # tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst (emcc 6.0.12)
python3 tools/plugins/slayer_engine_ia32/lift_text.py     # work/lift_text/ott_lifted.c (472 関数・41 import)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py    # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py --nega
```

- 鮮度: 測定後に変えたのは本付録と REPORT の文書のみ。 `git diff c0898cc7a HEAD -- tools/plugins/slayer_engine_ia32 tools/ott/rt tools/ott/lift` の出力は 0 行 (PR 本文の『検証 HEAD』欄が正)。
- 補足: `lift_text.py` の結果は `imports 41`・`functions 472` (pass2)。 pass1 の `38` は REPORT_APPENDIX_1098 §2 の値。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| export main の callback 非 0 経路 (`f_10009f64` → `f_1000a402`。 定数 `0x8298d8` は PE 外の host オブジェクト) | main の CRT 初期化・残りの import の経路が未突合。 0 埋めでは native が null 参照で SIGSEGV するため、 host オブジェクトのモデル化が要る | [PLG-G2-38] 子 (本 PR で起票) |
| `0x100106a5` (SEH: `mov eax, fs:[0]`・`mov fs:[0], esp`) を通る経路 (`0x1000d791` 等) | native に fs 基底が無く fs:[0] への書込みで落ちる。 wasm は `ott_teb_blk` (0 埋め)。 本入口からは外した | [PLG-G2-37] #3905 (fs: TEB を含む 8 関数) |
| fail-fast の 24 import の実行検証 | 呼ばれた時の止まり方を実行で確認していない | 本 PR の範囲外 (入口が要求した時に実装・検証する) |
| 間接 call 先 (`ott_dispatch`)・sahf の AF・fs: TEB の 0 埋め | #1223 から継続 (leaf 外の実行時の論点) | [PLG-G2-27] #3128 |
