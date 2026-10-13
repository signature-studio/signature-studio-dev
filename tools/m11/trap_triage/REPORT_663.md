# #663 [M11-N27]: `survey_units.mjs` の oob frames が最上位 frame を捨てる (`.slice(1)`) を直し、annotate の最上位集計を実測で更新

**判定: 受入条件 2 件とも達成。** 修正は `survey_units.mjs` の 1 行 (`slice(1, 30)` → `slice(0, 30)`)。kind は 942 unit 全てで不変 (ok 退行 0・icall 差 0)、
oob 21 unit の frames だけが最上位 frame を含む 1 段増えた。`annotate.py` は**コード変更なし** (入力の frames が正しくなったので集計が正しくなる)。
修正前の起点 = `8d883c3` (`origin/main`)。修正後の HEAD = 本 PR の最終 commit (hash は PR と最終回答に記載)。

既知類型との関係 (`docs/DEFECTS.md`): **該当なし**。lift の欠陥ではなく survey ハーネス (JS の stack 抽出) の欠陥。

## 1. 欠陥と修正

| 箇所 | 修正前 | 修正後 |
|---|---|---|
| `trap_triage/survey_units.mjs` 非 halt0 分岐 (oob / other / abort 共通) | `.filter(/wasm-function\|at /).slice(1, 30)` | `.slice(0, 30)` |
| 同 halt0 分岐 (参照, 変更なし) | `.filter(/wasm-function/).slice(0, 30)` | (同左) |

`e.stack` の先頭の wasm frame (実際に trap した関数) が非 halt0 でだけ落ちていた。REPORT_495 §2 の注記 (最上位 frame を 1 つ余分に捨てる) と一致。
unit 56 の生の鎖は Issue 本文どおり `function_417b70 ← function_417fc0 ← function_8cbb00 …` で、修正前の survey JSON は `417fc0` から始まっていた。

## 2. 検証 (基準 build = work-m11 の IR・obj から `m11_build.sh` で再リンク)

**build の前提**: `work-m11` の `m11_boot.cjs` は HEAD の `survey_units.mjs` より古く (`_m11_icall_cnt_n` 未 export)、そのままでは survey が落ちた (`TypeError`)。
`bash tools/m11/m11_build.sh` で HEAD の `m11_ov.c` 等からリンクし直した (`real 0m7.728s`、`OK: work/m11_boot.cjs(+.wasm)`)。
`m11_boot.cjs.wasm` md5 `c07aeb8924ec`。IR は snapshot の `boot_final.ll` をそのまま使用 (**REPORT.md §8.2 の基準 (c) = IR 再生成 + PE 有りとは別。(a) 相当**。
(c) は `m11_e2e.sh --full` (約 10 分・PE パス固定) が要るため本 run では再測定していない。§5 未解決)。

| 項目 | 修正前 (`8d883c3` の survey) | 修正後 (本 PR) |
|---|---|---|
| kind 件数 (ok / halt0 / miss / oob / noproc) | 818 / 56 / 46 / 21 / 1 | 818 / 56 / 46 / 21 / 1 |
| `survey_diff.py` 遷移 (A→B) | — | 全 5 種が同 kind → 同 kind (計 942) |
| ok 退行 unit | — | **0** |
| icall sites / targets の総数差 | — | **0 件 / 0 件** |
| kind 以外も含む差分 unit (frames は深さのみ) | — | 21 = oob 全件 `[56,58–63,87,95,149,158,275,280,291,296,304,477,555,659,895,923]` |
| `frames_check.py` (本 PR, 規則は下記) | — | **PASS** (oob 21 / frames が変わった 21 / 違反 0) |

`frames_check.py` の規則 (942 unit 全部): (1) kind 一致 (2) oob 以外は全欄一致 (3) oob は frames 以外の欄一致、
`post.frames[1:] == pre.frames[:len(post.frames)-1]`、`len(post.frames) == min(len(pre.frames)+1, 30)`。
JS の末尾 frame `file:///…/survey_units*.mjs` は配置場所だけで決まるため比較前に正規化 (`file://<survey>`)。空判定 (oob 0 件) は不合格。

### 2-1. 最上位 frame の変化 (`annotate.py` の出力, oob 21 unit)

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

