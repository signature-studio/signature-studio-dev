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
| `ldfix/embed_sx_ab.sh` (CAB-131 A/B) は ldfix 無しの base IR を install し build する。指紋・ldfix 検査で fail-closed になり、A/B は再実行できない | 旧 A/B 結果の再現不可 (実測値は `ldfix/REPORT_APPENDIX_AB.md` §3.3 が正)。#727 で**退役**: 冒頭で理由を出して exit 2。base 専用 opt-out は #680 の fail-closed を弱めるため採らない | #727 (退役済み・実行可否: 不可) |
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

## 11. #729: head での survey n=3 (同一 runner・work-m11 から IR 再生成)
- 条件: `1f83c5ee` (origin/main) に本 PR の `m11_lift.sh` の RetDec 解決修正のみ。素材は `fl-win64` (PE 1 member)・`work-m11`・`work-liftdiff`。`m11_gen_ir2.sh` を先に実行して `ir_conditions.json` を作成 (42.8 秒, ldfix applied, `ir_sha256` 995351f5…)。
- 障害: `m11_e2e.sh` が boot5 の RetDec lift で fail-closed (`retdec-decompiler: command not found`)。`[RETDEC]` の bin が PATH に無いことが原因。`m11_lift.sh` の RetDec 解決を `command -v` → `[RETDEC]` の bin (スクリプト内の既定) に変更して解消。

| 測定 | rc | 所要秒 | load (開始→終了) | ok | oob | halt0 | trap | miss | noproc | clobber | oom |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 (初回。lift boot5 込み) | 0 | 148 | 0.05 → 1.07 | 870 | 17 | 8 | 25 | 46 | 1 | 0 | 1 |
| R2 (増分) | 0 | 44 | 0.70 → 0.86 | 870 | 17 | 8 | 25 | 46 | 1 | 0 | 1 |
| R3 (増分) | 0 | 44 | 0.86 → 1.26 | 870 | 17 | 8 | 25 | 46 | 1 | 0 | 1 |

- n=3 の min–max: ok 870–870 / trap 25–25 / miss 46–46 / clobber 0–0 / oom 1–1。halt0 は trap 内の `halt0->longjmp` 8 件 (R1 は 8, R2・R3 も 8)。oob 17 件。
- `reached_stage` 4 / `units_run_full` 53 / `wasm_bytes` 6,042,784 (R1)。
- 注: 本節の ok 870 は §10-1 (head `4e084e1` で ok 866 / oob 21 / halt0 8 / trap 29) と**一致しない**。差の出所は未切り分け (本 run は work-m11 の旧スナップショットから `m11_gen_ir2.sh` で IR を作り直した。§10-1 は同 head の別 run で、IR の作り方・素材の版が同一かは未確認)。§3 の旧値 (864/23/31) とも異なる。
- 未実施: 別環境 (別 runner / VM) での n>=2、work-m11 の R2 再投入 (素材権限者)、73532f8 (c) の trap 内訳差の原因調査。
- HEAD 再現 (`a4aa766c`・retdec を PATH に入れない・`work/boot5.*` を削除して lift から): rc 0 / 101 秒 / load 0.07 → 0.83 / ok 870 · trap 25 · oom 1 · clobber 0 · miss 46。修正前は同条件で `retdec-decompiler: command not found` により 1 秒で rc 1。

### 11-b. #729: 別 runner VM での n=2 (`b4dac086` = origin/main 起点の worktree)
- 環境: 前節 (§11) と別の runner VM (hostname `runnervmmprz5`・machine-id 先頭 `566c0bdf`)。素材 `fl-win64` (PE 1 member, sha256 `b2c64da4…`)・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`・`work-liftdiff` を展開。
- 前提の追加: `work-m11` に `lift_pe.sha256` が無く、`m11_e2e.sh` は全再生成に入る。`m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を要求するため、Ghidra 12.1.4 を GitHub Release (`ghidra_12.1.4_PUBLIC_20260921.zip`) から取得して JDK 21 (Temurin)・`MAXMEM=12G`) で `DumpFunctions.java` を実行した (rc 0 / 609 秒 / 59010 行)。
- IR 生成: `m11_gen_ir2.sh` rc 0 / 44 秒 / ldfix applied。

