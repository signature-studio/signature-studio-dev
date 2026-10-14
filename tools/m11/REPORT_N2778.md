# M11 ptrcheck の基準ゲート (#2778, 部分達成)

親: #1004 (受入 3 の後半) / #403。素材: work-m11 (既存の wasm・image・boot_final.ll。`ir_conditions.json` と `lift_pe.sha256` は素材に無い)。fl-win64 は展開していない (run は image のみ読む)。
測定 commit: **`53b90b53`** (コードを変えた最後の commit。本 REPORT の commit は REPORT のみ)。

## 1. 変更 (測定 commit 53b90b53)

- `tools/m11/m11_ptrcheck.mjs`: `ptrCheck(mod, pre, maxEnv)` に基準の環境変数名を渡せるようにした。結果に `gate: {env, gated, max, pass}` を足す。整数 n を与えたときだけ `image_va_words_new <= n` で合格。非整数・負の n は不合格 (fail-closed)。未設定は情報出力のみ (従来どおり exit 0)。
- `tools/m11/m11_run.mjs`: 環境変数 `M11_PTRCHECK_MAX_NEW`。不合格なら M11_RESULT を出した後に `FAIL: ptrcheck ...` を stderr に出して exit 1。
- `tools/m11/m11_survey.mjs`: 環境変数 `M11_PTRCHECK_SURVEY_MAX_NEW` (run と件数が違うので別変数)。同じ扱い。
- `tools/m11/m11_ptrcheck_negctl.sh`: 次の 5 点を検査する。(a) 注入で差 +1 (b) 基準 = クリーンの実測値なら exit 0 (c) 同じ基準で注入すると exit 1 かつ FAIL 行 (d) 基準未設定の注入は exit 0 (e) 非整数の基準は exit 1。
- `tools/m11/m11_e2e.sh`・`tools/m11/e2e_expect.env`: `M11_EXPECT_PTR_NEW_MAX` / `M11_EXPECT_PTR_SURVEY_NEW_MAX` を各実行に渡し、run・survey の終了コードを最終 rc に反映する。**既定は未設定 (ゲート off)**。ただしゲート off でも、run・survey が非 0 で終わると (timeout の 124・未捕捉例外) e2e の最終 rc は非 0 になる。従来の最終 rc は judge と寛容起動の gate だけで決まっていた。

## 2. 受入条件の状態

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. 実行後 (run / survey) に guest ポインタ検査の assert を追加 | 達成 (ratchet 版)。run は §3、survey は §8 で実行して確認 |
| 2. 不合格で非 0 終了・ネガティブコントロール同梱 | 達成。run は §3、survey は §8 (`m11_ptrcheck_negctl.sh --survey`) |
| 「残件 0 (値が範囲に残らない)」を判定 | 未達 (基準の設計を変更)。判定基準は子 #3113 (§5) |

## 3. 実測 (測定 commit 53b90b53・作業 runner・単独実行)

load average (1 分値): run の直前 0.17、negctl の直前 0.32。

| 条件 | 結果 |
|---|---|
| `m11_run.mjs` 基準なし ×3 | rc 0 ×3 / wall 1.69–1.73 s / `units_run` 17 ×3 / `image_va_words_pre` 406,576 / `image_va_words_new` 68,938 (3 回一致) / `threw` は `memory access out of bounds` (素材が古いため既知) |
| `m11_ptrcheck_negctl.sh` ×2 | 両回 `clean=68938`・`injected(offset=22519877)=68939`・`diff=1`・`NEGCTL OK`。wall 8.6 / 8.7 s |
| 基準 `M11_PTRCHECK_MAX_NEW=68938` (= クリーン実測) | rc 0 (合格) |
| 基準 `M11_PTRCHECK_MAX_NEW=68937` (1 小さい) | rc 1。stderr: `FAIL: ptrcheck image_va_words_new=68938 > max=68937 (M11_PTRCHECK_MAX_NEW)` |

**変更前後の比較 (boot runner の KPI)**: 変更前 HEAD `71bf0957` でも同じ素材で `m11_run.mjs` を実行し、`units_run` 17・`image_va_words_new` 68,938・rc 0 を得た。変更は検査の追加のみで、基準を設定しない既定の経路の数値は変わらない。製品の起動 KPI (`tools/flelift/boot/REPORT.md` の dispatch 数・通過 unit 数) は本 PR では動かしていない。

