# #663 [M11-N27]: `survey_units.mjs` の oob frames が最上位 frame を捨てる (`.slice(1)`) を直し、annotate の最上位集計を実測で更新

**判定: 受入条件 2 件は commit `18dbb43` で実測して達成 (§2〜§4)。最終 HEAD (`a732daa` 以降の filter アンカー化を含む) でも survey を再測定し、同じ結果を確認 (§8)。** 残る未解決は基準 (c) の再測定のみ (§5)。
修正は `survey_units.mjs` の非 halt0 分岐 (`slice(1, 30)` → `slice(0, 30)`、後段で filter を `/^\s*at /` にアンカー。PR #703 と同一行)。kind は 942 unit 全てで不変 (ok 退行 0・icall 差 0)、
oob 21 unit の frames だけが最上位 frame を含む 1 段増えた。`annotate.py` は**コード変更なし** (入力の frames が正しくなったので集計が正しくなる)。
修正前の起点 = `8d883c3` (`origin/main`)。実測の commit = `18dbb43` (修正本体 = `442c46e`)。本 PR の最終 HEAD は PR コメントに記載。

既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。lift の欠陥ではなく survey ハーネス (JS の stack 抽出) の欠陥。

## 1. 欠陥と修正

| 箇所 | 修正前 | 修正後 |
|---|---|---|
| `trap_triage/survey_units.mjs` 非 halt0 分岐 (oob / other / abort 共通) | `.filter(/wasm-function\|at /).slice(1, 30)` | `.filter(/^\s*at /).slice(0, 30)` (実測 `18dbb43` は `.filter(/wasm-function\|at /).slice(0, 30)`) |
| 同 halt0 分岐 (参照, 変更なし) | `.filter(/wasm-function/).slice(0, 30)` | (同左) |

`e.stack` の先頭の wasm frame (実際に trap した関数) が非 halt0 でだけ落ちていた。REPORT_495 §2 の注記 (最上位 frame を 1 つ余分に捨てる) と一致。
unit 56 の生の鎖は Issue 本文どおり `function_417b70 ← function_417fc0 ← function_8cbb00 …` で、修正前の survey JSON は `417fc0` から始まっていた。

## 2. 検証 (基準 build = work-m11 の IR・obj から `m11_build.sh` で再リンク、実測 commit `18dbb43`)

**build の前提**: `work-m11` の `m11_boot.cjs` は HEAD の `survey_units.mjs` より古く (`_m11_icall_cnt_n` 未 export)、そのままでは survey が落ちた (`TypeError`)。
`bash tools/m11/m11_build.sh` で HEAD の `m11_ov.c` 等からリンクし直した (`real 0m7.728s`、`OK: work/m11_boot.cjs(+.wasm)`)。
`m11_boot.cjs.wasm` md5 `c07aeb8924ec`。IR は snapshot の `boot_final.ll` をそのまま使用 (**REPORT.md §8.2 の基準 (c) = IR 再生成 + PE 有りとは別。(a) 相当**。
(c) は `m11_e2e.sh --full` (約 10 分・PE パス固定) が要るため本 run では再測定していない。§5 未解決)。

| 項目 | 修正前 (`8d883c3` の survey) | 修正後 (`18dbb43`) |
|---|---|---|
| kind 件数 (ok / halt0 / miss / oob / noproc) | 818 / 56 / 46 / 21 / 1 | 818 / 56 / 46 / 21 / 1 |
| `survey_diff.py` 遷移 (A→B) | — | 全 5 種が同 kind → 同 kind (計 942) |
| ok 退行 unit | — | **0** |
| icall sites / targets の総数差 | — | **0 件 / 0 件** |
| kind 以外も含む差分 unit (frames は深さのみ) | — | 21 = oob 全件 `[56,58–63,87,95,149,158,275,280,291,296,304,477,555,659,895,923]` |
| `frames_check.py` (本 PR, 規則は下記) | — | **PASS** (oob 21 / frames が変わった 21 / 違反 0) |

`frames_check.py` の規則 (942 unit 全部): (1) kind 一致 (2) oob 以外は全欄一致 (3) oob は frames 以外の欄一致、
`post.frames[1:] == pre.frames[:len(post.frames)-1]`、`len(post.frames) == min(len(pre.frames)+1, 30)`。
別実装の検算 `recount_483.mjs pre.json post.json` (wasm 名前表を直接パース): 遷移は全て同 kind (`ok->ok 818` 他)、`ok->non-ok 0`、基準側 oob 最上位は §2-1 の修正前列と一致。
JS の末尾 frame `file:///…/survey_units*.mjs` は配置場所だけで決まるため比較前に正規化 (`file://<survey>`)。空判定 (oob 0 件) は不合格。

### 2-1. 最上位 frame の変化 (`annotate.py` の出力, oob 21 unit, `18dbb43` 基準)

| 修正前の最上位 (旧集計) | unit | 修正後の最上位 | 注 |
|---|---|---|---|
| `function_417fc0` ×7 | 56, 58–63 | `function_417b70` ×7 | Issue の指摘どおり。unit 56 の鎖は `417b70 ← 417fc0 ← 8cbb00 ← 8cbcb0 ← 8cc190 ← 8c7a10` |
| `function_4f9ff0` ×5 | 291, 296, 304, 555, 923 | `function_4f9f40` ×5 | |
| `function_414bb0` ×4 | 149, 158, 280, 659 | `function_414ad0` ×4 | REPORT.md §8.2 の「414ad0 は OOB 最上位に現れない」は誤り (§6) |
| `function_59f9a0` ×1 | 87 | `function_418190` ×1 | `qstore/REPORT.md` / REPORT.md の「idx 87 = 418190」と一致 |
| `function_536da0` ×1 | 95 | `function_47ad70` ×1 | |
| `function_80e040` ×1 | 275 | `function_864fe0` ×1 | |
| `function_904190` ×1 | 477 | `function_903d20` ×1 | |
| `function_40ffe0` ×1 | 895 | `function_40ff70` ×1 | |

修正後の最上位は 8 種・計 21 (7+5+4+1+1+1+1+1)。`annotate.py` の出力全文は `work/trap_triage/annotate_{base,after}.txt` (gitignore、再現可)。

### 2-2. 基準 JSON の更新

`survey_diff.py` / `frames_check.py` の基準は `negctl_663.sh` が `work/negctl_663/post.json` に再生成する (修正後のコード)。
**repo には commit しない**: frames の末尾に runner 上の絶対パス (`file://` で始まる JS frame) が入るため。再現は `bash trap_triage/negctl_663.sh`。

## 3. ネガティブコントロール (`bash trap_triage/negctl_663.sh`、期待と違えば exit 1)

| 構成 | 期待 | 結果 (`18dbb43`) |
|---|---|---|
| (a) 修正前 (`git show 8d883c3:…`) vs 修正後 → `frames_check.py` | PASS | **PASS** (exit 0) |
| (a) の `survey_diff.py` (post vs pre) | `ok 退行 unit: 0 []` | ok 退行 0 (`18dbb43`)。判定行は本 PR で追加 (script が grep で assert) |
| (b) 修正前 vs 修正前 (修正を外した状態) → `frames_check.py` | FAIL | **FAIL** (exit 1): 違反 21 = oob 全件 (同一 JSON 同士なので `frames[1:]` が 1 段ずれず一致しない) |
| (c) 修正後の 1 unit (unit 0, ok) の kind を oob に書換えた JSON → `frames_check.py` | FAIL | **FAIL** (exit 1) |
| (c) の `survey_diff.py` | `ok 退行 unit: 1 [0]` | **ok 退行 1 `[0]`** (判定行は本 PR で追加) |

(b) は kind 差 0 の検査が「修正後に frames が変わった」だけで落ちないことの裏返し。(c) は kind 変化を確実に検出することの確認。
判定行の文字列照合 (`ok 退行 unit: 0 []` / `ok 退行 unit: 1 [0]`) は、合成 JSON で `survey_diff.py` を走らせ、正例 OK・ok 退行を入れた負例 NG を確認した (survey 実測ではない)。

## 4. 所要と load (実測、`18dbb43`)

- `m11_build.sh` (再リンク): 7.728 s real (cached obj を流用)
- survey 1 回 (942 unit): 修正前 8.41 s (初回 `base_head`)。`negctl_663.sh` の pre / post は、作業ツリー段階で 8.10 / 8.04 s。コミット `442c46e` (survey 本体) を含む HEAD `18dbb43` での 2 回: pre 8.08 / 8.10 s、post 8.11 / 8.04 s (min–max、n=2)
- `negctl_663.sh` 全体: 16.27 s (survey 2 本 + checker 3 本 + survey_diff 2 本)。HEAD 上の 2 回とも `NEGCTL_663 ALL EXPECTED`
- 基準 JSON の md5 は全 run で一致: pre `9d9f778d9481`、post `b2815724d940`
- load average (1 分): 0.13–0.52 (各 run の前後 `uptime`)、並列数 1 (node は単一プロセス)、node `v22.23.3` (PATH の node)

## 5. 検証範囲 / 範囲外 / 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 基準 (c) (IR 再生成 + PE 有り) での再測定が未実施。REPORT.md §8.2 / REPORT_483 / REPORT_495 の最上位 frame 数値 (`8cc190` ×9 など) は旧 frames の基準 | 数値の確定は (c) が正。本 PR の kind 差 0 は (a) で実測 | PM 判断: `m11_e2e.sh --full` 後に `negctl_663.sh` を再実行して REPORT に追記 (起票不要、本 REPORT §7 の手順) |
| abort / other 種別は `18dbb43` の snapshot で 0 件 | 非 halt0 の共通分岐で ` at ` を含む例外文言は、旧 filter では frames[0] に入る (§5-1)。アンカー化で防ぐ | 起票不要 (実測 0 件。最終 HEAD の survey でも oob 21 件の msg は全て `memory access out of bounds`、` at ` を含む非 halt0 は 0 件 (§8)) |

範囲: 942 unit × 1 回 (先頭から順、`SV_*` 無し) の survey、snapshot の IR。範囲外: trace 付き (`SV_TRACE_AT`)・`SV_STK_FILL` 下の残骸感度 (REPORT_495 の範囲)。

### 5-1. filter のアンカー化の単体確認 (survey 外、node v22.23.3)

最小 wasm (func 0 = import `env.thr`、JS 側で throw / func 1 = `call 0` / func 2 = `call 1`、export `f`) を `f()` で呼び、捕まえた `e.stack` に filter を当てた。

| throw する Error の message | filter (`slice(0, 30)` と組む) | frames 先頭 |
|---|---|---|
| `Aborted: cannot read at offset 12` (` at ` を含む) | 旧 `/wasm-function\|at /` | `Error: Aborted: cannot read at offset 12` (メッセージ行が混入) |
| 同上 | 新 `/^\s*at /` | `at thr (…)`・`at wasm://…:wasm-function[1]:0x2c`・`…[2]:0x31`・… (メッセージ行なし) |
| `memory access out of bounds` (` at ` を含まない) | 旧 / 新 | 同一 (`at thr`・`wasm-function[1]`・`[2]`・…) |

結論: ` at ` を含む message では、旧 filter のまま `slice(0, 30)` にするとメッセージ行が frames[0] に入る。新 filter ではメッセージ行は入らず、wasm 関数の行は残る。
oob の message (`memory access out of bounds`) では新旧の出力は同一。実 survey の oob 21 unit の msg は本 REPORT では未確認 (survey JSON が無い)。

## 6. 既存 REPORT の訂正 (本 PR で該当箇所に注記)

- `trap_triage/REPORT_495.md` §7 の行 `survey_units.mjs の frames が非 halt0 で最上位 frame を捨てる` → 本件で解消 (本 REPORT)。
- `trap_triage/REPORT.md` §8.2 の「414ad0 は m11 survey の OOB 最上位 frame に現れない」 → 誤り (旧 frames の 1 段ずれ由来)。修正後は `function_414ad0` ×4 (unit 149, 158, 280, 659)。
- `trap_triage/REPORT.md` §8.2 の最上位 frame 表 (`8cc190` ×9 等) は、旧 frames (1 段ずれ) かつ基準 (c) の値。旧表は無効 (REPORT.md §8.1・§8.2 に注記)。修正後の値は (a) で §2-1。(c) での値は未確定 (§5)。

## 7. 再現手順

## 8. 最終 HEAD での再測定 (`523f55a`)

素材 `toolchain-emsdk`・`work-m11` を取得して実測 (`oc_artifacts` 行頭指定の run)。`work-m11` 展開後に `m11_build.sh` で再リンク (OK、`real 11.4 s`)、`bash trap_triage/negctl_663.sh` を foreground で実行。

| 項目 | 結果 (`523f55a`) |
|---|---|
| 所要 (negctl 全体, 2 回実測) | 33.08 s / 31.46 s。survey 単体 wall: pre 17.11 / 15.63 s、post 15.78 / 15.64 s |
| kind 件数 (pre / post) | 818 / 56 / 46 / 21 / 1 (ok / halt0 / miss / oob / noproc) |
| `frames_check.py` (post vs pre) | PASS (exit 0)。ネガコン pre vs pre = FAIL (exit 1)、kind 書換え = FAIL (exit 1) |
| `survey_diff.py` ok 退行 (post) | `ok 退行 unit: 0 []` |
| ok 退行 (mut, unit 0 の kind 書換え) | `ok 退行 unit: 1 [0]` |
| oob 21 件の最上位 frame | 417b70 ×7・4f9f40 ×5・414ad0 ×4・418190・47ad70・864fe0・903d20・40ff70 (各 ×1)。§2-1 と一致 |
| oob 21 件の msg | 全て `memory access out of bounds`。` at ` を含む非 halt0 の msg は 0 件 (§5-1 の懸念は実データでは起きていない) |
| 最終判定 | `NEGCTL_663 ALL EXPECTED`、exit 0 |
| load average | 0.68 → 0.99 (1 分)、node v22.23.3 |

基準 JSON の md5 は `18dbb43` の実測と同じ (pre `a13bcb65a949`、post `de499c37a63d`)。survey 出力は `18dbb43` と一致し、`a732daa` 以降の filter アンカー化は kind・frames に影響しなかった。
残る未解決は §5 の基準 (c) の再測定のみ。

## 7. 再現手順 (補足)

```sh
cd tools/m11                                   # work/ = work-m11 展開済み、emsdk ([EMSDK]、docs/REFERENCES.md) が要る
bash m11_build.sh                              # HEAD のソースで再リンク (snapshot の IR を使用)
bash trap_triage/negctl_663.sh                 # 修正前 (8d883c3) / 修正後 / ネガコン 2 種 / survey_diff の判定。期待と違えば exit 1
python3 trap_triage/annotate.py work/negctl_663/post.json
python3 trap_triage/survey_diff.py work/negctl_663/pre.json work/negctl_663/post.json
```
