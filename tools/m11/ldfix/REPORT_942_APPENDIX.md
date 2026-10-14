# #942 REPORT 付録: §8-3 trap 最上位 frame 表 (#1292)

本体 REPORT_942.md §8-3 の全文。250 行上限のため分割移動 (内容は削除していない)。

### 8-3. 受入 4: trap 最上位 frame と #942 の結論

`tools/m11/ldfix/trap_units.mjs` で base 26 件・fix 24 件すべての unit の最上位 frame を取得 (`S4_NAME=base|fix`)。frame の IR 関数名は `m11_wasmnames.py` で変換。F3a/F3c は `ldfix_report.json` の `f3a_vas` / `f3c_vas` と突合。

**base (ldfix 無し IR)**

| unit VA | 種別 | 最上位 frame | IR 関数 | F3a/F3c |
|---|---|--:|---|---|
| 0x16fde0 | unreachable | 3473 | function_8c5eb0 | 無し |
| 0x223840 | halt0 | (frame 無し) | - | - |
| 0x25c540 | halt0 | (frame 無し) | - | - |
| 0x264260 | OOB | 75 | function_412e40 | 無し |
| 0x26d1a0 | OOB | 707 | function_413540 | **F3a** |
| 0x333090 | halt0 | (frame 無し) | - | - |
| 0x40e170 | OOB | 389 | function_864fe0 | 無し |
| 0x4136d0 | halt0 | (frame 無し) | - | - |
| 0x416010 | OOB | 4476 | function_6cefb0 | 無し |
| 0x483140 | OOB | 3372 | function_535bf2 | 無し |
| 0x4e48a0 | halt0 | (frame 無し) | - | - |
| 0x6bfd60 | OOB | 5371 | function_903d20 | 無し |
| 0x6d0680 | OOB | 5372 | function_903e00 | 無し |
| 0x6d5700 | OOB | 14873 | function_4133f0 | **F3a** |
| 0x6d9ba0 | halt0 | (frame 無し) | - | - |
| 0x739ca0 | halt0 | (frame 無し) | - | - |
| 0x7654c0 | OOB | 5372 | function_903e00 | 無し |
| 0x776bf0 | OOB | 5372 | function_903e00 | 無し |
| 0x7f2500 | OOB | 3372 | function_535bf2 | 無し |
| 0x897ac0 | halt0 | (frame 無し) | - | - |
| 0x8eaa30 | OOB | 4476 | function_6cefb0 | 無し |
| 0xabb3b0 | OOB | 1875 | function_407e20__lifted | 無し |
| 0xcd50d0 | OOB | 711 | function_10c7cd0 | 無し |
| 0xe63540 | OOB | 1158 | function_125da90 | 無し |
| 0xeddfe0 | OOB | 2001 | function_40ff70 | 無し |
| 0xf6c660 | OOB | 14900 | function_410b10 | 無し |

**fix (ldfix 適用 IR)**

| unit VA | 種別 | 最上位 frame | IR 関数 | F3a/F3c |
|---|---|--:|---|---|
| 0x16fde0 | unreachable | 3473 | function_8c5eb0 | 無し |
| 0x223840 | halt0 | (frame 無し) | - | - |
| 0x25c540 | OOB | 1875 | function_407e20__lifted | 無し |
| 0x264260 | OOB | 75 | function_412e40 | 無し |
| 0x333090 | halt0 | (frame 無し) | - | - |
| 0x40e170 | OOB | 389 | function_864fe0 | 無し |
| 0x4136d0 | halt0 | (frame 無し) | - | - |
| 0x416010 | OOB | 4476 | function_6cefb0 | 無し |
| 0x483140 | OOB | 3372 | function_535bf2 | 無し |
| 0x4e48a0 | halt0 | (frame 無し) | - | - |
| 0x6bfd60 | OOB | 5371 | function_903d20 | 無し |
| 0x6d0680 | OOB | 5372 | function_903e00 | 無し |
| 0x6d5700 | OOB | 14873 | function_4133f0 | **F3a** |
| 0x739ca0 | halt0 | (frame 無し) | - | - |
| 0x7654c0 | OOB | 5372 | function_903e00 | 無し |
| 0x776bf0 | OOB | 5372 | function_903e00 | 無し |
| 0x7f2500 | OOB | 3372 | function_535bf2 | 無し |
| 0x897ac0 | halt0 | (frame 無し) | - | - |
| 0x8eaa30 | OOB | 4476 | function_6cefb0 | 無し |
| 0xabb3b0 | OOB | 1875 | function_407e20__lifted | 無し |
| 0xcd50d0 | OOB | 711 | function_10c7cd0 | 無し |
| 0xe63540 | OOB | 1158 | function_125da90 | 無し |
| 0xeddfe0 | halt0 | (frame 無し) | - | - |
| 0xf6c660 | OOB | 14900 | function_410b10 | 無し |

