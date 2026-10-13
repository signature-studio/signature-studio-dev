# tools/gui REPORT 付録 (本体 REPORT.md は 250 行上限のため §12 を分割)

## 12. GUI-5 (#181) 続き: e2e.sh 全体と wasm shim 全体の SIMD/scalar 比較

既知類型との関係: lift 欠陥ではなく shim の意味論 (§10 の同一サーフェス複数クリップ欠陥は `docs/DEFECTS.md` D18 に登録)。
検証起点: 最終 HEAD `1f20ec7`。`tools/gui/src`・`include` は `1457db3` (main `8d883c3` 取り込み後) から無変更 (`git diff 1457db3 1f20ec7 -- tools/gui/src tools/gui/include` が空)。差分は `test/wbench.sh` の前提チェックと説明文、`REPORT.md` §10 の 1 行のみ。runner 4 CPU、`/opt/emsdk`・`/opt/retdec`、mingw-w64 GCC 13 (apt `gcc-mingw-w64-x86-64`)。

### 1. `bash tools/gui/e2e.sh` (RetDec 付き・全層)

試行の一覧 (同 src 群。1/6 の ASan UAF を含め、全試行を記録):

| HEAD | 試行 | 実行者 | rc | 所要 | load (開始→終了) | 1/6 selftest |
|---|---|---|---|---|---|---|
| `1457db3` | T1 | bot (PR コメント) | 1 | 15 s | — | ASan heap-use-after-free で停止 |
| `1457db3` | T2 | bot (PR コメント) | 0 | 189 s | — → 2.13 | 426 passed |
| `1457db3` | R1 | レビュワー独立 | — | — | — | 426 passed (5/6 は検証用 worktree の `node_modules` 不在で停止。不計上) |
| `1457db3` | R2 | レビュワー独立 | 1 | — | — | ASan heap-use-after-free (`gui_headless.c:33 blit_surf` が `gui_core.c:177 surf_free` 済み surface を読む) |
| `1f20ec7` | run1 | 検証 subagent | **0** | 173 s | 0.11 → 1.71 | 426 passed |
| `1f20ec7` | run2 | 検証 subagent | **0** | 102 s | 1.33 → 1.44 | 426 passed |

