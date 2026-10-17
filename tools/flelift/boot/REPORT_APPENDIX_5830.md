# REPORT_APPENDIX_5830 — FLE-48 (#5830): 既定経路の非決定 9 バイトの書込み unit 帰属

測定 commit: `3a3a1f152` (`fle_boot.c` の `g_py_watch` に非決定 8B ワード 4 つを追加。挙動は変えず記録だけ増やした)。
コード差分 `git diff f82959016 3a3a1f152 -- tools/flelift` は `fle_boot.c` の 2 行 (`PY_WATCH_N` 9→13 と配列 4 要素の追加) だけ。
工程: `fle6_measure.sh` (`FLE_BOOT_RUNS=default`・`FLE_EXTRA_ROOTS=`・`FLE_BOOT_TAG=fle5830`) で build → 既定経路 boot 1 回 (`FLE_IPP`・`FLE_TOLERANT` 未指定)。
素材: `fl-win64` (`extracted/block00031_PE.bin` のみ展開)・`toolchain-emsdk` (`[EMSDK]` の pin 6.0.12)。
実測: build (gen-A・lift 82 s・clang-plain 98 s)・boot 9 s・load 2.16。`fle6_measure.sh` rc 0。
boot 結果: units_run 895・units_total 942・boot_threw `exit`・IPP ok (`ptr_15F34A0=0x7f10001c`)。REPORT_APPENDIX_5177 §2 と一致。

## 1. 結論

- 非決定 9 バイトを含む 4 ワードの変化を unit 境界の監視点 (site 1・2・8) で捉えた。変化が起きた unit と、その unit の proc VA を特定できた。
- 書込み命令 (どの関数の、どの store か) は未特定。unit 単位までの帰属で止まる。
- 測定は 1 回だけ (再測定しない・PM 指示)。run 間で同じ unit に出るかは未確認。

## 2. 変化点 (今回の 1 run)

監視点は site 1 (unit dispatch 直前)・site 2 (直後)・site 8 (GetMem 呼出し直前) の 3 つ。変化は「前回の監視点から今回までの間」に起きたことを示す。

| ワード (VA) | 含む非決定バイト | 変化 unit | site | unit の proc VA | 値 (old → new) | 窓 |
|---|---|---|---|---|---|---|
| `0x13a5010` | `0x13a5010`〜13 | 85 | 2 | `0x59f9a0` | `0x200000000` → `0x2000bcae9` | unit 85 の dispatch 中 (site 1 → 2) |
| `0x13a5010` | 同上 | 548 | 2 | `0xc21b50` | `0x2000bcae9` → `0x25a00c1e0` | unit 548 の dispatch 中 |
| `0x13a5010` | 同上 | 560 | 2 | `0xc44460` | `0x25a00c1e0` → `0x21a6cfdd2` | unit 560 の dispatch 中 |
| `0x13e4d58` | `0x13e4d58` | 123 | 2 | `0x63aae0` | `0x0` → `0x324` | unit 123 の dispatch 中 (site 1 → 2) |
| `0x15f26e8` | `0x15f26e8`〜ea | 43 | 8 | `0x28` (GetMem 要求サイズ) | `0x0` → `0xacbf4` | unit 43 内・GetMem 直前 |
| `0x16bcbf0` | `0x16bcbf0` | 851 | 8 | `0x470` (GetMem 要求サイズ) | `0x0` → `0x598` | unit 851 内・GetMem 直前 |

- `0x13a5010` は 3 unit (85・548・560) で値が変わった。`0x13a5010`〜13 の 4 バイトを含む。
- unit 43 と 851 の site 8 は、GetMem 呼出し直前の監視点で検出した。`proc` 欄は GetMem の要求サイズであり、unit の VA ではない。窓は「前回の監視点から GetMem 直前まで」で、unit 43・851 の内部に入るのは、前回の監視点がその unit の中だった場合のみ。前回の監視点は記録していないため、窓の下端は確定しない。
- 初期 (unit 0・site 0) の `0x13a5010` (`0x200000000`) は boot 前のセットアップの値。

## 3. 読み方と限界

- 変化は値の差分として検出している。書込み命令は見ていない。同じ unit 内の callee が書いた可能性がある。
- 上の unit VA は書込みを行った関数とは限らない。書込み元は unit が呼ぶ関数の中にあり、特定には命令単位のウォッチポイント (lift の store フック) が要る。
- 静的解析 (停止報告) で、非決定 9 バイトを RIP 相対・絶対アドレスで直接書く命令は .text に 0 件だった。今回の結果と合わせると、書込みは間接 (ポインタ経由) と考えられる。
- REPORT_APPENDIX_5177 §3 の「時刻風の値が `GetSystemTimeAsFileTime` 等に由来する可能性」は、この run では確認できなかった。`fle_boot.c`・`fle_imp_bridge.c` に当該 import の参照はない。
- 次の手順 (本 issue の残件): unit 85・548・560・123 の dispatch 中について、store 命令単位で書込み PC を取る計装を入れる。窓は今回の site 1→2 の範囲に限る。
