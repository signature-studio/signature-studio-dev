# #3195 (LD-149): first-deref-not-entry の見送り 10 組の不能理由の記録 — 判定の再測定

**判定: 見送り 10 組の不能理由をすべて記録。修復は 0 組**。#1325 の見送り 10 組を、本体 `ldfix.py` と同じ `Machine` (PE 直読) で判定し直した。コードは変えていない (`ldfix.py` の差分 0 行)。10 組はすべて門の判定で止まる (下記 §2)。12f9730 は arg3 が `rep-not-dominated` (3 回連続で一致)。同関数の arg2 は entry 経路で 2 件置換されるが、これは見送り 10 組の外の別経路である (§5)。

測定 commit: 本 PR の HEAD (base は `origin/main` `43cabef4c`)。`ldfix.py` は base から変えていない (§4)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 見送り 10 組のそれぞれを、修復する、または不能理由を関数ごとに REPORT に記録する | **達成** (修復 0 組。全 10 組の理由を §2 に記録。判定は本体と同じ `Machine` で測った) |
| 修復した組は、survey (ok 退行 0) と `ldfix_509_e2e.sh` 7/7 で確認する | **該当なし** (本 PR で修復した組は無い。e2e は走らせていない) |

## 2. 関数ごとの判定 (本体 `Machine`、`ldfix/residual_3195.py`)

列: keep = 機械語の生の使用数 / rep = 置換対象の数。判定は `fix_f3c_use` の門の順。

| 組 | 最初の deref | B (IR) | keep/rep | 判定 | 不能理由 |
|---|---|---|---|---|---|
| 101d180 arg3 | 101d477 | 101d469 | 0/3 | rep-not-dominated | 置換対象の使用が B に支配されない。`fix_f3c_use` は not_dom |
| 10626e0 arg3 | 1062752 | 1062752 | 1/1 | rep-not-dominated | 同上 (not_dom) |
| 12f9730 arg3 | 12f9872 | 12f986d | 0/2 | rep-not-dominated | 同上 (not_dom)。3 回連続の実行で一致 (§5) |
| 41a670 arg1 | 41a6a0 | 41a69c | 2/2 | rep-not-dominated | 同上 (not_dom)。`fix_ld108` (LD-112) の対象関数 |
| 786d50 arg3 | 787019 | 786fe7 | 0/1 | rep-not-dominated | 同上 (not_dom) |
| 787380 arg3 | 78753f | 787523 | 0/1 | rep-not-dominated | 同上 (not_dom) |
| 1050f90 arg2 | 1051098 | 1051070 | 3/1 | w32 | 32bit deref を含む。既存の門は 64bit 限定 |
| 1050f90 arg3 | 105114c | 105112e | 3/1 | w32 | 同上 |
| 10628d0 arg1 | 10628d8 | (無し) | 1/2 | no-ir-block | 最初の deref の機械語ブロック先頭に対応する IR ブロックが無い |
| 6905f0 arg2 | 69072a | 69071c | 7/0 | raw-after(3) | **REPORT_1325 の説明を訂正** (§3) |

修復できるかの判定は、`dom_1325.py` (ImageMachine) では `dominated` だった 6905f0 を含めて、本体 `Machine` で行う。

注記: `residual_3195.py` は entry ブロックにある引数 (最初の deref が B の先頭ブロック内) を表示せず飛ばす。そのため、同じ関数で entry 経路の置換が起きても表に現れない。12f9730 の arg2 がこれに当たる (§5)。

## 3. 6905f0 の訂正 (REPORT_1325 §3・§8 U-2)

REPORT_1325 は 6905f0 を「支配は成立するが、前段パスとの相互作用で IR が変わらない」とした。この「前段パスとの相互作用」という説明は取り下げる (相互作用の有無は確認していない)。

- `dom_1325.py` は `ImageMachine` で機械語の使用を数える。この読み方では生の使用が最初の deref より後に無く、`dominated` と判定された。
- 本体の `ldfix.py` は `Machine` (PE 直読) で数える。この読み方では、最初の deref (69072a) の後に生の使用が 3 件 (6883330・6883505・6883928) ある。`fix_f3c_use` の門 (b) で `raw-after` となり、置換は行われない (ゲートの条件から決まる)。
- 単独の `fix_f3c_use` を `Machine` で呼ぶと、6905f0 は `replaced=0 dom=0 not_dom=0` (門 (b) で止まるため、支配の判定に届かない)。今回の再実行 (§4) でも同じ値。

よって 6905f0 の不能理由は「生の使用の位置 (機械語の 3 件)」である。REPORT_1325 §6 の修復 11 関数 (40fe90〜f552a0) は 6905f0 を含まず、本体パイプラインの `f3c_use_dom` 11 と一致する (再測定 §4)。修復済み 11 組の内容は変わらず、誤ったのは 6905f0 の理由の記述だけである。

## 4. 再現・コード差分

