# REPORT_739 — unit 101 (VA 0x1de960) の暴走 loop の再測 (#739 = [M11-N40], 親 #513 / #679)

## 0. 結論 (先出し)

1. 既存 lift 出力から再生成した IR (出典未確定・§5 前提) では、記録上 OFF/ON とも unit 101 は ok で、暴走は再現しなかった。ただし生出力と取得元 (run ID / artifact 名) が無いため、この数値は**未検証**である。lift 出力の生成元 PE も未確認のため、REPORT_679 の比較対象とは比べられない。
2. ON 構成 (`M11_OV_CLASSCREATE=1`) でも、記録上 unit 101 は ok である (未検証)。ON の icall 検査の expect (REPORT_679 の旧構成の値 23,053,861) とは一致しないと記録されているが、生の FAIL 行は保存されていない (未検証)。
3. probe 2 件 (`ListFind(4fa210)`・`ListRaise(47a250)`) は関数入口の計数であり、周回数と object 数の代わりにはならない (§3)。
4. REPORT_679 §末尾に未切り分けとして残っている GetMem と AfterConstruction の差は、比較対象の暴走を本 PR で再現できていないため、切り分けできていない。

受入条件: 1 未達 (根本原因は未特定)・2 未達 (差の切り分けなし)・3 未達 (入口回数のみ。1 周回あたり object 数は未確認)。

## 1. 基準と再現

- 基準: `docs/REFERENCES.md` `[WIN64]` の fl-win64 (PE `block00031_PE.bin`) で `m11_image_gen.py` / `m11_data_gen.py` / `m11_gen_ir2.sh` を再生成 (work-m11 スナップショットの IR は古いため使わない)。
- 検証起点: `63ed695b` (PR ブランチ `739-m11-n40-unit101-loop-3` の base)。`63ed695b..HEAD` で `tools/m11` のコード差分は 0 (§5 の確認コマンド)。本 PR の変更は本 REPORT のみ。
- build: `M11_OV_CLASSCREATE=0|1 bash m11_build.sh` (`PE` を fl-win64 の展開先に指定)。

## 2. 過去 run の報告 (撤回)

