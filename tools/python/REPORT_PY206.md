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

## 実測 (測定 commit `0641856`)

| 検査 | 結果 | rc |
|---|---|---|
| `bash provider/build.sh` (`emsdk` は `[EMSDK]` (既定の `EMSDK_ENV`)、`toolchain-emsdk` 素材は未展開) | `fl_table.c: 435 関数, ハンドラ 156` | 0 |
| `bash build_flpy.sh` (CPython 3.12 wasm は `build_cpython_wasm.sh` で作成、3 分 14 秒) | flpy.js / flpy.wasm 生成 | 0 |
| `node tests/device_diff.mjs` | calls 18・rejects 10・midi_out 5・**diffs 0**・PASS | 0 |
| `node tests/provider_check.mjs` | functions 435・**implemented 156**・unimplemented 279・PASS | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | 0 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok・host_calls 37,425 | 0 |

- 測定環境: GitHub Actions runner (親 dir の worktree `ws-3494`、commit `0641856`)。load average は測定中 2.2〜2.9 (`uptime`、n=1)。`device_diff` / `provider_check` / `all_tools` の所要は main 作業ツリーでの先行測定 (provider_check 0.33 秒、all_tools wasm 1.39 秒、load 2.2〜2.4)。
- **ネガティブコントロール** (1 件を壊して FAIL すること。作業ツリーの写し・base `e5c96411e` 上で実施): (a) mock の `getMasterSync` を `return true` → `device 差分 1 件`・exit 1 (`device.getMasterSync` の値の不一致)。(b) mock の `setMasterSync` を `st.masterSync = false` → `device 差分 1 件`・exit 1。本体 (壊していない版) は diffs 0・exit 0。
- 追加の確認: `git status` で作業ツリーに残る変更は本 PR の 4 ファイル (+ `REPORT_PY206.md` と `docs/DOC_MAP.md`) のみ。`package.json`・`pnpm-lock.yaml` は runner 側の既存差分で commit に含めない。

## 競合解消後の再測定 (測定 commit `dc65d9857`)

