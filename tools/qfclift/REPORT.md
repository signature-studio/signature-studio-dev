# tools/qfclift — T-SH-12 (#154): QuickFontCache_x64.dll を FLEngine と同じ x64c パイプラインで lift

既知類型との関係 (docs/DEFECTS.md): 該当なし (新規類型の発見なし)。ただし D2 (DEFECTS.md, movaps 上位 64bit) 系の
「XMM 命令 lift の bit 一致」を native 実機械語との直接比較で検査する方針は同じ。

## 0. 結論 (先出し)

- **判定: 部分達成 (lift + wasm build + 2 関数の native 一致まで。boot/実行は未着手)**。#154 の受入範囲
  (QuickFontCache → ILTools → FruityPlug) のうち **QuickFontCache の lift 層だけ**を完了。ILTools / FruityPlug(SGv2) は未着手 (§5)。
  よって PR は `Refs #154` (Closes しない)。
- `QuickFontCache_x64.dll` = `block24350_PE.bin` (PE32+, 2,067,968 B, ImageBase 0x400000, SizeOfImage 0x20e000)。
  export 10 本 (`CreateVST3Instance`/`FontCache_AcquireFont`/`InitSharedPython` ほか)。
- **`.pdata` 全 6,347 関数を roots にして lift: 6,347 関数 / 208,714 命令 / unsup 0 / unlifted callees 0 / import 222 名**
  (`closure 0`。.pdata が関数境界の全集合なので closure 不要)。flelift の x64c をそのまま使い、未対応は SSSE3 の 3 種 14 site のみ
  (pshufb 6 / pmulhrsw 4 / phaddw 4) → `x64c_qfc.py` で handler 注入して 0 に (tools/flelift は無改変)。
- emcc -O0 で wasm 生成 (15,115,363 B, `work/`)。native 実機械語 vs wasm の spot diff: SSSE3 を含む 2 関数
  (0x57de50 / 0x57e2a0) × 6 case = **12/12 case で dst 4096 B・rax・xmm0 が bit 一致**。
- **ネガコン 4 本全て FAIL 検出**: (a) handler 無効 → lift が unsup 14 を報告 / (b) pmulhrsw 丸め除去 → 不一致 2/12 case /
  (c) pshufb の 0x80 ゼロ化除去 → 不一致 2/12 case / (d) phaddw に +1 → 不一致 2/12 case。

## 1. 成果物

