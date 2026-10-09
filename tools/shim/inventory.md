# M4 shim: Windows API 相当 実装インベントリ

## 結論

**strategy.md §3 のうち #2 / #3 / #4 / #7 (+ #8 の最小面) に相当する 53 API を `tools/shim/src/` 配下に実装し、MT (pthread) / ST (シングルスレッド) の両ビルドで node 上の単体テストが ALL PASS (`bash tools/shim/test.sh` で exit 0)**。未対応 import は `shim_unimplemented()` で即 abort + 関数名出力する fail-fast を実装済み。FLEngine (Delphi) 実リンクは M5 以降であり、本成果物は「shim の土台 + テスト規律」の確立を目的とした v1 (最小面) である。

## 実装配置

| ファイル | 内容 | §3 行対応 |
|---|---|---|
| `src/shim.h` | 共通型・定数・宣言 (x64 Windows 相当の幅) | すべて |
| `src/shim_internal.h` | HANDLE テーブル共有 (内部用、外部非公開) | すべて |
| `src/timer.c` | GetTickCount64/GetTickCount/timeGetTime/QPC/QPF/Sleep | **#3** |
| `src/file.c` | CreateFileW/Read/Write/SetFilePointer(Ex)/SetEndOfFile/GetFileSize(Ex)/CloseHandle + HANDLE テーブル | **#2** |
| `src/sync.c` | CreateThread/ExitThread/WaitForSingleObject(Ex)/Event/CRITICAL_SECTION/Interlocked/MemoryBarrier/TLS | **#4** (+ §5.3 TLS 前提の一部) |
| `src/heap.c` | HeapCreate/HeapAlloc/HeapReAlloc/HeapFree, GlobalAlloc/Lock/Unlock/Free, LocalAlloc(ReAlloc)/Free | **#7** |
| `src/failfast.c` | `shim_unimplemented()` — 未対応 import を即 abort + 関数名出力 | 未対応面の運用 (M5 前提) |
| `exports.txt` | export する 53 API 一覧 (ビルド時のリンク検証に使う) | 全部 |
| `flags.sh` | emcc フラグ (m1/flags.sh の流儀, ST/MT 2 系統) | — |
| `test/test_main.c` | 単体テスト本体 (C) | — |
| `test/test_failraise.c` | fail-fast 確認用ハーネス | — |
| `test.sh` | テスト実行 (node 上で完結, exit 0 基準) | — |

## API 一覧 (§3 対応表)

52 API + `shim_unimplemented` = 53 export。★ = テストで直接検証済。

