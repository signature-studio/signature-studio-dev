# REPORT_N27 — #680: survey 測定基準の固定化 (IR 生成条件の fail-closed・PE パス env 化・n 実測)

既知類型との関係: DEFECTS.md D17 (qstore) と無関係の harness 欠陥 (fail-open)、類型行案あり (§6)。

## 1. 結論
- 確認できた fail-open 機構: IR 生成条件 (ldfix・qstore) が capstone/pefile 不足時に **黙って** 変わり得た。`m11_gen_ir2.sh` の ldfix と `m11_build.sh` の qstore は WARNING のみでスキップされ、`m11_e2e.sh` は PE 無しでも exit 0 だった。PE パスは repo 外の固定パス (`tools/shared/env.sh` の既定) だった。
- 「OFF が 818/21 ↔ 828/13 と変わる」の原因は、本 PR では断定しない。(a) 旧 IR は再測定しておらず、trap 内訳の差も未調査 (§4・§6)。本 PR で確定したのは、IR 生成条件の欠落・不一致を fail-closed にし、条件を `work/ir_conditions.json` に記録すること。
- 修正 (commit `3807851`・後続 review 対応 commit): skip は非 0 終了。PE は `FL_WIN64_DIR` / `M11_PE` 経由 (既定値は従来どおり)。IR 生成条件と IR の指紋 (sha256) を記録し、`m11_judge.py` が印字する。build は指紋・PE・ldfix の記録が一致する IR だけを受け付ける。
- 測定 (本 runner, capstone 5.0.7 / pefile 2024.8.26, PE は [WIN64] の `extracted/block00031_PE.bin` 1 member, 測定は `3807851` 時点のコード): 既定 (qstore on) は n=2 で完全一致 (ok 864 / oob 23 / trap 31 / miss 46 / noproc 1 / clobber 0)。qstore off は n=2 で完全一致 (ok 856 / oob 31 / trap 38 / clobber 1)。qstore の有無で ok が 8 件、clobber が 1 件動く。
- 修正後の再測定 (§10): head `4e084e1` (測定時の HEAD) で n=3 (survey ok 866 / oob 21 / halt0 8 / trap 29 / miss 46 / noproc 1 / clobber 0 が 3 回一致)。`origin/main` 77340a4 で 1 回 (同値)。§3 の 864/23/31 (`3807851` 時点) との差は本 PR の変更ではなく、その後 main に入った m11 変更による (§10)。
- **未達**: 環境間一致 (別環境との比較) は未実測。R2 への work-m11 再投入は権限なし。`--full` (M3) は head で実行し `m11_bounds` で fail-closed になった (入力 `tools/m2/work/ghidra_dll/functions_dll.csv` が素材に無い・§10)。

## 2. 原因の切り分け (コード調査)
| 箇所 | 修正前 | 修正後 (3807851) |
|---|---|---|
| `m11_gen_ir2.sh` ldfix | capstone/pefile/PE 無し → WARNING, IR は未 ldfix で続行 (exit 0) | ERROR, exit 1。`ir_conditions.json` `ldfix=skipped` |
| `m11_build.sh` qstore (`M11_QSTORE=1` 既定) | 同 WARNING, exit 0 | ERROR, exit 1。`qstore=skipped` |
| `m11_build.sh` `M11_QSTORE=0` | 適用済み IR でも黙って無効扱い | 適用済み (`qstore=applied`) の IR なら exit 2 (IR の作り直しを要求) |
| `m11_build.sh` ldfix 未記録 | 検査なし | `ldfix=applied` の記録が無い IR は exit 2 (旧スナップショット IR を弾く) |
| `m11_e2e.sh` 前提不足 | PE・emsdk・node 無しで exit 0 | exit 1 (capstone/pefile 不足も前提に追加) |
| `m11_e2e.sh` IR 生成・build 失敗 | `run` で継続 (stale wasm で survey 実行) | `must` で即失敗 (exit 1) |
| PE パス | `m11_e2e.sh` `m11_gen_ir2.sh` `m11_data_gen.py` `m11_image_gen.py` `m11_icall_audit.py` が repo 外の固定パス (`tools/shared/env.sh` の既定) | `FL_WIN64_DIR` / `M11_PE` 経由 (既定値は従来どおり) |

