# icall #3604 (CI-170): tools/icall の従来既定値 8 本を tools/shared の環境変数定義へ置換

親: #294 (CI-4)。`tools/icall/REPORT.md` は 250 行上限のため、本節は付録に置く (REPORT.md §8.5 の『`/home/ubuntu/...` ハードコード』行を解決済みに更新)。
従来の既定値は `docs/REFERENCES.md` §4 の `[ANALYSIS-DIR]` (`ANALYSIS_DIR` の既定値) で表す。

## 1. 結論

- 対象 8 本の従来既定値の直書き (`home/ubuntu` を含む文字列) は **0 件**。`tools/icall` の code 全体 (`*.sh`・`*.py`・`*.json`・`*.ts`・`*.mjs`、`work/` 除く) も 0 件。既定値は `tools/shared/env.sh`・`paths.py` 経由で従来値と**同一** (§3 で実測)。
- 代表 e2e `bash tools/icall/icall_e2e.sh` は **before (origin/main `4517825a2`) も after (測定 commit `58dad0116`) も PASS**。stdout は time 行を除いて一致 (§4)。監査 70→0・matrix 89/89 scenario・50,236 cell 全 bit 一致・max_ulp 0・state diff 0 は before/after で同じ。
- **前提の不具合 (素材)**: 素材 `work-m6-ott` の `tools/ott/work/libottnative.so` は古く `ott_enc_slots` を export しない。素材のままでは e2e は **FAIL** (matrix 89/89 failed・CRT gate FAIL)。`bash tools/ott/native/build.sh` で作り直すと PASS。before/after とも作り直した so で測った (§4・§7)。

## 2. 変更 (8 本・commit `58dad0116`)

| ファイル | 旧 (従来の既定値の直書き) | 新 (tools/shared 経由) |
|---|---|---|
| `icall_e2e.sh` | `ANALYSIS_DIR="${ANALYSIS_DIR:-[ANALYSIS-DIR]}"`・`--small`/`--full` の PE を `$ANALYSIS_DIR/win64/...` | `source "$T/shared/env.sh"`・DLL は `$PLUGINS_DIR`・PE は `$FL_WIN64_DIR` |
| `ott_route.sh` | `${ANALYSIS_DIR:-[ANALYSIS-DIR]}/plugins/...` | `source "$T/shared/env.sh"`・`$PLUGINS_DIR` |
| `x64c_fle_probe.sh` | `${ANALYSIS_DIR:-[ANALYSIS-DIR]}/win64/...` | `source "$T/shared/env.sh"`・`$FL_WIN64_DIR` |
| `prep_targets.py` | `A.Image('[ANALYSIS-DIR]/win64/extracted/block18983_PE.bin')` | `FL_WIN64_DIR` (`sys.path` に `tools/shared`) |
| `diff/fn_diff.py` | DLL を `[ANALYSIS-DIR]/plugins/...` で直書き | `PLUGINS_DIR` |
| `diff/rax_callers.py` | `PLUGINS_DIR` env → `ANALYSIS_DIR` env → 直書き | `PLUGINS_DIR` (`paths.py` が同じ優先順位) |
| `disp_size/census.py` | `EXT`・`OTT`・`MACROOT` を `[ANALYSIS-DIR]` 配下で直書き | `FL_WIN64_DIR`・`PLUGINS_DIR`・`FL_MAC_DIR` |
| `tests/test_icall.py` | `ANALYSIS_DIR` env → 直書き | `PLUGINS_DIR` |

- 従来の既定値が残るのは定義点 (`tools/shared/env.sh`・`paths.py`・`paths.mjs` の既定値) だけ。既定値そのものは変えていない。

## 3. 既定値の同一性 (env 未設定時の解決値)

`ANALYSIS_DIR`・`FL_WIN64_DIR`・`FL_MAC_DIR`・`PLUGINS_DIR` を未設定にして `tools/shared/paths.py` を読み、新しい式の結果を従来の直書きと文字列比較した (`os.path.join` の結果):