## 4. survey は未実行 (前回 PR の理由。§8 で解消)

- 素材の wasm (`work/m11_boot.cjs.wasm`) は `_m11_set_va_unit_budget` を持たない古い build。survey は `is not a function` で開始できない (`REPORT_N1004.md` §2 と同じ)。
- 再ビルド (`m11_build.sh`) は IR 来歴のガード (`ir_conditions.json` の ldfix・ld108・qstore の記録と PE 一致) で拒否される。素材に記録が無い。このガードを迂回して作った wasm は測定の根拠にならないため、作らなかった。
- したがって survey のゲートは `node --check` の構文検査のみ。`M11_EXPECT_PTR_SURVEY_NEW_MAX` は未設定。

## 5. 判定基準の選び方 (受入 1 の「値 0」を採らない理由)

- 範囲内の新規 word は、クリーン実行でも 68,938 件 (run)。値だけでは未 remap の VA と正当な LVA 整数を区別できない (`REPORT_N1004.md` §3・§5)。値 0 を要求すると常に不合格になる。
- そこで **ratchet** を採る。同じ wasm・image の実測件数を基準にし、それを超えたら不合格とする。未 remap の増加という退行を検出できる。remap 修正で件数が減っても合格する (基準は手で下げる)。
- 既定は未設定 (情報出力のみ)。基準の値は fresh 再生成 (IR 来歴の記録付き) の実測で決める。本 run の素材の 68,938 は、`REPORT_N1004.md` §5 の fresh 再生成の値 (LB=0 で 69,306・LB=0x10000 で 69,044) と一致しないため、e2e の基準には採らない。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 「残件 0」の判定基準 (LVA 整数と未 remap VA の区別) | 受入 1 の文言どおりの assert は未実装 (ratchet で代替)。分類 B の基準は #3113 (PR #3130) で定めた | #3129 (fresh 再生成での分類 B 件数の実測。`tools/m11/REPORT_N3113.md` §7) |
| `m11_e2e.sh --full` の全再生成 (scan・bounds・lift・Ghidra) を本 runner で通す | 基準値の CI 側での再現は未検証。素材に `functions_dll.csv` と `lift_pe.sha256` が無く、全再生成は fail-closed で止まる (§8.1) | #3129 のコメント https://github.com/signature-studio/signature-studio-dev/issues/3129#issuecomment-6180450191 (再現素材・`functions_dll.csv` の生成手順・`lift_pe.sha256` の出どころ。#3113 のコメントから移した) |

## 7. 前回 PR (測定 commit 53b90b53) の差分 (履歴)

測定 commit `53b90b53` 以降のコード差分は `e2e_expect.env` のコメント 1 行 (参照節 §3 → §5) だけ。値と構文は変わらない (`source` した 6 個の変数の値が測定 commit と同一)。よって測定値は再測定せず採用する (素材 work-m11 は本 runner に無く、再測定はできない)。
`git diff 53b90b53 -- tools/m11 ':!tools/m11/REPORT_N2778.md'` の出力 (754 バイト) は次のとおり。

```diff
diff --git a/tools/m11/e2e_expect.env b/tools/m11/e2e_expect.env
index 85f92041..0762450c 100644
--- a/tools/m11/e2e_expect.env
+++ b/tools/m11/e2e_expect.env
@@ -9,6 +9,6 @@
 : "${M11_EXPECT_STRICT_DONE:=56}"
 : "${M11_EXPECT_SURVEY_OK_EXACT:=872}"
 # #2778: ptrcheck ゲートの基準 (image_va_words_new の上限・run と survey は別々)。未設定 = 情報出力のみ (既定)。
-# 基準は同一 wasm・image の実測値を入れる (ratchet)。値 0 は正当な LVA 整数のため使えない (REPORT_N2778.md §3)。
+# 基準は同一 wasm・image の実測値を入れる (ratchet)。値 0 は正当な LVA 整数のため使えない (REPORT_N2778.md §5)。
 : "${M11_EXPECT_PTR_NEW_MAX:=}"
 : "${M11_EXPECT_PTR_SURVEY_NEW_MAX:=}"
```

## 8. fresh 再生成での基準件数の実測 (#2778 の残り)

測定 commit: **`9b795530`** (コードを変えた最後の commit。本 REPORT の commit は REPORT のみ)。
素材: work-m11 を worktree の `tools/m11/work` に展開。fl-win64 は `block00031_PE.bin` (22,227,016 B) のみを展開し、`FL_WIN64_DIR` で指した。

