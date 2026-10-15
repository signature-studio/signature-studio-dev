# REPORT — GUI-3 (#174): 実 FLEngine の lift に GUI shim を結合する

**判定: 部分達成 (受入条件 1 は未達。過去の `c4e3c064` の 14/14 PASS (§6c-4) は当時の値。HEAD `bf9cf547` の flengine e2e は judge 13/14 (S1 FAIL。§6d を正とする)。PR は `Refs #174`)**。§1〜§5 の数値・記述は旧 HEAD `52e6bd57` 時点のもの (参考)。現 HEAD の実測は §6 を正とする。実 FLEngine (m11 closure, `FLEngine_x64.dll` の 7,421 関数 lift) に `tools/gui` shim を全 TU `-pthread` でリンクし、
**自然起動 (DllMain attach) で最初の GUI API (`LoadStringW`) が shim に到達**した。942 unit の隔離 survey では GUI API **32 種**が shim に到達 (実装済み 31 / fail-fast stub 1 = `LoadImageW`)。
`CreateWindowExW` は survey で **1 回だけ自然到達**したが、直前の `RegisterClassW` は呼ばれず (`GetClassInfoW` の後に直行)、窓は生成されない (§5-2 の lift 欠陥)。受入条件 1 の意図する「実登録を経た窓生成の自然到達」は未達。
実 WNDCLASS を JS から指向呼出した場合は `RegisterClassW` ×2 が shim に届き、`TApplication` の窓 (hwnd 31bit) が生成できる。
前回 FAIL だった S2 は、`SystemParametersInfoW` の未対応 action を fail-fast から `FALSE` 返却へ変えて解消した (§5-5)。S2 の判定式は `8a6dcf4b` (main 取り込み済み) で旧式から新式に変更済みで、本 PR は判定式を変えていない (詳細は REPORT_APPENDIX §6i)。S1 の判定式も変えていない。
再現: `bash tools/gui/flengine/e2e.sh` (gate 12 + ネガコン 5。FAIL なら exit 1)。

