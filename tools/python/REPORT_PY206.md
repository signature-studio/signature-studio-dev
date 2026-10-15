# tools/python REPORT PY-206 — device 系 32 関数のうち PE 確定の 7 関数を C provider に実装 (#3494, 親 #941)

既知類型との関係 (DEFECTS.md): 該当なし (逆アセンブルで戻り値・status 経路を読んだが、lift の miscompile ではなく Python API の意味論の確定)。

## 結論

- device 37 関数のうち実装は 5 → **12** (本 PR で 7 追加: `createRefreshThread` / `destroyRefreshThread` / `fullRefresh` / `getIdleElapsed` / `isMidiOutAssigned` / `getMasterSync` / `setMasterSync`)。残り **25 関数**は子 issue 3 件へ分割 (表 §未解決)。
- 7 関数の戻り型・status 経路は PE (VA) で確定。**値**は仮置き: `getIdleElapsed = 0.0`・`isMidiOutAssigned = False`・`getMasterSync = False` (`setMasterSync` で書いた値を返す)。実機の初期値は未測定。
- 通知 3 件 (`createRefreshThread` 等) の**効果**は、assigned 機器の vtbl 先 (未読) にあり、状態を持たない。
- mock (`host/fl_mock.mjs`) と C (`provider/fl_engine.c`) の差分 0 (`tests/device_diff.mjs`)。`FL_ENGINE=wasm tests/all_tools.mjs` は 48/48 ok を維持。

## 手段

- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <命令数>`。エントリ探索: `analysis/flapi/pe_handler_probe.py <名前...>` (PyMethodDef の entry・fn・flags を引く)。
- 入力: `fl-win64.tar.zst` から `*block00031_PE.bin` (22,227,016 B) のみ展開 (`tar --zstd -xf ... --wildcards`、約 2.3 秒)。`fetch_inputs.sh` 用に `block25159` / `block24429` / `block24430` / `block24618` を追加展開。
- 署名: `analysis/flapi/flapi_table.json` (device 37 関数)。未実装 32 = 本 issue の対象 (`tests/provider_check.mjs` の dev 集合 5 件を除く)。
- 共通の取得 helper `0xd77da0`: `mov rax,[rip+..]; call [rax]` の 1 命令 thunk。device 関数は `obj = [[0xd77da0()]]`、assigned 機器 `q = [obj+0x50]` を読む。`q == 0` は status **-7** (`Device not assigned`、写像は `REPORT_PY61.md` §4-2)。

## PE 確定事項 (entry / fn は `pe_handler_probe.py` の出力)

| 関数 (flags) | entry / fn | 戻り | 分岐 (VA) | 本 PR の扱い |
|---|---|---|---|---|
| `createRefreshThread` (NOARGS) | 0x151d340 / 0xd75f40 | None | `q`≠0 → `call [q.vtbl+0x68]` (0xd75f5f、戻り捨て)、status 0 → None。`q`=0 → -7 (0xd75f64) | None を返す。vtbl 先の効果は未読 |
| `destroyRefreshThread` (NOARGS) | 0x151d360 / 0xd75f80 | None | `call [q.vtbl+0x60]` (0xd75f9f)。`q`=0 → -7 (0xd75fa4) | 同上 |
| `fullRefresh` (NOARGS) | 0x151d380 / 0xd75fc0 | None | `call [q.vtbl+0x70]` (0xd75fdf)。`q`=0 → -7 (0xd75fe4) | 同上 |
| `getIdleElapsed` (NOARGS) | 0x151d460 / 0xd76980 | float | `q`=0 → -7 (0xd769a9)。else `cvtss2sd` の `[q+0x3d0]` (float32) → PyFloat (0xd76995〜0xd769a5) | 状態読出し。初期値 0.0 は仮置き |
| `isMidiOutAssigned` (NOARGS) | 0x151d220 / 0xd75a40 | bool | `q`=0 → False (0xd75a60)。else `[[q+0x7c]+0x4c] != 0` (0xd75a55〜0xd75a5e) | 状態読出し。エラー経路なし。初期値 False は仮置き |
| `getMasterSync` (NOARGS) | 0x151d4a0 / 0xd76b80 | bool | `q`=0 → -7 (0xd76bba)。`r=[q+0x7c]`=0 → -6 (0xd76bae、`0xfffffffa`)。else `bool([r+0x48])` (0xd76b9e) | 状態読出し。-6/-7 は到達させない (assigned を仮定)。初期値 False は仮置き |
| `setMasterSync` (value:bool, PyArg `i`) | 0x151d480 / 0xd76a60 | None | dispatch `0xd843d0` (`arg5 = value`、callback `0xd769c0`)。callback: 述語 P 偽 → status -2 のまま (0xd76a56)。`q`=0 または `[q+0x7c]`=0 → -7 (0xd76a4e)。else `[r+0x48] = (value == 1)` (0xd76a17 `sete`) | `[r+0x48] = (value==1)` を書き、`getMasterSync` が同じ byte を読む (PE で一致)。P は真と仮定 |

- `setMasterSync` の callback は `REPORT_PY125` §2 と同形の述語 P (`[[Y]+0x98]`) で始まる。同一の述語かは未照合。P 偽の -2 経路は実行時値に依存するため、仮定 (真) で閉じる。
- `getMasterSync` の -6 と `setMasterSync` の -7 は、同じ `[q+0x7c]` の欠落に対して別の status を返す (PE の事実)。C/mock では両方とも到達させない。

## 実装

- `provider/fl_engine.c`: 7 handler。状態 `idle_elapsed` (double)・`midi_out_assigned`・`master_sync` (int) を追加し、`fl_engine_reset` で 0 に戻す。`setMasterSync` は `A_INT(0, 0) == 1` (`screen.unBlank` と同形)。
- `host/fl_mock.mjs`: 7 エントリ。`st.idleElapsed` / `st.midiOutAssigned` / `st.masterSync` を追加。`setMasterSync` は `argI(a,0,0) === 1`。
- `tests/device_diff.mjs`: 呼出し 8 → 18 (追加 10: 通知 3・状態読出し 3・`setMasterSync(true)` / `getMasterSync` を交互の 4)。署名違反 (code 5) 4 → 10 (追加 6)。戻り float は `{t:'D', v}` のタグを外して比べ、`getIdleElapsed` の D タグは別に確認。
- `tests/provider_check.mjs`: `pe206` の 7 関数を実装集合に追加。期待値は main (ed70adf5a、`pe40` 取り込み後) の 149/286 から **156/279** へ。

## 旧測定節 (`0641856`〜`b3c3dafdd`)

- 分割移動: `tools/python/REPORT_PY206_APPENDIX.md` (`0641856`・`dc65d9857`・`342d8ce92`・`868d0fbbb`・`17969a203`・round 6・round 6b の各節)。

## 再測定 (競合解消 round 7・測定 commit `e814e9d20`・main `14cda5e43` 取り込み後)

- 測定 commit: `e814e9d20` (`origin/main` (`14cda5e43`) を merge した commit。前節 `b3c3dafdd` の後に main へ入った変更を取り込んだ: `fl_mock.mjs`・`fl_engine.c` (`mixer.getTrackColor` の idx < 0、`playlist.muteTrackLock` の safe-edit 判定、`ui.showPicker`・`ui.openEventEditor` の PyArg 検査 (PY-133・#3014)、`setSafeEdit`)・`fl_provider.mjs`・`provider/build.sh`・テスト 4 本。device 関数の C / mock コードは変わっていない)。競合は `tests/provider_check.mjs` の 1 箇所 (判定 `if` と件数 assert)。main 側の `pe133` (ui PE 確定 2 件) を PR 側 `pe206` と併存させ、件数を **182** 実装・**253** 未実装にした (`fl_table.c` のハンドラ数 182 と一致)。コードを変えた最後の commit。
- 測定 commit から HEAD までのコード差分: `git diff e814e9d20 HEAD -- tools/python/host tools/python/provider tools/python/tests` は出力 0 行 (本節を書いた commit は `tools/python/REPORT_PY206.md` と PR 本文だけを変える)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に全展開 (`tar --zstd -xf`・約 6 秒)、`toolchain-emsdk` は `[EMSDK]` (emsdk 6.0.12)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` rc 0。`block00031_PE.bin` (win PE) は展開していないため、`build_flpy.sh` は `FLPY_SKIP_TABLE=1` で追跡済みの `flapi_table.json` を使った。