過去 run の数値 (PR #993・#1184 の報告) は出典を示せず、差し戻しで撤回された。本 REPORT では採らない。§5 の数値も、取得元が示されるまで根拠にしない。

## 3. 未解決

| 未解決 | 理由 | 起票先 |
|--|--|--|
| 暴走 (unit 101 の halt0) の再現条件 | §5 の本 IR での結果は未検証の記録のみ。REPORT_679 / #513 の構成 (IR・image の版) を特定できていない | #739 (本 issue を Refs で継続) |
| REPORT_679 の未切り分けの差 | 比較対象の暴走を本 IR で確認できていない。IR の生成元が未確認のため、旧構成と比較できない | #739 |
| 周回数の確認 (1 周回あたり object 数) | probe は入口回数のみ。周回数と object 数は未計測 | #739 |
| §5 の数値の再取得 (取得元の記録) | 生出力・run ID・artifact 名が無い。`work-m11` と fl-win64 で再測し、出力と run ID を保存する | #739 |
| 0x41037d の hit 位置 (unit 898 への集中の報告) | 別の site / 別の unit の集中の可能性。本 issue の範囲外の可能性 | #739 で切り分け (要起票判断) |

## 4. 再現手順

すべて `tools/m11` を起点に実行する (`work/` はそこからの相対パス)。`work/` は gitignore 対象。

```sh
cd tools/m11
export FL_WIN64_DIR=<fl-win64 の展開先>        # 例: $RUNNER_TEMP/a (tar --zstd -xf fl-win64.tar.zst; extracted/block00031_PE.bin)
# work-m11 を tools/m11/work に展開済みであること (lift 出力 boot0〜4.lift.ll を使う)
bash m11_gen_ir2.sh                                                                      # boot_final.ll (ldfix 込み・ir_conditions.json 記録)
M11_OV_CLASSCREATE=0 bash m11_build.sh                                                   # OFF
M11_SURVEY_COST=work/trap_triage/n40_cost.json node m11_survey.mjs > work/n40_survey.out  # OFF 集計・unit 別 VA/GetMem
node trap_triage/survey_units.mjs work/trap_triage/off_c.json > work/trap_triage/off_survey.out
M11_OV_CLASSCREATE=1 bash m11_build.sh                                                   # ON
node trap_triage/survey_units.mjs work/trap_triage/on_c.json > work/trap_triage/on_survey.out
python3 trap_triage/icall_41037d_679.py work/trap_triage/on_c.json --expect-ok 23053861 --expect-miss 9
```

`n40_cost.json` の `listfind` / `listraise` / `getmem` を unit ごとに見る (`work/trap_triage/n40_cost.json`)。上の出力ファイルは各測定で必ず保存し、run ID または artifact 名と併記する。

## 5. 実測 (2026-10-13 測定・取得元未記録)

**取得元の状態**: 以下の数値は、生出力を保存せずに記述されたものである。測定の run ID・artifact 名は記録されておらず、`tools/m11/work` は現在存在しない (`work-m11` 素材も本 PR の body で指定されていない)。そのため**本節の数値はすべて未検証**であり、再現も確認していない。取得元が示されるまで、結論の根拠にしない。

**測定 commit と差分 0 の確認**: 測定 commit は記録されていない。PR 本文の `b3b288b4` は文書のみの commit で、測定対象のコードではない。`63ed695b` と `b3b288b4` の間で `tools/m11` のコードは変わっていない (下記)。これは `b3b288b4` のコードと `63ed695b` が同一であることを示すだけで、測定そのものの証跡ではない。

```
$ git diff 63ed695b HEAD -- tools/m11 ':(exclude)tools/m11/trap_triage/REPORT_739.md'
(出力なし = コード差分 0)
```

**前提 (IR の出典)**: `work-m11` 内の lift 出力 `boot0`〜`boot4.lift.ll` (2025-10-10 生成) を入力に `m11_gen_ir2.sh` で IR を再生成した (記録上 rc 0・ldfix applied・491,108 行)。lift 出力の生成元 PE 指紋 (`work/lift_pe.sha256`) と `functions_dll.csv` は素材に無く、lift が現 PE `b2c64da4…9496d` (fl-win64 `block00031_PE.bin`) から作られたかは**未確認**。全再生成 (RetDec lift, unit ごと最大 2400 秒) は 58 分に収まらないため行っていない。したがって以下は「この IR での記録上の結果」であり、現 main の全再生成 IR での結果とは限らない。また旧構成 (REPORT_679) の IR と同一であるかは確認できないため、REPORT_679 との比較は成立しない。

**集計 (未検証・取得元なし)**

- OFF `m11_survey.mjs` (記録): `"units":942,"ok":870,"noproc":1,"miss":47,"trap":24,"getmem":2012,"va_bytes":1412366336`
- OFF `survey_units.mjs` (記録): `SURVEY_UNITS {"ok":870,"miss":47,"other":1,"halt0":7,"oob":16,"noproc":1}`
- ON `survey_units.mjs` (記録): `SURVEY_UNITS {"ok":869,"miss":47,"other":1,"halt0":7,"oob":15,"abort":2,"noproc":1}`
- OFF/ON で kind が異なる unit (記録): unit 190 (ok→oob)・unit 304 (oob→abort)・unit 555 (oob→abort)

**unit 101 (VA 0x1de960) (未検証)**

- OFF `n40_cost.json` (記録): `{"i":101,"va":"0x1de960","va_bytes":131399680,"getmem":2,"listfind":2,"listraise":0}`。kind は ok (記録)
- ON (記録): `{"unit":101,"va":"0x1de960","kind":"ok","va_mb":131.4,"err":["[m11][VA-big] #20 size=131399680 (125.3 MB) live=407.0MB"]}`
- 記録上の判定: OFF/ON とも ok。この IR では暴走は再現しなかったと記録されている (未検証)。

**0x41037d (ON) (未検証)**

- `icall_41037d_679.py --expect-ok 23053861 --expect-miss 9` (記録): ok 1064 / miss 2 / 最上位 unit 898 (`0xf06110`・ok 504・miss 0)。期待値と不一致と記録されているが、FAIL 行の生出力は保存されていない。
- OFF 側の `0x41037d` hit 合計は、出力が無いため値を採らない。
- OFF の `n40_cost.json` (記録): 最上位 GetMem は unit 898 (`getmem` 504)。GetMem と icall の集中が同じ unit 898 にあるかは、再測で確認する。

**REPORT_679 との差**: 期待値 (ok 23,053,861 / miss 9) と記録上の値 (ok 1,064 / miss 2) は一致しない。ただし本 IR の出典が未確定 (上記) のため、旧構成の値との差が IR の違いによるものかは判定できない。

## 6. 受入条件 (本 PR の判定)

1. 根本原因: **未達**。§5 は未検証であり、暴走対象を特定できていない。
2. GetMem 差 2,663: **未達**。比較対象の暴走を本 IR で確認できていない。
3. 周回数 probe: **未達**。入口回数 (`listfind` 2) のみで、1 周回あたり object 数は未計測。

## 7. 未解決 (起票先 #739)

- REPORT_679 の unit 101 暴走の再現条件 (旧 IR の構成 = lift の PE 指紋・IR 生成条件) の特定。本 IR は旧 IR の再現条件を満たしていない可能性がある
- lift 出力 (`boot0`〜`boot4`) の生成元 PE の確認。全再生成 (`m11_e2e.sh --full`) による IR の作り直しは 58 分の上限外のため、本 run では未実施
- §5 の数値の再取得。生出力と run ID / artifact 名を併記して記録し直す
- 0x41037d の最上位が unit 898 である件 (REPORT_679 の「unit 101 集中」と不一致)。別 issue に分けるかは PM 判断
- ON 固有の oob/abort (unit 190・304・555) は本 issue の範囲外
