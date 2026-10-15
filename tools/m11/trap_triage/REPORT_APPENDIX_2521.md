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
- §8.1 の値 (OFF 873/22/46、unit 144 は OFF で ok) は、どの条件でも再現しなかった。§8.3 の未解決 (IR sha256 `6909f85d…` と `17a98d6e…` の差) が原因かは未切り分け。

### 9.4 unit 144 の trap の経路と [0] の書込み元 (ON と OFF で同一)

- 呼出し連鎖 (`407e20` の wasm 番号 1877 は §8.2 と同じ。他は関数名で示す): `412d60` (C 転記、`m11_ov.c` の UStrClr) → `409440` (FreeMem) → `407e20` (FastMM 解放、IR `function_407e20__lifted`)。`407e20` の引数は 0x5c (= 0x6c − 0x10)。`407e20` は `[0x54]` (= 0) を読み、次ブロックとして `[0]` (= 0x865901) を読んで範囲外で trap する。
- unit 144 の開始時点で `[0x60, 0x80)` は全て 0。trap の後も同じ。
- IR の全 store を計装して番地 `0x60`〜`0x7f` を監視したが、unit 0〜144 で 0 件。`412d60` の refcount (`[0x64]`) を 1 にした書込みは IR store の外 (C 側の書込み、または wasm 番号の対応の誤り) と見られるが、未確定。
- `[0]` の書込み (計装は `store_watch_2408.sh` の派生で、run 部を unit 0〜144 の全区間に変えた。`work/probe3592/sw.sh`、コミットしない。`WATCH_ALL=1 WATCH_ADDR=0x0u`):

| unit | IR の位置 (関数・行) | 書込み | `[0]` の値 |
|---|---|---|---|
| 114 | `function_8651a0` 331555 | `store i64 0x8659b0, ptr %8` (nil への 8 バイト書込み。code アドレス) | 0x8659b0 |
| 114 | `function_8651a0` 331562 | `store i64 0x8659d0, ptr %12` | 0x8659d0 |
| 135 | `function_63aae0` 215899 | `store i8 1, ptr %22` (下位 1 バイト) | **0x865901** |

- 同様の 8 バイト書込み (code アドレス) が unit 15 (`44a3e0`)・17 (`455100`)・22 (`467f00`)・35 (`482d10`)・37 (`4bdfa0`)・95 (`5d2680`) にもある。nil を this とするコンストラクタの VMT 書込みと見られる。

### 9.5 検証

- 測定 commit: `68b9de191` (コード変更の最後の commit)。以後の差分は本節 (REPORT) のみ。`git diff 68b9de191 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_APPENDIX_2521.md'` の出力は 0 行。
- e2e (`m11_e2e.sh`) は未実行 (§9.2)。survey のみ実測。