`survey_diff.py` / `frames_check.py` の基準は `negctl_663.sh` が `work/negctl_663/post.json` に再生成する (修正後の HEAD)。
**repo には commit しない**: frames の末尾に runner の絶対パス (`file:///home/runner/...`) が入るため。再現は `bash trap_triage/negctl_663.sh`。

## 3. ネガティブコントロール (`bash trap_triage/negctl_663.sh`、期待と違えば exit 1)

| 構成 | 期待 | 結果 |
|---|---|---|
| (a) 修正前 (`git show 8d883c3:…`) vs 修正後 → `frames_check.py` | PASS | **PASS** (exit 0) |
| (b) 修正前 vs 修正前 (修正を外した状態) → `frames_check.py` | FAIL | **FAIL** (exit 1): 違反 21 = oob 全件 (unit 95: `pre 8 / post 9` 等) |
| (c) 修正後の 1 unit (unit 0, ok) の kind を oob に書換えた JSON → `frames_check.py` | FAIL | **FAIL** (exit 1) |
| (c) の `survey_diff.py` | ok 退行 1 | **ok 退行 1 `[0]`** |

(b) は kind 差 0 の検査が「修正後に frames が変わった」だけで落ちないことの裏返し。(c) は kind 変化を確実に検出することの確認。

## 4. 所要と load (実測, n=3 は §4 末尾)

- `m11_build.sh` (再リンク): 7.728 s real (cached obj を流用)
- survey 1 回 (942 unit): 修正前 8.41 s (初回, `base_head`)、`negctl_663.sh` 内 pre 8.10 s / post 8.04 s
- `negctl_663.sh` 全体: 16.27 s (survey 2 本 + checker 3 本 + survey_diff 2 本)
- load average (1 分): 0.20–0.61 (実行中 `uptime` 計測)、並列数 1 (node は単一プロセス)、node `v22.23.3` (PATH の node)

## 5. 検証範囲 / 範囲外 / 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 基準 (c) (IR 再生成 + PE 有り) での再測定が未実施。REPORT.md §8.2 / REPORT_483 / REPORT_495 の最上位 frame 数値 (`8cc190` ×9 など) は旧 frames の基準 | 数値の確定は (c) が正。本 PR の kind 差 0 は (a) で実測 | PM 判断: `m11_e2e.sh --full` 後に `negctl_663.sh` を再実行して REPORT に追記 (起票不要、本 REPORT §6 の手順) |
| abort / other 種別は本 snapshot で 0 件 (共通分岐を直したので、出た場合は同じく 1 段戻る) | 未観測 | 起票不要 (実測 0 件) |

範囲: 942 unit × 1 回 (先頭から順、`SV_*` 無し) の survey、snapshot の IR。範囲外: trace 付き (`SV_TRACE_AT`)・`SV_STK_FILL` 下の残骸感度 (REPORT_495 の範囲)。

## 6. 既存 REPORT の訂正 (本 PR で該当箇所に注記)

- `trap_triage/REPORT_495.md` §7 の行 `survey_units.mjs の frames が非 halt0 で最上位 frame を捨てる` → 本件で解消 (本 REPORT)。
- `trap_triage/REPORT.md` §8.2 の「414ad0 は m11 survey の OOB 最上位 frame に現れない」 → 誤り (旧 frames の 1 段ずれ由来)。修正後は `function_414ad0` ×4 (unit 149, 158, 280, 659)。
- `trap_triage/REPORT.md` §8.2 の最上位 frame 表 (`8cc190` ×9 等) は、旧 frames (1 段ずれ) かつ基準 (c) の値。修正後の値は (a) で §2-1。(c) での値は未確定 (§5)。

## 7. 再現手順

```sh
cd tools/m11                                   # work/ = work-m11 展開済み、emsdk (/opt/emsdk) が要る
bash m11_build.sh                              # HEAD のソースで再リンク (snapshot の IR を使用)
bash trap_triage/negctl_663.sh                 # 修正前 (8d883c3) / 修正後 / ネガコン 2 種。期待と違えば exit 1
python3 trap_triage/annotate.py work/negctl_663/post.json
python3 trap_triage/survey_diff.py work/negctl_663/pre.json work/negctl_663/post.json
```
