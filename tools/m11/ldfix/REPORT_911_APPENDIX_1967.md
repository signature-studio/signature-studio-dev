# #911 付録: 分岐の実行確認 (LD-71 / #1967)

## 6f. #1967 (LD-71): 分岐の実行確認 (既存 v5.0 バイナリへの uprobe。ソースビルドはしていない)

測定 commit: `748c595e` (ws-1967 の基点。repo のコードは使っていない)。素材: `toolchain-retdec` の v5.0 バイナリと `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…9496d`)。uprobe は `perf probe -x` で関数内の 3 つの `convertConstantToType` 呼び出し点 (`+768` siteA、`+1426` siteB、`+1475` siteC) に張った。

| 範囲 (`--select-ranges`) | siteA | siteB | siteC |
|---|---|---|---|
| 41a670-41a6f4 (全体) | 2 | 0 | 3 |
| 41a6a0-41a6a3 | 1 | 0 | 0 |
| 41a6d3-41a6d6 | 1 | 0 | 0 |
| 41a6b3-41a6b7 (対照) | 0 | 0 | 0 |
| 666b10-666b13 | 1 | 0 | 0 |
| 666b20-666b23 | 1 | 0 | 0 |
| 666a60-666b20 | 4 | — | — |

- 41a6a0・41a6d3 の各 1 回は、§6c の deref 脱落 2 命令と一致する。
- **未確定**: siteA が L163〜166 (`gv` の分岐) に当たるかは、バイナリに DWARF が無く (`addr2line` は `??`) 逆アセンブル照合でのみ推定した。siteA は別の `convertConstantToType` 呼び出し (ngv 系) と区別できていない。
- 所要: 41a670-41a6f4 の 1 回 7.54 秒 (real、n=1、4 コア)。load average は**未測定** (元の測定時に記録していない)。
- 再現: `tools/m11/ldfix/uprobe_1967.sh` (env: `RETDEC_BIN`・`PE_BIN`・`FUNC_BASE`)。**未検証**: 本 run では `toolchain-retdec` が無く未実行、`perf` は tracefs 権限無しで probe 登録を試せなかった。`FUNC_BASE` (呼び出し元関数の VA) は付録に記録が無く未確定。初回実行で構文と件数を確かめること。


## 6g. #2038 (LD-75): RetDec ソースビルドで発火行を確定 (v5.0 `53e55b4b`)

