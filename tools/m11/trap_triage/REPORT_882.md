# #882 unit 95 / 895 の出所調査: 現行 main での再測定

親: #684 (REPORT_684.md §4・§5)。子の依頼元: #684 の受入条件の残り。
検証起点: main `7736a5c5` (PR #1057 取込み後)。素材: fl-win64 / work-m11 / toolchain-emsdk / toolchain-retdec (`$ARTIFACTS_DIR`)。

## 0. 結論

1. **前提が現行 main では成立しない**。REPORT_684 の対象 2 unit は現行 build で挙動が変わっている。
   - unit 95 (`0x1d2680`): OOB → **ok** (survey kind=ok、GDI stub 呼出し 14 件、0 を返して継続)。
   - unit 895 (`0xeddfe0`): OOB → **halt0** (`MessageBoxA` `Runtime error 210 at 0000000010251460`、最上位 frame `function_412770`)。
   よって「unit 95 の OOB の出所」「unit 895 の `p-144` の出所」は、現行 build では観測できる OOB が存在せず、受入条件の対象が消えた。
2. 現行 build の OOB は 16 件 (REPORT_684 §8 `0618c61` 時点 11 件、`e920ac3` 時点 13 件から変化)。単発 OOB 4 unit のうち、**477 と 275 は残存** (`903d20` / `864fe0`)、95 は消えた。
3. **未達**: #882 の受入条件のうち「unit 95 の index・arg1 の出所を実測で特定」「unit 895 のリスト先頭・`p-144` の構造体特定」は、対象の観測が現行 build にないため実測できない。DEFECTS 行案は REPORT_684 §6 に既出 (477 の D11 変種) で、本 run では新規の類型を確定できなかった。

## 1. 再現の条件 (現行 main)

- `m11_e2e.sh` 全体は**未実行**。`m11_bounds.py` が `tools/m2/work/ghidra_dll/functions_dll.csv` を要求し、work-m11 にも fl-win64 にも無いため、全再生成モードで失敗した (fail-closed)。
- `functions_dll.csv` の生成経路 (`docs/WORKFLOW.md` §11: Ghidra 12.1.4 の `support/analyzeHeadless`・JDK 21・`tools/m2/ghidra_scripts/DumpFunctions.java`) は **未試行**。理由: 本 run の runner に Ghidra 12.1.4 が無く (`analyzeHeadless` 不在、`$ARTIFACTS_DIR` は fl-win64 のみ)、JDK は 17.0.20 で 21 ではない。csv の作成には Ghidra 12.1.4 の取得・JDK 21 の導入・`DumpFunctions.java` の実行が必要で、本 run では着手していない。csv が作れれば `m11_e2e.sh` 全体の再現を試せる (素材の追加は §5)。
- 代わりに、既存の lift 成果物 (`work/boot{0..4}.lift.ll`) から `m11_gen_ir2.sh` で IR を再生成 (rc=0、33.5 s、`ldfix` applied)、`m11_build.sh` で build (rc=0、18.8 s)、`survey_units.mjs` を `SV_RAW=1` で実行 (rc=0、9.8 s)。
- 上記の再生成 IR は `work-m11` 素材の IR と同一である保証は無い (provenance stamp が素材に無いため、`ir_conditions.json` の指紋は新規記録)。以降の数値はこの再生成 build の値。

## 2. 実測 (survey、現行 main)

| 構成 | ok | halt0 | miss | oob | other | noproc |
|---|--:|--:|--:|--:|--:|--:|
| REPORT_684 `e920ac3` | 828 | 54 | 46 | 13 | — | 1 |
| REPORT_684 §8 `0618c61` (比較の基準) | 829 | 55 | 46 | 11 | 0 | 1 |
| 本 run `7736a5c5` (再生成 build) | 869 | 8 | 47 | 16 | 1 | 1 |

各行の合計は 942 units (`0618c61` は 829+55+46+11+1 = 942、本 run は 869+8+47+16+1+1 = 942)。

### 2.1 `0618c61` → 本 build の OOB 遷移 (unit 単位)

`0618c61` の OOB 11 件 (56 / 95 / 149 / 275 / 291 / 296 / 304 / 477 / 555 / 895 / 923) と、本 build の OOB 16 件 (144 / 149 / 275 / 280 / 304 / 477 / 484 / 492 / 513 / 520 / 555 / 659 / 745 / 830 / 880 / 923) の差:

| 区分 | unit | `0618c61` | 本 build |
|---|---|---|---|
| OOB → ok | 95 | OOB (`47ad70`) | ok |
| OOB → halt0 | 895 | OOB (`40ff70`) | halt0 (`412770`) |
| OOB → OOB でない | 56 | OOB (`8c6530`) | OOB でない (本 run の survey 出力は 16 件の OOB 一覧のみで、現 ok/halt0/miss の区分は未取得) |
| OOB → OOB でない | 291 / 296 | OOB (`4f9f40`) | OOB でない (同上) |
| halt0 → OOB | 280 / 659 | halt0 (`412770`) | OOB (`6cefb0`) |
| halt0 → OOB でない | 158 | halt0 (`414ad0`) | OOB でない (本 build の OOB 16 件に含まれない)。ok / halt0 / miss の区分は未取得 (本 run の survey 出力に unit 単位の halt0 一覧なし) |
| 新たに OOB | 144 / 745 (`407e20`)、484 / 513 / 520 (`903e00`)、492 (`4133f0`)、830 (`10c7cd0`)、880 (`125da90`) | OOB でない (分類は未取得) | OOB |
| OOB のまま (top frame 変化) | 304 / 555 (`4f9f40` → `535bf2`)、923 (`4f9f40` → `410b10`) | OOB | OOB |
| OOB のまま (top frame 同じ) | 149 (`412e40`)、275 (`864fe0`)、477 (`903d20`) | OOB | OOB |

件数: 両方 OOB 6 件、`0618c61` のみ 5 件 (56 / 95 / 291 / 296 / 895)、本 build のみ 10 件 (144 / 280 / 484 / 492 / 513 / 520 / 659 / 745 / 830 / 880)。

主な変化は次のとおり。(a) 95 の OOB が消え、895 は halt0 になった。(b) 280 / 659 が halt0 から OOB に移った。(c) 144 / 484 / 492 / 513 / 520 / 745 / 830 / 880 が新たに OOB になった。(d) 56 / 291 / 296 の OOB が消えた。halt0 の残り (55 → 8) の内訳は、unit 単位の JSON を本 run で取得していないため未切り分け。main 側のどの変更 (#1057 など) に由来するかも未切り分け。

OOB 16 件の最上位 frame (現行 build): 144 `407e20` / 149 `412e40` / 275 `864fe0` / 280 `6cefb0` / 304 `535bf2` / 477 `903d20` / 484 `903e00` / 492 `4133f0` / 513 `903e00` / 520 `903e00` / 555 `535bf2` / 659 `6cefb0` / 745 `407e20` / 830 `10c7cd0` / 880 `125da90` / 923 `410b10`。

**注意**: halt0 が `0618c61` の 55 → 8 に大きく動いた (`e920ac3` からは 54 → 8)。main 側の変更 (#1057 含む) による遷移と推定するが、未検証 (本 run では main の差分を切り分けていない)。

## 3. unit 95 (現行 ok)

- `function_47ad70` (現行 IR): `[arg1+40] == 0` なら `47ad00`、そうでなければ `[arg1+8]` を長さとする線形探索 (`*(arg1 + 8*i) == arg2` で `i` を返す)。
- REPORT_684 の OOB 経路 (`i64.load` at wasm `0x18f8df`) は、現行 build で unit 95 が通るため**発火しない**。wasm オフセットは再取得していない (現行 wat が無い。`work/m11_boot.wat` は 10/10 の古い生成物)。
- 結論: unit 95 の index `v` と `arg1` の出所は、現行 build では問題の挙動が無いため特定の対象外。

## 4. unit 895 (現行 halt0)

- 最上位 frame `function_412770` (`Runtime error 210` の表示元の前段)。`412770` は `[arg1+56]` から 30 要素、`ptr null` から 37 要素 (i64) を `__asm_rep_movsq_memcpy` で複写し、その後 `function_4126f0` を呼ぶ。
- **観測**: `ptr null` (wasm 上は address 0) からの読み出しを含む。wasm では address 0 は読めるため即 trap はしない。この経路が Runtime error 210 の直接原因かは**未検証**。
- REPORT_684 が述べた `40ffe0` のリスト先頭 (`p-144`) は、現行 build では `40ffe0` まで到達しない (halt0 frame 上では `40ffe0` は `40c820` の caller の一つ)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 現行 main で unit 95 / 895 の trap が消えたことの原因 (main 側のどの変更か) | REPORT_684 の前提の再検証 | PM 判断: #684 へのコメント (main 差分の切り分けを含む) |
| 895 の `412770` の null memcpy が Runtime error 210 の直接原因か (#1080) | 895 の halt0 原因 | #1080 (親 #684) |
| 477 (`903d20`) / 275 (`864fe0`) の残存 OOB | REPORT_684 §3・§4 の未解決 | 既存: #684 |
| `m11_e2e.sh` 全再生成の `tools/m2/work/ghidra_dll` 素材の欠落 (Ghidra 経路は §1 のとおり未試行) | e2e 全体を再現できない | PM 判断: `prepare-event-context.sh` の allowlist に `work-m2` を追加し、R2 に素材を置く。`docs/WORKFLOW.md` §11 の許可名に `work-m2` は無く、`work-m6-ott` は `tools/m2` を展開しないため、現状の `oc_artifacts` 指定では届かない |

## 6. 検証の記録

- `m11_gen_ir2.sh` (foreground、rc=0、33.5 s): `ldfix` F1=902 F2=30 F3c=36 errors=0。
- `m11_build.sh` (foreground、rc=0、18.8 s): `_m11_icall_cnt_n` 2 件。
- `survey_units.mjs` (`SV_RAW=1`、foreground、rc=0、9.8 s): `SURVEY_UNITS {"ok":869,"miss":47,"other":1,"halt0":8,"oob":16,"noproc":1}`。
- `m11_e2e.sh` 全体: 未達 (§1 参照)。

## 7. 元記録 (`7736a5c5`) と main `8bc34ed9` の差分確認 (本 PR では未再実行)

- 起点: origin/main `8bc34ed9` (PR #1242 取込み後、`7736a5c5` から 473 commit 先)。
- 本 PR の run では `fl-win64` のみ取得した。`work-m11` 等が無いため、`8bc34ed9` での build・survey は**未実施**。§6 の数値は `7736a5c5` 起点の元記録であり、`8bc34ed9` での値ではない。
- main 側のどの変更が §2 の遷移を生んだかは未切り分け (§5 の #684 で扱う)。
- 結論: §6 の元記録の範囲では §0 の前提と整合する。`8bc34ed9` での実測は未実施のため、前提が `8bc34ed9` でも成立するかは未検証。受入条件 1・2 (`47ad70` の index / arg1、`40ffe0` のリスト先頭) は対象の観測が無いため未達のまま。受入条件 3 (DEFECTS 行案) は §6 既出の D11 変種の範囲に留まる。
- 未解決の起票先は §5 のとおり。

## 8. 現行 main `f7bebc7b` での再測定 (3 回目の run)

測定 commit: `f7bebc7b` (origin/main、PR #1370 取込み後)。前回 §7 の未実施分を、この commit で実測した。

### 8.1 手順と結果 (foreground、すべて rc=0)

- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`work-m11` / `work-liftdiff` を repo 直下で展開 (`tools/m11/work/`・`tools/liftdiff/work/`)、`toolchain-retdec` / `toolchain-emsdk` を `$RUNNER_TEMP` に展開 ([RETDEC]・[EMSDK] は既存)。
- `m11_gen_ir2.sh`: rc=0、44.6 s、`ldfix` F1=902 F2=30 F3c=36 errors=0。
- `m11_build.sh`: rc=0、25.4 s、`wasm-ld signature mismatch: 0`。
- `survey_units.mjs` (`SV_RAW=1`): rc=0、13.5 s、`ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1`。
- 前回 (§7 の `8bc34ed9`・PR #1261) 記録の `869 / 8` とは 1 件ずれる (ok +1、halt0 -1)。原因は未切り分け。
- 鮮度の証跡 (`docs/WORKFLOW.md` §6): 測定範囲は `src`・`tools/m11`・`tools/liftdiff` (測定に使うコードと素材の生成元)。`git diff f7bebc7b HEAD -- src tools/m11 tools/liftdiff` の結果は `tools/m11/trap_triage/REPORT_882.md` の 37 行追記のみ (本 PR の文書、測定対象外)。それを除いた差分は 0 byte。よって `f7bebc7b` の実測値は現 HEAD と同じコードに対する値であり、再測定は不要。

### 8.2 対象 unit の状態

| unit | VA | 現行 kind | 観測 |
|---|---|---|---|
| 95 | `0x1d2680` | **ok** | GDI stub (`GetDC` 等) を 14 件呼び 0 を返して継続。OOB 不発 |
| 895 | `0xeddfe0` | **halt0** | `MessageBoxA` `Runtime error 210 at 0000000010251440`。最上位 frame `function_412770`。`40ffe0` は frame 上にあるが `40c820` の caller の一つ |

- 受入条件 1 (unit 95 の `47ad70` index・arg1): OOB が出ないため観測対象が無い。**未達**。
- 受入条件 2 (unit 895 の `40ffe0` リスト先頭・`p-144`): 静的な機械語は下記で読めた。動的な値 (先頭の出所・構造体の中身) は未取得。**未達**。
- 受入条件 3 (DEFECTS 行案): 新規類型は確定できず、§6・#1080 §5 の D4 変種のまま。**未達**。

### 8.3 `40ffe0` / `40ff70` の機械語 (`disasm_fn.py`、`f7bebc7b` の PE)

- `40ffe0`: `mov rcx,[rcx]` で 1 段 deref した値を `40ff70` に渡し、戻り値が 0 なら `40c820` を呼ぶ。
- `40ff70`: `rax = rcx` とし、`[rax-0x90]` (= p-144) を先頭ノードとして辿る。各ノードで `word [rcx]` の要素数を見て `[rcx+r9*2+2]` と `dx` を比較し、一致すれば `[rcx + 8*i + …]` を返す。一致が無ければ `[rax-0x78]` の次ノードへ進む (`[rax]` を読んで反復。再帰ではない)。終端では `xor eax,eax` で 0 を返す。
- 読み: halt0 の経路は `40ff70` が 0 を返した後の `40c820` 呼び出しに入る形と整合する。ただし「`p-144` が 0 だった」「一致が無かった」のどちらかは、本 run では動的に切り分けていない。

### 8.4 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `40ff70` の `p-144` の実値と走査結果 (0 の経路が null 先頭か不一致か) | 受入条件 2 | #882 の次 run (`SV_TRACE_AT` での値取得が必要) または #684 |
| 前回 `869 / 8` と本 run `870 / 7` の差 | 比較基準の揺れ | #684 (PM 判断) |
| `functions_dll.csv` の素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM 判断 (§5 と同じ) |

## 9. 4 回目の run: unit 895 の trace 取得 (`SV_TRACE_AT`)

測定 commit: `origin/main` `12586095` (測定用 worktree `ws-882` 起点)。素材は `$ARTIFACTS_DIR` の 5 本を展開 (`fl-win64` → `$RUNNER_TEMP/fl-win64`、`toolchain-retdec` / `toolchain-emsdk` → `$RUNNER_TEMP`、`work-m11` / `work-liftdiff` → worktree 直下)。全コマンド foreground、rc=0。

- `m11_gen_ir2.sh`: rc=0、43.3 s、`ldfix` F1=902 F2=30 F3c=36 errors=0。
- `m11_build.sh`: rc=0、24.9 s。
- `survey_units.mjs` (`SV_RAW=1`): rc=0、13.2 s、`ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1`。§8 (`f7bebc7b`) と一致。load (1 分) 1.14。

### 9.1 unit 895 の trace

- `SV_ONLY=895 SV_TRACE_AT=895` (単独): kind=**oob** (最上位 `function_40ff70`)。全体 survey の halt0 とは**異なる**。差の原因は未切り分け (単独は前 unit を流さないため、その状態の違いが候補)。
- `SV_TRACE_AT=895` (全体): kind=**halt0** (`Runtime error 210 at 0000000010251450`、最上位 `function_412770`)。unit 895 の trace 区間で出たのは `[m11][icall] 0xeddfe0`・`[m11][UStrAsg] dest=0x153fce0 src=0x0 old=0x0`・`MessageBoxA` (Runtime error 210) の 3 種類のみ。
- 区間内に `40ff70` の走査を示す行は無く、`p-144` の値は出力されていない。

### 9.2 結論

- `40ff70` の `p-144` の実値は、本 run でも**未取得**。受入条件 2 は未達のまま。
- 単独 (oob) と全体 (halt0) の差は未切り分け。unit 895 の挙動を読むには全体 survey の文脈が要る。
- `MessageBoxA` のアドレスは §8 (`f7bebc7b`) が `0000000010251440`、§9 (`12586095`) が `0000000010251450`。測定 commit が違い (間に `tools/m11` の変更あり)、commit 差によるものか未切り分け。
- 次の一手: `40ff70` の入口で `p-144` と走査ノードの `word [rcx]` を出す probe を生成 IR に入れる (`m11_ov.c` 改修か `ov` 試験パッチ。`ov_409470_410320_experiment.patch` と同方式)。これは別 run の作業。
- 受入条件 1・3 は本 run でも未達 (§3・§8.2 と同じ)。

## 10. 5 回目の run: probe 設計の確認のみ (実装・測定は未実施)

測定 commit: `origin/main` `83e6ff76` (worktree `ws-882` / branch `882-m11-p144-probe`)。計測・再ビルドは行っていない。

- 機械語の再確認 (`disasm_fn.py 40ff70`、`block00031_PE.bin`、size 109): §8.3 の読みと一致。`rax=rcx` → `[rax-0x90]` (p-144) を先頭ノードとし、`word [rcx]` の要素数で走査、`[rax-0x78]` を次ノードとして辿る。
- probe の入れ方: 既存の計測 probe (`M11_INSTR_413060`、#944) と同じく、C の強定義 `function_40ff70` を `M11_INSTR_40FF70` (既定 0) で gate する。`40ff70` の入口で `p-144` の値と先頭ノードの `word [rcx]` を `m11_probe` / stderr に出す。`m11_post.py` が IR 側を weak 化しているため、強定義で差し替えられる。
- 未実施の理由: 本 run は probe の実装から IR 再生成・build・survey・ネガコンまでを 1 run に収める見込みが無かった。計測と結果の記録は次 run の作業とする。
- 素材の注記: `pefile` が runner の python に無く、`disasm_fn.py` は `LD_M11_PE` 指定で動いた (本 run で `pip` は使えず、既存の venv 側の導入が要る)。
- 受入条件 1・2・3 は未達のまま。

## 11. 6 回目の run: `40ff70` の `p-144` probe の実装と測定 (`M11_INSTR_40FF70`)

既知類型との関係: 該当なし (計測 hook の追加のみ。新規類型は未確定。既出 D4 変種 (DEFECTS.md) の範囲で読む)。

### 11.1 実装

- `m11_post.py`: `M11_INSTR_40FF70=1` のときだけ `function_40ff70` の wrapper 先頭に `m11_p144_obs(arg1)` を入れる。`PROBES` の index は変えない (末尾追加)。
- `m11_ov.c`: `M11_INSTR_40FF70=1` のときだけ `m11_p144_obs` を定義する。`p-144` (= arg1-0x90) と先頭ノードの `word [head]` を `stderr` に `[m11][p144]` として出す。線形メモリ外は読まない。
- `m11_build.sh`: `M11_INSTR_40FF70` を CF に渡し、`ov.o` と `boot_final3.ll` を stamp で無効化する。既定 0 は従来どおり。

### 11.2 測定 (全体 survey = `SV_RAW=1 node survey_units.mjs`、素材 `fl-win64` を `$RUNNER_TEMP`)

| build | survey 集計 | unit 895 の `[m11][p144]` |
|---|---|---|
| probe ON (`M11_INSTR_40FF70=1`) | `ok 872 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1` | `#1 arg1=0xc343f0 p-144=0x9078558948704d89 word[head]=0` |
| probe OFF (既定) | `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` (前回 §8・§9 と一致) | (出力なし) |
| probe ON・`SV_ONLY=895` (単独) | `oob 1` | `#1 arg1=0x0 p-144=0x0 word[head]=0` |

- 集計は probe ON で ok +2 / oob -2 と動く。これは観測 hook が survey の分類を動かした**副作用の確認 (probe ON で分類が変わる)** であり、WORKFLOW §5 のネガティブコントロール (1 件を壊して FAIL を確認) ではない。この build の集計は計測専用で、既定の基準には使わない。
- 全体 survey の `p-144 = 0x9078558948704d89` をリトルエンディアンで並べると `89 4d 70 48 89 55 78 90` となり、x86 機械語の断片に見える。`p-144` が本来のリスト先頭ではなく、コード・壊れた領域を指している可能性がある。ただし 1 件の観測であり、断定はしない。
- 単独 (`SV_ONLY=895`) では `arg1=0`、`p-144=0` で、null 先頭からの読み出しになる (oob)。全体 survey と状態が異なる。

### 11.3 受入条件

1. unit 95 の `47ad70` index / arg1: 未達 (現行 main で OOB 不発。§8.2 と同じ)。
2. unit 895 の `40ff70` の `p-144`: **部分達成**。全体 survey で 1 件の値を取得 (上記)。ただし値が機械語断片に見え、リスト先頭の出所・構造体の中身は未特定。`arg1` の出所 (`40ffe0` の引数) は未確認。
3. DEFECTS 行案: 未達 (新規類型を確定できず)。

### 11.4 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 全体 survey の `p-144` が機械語断片を指す原因 (壊れたリスト・誤った arg1 のどちらか) | 受入条件 2 | #882 の次 run (`arg1` の caller 側の値の取得) または #684 |
| probe ON の集計 (872/14) と OFF (870/16) の差 (probe ON で分類が変わるため、probe ON の集計は基準に使えない) | 計測 hook が分類を変える | #684 (PM 判断) |
| `functions_dll.csv` の素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM 判断 |

### 11.5 検証 (測定 commit と差分)

- 測定 commit: `19b21178` (コード変更の最後の commit。§11.1 の 3 ファイル)。
- 測定 commit から HEAD までの差分 (`git diff 19b21178 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_882.md'`): 出力 0 byte (コード差分 0)。
- 同 `--stat` (REPORT のみ): `tools/m11/trap_triage/REPORT_882.md | 18 ++++++++++++++----` (14 insertions, 4 deletions)。変わったのは本 REPORT の文書のみ。コードの再測定は不要。
- §11.2 の 3 build は作業ツリーで測った。測定時の `git status --porcelain` は記録していない。`19b21178` と同一であることは、本 run では**確認できていない**。再測定 (`git worktree add --detach ... 19b21178`) は、`work-m11` 素材が本 run の `$ARTIFACTS_DIR` に無く (`fl-win64` のみ) 未実施。そのため §11.2 の数値は「作業ツリー測定・未再現」の値として扱い、基準には使わない。
- 既定 build (probe OFF) は §11.2 の `870 / 16` で前回値 (§8・§9) と一致 (= 既定の挙動は変わらない)。
- 差分確認: `git diff 31cb5831 19b21178 -- tools/m11` は `m11_build.sh` / `m11_ov.c` / `m11_post.py` の probe 追加のみ (既定 0 で無効)。

## 12. 7 回目の run: `p-144` の再現測定 (HEAD `edef8fa0`、commit 済み HEAD で再現)

既知類型との関係: 該当なし (計測のみ。新規類型は未確定。既出 D4 変種の範囲)。

### 12.1 手順と結果

- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR` はその展開先)、`work-m11` / `work-liftdiff` を repo 直下から展開。`m11_gen_ir2.sh` rc=0 (ldfix errors=0)。
- 検証 HEAD: `edef8fa0` (origin/main、detached worktree `~/ws-882`)。
- probe ON (`M11_INSTR_40FF70=1 m11_build.sh`) を 2 回: 2 回とも rc=0・survey 集計は `ok 871 / halt0 7 / miss 47 / oob 14 / other 1 / noproc 1`。
  - 出力行: `[m11][p144] #1 arg1=0xc343f0 p-144=0x9078558948704d89 word[head]=0` (survey JSON の unit 895 の `err` 内、unit 896 の直前に出る)。
  - 2 回で同一。`p-144` の値は再現した。
- probe OFF (既定) を 2 回: 2 回とも `ok 869 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1`。
  - `[m11][p144]` 行は 0 件。
- survey の所要: 約 13 s (rc=0)。

### 12.2 §11.2 との差分

- §11.2 の probe OFF `ok 870 / oob 16` は、本 run の `edef8fa0` 再測定 (`ok 869 / oob 16`) と 1 件ずれる。§11.2 の数値は作業ツリー測定 (commit 未確定) で、今回の commit 済み HEAD と一致しない。
- §11.2 の probe ON `ok 872 / oob 14` も、本 run (`871 / 14`) と 1 件ずれる。
- 基準として使うのは本 §12 の commit 済み HEAD の値。§11.2 の数値は「未再現」として残す。
- `git diff 19b21178 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_882.md'` の出力は 0 byte ではない (56 files・3076 insertions 等)。§11.5 の「コード差分 0」は、この main 取り込みにより成立しなくなった。

### 12.3 解釈 (断定しない)

- `p-144` の 8 byte `89 4d 70 48 89 55 78 90` は、リトルエンディアンで x86 機械語 (`mov [rbp+0x70],ecx` / `mov [rbp+0x78],rdx` / `nop` に見える) として読める。`p-144` が本来のリスト先頭ではなく、コード領域を指している可能性は残る。
- 単独 (`SV_ONLY=895`) では `arg1=0`・`p-144=0` (§11.2 と同じ)。全体 survey と単独で状態が異なる点は未切り分け。
- `arg1` (`0xc343f0`) の caller 側の値は未確認。

### 12.4 受入条件

1. unit 95 `47ad70` の index / arg1: 未達 (現行 main で OOB 不発。観測対象が無い)。
2. unit 895 `40ff70` の `p-144`: 部分達成 (値は commit 済み HEAD で再現)。リスト先頭の出所・構造体の中身・`arg1` の caller 側は未特定。
3. DEFECTS 行案: 未達 (新規類型未確定)。

### 12.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `p-144` が機械語を指す原因 (壊れたリスト / 誤った `arg1`) | 受入条件 2 | #882 の次 run (`arg1` の caller 側) または #684 |
| §11.2 の作業ツリー測定値 (870/16・872/14) と本 §12 の commit 済み値 (869/16・871/14) の差 | 数値の基準 | #684 (PM 判断) |
| probe ON で分類が変わる (ok +2 / oob -2) | 計測 hook が survey を動かす | #684 (PM 判断) |
| `functions_dll.csv` 素材化 (`m11_e2e.sh` 全再生成) | e2e 全体の再現 | PM 判断 |
