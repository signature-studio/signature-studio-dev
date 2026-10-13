# #130 survey trap 再測定と残 trap の切り分け (2026-10-13)

**判定: 部分達成 (trap 25、完了条件 < 20 は未達)**。本 run はコード変更なし。main `97f28539` (merge `a6b58d7e`) を再ビルドして実測し、残 trap の原因候補を切り分けた。

## 1. 実測 (main `97f28539` (merge `a6b58d7e`)、コード変更なし)

素材: `fl-win64` (block00031_PE.bin のみ展開), `work-m11` / `work-liftdiff` (`tools/m11/work/`, `tools/liftdiff/work/` へ展開), `toolchain-emsdk` ([EMSDK])。`capstone` / `pefile` は `$RUNNER_TEMP/pyenv130` (pip) で導入。

`bash tools/m11/m11_e2e.sh` (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`):

| 項目 | 値 |
|---|--:|
| wall | 30 s (HEAD a6b58d7e = main `97f28539` を merge した状態。emcc 増分ビルド済みで実測。初回 96 s は emcc 込み。load avg 0.54/0.65/0.42) |
| reached_stage | 4/6 (不変) |
| units_run (通常起動) | 53 (※ 前回記録 17 から変化。IR 再生成後の値) |
| survey ok | **870** |
| survey trap 計 | **25** (oob 17 + halt0 8。oom は halt0 の併発 1 件 = unit 368 で、独立カテゴリではない) |
| survey miss / noproc / clobber | 46 / 1 / 0 |
| ir_conditions | ldfix applied / qstore applied |

`node tools/m11/trap_triage/survey_units.mjs` (per-unit JSON): trap 25 件の内訳は下表。

| 群 | unit | 最上位 frame | 状態 |
|---|---|---|---|
| halt0 (`411d20` raise 経由) | 245 279 647 | `412770` ← `4128b0` ← `412a40` ← `412a60` ← `411d20` ← `411e80` ← `814d30` (245・279・647) | 原因候補あり (§2) |
| halt0 (`411d20` raise 経由・別経路) | 509 | `412770` ← `4128b0` ← `412a40` ← `412a60` ← `411d20` ← `411e80` ← `b41bb0` | 未調査 (`814d30` を通らない) |
| halt0 (`4096b0` 経由) | 314 368 895 | 314・368 は `412a40`→`4096b0`→`4096d0`→`40f560`/`409730`、895 は `412a40`→`4096b0`→`40c820`→`40ffe0` (314 は `8dc210`, 368 は `409730`, 895 は `40ffe0`) | 未調査 (368 は oom 併発) |
| halt0 (`4096b0` 経由) | 114 | `412770` ← `4128b0` ← `412a40` ← `4096b0` ← `4096d0` ← `41a800` ← `8494c0` ← `86b9a0` ← `867710` ← `620cd0` ← `623840` (VA `0x223840`) | 未調査。上位 9 frame に `410630` は出ない。MessageBox の帰属は根拠なし |
| oob | 56 | `8c6530` ← `8c5eb0` ← `56fde0` | 未調査 (旧 §8 の `8cc190` 系とは別) |
| oob | 144 745 | `407e20` ← `409440` | 未調査 |
| oob | 149 | `412e40` ← `653660` ← `6539e0` | 未調査 (`414bb0` 系) |
| oob | 275 | `864fe0` ← `80e040` | 未調査 |
| oob | 280 659 | `6cefb0` ← `815050` ← `815e10` | 未調査 |
| oob | 304 555 | `535bf2` ← `535c11` ← `4fad10` (VA-big 125 MB) | 未調査 |
| oob | 477 484 513 520 | `903e00`/`903d20` ← `904190` | 未調査 |
| oob | 492 | `4133f0` ← `4473f0` ← `446400` | 未調査 |
| oob | 830 880 | `10c7cd0` / `125da90` (stub 呼出あり) | 未調査 |
| oob | 923 | `410b10` ← `410730` ← `4fb910` | 未調査 |

## 2. halt0 の 3 unit (245 279 647) の経路 (509 は別経路)

`814d30` (`Exception.Create` 系の raise helper) が `448ee0` を呼び、その第 1 引数に定数 `inttoptr i64 200376` (= 0x30eb8, VA 0x430eb8 の RVA 形) が入る。対象は 245・279・647 (`411e80`→`814d30`)。509 は `411e80`→`b41bb0` で `814d30` を通らないため、ここには含めない。

- PE 上の global `0x430df0` (`814da1` の `mov rcx,[rip-0x3e3fb1]` の参照先) の値は `0x00430eb8`。IR の定数 `200376` (= 0x30eb8) はこの値の RVA 形 (`LB_BASE=0`) と一致する。**したがって「VA 未変換」(D11 直撃) は否定**。REPORT.md §6-2 の 10 進 inttoptr 類型とは別と判断する。
- `448ee0` は引数 `arg2` (=1) が非 0 で `410320` を経由する分岐に入る。`410320` (`_ClassCreate`) の戻り値は `function_40f960`/`41c160` の C 転記に依存するため、そこが 0 を返すと `448ee0` が 0 を返し、`411d20` が `arg1 == 0` 分岐で `412a60` (Runtime error 216) へ落ちる。
- **未解決 (推定の段階)**: 0x30eb8 の指す class の VMT 解決 (`410320` の `m11_icall` 経路) で 0 になる理由は未特定。REPORT.md §6-2 の M2p 全件 remap は採用しない。

## 3. 未解決 (起票先)

- halt0 3 unit (245 279 647) の `814d30` → `448ee0` の VA 定数化 (D11 変種)。修正方針は個別 override で `814d30` の分岐値を正す案。起票先: 本 issue #130 の後続 (PM 起票依頼)。
- halt0 509 (`b41bb0` 経路)・314 368 895・114 の個別原因。起票先: PM 起票依頼。
- oob 17 件の個別原因 (最上位 frame は §1 の表)。起票先: PM 起票依頼。
- 完了条件 (trap < 20) は未達 (25)。あと 6 件以上の削減が必要。

## 4. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH="$RUNNER_TEMP/pyenv130/bin:$PATH"
bash tools/m11/m11_e2e.sh
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/base130.json
```

注: `work-m11` の `obj/rt.o`・`obj/win.o` は snapshot 由来の古い obj で、`m11_rt.c` の新関数 (`m11_set_va_bigtrace`) が欠けて emcc が fail-closed で落ちた。削除して再ビルドすると通る。

## 5. 追補 (2026-10-13, 再着手 run): M11_FIX_535BF2=1 の実測 (負の結果)

基準 HEAD `36edc993` (main) を再ビルドして baseline を再現し、`m11_ov.c` の `M11_FIX_535BF2` 既定を 1 にした build と比較した (コードは commit せず、測定後に 0 へ戻した)。

| 項目 | baseline (既定 0) | M11_FIX_535BF2=1 |
|---|--:|--:|
| e2e wall | 125.8 s (初回 emcc 込み) | 38.6 s (増分) |
| survey ok / trap / miss | 870 / 25 / 46 | 870 / 25 / 46 |
| trap kinds | OOB 17 / halt0 8 (oom 1 併発) | OOB 17 / halt0 8 (同左) |
| top frame `function_535bf2` | x2 | 0 (代わりに `function_410010` x2 が出現) |

- `535bf2` の closure 外呼出し (`function_535c2e`) は、転記で消えても trap 数は変わらない。unit 304・555 の OOB は `535bf2` の境界条件では解けず、呼出元の `tbl`/`cnt` の値 (`obj` の生成元) が原因と判断する。`#714` の次の一手に従う。
- `function_903e00` 系 (unit 477 484 513 520) は `#684` (`903d20` ← `904190`) で追跡済み。本 run では未着手。
- 完了条件 (trap < 20) は引き続き未達 (25)。残 trap の既存の追跡先 (issue 本文の対象での照合): 304・555・923 → #714 / 477 (+484・513・520 は `904190` 系) → #684・#596 / halt0 22・245・279・509・647 → #860 / halt0 492 → #862 / halt0 189 → #861 / oob 149 → #748 / oob 95・895 → #882 / oob 275 → #881 / oob 56 → #856 / oob 280・659 → #878。

再現: `export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH="$RUNNER_TEMP/pyenv130/bin:$PATH"; bash tools/m11/m11_e2e.sh`
