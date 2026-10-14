<!-- 自動生成: python3 tools/liftdiff/tests/trace_diverge_418be0.py > tools/liftdiff/results/m11_418be0_thunk.md (LD-28 / #1035) -->
# m11 0x418be0 (型 D・P2) の食い違い分解 (LD-28, #1035)

対象 = batch の unreachable case のうち、最初の食い違い直前の共通 entry が 0x418be0 のもの 20 件。
最初の食い違いは 0x407030 (LoadStringW thunk) の有無 (native のみ)。thunk を除いた列で再比較した。

| 項目 | 件数 |
|---|---:|
| thunk 除去後も trace_head 内で食い違う | 16 |
| trace_head (最大 12 件) の上限で判定不能 | 4 |
| trace_head に解析不能要素があり丸ごと除外したケース (N/W いずれか) | 0 |

| 直前の共通 entry (L2) | native 次 entry | wasm 次 entry | 件数 |
|---|---|---|---:|
| 0x410320 | 0x409410 | 0x4133f0 | 9 |
| 0x446290 | 0x4233b0 | 0x413060 | 3 |
| 0x464c60 | 0x467910 | 0x4133f0 | 2 |
| 0x410320 | 0x409410 | 0x43dd60 | 1 |
| 0x414ad0 | 0x412c20 | 0x412d60 | 1 |
