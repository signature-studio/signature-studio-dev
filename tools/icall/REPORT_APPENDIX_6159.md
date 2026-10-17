# tools/icall REPORT 付録 — ICALL-127 (#6159): RetDec v5.0 を debug 有効で再ビルドし install tree との版一致を確かめる

自動生成ではない (手書きの測定記録)。親 #5115 (ICALL-109) の受入 1 の前提。上位 #4206 (ICALL-95)。

## 1. 結論

- debug 有効 (`CMAKE_BUILD_TYPE=Debug`, `-g`) の `retdec-decompiler` を上流 `avast/retdec` の `v5.0` から再ビルドし、完走した。
- `--version` は `v5.0` / commit `53e55b4b26e9b843787f0e06d867441e32b1604e`。素材 install tree の `share/retdec/BUILD-ID` と **commit hash が一致**。
- 同一入力 (`/bin/true`) で新旧の出力 C は **sha256 一致** (`3fb49af7…41fe`)。ログ差は時間のみ。
- **未達**: `getJumpTarget` の Undefined 値確定 (受入 1 の本体) は本 run では未実施。`/bin/true` は間接 call を含まないため icall 経路の検証には使えない。#5115 の受入 1 は前提が揃った後の別 run。

## 2. 版一致の確認 (受入 2)

| 項目 | 素材 install tree (`toolchain-retdec`) | 本 run の debug 再ビルド |
|---|---|---|
| `--version` | `RetDec version: v5.0` | `RetDec version: v5.0` |
| Commit hash | `53e55b4b26e9b843787f0e06d867441e32b1604e` | `53e55b4b26e9b843787f0e06d867441e32b1604e` |
| Build date | 2022-12-08T10:13:13Z | 2026-10-17T14:38:52Z (再ビルド日時) |
| ビルド型 | 未確認 (素材の build 型は測定していない) | Debug (`CMAKE_BUILD_TYPE=Debug` を指定。`CMakeCache.txt` の値は未保存のため未確認) |
| 入力 `/bin/true` の出力 C | sha256 `3fb49af7f60ec9a84cc230b2bbdd68ed4a3b3f63951f7e7b465deb73824b41fe` | 同じ |

**版一致の範囲**: commit hash (`53e55b4b`) は一致。install tree 内の全バイナリ (`bin/*`) や `lib/*.a` との逐一比較は**未確認**。上流ソースからの再現 build で Release と Debug の差を取っただけで、素材 bundle が上流 `v5.0` から作られたかの完全な確認は「未確認」のまま (R7 ④)。

素材 install tree には上流ソース (`src/`・`deps/`) は含まれていない (`retdec.tar.xz` は `include/`・`share/` のみ)。ソースは GitHub `avast/retdec` の `v5.0` タグ (`git clone --depth 1 --branch v5.0`) から取得した。

## 3. ビルド手順と所要時間 (受入 3)

環境: 4 vCPU, 15 GiB RAM, GCC 13.3.0, CMake 3.31.6, Ninja/Make。

| 段階 | 結果 | 所要 |
|---|---|---|
| 上流 clone (`v5.0`) | OK (commit `53e55b4b`) | 2 秒 |
| 素材の展開 (`toolchain-retdec`) | OK | 3 秒 |
| configure 1 回目 (既定) | Configure 成功 | 1 秒 |
| `ninja` 全体 (既定 target) | **失敗** (`src/utils/file_io.cpp.o`: `uint8_t` が `std` 下に無い。GCC 13 の `<cstdint>` 不足) | 14:24 〜 14:30 (110 秒 × 区切り 3 回の実測) |
| 対処 1 | `-DCMAKE_CXX_FLAGS="-include cstdint"` で回避 | — |
| configure 2 回目 | yara の configure step が `config.status` の depfile 生成で失敗 (`MAKE=OFF`) | — |
| 対処 2 | Ninja → Unix Makefiles に変更 | — |
| yaramod 段 | **失敗** (`yaramod/src/utils/utils.cpp`: `std::optional` の `.value()` 誤用・GCC 13) | — |
| 対処 3 | `RETDEC_ENABLE_YARAMOD` は他の `RETDEC_ENABLE_*` から自動決定され `-D` で OFF にできない。`retdec-decompiler` 本体は yaramod に依存しないため、`make retdec-decompiler` で対象を絞る | — |
| `make retdec-decompiler` (LLVM 込み) | **成功** (`[100%] Built target retdec-decompiler`) | 14:40 〜 14:55 (`uptime` 表示の実測。110 秒 × 区切り 8 回) |
| 実行確認 | 支援データ (`share/retdec/decompiler-config.json` 等) は build tree に無いため、素材 install tree を複製し `bin/retdec-decompiler` だけを新ビルドに差替えて実行 | 14 秒 (`/bin/true`) |

