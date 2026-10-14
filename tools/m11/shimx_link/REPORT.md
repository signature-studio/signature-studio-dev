# M11 × shimx リンク REPORT (CAB-166 / SHX-T1) — 担当 T1

- 日付: 2026-10-10 / 環境: emcc 6.0.12, node v26.10.0 / 再現: `bash tools/m11/m11_e2e.sh` (前提; lift 成果物生成) → **`bash tools/m11/shimx_link/e2e.sh`** (約 40 秒, 常に exit 0)
- 既知類型との関係: 該当なし。D11 (絶対 VA の i64 定数の切り捨て) と D17 (8B store の 4B 縮小) は wasm32 の幅差を含むが機構は別。本件は外部関数 (shimx) との宣言の型幅の不一致 (詳細は付録 §12)。
- 書込: `tools/m11/shimx_link/` のみ。`tools/shimx` / `tools/m11` 既存ファイル / `tools/startup` は **読取のみ (差分 0 行)**。一時物は `tools/m11/work/shimx_link/` (gitignore 済)
- **tools/m11 既存ビルド/実行スクリプトへの差分: なし** (build.sh は M11 のソース `m11_rt.c` `m11_ov.c` と work/ の生成物を無改変で再利用する別系統ビルド)

## 0. 結論

| 項目 | 実測 |
|---|---|
| shimx リンク | M11 closure (boot_final3.ll, 外部参照 570) に shimx 全 19 ソースを**厳密リンク (重複許容なし)**: **signature mismatch 0 / undefined symbol 0 / duplicate 0** (5 ビルド全て。**旧 IR の値。現 IR の値は §10.3**)。wasm 6.18 MB (既存 6.01 MB) |
| 退役した旧 shim | `tools/shim` 5 ファイル (heap/failfast/file/timer/sync, 計 59 定義) と `m11_win.c` (35 定義) をリンクから外した。うち 85 シンボルが shimx の定義に置換、`m11_win.c` の残り 3 (LoadStringW/MessageBoxA/MessageBoxW = user32) は暫定互換 `gui_compat.c` (soft のみ) |
| 外部参照 557 の内訳 (boot_final2) | shimx **182** (+署名ずれ declare `SHGetFolderPathW.1` 1 = shimx REPORT の 183 と一致) / GUI・audio 対象外 **171** / lift 由来 **203** (うち m11 側 C が提供 188 = SIMD helper 179 + fnstub 8 + rt 1, 未提供 12, intrinsic 3) |
| **純リンクだけでは後退する** | IR 無改変 + shimx: GUI fail-fast では **unit 16** (`LoadStringW`) で停止、0 返却 GUI でも **unit 17** で shadow stack を破壊して Halt0 に至る (偽の「DllMain 完走」)。原因は lift 側 (§3)。**補正 `--fix` (alloca 拡幅 + 列挙コールバック変換 + `_WStrClr` 1 関数)** を入れると M11 既存と同じ **17 unit 完走・unit #18 で OOB** に戻る (後退なし) |
| 起動実行 (trace, `--trace --soft --fix`) | shim 呼出 **94 回 / 26 種 (shimx 25 + GUI スタブ 1)**。17 unit 完走区間 30 回 / 18 種、unit #18 で 64 回 / 12 種 (`GetLocaleInfoW` 48 含む) → `_UStrAsg` OOB |
| shimx スタブ 115 本 | 起動経路 (17 unit + #18) で**呼ばれたもの 0**。942 unit 隔離 survey でも **`SetErrorMode` / `acmMetrics` の 2 本のみ**。fail-fast 系 `RtlUnwind*`/`RaiseException` は **closure の declare 自体が 0** で到達しない |
| unit 隔離 survey (942) | ok **800** / oob 41 / halt0 53 / closure 外 46 / abort 1 / proc 無し 1。既存 M11 ビルドを同手順で再測 ok **800** / oob 50 / halt0 44 / 同 46 / 1 / 1 → ok 同数、oob 9 unit が halt0 まで前進 |
| CAB-176 (DllMain closure) | **未完 (Todo 維持)**。unit #18 OOB (CAB-129) が先。shimx 起因ではないことを実証 (§4) |

## 1. 外部参照の解決状況表 (`results/resolution.md`, `classes_boot_final{2,3}.json`)

分類は `gen_link.py` (shimx の `ir_undef.py` を import 再利用) が **リンクした shimx オブジェクトの nm** と突合して決定。

| 区分 | boot_final2 (shimx REPORT の 557) | boot_final3 (現行リンク対象 570) |
|---|---|---|
| 外部参照 総数 | 557 | 570 |
| **shimx 解決** | 182 (機能 169 / スタブ 13) | **184** (機能 171 / スタブ 13) |
| GUI/audio 対象外 | 171 (user32 114 / gdi32 53 / shcore 2 / uxtheme 1 / dsound 1) | 171 (同) |
| lift 由来 | 203 | 214 |
| └ m11 側 C が提供 | 188 | 211 (SIMD helper `__asm_*` 201 + `function_*` fnstub 8 + `m11_counter_ptr`/`m11_probe`) |
| └ どこも未提供 | 12 | 0 |
| └ LLVM intrinsic | 3 | 3 |
| 未分類 | 1 (`SHGetFolderPathW.1`) | 1 (`SHGetFolderPathW_D1`) |

- 570 > 557 は m11 側の probe/trampoline 追加分と lift 再生成差 (IR が boot_final2 → boot_final3 に進んでいるため)。
- 未分類の `SHGetFolderPathW_D1` は RetDec が `SHGetFolderPathW` とは別に **0 引数 i64 返し**で declare した重複 (呼出 1 箇所)。GUI/audio と同様に fail-fast/0 返却スタブで受けている (署名正規化 = shimx T7 の対象)。
- GUI/audio 171 は `gui_stubs_failfast.c` (`shim_unimplemented` で名前を出して abort) / `gui_stubs_soft.c` (0 返却 + `m11_stub_hit` 計数) を IR の declare から自動生成。
  shimx 付属 `ir_undef.py --emit-stubs` は**構造体 by-value 引数を展開しない**ため `WindowFromPoint(%tagPOINT)` で実際に signature mismatch 1 を出した → `gen_link.py` は構造体を wasm32 規則で展開して生成 (shimx T7/要求 R6)。

## 2. ビルド (`build.sh`)

```
bash tools/m11/shimx_link/build.sh [--trace] [--soft] [--fix]    # → work/shimx_link/m11_sx_<plain|trace>_<failfast|soft>[_fix].cjs
```

| オプション | 内容 |
|---|---|
| (既定) | IR 無改変 + shimx 厳密リンク + GUI fail-fast スタブ (= CAB-166 本体) |
| `--soft` | GUI/audio を 0 返却スタブ (M11 既存挙動) + `gui_compat.c` (LoadStringW/MessageBox の 3 本) |
| `--trace` | IR の shimx/GUI 参照 356 名を `@__sxt_<name>` に改名し、計数ラッパ (`trace_wrap.c`) 経由にする。lifted 側の呼出だけを数える (shimx 内部の再入呼出は数えない) |
| `--fix` | `fix_alloca.py` (alloca 拡幅) + `cb_adapt.c` (列挙コールバック変換) + `sx_liftfix.c` (`_WStrClr` 1 関数) — **CAB-129 / hostbridge T2 の計測用回避**。shim の実装ではない |

- `VirtualAlloc/Free/Protect/Query` は shimx では weak 定義 (shimx の設計どおり) → M11 の `m11_rt.c` (強定義, 64KB 整列 calloc + va_used 計数) が優先。
- shimx は ST でビルド (M11 の IR は非 pthread)。`CreateThread` は ST で fail-fast → closure は CreateThread を declare するが**未到達**。MT 版は IR を `-pthread` で再コンパイルする必要があり未検証。
- `SHIMX_TRACE=1`: Emscripten の `ENV` を preRun で設定しても shimx の `getenv` には届かなかった (実測) → ハーネスが `shimx_set_trace(1)` を export 経由で呼ぶ。

## 3. 純リンクで顕在化した lift 側の誤り (shimx が「仕様どおり」動くため露呈)

M11 旧 stub は構造体を部分書込み・`SysFreeString` は no-op だった。shimx は Win32 仕様どおり動くので、隠れていた lift 誤りが出た。

| # | 症状 (実測) | 原因 | 対処 (`--fix`) |
|---|---|---|---|
| 1 | unit 13 の `function_412e00` が `SysFreeString` → `free` で abort | `_WStrClr` の 2 段 deref 脱落 (`if (&S) {S=0; SysFreeString(&S)}`)。逆アセンブル `mov rax,[rbx]…mov rcx,[rbp+28]; call 0x407290` と不一致 | `sx_liftfix.c` で 1 関数を C 転記 (m11_ov.c と同流儀) |
| 2 | unit 17 (`function_454090`) の `GetVersionExW` が **284B を 8B の `alloca i64` に書き**、`InitUnits` のローカルを破壊 → 偽の Halt0 (`dllmain_done` が true になるが units_run 17/942) | RetDec の集成体ローカル縮退 (CAB-129 と同根) | `fix_alloca.py`: 出力パラメータ API の要求サイズ表 + `rep stos` 定数長から alloca を `[K x i64]` に拡幅。**24 alloca / 23 関数** (`GetVersionExW` 3, `FindFirstFileW` 4, `VirtualQuery` 4, `GetLocalTime` 4, `rep stosq` 4 = `44bb70`/`59b100`/`95b400`/`ade4d0` 他)。`results/fix_alloca_report.json` |
| 3 | unit 18 の `EnumCalendarInfoW` が `table index is out of bounds` | lifted が渡すコールバックは VA/LVA で wasm table index ではない (shimx REPORT §5 のとおり) | `cb_adapt.c` が `m11_icall` 経由のトランポリンに変換 (`EnumCalendarInfoW`/`EnumSystemLocalesW`, 同期のみ)。コールバック本体 `0x4476d0` は closure 外 → icall-miss 1 で列挙は打切り |
| 4 | `GetProcAddress miss: kernel32.dll!#39682` | image を LVA 0 に敷設しているため `.text` 内の Delphi 文字列 (LVA < 0x10000) が shimx の「ポインタ < 0x10000 は序数」判定に該当 | 未対処 (要求 R1)。結果は NULL のまま (旧 stub と同じ) |
| 5 | `LoadStringW` を fail-fast にすると unit 16 で停止 | user32 = GUI 担当。soft では暫定互換で `buf[0]=0` を書く (書かないと unit 17 が Halt に至った) | `gui_compat.c` |

## 4. トレース実測 (`SHIMX_TRACE=1`, `--trace --soft --fix`; `results/trace_units.md`, `trace_units.json`)

### 4.1 17 unit 完走区間 (unit 0 = InitUnits 前 〜 17): 30 呼出 / 18 種

| 初回 unit (init LVA) | shim (回数) |
|---|---|
| 0 (InitUnits 前) | GetCurrentThreadId 2, TlsAlloc, LocalAlloc, TlsSetValue, TlsGetValue |
| 2 (0x1ce10) | VerSetConditionMask 3, VerifyVersionInfoW, GetModuleHandleW 4, GetProcAddress 4, SetThreadLocale, InitializeCriticalSection, GetVersion 2, GetSystemInfo, GetCommandLineW, GetStartupInfoW, GetACP |
| 16 (0x4a570) | **LoadStringW 3 (GUI スタブ)** |
| 17 (0x54090) | GetVersionExW |

unit 1・3〜15 は shim を呼ばない。

### 4.2 unit #18 (init LVA 0x55790, `function_455790`→`44bb70`→`446400`) 停止まで: 64 呼出 / 12 種

GetCurrentThreadId 3, GetModuleHandleW, GetProcAddress, InitializeCriticalSection, **VirtualAlloc 3**, GetModuleFileNameW, WideCharToMultiByte, GetThreadLocale, GetCPInfo, IsValidLocale, **GetLocaleInfoW 48**, **EnumCalendarInfoW 2**。
停止は `function_4133f0` (`_UStrAsg`) の `memory access out of bounds` (`446400` 内)。M11 既存ビルドの stub_hits (`GetLocaleInfoW:48`, `EnumCalendarInfoW:2`) と**呼出回数まで一致**。

### 4.3 `[shimx]` トレース出力 (survey 全体, `results/survey.md`)

- `GetProcAddress miss`: kernel32 `GetThreadPreferredUILanguages` / `SetThreadPreferredUILanguages` / `GetThreadUILanguage`、shell32 序数 #16 #17 #18 #19 #21 #25 #152 #153 #155、空名 (ole32 6 / dwmapi 23 / user32 8 / comctl32 12 / kernel32 11 他)
- `LoadLibrary 失敗`: `Msctf.dll` (unit 104) / `avrt` / `PowrProf.dll` (unit 146)
- `CreateProcess 拒否` / `ShellExecute`: 0 件

### 4.4 スタブ (inventory status=S) の使用 (`results/stub_usage.md`)

- FLEngine 静的 import に対するスタブ 115 本: **17 unit + #18 では 0 本**、survey では `SetErrorMode` (unit 104) / `acmMetrics` (unit 171) の 2 本。
- shimx 解決 184 名のうちスタブは 13 名 (CoCreateInstance, InternetGetConnectedState, OutputDebugStringW, SHAppBarMessage, SetErrorMode, SetThreadErrorMode, ShellExecuteW, WTSRegisterSessionNotification, acmMetrics, midiOutShortMsg, timeBeginPeriod, timeEndPeriod, timeGetDevCaps)。
- **RtlUnwind/RtlUnwindEx/RaiseException は closure が declare しない** (Delphi は自前 SEH) → 起動への影響なし。shimx 内部 fail-fast に当たったのは survey の unit 115 の `EnterCriticalSection (NULL/misaligned)` 1 件のみ (既存 M4 shim でも同 unit で同じ abort; 単独実行では Halt0 で、直前 unit の状態依存 = lift 側のポインタ不正)。

## 5. DllMain closure の shimx 到達範囲 (CAB-176 向け; `results/survey.md`, `reach.json`)

| 観点 | 実測 |
|---|---|
| 逐次起動で到達 | `entry_point` → `_StartLib` → `_InitLib` → `InitUnits` → unit 1〜17 通過、18 で停止。この間 shimx 25 種 (全て機能実装) + GUI スタブ 1 種を呼び、全て復帰 |
| 隔離 survey (942) | ok 800。呼ばれた shim は **51 種** (shimx 37 + GUI スタブ 14; 逐次トレースとの和集合は shimx 40 + GUI 14)。最頻 `TlsGetValue` 53 unit / `InitializeCriticalSection` 22 unit / `VirtualAlloc` 16 unit / `GetProcAddress` 13 unit |
| 静的到達 (unit proc 942 + entry を根, 直接 call/参照グラフ) | 定義 7,422 関数中 6,048 到達、shimx 184 名中 **172**、GUI 170 中 153、dsound 1。うち**動的に一度も呼ばれていない shimx 名 133** (CloseHandle, CreateFileW, CompareStringW, CreateThread, レジストリ大半 等) = **shimx 側の実機検証が未実施の範囲** |
| 間接 call | RetDec は間接 call を落とす (M11 REPORT §2.1) ため静的到達は下限 |

### CAB-176 の現状ブロッカー (優先順)

1. **unit #18 OOB (CAB-129) が先**。shimx 無関係を実証: `GetLocaleInfoW`/`EnumCalendarInfoW` を `--wrap` で旧 stub と同じ 0 返却に戻しても同じ `_UStrAsg` OOB (`experiments/locale_stub0.sh`)。さらに `VirtualAlloc` 要求サイズがビルドごとに変わる (既存 355MB / plain 360MB / trace 629MB) = 未初期化メモリ由来のサイズ算出で、`44bb70` の alloca 拡幅 (392B) だけでは解消しない。
2. **LoadStringW** (user32; GUI 担当): 現状 0 返却。survey で 28 unit・計 2.9 億回の呼出 (戻り 0 でリトライ/ループしていると推定)。実リソース (`FindResource/LoadResource` provider フックは shimx に有) の接続が要る。
3. Halt0 (survey 53 unit; うち `MessageBoxA` "Runtime error 0 at …" を出すのは 42 unit): 失敗系 unit の根因は未調査。stage 5/6 (全 unit 完走 → DllMain TRUE) は未達。
4. closure 外 46 unit、`EnumCalendarInfoW` コールバック `0x4476d0` など closure 外コールバック。
5. 純リンク (`--fix` なし) は unit 17 で壊れる: alloca 縮退の本修正 (CAB-129) と SEH/コールバックの hostbridge (shimx T2) が取り込まれるまで `--fix` が必須。

## 6. shimx への要求リスト (独自実装はしていない)

| # | 要求 | 根拠 |
|---|---|---|
| R1 | 「ポインタ < 0x10000 は整数」の閾値を設定可能に (`shimx_set_intptr_limit` 等)、または image 敷設を 64KB 以上へ | `GetProcAddress miss: kernel32.dll!#39682` (Delphi 文字列が LVA 0x9b02) |
| R2 | 関数ポインタ引数の変換フック (`shimx_set_callback_translator`)。対象: Enum* / CreateThread / FlsAlloc / タイマ / スレッドプール | §3-#3 (同期列挙のみ link 側アダプタで暫定対応) |
| R3 | GetProcAddress 組込み表へ追加: kernel32 `GetThreadPreferredUILanguages`/`SetThreadPreferredUILanguages`/`GetThreadUILanguage`、shell32 序数 16/17/18/19/21/25/152/153/155 (既知 74/190 に追加) | §4.3 |
| R4 | `LoadLibrary` 失敗の方針: `Msctf.dll`/`avrt`/`PowrProf.dll` を擬似 DLL として登録するか (失敗のままで起動は進む) | §4.3 |
| R5 | `SysFreeString` が shimx 管理外ポインタを受けたときの挙動 (`shimx_set_strict(0)` で無視) の検討 | §3-#1 (今回は lift 側を直した) |
| R6 | `ir_undef.py --emit-stubs` の構造体 by-value 展開、IR の `NAME.1` 重複 declare の正規化 | §1 (T7) |
| R7 | `EnterCriticalSection(NULL)` 時の方針 (fail-fast のままか Win32 同様の AV 相当か) | survey unit 115 |
| R8 | 未検証範囲 133 名の実機検証 (レジストリ・ファイル系が大半)。survey で呼ばれていないため T9 の後続は unit 完走後 | `reach.json` |

## 7. 成果物 (`tools/m11/shimx_link/`)

| ファイル | 役割 |
|---|---|
| `e2e.sh` | 5 ビルド + 実行 + survey + 集計の 1 コマンド |
| `build.sh` / `gen_link.py` | shimx 厳密リンク / 外部参照分類 + GUI スタブ + 計数ラッパ + 改名 IR 生成 |
| `fix_alloca.py` / `cb_adapt.c` / `sx_liftfix.c` / `gui_compat.c` | `--fix` / `--soft` の計測用回避 (CAB-129・T2 の本修正までの暫定) |
| `experiments/locale_stub0.sh` | unit #18 OOB が shimx 起因でないことの対照実験 (ロケール API を旧 stub と同じ 0 返却に戻す) |
| `trace_rt.c` / `run_trace.mjs` / `survey_trace.mjs` | 計数ランタイム / 起動ハーネス / 942 unit survey (abort 時は新インスタンスで継続) |
| `analyze.py` / `results/` | 集計 / 結果 (`resolution.md`, `trace_units.md`, `survey.md`, `stub_usage.md`, `reach.json`, `fix_alloca_report.json`, `classes_*.json`, `stderr_trace_soft_fix.txt`) |

## 8. 制限

- 実行は node の -O0 ビルド。ブラウザ・MT は未検証。survey の ok 数は abort 後にインスタンスを作り直す手順に依存し、M11 REPORT の survey (ok 812) とは直接比較できない (同手順で既存ビルドを再測して比較した)。
- トレースは lifted コードからの呼出のみ (shimx 内部の呼出・`m11_ov.c` から C で直接呼ぶ `LCMapStringW` は含まない)。
- `ok` = 例外なく戻っただけで、意味の正しさは保証しない (M11 REPORT §4 の「lift 検証手段が無い」は未解決)。

## 9. R2/R3 実体接続 (CAB-177) — cb_adapt 廃止と sx_cbboot

本チケット (CAB-177) により §3-#3 / §6-R2 の暫定対応を置換した。詳細は `tools/hostbridge/cb/REPORT.md` と
`tools/shimx/REPORT.md` §10。**本 REPORT の数値は CAB-166/CAB-129 時点 (cb_adapt 時代) の記録として保持**
し、接続後の実測は下表のとおり (2026-10-10 再測, `results/` 更新済み)。

- `cb_adapt.c` (--wrap=EnumCalendarInfoW/EnumSystemLocalesW, 単一 global g_cb, 同期 2 API のみ) を**削除**。
- 代わりに `sx_cbboot.c` (constructor) が全 variant で `shimx_cbtrans_set_invoke(m11_icall)` →
  `shimx_cbtrans_install()` → `shimx_set_proc_resolver(shimx_lifttab_proc_resolver)` を実行し、
  build.sh は `-Wl,--wrap=m11_icall` (R3 トークン → `shimx_lifttab_trampoline` → `__real_m11_icall`) を追加。
- `--fix` は fix_alloca.py + sx_liftfix.c のみになった (**コールバック変換は全 variant の常時機構に昇格**)。
  なお現行 boot_final3.ll は CAB-129 pass 適用済みで fix_alloca の拡幅対象は 0 関数 (`results/fix_alloca_report.json`)。

| 項目 | §0〜§8 の記録 (cb_adapt 時代) | 接続後 (CAB-177) |
|---|---|---|
| 純リンク (trace_soft) | init_count 17〜18 / unit 18 で table index trap (§3-#3) | **init_count 18 / longjmp_hit 0 / threw=memory access out of bounds** (= §4.2 の CAB-231 停止点に到達) |
| trace_soft の shimx 呼出 | 94 回 / 26 種 (§4, --fix 時) | **91 回 / 26 種 (純リンク --fix 無しで同等に到達)** |
| R3 の GetProcAddress | §4.3 の miss 12 名 (UI言語 3 + shell32 序数 9) | **13 名トークン解決** (`lifttab: … -> token 0x7f0000xx`), miss 消滅 |
| survey (trace_soft_fix) | ok 800 / oob 41 / halt0 53 | **同値 (不変)** |
| ビルド 5 variant | mismatch/undefined/duplicate 0 | **0 (不変)** |

## 10. winstubs 結線 (#223 / ST-T3b) — `build.sh --ws`

2026-10-13 / 再現: `bash tools/m11/shimx_link/build.sh --soft --fix --ws && node tools/m11/shimx_link/ws_e2e.mjs tools/m11/work/shimx_link/m11_sx_plain_soft_fix_ws.cjs` (exit 0 = 全 PASS)。
`tools/startup/winstubs` `tools/shimx` は読取のみ (差分 0 行)。`tools/m11` の変更は `m11_simd2.py` (オプション追加のみ。既定出力は変更前と byte 一致) と本ディレクトリ。

| 要素 | 実装 |
|---|---|
| `--wrap` | `winstubs/wrap_list.txt` の現行 **12 本**を `-Wl,--wrap=<api>` で付与 (issue 本文の 16 本は CAB-214 follow-up で退役済み。受入は 12 本で解釈) |
| winstubs ソース | `winstubs/src/*.c` を `obj_ws/` にビルドしてリンク。weak 定義は `gen_link.py` の m11 nm に加えるため **GUI/audio スタブから自動除外** (gui スタブ 170→156 本 / lift_c 211→225) |
| `winstubs_init(0)` | `sx_winstubs.c` の `constructor(102)` (sx_cbboot の既定優先度より先)。`m11_boot_enter` より前に 1 回 = THostInstance 構築前の要件を満たす |
| cpuid 橋 | `m11_simd2.py --cpuid=winstubs` が `__asm_cpuid*` の実体を `winstubs_cpuid` 呼出へ置換 (`work/m11_simd_ws.c`)。既定 (`m11_build.sh`) は旧 CPUID_BODY のまま |
| 観測口 | `sx_ws_probe_{cpuid,g03,g12}` / `sx_ws_stat` / `sx_ws_loadlib_miss` を export (同一 wasm 内から `__wrap_*` 経由で呼ぶ) |

### 10.1 実測 (コミット 6dd00c2 でクリーンビルドから再現)

| 項目 | 実測 |
|---|---|
| リンク (`--soft --fix --ws`) | **signature mismatch 0 / undefined symbol 0 / duplicate 0**。所要 5.4 秒 (obj キャッシュ無し)。wasm 6,250,610 B (ws 無し 6,239,337 B) |
| `ws_e2e.mjs` | **PASS 19 / FAIL 0** (所要 0.76 秒)。うち **9 件は `[probe由来]`** (G03 ×4 / G12 ×3 / `WRAP.symbols_in_wasm` / `LOG.loadlib_miss_available`: `sx_ws_probe_*` か wasm バイト列検査で得た証拠で、lift の自然経路ではない)。残り 10 件 (BOOT ×2 + G05 ×7 + `WRAP.count`) のうち、boot 中に lift が自然に踏んだと言えるのは `BOOT.*` ×2 (到達点) と `G05.boot_cpuid_from_lift` (`winstubs_cpuid` 8 回) (他の G05 6 件も `sx_ws_probe_cpuid` 経由の値検査)。`BOOT.init_count_ge_18` / `BOOT.units_run_ge_17` は下限のみ (#236 / #307 で先へ進んでも落ちない) |
| G05 (lift `__asm_cpuid` 経由) | leaf1.EDX=`0x078bfbff` / cmov=1 / leaf1.ECX=0 / leaf7 AVX2=0。**boot 中に lift から `winstubs_cpuid` が 8 回呼ばれた** (自然経路) |
| G03 (`--wrap` 経由 probe) | engine ×2 + host exe とも signer_match=1。`WinVerifyTrust` 計数 6 (VERIFY+CLOSE ×3) |
| G12 (probe) | CreateProcessW 試行 1 / 成功 **0**、`WebView2Loader.dll` は NULL・GetLastError=126、loadlib_blocked=1 |
| `winstubs_loadlib_miss` | `["WebView2Loader.dll"]` を取得 (probe 由来) |
| `--wrap` シンボル | wrap_list 12/12 の `__wrap_*` が wasm 内に存在 |
| 回帰 `bash tools/startup/winstubs/winstubs.sh` | **exit 0 / ALL PASS (checks=1133) / boot 21/21 / リンク 67/67 (ST/MT) / shimx 回帰 ST・MT ALL PASS**。所要 10.1 秒。coexist_gui は gui 側ビルド物が無く SKIP |
| 既存 closure (`--soft --fix`, ws 無し) | 到達点は不変: init_count 18 / units_run 17/942 / threw=memory access out of bounds (CAB-231 停止点) |

### 10.2 未達・制限

- **boot は従来どおり unit #18 の OOB (CAB-231/#236) で止まる**。G03 署名・G12 CreateProcessW/WebView2Loader は FL が自然に呼ぶ前に停止するため、これらは同一 wasm 内の probe で `__wrap_*` 経由の挙動を測った (boot 中に自然経路で呼ばれた winstubs は cpuid の 8 回のみ。他の統計は boot 時点で 0)。
  「lift 実機で `winstubs_loadlib_miss` を取得し retval_table を実測校正」は、unit 18 の先へ進むまで**実施不可** (probe の 1 件は校正根拠にならない)。
- #103 引継ぎ 3 点のうち未着手: (1) `m11_genstubs.py` の除外リストへの pump API 追加は、`shimx_link` 系が genstubs の `m11_winstubs.c` を使わず pump TU も未リンクのため**現構成では不要** (pump を closure に入れる #102 で必要)。(2) `pump_ring_addr()` → `new PumpRing(...)` 結線も #102。(3) 時計較正は ctrl 単体を使わない — 本結線は時計に触れない。
- `--trace` と `--ws` の併用は未検証 (trace_wrap の改名 IR は ws の定義済み名と未突合)。リンクのみ確認 (`--trace --soft --fix --ws`: mismatch 0 / undefined 0 / duplicate 0)、実行は未確認。trace の obj / `BOOT` パスは `$WSUF` 付きで WS 有無のキャッシュを分離済み (`boot_trace_fix.o` 4,282,726 B と `boot_trace_fix_ws.o` 4,282,642 B は別内容)。

### 10.3 再測定 (2026-10-14, 測定 commit `e7491b4f`): 閉包リンクの復旧と現 IR での boot 到達点

§10.1 の値は旧 IR (`work-m11` の `boot_final3.ll`, 2026-10-10 生成) での測定。以下は現 main のコードで IR を作り直した結果。

| 項目 | 実測 |
|---|---|
| 修正前 (origin/main `580dd294`) | `build.sh --soft --fix --ws` が exit 1。`emcc: error: undefined exported symbol: "_sxt_count" [-Wundefined] [-Werror]`。`--trace` 専用の `sxt_*` (`trace_rt.c`) を plain の EXPORTS に入れていたため (emsdk 6.0.12 は未定義 export を -Werror 扱い) |
| 修正 (`e7491b4f`) | `sxt_*` の EXPORTS を `[ $TRACE = 1 ]` のときだけ追加 (`build.sh` 2 行) |
| リンク `--soft --fix --ws` | exit 0 / signature mismatch 1 / undefined 0 / duplicate 0 (3.8 s, obj キャッシュ有) |
| リンク `--soft --fix` (ws 無し) | exit 0 / mismatch 1 / undefined 0。plain の mismatch は §10.1 (旧 IR) で 0、再生成 IR で 1。変化の原因は未確認 |
| リンク `--trace --soft --fix` | exit 0 / mismatch 1 / undefined 0 |
| mismatch 1 の出所 | `midiOutShortMsg`: 再生成 IR は (i64,i32)→i32、`tools/shimx/src/midi_conv.c:163` は (HANDLE,DWORD)→UINT。IR 側 i64 と shimx 定義 i32 の型不一致 (REPORT_N1050 の trace 版 mismatch 1 と同じ組)。本 PR は shimx を変更していない (`git diff origin/main...HEAD -- tools/shimx` 0 行)。起票先 #1628 (SHX-T25, OPEN) に mismatch 1 の事実をコメント済み |
| EXPORTS 変更の影響 (確認した事実) | 本修正の差分は `build.sh` の `_sxt_*` 13 本を `--trace` のときだけ EXPORTS に足す分岐のみ (`git diff origin/main...HEAD -- tools/m11/shimx_link/build.sh` で確認)。export 指定は各 object の関数型を変えないため、型照合 (mismatch) の入力にならない。同一 IR で trace (`_sxt_*` あり) と plain (なし) が共に mismatch 1 だが、trace は改名 IR の別ビルドなので export の有無だけを変えた比較ではない。修正前後の件数比較は、修正前の plain が exit 1 で件数行を出していないため未実施 |
| IR 再生成 | `M11_PE=<fl-win64 の extracted/block00031_PE.bin> bash tools/m11/m11_gen_ir2.sh` → OK (490,735 行, 45 s)。続けて `bash tools/m11/m11_build.sh` → OK (wasm-ld signature mismatch 0 / undefined 0, 22 s)。`m11_e2e.sh --full` は `m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` (素材に無い) を要求して止まるため使えなかった。起票先: #223 へのコメント (親への提案。既存記録 `tools/m11/REPORT_N1004.md` の「PM 起票を要求」行と同じ論点。子 issue は作らない) |
| `ws_e2e.mjs` | PASS 19 / FAIL 0 (0.35 s) |
| boot 到達点 (ws 込み, 現 IR) | `boot_stage 1 / init_count 18 / units_run 17/942 / threw null / rc "1"`。§10.1 の OOB (`memory access out of bounds`) は消えた |
| boot 到達点 (ws 無し, 同 IR) | 同じ (`units_run 17 / threw null / rc "1"`)。ws の有無で到達点は変わらない |
| `BOOT_WS_STATS` (ws 込み) | `cpuid 8` (lift の自然経路) / `loadlib_calls 0` / `loadlib_miss 0` / `createprocess 0` / `pump_calls 0` |

**結論**: 閉包リンクは現 main で再びリンクできる (修正前は exit 1)。ただし現 IR の boot は unit 17 で `rc=1` により停止し、FL の自然経路で LoadLibrary が 1 回も呼ばれない。`winstubs_loadlib_miss` の lift 実機取得 (受入) は未達。`LOADLIB_MISS ["WebView2Loader.dll"]` は引き続き probe 由来。

**差分確認 (測定 commit から HEAD まで・コード範囲)**: `git diff e7491b4f HEAD -- tools/m11/shimx_link/build.sh tools/m11/shimx_link/*.c tools/m11/shimx_link/*.py` の出力は 0 行 (本節は REPORT のみ変更)。

## 11. 旧 main の link 失敗の修正と `--midi` の winstubs 結線 (#179 SHX-T6)

- 結論: 旧 main (`46c92356`) で実測した 4 variant (既定・`--ws`・`--midi`・`--ws --midi`) は全て `undefined exported symbol: "_sxt_count"` で rc 1 だった。`sxt_*` を `--trace` 限定にする修正は #2732 (`e7491b4f`、§10.3) で main に入り済み。`--midi` の e2e と `--ws --midi` の boot 基準は測定 commit `397c4161` で確認 (`midi_e2e.mjs` 3/3 PASS、`ws_e2e.mjs` PASS 19 / BOOT init 18 / units 17/942)。
- 修正前後の表・e2e 実測・起動 KPI・残件: `tools/m11/shimx_link/REPORT_APPENDIX_179.md` (§11.1〜§11.4)。

## 12. midiOutShortMsg の HANDLE 幅 (#1628 SHX-T25): IR 側の正規化 (要約)

- 結論: IR 側の宣言と呼出しを i32 に揃える正規化 (`sx_handle_norm.py`、`build.sh` 2c) で、plain / trace の `signature mismatch` 1 → 0 (測定 commit `e0e35f9a`)。切り詰めは HMIDIOUT の値を変えない。
- 測定値・修正前の出典と IR 同一性の限界・e2e の範囲: 付録 `REPORT_APPENDIX_1628.md` §12 が正本。fail-closed 化 (`763a599d`) は未測定のため本 PR から外した (付録 §12.4)。
- 未解決の起票先: IR 生成側の根本 → #2839 `[SHX-T31]`。fail-closed 化の復元と HEAD での再測定 (942 survey・plain の boot 到達点を含む) → #2877 `[SHX-T32]`。
