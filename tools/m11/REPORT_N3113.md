# M11 ptrcheck の新規 word の分類 (#3113・#2778 の残り)

親: #2778 (ratchet 版・closed)・#1004・#403。素材: work-m11 (`boot_final.ll`・`m11_boot.cjs.wasm`・既存 image)・fl-win64 (`extracted/block00031_PE.bin` のみ展開。ImageBase 0x400000)。
数値の測定 commit: **`f3aa9450`** (コードを変えた最後の commit。§3 の値はこの commit の code で取った。round 1 の測定 commit `4c796def` と同じ値)。
差し戻し対応 (round 2・3) で `m11_ptrcheck.mjs`・`m11_ptrclass.py`・`m11_ptrcheck_negctl.sh`・`e2e_expect.env` を直した。round 3 で `f3aa9450` の run・negctl を実測した (§3・§8)。
素材 image は `m11_image_gen.py` で作り直したものと byte 一致 (`cmp` 差分 0・DIR64 278,531 件補正済み)。IR の来歴記録 (`ir_conditions.json`) は素材に無い。

## 1. 結論

- 受入 1 (分類基準): **定めた** (§2)。IR・PE・image の 3 種の情報で 4 類に分ける。
- 受入 2 (残件 0 の検査・ネガコン): **run は測定 commit `f3aa9450` で達成** (§3)。`M11_PTRCHECK_UNREMAP_MAX=0` で合格 (分類 B 0 件)・注入 (分類 B 1 件) で不合格。**survey と `--survey` の negctl は未実行** (§5)。
- 受入 3 (REPORT・DOC_MAP): 本ファイル。`tools/m11/m11_ptrclass.py` を DOC_MAP に登録。
- 旧 #2778 の「値 0」を採らない理由 (LVA 整数) は変わらない。今回、その 68 語の正体 (イメージ由来の LVA コピー) が特定できた (§4)。
- 差し戻し対応後の HEAD (`f3aa9450`) の run・negctl は実測済み (§3)。`--survey` は素材の wasm が survey 用の export を持たず、開始できない (§5)。

## 2. 分類基準と根拠

`m11_ptrcheck.mjs` が新規範囲内 word `(offset, value)` を次の順で分ける (`m11_ptrclass.py` が作る `work/ptrclass/classes.json` を読む)。

| 類 | 定義 | 件数 (run・f3aa9450) | 根拠 |
|---|---|---:|---|
| **A** code_va | 値が IR の関数先頭 VA (`define @function_<VA>`) | 7,552 | `m11_icall` の target は VA (`m11_ov.c` の `ICALL_AT`・`icall_viaVA`)。関数ポインタを VA で持つのは設計どおりで、未 remap に数えない |
| **B** unremap_cand | 値が IR のポインタ定数 (`inttoptr (i64\|i32 N to ptr)`) で、範囲 `[0x400000, 0x1ec0000)` にあり、関数先頭でなく、PE の非実行セクションを指し、**かつ image の DIR64 地点の値ではない** | **0** | データの参照は LVA で持つ規則 (`REPORT_N1318` の VA→LVA)。VA のまま入れば未 remap の疑い |
| **D** image_copy | B と同じ条件だが、値が image の `.reloc` DIR64 地点に実行時の値として入っている | 68 | LB=0 では LVA = RVA で、VA 定数と数値が重なる。§4 でイメージ由来のコピーと確認 |
| **C** other | 上記以外 (整数・計算結果) | 61,318 | 値だけでは判定しない (`REPORT_N1004` §3・§5) |

A + B + C + D = 68,938 = `image_va_words_new` (一致)。

- 範囲と定数集合 (`classes.json`): IR の関数 7,421 / IR のポインタ定数 (範囲内) 8,828 / データ領域の定数 693 / うち image の DIR64 地点の値 68。
- 素材の指紋: IR `69c774de…` (`boot_final.ll`)・PE `b2c64da4…`・image `2d10d692…`。

## 3. 実測 (測定 commit f3aa9450・作業 runner・単独実行・素材 work-m11 / fl-win64 の展開後)

測定 commit `f3aa9450` の code の値 (= HEAD の code)。round 1 の測定 (`4c796def`) も同じ値だった。load average (1 分値): 0.27〜0.55 (測定の前後)。素材の指紋 (sha256 先頭): IR `69c774de`・PE `b2c64da4`・image `2d10d692` (REPORT の記載と一致)。

