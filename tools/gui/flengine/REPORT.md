# REPORT — GUI-3 (#174): 実 FLEngine の lift に GUI shim を結合する

**判定: 部分達成 (受入条件 1 は未達。過去の `c4e3c064` の 14/14 PASS (§6c-4) は当時の値。HEAD `bf9cf547` の flengine e2e は judge 13/14 (S1 FAIL。§6d を正とする)。PR は `Refs #174`)**。§1〜§5 の数値・記述は旧 HEAD `52e6bd57` 時点のもの (参考)。現 HEAD の実測は §6 を正とする。実 FLEngine (m11 closure, `FLEngine_x64.dll` の 7,421 関数 lift) に `tools/gui` shim を全 TU `-pthread` でリンクし、
**自然起動 (DllMain attach) で最初の GUI API (`LoadStringW`) が shim に到達**した。942 unit の隔離 survey では GUI API **32 種**が shim に到達 (実装済み 31 / fail-fast stub 1 = `LoadImageW`)。
`CreateWindowExW` は survey で **1 回だけ自然到達**したが、直前の `RegisterClassW` は呼ばれず (`GetClassInfoW` の後に直行)、窓は生成されない (§5-2 の lift 欠陥)。受入条件 1 の意図する「実登録を経た窓生成の自然到達」は未達。
実 WNDCLASS を JS から指向呼出した場合は `RegisterClassW` ×2 が shim に届き、`TApplication` の窓 (hwnd 31bit) が生成できる。
**#4447 (LD-219)**: 起動の dispatch 数 (`units_dispatched` = 109) を e2e JSON に出すようにした。`a4a620a9^` / `a4a620a9` の前後比較は基準環境 (`fl-win64` の PE あり・IR 再生成) で両側 dispatch 109 = 109 (差 0・基準 109 を再現)。詳細は `REPORT_APPENDIX_4447.md`。
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

### 旧 HEAD の実測 (参考)

旧 HEAD `a927ac87`・`de8d603e` 時点の e2e 実測 (ネガコン表・IR 指紋を含む) は [REPORT_APPENDIX_HISTORY_4645.md](REPORT_APPENDIX_HISTORY_4645.md) に移した (250 行上限。現 HEAD の実測は上の表を正とする)。

## 6b〜6d・6i (付録へ分割移動)

§6b (#565)・§6c・§6d・§6i (#1442 / GUI-21) の全文は [REPORT_APPENDIX_HISTORY_3832_A.md](REPORT_APPENDIX_HISTORY_3832_A.md) に移した (250 行上限)。

### 6j. issue #4645: EnumDisplayMonitors callback `0x85df70` の icall miss

- 原因と対応: `e2e.sh` が boot5 (`m11_extra_ranges5.txt`) を複製側で lift していなかったため callback が IR に無かった。`e2e.sh` で lift を追加 (元の `tools/m11` は読取のみ)。`judge.py` は無変更。
- 実測 (boot, 測定 commit `f0235912`): `units_run 110` (旧 109)、`icall_miss 4` (旧 7)、miss 先は `0xfa9390` のみ。B1 PASS。
- survey は本変更で動いていない: `results/survey_soft.json` (隔離版) は `764/1/46/131` で、`f0235912`〜HEAD 不変。`survey_soft_chain.json` は `875/1/46/20` で、`f0235912`〜HEAD 不変。main 側の値 (`872/1/47/22`) との差は main の測定由来。詳細と測定鮮度は [REPORT_APPENDIX_4645.md](REPORT_APPENDIX_4645.md) §3・§4。

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
| `0xfa9390` の icall miss (boot の残 1 件。#4645 で `0x85df70` は解消) | 影響は未確認 | #4730 (GUI-27、親 #4645) |
| survey_soft_chain の旧 REPORT 値 (871) と現 JSON 値 (`ok` 875・`trap` 20・`miss` 46・`icall_miss` 46) の不一致 | 既存の不整合。原因は未確認 | #4731 (GUI-28、親 #4645) |
| 前回 run で観測した selftest (ASAN) の `heap-use-after-free` (`gui_headless` の描画スレッドと `surf_free`。前 run で約 2/8 で再現) | 本 HEAD の 3 回では再現せず (433/0 ×3)。HEAD 7d44c033 の 1 回 (500/0) でも再現せず。main 側の #489 系 (headless surface UAF) の merge を含む HEAD での結果。再現率の定量確認は未実施 | PM 起票依頼 (gui_headless の描画と surf_free の排他) |

### GUI-25 (#4420): B1 の GetMem 不一致の切り分け

- 切り分け: GetMem の 761 対 760 は shim ではなくビルド条件。比較元 `m11_run.mjs` は非 pthread の wasm、GUI 結合は `-pthread`。同じ `-pthread` の shim 無し base (`run.mjs --wasm m11_base.cjs`) は GetMem 760 (2 回再現)、非 pthread は 761 (2 回再現)。
- 修正: boot の比較元を `-pthread` の base に揃えた (`e2e.sh` / `judge.py` の `threw` キー名も `boot_threw` に揃えた。判定条件は緩めていない)。
- 記録値の変化: main の `results/boot.json` は GetMem 761 (FastMM_GetMem 782)。`696d3f18b` の記録も 761。`309a38d0e` (results のみの記録 commit) で GetMem 760 (FastMM_GetMem 781) に変わった。変わった原因は未確認 (再測定は未実施。本 PR の commit で GUI ビルド入力は変わっていない)。よって「GetMem 760 は変更前後で同じ」とは言えない。
- 残件: `icall_miss` GUI 7 対 base 6。差分の宛先は `0x85df70` 1 件。これは `EnumDisplayMonitors` の callback (#1096 / #1331 / #1507 / #881 で確定済み)。GUI では `EnumDisplayMonitors` が IMPL のため callback が呼ばれる。子 #4645 で解消する。
- 測定 (HEAD `696d3f18b`・foreground 1 回): e2e rc 1 / 432 s / judge 14/15 (FAIL は B1 のみ: `icall_miss` 7 対 6)。ネガコン N1〜N10 は期待どおり FAIL。

## 6e〜6h・6f (付録へ分割移動)

§6e・§6f・§6g・§6h の全文は [REPORT_APPENDIX_HISTORY_3832_B.md](REPORT_APPENDIX_HISTORY_3832_B.md) に移した (250 行上限)。
