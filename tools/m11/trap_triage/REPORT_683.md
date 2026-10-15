# #683: function_414ad0 の `[arg1]` deref 復元 — 4 unit (149/158/280/659) と #307 の 68 関数への波及

**判定: 受入条件 1 は未達** (4 unit のうち ok になるのは 158 のみで、merged HEAD では gate の ON/OFF で差が出ない。149/280/659 は oob のまま)。受入条件 2 は部分 (68 関数で「最初の trap が 414ad0 の OOB」は消えるが、verdict は全件 mismatch のまま)。受入条件 3 (ok→非 ok の退行 0) は survey 942 unit と 68 関数では達成、closure 7421 関数では未達 (match→非 match 7 件、§5 の旧測定)。**Closes しない (Refs #683)**。
**既定は OFF** (`M11_OV_414AD0=0`)。既定 OFF では main と同じ LStrSetLength 版が build され、main の build の挙動は変わらない (§2: gate=0 の `m11_ov.c` は main と同一のオブジェクトを生成)。
既知類型との関係 (`docs/DEFECTS.md`): **D4** (disp=0 の 1 段 deref 脱落) の再発。新規類型なし。
検証 HEAD = `a1ebdd31` (`origin/main` (`c5df4657`) を merge した commit。ブランチ独自の変更は `4d5a019e` から増えていない。merge で main 側の変更が入った)。main 取込前 (`4d5a019e`) の測定値は §3 末尾に旧値として残す。

## 1. 機械語と lift 後 IR の突合 (function_414ad0, VA 0x414ad0..0x414ba9)

- 機械語の `[rbx]` (rbx = 入口 rcx = `var s` のアドレス) の 1 段 deref は **4 箇所** (414af3 / 414b49 / 414b64 / 414b78)。
- 作業 IR (`work-m11` の `boot_final3.ll`) では `%arg1` を ptr とする load が **0 件**。`%arg1` を値のまま `icmp eq i64 %arg1, 0` / `add i64 %arg1, -N` に使い、`%arg2-4` を ptr として読む (414b6c の `load i32, ptr (%37-4)` がトラップ位置 0xbc575 = unit 149/158/280/659 の入口)。
- 機械語との同一入力突合 (C 版・IR 版・LStr 版): §9 を参照。
- IR はさらに機械語と違う点がある: 414b49 の `call 0x414850` の引数が `[rbx]` の新しい値ではなく **スタック slot のアドレス**、414b01 の早期 return の戻り値が機械語の rax (= `[rbx]` の値) ではなく arg1。転記では機械語どおりに写した。

## 2. 転記 (C 版) と IR 版 (機械語との突合は §9)

- **C 版**: `tools/m11/m11_ov.c` の `function_414ad0`。gate は `-DM11_OV_414AD0` (既定 **0**)。`origin/main` に対して追加 36 行・削除 0 行 (`git diff origin/main HEAD -- tools/m11/m11_ov.c`)。
  - `M11_OV_414AD0=1`: UStrSetLength 版 (`#if` 側。機械語 414ad0..414ba9 の分岐を写した転記。deref 復元あり)。
  - `M11_OV_414AD0=0` (既定): LStrSetLength 版 (`#else` 側。main の #134 版と同じ本体)。
  - **gate=0 と main の同一性**: `origin/main` の `m11_ov.c` と本 HEAD の `m11_ov.c` を同名 (`m11_ov.c`) の別ディレクトリで `emcc -c -O0 -g0 -DM11_OV_414AD0=0` でコンパイルし、オブジェクトを `cmp` で比較 → 一致 (rc=0 / 0 バイト差)。
  - **注意**: 両版とも C で `function_414ad0` を定義するため、gate の切替は「C 転記 (UStr 版) ↔ main と同じ C 版 (LStr 版)」の切替であり、「転記あり ↔ IR 版」の切替ではない。IR 版 (`ir414_fix.py`) は liftdiff の A/B (§4・§5) でのみ使う。
  - `m11_build.sh` は `work/ov_414ad0.stamp` で `ov.o` だけ切り替える (`emcc -c` に `-DM11_OV_414AD0` を渡す)。gate 1 と 0 で `ov.o` の md5 が異なることを確認済み (`1555187c…` = gate0 / `3d968dfb…` = gate1、`-g1` のビルド)。
- **IR 版** (`trap_triage/ir414_fix.py`): C 版と同じ分岐・同じ deref 復元を LLVM IR で書いたもの。liftdiff は C 上書きを取り込まないため、68 関数の batch はこちらを使う。`--none` は無変更の複写 (A 側・ネガコン)。

## 3. m11 survey (942 unit): gate OFF (既定) / ON

`bash trap_triage/neg_683.sh` (ON/OFF を順に build + `survey_units.mjs` + `survey_diff.py`)。素材 `work-m11` は #516/#680 以前の生成物で `ir_conditions.json` が無く、そのままでは build が fail-closed で止まる。そこで `m11_gen_ir2.sh` で同じ `boot*.lift.ll` から IR を作り直した (`ldfix=applied`)。

- 実行: HEAD `a1ebdd31` (main 取込後)。`m11_gen_ir2.sh` で IR を再生成 (34.8 s、`ldfix=applied`、`ir_sha256` 995351f5…、`boot_final.ll` 490711 行) の後に `neg_683.sh` を 3 回、**1 回ずつ順に**実行 (並列実行は `work/` を共有するため不可。誤って同時起動した 2 回は、1 回が rc=1 で失敗し、もう 1 回も結果を信用できないため破棄して、順次再実行した)。
- 各回で ON build → survey → OFF build → survey の順。`neg_683.sh` は PE・capstone・pefile の存在を事前確認し、各 build 後に `ir_conditions.json` の `qstore=applied` を確認する (欠けたら exit 1)。build log は `[m11build] OK`。
- 所要 (測定 1 の実測。load は各段階終了時の 1 分値): 全体 56.4 s (ON build 20.2 s / survey 9.9 s (load 0.81) / OFF build 16.4 s / survey 9.9 s (load 0.89))。測定 2・3 は所要を記録していない (rc=0 と結果の一致のみ確認)。

| 構成 | ok | oob | halt0 | miss | noproc | trap | 計 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OFF (既定, gate=0) n=3 | 869 | 17 | 8 | 47 | 1 | 25 | 942 |
| ON (gate=1) n=3 | 869 | 17 | 8 | 47 | 1 | 25 | 942 |

- **本 PR の環境で n=3 の min = max**: 測定 1〜3 は全件一致。本測定では OFF = ON (差 0)。ただし独立測定 (`d8075de` 上) では OFF = ok 828 / oob 13 / halt0 54、ON = ok 828 / oob 10 / halt0 57 で、本測定 (828/11/55 の OFF = ON) と食い違う。原因は未確認 (下記 61 行目)。
- **`survey_diff.py` の全出力** (測定 3。測定 1〜3 とも同一):

```
A: {'halt0': 8, 'miss': 47, 'noproc': 1, 'ok': 869, 'oob': 17}  trap=25
B: {'halt0': 8, 'miss': 47, 'noproc': 1, 'ok': 869, 'oob': 17}  trap=25
遷移 (A -> B):
  halt0   -> halt0   8
  miss    -> miss    47
  noproc  -> noproc  1
  ok      -> ok      869
  oob     -> oob     17
ok 退行 unit: 0 []
kind 以外も含めた差分 unit (frames は深さのみ比較): 0 []
icall sites の総数 [ok, miss] 差 (A -> B): 0 件 
icall targets の総数 [ok, miss] 差 (A -> B): 0 件 
off  units 149/158/280/659: [(149, 'oob'), (158, 'ok'), (280, 'oob'), (659, 'oob')]
on   units 149/158/280/659: [(149, 'oob'), (158, 'ok'), (280, 'oob'), (659, 'oob')]
```

- **遷移 (OFF → ON)**: 942 unit 全件で kind 不変。frames の深さの変化も 0。icall sites / targets の [ok, miss] 差も 0。
- **4 対象 unit (merged HEAD)**: 158 は OFF = ON = ok (main 取込で ok になった。原因は未確認。gate の効果ではない)。149 は OFF = ON = oob (最上位 frame `412e40 ← 653660 ← 6539e0`)。280・659 は OFF = ON = oob (最上位 frame `6cefb0 ← 815050 ← 815e10`)。**受入条件 1 (4 unit すべて ok) は未達** (3 unit が oob のまま)。
- **旧値 (main 取込前 `4d5a019e`、同じ手順で n=3)**: OFF = ON = ok 828 / oob 11 / halt0 55 / miss 47 / noproc 1。このときは 149 = oob、158/280/659 = halt0。main 取込後は ok 869 / oob 17 / halt0 8 で、158 は halt0→ok、280/659 は halt0→oob に変わった (件数の全量は未集計)。前版の「ok +9」「副作用 58-63・307・311・917・56」「149 の最上位が 414c70」は再現しない (`50fed21d`・`fe662e88` の測定でも同じ)。
- **旧 818/21 の出所**: REPORT.md §8.2 の (a)「スナップショット (旧生成物)」の値。(c)「再生成 IR」を採用基準とする (REPORT.md §8.2 (e))。本 REPORT は (c) を基準とする。
- **独立測定との差 (未確認)**: 独立再実行 (`d8075de` 上、PE・capstone・pefile あり) では OFF = ok 828 / oob 13 / halt0 54 / miss 46、ON = ok 828 / oob 10 / halt0 57 / miss 46 となった。本 REPORT の旧値 (828/11/55/47) とも一致しない。原因は未確認 (IR の生成条件か、build 時の qstore の有無のいずれかと推定。`d8075de` 時点の build log は本 run では再現していない)。

ネガコン: 上記 gate OFF/ON の切替で結果は変わらない。したがって本 gate は survey 上では効果を持たない (C 版 UStr 版と LStr 版が survey で同一の結果)。

## 4. liftdiff: #307 の 68 関数への波及 (A/B、同一ハーネス)

- **定義** (`tests/oob_414ad0.py` と同じ): batch の関数のうち「最初の `wasm_trap` case の wasm_detail が `memory access out of bounds @ ld_wasm.wasm.function_414ad0` で始まる」関数。基準 jsonl `tools/liftdiff/work/m11/batch_closure.jsonl` (7421 行) で **68**。
- **A** = IR 無変更の複写 (`m11_414base`)、**B** = `ir414_fix.py` で修復した IR (`m11_414fix`)。68 関数を `--set file:` で指定、`--shards 4 --state auto`。
- **実行手順**: `liftdiff68_683.sh` を end-to-end で実行 (HEAD `a1ebdd31`、`FL_WIN64_DIR` = fl-win64 展開先、`PY` = python3 + capstone/pefile/numpy)。3 回実行し、いずれも rc=0 で同一の要約行 (所要は merged HEAD では未計測。main 取込前 `4d5a019e` の 3 回は 34.2 s / 33.4 s / 33.5 s)。`cp` の同一ファイル問題 (`[ "$src" = "$dst" ] || cp`) は修正済みで、停止しないことを確認した。
- 測定 1〜3 の要約 (`cmp68_683.py` 出力): A の oob414 = **59**、B の oob414 = **0**、verdict は A・B とも mismatch 68 / match 0。3 回とも同一。

| 指標 (68 関数、n=3 で同一) | A (IR 無変更) | B (414ad0 修復) |
|---|--:|--:|
| 最初の wasm_trap が 414ad0 の OOB | **59** | **0** |
| verdict = match | 0 | 0 |
| verdict = mismatch | 68 | 68 |

- 遷移 (cmp68_683.py): oob414→other・verdict mismatch→mismatch が **59**、other→other・verdict mismatch→mismatch が **9**。**match → 非 match の退行は 0** (A で match は 0 件のため自明)。
- B (68 関数) の最初の wasm_trap の内訳 (batch jsonl からの集計): 上記 `cmp68_683.py` の関数別表を参照 (`4133f0` 等が多い)。A の内訳は `414ad0` 59・`408040` 7・`4133f0` 1・trap なし 1。
- **414ad0 の修復で消えた OOB は、別の関数の OOB (`4133f0 < 414c70`、`412e40 < 652750` 等) に置き換わった**。その原因 (deref 脱落の有無) は未確認。68 関数はいずれも verdict が mismatch のまま。
- 旧記述の A = 67 は再現しない (`956d2ed` 時点の値は別の実行状態だった可能性があるが未確認)。A/B の比較は同一ハーネス・同一実行内に限って読む。

## 5. closure 全体 (7421 関数) の A/B (14 shard、同一ハーネス) — **旧測定 (`0113c86`)、本 REPORT の再測定の対象外**

A = IR 無変更 (`m11_414base`、`batch_414base_closure.jsonl`)、B = 修復 IR (`m11_414fix`、`batch_414fix_closure.jsonl`)。両方 `--set closure --shards 14 --state auto`。所要 A 779 s / B 796 s (B は A と非並行、A は m11 survey と並行していた時間を含む)。突合 = `cmp68_683.py` (全 VA)。

| 指標 (7421 関数) | A (IR 無変更) | B (414ad0 修復) |
|---|--:|--:|
| 最初の wasm_trap が 414ad0 の OOB | 63 | **0** |
| verdict = match | 3125 | 3127 (+2) |
| verdict = mismatch | 2135 | 2133 |
| verdict = unexec | 2161 | 2161 |

- 遷移 (A → B): match→match 3118 / **match→mismatch 7** / mismatch→match 9 / mismatch→mismatch 2063 / unexec→unexec 2161 / OOB414→other 63。
- **match → 非 match の 7 件**: 0x5af280 (ret_only)、0x50d920 (ret_only)、0x44b090 (callee_divergence、heap 書込み差)、0x79d920 (spill_slot_deref + callee_divergence)、0x663d80 (memory_semantics)、0x699ca0 (simd_helper + wasm_trap)、0x4447d0 (wasm_trap)。いずれも 414ad0 を直接呼ぶ関数ではない。heap 配置の変化など間接経路と推定 (**未確認**)。
- **単独 batch での再現 (本 run、旧 IR 基準の 7 件のみ)**: 上記 7 件を shards 4 で A/B 実行すると 7 件とも A・B で match のまま。14 shard の closure でのみ出ており、harness の状態依存の可能性が高い (**未確認**)。
- **受入条件 3 (退行 0) は closure 全体では未達** (7 件)。68 関数の subset では 0。
- 注意: 既存の `batch_closure.jsonl` (別の実行時) を基準にすると match→非 match が 106 件と出る。同一 harness の A (上表) では 7 件。差 99 件は harness 状態 (§4 と同根と推定) であり、退行の数え方は同一 harness の A を基準にする。
- **本 REPORT の再測定の範囲外**: §5 の closure は merged HEAD で再実行していない (14 shard で約 13 分。main 取込後の IR では base が変わっているため、§5 の数値は merged HEAD の値ではない)。

## 5.1 kind 以外の差分 unit

merged HEAD `a1ebdd31` の survey 942 unit では、kind は ON/OFF で全件一致 (§3)。`survey_diff.py` の「kind 以外も含めた差分」も 3 回とも 0 件。前版 (`956d2ed` 確認) で出ていた unit 235・888 の差分は、merged HEAD では再現しない。前版の IR 生成条件は再現していない (原因は未確認)。

## 6. 再現手順 (1 コマンド)

```sh
# m11 survey (ON/OFF。work-m11 展開済み、IR は m11_gen_ir2.sh で再生成、emsdk は m11_build.sh が source)
bash tools/m11/trap_triage/neg_683.sh
# liftdiff 68 関数 A/B (work-m11 + work-liftdiff 展開済み、PY は capstone + pefile + numpy 入り python)
FL_WIN64_DIR=... PY=... bash tools/m11/trap_triage/liftdiff68_683.sh
```

ネガコン: `liftdiff68_683.sh` の A (`--none`、IR 無変更)。survey の 0/1 比較は gate の両版比較であり、IR 版の無変更比較ではない (§2)。

## 7. 検証範囲 / 範囲外

- 範囲内 (merged HEAD `a1ebdd31`): m11 survey 942 unit (ON/OFF 各 n=3)、liftdiff 68 関数 (A/B 各 n=3、end-to-end 実行)。gate=0 と main のオブジェクト同一性 (§2)。
- **n の限界**: 上記は n=3 で全件一致 (min = max)。ただし同一素材・同一マシン上の反復であり、別マシン・別負荷での再現は未確認。独立測定 (`d8075de`) では §3 の差が出ており、その原因は未確認。
- 範囲外: closure 7421 関数の再測定 (§5 は旧測定値)、`m11_e2e.sh` 全体 (stage4 / bit-exact) への影響 (未実施)、C 版と IR 版の相互検算は §9 で実施 (機械語との突合)、副作用の原因 (旧 PR 記述の再現が無いため対象外)。
- 既存 REPORT の数値 (`818 / 21` 等) は旧生成物 (a) の値で、本 gate の有無とは無関係。他 REPORT の書換えは行わない。

## 9. C 版・IR 版の機械語突合 (#764)

- **対象**: function_414ad0 (VA 0x414ad0..0x414ba9, 218 byte)。oracle = PE の実バイト列を unicorn (2.1.4) で実行 (`xcheck414.py`)。callee (412d60 / 409470 / 414850 / 412c20 / 409c80 / 40f560) は Python スタブで置換し、C 側 (`xcheck414_harness.c`) と同じ仕様。
- **入力**: 5000 case (seed 0x764)。var 引数 s の内容 (ヘッダ refcnt・length・ポインタ値を乱数化)、n ∈ {-2..100}。fault (oob 相当) 1131 / 非 fault 3869。
- **実行**: `FL_WIN64_DIR=… tools/m11/trap_triage/xcheck414.py 5000` (実測 46.5 s、load 0.65 / 0.29 / 0.15 の 1 分値)。rc=0。
- **結果 (機械語との差 = fault・ret・arena の fnv1a64・bump 全一致で判定)**:

| 版 | 差 / 5000 |
|---|--:|
| C 版 (`m11_ov.c` の `#if M11_OV_414AD0`、UStr 版) | **0** |
| IR 版 (`ir414_fix.py`) | **0** |
| LStr 版 (`#else`、既定 OFF・main と同じ本体、負の対照) | 2900 |

- **読み**: C 版と IR 版は、この突合の範囲 (分岐・deref・戻り値・arena 副作用) で機械語と一致する。LStr 版は機械語と異なるので、既定 OFF の版は本件の転記とは別物であり、試験は差を検出できている。
- **限界**: callee は stub。stub の値 (412c20 が読む flags 語 G_WORD=2、409470 の確保規則) は実 PE の値を検証していない。機械語側の実 callee を使う突合ではない。`mc` と `C`/`IR` が同じ stub を使うため、stub 自体の誤りは検出できない。
- 成果物 (`tools/m11/work/xcheck414/`) は gitignore 対象。生成は `FL_WIN64_DIR` と `pyvenv (capstone/pefile/numpy/unicorn)` が要る。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 149 の最上位 frame (`412e40 ← 653660 ← 6539e0`) の原因 | 4 対象 unit のうち 149 が oob のまま | #307 の次候補 (起票は PM) |
| 280・659 の最上位 frame (`6cefb0 ← 815050 ← 815e10`) の原因 | 4 対象 unit のうち 2 unit が oob のまま | #683 の継続 (本 PR は Refs) |
| 158 が ok になった原因 (main 取込による) | 受入条件 1 の 1/4 を満たす理由が未確認 | #683 の継続 |
| liftdiff 68 の次の trap (`4133f0` / `412e40` 経由の OOB 等) | 68 関数が verdict match に届かない | #307 |
| closure の match→非 match 7 件 (0x5af280 / 0x50d920 / 0x44b090 / 0x79d920 / 0x663d80 / 0x699ca0 / 0x4447d0) の原因・merged HEAD での再測 | 受入条件 3 (退行 0) が closure 全体で未達 | #307 |
| 独立測定 (`d8075de`) の OFF 13/10 と本測定の差 | survey 数値の再現性 | #680 (IR 生成条件で OFF が 818/21 ↔ 828/13 と変わる件。既存) |
| liftdiff batch の再現性 (A 67 と closure 68 の差) | A/B の読み方 | #307 (harness 件) |
| (解消) C 版 (m11_ov.c) と IR 版 (ir414_fix.py) の相互検算 | — | #764 で実施。§9 (5000 case で C 版・IR 版とも機械語と差 0) |
| gate ON が survey で効果を持たない理由 (C 版の 2 版が同じ結果) | 本 gate の存在意義 | #683 の継続 |
| `work-m11` が #516/#680 以前の生成物で `ir_conditions.json` 無し (そのままでは build 不可) | 素材の更新 | #729 (survey 測定基準の残課題。work-m11 の R2 再投入を含む) |
| 280・659 の `6cefb0` 内 OOB (第 3 引数の修復 `fix_r8b815050` 後も残る。§8.1) | 4 対象 unit のうち 2 unit が oob のまま。因果仮説 (引数の ptr 化が原因) は 280/659 で否定 | #3444 |

### 8.1 #878: 815e10 系 (6cefb0 ← 815050 ← 815e10) の突合と分類

- **対象**: unit 280 / 659 の最上位 frame `6cefb0`。上流 `815050` (呼出元 `815e10`)。
- **出所**: 以下の機械語・IR の観測は、PR #1243 の作成時 (初版 `de8c9889` 時点) のもの。展開元 run ID は未記録。本 review run の `$ARTIFACTS_DIR` には `work-m11` が無く、`fl-win64` も展開していないため、この run では再検証していない。
- **機械語側 (作成時の観測)**: `815e10` → `815050` の引数対応 (`ebx→ecx` / `esi→edx` / `edi→r8d`) は一致。`815050` の `8158f5: mov r8b, 1` (即値 1) → `8158f8: call 6cefb0`。`815050` 内の `call 6cefb0` は 1 箇所のみ。`6cefb0` の `6cf021: cmp byte ptr [rcx+0x496], r8b` / `6cf028: jg`。
- **IR 側の突合 (作成時の観測。`work-m11` の `boot_final.ll` 490653 行を読んだもの)**:
  - `815050` (定義 315047 行) の 315539 行: `%251 = call i64 @function_6cefb0(i64 %250, i64 %250, ptr nonnull %stack_var_-255)`。第 3 引数は機械語の即値 `r8b = 1` ではなく、`815050` の `alloca` (315076 行) の slot アドレス。
  - その slot `%stack_var_-255` は `alloca` 宣言のみで、`815050` 内に store / load が無い (未初期化の slot のアドレスが渡る)。
  - `6cefb0` (270434 行) は第 3 引数を `%0 = ptrtoint %arg3` して `icmp slt i64 %0, %29` (`%29` = `[arg+0x496]` の sext byte) と比較する。よって機械語の `cmp byte ptr [rcx+0x496], r8b` (即値 1) と、IR のアドレス比較が一致しない。
  - `815050` 内の `6cefb0` 呼出は 315539 行の 1 箇所のみ。`815050` の呼出元は 315807 行の `815e10` 1 箇所。
- **分類 (暫定)**: 機械語の即値 1 が IR で slot のアドレスに変わっている。観測から見ると deref 脱落とは見えにくい (定数の ptr 化に見える)。ただし置換を行った pass は未特定 (`m11_passes.py` / `ldfix/ldfix.py` / `alloca/m11_alloca.py` を grep したが該当箇所は確定していない)。因果 (この差で 6cefb0 の OOB が起きる) も未検証。よって「ldfix 型ではない」とは断定しない。
- **注意**: 上記は `work-m11` 素材 (#516/#680 以前の生成物) の IR に対する作成時の観測。現 main の生成手順で再生成した IR では置換の有無が変わりうる (#729)。
- **素材の注意**: 読んだ IR は `work-m11` の `boot_final.ll` (#516/#680 以前の生成物、`ir_conditions.json` 無し、#729)。現 main の生成手順で再生成した IR では行番号・有無が変わる可能性がある。本 review run では `work-m11` が無いため、IR 側の再確認は未実施。
- **未確認**: 定数 1 がスタック slot のアドレスに置き換わった pass・関数は未特定 (置換の段は RetDec 段と観測済み。下記「経路の段の特定」)。`6cefb0` の OOB がこの分岐差から来るという因果も未検証。
- **影響**: 修復の範囲 (ldfix 型か否か) は暫定でも判定しない (pass 未特定・因果未検証)。survey 再測定と退行確認は、修復を入れたときに行う。本 run では修復を入れていない (受入条件 2 は対象外)。
- **起票**: 残り (型推定で byte 値が ptr 化される欠陥の特定と修復、280/659 の ok 化) は子 issue に分割する。
- **経路の段の特定 (#1081)**: 置換が起きた段を RetDec 段と観測した。pass・関数の特定は未完 (#1293 へ)。
  - 観測の出所: 素材 `work-m11` (#516/#680 以前の生成物。生成 commit は未特定) の `boot1.lift.ll` と、その上流の RetDec 出力 `boot1.drc.ll` / `boot1.drc.c`。**この run では素材が無く再確認していない** (作成時の観測の記録)。
  - 機械語 (PE `block00031_PE.bin`): `815050` の `8158f5: mov r8b, 1` → `8158f8: call 6cefb0`。`6cefb0` は `6cf021: cmp byte ptr [rcx+0x496], r8b` で第 3 引数を比較に使う。
  - `boot1.drc.c` では `int64_t v69; // bp-255` → `function_6cefb0(v68, v68, &v69)`。`boot1.drc.ll` 126348 行でも `i64* nonnull %stack_var_-255`。よって `drc` (RetDec 出力) の段で既に alloca アドレスが第 3 引数に入っている。
  - 段の根拠: `tools/m11/m11_lift.sh` は `RetDec → drc.ll → m2/ir_normalize.py → m5/ir5_patch.py → lift.ll` の順。`tools/m2/*.py` には alloca / inttoptr を扱う処理が無い (grep 済み)。`ir5_patch.py` の `patch_uninit_alloca` (L286-311) は未初期化 alloca からの **load** を 0 (`xor` / `inttoptr i64 0 to ptr`) に置換する処理で、store は補完しない。今回の call 引数 (alloca アドレス自体) は load ではないため、この関数は触れない。`ir5_patch.py` には他に `lift_residual_constexpr` / `lower_asm_store` / `xmm_arg_inject` / `redirect_calls` 等もあり、ir5 段全体で値を ptr 化しないとは言えない (L495-514 は iN→ptr を inttoptr 命令化する)。ir5 段が原因かは未判定。
  - 仮説 (未検証): RetDec の型推定が `r8b` 即値の引数を `int64_t*` として扱い、slot アドレスに置換した。
  - 鮮度: 素材の生成 commit は未特定。`git diff c4e93550 HEAD -- tools/m2 tools/m5 tools/m11` は本 PR で REPORT_683.md の 6 行のみだが、素材の生成 commit から HEAD までの差分は未確認 (lift 系の変更で行番号・有無が変わり得る。#729)。鮮度は未確定。
  - 再現手順 (未実行。作成時に実際に使ったコマンドは記録していない。素材が揃えば次の形で再確認できる): capstone で PE の `0x815050` / `0x6cefb0` を逆アセンブルし、`work/boot1.drc.ll` と `work/boot1.drc.c` に対して `grep -n "stack_var_-255\|function_6cefb0" work/boot1.drc.ll` / `grep -n "bp-255\|function_6cefb0" work/boot1.drc.c` を実行する。
  - 未完 (起票先): 因果 (この差が 6cefb0 の OOB の原因か)・置換を行った pass・修復・survey 再測定と退行確認は #1293 (`[M11-N80]`)。
- **再確認 (#1293 run、素材 `work-m11` = #516/#680 以前の生成物、HEAD `604e900f`)**: 上記の段の観測は同じ素材で再現した。
  - 機械語 (`boot1.drc.dsm`): `0x8158f5: 41 b0 01` (`mov r8b, 1`) → `0x8158f8: call 0x6cefb0`。
  - RetDec 出力 (`boot1.drc.c` 63944-63945): `int64_t v69; // bp-255, 0x815050` → `function_6cefb0(v68, v68, &v69)`。`boot1.drc.ll` 126348 行でも `i64* nonnull %stack_var_-255`。
  - callee (`boot1.drc.c` 41206 ff.): 第 3 引数は `(int64_t)a3` と `(char)v1` としてのみ使われ、ポインタとしては読まれない。よって ptr 化は誤りと読める。
  - `boot_final3.ll` (現 IR 系) でも 318822 行に `ptr nonnull %stack_var_-255` が残る。
  - 未確認のまま: 即値 1 を alloca に置き換えた pass・段 (RetDec の型推定か後段か)、修復、survey 942 unit の再測定、因果。これらは子 issue `[M11-N93]` に分割して起票する。
- **再確認 (#1448 run、HEAD `cb3a89a6`、素材 `work-m11` = #516/#680 以前の生成物、`ir_conditions.json` 無し)**:
  - 機械語 (`boot1.drc.dsm`): `0x8158f5: 41 b0 01` (`mov r8b, 1`) → `0x8158f8: call 0x6cefb0`。
  - RetDec 出力 (`boot1.drc.c` 63944-63945): `int64_t v69; // bp-255` → `function_6cefb0(v68, v68, &v69)`。`boot1.drc.ll` 126348 行: `call i64 @function_6cefb0(i64 %250, i64 %250, i64* nonnull %stack_var_-255)`。
  - 後段 (`m11_gen_ir2.sh` の lift 段): `boot1.lift.ll` 118467 行も同じ `ptr nonnull %stack_var_-255`。`m2/ir_normalize.py` と `m5/ir5_patch.py` の該当 call 引数は変えていない (lift 段でも既に alloca)。よって置換は RetDec 段 (`drc`) までに起きていると読め (RetDec 内の pass は未特定)、`m2`/`m5` は除外する。
  - 同じ callee の他 2 call (`0x8208e1` / `0x826406`) は `NULL` を渡す (`drc.ll` 129687 / 134183)。`0x8158f8` だけが alloca アドレスになる。
  - 未確認のまま: RetDec 内のどの型推定 (引数型の推定か、`r8b` の型付けか) が置換を行ったか。修復と 942 unit survey 再測定、因果。これらは親 #1293 (`[M11-N80]`) で扱う (#1081・#878 とも同じ chain を追跡中のため、本 run では新規 issue を起票しない)。
- **修復と survey (#1448、測定 commit `5c43ea98a`)**:
  - **修復**: `tools/m11/ldfix/fix_r8b815050.py` (`m11_gen_ir2.sh` の ldfix 後段。既定 ON、`M11_FIX_R8B=0` で外す)。`function_815050` の `call @function_6cefb0(i64 %250, i64 %250, ptr nonnull %stack_var_-255)` の第 3 引数を `ptr inttoptr (i64 1 to ptr)` に置換する。機械語の前提 (`8158f5: mov r8b,1`・`8158f8: call 0x6cefb0`・`6cf021: cmp byte ptr [rcx+0x496], r8b`) を capstone で検査し、IR の想定外は assert で止める。
  - **根拠 (機械語)**: `r8` は `81550a: lea r8,[rbp+0x1c8]` の後に call (`4255d0` ほか) が挟まり、`8158f5` の直前では呼出しで壊れた値になる (Win64 の揮発性レジスタ)。`6cefb0` は第 3 引数を IR で `icmp slt i64 %0, %29` と `trunc i64 %0 to i8` (`%0 = ptrtoint %arg3`) にしか使わず、機械語も `cmp byte ptr [rcx+0x496], r8b` (8bit 比較) だけ。よって値 1 は機械語の振る舞いと一致する。RetDec 段のどの pass が alloca に置換したかは**未特定** (推定のみ)。
  - **測定**: `bash tools/m11/trap_triage/neg_1448.sh` (修復 ON / OFF で IR を `m11_gen_ir2.sh` から作り直し、build、942 unit survey)。素材 `work-m11` は再生成 IR (`ldfix=applied`・`ld108=applied`)。gen+build 49 s / survey 7 s / load 0.8 前後。同じ commit で 2 回測定し、結果は一致した (作業ツリー版と `5c43ea98a` で同一)。

| 構成 (942 unit) | ok | oob | halt0 | miss | noproc | trap |
|---|--:|--:|--:|--:|--:|--:|
| OFF (修復なし, A) | 873 | 14 | 7 | 47 | 1 | 21 |
| ON (修復あり, B, 既定) | 873 | 14 | 7 | 47 | 1 | 21 |

  - **遷移 (A → B)**: 942 unit の kind は全件不変。**ok 退行 0**。icall sites / targets の差 0。
  - **4 対象 unit**: 149 = oob / 158 = ok / 280 = oob / 659 = oob (OFF = ON)。
  - **kind 以外の差分 7 unit** (`survey_diff.py`): 280・659 は ON で `va_mb` の項目が出ない (OFF は 120.8 / 21.3 MB)。trap の `msg` は両方とも "memory access out of bounds" で、最上位 frame は `function_6cefb0 ← 815050 ← 815e10` のまま。291・296・302・304・888 は ok のままで、`[m11][VA-big]` の記録上の live 量が ON で約 64 MB (888 は約 85 MB) 少ない。
  - **結論**: 修復は機械語の値と一致し、kind の退行は 0。しかし 280・659 の `6cefb0` 内 OOB は修復の有無で変わらない。よって「第 3 引数の ptr 化が 6cefb0 の OOB の原因」という因果仮説は 280・659 では成立しない。真因は子 #3444 (6cefb0 内で最初に起きる OOB の場所と、第 1・第 2 引数 (size) の出どころ)。
  - **鮮度**: 測定 commit `5c43ea98a` から HEAD までのコード差分 `git diff 5c43ea98a HEAD -- tools/m11/ldfix tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/trap_triage/neg_1448.sh` の出力は 0 行 (本 REPORT の追記だけが後の変更)。
  - **main 取り込み後 (merge `6b5774526`)**: 上の鮮度の差分は main 側の変更で 0 行でなくなった (`git diff 5c43ea98a HEAD -- ...` は 437 行、8 files、242+/39-。内訳は main 側の ld115 (#2447・#2527) の変更と `m11_build.sh` の競合解消)。上の表は `5c43ea98a` の値で、取り込み後の HEAD では**未再測定** (素材 `work-m11`・`toolchain-emsdk` が本 run に無く、emsdk の実体も無い)。
  - **取り込み後の build gate (本 run、HEAD `6b5774526`)**: `m11_build.sh` の gate 部分だけを一時コピーで検査した (emsdk の参照先のみ差替え。リポジトリは未変更)。ir_conditions.json の組合せ 6 通り: S1 全 applied → gate 通過 (後段の指紋検査で停止)。S2 r8b 記録無し → 拒否。S3 ld115 記録無し → 拒否。S4 r8b=disabled (ALLOW 無し) → 拒否。S5 r8b=disabled + `M11_ALLOW_R8B_DISABLED=1` → WARNING で続行。S6 ld115=disabled (ALLOW 無し) → 拒否。r8b と ld115 の 2 つの検査が独立に効くことを確認。

