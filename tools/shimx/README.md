# tools/shimx — Win32/CRT shim 拡張 (M4 shim の上位互換)

`tools/shim` (M4: timer/file/sync/heap の 53 API) を **置換・拡張** する C 実装。FLEngine_x64.dll / プラグイン DLL が使う
kernel32 / ntdll / advapi32 / ole32 / oleaut32 / shell32 / shlwapi / version / winmm(timeGetTime 等) / imagehlp /
wininet / crypt32 / wintrust / mpr / msacm32 / winspool / comdlg32 の API を wasm 上に提供する。GUI (user32/gdi32/comctl32) は tools/gui、
DirectSound は tools/audio の担当で本実装の対象外。

```
bash tools/shimx/test.sh          # ビルド + node 単体テスト (MT/ST/M4 互換/fail-fast/署名突合/OTT) — exit 0 が成功
bash tools/shimx/test.sh --quick  # OTT 再リンク (verify_ott) を省略
```

結果・実測は `REPORT.md`、API 表は `inventory.md`、優先度付きバックログは `BACKLOG.md`、行別データは `data/inventory.csv`。

## 使い方 (下流ビルド)

```
emcc <lift IR / runtime> tools/shimx/src/*.c ... -sGLOBAL_BASE=<64KB 以上>      # M4 の ../shim/src/*.c を置き換える (混在リンク不可: 同名シンボル)
```

- `src/shimx.h` が公開ヘッダ (M4 の `shim.h` 互換: `src/shim.h` は `shimx.h` を include するだけ)。
- 未対応 API は `shim_unimplemented("関数名")` で名前を出して abort (M4 方針を維持)。lift 産物 IR の未提供 API 用スタブは
  `python3 scripts/ir_undef.py <ir.ll> --emit-stubs stubs.c` で署名付き生成できる。
- IR の declare 署名と shimx 定義の wasm 署名の一致検査: `bash scripts/verify_sig.sh <ir.ll> <tag>`。
- 構造体は Win64 レイアウト (ポインタ 8B スロット)。ポインタ値 < 0x10000 は整数 (序数/MAKEINTRESOURCE/単一文字) とみなすので GLOBAL_BASE は 64KB 以上。

## 運用フック (`shimx_*`, 詳細は shimx.h 末尾)

| 領域 | API |
|---|---|
| VFS | `shimx_set_path_mapper` (Win→FS パス写像) / `shimx_path_to_posix` |
| モジュール | `shimx_module_register` / `shimx_proc_register` / `shimx_set_proc_resolver` / `shimx_set_load_hook` / `shimx_set_resource_provider` / `shimx_set_exe_path` / `shimx_set_strict` |
| レジストリ | `shimx_reg_set[_sz/_dword]` / `shimx_reg_import_text` / `shimx_reg_export_text` / `shimx_reg_reset` |
| プロセス | `shimx_set_command_line` / `shimx_setenv_utf8` / `shimx_set_version` / `shimx_set_exit_hook` / `shimx_set_acp` / `shimx_set_locale` |
| 例外 | `shimx_set_raise_hook` (RaiseException を外部で処理) |
| シェル/信頼 | `shimx_set_shell_execute_hook` / `shimx_set_trust_ok` / `shimx_get_drop_target` |
| 診断 | `shimx_set_trace(1)` または環境変数 `SHIMX_TRACE=1` |

## 構成

| ファイル | 内容 |
|---|---|
| `src/handles.c` | 統一ハンドル表 (16384 スロット, 参照カウント, 名前付きオブジェクト), futex mutex, CloseHandle/DuplicateHandle |
| `src/wait.c` `thread.c` `locks.c` | Wait*/Event/Mutex/Semaphore, スレッド/タイマキュー/スレッドプール, CS(Win64 40B)/SRW/CondVar/InitOnce/SList/Interlocked |
| `src/teb.c` | LastError/TID/擬似 TEB(`__readgs*`)/TLS(1088)/FLS |
| `src/file.c` `ini.c` | パス写像, CreateFile 系, Find*, FileMapping, 属性/一時/ドライブ, INI, コンソール |
| `src/timer.c` `heap.c` `str.c` `locale.c` | 時刻, heap/Global/Virtual, MultiByte/WideChar・比較・LCMap, ロケール/FormatMessage |
| `src/reg.c` `env.c` `module.c` `seh.c` | レジストリ(メモリ内)+Crypt スタブ, 環境/システム情報/バージョン/アトム, モジュール表/GetProcAddress/リソース/IMAGEHLP, SEH 第一手+CRT ロック |
| `src/ole.c` `shell.c` `net.c` | BSTR/VARIANT/SAFEARRAY/IStream/IMalloc, shell32/version/各種スタブ, ネットワーク・認証・MIDI の常時エラー |
| `src/proctable.c` `shimx_stubs.h` `exports.txt` | 自動生成 (test.sh)。GetProcAddress の組込み表 / 未宣言 API の prototype / 公開関数一覧 |
| `scripts/` | import_scan(PE 走査) / build_objs / gen_proctable / gen_stub_protos / gen_inventory / ir_undef / verify_sig / verify_ott |
