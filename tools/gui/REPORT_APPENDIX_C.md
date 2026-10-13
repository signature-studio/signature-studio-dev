
`REPORT.md` の 250 行上限 (docs/DOC_MAP.md §1) のため、§13 (GUI-7 #183) の全文を無変更で分割移動した (GUI-13 #615 の §13 と衝突したため §14 として再編)。要約は `REPORT.md` §14。

## 13. GUI-7 (#183): popup/tooltip・非クライアント領域・無効領域複数矩形・DPI (FL 非依存部)
既知類型との関係: lift 欠陥ではなく shim の意味論 (`docs/DEFECTS.md` D1a〜D16 に該当なし)。ただし RetDec lift 済み WndProc の lParam が int32 に切り詰められる既知要件 (§4-6) が新規経路 (`WM_NCCALCSIZE` の `NCCALCSIZE_PARAMS*`) で再発した (下記「発見」)。検証起点: `e822e53` (クリーン tree)。仕様は [PROTOCOL.md §12](PROTOCOL.md)。

### 結論
- **FL 非依存部は実装・検証済み、FL の窓種別に基づく部分は未達 → PR は `Refs #183` (`Closes` なし)**。実装: TOPMOST/NOACTIVATE/`HTTRANSPARENT` を含む popup・tooltip の z 順 (surface 単位)・`WM_NCCALCSIZE`/`WM_NCPAINT`/`WM_NCHITTEST` と `WM_NC*MOUSE*` 配送・`GetWindowDC`/`GetWindowRect`/`AdjustWindowRect[Ex]` の NC 反映・無効領域の複数矩形化 (ウィンドウ/surface dirty とも)・DPI (`SetThreadDpiAwarenessContext` の保持、`GetDpiForWindow`/`GetDpiForSystem`/`IsProcessDPIAware`/`GetDeviceCaps(LOGPIXELS)`/`GetSystemMetrics`/NC 幅の dpr 反映)。
- **golden 画素一致 (差 0)**: `bash tools/gui/test/nc_golden.sh` (`e2e.sh` 1d/6 に組込み)。popup + TOPMOST tooltip + 枠/caption 付きウィンドウ + 無効 2 矩形だけの再描画の 200×140 シーンを独立 Python オラクル `golden/gen_golden_nc.py` (shim と共有するものなし) と比較: **28,000 px 差 0**。同じバイナリが 26 assertion (client/window rect・HT* 判定・`WindowFromPoint` の HTTRANSPARENT 素通し・`WM_NCLBUTTONDOWN(HTCAPTION)` 配送・`GetUpdateRgn` = COMPLEXREGION・DPI 96↔192 の切替と `AdjustWindowRectEx`・z 順 3 本) も実行: **26 passed / 0 failed**。
- **ネガコン (3 本; どれかが通ると exit 1)**: 期待値を 1 画素改変 → 拒否 / `NC_FAULT=1` (tooltip を TOPMOST にしない) → **840 px 不一致で拒否** / `NC_FAULT=2` (2 矩形でなく外接矩形を無効化) → **4,270 px 不一致で拒否**。

### 検証 (現 HEAD `67d5cb7`、この run の実測; 以下の `7105a2d` 以前の行は過去 HEAD の記録)
| 項目 | 結果 |
|---|---|
| `bash tools/gui/e2e.sh` (HEAD `67d5cb7`、origin/main `8d64067` の merge commit、`$RUNNER_TEMP` で実行) | **ALL PASS、rc 0、142 s** (開始 load 0.72 → 終了 load 3.22)。内訳: selftest 428/0・bpp 16,000 px 差 0 (negctl 2/2)・text golden ALL PASS (negctl 4/4)・**nc golden 28,000 px 差 0 (asserts 26/0)**・native lift 0/64,000 px・SIMD 15,679 mismatch 0 (故意欠陥 4 種 FAIL 確認)・Chrome readback / screenshot 0 px (6 / 6b / 6c / 6d PASS)・sigprobe mismatch 0 (negctl 177)・present 7 pass / 0 fail |
| nc golden 単体 (`67d5cb7`) | `bash tools/gui/test/nc_golden.sh`: rc 0、asserts 26/0、28,000 px 差 0。ネガコン 3 本 (1 px 改変 / `NC_FAULT=1` 840 px / `NC_FAULT=2` 4,270 px) すべて拒否 |
| 注記 | レビュー側で出た `node_modules` 不在による tsc (step 5) ENOENT は、`pnpm install --frozen-lockfile` で解消する環境依存でありコード起因ではない。本 run では e2e 開始前 (12:24:25) に `node_modules` が存在していたため、本 run の実測は `pnpm install` 直後の状態に該当する (作成経路は未確認) |
| `bash tools/gui/e2e.sh` (HEAD `7105a2d`) | **ALL PASS、rc 0、110 s** (終了時 load 1.60)。内訳: selftest 426/0・bpp 16,000 px 差 0・text golden ALL PASS・**nc golden 28,000 px 差 0 (asserts 26/0)**・native lift 0/64,000 px・SIMD 15,679 mismatch 0・Chrome readback / screenshot 0 px・sigprobe mismatch 0 (negctl 177)・present ALL PASS |
| nc golden ネガコン (`7105a2d`) | 1 px 改変 → 拒否 / `NC_FAULT=1` → MISMATCH 840 px / `NC_FAULT=2` → MISMATCH 4,270 px。判定は「PPM 出力 + MISMATCH 行」に厳格化 (欠落・クラッシュは不合格) |
| z 順 assert の感度 | 修正前の `gui_core.c` (`51e6170`) に対し新 assert 2 件が FAIL (`non-topmost after TOPMOST stays below it` / `HWND_BOTTOM clears TOPMOST`)、修正後は PASS |
| 試行 | 1 回目は 5/6 で worktree に `node_modules` が無く `tsc` が ENOENT で停止 (コード起因ではない)。`pnpm install --frozen-lockfile` 後の 2 回目で ALL PASS |
| 最終 HEAD `87c20fc` (docs のみ追加) | 試行 1: **rc 1** で 2b/6 `reach_test` の `selftest_wrapped` が停止。同バイナリ 20 回で **16 ok / 4 fail** (4 件とも `gui_headless.c:33 blit_surf` の ASan heap-use-after-free = #489)。試行 2: **ALL PASS、rc 0、101 s** (load 1.98)。全 step PASS の内訳は `7105a2d` と同一 |
| 参考: `51e6170` の e2e | PR コメント記載 (3 試行中 2 回失敗、1/6 と 2b/6 の ASan UAF = #489 系、3 試行目 ALL PASS 97 s)。修正前の HEAD 実測として参照のみ |

### 検証 (`e822e53`、runner 4 CPU、RetDec・emsdk・mingw あり)
| 層 | 結果 |
|---|---|
| `bash tools/gui/e2e.sh` 全体 | **ALL PASS、80.9 s** (1 run; `uptime` load 1.51 → 2.31)。native selftest 406 passed / 0 failed・bpp golden 16,000 px 差 0 (ネガコン 2)・**nc golden 28,000 px 差 0 (ネガコン 3)**・native lift golden 0/64,000 px・Chrome E2E (固定メモリ / ALLOW_MEMORY_GROWTH / reach) の readback・screenshot とも差 0・simd ALL PASS (故意欠陥 4 種を検出)・present e2e 7 pass / 0 fail |
| 変更前 (`021fd75`) の同コマンド | ALL PASS、99.5 s (load 0.62 開始)。同 HEAD での回帰なしの比較用 |
- 途中の `57b46f2` では `e2e.sh` 2/6 (native lift) が ASan SEGV で FAIL (下記「発見」)。`e822e53` で修正して全体 ALL PASS を再確認した。
- 自作ネガコンは nc golden のみ。既存層は従来どおり (`sigprobe` の `unresolved-imports=0` は `wasm-objdump` 不在で空振り; 既知、#180)。

### 発見
- **lift 済み WndProc が `NCCALCSIZE_PARAMS*` を取りこぼす (native で SEGV)**: RetDec の PE lift は `lParam` を int32 へ切り詰める (§4-6)。`gui_app` は `DefWindowProcA(h,m,w,l)` へ転送するので、native (64bit) では切り詰めた上位 32bit 欠落のポインタを `DefWindowProc` が読んで落ちた。修正 = 送信中の params を保持し下位 32bit 一致で復元 (wasm32 は 32bit ポインタなので元から無影響)。**FL 本体 lift で `WM_NCCALCSIZE` を DefWindowProc へ転送する WndProc があれば同型**。`docs/DEFECTS.md` 行案: 症状 = 構造体ポインタ lParam を持つメッセージで native lift だけ SEGV / 根本原因 = lParam の int32 化 / 検出信号 = native_e2e の ASan / 修復 = shim 側で送信中ポインタを保持 (DEFECTS.md の直接編集は PM 判断)。

### 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
| FL が実際に生成する top-level 窓の数/種別 (`CreateWindowExW` の WS_POPUP / WS_EX_*) の確定 | NC 幅の既定値・自前枠/ネイティブ枠の判断・メニュー/ツールチップの要否が FL 実機で未確認 (本 PR の NC 幅は決定的な shim 規約で実 Windows とは一致しない) | #174 (GUI-3) / #564 / #565 後に #183 へ追記 |
| host (ブラウザ) 側の複数矩形 PRESENT は従来実装を流用 (headless host + 既存 present e2e のみ。popup/NC シーンを Chrome 上の lift 済みアプリで走らせていない) | Chrome での NC/popup 描画は未確認 | #183 (NC/popup を含むテスト PE の `gui_app` 追加と Chrome golden) |
| 複数 canvas / DOM 重畳、`SetWindowRgn` 形状クリップ、リサイズ角 HT*、`WM_DPICHANGED`・複数モニタ別 DPI、NC のテーマ描画、メニュー | 完了条件「テスト PE にポップアップ窓 + ツールチップ + 非クライアント描画を追加し `e2e.sh` 組込み」のうち PE (lift) 経由は未達 (shim 直接呼出し golden で代替) | #183 (Refs のまま open) / メニューは #175 |
| 既存の不安定: native selftest の ASan UAF (§12, GUI-12 #489 で修正済み) | `e2e.sh` 1/6 が稀に FAIL | #489 (既存) |
