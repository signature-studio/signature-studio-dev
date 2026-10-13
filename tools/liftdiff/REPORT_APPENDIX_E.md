# liftdiff REPORT 付録 E (分割移動)

## 10. 旧記録: OTT 旧 chain (D1〜D6) の Actions 再現 (LD-8 / #406) — 未検証時点の記述

本文は `REPORT_APPENDIX.md` §10 に置き換えた。以下は `ebf5114a` 時点の記述を移動したもの (250 行上限のため分割移動)。repo 外絶対パスは `$HOME/analysis` に正規化した (AGENTS.md §4.1)。本節の数値は**未検証・申告値 (`ebf5114a` 時点)** であり、実測の正本は `REPORT_APPENDIX.md` §10。


既知類型との関係 (DEFECTS.md): 新規類型なし (D1〜D6 は OTT 旧 chain の既存分類 = `check_ott.py`)。検証起点 commit: `59eea5c` (main `bb76f7c` 上) と、本 run の `6e5c8da` (main 上) の 2 系統。
素材 (PR 作成者の申告): `fl-win64 plugins-ott analysis-ott-binaries toolchain-retdec toolchain-emsdk work-liftdiff work-m6-ott work-m11`。申告どおりの `$ARTIFACTS_DIR` 実在は、レビュー時点の runner では `fl-win64` のみ確認 (他は未取得)。`fl-win64` は `tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 (3.3 GiB) し `FL_WIN64_DIR` に設定とあるが、展開ログは未添付。python 依存 (numpy capstone pefile) は `pip install --user` で導入とあるが、ログは未添付。

### 本 run の照合状況 (LD-8 受入条件 1・`ebf5114a` 時点・未検証)

- **e2e 実行 run の URL / run ID: 未記録**。PR 作成者による実行 run を特定できなかった。照合した範囲:
  - `406-liftdiff-e2e-full-run` の run `38421355705` (event `pull_request`・success): `review` ジョブのみ実行、`implement` / `watchdog` は skipped。e2e の step は無い。
  - `122-liftdiff-ott-chain-e2e` の run `38421035101` (sha `5486e109`・PR 本文の類似記述の出どころと推定): `review` のみ、`implement` は skipped。
  - 上記以外に e2e の実行ログは見つからず。
- そのため、以下の数値 (176 s・`LIFTDIFF_E2E PASS`・[2/4] 集計) は **PR 作成者の申告値であり、ログで裏付けられていない**。受入条件 1 は未達扱いとする。
- 申告の [2/4] OTT 集計: 212 関数 = 一致 33 / 不一致 110 / 実行不能 69。D1 icall_drop 4 / D2 short_global 6 / D3 callsite_arg_drop+arg_drop 13 / D4_D5 C 定義 port 19 / D6 body 層 26。ネガコン 5/5 PASS の申告 (D1/D2/D3/D6 のタグ除去で exit 1)。
- 申告の実行環境 (参考): 176 s 全体・[0/4] 単体 23 件 OK・[1/4] build・[3/4] unit #18 3 件 PASS・[4/4] M11 closure sample:800 (99 s)。`check_ott.py` は同一出力 3 回 (申告)。
- **前回 (`59eea5c`) との差**: 前回 38/108/66 (D3 14、D4_D5 18)。本 run は 33/110/69 (D3 13、D4_D5 19)。D1・D2・D6 は不変。差分の原因は未切り分け (main の `59eea5c`→`6e5c8da` 間の変更による可能性が高いが、未確認)。検出自体 (D1〜D6 全検出) は維持。
- **[3/4] unit #18**: `UStrAsg` mem diff / `Move(409c80)` spill_slot_deref / `4123c0` resourcestring 脱落 (native 67 > wasm 46、mem diff 7) の 3 件 PASS。boot は unit 22 で segv (native 側、`units_run=22/942`) したが、判定条件の対象外。
- **[4/4] M11 closure sample:800**: 一致 357 / 不一致 213 / 実行不能 230。主因の上位は callee_divergence 52・wasm_trap 36・memory_semantics 25・callsite_arg_drop 24。
- **ネガコン・PE 解決**: `ANALYSIS_DIR=$HOME/analysis` で `pe` が解決し check_ott.py が実行できたことで確認 (受入条件 2)。

### 前回 run (`59eea5c`・fl-win64/work-m11 未取得)

- **PE パス解決**: `targets/ott_old.json` の `pe` = `${PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll`。`PLUGINS_DIR` 未設定・`ANALYSIS_DIR=$HOME/analysis` で
  `ldlib/build_wasm.py` と同じ展開式 (`tools/shared/paths.py` 既定 `$ANALYSIS_DIR/plugins`) が `$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll` (3,146,752 B, 実在) に解決。
- **D1〜D6 検出** (`ld_native` + `build ott_old` + `batch --set closure --shards 4` + `tests/check_ott.py`、クリーン worktree で 3 回): 3 回とも exit 0・出力同一。
  212 関数 = 一致 38 / 不一致 108 / 実行不能 66。D1 icall_drop 4 / D2 short_global 6 / D3 callsite_arg_drop+arg_drop 14 / D4_D5 C 定義 port 18 / D6 body 層 26 (分母 = 212 関数、タグは複数重複あり)。
  ctor `18011d400` = mismatch (icall_drop, callsite_arg_drop, callee_divergence, import_call_seq, zero_init_drop, fp_flag_unreflected)。
  §5 の旧実測 (38/108/66) と完全一致。ott_old build は wasm 931,471 B (sig_mismatch 0, undefined 0)。
- **所要 (実測、4 vCPU runner)**: build+batch+check 20.2 / 22.7 / 21.8 s (load 0.67 / 1.16 / 1.24)。単独 build 6.4 s・batch 15.0 s・nc 0.37 s。
- **ネガコン** (`tests/nc_check_ott.sh`、新規・`liftdiff_e2e.sh` [2/4] から呼ぶ): batch 複製から D1 / D2 / D3 / D6 のタグを 1 系統ずつ除去 → `check_ott.py` は 4/4 とも exit 1、無加工は exit 0 (計 5/5 PASS)。
  1 つでも期待外なら nc は exit 1 で e2e が落ちる。
- **検証範囲**: [2/4] OTT 旧 chain のみ。範囲外: [3/4] unit#18・[4/4] m11 closure と `liftdiff_e2e.sh` の全体 exit 0 は
  `fl-win64`・`work-m11` 未取得のため未実施 (`tools/m11/work/` 無し → 設計どおり exit 2)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `liftdiff_e2e.sh` (--m11-only なし) 全体 exit 0 の実行 run (URL / run ID・ログ) 未記録 | Issue #406 受入条件 1 が未検証 | #406 に残す。`oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff work-m6-ott analysis-ott-binaries` で再実行し、run URL とログ抜粋を追記 |
| 前回比の OTT 集計差分 (38/108/66 → 33/110/69) の原因未切り分け | D3 14→13・D4_D5 18→19 の変化理由が不明 | PM に起票依頼 (liftdiff 次 issue) |
| runner に numpy/capstone/pefile が無く e2e 前に `python3 -m pip install` が必要 | 素の Actions で e2e が exit 2 | PM に起票依頼 (agent-setup への追加) |

