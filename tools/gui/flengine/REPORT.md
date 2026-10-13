# REPORT — GUI-3 (#174): 実 FLEngine の lift に GUI shim を結合する

**判定: 部分達成 (受入条件 1 は未達、条件 2 は達成。PR は `Refs #174`)**。実 FLEngine (m11 closure, `FLEngine_x64.dll` の 7,421 関数 lift) に `tools/gui` shim を全 TU `-pthread` でリンクし、
**自然起動 (DllMain attach) で最初の GUI API (`LoadStringW`) が shim に到達**した。942 unit の隔離 survey では GUI API **23 種**が shim に到達 (実装済み 22 / fail-fast stub 1 = `LoadImageW`)。
一方 **`RegisterClass*` / `CreateWindowEx*` は自然起動でも survey でも未到達** (通常起動は unit #23 で Halt0、#134 / #490 の先)。実 WNDCLASS を JS から指向呼出した場合は
`RegisterClassW` ×2 が shim に届き、`TApplication` の窓 (hwnd 31bit) が生成できる。再現: `bash tools/gui/flengine/e2e.sh` (gate 12 + ネガコン 5。FAIL なら exit 1)。

既知類型との関係: 該当 `docs/DEFECTS.md` D1b 系 (比較が定数に畳まれ分岐が誤る) の入力側変種 1 件 (§5-2, 新規行案あり) / D1 系は m11 REPORT §10 と同根。他は該当なし。

## 1. 結論と実測

検証コード: `f530d37` (`main` (`3d86c3f`) を取り込んだ merge commit。`e6f2d7c` の S1 修正を含む)。結果 JSON はこのコードで e2e を実行して再生成したもの。環境: runner 4 vCPU, node v22.23.3, emcc ([EMSDK], pin 6.0.12)、retdec ([RETDEC])、素材 work-m11 + fl-win64 (`docs/REFERENCES.md` の [WIN64])、x86_64-w64-mingw32-gcc (apt-mingw)、pefile / capstone (pip)。e2e の IR は work-m11 素材の `boot_final.ll` (`m11_gen_ir2.sh` 済み) を使い、本 e2e 内では IR を再生成しない。

**現 HEAD の判定: 10/12 (FAIL 2 件、n=3 で再現)**。FAIL は B1 (起動の回帰) と S2 (fail-fast の STUB 判定)。原因は §2-3 の「main 取り込みによる baseline の変化」。判定の期待値は変えていない (PM 判断待ち、§7)。

| 項目 | 実測 (n=3 の範囲) | 定義 / 分母 |
|---|---|---|
| リンク | wasm-ld signature mismatch **0** / undefined **0** / duplicate **0** (ff・soft 両ビルド) | `build.sh` のリンクログを grep |
| GUI declare ↔ adapter | IR の GUI declare **177** = adapter **177** (実装 158 / stub 19)、突合不一致 c=0 d=0 | `integ/gen_adapt.py --ir boot_final.ll` |
| 起動の回帰 | shim 有り/無し (同一 IR) で **units_run 22 / dllmain_done true / GetMem 33 / FreeMem 20 / icall_miss 0 が一致** | baseline = `m11_run.mjs` (GUI 3 本は m11_win.c の暫定 stub) |
| survey の回帰 | soft ビルド (stub は 0 返却) の survey が baseline と **ok 865 / noproc 1 / miss 47 / trap 29 が一致** (S1 PASS、n=3)。trap 内訳 halt0 7 + OOB 19 + fail-fast 3 (SystemParametersInfoW 未対応 action, IMPL 側) | 942 unit 隔離 (`m11_survey.mjs` と同じ unit 別 VA 予算 256 MB, #513) |
| 最初の GUI 呼出 (自然起動) | **`LoadStringW` ×4 → shim (IMPL, P1)**。DllMain attach の 22 unit 内 | `GUI-REACH` 行 (`boot.json`) |
| survey で shim に到達した API | **23 種** (IMPL 22 / STUB 1)。§3 | `survey_soft.json` の reach |
| fail-fast ビルドの survey | ok 865 / noproc 1 / miss 47 / trap 29。fail-fast は 3 unit (`LoadImageW` 1 = P2 STUB、`SystemParametersInfoW` 2 = IMPL 側の未対応 action) | `survey_ff.json` |
| 起動の baseline (main 取り込み後) | `m11_run.mjs` は unit 52 で `memory access out of bounds` (shim 無しでも同じ)。旧 22 unit 停止から変化 | `baseline_boot.json` |
| `RegisterClass*` / `CreateWindowEx*` の自然到達 | **0** (起動・survey とも) | judge の INFO 行 |
| 指向呼出 (§4) | `RegisterClassW` ×2 成功 (atom 0xC001 / 0xC002)、`TApplication` 窓 hwnd `0x210000e` (< 2^31)、WNDPROC 4 引数が `m11_icall` 経由 | `probe.json` |

## 2. 変更と成果物

| パス | 内容 |
|---|---|
| `tools/gui/flengine/build.sh` | `m11_build.sh` の除外リスト方式で結合ビルド。shim `.o` を `build_objs.sh --reach --ir` で作り、m11 側 C (shim/rt/win/ov/simd/fnstubs/data/winstubs/boot) を **`-pthread` で再コンパイル**して `emcc` リンク。`--soft` (STUB は 0 返却)、`--plain` (到達ログ無し) |
| `flengine_glue.c` | 起動前 constructor: `gui_headless_attach` (host_ready=1)・out ring は host 不在なので満杯時に破棄・icall hook = `m11_icall`。`--wrap=gui_failfast` で fail-fast を JS 例外に (§2-3) |
| `gen_thunks.py` | PE の import thunk (`jmp [IAT]`) のうち `DefWindowProc{A,W}` の LVA を C 表化 (§4)。pefile を使う |
| `run.mjs` / `probe.mjs` | 実行ハーネス (通常起動 / `--survey` / 指向呼出)。JSON を出力。`--survey` は m11_survey と同じ unit 別 VA 予算 (256 MB) を掛ける (S1 の差を解消) |
| `judge.py` / `e2e.sh` | gate 12 + 情報行。ネガコン 5 本を「期待した FAIL 行が出ること」まで検査。e2e は `tools/m11` を `work/flengine/snap/` に複製し、複製側で baseline・build を回す (元の `tools/m11` は書き換えない) |
| `results/*.json` | 実測の機械可読。`reach_expected.json` は R2 gate の到達 floor |
| `tools/gui/src` ほか | `GetDC(NULL)` の画面 DC 実装 (§2-4)、`test/selftest.c` に回帰 assertion、`gen_api.py` が `IMPORTS.md` に「実到達」列と §4 を出力 |

### 2-1. 結合で踏んだ問題と対処

| # | 症状 (実測) | 原因 | 対処 |
|---|---|---|---|
| 1 | `LinkError: memory import has 256 pages which is smaller than the declared initial of 4608` | `-pthread` では共有メモリを JS 側が `INITIAL_MEMORY` で作る。`-Wl,--initial-memory` は効かない | `-sINITIAL_MEMORY=0x12000000 -sMAXIMUM_MEMORY=0x72000000` (< 2 GiB, INTEGRATION §4-5) |
| 2 | m11 の `m11_win.c` と shim が `LoadStringW` / `MessageBoxA` / `MessageBoxW` を二重定義 | m11 が user32 の 3 本を暫定実装 | m11 を変えず `-DLoadStringW=m11_win_LoadStringW` 等で改名コンパイル (shim 定義が勝つ) |
| 3 | shim の `gui_failfast` は `abort()` で wasm ごと止まる | 隔離 survey ができず「最初の 1 本」しか分からない | `-Wl,--wrap=gui_failfast` → 同じ `FAIL-FAST:` 行を出して JS 例外で脱出 (m11 の Halt0 と同流儀)。`--soft` は STUB を 0 返却にして後続の API まで集める計測用 (shim 本体は無変更) |
| 4 | `GetDC(NULL)` が fail-fast (survey の 2 unit。後続の `GetDeviceCaps` / `CreatePalette` / `GetStockObject` / `LoadIconW` が見えない) | shim は画面 DC 未実装 | `gdi_get_screen_dc()` = 既定 1x1 ビットマップ選択済みのメモリ DC (既存 `CreateCompatibleDC` と同じ方式。描画は捨てる) を追加。native selftest は全件通過 (現 HEAD 433 passed / 0 failed) |
| 5 | `TApplication` の `CreateWindowExW` が NULL | `WNDCLASS.lpfnWndProc = 0x24920` は **`DefWindowProcW` の import thunk** (`ff 25 …`) で lift closure の関数ではない → `m11_icall` が miss → WM_NCCREATE=0 | `gen_thunks.py` の表を glue の icall hook で先に引き、shim の `DefWindowProcW` へ。thunk は PE 全体で 1 本 (`0x24920`) |
| 6 | 指向呼出でない survey の S1 が FAIL (soft 828/1/46/67 対 base 864/1/46/31、取り込み前の測定) | `run.mjs --survey` が unit 別の VA 予算 (`_m11_va_unit_begin` / `_m11_set_va_unit_budget`) を掛けておらず、VirtualAlloc の累計で OOM 扱いになる unit が増えた | `m11_survey.mjs` と同じ 256 MB 予算と unit ごとの `_m11_va_unit_begin()` を `run.mjs` に入れた (commit `e6f2d7c`)。修正後 S1 PASS (864/1/46/31) |

### 2-2. ABI チェックリスト (INTEGRATION.md §4) の実機確認

| # | 項目 | 結果 |
|---|---|---|
| 1 | `-sGLOBAL_BASE` ≥ 0x10000 | `0x10000000` で link。`gui_shared_ptr` = 271,662,080 (probe の gate P2) |
| 2 | ハンドル 31bit | `GetDC(0)` = `0x120000f`、`TApplication` hwnd = `0x210000e`、`RegisterClassW` atom は 0xC001+ |
| 3 | 全 TU `-pthread` | wasm-ld エラー無し (m11 側 15 TU + shim 7 TU) |
| 4 | WNDPROC 4 引数 | `gui_call4` → `m11_icall(t,a,b,c,d,0,0,0,0)`。`CreateWindowExW` ごとに 2〜4 回呼ばれる |
| 5 | メモリ上限 < 2 GiB | max 0x72000000。survey 通算で `Cannot enlarge memory` (上限到達) が出る = m11 REPORT §10 の VirtualFree no-op leak と同じ現象 (回数は baseline 側を未計数) |
| 8 | UI スレッドのスタック量 | **未実測** (GUI スレッドは起動していない。結合は node 主スレッド) |

## 3. 実到達 API (自然起動 + survey; 回数は `survey_soft.json`)

P は `IMPORTS.md` の優先度。起動 = DllMain attach で到達、他は survey (942 unit 隔離) で到達。

| 状態 | API (P) |
|---|---|
| 起動で到達 | `LoadStringW` (P1) ×4 |
| survey で到達・実装済み (IMPL 22 のうち起動分を除く 21) | `EnumFontFamiliesExW` (P2), `GetDC` (P0), `GetDeviceCaps` (P0), `ReleaseDC` (P0), `GetStockObject` (P1), `LoadIconW` (P1), `LoadCursorW` (P1), `CreatePalette` (P2), `MessageBoxA` (P2), `RegisterWindowMessageW` (P0), `RegisterClipboardFormatW` (P0), `GetClipboardFormatNameW` (P1), `GetSystemMetrics` (P0), `FindWindowW` (P1), `GetKeyboardLayout` (P0), `CharLowerBuffW` (P1), `EnumDisplaySettingsW` (P1), `GetClipCursor` (P0), `EnumDisplayMonitors` (P1), `SystemParametersInfoW` (P0), `GetMonitorInfoW` (P1) |
| survey で到達・**fail-fast stub** | **`LoadImageW` (P2)** — 1 unit (`survey_ff.json` の `failfast_units`)。stub のまま実到達 → **実装必須へ昇格** |
| survey で到達・IMPL だが **fail-fast** | `SystemParametersInfoW` (P0) — 2 unit (`survey_ff.json`)。未対応 action (`gui_core.c` の `SystemParametersInfoW`) で IMPL 側が落ちる | 未対応 action の実装 (§7) |

- `EnumFontFamiliesExW` は head の shim で IMPL (`tools/gui/src/gui_gdi.c`)。fail-fast 経路は無く、`failfast_units` に出ない。
- **IMPORTS.md の P 分類への入力** (`IMPORTS.md` §4 に自動出力): `LoadImageW` は stub のまま実到達 → 実装必須へ昇格。`CreatePalette` / `MessageBoxA` / `LoadImageW` は P2 だが実到達 → P1 以上へ昇格候補。
  P0 の未到達は現 m11 到達段が浅いため (SendMessage / PostMessage / BitBlt / SelectObject ほか) 「不要」の根拠にはならない。
- `MessageBoxA` は Delphi RTL の `Runtime error 0` ダイアログ (unit の Halt0 経路)。shim は host 無しなら即 IDOK。
- `LoadStringW` は survey 通算で多数回 (実行ごとに数回ずれる)。1 unit が資源 ID を回している疑い (shim は資源供給 hook 未接続で常に 0 を返す)。**未調査** (§7)。
- `SystemParametersInfoW` の未対応 action は IMPL 側が fail-fast する (STUB ではないため S2 の対象外。`survey_soft.json` の `failfast_units` は 3 件)。judge の S2 は「fail-fast した API は soft で STUB」を要求するため、この IMPL 由来の fail-fast で FAIL する (§7)。
- icall hook 経由の呼出: survey で 1 回 (推定: `EnumDisplayMonitors` の callback)。target が closure 外で `m11_icall` miss (survey の icall_miss は baseline 46 → 47)。

## 4. 指向呼出 (`probe.mjs`; 自然到達ではない)

自然起動は `RegisterClass*` に届かないため、DllMain attach 後に JS から lift 済み関数を直接呼ぶ。**呼出元が JS である点で自然到達とは区別する**。
実 FLEngine の RegisterClassW 呼出点は IR 全体で 5 (`lift_fnmap.py --ir`: `function_425260` (= RegisterClassW ラッパ)・`function_52a7f0`・SetWindowLongPtrW 2・SetClassLongPtrW 1)。
`function_425260` の呼出元は `function_71dd80` と `function_867e10`。

| WNDCLASS (PE 実値) | lpfnWndProc | RegisterClassW | CreateWindowExW |
|---|---|---|---|
| `TLightweightLayeredControl` (`function_71dd80` が渡す) | 0x31dd10 (**closure 外**) | atom 0xC001 | **NULL** (WM_NCCREATE の WNDPROC が `m11_icall` miss ×2) |
| `TApplication` (`function_867e10` が渡す) | 0x24920 (DefWindowProcW import thunk) | atom 0xC002 | **hwnd 0x210000e** (WNDPROC 4 回, thunk 経由で shim の DefWindowProcW) |
| `TPUtilWindow` (`function_52a7f0` = AllocateHWnd 相当) | 0x24920 | **呼ばれない** | NULL (§5-2) |

## 5. 未達の理由と発見

1. **受入条件 1 (最初の `RegisterClass*`/`CreateWindowEx*` が shim に自然到達) が未達**: 通常起動は unit #23 (`0x467f00`) の Delphi 例外 → Halt0 で 22 unit で止まり (m11 REPORT §10)、survey の unit 単独実行にも該当呼出が無い。#134 (M11-N5) / #490 (M11-N15) の先。本 PR は「到達したときの受け皿」(link / ABI / 署名 / WNDPROC 解決 / 到達ログ) を実機で通した段階。
2. **新規 lift 欠陥 (`function_52a7f0`; Delphi `AllocateHWnd`)**: 機械語は `GetClassInfoW(…, &TempClass)` の後 `cmp [rbp+0x70], DefWindowProc` (`TempClass.lpfnWndProc` と比較) で `RegisterClass` の要否を決める。
   IR では `[rbp+0x70]` の load が `%1 = xor i64 0, 0` (定数 0) に化け、比較が常に false に畳まれて「未登録 (GetClassInfoW=false)」でも `RegisterClassW` を**飛ばす**。後続の `CreateWindowExW` はクラス未登録で NULL。silent miscompile。
   `GetClassInfoW` が書く escape 済み stack local の読出し脱落で、既存 ldfix の F1 (load_dropped) は直していない。DEFECTS 行案 (起票先は PM 判断):

| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| `if not registered or (cls.lpfnWndProc <> DefWindowProc) then RegisterClass` が未登録でも登録しない | callee (`GetClassInfoW`) が書く 72B 構造体 (stack_var) のフィールド load が脱落し `xor i64 0,0`、比較が定数に畳まれる (D1b の入力側) | `function_52a7f0` で `RegisterClassW` が呼ばれず `CreateWindowExW` が NULL | IR の `xor i64 0, 0` が `icmp` の被演算子になっている | escape する stack_var からの load を ldfix で復元 (ldfix 系の PM 起票依頼。既存 F1 の拡張) |

3. **WNDPROC が closure 外** (`0x31dd10` ほか): WNDCLASS が `.data` の静的実体で WNDPROC を持つ場合、call graph に現れず lift されない (m11 REPORT §2-6 と同根)。`m11_extra_seeds.txt` 相当の seed を WNDCLASS 走査で自動生成する pass が要る。
4. `GetDC(NULL)` 未実装は実 FLEngine に当たって初めて分かった shim の穴 (selftest は mingw 製 PE の範囲で未検出だった)。

## 6. 検証

実行: `bash tools/gui/flengine/e2e.sh` (前提: `tools/m11/work/` (work-m11 素材 + `boot_final.ll`)、`FL_WIN64_DIR` (fl-win64 展開先)、`x86_64-w64-mingw32-gcc` (apt-mingw; `gen_api.py` の arity 表)、`pefile` (pip))。`RETDEC_DECOMPILER` は `test/pe_image_e2e.sh` が使う ([RETDEC])。

| gate | 内容 |
|---|---|
| L1×2 / A1 | link の sigmismatch / undefined / duplicate が 0 (ff・soft) / adapter 数 = declare 数 かつ c=d=0 |
| B1 / S1 | 起動・survey が baseline と一致 (§1) |
| R1 / R2 / S2 | 最初の GUI API が IMPL で shim に到達 / survey の到達集合が committed floor (19) を包含 / fail-fast した API は soft で STUB |
| P1〜P4 | 指向呼出で RegisterClassW×2・CreateWindowExW 到達 / `gui_shared_ptr` ≥ 0x10000 かつ 31bit ハンドル / WNDPROC が hook 経由 / TApplication の窓が生成される |

ネガティブコントロール (全て「期待した FAIL 行が出る」まで検査。judge のクラッシュを FAIL 確認と誤認しない):

| NC | 壊し方 | 結果 |
|---|---|---|
| N1 | 到達ログ無し (`--plain`) ビルドの起動を判定 | R1 FAIL (reach 0 件), exit 1 |
| N2 | baseline の units_run 期待値を 23 に | B1 FAIL, exit 1 |
| N3 | 到達 floor に未到達 API `NoSuchGuiApi` を 1 つ追加 | R2 FAIL (floor 20 / reached 23), exit 1 |
| N4 | survey の 1 unit を ok→trap に改竄 | S1 FAIL, exit 1 |
| N5 | `GetDC(NULL)` を元の fail-fast に戻した shim で native selftest | `FAIL-FAST: unimplemented Win32 API: GetDC`, exit 134 |

**実測 (現 HEAD = 本 REPORT を含む commit の直前までのコード + 再生成結果, runner 4 vCPU)**:

- `bash tools/gui/flengine/e2e.sh` (`f530d37`, n=3): rc 1 / **judge 10/12 (FAIL: B1・S2、3 回とも同一)**。所要 **97 / 95 / 92 秒** (`6/6 done` 行の load: 1.05 / 0.90 / 1.09)。
  - PASS 10: L1 (ff・soft 各 0/0/0)、A1 (declare 177 = adapter 177、impl 158 / stub 19、c=d=0)、R1 (`LoadStringW` IMPL)、R2 (到達 27 ≥ floor 19)、S1 (soft 865/1/47/29 = base)、P1〜P4 (atoms −16383/−16382、hwnd 0x210000e、screen DC 0x120000f、hook calls [2,4])。
  - FAIL B1: `units_run` 52 = base 52、`GetMem` 560 / `FreeMem` 20 / `icall_miss` 5 は一致。ただし shim 版の `boot_threw` が `memory access out of bounds`。baseline (`m11_run.mjs`) も同じ unit 52 で同じ `boot threw: memory access out of bounds` を出す (`snap/m11` で単独実行して確認)。`m11_run.mjs` は `boot_threw` を JSON に出さないため、B1 の比較式が食い違う。
  - FAIL S2: ff survey の fail-fast API = `LoadImageW` (STUB) + `SystemParametersInfoW` (IMPL の未対応 action)。soft の STUB 集合は `LoadImageW` のみ。S2 の期待 (fail-fast は STUB) と `SystemParametersInfoW` が合わない。
  - ネガコン 5/5 は期待どおり FAIL (N1 R1 / N2 B1 / N3 R2 / N4 S1 / N5 selftest rc 134)。pe_image parity P1・P2・N1〜N3 PASS (exit 0)、`pe_image_e2e` P1・P2・N1・N2 PASS。
  - 選択 (§7): 判定の期待値は変えていない。B1 と S2 の修正は PM 判断。
- 前回 (`e6f2d7c` / `e391713`、main 取り込み前) の測定: judge 12/12、所要 108 / 109 / 113 秒。main 取り込みで baseline (`units_run` 22 → 52) が変わったため、旧値は現 HEAD では無効。
- `bash tools/gui/e2e.sh` は本 run では未再実行 (時間の都合)。前回値は取り込み前のもの。

個別の単発計測 (開発中・取り込み前): baseline survey 16.9 秒 / 結合 build 10.6〜17.0 秒 / 結合起動 0.371 秒 / 結合 survey 18.2〜24.1 秒。
`git status --porcelain -- tools/gui` は commit 後クリーン (results と IMPORTS.md は再生成しても差分 0)。

受入条件 2 (`bash tools/gui/e2e.sh` ALL PASS 維持): 本 PR の shim 変更 (`GetDC(NULL)`) 後に実行し ALL PASS。`selftest` 件数は現 HEAD で 433 passed / 0 failed。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `RegisterClass*` / `CreateWindowEx*` の自然到達 (#134 / #490 の先) | 受入条件 1 | #134 / #490 に依存。到達後に `bash tools/gui/flengine/e2e.sh` の INFO 行が変わる (R2 floor を更新) |
| `function_52a7f0` の `TempClass.lpfnWndProc` load 脱落 (§5-2) | AllocateHWnd 経路 (TPUtilWindow = Timer / 非同期 window) が全滅 | ldfix 系の子チケットを PM が起票 (本 REPORT の DEFECTS 行案) |
| WNDCLASS 静的実体の WNDPROC を closure seed に追加する pass (`TLightweightLayeredControl` 0x31dd10 ほか) | その class の窓生成が NULL | m11 / icall 系で PM が起票 (#90 の間接 call 復元と近い) |
| `LoadImageW` 実装 (P2 STUB、survey 1 unit が fail-fast) | survey の 1 unit が fail-fast | GUI-2 系 (P2 stub 昇格, #174 に所見) |
| `SystemParametersInfoW` の未対応 action (IMPL 側 fail-fast、survey 2 unit) と judge S2 の期待値 | judge S2 が FAIL。IMPL 由来の fail-fast を STUB 判定と分けて扱うか、action を実装するかの判断が要る | PM 判断 (GUI-3 #174 の子チケット候補) |
| B1 の `boot_threw` 比較 (shim 版 OOB 52 / baseline は JSON 未記録) と main 取り込みによる m11 起動の unit 52 停止 | judge B1 が FAIL。shim の回帰ではない (baseline と同じ停止) | PM 判断 (m11 #134 系と judge の比較式) |
| `LoadStringW` 多数回の unit 特定と資源供給 hook (`gui_set_resource_provider` ← shimx / PE .rsrc) の接続 | LoadStringW が常に空文字 | #174 に所見 / GUI-2 または shimx |
| `tools/m11` の `m11_e2e.sh` と `m11_gen_ir2.sh` は PE パスが固定 (`FL_WIN64_DIR` 非対応) | runner では ldfix が黙ってスキップされ数値が変わる (本 e2e は `FL_WIN64_DIR` で回避) | m11 に `FL_WIN64_DIR` 参照を提案 (#132 の未解決と同件) |
| 受入「`__pe_image` を m11_data_gen 方式の data 実体化へ統合」(スコープ 3) | **#566 (GUI-12) で対応済み → §8**。残り: RetDec C 経路に実 FLEngine 規模の PE を通した実測は無い (§8-4) | #566 |
| 実ブラウザ host 結線 (`GuiHost.attach`・FL ワーカ化・UI スレッドのスタック量 §2-2 #8) | node の headless host のみ。描画 (#32) は別 | #32 / #121 |

## 8. `__pe_image` の m11_data_gen 方式統合 (#566 / GUI-12; #174 スコープ 3)

**結論**: RetDec C 経路 (`tools/gui/lift/gui_lift_post.py`) の `__pe_image` を、m11 と同じ .reloc DIR64 補正規則の共通モジュール `tools/gui/lift/pe_image.py` に統合した。実 FLEngine PE で m11_data_gen.py の出力とバイト一致 (§8-3)。

### 8-1. 設計
経路が 2 つあり、データの置き方が違う。FLEngine の結線 (本 REPORT §1〜6) は m11 IR 経路で、`__pe_image` は使っておらず、元から m11_data.c / m11_image.bin (LVA 固定敷設) である。`__pe_image` は RetDec C 経路 (テスト PE・プラグイン DLL 向け) だけにある。

| | m11 経路 (FLEngine) | RetDec C 経路 |
|---|---|---|
| 敷設先 | linear memory の固定アドレス LVA = RVA + LB | C の静的配列 `__pe_image` (アドレスはリンク時まで不定) |
| イメージ内ポインタ (.reloc DIR64) | 静的に書換え (`m11_data_gen.py`) | **従来は未補正**で生 VA のまま (§8-2) |
| 統合後 | 変更なし (m11 は読取専用) | `pe_image.runtime_image` が再配置テーブル (image offset) を出し、`gui_lift_entry()` 先頭の `__pe_image_fixup()` が `delta = &__pe_image[0] - ImageBase` を加算 |

共通にした規則 (`pe_image.py`): DIR64 の走査 (page==0 / 不正 block で打切り)。lva モード (`rebase_sections`) は m11_data_gen.py と同じ境界 `lo <= r <= lo + len(sd) - 8` (末尾 slot を含む)。runtime モードの補正対象は `base < v < base + span` で、.text を指す値 (関数 VA) は fnmap の鍵なので補正しない。

### 8-2. 実測した既存欠陥 (統合前)
- イメージ内ポインタが生 VA (`0x14000xxxx`) のまま: 文字列ポインタ表・配列要素へのポインタ・連結リストを持つテスト PE を lift すると**クラッシュ** (補正を出さない `--no-pe-reloc` で再現, rc 139)。従来の gui_app.c は data にイメージ内ポインタを持たないので e2e では出なかった。
- 配列 global (`char *g3[4] = {…}; // 0x…`) は `#define` されず、gcc が `gN undeclared` で落ちる。→ 配列 lvalue (`*(T (*)[N])(__pe_image+off)`) のマクロにした。

### 8-3. 検証 (`tools/gui/flengine/pe_image_parity.py`, `tools/gui/test/pe_image_e2e.sh`)

| 検査 | 結果 (実測) |
|---|---|
| P1 共通モジュール == m11_data_gen.py 出力 (実 FLEngine PE, LB=0 / 0x10000) | 一致 (.data 2,359,304 B / .rdata 69 B)。DIR64 全 278,531、補正 **10,284** (.data) / 0 (.rdata) |
| runtime 方式の内訳 (INFO; .text 外のスロット, 実測) | 補正対象 2,354 (全て .data) / .text 宛で非補正 8,044 (.data 7,930 + .didata 114) / image 外 0。lva 方式の .data 補正 10,284 との突合: 2,354 + 7,930 = 10,284 で一致 |
| RetDec C 経路の実行テスト (`pe_image_app.c`: 文字列表 / 配列要素ポインタ / 連結リスト / 関数ポインタ表) | lift の戻り値 = host gcc 直ビルドの戻り値 (34622010)。補正スロット 7 |

旧 P3 (`tools/m11/work/m11_data.c` との比較) は e2e の判定から外した。その m11_data.c は #572 より前に生成されたもので、末尾 slot を補正していない (`<` 規則の出力)。現行 m11_data_gen.py の出力との一致 (P1) を判定基準とする。

ネガティブコントロール (全て「一致してはならない」を要求。判定が不合格なら非 0): parity N1 補正値 1 bit 破壊 → FAIL / N2 補正ゼロの実装 → FAIL / N3 セクション欠落 → FAIL、pe_image_e2e N1 `--no-pe-reloc` → クラッシュ (rc 139) / N2 再配置表を 1 件ずらす → クラッシュ (rc 139)。

### 8-4. 未達・未実測
- 実 FLEngine 全体 (7,421 関数) を RetDec C 経路に通した実測は無い (FLEngine は m11 の LLVM IR 経路。RetDec C に通すのは規模上非現実的) ため、実 PE での検証は「規則の一致 (バイト比較)」までで、RetDec が出す `gN` 分割の実 FLEngine 上の挙動は未検証。
- runtime 方式の補正対象は「値が SizeOfImage 内を指し、かつ .text 宛でない」DIR64。image 外を指す値は 0 件 (実測)。`.didata` の DIR64 114 件は全て .text 宛で、m11 (.data/.rdata のみ敷設) は補正しない。
- `__pe_image` は 1 配列で SizeOfImage 全体 (FLEngine なら 25 MiB 超) を抱えるため、大きな PE には向かない (20 MiB 超 blob を commit しない規約。生成物は work/ 側)。

### 8-5. m11_data_gen.py の境界条件 (解消)
`m11_data_gen.py` は当初 `lo <= r < lo + len(sd) - 8` で DIR64 スロットを選んでおり、セクション末尾の 8 バイト slot (実 FLEngine の `.data` 末尾 RVA `0x11e5000`、値 `0x425f00` = .text 宛の関数ポインタ) が補正されなかった。
`#572` (`10c8278`) で `<=` に修正済み。本 PR の `pe_image.py` lva モードも同じ `<=` に揃えた (`c39ca16`)。これにより P1 が PASS し、補正件数は m11 と同じ 10,284 (現 HEAD で再確認: `pe_image_parity.py` exit 0)。

## 9. 未解決 (#566)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec C 経路で実 FLEngine 規模の PE を通した実測なし (§8-4) | `gN` 分割の実機挙動が未検証 | 範囲外 (FLEngine は m11 IR 経路) |

範囲外: 実ブラウザ・Canvas 描画、audio、UI スレッドのスタック量、`gui_reach` の性能影響 (INTEGRATION §4-12 の未計測は継続)。
