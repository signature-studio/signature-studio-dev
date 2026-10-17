# MX-15 (#1810) .pdata 残 490 件の UNWIND_INFO 読み方と親 18 件の解決 (内訳の計測)

- 親: #1624 (MX-12, CLOSED・PR #1830 merge 済) / 起票: #1810 (MX-15)。本ファイルは #1810 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`。REPORT_MX12 と一致)。
  - **PE の入手手順**: `plugins-massivex.tar.zst` の中身は Inno Setup の exe (`Native Instruments Massive X v1.7.1.exe`, 1,870,391,792 B) と dmg の 2 本。exe は 7z で開けず、`Massive X.vst3` は exe の中に平文では無い。`tar --zstd -xf` で展開後、`tools/targets/massivex/scripts/parse_setup_headers.py <exe> work` → `scripts/extract_massivex.py <exe> work key` で `work/extracted/VST3/Massive X.vst3` を生成する (REPORT.md §11.1)。`work/` は gitignore。2026-10-15 に本手順を再実行し、md5 `622993e7…` (95,356,824 B) を再現した。
- 計測スクリプト: `dsp/scripts/mx_unres_residual.py`。残件の定義は `mx_unres_orig7498.py` と同一。`parent18` の所在別内訳 (`parent18_location`) を本 run で追加した。

## 1. 今 run で達成した範囲

- 受入 1 (残件 490 件の読み方): **未達**。残件の内訳を分類し、再現した。読み方の規則は決めていない (子 MX-49)。
- 受入 2 (MX-10 親 18 件の解決): **未達**。親が valid `.pdata` に無い理由を分類した。解決は未着手 (子 MX-50)。
- (#4197 / MX-49 の受入 2「2 件以上 32 件を区別する規則の有無」は §5 で実測・達成。上記の「受入 2」は MX-15 #1810 の受入で、別の番号。)
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
- 内訳 (`mx_unres_residual.py` の `parent18_location`・出力 JSON を転記): 親の begin が全 `.pdata` 内に在る 7 件 (`begin_in_pdata`)・在らない 11 件 (`begin_not_in_pdata`)。親の RVA (begin) が `.text` 内 16 件 (`begin_in_text`)・外 2 件 (`begin_not_in_text`)。親の end が `.text` 内 11 件 (`end_in_text`)・外 7 件 (`end_not_in_text`)。

この 18 件は残件 490 件とは別の母集団。読み方の規則が決まるまで、親を確定できない。

## 4. 検証

- **測定 commit (コードを変えた最後の commit)**: `791d4f4a9` (`feat(massivex): output MX-10 parent18 location breakdown in residual script (Refs #1810)`)。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1)**: rc 0 / `OK elapsed=17s` / load 0.22 0.45 0.26 → 0.40 0.47 0.27。
- **negctl (`bash dsp/negctl.sh`・測定 commit・n=1)**: rc 0 / 6s。NC1 insns 3118 / unsup 5 (base 24002) → FAIL<期待>。NC2 insns 4575 / unsup 292 → FAIL<期待>。NC3 insns 31 / unsup 0 → FAIL<期待>。3 件とも FAIL<期待>。
  - **未解決 (追跡先 #4197)**: REPORT_MX12 §4 の negctl は NC1 unsup 67 / NC2 unsup 746 と記録されている。本 run の値 (5 / 292) と一致しない。同じ PE (md5 一致) での差の理由は未確認。判定 (3 件とも FAIL<期待>) は両方で一致する。#4197 (MX-49) の再測定で、同じ PE・同じ commit の 2 回の実行値を並べて原因を確定する。
- **残件の再計測 (`mx_unres_residual.py`・測定 commit)**: `{parent18: 18, population: 7498, redo_0: 458, redo_1: 7008, redo_2: 32}`。REPORT_MX12 §2 と一致。
- **§3 の所在別内訳 (同・測定 commit・出力 JSON `dsp/work/mx_unres_residual.json` の `parent18_location`)**: `{begin_in_pdata: 7, begin_not_in_pdata: 11, begin_in_text: 16, begin_not_in_text: 2, end_in_text: 11, end_not_in_text: 7}`。§3 の値はこの出力から転記した。
- **測定 commit から HEAD までのコード差分 (差分 0 の証跡)**: `git diff 791d4f4a9 HEAD -- tools/targets/massivex/dsp/scripts` の出力は 0 バイト。本 REPORT の commit は docs のみ。

## 5. MX-49 (#4197) 受入 2: 再判定後 2 件以上の 32 件を区別する規則の有無

- 計測スクリプト: `dsp/scripts/mx_unres_pair32.py` (測定 commit `d4ba65dc4`)。残件 490 件の読み方 (受入 1) は本 run では未着手 (#4197 は部分達成)。
- 再現: `mx_unres_residual.py` の 2 件以上 32 件を、同じ判定 (redo の `plain_ok` / `chain_ok`) で再抽出した。`pairs 32`・`n2 32` (全件 ok 2 候補)。
- 候補間の比較 (32 pair): `same_ver` 32 / `same_cnt` 32 / `same_flags` 31 / `same_codes` 31 / `same_prolog` 29 / UNWIND_INFO バイト列 `same_uwind` 26。`diff_sec` は 32 件すべて。
- 32 件中 26 件は UNWIND_INFO のバイト列が完全一致 (同一内容が 2 つの section に載る)。残り 6 件も差は flags / prolog / codes の数項目。
- 読み取り: 32 件すべてで異なる欄は section 名のみ。section 名 (`.qtmimed` 31 / `.pdata` 1 と `.xdata` の組) で選ぶ規則は、どちらが正かの根拠が無いため採らない。**既存の規則 (mx10 / plain) では 2 件を区別できないことを実測で示した** (受入 2 達成)。
- 検証 (commit `d4ba65dc4`・n=1): `e2e.sh` rc 0 / `OK elapsed=22s` / load 0.56 0.52 0.24 → 0.71 0.56 0.26 (受入 3 の e2e)。`negctl.sh` rc 0 / 9 s / NC1 insns 3118 unsup 5 → FAIL<期待>、NC2 insns 4575 unsup 285 → FAIL<期待>、NC3 insns 31 unsup 0 → FAIL<期待>。
  - §4 で未解決としていた NC2 unsup の差 (292 と MX12 の 746) は、本 run で 285 (同 PE・同 commit の 2 回目も 285 で再現)。3 件の判定は全 run で FAIL<期待>。
- 入力: `plugins-massivex` を `work/` に展開し、`Massive X.vst3` md5 `622993e76565f49c094063a2b717d6ca` を再現 (95,356,824 B)。