| 検査 | 結果 | rc |
|---|---|---|
| `bash provider/build.sh` | `fl_table.c: 435 関数, ハンドラ 182` | 0 |
| `bash build_cpython_wasm.sh` | 新規ビルド 4 分 10 秒 (4 core) | 0 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | flpy.js / flpy.wasm 生成 6 秒 | 0 |
| `node tests/provider_check.mjs` (§3 flpy 段を含む) | functions 435・**implemented 182**・unimplemented 253・mcp_static 60・PASS (0.37 秒) | 0 |
| `node tests/device_diff.mjs` | calls 21・link_calls 6・rejects 10・**diffs 0**・PASS | 0 |
| `node tests/*_diff.mjs` (22 本・device_diff を含む) | 全て **diffs 0**・PASS (各 0〜1 秒) | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true (2.4 秒) | 0 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok・host_calls 37,425 (2.2 秒) | 0 |
| `node tests/midi_script.mjs` / `node tests/ilmcp_e2e.mjs` | MIDI SCRIPT OK (checks 29・failed []) / PASS | 0 |
| `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 node tests/pyscript_e2e.mjs` | **72 PASS・fail 0** (3.5 秒) | 0 |

- ネガティブコントロールは今回は再実行していない。device 関数 (PY-206 の 7 関数) の C / mock 実装は `b3c3dafdd` から変わっていない (差分は main 由来の mixer・playlist・ui の関数のみ)。
- 負荷: load average は未計測。各検査は単発の直列実行。

## 再測定 (競合解消 round 8・測定 commit `a2ecafa0b`・main `512b09ffa` 取り込み後)

