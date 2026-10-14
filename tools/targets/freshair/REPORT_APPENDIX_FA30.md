# freshair FA-30 (#2187): ca1480 の 2 回目呼出 (C=Z) の呼出元と由来

FA-29 (#2145, `REPORT_APPENDIX_FA29.md` §2) で「2 回目の `ca1480` 呼出は `C=Z`」と判明した呼出の呼出元を特定する付録。
判定基準 (`run_fa9.sh` (a) の期待値) は変更していない。

## 1. 結論

- **呼出元は setter 0x180c9d700 自身の再帰呼出 (0x180c9d827) である。** `ca1480` が「見つからなかった」経路で `out[0]=0` かつ `out[2]!=0` のとき、setter は `C=out[2]`, `key=out[4]` で自分を呼び直す (`0x180c9d813`→`0x180c9d827`)。
- **`out[2]=Z` は harness が注入した 1 ノード (`FA_NODE1=1`) の値オブジェクトである。** `ca1480` の found 経路 (`0x180ca156f`〜`0x180ca15b5`) は、木のノードの値を `out[2]`、blk を `out[3]` に写す。harness の空 map (`FA_NODE1` 無し) では `out[2]=0` のまま再帰しない。
- **判定: 注入 node の found 経路でのみ発生する (harness 配線に依存)。** 本ハーネスの空 map では再帰は 0 回。実機の controller map に node があるかは本ハーネスでは再現されていないため、実機で同じ再帰が起きるかは未判定 (子 #2207 で扱う)。
- 2 回目の呼出で `out[0]=Z+0x2b0` になるのは、`key` の個数が 0 になり key 無し分岐 (`0x180ca1651`: `C+0x2b0`) に入るため。FA-29 §1 の説明と整合する。

## 2. 実行による確認 (`FA_PROBE9=1 FA_CHAIN9=1 FA_NODE1=1 FA_OUT0=1`)

新設の観測フック `FA_CHAIN9=1` (`native/native_ctrl.c`, 呼出のみ・既定 OFF) で `ca1480` の入出力を 1 行ずつ記録した。

| 呼出 | C | key (kc, k0) | 戻り out0 | out2 | out4 |
|---|---|---|---|---|---|
| 1 回目 (setter 直接) | C_0 (子) | (1, 0) | 0 | Z (`C_0` 側の node 値) | key+4 |
| 2 回目 (setter 再帰) | Z | (0, 1) → 個数 0 | `Z+0x2b0` | 0 | 0 |

- 8 シナリオ (S900–S907) すべてで同じ 2 段構造。`CHAIN9` は 16 行 (8×2)。
- 2 回目の `out0` は `OUT0 out0=Z+0x2b0` と一致 (`FA_OUT0` の出力と同値)。
- 対照 (`FA_NODE1` 無し): `CHAIN9` は 72 行 (8×9)、**全行で `out2=0`・`out0=0`**。再帰は 0 回。

## 3. 判定の根拠 (実機判定は #2207 へ移送)

- 再帰の機械語 (`0x180c9d813`: `[rsp+0x58]` (= out[2]) が非 0 なら `0x180c9d827` で `0x180c9d700` を再呼出し) は実機の機械語そのもの。
- 再帰を起こすのは「木に node があり、found 経路で `out[2]` が非 0」になること。`FA_NODE1` 無しでは found が 0/72 で、再帰は起きない。
- よって 2 回目の `C=Z` は、harness が node を注入したことで初めて発生する。実機で同じ再帰が起きるかどうかは、実機の controller map の中身 (node と値オブジェクト) に依存し、本ハーネスの空 map からは判定できない。
- 既定の判定 (`found=0`・`da6c00=0`) は変えない。FA-29 の full probe の ERR (2 回目の `[C+0x318]` poison deref) は、この注入 node に由来する副作用として記録する。

## 4. 測定 (測定 commit `ac6f1b77`, lift2 のコードを変えた最後の commit)

- `bash tools/targets/freshair/lift2/run_fa9.sh` (HEAD `ac6f1b77`): wall 5 s, load 0.13→0.20, **GATE PASS**
  - (a) base: ERR=0・ca1480=72・path=map・eq=1・found=0・da6c00=0
  - (b) alt: ERR=8/8 path=static / (b-wasm) alt: wasm ERR=8/8
  - (c) pert: 差分 395 トークン・L/R 同一 40 呼出・差分 0 呼出
- `run_ctrl 2 5` (同 run の末尾): **BIT-EXACT 15/15**, wall 4 s, rc=0
- 観測 (FA_CHAIN9, 1 回): 16 呼出 (注入 node あり) / 72 呼出 (無し)。再帰は注入 node ありの 8 本のみ。
- 測定 commit から HEAD までの lift2 差分: `git diff ac6f1b77 HEAD -- tools/targets/freshair/lift2` (本付録の commit は docs のみ)

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実機の controller map に node があるか (node の値オブジェクトが実機で `C` として再帰するか) | 2 回目の呼出が実機の挙動か harness 注入の副作用かは、実機の map 内容の観測が要る。本付録は「注入でのみ発生」までしか言えない | #2207 (FA-31) |
| full probe の 2 回目呼出の deref ガード (全 72 呼出で found/out0 を観測) | 既定 probe の「out0=0」は 1 回目のみ | 未起票 (PR 本文の未解決表) |
