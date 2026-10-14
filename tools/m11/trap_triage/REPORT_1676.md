# #1676 (#1507 の残り): unit 275 の list B が base=0 で生成される経路

親: #1507 (REPORT_881 §10)。前提: `tools/m11/trap_triage/REPORT_881.md` §10。

## 0. 結論

1. **list B は unit 114 で生成され、生成時点で `base(+8)=0`・`cnt=1` になる** (`probe1676_listB_writes.mjs`、n=1)。base は後から 0 になるのではなく、作られた時点で 0。
2. base=0 のまま `50a830` が `[base+8*cnt]` に書くため、unit 114 の callback は `mem[0]` に書き (REPORT_881 §10 の `mem[0]` 一致と同じ)、unit 275 の callback は `mem[8]` (= list A の base 番地) を書き換える。
3. 生成経路の **IR と機械語は一致しない**。`function_410320` / `function_410360` は IR 上 `ret arg1` (identity) だが、機械語はそれぞれ `call qword ptr [rax-0x30]` / `call qword ptr [rbx-0x50]` の **メモリ間接 call** を含む。IR にはこの間接 call が無い。`40f9e0` (list を作る 8651a0 が呼ぶ) はこの 2 関数を経由する。
4. よって base=0 の原因は **間接 call 脱落 (DEFECTS D15 と同類型、メモリ間接 `call [reg+disp]`)** が第一候補。ただし脱落先の vtable 実体で list の base を入れているかは **未確認** (次段で確定)。
5. survey は HEAD で n=2 再現 (`ok 872 / oob 15 / halt0 7`、unit 275 は oob)。

## 1. 実測の基準

- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`)、`toolchain-retdec` ([RETDEC])、`toolchain-emsdk` ([EMSDK])、`work-m11`。
- `work/lift_pe.sha256` は手作業で PE 指紋を記録 (REPORT_881 §10.2 と同じ手順)。
- 全再生成は実行: `m11_e2e.sh` (foreground、rc=0、165 s、load 約 1.0)。reached_stage 4、survey_ok 872、IR sha256 `6909f85d…` (REPORT_881 §10 と一致)。
- 注意: 展開直後の `work-m11` の wasm (`m11_boot.cjs`) は `_m11_icall_cnt_n` を持たず、survey が `TypeError` で落ちた。e2e の再ビルドで解消。

## 2. list B の生成と監視 (n=1)

`trap_triage/probe1676_listB_writes.mjs` (全 942 unit、unit ごとに `[G2+188]`・base・cnt を監視):

| unit | 結果 | list B | base | cnt |
|---|---|---|---|---|
| init | - | 0 | - | - |
| 114 | halt0 | 0x10bd4c20 (新規生成) | **0** | 0→1 |
| 275 | trap (oob) | 同 | 0 | 1→2 |
| 830 | trap | 0 (消失) | - | - |

- 変化した unit は 114・275・830 の 3 件のみ。
- 114 で list B が初めて非 0 になり、そのとき base は既に 0。**生成時の base 初期化が無い**。

## 3. 生成経路 (IR と機械語の突合)

- `function_867510` は `8674a0` (list を走査) の後 `EnumDisplayMonitors(… [G2+188])` を呼ぶ。`8674a0` は `50aa70` と `40faa0` を呼ぶ。
- list の生成元は `function_8651a0` (object 構築)。`[obj+188]` は `40f9e0(obj, 1)` の戻り値 (§7.1 で訂正: 引数 `0xC9A40` は誤りで、正しくは obj=`0xc9bc0`)。
- `40f9e0` → `410320` (alloc 相当) / `410360` (固定サイズ helper)。IR はどちらも `ret arg1`。
- 機械語 (`disasm_img.py`):
  - `410320`: `test dl,dl; ...; call qword ptr [rax-0x30]` (**vtable 間接 call**)。
  - `410360`: `call qword ptr [rbx-0x50]` (**vtable 間接 call**、`rbx = [rax]`)。
  - `8651a0` 内の call 列 (`40f9e0`×6、`5c0d40`×5 など) は IR と一致。
- 既知類型: `tools/m11/REPORT.md` 行 34 の「間接 call が IR から全滅 (4,175 件中 IR 0)」と、`docs/DEFECTS.md` の D15 (メモリ間接 call の空ブロック)。

## 4. 未達と起票先

| 未達 | 理由 | 起票先 |
|---|---|---|
| list B の base 初期化の実体 (vtable 間接 call の実 target と戻り値) の確定 | 間接 call 先の target を `m11_icall` 相当で解決する必要がある | 子 issue (親 #1676) |
| DEFECTS 行の確定 (D15 同類型か、別類型か) | 上記確定後 | 子 issue |
| n≥2 の list B 監視 (probe 1676 の繰り返し) | 本 run は n=1 | 子 issue (再測定) |

## 5. 検証結果 (実測)

- e2e `m11_e2e.sh` (foreground、rc=0、165 s、reached_stage 4、survey_ok 872)。
- survey `SV_RAW=1 survey_units.mjs` n=2: 両回 `{"ok":872,"miss":46,"other":1,"halt0":7,"oob":15,"noproc":1}`。
- probe `probe1507_listB.mjs` n=2: 両回で list B `base(+8)=0`、unit 114 halt0、275 の callback が `mem[8]` を `0x10bd5280` に書換え (REPORT_881 §10 と一致)。
- probe `probe1676_listB_writes.mjs` n=1: list B は unit 114 で base=0 のまま生成。
- 注意: 本 run の確定は n=1 (監視 probe)。n≥2 は未実施。

## 6. #1931 の追補 (n=2 再現・thunk の逆アセンブル)

- 測定 commit: 検証起点 `8f4c6379` (main)。素材: `fl-win64` (sha256 `b2c64da4…`)・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`。
- `work-m11` には `lift_pe.sha256` が無く、`m11_e2e.sh` の全再生成は `m11_bounds.py` が `m2/work/ghidra_dll/functions_dll.csv` を要求して落ちた (素材に無い Ghidra 中間物)。
  PE 指紋 `b2c64da4…` が一致したため `work/lift_pe.sha256` を手で記録し、非 `--full` 経路で再ビルドした。
