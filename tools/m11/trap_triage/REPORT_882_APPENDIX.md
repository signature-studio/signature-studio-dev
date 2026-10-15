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
| `functions_dll.csv` 素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM agent の判断待ち: `functions_dll.csv` を素材に含めるか。既定案: 含めず、`m11_e2e.sh` 全体は未実行のまま |

### 14.6 現 head での再測定 (競合解消 merge `8963d89b`)

- 測定 commit: `8963d89b` (`origin/main` `fec12353` を取り込む merge。コードを変えた最後の commit)。競合は `tools/m11/m11_build.sh` の `CF=` 行 1 か所のみで、main の `-DM11_INSTR_40F960` (#1317) と本 PR の `-DM11_INSTR_60A270` (#882) を両方残して解消した。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64`、`work-m11` / `work-liftdiff` を worktree 直下に展開。[EMSDK] が runner に無かったため emsdk 6.0.12 を `emsdk install 6.0.12` で入れた。`llvm-nm` が PATH に無かったため emsdk 同梱の `llvm-nm` を PATH に通した。
- `m11_gen_ir2.sh` rc=0 (29.7 s、`ldfix` errors=0)。`m11_build.sh` は 4 build とも rc=0 (15〜16 s、`wasm-ld signature mismatch: 0`)。`survey_units.mjs` (`SV_RAW=1`) は 4 回とも rc=0 (6.3〜6.6 s)。load average (1 分) は 0.72〜1.21。
- 前回の測定 commit `a28a8e30` から測定 commit までの差: `git diff --numstat a28a8e30 8963d89b -- tools/m11/m11_rt.c tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_post.py` は `m11_build.sh` +4/-2・`m11_ov.c` +16/-0・`m11_rt.c` +13/-1 (`m11_post.py` は差分なし)。内容は次のとおりで、いずれも既定 0 では build 出力を変えない。
  - `m11_build.sh`: CF に `-DM11_DEST_GUARD` (#1547)・`-DM11_INSTR_40F960` (#1317) を追加。`S_NEG` の stamp に `-guard` の項を追加。`ov_instr_40f960.stamp` を追加。
  - `m11_ov.c`: `M11_INSTR_40F960` (既定 0) の計測分岐のみ。
  - `m11_rt.c`: `M11_DEST_GUARD` (既定 0) の分岐を追加。既定 0 でも `m11_dest_obs` の `v` の読出し位置が変わる。

| build (probe) | survey 集計 | unit 895 の観測 (`err` 先頭 3 行) | 895 以外の kind 差 (OFF 比) |
|---|---|---|---|
| OFF (既定 0) | `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` | `Runtime error 210 at 0000000010251450` のみ | — |
| `60A270` 単独 | `ok 872 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1` | `[m11][a270] #1 this=0x0 [this]=0xc343f0 [this+a9]=0` (#2・#3 も同じ) | unit 304・555 が oob→ok |
| `40FFE0`+`40FF70` | `ok 872 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1` | `[m11][ffe0] #1 arg1=0x0 v=[arg1]=0xc343f0 p-144=0x9078558948704d89`、`[m11][p144] #1 arg1=0xc343f0 p-144=0x9078558948704d89 word[head]=0` | unit 304・555 が oob→ok |
| 3 つ全部 ON | `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` | `[m11][a270]` の 3 行 (上と同じ値) | なし |

- 4 行とも §14.3 (測定 commit `a28a8e30`) と集計・unit 895 の値が一致した。現 head でも `60a270` の `this = 0` (null)、`[this] = 0xc343f0` で、受入条件 2 (部分達成) の結論は変わらない。
- 測定 commit `8963d89b` から本 REPORT を含む commit までのコード差分: `git diff 8963d89b HEAD -- tools/m11/m11_rt.c tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_post.py` は 0 (docs のみ)。

## 15. 10 回目の run: `e3ef60` の 60a270 呼出し 9 箇所の `this` 観測 (#2400, 親 #2373)

既知類型との関係: 該当なし (計測 hook の追加のみ。新規の欠陥類型は無い)。

測定 commit: `05f228143` (コードを変えた最後の commit。`tools/m11/m11_ov.c` の `edx` 書式を `%x` に直した commit (review m1))。`tools/m11/m11_build.sh`・`tools/m11/trap_triage/probe2400_ir.py` は `aeb6ceb71` から変えていない。起点は `origin/main` `f44264ebe`。
素材: `fl-win64` を `$RUNNER_TEMP/fl-win64`、`work-m11`・`work-liftdiff` を worktree 直下に展開 (`toolchain-*` は agent-setup が `/opt` に展開済み)。`m11_gen_ir2.sh` rc=0 (33.3 s)。測定後の `/proc/loadavg` は `0.24 0.46 0.29`。
build は `m11_gen_ir2.sh` と同じ `FL_WIN64_DIR` を付ける (build は IR の PE パスと一致しないと止まる)。

### 15.1 実装

- `m11_ov.c`: `M11_PROBE_2400=1` のときだけ有効。`m11_e3ef60_site_obs(site, arg1, this, edx)` が `[m11][e3ef60] #n site=k pe=… off=… arg1=… this=… edx=…` を stderr に出す (512 行で打ち切り)。既定 0 では何も入らない。
- `trap_triage/probe2400_ir.py`: `boot_final3.ll` の `function_e3ef60` 内で `call i64 @function_60a270(i64 <this>, i32 <edx>)` の 9 箇所の直前に呼出しを挿入する (番地順 1〜9)。箇所数が 9 でなければ止まる。冪等。
- `m11_build.sh`: CF に `-DM11_PROBE_2400`、stamp `work/instr_2400.stamp` (値が変わると post 結果と `ov.o` を作り直す)、`M11_PROBE_2400=1` のときだけ probe を呼ぶ。

### 15.2 静的な 9 箇所との突合 (`REPORT_2373.md` §3)

IR 上の 9 呼出しの this は `[arg1+off]` のロード値で、off は §3 の表と一致する (0x778・0x7d8・0x810・0x840・0x808・0x7f0・0x838・0x8e8・0x9c8)。
出現順の確認 (`05f228143` の build の `work/boot_final3.ll`、`function_e3ef60` の `m11_e3ef60_site_obs` 9 呼出しを IR の記述順に並べた):
- `this` の `inttoptr (%arg1 + N)` の N は 1912・2008・2064・2112・2056・2032・2104・2280・2504 = 0x778・0x7d8・0x810・0x840・0x808・0x7f0・0x838・0x8e8・0x9c8。C 側の `off` 表と記述順に一致する。
- IR のブロックラベル `dec_label_pc_e3…` (13 個) は記述順に番地が単調増加する。site 1 は `e3f0a4` のブロック (次は `e3f0c2`)、site 2〜9 は `e3f0db` のブロック (次は `e3f3f3`)。C 側の PE 番地はすべて対応するブロックの範囲 (直前のラベル ≤ PE < 次のラベル) に入る。同一ブロック内は IR の記述順 = 命令順。

### 15.3 測定 (`05f228143`・`SV_RAW=1 node trap_triage/survey_units.mjs`・全て rc=0)

| build | survey 集計 | 備考 |
|---|---|---|
| 既定 (`M11_PROBE_2400` 未設定) | `ok 873 / halt0 7 / miss 47 / oob 14 / noproc 1` (7.3 s) | 起点 `origin/main` `f44264ebe` と同一 (§15.4) |
| `M11_PROBE_2400=1` | `ok 871 / halt0 7 / miss 47 / oob 16 / noproc 1` (JSON の unit 別分類で突合) | 既定との分類差は unit 304・555 (ok→oob) の 2 件 |
| `M11_PROBE_2400=1 M11_INSTR_60A270=1 M11_INSTR_40FFE0=1` | `ok 873 / halt0 7 / miss 47 / oob 14 / noproc 1` (JSON の unit 別分類で突合) | 既定との分類差 0 |

unit 895 (既定・3 build とも `halt0`。frames は `function_60a270` ← `function_e3ef60` ← `function_12d0f80` ← … で同一)。`e3ef60` の arg1 は全呼出しで `0x12ba808`。

| 呼出し | PE | off | this (= `[arg1+off]`) | edx | 60a270 → 40ffe0 (観測) |
|--:|---|--:|--:|--:|---|
| 1 | `e3f0b4` | 0x778 | **0x0** | 0 | 観測なし |
| 2 | `e3f0f7` | 0x7d8 | **0x0** | 0 | 観測なし |
| 3 | `e3f118` | 0x810 | **0x0** | 0 | 観測なし |
| 4 | `e3f139` | 0x840 | 0x10bba000 | 0 | 観測なし |
| 5 | `e3f15a` | 0x808 | **0x0** | 0 | 観測なし |
| 6 | `e3f178` | 0x7f0 | **0x0** | **1** | `40ffe0` arg1=0 → trap (Halt0) |
| 7〜9 | `e3f196`・`e3f1b4`・`e3f215` | — | 未到達 | — | — |

- 3 build で `60a270` の観測 (`[m11][a270]` #1〜#6) も順序どおり (`this`・`[this]` = `0xc343f0` は 1,2,3,5,6、4 は `this=0x10bba000`・`[this]=0`)。`40ffe0` の観測は 1 件だけで、site 6 の 60a270 の中で起きた。
- site 6 と site 7 の間に関数呼出しは IR に無い。trap は site 6 の呼出しの中で起きたと読める。
- this=0 の呼出しは 5 件 (1・2・3・5・6) あるが、`40ffe0` に入ったのは site 6 の 1 件だけ。site 6 だけ edx=1 で、edx=0 の 4 件は `40ffe0` に入らなかった。60a270 の分岐 (edx と this のどちらが効くか) は機械語で未確認。
- `this=0` は arg1 のフィールド (+0x778・+0x7d8・+0x810・+0x808・+0x7f0) の値が 0 であることと同じ。フィールドが 0 になる書込み元は未特定。

### 15.4 既定 build の同一性 (基準値の移動)

- 受入の「既定 build が 870 / 16」は起点 `f44264ebe` 時点でも成り立たない。870/16 は #882 時点 (`8963d89b`) の値で、その後に m11 の変更が入り (#2439・#2502・#2773・#3325 など)、起点時点の既定 build は `873 / 14` になっている。現在の `origin/main` (`10daa391b` 以降) については確認していない。
- 本 PR の既定挙動が変わらないことは、起点 `f44264ebe` の clean worktree で既定 build と survey を取って確認した (`aeb6ceb71` の測定)。`tools/m11/work/boot_final3.ll` の sha256 が一致 (`a415baa4…`)、`m11_boot.cjs.wasm` の sha256 が一致 (`42ae28e1…`)、942 unit の survey 結果が一致 (frames に出る JS のソースパス `ws-2400` と `ws-2400-base` の違いを除く)。`05f228143` の既定 build の wasm sha256 も `42ae28e1…` で一致する (§15.3)。

### 15.5 受入条件

1. `e3ef60` の 9 呼出しのうち this=0 を渡す呼出し: **達成** (5 件: `e3f0b4`・`e3f0f7`・`e3f118`・`e3f15a`・`e3f178`。trap に至るのは `e3f178` の 1 件、§15.3)。
2. 既定 0 の計測専用 probe で、this と arg1・フィールドを観測: **達成** (`M11_PROBE_2400`)。
3. 既定 build の survey が 870 / 16: **文言どおりは未達** (基準が 873 / 14 に移動)。受入は原文のまま #2400 の本文に残し、PR は `Refs #2400` (理由は PR 本文の先頭)。参考として、起点 `f44264ebe` と既定 build が同一であることを §15.4 に記録した。
4. REPORT_882_APPENDIX に観測結果: **達成** (本節)。

### 15.6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `e3ef60` の arg1 (`0x12ba808`) のフィールド +0x778・+0x7d8・+0x810・+0x808・+0x7f0 が 0 である理由 (書込み元。上位 caller `12d0f80` 以降を含む) | null `this` の出所 | #2373 (親 #882) |
| `60a270` が `40ffe0` に入る条件 (edx=1 と this=0 のどちらが効くか。機械語の分岐は未確認) | 受入 2 系 (`40ffe0` の arg1=0 の経路) | #2373 (親 #882) |
| 受入 3 の `870 / 16` の未達 (基準値 870 / 16 → 起点時点 873 / 14 への更新は PM 判断) | 受入文言の基準 | #2400 (`Refs`。基準値の更新は PM 判断) |
| probe 組合せで unit 304・555 の分類が動く (`M11_PROBE_2400=1` 単独で ok→oob) | 計測 hook が分類を変える | #2784 (`[M11-N161]` 304/555/923 の OOB 分類。open) |

### 15.7 再現

```
cd tools/m11 && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash m11_gen_ir2.sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 M11_PROBE_2400=1 bash m11_build.sh
rm -f work/e3ef60_err.log; SV_RAW=1 SV_ERR_LOG=$PWD/work/e3ef60_err.log node trap_triage/survey_units.mjs work/m_on.json
grep '^unit 895 \[m11\]\[e3ef60\]' work/e3ef60_err.log
```

- 測定 commit `05f228143` から本 REPORT を含む commit までのコード差分: `git diff 05f228143 HEAD -- tools/m11/m11_rt.c tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_post.py tools/m11/trap_triage/probe2400_ir.py` は 0 (docs のみ)。
