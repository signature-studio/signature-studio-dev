# 自動生成: `SHIMX_TRACE=1` の shimx 呼出トレース出力

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

# shimx 呼出トレース (lifted コード → shim; 計数ラッパ経由, SHIMX_TRACE=1, soft+fix ビルド)
停止: init_count_var=18 (InitUnits が unit #18 の init 実行中に memory access out of bounds)

## A. 17 unit 完走区間 (unit 0=InitUnits 前 〜 unit 17)

| shim | 区分 | 状態 | 回数 | 初回 unit | 初回 unit の init LVA |
|---|---|---|---|---|---|
| GetCurrentThreadId | shimx | 機能 | 2 | 0 (InitUnits 前) | - |
| TlsAlloc | shimx | 機能 | 1 | 0 (InitUnits 前) | - |
| LocalAlloc | shimx | 機能 | 1 | 0 (InitUnits 前) | - |
| TlsSetValue | shimx | 機能 | 1 | 0 (InitUnits 前) | - |
| TlsGetValue | shimx | 機能 | 1 | 0 (InitUnits 前) | - |
| VerSetConditionMask | shimx | 機能 | 3 | 2 | 0x1ce10 |
| VerifyVersionInfoW | shimx | 機能 | 1 | 2 | 0x1ce10 |
| GetModuleHandleW | shimx | 機能 | 4 | 2 | 0x1ce10 |
| GetProcAddress | shimx | 機能 | 4 | 2 | 0x1ce10 |
| SetThreadLocale | shimx | 機能 | 1 | 2 | 0x1ce10 |
| InitializeCriticalSection | shimx | 機能 | 1 | 2 | 0x1ce10 |
| GetVersion | shimx | 機能 | 2 | 2 | 0x1ce10 |
| GetSystemInfo | shimx | 機能 | 1 | 2 | 0x1ce10 |
| GetCommandLineW | shimx | 機能 | 1 | 2 | 0x1ce10 |
| GetStartupInfoW | shimx | 機能 | 1 | 2 | 0x1ce10 |
| GetACP | shimx | 機能 | 1 | 2 | 0x1ce10 |
| LoadStringW | GUI/audio stub | - | 3 | 16 | 0x4a570 |
| GetVersionExW | shimx | 機能 | 1 | 17 | 0x54090 |

合計 30 呼出 / 18 種 (うち GUI/audio stub 1 種)

## B. unit #18 (停止 unit) の呼出と停止時点

| shim | 区分 | 状態 | 回数 |
|---|---|---|---|
| GetCurrentThreadId | shimx | 機能 | 3 |
| GetModuleHandleW | shimx | 機能 | 1 |
| GetProcAddress | shimx | 機能 | 1 |
| InitializeCriticalSection | shimx | 機能 | 1 |
| VirtualAlloc | shimx | 機能 | 3 |
| GetModuleFileNameW | shimx | 機能 | 1 |
| WideCharToMultiByte | shimx | 機能 | 1 |
| GetThreadLocale | shimx | 機能 | 1 |
| GetCPInfo | shimx | 機能 | 1 |
| IsValidLocale | shimx | 機能 | 1 |
| GetLocaleInfoW | shimx | 機能 | 48 |
| EnumCalendarInfoW | shimx | 機能 | 2 |

合計 64 呼出 / 12 種

停止直前の呼出列 (末尾 40):
```
unit=18 GetLocaleInfoW x40
```

停止スタック (wasm):
```
RuntimeError: memory access out of bounds
    at wasm://wasm/017eed06:wasm-function[1240]<function_4133f0>:0x8d088
    at wasm://wasm/017eed06:wasm-function[4338]<function_446400>:0x1aa653
    at wasm://wasm/017eed06:wasm-function[4392]<function_44bb70>:0x1aefca
    at wasm://wasm/017eed06:wasm-function[4462]<function_455790>:0x1b4bea
    at wasm://wasm/017eed06:wasm-function[11360]<m11_tr_function_455790>:0x3792ca
    at wasm://wasm/017eed06:wasm-function[1227]<m11_icall>:0x8c3a0
    at wasm://wasm/017eed06:wasm-function[42]<__wrap_m11_icall>:0x64ce9
    at wasm://wasm/017eed06:wasm-function[1235]<function_4120c0>:0x8c891
    at wasm://wasm/017eed06:wasm-function[1236]<m11_InitLib>:0x8ccd0
```
