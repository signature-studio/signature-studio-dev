# #1043: unit 368 の 409470 VA-big 確保 (転記あり halt0 / なし ok) の原因切り分け

親: #861 (受入 4 の持ち越し先)。前提: `main` `49bca5e6`。

## 1. 確保呼び出し列 (受入 1)

測定条件は survey と同じ (unit 0..367 を先に実行し、unit 368 を実行; 予算 0)。`m11_vabig_probe.mjs 368 --pre=0-367` (`M11_VA_UNIT_BUDGET_MB=0`)。

- HEAD (M2q 無効): `function_981000` が `409470` を呼ぶ VirtualAlloc の要求は 125.3 MB ×9 と 832.1 MB (`size=872480768`) の順。832 MB の確保で wasm の 2 GiB 上限を超え halt0。
- 修正後 (M2q 有効): 125.3 MB ×9 は残るが 832 MB は出ない。unit 368 は `ret=1, trap=null` で完走。

832 MB 要求の発生源は `function_980ed0` の `mov edx,[rax]` (VA 0x15e4080 の int32 = n) → `981000(self, n)` → `409470`。n は `8×((8n+31)&~31)` で決まる。

## 2. 原因の類型 (受入 2)

IR (`work/boot_final.ll`, M2q 無効) で `%ce0n11_function_980ed0 = inttoptr i64 22954112 to ptr` が **VA のまま** (LVA 18759808 = VA−0x400000 に remap されていない)。
RetDec がこの 1 件だけ 10 進で出し、`pass_m2` (16 進のみ対象) を素通りした。linear 0x15e4080 は image 外で、読んだ値 (n) が build ごとに変わる (REPORT_APPENDIX §5 の 190.6 MB / 700.7 MB と一致)。

類型: VA→LVA remap 漏れ (10 進 `inttoptr` 命令)。`docs/DEFECTS.md` の該当類型は「絶対アドレスの未 remap」(M2p の対象と同じ型)。

## 3. 修復 (受入 2)

`tools/m11/m11_passes.py` に `pass_m2q_fn980ed0` を追加し `main()` で `pass_m2` の直後に呼ぶ。`function_980ed0` の定数 22954112 (VA 0x15e4080) を `shiftva` で LVA 18759808 に直す。

全件 remap の `M11_M2P=1` は unit 503 で survey がハングするため使わない (既定 OFF のまま)。この修復は 1 件に限定する。

## 4. 実測 (受入 3・4)

| 構成 | ok | miss | other | halt0 | oob | noproc | 測定 |
|---|--:|--:|--:|--:|--:|--:|---|
| M2q 無効 (NC = HEAD) | 869 | 47 | 1 | 8 | 16 | 1 | 本 run の HEAD 版 IR で build 23.9 s / survey 12.5 s (IR 再生成 40.6 s) |
| M2q 有効 (修復) | 870 | 47 | 1 | 7 | 16 | 1 | 修復版 IR 再生成 (M2q 1 sites) / build OK / survey 12.2 s |

per-unit 比較 (NC → 修復):

- 変化: unit 368 の `halt0 → ok` の 1 件のみ。
- ok → 非 ok: **0 件** (受入 4 を満たす)。
- wasm-ld signature mismatch 0 / undefined symbol 0。

## 5. 未解決

- unit 368 の 125.3 MB 確保 ×9 は残る (予算 0 でも完走)。これが実機で必要かは未確認。
- unit 888 の `129f140` (load 脱落・71.3 MB) は #513 系の別件 (REPORT_APPENDIX)。本件の範囲外。
- 修復の真偽 (unit 368 が正しい結果を出すか) は kind が ok になったことのみで判定。出力の正しさは未検証。

## 6. 再現

```sh
export FL_WIN64_DIR=$HOME/analysis/win64 ANALYSIS_DIR=$HOME/analysis RETDEC_ROOT=$HOME/tc/retdec
bash tools/m11/m11_gen_ir2.sh
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs out.json   # ok 870 / halt0 7 が期待値
```
