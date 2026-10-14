# #882 付録: REPORT_882.md の §12・§13 (分割移動)

> **正本**: `tools/m11/trap_triage/REPORT_882.md` (§0 結論・§1〜§11)。本付録は REPORT_882.md の §12・§13 を 250 行上限のため移動したもの。内容は削除していない (Git 履歴の `31bbe1a2` 時点の該当行と同一。ただし §13 表の HEAD 表記のみ修正している)。

## 12. 7 回目の run: `p-144` の再現測定 (HEAD `edef8fa0`、`work-m11` 由来 IR)

既知類型との関係: 該当なし (計測のみ。新規類型は未確定。`p-144` の値が D4 (deref 脱落) に当たるかは未検証のため、DEFECTS の既知 ID には紐付けない)。

### 12.1 手順と結果

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR` はその展開先)、`work-m11` / `work-liftdiff` を repo 直下から展開。`m11_gen_ir2.sh` rc=0 (ldfix errors=0)。
- `m11_gen_ir2.sh` が読むもの: `work/boot0..6.lift.ll` (`work-m11` 同梱の lift 成果) と `$FL_WIN64_DIR` の `block00031_PE.bin` (ldfix の突合用 PE)。
- **IR の出所**: `work-m11` 由来 (#516 以前の生成で、`m11_e2e.sh --full` 由来ではない。WORKFLOW §11・#680)。このため本 §12 の数値は「`work-m11` 由来 IR での実測」であり、survey の基準値ではない。
- 検証 HEAD: `edef8fa0` (origin/main。`git worktree add --detach <repo>/work/wt_verify edef8fa0` で展開し、終了時に `git worktree remove --force`)。
- probe ON (`M11_INSTR_40FF70=1 m11_build.sh`) を 2 回: 2 回とも rc=0・survey 集計は `ok 871 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1`。
  - 出力行: `[m11][p144] #1 arg1=0xc343f0 p-144=0x9078558948704d89 word[head]=0` (survey JSON の unit 895 の `err` 内、unit 896 の直前に出る)。
  - 2 回で同一。`p-144` の値は再現した。
- probe OFF (既定) を 2 回: 2 回とも `ok 869 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1`。
  - `[m11][p144]` 行は 0 件。
- survey の所要: 約 13 s (rc=0)。

### 12.2 §11.2 との差分

- §11.2 の probe OFF `ok 870 / oob 16` は、本 run の `edef8fa0` 再測定 (`ok 869 / oob 16`) と 1 件ずれる。§11.2 の数値は作業ツリー測定 (commit 未確定) で、今回の commit 済み HEAD と一致しない。
- §11.2 の probe ON `ok 872 / oob 14` も、本 run (`871 / 14`) と 1 件ずれる。
- 本 §12 の値は `work-m11` 由来 IR の測定で、survey の基準にはしない。§11.2 の数値と合わせて「未再現 (IR 出所が異なる)」として残す。
- `git diff 19b21178 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_882.md'` の出力は 0 byte ではない (56 files・3076 insertions 等)。§11.5 の「コード差分 0」は、この main 取り込みにより成立しなくなった。

### 12.3 解釈 (断定しない)

- `p-144` の 8 byte `89 4d 70 48 89 55 78 90` は、リトルエンディアンで x86 機械語 (`mov [rbp+0x70],ecx` / `mov [rbp+0x78],rdx` / `nop` に見える) として読める。`p-144` が本来のリスト先頭ではなく、コード領域を指している可能性は残る。
- 単独 (`SV_ONLY=895`) では `arg1=0`・`p-144=0` (§11.2 と同じ)。全体 survey と単独で状態が異なる点は未切り分け。
- `arg1` (`0xc343f0`) の caller 側の値は未確認。

### 12.4 受入条件

1. unit 95 `47ad70` の index / arg1: 未達 (現行 main で OOB 不発。観測対象が無い)。
2. unit 895 `40ff70` の `p-144`: 部分達成 (値は `work-m11` 由来 IR の 2 回の probe ON で再現)。リスト先頭の出所・構造体の中身・`arg1` の caller 側は未特定。
3. DEFECTS 行案: 未達 (新規類型未確定)。

### 12.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `p-144` が機械語を指す原因 (壊れたリスト / 誤った `arg1`) | 受入条件 2 | #2373 (`arg1` の caller 側) |
| §11.2 の作業ツリー測定値 (870/16・872/14) と本 §12 の `work-m11` 由来値 (869/16・871/14) の差 | 数値の基準 | #882 の次 run (同一 HEAD で survey を取り直す) |
| `m11_e2e.sh --full` 由来 IR での再測定 (本 §12 の値の再現) | 数値の出所 | #882 の次 run (`oc_artifacts:` に `work-m11` を含める場合は素材名を明記) |
| probe ON で分類が変わる (ok +2 / oob -2) | 計測 hook が survey を動かす | #1602 (`[M11-N105]`。採取前後で ok/trap が変わらないことを示す受入条件を持つ) |
| `functions_dll.csv` 素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM agent の判断待ち: `functions_dll.csv` を素材に含めるか。既定案: 含めず、`m11_e2e.sh` 全体は未実行のまま |