| 用途 (対象ファイル) | 新しい式の結果 | 従来の直書き (基点 `[ANALYSIS-DIR]`) | 一致 |
|---|---|---|---|
| DLL (`icall_e2e.sh`・`ott_route.sh`・`fn_diff.py`・`rax_callers.py`・`test_icall.py`) | `PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll` | `[ANALYSIS-DIR]/plugins/ott/binaries/OTT_vst2_win64.dll` | SAME |
| EXT (`census.py`) | `FL_WIN64_DIR/extracted` | `[ANALYSIS-DIR]/win64/extracted` | SAME |
| block18983 (`prep_targets.py`) | `FL_WIN64_DIR/extracted/block18983_PE.bin` | `[ANALYSIS-DIR]/win64/extracted/block18983_PE.bin` | SAME |
| block00031 (`x64c_fle_probe.sh`・`icall_e2e.sh --full`) | `FL_WIN64_DIR/extracted/block00031_PE.bin` | `[ANALYSIS-DIR]/win64/extracted/block00031_PE.bin` | SAME |
| MACROOT (`census.py`) | `FL_MAC_DIR/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Plugins/Fruity` | `[ANALYSIS-DIR]/mac/pkg_extract/payload_out/Applications/FL Studio 2026.app/Contents/Resources/FL/Plugins/Fruity` | SAME |

- `bash tools/shared/test_paths.sh`: PASS 4/4 (default・analysis_dir_only・individual_override・negctl)。
- 上書き時 (CI の実環境): CI は `ANALYSIS_DIR` を展開先に設定する (agent-setup)。そのとき `PLUGINS_DIR` は `ANALYSIS_DIR/plugins`、`FL_WIN64_DIR` は `ANALYSIS_DIR/win64` になる。`FL_WIN64_DIR` を別に指定すると、それが返る (`$RUNNER_TEMP/fl-win64` で確認)。

## 4. e2e before / after

| 項目 | before: origin/main `4517825a2` (so 作り直し後) | after: 測定 commit `58dad0116` |
|---|---|---|
| 実行 | `TMPDIR=$RUNNER_TEMP bash tools/icall/icall_e2e.sh` (既定モード・`ANALYSIS_DIR` は CI の展開先) | 同左 |
| 結果 | **PASS** (rc 0) | **PASS** (rc 0) |
| 所要 (real / user) | 66.492 s / 65.636 s | 67.973 s / 67.246 s |
| load (1 分平均・4 core) | 開始 0.53 → 終了 1.15 | 開始 0.19 → 終了 1.36 |
| unit (`tests/test_icall.py`) | RESULT PASS (0 failed) | RESULT PASS (0 failed) |
| 監査 (OTT closure F) | 非 IAT 間接 call 81: 落ち 70→0・tail-jmp 11: 11→0・jump table 8: RetDec 未解決 1 → 8 展開・監査判定 PASS | 同左 |
| matrix | 89 scenario・failed 0・cells 50,236・bit-equal 50,236・max_ulp 0・state diff 0 qword | 同左 |
| CRT 関数単位 gate | PASS (SSE2・FMA3・負入力・override 4/4) | PASS |
| stdout の差 | — | before と差 0 (time 行を除く。`diff` が空) |

- 比較は `diff <(grep -v "real\|user\|sys" before.txt) <(grep -v "real\|user\|sys" after.txt)` (空)。
- **素材のまま (so を作り直す前) の before**: FAIL (68.166 s)。matrix の全 scenario が `undefined symbol: ott_enc_slots` で 89/89 failed・cells 0。CRT gate も FAIL。原因は §7。

## 5. 追加の検証

