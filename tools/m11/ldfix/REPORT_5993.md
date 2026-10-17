# #5993 (LD-294): first-deref-not-entry 関数群 A (10 関数) の survey 到達理由の記録 (#3194 受入 4 の分割)

**判定: 達成**。10 関数それぞれについて、survey (942 unit) で到達しない理由を呼び出し元と計装の届かない経路で記録した (§3)。修復は行っていない。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| 10 関数 (101d180, 1050f90, 10626e0, 10628d0, 12f9730, 5c44b0, 6905f0, 75a180, 786d50, 787380) について、survey で到達しない理由 (呼び出し元・計装の届かない経路) を関数ごとに REPORT に記録する | **達成** (§3) |

## 2. 測定

- 測定 commit: 本 PR のコード commit (`ldfix/survey_reason_5993.py` を追加した commit)。
- IR: `m11_gen_ir2.sh` (rc 0・ldfix=applied・`boot_final.ll` 490790 行) → `m11_build.sh` (rc 0・wasm-ld signature mismatch 0 / undefined symbol 0)。素材は `fl-win64` の `block00031_PE.bin` のみを展開、`toolchain-emsdk` を `/opt/emsdk` で使用。`work-m11` は `work/` に既存のものを使った。
- 計装: `ldfix/reach_509.sh` (`reach_survey.mjs`、942 unit、kind は ok/miss/oob/halt0/noproc)。
- 対照 (同じ build): 44f040 = 3 unit、47ad70 = 7 unit。REPORT_1325 §4 と一致し、計装が機能していることを確認。
- 出力: `results/reach_5993.json` (27 関数 = 10 対象 + 直接呼び出し元 17、全 942 unit)、`results/reach_5993_roots.json` (14 関数 = 対象 10 + 閉包の根 4)。
- 実行時間 (実測): reach 1 回 18.3 s。gen_ir2 53.9 s、build 25.5 s。

### 2.1 直接呼び出し元の計装結果

27 関数を計装 (942 unit)。10 対象と直接呼び出し元 17 は **全て 0 unit で入口通過 0**。

### 2.2 閉包の根の計装結果

| 根 (IR に直接呼び出し元が無い) | 入口に hit した unit (kind) | 対象の入口 hit |
|---|---|---|
| 12ddfe0 | 895 (oob) | 0 |
| 1306110 | 898 (**ok**) | 0 |
| 623840 | 114 (halt0) | 0 |
| ebb3b0 | 745 (oob) | 0 |

`kind=ok` で根に hit したのは 1306110 (unit 898) の 1 件だけ。この unit でも対象は入口に入らなかった。

## 3. 関数ごとの理由

「閉包」は IR の直接 call を逆向きに辿った推移閉包 (`ldfix/survey_reason_5993.py`)。閉包の根は、IR に直接呼び出し元が無く、`m11_tr_function_*` のラッパ参照 (間接呼び出し経路) からだけ届く関数。

| 関数 | IR の直接呼び出し元 | 閉包の大きさ | 閉包の根 | 根の survey 結果 | 対象の survey 結果 | 理由 |
|---|---|--:|---|---|---|---|
| 101d180 | 1016600・1019da0・101b780 | 215 | 12ddfe0・1306110 | 895 (oob)・898 (ok) | 0 unit | 根 1306110 は ok unit 898 で入るが対象へ進まない。根 12ddfe0 は oob でしか入らない |
| 1050f90 | ddf630・e3d440 | 190 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |
| 10626e0 | e2a280 | 197 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |
| 10628d0 | 12d1760・e391b0 | 191 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |
| 12f9730 | de43b0 | 195 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |
| 5c44b0 | 5c5170 | 9 | 623840 | 114 (halt0) | 0 unit | 閉包が 9 関数と小さく、根 623840 は halt0 unit でしか入らない。ok で届く経路が無い |
| 6905f0 | 690b40・690f00・69b340 | 236 | 12ddfe0・1306110・ebb3b0 | 895 (oob)・898 (ok)・745 (oob) | 0 unit | 根 1306110 は ok unit 898 で入るが対象へ進まない。ebb3b0 は oob でしか入らない |
| 75a180 | 759e10 | 194 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |
| 786d50 | 787f20・78bab0 | 330 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |
| 787380 | 7878c0・787f20・78bab0 | 330 | 12ddfe0・1306110 | 同上 | 0 unit | 同上 |

- **閉包に unit proc は 0 件** (941 unit proc のうち、どの閉包にも含まれない)。survey の unit 入口から直接 call で届く対象は無い。
- 「根 1306110 が ok で入るのに対象へ進まない」は、その unit では対象へ至る分岐が取られない、または間接呼び出し先が対象に届かない、ことを示す。どちらかは未確認 (§4 U-1)。
- 5c44b0 は閉包 9 関数で、他の 9 件より遥かに小さい。根 623840 は ok unit では入らない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U-1 根 1306110 (ok unit 898) から対象へ至らない分岐・間接呼び先の特定 (閉包の中間関数を計装していない) | 10 関数の到達条件の正確な形は未確定。survey 上の到達 0 は確定 | 本 issue の残件として PR 本文の未解決表に記載。未特定の関数別の分岐条件は新規 issue 扱い |
| U-2 m11_tr ラッパの間接テーブルの参照経路 (どのスロットが根を呼ぶか) | 根が「間接経路でしか届かない」ことは IR の参照から確認、スロットの特定は未実施 | 同上 |
| U-3 5c44b0 の理由 (REPORT_930 で未特定だった点) | 閉包が小さいため原因の候補は絞れるが、分岐条件の確定は未実施 | 同上 |

## 5. 再現

```
cd tools/m11
python3 ldfix/survey_reason_5993.py work/boot_final3.ll <unit VA 出力> results/reason_5993.json
EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash ldfix/reach_509.sh <VA 列> results/reach_5993.json
```

unit VA 出力は `ldfix/unitva_5993.mjs` で作る (`node ldfix/unitva_5993.mjs <m11_probe.cjs> work/m11_image.bin <out>`)。`results/unitva_5993.txt` に 942 行 (0 = proc 無し) を同梱する。