## 13. 8 回目の run: `40ffe0` の入口 probe (`M11_INSTR_40FFE0`) と caller 側の値

測定 commit: `origin/main` `f5d2aa3b` 起点の `882-m11-p144-caller` (コード変更は本節の probe のみ)。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64`、`work-m11` / `work-liftdiff` を worktree 直下、`m11_gen_ir2.sh` rc=0 (54.1 s)。

### 13.1 実装

- `m11_post.py`: `M11_INSTR_40FFE0=1` のときだけ `function_40ffe0` の wrapper 先頭に `m11_ffe0_obs(arg1)` を入れる (PROBES の末尾追加。既存 index 不変)。
- `m11_ov.c`: `m11_ffe0_obs` を定義。`a` (arg1)、`v = [a]` (40ff70 へ渡る値)、`p-144 = [v-0x90]` を `[m11][ffe0]` として stderr に出す。線形メモリ外は読まない (address 0 は線形メモリ内なので読む)。
- `m11_build.sh`: `M11_INSTR_40FFE0` を CF に渡し、stamp を `40ff70:40ffe0` の組で管理する。既定 0 は従来どおり。

### 13.2 測定 (`SV_RAW=1 node trap_triage/survey_units.mjs`、全て rc=0)

| build | survey 集計 | 観測行 |
|---|---|---|
| probe ON (`M11_INSTR_40FFE0=1 M11_INSTR_40FF70=1`、測定 commit `b559594b`、HEAD `31bbe1a2` は docs のみの差分でコード差分 0、load 1.00) | `ok 872 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1` (13.1 s、rc=0) | `[m11][ffe0] #1 arg1=0x0 v=[arg1]=0xc343f0 p-144=0x9078558948704d89` |
| probe OFF (既定) | `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` | 0 件 |

- 観測の 1 件目 (unit 895 の `err` 内) では `40ffe0` の `arg1` が **0 (null)**。`v = [0] = 0xc343f0` が `40ff70` の `arg1` になり、§12 の `[m11][p144] arg1=0xc343f0` と一致する。
- 前版の probe は `a >= 8` の条件で `[0]` を読まず、`v=0` と誤記録していた。修正後 (address 0 を読む) で値が出た。
- probe ON の survey 集計 (`872/14`) は §11.2・§12 と同じ。

### 13.3 caller 側

- `40ffe0` の唯一の観測 caller は `function_60a270` (`REPORT_596`・`REPORT_663` と一致)。`60a270` は `40ffe0` へ `%8` を渡す。`%8` の出所 (`[rcx]` の deref 元) は本節では未追跡。

### 13.4 受入条件

1. unit 95 `47ad70` の index / arg1: 未達 (現行 main で OOB 不発。観測対象が無い)。
2. unit 895 `40ff70` の `p-144`: **部分達成**。`40ffe0` の `arg1=0` (null) で、`[0]=0xc343f0` が `40ff70` に渡ることを実測。null 由来の `arg1` が 895 の halt0 経路に入る点までは確定。`60a270` の `%8` 出所は未特定。
3. DEFECTS 行案: 未達 (新規類型未確定。D4 変種との対応は未検証)。

### 13.5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `60a270` が `40ffe0` に渡す `%8` (= `arg1` の値) の出所 | 受入条件 2 | #2373 (親 #882) |
| 895 の halt0 が null `arg1` の経路に由来するか (`412770` の null memcpy との関係) | 受入条件 2 | #2373 (親 #882。#1080 は CLOSED のため参照のみ) |
| probe ON の集計 (872/14) と OFF (870/16) の差 | 計測 hook が分類を変える | #1602 (`[M11-N105]`) |
| `functions_dll.csv` 素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM agent の判断待ち: `functions_dll.csv` を素材に含めるか。既定案: 含めず、`m11_e2e.sh` 全体は未実行のまま |

## 14. 9 回目の run: `60a270` の入口 probe (`M11_INSTR_60A270`) と `this` の値

既知類型との関係: 該当なし (計測 hook の追加のみ。既出 D4 変種 (DEFECTS.md) の範囲で読む)。

測定 commit: `a28a8e30` (コード変更の最後の commit。`tools/m11/m11_ov.c` / `m11_post.py` / `m11_build.sh` の 3 ファイル)。
素材: `fl-win64` を `$RUNNER_TEMP/fl-win64`、`work-m11` / `work-liftdiff` を worktree 直下に展開 (tarball は `tools/m11/work/` を含む)。
`m11_gen_ir2.sh` rc=0 (33.8 s)。load average は測定中 0.8–1.0。

### 14.1 機械語 (`disasm_fn.py 60a270`、size 125)

- `60a270` は `40ffe0` を `dx=0xffcd` / `dx=0xffef` で 2 回呼ぶ。どちらも `rcx = rbx` (this) を渡す。`rbx = rcx` (入口の this) である。
- したがって `40ffe0` の arg1 = `60a270` の this。`60a270` の入口で this を観測すれば、`40ffe0` の arg1 の値が分かる。

