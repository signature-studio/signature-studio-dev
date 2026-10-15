# python 付録: PY-80 の残件 pthread + GIL (PY-97, #2856 / 親 #2633)

`tools/python/REPORT_PY80.md` (#2633) §4 の未解決 (pthread + GIL) を子 #2856 (PY-97) に分割した、その子の結果を置く。#2633 の記録は `REPORT_PY80.md` に残す。

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。検証は wasm の結果比較)。

測定 commit: **`a2926d53`** (§3 の数値を測った最後の commit)。以降の commit で `src/flpy.c` と `tests/static_mt_check.mjs` を変えた (§8)。このため §3 の数値は現 HEAD のものではない (未再測定。理由は §8)。

## 1. 結論

- pthread 版 CPython (`--enable-wasm-pthreads`) を別 build dir に作り、静的版 `flpy_static_pthread` を `-pthread` でリンク: **rc 0** (`a2926d53` で再現)。
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

## 3. 実測 (測定 commit `a2926d53`。main 取り込み後の再測定は §9)

| 手順 | 結果 | 所要 | load (1 分平均、開始 → 終了) |
|---|---|---|---|
| `CPY_PTHREADS=1 bash build_cpython_wasm.sh` (`work/build-wasm-pthread` を `rm -rf` してから。native は既存を再利用) | rc 0 | 2 分 10 秒 | 0.54 → 2.64 |
| `bash build_cpython_wasm.sh` (stock、native 込みの初回) | rc 0 | 4 分 11 秒 | 0.73 → 3.17 |
| `CPY_PTHREADS=1 bash build_flpy_static.sh` | rc 0。警告 1 件 `-Wpthreads-mem-growth` (下の §6) | 6.5 秒 | 2.23 |
| `bash build_flpy_static.sh` (stock、再リンク) | rc 0 | 6.0 秒 | 2.66 |
| `node tests/static_check.mjs` (stock 静的版) | `STATIC CHECK OK` (48/48、SAB 版と 0/48、mock と 0/48) | 0.395 秒 | 2.66 |
| `node tests/static_mt_check.mjs` (pthread 版) × 3 | `STATIC MT CHECK OK` × 3 | 1.073 / 1.080 / 1.057 秒 (プロセス全体)、MT 部 wall 518 / 527 / 531 ms | 2.25 |

結果の内訳 (`work/mt_check.flpy_static_pthread.json`):

| 項目 | 値 |
|---|---|
| (1) 単一スレッド列 vs stock 記録 | 48 tool、tool 別差 0/48、host_calls 合計 37,424 (`static_check` の tool 合計 `host_calls_tools_sum` と一致) |
| (2) 2 スレッド | 48 tool × 2 本 = 96 呼出し。不一致 0 |
| (2) 4 スレッド | `get_session_context` (基準 18,056) と `get_mixer_routing` (基準 16,381) 各 4 本。不一致 0。host_calls 合計は 72,224 (= 18,056 × 4) と 65,524 (= 16,381 × 4) で、同じ初期状態から逐次に 4 回呼んだ合計と一致 |
| 行数 | 50 行 (48 + 重い 2 件の T=4)。スレッド結果 104 本中 104 本一致 |

比較元の SAB 版は `FL_ENGINE=wasm node tests/all_tools.mjs` で 48/48・host_calls 37,425 (rc 0、2.02 秒、`a2926d53` より前の同じ入力での実測。`flpy.wasm` は本 commit で変わっていない)。tool 別合計 37,424 との 1 件差は、`static_check.mjs` が tool 集計の後に highlight callback を 1 回往復させ、その 1 件を `hostCallsAfterTools` (summary) 側だけで数えるため。

## 4. 失敗から得た知見 (host_calls の期待値)

最初の実行では `open_piano_roll_for_channel` (T=2) の host_calls 合計が 31 で、期待値 `2 × 15 = 30` と FAIL した。reset 後に逐次 2 回呼んで確かめると、**1 回目は 15、2 回目は 16** (既に開いた piano roll をもう一度開く分岐)。並行実行の取りこぼしではなく、tool の状態依存だった。結果文字列と status は全スレッドで一致していた。

テストの期待値を「同じ初期状態から逐次に T 回呼んだ合計」に直した (修正後: 31 = 31)。修正前の式は `T × 基準` で、この失敗は commit 前の作業中に出たもの (commit 済みのテストは修正後の式)。

再現 (fix で追加した引数モード。先に `CPY_PTHREADS=1 bash build_cpython_wasm.sh && CPY_PTHREADS=1 bash build_flpy_static.sh` を済ませておく):

