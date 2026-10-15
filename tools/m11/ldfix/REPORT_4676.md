# REPORT #4676 — `10479c7` の再判定と本番影響の測定 (LD-237・#3675 子・#4675 の後)

親: #3675 (LD-172)。前提: #4675 (PR #4695・`fix_ld236.py`・既定 OFF)。

## 1. 結論

- `10479c7` の判定根拠 (ii) (`%492` と slot の対応) と (iii) (`stack_var_16` の後続の読み) を確認した。判定は**判定不能のまま**。理由は §3。
- `spill178_1161.tsv` は再生成した。既存の結果と**一致** (差分 0 行)。
- 本番 unit e2e (既定 OFF と `M11_FIX_LD236=1` の 2 通り) は、unit 結果 (run・survey・trap・miss・clobber) が**一致**した。`1046a30` の読み値は実行時に確認していない (§4)。
- 本番 e2e の回帰ゲートは OFF・ON とも `survey ok=875 != 期待 873` で失敗した。原因は未確認 (素材の指紋検査を迂回した参考値による環境差の可能性。§4・§5)。OFF でも同じ失敗のため、修正 (`M11_FIX_LD236`) が原因ではないことだけは確認した。

## 2. 再判定 (受入 1)

測定 commit: 本 PR のコードを変えた最後の commit (§6)。

| site | 判定 | 根拠 |
|---|---|---|
| 10479c7 | 判定不能 (維持) | 下記 |

- (i) `[rbp+0x4d8]` への書込は `1047942` の 1 箇所だけ (`1046a30`〜`1048000` の全数)。`lea` で取るアドレスも無い (REPORT_2958 §3 と同じ)。
- (ii) IR: `%491 = add %363,364`・`%492 = inttoptr %491` が P。`104797c` の `store i32 %498 → %492` (機械語 `1047988`〜`1047995`) と `10479be` の `load %505 ← %492` (機械語 `10479be`〜`10479c5`) は同じ SSA 値 P を指す。P の slot への書込は `1047942` の 1 箇所だけなので、P の値は `10479be` まで変わらない。
- (iii) `10479be` の結果は `stack_var_16` に入り、`10479de` の `load %508 ← stack_var_16` (機械語 `10479fa` の `mov edx,[rbp+0x5b8]`) に対応する。
- 上流 X (`[rbp+0x4e8]`) への書込は `10474d8` の 1 箇所。X の 4 段 (`10474a6`〜`10474d8`) は、修正後 IR (`fix_ld236.py` 適用) で機械語と一致する (`audit_lsf_ssa.py` の出力で確認)。

判定を `results/candidate_verdicts_4676.jsonl` に残した。判定が UNDETERMINED のままなのは、本番 IR (既定 OFF) の X が 1 段足りないため、P の値が機械語と一致しないから。修正後 IR だけを根拠に OK_LOAD にすると、本番の spill 表と合わなくなる。OK_LOAD にするには、本番 IR で `M11_FIX_LD236=1` を既定にする判断が要る (PM の判断)。

## 3. spill 表の再生成

`TMPDIR=$RUNNER_TEMP M11_WORK=<work-m11 展開先> LD_WORK=<work-liftdiff 展開先> bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` の実測:

- 測定 commit `740289e98` (コードを変えた最後の commit。以後 HEAD までのコード差分は 0 行)。実行: real 3m00.4s・load 1.10 (11:30:57 時点の uptime)・rc=0・7/7 完走 + step 8 完走。
- `[spill178_1161.tsv] results/ と一致`・`[spill178 (修復後 IR)] results/spill178_1161.tsv と一致`。
- 集計: spill 宛 unk site 178 / 71 関数。確定 154 / 判定不能 23 / 未判定 1。`10479c7` の判定不能は既存 (REPORT_2958)。

## 4. 本番 unit e2e (受入 2)

素材: `fl-win64.tar.zst` を `$RUNNER_TEMP/win64` に展開 (11 s)。`work-m11` の `work/` を `tools/m11/work` に置いた。`lift_pe.sha256` が素材に無いため `M11_SKIP_LIFT_FP=1` で指紋検査だけを迂回した (REPORT_2779・REPORT_3647 と同じ扱い)。**この結果は参考値**。