### 14.2 実装

- `m11_ov.c`: `M11_INSTR_60A270=1` のときだけ `m11_a270_obs(this)` を定義。`this`、`[this]`、`[this+0xa9]` を `[m11][a270]` として stderr に出す。線形メモリ外は読まない。
- `m11_post.py`: `PROBES[0x60a270]` を末尾に追加 (既存 index 不変)。wrapper 先頭で `m11_a270_obs(%p0)` を呼ぶ。
- `m11_build.sh`: CF に `-DM11_INSTR_60A270` を渡し、stamp を `40ff70:40ffe0:60a270` の組にする。既定 0 は従来どおり。

### 14.3 測定 (`SV_RAW=1 node trap_triage/survey_units.mjs <out>`、全て rc=0)

| build (probe) | survey 集計 | unit 895 の観測 (`err` 先頭 3 行) | 895 以外の kind 差 (OFF 比) |
|---|---|---|---|
| OFF (既定 0) | `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` | (出力なし) | — |
| `60A270` 単独 | `ok 872 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1` | `[m11][a270] #1 this=0x0 [this]=0xc343f0 [this+a9]=0` (#2・#3 も同じ) | unit 304・555 が oob→ok |
| `40FFE0`+`40FF70` | `ok 872 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1` | `[m11][ffe0] #1 arg1=0x0 v=[arg1]=0xc343f0 p-144=0x9078558948704d89`、`[m11][p144] #1 arg1=0xc343f0 ... word[head]=0` | unit 304・555 が oob→ok (§13 と一致) |
| 3 つ全部 ON | `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` | `[m11][a270]` の 3 行が先に埋まり、`ffe0`/`p144` は rec.err の 3 行上限で見えない | なし (OFF と同じ kind) |

- 読み: unit 895 の `60a270` は 3 回呼ばれ、いずれも `this = 0` (null)。`[this] = 0xc343f0` で、`40ffe0` の `arg1 = 0` (§13) と一致する。`this` が null で `40ffe0` → `40ff70` に入る経路が 895 にある。
- 3 つ全部 ON の集計が OFF と一致するのは、probe の組み合わせで unit 304・555 の分類が戻るため。probe 同士の干渉か、rec.err 上限の見え方かは未切り分け (前節の注意と同じ)。probe の ON/OFF で分類が動くので、ON の集計は基準に使わない。
- 既定 build (probe OFF) は `870 / 16` で §8・§9・§11・§13 と一致。既定の挙動は変わらない。

### 14.4 受入条件

1. unit 95 `47ad70` の index / arg1: 未達 (現行 main で OOB 不発。観測対象が無い)。
2. unit 895 `40ff70` の `p-144`: **部分達成**。`60a270` の `this` が null であることを実測 (`40ffe0` の arg1 = 0 と一致)。null の `this` を渡す caller (`60a270` の caller と `rcx` の出所) は未特定。
3. DEFECTS 行案: 未達 (新規類型未確定)。

### 14.5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `60a270` の `this` (= `rcx`) の出所。`60a270` の caller を特定し、その caller の入口 probe で `this` を観測する | 受入条件 2 | #2373 (親 #882) |
| probe 組み合わせで unit 304・555 の分類が動く (ON で oob→ok)。3 つ全部 ON で OFF と一致する理由 | 計測 hook が分類を変える | #1602 (`[M11-N105]`。採取前後で ok/trap が変わらないことを示す受入条件を持つ) |

### 14.6 現 head での鮮度 (未再測定)

- 測定 commit `a28a8e30` から検証 head `a3a026ae` (main 取り込み merge) までで、測定に使うファイルに差分がある。
  `git diff a28a8e30 a3a026ae -- tools/m11/m11_rt.c tools/m11/m11_build.sh` の出力は次のとおり (差分 0 ではない)。
  - `m11_build.sh`: CF に `-DM11_DEST_GUARD=${M11_DEST_GUARD:-0}` を追加。`S_NEG` の stamp に `-guard` の項を追加 (既定 0 では従来と同一の値)。
  - `m11_rt.c`: `M11_DEST_GUARD` (既定 0) の分岐を追加。既定 0 でも `m11_dest_obs` の読出し位置 (`v` の読出しが `k` の代入の後) が変わる。
- したがって §14.3 の実測値は `a28a8e30` の build に対する値で、現 head の値ではない。
- 現 head の再測定 (OFF / `60A270` 単独 / `40FFE0`+`40FF70` / 3 つ全部 ON) は、`work-m11`・`work-liftdiff` が要るため、この fix run では未実施。
  `$ARTIFACTS_DIR` には `fl-win64` しか無かった。次の review run で `oc_artifacts: fl-win64 work-m11 work-liftdiff` により再測定する。
| `functions_dll.csv` 素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM agent の判断待ち: `functions_dll.csv` を素材に含めるか。既定案: 含めず、`m11_e2e.sh` 全体は未実行のまま |
