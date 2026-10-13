# REPORT_N1165 — #1165: 旧 IR (818/21/56/77) の再測定・ldfix 切り分け・ldfix 無し build 経路

既知類型との関係: DEFECTS.md の類型は本測定で新規確定しない (ldfix の有無による survey 差のみ観測)。該当なし。

## 1. 結論
- (a) 旧 IR の再測定: **達成**。`d6a17b64` の手順 (旧 `m11_build.sh` + `survey_units.mjs`) で work-m11 の旧 IR を build・測定すると ok 818 / halt0 56 / miss 46 / oob 21 / noproc 1 (trap 77 = oob 21 + halt0 56)。Issue の旧値と一致。
- (c) lift 段の切り分け: **部分達成**。ldfix の有無だけで 818 ↔ 828 (ok 10 件差) が説明できた。ただし lift 段 (RetDec 出力) の起点は未特定 (§4 未解決)。
- ldfix 無し IR で build する経路: **達成 (opt-in)**。`M11_ALLOW_LDFIX_DISABLED=1` のときだけ `ldfix=disabled` の IR を build する。既定は従来どおり拒否 (rc 2 を実測)。変更 commit `87b9ecbd`。
- HEAD の検証: **部分達成**。`m11_build.sh` と `m11_survey.mjs` は HEAD で通る (2×2 を実測)。`m11_e2e.sh` は素材不足で `m11_bounds` が fail-closed (rc 1) し、e2e 全体は未通過。
- 未達が残るため、Issue は `Refs #1165`。

## 2. 測定の条件
- 検証起点 (測定 commit): `87b9ecbd` (本 PR の唯一のコード変更。`tools/m11/m11_build.sh`)。HEAD ではこの commit に REPORT のみ追加。
- 素材: work-m11 (snapshot の IR・`m11_image.bin`・lift 中間物 `boot{0..4}.lift.ll`)・fl-win64 (PE 1 member, sha256 `b2c64da4…`)・toolchain-emsdk・toolchain-retdec。`FL_WIN64_DIR` は fl-win64 の展開先。
- 環境: 4 vCPU, load 0.04〜0.9 (各測定の前後を記録), 1 並列。Node v22.23.3。capstone 5.0.7・pefile 2024.8.26。
- 作業ディレクトリ: 旧手順は detached worktree (`d6a17b64`)、HEAD 手順は `87b9ecbd` の worktree。どちらも `tools/m11/work/` (gitignore) に成果物を置く。

## 3. 測定値

### 3-1. (a) 旧 IR の再現 (旧手順 `d6a17b64`)
| 測定 | IR | build | survey | 所要秒 | load | ok | halt0 | oob | miss | noproc |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | snapshot `boot_final.ll` (sha `69c774de…`) | `d6a17b64` の `m11_build.sh` rc 0 (10 s) | `survey_units.mjs` rc 0 | 11 | 0.39→0.48 | **818** | **56** | **21** | 46 | 1 |

- 対照 A0 (snapshot の同梱 wasm を同梱の `work/survey.mjs` で実行): ok 812 / trap 83 (oob 34・halt0 48・abort 1)。snapshot の wasm は build 時点が古く、旧 IR の 818 とは一致しない。**旧 IR の値は「snapshot IR を現 build 手順で作り直した wasm」からしか再現しない**。
- 旧 IR の入手経路: `work-m11.tar.zst` の `tools/m11/work/boot_final.ll` (10/10 作成, 19,787,837 B)。build 前提の `m11_image.bin` も同梱。`ir_conditions.json` は無い (`ldfix` 記録なし)。

### 3-2. (c) ldfix の有無による差 (旧 build 手順 `d6a17b64`)
同じ lift 中間物 (snapshot 由来) から HEAD の `m11_gen_ir2.sh` で IR を再生成し、旧 build で測定。

| IR | 生成条件 | ir_sha256 | ok | halt0 | oob | miss | noproc |
|---|---|---|---|---|---|---|---|
| ldfix0 | `M11_LDFIX=0` (ldfix=disabled) | `25e931f2…` | **828** | **54** | **13** | 46 | 1 |
| ldfix1 | 既定 (ldfix=applied) | `2c68ceae…` | **818** | **56** | **21** | 46 | 1 |

- ldfix0 の 828/13/54 は `73532f8` の (c) 値 (ok 828 / oob 13 / halt0 54 / miss 46 / noproc 1) と数値が一致する。`73532f8` の (c) は条件表記が「ldfix・qstore 適用」だが、当時の生成記録は無いため、一致の理由 (表記の誤りか別条件か) は未確定。
- ldfix の差: ok +10 / oob −8 / halt0 −2。ldfix1 の差分は `ldfxu` 122 行 (load の値↔アドレス修復)。

