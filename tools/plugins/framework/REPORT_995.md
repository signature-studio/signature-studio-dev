# #995 REPORT — FW_EXT_FUNCS 指定経路の入力差替え (hs_e2e の HS_WFW) [P0c-14]

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID に一致する類型は無い。Phase B の OOB は #2115 の追跡対象)。

親: #610。未達の受入の移管先は既存 issue: Phase B の OOB → #2115、fw_269 の smoke 検査 gate → #2510。子 #2767 は閉じた (再測定のみの子は起票しない)。#1283 (親: #1253) は受入の一部が重なるが #995 の子ではない。前提の経緯は `REPORT_2571.md`。

## 1. 結論

- `hs_e2e.sh` の入力 dir を環境変数 `HS_WFW` で差し替えられるようにした (未指定時の既定は従来と同じ `tools/plugins/work/fw`)。入力は**絶対パス**で指定する。相対パスは `cd` 後に解決されて前提不足で止まる (§3)。ext 版の `fw_flat4_canon3.ll` を hs_e2e が読む経路ができた (受入 4 の機械部分)。
- 実行コードは測定 commit `e14a1a5d` から変えていない。修正 commit `0ea83831` は header コメントのみ。`cb10e458` の realpath 化は取り下げた (実行コードを変えると WORKFLOW §6 で再測定が必要になり、この run では素材が無く再測定できないため)。
- ext 版 (4 関数) で hs_e2e を実行: Phase A は PASS、Phase B は `memory access out of bounds` で FAIL (`rec=7`)。hs_e2e の PASS は未達 (→ #2115)。
- ext 版 fw_269_verify: stage2 の SMOKE は PASS。smoke 検査 gate は FAIL (`runerr=1`・`init_reach≠288`)。`REPORT_2571.md` §7 の既存 FAIL (#2510) と同種。
- 既定 wasm との比較は同一 HEAD ではない (§4)。同一 HEAD の既定測定は未実施。

## 2. 受入条件の判定

| # | 判定 | 根拠 |
|---|---|---|
| 1 | 一覧は達成・選定根拠は未達 | 41 関数の一覧 (issue #995 のコメント)。選定根拠は ext 版 hs_e2e の PASS 後に確定 (→ #2115・#2510) |
| 2 | 未達 | fw_269_verify の gate FAIL・hs_e2e FAIL (§3) (→ #2510・#2115) |
| 3 | 達成 (n=1・別 commit 比較) | ext wasm 15,075,735 B (測定 commit `e14a1a5d`)。既定 15,062,173 B は `a67af27b` の同一 run 対で測られた値 (§4)。同一 HEAD の比較は未実施 |
| 4 | 機械部分は達成・PASS は未達 | `HS_WFW` で ext canon3 を読ませて `hs_e2e.sh --fresh` を実行 (§3)。結果は FAIL (→ #2115) |

## 3. 実測 (n=1・測定 commit `e14a1a5d`)

計測の素材: stage-1 dir (`toolchain-emsdk`・`work-fw-stage1` を使う stage-1/stage-2 の成果物)。取得元の run は記録が残っておらず未確認。本 run の `$ARTIFACTS_DIR` は `fl-win64` のみで、emsdk (`[EMSDK]`) も無いため、この run では再実行していない。

| 手順 | 結果 | 所要 | load (1/5/15 分) |
|---|---|---|---|
| `FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0 bash fw_269_verify.sh <stage-1 dir>` | ext=4 skip=0 (rewritten 26/10/49/71)。stage2 `SMOKE PASS dispatch=38 units_done=0 ff=0`。smoke 検査 FAIL (`runerr=1` 期待 0、`init_reach=16` (run.log) / `-1` (smoke1-3.log) 期待 288)。wasm 15,075,735 B | 6 分 54 秒 (ログ mtime 由来: 17:32:08→17:39:02) | 未記録 |
| `HS_WFW=<上の W>/fw bash hostshim/hs_e2e.sh --fresh` | Phase A `dispatch=38 ff=0` PASS。Phase B `memory access out of bounds`・`status=0xffffffff plug=0x0 rec=7`・`E2E FAIL: 1 項目` | 162 秒 | 終了時 1.05 1.64 1.03 (開始時は未記録) |

- 上の実測は測定 commit `e14a1a5d` の `hs_e2e.sh` で行った。その後、実行コードは変わっていない。`git diff e14a1a5d HEAD -- tools/plugins/framework tools/plugins/p0c ':!*.md'` の出力は次の 1 件のみで、header コメントの 2 行だけ (実行行の差分は 0):

```diff
diff --git a/tools/plugins/framework/hostshim/hs_e2e.sh b/tools/plugins/framework/hostshim/hs_e2e.sh
index 451305be..61eafc90 100755
--- a/tools/plugins/framework/hostshim/hs_e2e.sh
+++ b/tools/plugins/framework/hostshim/hs_e2e.sh
@@ -4,7 +4,8 @@
 #   bash hs_e2e.sh --fresh    # IR patch / table / emcc を作り直し
 #   bash hs_e2e.sh --observe  # 判定なし観測モード (GOLDEN 固定前の ID 序列観測)
 #   HS_WFW=<dir> bash hs_e2e.sh --fresh  # 入力 dir を差し替え (FW_EXT_FUNCS の ext 版 canon3 で検証)。
-#                                        # 増分判定は WFW を見ないため、差し替えるときは必ず --fresh
+#                                        # 絶対パスで指定する (相対パスは cd 後に解決されて前提不足になる)。
+#                                        # 増分判定は WFW の fw_flat4_canon3.ll と fw_rt.c の mtime だけを見るため、差し替えるときは必ず --fresh
 #
 # 前提: CAB-194 の framework lift 済み (tools/plugins/framework/fw_stage2.sh 完走)。
 #   本 script は framework 成果物を **読み取りのみ** で利用する:
```

- よって §3 の実測は HEAD の実行コードに対するものとして扱う (WORKFLOW §6: 差分 0 なら再測定は不要)。
- 相対パスの前提チェック (HEAD `0ea83831`): `HS_WFW=tools/plugins/framework/work/fakewfw bash hostshim/hs_e2e.sh --fresh` → `[hs] 前提不足: tools/plugins/framework/work/fakewfw/fw_flat4_canon3.ll (fw_stage2.sh を先に実行)` (rc 1)。絶対パスは §6。
- 修正後の hs_e2e ext 再測定 (素材が要る) と同一 HEAD の既定 wasm 測定は未実施 (§5)。

## 4. 既定 wasm との比較 (同一 HEAD ではない)

- 既定の参照値: `tools/plugins/framework/REPORT_P0c9.md` の「再測定」節 (P0c-16 run・HEAD `a67af27b`・クリーン HEAD 展開・`fw_269_verify.sh` の ALL PASS)。ext 15,075,739 B / 既定 15,062,173 B、`cmp` DIFF (byte 94 から)。ext と既定が同一 run 対・同一 commit で測られている。
- `REPORT_2571.md` §3 (測定 commit `133d8b11`) は wasm サイズを含まないため、比較の基準から外した。
- 測定 commit `a67af27b` から HEAD `0ea83831` までの差分 (`git diff --stat a67af27b HEAD -- tools/plugins/framework tools/plugins/p0c ':!tools/plugins/framework/REPORT_995.md'` の出力。REPORT_995 は本 stat の出所なので除外。この後の commit は REPORT_995 と `docs/DOC_MAP.md` のみのため stat は変わらない):

```
 tools/plugins/framework/REPORT_1229.md             |  60 ++++++
 tools/plugins/framework/REPORT_1478.md             |  62 ++++++
 tools/plugins/framework/REPORT_1609.md             |  95 +++++++++
 tools/plugins/framework/REPORT_1848.md             |  94 +++++++++
 tools/plugins/framework/REPORT_1890.md             |  54 +++++
 tools/plugins/framework/REPORT_1891.md             |  88 +++++++++
 tools/plugins/framework/REPORT_1933.md             |  72 +++++++
 tools/plugins/framework/REPORT_1935.md             |  50 +++++
 tools/plugins/framework/REPORT_2008.md             | 205 +++++++++++++++++++
 tools/plugins/framework/REPORT_2016.md             |  77 ++++++++
 tools/plugins/framework/REPORT_2069.md             |  77 ++++++++
 tools/plugins/framework/REPORT_2070.md             |  69 +++++++
 tools/plugins/framework/REPORT_2115.md             | 220 +++++++++++++++++++++
 tools/plugins/framework/REPORT_2115_APPENDIX.md    |  52 +++++
 tools/plugins/framework/REPORT_2425.md             | 126 ++++++++++++
 tools/plugins/framework/REPORT_2426.md             |  90 +++++++++
 tools/plugins/framework/REPORT_2510.md             | 181 +++++++++++++++++
 tools/plugins/framework/REPORT_2571.md             |  69 +++++++
 tools/plugins/framework/REPORT_P0c9.md             |  26 ++-
 tools/plugins/framework/fw_269_verify.sh           |   2 +-
 tools/plugins/framework/fw_boot.c                  |   6 +-
 tools/plugins/framework/fw_hostfix.py              |  24 +++
 tools/plugins/framework/fw_pack_stage1.sh          |   2 +-
 tools/plugins/framework/fw_rt.c                    |   6 +-
 tools/plugins/framework/fw_smoke_check.py          |  52 ++++-
 tools/plugins/framework/hostshim/REPORT_DISPATCHER.md |  95 ++++++++-
 tools/plugins/framework/hostshim/hs_callee_disasm.py |  28 ++-
 tools/plugins/framework/hostshim/hs_disp_emu.py    |  16 +-
 tools/plugins/framework/hostshim/hs_e2e.sh         |   5 +-
 tools/plugins/framework/hostshim/hs_irfix.py       | 112 +++++++++--
 tools/plugins/framework/hostshim/hs_plug.c         |  17 ++
 tools/plugins/framework/hostshim/hs_preinit.mjs    |  36 ++++
 tools/plugins/p0c/REPORT.md                        |  58 ++++++
 tools/plugins/p0c/REPORT_APPENDIX_E.md             |  83 +-------
 tools/plugins/p0c/REPORT_APPENDIX_E2.md            |  95 +++++++++
 tools/plugins/p0c/REPORT_APPENDIX_H.md             |  87 ++++++++
 tools/plugins/p0c/check_report_split.sh            |  27 +--
 tools/plugins/p0c/p0c_e2e.sh                       |   2 +-
 38 files changed, 2387 insertions(+), 133 deletions(-)
```

- wasm のビルド入力 (`fw_rt.c`・`fw_boot.c` が含まれる) がこの差分に入るため、既定 wasm は `a67af27b` の 15,062,173 B から変わりうる。ext 値も `a67af27b` (15,075,739 B) と本 PR の `e14a1a5d` (15,075,735 B) で 4 B 違う。この差は同一 HEAD でない比較の誤差の目安として扱う。
- 同一 HEAD の既定測定は未実施 (素材 `toolchain-emsdk`・`work-fw-stage1` が本 run の `$ARTIFACTS_DIR` に無い)。→ §5。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| hs_e2e ext 版の PASS (Phase B の OOB・`rec=7`。原因の追跡は #2115) | 受入 2・4 の PASS | #2115 |
| fw_269_verify ext 版の smoke 検査 gate FAIL (原因の追跡は #2510) | 受入 2 の fw_269 PASS | #2510 |
| x87 関数の選定根拠 (受入 1 の残り) | ext 版 hs_e2e の PASS 後に確定 | #2115・#2510 (PASS 後) |
| 同一 HEAD の既定 wasm 測定と ext との比較 (§4)。素材 (`oc_artifacts`) のある run で `fw_269_verify.sh` (FW_EXT_FUNCS 未指定) を回す | 受入 3 の比較を同一 HEAD にする | 本表のみ (再測定のみのため子は起票しない) |

## 6. 再現

素材: `oc_artifacts: fl-win64 toolchain-emsdk work-fw-stage1` (retdec 不要)。stage-1 成果物は `tools/plugins/work/fw/` に置く。`fw_269_verify.sh` は `cd` の後に SRC を読み、`hs_e2e.sh` は `cd` の後に入力を読むため、入力は絶対パスで渡す (相対パスは失敗する)。

```
R="$(git rev-parse --show-toplevel)"
FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0 bash "$R/tools/plugins/framework/fw_269_verify.sh" "$R/tools/plugins/work/fw"
HS_WFW="$R/tools/plugins/framework/work/verify_269/fw" bash "$R/tools/plugins/framework/hostshim/hs_e2e.sh" --fresh
```

`--fresh` は必須。増分判定は WFW の `fw_flat4_canon3.ll` と `fw_rt.c` の mtime だけを見る (`fw_imports.json`・`fw_simd.c`・`fw_boot.c`・`fw_rt.h` は見ない)。差し替え時に判定から漏れる入力があるため、差し替えたら `--fresh` で作り直す。`work/verify_269/fw/` は既定と ext で共有するため、切り替えるときは削除してから実行する。