## 3. 測定 (旧: 全て commit `3807851` の HEAD 内容・同一 runner・ `FL_WIN64_DIR` は [WIN64] 展開先。現 head の再測定は §10)
所要秒は `date` 差分、load は `uptime` の 1 分値 (開始→終了)。survey 値は `M11_SURVEY` (`work/e2e_survey.out`)。oob は survey の trap kind `memory access out of bounds` 件数。

| 測定 | コマンド | rc | 所要秒 | load (開始→終了) | ok | oob | halt0 | trap | miss | noproc | clobber | IR 条件 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NC1 | `bash m11_gen_ir2.sh` (capstone 未導入) | 1 | 9 | 0.02 → 0.17 | – | – | – | – | – | – | – | ldfix=skipped |
| NC1b | `PE=/nonexistent bash m11_build.sh` | 1 | 0 | 0.78 → 0.78 | – | – | – | – | – | – | – | qstore=skipped |
| NC2 | `FL_WIN64_DIR=/nonexistent bash m11_e2e.sh` | 1 | 0 | 0.21 → 0.21 | – | – | – | – | – | – | – | – (前提不足) |
| NC3 | `M11_QSTORE=0 bash m11_build.sh` (qstore 適用済み IR) | 2 | 0 | 0.70 → 0.70 | – | – | – | – | – | – | – | – |
| **M1-1** | `bash m11_e2e.sh` (既定 qstore on, snapshot から IR 再生成込み) | 0 | 68 | 0.25 → 1.00 | 864 | 23 | 8 | 31 | 46 | 1 | 0 | ldfix=applied qstore=applied |
| **M1-2** | `bash m11_e2e.sh` (同, 増分) | 0 | 39 | 0.66 → 0.83 | 864 | 23 | 8 | 31 | 46 | 1 | 0 | ldfix=applied qstore=applied |
| (前処理) | `bash m11_gen_ir2.sh` (M2 用に IR を作り直し) | 0 | 21 | 0.70 → 0.79 | – | – | – | – | – | – | – | qstore=not-applied |
| **M2-1** | `M11_QSTORE=0 bash m11_e2e.sh` (qstore off) | 0 | 31 | 0.72 → 0.97 | 856 | 31 | 7 | 38 | 46 | 1 | 1 | ldfix=applied qstore=disabled |
| **M2-2** | `M11_QSTORE=0 bash m11_e2e.sh` (同, 増分) | 0 | 26 | 0.82 → 0.96 | 856 | 31 | 7 | 38 | 46 | 1 | 1 | ldfix=applied qstore=disabled |
| M3 | `bash m11_e2e.sh --full` | – | – | – | – | – | – | – | – | – | – | **未実施** (§5) |

- M1-1 と M1-2 の judge 出力 (`[m11_e2e]` 行を除く) は全行一致。M2-1 と M2-2 も全行一致。
- clobber unit は M2 で `0x25c540` の 1 件。M1 では 0 件。
- 範囲 (n=2 の min–max): M1 は ok 864–864, oob 23–23, trap 31–31。M2 は ok 856–856, oob 31–31, trap 38–38。

### 3-1. M2 の差 (qstore on − off, 同一 ldfix 条件)
| 指標 | qstore on (M1) | qstore off (M2) | 差 |
|---|---|---|---|
| ok | 864 | 856 | +8 |
| oob | 23 | 31 | −8 |
| halt0 | 8 | 7 | +1 |
| trap | 31 | 38 | −7 |
| clobber | 0 | 1 | −1 |

