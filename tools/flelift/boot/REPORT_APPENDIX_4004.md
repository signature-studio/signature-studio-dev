# FLE-18 (#4004): 既定経路の dispatch(0) (0x67264b の target 0)・[0x15e0a48] の呼出時実測

> 正本: `tools/flelift/boot/REPORT.md` §10 (#3060 の未達 3 件のうち 2 件は本付録で実測)。
> 測定は `fle6_measure.sh` (FLE_EXTRA_ROOTS= 空・FLE_BOOT_RUNS=default shim・`FLE_BOOT_WORK` は ws-4004 内の work)。
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
- 既定経路の `0x6b91e8` は `ippsZero_8u` 相当が未適用で、40 バイトのうち 20 バイトが非 0 のまま戻る。

## 3. exit 時の値 (REPORT §10 の記述との比較)

`ipp.call_slot` (終了時): 既定 `slot_15e0a48=0x15f34a0`・`obj_first_qword=0x0`、shim `slot=0x15f34a0`・`obj_first_qword=0x7f10001c`。
REPORT §10 は「終了時の `[0x15e0a48]` は shim 有で 0」と記したが、本測定では shim でも 0x15f34a0 だった (既存の `boot_summary_fle6.json` は 0 で、今回と一致しない)。
同じ commit 系列でも結果が変わるため、「終了時の slot が 0 に戻る」は実測の裏付けが無く、取り下げる。

## 4. 影響 (#4004 受入 3)

- 既定経路の 0x67264b は icall-miss で `ret 0` に戻るため、`ippsZero_8u` 相当の処理は走らない (len 0 の呼出しは実害なし)。
- 0x6b91e8 の呼出しは 40 バイトのゼロ埋めを飛ばす。`dst=0x12d677d0` のバッファを後で読むかは**未確認**。
  よって「silent miscompile が起きる」とは言えない (未確定)。出力メモリの全体 hash は既定と shim で異なる
  (`boot_summary_fle4004_default.json` / `boot_summary_fle4004.json` の `outmem.full`) が、GetMem 数の差 (1,890 / 2,313) も含むため、この差を 0 埋めの影響とは切り分けていない。

## 5. KPI (起動・GUI の PR)

- units_run: 前 209 → 後 209 (差 0)。
- 最初のウィンドウ: 未到達 (停止点は unit 209 の後の `MessageBoxA` → `exit(0)`、REPORT §10 と同じ)。

## 6. 再現

```sh
FL_WIN64_DIR=<[WIN64] の展開先> FLE_EXTRA_ROOTS= FLE_BOOT_RUNS="default shim" FLE_BOOT_TAG=fle4004 \
  FLE_BOOT_WORK=<repo>/tools/flelift/work/boot4004 bash tools/flelift/boot/fle6_measure.sh
grep -a '\[slot\]' tools/flelift/work/boot4004/run_fle4004_*.log
```

素材: `oc_artifacts: fl-win64 toolchain-emsdk` (fl-win64 は `[WIN64]` の展開先に展開)。
