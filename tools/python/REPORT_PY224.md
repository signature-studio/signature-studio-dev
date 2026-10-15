# PY-224 (#3628): getGridBitWithLoop の loop 分岐 (PE 0x12d3ff0) を C provider と mock に実装

既知類型との関係: 該当なし (逆アセンブルの式を C と mock に写した照合。`docs/DEFECTS.md` の lift 欠陥類型には当たらない)。

## 結論

- loop 分岐の式を `provider/fl_engine.c` (`grid_bit_loop`) と `host/fl_mock.mjs` (`loopBit`) に実装した。`tests/channels_diff.mjs` は diffs 0 (loop 検査 9 ケース・position -1..127・件数以上の点を含む)。
- base は main の `grid_bit` / `gridBit` を使う。件数以上 (p >= 64) は PY-218 (#3657) の event 経路 (`grid_event` / `gridEvent`) に従い、範囲外を RANGE にしない (PE `0xd5b420` は範囲検査を持たない・`fl_engine.c` の `grid_bit` の注記)。
- 式は PE `0x12d3ff0` の逆アセンブルと 1 点ずつ照合した (下の表)。`REPORT_PY101` の読解と一致した。
- 行 `T[1]` の作成経路 (`0x12da6d0` の間接呼出し元・flag の書込み元) は PY-223 (#3627) の結果待ち。本 PR では検査用の注入 (`setLoop`・C は `fl_engine_loop_set` / `fl_engine_loop_add`) でしか行を置けない。既定は行なし (PE の `.bss` 0) で、loop 分岐に入らない。このため通常経路の値は変わらない。残りは子 #3659 (`[PY-229]`) に移した。
- 経緯: 当初の測定 commit は件数以上を RANGE にしていたため、main の #3601 (`651eb50cb`) と #3657 (`058984fa0`) と競合した。解消は merge commit `b3f90a545` (#3601)・`fc9525275` (#3657)。以後 main の取り込みを重ね、現在の測定 commit は `828c677e6` (main `ccea1a0df` の取り込み merge)。このとき `host/fl_mock.mjs` の `stepParam` が main の PY-111 (`STEP_V`・param 8) と競合したため、両方を残した。

## 式と実装の対応

PE は `analysis/flapi/pe_disasm.py 12d3ff0 90` の逆アセンブル (`FL_WIN64_DIR` 展開先の `block00031_PE.bin`)。

| PE (`0x12d3ff0`) | 実装 |
|---|---|
| `mov eax, [[grid+0x3b4]+0x794]` (cid) | `_i` (`CH(0)` の channel 索引)。根拠: `[grid+0x3b4]` は grid の所有 channel obj への back-pointer (`REPORT_PY101` の `0xff63f0`)、`[obj+0x794]` は channel 索引 (`REPORT_PY101` の `0xff5aa0`・`REPORT_PY112` の cid 読出し)。grid を問い合わせた channel `_i` の cid は `_i` |
| `[T + G1*192] == 0` で分岐なし (`je 0x12d40c6`) | `lp_row == 0` (行なし) |
| `[[[0x15e14a0]]+0x7e0] + 0x49e` の byte が 0 で分岐なし | `lp_flag49e == 0` |
| 20 byte の record を先頭から走査。`rec+0 == cid`・`rec+4 != 0`・`[obj+0x54] != 0` を満たす最初の rec | `lp_cid` / `lp_f4` / `lp_flag54` の走査 (最初の一致で止まる) |
| `L = [rec+8] / [G2]` (`cdq; idiv dword [r9]`・G2 = 静的 24) | `lp_len[r] / LP_G2` (`LP_G2 = 24`) |
| `L <= 0` または `p < L` (`cmp r8d, r9d; jl`) なら `base(p)` | `L <= 0 \|\| p < L` で `base` |
| それ以外は `base(p mod L)` (`idiv r9d` の余り)。`call 0x12d3e20; cmp eax, 1` で 1 なら 2・そうでなければ 0 | `grid_bit(p % L) ? 2 : 0` (bool 戻り値では True / False) |

- 戻り値は table 型 `bool` (`fl_ret_b`) に写る。`2` は True。`0xd5bc10` 側で int のまま callback に渡るという読解は #3628 本文のもの (本 REPORT では再確認していない)。型の確定は PY-217 (#3595) の未解決に残す。
- 基底の `0x12d3e20` の戻り値は `eax == 1` で比べられる。`grid_bit` / `grid_event` の戻り値は 0/1 のみなので、`? 2 : 0` は PE の `cmp eax,1` と同じ結果になる。
- 基底 `grid_bit` (C) / `gridBit` (mock) は件数以上 (p >= 64) を PY-218 の event 経路で読む。loop 分岐の base と `p mod L` の読出しも同じ関数を使う。

## 測定

- 測定 commit: `828c677e6` (main `ccea1a0df` の取り込み merge。コードを変えた最後の commit。競合は `host/fl_mock.mjs` の `stepParam` のみ。main の PY-111 (`STEP_V`・param 8) と本 PR の `loopBit` を両方残した)。
- 検証 HEAD: 本 REPORT の commit。コード範囲の差分 `git diff 828c677e6 HEAD -- tools/python/host tools/python/provider tools/python/tests` は 0 行 (本 REPORT の commit は範囲外)。
- 直前の測定 commit からの差分: `git diff a923a54db 828c677e6 -- tools/python/host tools/python/provider tools/python/tests` は 6 files・110 insertions・15 deletions (main の取り込み分と競合解消)。
- 変更の規模 (main `ccea1a0df` に対する正味): 7 files・211 insertions・6 deletions (`docs/DOC_MAP.md`・`REPORT_PY224.md`・`fl_engine.c`・`fl_mock.mjs`・`fl_provider.mjs`・`build.sh`・`channels_diff.mjs`)。`fl_engine.c` は `getGridBitWithLoop` の行の書換えのみで、新規のハンドラは追加していない (implemented の増減は main 由来)。
- 素材: `fl-win64` を `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C $RUNNER_TEMP/fl-win64` で全展開。`fetch_inputs.sh` は `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` で rc 0 (`work/midi.py`・`work/utils.py`・`work/fl-stubs` を生成)。emsdk は `[EMSDK]` (既定の `EMSDK_ENV`・`docs/REFERENCES.md` §4) をそのまま使用。
- flpy: `build_cpython_wasm.sh` rc 0 (04:10:34 → 04:14:39 の 245 秒)。`FLPY_SKIP_TABLE=1 build_flpy.sh` rc 0 (`flpy.wasm` 5,924,680 B。REPORT_PY101 と同じサイズ)。
- 負荷: 測定開始時の load average 1.38 / 1.62 / 0.85、測定終了時 1.83 / 1.71 / 0.89。node v22.23.3。

| 検査 (828c677e6) | コマンド | 結果 | 所要 |
|---|---|---|---|
| provider ビルド | `bash tools/python/provider/build.sh` | rc 0・関数 435・ハンドラ 165・警告 0 | 1,061 ms |
| channels 差分 (loop 検査と件数超え検査を含む) | `node tests/channels_diff.mjs` | calls 238・loop_cases 9・loop_event_true 51・diffs 0・grid_calls 1200・grid_true 30・grid_diffs 0・PASS | 79 ms |
| 実装数 | `node tests/provider_check.mjs` | functions 435・implemented 165・unimplemented 270・mcp_static 60・PASS | 352 ms |
| 全 tool | `FL_ENGINE=wasm node tests/all_tools.mjs` | total 48・ok 48・soft_error 0・raised 0・host_calls 37425・callback_roundtrip true・rc 0 | 1,612 ms |
| general 差分 | `node tests/general_diff.mjs` | calls 41・diffs 0・PASS | 52 ms |
| device 差分 | `node tests/device_diff.mjs` | calls 11・link_calls 6・rejects 4・midi_out 10・diffs 0・PASS | 55 ms |
| ui 状態差分 | `node tests/ui_state_diff.mjs` | calls 58・diffs 0・PASS | 55 ms |
| screen 差分 | `node tests/screen_diff.mjs` | calls 32・diffs 0・PASS | 56 ms |
| mixer 差分 | `node tests/mixer_diff.mjs` | calls 69・diffs 0・PASS | 55 ms |
| arrangement 差分 | `node tests/arrangement_diff.mjs` | calls 25・diffs 0・PASS | 52 ms |
| arrangement 選択差分 | `node tests/arrangement_selection_diff.mjs` | calls 8・diffs 0・PASS | 52 ms |
| ui 表示差分 | `node tests/ui_display_diff.mjs` | ok_calls 12・bad_calls 11・diffs 0・displayTime 2000・PASS | 53 ms |
| playlist 差分 | `node tests/playlist_diff.mjs` | calls 72・diffs 0・mock_state_steps 8・PASS | 56 ms |
| step item 差分 | `node tests/step_item_diff.mjs` | calls 5929・spot 5・diffs 0・PASS | 66 ms |

- 所要は `date` の差分 (node の起動を含む)。

### loop 検査の内容 (`tests/channels_diff.mjs`)

- channel 2 の steps を `[1,0,0,1,0,1,0,0]` にし、行 T[1] を 9 通り (行なし・flag 0 2 通り・cid 不一致・f4 0・L 0・L 3・先頭一致 (L 3 の後に L 5)・L 70) に置いて、`getGridBitWithLoop(2, p)` を p = -1..127 で mock と C に流す。
- 件数以上 (p >= 64) の経路を通すため、検査の間は `gridItemsProbe(1, 40)` で項目を入れる。`loop_event_true` 51 点で、件数以上の event 経路が真を返す点を含む (0 なら検査が空振り。assert で防ぐ)。L 70 の case は `L > p` (p 64..69) と `p mod L` (p >= 70) の両方を通す。
- 差分 0。`loop_moved_vs_base` (loop 結果が `getGridBit` と違う点の数): L 3 (len 72) は 43 点、先頭一致は 43 点、L 70 は 4 点。行なし・flag 0・cid 不一致・f4 0・L 0 は 0 点で、分岐が空振りしていないことが分かる。
- 数値の期待: L 3 で p=5 は `base(2) = 0` (base は 1)・p=6 は `base(0) = 1` (base は 0)。両側で `{ok:false}` と `{ok:true}` を assert する。
- 先頭一致と末尾一致の区別: `[[2,1,72],[2,1,120]]` (L 3 の後に L 5) で p=5 は false (先頭 L 3 なら `base(2)`・末尾 L 5 なら p<5 でなく `base(0) = 1` で true)、p=6 は true。両側で assert する。
- 上限: 9 件の `setLoop` は mock・wasm とも throw する (`上限 8`)。C は `fl_engine_loop_add` が上限超過で 0 を返し、JS の wrapper が throw する。

### ネガティブコントロール (828c677e6 と内容一致の作業ツリーで実施)

- mock の loop 分岐を無効化 (`fl_mock.mjs` の `loopBit` 先頭の `if (!st.loop.row || …) return base;` を `if (true || …)` に変更) → `channels_diff` は `AssertionError [ERR_ASSERTION]: mock loop p=5` で rc 1 (FAIL)。
- C の loop 分岐を無効化 (`fl_engine.c` の `grid_bit_loop` 先頭の `if (!lp_row || …) return base;` を `if (1 || …)`・`provider/build.sh` で再ビルド) → `AssertionError [ERR_ASSERTION]: wasm loop p=5` で rc 1 (FAIL)。
- 両方とも退避したファイルを `cmp` で戻し、再ビルドすると PASS (calls 238・loop_cases 9・diffs 0・grid_diffs 0)。

### 検査の補足

- `tests/provider_check.mjs` の implemented は 165 (main `ccea1a0df` の取り込みで a923a54db の 162 から増えた。main 側の追加ハンドラによる。本 PR は `FL_H` の追加を含まず、ハンドラの有無を変えていない)。REPORT_PY101 の 124 とは基底の main が違うため比べない。
- 件数超えの検査 (`gridRun`・PY-218) は main 由来で `channels_diff` の中央にある。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は対象外。

## 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 行 `T[1]` の `obj` を作る経路 (`0x12da6d0` の間接呼出し元)・flag `[[[0x15e14a0]]+0x7e0]+0x49e` の書込み元 | 起動時に loop 分岐へ入るかは未確定。現状は `setLoop` 注入でしか到達しない | 子 #3659 (`[PY-229]`)・前提 #3627 (PY-223) |
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
