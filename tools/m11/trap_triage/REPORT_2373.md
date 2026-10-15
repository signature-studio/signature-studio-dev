# REPORT_2373 — unit 895: `60a270` の caller は `e3ef60` (#2373, 親 #882)

> `M11_INSTR_60A270` probe の実装と ON/OFF の survey 集計表は PR #2371 の `REPORT_882_APPENDIX.md` §14 が正本。本書は集計値を複製しない。

既知類型との関係: 該当なし (呼出元の特定のみ。新規の欠陥類型は無い)。

## 0. 結論

- `60a270` の直接呼出しは 210 関数・638 箇所 (§1)。unit 895 の経路で `60a270` を呼ぶのは `e3ef60` で、`e3ef60` 内の 9 箇所のどれか (§2・§3)。
- unit 895 の経路 12 関数の隣り合う全 11 組が、PE 上の直接 call として確認できた (§2)。
- `e3ef60` の 9 箇所は、どれも this を `e3ef60` の arg1 のフィールド (`[arg1+off]`) から取る (§3)。どの箇所が 0 を渡すかは動的観測が要る (#2400。観測済み: `REPORT_882_APPENDIX.md` §15)。arg1 自体は #2407。
- 当初の head `0e6b21da` は `M11_INSTR_60A270` を独自実装していたが、PR #2371 と同じ probe の二重実装で競合するため外した。HEAD に probe のコードは無い。

## 1. `60a270` の caller の列挙 (静的。素材は `fl-win64` のみ)

測定 commit `e18e37cd` (`callers_of.py` の最後の変更)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、`capstone`・`pefile` 入りの Python。

```
python3 tools/m11/trap_triage/callers_of.py 60a270     # rc=0、5.8 s (`--chain` も 5.8 s)
```

- 出力末尾: `callers=210 sites=638`。全て `call` で `jmp` は 0 件。
- 呼出し箇所が 1 の関数が 106 件。多いのは `f5d510` (49)・`11390c0` (33)・`eee1a0` (19)。
- 先頭 5 件 (VA 昇順): `608110` (1)・`60ae30` (1)・`60ae40` (1)・`60e310` (1)・`61db60` (1)。
- `e3ef60`: n=9 (`e3f0b4`・`e3f0f7`・`e3f118`・`e3f139`・`e3f15a`・`e3f178`・`e3f196`・`e3f1b4`・`e3f215`)。
- 数えないもの: 間接呼出し (vtable・jump table)、`.pdata` に無い関数 (leaf)。
- 前 run の記録にあった「IR 上 206 件」(`grep -c "call i64 @function_60a270("`) は、数え方が違い、本 run は IR が無いため突合していない。

## 2. unit 895 の経路 (呼出順。外側 → 内側)

前 run (head `0e6b21da`、`M11_INSTR_60A270=1 M11_INSTR_40FFE0=1 M11_INSTR_40FF70=1` の build) の unit 895 の wasm frame:

`12ddfe0` → `12d0cc0` → `12d0c10` → `12d0f80` → **`e3ef60`** → **`60a270`** → `40ffe0` → `40c820` → `4096b0` → `412a40` → `4128b0` (Halt0) → `412770`

- 前 run の記録は `←` で書かれていたが、向きは呼出順 (左が呼出元)。次の静的確認で確定した。

```
python3 tools/m11/trap_triage/callers_of.py --chain 12ddfe0 12d0cc0 12d0c10 12d0f80 e3ef60 60a270 40ffe0 40c820 4096b0 412a40 4128b0 412770
12ddfe0 -> 12d0cc0 : call@12ddffd
12d0cc0 -> 12d0c10 : call@12d0ce0
12d0c10 -> 12d0f80 : call@12d0c5d
12d0f80 -> e3ef60 : call@12d0fbe
e3ef60 -> 60a270 : call@e3f0b4 call@e3f0f7 call@e3f118 call@e3f139 call@e3f15a call@e3f178 call@e3f196 call@e3f1b4 call@e3f215
60a270 -> 40ffe0 : call@60a28d call@60a2ca
40ffe0 -> 40c820 : call@40fff5
40c820 -> 4096b0 : call@40c841
4096b0 -> 412a40 : call@4096bb
412a40 -> 4128b0 : call@412a4a
4128b0 -> 412770 : call@4128ff call@4129e8
```

- 前 run の観測 (動的): unit 895 の `err` 先頭 3 行 (`rec.err` の上限) に `[m11][60a270] #1..#3`。`arg2 = 0x0` (3 行とも)。`this = 0` は #2371 §14.3 と同じ観測で、値の正本はそちら。呼出しの総数は未確認。
- 前 run の survey (probe OFF / 3 つ全部 ON) は、集計が #2371 §14.3 の同名の 2 行と同じ。前 run の所要は OFF 13.1 s・ON 13.0 s、build・survey とも rc=0。3 つ全部 ON は、`REPORT_882_APPENDIX.md` §13 の `40FFE0`+`40FF70` の 2 つだけの測定とは条件が違う。
- 前 run の素材: `fl-win64`・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`・`work-liftdiff`。`m11_gen_ir2.sh` rc=0 (50.3 s、ldfix errors=0)。

## 3. `e3ef60` の 9 箇所 (静的。`disasm_fn.py e3ef60`、測定 commit `e18e37cd`)

`e3ef60` は入口で arg1 を `[rbp+0x28]` に保存する。各箇所の `rcx` (this) は `[arg1 + off]`、`edx` は次のとおり。

| # | 箇所 | this (rcx) | edx (arg2) |
|--:|---|---|---|
| 1 | `e3f0b4` | `[arg1+0x778]` | `ebx` (`bl` は `[arg1+0xc4c]` が非 null かつ `10469e0([..+0x3f4])` が真なら 1、でなければ 0) |
| 2 | `e3f0f7` | `[arg1+0x7d8]` | `[arg1+0xb18] >= 1` |
| 3 | `e3f118` | `[arg1+0x810]` | `[arg1+0xb18] >= 1` |
| 4 | `e3f139` | `[arg1+0x840]` | `[arg1+0xb18] == 1` |
| 5 | `e3f15a` | `[arg1+0x808]` | `[arg1+0xb18] == 2` |
| 6 | `e3f178` | `[arg1+0x7f0]` | `[arg1+0xb18] <= 1` |
| 7 | `e3f196` | `[arg1+0x838]` | `[arg1+0xb18] == 1` |
| 8 | `e3f1b4` | `[arg1+0x8e8]` | `[arg1+0xb18] == 1` |
| 9 | `e3f215` | `[arg1+0x9c8]` | `[arg1+0xb18] == 1` |

- 箇所 1 は呼出し直後に `[rdi+0x49e]` を null 検査なしで読む (`rdi` = 箇所 1 の this)。
- 2 以降の `edx` は `dl` だけを設定する。上位 24 bit は直前の呼出しから戻った時点の `rdx` の値で、この表では決まらない。

## 4. #2373 の受入条件

1. `60a270` の caller を列挙し、unit 895 の経路上のものを特定: 達成 (§1・§2。経路上の caller は `e3ef60`)。
2. その caller (`e3ef60`) の入口で this を観測する probe: 本 PR では実施しない。#2371 が `M11_INSTR_60A270` を持つため、同じ行を触る probe は #2371 の merge 後に着手する → #2407。
3. 観測結果の記録: §2 に記録。HEAD は `tools/m11/m11_build.sh`・`m11_ov.c`・`m11_post.py` が `origin/main` と同一 (差分 0)。build 経路に変更は無い。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `e3ef60` の 9 箇所のうち this=0 を渡す箇所と、そのフィールドの値 | null this の出所 | #2400 (親 #2373) |
| `e3ef60` 入口の this (arg1) を観測する probe (受入条件 2) | arg1 自体の出所 | #2407 (親 #2373) |
| `e3ef60` の arg1 (this) の出所 (上位 caller `12d0f80` 以降) | 上位 caller | #882 |
| probe の組み合わせで unit 304・555 の分類が動く理由 | 計測 hook が分類を変える | #1602 (`[M11-N105]`) |
