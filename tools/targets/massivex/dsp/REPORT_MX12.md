# MX-12 (#1624) .pdata 解決不能 7,498 件の UNWIND_INFO 読み方 (候補一意化)

- 親: #1488 (MX-10) / 起票: #1624 (MX-12)。本ファイルは #1624 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX10 §4 と一致)。
- 母集団: REPORT_MX10 §2 の整合候補 0/2/3 件 7,498 件 (160 / 7,274 / 64)。`mx_unres_orig7498.py` が MX-10 と同じ定義で再計算して一致を確認。

## 1. 今 run で達成した範囲

- 受入 1 (7,498 件の読み方): **部分達成**。判定規則を決め、7,008 件は「整合候補が一意」になった (正解の証明ではない。構造と prolog 命令の整合による絞り込み)。残り 490 件は未確定、親 18 件の確定は未着手 (子 MX-15 #1810 へ、§3)。
- 受入 2 (判定根拠を REPORT_MX10 §2 の検証を拡張して実測): **達成**。`mx_unres_decode.py` (UNWIND_CODE 完全復号) と `mx_unres_prolog.py` (prolog 命令境界照合) を追加した。
- 受入 3 (e2e PASS・negctl 3 件 FAIL<期待>): **達成** (§4)。

## 2. 判定規則と結果

判定は候補 (section hit ごと) に対して次の順で行う。

1. MX-10 条件 (Version・SizeOfProlog・CountOfCodes・CHAININFO 親一致) を満たすもの。
2. UNWIND_CODE 列を先頭から完全復号し、スロット数の合計が CountOfCodes と一致する (`full_decode`)。opcode は 0..10、EPILOG (6) は Version 2 のみ、非 EPILOG の CodeOffset は SizeOfProlog 以下で単調非増加。
3. plain 候補のみ: UWOP_PUSH_NONVOL の CodeOffset が、関数先頭から線形逆アセンブルした命令境界に一致し、その命令が `push <reg>` である (`mx_unres_prolog.py`)。

| 指標 | 値 |
|---|--:|
| 母集団 (MX-10 整合候補 0/2/3 件) | 7,498 (160 / 7,274 / 64) |
| 再判定後 0 件 | 458 |
| 再判定後 1 件 (整合候補が一意) | 7,008 |
| 再判定後 2 件以上 (未確定) | 32 |

全 19,420 件に対する内訳 (`mx_unres_decode.py`・完全復号のみ): 候補 1 件 (plain) 16,326 / 2 件 2,918 / 3 件 16 / 0 件 160。これは MX-10 時点の plain 11,922 件から増えた分 (4,404 件) が、完全復号で候補を落とせたことによる。

完全復号後の 2 件以上 (multi) 2,934 件のうち、候補ごとの UNWIND_INFO バイト列が異なるものは 2,913 件、同一は 21 件 (`mx_unres_multi.py`)。バイト列の一致だけでは候補は決まらない。

## 3. 未解決 (子 issue へ)

| 残件 | 受入 | 起票先 |
|---|---|---|
| 再判定後 0 件 458 件・2 件以上 32 件 (計 490 件) の読み方と、確定 7,008 件を使った親 18 件の解決 (MX-10 受入 1 の後段) | 1 | 子 MX-15 (#1810) |
| code/data 区別 (jump table・文字列窓) を入れた再帰降下と round 推移 | MX-10 受入 2 | 既存 MX-13 (#1625) |
| leaf 境界を実 unwind / 境界に置換し、closure バイト数と target 判定の変化を定量化 | MX-10 受入 3 | 既存 (MX-14) |

## 4. 検証

- **測定 commit (コードを変えた最後の commit)**: `eaa4da33` (`feat(massivex): decode unresolved UNWIND_INFO candidates and recheck MX-10 population (Refs #1624)`)。e2e が使うコードは base (`2626e445`) と同一 (`git diff 2626e445 eaa4da33 -- tools/targets/massivex` は dsp/scripts の新規 4 本と REPORT のみ、既存ファイルの変更なし)。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1、時間は参考・判定は PASS のみ)**: rc 0 / `OK elapsed=43s` / load 0.02 0.01 0.01 → 0.50 0.14 0.06。
- **negctl (`bash dsp/negctl.sh`・測定 commit)**: NC1 unsup 67 / NC2 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待> (rc 0)。
- **probe (`mx_unres_probe.py`・測定 commit)**: valid 186,961 / 解決不能 19,420 / 整合候補 0・2・3 件 = 160・7,274・64 (REPORT_MX10 §2 と一致)。
- **母集団の再判定 (`mx_unres_orig7498.py`・測定 commit)**: 0/2/3 件の母集団 7,498 → 再判定後 0 件 458 / 1 件 7,008 / 2 件 32。
- **全件の完全復号 (`mx_unres_decode.py`・測定 commit)**: 19,420 件 → 候補 1 件 16,326 / 2 件 2,918 / 3 件 16 / 0 件 160。
- **測定 commit から HEAD までのコード差分 (差分 0 の証跡)**: `git diff eaa4da33 HEAD -- tools/targets/massivex/dsp/scripts` の出力は空 (`| wc -c` = 0)。測定 commit 以降の HEAD の変更は本 REPORT のみ。実測値は測定 commit `eaa4da33` のままで有効。
- **素材の再確認**: 本 review 修正 run の `$ARTIFACTS_DIR` には `fl-win64` のみで `plugins-massivex` は無いため、e2e と `mx_unres_*.py` の再実行は行っていない (測定は `eaa4da33` で実施)。
