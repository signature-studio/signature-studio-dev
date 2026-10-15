# AU-15 (#4089) 付録: underrun 時刻と write 区間の突き合わせ


測定 commit `60b58c68a` (コード変更は本 commit のみ・base `47a76cf4b`)。`bash tools/audio/integration/e2e.sh` を foreground で実行 (`TMPDIR=$RUNNER_TEMP`)。

- 時間軸: worklet は underrun の最初の 1 回を `Date.now()` の epoch µs 下 32bit (`capture hdr[7]`) へ記録。producer の `pw_trace` は `emscripten_get_now()` の epoch 基準 µs 下 32bit。両者とも epoch 基準なので同じ軸で差を取る。精度は worklet 側の ms (±1000 µs)。
- 判定行: `uo_overlap` (重なり有無)・`uo_gap_us` (0 で区間内、>0 で区間後、<0 で区間前)・`uo_w`・`uo_wake_us`・`uo_done_us`。`underrun=0` の run は `uo_overlap=none`。
- 合成検証: `node tools/audio/integration/uo_negctl.mjs` で `matchUnderrunWrite` を抜き出して実行。正例 3 (内側・両端)・負例 3 (前・間・後)・u32 折り返し 2・空 1 の計 9 件 **ALL PASS** (終了コード 0)。
- 実 e2e: 無負荷 10 run・負荷 (Python 4 プロセスの CPU 占有) 10 run、計 20 run。**全 20 run exit 0・13/13 PASS**。無負荷 10.4〜10.9 s、負荷 14.9〜15.9 s。全 run で underrun 0 件のため、`uo_overlap` の実値 (true/false) は**未取得**。実 underrun での判定は #863 の再現待ち。
