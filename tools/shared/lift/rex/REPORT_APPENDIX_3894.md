# tools/shared/lift/rex 付録 — info 4 件の trap の原因と movnti 閾値の実測 — T-SH-94 (#3894)

測定 commit: `80ff26da6` (`tools/shared/lift/rex/` の `.py` を変えた最後の commit)。`git diff 80ff26da6 HEAD -- tools/shared/lift/rex` の出力: 行数 0 (本測定の後にコードは変えていない)。以前の測定 HEAD: `69387a6d7` (その時点の `gen_movnti.py`・`movnti_check.py` は旧版で、本付録の sweep に置換)。
既知類型との関係: 該当なし (不一致 0)。lift の出力 (`lift/fle_lifted.c`) は変えていない。

## 結論 (1 行)
info 4 件 (fn=0・a1 ∈ [0x10000, 0x70000)) の trap は movnti ではなく、ハーネスの入力が arena (64 KiB) を越えて書くため。native は arena 末尾 0x30110000 で落ちる。wasm は同じ入力で movnti 以外の OOB (VA 0) で trap する (trap 位置は未特定。wasm の線形メモリは arena より広い)。movnti に入る閾値は実測で a1 ≥ 0x70000 (0x6ffff は入らず、0x70000 は入る) で、静的読み `count>>6 ≥ 0x1c00` と一致。

## 1. 原因の判定 (付録 #3589 §2 と同じ形式)
入力: `gen_movnti.py` の sweep。fn=0・a2 = arena 先頭 (0x30100000)・a1 = 0x10000〜0x7ffff の値 (`memset(a2, 0, sext32(a1))`)。

| a1 | wasm の trap | native の fault | 判定 |
|---|---|---|---|
| 0x27878 (info 旧 #1) | memory access out of bounds (VA 0) | 0x30110000 (arena 末尾) | movnti 以外。OOB (trap 位置は未特定) |
| 0x2d324・0x3d429・0x3ffa3 (info 旧) | 同上 | 0x30110000 | movnti 以外。OOB (trap 位置は未特定) |
| 0x6ffff | trap なし | 0x30110000 | movnti に入らない。native は arena 外で落ち、wasm は trap しない (arena 越境だけでは wasm は trap しない。§4) |
| 0x70000・0x70001・0x70040 | `ott_unsup` (movnti 0x18001c9a0) | 0x30110000 | movnti に入る |

- wasm 側の trap は `RuntimeError: memory access out of bounds` で、`unsup` ではない (`run_wasm.mjs` の debug 実行で確認。`rex_unsup_get` は 0)。
- native は arena 末尾 (0x30110000) で SIGSEGV。wasm は `INITIAL_MEMORY=0x31000000` の線形メモリ内で arena を越えた書込を受けるため、memset の store 自体は OOB にならない (a1 ≤ 0x7ffff の書込は最大 0x3016ffff < 0x31000000)。wasm の trap (VA 0) の位置は未特定。arena 内データの破損による後続 load などの推定は未確認。

## 2. 閾値の実測 (sweep 64 件・1 件ずつ判定)
- a1 ∈ [0x10000, 0x80000) を 0x2000 刻みに、加えて境界 (0x6ffff・0x70000・0x70001・0x70040) と旧 info の 4 値。
- 判定: 「movnti の VA で trap ⇔ a1 ≥ 0x70000」。**64/64 一致**。
- 閾値は 0x70000 で確定 (静的読み `count>>6 ≥ 0x1c00` と一致)。
- reach (a1 ∈ [0x70000, 0x80000)・16 件) は 16/16 が movnti の VA で trap し、native は 16/16 が arena 外で落ちる (#3589 の結果と同じ)。

## 3. 直した範囲
- 原因は lift ではなくハーネス入力。`gen_movnti.py` の info 4 件は `a2` を乱数の arena ポインタにして count (≈ 160 KiB) を書かせていたため、arena 外へ書いた。wasm 側の trap が memset の越境によるかどうかは本付録では確定していない (上記のとおり、越境だけでは wasm の trap は説明できない)。
- 修正: `gen_movnti.py` は a2 = arena 先頭に固定し、a1 を閾値スイープにする。`movnti_check.py` は「movnti に入る ⇔ a1 ≥ 0x70000」で判定する。
- lift (`tools/flelift/`) と `lift_x64c.sh` は変えていない。

## 4. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 同じ入力で wasm は trap せず、native だけが落ちる case がある (sweep の a1 = 0x20000・0x22000 など 10 件以上。例: a1 = 0x10000 は wasm が trap せず、native は 0x8b516b8 で落ちる)。wasm の線形メモリは arena より広いため、arena 外への書込が検出されない | arena 外への書込の一致は未検証。比較は arena 内だけ | 未起票 (本表で追跡。ハーネスの OOB 比較の設計は #2870 の範囲) |
| wasm の movnti 以外の OOB (VA 0) の trap 位置。arena 内データの破損による後続 load などの推定は未確認 | 原因の確定は未達 | 未起票 (本表で追跡) |
| movnti (memset 8 箇所) の x64c 対応 | a1 ≥ 0x70000 で fail-fast の trap | 子 #3893 [T-SH-93] |
| `REX_RUN_CRASHED=1` で全件流すと wasm が戻らない | 元が落ちる入力を全件 wasm で流せない | 子 #3895 [T-SH-95] |
