# REPORT_APPENDIX_2521 — #2521 の詳細 (REPORT_2408 §8.1〜§8.4)

> **正本**: `tools/m11/trap_triage/REPORT_2408.md` §8.0 (結論)。本付録は §8.1〜§8.4 (実測表・trap 経路・未解決・既定変更の到達先)。REPORT_2408.md の 250 行上限のため分割移動した (内容は削除していない)。

### 8.1 実測 (測定 commit `d80e9909f`。素材・環境は §1 と同じ。直列 1 本、load average は uptime の 1 分値 1.04 (基準 OFF の直後))

| 条件 | 環境変数 (`M11_FIX_50A830` / `M11_FIX_535BF2`) | e2e rc | wall | survey ok / trap / miss | 基準 (origin/main OFF) との unit 差 |
|---|---|---|---|---|---|
| 既定 (`d80e9909f`) | 未指定 (既定 `0` / `1`) | 1 | 1m11.5s | 873 / 22 / 46 | 0 |
| `M11_FIX_50A830=1` (`d80e9909f`) | `1` / 未指定 (既定 `1`) | 1 | 1m10.3s | 872 / 23 / 46 | 1 (144 ok → oob。304・555 は OFF と同じ oob) |
| 基準 OFF (`44a7f4465`、変更前) | 未指定 (既定 `0` / `0`) | 1 | 3m13s (初回の build を含む) | 873 / 22 / 46 | — |
| ON + `M11_FIX_535BF2=0` (変更前の既定、`44a7f4465`) | `1` / `0` | 1 | 1m11s | 872 / 23 / 46 | 3 (144 ok → oob、304・555 oob → Aborted) = 変更前の abort を再現 (ネガコン) |
| OFF + `M11_FIX_535BF2=1` (`44a7f4465` + フラグ) | `0` / `1` | 1 | 1m12s | 873 / 22 / 46 | 0 (535BF2 は OFF 経路の分類を変えない) |

再現: `cd tools/m11 && FL_WIN64_DIR=<展開先> [M11_FIX_50A830=… M11_FIX_535BF2=…] bash m11_e2e.sh`。unit 別の突合は `M11_SURVEY_DETAIL=<path>` を付ける。

- e2e rc=1 の内訳 (既定・ON 共通): (a) tolerant gate `通常起動の完了数 101 != 期待 56` (units_run_full 98 + skipped)、(b) `survey ok=873 != 期待 872` (OFF)、(c) ptrcheck survey `image_va_words_new 71005 > M11_EXPECT_PTR_SURVEY_NEW_MAX 71001`。期待値は変更していない (e2e_expect.env・m11_tolerant_gate.py)。
- 根拠ログ (M6): 原本 (`work/e2e_full.out`・`work/e2e_survey.out`・`work/judge.out`) は `tools/m11/work/` (gitignore) にあり repo に残らない。本 run は素材 `work-m11` が無く再採取できなかった。上の (a)〜(c) は作成者 run の値。出力形式はコードで確認済み: (a) `m11_tolerant_gate.py:46` `通常起動の完了数 %s != 期待 %d (strict の挙動が変わった)`、(b) `:51` `survey ok=%s != 期待 %d (survey の数値が変わった)`、(c) `m11_survey.mjs:161` `FAIL: survey ptrcheck image_va_words_new=%s > max=%s (%s)`。次の run で原本を採取して本節へ貼る (未解決表)。
- IR sha256 は `17a98d6e…` (`ir_conditions.json`)。§1 の `6909f85d…` と異なる。環境差か drift かは未切り分け。

### 8.2 unit 144 の trap 経路 (ON・`M11_SURVEY_STACK=144 node m11_survey.mjs`)

wasm スタック (内側→外側、`m11_wasmnames.py` で名前化): `function_407e20` (wasm 1877) ← `function_409440` ← `function_412d60` ← `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_414c70` ← `function_43c4c0` ← `function_653660` ← `function_6539e0` ← `function_653f40` ← `function_65c540` (unit 144 の本体)