REPORT.md §13 (#516, HEAD `8e5f760`) の「修復 864/31/46/1 (clobber 0)」と本測定の qstore on は ok・trap・miss・noproc・clobber が一致する。qstore off (「NC 856/38/46/1 (clobber 1)」) も一致する。

## 4. 「818/21 ↔ 828/13」との関係
- 出典: commit `73532f8` (#419 REPORT §8.2)。(a) 旧スナップショット IR = ok 818 / oob 21 / halt0 56 / trap 77、(c) 再生成・PE 有り = ok 828 / oob 13 / halt0 54 / trap 67 (採用)。
- 本 PR では (a) を再測定していない。(c) の表記は「ldfix・qstore 適用」だが、qstore (#516) は当時未取り込みと読める。(c) の trap 内訳 (halt0 54 / oob 13) は本測定 (halt0 7–8 / oob 23–31) と大きく異なる。差の原因は未調査 (§6 未解決)。
- 本 PR で確定したのは「IR 生成条件を記録し、不一致・欠落を fail-closed にする」こと。測定基準は `ir_conditions.json` の値で識別できる。

## 5. 検証範囲 / 範囲外
- 範囲: 本 runner の 1 ホスト。PE は [WIN64] 展開物の 1 member。ldfix/qstore の両方適用 (既定) と qstore off の 2 条件 (qstore off は §3 の旧測定のみ)。
- 範囲外: 別環境 (作業 VM 等) との一致、R2 の work-m11 再投入、`--full` の成功実走。
- **M3 (`--full`) の現状**: head で実行した (§10)。`m11_scan` は ok、`m11_bounds` が rc 1 で止まる。入力の `tools/m2/work/ghidra_dll/functions_dll.csv` は Ghidra の中間物で、work-m11 にも fl-win64 にも無い。`toolchain-retdec` ([RETDEC]) は取得可能で展開済みだが、CSV が無いため RetDec の lift まで届かない。
- `--full` 経路の repo 外パス (`m11_scan.py` `m11_bounds.py` `m11_tail.py` `m11_lift.sh` `m11_lift_all.sh` `m11_postjs.py`) は、PE を `FL_WIN64_DIR`/`M11_PE` 経由に、work・m2/m6 の参照を repo 内の相対パスに直した (静的確認のみ: `py_compile`・`bash -n`)。実行による確認は未了 (§6)。
- 本 PR で追加した fail-closed 分岐の実測は §9 (NC2 は本 HEAD で実行、build の指紋・PE・qstore 分岐は一時コピーで実行)。

## 6. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| work-m11 スナップショットの R2 再投入 (本 subagent に権限なし)。`docs/WORKFLOW.md` §11 は再生成手順を正とする旨を記載 | 測定基準が Actions 再生成に依存する | #729 (R2 権限者) |
| `--full` の実走: `m11_bounds` が `tools/m2/work/ghidra_dll/functions_dll.csv` を要求し、素材に無い (§10)。lift 成果物がどの PE から出たかも未記録 | WORKFLOW §11 の再生成手順が未検証 | #728 |
| 環境間一致の実測 (別環境で n>=2)。同一 runner の n=3 は §10 で実測済み | 「環境間で一致」は未確認 | #729 |
| `73532f8` (c) の trap 内訳 (halt0 54 / oob 13) と本測定 (halt0 7–8 / oob 23–31) の差、(a) 818/21 の再測定 | 過去数値の解釈 | #729 |
| `ldfix/embed_sx_ab.sh` (CAB-131 A/B) は ldfix 無しの base IR を install し build する。指紋・ldfix 検査で fail-closed になり、A/B は再実行できない | 旧 A/B 結果の再現不可 | #727 |
| NC1 / NC1b / NC3 の再測定 (work-m11 無し)。本 HEAD で NC1 / NC1b / NC2 / NC3 をログ行付きで再実行済み (§9) | rc と理由行の証跡は揃った。素材での再測定は未実施 | #729 |
| `m11_build.sh` 冒頭の `source [EMSDK]/emsdk_env.sh` は emsdk 無しで rc 1 で落ちる (既存) | 前提不足の理由が見えにくい | #730 |
| DEFECTS.md への類型追加 (行案は §7) | カタログ未更新 | #716 (DOCS-9) |

## 7. 類型行案 (DEFECTS.md 本体は未編集)
- 行案: 「前処理の依存 (capstone/pefile・実機バイナリ) が無いとき、IR 生成条件 (ldfix・qstore) を WARNING のみでスキップし、測定基準が環境で変わる (fail-open harness 欠陥)」。検出: `ir_conditions.json` の値。対処: skip を非 0 終了にする (本 PR)。

## 8. 再現
前提: `FL_WIN64_DIR` は [WIN64] の展開先 (`extracted/block00031_PE.bin` を `tar --zstd -xf <fl-win64 artifact> -C <dir> extracted/block00031_PE.bin` で 1 member だけ展開)。`python3 -m pip install --user capstone pefile`。
```
bash tools/m11/m11_e2e.sh                       # M1 (既定, n=2)
bash tools/m11/m11_gen_ir2.sh                   # M2 の前に IR を作り直す (qstore 印を外す)
M11_QSTORE=0 bash tools/m11/m11_e2e.sh          # M2 (n=2)
FL_WIN64_DIR=/nonexistent bash tools/m11/m11_e2e.sh   # NC2: exit 1
```
NC1 (capstone 未導入) は `bash tools/m11/m11_gen_ir2.sh` が exit 1 になることを確認。NC1b は `PE=/nonexistent bash tools/m11/m11_build.sh` (ldfix 記録済みの状態) が exit 1。NC3 は qstore 適用済み IR に対する `M11_QSTORE=0 bash tools/m11/m11_build.sh` が exit 2。

## 9. レビュー指摘への対応 (PR #685 の差し戻し、本 HEAD での実測)
実測 (本 HEAD のコード。素材 (work-m11・toolchain) 無しの runner):
- NC2: `FL_WIN64_DIR=/nonexistent bash tools/m11/m11_e2e.sh` → rc 1。出力 `PE バイナリ無し` / `emsdk 無し` / `capstone/pefile 無し` / `M11_SUMMARY {"reached_stage":0,"stop_reason":"prerequisite missing"}`。
- `m11_cond.py`: `--check` は bind 前 rc 1・bind 後 rc 0・IR 差替え後 rc 1。`--get` を引数なしで呼ぶと usage を出して rc 1 (IndexError 無し)。
- `m11_build.sh` の gate (emsdk 行を no-op にした一時コピーで実行。build 本体は未実行): PE 不一致 rc 2 / 指紋不一致 rc 2 / ldfix 未記録 rc 2 / qstore 前提不足 rc 1 で `qstore=applied` の記録は残る / `M11_QSTORE=0` で applied IR を拒否 rc 2。
- 未実測: `m11_e2e.sh` の非 full 回復分岐 (gen_ir2 の自動実行) と `--full` (前提の素材が無い)。コードのみ確認 (`bash -n`・`py_compile`)。

| 指摘 | 扱い | 根拠・備考 |
|---|---|---|
| 必須 1: `ldfix/audit_lsf_e2e.sh` が PE 無し前提で gen_ir2 を呼ぶ | 直した | `M11_LDFIX=0` の明示 opt-out (ir_conditions `ldfix=disabled`・build 拒否)。加えて、`3807851` で gen_ir2 が `tools/shared/env.sh` を source するようになったため、複製に `tools/shared` を含める (無いと source で失敗)。end-to-end は素材無しで未実行 |
| 必須 2: 既存 work/ の回復経路 (`m11_e2e.sh`) | 直した | ldfix 未記録・指紋不一致・PE 変更で gen_ir2 を自動実行。`alloca/e2e.sh` は指紋を bind して継続可。`ldfix/embed_sx_ab.sh` は §6 で PM 判断 |
| 必須 3: `--full` の PE・repo 外パス | 直した (未実行) | `m11_scan/bounds/tail/lift/lift_all/postjs` を env・相対パスに。[RETDEC] 未取得のため未実行 |
| 必須 4: PR 本文 (Refs・oc_artifacts・検証・起票先) | 直した | PR 本文を更新 (`Refs #680`・`oc_artifacts` 行・検証 節・未解決の起票先) |
| 推奨 5: fail-closed の取りこぼし | 直した | lift 4 chunks・tail・lift boot4・m11_scan・bounds・data/image・lb_check を `must` に |
| 推奨 6: NC の証跡が rc のみ | 直した (§10) | NC1 / NC1b / NC2 / NC3 を本 HEAD でログ行付きで再実行 (§10-2) |
| 推奨 7: n=2 | 直した (§10) | 同一 head で n=3 (survey 件数 3 回一致)。別環境は未実測 (#729) |
| 軽微: `m11_cond.py --get` の IndexError | 直した | usage を出して rc 1 |
| 軽微: commit 件名の途切れ | 不採用 (事実確認) | `git log` で `d1a20ed` の件名は完全。履歴の書換えは force push になるため行わない |
| Copilot: ldfix マーカーを IR に結び付ける | 直した | `ir_sha256` (sha256) を正規 pass (gen_ir2・qstore・alloca) の直後に bind。build は一致しない IR を拒否 (§9 上部) |
| Copilot: qstore skip が applied を上書き | 直した | applied の記録を残す (§9 上部: rc 1 で `qstore=applied` 維持) |
| Copilot: PE 変更で成果物が無効化されない | 直した (lift は未対応) | `pe` を比較し不一致なら gen_ir2・data/image を作り直し。build は pe 不一致を拒否。lift 成果物の PE 指紋は未対応 (§6) |
| Copilot: 検証範囲の索引 (環境間一致) | 直した | DOC_MAP の索引を「本 runner の n=2 のみ・環境間一致は未実測」に |
| Copilot: repo 外の絶対パス (WORKFLOW・本書) | 直した | `FL_WIN64_DIR` 経由・記述を一般化 (`docs/REFERENCES.md` の ID 参照) |
| Copilot: REPORT §15 の数値重複 | 直した | 数値を削除し導線のみ (数値の正は本書) |
| Copilot: 直接原因の断定 | 直した | §1 を「確認できた機構」と「断定しない」に分けた |

起票 (番号は §6 の表を正とする): `--full` の実走と PE 紐付け = #728 / `ldfix/embed_sx_ab.sh` の退役か opt-out = #727 / n≥3 (同一 runner は §10 で実測済み)・環境間一致・work-m11 の R2 再投入・NC の素材での再測定 = #729 / emsdk 前提チェック = #730 / DEFECTS.md 類型追加 = #716。

## 10. head `4e084e1` での再測定 (レビュー指摘 3・推奨 5・6・7)
実行環境: 本 runner (ubuntu, load 0.2–1.1)。`FL_WIN64_DIR` は `fl-win64.tar.zst` の `extracted/block00031_PE.bin` (1 member, 22 227 016 B)。capstone 5.0.7 / pefile 2024.8.26 (`pip install --user`)。`work/` は `work-m11` の旧スナップショット (`ir_conditions.json` 無し) から開始。

### 10-1. survey n=3 (head `4e084e1`) と main (77340a4) の比較
| 測定 | コマンド | rc | 所要秒 | load (開始→終了) | ok | oob | halt0 | trap | miss | noproc | clobber | IR 条件 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | `bash m11_e2e.sh` (旧スナップショット。lift 成果物は有効で、`ir_conditions.json` 無しのため gen_ir2 で IR を回復 → build) | 0 | 101 | 0.93 → 1.07 | 866 | 21 | 8 | 29 | 46 | 1 | 0 | ldfix=applied qstore=applied |
| H2 | `bash m11_e2e.sh` (同, 増分) | 0 | 41 | 0.85 → 0.92 | 866 | 21 | 8 | 29 | 46 | 1 | 0 | 同上 |
| H3 | `bash m11_e2e.sh` (同, 増分) | 0 | 41 | 0.62 → 0.81 | 866 | 21 | 8 | 29 | 46 | 1 | 0 | 同上 |
| M-main | `origin/main` 77340a4 の `bash m11_e2e.sh` (IR を削除して作り直し, `m11_bounds`/`m11_tail` が rc 1 で失敗し `run` で継続した後に gen_ir2 / build) | 0 | 164 | 0.85 (開始) | 866 | 21 | 8 | 29 | 46 | 1 | 0 | 同上 |

- H1〜H3 の survey 件数は全 run で一致 (n=3)。M-main も同値。
- 差分の出所: §3 の 864/23/31 は `3807851` 時点の測定。その後 main に入った m11 変更 (`8afdc9e` の boot5・`c293660` の `M11_PE`・`de50ffa`・`04fafae` 等。`git log 3807851..origin/main -- tools/m11` で 19 files, +665/-116) が差の源。本 PR の差分でも、`origin/main` でも同じ結果になるため、本 PR は survey の出力を変えていない。
- 注: M-main の 2 回目以降 (`m11_bounds` 失敗の経路) は `run` の継続で走るため、main の `--full` 経路は未確認のまま。

### 10-2. NC (本 HEAD のコード。ログ行付き)
| 測定 | コマンド | rc | ログ行 |
|---|---|---|---|
| NC1 | capstone を `ImportError` にした一時ツリーで `bash m11_gen_ir2.sh` | 1 | `[gen_ir2] ERROR: ldfix skip (PE 無し: ... / capstone・pefile 無し) — fail-closed で失敗`。`ir_conditions.ldfix=skipped` |
| NC1b | 一時ツリーで `PE=/nonexistent bash m11_build.sh` (qstore=applied の IR) | 1 | `[m11build] ERROR: qstore skip (PE 無し: /nonexistent / capstone・pefile 無し) — fail-closed で失敗`。`qstore=applied` は残る |
| NC1b' | `PE=/nonexistent` (記録 PE は実 PE) で `m11_build.sh` | 2 | `[m11build] ERROR: IR の生成 PE (...) と現在の PE (/nonexistent) が違う` |
| NC2 | `FL_WIN64_DIR=/nonexistent bash m11_e2e.sh` | 1 | `[m11_e2e] PE バイナリ無し: /nonexistent/...` / `M11_SUMMARY {"reached_stage":0,"stop_reason":"prerequisite missing"}` |
| NC3 | 一時ツリーで `M11_QSTORE=0 bash m11_build.sh` (PE は記録と一致, qstore=applied の IR) | 2 | `[m11build] ERROR: work/boot_final.ll は qstore 適用済み (ir_conditions.json)。M11_QSTORE=0 の前に m11_gen_ir2.sh で IR を作り直すこと` |

- NC3 は PE を記録と揃えた状態で、qstore gate (rc 2) に到達した (推奨 5 への対応)。PE 不一致で先に落ちる試験ではない。

### 10-3. `--full` (head)
- `bash m11_e2e.sh --full` → rc 1 (fail-closed)。`m11_scan: ok` の後、`m11_bounds` が `FileNotFoundError: tools/m2/work/ghidra_dll/functions_dll.csv` で失敗。
- `functions_dll.csv` は `tools/m2/m2.sh` が Ghidra headless (`DumpFunctions.java`) で作る中間物で、`work-m11` にも `fl-win64` にも含まれない。`toolchain-retdec` ([RETDEC]) は展開されるが、この CSV が無いので RetDec の lift に届かない。
- 結論: `--full` は本 runner では成功しない。WORKFLOW §11 の `--full` が正という記述は未検証のまま (#728)。
- 検証 (推奨 6): `--full` の実走を試みた。「実走しない理由」は CSV 欠落 (上記)。
