# REPORT — GUI-3 (#174): 実 FLEngine の lift に GUI shim を結合する

**判定: 部分達成 (受入条件 1 は未達、条件 2 は達成。PR は `Refs #174`)**。実 FLEngine (m11 closure, `FLEngine_x64.dll` の 7,421 関数 lift) に `tools/gui` shim を全 TU `-pthread` でリンクし、
**自然起動 (DllMain attach) で最初の GUI API (`LoadStringW`) が shim に到達**した。942 unit の隔離 survey では GUI API **23 種**が shim に到達 (実装済み 22 / fail-fast stub 1 = `LoadImageW`)。
一方 **`RegisterClass*` / `CreateWindowEx*` は自然起動でも survey でも未到達** (通常起動は unit #23 で Halt0、#134 / #490 の先)。実 WNDCLASS を JS から指向呼出した場合は
`RegisterClassW` ×2 が shim に届き、`TApplication` の窓 (hwnd 31bit) が生成できる。再現: `bash tools/gui/flengine/e2e.sh` (gate 12 + ネガコン 5。FAIL なら exit 1)。

既知類型との関係: 該当 `docs/DEFECTS.md` D1b 系 (比較が定数に畳まれ分岐が誤る) の入力側変種 1 件 (§5-2, 新規行案あり) / D1 系は m11 REPORT §10 と同根。他は該当なし。

## 1. 結論と実測

検証起点: コード commit `6a05082` (本 REPORT の commit は docs と `results/` の再生成のみ)。環境: runner 4 vCPU, node v22.23.3, emcc (`[EMSDK]`)、素材 `work-m11` + `fl-win64`、`python3` の pefile・capstone、`x86_64-w64-mingw32-gcc` (`apt-mingw`)。
IR は素材 `work-m11` の `boot_final.ll` / `boot_final3.ll` を `tools/gui/work/flengine/tree/` に複製し、複製側で `m11_build.sh` (qstore・alloca・post) を実行してから測った。`m11_gen_ir2.sh` は使っていない (e2e は IR を再生成しない。sha256 は §6)。

| 項目 | 実測 (6a05082, 3 回) | 定義 / 分母 |
|---|---|---|
| リンク | wasm-ld signature mismatch **0** / undefined **0** / duplicate **0** (ff・soft 両ビルド、3 回とも) | `build.sh` のリンクログ `[gf] OK:` 行 |
| GUI declare ↔ adapter | IR の GUI declare **177** = adapter **177** (impl 158 / stub 19)、c=0 d=0 | `integ/gen_adapt.py`、`build_ff.log` |
| 起動の回帰 | shim 有り/無し (同一 IR) で **units_run 22 / init_count 23 / dllmain_done true / GetMem 33 / FreeMem 20 / icall_miss 0** が 3 回とも一致 | baseline = `m11_run.mjs` (GUI 3 本は m11_win.c の暫定 stub) |
| survey の回帰 | soft (stub は 0 返却) の survey が baseline と **ok 864 / noproc 1 / miss 46 / trap 31 / clobber 0** で一致 (3 回とも)。ただし trap の**種別**が 1 件だけ異なる (§5-5) | 942 unit 隔離。`m11_survey.mjs` と同じプロトコル (VA 予算・clobber 復元) |
| fail-fast ビルドの survey | ok 864 / noproc 1 / miss 46 / trap 31。fail-fast で止まった unit は 1 (`LoadImageW`) | `survey_ff.json` |
| 最初の GUI 呼出 (自然起動) | **`LoadStringW` ×4 → shim (IMPL, P1)**。DllMain attach の 22 unit 内 | `boot.json` の GUI-REACH |
| survey で shim に到達した API | **23 種** (IMPL 22 / STUB 1)。3 回とも同一集合。§3 | `survey_soft.json` の reach |
| `LoadStringW` の通算回数 | 8,365,791 回 (survey、run 3 の 1 回のみ記録)。旧 REPORT の 48M 回は clobber 復元前の値 | `survey_soft.json` |
| `RegisterClass*` / `CreateWindowEx*` の自然到達 | **0** (起動・survey とも) | judge の INFO 行 |
| 指向呼出 (§4) | `RegisterClassW` ×2 成功 (atom 0xC001 / 0xC002)、`TApplication` 窓 hwnd `0x210000e` (< 2^31)、WNDPROC 4 引数が `m11_icall` 経由 | `probe.json` |
| 親の受入条件 2 `bash tools/gui/e2e.sh` | **ALL PASS / rc 0 / 99 秒** (1 回、6a05082)。途中の rc 127 は worktree に `node_modules` が無いため (`pnpm install --frozen-lockfile` で解消) | `tools/gui/e2e.sh` の出力 |

## 2. 変更と成果物

| パス | 内容 |
|---|---|
| `tools/gui/flengine/build.sh` | `m11_build.sh` の除外リスト方式で結合ビルド。shim `.o` を `build_objs.sh --reach --ir` で作り、m11 側 C (shim/rt/win/ov/simd/fnstubs/data/winstubs/boot) を **`-pthread` で再コンパイル**して `emcc` リンク。`--soft` (STUB は 0 返却)、`--plain` (到達ログ無し)。CF に `-DM11_OV_CLASSCREATE` を追加 (m11_build.sh と同じ -D 集合) |
| `flengine_glue.c` | 起動前 constructor: `gui_headless_attach` (host_ready=1)・out ring は host 不在なので満杯時に破棄・icall hook = `m11_icall`。`--wrap=gui_failfast` で fail-fast を JS 例外に (§2-1 #3) |
| `gen_thunks.py` | PE の import thunk (`jmp [IAT]`) のうち `DefWindowProc{A,W}` の LVA を C 表化 (§4) |
| `run.mjs` / `probe.mjs` | 実行ハーネス (通常起動 / `--survey` / 指向呼出)。JSON を出力。m11 の場所は `GF_M11` で差し替え可能 |
| `judge.py` / `e2e.sh` | gate 12 + 情報行。ネガコン 5 本を「期待した FAIL 行が出ること」まで検査。step 0 は素材を複製して m11_build.sh・baseline を走らせる |
| `results/*.json`、`results/ir_sha256.txt` | 実測の機械可読。`reach_expected.json` は R2 gate の到達 floor (19) |
| `tools/gui/src` ほか | `GetDC(NULL)` の画面 DC 実装 (§2-1 #4)、`test/selftest.c` に 4 assertion、`gen_api.py` が `IMPORTS.md` に「実到達」列と §4 を出力 |

### 2-1. 結合で踏んだ問題と対処

| # | 症状 (実測) | 原因 | 対処 |
|---|---|---|---|
| 1 | `LinkError: memory import has 256 pages which is smaller than the declared initial of 4608` | `-pthread` では共有メモリを JS 側が `INITIAL_MEMORY` で作る。`-Wl,--initial-memory` は効かない | `-sINITIAL_MEMORY=0x12000000 -sMAXIMUM_MEMORY=0x72000000` (< 2 GiB, INTEGRATION §4-5) |
| 2 | m11 の `m11_win.c` と shim が `LoadStringW` / `MessageBoxA` / `MessageBoxW` を二重定義 | m11 が user32 の 3 本を暫定実装 | m11 を変えず `-DLoadStringW=m11_win_LoadStringW` 等で改名コンパイル (shim 定義が勝つ) |
| 3 | shim の `gui_failfast` は `abort()` で wasm ごと止まる | 隔離 survey ができず「最初の 1 本」しか分からない | `-Wl,--wrap=gui_failfast` → 同じ `FAIL-FAST:` 行を出して JS 例外で脱出 (m11 の Halt0 と同流儀)。`--soft` は STUB を 0 返却にして後続の API まで集める計測用 (shim 本体は無変更) |
| 4 | `GetDC(NULL)` が fail-fast (survey の 2 unit。後続の `GetDeviceCaps` / `CreatePalette` / `GetStockObject` / `LoadIconW` が見えない) | shim は画面 DC 未実装 | `gdi_get_screen_dc()` = 既定 1x1 ビットマップ選択済みのメモリ DC (既存 `CreateCompatibleDC` と同じ方式。描画は捨てる) を追加。native selftest 0 failed |
| 5 | `TApplication` の `CreateWindowExW` が NULL | `WNDCLASS.lpfnWndProc = 0x24920` は **`DefWindowProcW` の import thunk** (`ff 25 …`) で lift closure の関数ではない → `m11_icall` が miss → WM_NCCREATE=0 | `gen_thunks.py` の表を glue の icall hook で先に引き、shim の `DefWindowProcW` へ。thunk は PE 全体で 1 本 (`0x24920`) |

### 2-2. ABI チェックリスト (INTEGRATION.md §4) の実機確認

| # | 項目 | 結果 |
|---|---|---|
| 1 | `-sGLOBAL_BASE` ≥ 0x10000 | `0x10000000` で link。`gui_shared_ptr` = 271,661,888 (probe の gate P2) |
| 2 | ハンドル 31bit | `GetDC(0)` = `0x120000f`、`TApplication` hwnd = `0x210000e`、`RegisterClassW` atom は 0xC001+ |
| 3 | 全 TU `-pthread` | wasm-ld エラー無し (m11 側 + shim 側) |
| 4 | WNDPROC 4 引数 | `gui_call4` → `m11_icall(t,a,b,c,d,0,0,0,0)`。`CreateWindowExW` ごとに 2〜4 回呼ばれる |
| 5 | メモリ上限 < 2 GiB | max 0x72000000。survey 通算で `Cannot enlarge memory` (上限到達) が出る = m11 REPORT §10 の VirtualFree no-op leak と同じ現象 (回数は baseline 側を未計数) |
| 8 | UI スレッドのスタック量 | **未実測** (GUI スレッドは起動していない。結合は node 主スレッド) |

### 2-3. レビュー指摘への対応 (commit `6a05082`)

| 指摘 | 対応 |
|---|---|
| S1 FAIL (soft 828 vs baseline 864) | 原因: `run.mjs --survey` が `m11_survey.mjs` の隔離プロトコル (unit ごとの VA 予算 #513・clobber 時の image 復元) を持たず、clobber が起きた後の unit が連鎖して trap していた。プロトコルを移植して一致 (**予算と clobber 復元のどちらが効いたかは未分離**)。judge の S1 に `clobber` も追加 |
| 検証起点・数値の再測定 | 検証起点を `6a05082` に更新し、全数値を HEAD で 3 回測定 (§6) |
| `EnumFontFamiliesExW` の記述 | main の GUI-9 で実装済み。本 REPORT §3 / §7 を実到達結果で書き直し (STUB は `LoadImageW`) |
| `apt-mingw` が `oc_artifacts` に無い | PR 本文に `apt-mingw` を追加。前提は §6 |
| m11 `work/` の in-place 書換え | `e2e.sh` step 0 を複製 (`tools/gui/work/flengine/tree/`) 側で実行。本体 `tools/m11` は読取のみ |
| repo 外絶対パス | `[EMSDK]` / `[WIN64]` / `[ANALYSIS-DIR]` の ID で参照 (§1・§7) |
| 誤った起票先 (#505) | §5-2 の DEFECTS 行案から #505 (MERGED) を外し PM 起票依頼に変更 |
| IR provenance | §6 の sha256 (素材と m11_build.sh 後の 2 組) |

## 3. 実到達 API (自然起動 + survey; 回数は `survey_soft.json`)

P は `IMPORTS.md` の優先度。起動 = DllMain attach で到達、他は survey (942 unit 隔離) で到達。

| 状態 | API (P) |
|---|---|
| 起動で到達・実装済み | `LoadStringW` (P1) ×4 |
| survey で到達・実装済み | `GetDC` (P0), `GetDeviceCaps` (P0), `ReleaseDC` (P0), `GetStockObject` (P1), `LoadIconW` (P1), `LoadCursorW` (P1), `CreatePalette` (P2), `MessageBoxA` (P2), `RegisterWindowMessageW` (P0), `GetSystemMetrics` (P0), `FindWindowW` (P1), `RegisterClipboardFormatW` (P0), `GetClipboardFormatNameW` (P1), `CharLowerBuffW` (P1), `GetKeyboardLayout` (P0), `EnumDisplayMonitors` (P1), `EnumDisplaySettingsW` (P1), `GetMonitorInfoW` (P1), `GetClipCursor` (P0), `SystemParametersInfoW` (P0), **`EnumFontFamiliesExW` (P2、GUI-9 で実装済み)** |
| survey で到達・**fail-fast stub** | **`LoadImageW` (P2)** — STUB 経路で 21 回呼ばれる。fail-fast ビルドではこの 1 unit が止まる |

- 数え方: `survey_soft.json` の reach 集合 23 種 (`LoadStringW` を含む。起動で到達した 1 種はこの中に含まれる)。IMPL 22 / STUB 1。
- **IMPORTS.md の P 分類への入力** (`IMPORTS.md` §4 に自動出力): `LoadImageW` は stub のまま実到達 → **実装必須へ昇格**。`CreatePalette` / `MessageBoxA` は P2 だが実到達 → P1 以上へ昇格候補。
  P0 の未到達は現 m11 到達段が浅いため (SendMessage / PostMessage / BitBlt / SelectObject ほか) 「不要」の根拠にはならない。
- `MessageBoxA` は Delphi RTL の `Runtime error 0` ダイアログ (unit の Halt0 経路)。shim は host 無しなら即 IDOK。
- `LoadStringW` は survey 通算 8,365,791 回。1 unit が資源 ID を回している疑い (shim は資源供給 hook 未接続で常に 0 を返す)。**未調査** (§7)。
- icall hook 経由の呼出: survey (soft) で 2 回 (`gui_icall_calls`。`EnumDisplayMonitors` の callback と推定)。`m11_icall` miss は soft survey で 48 (baseline 側は未計数)。

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
   `GetClassInfoW` が書く escape 済み stack local の読出し脱落で、既存 ldfix の F1 (load_dropped) は直していない。DEFECTS 行案:

| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| `if not registered or (cls.lpfnWndProc <> DefWindowProc) then RegisterClass` が未登録でも登録しない | callee (`GetClassInfoW`) が書く 72B 構造体 (stack_var) のフィールド load が脱落し `xor i64 0,0`、比較が定数に畳まれる (D1b の入力側) | `function_52a7f0` で `RegisterClassW` が呼ばれず `CreateWindowExW` が NULL | IR の `xor i64 0, 0` が `icmp` の被演算子になっている | escape する stack_var からの load を ldfix で復元 (既存 ldfix F1 の拡張。既存 issue は未特定 → PM 起票) |

3. **WNDPROC が closure 外** (`0x31dd10` ほか): WNDCLASS が `.data` の静的実体で WNDPROC を持つ場合、call graph に現れず lift されない (m11 REPORT §2-6 と同根)。`m11_extra_seeds.txt` 相当の seed を WNDCLASS 走査で自動生成する pass が要る。
4. `GetDC(NULL)` 未実装は実 FLEngine に当たって初めて分かった shim の穴 (selftest は mingw 製 PE の範囲で未検出)。
5. **soft の trap 種別 1 件の差**: baseline は同じ unit を `halt0` 8 件として数えるが、GUI soft は `halt0` 7 件 + `gui_failfast` 1 件 (`SystemParametersInfoW` の shim 内 fail-fast。STUB 0 返却ではない経路)。trap 総数は一致するので S1 は通る。種別の一致までは gate にしていない。shim 側の未対応 action は未調査 (§7)。

## 6. 検証

実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/gui/flengine/e2e.sh` (HEAD `6a05082`, 4 vCPU, 3 回直列)。
前提: 素材 `work-m11` (`tools/m11/work/` に展開。e2e は読取のみで、複製 `tools/gui/work/flengine/tree/` 側で使う)、`fl-win64` (`$RUNNER_TEMP/fl-win64`)、`x86_64-w64-mingw32-gcc` (`apt-mingw` = `gcc-mingw-w64-x86-64`)、`python3` に pefile・capstone (`python3 -m pip install pefile capstone`。`pip` 単体は別の Python を指すことがあるため `python3 -m pip` を使う)。

| 回 | rc | 所要 (wall) | load 開始 → 終了 | judge | native selftest (`tools/gui/test`) | ネガコン |
|---|---|---|---|---|---|---|
| 1 | 0 | 138 s | 0.29 0.42 0.23 → 1.15 0.72 0.37 | 12/12 PASS | 431 passed / 0 failed | 5/5 期待どおり FAIL |
| 2 | 0 | 129 s | 0.97 0.70 0.36 → 1.17 0.89 0.48 | 12/12 PASS | 431 passed / 0 failed | 5/5 期待どおり FAIL |
| 3 | 0 | 130 s | 1.17 0.89 0.48 → 1.31 1.04 0.60 | 12/12 PASS | 431 passed / 0 failed | 5/5 期待どおり FAIL |

- min–max: 所要 129–138 s。S1 `864/1/46/31/0` (3/3 一致)。R2 reached 23 (3/3)。B1 units_run 22 (3/3)。`results/*.json` は 3 回で同一の gate 結果、survey の一部数値 (`LoadStringW` の回数など) は run 3 の結果のみ記録。
- IR provenance (`results/ir_sha256.txt`): 素材 `boot_final.ll` `69c774de…`・`boot_final3.ll` `010451ad…`。m11_build.sh 後 (qstore 段: fixed_stores 279・alloca 段: 拡幅 alloca 2,361 個) `boot_final.ll` `30a4e00d…`・`boot_final3.ll` `4f0a0cc6…` (全文は results/ir_sha256.txt)。
- 親 `bash tools/gui/e2e.sh` (受入条件 2): ALL PASS / rc 0 / 99 秒 (1 回)。内訳は native lift・bpp・FreeType・SIMD・Chrome E2E・present・sigprobe の各段が PASS。

ネガティブコントロール (全て「期待した FAIL 行が出る」まで検査。judge のクラッシュを FAIL 確認と誤認しない):

| NC | 壊し方 | 結果 (3 回とも同じ) |
|---|---|---|
| N1 | 到達ログ無し (`--plain`) ビルドの起動を判定 | R1 FAIL (reach 0 件), exit 1 |
| N2 | baseline の units_run 期待値を 23 に | B1 FAIL, exit 1 |
| N3 | 到達 floor に未到達 API `NoSuchGuiApi` を 1 つ追加 | R2 FAIL (floor 20 / reached 23), exit 1 |
| N4 | survey の 1 unit を ok→trap に改竄 | S1 FAIL, exit 1 |
| N5 | `GetDC(NULL)` を元の fail-fast に戻した shim で native selftest | `FAIL-FAST: unimplemented Win32 API: GetDC`, exit 134 |

- 範囲外: 実ブラウザ・Canvas 描画、audio、UI スレッドのスタック量、`gui_reach` の性能影響 (INTEGRATION §4-12 の未計測は継続)。
- 親 `tools/gui/e2e.sh` の rc 127 (初回) は worktree に `node_modules` が無いことによる環境起因。`pnpm install --frozen-lockfile` 後に rc 0。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `RegisterClass*` / `CreateWindowEx*` の自然到達 (#134 / #490 の先) | 受入条件 1 | #134 / #490 に依存。到達後に `bash tools/gui/flengine/e2e.sh` の INFO 行が変わる (R2 floor を更新) |
| `function_52a7f0` の `TempClass.lpfnWndProc` load 脱落 (§5-2) | AllocateHWnd 経路 (TPUtilWindow = Timer / 非同期 window) が全滅 | PM 起票依頼 (DEFECTS 行案あり。既存 ldfix issue は未特定。#505 は MERGED のため不可) |
| WNDCLASS 静的実体の WNDPROC を closure seed に追加する pass (`TLightweightLayeredControl` 0x31dd10 ほか) | その class の窓生成が NULL | PM 起票依頼 (m11 / icall 系。#90 の間接 call 復元と近い) |
| `LoadImageW` の実装 (STUB、survey 21 回・ff で 1 unit が停止) | ff ビルドでは 1 unit が止まる | PM 起票依頼 (GUI-2 系 P2 stub 昇格。#174 に所見) |
| `SystemParametersInfoW` の shim 内 fail-fast (soft でも 1 unit 停止、§5-5) | soft の trap 種別が baseline と 1 件異なる | PM 起票依頼 (#174 に所見。未調査) |
| `LoadStringW` 8.4M 回の unit 特定と資源供給 hook (`gui_set_resource_provider` ← shimx / PE .rsrc) | LoadStringW が常に空文字 | #174 に所見 / GUI-2 または shimx |
| 受入「`__pe_image` を m11_data_gen 方式の data 実体化へ統合」(スコープ 3) | 未着手 (本 PR は m11 の image 敷設をそのまま利用) | PM 起票依頼 (新規子チケット) |
| 実ブラウザ host 結線 (`GuiHost.attach`・FL ワーカ化・UI スレッドのスタック量 §2-2 #8) | node の headless host のみ。描画 (#32) は別 | #32 / #121 |
| `tools/m11/m11_e2e.sh` と `m11_gen_ir2.sh` が PE パスを `[ANALYSIS-DIR]` 既定 (`/home/ubuntu` 固定) で持つ | runner では ldfix が黙ってスキップされ数値が変わる。本 PR の測定は `gen_ir2` を使わず素材 IR で行う | m11 に `FL_WIN64_DIR` 参照を提案 (#132 の未解決と同件。PM 起票依頼) |
| 前回 run で観測した selftest (ASAN) の `heap-use-after-free` (`gui_headless` の描画スレッドと `surf_free`。前 run で約 2/8 で再現) | 本 HEAD の 3 回では再現せず (431/0 ×3)。フレークは未解消 | PM 起票依頼 (gui_headless の描画と surf_free の排他) |