| 条件 | 結果 |
|---|---|
| `m11_run.mjs` 基準なし ×3 | rc 0 ×3 / wall 1.74–1.76 s / `units_run` 17 ×3 / `image_va_words_new` 68,938 (3 回一致) / `threw` は `memory access out of bounds` (素材の wasm が古いため既知・`REPORT_N2778` §3 と同じ) |
| 分類 (同 run) | A 7,552・B **0**・D 68・C 61,318 (合計 68,938) |
| `M11_PTRCHECK_UNREMAP_MAX=0` + `M11_PTRCHECK_MAX_NEW=68938` | rc 0 (合格・wall 1.74 s) |
| `m11_ptrclass.py` | code 7,421・ptr 定数 8,828・data 693・D 68 |
| `m11_ptrclass.py --hits` (D の block copy) | D 68 語すべて `heap − site` = `0xf069750` |
| `M11_PTRCLASS=<無いパス>` + 基準 0 | negctl の (e) で rc 1 (fail-closed) を確認 |
| `m11_ptrcheck_negctl.sh` | `NEGCTL OK`・wall 18.0 s。`clean=68938` / `injected(0x400000 @22519877)=68939` (diff 1)・`unremap_cand clean=0 injected(0x153fb68)=1`。基準 = クリーンで exit 0・注入で exit 1 + `FAIL: ptrcheck unremap_cand=` |
| `m11_ptrcheck_negctl.sh --survey` | **開始前に失敗** (rc 1)。`m11_survey.mjs:21` の `mod._m11_set_va_unit_budget` が `is not a function` (§5) |

- 注入値 `0x153fb68` は B の定数 (データ領域 VA・image の DIR64 地点の値ではない) で、既知の未 remap 値の代わり。注入は D にならないことも同時に確かめる。
- 変更前後の製品 KPI: 変更は検査の追加のみ。`units_run` 17 は変更前後で同じ。起動・GUI の挙動は変えていない (`tools/flelift/boot/REPORT.md` の値は動かしていない)。

## 4. D の 68 語がイメージ由来の LVA コピーである根拠

- 68 語の値はすべて image の `.reloc` DIR64 地点に入っている値 (補正済みの LVA) と一致する。たとえば `image 0x11dfc48 = 0x153fbf0` は、PE 上の VA `0x193fbf0` を `image_gen` が LVA に補正した値。
- ヒープ側の位置 (word の offset) と、対応する image の DIR64 地点の差 `heap − site` は **68 語すべて `0xf069750`** (`m11_ptrclass.py --hits`)。ヒープは image の連続領域 (ポインタ表) を一括コピーしたもので、個々の値の偶然の一致ではない。
- 同じ値の IR 参照先 (`ir_use_fn`) は 68 語に分散する (`work/ptrclass/hits_head.txt`)。`load` のアドレスとして使う関数もある。このため「IR の VA 定数が未 remap でそのまま入った」とは判定しない。

## 5. survey と `--survey` の negctl は未実行 (理由)