- `407e20` は IR 先頭で `arg1 - 8` のヘッダを読み、trap はこの読み出しで起きる。`409440` は `arg1 ≠ 0` を確かめてから `407e20` を呼ぶ。つまり解放される値は nil ではなく、範囲外の非 0 値である (推定。値は未採取)。
- `412d60` は参照解放 (管理フィールドの減算と 0 判定) の形。`43c4c0` の呼出し先の一部 (`413760`) は `412d60` に至る。推定: Grow 後の list 関連の状態のうち、後の解放経路で参照される値が不正になっている。**未検証**。
- 照合済み (引数の取り違えは否定): `50ade0` の C 転記 (`m11_ov.c`) は機械語 (`50ade0` 78 B) と一致する。`417fc0` の IR シグネチャは `(ptr, ptr, i64, i64)` で、C 側の `(&FItems, ti, 1, newcap)` と一致する。

### 8.3 未解決 (次の一手: `407e20` に渡る arg1 を ON/OFF で採取し、FItems・Count・Capacity のどれかを判定する)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 144 の回帰の原因と修正 (受入 1・2・4) | 既定 ON (`M11_FIX_50A830`) 不可 | #3482 (#2521 の残り。本 PR で issue の範囲を縮めた) |
| e2e の期待値と実測の不一致 (8.1 の (a)〜(c)) と原本ログの採取 | e2e が既定でも rc=1 | PM 判断 (issue コメント) |
| 既定 ON の可否 (`M11_FIX_535BF2`。既定案: ON。survey は OFF と 0 差分) | 本 PR の既定変更を採るか | PM 判断 (`tools/m11/trap_triage/REPORT_1275.md` 52 行目の「既定 ON 化は PM 判断」への回答) |
| origin/main (`cf9dce6fe`。`44a7f4465` より後) は `tools/m11` に 20 ファイルの差分があり、本 PR は取り込んでいない。main 上の survey は未測定 | merge 後の既定の挙動 | PM 判断 (merge 後の再測定の要否) |
| `tools/m11/alloca/e2e.sh` の既定変更の影響 (既定の `m11_build.sh` を使う) | 未測定。影響の有無は未確認 (素材 `work-m11`・toolchain が本 run に無い) | 未解決 (次の run で `oc_artifacts` を付けて実行) |
| IR sha256 の差 (`17a98d6e…` と §1 の `6909f85d…`) | 基準の再現性 | PM 判断 |

### 8.4 既定変更の到達先

| 経路 | 既定 1 の影響 | 対処・結果 |
|---|---|---|
| `tools/m11/m11_build.sh` → `work/obj/ov.o` (m11 mainline) | `function_535bf2` / `function_535c11` の C 転記が入る | 本 PR の目的。m11 側の実測は §8.1 |
| `tools/gui/flengine/build.sh` (`m11_ov.c` を `$CF` で直接コンパイル) | 修正前は GUI の `m11_gui.cjs` にも入っていた | `CF` に `-DM11_FIX_535BF2=0` を足し、従来値 (0) に固定 (本 PR の修正 commit)。照合: `clang -E -P` の出力で、変更前 (`44a7f4465`) と修正後 HEAD の `m11_ov.c` は 1704 行で一致。修正前の `CF` を HEAD に当てると 17 行が増える (ネガコン)。GUI の e2e は再実行していない (素材 `work-m11` が本 run に無い)。GUI の実測値は `tools/gui/flengine/REPORT.md` §6j |
| `tools/m11/alloca/e2e.sh` (既定の `m11_build.sh` を使う) | 既定変更の影響を受ける | 未実行 (§8.3 の未解決) |

### 8.5 #3482: unit 144 の trap の直接原因 (計測)

> 注 (fix round 1): 本節の数値は PR 時点の IR (ir_sha256 `116d9406…`) での計測。同じ手順を本 run の IR (`e608b0f3…`) で取り直すと (§8.6)、unit 144 は OFF でも trap し、ON 固有の差は出なかった。『ON で unit 144 が ok → oob』『OFF の `[0]` = 0x10bd4c01』は本 run では再現していない。trap 経路の記述は probe 下の経路として §8.6 で再確認した。

