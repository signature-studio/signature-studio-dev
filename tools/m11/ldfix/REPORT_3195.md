# #3195 (LD-149): first-deref-not-entry の見送り 10 組の不能理由の記録 — 判定の再測定

**判定: 受入条件 (不能理由の関数ごとの記録) を達成、修復は 0 組**。#1325 の見送り 10 組を、本体 `ldfix.py` と同じ `Machine` (PE 直読) で判定し直した。修復は 0 組 (コードは変えていない)。`fix_f3c_use` の支配判定を広げれば直る組は無い (下記 §2 の 10 組はすべて門で止まる)。

測定 commit: 本 PR の HEAD (base は `origin/main` `43cabef4c`)。`ldfix.py` は base から変えていない (§4)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 見送り 10 組のそれぞれを、修復する、または不能理由を関数ごとに REPORT に記録する | **達成** (修復 0 組。全 10 組の理由を §2 に記録。判定は本体と同じ `Machine` で測った) |
| 修復した組は、survey (ok 退行 0) と `ldfix_509_e2e.sh` 7/7 で確認する | **該当なし** (修復した組が 0 のため、e2e は走らせていない) |

## 2. 関数ごとの判定 (本体 `Machine`、`ldfix/residual_3195.py`)

列: keep = 機械語の生の使用数 / rep = 置換対象の数。判定は `fix_f3c_use` の門の順。

| 組 | 最初の deref | B (IR) | keep/rep | 判定 | 不能理由 |
|---|---|---|---|---|---|
| 101d180 arg3 | 101d477 | 101d469 | 0/3 | rep-not-dominated | 置換対象の使用が B に支配されない。`fix_f3c_use` は not_dom |
| 10626e0 arg3 | 1062752 | 1062752 | 1/1 | rep-not-dominated | 同上 (not_dom) |
| 12f9730 arg3 | 12f9872 | 12f986d | 0/2 | rep-not-dominated | 同上 (not_dom)。ただし同関数の `fix_f3c_use` の戻りは 1 回目 `replaced=2`・2 回目 `replaced=1 dom=1` で一致しない (§5) |
| 41a670 arg1 | 41a6a0 | 41a69c | 2/2 | rep-not-dominated | 同上 (not_dom)。`fix_ld108` (LD-112) の対象関数 |
| 786d50 arg3 | 787019 | 786fe7 | 0/1 | rep-not-dominated | 同上 (not_dom) |
| 787380 arg3 | 78753f | 787523 | 0/1 | rep-not-dominated | 同上 (not_dom) |
| 1050f90 arg2 | 1051098 | 1051070 | 3/1 | w32 | 32bit deref を含む。既存の門は 64bit 限定 |
| 1050f90 arg3 | 105114c | 105112e | 3/1 | w32 | 同上 |
| 10628d0 arg1 | 10628d8 | (無し) | 1/2 | no-ir-block | 最初の deref の機械語ブロック先頭に対応する IR ブロックが無い |
| 6905f0 arg2 | 69072a | 69071c | 7/0 | raw-after(3) | **REPORT_1325 の説明を訂正** (§3) |

修復できるかの判定は、`dom_1325.py` (ImageMachine) では `dominated` だった 6905f0 を含めて、本体 `Machine` で行う。

## 3. 6905f0 の訂正 (REPORT_1325 §3・§8 U-2)

REPORT_1325 は 6905f0 を「支配は成立するが、前段パスとの相互作用で IR が変わらない」とした。これは誤り。

- `dom_1325.py` は `ImageMachine` で機械語の使用を数える。この読み方では生の使用が最初の deref より後に無く、`dominated` と判定された。
- 本体の `ldfix.py` は `Machine` (PE 直読) で数える。この読み方では、最初の deref (69072a) の後に生の使用が 3 件 (6883330・6883505・6883928) ある。`fix_f3c_use` は `raw-after` で門を通らず、全パス実行でも IR は変わらない。
- 単独の `fix_f3c_use` を `Machine` で直接呼ぶと、6905f0 は `replaced=0` (変化なし)。前段パスとの相互作用は無い。

よって 6905f0 は「支配の問題」ではなく「生の使用の位置 (機械語の 3 件)」で止まっている。REPORT_1325 §6 の修復 11 関数 (40fe90〜f552a0) は 6905f0 を含まず、本体パイプラインの `f3c_use_dom` 11 と一致する (再測定 §4)。つまり修復済み 11 組の内容は変わらず、誤ったのは 6905f0 の理由の記述だけである。

## 4. 再現・コード差分

- 入力: `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst` (`tools/m11/work/`)・`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/m11/work extracted/block00031_PE.bin`。
- 実行: `cd tools/m11 && python3 ldfix/residual_3195.py work/extracted/block00031_PE.bin` (実測 0.7 秒・rc 0)。
- 比較の実測: `python3 ldfix/dom_1325.py <out.json>` は 26.8 秒・合計 487 組 (`raw-after` 445 / `no-rep-use` 12 / `rep-not-dominated` 6 / `w32` 10 / `no-ir-block` 2 / `dominated` 12)。REPORT_1325 §3 の合計と一致。
- `ldfix.py` 全 pass は 41 秒・F3c=43 (REPORT_1325 §6 の 43 と一致)。`6905f0` は差分 0 (`same`)。
- コード差分: `git diff <測定 commit> HEAD -- tools/m11/ldfix/ldfix.py` は 0 行 (`ldfix.py` は変えていない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U-1 修復対象 11 関数と c62780 の動的確認 | 修復の正しさは survey の到達 3 関数以外で未確認 | #3194 (LD-148) |
| U-3 B 先頭の load 配置の安全性 (806740 は unexec で動的確認不可) | 11 組の修復値が機械語と一致するかが未確認 | #3194 (LD-148) |
| U-4 c62780 の `ldfxn` 採番のずれ | §6 の説明は推定のまま | #3194 (LD-148) |
| 残り 6 組 (rep-not-dominated) の修復方式。B 以外からの経路で値を使う形を表す設計が必要 | 6 組は現状のまま | 未起票 (設計判断。PM が起票を判断) |
| 残り 3 組 (w32) の 32bit 版の門。`fix_f3c_use` の 64bit 限定の拡張 | 3 組は現状のまま | 未起票 (PM が起票を判断) |
| `REPORT_930` の 23/24 と 30/33 の不一致 (REPORT_1325 §8 の既存行) | 分類の母集団の差 | #1134 (既存) |
| 12f9730 の `fix_f3c_use` 戻り値が呼び出しごとに違う (1 回目 `replaced=2`・単独の 2 回目 `replaced=1 dom=1`)。`f3c_track` / `FnMach` の状態依存を疑うが未確認 | 判定の再現性。修復 0 組の結論には影響しない (どの呼び方でも 10 組は修復されない) | 未起票 (PM が起票を判断) |