| 測定 | rc | 所要秒 | load (開始→終了) | ok | oob | halt0 | trap | miss | clobber | oom | ir_sha256 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 (全再生成: scan→lift 4 chunk→tail→IR→build→survey) | 0 | 599 | 0.57 → 1.22 | 870 | — | — | 25 | 46 | 0 | 1 | `20d68876…` |
| E2 (増分) | 0 | 45 | 1.04 → 1.08 | 870 | — | — | 25 | 46 | 0 | 1 | `20d68876…` |

- E1 の `reached_stage` 4 / `units_run_full` 53 / `wasm_bytes` 6,042,952。trap の停止点は `unreachable @ function_8c5eb0`。E2 の `ir_sha256` は E1 と一致。
- 結論: 本 VM で n=2 (E1・E2) の survey 値が一致し、§11 (別 run・別 VM 不明) の 870/25/1/0/46 とも一致した。ただし §11 の VM を確認していないため「環境が違う」とは断定しない。別クラウド・別 OS イメージでの一致は未確認。
- 注: E1 の全再生成の IR sha256 (`20d68876…`) は §11 の `995351f5…` と異なる。§11 は work-m11 から `m11_gen_ir2.sh` のみで作った IR、E1 は scan→lift→tail を走らせ直した IR で、作り方が違うため差は想定内。survey の値は同一。

## 12. #728: `--full` の実走 (head `2e128c5c`) と lift 成果物の PE 紐付け
実行環境: 本 runner (4 vCPU, 16 GiB)。素材 `fl-win64` (`block00031_PE.bin`, sha256 `b2c64da4…`)・`toolchain-retdec` ([RETDEC])・`toolchain-emsdk`・`work-m11`・`work-liftdiff` を展開。Ghidra 12.1.4 (公式 release, JDK 21) で `functions_dll.csv` を再生成 (59 009 行, sha256 `90d1bbac…`, Ghidra headless 約 10 分)。capstone 5.0.7 / pefile 2024.8.26。
- 測定 head: 下表の F1〜F3 は `2e128c5c` (PR 本文の `2e128c5c` 測定)。現 head `74312499` は `2e128c5c..74312499` のスクリプト差分が空で、コード同一。その後の修正 commit `74b365f6` は `m11_lift.sh` の 1 行 (RETDEC_ROOT 既定値) だけを変える。F3 は PATH で retdec を解決しており、この行は通らない。下の (a)(b)(c) で修正後 head を実測。

| 測定 | コマンド | rc | 所要秒 | 結果 |
|---|---|---|---|---|
| F1 | `m11_e2e.sh --full` (head `616d1dd2` 相当・RetDec の PATH 無し) | 1 | 36 | `lift boot4 #1` が `rc=127` (retdec-decompiler 無し)。`m11_lift_all.sh` がこれを無視して DONE を立てていた (fail-open) |
| F2 | `PATH=<[RETDEC]>/bin:$PATH m11_e2e.sh --full` (`616d1dd2`) | 0 | 636 | 全段 ok。`reached_stage` 4、trap `memory access out of bounds` @ function_8c6530 |
| F3 | 同上 (head `2e128c5c`: fail-closed 化 + PE 指紋記録 + RetDec の PATH 解決) | 0 | 633 | 全段 ok。`reached_stage` 4、同じ trap。`ir_sha256` = `fd628f3d…` (F2 は `a5841949…`) |

