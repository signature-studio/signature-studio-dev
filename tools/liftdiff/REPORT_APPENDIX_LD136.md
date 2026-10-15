# liftdiff REPORT 付録: LD-136 (#2841) shim block_ok 修正後の 1801c5e84 u16 trap の消失・site trace・12 case 比較

親 issue #2802 (LD-132・shim の `block_ok` 範囲検査 `a4a620a9`)。前版 LD-83 (#2192・`REPORT_APPENDIX_LD83.md`)。HeapFree 応答の変更 LD-133 (#2821・`7278e8571`)。

## 結論

- 受入 1 (trap の消失): 測定 commit `6ead9dcc1` で `targets/ott_old.json` (既定)・`ott_old_blk.json` (計装)・`ott_old_site.json` (site 計装) を build し、`1801c5e84` の vm0・u16 を測った。raw を持つ 8 case はすべて wasm `status = ok` (trap 0)。LD-83 の `wasm_trap` (u16) は消えた。
- 受入 2 (site trace): u16 の wasm 側は HeapFree の call site `C801c0b71` を **5 回** 記録する。native の HeapFree も 5 回 (`native_calls 5`)。各回の戻り br `J801c0b71.1=1` (TRUE) の後は `B1801c0ba8` へ進み、`1c5eb8 → 1c0b6c` のループを経て `B1801c5ecc` で終わる。trap 地点の後続 block は欠けずに取れる。
- 受入 3 (12 case): `results/ld67/compare_blk.py` で既定 vs 計装 (`ott_old_blk`) と既定 vs site (`ott_old_site`) を r1・r2 とも `cases=12 diff=0`。site trace の JSON は r1 と r2 でバイト一致 (`cmp`)。
- 受入 4 (製品 KPI の前後): gui flengine の e2e を `a4a620a9^` (前) と `a4a620a9` (後) で各 1 回測った。前後で KPI は変わらない (§5・§7)。

## 1. 測定条件

