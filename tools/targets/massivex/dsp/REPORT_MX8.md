# MX-8 (#1321) chained .pdata の CHAININFO 親への束ね規則

- 親: #1122 (MX-5) / 起票: #1321 (MX-8)。本ファイルは #1321 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX5 §5 と一致)。
- 計測スクリプト: `dsp/scripts/mx_pdata_quant.py` (e2e.sh の step 5/5)。

## 1. 今 run で達成した範囲

受入 2 のうち「chained 親への束ね規則の決定と実装 (CHAININFO 親に束ねる)」のみ。
受入 1 (code/data 区別と再帰降下)・受入 3 (leaf 境界の実 unwind 化)・受入 4 の closure 側は未着手 (§5 の子 issue)。

## 2. 束ね規則

1. valid entry (`e > b`・`.text` 内・`e <= .text 末尾`) の UNWIND_INFO を REPORT_MX5 注 4 の規則 (VirtualSize 範囲に当たる section がちょうど 1 つ) で解決する。
2. UNWIND_INFO の Flags に CHAININFO (`& 4`) が立つ entry は、末尾の RUNTIME_FUNCTION を親とする。
3. 親 (begin, end) が valid .pdata 内に **完全一致**で在るときだけ束ねる。一致しない親は束ねず、独立した関数として数える。
4. 束ねた member (begin が親と異なる entry) を関数の根から除く。残りを関数の根とする。

## 3. 実測 (測定 commit `5e26f032`)

| 指標 | 値 |
|---|--:|
| valid entry | 186,961 |
| UNWIND_INFO 解決 1 件の entry | 167,541 |
| CHAININFO (解決済み) | 62,516 |
| 親が valid .pdata 内に完全一致 | 62,498 |
| **束ねた member (chain member bound)** | **62,498** |
| **束ね後の関数の根 (valid − member)** | **124,463** |
| 参考: chained (begin == 直前 end) | 70,489 |
| 参考: leaf 近似 > pdata end (過大評価) | 116,460 |

- 62,516 − 62,498 = 18 件は親が pdata 内に無い (MX-5 注と同じ)。束ねず独立扱い。
- 解決不能 19,420 件 (section 0 件・2 件以上) は規則上束ねない。その中の CHAININFO 件数は未確定。

## 4. 未解決 (子 issue へ)

| 残件 | 受入 | 起票先 |
|---|---|---|
| 解決不能 19,420 件の UNWIND_INFO の正しい読み方、親 18 件の解決 | 2 | 子 issue (下記) |
| chained (begin == 直前 end) 70,489 と CHAININFO 束ね 62,498 の関係の確定 | 2 | 子 issue (下記) |
| leaf 境界を実 unwind / 境界に置換 (過大評価 116,460 件) | 3 | 子 issue (下記) |
| code/data 区別 (jump table・文字列窓) を入れた再帰降下と round 推移 | 1 | 子 issue (下記) |
| process 起点 closure の確定値 | 4 | #266 (U1) に依存 |

## 5. 検証

- **測定 commit (コードを変えた最後の commit)**: `5e26f032` (`feat(massivex): bind chained members to exact-match CHAININFO parent (Refs #1321)`)。以後の commit は REPORT のみ。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1)**: rc 0 / `OK elapsed=43s` / load 0.54 0.49 0.23 → 0.78 0.56 0.27。step 5/5 で `chain_member_bound` 出力を確認。
- **e2e (ベースライン 851c342e・変更前)**: rc 0 / `OK elapsed=43s` / load 0.78 0.47 0.19 → 0.89 0.54 0.23。
- **negctl (`bash dsp/negctl.sh`・測定 commit)**: NC1 unsup 67 / NC2 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。
- **step 5 再現 (MX-5 との突合)**: chained 70,489 / 解決 1 件 167,541 / CHAININFO 62,516 / 親一致 62,498 / 過大評価 116,460 件・2,618,866 B / 過小評価 12。MX-5 と完全一致。
- **鮮度 (WORKFLOW §6)**: `git diff 5e26f032 HEAD -- tools/targets/massivex/dsp/e2e.sh tools/targets/massivex/dsp/negctl.sh tools/targets/massivex/dsp/scripts/mx_pdata_quant.py tools/flelift/x64c.py tools/shared/env.sh` は 0 行 (本 REPORT の commit は dsp 外のみ)。
