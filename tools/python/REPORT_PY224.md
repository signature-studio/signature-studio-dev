# PY-224 (#3628): getGridBitWithLoop の loop 分岐 (PE 0x12d3ff0) を C provider と mock に実装

既知類型との関係: 該当なし (逆アセンブルの式を C と mock に写した照合。`docs/DEFECTS.md` の lift 欠陥類型には当たらない)。

## 結論

- loop 分岐の式を `provider/fl_engine.c` (`grid_bit_loop`) と `host/fl_mock.mjs` (`loopBit`) に実装した。`tests/channels_diff.mjs` は diffs 0 (loop 検査 8 ケース・全 position -1..63)。
- base は main の `grid_bit` / `gridBit` を使う。件数以上 (p >= 64) は PY-218 (#3657) の event 経路に従う。PR の測定 commit (`2da8e81d6`) は件数以上を RANGE にしていたため、main の #3601 と #3657 の 2 回と競合した。解消は merge commit `b3f90a545` (#3601)・`fc9525275` (#3657) で行った。main `c0fb6e074` の取り込みは競合なし (`5d62db1e4`)。
- 式は PE `0x12d3ff0` の逆アセンブルと 1 点ずつ照合した (下の表)。`REPORT_PY101` の読解と一致した。
- 行 `T[1]` の作成経路 (`0x12da6d0` の間接呼出し元・flag の書込み元) は PY-223 (#3627) の結果待ち。本 PR では検査用の注入 (`setLoop`・C は `fl_engine_loop_set` / `fl_engine_loop_add`) でしか行を置けない。既定は行なし (PE の `.bss` 0) で、loop 分岐に入らない。このため通常経路の値は変わらない。
- 残り (行の作成経路) は子 #3659 (`[PY-229]`) に移した。本 issue の範囲は縮めた。

## 式と実装の対応

PE は `analysis/flapi/pe_disasm.py 12d3ff0 90` の逆アセンブル (`FL_WIN64_DIR` 展開先の `block00031_PE.bin`)。

| PE (`0x12d3ff0`) | 実装 |
|---|---|
| `mov eax, [[grid+0x3b4]+0x794]` (cid) | `_i` (`CH(0)` の channel 索引) |
| `[T + G1*192] == 0` で分岐なし (`je 0x12d40c6`) | `lp_row == 0` (行なし) |
| `[[[0x15e14a0]]+0x7e0] + 0x49e` の byte が 0 で分岐なし | `lp_flag49e == 0` |
| 20 byte の record を先頭から走査。`rec+0 == cid`・`rec+4 != 0`・`[obj+0x54] != 0` を満たす最初の rec | `lp_cid` / `lp_f4` / `lp_flag54` の走査 (最初の一致で止まる) |
| `L = [rec+8] / [G2]` (`cdq; idiv dword [r9]`・G2 = 静的 24) | `lp_len[r] / LP_G2` (`LP_G2 = 24`) |
| `L <= 0` または `p < L` (`cmp r8d, r9d; jl`) なら `base(p)` | `L <= 0 \|\| p < L` で `base` |
| それ以外は `base(p mod L)` (`idiv r9d` の余り)。`call 0x12d3e20; cmp eax, 1` で 1 なら 2・そうでなければ 0 | `grid_bit(p % L) ? 2 : 0` (bool 戻り値では True / False) |

- 戻り値は table 型 `bool` (`fl_ret_b`) に写る。`2` は True。`0xd5bc10` 側で int のまま callback に渡るという読解は #3628 本文のもの (本 REPORT では再確認していない)。型の確定は PY-217 (#3595) の未解決に残す。
- 基底の `0x12d3e20` の戻り値は `eax == 1` で比べられる。mock と C の `steps` は `setGridBit` が 0 / 1 しか書かないため、値域の前提は一致する。
- 基底 `grid_bit` (C) / `gridBit` (mock) は件数以上 (p >= 64) を PY-218 の event 経路 (`grid_event` / `gridEvent`) で読む。loop 分岐の base と `p mod L` の読出しも同じ関数を使う。

## 測定

- 測定 commit: `5d62db1e4` (main `c0fb6e074` の取り込みの merge commit。コードを変えた最後の commit)。
- 検証 HEAD: 本 REPORT の commit。コード範囲の差分 `git diff 5d62db1e4 HEAD -- tools/python/host tools/python/provider tools/python/tests` の出力は 0 行 (本 REPORT の commit は範囲外)。
- 変更の規模 (main に対する正味): 5 files・89 insertions・6 deletions (`fl_engine.c`・`fl_mock.mjs`・`fl_provider.mjs`・`build.sh`・`channels_diff.mjs`)。
- 素材: `fl-win64` を `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C $RUNNER_TEMP/fl-win64` で全展開 (7.588 秒)。`fetch_inputs.sh` rc 0 (1.083 秒)。
- emsdk: runner に `[EMSDK]` が無かったため、上流 emsdk を取得して pin 6.0.12 を install した (20.273 秒)。`build_cpython_wasm.sh` は `[EMSDK]` の既定パスを直接 source するため、取得した emsdk をそのパスへ置いた。
- flpy: `build_cpython_wasm.sh` rc 0 (1 分 58.819 秒)。`FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0 (4.004 秒・`flpy.wasm` 5,924,680 B。REPORT_PY101 と同じサイズ)。flpy の入力 (`tools/python/src`・`build_flpy.sh`・`build_cpython_wasm.sh`・`fetch_inputs.sh`) は main `c0fb6e074` の取り込みで変わっていない (差分 0 行)。
- 環境: runner 4 core・node v22.23.3。測定開始時の `uptime` の load average 0.14 / 0.37 / 0.48 (03:28:11)。

| 検査 (5d62db1e4) | コマンド | 結果 | 所要 |
|---|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0・関数 435・ハンドラ 162・警告 0 | 764 ms |
| channels 差分 (loop 検査と件数超え検査を含む) | `node tests/channels_diff.mjs` | calls 214・loop_cases 8・diffs 0・grid_calls 1200・grid_true 30・grid_diffs 0・PASS | 51 ms |
| 実装数 | `node tests/provider_check.mjs` | functions 435・implemented 162・unimplemented 273・mcp_static 60・PASS | 241 ms |
| 全 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | total 48・ok 48・soft_error 0・raised 0・host_calls 37425・callback_roundtrip true・rc 0 | 1,118 ms |
| general 差分 | `node tests/general_diff.mjs` | calls 41・diffs 0・PASS | 37 ms |
| device 差分 | `node tests/device_diff.mjs` | calls 8・rejects 4・midi_out 5・diffs 0・PASS | 38 ms |
| ui 状態差分 | `node tests/ui_state_diff.mjs` | calls 33・diffs 0・PASS | 36 ms |
| screen 差分 | `node tests/screen_diff.mjs` | calls 32・diffs 0・PASS | 39 ms |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 62・diffs 0・PASS | 38 ms |
| arrangement 差分 | `node tests/arrangement_diff.mjs` | calls 25・diffs 0・PASS | 38 ms |
| arrangement 選択差分 | `node tests/arrangement_selection_diff.mjs` | calls 8・diffs 0・PASS | 37 ms |
| ui 表示差分 | `node tests/ui_display_diff.mjs` | ok_calls 12・bad_calls 11・diffs 0・displayTime 2000・PASS | 39 ms |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 72・diffs 0・mock_state_steps 8・PASS | 38 ms |
| step item 差分 | `node tests/step_item_diff.mjs` | calls 5929・spot 5・diffs 0・PASS | 43 ms |

- 所要は `date` の差分 (node の起動を含む)。

### loop 検査の内容 (`tests/channels_diff.mjs`)

- channel 2 の steps を `[1,0,0,1,0,1,0,0]` にし、行 T[1] を 8 通りに置いて、`getGridBitWithLoop(2, p)` を p = -1..63 で mock と C に流す。
- 差分 0 のほか、`loop_moved_vs_base` (loop 結果が `getGridBit` と違う点の数) を記録した。L 3 (`len` 72) の場合は 21 点で base と違う。行なし・flag 0・cid 不一致・f4 0・L 0 の場合は 0 点で、分岐が空振りしていないことが分かる。
- 数値の期待: L 3 で p=5 は `base(2) = 0` (base は 1)・p=6 は `base(0) = 1` (base は 0)。両側で `{ok:false}` と `{ok:true}` を assert する。
- loop 検査の p は -1..63 だけで、loop 有効時の p >= 64 は差分検査していない (未解決の表)。

### ネガティブコントロール (5d62db1e4 と内容一致の作業ツリーで実施)

- mock の loop 分岐を無効化 (`fl_mock.mjs` の `loopBit` 先頭の `if (!st.loop.row || …) return base;` を `if (true || …)` に変更) → `channels_diff` は `AssertionError: mock loop p=5` で rc 1 (FAIL)。
- C の loop 分岐を無効化 (`fl_engine.c` の `grid_bit_loop` 先頭の `if (!lp_row || …) return base;` を `if (1 || …)`・`provider/build.sh` で再ビルド) → `AssertionError: wasm loop p=5` で rc 1 (FAIL)。
- 両方とも退避したファイルを `cmp` で戻し、再ビルドすると PASS (calls 214・diffs 0・grid_diffs 0)。

### 検査の補足

- `tests/provider_check.mjs` の implemented は 162 (main `c0fb6e074` の取り込みで 155 から増えた。main 側の playlist・midinote のハンドラ追加による。本 PR はハンドラの有無を変えていない)。REPORT_PY101 の 124 とは基底の main が違うため比べない。
- `playlist_diff` の calls は 72 (main 側の検査の追加による。本 PR の変更とは無関係)。
- 件数超えの検査 (`gridRun`・PY-218) は main 由来で `channels_diff` の末尾にある。本 PR の loop 検査は p = -1..63 のみ。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は対象外。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 `T[1]` の `obj` を作る経路 (`0x12da6d0` の間接呼出し元)・flag `[[[0x15e14a0]]+0x7e0]+0x49e` の書込み元 | 起動時に loop 分岐へ入るかは未確定。現状は `setLoop` 注入でしか到達しない | 子 #3659 (`[PY-229]`)・前提 #3627 (PY-223) |
| loop 有効時の件数以上 (p >= 64) の差分検査 (loop 検査は p = -1..63 のみ) | loop 分岐で `p >= 64` を読む経路 (`L > p`・`p mod L`) は mock と C の差分が未検査 | 未起票 (本表で追跡。PY-218 は #3596 として #3657 で完了済み) |
| 戻り値 2 の callback での型 (bool か int) | 現状は table 型 bool で True に写る。PE は int のまま callback に渡す | #3595 (PY-217) |
| G1 (= 1) と G2 (= 24) の書込み元 | 静的初期値として扱った | #3595 (PY-217) |

## 範囲外

- `REPORT_PY101` の「loop 分岐は未モデル」の記述は、本 REPORT で式を実装したため古くなった。履歴として残し、本 PR では書き換えない。
- `useGlobalIndex = 1` の経路は未モデルのまま。

## 再現

- 素材: `mkdir -p $RUNNER_TEMP/fl-win64 && tar --zstd -xf <fl-win64>.tar.zst -C $RUNNER_TEMP/fl-win64`。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 逆アセンブル: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 12d3ff0 90`。
- flpy: `bash fetch_inputs.sh` → `bash build_cpython_wasm.sh` → `FLPY_SKIP_TABLE=1 bash build_flpy.sh` (`EMSDK_DIR` は `[EMSDK]`。`build_cpython_wasm.sh` は既定パスを直接 source する)。
- 検査: `bash provider/build.sh` → `node tests/channels_diff.mjs`・`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs`。