- e2e `m11_e2e.sh` (foreground、rc=0、166 s、load 0.5): reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (§10 と一致)。
- probe `probe1676_listB_writes.mjs` n=2: 両回とも unit 114 で `L=0x10bd4c20`・`base=0`・`cnt=1` の生成、unit 275 で trap。n=1 の結論が n=2 でも再現。
- thunk の逆アセンブル (`trap_triage/dis1676_thunks.py`):
  - `410320`: `rax=rcx`。`dl<0` 以外のとき `call qword ptr [rax-0x30]` (引数 `rcx=rax`)。
  - `410360`: `rbx=[rax]`、`call qword ptr [rbx-0x50]`。
  - `40f9e0`: `dl≠0` のとき `410320` → `410360` の順に呼ぶ。`dl=0x81` の分岐には `call qword ptr [rbx-0x20]` がある。
  - 補足: IR の `function_410320` / `410360` は `ret arg1` のみで、上記 2 つの間接 call は IR から脱落している。
- 未確定: 間接 call の**実 target** (vtable の中身) と、list B の base を入れる関数。object→vtable の対応は未特定。
  線形逆アセンブルの call 元走査が 0 件だったため、呼出し元の追跡は未完。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[rax-0x30]`・`[rbx-0x50]` の実 target と base 設定関数の確定 | list B の base=0 の原因特定 | 既存 #1783 [LD-63] (410320 スロットの書き込み元の実行時 watch) |
| DEFECTS 行 (D15 同類型か) | 分類 | 上記確定後 (#1931 の残件) |
| `SV_RAW=1 survey_units.mjs` の n≥2 は未実施 (本 run は e2e 内の survey n=1) | survey 側の再現性が未確認 | 既存 #1783 の再測定に含める |

## 7. #1965 の追補: 間接 call の実 target (probe 1 回・実行時メモリ)

- 測定 commit: `f9c89955` (origin/main)。素材・e2e の結果は §6 参照 (本節では e2e を再実行していない)。
- probe `probe1676_listB_writes.mjs` は 1 回のみ実行 (n=1 相当)。n≥2 は未実施。結果: unit 114 で `L=0x10bd4c20`・`base=0`・`cnt=1` の生成、unit 275 で trap。

### 7.1 §6 の訂正 (引数の値)

§6 は `40f9e0(0xC9A40, 1)` と書いたが誤り。`8651a0` の call 元 (VA `0x86522d` 等) は `mov rcx, [rip+disp]` で、`disp` 先のグローバルは VA `0x4c9af8` (wasm `0xc9af8`)。その値 (実行後メモリ) は **`0xc9bc0`** (実 object)。`0xC9A40` は object ではない。

### 7.2 間接 call の実 target (実行後メモリで評価)

- `40f9e0(obj=0xc9bc0, dl=1)` → `410320(rcx=obj)` の `call qword ptr [rax-0x30]`: `[obj-0x30]` = `0xf960` → **VA `0x40f960`**。
- `410360` の `call qword ptr [rbx-0x50]` (`rbx = [rax]`、`rax` は `410360` の引数) の実 target は **未確定**。前回の `[obj-0x50]` の読みは `rbx=[obj]` を評価していないため誤りで、取り消す。
- `40f960` の中身 (逆アセンブル): `rbx=rcx`、`rcx=[rbx-0x80]` (dword) を `409410` に渡し、結果を `40fb40(rcx=rbx, rdx=rax)` に渡す。
- `40fb40` は list を走査し (`[rcx-0xc0]` の配列から `[rsi+r9]` へ 8 byte 書き込み)、`[rsi]=rdi` を書く。`40fac0` は再帰で同系統。**base (+8) を 0 から設定する命令はこの走査には見えない**。
- `409410` の間接 call は `call qword ptr [rip+0xf9c86c]` (IAT slot VA `0x13a5c90` = `0x407a50`)。

### 7.3 IR との突合

- `function_40f960` / `function_40fb40` / `function_40fac0` は IR に定義が無い (`grep 'define.*@function_<VA>'` 0 件)。
- `function_409410` / `40f9e0` / `410320` / `410360` は IR に定義あり。

### 7.4 未確定

- list B の base (+8) を 0 のまま生成する原因の**設定元**は未確定。`40fb40` の走査が base を書かないため、base は `40f9e0` 以外の経路 (list 生成直後の `[L+8]` 未初期化) の可能性が高いが、本 run では未確認。
- DEFECTS 行案 (D15 同類型か) は設定元の確定後。

## 8. #2021 の実測: list B 生成点の窓 (未確定の残件あり)

- 測定 commit: `2782ce9e` (origin/main)。素材: `fl-win64` (sha256 `b2c64da4…`)・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`・`work-liftdiff` を展開。`work/lift_pe.sha256` を PE 指紋で手記録し `m11_e2e.sh` (非 `--full`) を foreground 実行: rc=0、wall 167 s (08:26:11〜08:28:58)、load 1.00 (uptime)、reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (§6 と一致)。
- 数値の出所 (各 n=1): wall・load・reached_stage・survey・IR sha256 は `cd tools/m11 && bash m11_e2e.sh` の結果。icall 列は `cd tools/m11 && node trap_triage/probe1676_u114.mjs` の stderr (unit 114 のみ `_m11_set_trace(1)`)。生成窓は `cd tools/m11 && node trap_triage/probe1676_watch.mjs` の出力。
- 測定対象コードの不変性: `git diff 2782ce9e HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行 (差分 0)。
- `--full` は `m2/work/ghidra_dll/functions_dll.csv` が素材に無く `m11_bounds.py` で落ちた (§6 と同じ)。
- `probe1676_listB_writes.mjs` n=2 (08:29): 両回とも unit 114 で `L=0x10bd4c20`・`base=0`・`cnt=1` の生成、unit 275 で trap、unit 830 で L 消失。§2 と一致。
- `probe1676_u114.mjs` (unit 114 だけ `_m11_set_trace(1)` で icall トレース): stderr 84 行。icall 列の要点は `0x223840`→`0xf960`×…→`0x85df70`→`0xf960`×…→`0x1c0e70`/`0x1c04a0` の交互→`0xf960`×8→`0x1c160`→`0xf960`×2→Halt0。
  - `icall` の値は LVA 相対 (`tkey = target + 0x400000`)。`0xf960`=VA `0x40f960` (`TObject.NewInstance`、m11_ov.c 482 行)、`0x1c04a0`=VA `0x5c04a0` (`ret` 1 命令の既定実体 tr_ret0)、`0x1c0e70`=VA `0x5c0e70` (function_5c0e70)。
- `probe1676_watch.mjs` (icall 行ごとに list B `[G2+188]` の L/base/cnt を比較): n=1 (再実行なし) で次の 1 件のみ変化。
  - `after [icall 0x1c04a0] before [icall 0xf960]: L 0x0->0x10bd4c20, base -(未生成)->0x0, cnt -(未生成)->1`
  - **list B は `icall 0x5c04a0` の直後〜次の `icall 0xf960` (`TObject.NewInstance`) の間に生成され、生成時点で base=0**。
  - 生成窓までは確定。base=0 の書込み主体は未確定: `40f960`/`40fb40` が base を 0 に初期化するかは未確認 (`40fb40` は §7.2 のとおり list を走査して 8 byte 書き込む関数で、memset とは記録していない)。窓内で base を 0 のまま残す命令も本 run では未特定。
- IR 突合: `function_8651a0` が `function_40f9e0(obj, 1)` を 6 回呼び、`+188` に list を格納する (boot0.lift.ll)。ただし `function_40f9e0` の窓内の実際の呼出し経路 (`410320`→`40f960` か) は本 run で未確認。
- `function_47a3e0` (TList Grow) の IR は `[rax-8]` の cap を読む。cap=0 の初期 grow 経路が base 相当を埋めるかは未確認。

| 未達 (#2021 受入条件) | 状況 | 起票先 |
|---|---|---|
| base(+8)=0 の設定元 (関数・命令) の確定 | 生成窓 (icall 0x5c04a0 直後〜0xf960 の間) まで確定。窓内の命令は未特定 | 子 issue (親 #2021) |
| 欠落 IR 箇所と DEFECTS 行案 | 設定元の確定後 | 上記子 issue |
| REPORT §7 続きへの実測記録 | 本節 (§8) で記録済み | 完了 |

## 9. #2057 の実測: 生成窓の再確認 (n=2) と窓内の書込み主体

- 測定 commit: `0d9b5385` (origin/main、本節はコード変更なし。`git diff 0d9b5385 HEAD -- tools/m11` の出力は 0 行)。
- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`)・`toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff`。`work-m11` の展開直後の wasm は survey で落ちたため (§1 と同じ)、`m11_e2e.sh` を `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` で foreground 実行して再生成した。`work/lift_pe.sha256` は PE 指紋で手記録。
- e2e `m11_e2e.sh` (非 `--full`、foreground、rc=0、wall 114 s、uptime load 1.14): reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (§6・§8 と一致)。
- probe `probe1676_watch.mjs` n=2: 両回とも unit 114 で `halt0`、`after [icall 0x1c04a0] before [icall 0xf960]: L 0x0->0x10bd4c20, base -→0x0, cnt -→1` (§8 と一致)。
- probe `probe1676_u114.mjs` の icall トレース (n=1): `icall 0x1c04a0` (= VA `0x5c04a0`、`m11_ov.c` 130 行の `tr_ret0`) の直後に、stub 呼出しも icall も挟まず `icall 0xf960` が来る。L が現れるのはこの間の非 icall 区間。
- IR 上の候補 (未確定): `boot_final.ll` の `function_8651a0` (330118 行〜) は `function_40f9e0(826304, 1)` を 5 回呼び、その戻り値を `+164`・`+172`・`+180`・`+188`・`+244` に格納する (330157〜330180)。`+188` へ格納する値 (330173〜330175) が list B の候補だが、`[G2+188]` との対応は本 run では確認していない。
- 結論: 生成窓は n=2 で再現。窓内の書込み主体 (関数・命令) は未確定。watch の粒度は icall 境界のため、窓内の 1 命令までは絞れていない。

