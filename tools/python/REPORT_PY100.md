# PY-100 (#2879): channels.getStepParam / getCurrentStepParam の PE 確定と実装

親: #2808 (PY-90)。前段: `REPORT_PY41_1514.md` (本件を #2808 へ分割した根拠)、`REPORT_PY39_2548.md` (setStepParameterByIndex 側の共通経路 0xd5b930)。
本ファイルは PY-100 の run の実測のみ。全体の要約は `REPORT.md`。

## 結論

1. 2 関数の PyArg 書式・kwlist・既定値・エラー経路を PE で確定した (getStepParam = 5 引数、getCurrentStepParam = 4 引数)。stub (6 引数 / useGlobalIndex) とは binary が違う。
2. 共通読出し 0xd5b930 の param → 構造体 offset の写像 (0〜8) を確定した。範囲外と構造体無しは -1。
3. `[global]` (getStepParam の pat / getCurrentStepParam の pat) は **現在のパターン番号**。`patternNumber()` (0xd64d20) と同じ slot を読むことを PE で確認した。
4. C provider と mock に実装した。構造体 = grid bit が 1 の step とみなし、既定値は stub 順。`channels_diff` diffs 0 (呼出し数は §11)、provider 実装 77 → 79、`all_tools` (wasm) 48/48。
5. **未確定**: 構造体の生成経路 (note をどこで作るか) と既定値 (60/100/64/120/64/64/64/0) の PE 確認、param 8 (+0x11) の既定値。子 #2929 ([PY-111]) に分けた (§8)。

## 1. 書式と引数 (PE 実測。再現: `analysis/flapi/pe_step_param.py`)

| 関数 | VA | PyArg 書式 | kwlist (PE の文字列) | 既定値 | stub (REPORT_PY32) との差 |
|---|---|---|---|---|---|
| getStepParam | 0xd5ba00 | `iiii\|i` | step, param, offset, startPos, padsStride | padsStride = 16 (`mov [rbp+0x5c],0x10` @0xd5ba09) | stub の 3 番目 `index` が binary では `offset`。stub の 6 番目 `useGlobalIndex` は binary に無い |
| getCurrentStepParam | 0xd5bb30 | `iii\|i` | index, step, param, useGlobalIndex | useGlobalIndex = 0 (`mov [rbp+0x48],0` @0xd5bb38) | stub と一致 |

- `provider/gen/fl_table.c` の行 61 (getStepParam) は stub 由来の np=6 のまま。handler で `NARGS(4, 5)` とし、6 引数は binary と同じく TypeError (code 5)。表の再生成は `gen_provider.py` の別作業 (§8)。

## 2. 呼出し経路 (PE 実測)

**getStepParam (0xd5ba00)**
1. 引数解析に失敗すると `0xd5baf4` から `0xd82c20` へ進み、PyArg の例外に従って戻る (`0xd82c20` の status 0 の分岐は未読)。
2. `padsStride == 0` → status -3 (`Range error`、FL code 4)。(0xd5ba66〜0xd5ba71)
3. `q = step / padsStride` (idiv・切り捨て)、`idx = q + offset`。`idx` が `[0, 件数-1]` の外なら status -4 (`Index out of range`)。件数は `[[0x15e0128]+0x10]`。(0xd5ba7b〜0xd5baae)
4. `chanId = [list[idx] + 0x794]`。
5. `0xd5b930(chanId, [slot], pos = step - q*padsStride + startPos, param)`。

**getCurrentStepParam (0xd5bb30)**
1. 引数解析。
2. `0x1005730(index, useGlobalIndex > 0, &obj)` が偽なら status -4。(0xd5bb96〜0xd5bb9d)
3. `chanId = [obj + 0x794]`、`0xd5b930(chanId, [slot], step, param)`。

値の返し方: `0xd5b930` が -1 を返せば Python 側には -1 が値として返る (例外ではない。0xd5b93d〜0xd5b942 の `or eax,-1`)。status -3 / -4 は例外経路 (`0xd82c20`)。

## 3. 共通読出し 0xd5b930 の param 写像 (PE 実測)

