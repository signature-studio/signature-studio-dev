# LD-248 (#4975): 機械語入口型 double の i128 引数を xmm に記録し、i128 位置の除外を外す

親: #4195 (LD-202)。前提: LD-52 (#1528) で i128 位置を比較から除外していた (`537c4cb6e`)。

## 1. 原因と修正

- `irtool.instrument` は IR の `i128` 引数を `trunc` して整数側 (`A[i]`) にだけ載せた。機械語入口型が `double` (xmm0) の関数 (`cases.MACHINE_ENTRY`: 40c660・40c750 ほか) では x 側が 0 のままだった。
- 修正: `instrument(entry_types=...)` で機械語入口型を受け取り、`double` の i128 引数は下位 64bit を `X[i]` (xmm) にも載せる。`build_wasm` は `cases.MACHINE_ENTRY` を渡し、`irtool.py`・`cases.py` が新しいときも再計装する (古い `ir_instr.ll` を残さない)。
- `compare.cmp_trace`: IR i128 位置の除外を削除。i128 位置は `ctx.eq` の stack 範囲規則を使わず、bit 比較 + 領域内ポインタの rebase (`n2w`) だけを当てる。
  - 理由: `ctx.eq` の stack 規則は native の大きい値 (1.5 = `0x3ff8…`) と wasm の 0 を一致と見なし、xmm0 の欠落を隠す。
  - 初版は rebase を入れず、653c80 の r8 (領域内ポインタ) で偽の不一致 3 件 (`0x2247a000` vs `0x2207a000`) を出した。rebase を入れて解消 (単体テストで固定)。

## 2. 測定 (測定 commit `0bc4b9a39`)

| 項目 | 結果 |
|---|---|
| `liftdiff_e2e.sh --m11-only` (HEAD) | PASS・wall 194s・load 1 分値 3.06 → 4.54 |
| 単体テスト (LD-11/52/181/248/179/203/225・irtool sites) | 全 PASS |
| 対象 11 関数 (`targets/ld52_11.txt`) | 一致 2 / 不一致 8 / 実行不能 1 (base も同じ 2/8/1) |
| 対象 11 関数の i128 位置 entry_arg | base は除外で 0 件。修正後も 0 件 (偽の不一致なし) |
| sample:800 判定 | 一致 359 / 不一致 236 / 実行不能 206。base と同一 (判定の変化 0 件) |
| sample:800 case の outcome/diffs 差 | base vs 修正 13〜14 件。同一コードの再実行どうし (run1 vs run2) でも 12 件 → 実行ゆらぎの範囲 |

### 2.1 対象 11 関数の内訳 (修正後)

| VA | verdict | 残る理由 (i128 とは無関係) |
|---|---|---|
| 40c660 | match | — (xmm0 が一致) |
| 40c750 | match | — |
| 653c80 | mismatch | ret 差 (wasm `0x2000000000000`) と native 余分の call (`?vmslot0`)。i128 位置 (r8) は一致 |
| 691dd0 | unexec | native_fault (base も同じ) |
| 4256c0 | mismatch | diff (base も同じ) |
| 442a50 | mismatch | 子 `4428c0` の i64 pos 0 (native `0x11` / wasm `0x0`)。i128 ではない |
| 442b90 | mismatch | diff (base も同じ) |
| 664890 | mismatch | wasm_trap (base も同じ) |
| 6649b0 | mismatch | 子 `40bf40` の i64 pos 0 (native `0x11` / wasm `0x0`) |
| 6649c0 | mismatch | float pos 0 (native `0x3fc00000` / wasm `0x0`)。i128 ではない |
| 664a80 | mismatch | diff (base も同じ) |

判定: 11 関数の verdict は base と同一。i128 位置の偽の不一致は消えた。残る entry_arg は i64・float の位置で、本 issue の範囲外 (親 #4195 で扱う)。

## 3. 再現

```
cd tools/liftdiff
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash liftdiff_e2e.sh --m11-only                       # PASS
python3 liftdiff.py batch targets/m11.json --set file:targets/ld52_11.txt --nobuild       # 11 関数
```

素材: `fl-win64`・`work-m11`・`work-liftdiff` (`tar --zstd -xf`)。base 比較は `d7f396545` を別 worktree で `ldlib/build_wasm.py --force` して実施。
