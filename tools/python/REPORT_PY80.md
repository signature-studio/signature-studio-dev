# python 付録: PY-80 の残件 pthread + GIL (PY-97, #2856 / 親 #2633)

上流の `tools/python/REPORT_PY80.md` §4 は repo に存在しなかった (#2633 の PY-80 記録は `REPORT_PY2.md` §7d の未解決表だけ)。本ファイルを新設して #2856 の結果を置く。

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。検証は wasm の結果比較)。

測定 commit: **`a2926d53`** (コードを変えた最後の commit)。以降の commit は本ファイル・`docs/DOC_MAP.md`・`REPORT_PY2.md` の文書のみ。`git diff a2926d53 HEAD -- tools/python ':(exclude)*.md'` の出力は 0 行 (差分 0)。

## 1. 結論

- pthread 版 CPython (`--enable-wasm-pthreads`) を別 build dir に作り、静的版 `flpy_static_pthread` を `-pthread` でリンク: **rc 0** (HEAD で再現)。
- 単一スレッドの 48 tool 列は stock 静的版と **tool 別 0/48 差** (status・result・host_calls 合計 37,424 が一致)。
- 2 本のスレッド (48 tool 全て) と 4 本のスレッド (`get_session_context`・`get_mixer_routing`) から同時に tool を呼び、**全 104 本のスレッド結果の status・result が単一スレッドの基準と一致** (不一致 0)。
- 残件 (サブインタプリタ・`_PyInterpreterState_GetRefTotal`・Memory64・実 FLEngine 上の MT・C 側の負のコントロール) は §7 の未解決表。

## 2. 方式

| 項目 | 内容 |
|---|---|
| CPython | `CPY_PTHREADS=1 bash build_cpython_wasm.sh` → `work/build-wasm-pthread`。configure に `--enable-wasm-pthreads` (`CFLAGS -pthread`・`LDFLAGS -sUSE_PTHREADS`・`LINKFORSHARED -sPROXY_TO_PTHREAD`)。stock の `work/build-wasm` と LGL 記録 (`tools/legal/notices/records/cpython-3.12.1.json`) は変えない (pthread 版は記録を書かない) |
| 静的 wasm | `CPY_PTHREADS=1 bash build_flpy_static.sh` → `dist/flpy_static_pthread.{js,wasm,data}`。`flpy.c`・`pybind_resolve.c` を `-pthread -DFLPY_PTHREAD` でコンパイルし、リンクに `-pthread -sPTHREAD_POOL_SIZE=8`、export に `_flpy_mt_call` を追加 |
| 別スレッドからの実行 | `flpy.c` の `flpy_mt_call(n, target, args)` (`FLPY_STATIC && FLPY_PTHREAD` の時だけ有効)。main が `PyEval_SaveThread` で GIL を手放す → n 本の pthread が各自 `PyThreadState_New(interp)` → `PyEval_RestoreThread` → `flpy_call_json` → `PyThreadState_Clear` → `PyThreadState_DeleteCurrent` (GIL を返す) → main が `pthread_join` → `PyEval_RestoreThread`。戻り値は各スレッドの `call_json` 結果を並べた JSON 配列 |
| FL の束縛との関係 | `PyEval_SaveThread`・`PyEval_RestoreThread`・`PyThreadState_New` は FL が束縛する (`REPORT_PY2.md` §7d)。`PyThreadState_Swap` は本経路では直接使わない (RestoreThread が内部で行う) |
| テスト | `tests/static_mt_check.mjs` (新規)。(1) 単一スレッド 48 tool 列 (`static_check.mjs` と同順) を stock 静的版の記録 (`work/tool_coverage.flpy_static.json`) と突き合わせる。(2) tool ごとに `_fl_engine_reset` → 基準を 1 回 → reset → T 本同時。T=2 は 48 tool 全て、T=4 は重い 2 tool |

## 3. 実測 (測定 commit `a2926d53`、コミット済み HEAD で再現)

| 手順 | 結果 | 所要 | load (1 分平均、開始 → 終了) |
|---|---|---|---|
| `CPY_PTHREADS=1 bash build_cpython_wasm.sh` (`work/build-wasm-pthread` を `rm -rf` してから。native は既存を再利用) | rc 0 | 2 分 10 秒 | 0.54 → 2.64 |
| `bash build_cpython_wasm.sh` (stock、native 込みの初回。C1 時点) | rc 0 | 4 分 11 秒 | 0.73 → 3.17 (約) |
| `CPY_PTHREADS=1 bash build_flpy_static.sh` | rc 0。警告 1 件 `-Wpthreads-mem-growth` (下の §6) | 6.5 秒 | 2.23 |
| `bash build_flpy_static.sh` (stock、再リンク) | rc 0 | 6.0 秒 | 2.66 |
| `node tests/static_check.mjs` (stock 静的版) | `STATIC CHECK OK` (48/48、SAB 版と 0/48、mock と 0/48) | 0.395 秒 | 2.66 |
| `node tests/static_mt_check.mjs` (pthread 版) × 3 | `STATIC MT CHECK OK` × 3 | 1.073 / 1.080 / 1.057 秒 (プロセス全体)、MT 部 wall 518 / 527 / 531 ms | 2.25 |