- F3 の survey: units_run_full 53 / 942、survey_ok 870、trap 25 (oom 1)、clobber 0、miss 46、wasm 6 042 784 B。
- **解決経路の実測 (修正 commit `74b365f6`)**: `m11_lift.sh` を 3 range (`chunk_0.txt` の先頭 3 range, `work-m11` 由来) で実行。`--full` ではない。最終 head `162d9a80` (main を merge) では `tools/m11/m11_lift.sh` が `74b365f6` と同一で、(a)(b)(c) を再実行して同じ結果を確認した。
  - (a) PATH・RETDEC 無し、`RETDEC_ROOT=<[RETDEC]>`: rc 0 / `[lift] RetDec OK: 32 lines` / `[lift] ir5 OK: 27 lines` (解決して進む)。
  - (b) PATH・RETDEC・RETDEC_ROOT が無効 (`/nonexistent`): rc 1 / `[lift] FAIL: retdec-decompiler 無し (RETDEC_ROOT=/nonexistent; REFERENCES [RETDEC])`。
  - (c) PATH・RETDEC 無し、RETDEC_ROOT 未設定: 解決先 `<[RETDEC]>/bin/retdec-decompiler`、実行可 (`exec-ok`)。
- **PE の紐付け**: `work/lift_pe.sha256` に lift 生成時の PE sha256 を記録し、不一致なら lift を作り直す (`m11_e2e.sh`)。ただし作り直し経路の再実行 (指紋一致で skip・不一致で再生成) は**未実測**。
- **fail-open の修正**: `m11_lift_all.sh` は chunk の rc 非 0 で止まる。`m11_lift.sh` は `retdec-decompiler` を PATH → `$RETDEC_ROOT/bin` (未設定時は [RETDEC] の既定位置) の順で解決し、無ければ fail。
- **指紋の作り直し経路 (実測・G1〜G3)**: 同一 runner・2026-10-13・head `551931b7` 相当・素材 fl-win64 / toolchain-retdec / work-m11 / work-liftdiff。Ghidra 12.1.4 で `functions_dll.csv` 再生成 (10 分 10 秒・rc 0・59 010 行・JDK 21・MAXMEM 8G)。

| 測定 | 条件 | rc | 所要秒 | 経路 | ir_sha256 | ok / trap / miss |
|---|---|---|---|---|---|---|
| G1 | `work/lift_pe.sha256` 無し | 0 | 621 | 全再生成 → 指紋記録 | `fd628f3d…` | 870 / 25 / 46 |
| G2 | 指紋一致 (G1 の直後) | 0 | 45 | lift 段 skip・build 増分・実行 A/B | `fd628f3d…` | 870 / 25 / 46 |
| G3 | 指紋を 0 埋めで不一致化 | 0 | 605 | 全再生成 → 指紋を正値へ再記録 | `a8c36b84…` | 870 / 25 / 46 |

