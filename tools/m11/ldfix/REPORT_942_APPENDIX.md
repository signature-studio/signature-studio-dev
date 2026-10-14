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

- boot 前後で bin 表 (BASE 16404744・16 バイト刻み) の変化は base / fix とも **96 スロット** で、変化した k の一覧は一致 (一覧の md5 一致。値の一致は未比較)。
  変化した k は 0,1,4,5,6,8,9,10,… と 216 (k184〜186・215・236・255 は変化なし)。修復 pass の有無は boot の書き込みを変えない。
- `bin_post_probe.mjs` (base/fix): k184 P=0x7a50 / k185 P=0x8040 / k186 P=0x8870 / k215 P=0xee / k236 P=0xa027 は PRE・POST で同一。
- `bin_size_probe.mjs` (fix・`S4_IMAGE` 指定): PRE nonzero=0 / POST nonzero=324・max_bin=172・refs_ge184=0。
- `trap_bins.mjs` (fix・unit 17): BEFORE/AFTER とも k184・185・186・236 が OOB、k215 は F=0。unit 17 の trap は bin 表を書き換えない。

### P の正体 (新知見)
- k184〜186 の P の生値 (0x7a50 / 0x8040 / 0x8870) は、PE `.data` 上で VA (0x407a50 / 0x408040 / 0x408870) として `.reloc` DIR64 対象になっている (§12)。
- P が指す先の先頭バイトは `55 57 56 53` (push rbp/r15/r14/r13)・`55 41 57 41`・`53 48 83 ec` で、3 件とも関数の prologue に見える。
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