ソース: avast/retdec `53e55b4b` (v5.0)。LLVM は CMake が取得する avast/llvm `2a1f3d8a` (sha256 一致)。ビルドは `RelWithDebInfo`・`-j4`・yara 無効 (`RETDEC_COMPILE_YARA=OFF`・`YARA_MAKE_PROGRAM=/usr/bin/make`)・`-include cstdint` (GCC 13 対策)。
ビルド時間 (実測・n=1): 成功した最終 run (LLVM 含む、`ninja -j4`) real 9 分 10.623 秒。前段で失敗した run は real 10 分 0.841 秒 (yara 段で停止)。load average (`uptime`) は最終 run 中 2.75〜4.81 (4 コア)。
測定の鮮度: 測定経路は RetDec v5.0 (`53e55b4b`) のソースビルドと `tools/m11/ldfix/uprobe_1967.sh` である。`git diff 10b65967 HEAD -- tools/m11/ldfix/uprobe_1967.sh` は 0 行。`tools/m11/ldfix/` 内で差分が出るのは `audit_undefload_dest.py`・`ld92_machine_evidence.py`・`ld98_dump.py`・`verify_dest_2202.py` の 4 件 (263 行追加。main 取り込み由来)。このうち `.sh` から呼ばれるのは `audit_undefload_dest.py` だけで、呼び出し元は `repro_2143.sh` (#2143 の測定) である。`ld92`・`ld98`・`verify_dest_2202` は #2038 の測定経路に入らない。したがって本測定の鮮度は、RetDec 本体 (repo 外。`53e55b4b` に固定) と `uprobe_1967.sh` (差分 0 行) で判断できる。

行対応の確定: 一時ログ (`TAG_L150`・`TAG_L167`) をビルド用ソースにだけ入れ、成果物には含めない。`convertConstantToType` の呼び出しは v5.0 で 3 箇所: L150 (`max == &root`)・L157 (`userI`)・L167 (`gv` 分岐)。

| 範囲 (`--select-ranges`) | 発火行 | 発火命令 (IR) |
|---|---|---|
| 41a693-41a69a | L150 (1 回) | `%1 = load i64, i64* inttoptr (20598912)` (= `@0x13a5080`) |
| 41a6a0-41a6a3 | **L167 (1 回)** | `%2 = load i64, i64* %1` |
| 41a6d3-41a6d6 | **L167 (1 回)** | `%2 = load i64, i64* %1` |
| 666b10-666b13 | **L167 (1 回)** | `%2 = load i64, i64* %1` |
| 666b20-666b23 | L167 (1 回) | — |
| 41a6b3-41a6b7 (対照) | 0 | — |
| 41a670-41a6f4 (全体) | L150 ×3・L167 ×2 (合計) | — |

結論: 41a6a0・41a6d3・666b10 の発火は全て **L167 (v5.0 の L165〜170 の gv 分岐)** である。付録 §6f の siteA は、L167 と対応すると確定した (L150 ではない)。REPORT_911 §6c・§6d の「分岐が 41a6a0 で発火することは未確認」は、本 run で確認済みになった。

判定 (受入 4): **部分達成**。41a6a0 (段 16) と 666b10 (段 17) は同一分岐 (v5.0 `constants.cpp` L167) で発火することを実測で確認した。

同一機構の判定が出せない理由:
- 段番号差 (段 16 と 17): 実測は「どの段で値が変わるか」までで、段番号の差が何に由来するかは示せていない。`ConstantsAnalysis` の複数回適用という説明は REPORT_911 §6d のソース読みによる推定で、実測していない。
- 2 点は同じ分岐 (L167) だが、L167 を通る条件 (`root.ops.size() <= 1` と記号木の簡約結果) の一致を確かめていない。記号木の中身は実行時に出していない。
- 2019-03 版 (`6edcaaea`) と v5.0 では分岐内の `_toRemove.insert(val)` が異なる (§6d)。差が結果に効くかは未確認。

機構の所在は lift 段と推定する (`retdec-constants` は RetDec 本体の pass で、ldfix 段ではない。pass の特定はソース読みによる)。

残件: 上の 3 点 (段番号差・L167 条件の一致・2019-03 版との差) は、記号木の中身を出す一時ログ付きビルドと 2019-03 版の再ビルドを要する。fix run (5453dd3e 時点) では `$ARTIFACTS_DIR` に `fl-win64` のみあり、`toolchain-retdec` も 2019-03 版の `share/` も無いため実施できなかった。残件は PM 判断 (2026-10-14、出典: https://github.com/signature-studio/signature-studio-dev/issues/2038#issuecomment-6167618240) により子 issue に移した: 段番号差・L167 条件の一致は #2315 (受入 4)、2019-03 版との差は #2314 (受入 1 の版)、検出信号・修復・wasm 実測・DEFECTS 行は #2316 (#1091 の残り)。

注: 単独範囲の件数は §6f の表と一致した (41a6a0 = 1、41a6d3 = 1、666b10 = 1、対照 41a6b3 = 0)。

全体範囲 (41a670-41a6f4) の件数の内訳:
- 表の「L150 ×3・L167 ×2」は、全体範囲を指定した 1 回の lift で出たログの件数である。ただし、この件数の取り方 (ログをどう集計したか・何回測ったか) は本 run の記録に残っておらず、再現手順も無い。
- 単独範囲の測定で位置が確定しているのは、L150 が 41a693-41a69a の 1 回、L167 が 41a6a0-41a6a3 と 41a6d3-41a6d6 の各 1 回。全体範囲の L150 のうち残りの **2 回の発火アドレスは未確認**である。
- L167 の結論 (41a6a0・41a6d3・666b10 が L167 で発火) は単独範囲の件数に基づくため、全体範囲の未確認の件数には依存しない。全体範囲の件数の再確認は、範囲を分けた測定 (41a670-41a68f・41a69b-41a69f・41a6a4-41a6d2・41a6d7-41a6f4 など) で行う。本 run では未実施。

ビルド注: 自前ビルドの `retdec-decompiler` は、隣に `retdec/share` を置かないと `Initialization` 後に無言終了した。実装 run (4dcab82d 時点) の計測は、素材 `toolchain-retdec` の share を使ったと記録されている (展開先は §6 の `rd/retdec/` 配下と推定: `rd/retdec/share`)。出所: #2038 のコメント https://github.com/signature-studio/signature-studio-dev/issues/2038#issuecomment-6165881740 (「`$ARTIFACTS_DIR` に fl-win64 / toolchain-retdec / work-m11 が実在することを `ls` で確認済み」)。実装 run の展開コマンドは記録に無く、この記述は再確認していない。fix run (5453dd3e 時点) の `$ARTIFACTS_DIR` には `toolchain-retdec` が無いため、share は再確認できない。

版について (受入 1): issue #2038 は 2019-03 版相当でのビルドを求める。本 PR の実測は v5.0 (`53e55b4b`) のみ。2019-03 版 (`6edcaaea`) はソースを取得できたが、(1) fix run では `toolchain-retdec` が無く share の入手元が無い、(2) 2019-03 版のツリーに `share/` が無い、(3) LLVM は `avast-tl/llvm` の外部取得 (`3d1e5d0b`) を要する。fix run の上限 (40 分) では収まらないと判断し、ビルドしていない。PM 判断 (2026-10-14、出典: https://github.com/signature-studio/signature-studio-dev/issues/2038#issuecomment-6167618240) により、受入 1 は原文のまま子 issue #2314 に移した (v5.0 に改める (b) は採らない)。

## 6h. #2314 (LD-106): 2019-03 版 (`6edcaaea`) のソースビルド実測と、分岐発火確認の阻害要因

測定 commit: `e6cefa06` (main。本 run は repo のコードを変えていない。`git diff e6cefa06 HEAD -- tools/m11/ldfix` は本節の追記のみ)。
ビルド対象: avast/retdec `6edcaaea` (2019-03-09) を `git clone` で取得し、`deps/` は同梱のもの (LLVM は `avast-tl/llvm` `3d1e5d0b` を CMake が取得)。

ビルド (Makefile generator・`RelWithDebInfo`・`-j4`・4 コア・RAM 15GB。load average は make 前後の `uptime`):
- クリーン 1 回目 (`build-clean`・`CXXFLAGS=-include cstdint -include string`): real 644 s (10 分 44 秒)。rc=0。load average 1.19 → 4.95。n=1。
- 前段の試行 (LLVM 段で ninja が失敗・pelib/yaramod の sub-build を再実行) は 本測定に含めない。

ビルド時に必要だった回避 (v5.0 と異なる点):
- GCC 13 で `std::uintN_t`・`std::string` が未 include: `CXXFLAGS` に `-include cstdint -include string` を付けた (`CMAKE_CXX_FLAGS` だけでは pelib の ExternalProject に届かない)。
- yaramod の configure が `FLEX_INCLUDE_DIR` で失敗: `libfl-dev` を apt で導入 (`/usr/include/FlexLexer.h`)。
- 2019 版には `RETDEC_COMPILE_YARA` が無い (v5.0 の回避は使えない)。

未達 (受入 1 の後半・受入 2): 2019 版の `retdec-decompiler` を得られなかった。
1. `make install` が `cmake/install-share.py` で `retdec-support_2019-03-03.tar.xz` を取得し、HTTP 404 で失敗する (`github.com/avast-tl/retdec-support/releases/download/2019-03-03/...`。release API も 404。tag `2019-03-03` は存在するが LICENSE・README (172K) のみ)。share を入手できない。
2. `toolchain-retdec` の share は `2019-03-08` (v5.0 同梱)。`2019-03-03` の代替にはならない (版が違う)。
3. 2019 版の `retdec-bin2llvmir` は v5.0 と CLI が異なる (`--select-ranges` 無し。`-select-fncs` は値を取らず入力パスを解釈できない)。`retdec-decompiler.py` ラッパーは install 段が落ちるため使えない。

判定: 受入 1 は **部分達成** (2019 版のソースビルドは実測した。ただし実行可能な 2019 版バイナリを得ていない)。受入 2 (41a6a0 での分岐発火確認) は **未実施** (前提の 2019 版バイナリが無い)。
残件 (子 issue に移す): 2019 版の share 入手経路の確定 (2019-03-03 の share を別経路で得る、または 2019 版 `retdec-decompiler` 相当の起動方法を確立) → 41a6a0 での `checkForGlobalInInstruction` の L163〜168 発火確認 (`TAG` 一時ログ付きビルドも含む)。
素材の入力: `block00031_PE.bin` は `fl-win64` 内 `extracted/`、sha256 先頭 `b2c64da4` (付録 §6f と一致)。