- 結論: 指紋無し・不一致で全再生成し指紋を書き直す。一致で lift を skip する。3 経路とも実測で動く。G1 と G3 は同一 PE・同一コードだが `ir_sha256` が異なる (#960 と同じ非決定性。IR の一致は保証されない)。
- G3 の `m11_tail` が `tools/m11/m11_extra_seeds.txt` に `0x4572b0` を 1 行追加した (`m11_tail.py` の「コミット対象」仕様)。この commit には含めない (main 側の seeds が別途変わっているため)。
- 旧記述: 指紋無し・不一致で再生成する経路は未実測。
- **未解決**: (a) F2 と F3 で IR の `ir_sha256` が異なる。RetDec・ir5_patch・gen_ir2 の出力が実行ごとに変わる可能性があるが、原因は未切り分け。(b) `reached_stage` 4 の trap (§6 と同類の未解決。lift 成果物が正しいかは未判定)。(c) Ghidra 中間物 `functions_dll.csv` を素材に含めない場合、`--full` は Ghidra 再生成 (WORKFLOW §11 手順) が前提。
- 起票: (a)(b) は子 issue を #728 の下に起票 (番号はコメント参照)。

## 13. #936: `73532f8` (c) の trap 内訳 (halt0 54 / oob 13) と現 HEAD 実測 (halt0 8 / oob 16) の差の切り分け
- 受入条件 (#936 の縮小後、PM 判断): (c) 再生成条件 (ldfix・qstore・PE) を明示し、差が条件の違いで説明できるかを実測値付きで記録する。(a) 旧 IR (818/21/56/77) の再測定は別 issue #1165 に分離。
- 測定 head: `b4dac086` (origin/main)。素材 fl-win64 (PE 1 member, sha256 `b2c64da4…`)・work-m11・work-liftdiff・toolchain-retdec・toolchain-emsdk (展開先は [EMSDK]・[RETDEC])・capstone 5.0.7 / pefile 2024.8.26。`FL_WIN64_DIR` は展開先。
- 旧 (c) の数値は `trap_triage/survey_units.mjs` (`73532f8` の REPORT.md §8.2) で取った。現 HEAD で同じビルドに `survey_units.mjs` (F0') を当てた実測を、F0 の転記値と照合する (下表)。ok・halt0・miss・trap は転記値と一致する。oob は転記 17 と実測 16 で 1 件違う。この差は oom 1 の分類差によると推定するが、未確認。

| 測定 | IR 条件 (ir_conditions.json) | rc | 所要秒 | load (終了) | ok | oob | halt0 | trap | miss | noproc | clobber |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F0 | HEAD 既定 (ldfix applied・qstore applied・ir_sha256 `1fc847d4…`)・`m11_e2e.sh` (`m11_survey`) | 0 | 43 | 1.16 | 870 | 17 (§11 転記) | 8 (§11 転記) | 25 (oom 1 含む) | 46 | 1 | 0 |
| F0' | 同 IR・`survey_units.mjs` | 0 | 10 | – | 870 | 16 | 8 | 25 (oom 1 含む) | 46 | 1 | – |
| X1 | qstore 無し (ldfix applied, `M11_QSTORE=0 m11_build.sh`) | 0 | 9 | – | 868 | 18 | 8 | 27 (`m11_survey`) | 46 | 1 | 0 |
| X2 | 実際の条件: ldfix 無し・qstore 無し (`M11_LDFIX=0` で gen)。**注記: 測定時に `work/ir_conditions.json` を applied に書き換えて build を通した。保存された条件ファイルは実際の IR 条件と一致しない。この数値は採用しない (条件の再現・再記録は未実施)** | 0 | 36 | – | 867 | 18 | 9 | 28 (`m11_survey`) | 46 | 1 | 0 |

- F0 の oob 17・halt0 8 は §11 (R1〜R3: 870/17/8/25) の実測値の転記である。本節では F0 の内訳を再測定していない (`m11_survey` の出力は本 run に残っていない)。
- F0 と F0' の対比は**転記値との照合**であり、再測定の一致ではない。F0' を同一 IR で実測した ok 870・halt0 8・miss 46・trap 25 は、§11 の転記値 (870/8/46/25) と一致する。oob は転記 17 と実測 16 で 1 件違う。F0' の内訳は oob 16 + halt0 8 + oom 1 = 25 で trap と合う。転記 F0 は oob 17 + halt0 8 = 25 で、oom 1 が oob 側に含まれていると読めば合うと推定する。この分類の違いは推定であり、未確認。
- X1 の差は ok −2・trap +2 にとどまる。(c) の trap 67 (oob 13 / halt0 54) とは一桁以上違う。X2 は採用しない (上表の注記)。
- 結論: 73532f8 (c) の halt0 54 は、本測定の範囲では再現しない。
- 再生成条件との関係: qstore の有無では差を説明できない (X1 は halt0 8 のままで、ok −2・trap +2 にとどまる)。ldfix の有無では説明できるかは未確定 (採用できる実測が無い。X2 は採用しない)。
- halt0 の大半 (54 件) は **IR 生成前段 (RetDec lift・work-m11 の世代) の違い**に由来すると推定されるが、本測定では切り分け未了。
- 未解決 (起票先): 73532f8 (c) の lift 成果物の再構成 (当時の lift 入力・RetDec 版の特定)、ldfix 無しの IR で build する経路 (現状 `m11_build.sh` は `ldfix=disabled` を拒否)、(a) 818/21 の再測定 (旧 IR snapshot を `work-m11` から直接測る手順が必要) = #1165。
- 検証範囲: 本 runner の 1 ホスト・PE 1 member・n=1 (F0 のみ 2 ハーネス)。環境間一致は未実測。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/m11/m11_gen_ir2.sh && bash tools/m11/m11_e2e.sh` (lift 成果物が無ければ `work/lift_pe.sha256` で全再生成に入る。work-m11 は `lift_pe.sha256` を含まないため、本 run は PE の sha256 を手で書いて増分経路で回した。§12 G2)。
## 14. #960: `--full` を同一 HEAD・同一 PE で 2 回実行し、IR の差の段を切り分け

- 条件: HEAD `29f63707` (origin/main)・PE `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…`)・`toolchain-retdec`・`work-m11`・`work-liftdiff`。Ghidra 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`・sha256 `ddac49f9…`) で `functions_dll.csv` を再生成 (8 分 8 秒・rc 0・59 010 行・JDK 21)。2 回目の前に `work/` の lift・IR 生成物を削除 (`ir_conditions.json` 含む) してから全再生成した。
- PATH は `[RETDEC]` の bin と agent-py を先頭に置き、`FL_WIN64_DIR`・`RETDEC_ROOT` を設定。

| 測定 | コマンド | rc | 所要秒 | load (開始→終了) | ir_sha256 | reached_stage | survey ok / trap / miss |
|---|---|---|---|---|---|---|---|
| N1 | `bash m11_e2e.sh --full` | 0 | 506 (8 分 26 秒) | 1.32 → 1.10 | `20d68876…` | 4 | 870 / 25 / 46 |
| N2 | 同 (生成物を削除してから) | 0 | 492 (8 分 12 秒) | 0.80 → 1.03 | `90c59e22…` | 4 | ok 870 (trap / miss は未抽出) |

- **結論**: 同一 HEAD・同一 PE・同一素材でも `ir_sha256` は一致しない (N1 ≠ N2)。N1 の survey は 870 / 25 / 46 (`M11_SUMMARY`)、N2 は survey_ok 870 を確認した。IR の bytes の差が survey 結果に出るかは N2 の trap / miss を抽出して未確認。
- **差の段 (N1 と N2 を比較・N1 の中間物は `$RUNNER_TEMP/run1` に保存)**:
  - RetDec 段 `boot0.drc.ll` が最初に変わる。`uselistorder` 行の並びと、`@global_var_*` 定義行の位置の計 2 行の差。この 2 種を除いた差は無い。`boot0.drc.c`・`*.drc.dsm`・`*.drc.config.json` の差は `time` / `Decompilation date` と変数宣言 1 行 (`0x52a738` 付近) に限られる。
  - `boot0.lift.ll` (ir5_patch 後) は `@global_var_13bd880` 定義の 1 行が移動するだけ (行集合は一致)。
  - `boot_final.ll` は末尾の空行を除くと行集合が一致し、行の並びだけが違う。sha256 の差はこの並び順から出る。
  - 段の切り分けの結論: 最初に変わるのは RetDec (drc.ll) の出力順。後段 (norm0・ir5・gen_ir2) が順序を保存するかは、各段の入出力を個別に比較していないため未確認。`m11_passes.py` の一部は `sorted(...)` を使うが、順序を完全に固定するものかは未確認。
- **既知との関係**: RetDec の lift 出力が同一入力で実行ごとに変わることは #668 (LIFTLIB-9・k80 の drc.ll) で既に記録されている。本件はその m11 側の再現 (`--full` の boot0〜boot5)。
- **扱いの提案 (受入 3・PM 判断待ち)**: `ir_sha256` は実行ごとの固定指紋として使えない。survey 基準の比較は件数 (ok / trap / miss / reached_stage) で行い、`ir_sha256` の一致を再現性の証拠にしない。`ir_sha256` は「その IR から build した」ことの gate としてのみ使う (`m11_build.sh` の照合は現状どおり)。
- **未解決**: RetDec 段の出力順を固定する修正 (drc.ll の正規化、または RetDec 側の順序固定) は未実施。起票先 #668。
- 再現: `FL_WIN64_DIR=<fl-win64>/ RETDEC_ROOT=<[RETDEC]>/retdec PATH=<[RETDEC]>/bin:$PATH bash tools/m11/m11_e2e.sh --full` を 2 回 (間に `work/` の boot*/ir_conditions を削除)。
