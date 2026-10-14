# tools/plugins/p0c REPORT 付録 H (§18)

> **正本**: `tools/plugins/p0c/REPORT.md` (本体 §1〜§7 + 付録索引)。本節は #197 (親 PLG-P0c) の出口条件
> 「80 kernel 全てが native 機械語と bit-exact」に対する**最終センサス**として新規追加。

## 18. #197: 80 kernel の最終センサス (測定 HEAD `6444b186`)

### 18.1 目的と数え方

- 出口条件の判定は、REPORT 内に確定値が無かった (付録 C §91 の status センサスは、その後の修復 #277 / #983 / #982 等を反映していない) ため、同一コマンドで再測定して一本化する。
- 数え方は `p0c4_abi_e2e.py` の定義 (付録 B/C と同一): `buf_diff` = native と IR の出力バッファの bit 不一致 cell 数 (f32 4 B 単位・NaN 同士は nandiff に分離)。
- **除外される kernel**: `k80_diff.py` は ABI 判定 (`k80abi` + `build_argmodel`) が `ok` 以外の kernel を CSV に出さない (driver の `if K['status'] != 'ok': continue`)。これは本付録で再現した仕様であり、測定から外す判断ではない。

### 18.2 測定

- 測定 HEAD: `6444b186` (origin/main 起点の branch `197-p0c-census`、`tools/plugins/p0c` / `lift` は無変更)。
- 素材: `fl-win64` (`extracted/block18983_PE.bin`、展開先 `$RUNNER_TEMP/fl-win64`)、`llvm-as` は `/usr/lib/llvm-18/bin` (PATH 先頭)。
- 同一 HEAD での実行結果:

| 検証 | rc | 所要 | 結果 |
|---|---|---|---|
| `p0c_e2e.sh` (work/ 無し・クリーン) | 0 | 6 分 03 秒 | `== e2e OK ==` |
| `p0c4_abi_e2e.py 2000` (census) | 0 | 23.5 秒 | `run=67 ok=67 sig11=0`・冪等性 OK・llvm-as OK・45 変数 / 80 実装 / 10,886 B / x87 28 一致 |
| `p0c4_e2e.py 2000` (ext chain) | 0 | 1 分 40 秒 | 14 kernel 中 buf_diff=0 が 14 件 (下表 18.4) |

- 測定時の load average: p0c_e2e 開始時 1.39 (終了時 9.2)・census 直前 9.18 (並列 1, 4 コア runner)。

### 18.3 census の結果 (`p0c4_abi_e2e.py 2000`, 非 ext 鎖)

- 80 実装のうち CSV に出た kernel は **67** (全て status `ok`・sig11 0 件)。残る **13** は ABI 判定が ok でないため driver が CSV に出さない kernel (`k80_diff.py` の仕様)。
- そのうち **buf_diff = 0 は 49 / 67**。

#### buf_diff ≠ 0 の 18 kernel (非 ext 鎖・2000 case/kernel)

| kernel | buf_diff | maxulp (harness 出力) |
|---|---:|---:|
| 0x5de620 | 301,144 | 0.0000 |
| 0x5dea40 | 5,166,346 | inf |
| 0x5dec40 | 5,088,752 | inf |
| 0x5dedb0 | 2,583,215 | 535,560,460 |
| 0x5dee20 | 5,168,510 | 920,645,431 |
| 0x5dee50 | 5,168,510 | 224,174,645 |
| 0x5df340 | 1,283,847 | 0.0000 |
| 0x5dfae0 | 1,292,623 | 0.0000 |
| 0x5dfbe0 | 20,498 | 6,633.0000 |
| 0x5dfc90 | 110,434 | 51,082.000 |
| 0x5dfdb0 | 13,901 | 5,387.0000 |
| 0x5dffc0 | 4,000 | 441,131,124 |
| 0x5dfff0 | 4,000 | 159,985,194 |
| 0x5e0300 | 2,584,255 | 425,033,422 |
| 0x5e0350 | 5,168,510 | 425,493,409 |
| 0x5e03f0 | 5,168,510 | 0.0000 |
| 0x5e12c0 | 1,814,580 | 0.0000 |
| 0x5e1490 | 1,201,366 | 0.0000 |

- 注: `maxulp` の値が 10^8 台になるものは、比較対象の値がほぼ全域で異なる (符号・NaN・桁落ちによる無効比較) ことを示す。harness の `maxulp` を精度の指標として使うのは不適切で、本節では buf_diff のみで判定する。
- 0x5dfbe0 / 0x5dfc90 / 0x5dfdb0 は、ext 鎖 (18.4) で buf_diff = 0 になる kernel。非 ext 鎖では残る。

### 18.4 ext 鎖 (`p0c4_e2e.py 2000`) の結果

- 対象 14 kernel 全てで buf_diff = 0 (下表)。判定行 `bit-exact 7/14` は `ret_diff == 0` も要求する stricter 条件で、ret_diff は native が rax を放置する kernel で意味を持たない (付録 B/C の定義) ため、buffer 判定としては 14/14。

| kernel | class | buf_diff |
|---|---|---:|
| 0x5dfbe0 | rc_chop | 0 |
| 0x5dfc90 | rc_chop | 0 |
| 0x5dfd30 | f32chain | 0 |
| 0x5dfdb0 | rc_chop | 0 |
| 0x5de820 / 0x5dedf0 / 0x5dfb60 | f32chain | 0 |
| 0x5df210 / 0x5df240 | f32chain | 0 |
| 0x5e0760 / 0x5e0b70 / 0x5e0bb0 / 0x5e1590 / 0x5e1780 | sse | 0 |

### 18.5 出口条件への当てはめ

- **80 本全て bit-exact は未達**。判定に使える数は次のとおり:
  - 非 ext 鎖の census: 67 測定中 buf_diff=0 が 49。18 は未達。残り 13 は ABI 非 ok で未測定。
  - ext 鎖: 測定した 14 は全て buf_diff=0 (f80 系 4 kernel を含む)。ただし ext 鎖の対象は f80 kernel の一部に限られ、non-ext census の 18 件全体はカバーしない。
- Group B 12 本 (Delphi RTL / x87 helper 外部呼出) は付録 A §3 のとおり数値差分の対象外。本出口条件の扱いは PM 判断 (下表)。

## 18.6 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 非 ext 鎖 census の buf_diff≠0 が 18 kernel (18.3 表) | 80 本 bit-exact の未達の本体。ext 鎖では 4 件が解消済み | 子 issue (本 PR で起票) |
| 未測定 13 kernel (ABI 非 ok で CSV 対象外: 0x5de410 0x5de4b0 0x5de540 0x5de6a0 0x5de870 0x5deaa0 0x5df460 0x5df5a0 0x5dfa70 0x5e0380 0x5e11a0 0x5e12b0 0x5e1870) | 80 本の完全な判定ができない。0x5e12b0 は既存 #938 が担当。内訳 (Group B / abi-mismatch 等) は本測定では未分類 | 残りの分類は PM 判断 (#197 本文の更新時に付録 A/C の status と突き合わせる) |
| Group B 12 本を出口条件に含めるか | 判定基準そのもの | PM 判断 (#197 本文の更新) |
| harness の `maxulp` が 10^8 台を返す | 精度指標としては使えない (buf_diff のみで判定) | harness 修正は本 issue 外 |