結果の内訳 (`work/mt_check.flpy_static_pthread.json`):

| 項目 | 値 |
|---|---|
| (1) 単一スレッド列 vs stock 記録 | 48 tool、tool 別差 0/48、host_calls 合計 37,424 (`static_check` の tool 合計と一致) |
| (2) 2 スレッド | 48 tool × 2 本 = 96 呼出し。不一致 0 |
| (2) 4 スレッド | `get_session_context` (基準 18,056) と `get_mixer_routing` (基準 16,381) 各 4 本。不一致 0。host_calls 合計は 72,224 (= 18,056 × 4) と 65,524 (= 16,381 × 4) で、同じ初期状態から逐次に 4 回呼んだ合計と一致 |
| 行数 | 50 行 (48 + 重い 2 件の T=4)。スレッド結果 104 本中 104 本一致 |

比較元の SAB 版は `FL_ENGINE=wasm node tests/all_tools.mjs` で 48/48・host_calls 37,425 (rc 0、2.02 秒、`a2926d53` より前の同じ入力での実測。`flpy.wasm` は本 commit で変わっていない)。

## 4. 失敗から得た知見 (host_calls の期待値)

最初の実行では `open_piano_roll_for_channel` (T=2) の host_calls 合計が 31 で、期待値 `2 × 15 = 30` と FAIL した。reset 後に逐次 2 回呼んで確かめると、**1 回目は 15、2 回目は 16** (既に開いた piano roll をもう一度開く分岐)。並行実行の取りこぼしではなく、tool の状態依存だった。結果文字列と status は全スレッドで一致していた。

テストの期待値を「同じ初期状態から逐次に T 回呼んだ合計」に直した (修正後: 31 = 31)。修正前の式は `T × 基準` で、この失敗は commit 前の作業中に出たもの (commit 済みのテストは修正後の式)。

## 5. 負のコントロール

- 比較ロジックが実際に失敗を出すか: `tests/static_mt_check.mjs` の基準 (`ref.text`) に `"!"` を足した一時コピーを実行 → `STATIC MT CHECK FAIL (50)`、rc 1 (50 行すべてが不一致として検出)。一時ファイルは削除済み。
- 未実施: C 側の変異 (スレッド側で `PyEval_RestoreThread` を外す等)。GIL の取り損ねが検出されるかは未確認 (§7)。

## 6. 検証範囲 / 範囲外

- 範囲: node の main スレッドと pthread worker 上の静的 pthread 版。FL 本体・実 FLEngine・AudioWorklet は対象外 (AudioWorklet からは呼ばない方針は `BRIDGE.md` §7)。
- GIL の交互実行 (実際に切り替わった回数) は未計測。結果一致は「どの順で動いても同じ結果」を示すが、切替の頻度は示さない。
- `ALLOW_MEMORY_GROWTH` と pthread の組合せで `-Wpthreads-mem-growth` (「非 wasm コードが遅くなり得る」) の警告が出る。性能への影響は未計測。`-sGROWABLE_ARRAYBUFFERS` は試していない。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| サブインタプリタ (`Py_NewInterpreterFromConfig`) の静的 pthread 版での動作 | FL がサブインタプリタ運用なら MIDI・piano roll の分離に影響 | 親 #2633 に残す (PY-80 の残件) |
| `_PyInterpreterState_GetRefTotal` を FL が使うか | 使うなら release build で束縛が失敗 (FL 側の挙動は未確認) | 親 #2633 に残す |
| Memory64 でのリンク (pthread 版を含む) | wasm32 決定 (#25) の退避路。未検証 | 親 #2633 に残す (`BRIDGE.md` §7) |
| 実 FLEngine wasm 上の MT 呼出し | 本節は provider の最小エンジン状態での結果 | 子 #2631 (PY-79) |
| C 側の負のコントロール (GIL 取り損ねの検出) と GIL 切替の計測 | 並行性の証拠の強さ (現状は結果一致のみ) | 親 #2633 に残す |
| `-Wpthreads-mem-growth` の性能影響 | 性能のみ (未計測) | 親 #2633 に残す |