- **結論**: 最終 HEAD `1f20ec7` で 2/2 ALL PASS (rc=0)。
- **ただし解消ではない**: 1/6 に到達した 6 回中 2 回 (T1・R2) が ASan UAF で rc=1 になった。既存の race (#489 `[GUI-12]`、§10 の旧測定 20 回中 4 回と同型) で、本 PR は `src` を変えていない。「ALL PASS」を受入とみなすかは PM 判断。
- 層ごとの結果 (run1 と run2 で同一):

| 層 | 結果 (`1f20ec7`) |
|---|---|
| 0/6 API 面 | 51 APIs: implemented 51, with unit test 51 |
| 1/6 selftest (ASan/UBSan) | 426 passed / 0 failed |
| 1b/6 bpp golden | 16,000 px 差 0 (EXACT)。陰性対照 (negctl) OK |
| 1c0/6 FreeType テキスト | native == wasm32 (TOTAL edd537e3b390f846)・wasm64 PASS、text golden ALL PASS |
| 2/6 native lift (PE→RetDec→gcc) | golden EXACT MATCH 0 / 64,000 px |
| 2b/6 reach / adapt / 改名 selftest | 11 passed / 28 passed / 426 passed、0 failed |
| 1c/6 SIMD == scalar | 15,679 ケース不一致 0。故意欠陥 `GS_FAULT=1〜4` は 1,632 / 271 / 252 / 268 件で FAIL (陰性対照)。v128 系命令 simd=1,074 / `-DGUI_NO_SIMD` 0 |
| 3〜6/6 lift → emcc → tsc → Chrome | OffscreenCanvas・画面とも golden EXACT (0 px)。6b (memory growth) EXACT (0 px) ×2。6c fail-fast `EXIT code 0xfa11`。6d 到達 `reached=36 impl=36 stub=0` |
| 6e/6 sigprobe | declares 177, mismatch 0 (陰性対照 mismatch 177)。`unresolved-imports` は未計測 (下記 §3) |
| 6f/6 present e2e | ALL PASS |

### 2. wasm 全体 (shim の API 単位) の SIMD128 / scalar: `bash tools/gui/test/wbench.sh 5`

最終 HEAD で 1 回 (23 s, load 1.32 → 1.73)。同一 `test/bench.c` を `-msimd128` / `-DGUI_NO_SIMD` で emcc ビルドし交互に 5 回ずつ (n=5, min–max ms/frame, 1920x1080)。最終 wasm の v128 系命令は simd 684 / scalar 0 (取り違えは exit 1)。`min 比` = scalar の最小 / simd の最小。

| API | scalar | simd128 | min 比 |
|---|---|---|---|
| BitBlt SRCCOPY mem→mem (memmove) | 0.33–0.67 | 0.37–0.60 | 0.89x |
| BitBlt SRCCOPY mem→window | 0.30–0.40 | 0.33–0.43 | 0.91x |
| BitBlt SRCINVERT (per-pixel) | 3.40–4.20 | 0.53–0.83 | 6.42x |
| BitBlt SRCPAINT (per-pixel) | 3.70–3.83 | 0.37–0.47 | 10.00x |
| StretchBlt 2x nearest | 1.70–1.77 | 0.53–0.77 | 3.21x |
| StretchDIBits 1:1 (32bpp, per-pixel) | 1.17–1.50 | 0.43–0.60 | 2.72x |
| StretchDIBits 24bpp 1:1 | 3.10–3.37 | 2.13–2.20 | 1.46x |
| StretchDIBits 8bpp 1:1 | 2.40–2.43 | 1.53–1.57 | 1.57x |
| AlphaBlend per-pixel α (sca=128) | 16.33–16.63 | 2.27–2.53 | 7.19x |
| AlphaBlend 定数 α (sca=128) | 16.17–16.77 | 1.63–1.87 | 9.92x |
| BitBlt SRCCOPY from 24bpp DIB section | 2.47–2.53 | 2.33–2.63 | 1.06x |
| BitBlt SRCCOPY into 24bpp DIB section | 4.17–4.17 | 4.40–4.43 | 0.95x |
| FillRect solid | 0.43–0.43 | 0.27–0.30 | 1.59x |
| BitBlt → window + present (headless) | 0.33–0.40 | 0.33–0.40 | 1.00x |

- SRCCOPY の 2 行 (memmove 系) は SIMD の対象外で、0.89x・0.91x は範囲が重なる誤差内 (1.00x が正)。24bpp 先・DIB 源は pull/push が支配的で差が出ない。
- レビュワーの `1457db3` 測定 (AlphaBlend per-pixel 7.16x・定数 α 9.64x・SRCINVERT 6.92x・SRCPAINT 10.63x) と同水準。
- 画素一致は §10 と本付録 §1 の 1c/6 が担い、本 bench は時間のみ。
- **未取得**: Chrome 上の lift 済みアプリでの API 単位 frame time。`gui_app.c` は 320x200 の静的シーンで、e2e の bench は renderer 側 (変換 + putImageData) のみを測るため shim の時間を分離できない。実 FL (#174) 到達後に取る。

### 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1/6 ASan UAF (`gui_headless.c:blit_surf` ↔ `surf_free`) が同 src 群の 6 回中 2 回で発火 | 「ALL PASS」は確率事象で、解消ではない。受入扱いは PM 判断 | #489 `[GUI-12]` (既存) |
| `integ/sigprobe.sh` の `unresolved-imports` が `wasm-objdump` (WABT) 不在で空振り (両 run で `command not found`) | 「未解決 import なし」の検査が無効 (`mismatch=0` と陰性対照 177 は有効) | #180 (既存コメント) |
| Chrome 上の lift 済みアプリの API 単位 frame time | 未取得 | #181 → 実 FL (#174) 到達後 |
| `main` (`0fa8283`) が本ブランチより 70 commit 先行 (`git merge-tree` は衝突なし) | merge 前に main を取り込んで e2e を取り直すかは PM 判断 | PM |

### 4. 再現

```
bash tools/gui/e2e.sh          # 全層 (run 102 s / 173 s)。前提: x86_64-w64-mingw32-gcc (apt gcc-mingw-w64-x86-64)、RetDec、emsdk
bash tools/gui/test/wbench.sh 5   # wasm SIMD/scalar の API 単位比較 (23 s)
```