> **注 (review #576 指摘 2・5)**: §1 表・§4 の数値は merge 前 (`b867b94` 以前) の測定。HEAD の実測は **§6c が正**。`EnumFontFamiliesExW` は現 main で IMPL (`gui_gdi.c` の `EnumFontFamiliesExW`)、`survey_soft.json` / `survey_ff.json` も IMPL と記録している。§3 の本文も同じ前提で書き直した。

既知類型との関係: 該当 `docs/DEFECTS.md` D1b 系 (比較が定数に畳まれ分岐が誤る) の入力側変種 1 件 (§5-2, 新規行案あり) / D1 系は m11 REPORT §10 と同根。他は該当なし。

## 1. 結論と実測

検証起点 (§1 表): 旧 HEAD `52e6bd57` (`d46b024` 時点の値、参考)。現 HEAD `3885765a` の実測は §6。環境: runner 4 vCPU, node v22.23.3, emcc 6.0.12 (`[EMSDK]`)、素材 `work-m11` + `fl-win64`、`python3` の pefile・capstone、`x86_64-w64-mingw32-gcc` (`apt-mingw`)。
IR は素材 `work-m11` の中間 IR (`boot0..4.lift.ll`) から、`tools/gui/work/flengine/tree/` の複製側で `m11_gen_ir2.sh` (ldfix 適用、main #680 の要件) を回して作り直し、続けて `m11_build.sh` (qstore・alloca・post) を実行してから測った。`tools/m11/work` (素材) は書き換えていない。sha256 は §6。

| 項目 | 実測 (52e6bd57, 3 回。全 rc 0・12/12 PASS) | 定義 / 分母 |
|---|---|---|
| リンク | wasm-ld signature mismatch **0** / undefined **0** / duplicate **0** (ff・soft 両ビルド、3 回とも) | `build.sh` のリンクログ `[gf] OK:` 行 |
| GUI declare ↔ adapter | IR の GUI declare **177** = adapter **177** (impl 158 / stub 19)、c=0 d=0 | `integ/gen_adapt.py`、`build_ff.log` |
| 起動の回帰 | shim 有り/無し (同一 IR) で **units_run 52 / init_count 54 / dllmain_done false / GetMem 560 / FreeMem 20 / icall_miss 5 / 例外 `memory access out of bounds`** が一致 (3 回とも)。baseline 側も同じ trap で止まる (main の #134 修正後の挙動。§5-1) | baseline = `m11_run.mjs` (`baseline_boot.json` の `threw`) |
| survey の回帰 | soft (stub は 0 返却) の survey が baseline と **ok 871 / noproc 1 / miss 47 / trap 23 / clobber 0** で一致 (3 回とも)。比較元は GUI と同じ `-pthread` build・同じ `run.mjs --survey` (§5-6) | 942 unit 隔離。隔離プロトコル (VA 予算・clobber 復元) は `run.mjs --survey` が持つ |
| fail-fast ビルドの survey | ok 871 / noproc 1 / miss 47 / trap 23。fail-fast で止まった unit は 1 (`LoadImageW` 1。`SystemParametersInfoW` は 0) | `survey_ff.json` |
| 最初の GUI 呼出 (自然起動) | **`LoadStringW` ×3 → shim (IMPL, P1)**。DllMain attach の 52 unit 内 (trap で止まる前) | `boot.json` の GUI-REACH |
| survey で shim に到達した API | **32 種** (IMPL 31 / STUB 1)。`CreateWindowExW` (IMPL) と `GetClassInfoW` を含む。§3 | `survey_soft.json` の reach |
| `LoadStringW` の通算回数 | 15 回 (survey、`survey_soft.json` の reach。§3)。資源供給 hook は未接続で常に空 (§7) | `survey_soft.json` |
| `RegisterClass*` / `CreateWindowEx*` の自然到達 | **`CreateWindowExW` ×1 のみ** (survey、unit 内で `GetClassInfoW` の直後)。`RegisterClassW` は自然到達 0。起動 (boot) では 0 | judge の INFO 行 |
| 指向呼出 (§4) | `RegisterClassW` ×2 成功 (atom 0xC001 / 0xC002)、`TApplication` 窓 hwnd `0x210000e` (< 2^31)、`TLightweightLayeredControl` は NULL (WNDPROC が closure 外)。WNDPROC 4 引数が `m11_icall` 経由 | `probe.json` |
| 親の受入条件 2 `bash tools/gui/e2e.sh` | **ALL PASS / rc 0** (本 HEAD `52e6bd57`、1 回・wall 139 s。`pnpm install --frozen-lockfile` 後に実行) | `tools/gui/e2e.sh` の出力 |

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
| 検証起点・数値の再測定 | `6a05082` で全数値を 3 回測定。main 取り込み (`27a9171`→`350d3ee`) で m11 の変更 (#134 unit #23 修正ほか) が入り、boot の数値が変わったため §1・§6 を再測定 (`9500d02`) |
| B1 の判定 (main 取り込み後の FAIL) | 素の m11 baseline も boot で `memory access out of bounds` を投げる (`baseline_boot.json` の `threw`)。judge は `boot_threw` と baseline の `threw` を同じ基準で比べるよう直した (`9500d02`)。判定の緩和ではなく、比較先の誤りの修正 |
| `EnumFontFamiliesExW` の記述 | main の GUI-9 で実装済み。本 REPORT §3 / §7 を実到達結果で書き直し (STUB は `LoadImageW`) |
| `apt-mingw` が `oc_artifacts` に無い | PR 本文に `apt-mingw` を追加。前提は §6 |
| m11 `work/` の in-place 書換え | `e2e.sh` step 0 を複製 (`tools/gui/work/flengine/tree/`) 側で実行。本体 `tools/m11` は読取のみ |
| repo 外絶対パス | `[EMSDK]` / `[WIN64]` / `[ANALYSIS-DIR]` の ID で参照 (§1・§7) |
| 誤った起票先 (#505) | §5-2 の DEFECTS 行案から #505 (MERGED) を外し PM 起票依頼に変更 |
| IR provenance | §6 の sha256 (素材と m11_build.sh 後の 2 組) |
| S2 FAIL (SPI 0x101a の fail-fast, 12:08 review) | 未対応 action を `return 0` (FALSE) に変更 (`472c7d5`)。判定器は緩めていない。§5-5 |
| 旧 REPORT の数値 (9500d02 の 11/12) | §1・§6 を `472c7d5` の 3 回実測で書き直し |

## 3. 実到達 API (自然起動 + survey; 回数は `survey_soft.json`)

P は `IMPORTS.md` の優先度。起動 = DllMain attach で到達、他は survey (942 unit 隔離) で到達。

| 状態 | API (P) |
|---|---|
| 起動で到達・実装済み | `LoadStringW` (P1) ×3 |
| survey で到達・実装済み | `GetDC` (P0), `GetDeviceCaps` (P0), `ReleaseDC` (P0), `GetStockObject` (P1), `LoadIconW` (P1), `LoadCursorW` (P1), `CreatePalette` (P2), `MessageBoxA` (P2), `MessageBoxW` (P2), `RegisterWindowMessageW` (P0), `GetSystemMetrics` (P0), `FindWindowW` (P1), `RegisterClipboardFormatW` (P0), `GetClipboardFormatNameW` (P1), `CharLowerBuffW` (P1), `GetKeyboardLayout` (P0), `EnumDisplayMonitors` (P1), `EnumDisplaySettingsW` (P1), `GetMonitorInfoW` (P1), `GetClipCursor` (P0), `SystemParametersInfoW` (P0。未対応 action は FALSE 返却, §5-5), `EnumFontFamiliesExW` (P2、GUI-9 で実装済み), `GetClassInfoW` (P0), `CreateWindowExW` (P0, 1 回。RegisterClass 無しの経路, §5-2), `SetWindowLongPtrW` (P0), `CharNextW` (P1), `CharLowerW` (P2), `DeleteObject` (P0), `GetIconInfo` (P1), `GetObjectW` (P0) |
| survey で到達・**fail-fast stub** | **`LoadImageW` (P2)** — STUB 経路で 21 回呼ばれる。fail-fast ビルドではこの 1 unit が止まる |

- 数え方: `survey_soft.json` の reach 集合 32 種 (`LoadStringW` を含む。起動で到達した 1 種はこの中に含まれる)。IMPL 31 / STUB 1。
- **IMPORTS.md の P 分類への入力** (`IMPORTS.md` §4 に自動出力): `LoadImageW` は stub のまま実到達 → **実装必須へ昇格**。`CreatePalette` / `MessageBoxA` は P2 だが実到達 → P1 以上へ昇格候補。
  P0 の未到達は現 m11 到達段が浅いため (SendMessage / PostMessage / BitBlt / SelectObject ほか) 「不要」の根拠にはならない。
- `MessageBoxA` は Delphi RTL の `Runtime error 0` ダイアログ (unit の Halt0 経路)。shim は host 無しなら即 IDOK。
- `LoadStringW` は survey の reach 計数で 15 回 (`survey_soft.json`)。shim は資源供給 hook 未接続で常に 0 を返す。**資源 ID の偏りは未調査** (§7)。
- icall hook 経由の呼出: survey (soft) で 2 回 (`gui_icall_calls`。`EnumDisplayMonitors` の callback と推定)。`m11_icall` miss は soft survey で 48 (baseline 側は未計数)。

## 4. 指向呼出 (`probe.mjs`; 自然到達ではない)

自然起動は `RegisterClass*` に届かないため、DllMain attach 後に JS から lift 済み関数を直接呼ぶ。**呼出元が JS である点で自然到達とは区別する**。下表は merge 前 (`b867b94`) の値 (WNDPROC seed 前のため `TLightweightLayeredControl` = NULL)。HEAD `19ebb43` の実測は `TApplication` hwnd `0x110000f` / `TLightweightLayeredControl` hwnd `0x110000e` (judge P4・P5 の PASS 行。§6c)。
実 FLEngine の RegisterClassW 呼出点は IR 全体で 5 (`lift_fnmap.py --ir`: `function_425260` (= RegisterClassW ラッパ)・`function_52a7f0`・SetWindowLongPtrW 2・SetClassLongPtrW 1)。
`function_425260` の呼出元は `function_71dd80` と `function_867e10`。

| WNDCLASS (PE 実値) | lpfnWndProc | RegisterClassW | CreateWindowExW |
|---|---|---|---|
| `TLightweightLayeredControl` (`function_71dd80` が渡す) | 0x31dd10 (**closure 外**) | atom 0xC001 | **NULL** (WM_NCCREATE の WNDPROC が `m11_icall` miss ×2) |
| `TApplication` (`function_867e10` が渡す) | 0x24920 (DefWindowProcW import thunk) | atom 0xC002 | **hwnd 0x210000e** (WNDPROC 4 回, thunk 経由で shim の DefWindowProcW) |
| `TPUtilWindow` (`function_52a7f0` = AllocateHWnd 相当) | 0x24920 | **呼ばれない** | NULL (§5-2) |

## 5. 未達の理由と発見

1. **受入条件 1 (`RegisterClass*`/`CreateWindowEx*` の自然到達) は実質未達**: main の #134 (unit #23 OOB 修正) 後は、通常起動が unit #23 で Halt0 せず **52 unit まで進み、その後 `memory access out of bounds` で止まる** (素の m11 baseline も同じ trap。`baseline_boot.json` の `threw`)。このため boot では `RegisterClass*` / `CreateWindowEx*` に届かない。survey では `CreateWindowExW` が 1 回だけ到達するが、直前に `RegisterClassW` は呼ばれず (`GetClassInfoW` の直後)、§5-2 の lift 欠陥の経路で窓は NULL。実登録を経た窓生成の自然到達は未達。#134 / #490 の先。本 PR は「到達したときの受け皿」(link / ABI / 署名 / WNDPROC 解決 / 到達ログ) を実機で通した段階。
2. **新規 lift 欠陥 (`function_52a7f0`; Delphi `AllocateHWnd`)**: 機械語は `GetClassInfoW(…, &TempClass)` の後 `cmp [rbp+0x70], DefWindowProc` (`TempClass.lpfnWndProc` と比較) で `RegisterClass` の要否を決める。
   IR では `[rbp+0x70]` の load が `%1 = xor i64 0, 0` (定数 0) に化け、比較が常に false に畳まれて「未登録 (GetClassInfoW=false)」でも `RegisterClassW` を**飛ばす**。後続の `CreateWindowExW` はクラス未登録で NULL。silent miscompile。
   `GetClassInfoW` が書く escape 済み stack local の読出し脱落で、既存 ldfix の F1 (load_dropped) は直していない。DEFECTS 行案:

| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| `if not registered or (cls.lpfnWndProc <> DefWindowProc) then RegisterClass` が未登録でも登録しない | callee (`GetClassInfoW`) が書く 72B 構造体 (stack_var) のフィールド load が脱落し `xor i64 0,0`、比較が定数に畳まれる (D1b の入力側) | `function_52a7f0` で `RegisterClassW` が呼ばれず `CreateWindowExW` が NULL | IR の `xor i64 0, 0` が `icmp` の被演算子になっている | escape する stack_var からの load を ldfix で復元 (既存 ldfix F1 の拡張。既存 issue は未特定 → PM 起票) |

3. **WNDPROC が closure 外** (`0x31dd10` ほか): WNDCLASS が `.data` の静的実体で WNDPROC を持つ場合、call graph に現れず lift されない (m11 REPORT §2-6 と同根)。`m11_extra_seeds.txt` 相当の seed を WNDCLASS 走査で自動生成する pass が要る。
4. `GetDC(NULL)` 未実装は実 FLEngine に当たって初めて分かった shim の穴 (selftest は mingw 製 PE の範囲で未検出)。
5. **`SystemParametersInfoW` の未対応 action (旧 S2 FAIL の原因、解消済み)**: 以前は action `0x101a` (SPI_GETICONTITLELOGFONT 相当) を `gui_failfast` で止めていたため、ff survey の 2 unit と soft の 2 unit が trap していた。S2 の gate (fail-fast の API は soft で STUB 扱い) を通すため判定は緩めず、未対応 action を Win32 の未対応 action と同じく `return 0` (FALSE) にした (`472c7d5`)。`LOGFONTW` の値は推定で埋めていないので、この action は実機値と一致しない (LOGFONT を要求する経路は未確認のまま、FALSE で後続へ進む)。ff survey の fail-fast は `LoadImageW` 1 unit のみ。
   trap の内訳は baseline と一致しない: baseline は `memory access out of bounds` 21 / `halt0` 8 (`baseline_survey.json` の `trap_kinds`)、GUI soft は 21 / 8 (`survey_soft.json` の `kinds`)。総数 29 は一致するため S1 は通る。種別の一致は gate にしていない。
6. **S1 の比較元 (baseline) を GUI と同一 build に揃えた (`52e6bd57`)**。旧 baseline は `m11_build.sh` の非 pthread `m11_boot.cjs` を `m11_survey.mjs` で測っていたが、GUI 結合 (`build.sh`) は m11 C と shim を `-pthread` で再コンパイルする。build 条件が違うため比較が成立していなかった。`1b99a5a4` での 871 vs 869 の差は、この build 差と shim の実装の差が混ざったもの。
   - 切り分け (`1b99a5a4` の tree、同一 IR、実測): 非 pthread baseline 869 / 同じ `run.mjs --survey` ハーネスに非 pthread wasm を通した値 869 (ハーネス差は無し) / `-pthread` で揃えた shim 無し baseline 871 / GUI soft 871。pthread 同士の差は 0。
   - 非 pthread baseline と pthread baseline の差は 10 unit (`15,16,158,189,190,232,265,304,555,616`、うち 8 unit は trap↔ok)。pthread baseline と GUI soft の差は 8 unit (`15,16,158,189,190,232,265,616`、全て trap→ok)。unit 16 は pthread baseline で `missing function: LoadStringW` となり、GUI soft では `LoadStringW` を shim が実装したため通る (GUI API 由来の変化)。残り (15・158・189・190・232・265・616) は単独実行で両方 trap する (15・189・190・232・616) か、GUI 以外の `m11` stub (`SetDllDirectoryW` 等。158・265) のみを呼ぶ。survey 内の前 unit の状態に依存する順序効果で、これらは GUI 実装の差ではない。
   - 判定式 (`judge.py`) は無変更。比較元の取り方のみ修正。
   - 比較元の `baseline_survey.json` は judge が読む最小形式 (`ok/noproc/miss/trap/clobber`) に変わった。詳細は `results/baseline_base_survey.json` (run.mjs 形式)。
   - 既知の未解決: 非 pthread と pthread の間で順序依存の unit が 8 件動く。これは m11 の survey 隔離 (前 unit の状態が後続に効く) の性質で、本 PR では直さない (PM 起票依頼 §7)。

## 6. 検証

実行: `ANALYSIS_DIR=$RUNNER_TEMP FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=<pefile・capstone の venv>:$PATH bash tools/gui/flengine/e2e.sh` (現 HEAD = `3885765a`。main `6aa4b397` 取込済 (`de8d603e`)、REPORT・probe.json のみ変更。runner 4 vCPU, 直列)。
素材の前提 (本 run で確認): `$HOME/artifacts` の `fl-win64` / `work-m11` / `toolchain-emsdk` / `toolchain-retdec` を展開し、`tools/m11/m11_gen_ir2.sh` を素材 `tools/m11/work/` で 1 回実行 (`ir_conditions.json` の `ldfix=applied`、gitignore 対象で commit なし)。`apt-mingw` は `[APT-MINGW]`。

| 回 | rc | 所要 (e2e.sh の done) | load 開始 → 終了 | judge | native selftest (`tools/gui/test`) | ネガコン |
|---|---|---|---|---|---|---|
| 1 | 0 | 137 s | 1.14 0.99 0.74 → 1.12 1.03 0.80 | 12/12 PASS | 433 passed / 0 failed | 5/5 期待どおり FAIL |
| 2 | 0 | 146 s | 1.03 1.02 0.79 → 1.02 1.03 0.84 | 12/12 PASS | 433 passed / 0 failed | 5/5 期待どおり FAIL |
| 3 | 0 | 143 s | 1.02 1.03 0.84 → 1.26 1.11 0.90 | 12/12 PASS | 433 passed / 0 failed | 5/5 期待どおり FAIL |
| HEAD 545883bb (main 33fd25a2 取り込み後・1 回) | 0 | 206 s | 1.03 0.96 0.55 → 1.08 1.02 0.66 (done 行) | 12/12 PASS | 433 passed / 0 failed | 5/5 期待どおり FAIL |
| HEAD 7d44c033 (main 6aa4b397 取り込み後・1 回) | 0 | 172 s (done 行) | 0.99 1.07 0.67 → 1.02 1.05 0.74 | 12/12 PASS | 500 passed / 0 failed (件数増加の原因は未確認) | 5/5 期待どおり FAIL |
| HEAD 40e4e4b0 (本 PR 現 head・1 回) | 0 | 209 s (done 行) | 0.78 0.95 0.59 → 1.16 1.04 0.71 | 12/12 PASS | 500 passed / 0 failed | 5/5 期待どおり FAIL |

- 3 回の一致: B1 `units_run 52 (base 52)` / `threw memory access out of bounds (base 同じ)`、L1 undefined/sigmismatch/duplicate `0/0/0`、A1 `177 = 177 (impl 159 / stub 18)`、S1 `871/1/47/23/0 (base 871/1/47/23/0)`、S2 `LoadImageW` のみ fail-fast (ff 1 unit) = soft STUB、R1 first `LoadStringW` ×3、R2 reached 32 (floor 19)、P1 atoms `[-16383, -16382]` / `RegisterClassW=2 CreateWindowExW=3`、P4 hwnd `0x210000e`。
- 所要は 137–146 s (e2e.sh の done 行。wall は run1 137 s・run2 146 s・run3 143 s)。runner 4 vCPU。
- IR provenance (`results/ir_sha256.txt`): 素材 `boot_final.ll` `69c774de…`・`boot_final3.ll` `010451ad…`。step 0 で複製側に `m11_gen_ir2.sh` を回して作り直した IR (ldfix=applied) を測定元にした。その後 `m11_build.sh` 後の sha256 は `boot_final.ll` `2be93e55…`・`boot_final3.ll` `ac64ad01…` (全文は results/ir_sha256.txt)。旧 REPORT の `30a4e00d…` / `4f0a0cc6…` は旧版の IR で、現 head の IR とは一致しない。
- 親 `bash tools/gui/e2e.sh` (受入条件 2): **ALL PASS / rc 0** (本 HEAD `40e4e4b0`、1 回・wall 3 分 18 秒 (198.8 s)、present-e2e 段の load 1.16 → 1.55)。事前に `pnpm install --frozen-lockfile` と `tools/e2e` の `npm ci` を実行 (step 6 の agent-browser 依存のため。いずれも rc 0)。同 HEAD の 1 回目 (`pnpm install` 前) は `tsc` 不在で rc 127、2 回目 (`tools/e2e` の `npm ci` 前) は step 6 の `agent-browser` 不在で rc 2。いずれも依存未導入で、ASan 由来ではない。

### HEAD `0246df1f` の e2e 実測 (本 PR 検証。`bash tools/gui/flengine/e2e.sh`)
実行: `RETDEC=<[RETDEC] の retdec-decompiler> ANALYSIS_DIR=<$RUNNER_TEMP> FL_WIN64_DIR=<[WIN64]> EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/gui/flengine/e2e.sh` (runner 4 vCPU、直列、開始 load 0.22 / 終了 1.02)。

| rc | 所要 (done 行) | judge | native selftest | ネガコン |
|---|---|---|---|---|
| 0 | 457 s | 14/14 PASS | 504 passed / 0 failed | 9/9 期待どおり FAIL (NC N1〜N9) |

- 親 `bash tools/gui/e2e.sh` (HEAD `0246df1f`・1 回): **rc 0 / ALL PASS**、wall 209 s (シェルで開始・終了時刻を取った実測)。前提欠如は 2 回: `tsc` 不在 (rc 127、`pnpm install --frozen-lockfile` で解消) と `agent-browser` 不在 (rc 2、`tools/e2e` の `npm ci` で解消)。どちらも ASan 由来ではない。
- `results/` は e2e が再生成した。`wasm_size` 6912872 → **6913035**、`ir_sha256.txt` の `material` / `after_m11_build` は変化 (`boot_final.ll` `e9aa138e…`・`boot_final3.ll` `5586d206…`)。`c994306b` の値とは一致しない。
- `results/probe.json` は本 e2e で変化なし (git 上で差分無し)。`util_window.ret` = `0x1100010` の値は c994306b の再生成物のまま。本 e2e のログに `util_window.ret` は出ない (P4 の `TApplication` hwnd = `0x110000f` のみ確認)。`REPORT_564.md` §4 の 0x110000f (f4_e2e の post 実測) との差は未解決。
- **HEAD `530fb5ef` の再実行** (foreground 1 回・`EMSDK_ENV` と `FL_WIN64_DIR` 指定、`RETDEC` は絶対パス指定): **459 s, rc 0**。judge **14/14 PASS**、ネガコン 9/9 期待どおり FAIL、native selftest **504 passed / 0 failed**。`P4` hwnd `0x110000f`、`P5` hwnd `0x110000e`。`S1` 871/1/47/23/0 = base。`results/probe.json` の `util_window.ret` = `0x1100010` は、この e2e が使う flengine 複製 tree の IR から作った wasm の値。f4_e2e の post (`tools/m11/work` の IR) では `0x110000f`。build 差ではないことを `703b4857` で同一 tree の ff/soft 比較により確認済み (§6 現 HEAD 節)。
- 旧 `40e4e4b0` の値 (selftest 500/0・judge 12/12) は本 HEAD で 504/0・14/14 に変わった。増分の原因は未確認。

### HEAD `703b4857` の実測 (main `b892fdc6` 取り込み後・本 PR の最終 HEAD。本節を正とする)

| 対象 | rc | 所要 | 結果 |
|---|---|---|---|
| `bash tools/gui/flengine/e2e.sh` (foreground 1 回) | 0 | **464 s** (done 行) | judge **14/14 PASS**、native selftest **504 passed / 0 failed**、ネガコン N1〜N9 期待どおり FAIL。S1 `871/1/47/23/0` = base。`probe.json` の `util_window.ret` = `0x1100010` (flengine 複製 tree の IR) |
| `bash tools/gui/e2e.sh` (親, foreground 1 回) | 0 | **214 s** | **ALL PASS** (`SKIP_NATIVE` 無し。native selftest 504 / 0 も含む) |
| 同一 tree の ff / soft 比較 (`probe.mjs`, 同 HEAD) | 0 / 0 | — | ff `ret 0x1100010` = soft `ret 0x1100010` (build 差は無し)。窓: `TLightweightLayeredControl` 0x110000e、`TApplication` 0x110000f |

- ret の出所: `f4_e2e` の post (`0x110000f`) は `tools/m11/work` の `boot_final.ll` (sha256 `fd059f2f…`)、本 e2e の probe (`0x1100010`) は複製 tree の `boot_final.ll` (sha256 `a57be8fd…`) から作った wasm の値。同じ tree の ff/soft では一致するため、差は IR の出所によるものと推定 (未判定)。

### 旧 HEAD `3885765a` の実測 (参考)

| 対象 | rc | 所要 | 結果 |
|---|---|---|---|
| `tools/gui/flengine/e2e.sh` (n=3) | 0 / 0 / 0 | **153 / 146 / 149 s** (e2e.sh の done 行。`time` の real は 2m33 / 2m27 / 2m29 の実測) | judge **12/12 PASS** ×3、native selftest 500 passed / 0 failed ×3、pe_image P1・P2・N1・N2 PASS ×3、parity exit 0 (P1 LB=0 / LB=0x10000 PASS、補正 10,284 = m11_data_gen.py) ×3、ネガコン N1〜N5 期待どおり FAIL ×3 |
| `tools/gui/e2e.sh` (親, 1 回) | 0 | **wall 124 s** (`time` real 2m04) | **ALL PASS** (step 0〜6h の全 PASS。step 6 (headless Chrome E2E) は `tools/e2e` の `npm ci` 後に実行) |

- judge の一致 (3 回): B1 `units_run 52 (base 52)` / `threw memory access out of bounds (base 同じ)`、L1 `0/0/0`、A1 `177 = 177 (impl 159 / stub 18)`、S1 `871/1/47/23/0 (base 871/1/47/23/0)`、S2 `LoadImageW` のみ fail-fast (ff 1 unit) = soft STUB、R1 first `LoadStringW` (calls=3)、R2 reached 32 (floor 19)、P1 atoms `[-16383, -16382]` / `RegisterClassW=2 CreateWindowExW=3`、P4 hwnd `0x210000e`。
- `results/probe.json` の `gui_shared_ptr` は実行ごとに変わる値 (ヒープ位置)。判定は範囲チェックのため PASS に影響しない。
- 前提の補足 (親 e2e): 最初の run は worktree に root の `node_modules` が無く step 5 の `tsc` が rc 127 で落ちた。`pnpm install --frozen-lockfile` 後に ALL PASS。`tools/e2e` の `npm ci` (agent-browser / puppeteer-core) を入れて step 6 を実行。どちらも環境の前提で、コードは変えていない。

### 旧 HEAD の実測 (参考・現 HEAD の値ではない)

以下の表と箇条書きは旧 HEAD `a927ac87` と `de8d603e` 時点の実測。現 HEAD の実測は上の表を正とする。
前提: 素材 `fl-win64` ([WIN64] = `$ANALYSIS_DIR/win64` に展開)、`work-m11` (`tools/m11/work/` に展開。e2e は読取のみで、複製 `tools/gui/work/flengine/snap/` 側で使う)、`toolchain-emsdk` ([EMSDK])、`toolchain-retdec` ([RETDEC])、`apt-mingw` (`x86_64-w64-mingw32-gcc`)、Python の pefile・capstone (runner の system python は PEP 668 で pip 不可のため venv を作って PATH の先頭に置いた)。`m11_gen_ir2.sh` を素材の `tools/m11/work/` で 1 回実行して `ir_conditions.json` の `ldfix=applied` を作った。

以下の表は main 取込み前の HEAD `a927ac87` の実測 (参考)。現 HEAD `de8d603e` の実測は上の箇条書きを正とする。

| 回 | rc | 所要 (e2e.sh の done) | load 開始 → 終了 | judge | native selftest (`tools/gui/test`) | pe_image parity / e2e | ネガコン |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 211 s | 1.13 1.02 0.60 (終了時) | 12/12 PASS | 433 passed / 0 failed | P1 LB=0・LB=0x10000 PASS、N1〜N3 PASS / pe_image P1・P2・N1・N2 PASS | 5/5 期待どおり FAIL |
| 2 | 0 | 212 s | 1.06 1.02 0.70 (終了時) | 12/12 PASS | 433 passed / 0 failed | 同上 | 5/5 期待どおり FAIL |
| 3 | 0 | 212 s | 1.02 1.01 0.77 (終了時) | 12/12 PASS | 433 passed / 0 failed | 同上 | 5/5 期待どおり FAIL |

- 3 回の一致: B1 `units_run 52 (base 52)` / `threw memory access out of bounds (base 同じ)`、L1 undefined/sigmismatch/duplicate `0/0/0`、A1 `177 = 177 (impl 159 / stub 18)`、S1 `871/1/47/23/0 (base 871/1/47/23/0)`、S2 `LoadImageW` のみ fail-fast (ff 1 unit) = soft STUB、R1 first `LoadStringW` (calls=3)、R2 reached 32 (floor 19)、P1 atoms `[-16383, -16382]` / `RegisterClassW=2 CreateWindowExW=3`、P4 hwnd `0x210000e`。
- parity (`pe_image_parity.py --pe block00031_PE.bin`): `.data` 補正 10,284 件 = m11 `m11_data_gen.py` の 10,284 件 (LB=0 / LB=0x10000 とも一致)。PR 側の旧 off-by-one (`<`) は `c39ca16` で `<=` に直済み (レビュー必須 1)。
- 所要は 211–212 s (e2e.sh の done 行)。
- IR provenance (`results/ir_sha256.txt`): 今回は素材の `boot_final.ll` を `m11_gen_ir2.sh` で作り直した (ldfix=applied)。material `boot_final.ll` = `995351f5…` (旧記録 `69c774de…` は素材そのままの IR の指紋)。`boot_final3.ll` は `010451ad…` (不変)。`m11_build.sh` 後は `boot_final.ll` `2be93e55…`・`boot_final3.ll` `ac64ad01…`。
- 親 `bash tools/gui/e2e.sh` (受入条件 2): **ALL PASS / rc 0** (HEAD `de8d603e`、1 回・wall 194 s、load 2.37 1.69 1.31 (終了時))。前提 `tools/e2e` の `npm ci` (rc 0)・`pnpm install --frozen-lockfile` (rc 0) を先に実行。初回 run は前提不足 (`tsc`・`agent-browser` 不在) で落ちたため、前提を入れてから再実行した。
- HEAD `de8d603e` (main `6aa4b397` 取込後) の flengine e2e (n=3): rc 0 / 0 / 0、所要 **215 / 219 / 219 s** (done 行)、judge 12/12 PASS ×3、native selftest 500 passed / 0 failed (main の追加テスト込み)、ネガコン N1〜N5 期待どおり FAIL ×3。
- `results/probe.json` の `gui_shared_ptr` は実行ごとに変わる値 (ヒープ位置。3 回目の実行の値を残した)。判定は `gui_shared_ptr_ge_0x10000` (範囲チェック) なので PASS には影響しない。
- `results/*.json` と `IMPORTS.md` は今回の 3 回目の run で再生成。`IMPORTS.md` は `CharLowerW`・`CreatePalette`・`EnumFontFamiliesExW`・`MessageBoxA` が「P2/P3 昇格候補」から外れた (実装済みのため)。

ネガティブコントロール (全て「期待した FAIL 行が出る」まで検査。judge のクラッシュを FAIL 確認と誤認しない。run1 で確認):

| NC | 壊し方 | 結果 |
|---|---|---|
| N1 | 到達ログ無し (`--plain`) ビルドの起動を判定 | R1 FAIL, exit 1 |
| N2 | baseline の units_run 期待値を 23 に | B1 FAIL, exit 1 |
| N3 | 到達 floor に未到達 API `NoSuchGuiApi` を 1 つ追加 | R2 FAIL (floor 20 / reached 32), exit 1 |
| N4 | survey の 1 unit を ok→trap に改竄 | S1 FAIL, exit 1 |
| N5 | `GetDC(NULL)` を元の fail-fast に戻した shim で native selftest | `FAIL-FAST: unimplemented Win32 API: GetDC`, exit 134 |

- 範囲外: 実ブラウザ・Canvas 描画、audio、UI スレッドのスタック量、`gui_reach` の性能影響 (INTEGRATION §4-12 の未計測は継続)。

## 6b. WNDCLASS 静的実体の WNDPROC を closure に加える (#565 / M11-N20)

**判定: 受入条件 3 つとも達成**。PE の `.data` から WNDCLASS 静的実体を走査し (`tools/m11/m11_wndclass_scan.py`)、closure 外の WNDPROC を seed に RetDec で lift (boot5) して IR に結合する流れを 1 コマンド化した (`bash tools/m11/m11_wndseed.sh`)。
新規 lift 欠陥は無し (DEFECTS.md 該当なし)。issue 記載の `0x31dd10` は **RVA**で、VA は `0x71dd10` (m11 の LVA は RVA 座標)。

| 項目 | 実測 | 定義 / 分母 |
|---|---|---|
| WNDCLASS 静的実体 | **11 件** (全て `.data`) | `.reloc` DIR64 の +8 が `.pdata` 関数先頭/import thunk、+64 が識別子風文字列、+16/+20/+24..+56 が妥当な全条件 AND。棄却 = 関数でない 132,128 / フィールド不整合 120,306 / 名前不正 41 (`results/wndclass_scan.json`) |
| WNDPROC の内訳 | 関数 **8** 本 (全て distinct) + `DefWindowProcW` import thunk (`0x424920`) **3** 件 (TPUtilWindow / TApplication / VTPanningWindow) | thunk は closure 外だが `gen_thunks.py` が shim へ解決済み (§2-1 #5) |
| closure 内 / 外 (seed 導入前 = boot0..4, 7,421 関数) | **内 0 / 外 8** | 0x6d8330 TTimerWindow, 0x71dd10 TLightweightLayeredControl, 0xc3e940 flpianoroll.Marker, 0xc3f060 flpianoroll.Pattern, 0xd2e620 flcpt.ChordAlternative, 0xd339b0 flrack.Channels, 0xd70600 TILRemoteWindow, 0xd82150 flmidimsg |
| seed の閉包 | 8 WNDPROC → call/jmp 即値を辿り **1,212 関数 / 398,396 B** を追加 (うち import thunk 6B 関数を含む) | 既存 lift 済みに当たったら止める。境界は `.pdata` + import thunk |
| lift / IR | RetDec boot5 **2 分 0.5 秒** (1,212 range)。`m11_gen_ir2.sh` 30.0 秒。IR 定義関数 **7,421 → 8,647** (+1,226 = 閉包 1,212 + RetDec の内部入口別関数化 14)。未定義 `function_*` は **8 → 8 (同一集合)** | 初回 (thunk 抜き 1,179 range) は未定義が 33 に増えたため、import thunk と遅延 import スロットの 6B 関数を閉包に含めた (2 回目 1,210 → 3 回目 1,212 で収束) |
| wasm | 6,021,637 → **6,905,826 B**、`wasm-ld` signature mismatch 0 / undefined 0 / duplicate 0 (m11 と GUI 結合の ff・soft) | `disp_entries` 7,399 → 8,621 |
| 起動・survey の回帰 | units_run **22** / init_count **23** / dllmain_done true / GetMem 33 / FreeMem 20 / icall_miss 0 は不変。survey の値は §6c (HEAD `19ebb43`: 864/1/46/31) | baseline (m11 単体) と GUI 結合の双方を新 IR で再測 |
| 指向 probe | `TLightweightLayeredControl` の `CreateWindowExW` が **NULL → hwnd 0x110000e** (WNDPROC `0x31dd10` = closure 内の `function_71dd10` へ `m11_icall` ok)。`RegisterClassW` ×2 / `TApplication` hwnd 0x110000f も維持 | gate **P5** (旧 REPORT §4 の OPEN の解消)。hwnd 値は GUI 関数が増えて採番が変わった (旧 0x210000e) |

残る観測: probe の `m11_icall` miss は 3 件 (target `0x6c6f` 1 種)。`function_71dd10` が WM_NCCREATE で `[lpCreateParams+0x78]` を `SetWindowLongPtrW(GWL_WNDPROC)` に渡す経路で、probe の `lpParam=NULL` だと低位メモリの値が WNDPROC になるためと**推定** (偽オブジェクトに `0x24920` を置いた追試でも 0x6c6f のままだったため、この仮説は**未確認**。再現・原因は未調査)。窓生成自体は成功する。
`function_52a7f0` (AllocateHWnd) の `RegisterClassW` 脱落 (§5-2) は本 issue の範囲外で未解決のまま (judge の OPEN 行)。

### 6b-1. 検証 (W1 / P5 / ネガコン N6〜N9。実測値は §6b-2)

- **W1** (走査 gate): 検出 WNDCLASS ≥ 11 かつ fn WNDPROC ≥ 8 かつ最終 IR に未定義の WNDPROC = 0。**P5**: `TLightweightLayeredControl` の hwnd が 31bit 内かつ `m11_icall` ok > 0。
- ネガコン (期待した FAIL 行まで検査): **N6** seed 導入前 IR (boot0 のみ) で `--check` → `WNDCLASS-CHECK FAIL` / **N7** その走査 JSON を judge → W1 FAIL / **N8** 検出 floor を実測+1 → floor FAIL (空振り PASS 防止) / **N9** hwnd=NULL の probe → P5 FAIL。
- `m11_wndclass_scan.py --check` は 走査 0 件・未定義 WNDPROC のどちらでも exit 1 (終了コードをそのまま gate に使う)。

### 6b-2. 実測 (コード commit `b867b94` の HEAD、`git status --porcelain -- tools` 空で実行)

- `bash tools/gui/flengine/e2e.sh`: **rc 0 / 160 秒** (load average 開始 0.35 → 終了 1.04)。judge **14/14 PASS** (W1 / P5 追加)、native selftest 324 passed / 0 failed、ネガコン **9/9** が期待した FAIL 行つきで FAIL (N1〜N5 既存、N6〜N9 追加)。実行前の同内容 (未 commit) の 1 回目も rc 0 / 163 秒・同一結果。
- `bash tools/gui/e2e.sh` (受入条件 3): 1 回目 **rc 1** — step 1 の native selftest (ASan) が `heap-use-after-free` (`gui_headless.c:33 blit_surf` を render スレッドが読み、`gui_core.c:174 surf_free` を main スレッドが先に解放)。同じ HEAD で再実行した 2 回目は **rc 0 / 61 秒** (selftest 324 passed、native lift・Chrome とも golden EXACT MATCH 0/64000 px、reach_test 11 / adapt_test 28 passed)。
  この PR は `tools/gui/src`・`test`・`include` を **変更していない** (`git diff a38ba81 HEAD` が空)。selftest 単体を 3 連続実行した結果は 3 回とも 324 passed / 0 failed。1/6 回の失敗の原因 (render スレッドと surface 解放の競合と推定、**未確認**) は未調査 → §7。
  なお最初の rc 1 の前に、新規 worktree に `node_modules` が無く step 5 (tsc) で rc 1 になる環境起因の失敗が 1 回あった (本 PR と無関係。symlink で解消)。
- 環境: runner 4 vCPU、素材 work-m11 + fl-win64 (PE は `FL_WIN64_DIR` 参照。§6c の再測は symlink 無しで実行)。`m11_wndseed.sh` の lift 実測: RetDec 1,212 range が 2 分 0.5 秒 (3 回目) / gen_ir2 30.0 秒。

## 6c. HEAD 再測 (review #576 指摘 1・4 への対応。修正 HEAD `19ebb43`)

main 取込後の木 (`c37522c`) で S1 が FAIL (828/67 vs 864/31) したため切り分けし、`run.mjs --survey` の隔離手順の差を修正した (commit `19ebb43`)。順序は `m11_wndseed.sh` → `flengine/e2e.sh` → `gui/e2e.sh`。素材は work-m11 / fl-win64 (`FL_WIN64_DIR`)、`toolchain-retdec` / `toolchain-emsdk` ([RETDEC] / [EMSDK] の展開先)、`apt: gcc-mingw-w64-x86-64`、capstone / pefile、`pnpm install --frozen-lockfile`。

| 実行 | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` (HEAD `c37522c`) | rc 0。WNDCLASS 11 件 / fn WNDPROC 8 / 最終 IR で未定義 0 (`WNDCLASS-CHECK PASS`) | 2 分 44 秒 |
| `bash tools/gui/flengine/e2e.sh` (修正前 `c37522c`) | rc 1。judge **13/14** (S1 のみ FAIL: 828/1/46/67) | 3 分 13 秒 |
| `bash tools/gui/flengine/e2e.sh` (**HEAD `19ebb43`**) | rc 0。**JUDGE PASS 14/14**。S1 = 864/1/46/31 (base 一致)。ネガコン N1〜N9 は 9/9 が期待どおり FAIL。selftest 0 failed | 2 分 36 秒 (load 0.45 → 0.97) |
| `bash tools/gui/e2e.sh` (**HEAD `19ebb43`**) | rc 0。ALL PASS (bpp / text / simd / present / Chrome E2E / fail-fast / reach-log / sigprobe)。ASan UAF は本回に出ず | 1 分 33 秒 |

### 6c-4. 現 HEAD `c4e3c064` の再測 (main `97f28539` を merge commit `986d8a67` で取込済み。`/opt` 絶対パスを REPORT から除去)

素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-m11` → `tools/m11/work/`、`toolchain-retdec` / `toolchain-emsdk` を [RETDEC] / [EMSDK] として使用 (`PATH` / `EMSDK_ENV`)、capstone 5.0.7 / pefile 2024.8.26、`pnpm install --frozen-lockfile`、`tools/e2e` は `npm install --no-save`。

| 実行 (HEAD `c4e3c064`, 2026-10-13 UTC) | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` | rc 0。`WNDCLASS-CHECK PASS` (WNDCLASS 11 / fn WNDPROC 8 / 最終 IR 未定義 0) | 146 秒 (load 0.53 → 0.95) |
| `bash tools/gui/flengine/e2e.sh` | rc 0。**JUDGE PASS 14/14**。native selftest 500 passed / 0 failed。ネガコン N1〜N9 は 9/9 が期待どおり FAIL | 188 秒 (load 0.80 → 1.11) |
| `bash tools/gui/e2e.sh` | rc 0。**ALL PASS** (`stress` の readback は golden と EXACT MATCH 0 px / 64000) | 132 秒 (load 1.88) |

- judge の各 gate: L1 (ff・soft) PASS / A1 declare=193 = adapter=193 (impl 173 / stub 20) / B1 units_run 52 = base 52 / R1 `LoadStringW` IMPL / R2 reach 32 ≥ floor 19 / **S1 871/1/47/23/0 = base 871/1/47/23/0 PASS** / S2 ff・soft とも STUB `LoadImageW` / P1〜P5 PASS (P5 hwnd `0x110000e`) / W1 PASS (外 0)。
- 本 run は 1 回の実測。繰り返しは行っていない。
- 初回失敗はいずれも環境要因で、コードの変更ではない: (a) `EMSDK_ENV` 未指定で `emcc` 不在 (rc 2)、(b) worktree の `node_modules` 不在 (rc 127)、(c) `tools/e2e/node_modules` 不在で agent-browser が ENOENT (rc 2)。(a)〜(c) を入れた後の rc 0 を上表に記録した。
- 直前の `f1e88c82` / `3d433c6f` で出た S1 FAIL (869/1/47/25 vs base 871/1/47/23) は、`c4e3c064` と `e9007ec` の実測では再現しない。**原因は特定していない** (unit 304 / 555 の差は未切り分け)。判定式は緩めていない。

### 6c-3. 旧 HEAD `e9007eca` の再測 (main `1adff847` を merge commit で取込済み。e2e の `m6/ottlib.py` 複製を追加)

素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`work-m11` → `tools/m11/work/`、`toolchain-retdec` → [RETDEC] (`RETDEC`)、`toolchain-emsdk` → [EMSDK] (`EMSDK_ENV`)、`apt-mingw` (`x86_64-w64-mingw32-gcc`)、pefile 2024.8.26 / capstone 5.0.7 (`python3 -m pip install --user`)、`pnpm install --frozen-lockfile` (ルート)、`tools/e2e` は `npm install --no-save` (agent-browser 0.39.0。repo に lockfile が無いため `--no-save` で入れた)。

手順は WORKFLOW どおり `m11_wndseed.sh` (boot6 lift + 最終 IR) → `flengine/e2e.sh` → `gui/e2e.sh`。

| 実行 (HEAD `e9007eca`) | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` | rc 0。`WNDCLASS-CHECK PASS` (WNDCLASS 11 / fn WNDPROC 8 / 最終 IR 未定義 0) | 2 分 13 秒 (user 2 分 13 秒) |
| `bash tools/gui/flengine/e2e.sh` run 1 | rc 0。**judge 14/14 PASS**。selftest 500 passed / 0 failed。ネガコン 9/9 が期待どおり FAIL | 175 秒 (load 0.99 → 0.90) |
| 同 run 2 | rc 0。judge 14/14。S1 871/1/47/23 = base | 176 秒 (load 1.00 → 0.92) |
| 同 run 3 | rc 0。judge 14/14。S1 871/1/47/23 = base | 175 秒 (load 1.01 → 0.95) |
| `bash tools/gui/e2e.sh` | rc 0。**ALL PASS** (simd / text / present / input / stress / Chrome E2E。ネガコン含む。ASan UAF は本回に出ず) | 2 分 1 秒 (121 s。`node_modules` 準備後の 1 回) |

- judge の各 gate (run 1〜3 共通): L1 (ff・soft) PASS / A1 declare=193 = adapter=193 (impl 173 / stub 20) / B1 units_run 52 = base 52 / R1 `LoadStringW` IMPL / R2 reach 32 ≥ floor 19 / S1 871/1/47/23/0 = base / S2 ff・soft とも STUB `LoadImageW` / P1〜P4 PASS / W1 PASS (外 0) / P5 PASS (hwnd 0x110000e)。
- 前段の 13/14 (S1 のみ FAIL: 869/1/47/25) は、取り込み前の main (`fe53ba30`) で出ていた値。main 取込後の `e9007eca` では base と一致し、判定式は一度も緩めていない。差分の詳細 (unit 304 / 555) は取込前の HEAD での調査結果で、現 HEAD では再現しない。
- `gui/e2e.sh` の初回は step 5 (tsc) と step 6 (agent-browser) が worktree に依存が無いため落ちた (rc 1 / rc 2)。環境起因で本 PR の変更とは無関係。依存を入れて rc 0 を得た。
- 素材の注意: `work-m11` の `boot0..4` は素材のまま、`boot6` は `m11_wndseed.sh` で作る必要がある。`m11_gen_ir2.sh` 単独では WNDPROC 8 件が未定義になり W1 FAIL。

### 6c-2. HEAD `b3819e2` の再測 (review #576 指摘 2 への対応・素材 `work-m11` / `toolchain-*` / `apt-mingw` を展開して実行)

素材: `work-m11` → `tools/m11/work/` (1.6 GiB)、`toolchain-retdec` (RetDec v5.0)、`toolchain-emsdk`、`fl-win64`、`apt-mingw` (`x86_64-w64-mingw32-gcc` は runner 既定で存在)、capstone 5.0.7 / pefile 2024.8.26、`pnpm install --frozen-lockfile`。

| 実行 (HEAD `b3819e2`) | 結果 | 所要 (実測) |
|---|---|---|
| `bash tools/m11/m11_wndseed.sh` | **rc 0**。WNDCLASS 11 / fn WNDPROC 8 / 最終 IR 未定義 0 (`WNDCLASS-CHECK PASS`)。boot6 lift 1212 関数 → 8648 defines | 2 分 52 秒 (172 s) |
| `bash tools/gui/flengine/e2e.sh` | **rc 1**。judge **12/14 FAIL**。FAIL は **B1** (`units_run 52 (base 52)` / `dllmain_done False` / `GetMem 560 FreeMem 20` / `icall_miss 5`) と **S2** (ff 側 fail-fast 集合 `LoadImageW`・`SystemParametersInfoW` ⊄ soft STUB `LoadImageW`)。L1・A1・R1・R2・S1 (865/1/47/29)・P1〜P5・W1 は PASS。ネガコン 9 本は FAIL 期待どおり | 3 分 21 秒 (201 s) |
| `bash tools/gui/e2e.sh` | **rc 0**。ALL PASS (text / simd / present / Chrome E2E)。**ASan UAF は本回に出ず** | 1 分 45 秒 (105 s) |

- **B1 の FAIL は GUI shim の回帰ではない**: 同じ IR で GUI shim 無しの `baseline_boot.json` 自体が `units_run 52 / dllmain_done false / boot_threw "memory access out of bounds"` になる。REPORT §6c 冒頭の期待値 (units_run 22 / init 23 / dllmain true) とは別物。素材 `work-m11` は #516 以前の生成で、現 main の手順と一致しない (WORKFLOW §11・#680)。`boot0..4` を現 main の `m11_e2e.sh --full` から再生成していないことが原因と**推定** (未確認)。
- **S2 の FAIL**: `SystemParametersInfoW` が ff survey で fail-fast 到達 (3 unit) だが soft 側は STUB 判定の集合に入らない。§3 の表では `SystemParametersInfoW` は P0 の「実装済み」扱いで、今回の素材 (`work-m11` 由来の IR) では別の経路で fail-fast に落ちている。原因は未調査。
- 結論: **HEAD `b3819e2` の flengine gate は 14/14 にならなかった** (`19ebb43` の 14/14 は素材の IR が違う時点の値で、現素材では再現しない)。PR は「未達」を明記して出す。

### S1 の切り分け (結論: shim の回帰ではなく survey ハーネスの隔離不足)

- unit 単位の結果を取得した。baseline (shim 無し, `m11_survey.mjs` の `M11_SURVEY_UNITS`) と GUI 結合 (soft) を突き合わせると、差は **36 unit の ok→trap** のみで、全て `halt0->longjmp` だった。
- 同じ GUI 結合 wasm を **`m11_survey.mjs` の手順で**回すと `864/1/46/31` になり、942 unit の結果が baseline と **1 件も違わない** (`GUI 結合 wasm × m11_survey.mjs` = baseline)。
- 差は `run.mjs --survey` だけにあった。`m11_survey.mjs` は unit ごとに `_m11_va_unit_begin()` で VA 上限を張り直し、unit が書いた image を実行前へ戻すが (clobber 対策)、`run.mjs` はこれを省いていたため、前 unit の状態を引きずって 36 unit が Halt0 で落ちていた。
- 修正: `run.mjs --survey` に `_m11_set_va_unit_budget` / `_m11_va_unit_begin` / unit 単位の image 復元を入れ、`m11_survey.mjs` と同じ手順にそろえた。shim 本体は変更していない。

(`19ebb43` 時点の値。HEAD `b3819e2` 以降の judge は上表のとおり 12/14 で、本段落は現 HEAD の結果ではない) judge の 14 gate は当時全て PASS: L1 (ff・soft) / A1 / B1 (units_run 22・init 23) / R1 (`LoadStringW` IMPL ×4) / R2 (到達 23 ≥ floor 19) / S1 (864/31) / S2 / P1〜P4 / P5 (`TLightweightLayeredControl` hwnd `0x110000e`) / W1 (WNDCLASS 11・fn WNDPROC 8・外 0)。
- R2 の到達は 23 (floor 19)。`run.mjs` の survey は unit 隔離の修正で到達集合が増えた (floor は未更新。下限として有効)。

### 発見 (本 PR 外)

- `tools/gui/flengine/e2e.sh` の前提: `x86_64-w64-mingw32-gcc` は runner 既定に無く `apt-get install gcc-mingw-w64-x86-64` が要る (`oc_artifacts` の `apt-mingw` で入る)。
- `tools/m11/m11_survey.mjs` 単体の `M11_SURVEY_UNITS` 出力は、`run.mjs` と同じ `[i, label]` 形式ではなく `label` の配列 (`perUnit` は文字列配列)。比較時は index で突き合わせる。

## 6d. 現 HEAD 節 (review #577 対応。HEAD `bf9cf547`)

review `b9f0b32b` の指摘 1 (S1) と 2 (run.mjs のコメント) への対応。

- **S1 の切り分け (実測)**: baseline と soft は **同じ `run.mjs --survey` 経路・同じ VA 予算 256 MiB** で取っており、予算の差ではない (前回の「baseline は m11_survey.mjs 既定 256 MB」は `e2e.sh` の経路変更で成立しなくなっていた)。`baseline_base_survey.json` と `survey_soft_units.json` を unit 別に突き合わせると、差は **unit 304 と 555 の 2 件のみ** (base `ok` / soft `memory access out of bounds` の trap)。ok/trap 以外の差は無い。shim の有無で build が違うため、この 2 件は shim 組込み後の wasm 側の挙動差 (未特定)。
- 単独 unit の再現 (`m11_base.cjs` / `m11_gui_soft.cjs` を unit 304・555 で単独実行) は、両方とも trap したため切り分けに使えず、原因は未特定。
- **判定**: S1 は FAIL のまま (870/1/47/24/0 vs 872/1/47/22/0)。判定を PASS に動かす変更は入れていない。judge 13/14。
- `run.mjs` 4 行目のコメントを実装 (既定 256 MiB) に合わせた。

本節の実測は **HEAD `125fefd2`** (コード差分なし。`bf9cf547` の測定値を含む) で取り直した値。実行環境: runner 4 vCPU、`apt-mingw` (`x86_64-w64-mingw32-gcc`) を apt 導入、`[EMSDK]` (`EMSDK_ENV` で指定)、`fl-win64` / `work-m11` を展開。

| 実行 (HEAD `125fefd2`・foreground・1 回) | rc | 所要 | 結果 |
|---|---|---|---|
| `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> FL_WIN64_DIR=<[WIN64]> ANALYSIS_DIR=… RETDEC=<[RETDEC] の retdec-decompiler> bash tools/gui/flengine/e2e.sh` | **1** | 466 s (load 0.68→1.09) | judge **13/14**。S1 のみ FAIL: `870/1/47/24/0` vs base `872/1/47/22/0`。他 13 gate PASS (L1×2・A1 declare=193 adapter=193 impl=173 stub=20・B1 units 52・R1 LoadStringW・R2 reach 33≥19・S2・P1〜P5・W1)。ネガコン N1〜N9 期待どおり FAIL。selftest 506 passed / 0 failed |
| `EMSDK_ENV=… FL_WIN64_DIR=… bash tools/m11/ldfix/f4_e2e.sh` | **0** | 385 s (load 1.00) | 6 gate PASS (F1/F2/D1/D2/P1/A1)。ネガコン 4/4 期待行付き FAIL。RegisterClassW 2→2→3。`function_52a7f0` ret pre `0x0` → noand `0x0` → post **`0x110000f`**。survey pre/noand/post = `870/1/47/24`。`ir_sha256.txt` の `after_m11_build` 行は再生成で変化 (下記 §6d-2) |
| `EMSDK_ENV=… FL_WIN64_DIR=… bash tools/gui/e2e.sh` | **0** | 302 s (load 2.28) | ALL PASS (SIMD / present / input / stress (negctl 2/2 exit 1) / pe_image / selftest 506/0) |

**S1 の判定**: 上表のとおり FAIL のまま。判定式は変えていない。unit 304 / 555 の差 (soft 側のみ `memory access out of bounds`) の原因は未特定。同じ unit 304 / 555 の oob を扱う OPEN issue として [M11-N78] #1275 (`ClassCreate ON で unit 304/555 が oob→abort`) があるが、原因が同一かは未確認。起票先は #1275 にコメントで接続する。

### 6d-2. `function_52a7f0` の ret 値の対応 (同一 build 内の不整合ではない)

| 測定元 | IR の作り方 | 窓の採番 (probe) | `function_52a7f0` ret |
|---|---|---|---|
| `f4_e2e.sh` post (`0246df1f`〜`125fefd2`) | `m11_gen_ir2.sh` → `m11_build.sh` | `TLightweightLayeredControl` = `0x0` (未生成)、`TApplication` = `0x210000e` | `0x110000f` |
| `flengine/e2e.sh` probe (`125fefd2`) | 上記に加え `m11_wndseed.sh` (boot6 seed。WNDPROC 閉包を追加) | `TLightweightLayeredControl` = `0x110000e`、`TApplication` = `0x110000f` | `0x1100010` |

- 両者とも soft build・同じ `probe.mjs` で取っている。差は IR (`m11_wndseed.sh` の有無) で、`e2e.sh` は step 0 で wndseed を回し、`f4_e2e.sh` は回さない (スクリプトで確認済み)。窓の採番が変わる機構は推定 (未検証)。
- したがって受入条件 3 の値は **「f4 の IR (wndseed 無し) では `0x110000f`、wndseed 込みの最終 IR では `0x1100010`」**。どちらも `0x0` からの修復を示す。一意の値は wndseed 込みの最終 IR (flengine の値) とする。f4 の値は f4 の構成でのみ有効。

### 6d-3. 注記 (run 上の前提)

- `x86_64-w64-mingw32-gcc` は runner に無かったため `apt-get install gcc-mingw-w64-x86-64` で導入 (`apt-mingw` 素材の代替)。初回の flengine e2e は前提欠如 (rc 2) で止まり、導入後に再実行。
- `tools/m11/work` は `work-m11` の展開先 (gitignore。commit しない)。


注記: `tools/gui/e2e.sh` の初回は `node_modules` 不在で step 5 (tsc) が rc 127 だった (`pnpm install` で解消。環境要件)。

## 6i. S1 (soft) の unit 304/555 調査 (#1442 / GUI-21)

結論 (測定 commit `719f1c43`・judge 13/14・S1 `870/1/47/24/0` vs base `867/1/47/27/0`): 304/555 は base・soft 両方で OOB (真因は #1426 で未達)。S1 は FAIL のまま (差は 101/291/296 の 3 unit)。

| 判定 gate (現 HEAD) | 結果 | 備考 |
|---|---|---|
| S1 survey parity (soft) | FAIL `870/1/47/24/0` (base `867/1/47/27/0`) | 判定式は不変。FAIL は未解消 |
| S2 soft adds no fail-fast beyond ff | PASS | 判定式は `8a6dcf4b` (main) 由来。本 PR では不変 |

詳細と実測値は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §6i (測定 commit `719f1c43`・鮮度の範囲を含む)。

WIN-4 (#2715・部分達成): `CreateFruityInstance` の閉包 (2,071 関数) を boot7 として取り込み、呼出しまで到達した (`EnterCriticalSection` で fail-fast)。測定 commit `5f9d7cbd`・判定と未解決は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §7 を正とする。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `RegisterClass*` / `CreateWindowEx*` の自然到達 (#134 / #490 の先) | 受入条件 1 | #134 / #490 に依存。到達後に `bash tools/gui/flengine/e2e.sh` の INFO 行が変わる (R2 floor を更新) |
| `function_52a7f0` の `TempClass.lpfnWndProc` load 脱落 (§5-2) | AllocateHWnd 経路 (TPUtilWindow = Timer / 非同期 window) が全滅 | PM 起票依頼 (DEFECTS 行案あり。既存 ldfix issue は未特定。#505 は MERGED のため不可) |
| WNDCLASS 静的実体の WNDPROC を closure seed に追加する pass (`TLightweightLayeredControl` 0x31dd10 ほか) | その class の窓生成が NULL | PM 起票依頼 (m11 / icall 系。#90 の間接 call 復元と近い) |
| `LoadImageW` の実装 (STUB、survey 21 回・ff で 1 unit が停止) | ff ビルドでは 1 unit が止まる | PM 起票依頼 (GUI-2 系 P2 stub 昇格。#174 に所見) |
| `SystemParametersInfoW` の未対応 action (例: `0x101a` SPI_GETICONTITLELOGFONT 相当) は FALSE 返却。LOGFONTW の値は未実装 (§5-5) | 当該 action を呼ぶ経路で FL の見た目が既定値と異なり得る | PM 起票依頼 (LOGFONTW の FL 実機値の確認と実装。shim の SPI 対応範囲) |
| `LoadStringW` の資源 ID 供給 hook (`gui_set_resource_provider` ← shimx / PE .rsrc) | LoadStringW が常に空文字 | #174 に所見 / GUI-2 または shimx |
| survey の順序依存 (非 pthread と pthread で 10 unit が trap↔ok で動く、§5-6) | survey の unit 別結果が build 条件と前 unit の状態に依存する。S1 の比較は同一 build (`--base`) に限る | PM 起票依頼 (m11 survey 隔離の状態汚染。m11 側の件) |
| 実ブラウザ host 結線 (`GuiHost.attach`・FL ワーカ化・UI スレッドのスタック量 §2-2 #8) | node の headless host のみ。描画 (#32) は別 | #32 / #121 |
| `tools/m11/m11_e2e.sh` が PE パスを `[ANALYSIS-DIR]` の固定既定値で持つ (`[WIN64]` 経由にしていない)。`m11_gen_ir2.sh` は本 PR で `FL_WIN64_DIR` 参照に変更済み | `m11_e2e.sh` を直接使うと runner では ldfix が黙ってスキップされ数値が変わる。本 PR の測定は `m11_gen_ir2.sh` (FL_WIN64_DIR 経由) を使う | m11_e2e.sh に `FL_WIN64_DIR` 参照を入れる件は PM 起票依頼 (#132 の未解決と同件) |
| 前回 run で観測した selftest (ASAN) の `heap-use-after-free` (`gui_headless` の描画スレッドと `surf_free`。前 run で約 2/8 で再現) | 本 HEAD の 3 回では再現せず (433/0 ×3)。HEAD 7d44c033 の 1 回 (500/0) でも再現せず。main 側の #489 系 (headless surface UAF) の merge を含む HEAD での結果。再現率の定量確認は未実施 | PM 起票依頼 (gui_headless の描画と surf_free の排他) |

## 6e. 再測定と main 切り分け (PR #577 の PM 指示 1・2。測定 commit `a88aabfa`)

測定対象のコード差分は `22062917` 以降 0 (`git diff 22062917 a88aabfa -- tools/gui tools/m11` は `results/` のみ)。`a88aabfa` は `results/baseline_boot.json` と `results/ir_sha256.txt` の再生成のみ commit。

| 実行 (foreground・1 回・rc は実測) | rc | 所要 | 結果 |
|---|---|---|---|
| `flengine/e2e.sh` (HEAD `22062917`、`pnpm install` 前は gui/e2e.sh のみ tsc 欠落) | **1** | 304 s (load 1.00→1.00) | judge **13/14**。S1 FAIL `870/1/47/24/0` (base `872/1/47/22/0`)。他 13 PASS。P1 `RegisterClassW=3`、P4 `hwnd=0x110000f`、P5 `hwnd=0x110000e`。ネガコン N1〜N9 期待どおり FAIL |
| `flengine/e2e.sh` (**origin/main `c6f70c98`**、検証用 worktree `work/main_wt`) | **1** | — | **main 単体は build 段で停止**: `wasm-ld: duplicate symbol: GetMonitorInfoW` (#1096 `6f979463` の `tools/m11/m11_win.c` と `tools/gui/build/gui_adapt_w32.c` の重複)。S1 まで到達せず |
| 同 (main、重複 2 関数 `GetMonitorInfoW`・`EnumDisplayMonitors` を scratch で削除。**コミットしない**) | **1** | 301 s (load 1.00→1.00) | judge **13/14**。**S1 FAIL `870/1/47/24/0` (base `872/1/47/22/0`)**。S1 の値は HEAD と同一 |
| `gui/e2e.sh` (HEAD `a88aabfa`、`pnpm install --frozen-lockfile` 後) | **0** | 139 s (load 2.60→1.60) | ALL PASS (selftest 506/0、stress negctl 2/2 exit 1、text/pe_image/present/input ALL PASS) |
| `m11/ldfix/f4_e2e.sh` (HEAD `a88aabfa`) | **0** | 249 s (load 1.04→1.27) | 6 gate PASS (F1/F2/D1/D2/P1/A1)。ネガコン 4/4 期待行付き FAIL。RegisterClassW pre 2 / noand 2 / post 3。survey `870/1/47/24` |

**切り分けの結論 (PM 指示 1)**: S1 FAIL は main でも同じ値で再現する。したがって **この PR の変更が原因ではない**。S1 の判定は緩和していない (FAIL のまま)。原因特定は子 issue **#1442** (`[GUI-21]`、親 #564) に起票。#1275 ([M11-N78]) とは対象 unit が一致するが、同系統かは未確認。main でも同値 (S1 FAIL) であることは、この PR の原因ではないことの根拠。S1 の gate PASS の根拠ではない。追跡 #1442。

注記: main の build 段の重複は scratch の削除で回避しただけで、main 側の修正は行っていない。起票先は本 PR の範囲外 (`#1096` の作者 / m11 系の PM 判断)。

**ret 値の IR 併記 (PM 指示・受入条件 3)**: `function_52a7f0` の ret は IR ごとに異なる値。どの IR の値か:
- `f4_e2e.sh` の post IR (`m11_gen_ir2.sh` → `m11_build.sh`、wndseed 無し): **`0x110000f`**
- `flengine/e2e.sh` の最終 IR (wndseed 込み。`m11_wndseed.sh` を実行): **`0x1100010`** (§6d-2)

## 6g. 現 head の再測定 (review `bde0c341` 差し戻しの必須 2。main 取り込み後)

main `f3ffd7ba` 取り込み後の head `bde0c341` で、§6e の測定 commit `a88aabfa` 以降のコード差分を再測定した。`git diff a88aabfa bde0c341 -- tools/gui tools/m11` のうち `.sh`・`.py`・`.c`・`.h`・`.inc` 等の実行コードは `m11_win.c` (#1096 由来) と `gui/build/*` の main 側差分のみ (main が重複定義を持ち込んだ)。

| 実行 (foreground・1 回・rc は実測) | rc | 所要 | 結果 |
|---|---|---|---|
| `bash tools/m11/ldfix/f4_e2e.sh` (head `bde0c341`) | **2** | 86 s (load 0.59→1.03) | **build 段で停止** (gui build 失敗 (pre))。`wasm-ld: duplicate symbol: GetMonitorInfoW` と `EnumDisplayMonitors` (`obj/win.o` と `gui/gui_adapt_w32.o`)。F4 の gate には到達せず |
| `bash tools/gui/flengine/e2e.sh` (head `bde0c341`) | **1** | 325 s (load 1.12→1.33) | build 段で停止。`wasm-ld: error: duplicate symbol: GetMonitorInfoW` (同上 2 件)。judge は実行されず |
| `bash tools/gui/e2e.sh` (head `bde0c341`) | **0** | 301 s (load 3.47→0.89) | ALL PASS (simd / 6c/6 fail-fast / present / input / stress (negctl 2/2 exit 1) / selftest 506 passed 0 failed)。ASan の `heap-use-after-free` 等の出力 0 件 |

**判定 (bde0c341 時点の記録)**: `gui/e2e.sh` は PASS。`flengine/e2e.sh` と `f4_e2e.sh` は main 由来の重複定義 (#1096 `6f979463` の `tools/m11/m11_win.c` と `tools/gui/build/gui_adapt_w32.c`) で build 段が止まった。この時点の S1 と F4 の gate は未測定。`a88aabfa` の測定値は main 取り込み前のものなので、現 head の値としては使わない。**重複は `97db5a58` の weak 化で解消済み。現 head の値は §6h。**

**GetMonitorInfoW 重複の扱い**: 重複の解消 (どちらの定義を正とするか) は build 仕様の判断を要するため、本 run では commit しない。起票先は子 issue **#1559** (`[M11-N102]`)。

**回避版の実測 (参考・commit していない)**: `tools/gui/flengine/build.sh` のリンク行に `-Wl,--allow-multiple-definition` を一時的に足して測定し、測定後に元へ戻した (`git status` は測定後クリーン)。

| 実行 (回避版・foreground・1 回) | rc | 所要 | 結果 |
|---|---|---|---|
| `bash tools/gui/flengine/e2e.sh` (head `bde0c341` + 回避) | **1** | 467 s (load 1.13→1.07) | judge **12/14**。**R2 FAIL** `reached 31 (expected floor 19); missing=['EnumDisplayMonitors', 'GetMonitorInfoW']`。**S1 FAIL** `870/1/47/24/0` (base `872/1/47/22/0`、main と同値)。他 PASS: L1×2・A1 (193/193/173/20)・B1 52・R1・S2・P1 (RegisterClassW=3)・P2〜P5・W1。ネガコン N1〜N9 期待どおり FAIL |
| `bash tools/m11/ldfix/f4_e2e.sh` (head `bde0c341` + 回避) | **0** | 387 s (load 1.06) | 6 gate PASS (F1/F2/D1/D2/P1/A1)。ネガコン 4/4 期待どおり FAIL。`RegisterClassW` pre 2 / noand 2 / post 3。`function_52a7f0` ret pre `0x0` → noand `0x0` → post **`0x110000f`** (本 IR (wndseed 無し) の値)。survey pre/noand/post = `870/1/47/24` |

結論: 回避版では S1 の値は main と同じ (`870/1/47/24/0`)。R2 は重複の片方が消えたことで 2 件欠落する (§6f の回避の副作用と同じ形)。したがって flengine の判定 (12/14) は、重複の解消方法を決めるまで確定しない。S1 の判定式は変えていない。baseline の値は §6h 冒頭の注記のとおり再生成で変わっている (判定式ではない)。

## 6h. weak 化後の現 head の実測 (PM 指示 #577。測定 commit `97db5a58`)

`m11_win.c` の `EnumDisplayMonitors` / `GetMonitorInfoW` に `__attribute__((weak))` を付けた 1 変更 (`97db5a58`、差分 2 関数のみ) の head で、3 本を foreground・各 1 回。素材は `ws-577/work/` (gitignore) に展開。`retdec-decompiler` と `EMSDK_ENV` は `ws-577/work/toolchain/` を指定。

| 実行 | rc | 所要 | load (開始→終了) | 結果 |
|---|---|---|---|---|
| `bash tools/m11/ldfix/f4_e2e.sh` | **0** | 411 s | 0.89 → 1.30 | build 段は通過 (重複定義の解消を確認)。gate F1/F2/D1/D2/P1/A1 全 PASS。ネガコン N1〜N4 期待どおり FAIL。RegisterClassW pre 2 / noand 2 / post 3、ret pre `0x0` → noand `0x0` → post `0x110000f`。survey pre/noand/post = `870/1/47/24` |
| `bash tools/gui/flengine/e2e.sh` | **1** | 460 s | 1.18 → 1.23 | build 段通過。**judge 13/14**。FAIL は **S1 のみ**: `870/1/47/24/0` (base `872/1/47/22/0`)。R1・R2 (floor 19、reached 33)・B1 52・S2・P1〜P5・W1 は PASS。ネガコン N1〜N9 期待どおり FAIL。selftest 506 passed / 0 failed |
| `bash tools/gui/e2e.sh` | **0** | 211 s | 1.58 → 3.37 | **ALL PASS** (simd / 6c/6 fail-fast / text / stress (50000 frames ×2、negctl 2/2 exit 1) / selftest)。`heap-use-after-free` 0 件 |

前提 (回避版との違い): 回避版 (`--allow-multiple-definition`) は `m11_win.c` と GUI 側の両方を連結して片方を捨てる。weak 版は GUI 側の強い定義が勝つ。両者で `EnumDisplayMonitors` / `GetMonitorInfoW` の使われる定義が同じかは、R2 の `missing` の変化で見る。今回の R2 は `missing=[]` で PASS。

S1 の値 `870/1/47/24/0` は §6f の main と同値で、**S1 の判定式は変えていない**。#1442 で扱う。

**baseline の値の変化 (再生成によるもの。判定式は変えていない)**: `results/baseline_survey.json` の現値は `ok 872 / trap 22` (kinds: unreachable 1 / halt0->longjmp 7 / OOB 14)、`results/baseline_boot.json` の `threw` は `unreachable` (`units_run 52` は不変)。旧値は `baseline_survey` が `871 / 23`、`threw` が `memory access out of bounds`。両ファイルは `tools/gui/flengine/e2e.sh` が毎回 m11 baseline を測り直して `results/` にコピーする生成物 (e2e.sh の 36〜41 行・64 行)で、判定基準を手で書き換えた値ではない。main 取り込み後の再生成で値が変わった。
- `baseline_survey.json` の現値は commit `bf9cf547` で初めて現れた (それ以前は `52e6bd57`〜`d96a0fa8` の `871 / 23`)。
- `baseline_boot.json` の `threw` が `unreachable` になったのは `d96a0fa8` から (それ以前は `memory access out of bounds`)。
- 現 `results/` を作った run は**特定できなかった** (run ID は確認していない)。main の値 (871 / 23) に戻すと、現 IR の実測と食い違う古い値を残すことになるため戻していない。

**S2 gate の変更 (`judge.py`、commit `8a6dcf4b`。S1 の判定式とは別)**:
- 旧式: `ffu <= stub_soft and not (kinds.gui_failfast and not ffu)`。ff で fail-fast になった API は、soft で必ず STUB でなければならなかった (`ffu` = ff survey の fail-fast API 集合、`stub_soft` = soft の STUB API 集合)。
- 新式: `sfu <= ffu and ffu <= (stub_soft | sfu)` (`sfu` = soft survey の fail-fast API 集合)。soft が ff に無い fail-fast を増やさないこと、ff の fail-fast API は soft で STUB か fail-fast のままであること、の 2 条件。
- 変えた理由: fail-fast は API 単位ではなく **action 単位** で起きる (例: §5-5 の `SystemParametersInfoW` の未対応 action)。旧式は、同じ API が soft で別の action として fail-fast すると FAIL になり、action の違いを表せなかった。新式は「soft で fail-fast が増えない」を直接検査する。
- 注意: 新式は旧式より**緩い** (ff の fail-fast API が soft で fail-fast のままでも PASS する)。
- 現 head の値で旧式を手計算した (既存の `results/survey_ff.json` と `survey_soft.json` から。再実行はしていない): ff の fail-fast 集合 = `{LoadImageW}`、soft の STUB 集合 = `{LoadImageW}`、soft の fail-fast 集合 = `{}`。**旧式 = PASS、新式 = PASS**。S2 の判定結果は変わらない。

`tools/gui/flengine/results/*.json` と `baseline_boot.json` は本実測で再生成された出力 (`GetMem` 等の probe 値・`gui_shared_ptr` の 1 件・`ir_sha256` が現 head で変わる)。本 commit に含める。

## 6f. origin/main の S1 実測 (PR #577 の PM 指示 1。main commit `b4a8422c`)

PM 指示: 「main でも同じ 870 vs 872 なら既存の欠陥、違えば本 PR が原因」。S1 の判定式は変えていない。

| 項目 | 値 |
|---|---|
| 測定対象 | `origin/main` = `b4a8422c` (Merge #1443)。検証用 worktree (detached・本 PR の branch ではない)。素材 `work-m11` / `work-liftdiff` / `fl-win64` は同じ展開物 |
| 手順 | `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> RETDEC=<[RETDEC] の retdec-decompiler> FL_WIN64_DIR=<[WIN64]> ANALYSIS_DIR=… bash tools/gui/flengine/e2e.sh` (foreground・1 回) |
| rc / 所要 / load | **1** / 445 s / 0.62→1.65 (nproc 4) |
| S1 survey parity (soft) | **FAIL `870/1/47/24/0` (base `872/1/47/22/0`)** |
| 判定 | 12/14 (S1 FAIL、**R2 FAIL**)。他 L1×2・A1・B1・R1・S2・P1〜P5・W1 は PASS |

**main 側の build 段の回避 (本実測だけの前提。main に修正は入れていない)**: main `b4a8422c` は `wasm-ld: duplicate symbol: GetMonitorInfoW / EnumDisplayMonitors` で build 段で止まる (`tools/m11/m11_win.c` (#1096) と `tools/gui/build/gui_adapt_w32.c` (`gen_api.py` 生成) の重複)。scratch の `tools/gui/flengine/build.sh` のリンク行に `-Wl,--allow-multiple-definition` を足して通した (`obj/*.o` を先に並べるので `m11_win.c` 側の定義が使われる)。この変更は commit していない。

**R2 の FAIL は回避の副作用の可能性が高い (未確定)**: 回避後の main では `EnumDisplayMonitors` / `GetMonitorInfoW` が reach に出ず (`missing=['EnumDisplayMonitors', 'GetMonitorInfoW']`、reached 30 ≥ floor 19 だが欠落 2 件で FAIL)。直前の main 測定 (§6e、ソース側で重複を削除した版) では R2 PASS の 13/14 だった。回避方法で R2 が変わるため、本節の R2 は main の欠陥の根拠にしない。S1 の値は両方法で `870/1/47/24/0` と一致する。

**結論**: S1 の `870/1/47/24/0` (base `872/1/47/22/0`) は `origin/main` (`b4a8422c`) でも同一。**PR #577 の変更が原因ではない**。S1 は FAIL のまま (判定を緩和していない)。原因の追跡は子 issue **#1442** (`[GUI-21]`、親 #564)。#1275 (`[M11-N78]`) とは対象 unit が一致するが、同一原因か・同系統かは未確認 (機械語・IR の突合は未実施)。

## 6k. WIN-21 (#3352) の S1 unit 差と現 HEAD の実測

`REPORT_APPENDIX_3352.md` §6k に移動 (測定 commit `c3ee6daa7`)。S1 の差は unit 304・555 の 2 件のみ (base OOB trap・soft ok)。judge は 12/14 (B1 と S1 が FAIL)。判定式は変えていない。