### 8.1 手順

`m11_e2e.sh` は素材に `functions_dll.csv` (Ghidra 中間物) と `lift_pe.sha256` が無いため、全再生成に入って `m11_bounds.py` で fail-closed に止まる (§4・`REPORT_N1004.md` §4 と同じ)。そこで全再生成の後段を個別に実行した。

1. `m11_gen_ir2.sh` (LB=0): `work/ir_conditions.json` を作る (ldfix=applied・ld108=applied・qstore=applied)。
2. boot5 を `m11_lift.sh m11_extra_ranges5.txt boot5 600` で lift し、`m11_gen_ir2.sh` で IR を作り直す。素材に無かったため追加した。`m11_e2e.sh` の #132 経路と同じ。
3. `m11_data_gen.py`・`m11_image_gen.py` で data/image を作り直し、`m11_build.sh` で wasm を作る (6,033,114 B)。
4. 下表を測定する。

boot5 を入れなかった版 (IR sha256 `7c653b0f…`) は survey ok 870 で、e2e の完全一致期待値 `M11_EXPECT_SURVEY_OK_EXACT=872` と合わなかった。以後の基準は boot5 込みの値だけを採る。
boot5 込みの IR sha256 は `de46cadaaedc17866ea8e8ed3c1ce4d0d5f14dc219ca65eabe0cc06c6fff8636`。

§8.2 の測定に使った wasm (step 3 で作った 6,033,114 B) と `m11_image.bin` の sha256 は**未記録**。両方とも本 PR の fix run の runner に残っておらず、推測で書かない。後から同一性を照合できるよう、step 1–3 を再実行したときにこの節へ両方の sha256 を追記する。追跡先は未解決表 (§6) の #3129 コメント (#3113 のコメントから移した)。

### 8.2 実測 (測定 commit 9b795530・単独実行)

| 条件 | 結果 |
|---|---|
| `m11_run.mjs` ゲートなし ×3 | rc 0 ×3 / units_run 53・units_skipped 3 (計 56) / `image_va_words_new` 69,359 (3 回一致) / wall 1.27–1.28 s / load 0.66 |
| `m11_survey.mjs` ゲートなし ×2 | rc 0 ×2 / ok 872・noproc 1・miss 46・trap 23 / `image_va_words_new` 71,001 (2 回一致) / wall 16.0–16.1 s / load 0.56 |
| `m11_ptrcheck_negctl.sh` (run) | clean 69,359・injected 69,360・diff +1・`NEGCTL OK` |
| `m11_ptrcheck_negctl.sh --survey` | clean 71,001・injected 71,002・diff +1・`NEGCTL OK` (80 s) |
| run の境界 | 基準 69,359 → rc 0 / 基準 69,358 → rc 1 (`FAIL: ptrcheck image_va_words_new=69359 > max=69358`) |
| survey の境界 | 基準 71,001 → rc 0 / 基準 71,000 → rc 1 (`FAIL: survey ptrcheck image_va_words_new=71001 > max=71000`) |
| e2e 後段 (`m11_judge.py`・`m11_tolerant.mjs`・`m11_tolerant_gate.py`・`--negctl`) | judge rc 0 (reached_stage 4・survey_ok 872 ≥ 800) / tolerant attempted 942・ok 874・noproc 1・skipped 67 / tolerant gate rc 0 / negctl rc 0 |

### 8.3 基準の採用

`tools/m11/e2e_expect.env` に `M11_EXPECT_PTR_NEW_MAX=69359`・`M11_EXPECT_PTR_SURVEY_NEW_MAX=71001` を設定した (ratchet。超えたら e2e は非 0 で終わる)。
本 runner の素材の実測値であり、CI の `m11_e2e.sh --full` (Ghidra から全再生成) で同じ件数になるかは未検証 (§6)。件数が変わったら、理由を REPORT に書いて基準を更新する。

### 8.4 残件

「範囲に残らない (値 0)」は未達のまま。clean 実行の 69,359 件 (run) には正当な LVA 整数が含まれ、値 0 では常に不合格になる (§5)。判定基準は子 #3113 に移した。

### 8.5 測定 commit からのコード差分

`git diff 9b795530 HEAD -- tools/m11 ':!tools/m11/REPORT_N2778.md'` の出力は 0 バイト (測定 commit 以降のコードの変更は無い)。

