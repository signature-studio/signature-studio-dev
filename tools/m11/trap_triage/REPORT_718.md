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

## 4f. 件ごとの判定 (#1653・run 2: 確定判定 0 件・保留 95 件)

- 測定 commit: `6a88bf35` (origin/main)。`git diff 6a88bf35 HEAD -- tools/m11/guard699/ tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` = 0 行 (本 run はコード変更なし。REPORT のみ)。
- 入力の実測 (本 run): `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`、§4a・§4d と一致)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 実行: `scan_guard.py --report` (4.6 s) で strict 288。`strict_evidence.py --out` (14.9 s) で TSV 288 行。`judge_dump.py <IR> <TSV> 4 98` で 95 件をダンプ (`tools/m11/work/judge_1653_dump.txt`・gitignore・未コミット)。
- 対象: データ行 4〜98 の 95 件。**判定件数 (母数のうち確定した件数): 0 / 95**。確定した真陽性 0 件、確定した偽陽性 0 件、**保留 95 件**。偽陽性率は書かない。
- 判定方法 (件ごと。SSA 追跡で行う): 機械語 (`MACH`: jcc 直前 2 命令の cmp 被演算子) の値が、帰属ブロック・ループ先頭 (`LH-icmp`) の icmp の被演算子と同じ SSA 値かを、reg2mem の alloca 経由で追う。レジスタ名の一致だけでは根拠にしない。真陽性 = 同じ値の入口判定が IR に無く、jcc の脱出先に相当する経路が IR に無い。偽陽性 = 同じ値の同等判定が IR 側にある。
- 本 run で付けた候補判定は、確認で撤回した (保留に戻した):
  - 行 76 (`function_12df9d0`・jcc `12df9f7`): 「飛び先 `12dfa18` へ直接抜ける経路が無い」は誤り。`12dfa00` のカウンタ判定 (counter == 0) の脱出先として `12dfa18` が存在する。機械語の被演算子 `ecx` の対応は未確定のため保留。
  - 行 11・12 (`function_1050f90`): 偽陽性とした根拠は同種の `icmp` の存在だけで、被演算子の同一性 (SSA) を確認していない。保留。
- 保留の主な型 (件ごとの判定が付かなかった理由): (i) ループ先頭の icmp がカウンタ・null 判定だけで、機械語の被演算子に対応する値が追えない (行 4〜10, 13〜27 等)。(ii) 機械語の被演算子が IR の入口で定義されない (行 86・87 の `r9d` 等)。(iii) 機械語の被演算子が stack 変数経由で運ばれ、store/load を追えていない (行 83・84・91 等)。
- 作業の中間結果 (subagent 4 本の出力): `tools/m11/work/judge_1653_chunk_{4_27,28_51,52_75,76_98}.txt` (gitignore・未コミット)。上記の撤回 2 件は、これらの出力をそのまま採用しなかった結果である。
- 残作業 (未解決): 95 件の SSA 追跡による件ごとの判定 (受入 1・2)。起票先: #1653 (本 issue、Refs)。子 issue は新規に起票しない。

## 4e. 証拠表の行 194〜288 (#1655・部分達成: 判定 0 件・ダンプまで)

- 測定 commit: `b7a2a9d9` (origin/main)。`tools/m11/guard699/scan_guard.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_dump.py` はこの commit で変更されていない。
- 入力: `tools/m11/work/boot_final.ll` (19,787,837 B・`work-m11`) と `extracted/block00031_PE.bin` (22,227,016 B・`fl-win64`)。
- 実測: `scan_guard.py --report` で strict 288。`strict_evidence.py` で TSV 288 行を `tools/m11/work/strict_evidence_1655.tsv` に生成 (gitignore 対象・未コミット)。
- ダンプ: `judge_dump.py <IR> <TSV> 194 288` で 95 行を `tools/m11/work/judge_1655_dump.txt` に出力 (判定はしない)。
- 判定件数 (母数): **0 / 95**。偽陽性件数: **未判定**。偽陽性率は書かない。
- ダンプから機械的に言える事実 (判定ではない): loop_head に入口 icmp が 1 本も無いのは行 207・211・234・239・285 の 5 件。これは「真陽性の候補」ではあるが、IR 側に別名の判定がないことの確認 (SSA 追跡) は未実施。
- 判定方法 (件ごと・未実施): 機械語は jcc 直前の cmp/test の被演算子 (`MACH`) を取る。IR は `LH-icmp` と `BLK-term` の被演算子を SSA (`%<reg>.N.*`・`reg2mem` の alloca 経由) まで遡り、機械語の被演算子と同じ値に結べるかを見る。レジスタ名の一致だけでは根拠にならない。
- 残作業: 95 件の件ごとの判定 (受入 1・2)。本 issue (#1655) の範囲として未解決のまま残す。

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

## 4g. 証拠表の行 36〜66 (#3499・部分達成: 母数 31・判定 25 件 (真陽性 25・偽陽性 0)・保留 6 件)

- 測定 commit: `4b6ec01b0` (origin/main。本 PR の基点)。`git diff 4b6ec01b0 HEAD -- tools/m11/guard699/ tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_dump.py` = 0 行。本 PR は `tools/m11/trap_triage/judge_ctx.py` (文脈ダンプ) を追加するだけで、既存の走査・証拠表・ダンプのコードは変えない。
- 入力 (本 run で展開): `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`。§4a・§4d・§4e・§4f と一致)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 再現 (本 run で実行): `scan_guard.py --report` で fn 6969 / jcc 25618 / dropped 1380 / dropped_target_not_label 6868 / strict 288 (§3 の最終版と一致)。`strict_evidence.py --out` で TSV 288 行 (ヘッダ除く)。`judge_dump.py <IR> <TSV> 36 66` と `judge_ctx.py <IR> <TSV> 36 66` で文脈を出した。TSV とダンプは `tools/m11/work/` (gitignore・未コミット)。
- 判定方法 (件ごと。機械語と IR の突合):
  1. 機械語: jcc 直前の cmp の被演算子・条件コード・脱出先 T。
  2. IR: 帰属ブロック B は無条件 `br` で L (ループ先頭) に入る。T へ `br` するブロック (T の preds) を列挙する。
  3. 真陽性 = 機械語の被演算子と同じ値を比べる入口判定が IR の B→L 経路に無く、T へ抜ける経路が L の出口側にしか無い。偽陽性 = 同じ値の同等判定が IR 側にある。本範囲では偽陽性を示す同等判定は見つからなかった。
  4. 機械語の被演算子が IR の何段の参照に当たるかは件ごとに違う (注 2)。偽陽性の判定には同一値の確認が要る。
