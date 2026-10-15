# e2e REPORT 付録 (#3496 / WIN-28): GUI-REACH trace の機械検査

本付録は `tools/e2e/REPORT.md` の gui=wasm 節から分割移動した全文。(内容は削除していない。Git 履歴に残す)

## gui=wasm: GUI-REACH trace の機械検査 (WIN-28 #3496)
`gui-guest-boot` のゲストを reach 変種 (`gui_wasm.sh … reach`) で作り、ゲストが初回 WM_PAINT の後に `gui_reach_dump()` を呼ぶ。host の `GuiHost.logs` から `GUI-REACH` / `GUI-MSG` 行を回収し、`CreateWindowExA`・`BeginPaint`・`BitBlt` の件数と、初回の順序 `RegisterClassA < CreateWindowExA < WM_PAINT < BeginPaint < BitBlt` を検査する。生ログは `tools/e2e/work/logs/gui-guest-reach.log`。

- 件数 (HEAD): 到達行 25 (GUI-REACH 23 + GUI-MSG 1 + SUMMARY 1)、`CreateWindowExA`=1・`BeginPaint`=1・`BitBlt`=1・`WM_PAINT`=1。
- 初回の順序 (生ログ): `RegisterClassA`@1 → `CreateWindowExA`@2 → `DispatchMessageA`@9 → `WM_PAINT`@(GUI-MSG 行) → `BeginPaint`@10 → `BitBlt`@20 → `EndPaint`@21。
- 測定 commit: `b3a252976` (`feat(gui): gui=wasm reach trace (GUI-REACH) in product-page e2e`)。
- 実行: `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/e2e/run.sh --targets preview,edge-sim --driver agent-browser` (開始 08:02 UTC、load average 0.21 / 1 分)。wall 13.5 s (vite build・ゲストの emcc build を含む)、rc 0。**SUMMARY: PASS=23 FAIL=0 SKIP=3**。
- `gui-guest-boot`: preview 324 ms・edge-sim 430 ms で PASS (`state==='running'`, `frames=1`, `guest='test'`, lit 38400 px, 色 ≥7)。
- 実行環境: emsdk は素材 `toolchain-emsdk` ([EMSDK])。mingw-w64 は `build_guest.sh` が apt で導入。

- **未実施**: 順序検査のネガコン (WM_PAINT 行を消した変種で FAIL することの確認) は本 PR では未実施。`tools/gui/test/reach_order_check.py` の selftest は既存。`text_wasm_e2e.sh` の回帰は未実施 (FreeType wasm32 ビルドが要る)。
