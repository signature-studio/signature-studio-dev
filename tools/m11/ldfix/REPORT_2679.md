# REPORT #2679 — spill 宛 未判定 `128f9e0` 12 site の frame slot 突合と判定 (LD-120)

親: #2288 (LD-104) / #1161 (LD-35)。子: #2705 (LD-125・lift 段の欠落起点の特定)。
既知類型との関係: DEFECTS.md の D19 に近い (生 lift で欠落・機構未切り分け)。D1b と検出信号 (機械語 jcc に対応する IR br が無い) は同型だが、機構の切り分けは無い。同一類型かは未確定 (起点は #2705 で特定する)。
本 PR は 12 site を UNDETERMINED と判定した (根拠行付き)。TRUE_DROP / OK_LOAD / NO_CONSUMER は 0 件。

## 1. 測定

- 測定 commit: `39684e28` (コードを変えた最後の commit。`59aeff26` からの差分は `ld120_frame_128f9e0.py` の行番号の定数化と `ld120_controls.py` (新規) のみ)。
  `git diff 39684e28 HEAD -- tools/m11/ldfix` は本 REPORT だけ (docs)。
- 実行 (`39684e28`・4 core):
  - `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` → rc=0・7/7 完了・所要 2m43.7s。`drops_510.tsv`・`spill178_1161.tsv` は results/ と一致。
  - `python3 tools/m11/ldfix/ld120_frame_128f9e0.py --verdicts` → `results/ld120_frame_128f9e0.tsv` は差分 0、jsonl への追記は 0 行 (12 site は既存行)。
  - `python3 tools/m11/ldfix/ld120_controls.py` → §3-1 の `[prologue]`・`[F]`・`[cfg]`・`[F-scan]`、§3-2 の `[boot_final3.ll]` 行、§3-3 の `[boot3.lift.ll]`・`[boot3.drc.ll]` 行。
  - 実行後の `/proc/loadavg` の 1 分値 0.81 (実行中の load は未計測)。
- 素材: `work-m11` (`boot_final3.ll` の sha256 `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e`・#2288 と同一)、`work-liftdiff`。
  tarball 内が `tools/m11/work/...` の相対パスのため、repo 直下へ `tar --zstd -xf` で展開した (gitignore 対象・commit しない)。
- spill 宛 status (main `08138a06` → 測定 commit): 確定 109 → 109 / 判定不能 16 → 28 / 未判定 53 → 41。`128f9e0` の未判定 12 → 0 (判定不能 13 = 新規 12 + 既存 `12900c4`)。
  main 側の `c589b0` 12 site は #2659 で確定 (NO_CONSUMER) 済みで、本 PR はそこに触れない。
  脱落関数の和集合 69 は不変 (UNDETERMINED は和集合に入らない。audit の [5]・[6] で確認)。
- 取り込み前 (`1d454773`・5d88dda2 基準): 確定 97 / 判定不能 16 → 28 / 未判定 65 → 53。

## 2. 結論

- 12 site (`results/ld120_frame_128f9e0.tsv`) は全て **UNDETERMINED**。根拠行は `candidate_verdicts_1161.jsonl` の 12 行。
- 理由: 機械語では K 連鎖 (`mov rA,[rip+X]; mov rA,[rA]`) の値が `[rbp+d]` に store され、直後に nil 判定 `cmp [rbp+d],0` の消費がある。
  一方、IR 本体 (`boot_final3.ll`)・lift・drc のいずれにも該当 slot の alloca・store・load が無く、K (18746032) を読む load も IR に無い。
  IR 上の store→load の結線が立たないため、TRUE_DROP / OK_LOAD / NO_CONSUMER のどの軸も根拠を持てない。根拠の無い判定は入れていない。
- 0 件の観測は検索器の対照で確認済み (§3-2・§3-3)。既知の alloca・K の load への同じ検索は 1 以上を返し、1 行挿入すると 0 → 1 になる。
  よって 0 件は検索器の取りこぼしではなく、IR・lift・drc に該当 slot が無いことの観測として扱う。
- 欠落の起点 (lift 段で block `0x1290610` が打ち切られる理由) は未特定 (子 #2705)。

## 3. 証拠

### 3-1 機械語側と frame 対応 (`ld110_reg2mem_link.py` の helper を再利用・`ld120_controls.py` の `[prologue]`・`[F]`・`[cfg]`・`[F-scan]`)

- プロローグ (実測): `0x128f9e0 push rbp ; 0x128f9e1 push rbx ; 0x128f9e2 sub rsp, 0x818 ; 0x128f9e9 mov rbp, rsp`。
- frame F = push 2 本 * 8 + `sub rsp, 0x818` = 16 + 2072 = 2088 (0x828)。rbp の位置はエントリ rsp − 2088 で、`[rbp+d]` はエントリ rsp − (2088 − d) になる。
  RetDec の命名 `stack_var_-(F-d)` はこの式に従う (F の値は算術で決まる。命名規約そのものは下の config の確認で支える)。
- 命名規約の確認: config (`boot3.drc.config.json`) の `function_128f9e0` の locals は 291 本 (全て stack_var)。最小値 −2088 が rbp の位置と一致する (最大 24)。
- 名前の一致は F の独立の裏付けにならない: 12 site の `stack_var_-(F-d)` が全て config の locals に一致する F は、F ∈ [1328, 8192] に **65 通り**ある (1336, 1344, 1360, …, 2032, 2064, 2072, 2088 を含む)。
  F=2088 はその 1 つで、識別力が無い。F の候補ごとの 12/12 照合は行わない。
- 0 初期化 store の照合 (プロローグの store 152 本のうち IR の 0 初期化 store と一致: F=2088 で 40 本、次点 F=3472 で 39 本) は前の run の測定値で、本 run では再測定していない。識別力は弱いため記録のみ。
- 12 site の消費者は全て `cmp qword ptr [rbp+d], 0` (`ld92_machine_evidence.tsv` と一致)。

### 3-2 IR 本体 (`boot_final3.ll` の `function_128f9e0`・76541〜77198 行・閉じ括弧を含む)

- alloca は 42 本 (`stack_var_-2032`〜`-1400`・d = 56〜688 相当)。12 slot (`stack_var_-760`〜`-1336`) の alloca・言及は 0 件。K (18746032) を含む行も 0 件。
- 注記: 12 slot の範囲 (−1336〜−760) と alloca の範囲 (−2032〜−1400) は重ならない。slot が alloca の範囲の外にあるため、alloca が無いのは当然でもある (lift・drc も同じ 42 本)。
- 対照 (`ld120_controls.py` の `[boot_final3.ll]` 行):
  - 陽性 (slot): 既知 alloca `stack_var_-2032` の言及 **5 件** (期待 1 以上)。
  - 陽性 (K): K を含む行は IR 全体で 8 行で、全て `function_10c7cd0` (本体 32557〜38211 行) の中。同じ検索を同関数に当てると **8 件** (期待 1 以上)。`function_128f9e0` の 0 件はこの対照と整合する。
  - 陰性 (slot): 本体の先頭に `%neg = load i64, ptr %stack_var_-760` を 1 行挿入すると、言及が **0 → 1**。
  - 陰性 (K): 本体の先頭に `inttoptr (i64 18746032 to ptr)` の load を 1 行挿入すると、K の行が **0 → 1**。
  - 挿入はメモリ上の本体に対して行い、ファイルは書き換えない。

### 3-3 RetDec 出力 (lift・drc)

- `boot3.lift.ll` の同関数 (134989〜135583 行): stack_var は同じ 42 本 (−2032〜−1400)。12 slot の言及は 0 件。
- `boot3.drc.ll` の同関数 (142298〜142922 行): 同じ 42 本 (−2032〜−1400)。12 slot の言及は 0 件。
- 同じ名前は他の関数でも使われている (`boot3.drc.ll` 全体で `stack_var_-760` は 8 件)。欠落は関数単位の事象。
- 対照 (`ld120_controls.py` の `[boot3.lift.ll]`・`[boot3.drc.ll]` 行):
  陽性 `stack_var_-2032` の言及は lift **5 件**・drc **6 件** (期待 1 以上)。陰性は本体先頭に `stack_var_-760` を 1 行挿入すると lift・drc とも **0 → 1**。
  K の対照は IR のみ (§3-2)。

### 3-4 欠落の起点 (lift 段)

- block `dec_label_pc_1290610` は `boot3.lift.ll` の定義行から相対 437 行目 (ファイル上 135426 行) で始まり、135440 行の `br label %dec_label_pc_129460b` で終わる (空行を含めて 16 行)。
  再現: `sed -n '135426,135441p' tools/m11/work/boot3.lift.ll`。
- 機械語の分岐先 `0x1291bc7`・`0x1291bb4`・`0x1293ffb` の label は lift・IR のどちらにも無い (`grep -cE 'dec_label_pc_(1291bc7|1291bb4|1293ffb):' tools/m11/work/boot3.lift.ll` = 0)。
  site `0x12906d1` は、この block の打ち切りに続く機械語の範囲にある。
- `selectedRanges` (`boot3.drc.config.json` の `decompParams`・1631 本) は関数 `0x128f9e0`〜`0x1294ab8` を連続して被覆しており、範囲指定は原因ではない (本 run で確認)。
- 未確認: RetDec の lift がどの命令・分岐で打ち切るか。子 #2705 で扱う。
- 未実施: 入口 `128f9e0` から 12 site への到達経路 (BFS の親) の記録と、経路上の IR block の欠落の site ごとの確認。
  この 2 項目は #2679 の受入条件から外し、#2705 の受入条件へ移した (素材 `work-m11` が要る)。

### 3-5 issue 本文との差異

- 入口として挙がった `tools/m11/ldfix/ld104_reach.py`・`results/ld104_reach.tsv`・`results/ld104_checks.txt` は、取り込み前の base (`5d88dda2`) には無かった。main 取り込み後 (`08138a06`) は存在する (`ee237f22`・#2659 で取り込み)。
  本 PR は使わず、`results/ld104_sites.tsv`・`results/ld92_machine_evidence.tsv` と機械語・IR の直接突合を使った。

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
| 入口 `128f9e0` から 12 site への到達経路 (BFS の親) の記録と、経路上の IR block の欠落の site ごとの確認 (#2679 の受入条件から移送) | 12 site の欠落起点の確定が前提 | #2705 (受入条件) |
| frame 対応 F=2088 の照合 (根拠は §3-1 のプロローグ算術と config 最小値 −2088。RetDec の命名規約そのものは未検証。12/12 の独立照合は 65 通りで識別力が無いため行わない) | slot 名の誤りがあれば判定根拠が覆る | #2705 (受入条件・照合のみ) |
| config の locals 291 本に対し IR の alloca は 42 本。同じ欠落が他の関数にもあるか | 他関数の判定の前提に影響する可能性 (本 PR では未測定) | 起票なし (記録のみ) |
