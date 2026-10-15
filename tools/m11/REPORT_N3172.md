# REPORT_N3172 — #3172 (M11-N177): `m11_e2e.sh --full` を `functions_dll.csv`・`lift_pe.sha256` 無しで 1 コマンド rc 0 にする

親: #2779。関連: #3162 (未解決表の起票先)。既知類型との関係: DEFECTS.md の類型は新規確定しない (該当なし)。

## 1. 結論
- 受入 1 (全再生成経路で `bash tools/m11/m11_e2e.sh --full` が rc 0): **達成**。`functions_dll.csv`・`work/lift_pe.sha256` を消した状態から rc 0・1274 秒。
- 受入 2 (生成した lift 成果物の PE 指紋と使った fl-win64 の PE の一致): **達成**。`work/lift_pe.sha256` = `b2c64da4…` = fl-win64 の `extracted/block00031_PE.bin` の sha256。
- 修正の中身: `functions_dll.csv` は素材に無い Ghidra 12.1.4 の中間物で、全再生成の `m11_bounds.py` がこれを読めず fail-closed で止まっていた。`tools/m11/m11_ghidra_dll.sh` を新設し、無い時だけ Ghidra を取得 (sha256 検査) して作る。`m11_e2e.sh` の全再生成分岐で `m11_bounds` の前に呼ぶ。
- 到達 stage は **4/6** のまま (5・6 未達)。停止点は REPORT_N1598 §4 と同じ (`function_8c5eb0` の unreachable)。本 PR は起動の数値を変えていない (units_run 53・survey 872 は修正前の既存値と同じ)。