- 入力: `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst` (`tools/m11/work/`)・`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/m11/work extracted/block00031_PE.bin`。`work-m11` は PR 本文の `oc_artifacts: fl-win64 work-m11` で取得する。
- 実行: `cd tools/m11 && python3 ldfix/residual_3195.py work/extracted/block00031_PE.bin` (前回測定 0.7 秒・rc 0)。
- 再測定 (測定 commit `7935ba4b0`、素材 `work-m11` + `fl-win64` の `block00031_PE.bin`。`work/boot_final3.ll` は `work-m11` 展開物):
  - `python3 ldfix/residual_3195.py work/extracted/block00031_PE.bin`: 3 回連続で出力 md5 `044cf4af123b382bd749b4177a0a658a` (一致)。12f9730 の行は毎回 `replaced=2 dom=0 not_dom=1`。
  - `python3 ldfix/dom_1325.py <out.json>`: 21 秒・合計 487 組 / 452 関数 (`raw-after` 445 / `no-rep-use` 12 / `rep-not-dominated` 6 / `w32` 10 / `no-ir-block` 2 / `dominated` 12)。REPORT_1325 §3 と一致。
  - `python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe work/extracted/block00031_PE.bin --report out.json`: 33 秒・rc 0・`F3c=43`・`f3c_use_dom` 11・`f3c_use_not_dom` 7・`f3c_use_replaced` 80・errors 0。REPORT_1325 §6 の 43 と一致。
  - 本体 IR の差分: `function_12f9730` は `boot_final3.ll` に対して 6 行の差 (arg2 の entry 経路の置換 2 件・`%ldfxu4` の追加)。arg3 の置換は無い。
- `ldfix.py` の差分: `git diff 43cabef4c HEAD -- tools/m11/ldfix/ldfix.py` は 0 行 (`ldfix.py` は変えていない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U-1 修復対象 11 関数と c62780 の動的確認 | 修復の正しさは survey の到達 3 関数以外で未確認 | #3194 (LD-148) |
| U-3 B 先頭の load 配置の安全性 (806740 は unexec で動的確認不可) | 11 組の修復値が機械語と一致するかが未確認 | #3194 (LD-148) |
| U-4 c62780 の `ldfxn` 採番のずれ | §6 の説明は推定のまま | #3194 (LD-148) |
| 残り 6 組 (rep-not-dominated) の修復方式。B 以外からの経路で値を使う形を表す設計が必要 | 6 組は現状のまま | 未起票 (設計判断。PM が起票を判断) |
| 残り 3 組 (w32) の 32bit 版の門。`fix_f3c_use` の 64bit 限定の拡張 | 3 組は現状のまま | 未起票 (PM が起票を判断) |
| `REPORT_930` の 23/24 と 30/33 の不一致 (REPORT_1325 §8 の既存行) | 分類の母集団の差 | #1134 (既存) |

## 6. w32 の門の決定 (#6067 / LD-297)

**決定: `fix_f3c_use` の 32bit deref の門は開けない (64bit 限定のまま)**。1050f90 arg2・arg3 は見送りのまま。コードは棄却の counter (`f3c_use_w32`) を足しただけで、IR は変えていない。

根拠 (1050f90 の機械語と IR):

- 置換対象の `%argN` は、store の宛先ポインタ (`store i32 %54, ptr (inttoptr %arg2)`・`store i32 %59, ptr (inttoptr %arg3)`) である。
- 32bit deref (`mov ecx, dword ptr [rbx]` 0x1051098・`mov ecx, dword ptr [rsi]` 0x105114c) は、同じ宛先を直前に store した値の読み直し。arg3 側は間に直接 call (0x664090) がある。
- 門を開けて probe すると (一時コピー・門だけ外す)、`%55 = inttoptr i64 %arg2` が `inttoptr i64 %ldfxu1` (`*arg2` の内容 = 格納前の値) に置換される。宛先を格納値に取り違えるので、32bit 版の門は誤った IR になる。

測定 (測定 commit: 本 PR の HEAD、base `50e2f813b`、素材 `work-m11` + `fl-win64` の `block00031_PE.bin`):

- `python3 ldfix/residual_3195.py work/extracted/block00031_PE.bin`: rc 0・0.7 秒。出力 md5 `044cf4af123b382bd749b4177a0a658a` (§4 と一致)。
- `python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe ...`: base と HEAD の出力 IR が `cmp` で一致 (IR 差 0)。`f3c_use_replaced` 80・`f3c_use_dom` 11・`f3c_use_w32` 95 (棄却数の新 counter)。`f3c_fns` は base でも 42 (§4 の 43 は別測定の値。本 PR では変えていない)。
- 同じ判定で w32 になる組は他にもある: 784790 arg2・105f2e0 arg1・dc1a30 arg2 (`residual_3195.py` の既定 VA 外の関数、`residual_3195.py` の表示では同じ w32 門)。決定は同じ理由で全体に効く。
- `ldfix_509_e2e.sh` は実行していない。IR が base と byte 一致のため、修復後 wasm は変わらない (門の変更なし)。

未解決:

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1050f90 arg2・arg3 (w32・store 宛先の reload 形) の修復方式。宛先の store 値を使う形を表す設計が必要 | 2 組は現状のまま | 未起票 (設計判断。PM が起票を判断) |

12f9730 の事実 (3 回連続の実行と probe で確認): `fix_f3c_use` は 12f9730 で毎回 `replaced=2 dom=0 not_dom=1`。`replaced=2` は arg2 の分で、arg2 の最初の deref (`19896141`) は entry ブロックにあり、`fix_f3c_use` の entry 経路で 2 件置換される。単独 probe でも `{'f3c_use_replaced': 2, 'f3c_use_not_dom': 1}` だった。`not_dom` は arg3 の分で、不能理由は rep-not-dominated (§2)。見送り 10 組の判定は arg3 についてのもので、arg2 の置換は本体パイプラインで実際に起きている (§4 の IR 差分)。過去の「呼出しごとに戻り値が変わる」という記述は、arg2 の entry 経路と取り違えた誤りで、取り下げる。
