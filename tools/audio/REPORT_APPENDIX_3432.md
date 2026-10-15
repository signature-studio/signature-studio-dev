# #3432 burst_runs ゲートの検証 (付録)

親: `REPORT_AU2_CI.md` §12 (P2 の p99 の系譜)。変更の概要は PR #4249。

## 1. 測定 commit と差分 0 の証跡

- 測定 commit: `4d97f703e` (`feat(audio): AU-2 行列の PASS 判定に burst_runs > 0 を加える (#3432)`)
- 検証 HEAD: 本付録を含む commit (fix-up 後の PR head)。
- `git diff 4d97f703e HEAD -- tools/audio` の出力: **0 バイト** (`wc -c` = 0)。
  測定後に変わったのは PR 本文と本付録だけで、`tools/audio` のコードは測定時と同一。

## 2. node テスト (HEAD で再実行)

- コマンド: `node tools/audio/test/burst_gate_test.mjs`
- 結果: **9/9 PASS** (exit 0)
  - 正常な burst_hist (runs>0) は PASS
  - burst_hist 無し (取得失敗) は FAIL
  - burst_hist 全 0 (runs=0・p99=0) は FAIL
  - 全 0 の p99 は 0 (従来はこれを見ず PASS していた)
  - api=ds / api=wasapi は対象外 (PASS)
  - abort 結果は対象外 (PASS。abort の判定は各 expect)
  - stats 無しは対象外 (PASS)
  - p99 は該当 bin の上端 (runs=100 p99=512)

## 3. e2e (`--quick`) の結果

- コマンド: `node tools/audio/harness/run.mjs --quick --out <out.json>`
- 環境: headless Chrome・ubuntu runner・nproc 4・load avg 0.32→0.27
- 結果: **44/44 PASS**・wall **252.7 s**
- ASIO 全 scenario の `burst_runs`: **398〜1596** (`want > 0` を満たす)
- 出典: 測定 commit `4d97f703e` の run (PR #4249 の作成時)。生 JSON は本 fix run では残っていない
  (`/tmp/opencode/au38_quick.json` 不在)。差分 0 のため、同じ測定値が HEAD の結果を表す。
  reviewer の判断により再測定はしていない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `burst_gate_test.mjs` は CI・`package.json` script に配線されていない (手動実行のみ) | 規則を壊しても CI で検出されない | 未起票 (PM 判断) |
