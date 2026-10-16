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

## 4g. 証拠表の行 67〜98 (#3502・部分達成: 確定 2 / 32・保留 30)

- 測定 commit: `043720c53` (origin/main `01f1b7e51` の取り込み merge。競合なし)。判定に使うコード (`tools/m11/guard699/`・`tools/m11/ldfix/ldmach.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_ctx.py`・`judge_dump.py`) は、判定ダンプを追加した `e82d0c9ff` から変わっていない: `git diff e82d0c9ff 043720c53 -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py tools/m11/trap_triage/judge_dump.py` = 0 行。main 側で変わった `tools/m11/ldfix/ldfix.py`・`fix_r8b815050.py` は判定の import 経路の外。
- 入力 (本 fix run で実測): `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`)、`fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。`work-m11` は `tools/m11/work/` に展開した (gitignore)。
- 実行 (`043720c53`・foreground・各 1 回): `scan_guard.py --report` 4.3 s (strict 288・dropped 1380・jcc 25618。§3 と一致)、`strict_evidence.py` 12.2 s (TSV 288 行)、`judge_ctx.py <IR> <TSV> <PE> 67 98` 0.9 s (32 件・rc 0)。load average (1 分値) は開始 0.41・終了 0.58 (`/proc/loadavg`)。
- 判定方法 (件ごと): `judge_ctx.py` で、機械語の jcc 直前の命令列 (cmp の被演算子・条件コード)、帰属ブロック B・ループ先頭 L・脱出先 T の IR 本文、B の参照元の終端を出す。機械語の被演算子を、reg2mem の store/load を遡って IR の判定の被演算子と同じ SSA 値に結べた件だけを確定する。
  - 真陽性 (確定の条件): 同じ値の入口判定が IR に無く、jcc の脱出先に相当する経路がある。
  - 偽陽性 (確定の条件): jcc が到達しない (機械語の命令列だけで決まる)、または同じ値の同等判定が IR の直前にある。
  - 保留: 同じ値かの SSA 追跡が終わらないもの。名前 (`%21`・`sgt %113,8` 等) の一致も不一致も根拠にしない (§4c)。
- 判定件数: **確定 2 / 32** (真陽性 0・偽陽性 2)。保留 30。偽陽性率は保留が残るため書かない。
- 前版 (本節の旧版) の真陽性 21 件 (行 67〜71・73〜76・82〜87・91・93・95〜98) は、SSA 追跡を行わず入口判定の有無だけで確定したため撤回し、保留に戻した。

| 行 | 関数 | jcc → 脱出先 / L | 判定 | 理由 |
|---|---|---|---|---|
| 67 | function_12cfce0 | 12cfd97 → 12cfdb7 / 12cfd9e | 保留 | 機械語 `cmp 0, edx` (`ecx` は `xor` で 0、`edx` = `[rax+0x10]`−1)。IR の直前判定 P (12cfd48) の `%21` (`load [%17−8]`) と、B の count (`i32 @18752024`+16 の load) の同一性が未追跡 |
| 68 | function_12cfce0 | 12cfdcb → 12cfe2f / 12cfdd4 | 保留 | 機械語 `cmp ebx, r13d` の `r13d` の出所と、L の判定 (`%62` の i8 比較) の同一性が未追跡。B (12cfdb7) に icmp は無い |
| 69 | function_12d0090 | 12d00d4 → 12d0318 / 12d00df | 保留 | 機械語 `cmp ecx, esi` の被演算子 (`esi`) と、L の判定 (`%11` の i8 比較) の同一性が未追跡 |
| 70 | function_12d0b20 | 12d0b40 → 12d0b7b / 12d0b47 | 保留 | 機械語 `cmp esi, edi` の被演算子と、L の `icmp eq %19, %8` (ポインタ同値) の同一性が未追跡 |
| 71 | function_12d2df0 | 12d2e2f → 12d2f0c / 12d2e3a | 保留 | 機械語 `cmp [rbp+0x5c], ebx` (stack 変数) を store/load で追う作業が未了。B の null 判定 (`%15`・`%17`・`%19`) との同一性も未確認 |
| 72 | function_12d3da0 | 12d3dea → 12d3e0c / 12d3df1 | 保留 | T=12d3e0c は検索ループの続行ブロック。機械語 `ebx > count-1` と IR の添字 (rax.0 / rcx.0) の SSA 同一性が未追跡 |
| 73 | function_12d4480 | 12d4500 → 12d454e / 12d450b | 保留 | 機械語 `cmp [rbp+0x20], esi` (stack 変数) を追う作業が未了。B の参照元 P の `icmp eq i8 %3, 0` と、L の `icmp eq %15, 0` の同一性も未確認 |
| 74 | function_12d6730 | 12d6771 → 12d6859 / 12d677e | 保留 | 機械語 `cmp ebx, r13d` の被演算子と、L の `icmp eq i8 %20, 0` (バイト判定) の同一性が未追跡 |
| 75 | function_12dd6a0 | 12dd6fa → 12dd735 / 12dd703 | 保留 | 機械語 `cmp edi, r14d` の被演算子と、L の `icmp eq %20, %15` (i32) の同一性が未追跡。T の判定 `%40` も未確認 |
| 76 | function_12df9d0 | 12df9f7 → 12dfa18 / 12dfa00 | 保留 | 比較値は `xor ecx,ecx` で定数 0 (`eax` = 0)。被演算子は `r14d` = `[rbx+0x14]`−1 (`sub r14d,1` の後)。IR 側は B の `%0 = arg1+20` の i32 load → zext → `r14.0` (count)。両者が同じ count と言えるには、機械語の `rbx` と IR の `%arg1` が関数入口で対応する必要があり、これは未確認。L は count−1 の末尾判定 (`%4`・`%7`) で、入口判定ではない |
| 77 | function_12dfe90 | 12dfeca → 12dff38 / 12dfed3 | 保留 | L の入口判定 `slt %29,0` の %29 の出所が未追跡 (戻り値由来の可能性) |
| 78 | function_12e21a0 | 12e227e → 12e22b7 / 12e2285 | 保留 | B 直前の P (12e221e) の `slt %15,1` と、機械語の count (`call ea6e30` の戻り値) の同一性が未追跡。12e22d2 の後続も未確認 |
| 79 | function_12f9730 | 12f97a4 → 12f98e1 / 12f97b1 | 保留 | L の入口判定 (2 ロードの比較) の値が count か未追跡 |
| 80 | function_1306d60 | 1306e51 → 1306e85 / 1306e63 | 保留 | B (1306df4) に結果未使用の `slt %28, %storemerge23` があり、機械語の `1 vs count` との対応が未確認 |
| 81 | function_1310300 | 13103e8 → 1310460 / 13103f1 | 保留 | L の入口判定が複数 icmp の合成 (%74・%77 等)。count 由来かの追跡が未完 |
| 82 | function_1311050 | 13110b2 → 1311118 / 13110bb | 保留 | 機械語 `cmp ebx(=ecx), r13d` と、L の判定 (`sle`・`sgt`・`icmp eq %20`) の被演算子の同一性が未追跡。参照元 1311050 の `eq %1,0` は根拠にしない |
| 83 | function_13114d0 | 1311555 → 13115b7 / 131155c | 保留 | 機械語 `cmp [rbp+0x3c], esi` (stack 変数) の store/load を追う作業が未了。L の `icmp eq i64 %37, 0` (ポインタ null 判定) との同一性も未確認 |
| 84 | function_13114d0 | 1311737 → 1311784 / 131173e | 保留 | 機械語 `cmp [rbp+0x3c], esi` (83 と同じ stack 変数) と、L の `icmp eq i32 %157, 0` の同一性が未追跡 |
| 85 | function_4088d0 | 408901 → 40895b / 408908 | 保留 | 機械語 `cmp eax(=ecx), edx` の被演算子と、L の `icmp eq i64 %13, %arg1` (ポインタ同値) の同一性が未追跡。参照元の `eq i8 %3, 0` は根拠にしない |
| 86 | function_40ed10 | 40ed23 → 40ed40 / 40ed2c | 保留 | 機械語 `cmp ecx(=r9d), r10d` と、L の `icmp eq i32 %8, 0` の被演算子の同一性が未追跡。T の `slt %11, 0` も未確認 |
| 87 | function_40edd0 | 40ede0 → 40ee04 / 40ede9 | 保留 | 機械語 `cmp eax(=r9d), r10d` と、L の `icmp eq i32 %14, 0` の被演算子の同一性が未追跡 |
| 88 | function_410820 | 410878 → 4108e5 (jle) / 41087a | 保留 | 機械語の被演算子は `test r13d,r13d` (ループ内の再判定)。B に結果未使用の `icmp sgt/eq %.reload` がある。r13 との同一性が未確認 |
| 89 | function_4144a0 | 4144cb → 414519 / 4144d2 | 保留 | L の入口判定 `eq %7,0` の %7 が count か未追跡 |
| 90 | function_416a50 | 416abd (jb) → 416ae3 / 416abf | **偽陽性** | 機械語の `sub ebx,1` の直後の `test ebx,ebx` が CF を 0 にするため `jb` は成立しない (jcc は到達しない) |
| 91 | function_419400 | 4194b2 → 4194d5 / 4194b9 | 保留 | 機械語 `cmp [rbp+0x34], ecx` (stack 変数) と、L の `icmp eq i16 %33, 0` (i16 ロード) の同一性が未追跡。参照元の `eq i64 %24, 0` は根拠にしない |
| 92 | function_41b7c0 | 41b7df → 41b82e / 41b7e1 | **偽陽性** | 直前の `test r10d,r10d; jle 41b834` (IR の 41b7c0 `slt %2,1`) が count>0 を保証し、`0 > count-1` は成立しない |
| 93 | function_41b850 | 41b866 → 41b887 / 41b86d | 保留 | 機械語 `cmp esi(=eax), edi` と、L の `icmp eq i32 %19, 0` の被演算子の同一性が未追跡 |
| 94 | function_44a8c0 | 44a8d5 → 44a926 / 44a8df | 保留 | L (44a8df) は 44a8e8 へ無条件に進むため、入口判定は 44a8e8 の追跡が必要 |
| 95 | function_44bc50 | 44c04a → 44c083 / 44c053 | 保留 | 機械語 `cmp eax(=edx), r8d` と、L の末尾判定 `icmp eq i32 %165, 0` の同一性が未追跡。参照元 44c022 の `sgt %113,8` は根拠にしない |
| 96 | function_44bc50 | 44c19f → 44c1cd / 44c1a6 | 保留 | 機械語 `cmp eax(=ecx), edx` と、L の `icmp eq i32 %235, 0` の同一性が未追跡。参照元 44c18b の `sgt %202,8` は根拠にしない |
| 97 | function_44bc50 | 44c2cd → 44c2fb / 44c2d4 | 保留 | 機械語 `cmp eax(=ecx), edx` と、L の `icmp eq i32 %301, 0` の同一性が未追跡。参照元の `sgt %268,8` は根拠にしない |
| 98 | function_44bc50 | 44c407 → 44c435 / 44c40e | 保留 | 機械語 `cmp eax(=ecx), edx` と、L の `icmp eq i32 %367, 0` の同一性が未追跡。参照元の `sgt %334,8` は根拠にしない |

- 偽陽性 2 件 (行 90・92) の根拠は機械語の命令列だけで決まる (行 90: `test` が CF を消すため `jb` は成立しない。行 92: 直前ガードで `count-1 >= 0` が成り立つため `jg` は成立しない)。jcc が到達しないので、IR の対応は判定に使っていない。
- 保留 30 件 (行 67〜89・91・93〜98): 同じ値かの SSA 追跡 (reg2mem の store/load を遡る) が未了。起票先: #3502 (Refs。子 issue は新規に起票しない・本 PR の未解決表)。
- 真陽性の構造判定 (IR に count の入口判定が無い) の到達可能性 (count が 0 や負になる経路の有無) は未測定。`docs/DEFECTS.md` の類型への対応は PM 判断。
- 再現: `python3 tools/m11/guard699/scan_guard.py <boot_final.ll> --pe <block00031_PE.bin> --report strict.json` → `python3 tools/m11/trap_triage/strict_evidence.py <IR> --pe <PE> --report strict.json --out strict_evidence.tsv` → `python3 tools/m11/trap_triage/judge_ctx.py <IR> strict_evidence.tsv <PE> 67 98`。

## 4h. 証拠表の行 4〜35 (#3498・母数 32 件: 真陽性 27・偽陽性 1・保留 4)

- 判定 (母数 32): 真陽性 27・偽陽性 1 (行 4・#3854 で確定)・保留 4 (行 10・24・27・29)。保留の 4 件は #3854 の子 issue に移す。件ごとの表・判定規則・未解決は `tools/m11/trap_triage/REPORT_APPENDIX_3498.md` §4h が正本 (250 行上限のため分割移動)。

## 4j. 証拠表の行 36〜66 (#3499・部分達成)

- 結論の正本: 件ごとの判定表・根拠・注 1〜4・未解決は `REPORT_APPENDIX_3499.md` の §4j。250 行上限のため分割移動した (内容は削除していない)。
- 判定ツール `tools/m11/trap_triage/judge_ctx_3499.py` は、main の `judge_ctx.py` (#3502) と名前が衝突したため改名した。

## 4i. 証拠表の行 36〜66 の残り (#3564・部分達成: 判定 21 件・真陽性 12・偽陽性 1・保留 8)

- 全文・行ごとの根拠・判定方法は `REPORT_APPENDIX_3564.md`。本節は結論のみ。
- 測定 commit: `6d12e53f1` (`judge_src.py` の追加 commit。判定に使ったコードの正本)。`git diff 6d12e53f1 HEAD -- tools/m11/guard699/ tools/m11/ldfix/ldmach.py tools/m11/trap_triage/strict_evidence.py tools/m11/trap_triage/judge_ctx.py` = 0 行。入力の IR (`work-m11` の `boot_final.ll`・sha256 `69c774de…`) は本 run に無く、`435960297` での実測。`fl-win64` の `block00031_PE.bin` (22,227,016 B) は本 run で展開。strict 288 (§3 と一致)。
- 検証範囲: 判定は work-m11 の IR に限る (現 main の `m11_e2e.sh --full` 出力では未確認)。到達性 (count = 0 の実行時到達) は範囲外。
- ネガティブコントロール (機械語側・本 run で実測・commit `dd5faa039`): 行 51・56・64 で G・オフセット・幅・段数を 1 項目ずつ壊すと、記録値との照合は 11 件すべて不一致 (オフセットを持たない 64 の 1 件を除く)。行 41 は機械語 3 段・記録 2 段で不一致 (§3 の保留理由と一致)。全文は付録 §7。IR 側は再取得していないので、照合の相手は記録値。
- 基準: 機械語の count 源と IR の count 源が同じ G・同じ段数・同じ幅で、IR に入口判定が無く末尾が後判定 (do-while) なら、count = 0 で IR が本体を回り機械語は T へ直行するので真陽性 (構造判定。count = 0 の到達性は未測定)。jcc が機械語だけで不成立なら偽陽性。
- 結果: 真陽性 12 (51〜56・58・60・62〜64・66)、偽陽性 1 (43)、保留 8 (39・41・42・47・57・59・61・65)。母数 31 のうち残り 10 件 (36〜38・40・44〜46・48〜50) は #3499 の判定 (PR #3571・merge 済み e13f1efd2) で、本節の対象外。偽陽性率は母数 288 の判定が終わるまで書かない。
- 保留の型: 段数が不一致 (41・47・65)、幅が不一致 (57・59・61)、偽側が T と別経路 (39)、戻り値の出所未確認 (42)。
- #3499 節 (PR #3571・merge 済み) の行 40・41 は本節の基準では確定できない (行 41 は保留)。#3499 節の判定は本 PR では直さず、追跡先は #3564 (未解決表)。
- 競合解消 (#3571 の main 取り込み) で判明: 上の #3499 節と本節は行 41・43・57・59・61・63 で判定が一致しない (#3499: 41・57・59・61 真陽性、43・63 保留 / 本節: 41・57・59・61 保留、43 偽陽性、63 真陽性)。#3499 節の『真陽性 25』には 41・57・59・61 が含まれ、本節の基準では保留。どちらを正とするかは未判定。#3564 の 2 系統照合で確定させる (PM 判断: #3499 の判定は変えず、#3499 節の注 4 に『未確定』と明記する)。
- 本 run の追加 (付録 §8・測定 commit `28b96a18c`): 行 37 は jcc が機械語の命令列だけで不成立 (`[rbp+0xac]` = 0x40 の定数書込みは 1 箇所) → 偽陽性・実害なし (#3499 節の『真陽性』は誤り。merge 済みの #3571 の表は本 PR では直さず、追跡先は #3564)。保留 8 件 (39・41・42・47・57・59・61・65) の機構は 3 型: M1 (機械語は K を 2〜3 段 deref、IR は 1 回読み。行 41・42・47・65。`ldfix/REPORT_2794.md` の類型と同型かは未確認)、M2 (K を qword でなく i32 で読む。行 41・47・57・59・61)、M3 (行 39 の L 入口判定の幅 i64/i32)。行 40 は #3499 の範囲で保留 8 件には入らない (#3564 で再確認)。判定件数 (21 件) は変えず、保留の理由を機構で特定した。SSA 同値は未達 (IR 側の K 読みが機械語と一致しない段階で止まる)。

## 4k. 証拠表の行 67〜98 の保留 30 件の再判定 (#3502 run 2・部分達成: 判定 32 件中 確定 13・保留 19)

- 件ごとの表・判定基準・照合の範囲・未解決は `REPORT_APPENDIX_3502.md` が正本。本節は結論のみ。§4g の件数 (確定 2/32) は前 run の記録で、最新は本節と付録。
- 結論: 真陽性 9 (69・70・75・79・85・95・96・97・98)、偽陽性 4 (80・88 を新規、90・92 は前 run)、保留 19。真陽性のうち IR 本文で照合したのは 69・95・96 の 3 件。
- 測定 commit: `1d04852b0` (origin/main)。判定に使うコード (`tools/m11/guard699/`・`tools/m11/trap_triage/strict_evidence.py`・`judge_ctx.py`) は本 PR で変更していない。scan 288・TSV 288 行を再現。

## 4l. 証拠表の行 67〜74・76〜84 (#4885・部分達成: 判定 13 件・真陽性 6・偽陽性 0・保留 7)

- 件ごとの表・判定基準・再現・未解決は `REPORT_APPENDIX_4885.md` が正本。本節は結論のみ。
- 真陽性: 68・71・73・74・76・77。偽陽性: 0。
- 保留 7: 67 (G の読み幅が機械語 qword・IR i32)・72 (jcc の左辺と IR の SSA 同一性が未確定)・78 (IR の入口判定のスキップ先と機械語 jg 先が不一致)・81 (jcc 左辺と IR の SSA 同一性)・82 (count 源が間接呼び出し)・83 (段数・幅が不一致)・84 (参照の段数が 1 段不足)。
- 残り 0 件 (#4885 の担当 13 件のうち 13 件に判定を付けた)。受入条件 1 の「全件を真偽判定」は保留 7 件のため未達。#4885 は open のまま継続する。
- 行 119〜158 (#5660): 判定 0 件・保留 40 (`REPORT_APPENDIX_5660.md`)。行 139〜158 (#5689): 真陽性 12・偽陽性 0・保留 8 (`REPORT_APPENDIX_5689.md` §8)。判定方法と入力は付録 §7 に移した。偽陽性率は母数 288 の判定が終わるまで書かない。

## 4m. 証拠表の行 159〜193 (#5661・部分達成: 確定 6 件 (真陽性 5・偽陽性 1)・保留 29 (母数 35)。#5685 で 168・169 を確定)
件ごとの表・根拠・測定 commit (`f195a93a9`)・未解決は `REPORT_APPENDIX_5661.md` が正本。
行 233〜240 (#5751): 真陽性 8・偽陽性 0・保留 0。236・237 は前 run の保留を、内側ループの counter (`stack_var_-184`・`-180`) で訂正して確定。正本は `REPORT_APPENDIX_5751.md`。

## 4n. 証拠表の行 226〜232 (#5750・母数 7: 真陽性 2 (構造)・保留 5)。正本は `REPORT_APPENDIX_5750.md`

## 5. 再現

本 PR の再現手段は `guard699/scan_guard.py`・`trap_triage/strict_evidence.py`・`trap_triage/judge_entry_check.py` で、入力は `work-m11` の `boot_final.ll` を要する (`oc_artifacts: fl-win64 work-m11`)。`block00031_PE.bin` は `fl-win64` 素材に入っている。

```sh
cd tools/m11
python3 guard699/scan_guard.py <boot_final.ll> --pe <block00031_PE.bin> --report strict.json
python3 trap_triage/strict_evidence.py <boot_final.ll> --pe <block00031_PE.bin> --report strict.json --out strict_evidence.tsv
python3 trap_triage/judge_entry_check.py <boot_final.ll> strict_evidence.tsv 4 35
```

- 期待する出力 (`judge_entry_check.py`): 32 行。行 i の形式は `#<i> <関数> jcc=<jcc の VA> target=<target の VA> | jcc ブロック終端: ... | 脱出先 preds: ...`。先頭行は `#4 function_100bb90 jcc=100bcf4 target=100bd4d` で、以降の各行の関数・jcc・target は上の表の行 i と一致する (前版の記録。IR が無いと照合できない)。
- 形式の確認 (本 run): 合成 IR (`function_100bb90` を模した 1 関数) と TSV の 1 行で `judge_entry_check.py <IR> <TSV> 1 1` を実行し、rc 0 で `#1 function_100bb90 jcc=100bcf4 target=100bd4d | ...` の形式で出ることを確かめた。IR の実データは使っていない。