- `rax_callers.py 1801a9a6c` (DLL パスを実際に使う script): 旧版 (`git show 4517825a2:tools/icall/diff/rax_callers.py`) と新版の出力 47 行の `diff` は 0 (`ANALYSIS_DIR` を展開先に設定)。
- ネガティブコントロール: `PLUGINS_DIR=<存在しないパス> python3 tools/icall/diff/rax_callers.py 1801a9a6c` → `FileNotFoundError: <指定先>/ott/binaries/OTT_vst2_win64.dll`。環境変数が効いていることの確認。
- 構文: `bash -n` (`icall_e2e.sh`・`ott_route.sh`・`x64c_fle_probe.sh`) OK、`ast.parse` (`prep_targets.py`・`fn_diff.py`・`rax_callers.py`・`census.py`・`test_icall.py`) OK。

## 6. 検証範囲外 (限界)

- `--small` / `--full` の経路は**未実行**。`fl-win64` を展開していない (既定モードは fl-win64 を使わない)。未実行の行: `icall_e2e.sh` の `$FL_WIN64_DIR/extracted/block18983_PE.bin` (--small)・`block00031_PE.bin` (--full)、`prep_targets.py`・`census.py`・`x64c_fle_probe.sh`・`fn_diff.py` の PE/DLL 参照。既定値は §3 の式で確認したのみ。

## 7. 素材の不具合 (未解決)

- `work-m6-ott.tar.zst` に入る `tools/ott/work/libottnative.so` (作成 Oct 12 18:21) は `ott_enc_slots` を export しない (`nm -D <so> | grep -c ott_enc_slots` → 0)。現 HEAD の `tools/ott/native/ott_native.c` には定義がある (182 行)。素材が現 HEAD より古い。
- 回避: `bash tools/ott/native/build.sh` (`gcc -shared`・出力先 `tools/ott/work/libottnative.so` は gitignore 対象) → `nm -D` で 1 件。その後 e2e は PASS。本付録の before/after は両方とも作り直した so で測った。
- 起票先: #3604 のコメントで依頼者に素材の再梱包を依頼 (Actions の R2 認証は書き込み不可。手順は `docs/WORKFLOW.md` §11「R2 への投入」)。または `icall_e2e.sh` の前提に `build.sh` を入れる案 (PM 判断)。

## 8. 再現

```sh
bash tools/ott/native/build.sh                                  # 素材の libottnative.so が古い場合のみ
TMPDIR=$RUNNER_TEMP bash tools/icall/icall_e2e.sh               # 既定モード (実測 67.973 s, 4 core)
bash tools/shared/test_paths.sh                                 # 既定値・上書きの 3 言語一致 (PASS 4/4)
grep -rn 'home/ubuntu' tools/icall --include=*.sh --include=*.py --include=*.mjs --include=*.json --exclude-dir=work | wc -l   # 0
```

## 9. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 素材 `work-m6-ott` の `libottnative.so` が古い (§7) | 素材のままでは icall e2e が FAIL。`build.sh` が前提 | #3604 のコメントで依頼 (PM が素材の再梱包か e2e の前提化を判断) |
| `--small` / `--full` 経路 (fl-win64) の未実行 (§6) | FL_WIN64_DIR 依存の行の実行確認なし | #294 の残り (次の icall run で fl-win64 を展開して実行) |
| 素材内の絶対 symlink (`tools/ott/work/cab238/**` の 68 本 → 作成元 VM の絶対パス) | icall e2e は参照しない。`os.path.exists` 判定の類は影響し得る (`tools/icall/REPORT.md` 実走の前提 ② の dangling symlink と同種) | #294 |
| `tools/shared` 内の他ファイル (`lift/libkio/diff_test.py`・`run_all.sh`・`test_paths.sh`) の従来既定値の直書き | 本件の対象外 (定義点とは別の参照) | #294 |

## 10. 測定 commit

- 測定 commit: `58dad0116` (コード変更の最後の commit)。以降の commit は文書のみ。
- `git diff 58dad0116 HEAD -- tools/icall ':!*.md'` の出力は空 (コード差分 0)。
