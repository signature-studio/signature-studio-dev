# #995 REPORT — FW_EXT_FUNCS 指定経路の入力差替え (hs_e2e の HS_WFW) [P0c-14]

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID に一致する類型は無い。Phase B の OOB は #2115 の追跡対象)。

親: #610。残件の追跡先: #1283 (OPEN・受入条件が重なる)。前提の経緯は `REPORT_2571.md`。

## 1. 結論

- `hs_e2e.sh` の入力 dir を環境変数 `HS_WFW` で差し替えられるようにした (未指定時の既定は従来と同じ `tools/plugins/work/fw`)。ext 版の `fw_flat4_canon3.ll` を hs_e2e が読む経路ができた (受入 4 の機械部分)。
- ext 版 (4 関数) で hs_e2e を実行: Phase A は PASS、Phase B は `memory access out of bounds` で FAIL (`rec=7`)。hs_e2e の PASS は未達。Phase B の OOB は #2115 の追跡対象。
- ext 版 fw_269_verify: stage2 の SMOKE は PASS。smoke 検査 gate は FAIL (`runerr=1`・`init_reach≠288`)。`REPORT_2571.md` §7 の既存 FAIL (#2510) と同種。

## 2. 受入条件の判定

| # | 判定 | 根拠 |
|---|---|---|
| 1 | 一覧は達成・選定根拠は未達 | 41 関数の一覧 (issue #995 のコメント)。選定根拠は ext 版 hs_e2e の PASS を前提にするため未確定 (→ #1283) |
| 2 | 未達 | fw_269_verify の gate FAIL・hs_e2e FAIL (§3) |
| 3 | 達成 (n=1) | ext wasm 15,075,735 B。同一 HEAD の既定 wasm との比較は未実施 (§4) |
| 4 | 機械部分は達成・PASS は未達 | `HS_WFW` で ext canon3 を読ませて `hs_e2e.sh --fresh` を実行 (§3)。結果は FAIL |

## 3. 実測 (n=1・測定 commit `e14a1a5d`・コミット済み HEAD)

| 手順 | 結果 | 所要 | load (1/5/15 分) |
|---|---|---|---|
| `FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0 bash fw_269_verify.sh <stage-1 dir>` | ext=4 skip=0 (rewritten 26/10/49/71)。stage2 `SMOKE PASS dispatch=38 units_done=0 ff=0`。smoke 検査 FAIL (`runerr=1` 期待 0、`init_reach=16` (run.log) / `-1` (smoke1-3.log) 期待 288)。wasm 15,075,735 B | 6 分 54 秒 (ログ mtime 由来: 17:32:08→17:39:02) | 未記録 |
| `HS_WFW=<上の W>/fw bash hostshim/hs_e2e.sh --fresh` | Phase A `dispatch=38 ff=0` PASS。Phase B `memory access out of bounds`・`status=0xffffffff plug=0x0 rec=7`・`E2E FAIL: 1 項目` | 162 秒 | 終了時 1.05 1.64 1.03 (開始時は未記録) |

## 4. 未実施 (本 run の時間内に入らず)

- **同一 HEAD での既定経路 (FW_EXT_FUNCS 未指定) の再測定**。比較の基準は `REPORT_2571.md` §3 (測定 commit `133d8b11`) だが、その後 main に `hs_irfix.py` +64 行 (#2426 系) が入っており、同一 HEAD の比較ではない。`git diff --stat 133d8b11 e14a1a5d -- tools/plugins/framework` は 5 files・+407 / −1。
- ext と既定の Phase B 結果の比較は、issue #995 のコメントにある 8135c29c の実測 (既定・ext とも同じ OOB) に依る。
- n≥3 の所要の min–max。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| hs_e2e ext 版の PASS (Phase B の OOB・`rec=7`) | 受入 2・4 の PASS | #1283 (OPEN)・#2115 (OPEN) |
| fw_269_verify の smoke 検査 gate FAIL (`runerr=1`・`init_reach≠288`) | 受入 2 の fw_269 PASS | #2510 (OPEN) |
| 同一 HEAD の既定経路との突合せ (§4) | 受入 3 の比較根拠 | #1283 |
| 選定根拠 (受入 1 の残り) | ext 版 hs_e2e の PASS 後に確定 | #1283 |

## 6. 再現

素材: `oc_artifacts: fl-win64 toolchain-emsdk work-fw-stage1` (retdec 不要)。stage-1 成果物は `tools/plugins/work/fw/` に置く。

```
FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0 bash tools/plugins/framework/fw_269_verify.sh tools/plugins/work/fw
HS_WFW=tools/plugins/framework/work/verify_269/fw bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh
```

`--fresh` は必須 (増分判定は WFW を見ないため、差し替え時に古い中間生成物を再利用する)。