| param | 構造体 field | 型 (読出し) | 既定値 (stub 順) | 書込み側の clamp (REPORT_PY39_2548 の PE) | 状態 |
|---|---|---|---|---|---|
| 0 | +0xc | word・符号付き | 60 | (未読) | 既定値は stub 由来。PE 未確認 |
| 1 | +0x15 | byte | 100 | (未読) | 同上 |
| 2 | +0x12 | byte | 64 | (未読) | 同上 |
| 3 | +0x10 | byte | 120 | [0, 0xf0] | 同上 |
| 4 | +0x14 | byte | 64 | [0, 0x80] | 同上 |
| 5 | +0x16 | byte | 64 | [0, 0xff] | 同上 |
| 6 | +0x17 | byte | 64 | [0, 0xff] | 同上 |
| 7 | +0x0 | dword | 0 | (clamp 無し) | 同上 |
| 8 | +0x11 | byte | (未確定) | (書込み `low8(value)`・REPORT_PY39_2548) | **未モデル。本実装は -1** |
| その他 | — | — | — | — | -1 (PE: `or eax,-1`) |

0xd5b930 の先頭で `0x130f1e0` が NULL を返すと -1 (0xd5b93d〜0xd5b942)。構造体が無い step も -1。

## 4. 構造体 (note) の検索 (PE 実測。生成経路は未読)

- `0x130f1e0(chanId, pat, pos)` は `pos * A` を作って `0x130f060(chanId, pat, pos*A)` を呼ぶ薄い wrapper。`A` は slot `0x15e25f8` が指す dword。`0x130f1e0`・`0x130f060` 内の乗除・加算 (5 箇所) はすべて同じ slot を読む。`A` の実行時値は静的に読めない (ヒープ上の値と推定)。
- `0x130f060` の流れ:
  1. チャンネル列 (slot `0x15e2218`) を走査し `+0x794 == chanId` の添字 `r14` を求める (無ければ件数)。
  2. `r14` が `[0, 件数-1]`、`pat` が `[0, 998]` (`0x3e6`)、パターン表 (要素 24 バイト・slot `0x15e2aa0`) の `pat` の要素の `+0x28` が非 NULL。どれかに反すると NULL。
  3. `0x12df320(container, &cursor, tick + A)` を反復。`0x12df320` は「開始位置 (dword +0) が `tick + A` 未満の要素を順に返す」反復子 (0x12df320〜0x12df34a)。
  4. 要素の `+6` (word) が `chanId` と一致し、`tick` が `[snap(start), max(f(要素), snap + A - 1)]` に入ると採用。`snap(start) = floor(start / A) * A`、`f = 0x105f2e0` (未読)。
- 対応: 「構造体 = そのチャンネルの、step セルに掛かる note」。mock の grid bit (1 step の note とみなす) は、note 長が 1 step の場合だけ一致する。note 長 (`f`) と `A` の値は未確認。

## 4b. 参照先の一致 (`[global]` = 現在のパターン番号)

| 参照元 | 読む slot (計算値) | 備考 |
|---|---|---|
| getStepParam (0xd5bace の RIP 相対) | 0x15e4018 | `mov edx,[*slot]` を 0xd5b930 の第 2 引数へ |
| getCurrentStepParam (0xd5bbb0) | 0x15e4018 | 同上 |
| patternNumber() (0xd64d20 が読む slot) | 0x15e4018 | `int` を返す。PY-42 の「グローバル変数の int」 |

- 3 参照が同一 slot なので、`[global]` は `patternNumber()` と同じ値 (現在のパターン番号)。`0x130f060` が `[0, 998]` を検査し、パターン表の添字に使うのと整合する。
- 注 (未確認): getStepParam の件数付き列 (slot `0x15e0128`) は要素の `+0x794` を chanId とみなすが、`0x130f060` が走査する列 (`0x15e2218`) と別 slot。同一配列かは未確認。
- 計算の根拠: RIP 相対 `next_ip + disp` (`pe_step_param.py`)。

## 5. 実装 (C provider と mock)

