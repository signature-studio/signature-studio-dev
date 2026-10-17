# REPORT_APPENDIX_3127 — Slayer_Engine.dll の export main (0x10007ca0) の native vs wasm 差分試験と KERNEL32 import の ia32 方針 (#3127 PLG-G2-26)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。 前提の harness は #1223 (`REPORT_APPENDIX_1223.md`)。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない。 本件は実行結果の突合と import の ABI モデル)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。
- 測定 commit: `23cf2c56a` (検証 HEAD。 main `71953e2e1` の取り込み後)。 旧測定 `dadf4ea18`・`6c5e25f46` の値は §4 に残す。 §6 に鮮度の範囲。

## 1. 結論と範囲

- export `main` (0x10007ca0) を入口に加え、 native と wasm の eax・OBJ 領域 128 B・heap 先頭 64 B を bit 単位で突合した。 一致件数とネガコンの結果は §4 が正本。
- **main の 64 行は KERNEL32 import を 1 回も呼ばない** (§4 の計数)。 main の行で確認できたのは eax=0 と OBJ 領域が変わらないことまで。 import モデルは、 この入口では検証されていない。
- **範囲は縮めた**: main の callback が **0 を返す経路のみ**。 callback が非 0 を返すと main は定数 `0x8298d8` を `f_10009f64` に渡す。 これは PE の外の host オブジェクトで、 0 埋めでは連結 list の null 参照になり native が SIGSEGV する (wasm は linear memory の 0 を読んで続行するため分岐する)。 この経路は未モデル化で、 子 [PLG-G2-38] #3917 に移した (§7)。
- issue の題名・本文の「38 種」は pass1 (`REPORT_APPENDIX_1098.md` §2) の数。 現在の lift (#2814 の pass2 後) は **41 件**。 いずれも KERNEL32.dll の import (PE の import directory に CRT の DLL は無い)。 §3 の表は 41 件すべて。

## 2. 入口と方式

| 項目 | 内容 |
|---|---|
| 入口 (diff_entry.py `ENTRIES`) | leaf 4 本 (#1223) + `0x10007ca0` export main (callback 0 経路。 KERNEL32 import は通らない) + `0x1000e1b7` (HeapAlloc・VirtualAlloc・HeapReAlloc を通る。 HeapFree は実行では通らない (静的には失敗分岐から到達。 §8)。 fs: を使わない) + `0x1000ea7d` (LeaveCriticalSection を 1 回。 stdcall の pop の確認) |
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
- fail-fast の 24 件は 448 行の実行で 1 件も呼ばれていない (両側とも rc=0)。 呼ばれると weak stub が abort し、 native は exit 9 で終わるため、 rc=0 がその証跡になる。 呼ばれた時点で止まる動作は設計 (weak stub・`n_missing`) による。 **実行での検証は未実施** (§7)。 静的な到達 (§8) では、 24 件のうち入口から到達するのは RaiseException の 1 件だけで、 それもゲート経路 (§8) のみ。
- stub の値はすべて Win32 の実挙動ではなく、 両側で揃えた仮定。 この突合が検証するのは「同じ仮定の下で lift と ia32 規約が一致する」ことだけ。

## 4. 実測 (測定 commit `23cf2c56a`・n=3。 前回の値は下の行)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_entry.py`) | `[compare] PASS: 448 / 448 件が bit 一致、不一致 0 件`・`[diff_entry] PASS`・exit 0 (3 回とも同一) |
| HEAD `23cf2c56a` の再測定 (n=3) | build: native 0.07 s・wasm emcc 7.88・8.03・7.98 s。 run: native 0.035・0.039・0.035 s・wasm (node) 0.058・0.054・0.060 s。 load1 (run 直前) 0.33・0.32・0.36。 `--nega`: 447 / 448・FAIL・exit 1 (OK)。 `--check`: PASS (exit 0) |
| 前回の HEAD `60b13d4b8` (n=3) | build: native 0.06 s・wasm emcc 7.71・7.91・7.89 s。 run: native 0.035・0.035・0.036 s・wasm (node) 0.062・0.057・0.055 s。 load1 0.71・0.63・0.60。 main 取り込み前の値 |
| 旧測定 `6c5e25f46` (n=3・main 取り込み前) の突合の再実行の出力 | build: native 0.05–0.06 s・wasm emcc 7.03–7.14 s。 run: native 0.031–0.035 s・wasm (node) 0.049–0.053 s。 load1 (run 直前) 0.16・0.23・0.35 |
| ネガティブコントロール (`--nega`) | `[compare] FAIL: 447 / 448 件が bit 一致、不一致 1 件`・`[nega] 1 bit 壊した出力を検出 (FAIL, exit 1)。 ネガコン OK`・exit 0 (方法は §5) |
| import 呼出し数 (wasm 側・計数用の一時ビルド・`6c5e25f46`) | HeapAlloc 64・HeapReAlloc 4・VirtualAlloc 64・LeaveCriticalSection 64・HeapFree 0。 合計 196 件 (`grep '^IMP ' stderr \| sort \| uniq -c` の実出力)。 `dadf4ea18` の計数と一致 |
| 計数の方式 | 一時コピー (`git archive`) の `rt32_glue.c` の `imp_*` 入口と `ott_call32` に stderr 出力 (`ROW`・`IMP`) を入れ、 行ごとに数えた。 計数なしのビルドと出力 (`wasm_out.txt`) は `cmp` で一致。 リポジトリにはコードを入れていない。 上の 4 名以外の import は 0 件 |
| 非自明性 | native 実行で OBJ 領域が変わった行 256 / 448 (leaf 4 本の 256 行。 main・heap・LeaveCS の行は OBJ を変えない)。 heap 先頭 64 B が非 0 なのは `1000e1b7` の 64 行のみ (毎行の reset で heap 先頭 4 KiB を 0 に戻すため、 他の入口の行に前行の残りは出ない)。 `1000e1b7` は `eax=108004f4` などの heap アドレスを返す |
| 戻り値の内訳 | `10007ca0` (main) は 64 行とも eax=0 (callback 0 経路)。 `1000ea7d` (LeaveCriticalSection) は 64 行とも eax=0。 `1000e1b7` は eax が heap のアドレス (`108004f4`・`108004e0`・…) |
| ビルド (min–max, n=3・旧測定 `6c5e25f46`) | native build 0.05–0.06 s、 wasm emcc 7.03–7.14 s |
| 実行 (min–max, n=3・旧測定 `6c5e25f46`) | native 0.031–0.035 s、 wasm (node) 0.049–0.053 s |
| load1 (run 直前、 n=3・旧測定 `6c5e25f46`) | 0.16・0.23・0.35 |
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

- 鮮度: 検証 HEAD `23cf2c56a` (main `71953e2e1` 取り込み後)。 ハーネスの範囲は `diff_entry.py`・`native_entry.c`・`rt32_glue.c`・`entry_wasm.mjs`・`lift_text.py`・`tools/ott/rt`・`tools/ott/lift`。
  - `git diff --numstat HEAD origin/main -- <同じ範囲>` は 0 行。 main の取り込みで、ハーネスの 4 ファイルに `c71986f10` (fs: TEB、#3905) の変更が入った。 その取り込み後の HEAD で §4 を測り直した。
  - 測定 commit `dadf4ea18` (付録の旧測定) から HEAD までの範囲の差分は `git diff --numstat dadf4ea18 HEAD -- <同じ範囲>` で挿入 193・削除 7。 内訳: `tools/ott/lift/x64c.py` +17/-1、 `tools/ott/rt/ott_x87.h` +142/-4 (main 由来の x87 の変更)、 `diff_entry.py` +1/-1、 `entry_wasm.mjs` +7/-1、 `native_entry.c` +21/-0、 `rt32_glue.c` +5/-0 (`c71986f10` の fs: TEB 由来)。
  - HEAD での突合は 448 / 448 PASS (§4)。
- 補足: `lift_text.py` の結果は `imports 41`・`functions 472` (pass2)。 pass1 の `38` は REPORT_APPENDIX_1098 §2 の値。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| export main の callback 非 0 経路 (`f_10009f64` → `f_1000a402`。 定数 `0x8298d8` は PE 外の host オブジェクト) | main の CRT 初期化・残りの import の経路が未突合。 0 埋めでは native が null 参照で SIGSEGV するため、 host オブジェクトのモデル化が要る | [PLG-G2-38] #3917 (open) |
| 突合で未通過の KERNEL32 import 13 件: 実装 8 件 (EnterCriticalSection・InitializeCriticalSection・GetLastError・SetLastError・TlsGetValue・TlsSetValue・HeapFree・VirtualFree) と stub 5 件 (GetCurrentThreadId・GetModuleFileNameA・GetStdHandle・LoadLibraryA・WriteFile) | 既存の入口は実行で 1 回も呼ばない (計数 0 件。 静的には `HeapFree` が `f_1000e1b7` の失敗分岐から到達するが、 実行では通らない。 他 12 件はゲート経路のみ。 §8)。 実行で未検証で、 方針表の値は両側の仮定が一致することしか示していない | [PLG-G2-39] #3960 (Refs・部分達成。 残りは §8 の経路に依存) |
| fail-fast の 24 import の実行検証 | 呼ばれた時の止まり方を実行で確認していない (448 行では 1 件も呼ばれない)。 静的にも 23 件は入口から到達しない | [PLG-G2-39] #3960 (Refs・部分達成) |
| `0x100106a5` (SEH: `mov eax, fs:[0]`・`mov fs:[0], esp`) を通る経路 (`0x1000d791` 等) | native に fs 基底が無く fs:[0] への書込みで落ちる。 wasm は `ott_teb_blk` (0 埋め)。 本入口からは外した | [PLG-G2-37] #3905 (fs: TEB を含む 8 関数) |
| 間接 call 先 (`ott_dispatch`)・sahf の AF・fs: TEB の 0 埋め | #3128 で測定済み (結果は `REPORT_APPENDIX_3128.md`)。 fs: TEB の native 未達は上の `0x100106a5` の行 (子 [PLG-G2-37] #3905) | 測定済み (#3128・CLOSED) |

## 8. 13 件・fail-fast 24 件の到達経路 (#3960・静的解析)

- 測定 commit: `23cf2c56a` (検証 HEAD。 `reach_import.py` の最後の変更は `6c5e25f46`)。 入力は lift 出力 `work/lift_text/ott_lifted.c` (472 関数・41 import)。
- 再現 (`23cf2c56a` で実測): `python3 tools/plugins/slayer_engine_ia32/reach_import.py` (表)・`--paths` (入口から各 import までの最短経路)・`--check` (期待集合との照合)。 `FL_WIN64_DIR` は `block22434_PE.bin` を含むディレクトリ。
- 表 (`reach_import.py` の実出力・41 件)。 「入口から静的到達」は diff_entry.py の 7 入口からの静的な到達、 「ゲート無し」は main の callback 0 経路 (ゲート `f_10009f64`・`f_10007f30` を通らない) での到達。

| import | 呼出し元の数 | 入口から静的到達 | ゲート無しで到達 |
|---|---|---|---|
| CloseHandle | 1 | No | No |
| DeleteCriticalSection | 1 | No | No |
| EnterCriticalSection | 4 | Yes | No |
| ExitProcess | 1 | No | No |
| FlushFileBuffers | 1 | No | No |
| GetACP | 1 | No | No |
| GetCPInfo | 2 | No | No |
| GetCurrentProcess | 1 | No | No |
| GetCurrentThreadId | 1 | Yes | No |
| GetFileType | 1 | No | No |
| GetLastError | 5 | Yes | No |
| GetModuleFileNameA | 1 | Yes | No |
| GetModuleHandleA | 1 | No | No |
| GetOEMCP | 1 | No | No |
| GetProcAddress | 1 | No | No |
| GetStartupInfoA | 1 | No | No |
| GetStdHandle | 2 | Yes | No |
| GetStringTypeA | 1 | No | No |
| GetStringTypeW | 2 | No | No |
| HeapAlloc | 4 | Yes | Yes |
| HeapFree | 5 | Yes | Yes (`f_1000e1b7` の失敗分岐。 実行 0 件) |
| HeapReAlloc | 1 | Yes | Yes |
| InitializeCriticalSection | 2 | Yes | No |
| InterlockedIncrement | 2 | No | No |
| LCMapStringA | 1 | No | No |
| LCMapStringW | 3 | No | No |
| LeaveCriticalSection | 4 | Yes | Yes |
| LoadLibraryA | 1 | Yes | No |
| MultiByteToWideChar | 4 | No | No |
| RaiseException | 1 | Yes | No |
| SetFilePointer | 1 | No | No |
| SetHandleCount | 1 | No | No |
| SetLastError | 1 | Yes | No |
| SetStdHandle | 1 | No | No |
| TerminateProcess | 1 | No | No |
| TlsGetValue | 1 | Yes | No |
| TlsSetValue | 1 | Yes | No |
| VirtualAlloc | 3 | Yes | Yes |
| VirtualFree | 3 | Yes | No |
| WideCharToMultiByte | 4 | No | No |
| WriteFile | 2 | Yes | No |

- 読み方: 入口から静的到達が Yes の 13 件 (実装 8・stub 5 の全件) のうち、 ゲート無しで到達するのは HeapFree の 1 件だけ。 fail-fast 24 件のうち入口から到達するのは RaiseException の 1 件 (ゲート経路のみ)。
- `--check` の実出力: `[reach_import] PASS: ゲート無しで静的到達 HeapAlloc,HeapFree,HeapReAlloc,LeaveCriticalSection,VirtualAlloc (実測 HeapAlloc,HeapReAlloc,LeaveCriticalSection,VirtualAlloc / 静的のみ HeapFree<-f_1000e1b7)`・exit 0。 期待集合は「実測の 4 件」と「静的のみの 1 件 (HeapFree、 直接の呼出し元が入口 `f_1000e1b7` であることも確かめる)」の和。
- `--paths` の実出力 (抜粋): `HeapFree 入口→ f_10007ca0 > f_10009f64 > f_1000a402 > f_1000a42e > f_1000deae > f_1000e1b7 | ゲート無し: f_1000e1b7`。 `f_1000e1b7` が `imp_HeapFree` を直接呼ぶ (`f_1000deae` は経由するが、 ゲート無しの入口は `f_1000e1b7` 自身)。
- `HeapFree` の分岐: `f_1000e1b7` は `VirtualAlloc` の戻り値を `edi` (`xor edi, edi` で 0) と比べ、 等しいとき (失敗扱い) にだけ `imp_HeapFree` を呼ぶ。 harness の `imp_VirtualAlloc` は常に bump で成功するため、 実行では 0 件 (計数の表)。 静的な上界では到達するが、 実行では通らない。
- 静的解析は分岐の条件を見ない上界。 「静的に到達しない」は呼ばれない根拠になるが、 「到達する」は実行で通るとは限らない。
- **ゲート**: main (`0x10007ca0`) の callback が非 0 を返す経路。 `f_10009f64`・`f_10007f30` を遮断すると、 main から到達する import は 0 件になる。 つまり main の **callback 0 経路は、 本節の 13 件も fail-fast 24 件 (RaiseException を含む) も通らない**。
- 13 件 (実装・stub) の経路 (`--paths`・`23cf2c56a` の実出力):
  - ゲート無しで入口から静的に到達するのは `HeapFree` の 1 件 (`f_1000e1b7` が直接呼ぶ。 上記の失敗分岐)。 実行では 0 件。
  - 残り 12 件は `--paths` で「ゲート無し: なし」。 入口からの最短経路はすべてゲート `f_10009f64` または `f_10007f30` を通る (例: EnterCriticalSection は `f_10007ca0 > f_10009f64 > f_1000a402 > f_1000a42e > f_1000ea1c`、 GetLastError は `f_10007ca0 > f_10007f30 > ... > f_1000d791`)。
  - 直接の呼出し元 `f_1000f41e` (GetModuleFileNameA・GetStdHandle・LoadLibraryA・WriteFile の経路) と `f_100112e9` (LoadLibraryA の経路) は、 ゲート経路で入口から到達する。 旧記述の「fs: を使わない候補として入口に足す」は、 ゲートを通る経路では実行できないので成り立たない。
- fail-fast 24 件: ゲート無しで静的に到達する件は 0 件。 RaiseException のみ、 ゲート経路 (`f_10007f30 > ... > f_1000adc4`) で到達する。 残り 23 件は、 どの入口からも到達しない。
- 結論: **ゲート無しで入口から実行できるのは `HeapFree` の失敗分岐 (実行では 0 件) だけで、 残りの 12 件と RaiseException は現在の入口では実行できない**。 入口から到達させるには、 ゲート経路の host オブジェクトのモデル化 (#3917) や fs: 経路の native 対応 (#3905) が要る。 本 run は、 その依存関係を静的解析で示すところまでで止める。

## 9. 文字列系 6 API の ia32 モデルの値と根拠 (#6039・受入条件 1・2)

- 入力: fl-win64 の `block22434_PE.bin` (IAT: WideCharToMultiByte `0x10013094`・MultiByteToWideChar `0x100130c0`・GetStringTypeA `0x100130c4`・GetStringTypeW `0x100130c8`・LCMapStringA `0x100130cc`・LCMapStringW `0x100130d0`。 #6039 停止報告の逆アセンブル実測)。
- 根拠の出典: (a) 定数値 = mingw-w64 `winnls.h` (PE 由来の flag・即値の出典は #6039 停止報告 https://github.com/signature-studio/signature-studio-dev/issues/6039#issuecomment-6230794110) (CP_ACP=0・MB_PRECOMPOSED=0x1・MB_ERR_INVALID_CHARS=0x8・WC_NO_BEST_FIT_CHARS=0x400・CT_CTYPE1=1・LCMAP_* 等)。 (b) 挙動 = `tools/shimx/src/str.c` の既存実装 (CP932 表は `tools/shimx/REPORT_SHX-T8.md` §15.3 の 9,604 セル一致)。 (c) 失敗時の LastError 名 = Win32 の標準定数 (ERROR_INVALID_PARAMETER=87・ERROR_INSUFFICIENT_BUFFER=122・ERROR_NO_UNICODE_TRANSLATION=1113)。 MSDN 本文との逐語照合は未了。
- **実機の実値は範囲外** (Linux では得られない)。 下の CP_ACP は製品判断 (PM #6039 の判断・R7) であり、実行環境での実測ではない。

### 9.1 CP_ACP の扱い (未確認)

| 項目 | 値 | 根拠 |
|---|---|---|
| PE 内の CP の読み先 | `[0x10068160]` (`.text` 内で読み出しのみ・書込み無し) | PE の逆アセンブル (#6039 停止報告) |
| モデルの CP_ACP | **932** (Shift_JIS 系) | PM 判断 (#6039 コメント・R7)。 実行時ロケールの実値は未確認 |
| 現行 shimx の既定 | 1252 (`str.c` の `g_acp = 1252`)。 `shimx_set_acp(932)` で切替 | `tools/shimx/src/str.c` 12 行 |
| 差分 | shimx の既定 (1252) と PM 判断 (932) は**一致しない**。 モデルは `shimx_set_acp(932)` 相当を既定にする必要がある | 同上 |
| `[0x10068160]` の初期値 | .bss の 0 (= CP_ACP 相当)。 932 既定との関係: 0 のままなら CP_ACP の解決は実行時の host 値に依る (本 REPORT の 932 既定はその host 値を 932 と置いた仮定) | #6039 停止報告 (https://github.com/signature-studio/signature-studio-dev/issues/6039#issuecomment-6230794110) |
| CP_UTF8 (65001) | `str.c` 233・259 行で直接処理 (MB→WC は `utf8_decode`、WC→MB は `shimx_utf16_to_utf8`)。 MB_ERR_INVALID_CHARS と WC_ERR_INVALID_CHARS を見る。 Windows 仕様との逐語照合は未了 | `tools/shimx/src/str.c` |

### 9.2 6 API の値モデル

| API | 呼出しの引数 (PE 内の即値・由来) | モデルの値 | 失敗時 (モデル) | 根拠 |
|---|---|---|---|---|
| MultiByteToWideChar | CP = `[0x10068160]` か複写。 flag = `[ebp+0x20]` 非 0 → 9 / 0 → 1、 または即値 1 | 932 は `mb2wc_932`。 flag の MB_ERR_INVALID_CHARS(0x8) 有りなら無効バイトで失敗、 無しなら U+30FB に置換 | 戻り 0・LastError 1113 (無効) / 122 (`cchWc` 不足) | `str.c` 226・162-183 行 |
| WideCharToMultiByte | CP = 同上。 flag = 即値 `0x220` (WC_COMPOSITECHECK 0x200 + WC_SEPCHARS 0x20) | 932 は `wc2mb_932`。 shimx は **WC_NO_BEST_FIT_CHARS(0x400) だけを見る**。 0x220 は往復一致の制限に効かない | 戻り 0・LastError 122 (`cbMb` 不足) / 87 (引数不正) | `str.c` 252・184-198 行 |
| GetStringTypeW | dwInfoType = 即値 1 (CT_CTYPE1) | CT_CTYPE1 は実装済み (C1_UPPER/LOWER/ALPHA/DIGIT/XDIGIT/SPACE/BLANK/CNTRL/PUNCT/DEFINED)。 CT_CTYPE2 (簡易: L/EN/WS) と CT_CTYPE3 (簡易: C3_ALPHA のみ) も実装済み (完全な分類ではない)。 その他の型は引数不正で FALSE | 引数不正で FALSE・LastError 87 | `str.c` 408-427 行 |
| GetStringTypeA | dwInfoType (PE 内の呼出し箇所は 3905 §1 の 5 関数に含まれる) | **shimx の str.c・proctable に実装が無い** (grep 範囲) | 未決 | `tools/shimx/src` の grep |
| LCMapStringW | flag は呼出し箇所ごとに異なる (未整理) | LCMAP_LOWERCASE(0x100)・LCMAP_UPPERCASE(0x200)。 LCMAP_SORTKEY(0x400) は **shimx 独自の擬似キー** (Windows の形式ではない) | 引数不正で 0・LastError 87 / 不足で 122 | `str.c` 377-402 行 |
| LCMapStringA | 同上 | **shimx に実装が無い** | 未決 | 同上 |

### 9.3 未了 (受入条件 1・2 の残り / 3・4)

- CP_ACP の 932 が FL Studio の実行で正しいかは**未確認** (PM 判断の既定値)。 実値が 0 (CP_ACP=ASCII 扱い) と分かった時点で §9.1 の行だけ差し替える。
- WideCharToMultiByte の flag 0x220 の意味 (WC_COMPOSITECHECK・WC_SEPCHARS) と、 shimx がそれを無視することの影響は、 MSDN との逐語照合が未了。
- GetStringTypeA・LCMapStringA は shimx に無く、 モデル化は #4356 の範囲 (受入条件 3・4 の入力範囲と合わせて決める)。
- LCMapStringW の呼出し flag の整理と、 SORTKEY の擬似キーを使う経路の有無は未確認。
- 受入条件 3 (5 関数の引数の由来と入力範囲) と 4 (#4356 への引渡し) は本節では未了。 §10 に一部を記載。

## 10. 5 関数の正体と引数の由来 (#6039・受入条件 3 の一部)

- 入力: `block22434_PE.bin` (sha256 先頭 `84b64c43`・REPORT と一致)。 `objdump -d -M intel` の PE 逆アセンブル (実行日: 本 run)。
- **5 関数のうち 3 つは関数の入口ではない**: `0x1001157b`・`0x100116db`・`0x1001178f` は呼出し元が 0 件で、`0x10013fa0`〜 の SEH scope table の `__except` 本体 (handler funclet)。 filter は `0x10011577`・`0x100116d7`・`0x1001178b` で、いずれも `push 1; pop eax; ret` (catch-all)。 例外時にだけ入るので、入力範囲の対象ではない。
- 実際の入口は `0x1001147e` と `0x100115c7` の 2 本 (呼出し元あり)。 呼出し元は下の 2 系統に大別できる (他の呼出し元は未追跡)。

| 入口 | 呼出し元 | 確認できた事実 | 未確認 |
|---|---|---|---|
| 0x1001147e | 0x1000f5cf・0x100111e2 | 0x1000f5cf は 1 or 2 を引数に積む (`eax`)。 その前に `[0x10027184]` の ctype 表 (bit 0x80) で 1 バイト目の lead byte 判定をしている | 0x100111e2 側の長さ・ポインタの由来 |
| 0x100115c7 | 0x1000f6f8・0x10011206・0x1001122e・0x10012529 | 0x1000f6f8 は最後に積む引数が `[0x10068150]` (callee の `[ebp+8]`)。 1000f6b6 で WCHAR の上位バイトを `[0x10027184]` で判定している | 他 3 件の引数 (`0x200` の即値を含む) の意味 |

- 呼出し元の lead byte 判定 (`[0x10027184]`・bit 0x80) は CP932 の 2 バイト系の前提と整合しそうだが、表の中身 (lead byte 集合) は未突合。
- `[0x10068150]` は 0x100115c7 の `[ebp+8]` に渡る値。 `0x10068160` (§9.1) とは別の変数で、初期化元は未追跡。
- 引数番号と意味 (Locale・flags・src・dst など) の対応づけは未確定。 入力範囲を決める前に、各 callee の `[ebp+N]` の使い方を全部読む必要がある。

### 10.1 受入条件 3 の残り (未了)

- 上表の未確認欄 (0x100111e2・0x10011206・0x1001122e・0x10012529 の引数) の由来。
- 引数番号と意味の対応づけ、ポインタ引数で SIGSEGV しない範囲 (§4 と同型の危険がある)。
- #6039 本文の「5 関数」の表記は、3 つが handler funclet である点に訂正が必要 (本 PR の範囲外。issue 本文の更新は PM 判断)。
