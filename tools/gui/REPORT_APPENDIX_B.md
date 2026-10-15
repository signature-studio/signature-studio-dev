
`REPORT.md` の 250 行上限 (docs/DOC_MAP.md §1) のため、§11 の全文を無変更で分割移動した (GUI-13 #615 で §13 を追加した際)。要約は `REPORT.md` §11。

## 11. GUI-9 (#186): GDI テキストの FreeType 描画 (内蔵 8×8 → FreeType 2.7)
- **実装**: `src/gui_ft.c` (`GuiTextEngine` = FreeType 2.7、hinting は FT 既定) を `gui_set_text_engine(gui_ft_engine())` で有効化。未登録/face 解決不能/stock フォントは従来の 8×8 (既存 golden 維持)。`CreateFont{A,W}`/`CreateFontIndirect{A,W}` は face・height・weight・italic を保持 (`GetObject` の lfHeight は従来通り)、`GetTextMetrics`/`GetTextExtentPoint*`/`TextOut`/`ExtTextOut`/`DrawText` を engine 経由に、`EnumFontFamiliesExW` を STUB→IMPL (登録 face を列挙、`gui_call4` で cb 呼出、fontType=TRUETYPE)。
- **方針 (#186 PM 判断)**: Windows 標準フォントは同梱しない。`gui_ft_alias("Segoe UI", "Open Sans")` 型の face→OSS フォント代替表、未解決名は最初に登録した face。`gui_ft_register_lazy` で最初の `open` 時に load (VFS #22 取得口; 実 VFS 結線は未)。テスト用フォントは Open Sans (`googlefonts/opensans`) と Barlow (`google/fonts` ofl/barlow) を `test/fetch_fonts.sh` が `work/` (gitignore) へ sha256 検証付きで取得し、リポジトリには入れない。
- **独立オラクル**: `golden/ft_oracle.c` は shim のコードを一切使わず native FreeType 2.7 (`tools/shared/oss/freetype/build.sh` 産 `libfreetype.a`) を直接叩いて同一シーンの PPM と metrics 表を作る。共有するのは仕様 (ppem 規約・advance=四捨五入した hinted advance・合成式 `(fg*cov+dst*(255-cov)+127)/255`・TA_*/DT_* 配置) のみ。`golden/cmp_text.py` が画素と metrics 表 (2 face × 15 高さ = 30 行 × 9 列) を全一致判定。**実 Windows フォントとの一致は主張しない**。
- **実測 (HEAD 再現前の作業ツリー; 4 vCPU, gcc ASan/UBSan, emcc 6.0.12, node 24)**:
  - `bash tools/gui/test/text_golden.sh`: 前景 3826 画素・差 **0**、metrics 30 行・差 **0**、`EnumFontFamiliesExW` (全 2 face / 名指定 1 件=Barlow) OK、ネガコン 4/4 検出 (期待 1 画素+metrics 1 セル破壊 / フォント高さ +1 欠陥 = 1063 画素差 / engine 未登録 (8×8) / オラクルのフォントファイル差替え)。実時間 6.4 s。
  - `bash tools/gui/test/ft_wasm.sh`: engine (gui_ft.c) の metrics/advance/glyph coverage ダンプ 11 行が native と wasm32 (`-pthread` で再ビルドした FreeType 2.7, FORCE_INT64+patch) で一致 (TOTAL edd537e3b390f846)、ダンプ破壊のネガコン検出。実時間 6.7 s。
  - 回帰 (変更後): `selftest.sh` 406 passed/0 failed、`bpp_golden.sh` ALL PASS (ネガコン込み)、`simd_e2e.sh` ALL PASS、`reach_test.sh` 11+28 passed。
- **レビュー対応の再現 (コミット済み HEAD 5813bea; work/・build/・libfreetype 無しのクリーン状態, 4 vCPU)**: `e2e.sh` 1c0 ブロックを原文のまま抽出して実行 (前段に `gen_api.py`; `fetch_fonts.sh` → `FONT=work/OpenSans-Regular.ttf build.sh` → `text_golden.sh` → `ft_wasm.sh`)。rc=0、実時間 1m34.678s (n=1、終了時 load average 2.29)。`build.sh` 自己テスト PASS wasm32/wasm64 (40 行, TOTAL a4eff06d516ef88f)、`text_golden.sh` ALL PASS (前景 3826 画素・差 0 / metrics 30 行・差 0)、`ft_wasm.sh` PASS (11 行, TOTAL edd537e3b390f846)。修正前は `FONT` 既定値 (FL mac 展開物) が無く `build.sh` が exit 1 → `e2e.sh` が 1c0 で abort していた。
- **ネガコンの厳格化**: `text_golden.sh` は `cmp_text.py` が exit 1 (不一致) で拒否した場合だけ検出扱い (exit 0 受理・exit 2 入力不正はともに FAIL)。オラクル側 PPM を不正入力 (exit 2) にした変異版で `NEGCTL FAIL (rc=2)` と script exit 1 を確認 (従来の「非 0 なら検出」では通っていた)。
- **8×8 経路の `DrawText` 挙動差 (実測; 旧 = main 59c1169、新 = HEAD 5813bea の engine 未登録、100×40・stock フォント・FNV 画素ハッシュ)**: DT_LEFT 複数行・CRLF DT_LEFT・単一行 DT_CENTER の画素と戻り値は 3 件とも一致。複数行 `ab\ncdef` の DT_CENTER は 1 行目の最小 x が 34→42、DT_RIGHT は 68→84 (旧は全行がブロック幅基準の同一 x0、新は行ごとに配置 = Windows の挙動)。`tools/gui` の既存 golden/selftest/gui_app に `DrawText` 呼出は無い (grep)。`e2e.sh` 全体での確認は未 (下記未解決 (1))。
- **既知の限界**: カーニング・ClearType・合成 bold/italic・lpDx・DT_WORDBREAK/DT_END_ELLIPSIS/`&` プレフィックス・GetTextExtentExPoint/GetTextFace は未実装 (8×8 時代から DT 簡略のまま)。advance は整数 px (サブピクセル位置決めなし)。`GetTextMetrics` の `tmAveCharWidth` は OS/2 `xAvgCharWidth` (Windows の算出と異なりうる)。
- **未解決** (本 PR は `Refs #186`): (1) `bash tools/gui/e2e.sh` 全体 ALL PASS は af8ba9cc / 0cbc5651 で各 1 回確認。安定性 (flake) は未確認 (付録 §11 追補・§13 (2))。(2) 実 FL が要求する face/サイズの確定 (blockedBy GUI-3 #174) と alias 表の実値。(3) VFS (#22) からの実フォント遅延取得の結線 (口 `gui_ft_register_lazy` のみ)・ブラウザ (wasm 全体) 上のテキスト描画 e2e。(THIRD_PARTY_NOTICES (#86) への Open Sans/Barlow の license 登録は #616 で対応: `tools/legal/notices/REPORT.md`。)(4) `wasm32` の `gui_wasm.sh` ビルドへ `gui_ft.c` + libfreetype の組込み (本 PR は既定 e2e のビルドへ未リンク = 既存 wasm 経路は 8×8 のまま)。

## 11 追補. e2e.sh ALL PASS の実測 (#186 再実行 run; REPORT §11 から分割移動)

- **af8ba9cc (検証起点 = origin/main, docs 追記前)**: 素材 `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` 展開済み。runner に `x86_64-w64-mingw32-gcc` が無く `gen_api.py` が 0/6 で落ちたため `apt-get install gcc-mingw-w64-x86-64` (GCC 13) を導入して再実行。結果: **EXIT=0・`[gui-e2e] ALL PASS`**、real 5m02s、開始 load 0.54。native_run EXACT MATCH (0 px)、selftest 433 passed, 0 failed、Chrome E2E EXACT MATCH (読み戻し・スクリーンショットとも 0 px)、negctl (6a) rejected、fail-fast PASS、reach 36 APIs (impl 36 / stub 0)、stress 50,000 frames drop 0 (negctl burst / leak も exit 1 で検出)。ログ全文は run の一時ファイル (非コミット)。
- **0cbc5651 (PR HEAD, docs のみ追記; コード差分なし)**: **EXIT=0・ALL PASS**、real 3m03s、終了 load 1.93 (開始 load は未記録)。PR 作成時の run の記録で、後続の再現 run は未実施。native_run EXACT MATCH (0 px)、selftest 433 passed 0 failed、reach 11 + adapt 28 passed、text_golden ALL PASS (ネガコン 4/4)、ft_wasm PASS、bpp_golden・nc_golden・simd_e2e ALL PASS、Chrome E2E 読み戻し・スクリーンショット EXACT MATCH (0 px)、negctl rejected、fail-fast PASS、reach 36 APIs (impl 36, stub 0)、stress 50,000 frames drop 0・memory 有界。grep で出る "fail" 行はすべて "0 failed" か期待どおりの失敗 (ネガコン・fail-fast)。
- 前提: 0cbc5651 の run でも `x86_64-w64-mingw32-gcc` を `apt-get install gcc-mingw-w64-x86-64` で導入。
- 1 回 PASS のみで、flake の解消は主張しない (§13 (2) 参照)。
- **§11 追補 (2026-10-13, run 186-e2e-verify): origin/main `84e43186` の通常経路 `bash tools/gui/e2e.sh`**: **rc=0 ALL PASS**、実時間 3 m 31 s、開始時 load 1.11 (1 分値)。素材 fl-win64 / toolchain-retdec / toolchain-emsdk 展開済み。runner に `x86_64-w64-mingw32-gcc` が無く初回は `gen_api.py` で停止 → `apt-get install gcc-mingw-w64-x86-64` (GCC 13) で解消、`pnpm install --frozen-lockfile` を併せて実施。ネガコンの内訳: 6a は golden 1 画素改竄で拒否 (exit 1)、6h の burst / leak ネガコンも検出を確認、6e (sigprobe) は内部に陰性対照を持つ。6b・6c・6d・6f・6g は正の E2E として PASS (6c は fail-fast の期待失敗を grep で確認)。
  - 1 回 PASS のみで、flake の解消は主張しない。`selftest_wrapped` の既知 flake (§13 の 9/30 失敗) は未解決で、既存の #740 (GUI-15) で追跡する。

## 13 追補. c4b293d 再確認 (PR #661 レビュー対応: e2e.sh の FT ビルド保証を step 4 の前へ移動した後)

環境: 4 vCPU・RAM 15 GiB、RetDec v5.0 ([RETDEC])、emcc 6.0.12、Chrome headless、clean worktree。以下の数値は PR #661 レビュー (oc-reviewer, HEAD `7ead604`) の実測で、rc・所要・開始時 load (1 分値)・回数を記す。

- **負の対照 (旧順序の再現)**: libfreetype wasm32 が無い状態で `lift/gui_wasm.sh` を呼ぶと `run tools/shared/oss/freetype/build.sh first` で **rc=2** (1.1 s)。旧順序の e2e.sh step 4 は同じ経路で落ちる。
- **新順序の FT ガード** (`test/fetch_fonts.sh` → `FONT=… shared/oss/freetype/build.sh`): **rc=0**、実時間 1 m 31 s。native / wasm32 / wasm64 の自己テストは PASS (TOTAL a4eff06d516ef88f)、フォント 2 本取得・sha256 OK。続けて `lift/ft_wasm_lib.sh` **rc=0** (5.9 s、`build/ft_mt` へ -pthread 再ビルド)。`gui_wasm.sh` は FT 段を通過し、`/nonexistent/lifted.c` の emcc 入力エラー (rc=1) で止まる。失敗位置が FT 検査から lifted.c 入力へ移ったことを確認 (lifted.c の生成は RetDec が必要で本 run では未実施)。
- **`text_wasm_e2e.sh` (RetDec 不要)**: **3/3 rc=0 PASS**。実時間 18.27 s (初回) / 8.59 s / 8.63 s (FT ビルド 1 m 31 s は含まない)、開始時 load 1.84 / 1.76 / 3.01。読み戻し 0 px・スクリーンショット 0 px (38400 px 中、前景 3826 px)、metrics 30 行差 0、8×8 回帰 0 px (前景 2179 px)、ネガコン N1〜N5 全て拒否。
- **旧 `e2e.sh` (f3ba8e1) の `SKIP_NATIVE=1`・libfreetype 未ビルド (ネガコン)**: **rc=2 で step 4** (`run tools/shared/oss/freetype/build.sh first`)、11.2 s。
- **現 HEAD `SKIP_NATIVE=1 bash tools/gui/e2e.sh`・libfreetype 未ビルド**: **rc=0 ALL PASS**、2 m 24 s、開始時 load 1.28。step 33 のガードで FT native/wasm32/wasm64 を構築し、wasm32・wasm64 とも `[ft] PASS`。
- **現 HEAD `bash tools/gui/e2e.sh` (通常経路) 2 回**: 1 回目 **rc=0 ALL PASS**、3 m 21 s、開始時 load 0.60。2 回目 **rc=1、step 2b の末尾で停止**、2 m 15 s、開始時 load 0.59。2 回目の出力は grep で除外され、原因行は未取得。受入条件 1 は 2 回中 1 回 ALL PASS。
- **既知 flake (本 PR の変更とは独立)**: `tools/gui/test/reach_test.sh` 末尾の `selftest_wrapped` (ASan) が約 30% の確率で `gui_headless.c:33 blit_surf` の heap-use-after-free (`recompose_all` ← `on_cmd`、thread T1) で落ちる。同バイナリを単独 30 回回した結果は PR HEAD `7ead604` が **9/30 失敗**、origin/main `0fa8283` が **8/30 失敗** (同じ ASan エラー)。PR は `gui_headless.c`・`selftest.c`・`reach_test.sh` に触れていない。
- **未解決 (起票依頼)**: `gui_headless.c` の blit_surf race の issue 起票 (PM 依頼・未起票)。`toolchain-retdec` を含む素材での通常経路 ALL PASS の追加確認の要否は PM 判断。


## 11 追補 2. e2e.sh ALL PASS の再実測 (#186 再々実行 run)

検証起点 HEAD `9d1c632f` (origin/main、クリーン worktree `186-e2e-recheck`、`build/` 無し)。`TMPDIR=$RUNNER_TEMP`、`bash tools/gui/e2e.sh` 1 回、foreground。素材: fl-win64・toolchain-retdec・toolchain-emsdk 実在確認。前提: `apt-get install gcc-mingw-w64-x86-64` (GCC 13)、`pnpm install --frozen-lockfile`。

- **結果**: rc=0 / `[gui-e2e] ALL PASS` / 実時間 211 s / 開始時 load 0.37 (1 分値)。stress の negctl 4 本は FAIL を検出して拒否 (stress 本体は ALL PASS)。
- **安定性**: 本 run は 1 回のみ。受入条件「維持」の判定 (n 連続) は #1217 で扱う。flake (`blit_surf` の heap-use-after-free) の追跡は #740 (GUI-15)。

## GUI-20 (#1217): e2e.sh 連続実行と 6h CDP タイムアウトの再現確認

測定 commit `f2370c95` (= 本 run の PR head。コード部分は `0e9fcaae` と同一で、`git diff 0e9fcaae f2370c95 -- tools/gui` の差分は本節の REPORT_APPENDIX_B.md のみ)。`git diff f7bebc7b f2370c95 -- tools/gui` = 6 files / +190 −4 (main 取り込み由来。e2e 経路に `gui_core_ext.inc` +2 行を含む) のため、本節の数値は `f2370c95` の tree の実測として扱う (`docs/WORKFLOW.md` §6)。`TMPDIR=$RUNNER_TEMP`、`bash tools/gui/e2e.sh` を foreground で実行。素材: fl-win64 / toolchain-emsdk / toolchain-retdec を `$ARTIFACTS_DIR` で実在確認し、[EMSDK]・[RETDEC] に展開済み。

- **前処理 (記録のみ・判定外)**: 本 run の worktree は `pnpm install --frozen-lockfile` と `tools/e2e` の `npm ci --ignore-scripts` を実施し、`gcc-mingw-w64-x86-64` を apt で導入してから測定。前回 run までの前処理欠落 (mingw 不在・node_modules 無し) は解消済みの前提で、以下 7 run は同一環境で連続実行。
- **連続実行 (head `f2370c95`、foreground、7 回)**:

| run | rc | 実時間 | 開始時 load (1 分値) | 結果 | step 6h CDP timeout |
|---|---|---|---|---|---|
| 1 | 0 | 308 s | 0.61 | ALL PASS | 0 |
| 2 | 0 | 212 s | 2.90 | ALL PASS | 0 |
| 3 | 0 | 212 s | 2.54 | ALL PASS | 0 |
| 4 | **1** | 204 s | 3.12 | FAIL (step 6h `stress.sh` で `agent-browser eval: CDP command timed out: Runtime.evaluate`) | **1** |
| 5 | 0 | 212 s | 1.79 | ALL PASS | 0 |
| 6 | 0 | 210 s | 2.01 | ALL PASS | 0 |
| 7 | 0 | 210 s | 2.35 | ALL PASS | 0 |

- **run4 の失敗**: step 6h (GUI-8 長時間ストレス) で CDP 呼び出しがタイムアウトし、`stress.sh` が非 0 で終了して e2e が rc 1。step 1〜6g は run4 でも PASS。他 6 run の 6h は PASS。前回 run の失敗 (`0e9fcaae` 測定 run5) と同一の症状で、2 回の再現を確認。失敗の再現条件 (負荷・eval 待ち時間) は未特定。
- **前回 (`0e9fcaae`、6 回) との比較**: rc 0 は 5/6 (CDP timeout 1 件)。今回は rc 0 が 6/7 (CDP timeout 1 件)。通算 13 回中 rc 0 は 11 回、CDP timeout は 2 回。
- **判定**: 受入条件 2 (n≥10 連続 rc 0) は **未達** (同一 head の連続実行は 7 回。run4 で中断ではなく rc 1 として記録)。10 連続の取得は fix モードの時間上限 (40 分) を超えるため、本 run では 7 回で打ち切った。受入条件 1 (6h の CDP タイムアウト原因の特定) は **未達**。受入条件 3 (#740 の修正前 ASan 再現ログ) は **未達** (未取得)。
- 未解決の起票先: #1217 (本 issue を open のまま残す)。

## 11 追補 3. e2e.sh ALL PASS の連続実測 (#186 受入条件 3 点目、run 186-e2e-stability)

測定 commit: origin/main `80c32a06` (コード HEAD。以後コード差分 0)。クリーン worktree `186-e2e-stability`、`build/` 無し。`TMPDIR=$RUNNER_TEMP`、`bash tools/gui/e2e.sh` を foreground で同一 HEAD に 10 回連続実行。素材: fl-win64・toolchain-retdec・toolchain-emsdk を `ls` で実在確認、`/opt/retdec`・`/opt/emsdk` 展開済み。前提: `gcc-mingw-w64-x86-64` 導入済み、`pnpm install --frozen-lockfile` 済み。

| run | rc | 実時間 | 開始時 load (1 分値) | 結果 |
|---|---|---|---|---|
| 1 | 0 | 4 m 16 s | 0.89 | ALL PASS |
| 2 | 0 | 166 s | 2.18 | ALL PASS |
| 3 | 0 | 165 s | 2.17 | ALL PASS |
| 4 | 0 | 164 s | 3.07 | ALL PASS |
| 5 | 0 | 165 s | 1.91 | ALL PASS |
| 6 | 0 | 165 s | 1.86 | ALL PASS |
| 7 | 0 | 165 s | 1.96 | ALL PASS |
| 8 | 0 | 165 s | 2.27 | ALL PASS |
| 9 | 0 | 165 s | 2.43 | ALL PASS |
| 10 | 0 | 165 s | 2.02 | ALL PASS |

- **結果**: 10/10 rc=0 / `[gui-e2e] ALL PASS`。各ログに `heap-use-after-free` / UAF の出現 0 件。stress 本体は ALL PASS (drop 0)。ネガコンの `FAIL` 行は期待された拒否 (exit 1 を検出) で、rc には影響しない。
- **受入条件 3 点目 (`e2e.sh` ALL PASS 維持)**: 本 run で連続 10 回の rc=0 を確認 (#1217 の n≥10 基準を満たす)。
- **未解決 (移管先は変更なし)**: 修正前 ASan ログの再取得と flake の Closes 判定は #740 / #1217 (GUI-20) で扱う。#186 の判定には含めない。

## GUI-20 追補 (#1217 run: origin/main 連続 10 回 rc 0)

測定 commit `61ce9782` (origin/main、コード変更なし)。`git diff f2370c95 61ce9782 -- tools/gui ':!*.md'` と `tools/e2e` の差分は 0 行 (前回 head との差は REPORT のみ)。`TMPDIR=$RUNNER_TEMP`、`bash tools/gui/e2e.sh` を foreground で同一 worktree (`ws-1217`) に連続 10 回実行。素材: fl-win64 / toolchain-emsdk / toolchain-retdec を `$ARTIFACTS_DIR` で実在確認、`[EMSDK]`・`[RETDEC]` を利用、C コンパイラは MinGW-w64 gcc (PATH 上)。前処理: `pnpm install --frozen-lockfile`、`tools/e2e` の `npm ci` (e2e.sh の自動導入)。

| run | rc | 実時間 | 開始時 load (1 分値) | 結果 | step 6h CDP timeout |
|---|---|---|---|---|---|
| 1 | 0 | 319 s (初回 setup 込み) | 0.04 | ALL PASS | 0 |
| 2 | 0 | 207 s | 2.56 | ALL PASS | 0 |
| 3 | 0 | 206 s | 2.12 | ALL PASS | 0 |
| 4 | 0 | 209 s | 3.41 | ALL PASS | 0 |
| 5 | 0 | 209 s | 1.64 | ALL PASS | 0 |
| 6 | 0 | 209 s | 1.77 | ALL PASS | 0 |
| 7 | 0 | 211 s | 2.28 | ALL PASS | 0 |
| 8 | 0 | 208 s | 1.81 | ALL PASS | 0 |
| 9 | 0 | 207 s | 2.36 | ALL PASS | 0 |
| 10 | 0 | 208 s | 3.01 | ALL PASS | 0 |

- 判定: 受入条件 2 (n≥10 連続 rc 0) は **達成** (10/10)。ただし前回 head `f2370c95` の run4 (rc 1, CDP timeout) は今回 0/10 で再現せず。
- 受入条件 1 (CDP timeout 原因の特定) は **未達**。今回の 10 run では再現しなかったため原因は未切り分け。CLI (agent-browser linux-x64) の既定 action timeout は `AGENT_BROWSER_DEFAULT_TIMEOUT` = 25000 ms。stress.mjs の watchdog は 20 分で、失敗メッセージ (`CDP command timed out: Runtime.evaluate`) が CLI の既定値由来かは未検証 (推定)。
- 受入条件 3 (#740 の修正前 ASan 再現ログ) は **未達** (未取得)。
- 未解決の起票先: AC1 (CDP timeout 原因の特定) は #1665 (GUI-23)、AC3 (#740 の ASan 修正前ログ) は #1666 (GUI-24)。

## GUI-24 追補 (#740 残件: 修正前コードの ASan 再現ログ)

- 修正前の親 commit `e64ef6f0` (= `6e6c9b74^`、`surf_free` が即時 free のまま) を detached worktree で用意し、`bash tools/gui/test/selftest.sh` (ASan) を直列に回した。
- 結果: 1〜3 回目 rc 0、**4 回目で rc 1: heap-use-after-free** (`READ of size 4 at ... thread T1`, `blit_surf` `gui_headless.c:33` ← `recompose_all` `:45` ← `on_cmd` `:63` ← `gui_hl_drain` `:84` ← `render_thread` `:92`)。解放は `surf_free` `gui_core.c:177` (thread T0)、確保は `surf_alloc` `gui_core.c:156` ← `create_window_impl` `:454`。#489 の既知スタックと一致。
- 同じ手順の別試行 (先の試行) では 6 回目で同一の UAF。計 2 回の再現 (2 試行合計 10 回の selftest 中)。
- 再現時の所要: 4 回で 27 s、開始時 load 0.72 (1 分値)。
- ログ: `$RUNNER_TEMP/gui740/pre_uaf.log` (Git 管理外。run 終了で消える)。
- 判断: 受入条件 3 点目 (修正前 ASan 再現ログ) は **達成**。修正後は 94 回 (§18 の 30+64) で発火せず、修正前は 2/2 試行で発火しており、修正の有効性を示す対照として #740 の残件を閉じる根拠になる。#1666 (GUI-24) は本追補で完了扱い。

## GUI-23 (#1665): 6h CDP タイムアウトの切り分け (原因未特定)

測定 commit `f0cb6407d` (コード変更の最後の commit。診断として `stress.mjs` に eval 所要時間の採取と `[slow-eval]` 出力、`stress.sh` の grep に eval 行を追加)。`git diff f0cb6407d HEAD -- tools/gui` は本節 (REPORT) のみの差分。`TMPDIR=$RUNNER_TEMP`、worktree `ws-1665`、`pnpm install --frozen-lockfile`、`tools/e2e` の `npm ci --ignore-scripts`、`gcc-mingw-w64-x86-64` 導入済み。素材 fl-win64 / toolchain-emsdk / toolchain-retdec は `$ARTIFACTS_DIR` に実在を確認。

- **e2e 全体 (コミット済み HEAD で foreground、3 回)**: `76e7e74eb` 1 回目 rc=0 ALL PASS (2 m 41 s)、`76e7e74eb` 2 回目 rc=0 ALL PASS (2 m 28 s)、`f0cb6407d` rc=0 ALL PASS (2 m 26 s)。いずれも 6h の CDP timeout は 0。
- **6h の eval 所要 (`f0cb6407d` の診断ログ、負荷なし)**: stress.mjs 1 プロセスあたり max 613 ms / 595 ms、3 s 超 0 件。
- **負荷別の追加測定 (作業用の計測コピー、コミットなし。50000 frames、SAMPLE 2500、全て PASS)**:

  | 負荷 (busy loop) | eval 最大 | 3 s 超の件数 | 終了時 load (1 分値) |
  |---|---|---|---|
  | なし | 652 ms | 0 | 未記録 (計測時の load 1 分値は取らず) |
  | 4 本 | 1934 ms | 0 | 3.91 |
  | 8 本 | 3814 ms | 6 | 7.78 |
  | 16 本 | 5441 ms | 19 | 16.86 |

- **CLI の既定 action timeout の陽性対照**: `about:blank` で `new Promise(r => setTimeout(r, 30000))` を eval すると **`CDP command timed out: Runtime.evaluate`** で失敗 (実時間 30 s)。CLI の既定値 (25 000 ms) 由来のメッセージであることは確認できた。境界の厳密な秒数は未測定 (25 s 付近での挙動は未確認)。
- **`AGENT_BROWSER_DEFAULT_TIMEOUT=1` の対照 (負の結果)**: 600 ms 程度の `window.__s.single` を含む stress は eval の失敗なし (eval 最大 604 ms)。この環境変数だけでは `Runtime.evaluate` の上限が変わらない可能性がある。`AGENT_BROWSER_DEFAULT_TIMEOUT=300` でも 627 ms の eval が通った。**この切り分けは未確定** (env の適用範囲は未確認)。
- **判定**: 失敗の再現条件 (負荷・eval 長) は**未特定**。上の測定では eval は 25 s 近くまで伸びず、GUI-20 の失敗 (run4 / 0e9fcaae run5) の状態 (負荷・時刻) は再現できなかった。第一仮説 (eval が既定 timeout を超える) は、負荷 16 本でも eval が 5.4 s までしか伸びないため、この環境では説明できていない。
- **未切り分けの要素**: (1) 失敗時の load と eval 所要 (旧ログには無い。`f0cb6407d` の診断で次回以降採取される)。(2) `AGENT_BROWSER_DEFAULT_TIMEOUT` が `eval` の `Runtime.evaluate` に効くか。(3) GitHub Actions runner 固有のディスク・CPU の競合 (本 run は同一 runner 上で未再現)。(4) `stress.sh` 前段の `wasm_grow` / sync push 量 (burst) との組み合わせ。
- **次の確認**: 10 連続 rc 0 の再取得 (`f0cb6407d` で) と、失敗時に出る `[slow-eval]` / `eval failed after` 行の採取。
