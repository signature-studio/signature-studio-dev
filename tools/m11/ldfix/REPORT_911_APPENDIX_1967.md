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

注: 単独範囲の件数は §6f の表と一致した (41a6a0 = 1、41a6d3 = 1、666b10 = 1、対照 41a6b3 = 0)。
