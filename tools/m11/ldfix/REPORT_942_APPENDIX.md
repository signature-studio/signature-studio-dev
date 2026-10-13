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