main (`5fae94c61`) を merge して競合 (`tests/provider_check.mjs` の実装集合と期待件数) を解消した後に再測定した。main 側の patterns 4 関数 (PY-179・#3271) と合算し、期待値は **160/275** (`fl_table.c` ハンドラ 160)。前節の `0641856` の値は merge 前の値として残す。

| 検査 | 結果 | rc |
|---|---|---|
| `bash provider/build.sh` | `fl_table.c: 435 関数, ハンドラ 160` | 0 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` (CPython は `build_cpython_wasm.sh`、3 分 47 秒。flpy の入力 `src/`・flapi 表は main と差分 0) | flpy.js / flpy.wasm 生成 | 0 |
| `node tests/device_diff.mjs` | calls 18・rejects 10・midi_out 5・**diffs 0**・PASS | 0 |
| `node tests/provider_check.mjs` | functions 435・**implemented 160**・unimplemented 275・PASS | 0 |
| `node tests/patterns_diff.mjs` (main 側) | calls 25・**diffs 0**・PASS | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | 0 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok・host_calls 37,425 | 0 |

- 所要 (`date` 差分・整数秒): device_diff 0・provider_check 1・patterns_diff 0・all_tools wasm 1・all_tools mock 1。load average は測定中 2.75〜3.05 (`uptime`、n=1)。
- 測定 commit `dc65d9857` から HEAD までのコード差分: `git diff dc65d9857 HEAD -- tools/python/host tools/python/provider tools/python/tests` は出力 0 行 (本節の追記は REPORT のみ)。
- 前回測定 (`0641856`) から `dc65d9857` までのコード差分 (main 取り込み分、4 ファイル・+81/-3): `host/fl_mock.mjs` +7・`provider/fl_engine.c` +9・`tests/patterns_diff.mjs` +60・`tests/provider_check.mjs` (実装集合と期待件数)。

## main 再取り込み後の再測定 (測定 commit `342d8ce92`)

main (`cc5c28b8f`) を再度 merge した (merge commit `342d8ce92`)。前回の merge 後に main へ入った PY-205 (mixer 2 関数・`tests/mixer_diff.mjs`) と channels grid bit (PY-101/112) を取り込んだ。競合は `tests/provider_check.mjs` の 1 ファイル 2 箇所のみ: 実装集合の定義 (device の `pe206` と mixer の `pe205` を両方残す) と、実装判定 `if` と件数 assert。件数は device 7 + mixer 2 を加えて **162/273** (計 435)。`fl_engine.c`・`fl_mock.mjs` は自動 merge。

| 検査 | 結果 | rc |
|---|---|---|
| `bash provider/build.sh` | `fl_table.c: 435 関数, ハンドラ 162` | 0 |
| `bash build_cpython_wasm.sh` (fresh worktree・`work/` 無し) | 163 秒 | 0 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | flpy.js / flpy.wasm 生成 | 0 |
| `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash fetch_inputs.sh` | work/midi.py・utils.py・MCPTools.pyc 配置 | 0 |
| `node tests/provider_check.mjs` | functions 435・**implemented 162**・unimplemented 273・PASS | 0 |
| `node tests/device_diff.mjs` | calls 18・rejects 10・midi_out 5・**diffs 0**・PASS | 0 |
| `node tests/mixer_diff.mjs` | calls 62・**diffs 0**・PASS | 0 |
| `node tests/patterns_diff.mjs` | calls 25・**diffs 0**・PASS | 0 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | **48/48 ok**・soft_error 0・raised 0・host_calls 37,425・callback_roundtrip true | 0 |
| `node tests/all_tools.mjs` (JS mock) | 48/48 ok・host_calls 37,425 | 0 |

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf`・8 秒・rc 0)。emsdk は `/opt/emsdk` (emcc 6.0.12)。
- 所要 (整数秒・`date` 差分。provider build は `time` 実測 0.87 秒): cpython 163・flpy 4・provider_check 0・device_diff 0・mixer_diff 0・patterns_diff 0・all_tools wasm 1・all_tools mock 1。load average は測定中 1.27〜1.99 (`uptime`、n=3)。
- 前回測定 (`dc65d9857`) から `342d8ce92` までのコード差分 (main 取り込み分): `git diff --stat dc65d9857 342d8ce92 -- tools/python/host tools/python/provider tools/python/tests` は 4 ファイル (+28/-16)。`fl_mock.mjs`・`fl_engine.c` の差分は channels grid bit と mixer 2 関数で、device 関数の実装行は差分 0。device のネガティブコントロール (冒頭の検証節) は本節では未再実施。

## 検証範囲 / 範囲外

- 範囲内: PE の戻り型・status 経路 (上表)、mock と C の 7 関数の差分 0、既存 48 件の回帰、件数の表 (435 = 実装 162 + 未実装 273)。
- 範囲外 (未確定のまま残す): 実 FLEngine 上の状態値 (idle・midi-out・master sync の初期値)、通知 3 件の vtbl 先の効果、`setMasterSync` の述語 P 偽 (-2) の発生条件、`0x1366e00`・`0xfd7170`・`0xfd7240` の効果、-6/-7 の実発生。
- KPI: device API は起動・GUI に関わらないため、起動 KPI (`tools/flelift/boot/REPORT.md`) は動かしていない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残り 25 関数 (MIDI 送信・dispatch 系 13 / linked control 系 8 / その他 4) | device 系の未実装 25 件 (C provider は Unspecified error) | 子 issue C1〜C3 (本 PR 作成時に起票。番号は PR 本文・issue コメントに記載) |
| 状態値の実機初期値 (idle / midi-out / master sync) | 実 FLEngine の値と mock の値が異なりうる | 本 issue の子 C1〜C3 の受入に含めない。`general` 系と同じく仮置きのまま、実機測定の子を別途起票する (PM 判断) |
| P 偽 (-2) と vtbl 先の効果 | `setMasterSync` / 通知 3 件の副作用が C/mock で模擬されない | 同上 (PY-125 の `REPORT_PY125` §4 と同じ未解決として扱う) |
