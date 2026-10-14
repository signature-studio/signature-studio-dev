# REPORT #2679 — spill 宛 未判定 `128f9e0` 12 site の frame slot 突合と判定 (LD-120)

親: #2288 (LD-104) / #1161 (LD-35)。子: #2705 (LD-125・lift 段の欠落起点の特定)。
既知類型との関係: DEFECTS.md の D19 に近い (生 lift で欠落・機構未切り分け)。D1b と検出信号 (機械語 jcc に対応する IR br が無い) は同型だが、機構の切り分けは無い。同一類型かは未確定 (起点は #2705 で特定する)。
本 run は 12 site を UNDETERMINED と判定した (根拠行付き)。TRUE_DROP / OK_LOAD / NO_CONSUMER は 0 件。

## 1. 測定

- 測定 commit: `b28401d5` (main `08138a06` を取り込んだ merge commit。コードを変えた最後の commit)。
  `1d454773` は取り込み前の測定 commit で、その時点の数値は下の「取り込み前」の行に残す。`git diff b28401d5 HEAD -- tools/m11/ldfix` は本 REPORT だけ (docs)。
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (`b28401d5`) → 7/7 完了・所要 1m31.8s。`drops_510.tsv`・`spill178_1161.tsv` は results/ と cmp 一致。
- 追加の実行: `python3 tools/m11/ldfix/ld120_frame_128f9e0.py --verdicts` (TSV と UNDETERMINED 行を生成)。
- 素材: `work-m11` (`boot_final3.ll` の sha256 `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e`・#2288 と同一)、`work-liftdiff`。
  tarball 内が `tools/m11/work/...` の相対パスのため、repo 直下へ `tar --zstd -xf` で展開した (gitignore 対象・commit しない)。
- spill 宛 status (main `08138a06` → PR HEAD): 確定 109 → 109 / 判定不能 16 → 28 / 未判定 53 → 41。`128f9e0` の未判定 12 → 0 (判定不能 13 = 新規 12 + 既存 `12900c4`)。
  main 側の `c589b0` 12 site は #2659 で確定 (NO_CONSUMER) 済みで、本 PR はそこに触れない。
  脱落関数の和集合 69 は不変 (UNDETERMINED は和集合に入らない。audit の [5] で確認)。
- 取り込み前 (`1d454773`・5d88dda2 基準): 確定 97 / 判定不能 16 → 28 / 未判定 65 → 53。
- review round 1 の対応 (前 fix): 素材が取得されていなかったため IR・RetDec・config・機械語の再実行は行わなかった。
  main 取り込み後の run では素材が取得できたが、陽性対照と F 候補照合は本 PR の範囲外のため未実施のまま (§5)。

## 2. 結論

- 12 site (`results/ld120_frame_128f9e0.tsv`) は全て **UNDETERMINED**。根拠行は `candidate_verdicts_1161.jsonl` の 12 行。
- 理由: 機械語では K 連鎖 (`mov rA,[rip+X]; mov rA,[rA]`) の値が `[rbp+d]` に store され、直後に nil 判定 `cmp [rbp+d],0` の消費がある。
  一方、IR 本体には該当 slot の alloca・store・load が無く、K (18746032) を読む load も 0 件。
  IR 上の store→load の結線が立たないため、TRUE_DROP / OK_LOAD / NO_CONSUMER のどの軸も根拠を持てない。根拠の無い判定は入れていない。
  ただし IR 側の 0 件 (§3-2・§3-3) は、検索器の陽性対照 (既知の slot・K load を同じ検索で 1 以上にする確認) を**未実施**。0 件は未対照の観測であり、UNDETERMINED の根拠は暫定扱い。

## 3. 証拠

### 3-1 機械語側 (`ld110_reg2mem_link.py` の helper を再利用)

- frame F = push 2 本 * 8 + `sub rsp, 0x818` = 2088 (0x828)。`[rbp+d]` ↔ `stack_var_-(F-d)`。
- 検証は弱い: プロローグの 0 初期化 store 152 本のうち IR の 0 初期化 store と一致したのは F=2088 で 40 本、次点 (F=3472 等) で 39 本。
  F の候補ごとに config の名前一致本数を数える照合は未実施 (F=2088 だけが 12/12 になることは未確認。下記 §5)。
- 独立の裏付け: `boot3.drc.config.json` の `function_128f9e0` の locals に 12 名 (`stack_var_-760`〜`-1336`) が全て stack 格納で宣言されている。
  この名前は F-d の式で得た名前と一致する (config の locals は 291 本)。
- 12 site の消費者は全て次の参照が `cmp qword ptr [rbp+d], 0` (`ld92_machine_evidence.tsv` と一致)。

### 3-2 IR 本体 (`boot_final3.ll` の `function_128f9e0`・76541〜77198 行)

- alloca は 42 本 (`stack_var_-1400`〜`-2032`・d = 56〜688 相当)。12 slot の alloca・言及は 0 件。K の load は 0 件。
- **未対照**: 上の 0 件に対する陽性対照 (既知の alloca 1 本と K の load を持つ関数で、同じ検索が 1 以上になること) は未実施 (#2705 の受入条件)。

### 3-3 RetDec 出力 (lift・drc)

- `boot3.lift.ll` の同関数 (134989〜135583 行): stack_var は同じ 42 本 (-2032〜-1400)。12 slot の言及は 0 件。
  `1328`・`1336`・`760` 等の offset の直接表現も 0 件。
- `boot3.drc.ll` の同関数 (142298〜142921 行): 同じ 42 本。12 slot の言及は 0 件。
- 同じ名前は他の関数では使われている (`boot3.drc.ll` 全体では `-760` が 8 件)。欠落は関数単位の事象。
- 未対照 (§3-2 と同じ): 上の 0 件の陽性対照は未実施。

### 3-4 欠落の起点 (lift 段)

- block `dec_label_pc_1290610` (`boot3.lift.ll` の 437〜453 行・16 行) は `br label %dec_label_pc_129460b` で終わる。
- 機械語の `0x1290610`〜`0x1294612` は 3045 命令あり、分岐先 (例 `0x1291bc7`・`0x1291bb4`・`0x1293ffb`) の多くは IR に block ラベルが無い。
  関数全体の block ラベルは 35 個。`0x1290645` (`mov rax,[rip+...]`) 以降は block `0x1290610` に現れない。
  site `0x12906d1` はこの欠落域に入る。
- `selectedRanges` (`boot3.drc.config.json`・1631 本) は関数 `0x128f9e0`〜`0x1294ab8` を 100% 被覆しており、範囲指定は原因ではない。
- 未確認: RetDec の lift がどの命令・分岐で打ち切るか。子 #2705 で扱う。
- 未実施: 入口 `128f9e0` から 12 site への到達経路 (BFS の親) の記録と、経路上の IR block の欠落の site ごとの確認。
  この 2 項目は #2679 の受入条件から外し、#2705 の受入条件へ移した (素材 `work-m11` が要る)。

### 3-5 issue 本文との差異

- 入口として挙がった `tools/m11/ldfix/ld104_reach.py`・`results/ld104_reach.tsv`・`results/ld104_checks.txt` は repo に存在しない (`git ls-files` で 0 件)。
  本 run は `results/ld104_sites.tsv`・`results/ld92_machine_evidence.tsv` と機械語・IR の直接突合を使った。

## 4. 12 site の判定表

| site | disp | slot | 次の消費 (機械語) | IR alloca | IR 言及 | drc 言及 | config locals | 判定 |
|---|---|---|---|---|---|---|---|---|
| 12906d1 | 0x530 | stack_var_-760 | 12906d8 `cmp [rbp+0x530],0` | no | 0 | 0 | yes | UNDETERMINED |
| 1291ac3 | 0x490 | stack_var_-920 | 1291aca `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 1291b14 | 0x488 | stack_var_-928 | 1291b1b `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 1291b5f | 0x480 | stack_var_-936 | 1291b66 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 1291c20 | 0x468 | stack_var_-960 | 1291c27 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 1293012 | 0x3c8 | stack_var_-1120 | 1293019 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 1293063 | 0x3c0 | stack_var_-1128 | 129306a `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 12930ae | 0x3b8 | stack_var_-1136 | 12930b5 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 129312c | 0x3a0 | stack_var_-1160 | 1293133 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 129450c | 0x300 | stack_var_-1320 | 1294513 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 129455d | 0x2f8 | stack_var_-1328 | 1294564 `cmp` | no | 0 | 0 | yes | UNDETERMINED |
| 12945a8 | 0x2f0 | stack_var_-1336 | 12945af `cmp` | no | 0 | 0 | yes | UNDETERMINED |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 12 site の TRUE_DROP / OK_LOAD / NO_CONSUMER の判定 (lift 段の打ち切り起点の特定が前提) | 128f9e0 の判定は UNDETERMINED のまま。脱落関数の和集合 69 は 128f9e0 を含まず不変 | #2705 (LD-125) |
| フレーム対応 F=2088 の独立検証 (F の候補ごとにプロローグの 0 初期化 store の一致数と config 名の一致数を記録し、F=2088 だけが 12/12 になることを示す。プロローグ照合の識別力は弱く、config の名前一致で補強しただけ) | slot 名の誤りがあれば判定根拠が覆る | #2705 (受入条件に追記) |
| BFS による入口 `128f9e0` からの到達経路の記録と、経路上の IR block の欠落の site ごとの確認 (#2679 の受入条件から移送) | 12 site の欠落起点の確定が前提 | #2705 (受入条件に追記) |
| 0 件の主張の陽性対照 (IR の alloca・言及 0 件と K load 0 件について、既知の slot と K load を持つ関数で同じ検索が 1 以上になることを数値で示す) | 検索器の取りこぼしを否定できず、UNDETERMINED の根拠は暫定。素材 `work-m11` が要る | #2705 (受入条件に追記) |
| config の locals 291 本に対し IR の alloca は 42 本。同じ欠落が他の関数にもあるか | 他関数の判定の前提に影響する可能性 (本 run では未測定) | 起票なし (記録のみ) |
| `ld120_frame_128f9e0.py` の `--verdicts` 根拠文に行番号 `76541〜77198` が直書き (定数化は未実施) | 追記されるのは未登録 site のみ。現行の 12 行と TSV は影響を受けない。直すとスクリプトの測定 commit が変わるため、素材付きの再実行と同時に行う | 起票なし (次の `--verdicts` 再実行時に `start` / `end` から書く) |
