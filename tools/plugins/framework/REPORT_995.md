# #995 REPORT — FW_EXT_FUNCS 指定経路の入力差替え (hs_e2e の HS_WFW) [P0c-14]

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID に一致する類型は無い。Phase B の OOB は #2115 の追跡対象)。

親: #610。未達の受入の移管先: #2767 (親: #995)。#1283 (親: #1253) は受入の一部が重なるが #995 の子ではない。前提の経緯は `REPORT_2571.md`。

## 1. 結論

- `hs_e2e.sh` の入力 dir を環境変数 `HS_WFW` で差し替えられるようにした (未指定時の既定は従来と同じ `tools/plugins/work/fw`)。相対パスは `cd` の前に絶対化する (修正 commit `cb10e458`)。ext 版の `fw_flat4_canon3.ll` を hs_e2e が読む経路ができた (受入 4 の機械部分)。
- ext 版 (4 関数) で hs_e2e を実行: Phase A は PASS、Phase B は `memory access out of bounds` で FAIL (`rec=7`)。hs_e2e の PASS は未達。Phase B の OOB は #2115 の追跡対象。
- ext 版 fw_269_verify: stage2 の SMOKE は PASS。smoke 検査 gate は FAIL (`runerr=1`・`init_reach≠288`)。`REPORT_2571.md` §7 の既存 FAIL (#2510) と同種。
- 既定 wasm との比較は同一 HEAD ではない (§4)。同一 HEAD の既定測定と修正後の hs_e2e ext 再測定は #2767。

## 2. 受入条件の判定

| # | 判定 | 根拠 |
|---|---|---|
| 1 | 一覧は達成・選定根拠は未達 | 41 関数の一覧 (issue #995 のコメント)。選定根拠は ext 版 hs_e2e の PASS を前提にするため未確定 (→ #2767) |
| 2 | 未達 | fw_269_verify の gate FAIL・hs_e2e FAIL (§3) (→ #2767) |
| 3 | 達成 (n=1・別 commit 比較) | ext wasm 15,075,735 B (測定 commit `e14a1a5d`)。既定 15,062,173 B は `a67af27b` の同一 run 対で測られた値 (§4)。同一 HEAD の比較は未実施 (→ #2767) |
| 4 | 機械部分は達成・PASS は未達 | `HS_WFW` で ext canon3 を読ませて `hs_e2e.sh --fresh` を実行 (§3)。結果は FAIL (→ #2767) |

## 3. 実測 (n=1・測定 commit `e14a1a5d`)

| 手順 | 結果 | 所要 | load (1/5/15 分) |
|---|---|---|---|
| `FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0 bash fw_269_verify.sh <stage-1 dir>` | ext=4 skip=0 (rewritten 26/10/49/71)。stage2 `SMOKE PASS dispatch=38 units_done=0 ff=0`。smoke 検査 FAIL (`runerr=1` 期待 0、`init_reach=16` (run.log) / `-1` (smoke1-3.log) 期待 288)。wasm 15,075,735 B | 6 分 54 秒 (ログ mtime 由来: 17:32:08→17:39:02) | 未記録 |
| `HS_WFW=<上の W>/fw bash hostshim/hs_e2e.sh --fresh` | Phase A `dispatch=38 ff=0` PASS。Phase B `memory access out of bounds`・`status=0xffffffff plug=0x0 rec=7`・`E2E FAIL: 1 項目` | 162 秒 | 終了時 1.05 1.64 1.03 (開始時は未記録) |

- 上の ext 測定は修正前の `hs_e2e.sh` で行った。測定 commit から修正 commit `cb10e458` までの `hs_e2e.sh` の差分は次のとおり (変更は `WFW` の絶対化とコメントのみ。絶対パスの入力では挙動は変わらない):

```diff
diff --git a/tools/plugins/framework/hostshim/hs_e2e.sh b/tools/plugins/framework/hostshim/hs_e2e.sh
index 451305be..60d388f3 100755
--- a/tools/plugins/framework/hostshim/hs_e2e.sh
+++ b/tools/plugins/framework/hostshim/hs_e2e.sh
@@ -4,7 +4,8 @@
 #   bash hs_e2e.sh --observe  # 判定なし観測モード (GOLDEN 固定前の ID 序列観測)
 #   HS_WFW=<dir> bash hs_e2e.sh --fresh  # 入力 dir を差し替え (FW_EXT_FUNCS の ext 版 canon3 で検証)。
-#                                        # 増分判定は WFW を見ないため、差し替えるときは必ず --fresh
+#                                        # 相対パスも可 (cd の前に絶対化する)。増分判定は WFW の fw_flat4_canon3.ll と
+#                                        # fw_rt.c の mtime だけを見るため、差し替えるときは必ず --fresh
 #
 # 前提: CAB-194 の framework lift 済み (tools/plugins/framework/fw_stage2.sh 完走)。
 #   本 script は framework 成果物を **読み取りのみ** で利用する:
@@ -20,7 +21,7 @@ HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
 source "$HERE/../../../shared/env.sh"
 T="$REPO_ROOT"
 FW="$T/tools/plugins/framework"
-WFW="${HS_WFW:-$T/tools/plugins/work/fw}"
+WFW="$(realpath -m -- "${HS_WFW:-$T/tools/plugins/work/fw}")"
 W="$T/tools/plugins/work/hs"
 H="$HERE"
 FRESH=0
```

- 修正後の前提チェック (相対パス): 空の入力 dir (gitignore 対象の `tools/plugins/framework/work/fakewfw`) で `HS_WFW=tools/plugins/framework/work/fakewfw bash hostshim/hs_e2e.sh --fresh` を実行した。
  - 修正前 (`ece73d7f`): `[hs] 前提不足: tools/plugins/framework/work/fakewfw/fw_flat4_canon3.ll (fw_stage2.sh を先に実行)` (rc 1)。
  - 修正後 (`cb10e458`): 前提チェックを通過し、後段の `hs_irfix` で入力が空のため停止 (`[hs_irfix] function_6bdde0 が見つからない`・rc 1)。E2E の判定はこの入力では行っていない。
- 修正後の `hs_e2e` ext 再測定は未実施。`work/verify_269/fw` (stage-1 + stage-2 の成果物) が本 run の素材に無いため (→ #2767)。

## 4. 既定 wasm との比較 (同一 HEAD ではない)

- 既定の参照値: `tools/plugins/framework/REPORT_P0c9.md` の「再測定」節 (P0c-16 run・HEAD `a67af27b`・クリーン HEAD 展開・`fw_269_verify.sh` の ALL PASS)。ext 15,075,739 B / 既定 15,062,173 B、`cmp` DIFF (byte 94 から)。ext と既定が同一 run 対・同一 commit で測られている。
- `REPORT_2571.md` §3 (測定 commit `133d8b11`) は wasm サイズを含まないため、比較の基準から外した。
- 測定 commit `a67af27b` から修正 commit `cb10e458` までの差分 (`git diff --stat a67af27b cb10e458 -- tools/plugins/framework tools/plugins/p0c` の出力):

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
 tools/plugins/framework/REPORT_995.md              |  53 +++++
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
 39 files changed, 2440 insertions(+), 133 deletions(-)
```

- wasm のビルド入力 (`fw_rt.c`・`fw_boot.c` が含まれる) がこの差分に入るため、既定 wasm は `a67af27b` の 15,062,173 B から変わりうる。ext 値も `a67af27b` (15,075,739 B) と本 PR の `e14a1a5d` (15,075,735 B) で 4 B 違う。この差は同一 HEAD でない比較の誤差の目安として扱う。
- 同一 HEAD の既定測定は未実施 (素材 `toolchain-emsdk`・`work-fw-stage1` が本 run の `$ARTIFACTS_DIR` に無い)。→ #2767。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| hs_e2e ext 版の PASS (Phase B の OOB・`rec=7`。原因の追跡は #2115) | 受入 2・4 の PASS | #2767 (親: #995) |
| fw_269_verify ext 版の smoke 検査 gate FAIL (原因の追跡は #2510) | 受入 2 の fw_269 PASS | #2767 |
| 同一 HEAD の既定 wasm 測定と ext との比較 (§4) | 受入 3 の比較の根拠 | #2767 |
| 修正後 script での hs_e2e ext 再測定 (§3) | 修正 commit の実測 | #2767 |
| 選定根拠 (受入 1 の残り) | ext 版 hs_e2e の PASS 後に確定 | #2767 |

## 6. 再現

素材: `oc_artifacts: fl-win64 toolchain-emsdk work-fw-stage1` (retdec 不要)。stage-1 成果物は `tools/plugins/work/fw/` に置く。`fw_269_verify.sh` は `cd` の後に SRC を読むため、絶対パスで渡す (相対パスは stage-1 欠落で失敗する)。`hs_e2e.sh` の HS_WFW は `cb10e458` で `cd` の前に絶対化した。`work/verify_269/fw/` は既定と ext で共有するため、切り替えるときは削除してから実行する。

```
R="$(git rev-parse --show-toplevel)"
FW_EXT_FUNCS=function_5dfd30,function_5dfdb0,function_5de820,function_5dedf0 bash "$R/tools/plugins/framework/fw_269_verify.sh" "$R/tools/plugins/work/fw"
HS_WFW="$R/tools/plugins/framework/work/verify_269/fw" bash "$R/tools/plugins/framework/hostshim/hs_e2e.sh" --fresh
```

`--fresh` は必須。増分判定は WFW の `fw_flat4_canon3.ll` と `fw_rt.c` の mtime だけを見る (`fw_imports.json`・`fw_simd.c`・`fw_boot.c`・`fw_rt.h` は見ない)。差し替え時に判定から漏れる入力があるため、差し替えたら `--fresh` で作り直す。
