# REPORT_739 — unit 101 (VA 0x1de960) の暴走 loop の再測 (#739 = [M11-N40], 親 #513 / #679)

## 0. 結論 (先出し)

1. **暴走の再現有無は、本 PR の中では判定できていない**。作業者の手元の survey (main `f0d65f32` 起点) では、OFF (probe 有/無) の unit 101 は ok・131.4 MB・GetMem 1 回だった。ただし、その生出力 (`work/n40_survey.out`・`work/ctl_survey.out`・`work/trap_triage/n40_cost.json` 等) は gitignore 対象で PR に含まれず、本 run では IR・emsdk が無く再生成もできなかった。よって §2 の数値は**本 PR から検証できない未検証の値**として扱う。
2. **ON 構成 (`M11_OV_CLASSCREATE=1`) は「再現しない」とは判定しない**。ON の survey は ok 867 / miss 47 / halt0 8 / oob 18 で、icall の expect (REPORT_679 の旧構成の値) は FAIL している。halt0 8 件の unit 内訳は未確認で、unit 101 がそこに含まれるかは判定できていない。
3. probe 2 件 (`ListFind(4fa210)`・`ListRaise(47a250)`) の入口回数は、unit 101 で 0 回と報告されている (未検証)。入口回数は周回数と object 数の代わりにはならない (§3)。
4. 差 2,663 (#513 の GetMem 23,056,285 と REPORT_679 の AfterConstruction 23,053,622) は、比較対象の暴走が本 PR で再現できていないため、切り分けできていない。

受入条件: 1 未達 (根本原因は未特定)・2 未達 (差の切り分けなし)・3 未達 (入口回数のみ。1 周回あたり object 数は未確認)。

## 1. 基準と再現

- 基準: `docs/REFERENCES.md` `[WIN64]` の fl-win64 (PE `block00031_PE.bin`) で `m11_image_gen.py` / `m11_data_gen.py` / `m11_gen_ir2.sh` を再生成 (work-m11 スナップショットの IR は古いため使わない)。
- 検証起点: main `f0d65f32`。本 PR の変更は `m11_post.py` (probe 2 件の追加)・`m11_survey.mjs` (unit 別の probe 差分の出力) と本 REPORT。
- build: `M11_OV_CLASSCREATE=0|1 bash m11_build.sh` (`PE` を fl-win64 の展開先に指定)。

## 2. 実測 (現 main, 942 unit) — 未検証 (出典は PR 外)

| 構成 | 出典 (tools/m11 起点・未 commit) | ok / noproc / miss / trap | unit 101 (0x1de960) | `4fa210` 入口 (unit 合計) | `47a250` 入口 |
|--:|--|--|--|--:|--:|
| OFF (probe 有) | `work/n40_survey.out` | 869 / 1 / 47 / 25 | ok, va 131,399,680 B, GetMem 1 | 2 (unit 304 のみ) | 0 |
| OFF (probe 無・対照) | `work/ctl_survey.out` | 869 / 1 / 47 / 25 | — | — | — |
| ON (`M11_OV_CLASSCREATE=1`) | `node trap_triage/survey_units.mjs work/trap_triage/on_c.json` | 867 / 1 / 47 / 27 (SURVEY_UNITS: ok 867, miss 47, halt0 8, oob 18) | 未確認 (halt0 8 件の内訳に含まれるかは不明) | — | — |

- OFF の probe 有/無で ok・trap・GetMem の総数が一致 (869/25/2004) と報告されている。probe が挙動を変えないことの根拠になるのは、この一致が再取得された生出力で確認された後。
- ON の icall 集計 (`icall_41037d_679.py`): site 0x41037d の ok 1049 / miss 2、最上位は **unit 898 (VA 0xf06110, ok) 504 hit (48.0%)**。REPORT_679 の「unit 101 が 99.999%」とは一致しない。
- `icall_41037d_679.py --expect-ok 23053861 --expect-miss 9` は FAIL。期待値は REPORT_679 の旧構成の値で、現構成 (ON) とは別の数値。この FAIL は「再現しない」の根拠にはしない。

## 3. 未解決

| 未解決 | 理由 | 起票先 |
|--|--|--|
| 暴走 (unit 101 の halt0) の再現条件 | 本 PR では ON/OFF とも再現を確認できていない (OFF は未検証の値が ok、ON は halt0 の内訳が未確認)。REPORT_679 / #513 の構成 (IR・image の版) を特定できていない | #739 (本 issue を Refs で継続) |
| 差 2,663 (#513 の GetMem 23,056,285 と REPORT_679 の AfterConstruction 23,053,622) | 比較対象の暴走を本 PR で再現できていない | #739 |
| 周回数の確認 (1 周回あたり object 数) | probe は入口回数のみ。周回数と object 数は未計測 | #739 |
| 0x41037d の hit 位置 (unit 898 が最上位) | 別の site / 別の unit の集中。本 issue の範囲外の可能性 | #739 で切り分け (要起票判断) |

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
