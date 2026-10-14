# REPORT #2679 — spill 宛 未判定 `128f9e0` 12 site の frame slot 突合と判定 (LD-120)

親: #2288 (LD-104) / #1161 (LD-35)。子: #2705 (LD-125・lift 段の欠落起点の特定)。
本 run は 12 site を UNDETERMINED と判定した (根拠行付き)。TRUE_DROP / OK_LOAD / NO_CONSUMER は 0 件。

## 1. 測定

- 測定 commit: `1d454773` (コードを変えた最後の commit)。`c7e0f161` は同じ判定を先に入れた中間 commit。
  以後の差分は本 REPORT と `docs/DOC_MAP.md` の 1 行のみ (`git diff 1d454773 HEAD -- tools/m11/ldfix` は本 REPORT だけ)。
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` → rc=0・所要 2m34s・7/7 完了。
  `drops_510.tsv`・`spill178_1161.tsv` は results/ と cmp 一致 (`c7e0f161` でも 2m33s・一致)。
- 追加の実行: `python3 tools/m11/ldfix/ld120_frame_128f9e0.py --verdicts` (TSV と UNDETERMINED 行を生成)。
- 素材: `work-m11` (`boot_final3.ll` の sha256 `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e`・#2288 と同一)、
  `work-liftdiff`。tarball 内が `tools/m11/work/...` の相対パスのため、repo 直下へ `tar --zstd -xf` で展開した。
- 変更前の spill 宛 status (5d88dda2 の HEAD): 確定 97 / 判定不能 16 / 未判定 65。
- 変更後 (`1d454773`): 確定 97 / 判定不能 28 / 未判定 53。`128f9e0` の未判定 12 → 0 (判定不能 13 = 新規 12 + 既存 `12900c4`)。
  脱落関数の和集合 69 は不変 (UNDETERMINED は和集合に入らない)。

## 2. 結論

- 12 site (`results/ld120_frame_128f9e0.tsv`) は全て **UNDETERMINED**。根拠行は `candidate_verdicts_1161.jsonl` の 12 行。
- 理由: 機械語では K 連鎖 (`mov rA,[rip+X]; mov rA,[rA]`) の値が `[rbp+d]` に store され、直後に nil 判定 `cmp [rbp+d],0` の消費がある。
  一方、IR 本体には該当 slot の alloca・store・load が無く、K (18746032) を読む load も 0 件。
  IR 上の store→load の結線が立たないため、TRUE_DROP / OK_LOAD / NO_CONSUMER のどの軸も根拠を持てない。根拠の無い判定は入れていない。

## 3. 証拠

### 3-1 機械語側 (`ld110_reg2mem_link.py` の helper を再利用)

- frame F = push 2 本 * 8 + `sub rsp, 0x818` = 2088 (0x828)。`[rbp+d]` ↔ `stack_var_-(F-d)`。
- 検証は弱い: プロローグの 0 初期化 store 152 本のうち IR の 0 初期化 store と一致したのは F=2088 で 40 本、次点 (F=3472 等) で 39 本。
- 独立の裏付け: `boot3.drc.config.json` の `function_128f9e0` の locals に 12 名 (`stack_var_-760`〜`-1336`) が全て stack 格納で宣言されている。
  この名前は F-d の式で得た名前と一致する (config の locals は 291 本)。
- 12 site の消費者は全て次の参照が `cmp qword ptr [rbp+d], 0` (`ld92_machine_evidence.tsv` と一致)。

### 3-2 IR 本体 (`boot_final3.ll` の `function_128f9e0`・76541〜77198 行)

- alloca は 42 本 (`stack_var_-1400`〜`-2032`・d = 56〜688 相当)。12 slot の alloca・言及は 0 件。K の load は 0 件。

### 3-3 RetDec 出力 (lift・drc)

- `boot3.lift.ll` の同関数 (134989〜135583 行): stack_var は同じ 42 本 (-2032〜-1400)。12 slot の言及は 0 件。
  `1328`・`1336`・`760` 等の offset の直接表現も 0 件。
- `boot3.drc.ll` の同関数 (142298〜142921 行): 同じ 42 本。12 slot の言及は 0 件。
- 同じ名前は他の関数では使われている (`boot3.drc.ll` 全体では `-760` が 8 件)。欠落は関数単位の事象。

### 3-4 欠落の起点 (lift 段)

- block `dec_label_pc_1290610` (`boot3.lift.ll` の 437〜453 行・16 行) は `br label %dec_label_pc_129460b` で終わる。
- 機械語の `0x1290610`〜`0x1294612` は 3045 命令あり、分岐先 (例 `0x1291bc7`・`0x1291bb4`・`0x1293ffb`) の多くは IR に block ラベルが無い。
  関数全体の block ラベルは 35 個。`0x1290645` (`mov rax,[rip+...]`) 以降は block `0x1290610` に現れない。
  site `0x12906d1` はこの欠落域に入る。
- `selectedRanges` (`boot3.drc.config.json`・1631 本) は関数 `0x128f9e0`〜`0x1294ab8` を 100% 被覆しており、範囲指定は原因ではない。
- 未確認: RetDec の lift がどの命令・分岐で打ち切るか。子 #2705 で扱う。

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
| フレーム対応 F=2088 の独立検証 (プロローグ照合の識別力は弱く、config の名前一致で補強しただけ) | slot 名の誤りがあれば判定根拠が覆る | #2705 |
| config の locals 291 本に対し IR の alloca は 42 本。同じ欠落が他の関数にもあるか | 他関数の判定の前提に影響する可能性 (本 run では未測定) | #2705 (記録のみ) |
