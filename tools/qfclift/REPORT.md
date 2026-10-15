# tools/qfclift — T-SH-12 (#154): QuickFontCache_x64.dll を FLEngine と同じ x64c パイプラインで lift

既知類型との関係 (docs/DEFECTS.md): 該当なし (新規類型の発見なし)。ただし D2 (DEFECTS.md, movaps 上位 64bit) 系の
「XMM 命令 lift の bit 一致」を native 実機械語との直接比較で検査する方針は同じ。

## 0. 結論 (先出し)

- **boot (#3289 / T-SH-60): DllMain(PROCESS_ATTACH) の wasm 実行は FAIL** (§7)。strict (実装済み import のみ) は kernel32 `LocalAlloc` で停止。
  `LocalAlloc` を実装し、残りの未実装 import を soft stub に置き換えても、setjmp 系の戻り先 `0x59c210` (関数の途中) へ longjmp して UNLIFTED で停止。
  FreeType の FT_* 結合はこの停止より後段のため未到達。**InitDll は QuickFontCache の export ではない** (§7.1)。
- **判定: 部分達成 (lift + wasm build + 2 関数の native 一致まで。boot は §7 の停止点の測定まで)**。#154 の受入範囲
  (QuickFontCache → ILTools → FruityPlug) のうち **QuickFontCache の lift 層だけ**を完了。ILTools / FruityPlug(SGv2) は未着手 (§5)。
  #154 は ILTools / FruityPlug が残るため閉じない (`Refs #154`)。本 PR (boot 測定) の Closes は #3289 のみ。
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
| `qfc_lift.sh` | lift → emcc の共通関数 (`lift_build` / `wasm_build`)。`qfc_e2e.sh` と `qfc_boot.sh` が source する (処理は同一) |
| `qfc_boot.sh` / `qfc_boot.mjs` | boot 実行 (§7)。strict / soft の 2 版で DllMain → FontCache_GetStats → FontCache_CleanUp を実行し、判定 JSON を `work/boot/` に出す |
| `gen_soft_imp.py` / `qfc_imp.c` | rt に無い import を soft stub で埋める生成器 (`gen_soft_imp.py`)。`qfc_imp.c` は `LocalAlloc` / `LocalFree` の実装 |

実行: `FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=<capstone/pefile 入り python> bash tools/qfclift/qfc_e2e.sh`
boot 実行: `FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=python3 QFC_BOOT_REBUILD=1 bash tools/qfclift/qfc_boot.sh` (§7.2)

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
| QFC の boot (DllMain → FontCache_*) が wasm で完走しない (§7)。FT_* 結合は未到達 | lift が実行時に正しいかは未確認 | #3410 (戻り先 0x59c210) / #3411 (未実装 import) / #3412 (FT 結線と FontCache_*) |
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

## 7. boot 実行の測定 (T-SH-60 / #3289)

既知類型との関係 (docs/DEFECTS.md): 該当なし (DEFECTS は stage-0 / RetDec 系の類型。x64c の setjmp/longjmp 継続は別事象)。
FLEngine boot の同型 (longjmp の `--override` と断片 entry) を参照 (`tools/flelift/boot/fle_boot.c` 489〜504 行、`boot_e2e.sh`)。

### 7.1 対象の読み替え

- QuickFontCache の export は 10 本 (§0)。`InitDll` は**含まれない** (pefile で ImageBase `0x400000` の export 表を確認)。
- `InitDll` は `CreateVST3Instance` (VA `0x58a200`) が `LoadLibraryW(<.vst3 のパス>)` の後に `GetProcAddress("InitDll")` で呼ぶ、**VST3 モジュール側**の関数 (`tools/hostbridge/nfo/REPORT_APPENDIX_A.md` の `CreateVST3Instance` 節)。QFC に InitDll が無い根拠は export 表 (上の 10 本に無い) のみ。
- QFC 自身の初期化は PE entry = DllMain (`AddressOfEntryPoint` RVA `0x19c1f0` → VA `0x59c1f0`)。**本測定は DllMain(PROCESS_ATTACH) を boot の起点とした** (読み替えは PM 判断の範囲。受入の「InitDll」は DllMain と読んだ)。

### 7.2 手順 (再現)

`FL_WIN64_DIR=<fl-win64 展開先> QFC_PY=python3 bash tools/qfclift/qfc_boot.sh` (`QFC_BOOT_REBUILD=1` で lift から作り直す)。

1. lift: `qfc_lift.sh` の `lift_build` (qfc_e2e.sh と同一の x64c・emcc 設定)。
2. **strict**: rt (`tools/flelift/rt`) の実装済み import だけで wasm を作って実行。
3. **soft**: rt と `qfc_imp.c` に無い import を `gen_soft_imp.py` の soft stub (呼出しを stderr に記録し 0 を返す) で埋めて実行。`qfc_imp.c` は `LocalAlloc` / `LocalFree` のみ (calloc。戻り値は実物と同じ規約)。
4. 各版の段: `DllMain(hinst=0x400000, DLL_PROCESS_ATTACH, 0)` → `FontCache_GetStats(buf)` → `FontCache_CleanUp()`。1 段でも trap したら以降は実行しない。
5. 判定 (`qfc_boot.mjs`): **PASS = 3 段 ok かつ DllMain の RAX = 1 かつ soft 呼出し 0 件**。soft 呼出しが 1 件以上なら SOFT 扱い (PASS にしない。exit 1)。停止理由 `stopped_by` は stderr の最後の `[fle]` 行 (無ければ trap の文字列)。

soft stub の戻り値は実物ではないため、PASS の根拠にしない。

### 7.3 結果 (HEAD `1fd48d2ce`・n=3。各 run は lift + emcc×2 + 実行×2 を含む)

| 版 | 段 | 停止点 (JSON の `stopped_by`) | soft 呼出し | 判定 |
|---|---|---|---|---|
| strict | DllMain | `[fle] MISSING IMPORT LocalAlloc` (rt に実装なし) | 0 | FAIL |
| soft | DllMain | `[fle] call to UNLIFTED function 0x59c210 ret=0` | 0 | FAIL |

- 3 run (`QFC_BOOT_REBUILD=1 bash tools/qfclift/qfc_boot.sh`・逐次・foreground・nproc 4)。3 run とも判定 JSON は表と同一:

| run | real (script 計測) | load 開始 | load 終了 |
|---|---|---|---|
| B1 | 26 s | 0.39 0.30 0.12 | 0.60 0.35 0.15 |
| B2 | 26 s | 0.49 0.35 0.15 | 0.73 0.41 0.18 |
| B3 | 26 s | 0.73 0.41 0.18 | 0.84 0.47 0.21 |

- **min–max (n=3): real 26–26 s** (script は秒単位で計測)。前回の n=1 (HEAD `f1dc143e5`) の 44.94 s・レビュー側の 50.5 s との差は未切り分け (同一 HEAD の 3 回は一致)。
- import 集計 (`gen_soft_imp.py` の出力): 使用 222 件 / rt 実装 58 件 + `qfc_imp.c` 2 件 = 実装済み 60 件 / soft stub 162 件。
- 計数の動作確認 (HEAD `f1dc143e5` での試行。`qfc_imp.c` を渡さない版): `LocalAlloc` が soft 化された状態で DllMain の停止までに soft 呼出し **2 件** (`LocalAlloc`・`MessageBoxA`) を記録し、同じ `0x59c210` で停止した。この試行は commit に含まない (`gen_soft_imp.py` の引数から `qfc_imp.c` を外して再現できる)。

### 7.4 停止点の解析 (逆アセンブル・capstone による実測)

- DllMain (VA `0x59c1f0`) の `0x59c20b`: `call 0x40fa30`。`0x40fa30` は `lea rcx,[rcx+0x38]; jmp 0x40f950`。
- `0x40f950` は rcx に戻り番地・rsp・rbx/rbp/rsi/rdi/r12〜r15・xmm6〜15 を保存する **setjmp 相当** (lift 版 `f_40f950` は `ret` が C の return になり、正常に戻る)。
- `0x40f9c0` は保存値を復元し `jmp qword ptr [rcx]` で保存先へ戻る **longjmp 相当**。lift 版は `ott_dispatch(LD64(rcx))`。
- 保存された戻り番地 `0x59c210` は DllMain の `call` の直後 (関数の途中)。x64c の dispatch は関数先頭だけを受けるため、`UNLIFTED` で停止する。
- 未切り分け: longjmp を起動する呼出し元と条件 (`0x40fa40` 系の経路。strict の `LocalAlloc` 停止と soft 版の `MessageBoxA` 呼出しとの関係も未確定)。

### 7.5 FreeType (FT_* 14 本) の結合: 未到達

- DllMain 内で FT 解決 (`0x563000`) に入る前に停止する。`imp_GetProcAddress` は rt で常に 0 を返す (`tools/flelift/rt/fle_cpu.c` 156 行)。
- #3263 の実測 (Wine + 無改変 DllMain): QFC 範囲の GetProcAddress 950 件のうち FT_* 14 件 (戻り値は stub の NULL)。この経路は本測定では通っていない。
- FreeType 2.7 の wasm32 ビルド (`tools/shared/oss/freetype/build.sh`、#145 採用方式) は未実施。`qfc_import.c` の表 (14 本) は既存のまま。

### 7.6 検証範囲 / 範囲外

- 範囲内: strict / soft の 2 版で DllMain の停止点を再現 (HEAD `1fd48d2ce` で n=3、`f1dc143e5` で 1 回、`qfc_imp.c` を渡さない試行で 1 回。いずれも同じ停止点)。
- 範囲外 (主張しない): `FontCache_GetStats` / `FontCache_CleanUp` は未実行 (DllMain 失敗のため到達しない。引数仕様は REPORT に無い)。FT_* 結合。残り 162 import の挙動。DllMain 以外の export。

### 7.7 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 戻り先 `0x59c210` (setjmp/longjmp 継続) の lift 対応 (FLEngine 同型の override と断片 entry) と longjmp の起動元の特定 | DllMain が完走しない | #3410 (T-SH-77) |
| rt 未実装の import 162 件のうち、DllMain 経路で実際に呼ばれるものの実装 | 同上。soft stub の 0 返しは実物ではない | #3411 (T-SH-78) |
| GetProcAddress → FT_* 14 本 (`qfc_import.c`) の結線と FontCache_GetStats / CleanUp の実行 (PASS 判定) | FT 結合と boot 全体の検証 | #3412 (T-SH-79) |

## 8. 検証実行・再現 (§7 の追加分・実測)

- 測定 commit: e2e の E1〜E3 は **`f1dc143e5`** (コードを変えた commit。`qfc_lift.sh` の切り出しと `qfc_boot.*` 追加・`qfc_e2e.sh` の関数の source 化)。
  検証 HEAD = **`1fd48d2ce`** (`b5fa0f2f3`: `qfc_boot.mjs` の 1 行 + main 取り込み merge)。e2e の H1〜H3 と boot の B1〜B3 はこの HEAD で測定。
- `git diff f1dc143e5 HEAD -- tools/qfclift ':(exclude)*.md'` の出力は下記の 1 行 (`qfc_boot.mjs` のみ。e2e は読まない)。`git diff f1dc143e5 HEAD -- tools/flelift tools/liftlib tools/shared/env.sh` は 0 行 (lift の依存)。

```diff
-  stopped_at: stop ? stop.name : null, stopped_by: stop ? (stop.stderr[0] || stop.trap) : null,
+  stopped_at: stop ? stop.name : null, stopped_by: stop ? (stop.stderr.at(-1) || stop.trap) : null,
```

- e2e (`qfc_e2e.sh`、逐次・foreground)。H 行は `date +%s.%N` の差、E 行は `/usr/bin/time`:

| run | HEAD | 結果 | real | load 開始 | load 終了 |
|---|---|---|---|---|---|
| H1 | `1fd48d2ce` | PASS (exit 0) | 66.43 s | 0.65 0.45 0.20 | 0.89 0.56 0.26 |
| H2 | `1fd48d2ce` | PASS (exit 0) | 67.37 s | 0.83 0.56 0.26 | 0.94 0.65 0.31 |
| H3 | `1fd48d2ce` | PASS (exit 0) | 67.82 s | 0.94 0.65 0.31 | 0.98 0.72 0.37 |
| E1 | `f1dc143e5` | PASS (exit 0) | 116.87 s | 0.10 0.23 0.17 | 0.87 0.48 0.28 |
| E2 | `f1dc143e5` | PASS (exit 0) | 116.97 s | 0.74 0.47 0.27 | 1.14 0.72 0.39 |
| E3 | `f1dc143e5` | PASS (exit 0) | 116.70 s | 1.14 0.72 0.39 | 1.02 0.82 0.47 |

- **min–max (HEAD `1fd48d2ce`、n=3、全 PASS): real 66.43–67.82 s**。load 開始 0.65–0.94。
- min–max (HEAD `f1dc143e5`、n=3、全 PASS): real 116.70–116.97 s。前回測定 (`5c7a48a`、§6 の P1〜P3: 196.08–196.70 s) との差は未切り分け。
- 参考 (min–max に含めない):
  - レビュー側 (oc-reviewer) の独立再実行 (HEAD `6c22d26aa`・n=1): PASS real 129.5 s (load 開始 0.63)。
  - 3 つの値域 (66 s 台 / 116 s 台 / 129 s・196 s) の差は未切り分け。同一 HEAD の H1〜H3 は 1.4 s の範囲に収まっており、runner の負荷差の可能性がある (同一機での再測は未実施)。
- e2e の内容は §3 と同一: functions 6,347 / unsup 0 / unlifted 0 / spot diff 12/12 equal (H1〜H3 とも) / ネガコン 3 本 (pmulhrsw・pshufb・phaddw) すべて FAIL 検出 (H1〜H3 とも)。
- boot (`qfc_boot.sh`、HEAD `1fd48d2ce`、n=3): §7.3 の通り (real 26–26 s、判定は 3 run とも FAIL)。
- `find tools/qfclift -type f -size +20M -not -path '*/work/*'` → 0 件。生成物は `work/` (gitignore)。
