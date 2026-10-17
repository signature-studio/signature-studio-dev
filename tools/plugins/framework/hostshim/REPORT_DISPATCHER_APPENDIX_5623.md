# PLG-P0b-61 (#5623, 親 #5422 → #4849) — 0x13221be の到達条件

部分達成 (`Refs #5623`)。受入 2 は 1/11 のまま。0x13221be の到達条件を機械語と実測で確定した。格納される値の供給元は未確定。

## 1. 機械語で確定した到達条件

`hs_store_branch.py 0x13221be` の支配分岐 (格納を支配する jcc と成立側):

| jcc | 成立側 | 直前の供給元 |
|---|---|---|
| `0x1321e97 jne 0x13281af` | fall 必須 | `sub eax, 3` (0x1321e92) |
| `0x1321e8c je 0x13220be` | fall 必須 | `sub eax, 1` (0x1321e87) |
| `0x1321e81 je 0x132207a` | fall 必須 | `sub eax, 1` (0x1321e7c) |
| `0x1321e76 je 0x1321fce` | fall 必須 | `sub eax, 6` (0x1321e71) |
| `0x1321e3b jg 0x1321e71` | taken 必須 | `mov eax, [rbp+0x1878]` (0x1321e32) |
| `0x1321e19 je 0x13281af` | fall 必須 | `call 0x40fe90` の戻り値 (`test al, al`) |

要点: `[rbp+0x1878]` (Dispatcher の第 4 引数 r9 = Index) が 11 のときに fall-through で格納へ届き、かつ `0x40fe90` の戻り値が非 0 であること。

## 2. 実測 (`hs_store_cov.py`・基準 `base.json` 対比)

測定 commit `a2718eca0` (hostshim の差分 0 行)。素材 `fl-win64` の `extracted/block00031_PE.bin` を 1 件展開して使用。

| 条件 | real | rc | 終了時 load | 0x13221be |
|---|---|---|---|---|
| 基準 (`HS_DISP_PATH=1`・既定) | 73.58 s | 0 | 0.94 | 未実行 |
| `HS_DISP_INDEX=11` のみ | 73.23 s | 0 | 1.00 | 未実行 (新規 3・失う 3) |
| `HS_DISP_INDEX=11` + `HS_DISP_RET_SPEC=0x40fe90:one` | 71.01 s | 0 | 0.94 | **ID 0x4c で実行** (新規 6・失う 4) |

- 初回の `HS_DISP_INDEX=11` 実行は環境変数の設定漏れで PE 既定パスを読み失敗した (測定値なし)。環境変数を明示して再実行した値を上の表に書いた。
- 格納値: `slot_writes` は `0x13221be=0x-42333333`。`0x40ae70` の stub (戻り値 0) 由来の値で、供給元の真値ではない。

## 3. 判定

- 0x13221be は、分岐の条件 (Index=11・`0x40fe90` の戻り値 ≠ 0) を与えて到達させた。
- 格納される rax の供給元は未確定で、格納値は stub 由来 (`x0` と同じ) のため、「供給元の値を与えた実行」には数えない。
- 受入 2 は **1/11 のまま** (0x132206e のみ)。

## 4. 再現

```
FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> HS_DISP_INDEX=11 HS_DISP_RET_SPEC=0x40fe90:one HS_DISP_PATH=1 HS_DISP_OUT=idx11r.json python3 hs_disp_emu.py
FL_WIN64_DIR=<展開先> PYTHONPATH=<...> python3 hs_store_cov.py base.json idx11r.json
```

## 5. 残作業

- 0x40ae70 の戻り値 xmm0 の真値 (0x132206e と 0x13221be の格納値の確定)。
- 0x13220b2 の格納値 0 の要因 (`[rbp+0x109c]` の経路)。
- 未実測の 10 行 (0x1319f13・0x1320fc4・0x1320ff9・0x1321225・0x1321f0e・0x1321f34・0x1321f6c・0x1321fc2・0x13220b2・0x13221be) の供給元。0x13221be は到達済みで、格納値の供給元だけが残る。
