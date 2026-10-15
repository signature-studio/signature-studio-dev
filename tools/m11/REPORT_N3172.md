# REPORT_N3172 — #3172 (M11-N177): `m11_e2e.sh --full` を `functions_dll.csv`・`lift_pe.sha256` 無しで 1 コマンド rc 0 にする

親: #2779。関連: #3162 (未解決表の起票先)。既知類型との関係: DEFECTS.md の類型は新規確定しない (該当なし)。

## 1. 結論
- 受入 1 (全再生成経路で `bash tools/m11/m11_e2e.sh --full` が rc 0): **達成**。修正後の HEAD `93fac3c5` で `functions_dll.csv`・`work/lift_pe.sha256` を消した状態から rc 0・1335 秒 (レビュワー run・§3 run B)。修正前 script (測定 commit `de8a34d5`) でも rc 0・1274 秒 (§3 run A)。
- 受入 2 (生成した lift 成果物の PE 指紋と使った fl-win64 の PE の一致): **達成**。`work/lift_pe.sha256` = `b2c64da4…496d` = fl-win64 の `extracted/block00031_PE.bin` の sha256 (HEAD `93fac3c5`・§4)。
- 修正の中身: `functions_dll.csv` は素材に無い Ghidra 12.1.4 の中間物で、全再生成の `m11_bounds.py` がこれを読めず fail-closed で止まっていた。`tools/m11/m11_ghidra_dll.sh` を新設し、無い時 (または PE 指紋が sidecar と合わない時) だけ Ghidra を取得 (sha256 検査) して作る。`m11_e2e.sh` の全再生成分岐で `m11_bounds` の前に呼ぶ。
- 到達 stage は **4/6** のまま (5・6 未達)。停止点は REPORT_N1598 §4 と同じ (`function_8c5eb0` の unreachable)。本 PR は起動の数値を変えていない (units_run 53・survey ok 872 は修正前と同じ)。
- 未解決: 寛容起動の skipped 67 (内訳の追跡。§8)、main 取り込み後の再測定 (§7・§8)。

## 2. 測定の条件 (測定 run ごとに分ける)
- **run A**: 測定 commit `de8a34d5` (修正前 script)。worktree `ws-3172`。runner (4 vCPU, 15 GiB)。開始時 load `0.47 0.38 0.20`、終了時 `1.05 1.01 0.86`。素材: `work-m11` を `tools/m11/work/` に展開、`fl-win64` は `extracted/block00031_PE.bin` の 1 member のみを `$RUNNER_TEMP/fl-win64` に置き `FL_WIN64_DIR` に指定。RetDec v5.0 (`[RETDEC]`)・emsdk (`[EMSDK]`) は runner に既存。Ghidra 12.1.4 は runner に無く、公式 release (sha256 `ddac49f9…d2db` を script が検査) を `$RUNNER_TEMP/ghidra` に展開。JDK 21 (`JAVA_HOME_21`)、`MAXMEM=8G`。
- **run B**: HEAD `93fac3c5` (修正後 script)。レビュワー run (detached worktree・push なし)。素材: `$ARTIFACTS_DIR` の `fl-win64`・`toolchain-emsdk` (`[EMSDK]` emcc 6.0.12)・`toolchain-retdec` (`[RETDEC]` v5.0)・`work-m11`。JDK 21 は `/usr/lib/jvm/temurin-21-jdk-amd64` (既存)。Ghidra 12.1.4 は script が取得し sha256 を検査。
- 両 run の実行前の状態: `tools/m2/work/ghidra_dll/functions_dll.csv` 無し・`tools/m11/work/lift_pe.sha256` 無し。
- 素材の取得は差し戻し run ごとに異なる。round 2 の fix run では `oc_artifacts` 行が本文に無く `toolchain-emsdk`・`toolchain-retdec`・`work-m11` が取得されなかった (WORKFLOW §11)。run B の runner では 4 素材が揃っていた。

## 3. 受入 1: 1 コマンド (全再生成経路・fresh)
実行: `FL_WIN64_DIR=<fl-win64 の展開先> TMPDIR=$RUNNER_TEMP bash tools/m11/m11_e2e.sh --full`

| 工程 | run B (`93fac3c5`) | run A (`de8a34d5`) |
|---|---|---|
| 所要・時刻 | **rc 0・1335 秒** (00:38:30 → 01:00:45 UTC) | rc 0・1274 秒 (23:21:36 → 23:42:50 UTC) |
| m11_scan / functions_dll.csv (Ghidra 12.1.4) / m11_bounds | ok / **ok (新規作成)** / ok | ok / **ok** / ok |
| lift 4 chunks / m11_tail #1〜#3 / lift boot4 #1〜#3 / gen_ir2 #1〜#3 | 全 ok | 全 ok |
| lift boot5 / gen_ir2 (boot5 追加) / data_gen / image_gen / lb_check / build | 全 ok | 全 ok |
| 実行 A / B / C / 判定・回帰ゲート・ネガコン | rc 0 (期待値ゲート通過・ネガコン `NEGCTL_OK` 3 件) | PASS (stage ≥ 4・survey_ok ≥ 800・strict 56・survey 完全一致 872・ptr 基準)・`NEGCTL_OK` 3 件 |

