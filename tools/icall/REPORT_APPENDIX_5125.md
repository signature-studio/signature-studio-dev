# tools/icall 付録: icall 代表 e2e の before/after 一致の実測 (#5125 / 親 #4245)

本体 `REPORT.md` §0 からの参照。before/after 一致の実測の正本。

## 1. 結論

- before `706147914` と after `e5261de58` (main HEAD) で、`bash tools/icall/icall_e2e.sh` (モード無し) を同一入力・同一 toolchain で実行し、**両方 `[icall_e2e] PASS`**。
- 監査 (OTT F 非IAT間接call 落ち 70 → 0 / tail-jmp 11 → 0 / jump table 8 件展開)、matrix (89 scenario / 50,236 cell 全 bit 一致・max_ulp 0・state_diff 0 qword)、CRT 関数単位 gate (crt_fn_gate PASS) は両方で同じ値。
- 差分は `tools/icall` 等の別 commit の変更のみで、icall の判定値は変わっていない。

## 2. 測定条件

| 項目 | before | after |
|---|---|---|
| commit | `706147914` (detached worktree `ws-5125-before`) | `e5261de58` (branch `5125-icall-e2e-before-after`, base origin/main) |
| 実行 | `bash tools/icall/icall_e2e.sh` (foreground) | 同左 |
| 所要 (wall) | 1 分 54.7 秒 (`real 0m1:54.743s`) | 2 分 2.4 秒 (`real 2m2.394s`) |
| load (開始 → 終了) | 1.95 → 2.38 | 0.87 → 2.34 |
| 環境 | GitHub Actions runner (4 core, 15 GiB) | 同左 |
| 判定 | PASS (RC 0) | PASS (RC 0) |

所要は、route build 〜 matrix 〜 crt gate の全体を含む。`icall_e2e.sh` の既定モード (`--small` / `--full` は無し) で測定。

## 3. 結果表 (実測)

| 項目 | before `706147914` | after `e5261de58` |
|---|---|---|
| route build | OK | OK |
| unit (test_icall.py) | RESULT PASS (0 failed) | RESULT PASS (0 failed) |
| stk_value_gate (12/12・ネガコン 0/12) | (未存在: 本 commit に `tests/stk_value_gate.sh` 無し・#5339 で追加) | PASS |
| OTT F 非IAT間接call 81 | 落ち 70 → 0 | 落ち 70 → 0 |
| tail-jmp 11 | 落ち 11 → 0 | 落ち 11 → 0 |
| jump table 8 | RetDec 未解決 1 → 8 展開 | RetDec 未解決 1 → 8 展開 |
| 監査判定 | PASS | PASS |
| matrix | 89 scenario / failed 0 / cells 50,236 / equal 50,236 / max_ulp 0 / state_diff 0 qword | 同左 |
| crt_fn_gate | PASS | PASS |
| icall_e2e | **PASS** | **PASS** |

## 4. 前提素材と手順 (再現用)

- 素材 (`$ARTIFACTS_DIR` に実在を確認後に展開): `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`analysis-ott-binaries` → `$ANALYSIS_DIR` 直下の `plugins/` (`PLUGINS_DIR=$ANALYSIS_DIR/plugins`)、`work-m6-ott` / `work-icall` / `work-liftlib` → 各 worktree の `tools/*/work/`、`toolchain-retdec` / `toolchain-emsdk` → 展開先 (`docs/REFERENCES.md` の `[RETDEC]` `[EMSDK]` 参照)。
- 素材の展開時間: 約 82 秒 (7 本のうち 4 本を直列展開、`fl-win64` 除く)。
- 実行手順は素材展開後に `bash tools/ott/ott_e2e.sh` を 1 回 (native 参照 `libottnative.so` の作り直し)、続けて `bash tools/icall/icall_e2e.sh`。
- 前提の注意 (本 run で実測):
  - `tools/icall/ott_route.sh` 等は `[EMSDK]` と `[RETDEC]` の既定位置を直書きする。素材の展開先がそこと違う run では、既定位置へのリンクが要る。
  - `work-m6-ott` 同梱の `libottnative.so` は `ott_enc_slots` を持たず、icall の matrix が 89 scenario すべて `undefined symbol` で失敗した。`tools/ott/ott_e2e.sh` で作り直すと解消 (作り直し後 `ott_enc_slots` が 1 件)。作り直し後の matrix は両 commit で 50,236 cell 全一致。

## 5. 差分 (測定 commit から HEAD まで)

`git diff --stat 706147914 e5261de58 -- tools/icall tools/ott tools/liftlib tools/shared tools/x64c tools/flelift` = 205 files changed, 23,312 insertions, 1,103 deletions。
うち実行経路 (`tools/icall/icall_e2e.sh`・`tools/icall/ott_route.sh`・`tools/ott`・`tools/m6`) に限ると 19 files changed, 355 insertions, 32 deletions。
差分はあるが、上記の判定値 (監査・matrix・crt gate) は before/after で一致した。

## 6. 本 run で起きた副作用 (要報告)

- `[EMSDK]` と `[RETDEC]` の下に `ln -sfn` でリンクを作った際、`-f` が `[EMSDK]` 側の git 管理の `emsdk` スクリプトを上書きした。`git status` で型変更 (`T`) を確認し、HEAD の内容から書き戻して元に戻した (mode 100755・git status は clean)。`[RETDEC]` 側に作った新規リンクは削除した。
- この作業は runner 上の共有ディレクトリに対するもので、本 PR の repo には含まれない。
