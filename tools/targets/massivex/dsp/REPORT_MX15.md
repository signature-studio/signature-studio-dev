# MX-15 (#1810) .pdata 残 490 件の UNWIND_INFO 読み方と親 18 件の解決 (内訳の計測)

- 親: #1624 (MX-12, CLOSED・PR #1830 merge 済) / 起票: #1810 (MX-15)。本ファイルは #1810 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`。REPORT_MX12 と一致)。
- 計測スクリプト: `dsp/scripts/mx_unres_residual.py` (新規・本 run)。残件の定義は `mx_unres_orig7498.py` と同一。

## 1. 今 run で達成した範囲

- 受入 1 (残件 490 件の読み方): **未達**。残件の内訳を分類し、再現した。読み方の規則は決めていない (子 MX-47)。
- 受入 2 (MX-10 親 18 件の解決): **未達**。親が valid `.pdata` に無い理由を分類した。解決は未着手 (子 MX-48)。
- 受入 3 (e2e PASS・negctl 3 件 FAIL<期待> の維持): **達成** (§4)。

## 2. 残件 490 件の内訳 (MX-12 §2 の再判定の後段)

母集団 7,498 件 (MX-10 整合候補 0/2/3 件) の再判定は REPORT_MX12 と一致した (0 件 458 / 1 件 7,008 / 2 件 32)。

| 集合 | 件数 | 候補ごとの失敗理由 (件数は候補単位) |
|---|--:|---|
| 再判定後 0 件 | 458 | `plain_no_boundary` (prolog の命令境界に CodeOffset が乗らない) / `mx10:ver` (Version が 1・2 でない) / `plain_prolog_mismatch` (UWOP_PUSH_NONVOL の位置が push でない) / `plain_decode_fail` / `mx10:cnt0` / `mx10:prolog>len` / `chain_parent_absent` |
| 再判定後 2 件以上 | 32 | 2 件とも `plain_ok` (完全復号と prolog 照合を通る) の組。候補どうしを区別する規則が無い |

候補単位の失敗理由の合計: `plain_no_boundary` 379 / `mx10:ver` 150 / `plain_prolog_mismatch` 126 / `plain_decode_fail` 76 / `plain_ok` 64 / `chain_parent_absent` 56 / `mx10:cnt0` 19 / `mx10:prolog>len` 11。

読み取り: 0 件の大半は、prolog の境界に乗らない・Version が不正のどちらかで落ちている。2 件以上の 32 件は、どの候補も復号と prolog 照合を通るので、既存の規則では選べない。

## 3. MX-10 親 18 件の母集団

- 定義: section hit が 1 件 (一意) かつ CHAININFO の entry のうち、親 RUNTIME_FUNCTION が valid `.pdata` に完全一致で無いもの (`mx_unres_residual.py` の `parent18`)。
- 一意 CHAININFO 62,516 件のうち、親が valid `.pdata` 外の 18 件。
- 内訳 (`parent18b` の補助計測): 親の begin が全 `.pdata` 内に在る 7 件・在らない 11 件。親の RVA が `.text` 内 16 件・外 2 件。親の end が `.text` 内 11 件・外 7 件。

この 18 件は残件 490 件とは別の母集団。読み方の規則が決まるまで、親を確定できない。

## 4. 検証

- **測定 commit (コードを変えた最後の commit)**: `2c889acc7` (`feat(massivex): count MX-12 residual 490 candidates and MX-10 parent-absent 18 (Refs #1810)`)。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1)**: rc 0 / `OK elapsed=17s` / load 0.10 0.42 0.27 → 0.30 0.45 0.28。
- **negctl (`bash dsp/negctl.sh`・測定 commit・n=1)**: NC1 insns 3118 / unsup 5 (base 24002) → FAIL<期待>。NC2 insns 4575 / unsup 292 → FAIL<期待>。NC3 insns 31 / unsup 0 → FAIL<期待>。3 件とも FAIL<期待>。
  - **注 (未解決)**: REPORT_MX12 §4 の negctl は NC1 unsup 67 / NC2 unsup 746 と記録されている。本 run の値 (5 / 292) と一致しない。同じ PE (md5 一致) での差の理由は未確認。判定 (3 件とも FAIL<期待>) は両方で一致する。
- **残件の再計測 (`mx_unres_residual.py`・測定 commit)**: `{parent18: 18, population: 7498, redo_0: 458, redo_1: 7008, redo_2: 32}`。REPORT_MX12 §2 と一致。
- **測定 commit から HEAD までのコード差分 (差分 0 の証跡)**: `git diff 2c889acc7 HEAD -- tools/targets/massivex/dsp/scripts` の出力は空。本 REPORT の commit は docs のみ。