## 2. 測定の条件
- 測定 commit: `de8a34d5` (`fix(m11): build functions_dll.csv in m11_e2e --full (#3172)`。コード変更はこの commit の 2 ファイルのみ)。ブランチ `3172-m11-full-oneshot`、worktree `ws-3172`。
- 環境: 本 runner (4 vCPU, 15 GiB)。開始時 load `0.47 0.38 0.20`、終了時 `1.05 1.01 0.86` (`/proc/loadavg` の 1/5/15 分値)。
- 素材: `work-m11` を worktree の `tools/m11/work/` に展開 (gitignore)。`fl-win64` は `extracted/block00031_PE.bin` の 1 member のみ展開 (sha256 `b2c64da4…`・`[WIN64]`) を `$RUNNER_TEMP/fl-win64` に置き `FL_WIN64_DIR` に指定。
- 外部道具: RetDec v5.0 (`[RETDEC]`)・emsdk (`[EMSDK]`) は runner に既存。Ghidra 12.1.4 (`[GHIDRA]`) は runner に無く、公式 release `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 `ddac49f9…d2db` を `m11_ghidra_dll.sh` が検査して一致) を `$RUNNER_TEMP/ghidra` に展開。JDK 21 (Temurin 21・`JAVA_HOME_21`)、`MAXMEM=8G`。
- 実行前の状態: `tools/m2/work/ghidra_dll/functions_dll.csv` 無し・`tools/m11/work/lift_pe.sha256` 無し (issue の前提どおり)。

## 3. 受入 1: 1 コマンド (全再生成経路・fresh)
実行: `cd ws-3172 && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/m11_e2e.sh --full` (実測 23:21:36 → 23:42:50 UTC)

| 工程 | 結果 |
|---|---|
| m11_scan / **functions_dll.csv (Ghidra 12.1.4)** / m11_bounds | ok / **ok** / ok |
| lift 4 chunks (RetDec) / m11_tail #1〜#3 / lift boot4 #1〜#3 / gen_ir2 #1〜#3 | 全 ok |
| lift boot5 (RetDec) / gen_ir2 (boot5 追加) / data_gen / image_gen / lb_check / build (emcc) | 全 ok |
| 実行 A (通常起動) / B (unit survey) / C (寛容起動) / judge / 回帰ゲート・ネガコン | 実行。rc 0 |

- **rc: 0**・所要 **1274 秒** (21 分 14 秒)。判定 PASS (`e2e_expect.env`: stage ≥ 4・survey_ok ≥ 800・strict 56・survey 完全一致 872・ptr 基準は全て通過。ネガコン 3 件 `NEGCTL_OK`)。
- 初回の試行は Ghidra が project パスの `..` 要素を拒否し、43 秒で fail-closed (`M11_SUMMARY` `functions_dll.csv ... failed`)。パスを `cd`・`pwd` で正規化して再実行した。以下の数値は正規化後の 1 回だけの実測。

## 4. 受入 2: 指紋の一致
| 対象 | sha256 | 判定 |
|---|---|---|
| `tools/m11/work/lift_pe.sha256` (本 run が書いた) | `b2c64da4…496d` | — |
| fl-win64 `extracted/block00031_PE.bin` (使った PE) | `b2c64da4…496d` | **一致** |
| `tools/m2/work/ghidra_dll/functions_dll.csv` | `90d1bbac…5a11` (59,010 行) | REPORT_N1598 §3 の `90d1bbac…` と一致 |

Ghidra ログ: `DumpFunctions: 59009 functions`、image base `00400000`。

## 5. 実測結果 (受入 1 の run)
- 到達 stage **4/6** (1 image 敷設 / 2 `_InitLib` / 3 `InitUnits` / 4 FastMM4 実行: 達成。5 全 unit 完走 / 6 DllMain 正常終了: 未達)。
- 停止理由 (通常起動): `trap "unreachable" @ function_8c5eb0 <- function_56fde0 <- m11_tr_function_56fde0 <- m11_icall <- function_4120c0`。units_run 53 / 942、icall ok 236・miss 3、`halt0_early` false、`dllmain_normal_true` false。
- survey (隔離 942 本): **ok 872** / trap 23 (oom 0) / miss 46 / noproc 1 / clobber 0。
- 寛容起動 (実行 C): attempted 942 / ok 874 / noproc 1 / skipped 67 / clobber 0 / boot_rc 1。
- FastMM4 (通常起動): GetMem 572 / FreeMem 20、VirtualAlloc 19 回 275.6 MB、先頭 1,310,704 B (MediumBlockPoolSize)。
- wasm 6,047,577 B・trampoline 7,425・`ir_sha256` `7bfb67c4…` (過去値 `951e5b5d…` (REPORT_N1598) とは比較していない)。

## 6. 既定経路の再確認 (非 `--full`)
`bash tools/m11/m11_e2e.sh` (`functions_dll.csv`・`lift_pe.sha256` は §3 の run が作ったものを再利用): **rc 0・69 秒**・load `0.45 0.85 0.81` → `0.82 0.89 0.83`・survey ok 872 / trap 23 / miss 46 / noproc 1 (§5 と同じ)。CSV が有れば Ghidra 段は走らない (`m11_ghidra_dll.sh` は既存を検出して 0 を返す)。
最終 HEAD `dfbc2948` (測定後の既定分岐削除を含む) でも同じ経路を実行: **rc 0・67 秒**・load `0.10 0.58 0.72` → `0.90 0.74 0.77`・survey ok 872 / trap 23 / miss 46 / noproc 1 (同じ)。

## 7. コード差分 (測定 commit → HEAD)
- 測定 commit `de8a34d5` の後のコード変更は `tools/m11/m11_ghidra_dll.sh` の 1 commit (`dfbc2948`) のみ。内容は注記 1 行と、既定 Ghidra 位置 ([GHIDRA] の既定 install 先) の分岐の削除 (本 runner ではその位置に Ghidra が無く当該分岐は §3 の run で実行されていない。挙動は変えていない)。
- 残りは本 REPORT・`docs/DOC_MAP.md` の索引行・`docs/WORKFLOW.md` の 1 文 (コード不変)。
- `git diff --stat de8a34d5 HEAD -- tools/m11` の実出力は PR 本文と issue コメントに添付する (本ファイル自身の行数を含むため、本文中には書けない)。

## 8. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 通常起動の停止 (`function_8c5eb0` の unreachable・stage 4 で停止) | stage 5/6 未達 | #132 (既存の継続先) |
| 寛容起動の skipped 67 (miss 46・unreachable 1・halt0 7・oob 13) | 寛容経路の数値の意味は未確定 | #3229 (#3160 は CLOSED のため差し替え) |
| LB=0x10000 の数値差 | 範囲外 (issue 本文の除外) | #3161 |
| ptrcheck 分類 | 範囲外 (issue 本文の除外) | #3129 (#3113 は CLOSED のため差し替え) |
| 同一 head の `--full` 2 回目 (IR `ir_sha256` の実行間一致) | 受入外。今回は n=1 | #2577 (#1664 は CLOSED のため差し替え) |
| 修正後 HEAD (`29cdb2ab`) の `--full` 再測定 (§11) | 差し戻しの再測定が未実施。修正後の script の数値はまだ無い | open の起票先なし。本 PR の merge 前に PM が再投入 |
| work-m11 の R2 への再投入 | 範囲外 (WORKFLOW §11 の依頼者の担当) | 依頼者 (PM) |

## 9. 本番影響・KPI
- 起動・GUI の挙動は変えていない (変更は m11 の全再生成で使う CSV の作成経路のみ)。起動 KPI は §5 の通り修正前と同じ (stage 4・units_run 53・survey ok 872)。`infra/pm-worker` には触れない。
- `tools/m11/REPORT.md` は 250 行上限のため変更していない (本ファイルが正)。

## 10. 差し戻し対応 (fix commit `29cdb2ab`・round 1)
- blocking 1 (CSV の PE 非照合): `m11_ghidra_dll.sh` は `functions_dll.csv.pe_sha256` (sidecar) が現 PE の sha256 と一致する時だけ CSV を再利用する。不一致・sidecar 無しは旧 CSV を `functions_dll.csv.stale` に退避して作り直す。分岐の確認 (Ghidra を回さず `GHIDRA_HOME=/nonexistent` で止めた): A 指紋一致 → 既存で rc 0 / B 指紋不一致 → 退避し fail-closed rc 1 / C sidecar 無し → 退避し fail-closed rc 1。
- blocking 2 (project 名): 変数 `GPROJ=ghproj_dll` に統一し、`$GPROJ.gpr`・`$GPROJ.rep` を開始時と終了時に削除 (旧 `ghproj` は存在しない名前だった)。CSV と sidecar を消して 2 回続けて実行 (Ghidra 12.1.4 単体・PE `b2c64da4…496d`):
  - run 1: rc 0・10 分 18 秒・59,010 行・sha256 `90d1bbac…5a11`
  - run 2: rc 0・9 分 44 秒・59,010 行・sha256 `90d1bbac…5a11`
  - どちらの後も `tools/m2/work/ghidra_dll/` に `ghproj_dll.gpr`・`ghproj_dll.rep` は残らない (`ls` で確認)。
- blocking 3 (closed の起票先): §8 の表を open の issue に差し替え (#3160・#3113・#1664 は CLOSED)。
- blocking 4 (DOC_MAP 行): 測定値を消し、結論 1 行 + リンクに縮小。行数は実値に直す。
- minor (JDK 21 の絶対パス): `docs/REFERENCES.md` §1 のローカルツール表に `[JDK21]` を追加。script の既定値はこの ID を参照する。

## 11. 未実施: 修正後 HEAD の `--full` 再測定
- **未実施**。理由: 本 runner に `/opt/emsdk`・`/opt/retdec`・`/opt/ghidra` が無い (`command -v emcc` / `retdec-decompiler` も無し)。emsdk 6.0.12 と RetDec v5.0 の導入に加えて全再生成 (約 21 分) が、差し戻し run の上限 (40 分) に収まらない。
- §3〜§6 の数値は修正前の script (`de8a34d5`) の実測。修正後の script (`29cdb2ab`) では測っていない。修正後の script の検証は §10 (分岐・Ghidra 単体の 2 回) のみ。
- 対応: emsdk・RetDec 入りの runner で `bash tools/m11/m11_e2e.sh --full` を fresh (`functions_dll.csv`・`lift_pe.sha256` 無し) で再投入し、本節と §3 の測定 commit・数値を更新する。merge はその後。
