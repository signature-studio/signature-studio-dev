# MX-8 (#1321) chained .pdata の CHAININFO 親への束ね規則

- 親: #1122 (MX-5) / 起票: #1321 (MX-8)。本ファイルは #1321 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX5 §5 と一致)。
- 計測スクリプト: `dsp/scripts/mx_pdata_quant.py` (e2e.sh の step 5/5)。
- 入力の計測値 (chained・解決・CHAININFO・親一致・過大評価) は REPORT_MX5.md §2 が正本。本ファイルは束ね規則の適用結果だけを書く。

## 1. 今 run で達成した範囲

受入 2 のうち「chained 親への束ね規則の決定と計測上の実装 (CHAININFO 親に束ねる)」のみ。
mx_pdata_quant.py の計測カウンタに規則を入れた段階で、closure 側 (mx_roots.py / mx_closure.py の関数根) は未変更。
受入 1 (code/data 区別と再帰降下)・受入 3 (leaf 境界の実 unwind 化)・受入 4 の closure 側は未着手 (§4 の子 issue #1488)。

## 2. 束ね規則

1. valid entry (`e > b`・`.text` 内・`e <= .text 末尾`) の UNWIND_INFO を REPORT_MX5 注 4 の規則 (VirtualSize 範囲に当たる section がちょうど 1 つ) で解決する。
2. UNWIND_INFO の Flags に CHAININFO (`& 4`) が立つ entry は、末尾の RUNTIME_FUNCTION を親とする。
3. 親 (begin, end) が valid .pdata 内に **完全一致**で在るときだけ束ねる。一致しない親は束ねず、独立した関数として数える。
4. 束ねた member (begin が親と異なる entry) を関数の根から除く。残りを関数の根とする。

## 3. 実測 (測定 commit `5e26f032`)

束ね規則 (§2) を適用した結果。下表の 2 指標は MX-8 で新たに測った束ね後の値で、入力の内訳 (MX-5 の値) は REPORT_MX5.md §2 が正本。

| 指標 | 値 |
|---|--:|
| **束ねた member (chain member bound)** | **62,498** |
| **束ね後の関数の根 (valid entry 数 − member)** | **124,463** |

- 親が valid .pdata に完全一致しない CHAININFO entry は束ねず、独立関数として数える。件数は REPORT_MX5.md §2 の「親が valid 外」行。
- 解決不能 (section 0 件・2 件以上・REPORT_MX5.md §2 注 4) の entry は規則上束ねない。その中の CHAININFO 件数は未確定。

## 4. 未解決 (子 issue へ)

| 残件 | 受入 | 起票先 |
|---|---|---|
| 解決不能 entry の UNWIND_INFO の正しい読み方、親が valid .pdata 外の CHAININFO の解決 (件数は REPORT_MX5.md §2) | 2 | 子 issue #1488 |
| chained (begin == 直前 end) と CHAININFO 束ねの関係の確定 | 2 | 子 issue #1488 |
| leaf 境界を実 unwind / 境界に置換 (過大評価の解消) | 3 | 子 issue #1488 |
| code/data 区別 (jump table・文字列窓) を入れた再帰降下と round 推移 | 1 | 子 issue #1488 |
| process 起点 closure の確定値 | 4 | #266 (U1) に依存 |

### 受入 2 の未決の扱い (#1321)

#1321 受入 2 の旧数値は、REPORT_MX5.md §2 注 4 のとおり撤回済み。現行の未解決は REPORT_MX5.md §2 の解決不能・親 valid 外の件数が正本で、子 issue #1488 で扱う。

## 5. 検証

- **測定 commit (コードを変えた最後の commit)**: `5e26f032` (`feat(massivex): bind chained members to exact-match CHAININFO parent (Refs #1321)`)。以後の commit は REPORT のみ。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1)**: rc 0 / `OK elapsed=43s` / load 0.54 0.49 0.23 → 0.78 0.56 0.27。step 5/5 で `chain_member_bound` 出力を確認。
- **e2e (ベースライン 851c342e・変更前)**: rc 0 / `OK elapsed=43s` / load 0.78 0.47 0.19 → 0.89 0.54 0.23。
- **negctl (`bash dsp/negctl.sh`・測定 commit)**: NC1 unsup 67 / NC2 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。
- **step 5 突合 (MX-5 との一致)**: step 5 の出力は REPORT_MX5.md §2 と一致。値は MX-5 側のみに記載する。
- **鮮度 (WORKFLOW §6)**: `git diff 5e26f032 HEAD -- tools/targets/massivex/dsp/e2e.sh tools/targets/massivex/dsp/negctl.sh tools/targets/massivex/dsp/scripts/mx_pdata_quant.py tools/flelift/x64c.py tools/shared/env.sh` は 0 行 (本 REPORT の commit は dsp 外のみ)。
