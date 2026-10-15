# tools/shared/elastique REPORT — élastique 2.2.15 (win `elastique_x64.dll`) の KERNEL32・WS2_32 IAT の呼出元と host 置換方針 (T-SH-41 受入 4 / #2614)

> 正本: この文書 (#2614・T-SH-41 の受入 4)。方式は `docs/DECISIONS.md` D20。前段の入口と dispatch の実測は `REPORT.md` (#2613・T-SH-40) と `REPORT_152.md` (#152・T-SH-10)。対応表は `data/iat_policy.csv` (79 行・機械生成)。

日付: 2026-10-15 / 担当: #2614 (run 1) / 測定 commit: `870f4855` (`scripts/elastique_iat.py` と `data/iat_policy.csv`。以後 scripts・data の変更なし。`git diff 870f4855 HEAD -- tools/shared/elastique/scripts tools/shared/elastique/data` の出力は 0 行)

再現:

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
mkdir -p tools/shared/work/win && cp "$RUNNER_TEMP/fl-win64/extracted/block24357_PE.bin" tools/shared/work/win/elastique_x64.dll
python3 tools/shared/elastique/scripts/elastique_iat.py tools/shared/work/win/elastique_x64.dll
```

依存は capstone のみ (PE 解析は `scripts/elastique_facts.py` の関数を流用)。出力は `tools/shared/work/elastique/iat_callers.json` (gitignore) と `data/iat_policy.csv` (commit 対象)。

## 0. 結論

| 項目 | 結論 (実測) |
|---|---|
| 受入 4 (KERNEL32 77 件の置換方針) | 達成。79 IAT (KERNEL32 77・WS2_32 2) を分類 A〜J の 10 区分に置き、API ごとの wasm 側の写像・根拠・呼出元数を `data/iat_policy.csv` に書いた (§3・§4) |
| 呼出元 | pdata 内の直接参照 175 + pdata 外の `jmp [IAT]` thunk 経由 12 = 187 (バイト走査と一致)。thunk を持つ API は 8 件 |
| export からの到達 (下界) | 15 export から直接 call/jmp で 193 関数に到達。79 API のうち 17 件が到達する。残る 62 件は間接経路 (dispatch 表など) の先にある可能性があり、到達 0 は「未使用」を意味しない (§3.3) |
| 判断が要る項目 | 6 件 (§5)。特に (1) `HeapReAlloc` の 1 箇所が flags 0x10 (同位置でのみ伸長)、(2) `IsProcessorFeaturePresent` の 5 箇所が定数 0x17 を渡し戻り値が分岐を決める、(4) `RaiseException` が C++ 例外の標準コードを送出する経路を持つ |
| 受入 1〜3 | 未着手。子 [T-SH-67] #3332 (lift と side module) と [T-SH-68] #3333 (export 差分・除外フラグ) へ移した (§6) |

## 1. 対象・素材・測定方法

- 対象: `fl-win64` の `extracted/block24357_PE.bin` (`elastique_x64.dll`・4,997,632 B・PE32+)。`.text` の pdata 関数は **4,556 件** (スクリプトの出力 `pdata functions in .text: 4556`・issue 本文と一致)。
- import: KERNEL32.dll 77 名・WS2_32.dll 2 名 (序数 8 = `htonl`・序数 14 = `ntohl`。Winsock の序数表による)。IAT 枠の VA は `FirstThunk` + 8 × i。
- 測定:
  1. `.pdata` の各関数を capstone で逆アセンブルし、RIP 相対メモリ参照が IAT 枠を指すもの (call・jmp・データ参照) を数える (`refs_pdata`)。
  2. `.text`・`IPPCODE` の全バイトを走査し、`ff 15`・`ff 25` の rel32 が IAT 枠を指すものを数える (`refs_bytes`)。`48 ff 25` (REX.W) は opcode の位置が 1 byte ずれるため、直前が 0x40〜0x4F なら接頭辞の位置を採る。
  3. pdata 外の `jmp [IAT]` (thunk) の位置を (2) から求める。pdata 内の直接 call/jmp で thunk を指すものは、その API の呼出元に数える (`thunks`・`callers_pdata`)。
  4. export 15 関数から直接 call/jmp を辿る (下界。間接分岐は辿らない)。`reached_from_exports` は、その API の参照元 (または thunk) を含む到達済み関数の数。
- 整合: (2) の 187 = (1) の 175 + thunk 12。取りこぼしは 0 (REX による位置ずれは (2) で補正済み)。

## 2. 再現・検証

- 決定性: 測定 run を 3 回 (stdout・`iat_policy.csv`・`iat_callers.json`) し、すべて `cmp` 一致。
- 実行時間 (real・n=3): 9.95 s / 10.03 s / 10.24 s。load average (1 分) は 0.52 (測定時)。
- 陰性対照: `HeapFree` の呼出し 1 箇所 (VA 0x1802d8b4e・`call [IAT]` 6 B) を NOP にした DLL のコピー (リポジトリ外・`$RUNNER_TEMP/neg/`) で再実行 → pdata 直接参照 175 → 174、全体 187 → 186、`HeapFree` の pdata 参照 1 → 0、到達 1 → 0。検出器が 1 件の欠落を検出することを確認した。
- 素材は `fl-win64` のみ (`oc_artifacts` の追加なし)。

## 3. 結果

### 3.1 分類ごとの件数 (79 API)

| 分類 | API 数 | pdata 直接参照 | thunk 参照 | export 到達の API 数 |
|---|---|---|---|---|
| A メモリ | 6 | 9 | 0 | 2 (HeapAlloc・HeapFree) |
| B 同期・イベント (単一スレッド) | 10 | 20 | 7 | 0 |
| C TLS/FLS (インスタンス内の表) | 8 | 4 | 4 | 2 (FlsGetValue・FlsSetValue) |
| D 例外・unwind (SEH 無し) | 9 | 31 | 0 | 8 |
| E 動的ロード (常に失敗) | 6 | 18 | 0 | 0 |
| F ファイル・コンソール (host 無し) | 14 | 26 | 0 | 0 |
| G プロセス・エラー状態 | 13 | 47 | 0 | 4 |
| H 時刻・性能カウンタ | 2 | 2 | 0 | 0 |
| I CPU・コードページ・文字列 | 9 | 13 | 1 | 1 (IsProcessorFeaturePresent) |
| J バイトオーダ変換 (WS2_32) | 2 | 5 | 0 | 0 |
| 計 | 79 | 175 | 12 | 17 |

### 3.2 呼出元の偏り

- 呼出元が多い API: GetLastError (直接参照 24・呼出元関数 23)・SetLastError (6)・DeleteCriticalSection (6)・WriteFile (6)・IsProcessorFeaturePresent (5)・GetProcAddress (5)・FlsGetValue/FlsSetValue (thunk 経由で 5 関数)。
- 呼出元が 1 関数だけの API は 43 件 (`callers_pdata = 1`)。CSV の `callers_pdata` 列で確認できる。

### 3.3 export からの到達 (下界)

- 15 export から直接 call/jmp で到達する関数は 193。このうち 17 API の参照元を含む (GetLastError 5・SetLastError 4・IsProcessorFeaturePresent 3 ほか。CSV の `reached_from_exports` 列)。
- 62 API は到達 0。これは未使用の証明ではない。REPORT_152 §2 のとおり、export の先の分岐は dispatch 表 (`jmp [表 + 索引*8]`) を経由し、その 1 段目の飛び先 186 個は直接の call 経路に載らない。間接経路の先で呼ばれる可能性は残る (未確認)。

## 4. 置換方針 (受入 4)

全分類に共通する原則 (提案):

- 単一インスタンス・単一スレッド。`CreateThread` の IAT 枠は無い (スレッド生成の経路は無い)。
- 写像できない経路は **trap (fail-closed)** とし、黙って値を返さない。値を返す写像には §5 の確認事項を付す。
- 写像の正しさは子 [T-SH-68] #3333 の差分試験で確認する。本 REPORT は静的な方針だけを書く。

| 分類 | API と wasm 側の写像 (提案) |
|---|---|
| A メモリ | HeapAlloc → malloc (flags の 8 = HEAP_ZERO_MEMORY は calloc)・HeapFree → free・HeapReAlloc → realloc (flags 0x10 は §5-1)・HeapSize → サイズ表・HeapQueryInformation → 固定値・GetProcessHeap → 非 NULL の固定ハンドル |
| B 同期・イベント | EnterCriticalSection・LeaveCriticalSection・DeleteCriticalSection → no-op。InitializeCriticalSectionAndSpinCount → no-op (0 を返す)。InitializeSListHead → 先頭を 0 に初期化。InterlockedFlushSList → 0 を返す。SetEvent・ResetEvent → 成功 (1) を返す。CreateEventW → 固定の偽ハンドル。WaitForSingleObjectEx → WAIT_OBJECT_0 を返す (戻り値の分岐は未確認) |
| C TLS/FLS | TlsAlloc・TlsGetValue・TlsSetValue・TlsFree と FlsAlloc・FlsGetValue・FlsSetValue・FlsFree → インスタンス内の表 |
| D 例外・unwind | RtlCaptureContext・RtlLookupFunctionEntry・RtlVirtualUnwind・RtlUnwindEx → trap。RtlPcToFileHeader → NULL。RaiseException → trap (§5-4)。UnhandledExceptionFilter → 0 を返す。SetUnhandledExceptionFilter → NULL を返す (登録のみ)。IsDebuggerPresent → 0 を返す |
| E 動的ロード | GetModuleHandleW・GetModuleHandleExW・GetProcAddress・LoadLibraryExW → NULL (常に失敗)。FreeLibrary → 1。GetModuleFileNameW → 0 (§5-3) |
| F ファイル・コンソール | CreateFileW・WriteConsoleW・WriteFile・SetFilePointerEx・FindFirstFileExW・FindNextFileW → 失敗。CloseHandle・FlushFileBuffers・SetStdHandle・FindClose → 成功。GetStdHandle → NULL。GetFileType・GetConsoleMode → 0。GetConsoleOutputCP → 固定値。wasm は host の I/O を持たない (§5-6) |
| G プロセス・エラー状態 | GetCurrentProcessId・GetCurrentThreadId → 固定値。GetStartupInfoW → 0 埋め。GetCommandLineA・GetCommandLineW → 空文字列。GetEnvironmentStringsW → 空の環境ブロック。FreeEnvironmentStringsW → 成功 (1) を返す。GetCurrentProcess → 擬似ハンドル (-1)。EncodePointer → 恒等写像。GetLastError・SetLastError → wasm 内の変数。ExitProcess・TerminateProcess → trap |
| H 時刻・性能カウンタ | QueryPerformanceCounter・GetSystemTimeAsFileTime → 決定的な値。DSP 出力へ入らないことを確認してから固定する (§5-5) |
| I CPU・コードページ・文字列 | IsProcessorFeaturePresent → 0 (§5-2)。GetACP・GetOEMCP・IsValidCodePage・GetCPInfo・GetStringTypeW → 固定値。LCMapStringW → 入力をそのまま返す。MultiByteToWideChar・WideCharToMultiByte → UTF-8/ASCII の最小実装 |
| J バイトオーダ | WS2_32 序数 8 (htonl)・序数 14 (ntohl) → bswap32 |

## 5. 判断が要る項目 (未確認)

1. **HeapReAlloc の flags 0x10 (HEAP_REALLOC_IN_PLACE_ONLY)**: 呼出元 0x1802da416 (関数 0x1802da3a0 内) は `lea edx, [rax + 0xf]` で flags を作る。`mov eax, 1` が直前にあるため flags = 0x10。同じ API の別の呼出し (0x1802d8c41) は `xor edx, edx` で 0。0x10 の呼出しは、同位置で伸長できなければ NULL を返す契約であり、wasm の realloc (移動する) では写像が合わない。戻り値の分岐 (0x1802da41c の `test rax, rax`) の経路は未確認。export 到達は 0。
2. **IsProcessorFeaturePresent**: 5 箇所すべて `mov ecx, 0x17` (定数)。戻り値 0 (baseline 経路) を選ぶと、実機と違う分岐に入る可能性がある。0x17 の SDK 上の名前は未照合。export 到達は 3 関数。
3. **動的ロード (E)**: GetProcAddress の探索名は `SleepConditionVariableCS` (関数 0x1802c80b0。モジュール名 `api-ms-win-core-synch-l1-2-0.dll` と `kernel32.dll` を GetModuleHandleW で引く)・`CorExitProcess` (関数 0x1802d6688。`mscoree.dll`)・API セット名 `api-ms-*`/`ext-ms-*` (関数 0x1802ce4c8 と 0x1802dc170 の LoadLibraryExW・GetProcAddress)。NULL を返した後は MS CRT の標準の代替経路に入るとみられるが、経路は未確認。
4. **RaiseException**: 4 箇所。`ecx = 0xE06D7363` (C++ 例外の標準コード) は関数 0x1802caea8 の中 (0x1802caf32) で設定される。他の 3 箇所は ecx を実行時の値から取る (`mov ecx, [rsi]`・`mov ecx, edi`)。export 到達は 2 関数。trap へ写像すると、この経路を通った時点で wasm が止まる。通過の有無は未確認。
5. **QueryPerformanceCounter・GetSystemTimeAsFileTime**: 呼出元は各 1 関数。export 到達は 0。値が DSP 出力に入るかは、値の利用先を見るまで決まらない。
6. **CONOUT$ 出力**: CreateFileW (呼出元 2 関数) と WriteConsoleW (呼出元 1 関数) は文字列 `CONOUT$` を使う (関数 0x1802e0ac4・0x1802e0b34)。出力の目的 (デバッグ出力か) は未確認。export 到達は 0。

## 6. 受入条件との対応 (#2614)

| 受入 (元の本文) | 状態 | 所在 |
|---|---|---|
| 1 `.text` 4,556 件の RetDec lift と SIDE_MODULE (IPP 入口を自前実装へ置換) | 未着手 | 子 [T-SH-67] #3332 |
| 2 15 export の差分試験 (D18 の範囲) | 未着手 | 子 [T-SH-68] #3333 |
| 3 ビルドフラグ 1 つで除外・公開 tier の機械確認 | 未着手 | 子 [T-SH-68] #3333 |
| 4 KERNEL32 77 件の置換方針を REPORT に書く | 達成 (本 REPORT §3・§4・§5。対応表は `data/iat_policy.csv`) | 本 PR |

- #2614 の本文は受入 4 だけに縮めた。未達の 1〜3 は子へ移した。
- IPP 入口の置換 (子 #3332 の受入) には、未同定の入口の扱い (#2613 の未同定 163・#2667 の形のみ一致 131 ほか。`REPORT_152.md` §8.5) と、`tools/ipp` の stub のみの名前 28 件 (#38 系) が前提になる。どちらも未起票 (PM 判断) で、本 PR の未解決表に置く。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1 (lift・side module・IPP 入口の置換) | élastique の機能が wasm に無い | #3332 (T-SH-67) |
| 受入 2・3 (15 export の差分・除外フラグ) | 公開 tier への混入を機械検査できない | #3333 (T-SH-68) |
| §5-1〜6 の確認 (realloc の in-place・CPU 判定の値・動的ロード失敗後の経路・RaiseException の通過・時刻値の利用先・CONOUT$ の目的) | 置換の写像が仮定のまま | #3333 (T-SH-68 の差分試験で確認) |
| IPP 入口の同定の残り・tools/ipp の stub のみの 28 名 | 置換対象の件数が確定しない | 未起票 (PM 判断。`REPORT_152.md` §8.5・`REPORT.md` §7) |
| release guard の deny-list への élastique 追加 | 公開 tier への混入を機械検査できない | PM (D11・手元作業) |
| mac 版 (dylib) | 本 REPORT は win 版のみ | 依頼者の判断待ち (#152) |