- `provider/fl_engine.c`: `step_param` (構造体 = `steps[pos]` が 1、param 0〜7 は既定値、それ以外 -1) と 2 handler。
- `host/fl_mock.mjs`: `stepParam` と 2 impl。C と同じ検査順 (引数解析 → padsStride 0 → index)。
- 未モデル (両方に共通):
  - pattern 次元: mock は単一パターン。`pat` (`[global]`) は見ない。
  - `useGlobalIndex` (0x1005730 の group 配列 A/B): group 無し (既存関数と同じ扱い)。
  - param 8: 既定値未確定のため -1。
  - 構造体の生成条件: grid bit が 1 の step を構造体ありとみなす (推定。生成経路は未読)。
  - 既定値 (60/100/64/120/64/64/64/0): stub 由来。PE の生成経路で確認するまで実装の根拠は stub のみ。

## 6. 検証 (HEAD `ff2d288f`。コードを変えた最後の commit)

| 検査 | コマンド (`tools/python` で実行) | 結果 | 所要 |
|---|---|---|---|
| provider の build | `bash provider/build.sh` | rc 0 (emcc キャッシュ済み) | 0.92 秒 |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 79・unimplemented 356) | 0.353 秒 |
| C と mock の差分 | `node tests/channels_diff.mjs` | PASS (calls 145・diffs 0) | 0.049 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425) | 2.064 秒 |

- 作業用の素材と wasm (gitignore): `fl-win64` の PE と DATA 4 本 (`block24429`・`block24430`・`block25159`・`block24618`) を `$RUNNER_TEMP/fl-win64` に展開 (2.8 秒)。`toolchain-emsdk` を展開 (3.4 秒)。`fetch_inputs.sh` は 0.27 秒。CPython wasm は `build_cpython_wasm.sh` で 4 分 8.6 秒 (rc 0)、`FLPY_SKIP_TABLE=1 build_flpy.sh` は 6.3 秒 (rc 0)。
- 負荷: 計測直前 `uptime` で load average 0.27 / 1.18 / 0.81 (nproc 4)。
- 追加の PE 再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_step_param.py` は assert 通過 (書式・kwlist・slot 3 件の同一性)。
- ネガティブコントロール: mock の `STEP_DEF[3]` を 120 → 121 に変えると `channels_diff` は差分 1 件で rc 1 (FAIL)。戻すと PASS (145 呼出し・diffs 0)。
- 差分 0 の証跡: `git diff ff2d288f HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0` (測定 commit 以降のコードは無変更。以後の commit は `tools/python/REPORT_PY100.md` と `docs/DOC_MAP.md` のみ)。
- 検証範囲: 実 FLEngine (wasm) の戻り値との比較はしていない。C provider と mock の一致、PE 実測の書式・経路・slot の一致のみ。範囲外: 実機での既定値・note 生成・pattern 別の値。

## 7. 受入条件の状態 (#2879)

- [x] 書式・kwlist・既定値・エラー経路を PE で確定し、ABI を決めた (§1・§2)。
- [x] `[global]` が現在のパターン番号であることの確認 (§4b。slot 同一)。
- [x] 決めた ABI で `provider/fl_engine.c` と `host/fl_mock.mjs` に実装、`channels_diff` diffs 0 (§6)。
- [x] `provider_check` の件数更新 (77 → 79)。
- [x] `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 ok (§6)。

移管 (本文から除く・§8): 構造体 (note) の生成経路と既定値の PE 照合、param 8 → #2929 (PY-111)。検索条件 (note の chanId・pattern・step セル) は §4 で確定済み。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 構造体 (note) の生成経路 (setGridBit・fillEachNSteps 等がどの関数で note を作るか) と既定値 60/100/64/120/64/64/64/0 の PE 照合 | 既定値が stub 由来のまま。grid bit モデルの根拠が推定 | 子 #2929 ([PY-111]) |
| param 8 (+0x11) の既定値と意味 | param 8 は -1 固定 | #2929 ([PY-111]) |
| `f = 0x105f2e0` (note の終端) と `A` (tick / step) の値 | note 長 1 step 以外の検索結果が未確定 | #2929 ([PY-111]) |
| pattern 次元 (pat 別の note 保持) | mock は単一パターン | #2808 (PY-90) 系の pattern 作業 |
| `fl_table.c` 行 61 の np=6 (stub 由来) | handler の NARGS で吸収。表の再生成は `gen_provider.py` の作業 | 子 #2929 ([PY-111]) |
| useGlobalIndex (group 配列 A/B) | group 無しでは未モデル | #2808 (PY-90)。#2805 (PY-89) は CLOSED のため、ここへ移した (`親: #2808` の本文を持つ子は起票しない) |