**合計**: 14:22 (run 開始) 〜 14:57 (実行確認まで)。LLVM 込みの debug 再ビルド (14:40〜14:55) が支配的。`make install` は yaramod の失敗で止まるため使えず、上記の複製方式で検証した。

### 注意 (再現手順)

- `-DRETDEC_ENABLE_YARAMOD=OFF` は効かない (上流の `set_if_at_least_one_set` が上書きする)。`make retdec-decompiler` を指定する。
- `make install` は全体 target を要求するため yaramod の GCC 13 不具合で失敗する。`cmake --install --component` も効かなかった。
- GCC 13 で必要な回避: `-include cstdint`。上流 v5.0 は GCC 7 前提 (`docker/Dockerfile` の `-DCMAKE_LIBRARY_PATH=/usr/lib/gcc/x86_64-linux-gnu/7/`)。
- `timeout` で make を止めると `Error 2` が連鎖表示されるが、ビルド失敗ではない (再実行で続きから進む)。

## 3a. 測定 commit と差分 (WORKFLOW §6)

- 測定 commit: `097225b74` (main)。ビルド対象の上流は `avast/retdec` `v5.0` = `53e55b4b26e9b843787f0e06d867441e32b1604e` (`git ls-remote` で確認)。
- 検証起点 (本付録を書いた時点の PR head): `72bf22db2`。
- `git diff 097225b74 72bf22db2 -- tools/icall docs/DOC_MAP.md --stat` の出力:

```
 docs/DOC_MAP.md                     |  1 +
 tools/icall/REPORT_APPENDIX_6159.md | 65 +++++++++++++++++++++++++++++++++++
 2 files changed, 66 insertions(+)
```

- 同 diff の `docs/DOC_MAP.md` 部分は本 PR で追加した 1 行 (`tools/icall/REPORT_APPENDIX_6159.md` の索引行) のみ。コード (`tools/icall` 配下のスクリプト・ソース) の変更は 0 件。
- 上流ビルドはリポジトリのコードを使わないため、`097225b74` 以降のコード差分は測定結果に影響しない (再測定不要)。

## 4. 残件 (#5115 受入 1 の前提が揃った後)

- `getJumpTarget` が `Undefined` を返した値の確定 (Fresh Air 残落ち 6 件, `REPORT_APPENDIX_1844.md`)。これには debug build で `Decoder::resolvePseudoCalls()` (`decoder.cpp`) に入り、対象 6 件の SymbolicTree を確認する必要がある。本 run は版一致と build 手順までで、ここは未着手。
- 再実行に使う入力は Fresh Air の対象 binary (`plugins-freshair`) が必要 (`oc_artifacts` は #5115/#4206 の依頼参照)。

## 5. 再現 (§3 で実際に通した手順のみ)

`-DRETDEC_ENABLE_YARA=OFF` 等の yara 関連指定は §3 で実行していないため含めない (効果は未確認)。

```
git clone --depth 1 --branch v5.0 https://github.com/avast/retdec.git src-retdec
mkdir build-debug && cd build-debug
cmake ../src-retdec -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="-include cstdint" -G "Unix Makefiles" -Wno-dev
make -j4 retdec-decompiler
```

`-G "Unix Makefiles"` は §3 の対処 2 (Ninja から変更) に対応する。`make retdec-decompiler` の完了は §3 の表のとおり。