- survey の `top_frame_idx` の `14877` (`function_412770`) は base 8 件・fix 7 件で、halt0 unit 数と一致する。halt0 経路は frame を取れない。
- 結論: #942 の「修復対象は function_409c80 の 1 件のみ」は現 main では**一致しない**。`function_409c80` (F2・F3c) は trap の最上位 frame に現れない。最上位 frame に現れる F3a は `function_413540` (base の unit 0x26d1a0 のみ) と `function_4133f0` (unit 0x6d5700。修復後も残る)。
- chain 上の関数 (非最上位) の判定は本表では確認していない。

## 10. bin 表 P/F の由来とサイズ→bin 表 (#942 受入 1・2・run 6)

前回 run の記録 (測定 commit: `047f97c5`・origin/main)。以下は本 run の測定ではない。本 run の素材は fl-win64 のみ (work-m11 は無い)。
前回 run の `bash tools/m11/ldfix/ldfix_e2e.sh` は rc 0・judge PASS (実行時間は出所のログが無いため削除) (units 17/942・icall 24・threw `memory access out of bounds`・survey ok 136 / trap 9、base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。

- 照合 (`python3 tools/m11/ldfix/bin_table_source.py`、KS = k184/185/186/215/236 の 5 件のみ): k184 / k185 / k186 の P (`0x7a50` 等) は、PE `.data` に生値 `0x407a50` / `0x408040` / `0x408870` (LVA 補正前) として入っている。k236 の P `0xa027` は生値 `0xa027` として PE に入っている。
- 確認できたのは上記 5 件 (k184/185/186/215/236) のみ。512 スロット (k=0..255) の P/F を image と照合するコードは commit に無く、本 run では `work-m11` の `m11_image.bin` が無いため実行していない。「512/512 一致」は取り下げる。bin 表の初期値全体が PE 静的データ由来かは未確認。
- PE 上の k187 以降はバイト列 (機械語でない) で、bin 表の由来として扱える値ではない。
- サイズ→bin 表 (`0x11e6a3c`・326 バイト・`function_407a50` が `size/8` で索引) (`bin_size_probe.mjs`): **前回 run (測定 commit `047f97c5`) の観測値**。本 run (HEAD `d10f5bbf`) では未再現ではなく未実行 (`work-m11` の `m11_image.bin` が無く、`bin_size_probe.mjs` を再実行していない)。前回の値: PRE は全 0、boot 後は非 0 324 件・最大 bin 番号 172・k184 以上を指す参照 0 件。PRE/POST の出力行は本 run に無いため貼れない。
- 結論 (未確認): k184〜186・k215・k236 の不正な P/F が、サイズ→bin 表から参照されない bin であるか (通常経路 サイズ ≤ 2600 で読まれないか) は**未確認**。前回観測では参照 0 件とされたが、HEAD での再現が必要。unit 17 の trap の発生 load (`function_407a50` の `[P+24]` 読み) に k184 が関与するか否かも未確認で、「仮説は支持されない」とは言えない。
- 注意: `bin_table_pre_boot.mjs` の `OOB` 表示は `F<8 || F>=MEM` の機械的判定で、F=0x1 などの値も OOB になる。boot 後の 47 件の大半 (`P=0xfa5xxx`・`F=0x1`) はこの判定による見かけの OOB で、実際の trap とは対応しない。
- 未解決 (起票先): サイズ→bin 表の 172 以下の bin 中で、boot 後に F が不正な bin (trap の発生源候補) の特定 → #942 (次 run)。bin 表 P の書き込み元 (boot で self-loop 化される処理) → #942 (次 run)。


## 11. bin 表 k≥184 の中身と書き込み元の切り分け (#942 受入 1・2・run 7)

本 run の素材: fl-win64 のみ (`$ARTIFACTS_DIR` に `fl-win64.tar.zst` だけ)。work-m11 / work-liftdiff / toolchain-emsdk は展開されていない。
`ldfix_e2e.sh` は `tools/m11/work/m11_image.bin` を前提とするため、本 run では**未実行**。以下の rc 0・judge PASS・units 17/942・icall 24・threw `memory access out of bounds`・survey ok 136 / trap 9・修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0 は**前回 run からの引用** で、本 run の測定値ではない (実行時間は出所のログが無いため削除)。

- k184 / k185 / k186 の P 値は PE `.data` の `.reloc` 対象 slot の値、k236 の P 値は `.data` の `.reloc` 対象外の slot の値 (§10・§12 と同じ)。生値は P + 0x400000 で、k184 = 0x407a50、k185 = 0x408040、k186 = 0x408870 (k236 は非ポインタの 0xa027)。生値が `.text` の関数先頭に当たるかは本 run で未確認 (前版の「関数先頭に当たる」「関数ポインタの配列と読むのが自然」は撤回)。
- k184〜186・k236 の P/F が unit 0〜16 の実行で変化しないか: **未確認**。`tools/m11/trap_triage/oob684_probe.mjs 17 <P slot 4 本> watch` は本 run で未実行 (素材 `work-m11` の `m11_image.bin` が無いため)。よって「書き込みは boot 前のイメージ由来」とは言えない。
- `tools/m11/ldfix/trap_bins.mjs` (UNIT=17) の trap 前後の OOB bin: **未確認**。本 run で未実行のため、出力は貼れない。unit 17 の trap の発生 bin が k184〜186・k236 のどれかかも未確認。
- サイズ→bin 表 (`0x11e6a3c`・326 バイト) の boot 後の状態: **未確認**。`tools/m11/ldfix/bin_size_probe.mjs` は本 run で未実行 (出力なし)。§10 の前回観測 (boot 後 非 0 324 件・最大 172) の再現も未実施。
- 結論 (受入 1・2 の進捗): 書き込み元は未特定。「k≥184 が bin 表の一部か」は §10 と同じく未確認のまま。次の入口は、サイズ→bin 表が boot 後に非 0 になる条件 (前回観測の素材・手順) の再現と、bin 0..172 のうち F が不正なものの特定。
- 注: 上記の再実行には素材 `work-m11` (`oc_artifacts` に追加) が必要。
- 未解決 (起票先): サイズ→bin 表の再現条件の差 / boot 後に F が不正な bin の特定 → #942 (次 run)。現 main IR での ldfix 効果の再判定 → #1292 (merge 済み #1469)。work-m11 の IR と現 main の不一致 → 既存 #680。

## 12. k184/185/186/236 の書き込み元の除外 (#942 受入 1・2・run 8)

e2e (`bash tools/m11/ldfix/ldfix_e2e.sh`) は本 PR の範囲では再測定していない (`tools/m11/work/` 無し・`$ARTIFACTS_DIR` は fl-win64 のみで work-m11 が無い)。
以前の節にあった実行時間は、測定 commit・run ID・ログのいずれも辿れなかったため削除した。実行時間の実測値は本 PR に無い。

鮮度 (WORKFLOW §6): 本 fix run の HEAD `a8cefaec` での `git diff e082c4f1 HEAD -- tools/m11/ldfix/` の出力:

```
 tools/m11/ldfix/REPORT_942_APPENDIX.md | 46 ++++++++++++++++++++++++++++++++--
 tools/m11/ldfix/bin_post_probe.mjs     | 28 +++++++++++++++++++
 tools/m11/ldfix/pe_bin_source_check.py | 43 +++++++++++++++++++++++++++++++
 3 files changed, 115 insertions(+), 2 deletions(-)
```

実行経路 (`ldfix_e2e.sh` が呼ぶ `stage4.sh` / `run_stage4.mjs` / `survey_stage4.mjs` / `judge_e2e.py` / `ldfix.py` / `ldfix_img.py` / `ldframe.py` / `ldmach.py` / `tools/shared/env.sh`) の `git diff e082c4f1 HEAD` は空 (出力 0 行・`a8cefaec` で実測)。`bin_post_probe.mjs` と `pe_bin_source_check.py` は、どのスクリプトからも呼ばれない単独ツール。よって `ldfix_e2e.sh` の実行経路は e082c4f1 と同一。本 PR で e2e は再測定していないため、測定 commit は無い (本節冒頭参照)。

- **撤回**: 前版の「イメージ読込直後・boot 後・unit 17 の trap 前後で P 値が同じ」「F の値」「unit 0〜16 の監視 (`oob684_probe.mjs 17 <P 256 本> watch`) の結果」は、出所 (測定 commit・ログ) を辿れないため本節から削除した。unit 0〜16 の実行中に P 値が変化するかは**未検証**。
- **未再現**: `bin_post_probe.mjs` の PRE-BOOT / POST-BOOT 出力行は本 PR では得られていない (`tools/m11/work/m11_image.bin` が無いため。素材 `work-m11` が必要)。本 fix run では `bin_post_probe.mjs` を一度も実行していない。したがって `m11_dllmain_done` の分岐 (`__emscripten_stack_restore` の呼び出し) も未実行。
- PE 照合 (`pefile` 2024.8.26・`tools/m11/ldfix/pe_bin_source_check.py`、PE は `fl-win64` の `block00031_PE.bin`、ImageBase 0x400000): 再実行コマンド `python3 tools/m11/ldfix/pe_bin_source_check.py "$FL_WIN64_DIR/extracted/block00031_PE.bin"` (`tools/m11/ldfix/work/venv` は本 run に無いため system の python3 を使用)。HEAD `a8cefaec` で本 fix run 中に実行した全出力 (rc 0)。`PE:` 行のみ展開先パスを `<FL_WIN64_DIR>` に置換した:

```
PE: <FL_WIN64_DIR>/extracted/block00031_PE.bin
ImageBase: 0x400000
k184 P=0x7a50 値 0x7a50: なし
k184 P=0x7a50 値 0x407a50: raw=0xfa4690 sec=.data rva=0xfa5c90 reloc_dir64=True
k185 P=0x8040 値 0x8040: なし
k185 P=0x8040 値 0x408040: raw=0xfa46a0 sec=.data rva=0xfa5ca0 reloc_dir64=True
k186 P=0x8870 値 0x8870: なし
k186 P=0x8870 値 0x408870: raw=0xfa46b0 sec=.data rva=0xfa5cb0 reloc_dir64=True
k215 P=0xee 値 0xee: raw=0xaeec12 sec=.text rva=0xaef812 reloc_dir64=False; raw=0xaeec42 sec=.text rva=0xaef842 reloc_dir64=False; raw=0xaeed7f sec=.text rva=0xaef97f reloc_dir64=False; raw=0xaeedc6 sec=.text rva=0xaef9c6 reloc_dir64=False
k215 P=0xee 値 0x4000ee: なし
k236 P=0xa027 値 0xa027: raw=0xfa49d0 sec=.data rva=0xfa5fd0 reloc_dir64=False
k236 P=0xa027 値 0x40a027: なし
```

- 結論: k184〜186 の P の生値 (`0x407a50` / `0x408040` / `0x408870`) は PE `.data` の RVA `0xfa5c90` / `0xfa5ca0` / `0xfa5cb0` に入っており、いずれも `.reloc` DIR64 対象。VA→LVA 補正 (−0x400000) で `m11_image.bin` の値になる。
- k236 (0xa027) は `.data` (RVA 0xfa5fd0) に入るが `.reloc` 対象外。
- k215 (0xee) は 8 バイト一致が `.text` 内の機械語にしか出ず、`.data` に生値は無い。PE 由来とは言えない (前版の「PE 由来」の書き方は撤回)。
- 結論 (範囲を限定): k184・185・186・236 の P は、**イメージ読込直後 (boot 前) の時点で F が OOB** である (`tools/m11/ldfix/REPORT_942.md` 240 行の PRE 計測・測定 commit `35e6031e`)。同じ生値は PE `.data` に静的に存在する (本節の照合)。したがって「不正値は boot 前のイメージ段階から存在する」と言える。
- 言えないこと: boot 中・unit 0〜16 の実行で書き込まれていないこと。これは本 PR で未検証であり、「書き込み元から除外した」とは書かない。PE 側の値が bin 表 (16 バイト stride) の中に入る理由 (表の長さ・構造体の重なり) も未確認。
- 未確認 (次の入口): (a) unit 17 の trap がこの 4 スロットの F を実際に読むか (`trap_bins.mjs` は状態だけで、読み取り命令の特定は未実施)。(b) bin 表 k≥184 が FastMM の bin 表の一部か (PE の `.data` が同じ領域に別の配列を持つ可能性)。(c) 0x407a50 の `.text` 関数と P の関係 (`function_407a50__lifted` が FastMM_GetMem の実体かは未確認。根拠は未取得)。
- 未解決 (起票先): unit 17 の trap 命令の特定と、bin 表 k≥184 の構造 → #942 (次 run)。

## 13. bin 表の boot 前後差分と k184〜186 の正体 (#942 受入 1・2・run 9)

測定: `S4_NAME=base|fix node tools/m11/ldfix/bin_table_diff.mjs` (新規・`bin_post_probe.mjs` と同じ手順で boot 前後の bin 表 k=0..255 を比較)。
素材 `fl-win64` / `work-m11` (`tools/m11/work/` を worktree から参照)。
測定 commit `d5f5ee92` (HEAD・コードを変えた最後の commit)。`bash tools/m11/ldfix/ldfix_e2e.sh` は 50 秒 (real)・rc 0・load 0.82 / 0.87 / 0.49・judge PASS (base = fix)。units 17/942・icall 24・threw `memory access out of bounds` (base = fix)・survey ok 136 / trap 9 (base = fix)。修復件数 F3a 2 / F3c 33。
鮮度: `git diff d5f5ee92 HEAD -- tools/m11/ldfix/` は本 REPORT の追記のみ (ldfix_e2e.sh の実行経路は変更なし)。

- boot 前後で bin 表 (BASE 16404744・16 バイト刻み) の変化は base / fix とも **96 スロット** で、変化した k の一覧は base / fix で一致する (一致の照合手順は commit に無く、md5 照合は本 run では未再現。値の一致は未比較)。
  変化した k は 0,1,4,5,6,8,9,10,… と 216 (k184〜186・215・236・255 は変化なし)。修復 pass の有無は boot の書き込みを変えない。
- `bin_post_probe.mjs` (base/fix): k184 P=0x7a50 / k185 P=0x8040 / k186 P=0x8870 / k215 P=0xee / k236 P=0xa027 は PRE・POST で同一。
- `bin_size_probe.mjs` (fix・`S4_IMAGE` 指定): PRE nonzero=0 / POST nonzero=324・max_bin=172・refs_ge184=0。
- `trap_bins.mjs` (fix・unit 17): BEFORE/AFTER とも k184・185・186・236 が OOB、k215 は F=0。unit 17 の trap は bin 表を書き換えない。

### P の正体 (新知見)
- k184〜186 の P の生値 (0x7a50 / 0x8040 / 0x8870) は、PE `.data` 上で VA (0x407a50 / 0x408040 / 0x408870) として `.reloc` DIR64 対象になっている (§12)。
- P が指す先の先頭バイトは `55 57 56 53` (push rbp/rdi/rsi/rbx)・`55 41 57 41`・`53 48 83 ec` で、3 件とも関数の prologue に見える。
- 従って k184〜186 の「bin ポインタ」は、bin 表の隣に並ぶ**関数ポインタ表**の要素を 16 バイト刻みで読んでいる可能性がある。
  サイズ→bin 表は bin 172 までしか参照せず (refs_ge184=0)、k≥173 は bin 表の外と考えられる。仮説。
- k236 (P=0xa027) は先頭バイト `48 8d 4d 38` (lea) で、prologue とは言い切れない。仮説の支持は 3/4。

### 結論 (受入 1・2 の進捗)
- **確定**: boot は k184〜186・215・236 の P/F を書き換えない。bin 表の不正な値は boot より前 (イメージ読込時) から存在する。
- **確定**: 修復 pass の有無は boot 後の threw (`memory access out of bounds`) を変えない。変化スロットの一覧も一致する。ただし値の比較は未実施のため「書き込みの値が同一」とは言わない。
- **未確定**: boot の `memory access out of bounds` を起こす load の番地。boot で書かれる 96 スロットの値そのもの (書き込み元の関数) は未特定。
- **未確定**: unit 17 の trap が k184〜186 を実際に読むか (trap_bins は状態の表示のみ)。
- 次の入口: boot の書き込み関数 (96 スロットを書く store の関数) の特定と、k≥173 が bin 表の外であることの確認 (bin 表の長さ = `size/8` 索引の上限と照合)。

- 未解決 (起票先): boot 書き込み元の関数・trap の load 番地 → #942 (次 run)。現 main 生成 IR での ldfix 効果の再判定 → #1292 (merge 済み #1469)。work-m11 の IR と現 main の不一致 → 既存 #680。

## 14. 通常 boot の trap 位置と lift 誤り候補 (#942 受入 1・2・run 10)

既知類型との関係: 該当なし (docs/DEFECTS.md の既存 ID と機械語・IR の形が一致しない。近縁は D4。14-3 で比較)。

測定 commit: `54bacdc0` (origin/main・本 PR の基点。e2e の実行経路はこの commit と同一)。素材 fl-win64 / work-m11 / work-liftdiff を展開 (toolchain-emsdk は `[EMSDK]` が runner に既存のため展開せず)。
`FL_WIN64_DIR=$RUNNER_TEMP TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` は 71.5 秒 (real)・rc 0・judge PASS・load 0.96 / 0.67 / 0.31 (終了後)。stage4 units 17/942・icall 24・threw `memory access out of bounds` (base = fix)。survey ok 136 / trap 9 (base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。

### 14-1 survey 経路の bin 表観測は通常 boot と別物
- `trap_bins.mjs` / `trap_units.mjs` / `reach_survey.mjs` は `_m11_set_survey(1)` で InitUnits を抑止する。このとき once-init `function_41ce10` (FastMM 初期化) が走らず、counter `0x11e6a38` は 0 のまま、bin 表は P=0 の未初期化。
- 通常 boot (survey 無し・`run_stage4.mjs` と同じ経路) では counter = -1 (`function_41ce10` 実行済み) で、`function_4090e0` が bin 表を 64 バイト歩幅で self-loop (`P == rbx`) に初期化する。
- よって §2 (run 2) の「unit 17 の発生 load は FastMM 空きリスト走査」と、survey 経路の BEFORE/AFTER 結果 (§9 ほか) は通常 boot の trap 原因としては扱えない。

### 14-2 通常 boot の trap 位置 (wasm → IR)
- `normal_boot_probe.mjs` の例外スタック (top): `wasm-function[14871]:0x350d1b` ← `[2711]:0x16f6eb` ← `[2765]` ← `[2835]` ← `[9725]` ← `[14847]` (m11_icall) ← `[14865]` (function_4120c0) ← `[14866]` (m11_InitLib) ← `[14869]` (function_41d8f0) ← `[26]` (entry_point)。
- `python3 tools/m11/m11_wasmnames.py <wasm> <idx>` で 14871 = function_4133f0、2711 = function_446400、2765 = function_44bb70、2835 = function_455790、9725 = m11_tr_function_455790。
- wasm 逆アセンブル (`wasm-objdump -d`。npm `wabt` 1.0.39 の同梱バイナリ・リポジトリ外): 0x350d1b は `i32.load` で、アドレスは `[frame+40] - 8` (文字列ポインタの −8 の header 読み)。0x16f6eb は `call function_4133f0(local0+16, i64.load [frame+72])`。
- IR で対応する呼び出しは `function_446400` 内の `%56 = call function_4133f0(%54 = arg1+16, %55 = load stack_var_-112)`。`function_4133f0` の `if arg2 != 0: [arg2-8]` で trap。InitUnits の 18 番目 (init_count 18・units_run 17)。

### 14-3 lift 誤り候補 (PE 機械語と IR の照合)
- PE の `function_450560` (VA 0x450560。`python3 tools/m11/ldfix/pe_disasm_va.py <block00031_PE.bin> 0x450560`): `mov rcx,[rsp+0x68]` (2 番目引数 = &s) → `mov rax,[rsp+0x60]` (1 番目引数) → `mov rdx,[rax]` (**1 番目引数が指す値**) → `call 0x4133f0` → `cmp qword [rax],0`。つまり `_LStrAsg(&s, *arg1)` 相当。
- **D4 との比較 (判定)**: 1 段目の機械語 (`mov rdx,[rax]`・disp=0 の 1 段 deref) は D4 と形が同じだが、IR の代入元は deref 元のアドレス (rax = 1 番目引数 `arg1`) ではなく `%arg2` で、D4 の「rD := r8 (deref 元のアドレス)」とは一致しない。よって D4 と同型とはせず、「引数の取り違えを含む deref 脱落」の**別類型候補**とする (類型名は割り当てない。docs/DEFECTS.md への追記は PM 判断)。
- base IR (`tools/m11/work/boot_final3.ll`・ldfix 前) の同関数: `%0 = call function_4133f0(i64 %arg2, i64 %arg2)` と `%1 = icmp eq i64 %arg2, 0`。2 番目の引数 (`rdx = [rax]`) が **アドレス (arg2) に置き換わり**、逆参照が 1 段落ちている。ldfix の修復対象ではなく、lift 段階に既存。
- **2 段目 (同関数・比較の site)**: PE `0x45058d: cmp qword ptr [rax], 0` (rax = `[rsp+0x68]` = 2 番目引数 `arg2`)。base IR は `%1 = icmp eq i64 %arg2, 0`。比較オペランドの deref が落ち、arg2 (アドレス) そのものを比較している。D4 の「disp=0 の deref 脱落 → 当該 reg の値として扱う」と同型 (比較の消費者形)。修正対象は 1 段目と同じ子 #2502 の受入に含める。
- 同類型は libkio の `[T-SH-27]` (#1282・第 2 引数 deref 落ち・KIO_ARGREG で個別対応) にある。M11 側は未対応。D7 (スタック引数のずれ) と D8 (rax 戻り値の消失) は今回の形ではない。
- trap 直前の文字列 `stack_var_-112` は `function_447e30` → `function_450540` → `function_450560` を経由する。`GetLocaleInfoW` スタブ (常に 0 を返す) の影響も確認した。scratch (repo 外) でスタブを「NUL 1 文字・戻り 1」に差し替えて再リンクしても、trap 位置は同一 (`function_4133f0` @0x350d1b・init 18・units 17)。この再リンクは repo 外 scratch で行い、再現手段はリポジトリに無い (未再現)。よって GetLocaleInfoW の戻り値が原因でないとは確定しない (結論の強さは弱い)。

### 14-4 bin 表と size 表 (通常 boot・trap 後の状態)
- サイズ→bin 表 (0x11e6a3c・326 バイト): 相異なる値 44 種・最大 172・184 以上の参照 0 件 (値は 4·i)。よって k184〜186・k236 (PE 静的データ由来の非 self-loop) は size < 2601 の GetMem 経路から到達しない。
- bin 表 (k ≤ 172・4 刻み・44 個): self-loop (空) 43 個、非 self-loop 1 個 (k4: P=0x10be1990・F=0x10be1ac0・有効)。
- span 表 idx 104 (sentinel 0x11e72c0): 1 要素。head=0x10bda660・`[head-8]`=0x7333 で整合。
- 結論: 「不正 bin (k184〜186・236) が trap の発生源」仮説は通常 boot で棄却 (到達不能)。trap は GetMem 経路ではなく、文字列代入 (`function_4133f0`) の入力が不正なことで起きる。

### 14-5 受入への反映
- 受入 1 (trap 9 件の原因): 部分。通常 boot の trap (InitUnits 18 番目) の位置は確定。他 8 件は未確認。
- 受入 2 (boot threw の原因): 部分。ldfix 起因ではない (base IR に既存)。入口は `function_450560` の第 2 引数の逆参照落ち (14-3 の 1 段目) と、同関数の比較の逆参照落ち (14-3 の 2 段目)。trap 時点の値への伝播経路は未追跡。
- 受入 3: #1469 の判定 (§8) を維持。本 run で分かったこと: 修復対象 `function_4133f0` の trap は、修復 (F3a: ヘッダ読みの順序) では消えない入力 (14-3) を読んでいる。帰属は未確定。

未解決 (起票先): `function_450560` の 1 段目・2 段目の逆参照落ち (M11 lift・#1282 と同類型) → 子 #2502。他 8 件の trap の原因と、trap 時点の文字列値の伝播経路 → #942 (次 run)。
