# tools/gui REPORT 付録 (本体 REPORT.md は 250 行上限のため §12 を分割)

## 12. GUI-5 (#181) 続き: RetDec 付き e2e.sh 全体 ALL PASS と wasm 全体の SIMD/scalar 比較

既知類型との関係: lift 欠陥ではなく shim の意味論 (§10 の同一サーフェス複数クリップ欠陥は `docs/DEFECTS.md` D18 に登録)。検証起点: main `021fd75` + 本ブランチ (`tools/gui` の src は無変更。追加は `test/wbench.sh`・`test/wbench_shim.c` のみ)。runner 4 CPU、node v22.23.3、emcc 6.0.12、mingw-w64 は apt `gcc-mingw-w64-x86-64`、RetDec は `toolchain-retdec`。

### 1. `bash tools/gui/e2e.sh` (RetDec 付き・全層) → **ALL PASS (rc=0, 所要 88.6 s, load 0.95〜1.14)**
| 層 | 実測 |
|---|---|
| 1/6 selftest (ASan/UBSan) | 406 passed / 0 failed |
| 1b/6 bpp golden | 16,000 px 差 0。陰性対照 2/2 拒否 |
| 2/6 native lift (PE→RetDec→gcc) | golden EXACT MATCH 0/64,000 px |
| 2b/6 reach_test / adapt_test / 改名 selftest | 11 / 28 / 406 passed、0 failed |
| 1c/6 SIMD == scalar | 15,679 ケース不一致 0。故意欠陥 4 種 FAIL (1632/271/252/268 件)。v128 命令 1,020 / `-DGUI_NO_SIMD` 0 |
| 3〜6/6 lift → emcc → tsc → Chrome | readback・screenshot とも golden EXACT (0/64,000 px)。6b (memory growth)・6c (fail-fast 0xfa11)・6d (到達 36 API, stub 0) PASS |
| 6e/6 sigprobe | declares 177, mismatch 0 (adapter 無しの陰性対照 177)。`unresolved-imports` は `wasm-objdump` 不在のまま (#180 既存) |
| 6f/6 present e2e | fail 0, ALL PASS |
FAIL した層は無し。native selftest の ASan UAF (#489) は今回の 1 回では発火せず (確率事象のため解消ではない)。

### 2. wasm 全体 (shim の API 単位) の SIMD128 / scalar: `bash tools/gui/test/wbench.sh 5` (14.5 s, load 0.5〜0.7)
同一 `test/bench.c` を `-msimd128` / `-DGUI_NO_SIMD` で emcc ビルドし交互に 5 回ずつ (n=5, min–max ms/frame, 1920x1080)。最終 wasm の v128 命令は simd 684 / scalar 0 (取り違えは exit 1)。`gui_now_ms` が 1 ms 粒度のため 0.3 ms 未満の行は 0.03 ms 刻みの粗い値。
| API | scalar | simd128 | min 比 |
|---|---|---|---|
| BitBlt SRCINVERT | 2.70–3.23 | 0.43–0.67 | 6.28x |
| BitBlt SRCPAINT | 2.83–2.87 | 0.27–0.30 | 10.48x |
| StretchBlt 2x | 1.30–1.33 | 0.33–0.63 | 3.94x |
| StretchDIBits 32bpp 1:1 | 0.90–0.93 | 0.30–0.43 | 3.00x |
| StretchDIBits 24bpp / 8bpp 1:1 | 2.40–2.47 / 1.87–1.90 | 1.67–1.73 / 1.20–1.23 | 1.44x / 1.56x |
| AlphaBlend per-pixel / 定数 α | 12.67–12.87 / 12.53–12.63 | 1.73–1.87 / 1.30–1.33 | 7.32x / 9.64x |
| FillRect solid | 0.33–0.53 | 0.20 | 1.65x |
| BitBlt SRCCOPY (memmove 系 3 行) | 0.23–0.43 | 同左 | 1.00x |
| BitBlt SRCCOPY 24bpp DIB 源 / 先 | 1.87–1.90 / 3.20–3.27 | 1.77–1.80 / 3.37–3.47 | 1.06x / 0.95x |
- SRCCOPY は memmove で SIMD の対象外 (1.00x が正)。24bpp 先は pull/push が支配的で SIMD 差が出ない (0.95x = 誤差内)。
- 画素一致は SIMD == scalar を §10・§12-1 (1c/6) が担い、本 bench は時間のみ。lift 済みアプリ (scalar ビルド `GUI_NO_SIMD=1 gui_wasm.sh`、v128 命令 0 / SIMD 版 223) も Chrome e2e で golden EXACT (0/64,000 px)。
- **未取得**: Chrome 上の lift 済みアプリでの API 単位 frame time。gui_app.c は 320x200 の静的シーンで、e2e の bench は renderer 側 (変換 + putImageData) のみを測るため shim の時間を分離できない。実 FL (#174) 到達後に取る。