- 測定 commit: `a2ecafa0b` (`origin/main` (`512b09ffa`) を merge した commit。前節 `e814e9d20` の後に main へ入った `general.processRECEvent` (PY-235・#3701) の mock / C 実装と `general_diff.mjs` の追加分を取り込んだ)。競合は `tests/provider_check.mjs` の 1 箇所 (判定 `if` と件数 assert)。main 側の `pe235` (1 件) を PR 側 `pe206` (7 件) と併存させ、件数を **183** 実装・**252** 未実装にした (`fl_table.c` のハンドラ数 183 と一致)。`provider/fl_engine.c`・`host/fl_mock.mjs` は自動 merge。device 関数の C / mock 実装は round 6b から変わっていない。コードを変えた最後の commit。
- 測定 commit から HEAD までのコード差分: `git diff a2ecafa0b HEAD -- tools/python/host tools/python/provider tools/python/tests` は出力 0 行 (本節を書いた commit は `tools/python/REPORT_PY206.md` だけを変える)。
- 素材・入力: round 7 と同じ (`fl-win64` 全展開・`fetch_inputs.sh` rc 0・`[EMSDK]`・`FLPY_SKIP_TABLE=1`)。`build_cpython_wasm.sh` は round 7 の成果物を再利用。

| 検査 | 結果 | rc |
|---|---|---|
| `bash provider/build.sh` | `fl_table.c: 435 関数, ハンドラ 183` | 0 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | flpy.js / flpy.wasm 生成 (6 秒) | 0 |
| `node tests/provider_check.mjs` (§3 flpy 段を含む) | functions 435・**implemented 183**・unimplemented 252・mcp_static 60・PASS | 0 |
| `node tests/*_diff.mjs` (22 本・device_diff を含む) | 全て **diffs 0**・PASS (各 0〜1 秒) | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | 0 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok・host_calls 37,425 | 0 |
| `node tests/midi_script.mjs` / `node tests/ilmcp_e2e.mjs` | MIDI SCRIPT OK (checks 29・failed []) / PASS | 0 |
| `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 node tests/pyscript_e2e.mjs` | **72 PASS・fail 0** | 0 |

- ネガティブコントロールは round 6b (`b3c3dafdd`) の値を引き継ぎ、今回は再実行していない (device 関数の C / mock は変わっていない)。
- 負荷: load average は未計測。各検査は単発の直列実行。

## 再測定 (取り込み後 round 9・測定 commit `1a568288b`・main `43cabef4c` 取り込み後)

- 測定 commit: `1a568288b` (`origin/main` (`43cabef4c`) を merge した `eb6e8deaa` の後、`tests/provider_check.mjs` の件数 assert だけを変えた commit。コードを変えた最後の commit)。取り込みで main の `pe128` (ui 2 件・#3005) を PR 側の判定 `if` に併存させ、件数 assert を **195** 実装・**240** 未実装にした (`fl_table.c` のハンドラ数 195 と一致)。`provider/fl_engine.c`・`host/fl_mock.mjs` は自動 merge。
- 測定 commit から HEAD までのコード差分: `git diff 1a568288b HEAD -- tools/python/host tools/python/provider tools/python/tests` は出力 0 行 (本節を書いた commit は `tools/python/REPORT_PY206.md` と PR 本文だけを変える)。
- 素材・入力: `fl-win64` を `$RUNNER_TEMP/fl` に全展開 (`tar --zstd -xf`・8 秒)、`FL_WIN64_DIR=$RUNNER_TEMP/fl bash fetch_inputs.sh` rc 0。`FLPY_SKIP_TABLE=1 build_flpy.sh` の入力は追跡済みの `flapi_table.json`。

| 検査 | 結果 | rc |
|---|---|---|
| `bash provider/build.sh` | `fl_table.c: 435 関数, ハンドラ 195` | 0 |
| `bash build_cpython_wasm.sh` | 新規ビルド・python.wasm 生成 | 0 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | flpy.js / flpy.wasm 生成 | 0 |
| `node tests/provider_check.mjs` (§3 flpy 段を含む) | functions 435・**implemented 195**・unimplemented 240・mcp_static 60・PASS | 0 |
| `node tests/device_diff.mjs` | calls 21・link_calls 9・rejects 10・midi_out 11・**diffs 0**・PASS | 0 |
| `node tests/*_diff.mjs` (23 本・`screen_menu_diff` を含む) | 全て **PASS** (diffs 0) | 0 |
| `node tests/all_tools.mjs` (JS mock) | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425 | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | 0 |
| `node tests/midi_script.mjs` / `node tests/ilmcp_e2e.mjs` | MIDI SCRIPT OK (checks 29・failed []) / PASS | 0 |
| `FL_WIN64_DIR=$RUNNER_TEMP/fl node tests/pyscript_e2e.mjs` | **72 PASS・FAIL 0** (3 秒) | 0 |

- ネガティブコントロール (測定 commit `1a568288b` で再実行。`host/fl_mock.mjs` を一時変更し、`device_diff.mjs` の件数を記録してから元に戻した):
  - (a) `device.getMasterSync` を `return true` → **device 差分 2 件**・exit 1 (REPORT の前回値 2 件と一致)
  - (b) `device.setMasterSync` を `st.masterSync = false` → **device 差分 1 件**・exit 1 (前回値 1 件と一致)
  - 復元後 `device_diff.mjs` は rc 0。
- 負荷: load average は未計測。各検査は単発の直列実行。

## 検証範囲 / 範囲外

- 範囲内: PE の戻り型・status 経路 (上表)、mock と C の 7 関数の差分 0、既存 48 件の回帰、件数の表 (測定 commit `1a568288b` で 435 = 実装 195 + 未実装 240)。
- 範囲外 (未確定のまま残す): 実 FLEngine 上の状態値 (idle・midi-out・master sync の初期値)、通知 3 件の vtbl 先の効果、`setMasterSync` の述語 P 偽 (-2) の発生条件、`0x1366e00`・`0xfd7170`・`0xfd7240` の効果、-6/-7 の実発生。
- KPI: device API は起動・GUI に関わらないため、起動 KPI (`tools/flelift/boot/REPORT.md`) は動かしていない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 25 関数 (MIDI 送信・dispatch 系 13 / linked control 系 8 / その他 4) | device 系の未実装 25 件 (C provider は Unspecified error) | #3566 (PY-214・13 関数)・#3568 (PY-215・8 関数)・#3569 (PY-216・4 関数) |
| 状態値の実機初期値 (idle / midi-out / master sync) | 実 FLEngine の値と mock の値が異なりうる | 子 #3566・#3568・#3569 の受入に含めない。`general` 系と同じく仮置きのまま、実機測定の子を別途起票する (PM 判断) |
| P 偽 (-2) と vtbl 先の効果 | `setMasterSync` / 通知 3 件の副作用が C/mock で模擬されない | 同上 (PY-125 の `REPORT_PY125` §4 と同じ未解決として扱う) |
| 7 関数は未割当 (`q`=0) の status -7 を返さない (assigned を仮定)。`getMasterSync` の -6 も同じ。PE は -7・-6 を返す | 未割当で呼んだ戻りが実機と異なる。`midiOutMsg` (PY-227・`fl_engine.c`) は未割当で -7 を返すため、device 系の判定が揃わない | PM 判断の既定案 (2026-10-15・PM agent の判断待ち): 現状どおり assigned を仮定し、本表で追跡する。C/mock で返すかは未決定。本 PR では未起票。対応する場合は C の `if (!dev_assigned)`・mock の `devAssigned` を入れ、`device_diff` に未割当のケースを足す |