- 測定 commit: `6ead9dcc1` (origin/main。`a4a620a9` (#2802)・`7278e8571` (#2821) を含む)。本 PR はこの commit から REPORT 付録 1 本と `docs/DOC_MAP.md` の 1 行だけを足す。コードは変えていない (§4)。
- 素材: `work-m6-ott` (`tools/{ott,m6,m8,m9,m10}/work`)・`work-liftdiff` を worktree に展開。展開後に絶対 symlink 68 本を worktree 内へ張り直した。`analysis-ott-binaries` は `[ANALYSIS-PLUGINS]` の `ott/binaries/` に展開。`toolchain-emsdk` は `[EMSDK]` (`build_wasm.py` が `emsdk_env.sh` を読む)。
- build: `python3 ldlib/build_wasm.py targets/<t>.json --force` (`ott_old`・`ott_old_blk`・`ott_old_site` とも rc 0・`sig_mismatch` 0・`undefined` 0)。site の stderr は `sites skipped (block without dec_label_pc_ VA): 21` で LD-83 と一致。
- run: `python3 liftdiff.py run targets/<t>.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --json <out>`。各 run は約 5 秒 (`time` 実測)。r1・r2 の 2 回。
- 集計: `results/ld67/compare_blk.py` (既定 vs 計装)・`results/ld83/decode_sites.py` (site 記録の分解)。LD-83 のツールをそのまま使った。
- runner: 4 vCPU。`uptime` 未取得 (run は 5 秒だから load の影響は小さい)。

## 2. 結果 (測定 commit `6ead9dcc1`・r1)

`blocks / J / C / sites / 計` は `decode_sites.py` の出力 (`sites` = J + C、`計` = blocks + sites)。`ord` は全 case `ok`、`blk_over` は 0。

| 関数 | pattern | 既定 outcome (3 build 同一) | wasm status | blocks / J / C / sites / 計 | native calls (`native_len`) |
|---|---|---|---|---|---|
| 1ab1d0 | vm0 / u16 | equal | (raw 無し) | 0 | 0 |
| 1ab258 | vm0 / u16 | equal | (raw 無し) | 0 | 0 |
| 1c5e84 | vm0 | diff | ok | 18 / 12 / 1 / 13 / 31 | 1 |
| 1c5e84 | u16 | diff | ok | 22 / 16 / 5 / 21 / 43 | 5 |
| 1c621c | vm0 | diff | ok | 278 / 179 / 1 / 180 / 458 | 1 |
| 1c621c | u16 | diff | ok | 283 / 184 / 6 / 190 / 473 | 6 |
| 1c682c | vm0 | diff | ok | 33 / 29 / 1 / 30 / 63 | 1 |
| 1c682c | u16 | diff | ok | 34 / 30 / 1 / 31 / 65 | 1 |
| 1c69cc | vm0 | diff | ok | 286 / 184 / 2 / 186 / 472 | 2 |
| 1c69cc | u16 | diff | ok | 291 / 189 / 7 / 196 / 487 | 7 |

- 既定 build と計装 build の差は 0 (12 case)。計装の有無で outcome・wasm status・rax・x0 は変わらない。
- `1c5e84` の br `1c0b6c` (je 相当): u16 の 5 回は全て cond = 0 (je 不成立)。native (u16) の `rcx` と一致する (LD-83 §4 と同じ)。
- `1c5e84` vm0 の最初の HeapFree (`C801c0b71.0`): 戻り br `J801c0b71.1=1` (TRUE)。

## 3. LD-83 (`ed712942`) からの変化: HeapFree 応答

- LD-83 は main `83e7bde5` で測った。その時の wasm は範囲外 p の HeapFree で FALSE を返し、戻り br が偽 (`1c0b8c` へ) になっていた。
- 現 HEAD の `tools/shim/src/heap.c` は `7278e8571` (#2821) で「割当てのない p は解放せず TRUE を返す」に変わった (`git diff ed712942 6ead9dcc1 -- tools/shim/src/heap.c` の 5 行)。LD-83 の `J801c0b71.1=0` が、今回は `=1` になった。
- そのため件数は LD-83 の表と一致しない (例: `1c5e84` vm0 は LD-83 27 blocks・計 48 → 今回 18・31。u16 は 67・128 → 22・43)。trap の有無・12 case の差 0 の結論は変わらない。
- `ret` の差 (native `0x1` vs wasm `0xffffffffffffffff` 等) と native 側の余分な HeapFree 呼出しは、全 diff case に残る。これは LD-133 (#2821) の未解決項目 (GlobalFree・LocalFree の応答) とは別の差分で、本 issue の受入外。

## 4. 測定 commit と差分

- 測定 commit: `6ead9dcc1`。
- `git diff 6ead9dcc1 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/targets tools/liftdiff/results tools/shim tools/ott/rt tools/m6` の出力: 0 行 (本 PR は REPORT 付録と `docs/DOC_MAP.md` の 1 行だけ)。よって測定値の再測定は要らない。

## 5. 受入 4 (製品 KPI の前後) — 実施 (§7)

前後の値は §7。修正 `a4a620a9` は `tools/shim/src/heap.c` にあり、`tools/flelift/boot` の build (shimx) は heap.c を取り込まないため、boot 経路の KPI では効果を測れない (`grep heap.c tools/flelift/boot/*.sh` で 0 件)。本付録は `tools/gui/flengine/e2e.sh` (heap.c を取り込む) で測った。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 命令単位の完全 trace (RetDec IR に命令 VA が無い) | site 単位の対応まで | #2801 (LD-131) |
| 本測定は `--notrace` のため wasm 側の `calls` 欄が空。import 呼出しの対比は site 記録の `C` で代用 | wasm 側の HeapFree 引数・戻り値の直接比較は未実施 | 本付録の §2 のみ (起票無し) |

## 7. 製品 KPI の前後 (受入 4・gui flengine の e2e)

- 前: `a4a620a9^` = `740344ccc`。後: `a4a620a9` (#2802 の差分は `tools/shim/src/heap.c` +6/−1 と `tools/shim/test/test_main.c` +20 だけ)。
- 実行: 各 commit の detached worktree で `ANALYSIS_DIR=<RUNNER_TEMP> FL_WIN64_DIR=<RUNNER_TEMP>/fl-win64 EMSDK_ENV=[EMSDK]/emsdk_env.sh RETDEC=[RETDEC]/bin/retdec-decompiler bash tools/gui/flengine/e2e.sh` を foreground で 1 回ずつ。`fl-win64` は 1 回だけ展開した (19 秒)。

| 項目 | 前 (`740344ccc`) | 後 (`a4a620a9`) |
|---|---|---|
| e2e の done 行 | 405 s (rc 1) | 398 s (rc 1) |
| judge | 13/14 (S1 FAIL: 872/1/47/22/0 対 base 870/1/47/24/0) | 同じ |
| B1 boot parity (`units_run`・GetMem・FreeMem・icall_miss) | 52 (base 52) · 560 · 20 · 5 | 同じ |
| R2 reach floor | 33 (floor 19) | 同じ |
| P4 TApplication の window (hwnd) | created PASS `0x110000f` | 同じ |
| P5 TLightweightLayeredControl の window (hwnd) | created PASS `0x110000e` | 同じ |
| native selftest | 506 passed / 0 failed | 同じ |
| ネガティブコントロール N1〜N9 | 期待どおり FAIL | 同じ |
| baseline の `wasm_size` | 6914481 | 6914538 (+57 B) |

- rc 1 は S1 gate の FAIL による。前後とも同じ FAIL で、修正由来ではない (REPORT `tools/gui/flengine/REPORT.md` §6 の 14/14 は別 HEAD の値)。
- 解釈: 最初のウィンドウ (P4・P5 の window 作成) と通過 unit 数 (52) は修正の前後で変わらない。dispatch 数は e2e の出力に無く、本測定では取っていない。`tools/flelift/boot` の 209 dispatch は shimx の経路で、本修正の影響は無い。
- 起動の進み方は同じ。製品の起動を変える効果は、この gui 経路では確認できなかった。