| パス | 役割 |
|---|---|
| `qfc_e2e.sh` | 1 コマンド検証。lift→assert(unsup 0, 関数数 = .pdata 数)→emcc→spot diff→ネガコン 4 本。**いずれか不合格で exit 1** |
| `env.sh` | `FL_WIN64_DIR` から `QFC_PE` を導出、emsdk を source |
| `gen_entries.py` | `.pdata` RUNTIME_FUNCTION 開始 VA → entries JSON (6,347 roots) |
| `x64c_qfc.py` | flelift/x64c.py に SSSE3 handler を monkeypatch して main() 実行。`QFC_NEGCTL=` でネガコン用に handler を壊す |
| `qfc_diff.py` / `qfc_natdrv.c` / `qfc_wasm_runner.mjs` | native (flelift の `fle_native.c` を #include) vs wasm 差分。`--expect-fail` でネガコン判定 |

実行: `FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=<capstone/pefile 入り python> bash tools/qfclift/qfc_e2e.sh`

## 2. SSSE3 handler (x64c に無かった 3 命令)

| 命令 | 実装 (XMM 形のみ。MMX 形は Unsup) |
|---|---|
| pshufb | `r[k] = (m[k] & 0x80) ? 0 : a[m[k] & 15]` |
| pmulhrsw | `(((int32)a*b >> 14) + 1) >> 1` (符号付き 16bit, 丸め付き上位) |
| phaddw | `r[0..3] = a の隣接 w 和, r[4..7] = b の隣接 w 和` (wrap, 飽和なし) |

出現 site: 0x57de50 (pshufb/pmulhrsw 各 2)、0x57e2a0 (pshufb 4 / phaddw 4 / pmulhrsw 2)。いずれも 3byte 画素列 → 16bit レーン
ブレンドのループ。pshufb の mask (0x5d9f8c) は `.bss` で InitDll が実行時に書くため file 上は 0 → diff は両側に明示敷設。

## 3. 検証 (実測)

検証起点 commit: 下記 §6。コミット済み HEAD を別 worktree (`git worktree add --detach`) に展開して実行。

| 項目 | 値 |
|---|---|
| lift | functions 6,347 / insns 208,714 / unsup {} / unlifted callees 0 / imports 222 (lift 所要 21.9 s, 初回 1 回の実測) |
| spot diff | 12 case / equal 12 / mismatch 0。native dst が実際に変化した case 10/10 (w>0 の全 case: 非自明性) |
| ネガコン | none_ssse3: unsup 14 (検出) / pmulhrsw: 2/12 mismatch / pshufb: 2/12 mismatch / phaddw: 2/12 mismatch |
| e2e 全体 | 実行 1 (初版 phaddw ネガコンが +0 で素通り=NOT detected → exit 1): 196 s。ネガコンを修正し実行 2: **PASS 195 s (load 1.00 0.80 0.47, nproc 4)** |
| クリーン HEAD 再現 | §6 |

初回の e2e で phaddw ネガコンが「検出できない」(NOT detected → exit 1) となり、ネガコン自体の設計不備 (上位半分の複製が
テスト入力で等値) を発見・修正した。gate は不合格時に exit 1 になることを実運用で確認済み。

## 4. 検証範囲 / 範囲外

- 範囲内: 6,347 関数の lift が**完走し未対応命令 0 であること**、SSSE3 3 命令を含む **2 関数の bit 一致**。
- **範囲外 (主張しない)**: 残り 6,345 関数の挙動一致 (lift 完走 ≠ 正しい)。InitDll / FontCache_AcquireFont など boot/実行、
  FreeType 結合 (T-SH-01 依存) 、wasm のブラウザ/ランタイム統合。spot diff は SSE レーンの命令意味論の検査であり関数全体の網羅ではない。
- spot diff の入力は乱数 (seed 固定 1) 12 case。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ILTools_x64.dll 未 lift。PE は特定済: `block24347_PE.bin` (PE export 名 `ILTools_x64.dll`, 3,662,336 B, SizeOfImage 0x394000, .pdata 11,747 関数, export 7 本)。同じ `gen_entries.py` + `x64c_qfc.py` で着手可能 (img-size 0x394000 を指定) | #154 の第 2 段 | #154 (継続) |
| FruityPlug_x64.dll (SGv2) 未 lift。`extracted/` の PE export 名が `FruityPlug_x64.dll` の PE は 133 本 (`Fruityplug_x64.dll` 表記 1 本含む。大半は export 3 本 = CreatePlugInstance + dbk 2 本、最大 7,600,128 B)。**プラグイン毎に別バイナリで、SGv2 本体の一意特定は未了** (issue 本文の「CreatePlugInstance export 一致による推定」の通り、共有 lib ではなく個別プラグイン DLL の可能性が高い = 推定) | #154 の第 3 段・対象定義の見直し要 | #154 (継続・PM 判断) |
| QFC の boot (InitDll → FontCache_*) 実行・unit 級検証未着手 | lift が実行時に正しいかは未確認 | #154 (継続) / FreeType 部は T-SH-01 |
| 残り 6,345 関数の差分検証が無い (ランダム関数 diff / liftdiff 採点) | silent miscompile 残存の可能性 | #154 (継続)。liftdiff 採点は #129 系 |
| wasm 15.1 MB が `work/` のみ (配信/ロード方式未決) | 統合時のサイズ・ロード時間 | #154 (継続) |

## 6. クリーン HEAD 再現・取りこぼし検査

- 検証起点 commit: `204bba8` (lift + e2e 一式)。`git worktree add --detach <tmp> 204bba8` で展開して `qfc_e2e.sh` を実行:
  **PASS 195 s (real 3m15.749s, load 1.28 0.94 0.59, nproc 4)**。lift 値・12/12 一致・ネガコン 4 本検出は §3 と同一。
- 実行 2 (作業ツリー, 同一内容): PASS 195 s (real 3m14.790s)。
- `find tools/qfclift -type f -size +20M -not -path '*/work/*'` → 該当なし。生成物 (wasm 15,115,363 B ほか) は `work/` (gitignore)。
- 本 REPORT・`REPORT.md` 追記のみの後続 commit は検証対象のコード (`*.py`/`*.sh`/`*.c`/`*.mjs`) を変更しない。