## 6. 未解決 (子 issue に分割)

- **(a) strict 候補の件ごとの真偽と偽陽性率** → #1187 (`[M11-N72]`): strict 候補を機械語の条件式と IR の条件式で突合する。件ごとの判定は未完 (§4a・§4b。3 件は保留)。残りは子 issue #1653〜#1655 (`[M11-N109]`〜`[M11-N111]`) に分割 (§6b)。親 #1498 の残りも同じ子 issue に分割済み。
- **(b) RetDec の脱落機構の切り分け** (受入 1) → #1188 (`[M11-N73]`): 生 lift 段の CFG 復元と命令翻訳のどちらで落ちるか。`8c5eb0` と同型の最小再現が要る。
- **(c) DEFECTS.md 行案の確定** (受入 4): (a)・(b) の結果に依存する。PM 判断。
- **(d) `scan_guard.py` の接尾辞対応** → #1190 (`[M11-N74]`): `BLK_RE` を接尾辞付きブロックに対応させ、帰属規則を直す。#699 の positive control (`8c5f18`) を崩さないことを確かめてから行う。修正後に受入 3 の内訳を取り直す。

## 7. 範囲

- 本 REPORT の範囲と 20 MiB 超の blob は `REPORT_APPENDIX_5661.md` §7 に分割移動した (250 行上限・内容は削除していない)。
- 範囲外: `m11_ov.c`・`docs/DEFECTS.md` (PM 判断)。