- run B: `functions_dll.csv` は 59,010 行・sha256 `90d1bbac…5a11`・sidecar (PE 指紋) `b2c64da4…496d`。
- run A の注記: 初回の試行は Ghidra が project パスの `..` 要素を拒否し、43 秒で fail-closed (`M11_SUMMARY` `functions_dll.csv ... failed`)。パスを `cd`・`pwd` で正規化して再実行した。以下の数値は正規化後の 1 回だけの実測。

## 4. 受入 2: 指紋の一致
| 対象 | sha256 | 判定 |
|---|---|---|
| run B: `work/lift_pe.sha256` (run B が書いた) | `b2c64da4…496d` | — |
| run B: fl-win64 `extracted/block00031_PE.bin` (使った PE) | `b2c64da4…496d` | **一致** |
| run A: 同上 (run A が書いた lift_pe.sha256 と使った PE) | `b2c64da4…496d` | **一致** |
| `functions_dll.csv` (両 run) | `90d1bbac…5a11` (59,010 行) | REPORT_N1598 §3 の `90d1bbac…` と一致 |

Ghidra ログ (run A): `DumpFunctions: 59009 functions`、image base `00400000`。

## 5. 実測結果 (run B = `93fac3c5`。run A は括弧内)
- 到達 stage **4/6** (1 image 敷設 / 2 `_InitLib` / 3 `InitUnits` / 4 FastMM4 実行: 達成。5 全 unit 完走 / 6 DllMain 正常終了: 未達)。run A と同じ。
- 停止点 (通常起動): `trap "unreachable" @ function_8c5eb0` (run A の呼出し連鎖: `<- function_56fde0 <- m11_tr_function_56fde0 <- m11_icall <- function_4120c0`)。units_run 53 / 942 (run A と同じ)。run A の icall ok 236・miss 3、`halt0_early` false、`dllmain_normal_true` false。
- survey (隔離 942 本): **ok 872** / trap 23 (oom 0) / miss 46 / noproc 1 / clobber 0 (run A と同じ)。
- 寛容起動 (実行 C): attempted 942 / ok 874 / skipped 67 (miss 46・unreachable 1・halt0 7・oob 13)。run A の同じ値 (run A は加えて noproc 1 / clobber 0 / boot_rc 1 を記録)。
- wasm 6,047,577 B・trampoline 7,425・`ir_sha256` `7bfb67c4…8e9d` (run A も `7bfb67c4…`)。過去値 `951e5b5d…` (REPORT_N1598) とは比較していない。
- FastMM4 (run A のみ): GetMem 572 / FreeMem 20、VirtualAlloc 19 回 275.6 MB、先頭 1,310,704 B (MediumBlockPoolSize)。

## 6. 既定経路の再確認 (非 `--full`)
- 69 秒の run: `bash tools/m11/m11_e2e.sh` (`functions_dll.csv`・`lift_pe.sha256` は §3 run A が作ったものを再利用)。script は `dfbc2948` より前 (`de8a34d5` と同じ)。**rc 0・69 秒**・load `0.45 0.85 0.81` → `0.82 0.89 0.83`・survey ok 872 / trap 23 / miss 46 / noproc 1 (§5 と同じ)。
- 67 秒の run: script を `dfbc2948` (測定後の既定分岐削除を含む) にして同じ経路を実行。**rc 0・67 秒**・load `0.10 0.58 0.72` → `0.90 0.74 0.77`・survey ok 872 / trap 23 / miss 46 / noproc 1 (同じ)。
- どちらも `29cdb2ab` (sidecar 照合・GPROJ) より前の script。`29cdb2ab` 以降は CSV の再利用に sidecar (`functions_dll.csv.pe_sha256`) が要るため、この 2 run の CSV は再利用の条件を満たさない。**HEAD `93fac3c5` の非 `--full` 経路は未測定** (§8)。

