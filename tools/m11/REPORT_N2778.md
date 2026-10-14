# M11 ptrcheck の基準ゲート (#2778, 部分達成)

親: #1004 (受入 3 の後半) / #403。素材: work-m11 (既存の wasm・image・boot_final.ll。`ir_conditions.json` と `lift_pe.sha256` は素材に無い)。fl-win64 は展開していない (run は image のみ読む)。
測定 commit: **`53b90b53`** (コードを変えた最後の commit。本 REPORT の commit は REPORT のみ)。

## 1. 変更 (測定 commit 53b90b53)

- `tools/m11/m11_ptrcheck.mjs`: `ptrCheck(mod, pre, maxEnv)` に基準の環境変数名を渡せるようにした。結果に `gate: {env, gated, max, pass}` を足す。整数 n を与えたときだけ `image_va_words_new <= n` で合格。非整数・負の n は不合格 (fail-closed)。未設定は情報出力のみ (従来どおり exit 0)。
- `tools/m11/m11_run.mjs`: 環境変数 `M11_PTRCHECK_MAX_NEW`。不合格なら M11_RESULT を出した後に `FAIL: ptrcheck ...` を stderr に出して exit 1。
- `tools/m11/m11_survey.mjs`: 環境変数 `M11_PTRCHECK_SURVEY_MAX_NEW` (run と件数が違うので別変数)。同じ扱い。
- `tools/m11/m11_ptrcheck_negctl.sh`: 次の 5 点を検査する。(a) 注入で差 +1 (b) 基準 = クリーンの実測値なら exit 0 (c) 同じ基準で注入すると exit 1 かつ FAIL 行 (d) 基準未設定の注入は exit 0 (e) 非整数の基準は exit 1。
- `tools/m11/m11_e2e.sh`・`tools/m11/e2e_expect.env`: `M11_EXPECT_PTR_NEW_MAX` / `M11_EXPECT_PTR_SURVEY_NEW_MAX` を各実行に渡し、run・survey の終了コードを最終 rc に反映する。**既定は未設定 (ゲート off)**。

## 2. 受入条件の状態

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1. 実行後 (run / survey) に guest ポインタ検査の assert を追加 | 部分 | run は実装して実測 (§3)。survey は実装と構文検査 (`node --check`) のみ。実行は未了 (§4) |
| 2. 不合格で非 0 終了・ネガティブコントロール同梱 | 部分 | run は NEGCTL で exit 1 を実測 (§3)。survey は未実行 |
| 「残件 0 (値が範囲に残らない)」を判定 | 未達 (基準の設計を変更) | §5 |

## 3. 実測 (測定 commit 53b90b53・作業 runner・単独実行)

load average (1 分値): run の直前 0.17、negctl の直前 0.32。

| 条件 | 結果 |
|---|---|
| `m11_run.mjs` 基準なし ×3 | rc 0 ×3 / wall 1.69–1.73 s / `units_run` 17 ×3 / `image_va_words_pre` 406,576 / `image_va_words_new` 68,938 (3 回一致) / `threw` は `memory access out of bounds` (素材が古いため既知) |
| `m11_ptrcheck_negctl.sh` ×2 | 両回 `clean=68938`・`injected(offset=22519877)=68939`・`diff=1`・`NEGCTL OK`。wall 8.6 / 8.7 s |
| 基準 `M11_PTRCHECK_MAX_NEW=68938` (= クリーン実測) | rc 0 (合格) |
| 基準 `M11_PTRCHECK_MAX_NEW=68937` (1 小さい) | rc 1。stderr: `FAIL: ptrcheck image_va_words_new=68938 > max=68937 (M11_PTRCHECK_MAX_NEW)` |

**変更前後の比較 (boot runner の KPI)**: 変更前 HEAD `71bf0957` でも同じ素材で `m11_run.mjs` を実行し、`units_run` 17・`image_va_words_new` 68,938・rc 0 を得た。変更は検査の追加のみで、基準を設定しない既定の経路の数値は変わらない。製品の起動 KPI (`tools/flelift/boot/REPORT.md` の dispatch 数・通過 unit 数) は本 PR では動かしていない。

## 4. survey は未実行 (理由)

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
| fresh 再生成で run・survey の基準件数を実測し、`e2e_expect.env` に設定する | ゲートは e2e で有効化されていない (現在は情報出力のみ) | PM 起票を要求 (work-m11 素材の再生成手順。`REPORT_N1004.md` §4 と同じ) |
| survey の実行検証 (`_m11_set_va_unit_budget` を持つ wasm と IR 来歴の記録) | survey のゲートが未実行 | 同上 |
| 「残件 0」の判定基準 (LVA 整数と未 remap VA の区別) | 受入 1 の文言どおりの assert は未実装 | 親 #1004 / #403 で継続 |

## 7. 測定 commit からの差分

`git diff 53b90b53 -- tools/m11 ':!tools/m11/REPORT_N2778.md' | wc -c` の結果は **0** (コード差分 0 バイト)。本 REPORT の commit は REPORT_N2778.md と DOC_MAP の登録だけを変える。