| 条件 | 時間 | reached_stage | 通常起動 run | survey | 寛容起動 | ゲート |
|---|---|---|---|---|---|---|
| OFF (既定) | real 3m01s | 4/6 | 98/942 | ok=875 noproc=1 miss=46 trap=20 clobber=0 | attempted=942 ok=875 skipped=66 | 失敗 (survey 875 ≠ 期待 873) |
| ON (`M11_FIX_LD236=1`) | real 1m05s | 4/6 | 98/942 | ok=875 noproc=1 miss=46 trap=20 clobber=0 | attempted=942 ok=875 skipped=66 | 失敗 (同上) |

- ON の IR は `m11_gen_ir2.sh` を `M11_FIX_LD236=1` で再実行して作った (`ir_conditions.json` の `ld236=applied`・`fx236` 4 箇所)。OFF の IR と 3 行差 (`444153` → `444156` 行)。
- `m11_e2e.sh` 単体では、`M11_FIX_LD236=1` を付けても IR を作り直さない (既存 OFF の IR を再利用する)。ON で測るには `m11_gen_ir2.sh` を先に走らせる必要がある。これは本 PR で直していない (§5 の未解決)。
- unit 結果の比較: `tolerant_units.json` は一致。survey の差は ir_sha256 と wasm のアドレス・ハッシュだけ。ok/trap/miss の値は一致。
- ゲートの失敗は OFF でも同じ。`M11_EXPECT_SURVEY_OK=873` は canonical `--full` の値。差 875 との原因は測っていない (§5)。
- ON の build: `m11_e2e.sh` は IR 生成の後に `m11_build.sh` を必ず呼ぶ (増分ビルド・`work/obj/*.o` キャッシュ)。ON の wasm のハッシュが OFF と違う (`ir_sha256`・wasm アドレス) ことから、ON では build が走ったことを確認した。build 時間と OFF の 3m01s との内訳 (build の時間・キャッシュの効き) は測っていない。そのため real 1m05s と 3m01s の差の理由は未確認。

`1046a30` の読み値 (X・P の実行時の値) は確認していない。確認には trace が要る。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `m11_e2e.sh` が `M11_FIX_LD236=1` で IR を作り直さない (既存 IR を再利用) | ON の e2e は `m11_gen_ir2.sh` を先に走らせないと測れない | 本 PR 外 (#4676 の範囲外・PM 判断) |
| 本番 e2e の期待値 (873) と参考値 (875) の差。`lift_pe.sha256` 無しで全再生成していない | ゲート失敗の原因が環境か未確認 | 素材の指紋 (`lift_pe.sha256`) 付きの `work-m11` で再測定 |
| `1046a30` の X・P の実行時の値 | 機械語との一致は静的確認のみ | trace 付きの run (別途) |
| `10479c7` を OK_LOAD にするか | 本番 IR の X が 1 段足りないため判定不能 | `M11_FIX_LD236` の既定化の判断 (PM) |

## 6. 再現

```sh
W=$RUNNER_TEMP/m11w/tools/m11/work
python3 tools/m11/ldfix/fix_ld236.py $W/boot_final3.ll $RUNNER_TEMP/boot_final3.ld236.ll
TMPDIR=$RUNNER_TEMP M11_WORK=$RUNNER_TEMP/m11w/tools/m11/work LD_WORK=$RUNNER_TEMP/ldw/tools/liftdiff/work \
  bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
# ON: 先に IR を M11_FIX_LD236=1 で作り直す (m11_e2e.sh は既存 IR を再利用するため)。その後 m11_e2e.sh が m11_build.sh (増分) を内部で呼ぶ
(cd tools/m11 && FL_WIN64_DIR=$RUNNER_TEMP/win64 M11_FIX_LD236=1 M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash m11_gen_ir2.sh)
FL_WIN64_DIR=$RUNNER_TEMP/win64 M11_FIX_LD236=1 M11_SKIP_LIFT_FP=1 M11_LB_BASE=0 bash tools/m11/m11_e2e.sh
```