| 未達 (#2057 受入条件) | 状況 | 起票先 |
|---|---|---|
| 窓内で list B 構造体を書く命令 (関数 VA・命令) の確定 | 窓 (`icall 0x5c04a0` 直後〜`icall 0xf960` の前) まで確定。命令単位の watch 未実施 | 子 issue (親 #2057) |
| 欠落 IR 箇所と DEFECTS 行案 | 書込み主体の確定後 | 上記子 issue |

## 10. #2099 の実測: 命令単位の書込み watch (未達・計装が unit 106 で停止)

- 測定 commit: `637b70de` (origin/main。本節は追記のみで、コード差分は `trap_triage/store_watch_2099.sh`・`trap_triage/watch_addr_2099.c` の 2 ファイル)。
- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`)・`toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff`。`work/lift_pe.sha256` は PE 指紋で手記録 (§6 と同じ)。
- e2e `m11_e2e.sh` (非 `--full`、foreground、rc=0、wall 110 s、user 104 s): reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (§6・§8・§9 と一致)。`--full` は `m2/work/ghidra_dll/functions_dll.csv` 不在で `m11_bounds.py` が落ちた (§6 と同じ)。
- `probe1676_watch.mjs` (n=1): unit 114 `halt0`、`after [icall 0x1c04a0] before [icall 0xf960]: L 0x0->0x10bd4c20, base -->0x0, cnt -->1` (§8・§9 と一致)。
- 命令単位の watch: 全 store 計装 (`watch_store_682.py`) に、監視番地を `0x10bd4c20`・幅 32 byte に変えた `trap_triage/store_watch_2099.sh 0 114 u114 114 114` を実行した。**`timeout 900` で rc=124、`[aw]` 0 件、unit 106 で停止** (`u114.err` の `unit` 行は 107 行)。REPORT_1046 §12-13 の unit 106 停止と同じ点。計装 build の後は `m11_build.sh` で clean な wasm に復元済み (復元後の `probe1676_watch.mjs` は上記と同じ結果)。
- 結論: 窓内の書込み主体 (関数・命令) は本 run では未確定。全 store 計装では unit 114 に届かないため、watch の範囲を unit 114 の窓内の関数に絞る計装が必要。

| 未達 (#2099 受入条件) | 状況 | 起票先 |
|---|---|---|
| 窓内で list B `+8/+16` を書く命令 (関数 VA・命令) の確定 | 全 store 計装は unit 106 で停止。窓内の関数に絞った計装が未実施 | 子 issue (親 #2099) |
| 欠落 IR 箇所と DEFECTS 行案 | 書込み主体の確定後 | 上記子 issue |

## 11. #2165 の実測: unit 114 だけの store 計装 (未達・unit 106 で停止)

- 測定 commit: `6444b186` (main)。本節のコード差分は `trap_triage/probe1676_u114.mjs` の stderr 出力 1 行 (`errs` の表示) のみ。`git diff 6444b186 HEAD -- tools/m11` で確認する。
- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`work-m11`・`work-liftdiff`。toolchain は `/opt/emsdk`・`/opt/retdec` に既設。`work/lift_pe.sha256` は PE 指紋で手記録 (§6 と同じ)。
- e2e `m11_e2e.sh` (非 `--full`、foreground、rc=0、wall 140 s、user 128 s、load 1.23): reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (§6・§8・§9・§10 と一致)。
- probe `probe1676_watch.mjs` (再生成後の clean wasm、n=1): unit 114 `halt0`、`after [icall 0x1c04a0] before [icall 0xf960]: L 0x0->0x10bd4c20, base -->0x0, cnt -->1` (§8・§9・§10 と一致)。
- icall トレース (`probe1676_u114.mjs`、n=1、84 行): 最後の `icall 0x1c04a0` の直後に `icall 0xf960` が続く (交互列の末尾。§8 と一致)。
- 計装 (`store_watch_2099.sh 0 114 u114w 114 114`、n=2): 2 回とも `unit 106` で停止、`[aw]` 0 件。1 回目は `timeout 600` の外側で切れ、node が孤児として残ったため PID を指定して停止した。2 回目は script 内の `timeout 900` で rc=124。どちらも終了後に `m11_build.sh` で clean な wasm に復元し、`probe1676_watch.mjs` で baseline が再現することを確認した。
- 結論: 全 store 計装は窓の手前の unit 106 で止まり、unit 114 に届かない。書込み主体 (関数・命令) は未確定。次段は store 計装を窓内の関数だけに絞る (子 issue #2217)。

| 未達 (#2165 受入条件) | 状況 | 起票先 |
|---|---|---|
| 窓内で list B `+8/+16` を書く命令 (関数 VA・命令) の確定 | 全 store 計装は unit 106 で停止。窓内の関数だけの計装が必要 | 子 issue #2217 (親 #2165) |
| 欠落 IR 箇所と DEFECTS 行案 | 書込み主体の確定後 | 子 issue #2217 |

## 12. #2217 の実測: 窓に絞った store 計装 (未達・計装 build の挙動はコミット済み script で未確認)

- 測定 commit: `27a324e0` (origin/main)。本節のコード差分は `trap_triage/store_watch_2217.sh` の追加のみ。
- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff` を展開。`work/lift_pe.sha256` は PE 指紋で手記録 (§6 と同じ)。
- 前提: 素材・測定の基準値は §8 (baseline の e2e・probe 数値) を参照。展開直後の `work-m11` の wasm は `_m11_icall_cnt_n` を持たず、再生成が必要 (§1 と同じ)。
- 窓: 監視 ON は `[m11][icall] 0x1c04a0` (VA `0x5c04a0`) で開き、`[m11][icall] 0xf960` (VA `0x40f960`) でだけ閉じる。窓内の他の icall 行では閉じない (fix 版の script で実装)。IR 上の窓内候補は `function_8651a0` (`boot_final3.ll` 333572〜333722)・`function_40f9e0`・`function_410320`・`function_410360`・`function_409410` (定義あり)。`function_40f960`・`function_40fb40`・`function_40fac0`・`function_5c0e70`・`function_5c04a0` は `boot_final3.ll` に定義が無い。
- 計装: `store_watch_2217.sh <tag> [w114|diag]` は `store_watch_2099.sh` と同じ全 store 計装 (54,342 store) を使い、unit 114 のみ trace 有効。`w114` (既定) は stderr に `unit i` 行のみ、`diag` は各 unit の結果と ms も出す。
- 旧版の観測 (commit されていない作業版、n=1、foreground。コミット済み script では未確認): 計装 build の実行で unit 106 付近の停止が観測された (`timeout` で rc=124、`[aw]` 0 件)。計装を外した同じ wasm は unit 0〜113 を約 1 秒で実行する。監視を OFF にした条件でも停止が観測された。この観測は本 commit の script の出力とは一致しないものとして扱い、確定事実にはしない。
- 未測定: コミット済み script (`w114`・`diag`) での再測定。runner に `toolchain-emsdk`・`toolchain-retdec`・`work-m11` が無く (`fl-win64` のみ)、計装 build を再現できなかった。`w114` の stderr 行数・停止位置も本 commit では未確認。
- 後始末: 停止しなかった node (`run_diag.mjs`) は PID 指定で停止した。その後 `m11_build.sh` (`FL_WIN64_DIR` を export) で clean な wasm に復元し、`m11_sw` の参照が 0 件、`probe1676_watch.mjs` の baseline が `halt0` で再現することを確認した。
- 結論: 窓内の書込み主体 (関数・命令) は未確定。窓に絞った計装 (コミット済み script) の結果は本 runner では未測定。旧版では計装 build が停止したとの観測があるが、再現していない。次段はコミット済み script で `w114` と `diag` を 1 回ずつ実行し、停止位置と行数を確定すること。

| 未達 (#2217 受入条件) | 状況 | 起票先 |
|---|---|---|
| 窓内で list B `+8/+16` を書く命令 (関数 VA・命令) の確定 | 窓に絞った計装の再測定 (コミット済み script) が未実施 (本節) | 子 issue (親 #2217) |
| 欠落 IR 箇所と DEFECTS 行案 | 書込み主体の確定後 | 上記子 issue |
