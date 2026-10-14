# REPORT #2405 — RetDec 2019-03 版の share 入手経路と、41a6a0 での gv 分岐の発火確認 (LD-113)

既知類型との関係: 該当 ID は D20 (41a670 系の wrong-value reuse、既登録・機構未確定) の関連調査。新規類型なし。本 REPORT は gv 分岐の発火確認で、D20 の機構は確定していない (§6)。

親: #2314 (LD-106) / #2038 (LD-75)。付録 `REPORT_911_APPENDIX_1967.md` §6g・§6i の続き。#2405 は結果を同付録 §6i に追記するよう求めており、§6i 末尾に結論と測定 commit・主な実測値だけを追記した。表・コマンド・各範囲の結果は本 REPORT に置く。

**結論**
1. 2019-03-03 の share (`retdec-support_2019-03-03.tar.xz`) は、確認範囲 (§1 の経路) で見つからず、**入手不可として扱う**。GitHub の release asset は 404 で、確認範囲では複製も見つからない (§1)。
2. 代用 share ([RETDEC] v5.0 の share を 2019 版のレイアウトに合わせたもの。§2) で **2019 版 `retdec-decompiler.py` を起動でき**、`checkForGlobalInInstruction` の gv 分岐 (2019 版 L163〜168) が **41a6a0 で 1 回発火する**ことを実測した (§4)。41a6d3・666b10・666b20 も各 1 回、対照 41a6b3 は 0。件数・root・`ops` が v5.0 (付録 §6g・§6h) と一致した。
3. 発火後の IR も v5.0 と同じ形になる: Constants optimization で 41a6a0 の `load *rax` が `load @rcx` に変わる (§5)。違いは、2019 版では不要になった `inttoptr` が残ること。
4. 限界: share は 2019-03-03 の実物ではない。一時ログ付きビルド。各範囲 n=1 (2 つのビルドで同じ結果)。

## 1. 2019-03-03 の share の入手経路 (2026-10-14 実測)

| 経路 | 結果 |
|---|---|
| release API `repos/avast/retdec-support/releases/tags/2019-03-03` | 404。release 一覧は 7 件 (2019-03-08 〜 2017-12-12)。2019-03-03 は無い |
| `releases/download/2019-03-03/retdec-support_2019-03-03.tar.xz` | `avast`: 404。`avast-tl`: 301 で `avast` へ → 404 |
| tag `2019-03-03` | commit `02908241` (2018-06-10 の README 修正)。内容は LICENSE・README.md のみ。tag `2018-08-13`・`2018-07-27`・`2019-03-03-sources` も同じ commit |
| Wayback Machine | 2020-11-23 の `releases/tag/2019-03-03` は Assets 2 (ソース zip・tar.gz) のみ。`releases/download/2019-03-03/` の capture は CDX に無い。asset は遅くとも 2020-11 に無い |
| fork | `retdec-build/retdec-support`・`classicvalues/retdec-support` は tag のみで release 0 件。`mehrdad-shokri/retdec-support` は 2017 年の tag のみ |
| 検索 | GitHub code 検索で `retdec-support_2019-03-03` と期待 sha256 `7a5b06ec…` は各 0 件。archive.org の `retdec` 検索 10 件は retdec 本体リポジトリの 2017-12〜2018-01 の snapshot と awesome-* の一覧で、support パッケージは無い |
| 隣の版 2019-03-08 | asset は有るが sha256 `62935160…` で、`6edcaaea` の `install-share.py` が期待する `7a5b06ec…` と一致しない (`make install` は検証で失敗する) |

経緯: `install-share.py` は `3edc8d0f` (2019-03-03) で 2019-03-03 を指し、`4782b5b8` (03-05) で sha256 を更新した。`301f4e64` (2019-03-18、v3.3) で削除され、support は repo 内の `support/` と 2019-03-08 に移った。つまり `6edcaaea` (03-09) 〜 03-17 だけが 2019-03-03 を要する版で、その asset は GitHub から消えている。パッケージの内容は retdec-support の README によると ordinal 表・型 DB・static-code の YARA・暗号定数の YARA で、元データは repo に無く、source からの再生成はできない。