### 3-3. HEAD (`87b9ecbd`) の build・survey (2×2、各 n=1)
IR はそれぞれ `m11_gen_ir2.sh` で作り直した clean な IR (sha 一致を `m11_cond.py --check` で確認)。build は `M11_ALLOW_LDFIX_DISABLED=1` (ldfix0 のみ必要)・`M11_QSTORE` を切替。

| 組 | ldfix | qstore | build 秒 | survey 秒 | ok | miss | trap (oob / halt0 / unreachable) |
|---|---|---|---|---|---|---|---|
| H1 | 0 | on | 21 | 13 | 868 | 47 | 26 (17 / 8 / 1) |
| H2 | 0 | off | 10 | 13 | 867 | 47 | 27 (18 / 8 / 1) |
| H3 | 1 | on | 21 | 15 | **870** | 47 | 24 (16 / 7 / 1) |
| H4 | 1 | off | 10 | 14 | 868 | 47 | 26 (18 / 7 / 1) |

- H3 (既定経路) の ok 870 は REPORT_N27 §10 (head `4e084e1`) の 870 と一致。
- qstore の差は H3 − H4 = ok +2 / trap −2。ldfix の差は H3 − H1 = ok +2 / trap −2。どちらも小さい。
- 旧 build (A1/ldfix1 = ok 818) から HEAD (H4/ldfix1, qstore off = ok 868) までの +50 は、ldfix でも qstore でも説明できない。**`d6a17b64` 〜 HEAD 間のコード変更 (build・post・passes のいずれか) が原因だが、未特定** (§4)。
- miss は 46 (旧) → 47 (HEAD) で 1 件増。未調査。

## 4. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| (c) lift 段 (RetDec 出力) の起点。snapshot IR (`69c774de…`) と ldfix0 再生成 IR (`25e931f2…`) は 7,237 行差、`alloca [N x i64]` が snapshot 54 件 / 再生成 0 件。lift 中間物は同一だが、この差が lift 段由来か `m11_passes` 由来かは未切り分け | 73532f8 (c) 条件の確定 | #1165 (Refs のまま再依頼) |
| 旧 build (`d6a17b64`) → HEAD で ok 818 → 868 (+50) の原因となるコード範囲の二分探索 | 過去数値の解釈 | #1165 |
| `m11_e2e.sh` が `functions_dll.csv` 不足で `m11_bounds` fail-closed (rc 1, 1 s)。既定経路の e2e は未通過 (REPORT_N27 §10 と同じ)。`functions_dll.csv` は素材に無い Ghidra headless の中間物 (WORKFLOW §11) で、作成は未実施。ldfix0 の e2e 全体も未実施 | 受入 (e2e 検証) | #1165 (Ghidra で作成して再実施) |
| miss 46 → 47 の 1 件増 | 測定基準 | #1165 |

## 5. 検証範囲 / 範囲外
- 範囲: 本 runner の 1 ホスト・PE 1 member・n=1 (旧 build・HEAD の各測定)。環境間一致は未実測。
- 範囲外: e2e 全体 (`m11_e2e.sh`)・`--full` (RetDec からの再生成)・lift 段の再現。

## 6. 再現
```sh
# fl-win64 展開先を FL_WIN64_DIR に。work-m11 を tools/m11/work に展開 (repo root で tar --zstd -xf work-m11.tar.zst -C .)
cd tools/m11
M11_LDFIX=0 bash m11_gen_ir2.sh                       # ldfix0 IR (ldfix=disabled)
M11_ALLOW_LDFIX_DISABLED=1 bash m11_build.sh          # ldfix 無し IR の build (opt-in)
node m11_survey.mjs                                   # 集計行 M11_SURVEY (ok/halt0/oob/miss)
bash m11_build.sh && node trap_triage/survey_units.mjs work/trap_triage/base.json   # 旧 build 手順 (d6a17b64 で実施)
M11_QSTORE=0 bash m11_build.sh                        # qstore off
```

## 7. ネガティブコントロール
- NC-1 (既定の拒否): `m11_cond.py` で `ldfix=disabled` の IR を `M11_ALLOW_LDFIX_DISABLED` 未指定で build → **rc 2** (`ldfix=applied の記録無し` ERROR)。opt-in が既定の拒否を外していないことの確認。
- NC-2 (IR 指紋): 旧 IR (`69c774de…`) を現 build で使うと `ldfix` 記録が無く rc 2 (#680 の fail-closed を維持)。
