# REPORT_APPENDIX_6023 — #6023 (M11-38): RetDec use-list 計装ビルド (#6021 の前段)

## 1. 結果 (部分達成)

- 達成: LLVM fork `avast/llvm 2a1f3d8a` をソースからビルドし、RetDec v5.0 (`53e55b4b`) を再リンクした。LLVM の取得は CMake の `URL_HASH SHA256` が `cmake/deps.cmake` の `LLVM_ARCHIVE_SHA256` (`96389d21…`) で照合した。取得物の sha256 は `96389d211d74e758…` で一致。
- 達成: ビルドしたバイナリ (計装なし) で同一 PE・同一 150 range を 1 回流し、rc=0 を確認した。
- **未達**: use-list 計装 (LLVM 側に use-list の順序を出すパッチ) は適用していない。受入 1 の『計装が入ったことの確認』は未達。このビルドは配布 v5.0 と同じ RetDec 本体に、同じ LLVM fork を再リンクしたもの。
- **未達**: 計装版での段特定 (#6021 の受入) は未着手。
- **注意**: 計装ではないため、use-list の段の特定に使えるかは未確認。

## 2. 測定

- 測定 commit: `97a5bd8ab` (main)。本 PR のコードは `tools/m11/retdec_build_6023.sh` (ビルド手順) のみ。測定は同じ手順をコマンドで直接実行した (スクリプトは測定後に書いた)。
- ビルド: `cmake ../src -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DRETDEC_COMPILE_YARA=OFF -DYARA_MAKE_PROGRAM=/usr/bin/make -DCMAKE_CXX_FLAGS="-include cstdint"` → `ninja -j4 retdec-decompiler`。
  - 所要 (実測・n=1): real 18 分 51.97 秒 (1131.97 s)。rc=0。ninja は 749 段。load average は `uptime` で 3.8〜4.4 (4 コア)。
  - 所要には LLVM の取得・configure を含む (`time ( cmake && ninja )` の全体)。
- 再現: `RB_WORK=$RUNNER_TEMP/m11b bash tools/m11/retdec_build_6023.sh`。
- **share の配置**: ビルドしたバイナリは、隣に `share/` が無いと Initialization の後で無言終了する (rc=0 で drc.ll が出ない)。`share/` は `toolchain-retdec` (v5.0) の `share/` を `bin/` の隣に置いた (`inst/bin` + `inst/share`)。これは `REPORT_911_APPENDIX_1967.md` §6g の観測と一致する。
- バージョン: `retdec-decompiler --version` は `v5.0` / `53e55b4b26e9b843787f0e06d867441e32b1604e`。

## 3. 1 run の確認 (同一 PE・同一 150 range)

入力: `fl-win64/extracted/block00031_PE.bin`・`work-m11` の `boot_ranges.txt` 先頭 150 range・`--select-decode-only --timeout 250`。

| 実行 | バイナリ | rc | 秒 | drc.ll md5 (raw) | A7 後 lift.ll md5 | `uselistorder` 行 |
|---|---|---|---|---|---|---|
| s1 | 本ビルド (LLVM 再リンク) | 0 | 9.5 | `cbee7ce0` | `946aefb3` | 817 (raw) / 0 (lift) |
| ctl | 配布 v5.0 | 0 | 9.5 | `6000176e` | `946aefb3` | — / 0 |

- A7 後の lift.ll は両者一致 (`946aefb3`)。`uselistorder` の並びは raw では一致しない (`cbee7ce0` と `6000176e`)。これは `uselist_origin_2456.sh` の既知の揺れ (REPORT_APPENDIX_960 §20) と同じ種類の差で、1 回ずつの比較では由来を判断できない。
- 注: raw drc.ll の md5 は実行ごとに変わる (REPORT_APPENDIX_960 §20)。上の 1 組は『本ビルドが動く・A7 後の結果が配布版と一致する』ことの確認で、差の段の証拠にはしない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| use-list 計装パッチ (LLVM の use-list 出力) を適用し、計装が入ったことを確認する | 受入 1 の残り。段の特定 (#6021) が出来ない | 親 #6023 の本文にチェックリストとして残す (次 run で着手) |
| 計装版での 150 range の段特定 (#6021 の受入) | 上流 (RetDec) の修正箇所が決まらない | #6021 (親 #2577 の子) |
| 計装版での rc と drc.ll md5 の記録 | 受入 4 | 上と同じ |