```
node tests/static_mt_check.mjs open_piano_roll_for_channel
```

reset → 同じ tool を逐次 2 回 → 各回の status・host_calls を JSON で出す。期待値は `calls[0].host_calls` = 15、`calls[1].host_calls` = 16。**本 fix 時点では未実行** (toolchain-emsdk 素材が本 run に無く wasm を作れない。§8)。

## 5. 負のコントロール

- 比較ロジックが実際に失敗を出すか: `tests/static_mt_check.mjs` の基準 (`ref.text`) に `"!"` を足した一時コピーを実行 → `STATIC MT CHECK FAIL (50)`、rc 1 (50 行すべてが不一致として検出)。`a2926d53` 時点の実測。一時ファイルは削除済み。
  - 再現 (1 行): `sed 's/const ref = full(\(.*\));$/const ref = ((r) => ({ ...r, text: r.text + "!" }))(full(\1));/' tests/static_mt_check.mjs > tests/_neg_mt.mjs && node tests/_neg_mt.mjs; rm -f tests/_neg_mt.mjs`
  - 制限: この control は基準を全行で壊すため、比較が行われ不一致が数えられることの確認 (配線) にはなるが、「1 行だけ壊して 1 行だけ FAIL」は確認していない。1 行だけ壊す control は未実施 (§7)。上の再現コマンドは fix 後に未実行。
- 未実施: C 側の変異 (スレッド側で `PyEval_RestoreThread` を外す等)。GIL の取り損ねが検出されるかは未確認 (§7)。

## 6. 検証範囲 / 範囲外

- 範囲: node の main スレッドと pthread worker 上の静的 pthread 版。FL 本体・実 FLEngine・AudioWorklet は対象外 (AudioWorklet からは呼ばない方針は `BRIDGE.md` §7)。
- 比較の範囲: (2) の並行呼出しは基準と**全文**で比べる (fix で変更。`a2926d53` は先頭 160 字だった)。(1) は stock 記録 (`static_check.mjs` が先頭 160 字で保存する形式) と同じ 160 字で比べる。
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
| 1 行だけ壊す負のコントロール (§5 の制限) | 「1 件だけ FAIL」の確認なし | 親 #2633 に残す |
| `-Wpthreads-mem-growth` の性能影響 | 性能のみ (未計測) | 親 #2633 に残す |
| CPython wasm ビルドの所要 (§9) | §9 の再測定でビルドの所要を記録しなかった (完了時刻だけ) | 追加起票なし (注記) |

## 8. fix (PR #2901 の差し戻し対応)

- `src/flpy.c` `flpy_mt_call`: `strdup` と `malloc` の戻り値を検査していなかった。修正後は、`pthread_create` 失敗と `strdup` 失敗 (out が NULL) のスレッドには代用の `{"err":"thread result missing"}` を並べる (`strdup` の代わりに定数を使う)。`buf` の `malloc` が NULL なら確保済みの out を解放して NULL を返す。JS 側 `mtCall` は NULL を例外にする。
- `tests/static_mt_check.mjs`: (2) の比較を全文 (`full`) に変えた。引数 `<tool>` で §4 の再現モード (reset → 逐次 2 回) を追加。
- 検証 (本 run): 手元の gcc (`-std=gnu11 -Wall -Wextra`、Python 3.12 の system headers、`EMSCRIPTEN_KEEPALIVE` だけ空定義の stub) で `src/flpy.c` の構文チェック rc 0 (修正前後とも、警告 0)。`node --check tests/static_mt_check.mjs` rc 0。
- 未実施: `build_cpython_wasm.sh`・`build_flpy_static.sh` の再ビルドと、`static_check.mjs`・`static_mt_check.mjs` の再実行。本 run には `toolchain-emsdk` ([EMSDK]) の素材が無く、wasm を作れなかった。次の review run で `oc_artifacts: fl-win64 toolchain-emsdk` により独立に再実行する。
- 測定 commit `a2926d53` から fix commit までのコード差分 (`git diff --stat a2926d53 HEAD -- tools/python ':(exclude)*.md'`):

```
 tools/python/src/flpy.c                | 18 +++++++++++++-----
 tools/python/tests/static_mt_check.mjs | 22 ++++++++++++++++------
 2 files changed, 29 insertions(+), 11 deletions(-)
```

## 9. main 取り込み後の再測定 (merge `c1b3204c`)