## 2. 代用 share

`retdec2019_gv_2405.sh install` が作る。
- [RETDEC] (v5.0) の `share/retdec/support` をコピーし、`version.txt` を `2019-03-03` にする。`install-share.py` は `version.txt` が一致すれば download と sha256 検証を省くため `make install` が通り、ラッパー `retdec-decompiler.py` が使える (#2314 の付録 §6i は「`make install` が 404 で失敗し、ラッパーは使えない」としていた)。
- 2019 版 `scripts/retdec-config.py` (6edcaaea で `ARM_ORDS_DIR` が L23、`X86_ORDS_DIR` が L25) のレイアウトに合わせ、`x86/ords`・`arm/ords` を v5.0 の `ordinals/{x86,arm}` への symlink にする。
- 2019-03-03 の実物との差は確認できない (実物が無い)。確認できたのは次の 2 点。
  - `generic/types/*.json` 5 本は、v5.0 の share と 2019-03-08 の archive でバイト一致する (`cmp`)。
  - 変種 B: types と static-code を 2019-03-08 の archive (sha256 検証済み) の物に差し替えた share でも、41a6a0・41a6d3・666b10 の発火と対照 41a6b3 の 0 は変わらない (§4)。この archive は ordinals・signsrch・tools の YARA を持たない (レイアウトが `301f4e64` 以降) ため、それらは v5.0 の物のままである。
- 2019 版の fileinfo は `signsrch/signsrch.yara` を探すが、v5.0 の share は `.yarac` のみで無い。fileinfo は無言で続行し rc=0 だった。暗号定数の検出が行われないかは未確認。「decode 範囲の結果に使われない」は未検証の推定である (§6 (d))。

## 3. ビルド

対象: avast/retdec `6edcaaea` (2019-03-09)。LLVM は CMake が `avast-tl/llvm` `3d1e5d0b` を取得する。`constants.cpp` に `std::cerr` の一時ログ 4 行を足す (`retdec_constants_trace_2405.patch`。ログのみで挙動は変えない。成果物には含めない)。

| ログ | 場所 (パッチ前の行) | 意味 |
|---|---|---|
| `TAG_SITE1_MAXROOT` | L149 `convertConstantToType` の直前 | `max == &root` の分岐 |
| `TAG_SITE2_USERI` | L155 同上 | `userI` の分岐 |
| `TAG_PRE_GV` | L162 の直後 | gv 分岐の条件の直前 (inst・root の値・`root.ops.size()`・isLoad・gv の有無) |
| `TAG_SITE3_GV` | L165 の直前 (L163〜168 の分岐内) | **gv 分岐が発火した** |

コマンド (`retdec2019_gv_2405.sh build`): `git clone https://github.com/avast/retdec` → `git checkout 6edcaaea` → `git apply` → `CXXFLAGS="-include cstdint -include string" cmake ../src -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=<WORK>/install` → `time make -j4`。`libfl-dev` (apt) が要る。`make` の時間には LLVM の zip 取得 (ネットワーク) を含み、clone・cmake・`make install` は含まない。

実測 (4 コア・RAM 15GB。load average は `uptime` の 1 分値。rc=0):

| 回 | `make -j4` の real | user / sys | load average |
|---|---|---|---|
| 1 回目 (同じコマンドを手で実行) | 679.1 s (11 分 19.105 秒) | 40 分 28.171 秒 / 2 分 11.584 秒 | make 開始前 0.57、ビルド中 5.5〜5.9 |
| 2 回目 (別ディレクトリで `all`) | 675.5 s (11 分 15.517 秒) | 40 分 50.283 秒 / 2 分 22.310 秒 | make 開始前 0.49、終了直後 4.38 |

`make install` は 1 回目 2.2 s。一時ログなしの 2019 版は #2314 の記録 (付録 §6i の 644 s・860 s) がある。本測定との差の原因は未切り分け (各 n=1)。生ログは成果物にしない (runner の一時領域で run 終了時に消える)。必要な数値は本 REPORT に転記した。

## 4. 発火の実測

入力は `block00031_PE.bin` (sha256 `b2c64da4…9496d`)。範囲ごとに `retdec-decompiler.py in.bin --select-ranges <範囲> --select-decode-only --stop-after bin2llvmir` を実行し、stderr の `TAG_*` を数えた (`retdec2019_gv_2405.sh ranges`)。1 回目・2 回目のビルドで件数は全て同じ。

| 範囲 | SITE1 (L149) | SITE2 (L155) | **gv 分岐 (SITE3)** | PRE_GV | v5.0 (付録 §6g) | real (1 回目 / 2 回目) |
|---|---|---|---|---|---|---|
| 0x41a693-0x41a69a | 1 | 0 | 0 | 6 | L150 ×1 | 4.52 / 4.55 s |
| **0x41a6a0-0x41a6a3** | 0 | 0 | **1** | 2 | L167 ×1 | 4.36 / 4.32 s |
| 0x41a6d3-0x41a6d6 | 0 | 0 | 1 | 2 | L167 ×1 | 4.46 / 4.34 s |
| 0x666b10-0x666b13 | 0 | 0 | 1 | 2 | L167 ×1 | 4.30 / 4.35 s |
| 0x666b20-0x666b23 | 0 | 0 | 1 | 5 | L167 ×1 | 4.45 / 4.32 s |
| 0x41a6b3-0x41a6b7 (対照) | 0 | 0 | 0 | 2 | 0 | 4.31 / 4.33 s |
| 0x41a670-0x41a6f4 (全体) | 3 | 0 | 2 | 79 | L150 ×3・L167 ×2 | 4.69 / 4.56 s |
| 0x666a60-0x666b20 (全体) | 0 | 0 | 4 | 156 | 4 (付録 §6f) | 5.70 / 5.81 s |

gv 分岐が発火した単独範囲の root (`TAG_PRE_GV` の行。v5.0 の付録 §6h と同じ値):

| 範囲 | 発火命令 | root | `root.ops.size()` |
|---|---|---|---|
| 0x41a6a0-0x41a6a3 | `%2 = load i64, i64* %1` | `@rax` (裸の GV) | 0 |
| 0x41a6d3-0x41a6d6 | `%2 = load i64, i64* %1` | `@rcx` | 0 |
| 0x666b10-0x666b13 | `%2 = load i64, i64* %1` | `@r8` | 0 |
| 0x666b20-0x666b23 | `%2 = load i8, i8* %1` | `@rcx` | 0 |

- 全体範囲 (41a670-41a6f4・666a60-666b20) の発火の件数は上の表のとおり。root は本測定の出力に含まれず、ログを保存していないため**未確認** (付録 §6h の root との照合もしていない)。
- 41a693-41a69a は `TAG_SITE1_MAXROOT` (v5.0 の L150 に相当) で、gv 分岐ではない。
- 変種 B (§2、`retdec2019_gv_2405.sh variantb`): 41a6a0・41a6d3・666b10 は gv 分岐が各 1、対照 41a6b3 は 0 (どちらのビルドでも)。real 4.15〜5.61 s。
- load average (1 分値、`ranges` の前後): 1 回目のビルド 1.24 → 1.12、2 回目 1.22 → 1.11。

## 5. 発火後の IR (`retdec2019_gv_2405.sh stages`)

`retdec_stage_1091.py` を 2019 版に向けた (v5.0 の CLI を変換する adapter を経由。2019 版の `-print-after-all` は module pass の見出しの直後に改行が無く、そのままでは module pass の段を読めないため、adapter で改行を足す)。41a6a0 は関数 41a670 の範囲 41a670-41a6f4、666b10 は関数 666a60 の範囲 666a60-666b20 で、IR が変わる段を出した。1 回目・2 回目のビルドで出力は同じ。

| 命令 | 段 | 段名 | IR の変化 |
|---|---|---|---|
| 41a6a0 | 1 → **15** | Constants optimization | `load @rax` → `inttoptr` → `load` → `store @rax` が `load @rax` → `inttoptr` (残る) → **`load @rcx`** → `store @rax` に変わる |
| 666b10 | 1 → **16** | Constants optimization | 同型。`load @r8` → `inttoptr` (残る) → **`load @rcx`** → `store @r8` |

v5.0 (REPORT_911 §6c・§6e) との比較: 値の変化 (`load *rax` → `load @rcx`、`load *r8` → `load @rcx`) と変わる段名は同じ。違いは 2 点。(1) 2019 版は不要になった `%70 = inttoptr …` が残る。v5.0 は消える (v5.0 の gv 分岐にある `_toRemove.insert(val)` の効果と整合するが、`_toRemove` の効果としては未検証)。(2) 段番号は 2019 版が 15・16、v5.0 は 16・17 で 1 ずつ小さい。pass の数え方の差と推定するが調べていない。

## 6. 判定と残件

- **41a6a0 で gv 分岐 (2019 版 L163〜168) は発火する**。1 回、`%2 = load i64, i64* %1`、root = 裸の GV `@rax`、`ops=0`。41a6d3・666b10 も同じ分岐で、v5.0 と件数・root・`ops` まで一致する。
- 2019 版と v5.0 の `checkForGlobalInInstruction` の差は 3 点 (`6edcaaea` と `53e55b4b` を diff): (1) root の構築が `SymbolicTree root(RDA, val)` か `SymbolicTree::PrecomputedRda(RDA, val)` か、(2) 第 1 分岐に `getActiveBits() <= 64` の条件、(3) 第 1 分岐と gv 分岐に `_toRemove.insert(val)`。gv 分岐の条件式 `isa<LoadInst>(inst) && gv && root.ops.size() <= 1` は同じ。この 3 点は、少なくとも**発火の有無・件数・root、deref が `load @rcx` に変わる結果には効いていない**。
- 未確認 (各件の起票先は PR 本文の未解決表に残す。WORKFLOW §3):
  - (a) 代用 share と実物 2019-03-03 の差 (types・static-code では効かないことだけ確認)。
  - (b) 一時ログなしの 2019 版との差 (ログのみのパッチで、挙動を変えない前提)。
  - (c) 残る `inttoptr` が最終 C 出力に効くか (`--stop-after bin2llvmir` までで止めた)。
  - (d) fileinfo の yara 欠落が decode 範囲の結果に使われないこと (推定。未検証)。
- #2314 の付録 §6i の阻害要因のうち「ラッパーは install 段が落ちるため使えない」「CLI が違う」は、`version.txt` を合わせた代用 share でラッパー経由なら解消する (§2)。`retdec-bin2llvmir` を直接呼ぶ必要はなかった (ラッパーは `--select-ranges`・`--select-decode-only`・`--stop-after` を持つ)。

## 7. 測定の記録

- 測定 commit (コードを変えた最後の commit): `c810b847`。以降のスクリプトの変更は 1 行のコメント修正 (repo 外の絶対パスの除去。pr-lint の指摘) だけで、`git diff c810b847 HEAD -- tools/m11/ldfix/retdec2019_gv_2405.sh tools/m11/ldfix/retdec_constants_trace_2405.patch tools/m11/ldfix/retdec_stage_1091.py` は 1 行の置換 (コメント) だけ。パッチと `retdec_stage_1091.py` は 0 行。
- 範囲 (§4)・変種 B・段別 IR (§5) は `c810b847` のスクリプトで、2 つのビルドの両方に実行した。ビルドの 1 回目は同じコマンドの手実行、2 回目は `ad9d6adb` 版のスクリプトの `all` (build・install は最終版と同一)。
- 所要: `stages` は 1 回目のビルドで real 14.4 s、2 回目で 18.6 s (n=1)。範囲の real は §4。
- main 取り込み (`264030a7`) で入った `tools/m11/ldfix/` の差分は他 issue の追加だけで、測定経路 (上の 3 ファイル) には入らない。
