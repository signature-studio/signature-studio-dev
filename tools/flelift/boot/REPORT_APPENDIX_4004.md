# FLE-18 (#4004): 既定経路の dispatch(0) (0x67264b の target 0)・[0x15e0a48] の呼出時実測

> 訂正元: `tools/flelift/boot/REPORT.md` §10 (#3060 の未達 3 件のうち 2 件は本付録で実測)。
> 測定は `fle6_measure.sh` (FLE_EXTRA_ROOTS= 空・FLE_BOOT_RUNS=default shim・`FLE_BOOT_WORK` は `tools/flelift/work/boot4004`)。
> 測定 commit: 本付録と同じ commit (コードを変えた最後の commit)。

## 1. 数値の変化 (#4004 受入 1)

既定経路 (root 無し・`FLE_IPP` 未指定) の units 209 / GetMem 1,890 / FreeMem 776 は REPORT §2・§10 と**変わらない** (差 0)。
shim 有 (`FLE_IPP=1`) は units 209 / GetMem 2,313 / FreeMem 1,199 (2 回測定で同値)。REPORT §10 の 2,314 とは 1 差。
変化の理由は未確認 (測定 commit が異なるため、1 差の原因は区別していない)。

## 2. 呼出時の [0x15e0a48] (#4004 受入 2)

probe は `fle_ff` の `unlifted` 経路で、戻り番地 `[rsp]` が `0x67264d` (呼出点 0x67264b の戻り) または `0x6b91e8` のときに 1 行出す。
`[0x15e0a48]` は呼出時の値 (slot)、`[slot]` は slot 先頭の qword (呼出し先の関数ポインタ)。

| route | ret | `[0x15e0a48]` (呼出時) | `[slot]` (= target) | dst | len | dst の非 0 バイト |
|---|---|---|---|---|---|---|
| 既定 | 0x67264d | 0x15f34a0 | 0x0 (`dispatch(0)`) | 0x0 | 0x0 | - |
| 既定 | 0x6b91e8 | 0x15f34a0 | 0x0 (`dispatch(0)`) | 0x12d677d0 | 0x28 | 20 / 40 |
| shim | 0x67264d | 0x15f34a0 | 0x7f10001c (`ippsZero_8u`) | 0x0 | 0x0 | - |
| shim | 0x6b91e8 | 0x15f34a0 | 0x7f10001c (`ippsZero_8u`) | 0x12d677d0 | 0x28 | 20 / 40 |

- 呼出時の slot は両 route とも `0x15f34a0`。違うのは `[0x15f34a0]` の中身 (既定 0 / shim は token `0x7f10001c`)。
- `ippsZero_8u` の呼出しは 2 回で、呼出元は 0x67264d (len 0) と 0x6b91e8 (len 0x28) の 2 件。`0x6b91e8` は `0x67264b` 以外の呼出点で、REPORT §10 の「唯一の呼出し点」は誤り。
  (REPORT §10 の `ipp.called` の site 欄は初回呼出元だけを記録するため、2 回目の呼出元 0x6b91e8 は出ない。)
- 既定経路の `0x6b91e8` は `ippsZero_8u` 相当が未適用。**測定は呼出し時 (エントリ) の dst の内容**で、40 バイトのうち 20 バイトが呼出し時に非 0 (ゼロ埋め前)。戻った後の内容は**未測定**。

## 3. exit 時の値 (REPORT §10 の記述との比較)

`ipp.call_slot` (終了時): 既定 `slot_15e0a48=0x15f34a0`・`obj_first_qword=0x0`、shim `slot=0x15f34a0`・`obj_first_qword=0x7f10001c`。
REPORT §10 は「終了時の `[0x15e0a48]` は shim 有で 0」と記したが、本測定では shim でも 0x15f34a0 だった (既存の `boot_summary_fle6.json` は 0 で、今回と一致しない)。
今回の測定では shim でも `0x15f34a0` だった。「終了時の slot が 0 に戻る」は本測定では確認できず、取り下げる。

## 4. 影響 (#4004 受入 3)

- 既定経路の 0x67264b は icall-miss で `ret 0` に戻るため、`ippsZero_8u` 相当の処理は走らない (len 0 の呼出しは実害なし)。
- 0x6b91e8 の呼出しは 40 バイトのゼロ埋めを飛ばす (呼出し時に 20 バイトが非 0)。戻り後に `dst=0x12d677d0` を読むかは**未確認** (戻り後の内容は未測定)。
  よって「silent miscompile が起きる」とは言えない (未確定)。
- 出力メモリの hash (`outmem.full`) は**同じコードの 2 回の実行で変わった** (既定: `fc3ef797…` → `b6aaf6c2…`)。
  そのため出力の一致・不一致を影響の根拠に使えない。出力の正しさの判定は本付録の範囲外。

## 5. KPI (起動・GUI の PR)

- units_run: 前 209 → 後 209 (差 0)。
- 最初のウィンドウ: 未到達 (停止点は unit 209 の後の `MessageBoxA` → `exit(0)`、REPORT §10 と同じ)。

## 6. 測定 commit と HEAD の差分 (lift 出力の一致)

測定 commit `3c16e6fcc` から HEAD `469490b60` までの `tools/flelift/` の差分は `x64c.py` (VEX 語彙の追加・movnti 等) と `tests/x64c_vex_diff.py` のみ。`fle_boot.c` の差分は 0 行。
`x64c.py` の差分が boot closure の lift 出力を変えないことを、両 commit で同じ入力 (`gen_boot.py`・`FLE_EXTRA_ROOTS=0x6a7b70`・`x64c.py` の引数は `fle6_measure.sh` と同じ) から lift して確かめた。

| 項目 | 測定 commit `3c16e6fcc` | HEAD `469490b60` |
|---|---|---|
| `fle_entries_boot.json` | 同一 | 同一 |
| `fle_lifted_s0.c`〜`s7.c` (8 shard) | 全て byte 一致 (`cmp`) | 同左 |
| `lift_meta.json` | 同一 | 同一 |
| 全 shard 合計 | 161,689,300 B | 同左 |

`s0.c` の sha256 先頭は両方 `3bbad183e5856933f33e`、`lift_meta.json` は `a5297b964d7641bf465f`。
したがって lift 出力は変わらず、既存の測定 (units 209 / GetMem 1,890 / FreeMem 776 / shim 2,313 / 0x15f34a0) は HEAD の実行コードに対しても有効とみなす。
(注: 最初の HEAD の gen は `FLE_EXTRA_ROOTS` を外して実行し entries が一致しなかったが、入力の指定ミスで、コードの差分ではない。同じ環境で取り直して一致を確認した。)
emsdk は runner に無いため boot の再実行はしていない (lift までの一致のみ確認)。

## 6-b. #4426 受入 1: 0x6b91e8 の未適用が出力に影響するか (読出し監視・部分達成)

測定 commit: 70eae885a (origin/main 859f67429 の上に `FLE_RWATCH` を足したもの。既定ビルドは診断無効で、既定経路は変えていない)。

- 既定 (`FLE_IPP=0`・診断無効) の HEAD 再測定: units_run 209 / ptr_15F34A0 0x0 / IPP_CHECK ok。前回 (b92f450c5) の記録と一致。lift 83 s・clang 102 s・boot 10 s。
- 既定 `FLE_IPP` 未指定は、main 側で mode 3 (ILT 分岐入力) が既定になっていた。units 895 になるため、受入 1 の測定は `FLE_IPP=0` で行う。
- dst の位置: この run の dst は `0x12d777d0` (前回の `0x12d677d0` と 0x100000 ずれる)。監視範囲はこの値で測る (`-DFLE_RWATCH_LO/HI`)。
- 読出し監視 (`FLE_RWATCH`・`LD*`/`LDX`/`LDYSPLIT` に入る): dst+0x18〜+0x27 の guest 読出しは 17 件。読出し元は次のとおり。
  - `f_409c80` を `0x4080a7` から呼ぶ箇所の 16 バイト読出し 10 件 (構造体の複写と見られる)
  - `f_44f5d0` を `0x43c4e7` から呼ぶ箇所の 2 バイト読出し 4 件 (`0x2e` と比べる UTF-16 走査に見える)
  - `f_409c80` を `0x43c557` から呼ぶ 8 バイト読出し 1 件、`fle_lifted_s6.c:33493` の 8 バイト読出し 1 件、`0x1159fa00` 由来 2 バイト 1 件 (戻り番地が不正値のため呼出し元は未確認)
  - `fle_boot.c:305` の 16 件は診断コード自身の `nonzero` 計数で、guest の読出しではない。
- 残骸を読んだ値が後続の計算にどう流れるかは未確認。影響の有無はこの流れで決まるため、受入 1 は未達。
- 出力比較 (`image_writable`・`outmem_compare.py` の定義): 既定 (IPP=0) を 2 回実行すると不一致 (`d945…` と `f463…`)。差は `.data` 4 バイト (`0x13a5010`・`0x13e4d58`) と `.bss` 3 バイト (`0x15f26e8`〜`0x15f26ea`) で、前回の既知の非決定位置と同じ。dst 残骸 (+0x18〜+0x27) の差は 0 件。
- IPP=0 と IPP=1 (`ippsZero_8u` 実行 = 残骸なし) の `image_writable` は不一致。ただし、この差が残骸の影響か非決定位置の揺れかは、この 1 組では分けられない。
- 結論: 0x6b91e8 の未適用は、残骸の読出し (17 件) が確認されたので「影響なし」とは言えない。影響の有無は、読出し値の流れの追跡 (f_409c80・f_44f5d0 の戻り先) と、非決定位置を除いた比較の 2 組で判定する。未確認。

## 7. 再現

```sh
FL_WIN64_DIR=<[WIN64] の展開先> FLE_EXTRA_ROOTS= FLE_BOOT_RUNS="default shim" FLE_BOOT_TAG=fle4004 \
  FLE_BOOT_WORK=<repo>/tools/flelift/work/boot4004 bash tools/flelift/boot/fle6_measure.sh
grep -a '\[slot\]' tools/flelift/work/boot4004/run_fle4004_*.log
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk` (fl-win64 は `[WIN64]` の展開先に展開)。