## 9. main 取り込み後の再測定 (競合解消。測定 commit `9d49d429`)

- 経緯: PR ブランチ (HEAD `1872d54f`) が main (`04f4dca9`) と競合したため、`git merge origin/main` で解消した (rebase なし)。競合は 3 ファイル。
  - `tools/python/host/fl_mock.mjs`: 本 PR の `getStepParam`・`getCurrentStepParam` と main の `getChannelIndex`・`getChannelMidiInPort` (PY-89) の両方を残した。
  - `tools/python/tests/channels_diff.mjs`: 呼出し列を両方残した (本 PR 側 + main 側 15 件。呼出し 145 → 160)。
  - `tools/python/tests/provider_check.mjs`: 期待集合 `pe100` (本 PR) と `stub89` (main) を両方入れ、期待値を実装 79 → 81・未実装 356 → 354 に直した。
  - `tools/python/provider/fl_engine.c` は自動マージ。両方の関数が残り、重複は無い。
- 入力: fl-win64 の PE と DATA 4 本を `$RUNNER_TEMP/fl-win64` に展開し、`fetch_inputs.sh` で `work/` に配置した。CPython wasm は `build_cpython_wasm.sh` ([EMSDK]、emcc 6.0.12)。

| 検査 | コマンド (`tools/python` で実行) | 結果 | 所要 |
|---|---|---|---|
| provider build | `EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash provider/build.sh` | rc 0 | 11.505 秒 (sysroot キャッシュ生成を含む) |
| CPython wasm | `bash build_cpython_wasm.sh` | rc 0 | 3 分 18.656 秒 |
| flpy link | `FLPY_SKIP_TABLE=1 FL_WIN64_DIR=<展開先> bash build_flpy.sh` | rc 0 | 4.747 秒 |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 81・unimplemented 354) | 0.278 秒 |
| C と mock の差分 | `node tests/channels_diff.mjs` | PASS (calls 160・diffs 0) | 0.040 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425) | 1.280 秒 |
| 48 tool (mock) | `node tests/all_tools.mjs` | 48/48 ok (host_calls 37425) | 1.258 秒 |
| MIDI device 照合 | `node tests/device_diff.mjs` | PASS (calls 7・diffs 0) | 0.038 秒 |

- 計測直前 `uptime` の load average 1.19 / 1.44 / 0.79 (nproc 4)。検証範囲は §6 と同じ (実 FLEngine の値とは比較していない)。
- 差分: `git diff 9d49d429 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0`。本 commit は `tools/python/REPORT_PY100.md` だけを変える。

## 10. main 再取り込み後の再測定 (測定 commit `bf653917`・旧。最新は §11)

- 経緯: main が `eec639a3` (#2971 ほか) へ進み、PR ブランチ HEAD `48b950c1` と再び競合した。`git merge origin/main` で解消した (rebase なし)。
  - `tools/python/tests/provider_check.mjs` のみ競合 (2 箇所)。期待集合 `pe100` (本 PR) と `pe87` (main・PY-87 #2738 の general ゲッター 4 件) を両方残し、期待値を実装 81 → 85・未実装 354 → 350 に直した (`functions` 435 は不変)。
  - `fl_engine.c`・`fl_mock.mjs`・`channels_diff.mjs` は自動マージ。
- 検証の差: main 側で `channels_diff.mjs` に `channels.soloChannel` の呼出しが 1 件、`device_diff.mjs` の `device.midiOutMsg` に 6 個目の引数の検査が入った (`git diff 48b950c1 bf653917 -- tools/python/tests`)。そのため呼出し数は 160 → 161、device 照合は 7 → 8 (rejects 4)。
- 入力: fl-win64 の PE (`block00031_PE.bin`) と DATA 4 本だけを `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf ... --wildcards`、3.7 秒)。emsdk は `[EMSDK]` (emcc 6.0.12) を使った。`fetch_inputs.sh` は `FL_WIN64_DIR` 指定で実行。

| 検査 | コマンド (`tools/python` で実行) | 結果 | 所要 |
|---|---|---|---|
| provider build | `bash provider/build.sh` | rc 0 | 1.348 秒 |
| CPython wasm | `bash build_cpython_wasm.sh` | rc 0 | 4 分 14.958 秒 |
| flpy link | `FLPY_SKIP_TABLE=1 FL_WIN64_DIR=<展開先> bash build_flpy.sh` | rc 0 | 6.303 秒 |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 85・unimplemented 350・mcp_static 60) | 0.565 秒 |
| C と mock の差分 | `node tests/channels_diff.mjs` | PASS (calls 161・diffs 0) | 0.053 秒 |
| general 照合 (PY-87) | `node tests/general_diff.mjs` | PASS (calls 9・diffs 0) | 0.047 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425) | 2.215 秒 |
| 48 tool (mock) | `node tests/all_tools.mjs` | 48/48 ok (host_calls 37425) | 2.117 秒 |
| MIDI device 照合 | `node tests/device_diff.mjs` | PASS (calls 8・rejects 4・midi_out 5・diffs 0) | 0.052 秒 |