測定 commit `aa04b5352` (`tools/m11/m11_ov.c` に `M11_PROBE_LIST` (既定 0) の計測 probe を追加。既定ビルドは変わらない)。基点 `bd4463eaa` (origin/main)。IR は `m11_gen_ir2.sh` で作り直し (ir_sha256 `116d9406…`・`r8b=applied`)。素材 fl-win64・work-m11・toolchain-retdec は `$RUNNER_TEMP` と worktree に展開。直列 1 本。

| 条件 | 環境変数 | survey ok / trap / miss | 基準 (OFF) との unit 差 |
|---|---|---|---|
| 既定 OFF | 未指定 | 873 / 22 / 46 | — |
| ON | `M11_FIX_50A830=1` | 872 / 23 / 46 | 1 件: unit 144 (`0x25c540`) ok → oob |
| OFF + probe | `M11_PROBE_LIST=1` | 874 / 21 / 46 | probe が挙動を変える (unit 153 が変化。計測値として使わない) |
| ON + probe | `M11_FIX_50A830=1 M11_PROBE_LIST=1` | 872 / 23 / 46 | 計測の trace 用 |

- e2e (既定): rc=1 (既知: tolerant 通常起動 101 ≠ 期待 56、survey ok 873 ≠ 期待 872)。`m11_e2e.sh` の所要は 73 s (IR 再生成 51 s を除く)。load average は 0.42〜0.48 (いずれも単発・n=1)。
- trap の経路 (probe 下・PR 時点の IR。§8.6 で再確認): `function_407e20` は `[arg1-8]` (hdr) が 0 のとき `[0]` (wasm アドレス 0) を次の block として読む。`[0]` が範囲外なら trap する。
- unit 144 で `function_412d60` (参照解放: `[arg1]=0`、`[arg1-8]` を減算、0 なら `function_409440(arg1-16)`) に渡る `arg1` = `0x6c`。解放される値は `0x5c` (ポインタでない)。`[0x54]` (= hdr) は OFF/ON とも 0。
- 差は `[0]` の内容だけ: OFF = `0x10bd4c01` / ON = `0x865901` (`409440(0x5c)` の `[hdr]` の値)。OFF の `[0]` は lift 版 `function_50a830` が nil の FItems (items=0) に `Q(0 + cnt*8) = item` で書いた残骸と推定 (unit 114 の Add が `[0]` へ書く)。ON では list が Grow されるため、この残骸は残らない。ON の `[0]` の書込み元は**未特定**。
- unit 144 自身には list 操作が無い (`[probe_list]` 0 件)。範囲外の値が list Add で入る経路は無い (ON の Add 32 件はすべて範囲内の item)。
- ON で unit 745 も `409440(0x10ba240c)` (8 byte 境界外) を解放するが、hdr = `0xffffffa0` の経路で trap しない。
- `function_47b260` (REPORT_2408 §7.3 の同型): IR に Grow (`47a3e0`) は残っており、欠けているのは Notify (`[rbx+0x20]` 呼出し、既定 0)。nil FItems の経路とは別物と判断 (未測定)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ON の `[0]` (= 0x865901) の書込み元と、unit 144 が `412d60(0x6c)` に至る nil 読みの元 (どの list・配列が nil のまま読まれるか) | 既定 ON 不可 (survey ok −1) | #3643 ([M11-26])。`[0]` の書込み元は #3592 ([M11-24]) で特定済み |
| 既定 ON 化と e2e 期待値 (tolerant 101 ≠ 56、survey 872/873) | e2e rc=1 | PM 判断 (§8.3 の既存未解決) |

### 8.6 fix round 1: 再測定 (ON / OFF / probe の unit 別突合)