## 7. コード差分 (測定 commit → HEAD)
- run A `de8a34d5` → run B `93fac3c5` の `tools/m11` のコード変更は `m11_ghidra_dll.sh` のみ (29 行: sidecar 照合・GPROJ 後始末・注記)。
- run B `93fac3c5` → 本 commit: `tools/m11/m11_e2e.sh` のヘッダ注記 1 行 (コメント行のみ。実行行の差分 0 を `diff` で確認)。
- **main 取り込み**: 未実施。`origin/main` (`e59ca23b9`) は本ブランチ HEAD に無い commit を 734 件持ち、`tools/m11` の実行コードが main 側で変わっている (`m11_e2e.sh`・`m11_gen_ir2.sh`・`m11_run.mjs`・`m11_survey.mjs`・`m11_ptrcheck*.{sh,mjs}`・`e2e_expect.env`・`ldfix/` ほか)。GitHub 判定は MERGEABLE (競合無し) だが、取り込んだ HEAD は本 REPORT の測定対象ではない。取り込むなら取り込み後 HEAD で `--full` を再測定する (WORKFLOW §6)。

## 8. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 通常起動の停止 (`function_8c5eb0` の unreachable・stage 4 で停止) | stage 5/6 は未到達 | #132 (既存の継続先) |
| 寛容起動の skipped 67 (miss 46・unreachable 1・halt0 7・oob 13) | 寛容経路の数値の意味は未確定 | #3172 (内訳の追跡。#3229 は CLOSED で内容が別のため使わない) |
| LB=0x10000 の数値差 | 範囲外 (issue 本文の除外) | #3161 |
| ptrcheck 分類 | 範囲外 (issue 本文の除外) | #3129 |
| 同一 head の `--full` 2 回目 (`ir_sha256` の実行間一致) | 受入外。run A・run B の n=1 ずつ | #2577 |
| main 取り込み後の `--full` 再測定 (§7) | 取り込んだ HEAD の実測が無い。取り込むなら approve 前に必要 | #3172 |
| HEAD `93fac3c5` 以降の非 `--full` 経路 (CSV 再利用の sidecar 経路) の実測 | 既定経路の HEAD 実測が無い (§6) | #3172 |
| work-m11 の R2 への再投入 | 範囲外 (WORKFLOW §11 の依頼者の担当) | 依頼者 (PM) |

## 9. 本番影響・KPI
- 起動・GUI の挙動は変えていない (変更は m11 の全再生成で使う CSV の作成経路のみ)。起動 KPI は run B も run A と同じ (stage 4・units_run 53・survey ok 872)。`infra/pm-worker` には触れない。
- `tools/m11/REPORT.md` は 250 行上限のため変更していない (本ファイルが正)。

## 10. 差し戻し対応
- round 1 (fix commit `29cdb2ab`):
  - blocking 1 (CSV の PE 非照合): `m11_ghidra_dll.sh` は `functions_dll.csv.pe_sha256` (sidecar) が現 PE の sha256 と一致する時だけ CSV を再利用する。不一致・sidecar 無しは旧 CSV を `functions_dll.csv.stale` に退避して作り直す。分岐の確認 (Ghidra を回さず `GHIDRA_HOME=/nonexistent` で止めた): A 指紋一致 → 既存で rc 0 / B 指紋不一致 → 退避し fail-closed rc 1 / C sidecar 無し → 退避し fail-closed rc 1。
  - blocking 2 (project 名): 変数 `GPROJ=ghproj_dll` に統一し、`$GPROJ.gpr`・`$GPROJ.rep` を開始時と終了時に削除 (旧 `ghproj` は存在しない名前だった)。CSV と sidecar を消して 2 回続けて実行 (Ghidra 12.1.4 単体・PE `b2c64da4…496d`): run 1 rc 0・10 分 18 秒、run 2 rc 0・9 分 44 秒。どちらも 59,010 行・sha256 `90d1bbac…5a11`・project 残骸なし。
  - blocking 3 (closed の起票先): §8 の表を open の issue に差し替え。
  - blocking 4 (DOC_MAP 行): 測定値を消し、結論 1 行 + リンクに縮小。
  - minor (JDK 21 の絶対パス): `docs/REFERENCES.md` §1 に `[JDK21]` を追加。
- round 2: §1・§3〜§7 を測定 commit ごとに分けて書き直し、runner の記述を修正 (§2)。
- round 3: §3・§5 に run B (`93fac3c5`) を記録。§8 の「修正後の再測定」行を削除。§2・§11 の runner の記述を run ごとに分けた。m1 (`m11_e2e.sh` のヘッダ注記の所要時間) を実測に合わせた。

## 11. 測定の経緯と残り
- round 2 の fix run: 素材 (`toolchain-emsdk`・`toolchain-retdec`・`work-m11`) が取得されず、fresh `--full` を実測できなかった (§2)。
- round 3 (run B): レビュワーが HEAD `93fac3c5` で fresh `--full` を実施 (rc 0・§3・§4・§5)。
- round 3 の fix commit (本 commit): 再測定していない。変更は `m11_e2e.sh` のヘッダ注記 (コメント行のみ。§7) と docs。実行されるコードは `93fac3c5` と同じ。
- 残る測定: main 取り込み後の HEAD と、HEAD の非 `--full` 経路 (§8)。