- `m11_survey.mjs` に分類 B の基準 (`M11_PTRCHECK_SURVEY_UNREMAP_MAX`) と FAIL 行を配線した。`node --check` のみ通過。
- 素材の wasm (`work/m11_boot.cjs.wasm`) は `_m11_set_va_unit_budget` を持たない古い build で、survey は開始できない (`REPORT_N1004` §2・`REPORT_N2778` §4 と同じ)。
- 再ビルドは IR 来歴の記録 (`ir_conditions.json`) が無いため `m11_build.sh` が拒否する。迂回した wasm は測定の根拠にしない。
- `bash m11_ptrcheck_negctl.sh --survey` は一度も NEGCTL OK になっていない。(a)〜(e) はすべて未検証で、特に分類 B の (c)〜(e) は survey で走っていない。survey 用の wasm の作成は #3129。
- 差し戻し対応 (round 2) の run での確認 (素材 work-m11 が無かった時点の記録): `bash m11_ptrcheck_negctl.sh --survey` と `bash m11_ptrcheck_negctl.sh` は、どちらも `NEGCTL FAIL: work/ に wasm/image が無い (素材 work-m11 未展開)` (rc 1)。その run の `$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみだった。
- round 3 の run での確認 (素材 work-m11 あり・HEAD `f3aa9450`): wasm と image はある。`bash m11_ptrcheck_negctl.sh --survey` は開始前に rc 1 で止まる (`clean 実行が失敗`)。原因は `m11_survey.mjs:21` の `mod._m11_set_va_unit_budget(budgetMb)` が `TypeError: mod._m11_set_va_unit_budget is not a function` になること (wasm の export に無い。`WebAssembly.Module.exports` で確認)。`m11_ptrcheck_negctl.sh` のヘッダの「素材 work-m11 が無く」は round 2 時点の記述で、現状の原因は上の export の欠落。

## 6. 限界

- B は IR に定数として現れる VA だけを見る。計算で作られた VA・IR に定数の無い VA は判定外 (C)。
- D の判定は「image の DIR64 地点と同じ値」による。真の未 remap が同じ数値の image ポインタと一致する場合は取り違える (偽陰性)。LB=0 では VA と LVA の数値の重なりを構造上避けられない (LB≥0x1ec0000 以外の全 LB で範囲が重なる)。
- 基準 0 は本素材 (f3aa9450 の実測・round 1 の `4c796def` と同じ値) の実測。fresh 再生成 (IR 来歴付き) の実測は未実施 (追跡先 #3129)。本素材の run 件数 68,938 は、`REPORT_N2778` §8 の fresh 再生成の run 件数 69,359 と一致しない。そのため fresh 再生成での分類 B の件数は、この 2 つのどちらとも未測定。
- 素材の `functions_dll.csv` 不足で `m11_e2e.sh` の全再生成が落ちる (`REPORT_N1004` §3)。そのため `e2e_expect.env` の `M11_EXPECT_PTR_UNREMAP_MAX` は既定で未設定 (情報出力のみ)。
- `m11_e2e.sh` は `m11_ptrclass.py` を IR 生成の後に実行する。基準を設定したのに `classes.json` が無ければ fail-closed で不合格になる。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| survey の実行 (`_m11_set_va_unit_budget` を持つ wasm と IR 来歴の記録が要る)・`--survey` の negctl (a)〜(e) | survey の分類 B ゲートが未実行 | 子 #3129 ([M11-N170])。依存の参考 #3122 |
| fresh 再生成で run の分類 B 基準 (0) と A・B・D・C 件数を実測し、`e2e_expect.env` に設定 | e2e での分類 B ゲートが既定で無効 | #3129 (再現手順と素材は同 issue のコメント https://github.com/signature-studio/signature-studio-dev/issues/3129#issuecomment-6180450191)。#2778 は closed のため使わない |

## 8. 測定 commit からの差分と HEAD の扱い

round 1 の測定 commit `4c796def` から、§3 の測定 commit `f3aa9450` までに `tools/m11` のコードが変わった。REPORT_N3113.md を除いた差分は次のとおり。

```sh
git diff --stat 4c796def f3aa9450 -- tools/m11 ':!tools/m11/REPORT_N3113.md'
# 18 files changed, 1760 insertions(+), 876 deletions(-)
```

- そのうち round 2 で入った変更 (`9dff18da` → `f3aa9450`) の非 `.md` は 4 ファイル: `m11_ptrcheck.mjs` (`fileURLToPath` によるパス解決・検証用 env の整数検査)・`m11_ptrclass.py` (負の差分の表示)・`m11_ptrcheck_negctl.sh` (ヘッダに `--survey` 未検証を明記)・`e2e_expect.env` (B2 のコメント)。
- 残りは main 取り込み (`9dff18da`) による変更。分類 B の判定ロジックは 4c796def と同じで、round 2 の変更はパス解決・検証用 env の検査・表示だけ。
- §3 の値は `f3aa9450` の code で取った実測。`f3aa9450` の後の HEAD が REPORT と PR 本文だけを変える commit なら、§3 の値はその HEAD でも有効 (`git diff f3aa9450 HEAD -- tools/m11 ':!*.md'` が 0 行)。

## 9. 再現

```sh
export FL_WIN64_DIR=<展開先>                       # block00031_PE.bin を含む extracted/ の親
cd tools/m11
python3 m11_ptrclass.py                            # work/ptrclass/classes.json
M11_PTRCHECK_DUMP=work/ptrclass/new.txt node m11_run.mjs
python3 m11_ptrclass.py --hits work/ptrclass/new.txt   # 分類 B・D の内訳と block copy の差分
bash m11_ptrcheck_negctl.sh                        # NEGCTL OK
bash m11_ptrcheck_negctl.sh --survey               # survey 版 (wasm が要る・§5)
```
