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

測定 commit: `047f97c5` (origin/main)。素材 fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk を展開。
`bash tools/m11/ldfix/ldfix_e2e.sh` は 68.7 秒・rc 0・judge PASS (units 17/942・icall 24・threw `memory access out of bounds`・survey ok 136 / trap 9、base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。

- 照合 (`python3 tools/m11/ldfix/bin_table_source.py`、KS = k184/185/186/215/236 の 5 件のみ): k184 / k185 / k186 の P (`0x7a50` 等) は、PE `.data` に生値 `0x407a50` / `0x408040` / `0x408870` (LVA 補正前) として入っている。k236 の P `0xa027` は生値 `0xa027` として PE に入っている。
- 確認できたのは上記 5 件 (k184/185/186/215/236) のみ。512 スロット (k=0..255) の P/F を image と照合するコードは commit に無く、本 run では `work-m11` の `m11_image.bin` が無いため実行していない。「512/512 一致」は取り下げる。bin 表の初期値全体が PE 静的データ由来かは未確認。
- PE 上の k187 以降はバイト列 (機械語でない) で、bin 表の由来として扱える値ではない。
- サイズ→bin 表 (`0x11e6a3c`・326 バイト・`function_407a50` が `size/8` で索引) (`bin_size_probe.mjs`): **前回 run (測定 commit `047f97c5`) の観測値で、本 run・HEAD (`0383a426`) では未再現**。本 run では `work-m11` の `m11_image.bin` が無く、`bin_size_probe.mjs` を再実行していない。前回の値: PRE は全 0、boot 後は非 0 324 件・最大 bin 番号 172・k184 以上を指す参照 0 件。PRE/POST の出力行は本 run に無いため貼れない。
- 結論 (未確認): k184〜186・k215・k236 の不正な P/F が、サイズ→bin 表から参照されない bin であるか (通常経路 サイズ ≤ 2600 で読まれないか) は**未確認**。前回観測では参照 0 件とされたが、HEAD での再現が必要。unit 17 の trap の発生 load (`function_407a50` の `[P+24]` 読み) に k184 が関与するか否かも未確認で、「仮説は支持されない」とは言えない。
- 注意: `bin_table_pre_boot.mjs` の `OOB` 表示は `F<8 || F>=MEM` の機械的判定で、F=0x1 などの値も OOB になる。boot 後の 47 件の大半 (`P=0xfa5xxx`・`F=0x1`) はこの判定による見かけの OOB で、実際の trap とは対応しない。
- 未解決 (起票先): サイズ→bin 表の 172 以下の bin 中で、boot 後に F が不正な bin (trap の発生源候補) の特定 → #942 (次 run)。bin 表 P の書き込み元 (boot で self-loop 化される処理) → #942 (次 run)。


## 11. bin 表 k≥184 の中身と書き込み元の切り分け (#942 受入 1・2・run 7)

測定 commit: `edef8fa0` (origin/main)。素材 fl-win64 / work-m11 / work-liftdiff / toolchain-emsdk を展開。
`bash tools/m11/ldfix/ldfix_e2e.sh` は 68.0 秒・rc 0・judge PASS (units 17/942・icall 24・threw `memory access out of bounds`・survey ok 136 / trap 9、base = fix)。修復件数 F3a 2 / F3c 33 / F1 0 / F2 0 / F3b 0。

- k184 P=0x7a50 / k185 P=0x8040 / k186 P=0x8870 / k236 P=0xa027 の P 値は、PE `.data` の `.reloc` 補正済み slot の値 (§10 と同じ)。生値は P + 0x400000 で、k184 = 0x407a50、k185 = 0x408040、k186 = 0x408870 (k236 は非ポインタの 0xa027)。生値が `.text` の関数先頭に当たるかは本 run で未確認 (前版の「関数先頭に当たる」「関数ポインタの配列と読むのが自然」は撤回)。
- k184〜186・k236 の P/F が unit 0〜16 の実行で変化しないか: **未確認**。`tools/m11/trap_triage/oob684_probe.mjs 17 <P slot 4 本> watch` は本 run で未実行 (素材 `work-m11` の `m11_image.bin` が無いため)。よって「書き込みは boot 前のイメージ由来」とは言えない。
- `tools/m11/ldfix/trap_bins.mjs` (UNIT=17) の trap 前後の OOB bin: **未確認**。本 run で未実行のため、出力は貼れない。unit 17 の trap の発生 bin が k184〜186・k236 のどれかかも未確認。
- サイズ→bin 表 (`0x11e6a3c`・326 バイト) の boot 後の状態: **未確認**。`tools/m11/ldfix/bin_size_probe.mjs` は本 run で未実行 (出力なし)。§10 の前回観測 (boot 後 非 0 324 件・最大 172) の再現も未実施。
- 結論 (受入 1・2 の進捗): 書き込み元は未特定。「k≥184 が bin 表の一部か」は §10 と同じく未確認のまま。次の入口は、サイズ→bin 表が boot 後に非 0 になる条件 (前回観測の素材・手順) の再現と、bin 0..172 のうち F が不正なものの特定。
- 注: 上記の再実行には素材 `work-m11` (`oc_artifacts` に追加) が必要。
- 未解決 (起票先): サイズ→bin 表の再現条件の差 / boot 後に F が不正な bin の特定 → #942 (次 run)。現 main IR での ldfix 効果の再判定 → #1292 (merge 済み #1469)。work-m11 の IR と現 main の不一致 → 既存 #680。
