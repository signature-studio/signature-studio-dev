# SHX-T61 (#5855): callee `function_4483f0` の計装 (`fix_shx_t61`・既定 OFF)

## 1. 結論

- 計装の基盤を入れた。`M11_FIX_SHX_T61=1` のときだけ callee `function_4483f0` の入口に呼出し回数と `this+0x4c`・`this+0x48` を `@fx61_buf` へ書く。既定 OFF で、既定 IR は変わらない (`shx_t61=not-applied`)。
- 受入 1 (hang の機序の確定) は未達。ON で実 boot は rc 124 (hang) し、hang 後に `@fx61_buf` を読む経路が無い。hang 位置は未確定。
- 本 REPORT の ON・既定の数値は、PR 本文に書かれた前 run の実測である。本 run では lift 素材 (`tools/m11/work/boot*.lift.ll`) が無く、IR を再生成できなかった (§3)。

## 2. 測定条件

- 測定 commit: `390061627` (コード差分の最終 commit)。
- 差分 0 の証跡 (本 run・HEAD で確認):

```
$ git diff 390061627 HEAD -- tools/m11 ':!tools/m11/REPORT_SHX-T61.md' | wc -l
0
```

- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`) を本 run で展開。`work-m11` は本 run の artifacts 配置先 (`docs/WORKFLOW.md` §11 の `work-m11`) に無い。
- 負荷 (前 run): 1 分平均 0.99〜1.00 (nproc 4)。

## 3. 実測

### 3.1 既定 OFF の IR (前 run の実測)

| 項目 | 結果 |
|---|---|
| `m11_gen_ir2.sh` (既定) | rc 0 |
| `work/boot_final.ll` の `fx61` 件数 | 0 件 |
| `ir_conditions.json` | `shx_t61=not-applied` |
| `ir_sha256` (先頭 16 桁) | `b202c157a80807f2…` |

全文の `ir_sha256` は前 run の PR 本文に無く、本 run でも再生成できないため未記録。

### 3.2 本 run の再現 (失敗)

- `m11_gen_ir2.sh` (既定・FL_WIN64_DIR を展開先に設定): rc 1。`work/boot0.lift.ll` が無い (`m11_merge.py` が FileNotFoundError)。
- 原因: lift 素材 `boot0〜5.lift.ll` を含む `work-m11` が本 run に配置されていない。本 run の artifacts 配置先は `fl-win64.tar.zst` のみ。`boot*.lift.ll` の再生成は RetDec を使うため、新規の作業としては行わない (D5)。
- よって本 run では §3.1 の `ir_sha256` 全文と `fx61` 件数を再確認できなかった。

### 3.3 ON 計装 (`M11_FIX_SHX_T40=1 M11_FIX_SHX_T61=1`・前 run の実測)

| 段階 | 結果 |
|---|---|
| IR 生成 (`m11_gen_ir2.sh`) | rc 0 (42 秒)。`fx61` は 15 行 |
| build (`m11_build.sh`) | rc 0・signature mismatch 0・undefined 0 |
| trace build (`shimx_link/build.sh --trace --soft`) | rc 0・signature mismatch 0・undefined 0・duplicate 0 |
| 実 boot (`run_trace.mjs`・上限 150 s) | rc 124 (hang)。stdout・stderr・trace ファイルとも出力なし |
| 実 boot + `SXT_PRINT=1 M11_TRACE=1` | rc 124。`[m11][VA-stack]` の wasm スタックのみ。`function_4483f0` の呼出し回数は出ない |

### 3.4 trace 分岐の確認

`shimx_link/build.sh` の分岐は `grep -q '^@fx61_buf' "$GEN/boot_trace.ll"` で判定する。`gen_link.py` は `@fx61_buf` を `__sxt_` に改名しないため、この grep で検出できる (前 run のレビューで確認済み)。

## 4. 試行で分かったこと

- `printf` を計装に使うと、`m11_winstubs.c` の `printf` stub と型が衝突してビルドが落ちた。
- `sx_t61_rec` (IR から C の関数を呼ぶ形) も `genstubs` が生成する stub と名前が衝突し、リンクが落ちた (`gui_stubs_*.c`・`trace_wrap.c`)。IR の `declare` は stub 化されるため、IR から C を呼ぶ形は使えない。
- そこで IR 側は `@fx61_buf` (global) に書き、C 側は読み出し関数だけを持つ形にした。リンクは通った。
- ただし hang 中は `run_trace.mjs` が JS に制御を戻さないため、`fx61_buf` を読めない。

## 5. 未実装・未解決

- `fx61_rec.c` の `fx61_count` / `fx61_self` / `fx61_c4c` / `fx61_c48` を呼ぶ JS 側の経路は無い。読み出し口は定義済みだが未使用。
- hang 中の `@fx61_buf` を読む経路 (wasm メモリを hang 後に読む、または回数上限で callee から戻す計装)。起票先: #5855 (本 PR の Refs 先) の本文「次段の残り」チェックリスト。fix round 1 で追記済み。
- 修復 ON の hang の機序 (#5846 受入 1 の続き)。起票先: #5855 (受入 1 の続き)。#5846 の現タイトル (「(#4121 残件)」) とは対応しないため、#5846 へは追記しない。