- 測定 commit: **`c1b3204c`** (`origin/main` `8a2c6370` を取り込んだ merge commit)。以降の commit は本節を含む文書だけ (§9 末尾の差分 0 行の確認)。
- 競合の解消 (3 件): `build_flpy_static.sh` は `CPY_PTHREADS` (本 PR) と main の `CPY_BUILD`・`FLPY_MEMORY64` (`MEM64` 配列)・`_flpy_subinterp_run` の export を両立させた (main の変更は全て残す)。`REPORT_PY80.md` は main 側 (#2633 の報告、93 行) をそのまま残し、本 PR の報告を本ファイルへ移した。参照先を追従させた: `docs/DOC_MAP.md` (登録先)・`REPORT_PY2.md` の未解決表 (2/4 スレッドの実測先)・`tests/static_mt_check.mjs` の参照 (§4)。
- 環境: GitHub Actions runner (4 core)、emcc 6.0.12 ([EMSDK]、runner 上の既存の emsdk)、node v22.23.3。素材: fl-win64 ([WIN64]) から `extracted/` の 5 block (`block00031_PE.bin`・`block24429/24430/24618/25159_DATA.bin`) を展開。`toolchain-emsdk` ([EMSDK]) の tar は展開していない (runner 上の既存の emsdk を使用)。load は各 run 直前の OS の 1 分 loadavg の値。

| ビルド (cwd = tools/python) | 結果 | 所要 |
|---|---|---|
| `bash build_cpython_wasm.sh` (stock、native 込み) | rc 0。`work/build-wasm/python.wasm` 5,927,853 B | 未計測 (完了 20:51) |
| `CPY_PTHREADS=1 bash build_cpython_wasm.sh` | rc 0。`work/build-wasm-pthread/python.wasm` 6,124,019 B (native は再利用) | 未計測 (完了 20:52) |
| `bash build_flpy_static.sh` (stock) | rc 0。`dist/flpy_static.wasm` 5,969,667 B | 未計測 |
| `CPY_PTHREADS=1 bash build_flpy_static.sh` | rc 0。`dist/flpy_static_pthread.wasm` 6,165,862 B。警告 1 件 `-Wpthreads-mem-growth` (§6) | 未計測 (完了 20:53) |
| `bash build_flpy.sh` (SAB 版 `flpy.wasm`。`static_check` の正の対照) | rc 0 | 5.5 秒 (wall) |

| 検証 | 結果 | 所要 | load (直前) |
|---|---|---|---|
| `node tests/all_tools.mjs` (mock) | 48/48 ok・host_calls 37,425 | 1.432 秒 | 未計測 |
| `bash provider/build.sh` → `node tests/provider_check.mjs` | build rc 0。`PASS: true` (関数 435・実装 83) | build 0.845 秒 | 未計測 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok・host_calls 37,425 | 未計測 | 未計測 |
| `node tests/static_check.mjs` (stock 静的版) | `STATIC CHECK OK`。SAB+provider・mock の両方で tool 別差 0/48 | 0.285 秒 | 0.82 |
| `node tests/static_mt_check.mjs` (pthread 版) × 3 | 3 回とも `STATIC MT CHECK OK`。単一スレッド列と stock 記録の差 0/48 (host_calls 37,424)。2 スレッド 48 tool・4 スレッド 2 tool、`thread_mismatch` 0 | プロセス 0.676 / 0.676 / 0.697 秒。MT 部 293 / 299 / 293 ms | 0.76 (3 回とも) |
| `node tests/static_mt_check.mjs open_piano_roll_for_channel` (§4 の再現) | calls[0] host_calls 15・calls[1] host_calls 16 (期待値どおり) | 未計測 |
| §5 の負のコントロール (一時コピーを実行し削除) | `STATIC MT CHECK FAIL (50)`、rc 1 | 未計測 |
| `node tests/static_subinterp_probe.mjs` (main 取り込みの検証。stock 静的版) | `STATIC SUBINTERP OK` 12/12、rc 0 | 15.3 秒 |

- 差分の確認: 取り込みで PR 側に入ったコード (`git diff --stat 548f04ec c1b3204c -- tools/python ':(exclude)*.md'`) は 24 files、1664 insertions(+)、88 deletions(-)。main 側の変更 (provider・analysis・subinterp probe ほか) を含む。測定 commit から HEAD までのコード差分 (`git diff c1b3204c HEAD -- tools/python ':(exclude)*.md'`) は 0 行。
- 未解決 (§9): CPython wasm ビルドの所要は未計測 (完了時刻だけ記録)。§5 の 1 行だけ壊す負のコントロールは §7 の未解決のまま。
