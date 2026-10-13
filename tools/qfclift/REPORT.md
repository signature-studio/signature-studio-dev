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
- **ネガコン 4 本全て FAIL 検出**: (a) handler 無効 → lift が unsup 14 を報告 / (b) pmulhrsw 丸め除去 → 不一致 9/12 case /
  (c) pshufb の 0x80 ゼロ化除去 → 不一致 10/12 case / (d) phaddw に +1 → 不一致 5/12 case。
  (旧版の「各 2/12」は e2e ログが `tail -3` で末尾 2 行しか出さず、その 2 行を件数と取り違えた誤記。件数は全出力で再取得済み: §6。)

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
| lift | functions 6,347 / insns 208,714 / unsup {} / unlifted callees 0 / imports 222 (lift 単独の所要 21.9 s は 1 回のみの参考値。n<3 のため min–max 対象外) |
| spot diff | 12 case / equal 12 / mismatch 0。native dst が実際に変化した case 10/10 (w>0 の全 case: 非自明性) |
| ネガコン | none_ssse3: unsup 14 (検出) / pmulhrsw: 9/12 mismatch / pshufb: 10/12 mismatch / phaddw: 5/12 mismatch (4 本とも FAIL 検出) |
| e2e 全体 (検証 HEAD `5c7a48a`) | PASS 3/3。**real 196.08–196.70 s (min–max, n=3)**、script 内計測 195–197 s。各 run の load・再取得手順は §6 |

初回の e2e で phaddw ネガコンが「検出できない」(NOT detected → exit 1) となり、ネガコン自体の設計不備 (上位半分の複製が
テスト入力で等値) を発見・修正した。その初回 run (修正前) は FAIL 196 s (exit 1) で、PASS 集計 (§6) には含めない。
gate は不合格時に exit 1 になることを実運用で確認済み。

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
| `qfc_e2e.sh` の negctl 行が `tail -3` で件数行を隠す (旧版の「2/12」誤記の原因) | 件数の目視誤読。PASS/FAIL の gate 判定 (exit code) には影響しない | #154 (継続・次の qfclift 改修で表示のみ修正) |

## 6. 検証実行・再現 (実測)

- **検証 HEAD = `5c7a48a`** (検証対象コードの最終 commit。`204bba8` からの差分は `x64c_qfc.py` の未使用 `_old` 行の削除のみ)。
  以降の REPORT.md のみの commit は検証対象のコードを変更しない (`git diff --stat 5c7a48a..HEAD` で `*.py`/`*.sh`/`*.c`/`*.mjs` 無変更を確認)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`tar --zstd -xf fl-win64.tar.zst -C` で展開) / `QFC_PY=<capstone + pefile の venv>` /
  `bash tools/qfclift/qfc_e2e.sh`。作業 worktree `ws-154` (branch `154-quickfontcache-lift`)。
- 環境: AMD EPYC 7763 / nproc 4。run は逐次 (前 run 終了後に開始)。load は `/proc/loadavg` の 1 分平均 (script 出力。開始 = run 直前 / 終了 = run 完了時)。

| run | HEAD | 結果 | script 計測 | real (`/usr/bin/time`) | load 開始 | load 終了 |
|---|---|---|---|---|---|---|
| P1 | `5c7a48a` | PASS (exit 0) | 197 s | 196.52 s | 0.18 0.18 0.08 | 0.98 0.59 0.27 |
| P2 | `5c7a48a` | PASS (exit 0) | 196 s | 196.70 s | 0.90 0.58 0.27 | 1.09 0.82 0.43 |
| P3 | `5c7a48a` | PASS (exit 0) | 195 s | 196.08 s | 1.16 0.84 0.43 | 1.02 0.97 0.57 |

- **min–max (n=3, 全 PASS)**: real **196.08–196.70 s** / script 内計測 195–197 s。run 開始時 load 0.18–1.16。
- 参考 (min–max に含めない):
  - レビュー側 (oc-reviewer) の独立再実行 (`1d332ce`・クリーン worktree): PASS 138 s (load 0.50 0.39 0.17)。上の 3 run より 58 s 短い。
    原因は未切り分け (実行機・負荷の差の可能性。同一機での再測は未実施)。
  - 旧版 REPORT の記録 (run 対応を再構成できないため値のみ保持): 「実行 2 (load 1.00 0.80 0.47)」PASS 195 s /
    「クリーン HEAD (204bba8)」PASS real 3m15.749s (load 1.28 0.94 0.59) / 「実行 2 (作業ツリー)」PASS real 3m14.790s。
    同名の「実行 2」が 2 値を指していたため、以後は P1〜P3 のラベルのみを使う。
- **ネガコン件数の再取得**: e2e ログは negctl 行を `tail -3` で切るため件数行が出ない。`qfc_e2e.sh` が作った
  `work/neg_<name>/qfcl.cjs` に対し `$QFC_PY qfc_diff.py --pe <PE> --cjs work/neg_<name>/qfcl.cjs --out work/recheck_neg_<name> --expect-fail`
  の全出力を取得: pmulhrsw equal 3 / mismatch 9、pshufb equal 2 / mismatch 10、phaddw equal 7 / mismatch 5 (3 本とも `native dst changed 10/10`、FAIL detected)。
- `find tools/qfclift -type f -size +20M -not -path '*/work/*'` → 0 件。生成物は `work/` (gitignore): `work/lift/qfcl.wasm` 15,115,363 B ほか。
