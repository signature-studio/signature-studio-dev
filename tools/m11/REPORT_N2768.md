# M11 REPORT #2768 (M11-N155): 寛容起動で skip した unit が trap までに heap へ書いた範囲

親 #2714 (子として移管) / epic #2712。前提: `REPORT_N2714.md` (寛容起動・skip 一覧・image 差分の順位)。
本書は **heap の範囲**だけを扱う。image 差分は `REPORT_N2714.md` §4-2。

## 0. 結論

- 寛容起動の skip unit 72 件 (PR #2752 の記録 67 件を含む) について、各 unit が trap までに heap へ書いた範囲を実測した。heap の書換えは合計 **47,416,280 B** (c_static 2,327 B・stack 16,693 B は別集計)。
- 合計の **99.5% は 2 unit** に集中する: i=830 (oob・23,733,431 B・2,181,961 区間) と i=101 (oom・23,467,023 B・2,142,871 区間)。3 番目は i=280 (oob・199,169 B)。残りは 1 unit あたり 6,474 B 以下。
- 2 unit の書換えは **大量の 10〜11 B 断片**で、GetMem・VirtualAlloc による新規確保が無い i=830 でも発生する。既存 heap の構造を走査しながら書き換えている型と推定する (推定。構造は未特定)。
- **環境差 (要確認)**: この run では PR #2752 の数値 (survey ok 872・寛容 skip 67) を再現できなかった (survey 874・skip 72)。変更前の HEAD でも同じ数値で、e2e の判定ゲートは FAIL (§2・§6)。
- 区間は「状態に効くかの証明」ではない。後続 unit と `CreateFruityInstance` の経路がどこを読むかは未追跡 (推定のみ。`docs/DEFECTS.md` D17・D19 と同じく候補の列挙)。

## 1. 測定の方法

- **コード**: `tools/m11/m11_tolerant.mjs` に 2 つの環境変数を足した (既定は off。既定の strict・survey・寛容起動の経路は変えていない)。
  - `M11_HEAP_FROM=<寛容起動の記録 JSON>`: その JSON の `skipped` の unit だけ対象にする (2 回目の実行)。
  - `M11_HEAP_OUT=<path>`: 対象 unit の heap 差分を書く。
- **差分**: 対象 unit の直前に heap 全体 (`HEAPU8`) を退避し、trap 後に 64 KB 頁単位で比べて区間にした (16 B 以内の隙間は同じ区間)。image (`0..img_len`) は除外する。stack は別に合計だけ出す。
- **領域**: wasm の export の値 (`___global_base`・`___stack_low`・`___stack_high`・`___heap_base`)。
  - `c_static` = [268435456, 271188784) (C の静的領域)。
  - `stack` = [271188784, 279577392)。
  - `heap` = [279577392, メモリ末端) (malloc 領域。VirtualAlloc の確保を含む)。
  - `gap` = [img_len, gb) = [22515781, 268435456) (image の末端と C 静的の間)。この区間は存在し、そこへの書込みは 0 B。
- **決定性 (kind のみ)**: 2 回目 (heap 測定) の skip 72 unit は、1 回目 (寛容起動の記録) と kind が一致した (`match: true`)。`match` は kind だけを比べる (`m11_tolerant.mjs` の `p1.get(r.i) === r.kind`)。1 回目の記録には heap の区間が無いため、区間の一致は確認していない (§7 の未解決)。
- **集計**: `python3 tools/m11/m11_tolerant_heap.py work/tolerant_heap.json` (表の生成元。`--top N` で区間の先頭も出る)。

## 2. 環境 (PR #2752 の数値との差)

- 素材: `fl-win64` (PE sha256 `b2c64da4…`)・`toolchain-retdec`/`toolchain-emsdk` は runner の `/opt` に既存・`work-m11` を `tools/m11/work/` に展開。素材に `work/lift_pe.sha256` が無いので、PE の sha256 を手で書いた (`REPORT_N2714.md` §1 と同じ手順)。IR `ir_sha256 de46cada…` は `REPORT_N2714.md` と一致した。
- 素材の `m11_boot.cjs.wasm` (6010853 B) は #2714 より前のビルドで、`_m11_set_tolerant` を持たず寛容起動が走らない。そのため `m11_e2e.sh` が再ビルドした wasm (6044574 B) で測った。
- 素材の `m11_data.c` は再生成版と 33 B の文言差がある (生成器の LB_BASE 表記の変更)。`m11_image.bin` は素材と sha256 一致 (`2d10d692…`)。

| 項目 | PR #2752 (`REPORT_N2714.md`) | 本 run (変更前の HEAD `26f90ada` と f69ddc5d で同じ) |
|---|---|---|
| strict 完了 (units_run + skipped) | 56 | 56 (一致) |
| survey ok / trap | 872 / 23 | **874 / 21** |
| 寛容 試行 / ok / skip | 942 / 874 / 67 | 942 / **869** / **72** |
| skip の種類 | miss 46・halt0 7・oob 13・unreachable 1 | miss 46・halt0 7・**oob 17**・unreachable 1・**oom 1** |
| clobber | 0 | 0 |

- 差は 5 unit: **i=101** (oom)・**i=291・296・304・555** (oob)。
  - i=101: unit 内で成功した確保の累計 (`_m11_va_used` の差分 `va_bytes`) が 267,714,560 B に達した後、次の要求が単位予算 256 MiB (268,435,456 B) を超え、`m11_rt.c` が加算前に NULL を返した (GetMem 2,137,929 回)。
  - PR の逐次の記録 (`REPORT_N2714.md` §3) では 304・555 が ok だった。291・296・101 の PR 側の unit 単位の記録は無く、kind 件数 (oob 13→17・oom 0→1) からの推定。
- survey (unit を 1 本ずつ隔離) も 874 で、逐次の状態だけの差ではない。
- **原因は未特定**。確認した候補: (a) image は素材と同一 (差なし)。(b) wasm は再ビルド版で測ったが、PR 側の wasm が同じ版かは未確認 (ビルドの emsdk 版・data.c の生成版の切り分けは未実施)。(c) node は PR と同じ v22.23.3。
- (d) 素材 `work-m11` の版: `docs/WORKFLOW.md` §11 は、この素材を #516 qstore 以前の生成と記し、survey の基準には使わないとしている (#680)。展開先 `tools/m11/work/` に `qstore_report.json`・`ir_conditions.json` が無いことを確認した。pin (872・67) を立てた測定がどの素材で行われたかは未確認。現行の生成手順 (`m11_gen_ir2.sh`・`--full`) で作り直した素材での再測定は未実施 (`--full` は約 633 秒 + Ghidra の前提があり、本 run の時間内に収まらないと判断した)。
- e2e FAIL の原因候補は素材版の差 (推定。切り分けは未実施)。pin を変えるかの判断は §7 の PM 判断待ち。

## 3. heap 書換えの一覧 (72 unit・測定 commit f69ddc5d)

- `順位` は heap + c_static の合計の降順。`区間数` は heap と c_static の区間の合計。最後の列は最大の 2 区間 (領域・絶対アドレス・長さ B)。
- 列「VA」は unit の関数 VA (`0xfa9390` は関数の先頭ではない値 = Init 未実行の miss 群)。`GetMem`・`VA` の値は `REPORT_N2714.md` §4-2 と本書 §4 を参照。

| 順位 | i | VA | 種類 | c_static B | heap B | gap B | 区間数 (heap+c_static) | 最大の 2 区間 (領域・先頭の絶対アドレス・長さ B) |
|---:|---:|---|---|---:|---:|---:|---:|---|
| 1 | 830 | 0xcd50d0 | oob | 95 | 23733431 | 0 | 2181961 | heap 0x10be1a38 +11658, heap 0x41613834 +4992 |
| 2 | 101 | 0x1de960 | oom | 169 | 23467023 | 0 | 2142871 | heap 0x10bf373a +1673, heap 0x10bb9398 +67 |
| 3 | 280 | 0x416010 | oob | 178 | 199169 | 0 | 37869 | heap 0x41613834 +4992, heap 0x423b3834 +4992 |
| 4 | 114 | 0x223840 | halt0 | 401 | 6474 | 0 | 112 | heap 0x414b0008 +4065, heap 0x10be4c38 +660 |
| 5 | 56 | 0x16fde0 | unreachable | 55 | 5031 | 0 | 267 | heap 0x10bd3d48 +611, heap 0x10bc4db8 +139 |
| 6 | 745 | 0xabb3b0 | oob | 79 | 2147 | 0 | 102 | heap 0x39723d40 +196, heap 0x39723ec0 +196 |
| 7 | 314 | 0x4e48a0 | halt0 | 247 | 1510 | 0 | 53 | heap 0x10bb97b8 +395, heap 0x10be5318 +202 |
| 8 | 880 | 0xe63540 | oob | 108 | 332 | 0 | 32 | heap 0x10be5c18 +75, heap 0x10bbee98 +59 |
| 9 | 509 | 0x739ca0 | halt0 | 48 | 216 | 0 | 26 | heap 0x39722818 +75, heap 0x10bcccf8 +35 |
| 10 | 492 | 0x6d5700 | oob | 69 | 182 | 0 | 19 | heap 0x10be5778 +57, heap 0x39722758 +43 |
| 11 | 659 | 0x8eaa30 | oob | 93 | 96 | 0 | 25 | heap 0x4dcf0000 +48, heap 0x10be5b78 +25 |
| 12 | 245 | 0x333090 | halt0 | 44 | 83 | 0 | 17 | heap 0x39721e58 +60, c_static 0x1029ba70 +17 |
| 13 | 304 | 0x483140 | oob | 62 | 53 | 0 | 17 | heap 0x10bd5428 +32, c_static 0x1029aa50 +17 |
| 14 | 513 | 0x7654c0 | oob | 41 | 71 | 0 | 12 | heap 0x39722918 +38, heap 0x10bd6568 +31 |
| 15 | 520 | 0x776bf0 | oob | 41 | 71 | 0 | 12 | heap 0x39722958 +38, heap 0x10bd6598 +31 |
| 16 | 484 | 0x6d0680 | oob | 41 | 69 | 0 | 12 | heap 0x39722718 +38, heap 0x10be5778 +29 |
| 17 | 477 | 0x6bfd60 | oob | 41 | 66 | 0 | 12 | heap 0x10bd5c68 +37, heap 0x10be5758 +27 |
| 18 | 291 | 0x432660 | oob | 41 | 53 | 0 | 16 | heap 0x10bd53c8 +32, c_static 0x1029ba70 +17 |
| 19 | 296 | 0x446130 | oob | 41 | 53 | 0 | 16 | heap 0x10bd53f8 +32, c_static 0x1029ba70 +17 |
| 20 | 555 | 0x7f2500 | oob | 40 | 53 | 0 | 16 | heap 0x10bd65c8 +32, c_static 0x1029ba70 +17 |
| 21 | 279 | 0x4136d0 | halt0 | 44 | 44 | 0 | 17 | heap 0x39721ed8 +21, c_static 0x1029ba70 +17 |
| 22 | 275 | 0x40e170 | oob | 60 | 27 | 0 | 15 | heap 0x10bd5278 +25, c_static 0x1029aa50 +17 |
| 23 | 647 | 0x897ac0 | halt0 | 45 | 26 | 0 | 17 | c_static 0x1029ba70 +17, c_static 0x102919c0 +13 |
| 24 | 149 | 0x264260 | oob | 52 | 0 | 0 | 8 | c_static 0x1029ba70 +25, c_static 0x1029aa50 +17 |
| 25 | 29 | 0xfa9390 | miss | 31 | 0 | 0 | 5 | c_static 0x10291560 +19, c_static 0x10292b30 +9 |
| 26 | 895 | 0xeddfe0 | halt0 | 13 | 0 | 0 | 8 | c_static 0x10295224 +5, c_static 0x10299d7a +2 |
| 27 | 923 | 0xf6c660 | oob | 11 | 0 | 0 | 6 | c_static 0x10295368 +5, c_static 0x10299a74 +2 |
| 28 | 115 | 0xfa9390 | miss | 5 | 0 | 0 | 4 | c_static 0x1029a9f2 +2, c_static 0x10291560 +1 |
| 29 | 38 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 30 | 39 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 31 | 105 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 32 | 121 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 33 | 122 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 34 | 123 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 35 | 124 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 36 | 125 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 37 | 127 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 38 | 131 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 39 | 132 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 40 | 196 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 41 | 197 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 42 | 198 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 43 | 199 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 44 | 200 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 45 | 201 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 46 | 202 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 47 | 203 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 48 | 205 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 49 | 206 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 50 | 207 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 51 | 208 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 52 | 209 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 53 | 210 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 54 | 211 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 55 | 212 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 56 | 213 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 57 | 214 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 58 | 215 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 59 | 216 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 60 | 217 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 61 | 218 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 62 | 219 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 63 | 225 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 64 | 287 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 65 | 288 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 66 | 289 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 67 | 290 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 68 | 292 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 69 | 293 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 70 | 356 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 71 | 499 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |
| 72 | 913 | 0xfa9390 | miss | 3 | 0 | 0 | 3 | c_static 0x10291560 +1, c_static 0x102919c4 +1 |

- 合計 (B): c_static=2327, heap=47416280, gap=0, stack_gap=0, stack=16693 / 種類: {"miss": 46, "unreachable": 1, "oom": 1, "halt0": 7, "oob": 17} / units=72 match=True
- layout: {"gb": 268435456, "sl": 271188784, "sh": 279577392, "hb": 279577392} img_len=22515781

## 4. リスク評価 (上位を個別に・推定)

heap の範囲と、`REPORT_N2714.md` §4-2 の image 差分を併せて見る。「参照されうる」は全て推定で、参照の追跡はしていない。`VA N B` は unit 内で成功した VirtualAlloc の累計 (`_m11_va_used` の差分。予算超過で NULL になった要求は含まない)。

1. **i=830** (oob・heap 23,733,431 B・2,181,961 区間・GetMem 3・VA 0): 最優先。新規確保が無いのに既存 heap へ約 218 万か所・長さ 10〜11 B の書換え (アドレス範囲 `0x10aa0334`〜`0x4f144fdd`)。既存の大きな構造 (表・リスト) を走査しながら書き換え、途中で trap した型と推定。image 差分は `.data` 8 B・`.bss` 5 B (`REPORT_N2714.md` 順位 12)。後続 unit や `CreateFruityInstance` が同じ構造を読めば、例外無しで誤った値を読む恐れがある (推定)。
2. **i=101** (oom・heap 23,467,023 B・2,142,871 区間・GetMem 2,137,929・VA 267,714,560 B (成功分の累計)): PR の記録では oom は 0 件 (§2)。確保の暴走 (GetMem が 214 万回) の途中で、単位予算 256 MiB を超える要求を NULL にした。書換えの型は i=830 と同じ (10〜11 B 断片)。確保の途中で止まった構造は後続が参照しうる (推定)。
3. **i=280** (oob・heap 199,169 B・37,869 区間・VA 120,782,848 B): image 差分の順位 1 (`.text` 9 B 書換え。`REPORT_N2714.md` §4-3 の 1)。heap にも 199 KB の書換え。`.text` 書換えと heap 書換えの両方に当たる unit で、リスクは最も高い。
4. **i=114** (halt0・heap 6,474 B・c_static 401 B・VA 132,775,936 B): 初期化の途中で Halt。VA 要求が大きく、確保後に離脱した型 (推定)。
5. **i=56** (unreachable・heap 5,031 B・c_static 55 B): strict の停止点。寛容起動でも失敗のまま。後続 unit が依存するかは未確認。
6. **順位 6〜24 の 19 unit** (oob 14 件・halt0 5 件。i=745・314・880・509・492・659 など): heap 書換えは 0〜2,147 B (最大は i=745)、c_static は 40〜247 B。各 unit の区間は §3 の表の該当行を参照 (ここは分類の要約のみ)。
7. **miss 46 unit** (`0xfa9390` の Init 未実行): heap の書換えは 0 B。c_static に 1〜3 B だけ書いている (区間 2〜3 個。推定: `m11_icall` の miss 計数。未確認)。image 差分は `InitCount` の 1 B のみ (`REPORT_N2714.md` §4-1)。Init 本体が一度も走らないことが、欠落の本体 (`REPORT_N2714.md` 順位 6)。

## 5. 限界

- 「trap までに書いた」は、unit 直前と trap 後の heap 全体の比較で数えた。malloc の内部メタデータ・新規確保の領域への非 0 書込みを区別していない。どの確保に属する書換えかは未特定。
- 区間数は 16 B の隙間統合に依存する。i=830 と i=101 の 2 unit は 10〜11 B 断片が多く、区間数が大きくなる (バイト数は統合の影響を受けない)。
- c_static の 1〜3 B (miss 46 unit) の正体は未特定。
- 後続 unit と `CreateFruityInstance` が heap 範囲を読むかは未追跡。成功 unit (この run では 869 件) の書込みは未計測 (`REPORT_N2714.md` の未解決)。
- 測定は 1 環境 (§2) の 1 回 + 決定性の再実行 1 回。時間は n=1 (pass 2 は 47.7 秒)。
- 本表は正しさの証明ではない。候補の一覧である。

## 6. 検証

- 測定 commit: **f69ddc5d** (`m11_tolerant.mjs` を変えた最後の commit。node の測定はこの commit で行った)。後続の `a1e4f428` は `m11_tolerant_heap.py` の見出し文言だけを変えた (集計の計算は変えていない。入力の JSON が手元に無いため表は再生成せず、§3 の列見出しを合わせた)。以降の commit は本 REPORT と `docs/DOC_MAP.md` のみ。
- e2e (`bash tools/m11/m11_e2e.sh`・f69ddc5d・n=1・1 分 12 秒。生成物は再利用): **FAIL (rc=1)**。
  - 実行 A (strict): 56 完了で停止 (ゲート PASS)。
  - 実行 B (survey): ok 874 ≠ 期待 872 (`TOLERANT_GATE_FAILED`)。
  - 実行 C (寛容): 942 試行・ok 869・skip 72 (ゲートの試行数と集計は PASS)。
  - ネガコン 3 本: `NEGCTL_OK` ×3 (退行を検出)。
  - この FAIL は本 PR の前の HEAD (`26f90ada`) でも同じ数値で出た (§2)。
- 寛容起動の heap 測定 (pass 2・f69ddc5d・47.7 秒): `match: true` (kind のみの比較。§1)・72 unit。
- コード差分 (測定 commit f69ddc5d → HEAD、`tools/m11` 配下。REPORT を除く): 下の出力のとおり 0 件。

`git diff --stat f69ddc5d HEAD -- tools/m11 ':!tools/m11/REPORT*.md'` の出力 (`a1e4f428` の 1 行):

```
 tools/m11/m11_tolerant_heap.py | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

測定に使った `m11_tolerant.mjs` には差分が無い (`git diff --stat f69ddc5d HEAD -- tools/m11/m11_tolerant.mjs` の出力は 0 行)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| PR #2752 の 872・67 を再現できない (原因未特定。素材 `work-m11` の版 (§2 (d))・wasm・data.c の生成版の切り分けは未実施) | e2e の判定ゲート (`e2e_expect.env` の pin) が FAIL (変更前の HEAD と同じ) | PM agent の判断待ち: e2e の pin (872・67) を据え置くか、この環境の値 (874・72) に改めるか・既定案: pin は据え置き、本 PR では pin を変えない (環境差として §2 に記録のみ) |
| 寛容起動の heap 区間の決定性 (kind のみ一致を確認。区間は未比較) | 区間が run ごとに揺れるかは未確認。§3 の区間は 1 回分の測定 | 本表のまま (再測定には素材の wasm 再ビルドが要る。子は起票しない) |
| i=830・101 の heap 書換え (約 218 万区間・約 23 MB) の構造と読み手 | 最大のリスク。どの構造かは未特定 | PM 判断 (解析の追跡。子は起票しない) |
| miss 46 unit の c_static 1〜3 B の正体 | 小 (推定: icall の miss 計数) | 本表の未解決のまま |
| 後続 unit と `CreateFruityInstance` が heap 範囲を読むか | 参照の有無は未追跡 | WIN-4 (#2715) |
| 寛容起動の 101 (oom・GetMem 214 万回。PR の記録では oom 0 件) | 環境差の一部 | §2 の原因と合わせて PM 判断 |
| 成功 unit (869) の heap 書込みは未計測 | 成功 unit 側の欠落は見ていない | PR 本文の未解決表に留める (`REPORT_N2714.md` 未解決) |