- 確度: 「2 系統」= 独立した 2 系統の判定が一致、または本 run で IR を直接確認。「単独」= 1 系統のみで、本 run では未照合。
- 判定の経緯: 並列の判定 2 系統 (A: 行 36〜50、B: 行 36〜66) を取った。A は依頼文に範囲が無かったため 36〜50 のみ判定した。B の一部 (行 40・45・46) は本 run で IR を直接確認して採った。判定が割れた件は、上記の直接確認か保留で扱った。
- 行 41 の扱い: 行 41 は A の範囲 (36〜50) にも入るが、A の判定記録に行 41 の結論が残っていない。A が行 41 を判定しなかったのか、判定を記録し損ねたのかは、この記録からは確定できない。A と B の結論が割れたという記録も無い。そのため行 41 は B の 1 系統だけの『単独』とし、2 系統目の照合を #3564 に残す。
- 差し戻し対応の run では `work-m11` が展開されず、IR 側 (B・L・T の preds) を再確認していない。上記の件数 (真陽性 25・偽陽性 0・保留 6、うち 2 系統か直接確認 10・単独 15) は変えていない。

| 行 | 関数 | jcc → T | 判定 | 確度 | 根拠 |
|---|---|---|---|---|---|
| 36 | function_1251960 | 12519ba jg → 1251a47 | 真陽性 | 2 系統 | B `1251960` は無条件 br で L `12519c7` に入る。機械語の入口判定 (ebx=0 > r14d=N-1) に当たる判定が IR に無い。T の preds は L のみ |
| 37 | function_125da90 | 125e022 jg → 125e06d | 真陽性 | 2 系統 | B `125e00b` → L `125e034` に入口判定無し。T の preds は L のみ。注 1 |
| 38 | function_125da90 | 125e0c6 jg → 125e111 | 真陽性 | 2 系統 | B `125e0af` → L `125e0d8` に入口判定無し。T の preds は L のみ |
| 39 | function_1274260 | 12742fa jg → 127433e | 保留 | 2 系統 | L `1274303` に同系の `icmp ult` があるが、head 判定か否か未確定。偽側の `47a250` 呼出しの意味も未確認 |
| 40 | function_127bc80 | 127bcfc jg → 127bd31 | 真陽性 | 直接確認 | B `127bce6` → L `127bd03` に N≤0 の判定無し。T の preds は `127bd27` のみ。注 2 |
| 41 | function_127bc80 | 127be05 jg → 127beaf | 真陽性 | 単独 | 行 40 と同型 (B `127bdef` → L `127be10`)。T の preds は `127bea1` のみ。注 2 |
| 42 | function_127cea0 | 127cf07 jg → 127cf60 | 保留 | 2 系統 | 機械語 esi の源が未確認。IR の counter との同一性を確定できない |
| 43 | function_1280530 | 1285e80 jg → 1285ebc | 保留 | 2 系統 | IR の count は定数 501。機械語 ebx の源が未確認 |
| 44 | function_129f140 | 129f179 jg → 129f1f2 | 真陽性 | 2 系統 | B が同じ global を読む。入口判定無し。T の preds は L のみ |
| 45 | function_12a3ff0 | 12a415e jg → 12a41b6 | 真陽性 | 直接確認 | 機械語の count は call 12f9ed0 の戻り値 (eax−1)。B `12a414e` も同じ戻り値を count に使う。L `12a4165` に icmp 無し。T の preds は `12a41ab` (本体末尾) のみ |
| 46 | function_12a4450 | 12a4621 jg → 12a4671 | 真陽性 | 直接確認 | 機械語 r13d=[[G]+0x10]−1 (3 段参照) と IR (B `12a45fe`) の 3 段参照が一致。L `12a462a` の icmp は counter 判定のみ。T の preds は `12a4665` のみ |
| 47 | function_12a75e0 | 12a760d jg → 12a7685 | 保留 | 2 系統 | L の icmp は探索判定 (`==arg`)。T の preds が 3 本あり、入口判定の有無を確定できない |
| 48 | function_12b51d0 | 12b51ea jg → 12b5216 | 真陽性 | 2 系統 | B `12b51d0` → L `12b51f1` に入口判定無し。T の preds は L のみ |
| 49 | function_12b5220 | 12b523a jg → 12b5269 | 真陽性 | 2 系統 | 行 48 と同型 |
| 50 | function_12b5280 | 12b529a jg → 12b52c9 | 真陽性 | 2 系統 | 行 48 と同型 |
| 51 | function_12b52e0 | 12b52fa jg → 12b5329 | 真陽性 | 単独 | 行 48 と同型 |
| 52 | function_12b5390 | 12b53aa jg → 12b53d9 | 真陽性 | 単独 | 行 48 と同型 |
| 53 | function_12b53f0 | 12b540a jg → 12b5439 | 真陽性 | 単独 | 行 48 と同型 |
| 54 | function_12b5450 | 12b5479 jg → 12b54bc | 真陽性 | 単独 | 2 段で N を読み入口判定無し。T は counter 判定の後段のみ |
| 55 | function_12b54d0 | 12b54ec jg → 12b5536 | 真陽性 | 単独 | 行 54 と同型 |
| 56 | function_12ca540 | 12ca5cd jg → 12ca629 | 真陽性 | 単独 | L に N 判定無し。T は本体内からのみ |
| 57 | function_12ca640 | 12ca666 jg → 12ca73e | 真陽性 | 単独 | L に N 判定無し。T は本体内からのみ |
| 58 | function_12ca770 | 12ca79a jg → 12caaaf | 真陽性 | 単独 | L に N 判定無し。T は本体内からのみ |
| 59 | function_12cab20 | 12cad0f jg → 12cad72 | 真陽性 | 単独 | 2 段で一致。T は本体末尾からのみ |
| 60 | function_12cab20 | 12cad89 jg → 12cae48 | 真陽性 | 単独 | 2 段で一致。T は counter 判定の後段のみ |
| 61 | function_12cab20 | 12cadcb jg → 12cae11 | 真陽性 | 単独 | 2 段で一致。T は L 内の本体後の分岐のみ |
| 62 | function_12cab20 | 12caeec jg → 12cafaf | 真陽性 | 単独 | 2 段で一致。T は本体末尾からのみ |
| 63 | function_12cab20 | 12caf23 jg → 12caf7d | 保留 | 単独 | 単独判定は「IR の call 戻り値と同一」としたが、機械語の被演算子 `[rbx+0x10]` の rbx は call 12df530 の戻り値 (rsi) と別で、同一性の根拠が合わない。注 3 |
| 64 | function_12cb680 | 12cb76b jg → 12cb796 | 真陽性 | 単独 | 同じ `call 12f9ed0` の戻り値が count。T は L 末尾からのみ |
| 65 | function_12cb680 | 12cb803 jg → 12cb8a9 | 保留 | 単独 | 機械語 2 段 (`[[G]]`) に対し IR は 1 段の参照。同一性を確認できない。注 3 |
| 66 | function_12cb680 | 12cbb59 jg → 12cbb9f | 真陽性 | 単独 | 行 64 と同型。T は本体内からのみ |

- 集計: 真陽性 25 件 (2 系統か直接確認 10 件: 36・37・38・40・44・45・46・48・49・50。単独 15 件)、偽陽性 0 件、保留 6 件 (39・42・43・47・63・65)。偽陽性率は書かない (母数 288 のうち判定は 31 件のみ)。
- 注 1: 行 37 は N が 0x40 の定数とされ、jcc は実行時に成立しない可能性が高い。実害は未確認。
- 注 2: 行 40・41 は、機械語が `[[G]+0x10]` (3 段参照)、IR が `sext(i32 [G])+16` (2 段) で参照経路が一致しない。入口判定が IR に無いことは B・L を直接見て確認した。経路の差は別の lift 欠陥の疑いで、未確定。
- 注 3: 行 63・65 は、同一性の根拠が機械語と IR で一致しないため保留。
- 未解決: 保留 6 件と単独判定 15 件の 2 系統目の照合。起票先: #3564 (`[M11-N188]`・親 #3499)。

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
