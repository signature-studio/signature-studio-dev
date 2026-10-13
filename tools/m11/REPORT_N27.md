# REPORT_N27 — #680: survey 測定基準の固定化 (IR 生成条件の fail-closed・PE パス env 化・n 実測)

既知類型との関係: DEFECTS.md D17 (qstore) と無関係の harness 欠陥 (fail-open)、類型行案あり (§6)。

## 1. 結論
- 「OFF が 818/21 ↔ 828/13 と変わる」の直接原因は、IR 生成条件 (ldfix・qstore) が **黙って** 変わっていたこと。`m11_gen_ir2.sh` の ldfix と `m11_build.sh` の qstore は capstone/pefile 不足時に WARNING のみでスキップされ、`m11_e2e.sh` は PE 無しでも exit 0 だった (fail-open)。PE パスも `/home/ubuntu` 固定だった。
- 修正 (commit `3807851`): skip は非 0 終了。PE は `FL_WIN64_DIR` 経由 (既定値は従来どおり)。IR 生成条件を `work/ir_conditions.json` に記録し、`m11_judge.py` が印字する。
- 実測 (本 runner, capstone 5.0.7 / pefile 2024.8.26, PE は [WIN64] の `extracted/block00031_PE.bin` 1 member): 既定 (qstore on) は n=2 で完全一致 (ok 864 / oob 23 / trap 31 / miss 46 / noproc 1 / clobber 0)。qstore off は n=2 で完全一致 (ok 856 / oob 31 / trap 38 / clobber 1)。qstore の有無で ok が 8 件、clobber が 1 件動く。
- **未達**: 環境間一致 (別環境との比較) は未実測。本 runner の n=2 は再現性のみ。R2 への work-m11 再投入は権限なし。M3 (`--full`) は未実施 (§5)。

## 2. 原因の切り分け (コード調査)
| 箇所 | 修正前 | 修正後 (3807851) |
|---|---|---|
| `m11_gen_ir2.sh` ldfix | capstone/pefile/PE 無し → WARNING, IR は未 ldfix で続行 (exit 0) | ERROR, exit 1。`ir_conditions.json` `ldfix=skipped` |
| `m11_build.sh` qstore (`M11_QSTORE=1` 既定) | 同 WARNING, exit 0 | ERROR, exit 1。`qstore=skipped` |
| `m11_build.sh` `M11_QSTORE=0` | 適用済み IR でも黙って無効扱い | 適用済み (`qstore=applied`) の IR なら exit 2 (IR の作り直しを要求) |
| `m11_build.sh` ldfix 未記録 | 検査なし | `ldfix=applied` の記録が無い IR は exit 2 (旧スナップショット IR を弾く) |
| `m11_e2e.sh` 前提不足 | PE・emsdk・node 無しで exit 0 | exit 1 (capstone/pefile 不足も前提に追加) |
| `m11_e2e.sh` IR 生成・build 失敗 | `run` で継続 (stale wasm で survey 実行) | `must` で即失敗 (exit 1) |
| PE パス | `m11_e2e.sh` `m11_gen_ir2.sh` `m11_data_gen.py` `m11_image_gen.py` `m11_icall_audit.py` が `/home/ubuntu/...` 固定 | `FL_WIN64_DIR` / `M11_PE` 経由 (既定値は従来どおり) |

## 3. 測定 (全て commit `3807851` の HEAD 内容・同一 runner・ `FL_WIN64_DIR` は [WIN64] 展開先)
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
- 範囲: 本 runner の 1 ホスト。PE は [WIN64] 展開物の 1 member。ldfix/qstore の両方適用 (既定) と qstore off の 2 条件。
- 範囲外: 別環境 (作業 VM 等) との一致、R2 の work-m11 再投入、`--full` (RetDec 再生成) の実行。
- **M3 未実施の理由**: `--full` の経路 (`m11_scan.py` `m11_bounds.py` `m11_tail.py` `m11_lift_all.sh` `m11_lift.sh`) が `/home/ubuntu/work/webstudio/...` を書込み・読込みに使う。本 runner に該当ディレクトリは無く、途中で `work/` を破壊する恐れがあるため実行しなかった。
- 40 分制限内で M1/M2 を優先したため、`--full` の依存パス除去は本 PR の範囲外 (§6)。

## 6. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| work-m11 スナップショットの R2 再投入 (本 subagent に権限なし)。`docs/WORKFLOW.md` §11 は再生成手順を正とする旨を記載 | 測定基準が Actions 再生成に依存する | Issue #680 の子 (R2 権限者) |
| `--full` 経路の `/home/ubuntu/work/webstudio` 依存 (`m11_scan.py` OUT・`m11_bounds.py`・`m11_tail.py`・`m11_lift_all.sh`・`m11_lift.sh` の BIN・`m11_postjs.py` 既定)。M3 未実施 | WORKFLOW §11 の再生成手順が未検証 | 新規子 (PM 起票) |
| 環境間一致の実測 (別環境で n>=2)。本 PR は同一 runner の n=2 のみ | 「環境間で一致」は未確認 | Issue #680 の子 |
| `73532f8` (c) の trap 内訳 (halt0 54 / oob 13) と本測定 (halt0 7–8 / oob 23–31) の差、(a) 818/21 の再測定 | 過去数値の解釈 | Issue #680 の子 |
| DEFECTS.md への類型追加 (行案は §7) | カタログ未更新 | PM (docs/DEFECTS.md 更新) |

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
