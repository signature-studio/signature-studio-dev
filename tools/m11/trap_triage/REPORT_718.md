# #718: strict 候補 (ループ先頭ガード型) の真偽検証と、dropped_target_not_label の内訳

判定: 受入 3 (dropped_target_not_label の内訳) は**未達**。前版で報告した内訳は未再現のため採用しない (数値は記載しない)。接尾辞対応版での再集計は未実施。受入 2 (strict 候補の真偽) も**部分達成** (走査器の欠陥を発見。件ごとの真偽は未判定)。受入 1 (RetDec の機構切り分け) と受入 4 (DEFECTS 行案) は未達で、子 issue に分割した (§6)。
検証 HEAD: 本 commit (PR ブランチ `718-m11-strict-guard-verify`)。素材 `work-m11` (`boot_final.ll`) はこの run に無く、数値の再実行はしていない。

## 1. 走査器の前版実測 (未再現・数値なし)

前版で `tools/m11/guard699/scan_guard.py` を `work-m11` の `boot_final.ll` に当てた実測を報告していたが、当該 IR は本 run に無く未再現のため、数値は記載しない。再現には `work-m11` の取得が要る (§5)。

## 2. dropped_target_not_label の内訳 (受入 3) — 未確定

前版で報告した内訳は、非コミットの作業スクリプトで出した値であり、かつ §3 の走査器欠陥を含む。再現スクリプトはコミットされておらず、本 run では再生成できないため、**内訳の数値は本 REPORT に記載せず撤回する** (前版で報告があったが未再現)。受入 3 は接尾辞対応版で取り直すまで未達扱いとする (→ #1190 の後に再集計)。

## 3. 走査器の欠陥: 接尾辞付きブロックの取り違え

`scan_guard.py` の `BLK_RE` (27 行目) は `^dec_label_pc_([0-9a-f]+):` だけを拾う。IR には接尾辞付きブロック (`dec_label_pc_1003756.preheader:` 等) があり、この正規表現は `.` で止まるため一致しない。その結果、直前の接尾辞無しブロックの末尾 `term` に、別ブロックの終端が混ざる。これはコードから確認できる構造上の欠陥である。

- 件数への影響 (#1190 で実測。入力は `work-m11` の `boot_final.ll` (19,787,837 B)、PE は `fl-win64` の `block00031_PE.bin`):

  | 版 | fn | jcc | dropped | dropped_target_not_label | strict |
  |---|---|---|---|---|---|
  | 修正前 (`BLK_RE` 旧版, `916d9932`) | 6969 | 25618 | 1423 | 7058 | 406 |
  | 修正後 (接尾辞対応, `e7f3062e`) | 6969 | 25618 | 1380 | 6868 | 288 |
  | 修正後 + back-edge 判定修正 (`028e40a0` 単独) | 6969 | 25618 | 1380 | 6868 | 208 |
  | 最終版 (`e9bca3b6`, #1190 時の記録) | 6969 | 25618 | 1380 | 6868 | **288** |

  表の最終行は `e9bca3b6` 時点の前版記録であり、本 run では再測定していない。`git diff e9bca3b6 HEAD -- tools/m11/guard699/` は 0 行。
  `028e40a0` 単独では strict が 208 になった。これは指摘 1 の修正で、頭ブロックを back-edge 候補から外したことによる回帰である
  (単一ブロックの自己ループ `104c711` 型の back-edge を取りこぼした。除去 80 件は全て、ループ先頭への入口が先頭より前のブロックと先頭自身の自己ループだけという形)。
  `e9bca3b6` で頭自身を候補に戻し、実 IR の strict 一覧は `e7f3062e` と集合一致 (除去 0・追加 0) になった。
  よって 406 → 288 の減少は、接尾辞対応 (`e7f3062e`) に由来する分のみで、back-edge 判定の修正による件数変化は実 IR 上では 0 件である。
  preheader (`.preheader` 接尾辞のブロック 338 個) が back-edge と誤判定されない除外は、合成 IR 上での確認のみで、実 IR の件数には現れていない。

- 修正 (#1190): ブロックを VA ではなく名前 (`dec_label_pc_<VA>[.<suffix>]`) で区別する。
  機械語の帰属先は同 VA の接尾辞無しブロック、無ければ接尾辞付きブロック。`LABEL_RE` も接尾辞付きの参照を VA に畳む。
- positive control: `function_8c5eb0` の `8c5f18 jg → 8c6066` (loop_head 8c5f23) は修正後も strict に残る (確認済み)。
- back-edge 判定 (#1190 指摘 1): `back` の候補は「L の頭ブロック以降 (頭自身を含む) でテキスト順に並ぶブロック」。
  合成 IR (`8c5eb0` 型: `8c5f23.preheader` が `8c5f23` へ br し、後方の `8c5f30` が back-edge) で、旧ルール (VA >= L) は preheader を back-edge と誤判定し、現ルールは判定しないことを確認した。
  実 IR (`work-m11`) では、前段の `028e40a0` (頭自身を除外) が 80 件の回帰を入れたため、`e9bca3b6` で頭自身を戻した。
  その結果、実 IR の strict は接尾辞対応版 (`e7f3062e`) と集合一致 (288 件、除去 0・追加 0)。
  つまり実 IR 上では、back-edge 判定の変更による件数の変化は 0 件である。
- 接尾辞対応版の未コミット WIP の strict は 289 と記録されていたが、コミット版では 288 になる。
  差の原因は未切り分け。本 REPORT の数値はコミット版 (`e9bca3b6`) の実測値を正とする。件ごとの真偽は未判定 (#1187)。

## 4. strict 候補の真偽 (受入 2) — 部分達成

- 検出規則は heuristic。件ごとの真偽判定は未完。
- 前版で特定の strict 候補を偽陽性と目視判定したと報告していたが、本 run では未再現。当該候補の関数名・アドレス・判定は記載しない。偽陽性の判定は #1187 で件ごとに行う。
- 既知の真陽性: `function_8c5eb0` の `8c5f18 jg → 8c6066` (#699 で修復済み)。走査器修正後もこれが残ることを positive control として確かめる。
- 偽陽性率は未測定。

## 4a. 件ごとの真偽判定 (#1187・部分達成)

- 注記: 本節の件数 (288) は前版の記録であり、本 run では再実行していない (入力 `boot_final.ll` (`work-m11`) が無いため)。§3 の表は前版の記録として扱う。
- 再現に必要な入力: `work-m11` の `boot_final.ll` (19,787,837 B 記録)、`fl-win64` の `block00031_PE.bin`。
- 判定規則 (件ごと・機械語と IR の突合):
  1. 機械語: 候補 jcc の直前の `cmp` 被演算子 (レジスタ/メモリ) と条件コード (`jg` 等) を取る。
  2. IR: 対応する loop_head 側の判定 (`icmp`) を SSA を遡って同じ値に結ぶ。
  3. 真陽性: IR に入口判定が無く、機械語の jcc が脱出 (T) を指す。偽陽性: IR 側に同等の判定 (別ブロック・別変数) が存在する。
- 既知例 `function_1003730` (3 件, 受入 3): `10039be`・`1003a66`・`1003b10` (機械語の jcc は `cmp` 直後の `jg`)。**件ごとの判定は保留** (IR `boot_final.ll` がこの run に無く、IR 側の突合を実行していないため)。以前のこの節の「真陽性」判定は、IR を見ずに書いたものとして撤回する。再判定は子 issue で行う (§6)。
- 残り 285 件 (288 − 3) の件ごとの真偽と偽陽性率: **未測定**。子 issue へ分割 (§6 (a''))。偽陽性率は母数 288 に対して判定が終わるまで書かない。
- IR 突合 (上記 1〜3 の 2 の段階) は本 run では未完 (IR 入力なし)。§4b 参照。

## 4b. 件ごとの判定の続き (#1498・保留)

- 数値の出所: §4c (#1654 節) と同じ (前版の記録。本 run では再測定していない)。`git diff 088d9eaf HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py` は 0 行。
- 入力: `boot_final.ll` (`work-m11`) はこの run に無く、`scan_guard.py` の再実行も `strict_evidence.py` の実行もしていない。したがって本節は件数の再現も、TSV の生成もしていない。§3 の 288 は前版の記録として扱う。
- 証拠表: `tools/m11/trap_triage/strict_evidence.py` は strict 候補ごとに機械語 (jcc 直前 2 命令) と IR (帰属ブロックの終端・loop_head の icmp 本数) を TSV に書くスクリプトで、判定はしない。TSV はコミットしない (`work/` 配下に生成する)。
- 判定: 3 件 (`10039be`・`1003a66`・`1003b10`) とも**保留**。前版の「真陽性」判定 (IR の `dec_label_pc_*` を根拠にしたもの) は、IR を見ずに書かれていたため撤回する。
- 偽陽性率: 未測定 (判定母数 0)。
- 残り 285 件は子 issue に 3 分割した (§6b)。

## 6b. 残りの分割 (#1498)

- (a'') strict 288 件の件ごと判定 (保留の 3 件を含む) → 子 issue `[M11-N109]`〜`[M11-N111]` (#1653〜#1655)。分割は `strict_evidence.py` の出力 TSV のデータ行 1〜98・99〜193・194〜288 (ヘッダ除く 1 始まり)。TSV は再生成が必要 (`oc_artifacts: fl-win64 work-m11`)。

## 4d. 件ごとの判定 (#1653・部分達成: 判定 0 件・ダンプまで)

- 対象: `strict_evidence.tsv` のデータ行 4〜98 (ヘッダ除く 1 始まり・95 件)。
- 測定 commit (実行経路ごとに分けて記載。`tools/m11` 全体の差分ではなく、各実行物の差分を見る):
  - `scan_guard.py` / `guard699/`: 測定 commit `e9bca3b6`。`git diff e9bca3b6 HEAD -- tools/m11/guard699/` = 0 行。
  - `strict_evidence.py` (TSV 生成) と `scan_guard.py`: 最終変更 commit `e4f16b6e`。`git diff e4f16b6e HEAD -- tools/m11/trap_triage/strict_evidence.py tools/m11/guard699/scan_guard.py` = 0 行。`e9bca3b6..HEAD` では `strict_evidence.py` に 94 行の差分があるが、その変更 (`088d9eaf`・`e4f16b6e`) は現 HEAD の祖先に入っている。
  - 実行 HEAD: 記録なし。`judge_dump.py` が `b483689e` で追加されたため、実行は `b483689e` 以降と推定する。`strict_evidence.py`・`scan_guard.py` は `e4f16b6e` 以降で差分 0 行のため、`b483689e` 以降のどの commit でも同一コードである。ただし TSV 288 行が実際にその時点のコードで生成されたことは、記録がないため確認できていない。
  - `judge_dump.py` (本 PR で追加): 作成 commit `b483689e`。参照する列はいずれも `strict_evidence.py` の出力ヘッダと一致 (構文チェック OK)。
- 入力の実測 (PR 作成者の run。本 fix run では再実行していない): `work-m11` の `boot_final.ll` sha256 `69c774de…a43` (§4a と一致)。`scan_guard.py --report` で strict 288、`strict_evidence.py` で TSV 288 行 (件数 288 は §3 の現 HEAD 行と一致)。
- 判定ダンプ: `tools/m11/trap_triage/judge_dump.py <IR.ll> <evidence.tsv> <lo> <hi>` (判定はしない)。PR 作成者の run でデータ行 4〜98 の 95 件を出力し、loop_head ブロックの欠落は 0 件。本 fix run では IR・TSV が無く未実行 (構文チェックのみ)。
- 判定件数 (母数): **0 件**。偽陽性件数: **未判定**。偽陽性率は書かない。
- 判定方法 (件ごと・残りの作業): 機械語 (`MACH`: jcc 直前 2 命令の cmp 被演算子) を、IR 側 (`LH-icmp`・`BLK-term`) の icmp を SSA 追跡で同じ値に結ぶ。真陽性 = IR に入口判定が無く jcc が脱出先を指す。偽陽性 = IR 側に同等の判定がある。
- 観察 (判定前の所見・確定ではない): 例えば `function_1017ca0` (データ行 5) は機械語の `cmp ebx, r13d` に対し IR の loop_head に入口 icmp が無く、末尾の `%46 = icmp eq (r13−1), 0` のカウンタ判定だけがある。ただし判定は別途 SSA を遡って行うまで保留。
- 再現: `python3 tools/m11/guard699/scan_guard.py <boot_final.ll> --pe <block00031_PE.bin> --report strict.json` → `python3 tools/m11/trap_triage/strict_evidence.py ... --out strict_evidence.tsv` → `python3 tools/m11/trap_triage/judge_dump.py <boot_final.ll> strict_evidence.tsv 4 98`。
- 残り (未解決): データ行 4〜98 の 95 件の件ごとの判定。起票先: #1653 (本 issue、Refs)。

## 4c. 証拠表の行 99〜193 (#1654・部分達成: 判定 0 件)

- 数値の出所 (未確定): 本節の内訳 (jcc・IR 終端・icmp 本数・95 件) は本 run で再現していない。`strict_evidence.py` は `088d9eaf` で導入され、その後 `e4f16b6e` で変更されている。数値を出した版の commit は特定できないため、前版の記録として扱い、確定値にしない。`git diff 088d9eaf HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py` は 0 行 (`guard699/` と `ldmach.py` は不変)。
- 入力: `work-m11` の `boot_final.ll` (本 run に無い)、`fl-win64` の `block00031_PE.bin`。
- 再実行: 未実施 (本 run。`scan_guard.py`・`strict_evidence.py` とも走らせていない)。
- 対象: データ行 99〜193 (ヘッダ除く 1 始まり) の 95 件。内訳は次のとおり。
  - jcc: `jg` 94 件、`jle` 1 件 (`function_a97930`)。
  - IR 側の帰属ブロック終端: 95 件すべて無条件 `br` (`br i1` 無し)。
  - loop_head の icmp 本数: 0 件 11、1 件 39、2 件 40、3 件 2、5 件 1、6 件 2。
- **判定件数 0 / 95・偽陽性件数 0 (判定未完)**。偽陽性率は未測定。
- 判定方法 (件ごと。未実施): 機械語は jcc 直前の cmp/test の被演算子を取る。IR は loop_head の icmp の被演算子を SSA (`%<reg>.N.*`) まで遡り、機械語の被演算子と同じ値に結べるかを見る。レジスタ名の一致だけでは根拠にならない (IR は `reg2mem` の alloca 経由で値を運ぶため、名前の一致と値の同一性は一致しない)。
- 試作した自動突合は、レジスタ名の一致だけで偽陽性にしてしまうためコミットしていない。
- 残作業: 95 件の件ごと判定 (受入条件 1・2)。本 issue (#1654) の範囲として未解決のまま残す。

## 5. 再現

本 PR にコミットされた再現手段は `scan_guard.py` のみで、入力は `work-m11` の `boot_final.ll` を要する。

```sh
cd tools/m11
python3 guard699/scan_guard.py <boot_final.ll> --pe <block00031_PE.bin>
```

`block00031_PE.bin` は `fl-win64` 素材に入っている。`boot_final.ll` は `oc_artifacts: fl-win64 work-m11` で取得する。§2・§4 の数値を再現する作業スクリプトは本 PR にコミットされていない (`work/` は gitignore 対象)。

## 6. 未解決 (子 issue に分割)

- **(a) strict 候補の件ごとの真偽と偽陽性率** → #1187 (`[M11-N72]`): strict 候補を機械語の条件式と IR の条件式で突合する。件ごとの判定は未完 (§4a・§4b。3 件は保留)。残りは子 issue #1653〜#1655 (`[M11-N109]`〜`[M11-N111]`) に分割 (§6b)。親 #1498 の残りも同じ子 issue に分割済み。
- **(b) RetDec の脱落機構の切り分け** (受入 1) → #1188 (`[M11-N73]`): 生 lift 段の CFG 復元と命令翻訳のどちらで落ちるか。`8c5eb0` と同型の最小再現が要る。
- **(c) DEFECTS.md 行案の確定** (受入 4): (a)・(b) の結果に依存する。PM 判断。
- **(d) `scan_guard.py` の接尾辞対応** → #1190 (`[M11-N74]`): `BLK_RE` を接尾辞付きブロックに対応させ、帰属規則を直す。#699 の positive control (`8c5f18`) を崩さないことを確かめてから行う。修正後に受入 3 の内訳を取り直す。

## 7. 範囲

- 本 REPORT のみ変更。`tools/m11/guard699/` は変更しない。
- 範囲外: `m11_ov.c`・`docs/DEFECTS.md` (PM 判断)。
- 20 MiB 超の blob: 追加なし。
