# #860 M2p (10 進 inttoptr VA→LVA) の hang 切り分けと halt0 残 unit の再測定 (2026-10-13)

**判定: 部分達成 (受入 1 は未達・受入 2〜4 は未達)。** 本 run は再現手順の確定と、M2p ON/OFF の full-sequence 実測まで。
ハングの原因特定と 10 進 inttoptr の仕分け表は未着手で、子 issue に残す (§5)。

## 1. 測定の基準

- IR: `bash tools/m11/m11_gen_ir2.sh` で再生成 (`work-m11` の旧 IR は `ir_conditions.json` 無しで build 不可のため)。
  ldfix=applied、`F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=48 errors=0`。生成 36 s (17:27:18〜17:27:54 UTC)。
- PE: `fl-win64` 素材 (`block00031_PE.bin`)。capstone 5.0.7 / pefile を venv で導入 (runner の system pip は不可)。
- build: `m11_build.sh` 24 s、`wasm-ld signature mismatch 0 / undefined symbol 0`。
- 測定: `node tools/m11/trap_triage/survey_units.mjs <out.json>`、load average 0.58。
- 基準 HEAD: `origin/main` `986e7415` (worktree `ws-860`、branch `860-m11-m2p-decimal-inttoptr`)。

## 2. 実測 (full sequence)

| 構成 | 結果 | 所要 |
|---|---|---|
| M2p OFF (既定) | `ok 869 / miss 47 / halt0 8 / oob 16 / other 1 / noproc 1` | 10.25 s |
| M2p ON (`M11_M2P=1`) | survey が 800 s (timeout) で完走せず (exit 124)。IR は `M2p` で 4364 件 remap、build は成功 | 800 s 超 |

- M2p ON の進捗 (`SV_PROG=1`) は 240 s で unit 880 まで。同じ位置で 2 回止まった。
  unit 880 を単独 (`SV_ONLY`) で走らせると 0.30 s で `oob` を返す。**ハングは単独の unit に局在しない** (前の unit の状態が次へ持ち越される)。
- 旧記録 (REPORT.md §6-2) の「unit 503 でハング」は、本 IR では再現せず。503 は OFF の full sequence で `ok`、ON の sequence でも 503 は通過している (停止は 880)。
- 「前の unit の状態が次へ持ち越される」は推定。未検証 (持ち越し状態の特定は未着手)。

**注意**: `SV_ONLY=<unit>` の単独実行は、どの unit でも OFF/ON 両方が `oob` になり、full sequence と一致しない。
unit ごとの遷移 (halt0→ok など) は単独実行では測れない。遷移の判定は full sequence の per-unit JSON で行うこと。

## 3. halt0 残 8 の内訳 (OFF, full sequence)

`halt0_classify.py` の結果: `function_412770` 8 件 (units 114, 245, 279, 314, 368, 509, 647, 895)。
REPORT §6-1 の「`411d20` 系 6 件」とは内訳が異なる (IR が再生成されたため)。`412770` の呼出元の分類は未調査。

## 4. 仕分けの状態

10 進 inttoptr の「VA→LVA にすべき / VA のまま正しい」の仕分け表は**未作成** (受入 2)。
M2p ON の unit 遷移の表 (受入 3) も、full sequence が 800 s 超のため完成していない。

## 5. 未解決 (起票先)

- M2p ON の survey ハングの原因 (前 unit の状態持ち越し・ループの特定。`SV_PROG` で unit 880 付近まで) → 子 issue (§6)。
- 10 進 inttoptr 4364 件の仕分け表 (受入 2)・M2p 有無の unit 遷移 (受入 3)・既定 ON の是非 (受入 4) → 同子 issue。
- halt0 8 (`412770` 系) の個別原因 → 同子 issue。

## 6. 再現

```sh
bash tools/m11/m11_gen_ir2.sh                       # FL_WIN64_DIR と capstone/pefile が要る
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs work/trap_triage/off.json          # ~10 s
M11_M2P=1 bash tools/m11/m11_gen_ir2.sh && M11_M2P=1 bash tools/m11/m11_build.sh
SV_PROG=1 timeout 240 node tools/m11/trap_triage/survey_units.mjs work/trap_triage/on.json   # unit 880 で止まる
```
