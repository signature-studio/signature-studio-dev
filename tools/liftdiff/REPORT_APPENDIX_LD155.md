# liftdiff REPORT 付録: LD-155 (#3384) wasm 持ち越しの静的変数の内訳と RESET の証跡

親 #2723 (LD-126)・子 #3384 (LD-155)。前提は `REPORT_APPENDIX_LD126.md` (候補 `sta` が 4/18 match)。

測定 commit: **`1fc351661`** (コードを変えた最後の commit。`rt/ld_wasm.c`・`rt/ld_runner.mjs`・`ld126_wasm_state.py`)。
結果: `results/ld155_carryover_candidates.tsv` (`tools/liftdiff/results/`)。

## 結論

- `sta` の 4/18 match は、**heap 管理変数 4 個 (`ld_heap_used`・`ld_heap_hw`・`ld_heap_pristine_len`・`ld_heap_pristine_used`) だけを戻しても再現する** (`heapmgr` = 4/18・同じ 4 件)。`sta` の効果は heap 高水位の管理変数にある。
- malloc 管理変数 (`ld_blks`・`ld_nblk`) と g_inbuf (入力バッファ) は、単独では効果が無い (0/18)。
- RESET の証跡: 戻したバイト数は、heapmgr で 40 B・mallocvar で 20 B・inbuf で 2,360,869 B・sta で 409,128 B (chunk 1 の 18 件の合計)。戻す対象が snapshot と異なることが確認できた。
- 受入 (d) (スタック復元が `sta_img` の効果を打ち消す機構) は**未達**。本付録では測っていない。

## 1. 測定条件

- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-liftdiff`・`work-m11`。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- wasm: `build_wasm.build(m11, True)` (`wasm_size` 4464314・`sig_mismatch` 0)。
- 機: 4 vCPU・RAM 15 GiB。並列 4 本 (`heapmgr`・`inbuf`・`mallocvar`・`sta`) の wall 239〜288 s。`none` は単独で wall 254 s。load は未記録 (n=1)。
- 候補: `heapmgr` (mask 16)・`inbuf` (32)・`mallocvar` (64)・`sta` (2・新しい区分で heapmgr・inbuf・mallocvar を除く)。対照 `none` (0)。

## 2. 方法

- `ld_wasm.c` の `ld_rst_sta` で、`[__global_base, stack_end)` から g_heap・g_arena・g_inbuf と、新カテゴリの変数 (heap 管理 4 個・malloc 管理 2 個) を引いた残りを STA として登録する。
- `ld_w_reset(mask)` は、戻す前に選んだ区間の現在値と snapshot の違う byte 数を数えて返す (証跡)。`ld_runner.mjs` の RESET 応答 `{"reset":m,"diff":n}` を Python 側が読み、`<out>.reset.json` に保存する。

## 3. 結果 (chunk 1 の 18 対象関数・n=1)

| 条件 (RESET) | match | mismatch | 戻したバイト数 (18 件の合計) |
|---|---|---|---|
| `none` (対照) | 0 | 18 | 0 |
| `sta` (heap 管理・malloc 管理・inbuf を除く静的変数) | 4 | 14 | 409,128 |
| `heapmgr` (heap 管理変数 4 個) | 4 | 14 | 40 |
| `inbuf` (g_inbuf 全体) | 0 | 18 | 2,360,869 |
| `mallocvar` (ld_blks・ld_nblk) | 0 | 18 | 20 |

- `heapmgr` の match は `sta` と同じ 4 件: `0x50ab90`・`0x4bf600`・`0xb77200`・`0x7850d0`。
- 診断 (`--limit 306`・`0x50ab90` 含む chunk 先頭 306 件) の `heapmgr` は `0x50ab90` が match (戻したバイト数 20)。

## 4. 読み取り

- `sta` の効果は heap 管理変数 4 個に集中している。残りの静的変数 (`sta` から heapmgr を引いた分) を戻しても、新たな match は出ていない。
- heap 管理変数は 40 B しか戻らないのに効果が出る。heap 高水位の管理値が case 間で残ると、後続 case の heap 割当が変わるという機構が疑われる (未検証)。
- g_inbuf (約 2.3 MB 戻る) と malloc 管理変数は効かない。
- 注意: 本付録は n=1。`heapmgr` の 4 件が再現するかは未確認。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 (d): スタック復元が `sta_img` の効果を打ち消す機構 (スタックのどの範囲・どの読みが効くか。`ld_w_case_begin` の 128KB 0 埋めの外側を読んでいるか) | 候補の相互作用の説明 | #3384 (次の run) |
| 候補の n=2 反復 (本付録は n=1) | 結論の再現性 | #3384 (次の run) |
| heap 管理変数 4 個が効く機構 (どの読みが 40 B の差を結果に変えるか) | 持ち越しの説明 | #3384 (次の run) |
| malloc 領域の中身 (`ld_blks` 以外の dlmalloc 管理情報と、heap 領域の残存) | 候補に含めていない | #3384 (次の run) |

## 6. 差分と測定の鮮度

- 測定 commit `1fc351661` 以降、実行コード (`tools/liftdiff/rt`・`tools/liftdiff/ld126_wasm_state.py`・`tools/liftdiff/ldlib`) の差分は 95 行 (main 取り込み由来。`git diff 1fc351661 e27283d81 -- tools/liftdiff/rt tools/liftdiff/ld126_wasm_state.py tools/liftdiff/ldlib | wc -l` = 95)。内訳は `ldlib/session.py` の fvm 候補の対象外判定 (`fvm_cand`・`ret_fragment`・`multi_candidate`)、`ldlib/pe.py` の `is_ret_fragment`、`ldlib/cases.py` の `MACHINE_ENTRY` への 6 件追加 (`442a50`・`442b90`・`664890`・`6649b0`・`6649c0`・`664a80`)。`rt/` (C・runner) は変わっていない。
- 再測定はしていない (`work-m11` の `boot_final3.ll` が runner に無く、`ldlib.build_wasm` が再生成できないため。D5 により m11 の IR 再生成は新規作業にしない)。代わりに、差分が chunk 1 の 18 件の結果に影響しないことを次で示す:
  - `MACHINE_ENTRY` は `cases.machine_sig(va, ...)` で解析中の VA 自身にだけ掛かる。追加 6 件の VA は chunk 1 の 18 件 (`ch1` = TSV の VA 列) に 1 件も含まれない。
  - 18 件の結果 (`none`・`sta`・`heapmgr`・`inbuf`・`mallocvar`) はいずれも `mismatch` (計 90 セル)。fvm 分岐 (`session.py` の `_run_one`) は「`equal`・`diff`・`wasm_trap` の case が 1 件も無い関数」だけに入るため、判定の入口が 18 件の `mismatch` とは両立しない (`classify.verdict` は `diff`/`wasm_trap` が 1 件でもあれば `mismatch`)。よって fvm の対象外判定の変更は 18 件の判定を変えない。
  - `MACHINE_ENTRY` の全 11 キー (追加 6 件を含む) は chunk 1 の 18 件のどれにも含まれない (`python3` で照合)。`compare.py` の `ir_params` (i128 位置の除外) は `machine_sig` が差し替えた VA にしか付かないため、18 件の比較は変わらない。
- 本 PR が追加した REPORT・結果 TSV は実行コードではないため、範囲から外す。

## 7. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd tools/liftdiff
python3 -c "from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), True)"
printf '%s\n' none sta heapmgr inbuf mallocvar | xargs -P 4 -I{} sh -c 'python3 ld126_wasm_state.py --reset {} --out work/ld126/{}.jsonl > work/ld126/{}.log 2>&1'
```

生データは `work/ld126/` (gitignore)。戻したバイト数は `work/ld126/<条件>.jsonl.reset.json`。