測定は実測・単発 (n=1)。survey は直列 1 本、1 回 12 s。測定 commit `62f1345fd` (コード差分の最終 commit。`m11_build.sh` は `a2173a3f3` と同一、`trap_triage/probe_trace.sh` は `24a8965bd` で追加。基点 `bd4463eaa`)。`git diff 62f1345fd HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行。IR は本 run で `m11_gen_ir2.sh` を作り直した (`ldfix`・`ld108`・`ld115`・`r8b` = applied)。`m11_build.sh` 後は `qstore=applied`、ir_sha256 `e608b0f3…`。PR 時点の `116d9406…`・REPORT §1 の `6909f85d…`・#3482 本文の `17a98d6e…` のいずれとも異なる。IR の sha が環境ごとに変わる理由は未切り分け。

| 条件 | ok / trap / miss (noproc) | unit 144 (0x25c540) | OFF との unit 差 |
|---|---|---|---|
| OFF (既定) | 873 / 21 / 47 (1) | trap | — |
| ON `M11_FIX_50A830=1` | 873 / 21 / 47 (1) | trap | 0 件 |
| OFF + probe `M11_PROBE_LIST=1` | 873 / 21 / 47 (1) | trap | 0 件 |
| ON + probe | 871 / 23 / 47 (1) | trap | 2 件 (下) |

- ON + probe と ON の差は 2 件: unit 304 (VA `0x483140`)・unit 555 (`0x7f2500`) が ok → `memory access out of bounds`。OFF + probe と OFF の差は 0 件。
- 再現性: ON を 2 回取って 0 件差。ON + probe を 2 回 (trace 付きを含む) 取って 0 件差 (942 unit)。
- trap 経路 (probe 下): unit 144 の trace は ON + probe・OFF + probe とも `[probe_free] arg1=5c hdr=0 [hdr]=865901` (同じ値)。unit 745 は `arg1=10ba240c hdr=ffffffa0 [hdr]=0`。
- trace 行の件数 (ON + probe): `[probe_list]` 30・`[probe_grow]` 9・`[probe_free]` 2。§8.5 の『list Add 32 件』は PR 時点 IR の値。
- 判定: 『ON で unit 144 が ok → oob』は本 run では成立しない (OFF でも trap)。trap 経路 (`412d60(0x6c)` → `409440(0x5c)` → `407e20` で `[0]` が範囲外) は probe 下で ON/OFF とも再現した。ON 固有の回帰の有無は、PR 時点の IR と同じ sha を再現できてから判定する (#3592 の受入)。
- ov.o の注意: `m11_build.sh` には `M11_FIX_50A830` の切替えで `work/obj/ov.o` を作り直す stamp が無い (同じ修正は #3620・#3645 が持つ。本 PR では重ねない)。stamp 無しでは、ON で作った ov.o を後の OFF build が再利用する (`cc m11_ov.c` 0 件を確認)。上の数値は、各ビルドの前に `rm -f work/obj/ov.o` を実行して取った (各 build の `cc m11_ov.c` は 1 件)。HEAD (`62f1345fd`) で ON+probe・ON・OFF を取り直し、上の表と unit 単位で一致 (差 0)。

GUI (m2): `tools/gui/flengine/build.sh` は `m11_ov.c` を独自の CF で直接コンパイルする。差し戻し時の reviewer 実測 (同じ CF の `cc -E -P`): 基点 `bd4463eaa` と PR head の既定出力は同一 (9132 行・差 0)。`-DM11_PROBE_LIST=1` のみ +6 行 (ネガティブコントロール)。本 run では GUI の e2e は実行していない。

main との関係 (m3): `git merge-tree --write-tree origin/main HEAD` は競合なし (rc 0)。`git diff --stat bd4463eaa origin/main -- tools/m11` は 15 files。merge 後の既定 e2e は未測定。

再現手順 (1 コマンドずつ。作業ディレクトリはリポジトリのルート):

```sh
mkdir -p "$RUNNER_TEMP/win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/win64" extracted/block00031_PE.bin
tar --zstd -xf "$ARTIFACTS_DIR/work-m11.tar.zst"
cd tools/m11 && FL_WIN64_DIR="$RUNNER_TEMP/win64" bash m11_gen_ir2.sh
cd tools/m11 && rm -f work/obj/ov.o && FL_WIN64_DIR="$RUNNER_TEMP/win64" M11_FIX_50A830=1 M11_PROBE_LIST=1 bash m11_build.sh
cd tools/m11 && M11_SURVEY_DETAIL="$RUNNER_TEMP/detail_on_probe.json" node m11_survey.mjs
cd tools/m11 && M11_SURVEY_DETAIL="$RUNNER_TEMP/detail_trace.json" bash trap_triage/probe_trace.sh 2> "$RUNNER_TEMP/trace.err" > "$RUNNER_TEMP/trace.out"
awk '/^\[UNIT\] /{u=$2} /\[probe_(free|list|grow)\]/{print "unit=" u, $0}' "$RUNNER_TEMP/trace.err"
```

- OFF / ON の切替え: `cd tools/m11 && rm -f work/obj/ov.o && FL_WIN64_DIR="$RUNNER_TEMP/win64" bash m11_build.sh` (OFF) または `… M11_FIX_50A830=1 …` (ON) の後、`M11_SURVEY_DETAIL=<path>.json node m11_survey.mjs`。
- unit 差分: `python3 -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); print([(x['i'],x['kind'],y['kind']) for x,y in zip(a,b) if x!=y])" A.json B.json`
- 集計: survey の標準出力 `M11_SURVEY {...}` の `"ok"`・`"trap"`・`"miss"`・`"noproc"`。
- unit 144 のスタック: `M11_SURVEY_STACK=144 node m11_survey.mjs`。
- `trap_triage/probe_trace.sh` は `m11_survey.mjs` の複製 (printErr を stderr に流し、各 unit の前に `[UNIT] <i>` を出す。`work/m11_survey_trace.mjs` に作る) を実行する。unit 結果は `m11_survey.mjs` と一致 (ON + probe で 0 件差)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 本 run の IR (`e608b0f3…`) で ON と OFF が一致し、unit 144 は両方 trap。PR 時点の IR (`116d9406…`) との差 (IR 生成の決定性か環境差か) | 既定 ON 化の判定 (ON 固有の回帰が再現しない) | #3643 ([M11-26]) |
| `412d60(0x6c)` の元の nil 読み (ON・OFF の `[0]` (0x865901) の書込み元は #3592 で特定済み) | trap の原因 (probe 下) | #3643 ([M11-26]) |
| merge 後の既定 e2e は未測定 | merge 後の既定 e2e の結果が未確認 | PM 判断 (merge 後の確認) |

## 9. #3592 (M11-24): ON/OFF の再測定と unit 144 の trap の経路 (測定 commit `68b9de191`)

**結論**: 現 main (`15cf79560`) と `d80e9909f` の再生成 IR では、OFF でも unit 144 (`0x25c540`) が trap する。ON との unit 差は 0 で、ON 固有の回帰としては再現しなかった。受入 2 ([0] の書込み元) は特定した (§9.4)。

### 9.1 前提の修正 (`68b9de191`)

- `m11_build.sh` は `M11_FIX_50A830` の切替で `work/obj/ov.o` を作り直していなかった (他のフラグには stamp がある)。ON の後に OFF を build しても ON 版の ov.o が残り、build ログに `cc m11_ov.c` が出なかった。`work/ov_50a830.stamp` を追加して修正。
- 修正後: ON/OFF の `work/m11_boot.cjs` の md5 が異なる (ON `eaad1e62…`・OFF `c7b07c4c…`)。ON/OFF の各 build で `cc m11_ov.c` が 1 件出る。

### 9.2 素材と IR の条件

- 素材 `work-m11` には `ir_conditions.json` と `lift_pe.sha256` が無い。`bash m11_gen_ir2.sh` (`FL_WIN64_DIR` = `fl-win64` の展開先、33 秒、ldfix・ld108・ld115・r8b 適用) で IR を作り直した (`boot_final.ll` 490,761 行)。
- `m11_e2e.sh` は `lift_pe.sha256` が無いため lift 全再生成 (約 22 分) になり、本 run では実行していない。e2e の rc は未確認。

### 9.3 survey の実測 (`node m11_survey.mjs`。直列。uptime load 0.41〜0.47)

| 条件 | IR | `M11_FIX_50A830` | ok / trap / miss / noproc | unit 144 (`0x25c540`) |
|---|---|---|---|---|
| 現 main `68b9de191` | 再生成 | 1 (ON) | 873 / 21 / 47 / 1 | trap (memory access out of bounds) |
| 現 main `68b9de191` | 再生成 | 0 (OFF) | 873 / 21 / 47 / 1 | trap (同) |
| `d80e9909f` (worktree) | 再生成 | 0 | 873 / 21 / 47 / 1 | trap |
| `d80e9909f` (worktree) | 再生成 | 1 | 873 / 21 / 47 / 1 | trap。ON/OFF の unit 差 0 |
| `d80e9909f` (worktree) | 素材の `boot_final.ll` (10/10 版) + 条件記録を付与 | 0 | 872 / 22 / 47 / 1 | trap |

- ON/OFF の unit 別の差は 0 件 (`detail` の `kind`・`trap` を比較)。
- §8.1 の値 (OFF 873/22/46、unit 144 は OFF で ok) は、どの条件でも再現しなかった。原因候補は 2 つあり、未切り分け: (1) §8.3 の未解決 (IR sha256 `6909f85d…` と `17a98d6e…` の差)、(2) §8.1 の `d80e9909f` の行は stamp 修正 (`68b9de191`、9.1) より前に採られた。stamp が無いと ON/OFF の切替後に前の build の `work/obj/ov.o` が使われうるため、§8.1 の ON/OFF の数値に混ざった可能性がある (未検証)。§8.3 の IR sha256 差だけでは説明が付かない。

### 9.4 unit 144 の trap の経路と [0] の書込み元 (ON で採取。OFF は未採取)

- 呼出し連鎖 (`407e20` の wasm 番号 1877 は §8.2 と同じ。他は関数名で示す): `412d60` (C 転記、`m11_ov.c` の UStrClr) → `409440` (FreeMem) → `407e20` (FastMM 解放、IR `function_407e20__lifted`)。`407e20` の引数は 0x5c (= 0x6c − 0x10)。`407e20` は `[0x54]` (= 0) を読み、次ブロックとして `[0]` (= 0x865901) を読んで範囲外で trap する。
- unit 144 の開始時点で `[0x60, 0x80)` は全て 0。trap の後も同じ。
- IR の全 store を計装して番地 `0x60`〜`0x7f` を監視したが、unit 0〜144 で 0 件。`412d60` の refcount (`[0x64]`) を 1 にした書込みは IR store の外 (C 側の書込み、または wasm 番号の対応の誤り) と見られるが、未確定。
- `[0]` の書込み (計装は `store_watch_2408.sh` の派生で、run 部を unit 0〜144 の全区間に変えた。`work/probe3592/sw.sh`、コミットしない。`WATCH_ALL=1 WATCH_ADDR=0x0u`)。採取条件は **ON (`M11_FIX_50A830=1`) のみ**。OFF (`M11_FIX_50A830=0`) の採取は無い。下の表の `[0]` の値は ON のもの。issue #3592 本文の旧記録 (#3482) は OFF の `[0]` を `0x10bd4c01` とし、ON の `0x865901` と一致しない。よって「ON と OFF で同一」とは言えない (OFF の採取は未実施。PR 本文の未解決表に記載):

| unit | IR の位置 (関数・行) | 書込み | `[0]` の値 |
|---|---|---|---|
| 114 | `function_8651a0` 331555 | `store i64 0x8659b0, ptr %8` (nil への 8 バイト書込み。code アドレス) | 0x8659b0 |
| 114 | `function_8651a0` 331562 | `store i64 0x8659d0, ptr %12` | 0x8659d0 |
| 135 | `function_63aae0` 215899 | `store i8 1, ptr %22` (下位 1 バイト) | **0x865901** |

- 同様の 8 バイト書込み (code アドレス) が unit 15 (`44a3e0`)・17 (`455100`)・22 (`467f00`)・35 (`482d10`)・37 (`4bdfa0`)・95 (`5d2680`) にもある。nil を this とするコンストラクタの VMT 書込みと見られる。

### 9.5 検証

- 測定 commit: `68b9de191` (コード変更の最後の commit)。以後の差分は本節 (REPORT) のみ。`git diff 68b9de191 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_APPENDIX_2521.md'` の出力は 0 行。
- e2e (`m11_e2e.sh`) は未実行 (§9.2)。survey のみ実測。