### #3 timer / time (7 API)
| API | 実装先 | 備考 | テスト |
|---|---|---|---|
| GetTickCount64 | emscripten_get_now (ms, 単調) | bit 厳密一致は非目標。オーディオクロックは worklet 側 sample pos がマスター (survey §4.3) | ★ |
| GetTickCount | GetTickCount64 下位 32bit | | ★ |
| timeGetTime | GetTickCount64 | winmm 相当も同一時計として扱う | ★ |
| QueryPerformanceCounter | emscripten_get_now × 1000 (us 粒度) | オーディオクロックは worklet 側 sample pos がマスター (survey §4.3) | ★ |
| QueryPerformanceFrequency | 1,000,000 固定 | | ★ |
| Sleep (ms) | emscripten_futex_wait ループ | SAB 上。ST ビルドでは即 return (制限) | ★ |
| (#4 共通) WaitForSingleObject | futex_wait ループ | thread/event のみ v1 対応 | ★ |

※ timer.c 内コメントと整合 (下記「v1 の方針差」参照)。

### #2 file (9 API)
| API | 実装先 | 備考 | テスト |
|---|---|---|---|
| CreateFileW | open() (UTF-16→UTF-8 変換, disposition Map) | GENERIC_READ/WRITE × 5 disposition 対応 | ★ (byte-faithful + 日本語パス) |
| ReadFile | read() | OVERLAPPED 非 NULL は無視 (同期 I/O 前提) | ★ |
| WriteFile | write() | 同上 | ★ |
| SetFilePointer | lseek() (whence Map: BEGIN/CURRENT/END) | 戻り値は下位 32bit (x64 慣例) | ★ |
| SetFilePointerEx | lseek() | LARGE_INTEGER 直接 | ★ |
| SetEndOfFile | ftruncate(現在位置) | | ★ |
| GetFileSize | fstat() | high/low 分割対応 | ★ |
| GetFileSizeEx | fstat() | | ★ |
| CloseHandle | file/thread/event 汎用 (減算解放) | thread は未 join なら pthread_detach | ★ |

### #4 thread / sync (17 API)
| API | 実装先 | 備考 | テスト |
|---|---|---|---|
| CreateThread | pthread_create (trampoline で done フラグ) | pthread ビルド (MT) | ★ (join) |
| ExitThread | 自スレッド slot の done 設定 + pthread_exit | 待機者を閉じ込めない | ★ |
| WaitForSingleObject | futex_wait ループ (thread/event) | timeout → WAIT_TIMEOUT, 無効 HANDLE → WAIT_FAILED | ★ |
| WaitForSingleObjectEx | WaitForSingleObject 委譲 | APC/alertable 非対応 | (委譲のみ) |
| CreateEventW | HANDLE テーブル (manual/auto) | named event (プロセス間共有) 非対応 | ★ |
| CreateEventA | CreateEventW 委譲 | | (委譲のみ) |
| SetEvent / ResetEvent | atomic store + futex_wake(ALL) | auto-reset の多 waiter 競合は近似 | ★ |
| InitializeCriticalSection / ...AndSpinCount | shim 内ポインタ対応表に登録 | クライアント確保メモリ (Delphi 40byte 構造体相当) を上書きしない | ★ |
| EnterCriticalSection / LeaveCriticalSection | pthread_mutex (RECURSIVE) への写影 | Win32 同様再帰可能。SpinCount 無視 | ★ |
| TryEnterCriticalSection | pthread_mutex_trylock | | ★ |
| DeleteCriticalSection | 対応表からの解除 + mutex 破棄 | | ★ |
| MemoryBarrier | __atomic_thread_fence(SEQ_CST) | | (間接) |
| InterlockedIncrement / Decrement / Exchange / ExchangeAdd | __atomic builtins (SEQ_CST) | 4 thread × 10,000 加算の競合検証 | ★ |
| TlsAlloc / TlsFree | index テーブル + pthread_getspecific | スレッド別 64 slot | ★ (分離検証) |
| TlsGetValue / TlsSetValue | 同上 | | ★ |
| GetCurrentThreadId | pthread_self のハッシュ | 衝突時影響は最小 (表示/所有者管理のみ) | (委譲のみ) |

### #7 heap (10 API)
| API | 実装先 | 備考 | テスト |
|---|---|---|---|
| HeapCreate | ダミー非 NULL ハンドル (単一 malloc ヒープに束ねる) | | ★ |
| HeapAlloc | malloc + ヘッダ (magic/size/lock) | HEAP_ZERO_MEMORY 対応 | ★ |
| HeapReAlloc | realloc + ヘッダ再構築 | 先頭 min(old,new) バイト保持 | ★ |
| HeapFree | free | 二重フリー検出はヘッダ magic による緩い検査 (v1) | ★ |
| GlobalAlloc | 同方式 | GMEM_ZEROINIT 対応。**GMEM_MOVEABLE は FIXED 写影** (inventory 制限) | ★ |
| GlobalLock / GlobalUnlock | ポインタそのまま + lock count | | ★ |
| GlobalFree | free (magic 検証) | | ★ |
| LocalAlloc / LocalReAlloc / LocalFree | Global 系と同一経路 | 16bit 世代の差異は意味を持たない | ★ |

### #8 CRT (最小限, 2 API) + fail-fast (1 API)
| API | 実装先 | 備考 | テスト |
|---|---|---|---|
| GetLastError / SetLastError | プロセス単位の(簡易)変数 | スレッド別TLS化は M5 で実測後に再評価 | ★ (file NOT_FOUND) |
| shim_unimplemented | stderr への関数名出力 + abort() | 未対応 import 到達を即可視化 | ★ (別ビルド) |

## テスト実績 (`bash tools/shim/test.sh`, 2026-10-09)

- **MT (pthread)**: timer 進み / file byte-faithful・日本語パス・SetEndOfFile / CRITICAL_SECTION 4 thread × 10,000 排他加算 = 40,000 / Heap alloc-拡張-保持 / thread 生成 + join + TLS 分離 + event wake + ExitThread **ALL PASS (exit 0)**
- **ST (シングルスレッド)**: timer/file/heap/CS 単一・Interlocked/TLS 共通 smoke **ALL PASS (thread 面は pthread skipped)**
- **fail-fast**: `shim_unimplemented("DestroyWindow_NonImplemented_Example")` → **即 abort + stderr に関数名** (exit != 0 を確認)

## 未対応一覧 (fail-fast になる)

| 領域 | §3 行 | 状態 |
|---|---|---|
| GUI / MSG / GDI / Cocoa | #5 | 未実装 (M7 前提) |
| registry → IndexedDB | #6 | 未実装 (P1) |
| AudioWorklet / ASIO / DirectSound | #1 | 未実装 (M8 前提) |
| 外部プロセス (exec/fork/NSTask) | #9 | 未実装 (P2, 対象外宣言済み) |
| MIDI / Web MIDI | #10 | 未実装 (P1) |
| ネットワーク / 認証 / クラウド | #11 | 未実装 (P0, M5/M6 で fail-fast 化) |
| プラグイン ABI | #12 | 未実装 (M6 前提) |
| Win32 周辺のその他の API (FindFirstFileW, GetStartupInfo, LoadLibrary, VirtualAlloc, WaitForMultipleObjects 等) | #2/#7 の派生面 | 未実装 (M5 で import 面 diff をもとに追加予定) |

## v1 の方針差とリスク (M5 以降で要更新)

1. **GMEM_MOVEABLE = FIXED 写影**: wasm は単一アドレス空間なので移動不要。FLEngine が movable ハンドルを前提とした特殊な扱いをした場合のみ要確認 (§7 import 面照合時に確認)。
2. **named event / WaitForMultipleObjects 非対応**: Delphi TThread で 1 thread 待ちが主流の想定。MultiObjects 需要が出たら futex ループ + カウントで拡張。
3. **GetLastError はプロセス単位**: スレッド別化は M5 実測後に再評価 (Delphi RTL 側の実態に合わせる)。
4. **Sleep in ST build**: futex_wait が SAB 前提のため、「すぐ return (時間経過しない)」が起きうる。本番は pthread ビルド (MT) を前提とする。
5. **QPC 粒度 1us 固定**: bit 厳密一致は非目標 (timer 粒度は「意味論が破綻しない最小実装」基準)。オーディオクロックは worklet 側 sample pos マスター設計 (survey §4.3) への切换が必要であり、M8 で再検証する。
