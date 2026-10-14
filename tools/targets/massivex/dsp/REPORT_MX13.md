# MX-13 (#1625) code/data 区別つき再帰降下 (flow モード) と round 推移

- 親: #1488 (MX-10) / 起票: #1625 (MX-13)。本ファイルは #1625 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX5 §5 と一致)。
  抽出手順: `parse_setup_headers.py <exe> work` → `extract_massivex.py <exe> work key`。
- 実装: `dsp/scripts/mx_closure.py` の第 4 引数 `flow` (既定 `linear` は従来どおり)。

## 1. 今 run で達成した範囲

- 受入 1 (jump table 窓・文字列テーブルを code から除外する再帰降下): **未達** (文字列窓の明示除外は未実装・間接 jmp の先の到達は未確定)。以下は実装の現状。flow モードは入口から制御フローで到達する命令だけを code とし、間接 jmp (jump table) の先とテーブル窓は decode しない。文字列窓の除外は入れていない (テーブル窓は間接 jmp の先としてのみ現れるため、この定義で除外される範囲に限る)。
- 受入 2 (round 推移の記録): **部分達成**。round 5 まで記録。round 6 の途中で測定の 20 分上限に達し、収束値は未確定。
- 受入 3 (e2e PASS・negctl 3 件 FAIL<期待>): **達成** (§3)。

## 2. round 推移 (flow モード・実測)

測定 commit `96a8bbaf`。`timeout 1200` で打ち切り (rc 124)。

| round | 入口数 | 増分 | linear 担当バイト | flow 到達バイト | flow 到達命令 | 間接 jmp 未解決 (累計) |
|--:|--:|--:|--:|--:|--:|--:|
| seeds | 567 | — | — | — | — | — |
| 1 | 2,456 | +1,889 | 231,841 | 208,409 | 48,046 | 21 |
| 2 | 6,871 | +4,415 | 6,524,759 | 604,242 | 124,397 | 22 |
| 3 | 20,319 | +13,448 | 16,056,076 | 1,301,176 | 289,054 | 41 |
| 4 | 60,440 | +40,121 | 31,671,936 | 3,148,422 | 729,987 | 141 |
| 5 | 146,761 | +86,321 | 38,365,875 | 7,201,894 | 1,707,434 | 390 |
| 6 以降 | 未測定 | — | — | — | — | — |

- 比較の基準 (linear): REPORT.md §2 の 3,227 / 45,611 / 320,877 (round 1/2/3)。本 run の flow は round 1 で 2,456、round 2 で 6,871、round 3 で 20,319 と、linear より小さい入口数で推移した。
- ただし flow は round 5 でも増え続けており、収束していない。round 5 の入口数 146,761 は .pdata 関数数 186,960 の 78.5%。
- 「linear bytes」列は linear 方式の担当バイト (次の入口まで)。flow の到達バイトとの差が code/data 区別による除外量の目安。

## 3. 検証

- **測定 commit (コードを変えた最後の commit)**: `96a8bbaf`。**現 head (`c17dadb5` 以降) に対して鮮度 NG**。
- **鮮度の根拠 (WORKFLOW §6)**: `git diff 96a8bbaf HEAD -- tools/targets/massivex/dsp/scripts/mx_closure.py` は 12 行の変更 (linear 経路の `end` 計算・`begins` 参照の追加・sort のホイスト)。`git diff --stat 96a8bbaf HEAD -- tools/targets/massivex/dsp` は REPORT_MX12/13/14・`mx_unres_*.py` の追加も含む (計 511 行追加・4 行削除)。よって下記 e2e・negctl の数値は **旧コードの測定値** で、現 head の値ではない。
- **e2e (`bash dsp/e2e.sh`・測定 commit `96a8bbaf`・n=1・並列 1)**: rc 0 / `OK elapsed=41s` / load 0.13 0.41 0.63 → 0.56 0.49 0.65。旧値。n≥3 の min–max は未測定。
- **negctl (`bash dsp/negctl.sh`・測定 commit `96a8bbaf`)**: NC1 unsup 67 / NC2 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。旧値。
- **flow 測定**: `python3 dsp/scripts/mx_closure.py "work/extracted/VST3/Massive X.vst3" work/mx13/rtti.json work/mx13/flow flow` → 20 分で打ち切り (rc 124)。旧コードでの測定。

## 3.1 fix モード (差し戻し対応・2026-10-14) の状況

- **素材不足で未測定**: `plugins-massivex` が `$HOME/artifacts` に無く (取得されたのは `fl-win64` のみ)、`work/extracted/VST3/Massive X.vst3` が存在しない。よって以下は本 run で**実行していない**。
  - flow 測定の round 6 以降 (受入 2)・間接 jmp の到達確定 (受入 1)。
  - e2e の n≥3 レンジ (§5 の数値規約)・所要の並列数。
  - round 推移の別アルゴリズム検算 (§5)。
  - 文字列窓の除外 (受入 1)。コードは未変更。除外の定義 (テーブル窓の判定基準) を実測前に決めると、検証なしの変更になるため未着手。
- **必要素材**: `oc_artifacts: fl-win64 plugins-massivex` を付けて再起動する必要がある (`docs/WORKFLOW.md` §11)。
- **検証範囲 / 範囲外**: 本 REPORT の e2e・negctl は linear 経路の検証。`mx_closure.py` の `flow` モードは既定の `linear` と経路が別で、flow モードの正しさは本 REPORT では示していない。

## 4. 未解決 (追跡先)

| 残件 | 受入 | 起票先 |
|---|---|---|
| flow モードの収束 (round 6 以降) と収束後の round 推移・収束しない場合の原因 (到達バイト増加・間接 jmp 未解決 390 件の扱い) | 2 | #1625 (素材 `plugins-massivex` 付きの再実行を要する。コメントで追跡) |
| 間接 jmp (jump table) の先の到達の確定 (現状は未解決件数のみ) | 1 | #1625 (同上) |
| 文字列窓の除外 (code 扱いされた data の件数・除外の判定基準は PM 確認待ち) | 1 | #1625 (同上) |
| leaf 境界を実 unwind / 境界に置換 | 3 (MX-14) | #1626 (MX-14) |
