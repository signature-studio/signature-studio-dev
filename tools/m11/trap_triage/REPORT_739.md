# REPORT_739 — unit 101 (VA 0x1de960) の暴走 loop の再測 (#739 = [M11-N40], 親 #513 / #679)

## 0. 結論 (先出し)

1. **本 IR (既存 lift 出力から再生成) では、OFF/ON とも unit 101 は ok で、暴走は再現しない** (§5)。ただし lift 出力の生成元 PE は未確認で、全再生成 IR での判定ではない。
2. ON 構成 (`M11_OV_CLASSCREATE=1`) でも unit 101 は ok (§5)。ON の icall 検査の expect (REPORT_679 の旧構成の値 23,053,861) とは一致しない。
3. probe 2 件 (`ListFind(4fa210)`・`ListRaise(47a250)`) は関数入口の計数であり、周回数と object 数の代わりにはならない (§3)。
4. REPORT_679 §末尾に未切り分けとして残っている GetMem と AfterConstruction の差は、比較対象の暴走を本 PR で再現できていないため、切り分けできていない。

受入条件: 1 未達 (根本原因は未特定)・2 未達 (差の切り分けなし)・3 未達 (入口回数のみ。1 周回あたり object 数は未確認)。

## 1. 基準と再現

- 基準: `docs/REFERENCES.md` `[WIN64]` の fl-win64 (PE `block00031_PE.bin`) で `m11_image_gen.py` / `m11_data_gen.py` / `m11_gen_ir2.sh` を再生成 (work-m11 スナップショットの IR は古いため使わない)。
- 検証起点: origin/main (本 run の作業ブランチ `739-m11-n40-unit101-loop-3`)。本 PR の変更は本 REPORT のみ。
- build: `M11_OV_CLASSCREATE=0|1 bash m11_build.sh` (`PE` を fl-win64 の展開先に指定)。

## 2. 過去 run の報告 (撤回)

過去 run の数値 (PR #993・#1184 の報告) は出典を示せず、差し戻しで撤回された。本 REPORT では採らない。§5 の実測のみを根拠とする。

## 3. 未解決

| 未解決 | 理由 | 起票先 |
|--|--|--|
| 暴走 (unit 101 の halt0) の再現条件 | 本 IR (§5) では ON/OFF とも再現しない。REPORT_679 / #513 の構成 (IR・image の版) を特定できていない | #739 (本 issue を Refs で継続) |
| REPORT_679 の未切り分けの差 | 比較対象の暴走が本 IR に無い | #739 |
| 周回数の確認 (1 周回あたり object 数) | probe は入口回数のみ。周回数と object 数は未計測 | #739 |
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

`n40_cost.json` の `listfind` / `listraise` / `getmem` を unit ごとに見る (`work/trap_triage/n40_cost.json`)。

## 5. 実測 (2026-10-13, 本 run)

**前提 (IR の出典)**: `work-m11` 内の lift 出力 `boot0`〜`boot4.lift.ll` (2025-10-10 生成) を入力に `m11_gen_ir2.sh` で IR を再生成した (rc 0・ldfix applied・491,108 行)。lift 出力の生成元 PE 指紋 (`work/lift_pe.sha256`) と `functions_dll.csv` は素材に無く、lift が現 PE `b2c64da4…9496d` (fl-win64 `block00031_PE.bin`) から作られたかは**未確認**。全再生成 (RetDec lift, unit ごと最大 2400 秒) は 58 分に収まらないため行っていない。以下は「この IR での結果」であり、現 main の全再生成 IR での結果とは限らない。

**実行** (`tools/m11` 起点・`FL_WIN64_DIR=$RUNNER_TEMP/a`・build 各約 19 秒・survey 約 9〜10 秒):

- OFF: `M11_OV_CLASSCREATE=0 bash m11_build.sh` → `M11_SURVEY_COST=work/trap_triage/n40_cost.json node m11_survey.mjs` (rc 0)
- ON: `M11_OV_CLASSCREATE=1 bash m11_build.sh` → `node trap_triage/survey_units.mjs work/trap_triage/on_c.json` (rc 0)
- OFF (unit 別): `node trap_triage/survey_units.mjs work/trap_triage/off_c.json` (rc 0)

**集計 (生出力の該当行を貼る)**

- OFF `m11_survey.mjs`: `"units":942,"ok":870,"noproc":1,"miss":47,"trap":24,"getmem":2012,"va_bytes":1412366336`
- OFF `survey_units.mjs`: `SURVEY_UNITS {"ok":870,"miss":47,"other":1,"halt0":7,"oob":16,"noproc":1}`
- ON `survey_units.mjs`: `SURVEY_UNITS {"ok":869,"miss":47,"other":1,"halt0":7,"oob":15,"abort":2,"noproc":1}`
- OFF/ON で kind が異なる unit は 3 件のみ: unit 190 (ok→oob)・unit 304 (oob→abort)・unit 555 (oob→abort)

**unit 101 (VA 0x1de960)**

- OFF: `{"i":101,"va":"0x1de960","va_bytes":131399680,"getmem":2,"listfind":2,"listraise":0}` (`n40_cost.json`)。kind は ok
- ON: `{"unit":101,"va":"0x1de960","kind":"ok","va_mb":131.4,"err":["[m11][VA-big] #20 size=131399680 (125.3 MB) live=407.0MB"]}`
- 判定: **OFF/ON とも ok。halt0 でも oob でもない。暴走は本 IR では再現しない**。REPORT_679 の「unit 101 が halt0」「GetMem 差 2,663」の比較対象は、本 IR の unit 101 には存在しない。

**0x41037d (ON)**

- `icall_41037d_679.py --expect-ok 23053861 --expect-miss 9`: `ok 1064` / `miss 2` / 最上位 unit = 898 (`0xf06110`・ok 504・miss 0)。`FAIL (3)(5)` (期待値 23,053,861 と不一致、最上位が unit 101 でない)
- OFF の `0x41037d` hit 合計は 0 (`--off` 比較の出力)。ON 側の `0x41037d` 集計は上記のみ
- OFF の `n40_cost.json` でも最上位 GetMem は unit 898 (`getmem` 504)。GetMem と icall の集中は同じ unit 898 にある

**REPORT_679 との差**: 期待値 (ok 23,053,861 / miss 9) は本 IR の値と一致しない (ok 1,064 / miss 2)。旧構成 (lift 版・IR 生成条件) の値と推定するが、旧 IR の指紋が無いため確認できていない。

## 6. 受入条件 (本 run の判定)

1. 根本原因: **未達**。本 IR では unit 101 が暴走しないため、特定対象が無い。
2. GetMem 差 2,663: **未達**。比較対象の暴走が本 IR に無い。
3. 周回数 probe: **未達**。入口回数 (`listfind` 2) のみで、1 周回あたり object 数は未計測。

## 7. 未解決 (起票先 #739)

- REPORT_679 の unit 101 暴走の再現条件 (旧 IR の構成 = lift の PE 指紋・IR 生成条件) の特定。本 IR は旧 IR の再現条件を満たしていない可能性がある
- lift 出力 (`boot0`〜`boot4`) の生成元 PE の確認。全再生成 (`m11_e2e.sh --full`) による IR の作り直しは 58 分の上限外のため、本 run では未実施
- 0x41037d の最上位が unit 898 である件 (REPORT_679 の「unit 101 集中」と不一致)。別 issue に分けるかは PM 判断
- ON 固有の oob/abort (unit 190・304・555) は本 issue の範囲外