- 計測直前 `uptime` の load average 2.59 / 1.89 / 0.89 (nproc 4)。build 開始時は 0.57 / 0.38 / 0.16。
- 差分: `git diff bf653917 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0`。本 commit は `tools/python/REPORT_PY100.md` だけを変える。
- 検証は実 FLEngine との比較ではない (§6 と同じ範囲)。

## 11. main 再々取り込み後の再測定 (測定 commit `4c60dace`)

- 経緯: main が `798bbb67` (#2962 ほか) へ進み、PR ブランチ HEAD `b3833446` と再び競合した。`git merge origin/main` で解消した (rebase なし)。
  - `tools/python/tests/provider_check.mjs` のみ競合 (1 箇所)。main 側は PY-115 (#2951) の `pe115` (`mixer.getTrackColor`) を追加していた。期待集合 `pe100` (本 PR)・`pe87` (PY-87)・`pe115` (PY-115) の 3 つを残し、期待値を実装 85 → 86・未実装 350 → 349 に直した (`functions` 435 は不変)。
  - `fl_engine.c`・`fl_mock.mjs` は自動マージ。
- 入力: §10 と同じ fl-win64 の展開 (PE と DATA 4 本)。emsdk は `[EMSDK]`。`build_cpython_wasm.sh` は既存の `work/` ビルドを再利用した増分 (0.949 秒。初回の 4 分 14.958 秒は §10)。

| 検査 | コマンド (`tools/python` で実行) | 結果 | 所要 |
|---|---|---|---|
| provider build | `bash provider/build.sh` | rc 0 | 0.931 秒 |
| CPython wasm | `bash build_cpython_wasm.sh` | rc 0 (増分) | 0.949 秒 |
| flpy link | `FLPY_SKIP_TABLE=1 FL_WIN64_DIR=<展開先> bash build_flpy.sh` | rc 0 | 6.095 秒 |
| 件数・ABI | `node tests/provider_check.mjs` | PASS (functions 435・implemented 86・unimplemented 349・mcp_static 60) | 0.370 秒 |
| C と mock の差分 | `node tests/channels_diff.mjs` | PASS (calls 161・diffs 0) | 0.054 秒 |
| general 照合 (PY-87) | `node tests/general_diff.mjs` | PASS (calls 9・diffs 0) | 0.049 秒 |
| mixer 照合 | `node tests/mixer_diff.mjs` | PASS (calls 57・diffs 0) | 0.051 秒 |
| 48 tool (wasm) | `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok (soft_error 0・raised 0・host_calls 37425) | 2.153 秒 |
| 48 tool (mock) | `node tests/all_tools.mjs` | 48/48 ok (host_calls 37425) | 2.156 秒 |
| MIDI device 照合 | `node tests/device_diff.mjs` | PASS (calls 8・rejects 4・midi_out 5・diffs 0) | 0.050 秒 |

- 計測直前 `uptime` の load average 0.67 / 1.21 / 0.79 (nproc 4)。
- 差分: `git diff 4c60dace HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `0`。以後 (review round 2 の doc 修正) の commit は `tools/python/REPORT_PY100.md` と `docs/DOC_MAP.md` だけを変える。
- 検証は実 FLEngine との比較ではない (§6 と同じ範囲)。
