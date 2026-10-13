# REPORT_739 — unit 101 (VA 0x1de960) の暴走 loop の再測 (#739 = [M11-N40], 親 #513 / #679)

## 0. 結論 (先出し)

1. **現 main では暴走が再現しない**。REPORT_679 は ON 構成で unit 101 が halt0 (VirtualAlloc 1477.2 MB, GetMem 23M 回) と報告したが、
   同じ基準 (fl-win64 PE からの IR 再生成) の ON / OFF 両方で unit 101 は **ok・131.4 MB・GetMem 1 回** だった。
2. 周回数の probe (`4fa210` 入口・`47a250` 入口) を入れたところ、unit 101 の `4fa210` 入口は **0 回** (`listfind` の unit 合計は 2 回、
   いずれも unit 304)、`47a250` は **0 回**。REPORT_679 §3 の「`4fa210` の 1 段が繰り返し呼ばれる」仮説は、現 main では観測されない。
3. 逆アセンブルで `4fa210` (fl-win64 の `block00031_PE.bin`、x64) を確認: 走査回数は `[list+0x10]` (Count) で決まる有界ループ。
   境界外時の `47a250` 呼び出し (`0x4fa25d`) は 1 回の raise。単独では 23M 回の周回を作れない。
4. 受入条件の 2 (GetMem 差 2,663 の切り分け) と 1 の根本原因は、**再現条件 (REPORT_679 の VA/halt0 の構成) が現 main に存在しないため未達**。
   #513 / #679 の数値は、旧 IR (または別の lift 状態) で取られた可能性がある。

受入条件: 1 未達 (再現せず)・2 未達 (比較対象が無い)・3 達成 (probe で周回数を実測、結果は 0 回)。

## 1. 基準と再現

- 基準: `docs/REFERENCES.md` `[WIN64]` の fl-win64 (PE `block00031_PE.bin`) で `m11_image_gen.py` / `m11_data_gen.py` / `m11_gen_ir2.sh` を再生成 (work-m11 スナップショットの IR は古いため使わない)。
- 検証起点: main `f0d65f32`。本 PR の変更は `m11_post.py` (probe 2 件の追加)・`m11_survey.mjs` (unit 別の probe 差分) と本 REPORT。
- build: `M11_OV_CLASSCREATE=0|1 bash m11_build.sh` (`PE` を fl-win64 の展開先に指定)。

## 2. 実測 (現 main, 942 unit)

| 構成 | 出典 | ok / noproc / miss / trap | unit 101 (0x1de960) | `4fa210` 入口 (unit 合計) | `47a250` 入口 |
|--:|--|--|--|--:|--:|
| OFF (probe 有) | `work/n40_survey.out` | 869 / 1 / 47 / 25 | ok, va 131,399,680 B, GetMem 1 | 2 (unit 304 のみ) | 0 |
| OFF (probe 無・対照) | `work/ctl_survey.out` | 869 / 1 / 47 / 25 | — | — | — |
| ON (`M11_OV_CLASSCREATE=1`) | `survey_units.mjs` → `on_c.json` | 867 / 1 / 47 / 27 (SURVEY_UNITS: ok 867, miss 47, halt0 8, oob 18) | ok | — | — |

- OFF の probe 有/無で ok・trap・GetMem の総数が一致 (869/25/2004)。probe は挙動を変えない。
- ON の icall 集計 (`icall_41037d_679.py`): site 0x41037d の ok 1049 / miss 2、最上位は **unit 898 (VA 0xf06110, ok) 504 hit (48.0%)**。REPORT_679 の「unit 101 が 99.999%」とは一致しない。
- `icall_41037d_679.py --expect-ok 23053861 --expect-miss 9` は FAIL (期待値は REPORT_679 の旧構成の値)。

## 3. 未解決

| 未解決 | 理由 | 起票先 |
|--|--|--|
| 暴走 (unit 101 の halt0) の再現条件 | 現 main の ON/OFF とも非再現。REPORT_679 / #513 の構成 (IR・image の版) を特定できていない | #739 (本 issue を Refs で継続) |
| 差 2,663 (#513 の GetMem 23,056,285 と REPORT_679 の AfterConstruction 23,053,622) | 比較対象の暴走が現 main に無い | #739 |
| 0x41037d の hit 位置 (unit 898 が最上位) | 別の site / 別の unit の集中。本 issue の範囲外の可能性 | #739 で切り分け (要起票判断) |

## 4. 再現手順

```sh
cd tools/m11
export PE=<fl-win64 展開先>/extracted/block00031_PE.bin FL_WIN64_DIR=<fl-win64 展開先>
uv run --with capstone --with pefile python3 m11_image_gen.py "$PE" && uv run --with capstone --with pefile python3 m11_data_gen.py "$PE"
uv run --with capstone --with pefile bash work/gen_ir2_pe.sh   # 生成 gen_ir2_pe.sh は REPORT_679 §1 と同じ
M11_OV_CLASSCREATE=0 uv run --with capstone --with pefile bash m11_build.sh
M11_SURVEY_COST=work/trap_triage/n40_cost.json node m11_survey.mjs
```

`n40_cost.json` の `listfind` / `listraise` / `getmem` を unit ごとに見る。
