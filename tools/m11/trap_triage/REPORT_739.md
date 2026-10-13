# REPORT_739 — unit 101 (VA 0x1de960) の暴走 loop の再測 (#739 = [M11-N40], 親 #513 / #679)

## 0. 結論 (先出し)

1. **暴走の再現有無は、本 PR では判定できていない**。作業者手元の survey (main `f0d65f32` 起点) の報告では OFF で unit 101 は暴走せず ok だったとされるが、その出典 (`work/` 配下の生出力) は gitignore 対象で PR に含まれない。本 PR からは検証できないため、数値は本 REPORT に残さない (§2)。
2. **ON 構成 (`M11_OV_CLASSCREATE=1`) は「再現しない」とは判定しない**。ON の icall 検査の expect (REPORT_679 の旧構成の値) は現構成の結果と一致せず FAIL の報告があるが、この FAIL を再現判定の根拠にはしない。ON で unit 101 が halt0 の内訳に含まれるかは未確認。
3. probe 2 件 (`ListFind(4fa210)`・`ListRaise(47a250)`) は関数入口の計数であり、周回数と object 数の代わりにはならない (§3)。
4. REPORT_679 §末尾に未切り分けとして残っている GetMem と AfterConstruction の差は、比較対象の暴走を本 PR で再現できていないため、切り分けできていない。

受入条件: 1 未達 (根本原因は未特定)・2 未達 (差の切り分けなし)・3 未達 (入口回数のみ。1 周回あたり object 数は未確認)。

## 1. 基準と再現

- 基準: `docs/REFERENCES.md` `[WIN64]` の fl-win64 (PE `block00031_PE.bin`) で `m11_image_gen.py` / `m11_data_gen.py` / `m11_gen_ir2.sh` を再生成 (work-m11 スナップショットの IR は古いため使わない)。
- 検証起点: main `f0d65f32`。本 PR の変更は `m11_post.py` (probe 2 件の追加)・`m11_survey.mjs` (unit 別の probe 差分の出力) と本 REPORT。
- build: `M11_OV_CLASSCREATE=0|1 bash m11_build.sh` (`PE` を fl-win64 の展開先に指定)。

## 2. 手元の報告 — 本 PR では未検証

以下は作業者手元の survey の報告で、出典 (`work/` 配下の生出力) は gitignore 対象のため PR に含まれず、本 PR からは検証できない。数値は REPORT に残さない。

- OFF (probe 有/無) の ok・trap・GetMem の一致、unit 101 の挙動、`4fa210` / `47a250` の入口回数、ON の halt0 / oob の内訳: いずれも**未検証の作業者報告**。
- ON の icall 集計で最上位 hit が unit 898 に集中するという報告も未検証。REPORT_679 の「unit 101 が大半」とは一致しないとされる。
- 結論に使うには、§4 の手順で再取得し、生出力の該当行を本 REPORT に貼ってから判断する。

## 3. 未解決

| 未解決 | 理由 | 起票先 |
|--|--|--|
| 暴走 (unit 101 の halt0) の再現条件 | 本 PR では ON/OFF とも再現を確認できていない。REPORT_679 / #513 の構成 (IR・image の版) を特定できていない | #739 (本 issue を Refs で継続) |
| REPORT_679 の未切り分けの差 | 比較対象の暴走を本 PR で再現できていない | #739 |
| 周回数の確認 (1 周回あたり object 数) | probe は入口回数のみ。周回数と object 数は未計測 | #739 |
| 0x41037d の hit 位置 (unit 898 への集中の報告) | 別の site / 別の unit の集中の可能性。本 issue の範囲外の可能性 | #739 で切り分け (要起票判断) |

## 4. 再現手順

すべて `tools/m11` を起点に実行する (`work/` はそこからの相対パス)。`work/` は gitignore 対象。

```sh
cd tools/m11
export FL_WIN64_DIR=<fl-win64 の展開先>        # 例: $RUNNER_TEMP/fl-win64 (tar --zstd -xf fl-win64.tar.zst)
PE=$FL_WIN64_DIR/extracted/block00031_PE.bin
mkdir -p work/trap_triage
sed -e "s#^cd \"\$(dirname \"\$0\")\"#cd $PWD#" -e "s#^PE=.*#PE=$PE#" m11_gen_ir2.sh > work/gen_ir2_pe.sh   # REPORT_679 §1 と同じ
uv run --with capstone --with pefile python3 m11_image_gen.py "$PE" && uv run --with capstone --with pefile python3 m11_data_gen.py "$PE"
uv run --with capstone --with pefile bash work/gen_ir2_pe.sh                             # boot_final.ll (ldfix 込み)
M11_OV_CLASSCREATE=0 uv run --with capstone --with pefile bash m11_build.sh              # OFF
M11_SURVEY_COST=work/trap_triage/n40_cost.json node m11_survey.mjs > work/n40_survey.out  # OFF (probe 有)
M11_OV_CLASSCREATE=1 uv run --with capstone --with pefile bash m11_build.sh              # ON
node trap_triage/survey_units.mjs work/trap_triage/on_c.json                             # ON (unit 別 halt0/oob 内訳)
python3 trap_triage/icall_41037d_679.py work/trap_triage/on_c.json --expect-ok 23053861 --expect-miss 9
```

`n40_cost.json` の `listfind` / `listraise` / `getmem` を unit ごとに見る (`work/trap_triage/n40_cost.json`)。
