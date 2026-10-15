# RT-15 (#2552) 付録: memload real から派生 `PoolBridge` を撤去

REPORT.md の §RT-6 実 loader 接続 (#125) で使った派生 loader `PoolBridge` の撤去記録。REPORT.md が 250 行上限のため別置き。

## 変更 (測定 commit `0af3030c`)

- `real_worker.mjs`: `PoolBridge` (`HostBridge` 派生。LoadLibraryW の採番だけ単調増加に置換) を削除し、共有 `hb_bridge.mjs` の `HostBridge` を直接使う。`real_worker.mjs` と `run_real.mjs` の冒頭コメントから PoolBridge の記述を外した。
- 等価性: 共有 `HostBridge.LoadLibraryW` は #2553 (RT-14) で `allocHandle()` = `HMODULE_BASE + ++hseq × 0x10000` に変わった。PoolBridge の採番と同式で、`hseq` の初期値も 0。他の処理 (`readWStr`・`table.resolve`・`lastLoadMode`・`refs++`・`hbHostCall`・`guest.init()`・`loaded`/`byHandle` 登録) も同一。挙動が一致するので試験条件は変わらない。

## 受入 1 (memload real の PASS): 未実測

- `bash tools/hostbridge/lowbase/retdec/build_m10_lb.sh` は `lb_data_gen.py` で `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll` を読む。素材 `analysis-ott-binaries` が無く、`[ANALYSIS-PLUGINS]` 配下の `ott/binaries/OTT_vst2_win64.dll` が存在しないため `FileNotFoundError` で rc=1 停止。
- `node tools/runtime/memload/real/run_real.mjs --neg-only` は lowbase の `ott_hb.cjs` が無いため「前提無し」で rc=2。
- 再依頼の素材: `fl-win64 toolchain-emsdk toolchain-retdec work-m6-ott analysis-ott-binaries` (依頼 issue の `oc_artifacts` 行に `analysis-ott-binaries` を足す)。取得後は `build_m10_lb.sh` → `retdec/build_host_lb.sh` → `pnpm runtime:memload:real` の順で実行し、所要・PASS/FAIL・ロード数をこの付録に残す。
- 追補 (#2519 RT-13): 上の「未実測」は解消。実測結果は `tools/runtime/REPORT.md` の RT-13 節が正本。
