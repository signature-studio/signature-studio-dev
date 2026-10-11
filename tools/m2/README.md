# M2: mac x86_64 slice 抽出 + 静的解析成果物の機械化 + Delphi 品質確認

`docs/REFERENCES.md` `[STRATEGY]` §4 M2 / §5.7 Delphi-PE 品質確認を M1 の土台 (`tools/m1/`) の上で
実施する一連のスクリプト群。**結論/評価本体は `tools/m2/REPORT.md`**
(`m2.sh` で得た `work/` 成果物の数値をもとに手動で維持される)。

## 使い方

```sh
bash tools/m2/m2.sh          # 軽いステップ群 (+ 重い解析の成果物があれば合意検証)
bash tools/m2/poc_crc8_wasm.sh  # 300KB級副モジュール IR→wasm PoC 単体再実行
```

成果物は `tools/m2/work/` (gitignored: `tools/m2/.gitignore`)。

## 重い解析 (1 回だけ手動で実行するもの)

Ghidra headless / RetDec の全体解析は 30 分〜数時間かかるため `m2.sh` の外で
1 回だけ実行して `work/` に置く (取得済なら `m2.sh` は再利用する)。

```sh
# 外部ツールの install root: <ghidra> = `docs/REFERENCES.md` `[GHIDRA]` / <retdec> = `[RETDEC]`
# Ghidra headless (win64 FLEngine; ~12 min, Heap 16GB)
<ghidra>/support/analyzeHeadless \
  <work_dir_abs> ghproj_dll -import <WIN64 extracted>/block00031_PE.bin \
  -scriptPath tools/m2/ghidra_scripts \
  -postScript DumpFunctions.java <abs>/tools/m2/work/ghidra_dll/functions_dll.csv \
  -analysisTimeoutPerFile 5400
# 2 度目以降: 同 project に -process block00031_PE.bin -noanalysis で再取り出し可

# Ghidra headless (mac FLEngine x86_64 slice; ~12 min)
<ghidra>/support/analyzeHeadless \
  <work_dir_abs> ghproj_slice -import tools/m2/work/FLEngine_x86_64.dylib \
  -scriptPath tools/m2/ghidra_scripts \
  -postScript DumpFunctions.java <abs>/tools/m2/work/ghidra_slice/functions_slice.csv \
  -analysisTimeoutPerFile 7200

# RetDec selective リフト (§5.7 5観点; 数秒〜数十秒)
<retdec>/bin/retdec-decompiler tools/m2/work/block00031_PE.bin \
  -o tools/m2/work/d5fast.drc.c --select-ranges "0x40ace0-0x40ad60,..." \
  --select-decode-only --timeout 900

# FLEngine 規模の全体リフトは ~2-3h / ~15GB RAM で後段 LLVM optimization が
# 完了しにくい (--timeout 7200 / 10800 の 2 実行とも後段で打切り)。境界照合には
# decode 完了時点で書かれる .dsm の '; function:' ラベルで十分:
#   (win) <retdec>/bin/retdec-decompiler work/block00031_PE.bin \
#         -o engine_win.drc.c --keep-unreachable-funcs --backend-no-opts \
#         --max-memory 20000000000 --timeout 10800   (3h 設定推奨)
#   照合: function_boundary.py --retdec-dsm work/engine_win.drc.dsm \
#         --dsm-shift -0x400000   (VA→RVA 変換)
#   (mac) <retdec>/bin/retdec-decompiler work/FLEngine_x86_64.dylib \
#         -o macbound.drc.c --select-ranges "0x2b50-0x10d964c" \
#         --select-decode-only --timeout 5400 --max-memory 20000000000
#   照合: 既定で --dsm-shift 0 (mac slice は address==file offset)
```

出力 (いずれも `work/` に置く):
- Ghidra: `ghidra_*/functions_*.csv` (name,entry,size)
- RetDec: `<out>.dsm` (`; function: <名> at <start> -- <end>` = decode 完了時点の
  関数境界一覧; function_boundary.py --retdec-dsm で読む)。小規模モジュールでは
  `<out>.config.json` (startAddr/endAddr) も利用可

## Delphi 品質確認 (§5.7観点) の 5 選択

`delphi_scan.py` が以下の観点で自動候補抽出し, RetDec `--select-ranges` で
5 本をリフト→IR 評価 (tools/m2/REPORT.md §3)。

| 観点 | 自動選択条件 | §5.7 |
|---|---|---|
| SEH_try_finally | .pdata unwind flag UHANDLER/EHANDLER + 小さくて直接 call を含む | #1 |
| VMT_indirect | call [reg+off] + VMT ロード ([reg]) 参照の小関数 | #2 |
| RTTI_VMTfield | VMT fixed field (class pointer -112 含む 負 disp) を読む小関数 | #3 |
| FastMM_allocator | 全関数中で caller xref 上位 (例: 15,505 xref) の超小関数 | #4 |
| calling_convention | 中サイズ・xref 少の multi-arg 関数 | #5 |

## ファイル一覧

| ファイル | 役割 |
|---|---|
| `m2.sh` | ドライバ (軽いステップ群を順に実行, 重い解析は既存成果物を再利用) |
| `extract_slice.sh/.py` | universal2 (FAT Mach-O) 解析 + x86_64 slice 切出し (lipo 非依存) |
| `pescan.py` | PE32+ 解析 (.pdata/UNWIND_INFO/IAT/delay-IAT/exports) |
| `delphi_scan.py` | Delphi x64 観点自動候補抽出 (capstone: xref/VMT/RTTI/IAT 走査) |
| `delphi_mac_scan.py` | mac slice の Pascal 文字列/VMT 走査 |
| `delphi_inventory.py` | delphi_inventory.md 機械生成 (win+mac VMT 表 / dbk 除外リスト) |
| `shim_inventory.py` | §3 12 行写影表の機械生成 (win import / mac import / winbridge export) |
| `function_boundary.py` | 関数境界合意 (Ghidra × RetDec × 静的テーブル) の数値化 |
| `ir_normalize.py` | RetDec (LLVM 12) IR → 現行 wasm バックエンド互換の正規化 |
| `poc_crc8_wasm.sh` / `poc_crc8_harness.mjs` | 300KB級副モジュール (EasyFLAC) の lift IR → wasm → node bit-exact PoC |
| `ghidra_scripts/DumpFunctions.java` | Ghidra headless 用 postScript (関数一覧 CSV) |

## 制限・既知問題

- **RetDec 全体リフト**: FLEngine 規模 (31.6MB slice) の bin2llvmir は **15-22GB 規模
  のメモリ**を要求し、完了まで ~1h (完了すると .ll / config.json / dsm が生成される)。
  また RetDec (LLVM 12) の出力 .ll は現行 wasm バックエンドにはそのまま落ちない
  (typed-pointer / zext-constexpr / datalayout 差異) → `ir_normalize.py` で
  機械正規化する (そもそも M3 で内製 LLVM pass へ格上げする方針)。
- **揮発的ファイル** (`work/`) は gitignored; 「正本」の判断は REPORT.md / 各 json。
- **winbridge の export 面** (Reg*/WB* 系 34 本) は Mac 移植用 Win32 縮小面であり、
  FL engine 全体の Win32 面 (§3 P0 12 行) としては別途自家実装が増える。
