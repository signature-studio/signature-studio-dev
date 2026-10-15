# REPORT 付録 3510 — #3510 [WIN-32] 到達ログ (GUI-REACH) の順序検査と e2e.sh への組込み

親: `tools/gui/REPORT.md` §21 (要約)・`tools/gui/REPORT_APPENDIX_W.md` (#3508・#3509 の節)。前提 #3508 (PR #3582) は merge 済み。

## 結論
- W 版ゲストの到達ログを機械検査する: 初回の出現順が `RegisterClassW` < `CreateWindowExW` < `WM_PAINT` 配送 < `BitBlt`。判定は `test/reach_order_check.py`。native 通し (`test/native_w_e2e.sh`) で PASS。
- ネガコン: WM_PAINT 配送の行を出さない旧 shim (`gui_core` に `GUI_REACH_LOG` を付けないビルド) の trace は FAIL (`WM_PAINT が無い`・rc 1)。
- `tools/gui/e2e.sh` に step 2c/6 (W 版の native 通し・統計・EXACT MATCH・順序検査) を追加。

## 変更
- `src/gui_core.c` `call_proc`: `GUI_REACH_LOG` のときだけ WM_PAINT の配送を記録 (SendMessage・DispatchMessage の両経路)。
- `src/gui_reach.c`: `gui_reach_paint()` と行 `GUI-MSG WM_PAINT <calls>` (初回到達の位置に出す)。既存の `GUI-REACH` 行の形式は変えない。
- `test/native_w_e2e.sh`: 改名 (`gui_rename.h`) + `gui_wrap_i64.c` の wrapper 経由で組む (`reach_test.sh`・`gui_wasm.sh reach` と同じ構成)。本番は `GUI_REACH_LOG` 付き、ネガコンは無し。
- `lift/gui_wasm.sh` reach: `gui_core.c` に `-DGUI_REACH_LOG` (wasm の trace も同じ行を出す。emsdk 無しのため未実行)。

## 検証 (測定 commit `383e9462a`・コミット済み HEAD・4 vCPU・load 0.33〜0.60)
| 項目 | 結果 |
|---|---|
| `native_w_e2e.sh` ×3 | rc 0・15.81 / 15.76 / 15.73 s。PASS 行 3/3・EXACT MATCH 3/3 (0/64,000 px)・sha256 `6f809bdf…` 3/3・改竄ネガコン MISMATCH 3/3 |
| 順序検査 (本番 trace) | PASS 3/3 (32 件の到達行) |
| 順序検査 (ネガコン: 旧 shim) | FAIL `WM_PAINT が無い` 3/3 (rc 1) |
| `reach_order_check.py --selftest` | 4/4 (正例 PASS。WM_PAINT 欠落・BitBlt の先行・CreateWindowExW の先行は FAIL) |
| `test/selftest.sh` (回帰 gate) | 512 passed, 0 failed (14.5 s) |
| `test/reach_test.sh` (e2e 2b) | 11 passed, 0 failed・adapt_test 28 passed・selftest 512 passed (17.8 s) |

本番 trace の抜粋 (`build/native_w_run.log`):
```
GUI-REACH 13 UpdateWindow 1 IMPL P0
GUI-MSG WM_PAINT 1
GUI-REACH 14 BeginPaint 1 IMPL P0
...
GUI-REACH 21 BitBlt 1 IMPL P0
```
`UpdateWindow` の同期配送で最初の WM_PAINT が届き、`BeginPaint`・`BitBlt` はその後に出る。

## 差分 (測定 commit から HEAD まで)
`git diff 383e9462a HEAD -- tools/gui/lift tools/gui/test tools/gui/golden tools/gui/src tools/gui/e2e` の出力は 0 行 (本付録と REPORT の索引を入れた commit は文書だけ)。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `tools/gui/e2e.sh` の 1 本通し (step 4 以降の wasm 段) | emsdk の素材 (`toolchain-emsdk`) が本 run に無い。wasm の GUI-MSG 行も未実測 | #3510 (`oc_artifacts` に `toolchain-emsdk` を足して再投入) |
| `tools/gui/flengine/e2e.sh` の回帰確認 | `tools/m11/work` (work-m11 素材) と emsdk が無く、前提欠如 (exit 2) で止まる。shim の変更は `GUI_REACH_LOG` 付きの時だけ効く (flengine の build は付けない) | #3510 (同上) |
| native_w_run の PASS 行と ExitProcess の `exit()` の競合 (#3508 から続く既存の構造) | 主スレッドの PASS 行より先に app スレッドが exit すると PASS 行が欠ける。3/3 では起きていない | PM 判断 (本 PR の範囲外) |
