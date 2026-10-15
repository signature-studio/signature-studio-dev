# SHX-T36 (#3069): test.sh の emcc 無出力を FAIL にし、入力欠落で生成物を上書きしない

結論: `tools/shimx/test.sh` は、emcc が終了 0 でも出力が無い・空なら非 0 で FAIL する。M11 IR と M8 IR が揃わない run では step 6 が SKIP し、生成物 4 件 (`BACKLOG.md`・`data/coverage.json`・`data/inventory.csv`・`inventory.md`) を上書きしない。両規則は `test/guard/guard_test.sh` (7b) で検査し、規則を外すと落ちることを 3 通りの mutant で確認した。対象 issue: [#3069](https://github.com/signature-studio/signature-studio-dev/issues/3069)。

## 1. 背景

- #3023 の検証中、step 2 で emcc が終了 0 のまま `build/shimx_test_mt.js` を出さず、後続の `mv` が失敗した (元 issue で 4 回中 1 回)。
- step 6 は M11・M8 の gitignore 入力が無いと `gen_inventory.py` が空の値 (`m11_closure` が `{}`) で 4 生成物を書き換えていた。
- 依存の #3023 は closed、解消 PR #3056 は 2026-10-14 22:01Z に merged を確認済み。

## 2. 変更

| ファイル | 変更 |
|---|---|
| `tools/shimx/test.sh` | steps 2/3/5 の emcc を `emcc_js` に通す。終了 0 でも出力が無い・空なら非 0 (`FAIL: emcc が終了 0 だが出力が無い・空`)。step 6 の `gen_inventory.py` と coverage gate は M11 IR と M8 IR の両方があるときだけ実行し、欠落時は `SKIP` を表示する。入力パスは `SHIMX_M11_IR`・`SHIMX_M8_IR`、emcc は `SHIMX_EMCC` で差し替えられる (ガード用)。7b でガードを呼ぶ (子 run は `SHIMX_GUARD_CHILD=1` で省く) |
| `tools/shimx/test/guard/guard_test.sh` (新規) | G1a: `SHIMX_EMCC=/bin/true` (出力なし)。G1b: 空ファイルを出す偽 emcc。どちらも子 test.sh が非 0 で『出力が無い・空』を表示することを確かめる。G2: M11・M8 IR を存在しないパスへ向けた子 run が rc 0・SKIP で、生成物 4 件に置いた sentinel が消えない (sha256 不変) ことを確かめる |

変更していない: `tools/shimx/src`・`tools/shim/`・step 6 の sig gate / R6 / OTT 検査 (入力の有無で既に条件分岐している)。

## 3. 受入条件の対応

| 受入条件 | 結果 | 根拠 |
|---|---|---|
| emcc 終了 0 かつ出力無し/空 → 明示 FAIL・非 0 | 満たす | G1a・G1b (§4 mutant A) |
| 入力欠落で生成物 4 件を上書きせず SKIP。入力ありの挙動は変えない | 満たす | G2 (sha 不変・SKIP)。入力あり run の生成物差分は変更前と同一 (§5) |
| 検証手順 (入力欠落の再現を含む) を test.sh か既存テストに入れ、規則を壊すと落ちる | 満たす | 7b で `guard_test.sh` を実行。§4 mutant A/B/C |
| 測定 commit と `git diff` を REPORT に添える | 満たす | §5・§6 |

## 4. ネガティブコントロール (規則を 1 つずつ外して guard を実行)

各 mutant は作業ツリーの test.sh だけを一時的に変えて `bash tools/shimx/test/guard/guard_test.sh` を実行し、終わったら元に戻した。

| mutant | 外した規則 | guard の結果 |
|---|---|---|
| A | 空出力の検査 (`[ -s "$out" ]`) | `G1a: 出力が無い旨の FAIL が出ていない (rc=1)`。rc=1 は後続の `mv` の失敗によるもので、明示の FAIL は出ない |
| B | 入力欠落の分岐 (gen_inventory を常に実行) | `G2: step 6 の SKIP 表示が無い` |
| C | SKIP 表示は残し、再生成だけ行う | `G2: 入力欠落で生成物 4 件が上書きされた (sentinel が消えた)` |

- 初版のガードは mutant C を検出できなかった。G2 が「実行前の生成物の sha」を作業ツリーから取っていたため、直前の mutant B が書いた M11 無しの値を基準にしてしまい、前後が一致した。現版は実行前に sentinel を書き、終了時に退避内容へ戻す (`trap`)。直前の実行結果に依存しない。
- 最終版の guard は、規則を外していない test.sh で全 OK (rc 0・G1a・G1b・G2)。

## 5. 測定

測定 commit は `35970048d` (コードを変えた最後の commit)。全て commit 済みの内容で実行した。load は `uptime` の 1 分平均 (開始→終了)。

| run | 内容 | rc | 所要 | load | 生成物 4 件の差分 (HEAD 比) |
|---|---|---|---|---|---|
| 基準 `e13f1efd2` (変更前) | `test.sh` 全体・入力あり (ガード無し) | 0 | 74.5 s | 0.30 → 0.92 | 3 件変化 (23 行追加・22 行削除) |
| `35970048d` | `test.sh` 全体・入力あり (7b のガード含む) | 0 | 141.5 s (うち 7b 約 67 s) | 0.92 → 1.00 | 3 件変化 (23 行追加・22 行削除)。基準と同一 |
| `35970048d` | `test.sh --quick`・M11/M8 IR を存在しないパスへ (7b のガード含む) | 0 | 127.8 s (うち 7b 約 67 s) | 1.00 → 1.18 | **0 行** |

- 入力あり run の PASS: step 2・3・5 の MT/ST/M4 が ALL PASS、fail-fast 13 種と ExitProcess(7)、step 6 の coverage 基準 (`FLEngine 738: 実装 358 = 48.5% / 担当範囲 359 に対し 100.0% / 未実装 0`)、OTT `API 解決 24 種`、`t1 出力 SHA` 一致、`7/7 完了`。
- 入力欠落 run: `[shimx] SKIP: 入力 (M11 IR: … / M8 IR: …) が揃っていない` を 1 行出し、4 生成物の `git diff` は 0 行。`7/7 完了` まで PASS。
- 変更前の差分 (3 件・23/22 行) と変更後の入力あり run の差分が一致するため、入力あり時の挙動は変わっていない。

## 6. 差分 (測定 commit 以後)

`git diff 35970048d HEAD -- tools/shimx/test.sh tools/shimx/test/guard` は 0 行 (測定後にコード差分は無い)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD の生成物 3 件 (`BACKLOG.md`・`data/coverage.json`・`inventory.md`) が、入力ありの再生成結果と一致しない (`midi_conv.c` の追加・運用フックの 69→79 など。HEAD の値は古い) | 入力ありの run ごとに 3 件が書き換わる。repo の値は古いまま | [SHX-T41] (子 issue) |

- 入力欠落時は coverage 基準 (担当範囲の未実装 0・M4 継承 53/53) の検査も SKIP される。設計どおり。この検査は入力の揃う run (`oc_artifacts: toolchain-emsdk work-m11 work-m6-ott`) でのみ行われる。
