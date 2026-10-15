

## 10. PERF-P9 (#168) ④: closure の最適化 variant 別 build (LTO 効果)

検証起点: `origin/main` 36edc993 + 本節。環境: Actions runner (4 vCPU, load 0.6〜1.3)、素材 `fl-win64` + `toolchain-emsdk`。
同一 lift 産物 (`fle_lift.sh`: 7,018 関数 / 340,761 命令 / unsup 0) を variant 別に emcc link (`fle_lto.sh`)。

| variant | wasm (B) | emcc 所要 (s) |
|---|--:|--:|
| -O0 (既定) | 27,639,303 | 19.1 |
| -O2 | 13,705,498 | 87.4 |
| -O2 -flto | 11,122,894 | 108.8 |

実行確認 (`fle_lto_bench.mjs`: _UStrAsg 0x4133f0 + Move 0x409c80 の 2 関数を 7 種の n で反復、出力メモリの SHA-256 を取る):
20,000 反復 × 3 回の p50 (µs)。署名は 3 variant・3 回すべて一致 (`533e70fd7efebaa0`)。

| variant | 1 回目 | 2 回目 | 3 回目 |
|---|--:|--:|--:|
| -O0 | 0.450 | 0.341 | 0.290 |
| -O2 | 0.091 | 0.131 | 0.141 |
| -O2 -flto | 0.140 | 0.121 | 0.100 |

判定: **サイズと build 時間は実測で確定、実行時間は 2 関数の微小測定のみ**。-O2 系は -O0 の約 1/3〜1/4 の時間を示すが、
-O2 と -O2 -flto の差は回ごとに入れ替わり、LTO の効果は本測定では判定できない。
M11 級 (boot 連鎖) の closure 全体での実行時間は未測: boot closure の lift は RAM 上限で完走しない (`boot/REPORT_APPENDIX.md`, #918 = FLE-7)。

## 11. 環境パス置換 (#294 / #3603) の実測詳細

REPORT §11 の付録。指定の見出しは `## 10.` だが、既存の PERF-P9 節と衝突するため §11 とした。

検証起点: `origin/main` 03df83be4。測定 commit (コード): C1 `b5c49356c`。本節は別 commit (REPORT)。
環境: Actions runner (4 vCPU)。素材 `fl-win64` は展開して `FL_WIN64_DIR` で指定。`toolchain-emsdk` は成果物を展開せず、`fle_e2e.sh`・`fle_lift.sh` が直接 source する runner 既設の emsdk を使用 (emscripten 6.0.12。成果物・`tools/m1/flags.sh` の pin と同版を確認)。

### 11.1 変更

| ファイル | 置換内容 |
|---|---|
| `fle_nat.py` | `DLL` の既定を `FL_WIN64_DIR` 経由に。`sys.path` 追加と import は HERE の直後 (冒頭の ASLR 用 `setarch` 再実行より後) |
| `fle_diff.py` | `PE` の既定を同上 (`sys` は import 済み) |
| `probe_d9_disp.py` | `PE` の既定を同上。`sys` を import に追加し `HERE` を定義 |

`FLE_PE` → `FL_WIN64_DIR` → 既定、の優先順は不変。`fle_e2e.sh` は変更なし (既に `tools/shared/env.sh` を source)。
`git diff C1 HEAD -- tools/flelift/fle_nat.py tools/flelift/fle_diff.py tools/flelift/probe_d9_disp.py` は空 (本 commit までに変更なし)。

### 11.2 静的検証

| 検査 | 結果 |
|---|---|
| `python3 -m py_compile` (3 本) | OK |
| 旧既定値の残存 (3 本) | 0 件 |
| `bash tools/shared/test_paths.sh` | PASS (default / analysis_dir_only / individual_override / negctl) |
| 全変数未設定時の `FL_WIN64_DIR` | 従来の `[WIN64]` 既定と一致 |
| ネガティブ制御: `FL_WIN64_DIR` に存在しないディレクトリを指定し `probe_d9_disp.py` を実行 | `FileNotFoundError` (`<指定dir>/extracted/block00031_PE.bin` を開けず rc=1)。環境変数が効くことを確認 |

### 11.2b フォールバックの実測 (e2e 外、本 fix で追加)

`fle_e2e.sh` は `FLE_PE` を export してから `fle_diff.py`・`probe_d9_disp.py` を呼ぶため、この 2 本の `FL_WIN64_DIR` 式は e2e で評価されない。両スクリプトの先頭から PE 代入行 (`IMG = 0x400000` の直前まで) を exec し、解決先を 4 ケースで確認した (コード HEAD `ec306ec74`、コード変更なし)。

| 設定した環境変数 | PE の解決先 (両スクリプトで同一) |
|---|---|
| なし (すべて未設定) | `ANALYSIS_DIR` 既定 (`tools/shared/env.sh` の値) 配下の `win64/extracted/block00031_PE.bin` |
| `FL_WIN64_DIR=<存在しない dir>` | `<dir>/extracted/block00031_PE.bin` |
| `ANALYSIS_DIR=<存在しない dir>` | `<dir>/win64/extracted/block00031_PE.bin` |
| `FLE_PE=<存在しない file>` + `FL_WIN64_DIR=<存在しない dir>` | `<FLE_PE の値>` (`FLE_PE` 優先) |

4 ケースとも仕様どおり。

### 11.3 e2e before / after (`bash tools/flelift/fle_e2e.sh`、素材 `fl-win64`。`toolchain-emsdk` は展開せず、スクリプトが直接 source する runner 既設の `[EMSDK]` (6.0.12) を使用、`FL_WIN64_DIR` = 同一の展開先)

| 項目 | before (03df83be4) | after (C1 `b5c49356c`) |
|---|--:|--:|
| 所要 (s) | 158 | 157 |
| load average (1 分) 開始 → 終了 | 0.80 → 0.99 | 0.16 → 0.94 |
| 終了コード / 結果行 | rc=0 / `[fle_e2e] PASS` | rc=0 / `[fle_e2e] PASS` |
| lift | 7,018 関数 / 340,761 命令 / unsup 0 / unlifted callee 0 | 同左 |
| lift 所要 (ログ) | lift 19 s、emcc 40 s、合計 59 s | 同左 |
| smoke | UStrAsg case1・case2 OK、Move n=392/64/36/24/3/1/0 すべて OK | 同左 |
| spot diff | 7 関数 / 16 case / equal 16 | 同左 |
| D9 | rip-rel 136,333 site / mismatch 0 | 同左 |

### 11.4 比較

- ログ: 31 行。作業パス (worktree) と所要秒を正規化後に diff して一致。生の diff はパス 4 行のみ。
- 出力物: `work/verdict.jsonl`・`work/verdict_summary.json`・`work/lift/lift_meta.json`・`work/nat_results.jsonl`・`work/wasm_results.json`・`work/nat_cases.txt` と追跡の `results/verdict_flelift.jsonl`・`results/verdict_summary.json` の sha256 が全件一致。`work/lift/` (`flel.cjs`・`flel.wasm`・`fle_lifted.c`・`fle_data.c`・`lift_meta.json`) は `diff -rq` で同一。
- 追跡の `results/` 2 件は e2e がコピーで上書きするが、内容は HEAD と同一 (`git status` は空)。
- 検算 (別アルゴリズム): Python で `verdict.jsonl` の行 (7 行) と各 case の outcome を数え直し、`verdict_summary.json` (cases 16 / equal 16) と一致。`grep -c` でも照合して一致。D9 の prefix 別内訳 (none 10,569 / rex 106,219 / f2 9,049 / 66 2,542 / f3 7,765 / manual-unparsed 189) の合計は 136,333 で総数と一致。`lift_meta.json` の関数数 (7,018) はログと一致。

### 11.5 範囲

- 範囲内: `tools/flelift` 直下の 3 本と `fle_e2e.sh` (素材 `fl-win64` + emsdk 6.0.12)。
- 範囲外 (親 #294 の残り): `tools/flelift/boot`・`tools/icall` (#3604)・`tools/ott`・m11。
- 仕様差: `ANALYSIS_DIR` を設定した場合のみ既定が `$ANALYSIS_DIR/win64` になる (旧 3 本は `ANALYSIS_DIR` を見ていなかった)。両方未設定の既定は従来と同一。

## 12. #3661 (CI-173): `EMSDK_ENV` で emsdk を指定し、素材 `toolchain-emsdk` で e2e before / after

- **変更**: `fle_e2e.sh`・`fle_lift.sh` は `EMSDK_ENV` で `emsdk_env.sh` の場所を指定する (既定は `[EMSDK]` の `emsdk_env.sh`。未設定時の挙動は従来どおり)。ファイルが無ければ rc=2 で止まる。`fle_e2e.sh` は `emsdk_env.sh` の source 後に `EMSDK_ENV` を再 export する。`emsdk_env.sh` は `EMSDK_ENV` に触れないため (`[EMSDK]` の `emsdk_env.sh`・素材 `toolchain-emsdk` の `emsdk_env.sh`・`emsdk construct_env` の出力のいずれにも記述なし)、この再 export は子の `fle_lift.sh` へ渡す値を変えない。将来の emsdk の変化に備えた防御的な再 export。測定 commit `9e5f7f9f6` (最後にコードを変えた commit。以降の commit は REPORT のみ)。
- **素材**: `fl-win64` と `toolchain-emsdk` を `$RUNNER_TEMP` に展開 (`toolchain-emsdk` の最上位は `emsdk/`)。素材の emcc は 6.0.12 (commit `5488e0871d46`)。runner 既設の `[EMSDK]` と同一 commit。
- **素材が使われたこと**: `command -v emcc` で素材の `upstream/emscripten/emcc` が解決することを確認。初回 (`a85ca628d`) の素材版 run では素材側 `upstream/emscripten/cache` の 1,729 ファイルが更新され、`[EMSDK]` 側の更新は 0 件 (mtime 比較)。最終 HEAD の素材版 run は cache が暖まっており mtime の変化は出ないため、この確認は初回 run による。

| 項目 | before (`512b09ffa`・既定 `[EMSDK]`) | after 既定 (`9e5f7f9f6`・未設定) | after 素材 (`9e5f7f9f6`・`EMSDK_ENV`=素材) |
|---|--:|--:|--:|
| 所要 (s) | 121 | 119 | 120 |
| load average (1 分) 開始 → 終了 | 0.82 → 1.00 | 0.23 → 0.92 | 0.85 → 1.00 |
| 終了コード / 結果行 | rc=0 / `[fle_e2e] PASS` | rc=0 / PASS | rc=0 / PASS |
| lift 所要 (ログ) | lift 15 s、emcc 31 s、合計 46 s | lift 15 s、emcc 31 s、合計 46 s | lift 15 s、emcc 31 s、合計 46 s |
| lift | 7,018 関数 / 340,761 命令 / unsup 0 / unlifted callee 0 | 同左 | 同左 |
| spot diff | 7 関数 / 16 case / equal 16 | 同左 | 同左 |
| D9 | rip-rel 136,333 site / mismatch 0 | 同左 | 同左 |
| 出力 9 件の sha256 | 基準 | before と全件一致 | before と全件一致 |

- **出力 9 件**: `work/lift/` の `fle_lifted.c`・`fle_data.c`・`lift_meta.json`・`flel.wasm`・`flel.cjs`、`work/verdict.jsonl`・`work/verdict_summary.json`、追跡の `results/verdict_flelift.jsonl`・`results/verdict_summary.json`。
- **負の確認**: `EMSDK_ENV=<存在しない path>` で `fle_lift.sh`・`fle_e2e.sh` とも rc=2 とメッセージを出す。`fle_e2e.sh` が `EMSDK_ENV` で指定された `emsdk_env.sh` を source した後も、`EMSDK_ENV` の値が子の `fle_lift.sh` へ届くことを `bash -c` で確認 (`emsdk_env.sh` が `EMSDK_ENV` を書き換えないため、値は指定どおり)。
- **範囲外**: `fle_lto.sh` は `[EMSDK]` を直接 source したまま (e2e・lift の経路外で、本 issue の受入の対象外)。

## 13. REPORT §6 未解決・限界 (分割移動)


1. **[解消済 CAB-232] 0x6a7990 (MMX RGB 乗算) の dst 1-3 block が byte 単位で不一致** (16 case 中 2 case) — 原因は lift ではなく wasm 側 harness の scratch 初期化 no-op。以下は初版時の記述:r戻り値・xmm0・他の
   メモリは一致。packuswb/pmulhuw の primitive 単位は実機 probe で式を確認済みゆえ、ループ内の状態伝搬
   (eax leftover の `shl eax,16` 経由引継ぎ等) の差と推定。再現: `python3 fle_diff.py` (harness 完備)。
   → CAB-232/233 の liftdiff 本格採点で原因特定を推奨。
2. **D12 (Delphi landing pad, 879 site)** は未対応 — CAB-227 の範囲。SEH/例外経路に入る関数は fail-fast。
3. x87 は制御命令のみのモデル (x87_cw/x87_sw)。FLEngine lift 集合に x87 演算は出現しないことを確認済みだが、
   集合外関数には x87 演算が残る。ldmxcsr/stmxcsr は値の退避のみ (FTZ/DAZ 等の演算反映は未実装)。
4. cpuid/rdtsc/xgetbv は固定値モデル (CPUID leaf1 = 0x178bfbff/1, XCR0 = 7)。CPU 特性分岐は SSE2 側に寄る。
5. .text は原則 data 敷設せず jump table 窓 (1) + rip-rel textref 窓 (3,225) のみ。.text をデータとして
   読む経路が他にあれば fail-fast で顕在化する。
6. FastMM boot (`_InitLib` 8 引数含む unit init 連鎖) は未実施 — M11 (CAB-5) の領域。本 ticket は lift 基盤。
7. native spot diff は single-thread 前提 (lock 系非 atomic)。

## 14. #4234 (T-SH-104): rt の Win32 TLS import (TlsAlloc・TlsGetValue・TlsSetValue) を Windows 仕様に合わせる

- 変更前の実装: `TlsAlloc` は常に 0。`TlsGetValue` は `FLE_TLSARRAY` (gs:[0x58] の配列) を読むため、`fle_install_teb` で非 0 を入れた未設定 slot でも非 0 を返す。
- 変更後 (`rt/fle_cpu.c`): `TlsAlloc` は 0,1,2,… の連番 (上限 64 で超過は 0xFFFFFFFF)。Win32 TLS は `g_tls_val[64]` (0 初期化) に別管理し、未割当・未設定の slot は 0。`TlsSetValue` は割当済み slot のみ TRUE。gs:[0x58] の TLS 配列 (コンパイラ生成 TLS 用) と `fle_install_teb` は変えない。
- `GetCurrentThreadId` は変えない (実物の値の根拠が無いため。未確認のまま)。

### 14.1 e2e (`bash tools/flelift/fle_e2e.sh`、素材 `fl-win64`・`toolchain-emsdk`)

| 測定 commit | real | load (開始→終了) | lift | spot diff | D9 | 判定 |
|---|---|---|---|---|---|---|
| `9c0dfadc9` (変更前 = 当時の main、変更なし) | 158 s | 0.61 → 1.12 | 7,018 関数 / unsup 0 | equal 16/16 | mismatch 0 | PASS |
| 作業ツリー (変更後) | 141 s | 0.23 → 0.93 | 同上 | equal 16/16 | mismatch 0 | PASS |
| `973b85aca` (main 取り込み前の測定 commit) | 142 s | 0.58 → 0.96 | 7,018 / unsup 0 | equal 16/16 | mismatch 0 | PASS |
| **`6035a72d5` (測定 commit、コミット済み HEAD。main 取り込み後)** | 153 s (1 回目) / 150 s (2 回目) | 0.84 → 0.93 (1 回目) / 0.50 → 1.06 (2 回目) | 7,018 / unsup 0 | equal 16/16 | mismatch 0 | PASS |

`973b85aca` → `6035a72d5` の差分は `rt/fle_cpu.c` (+2/-1)・`rt/fle_cpu.h` (+2) の `fle_gpa_hook` 結線のみ (既定 0 = 従来挙動)。両 run とも同じ HEAD で再現した。

spot diff の 16 case は TlsAlloc 系を呼ばないため、この e2e では TLS の挙動変化は見えない (下の 14.2 で直接確認)。

### 14.2 TLS の直接確認 (`tools/flelift/rt/fle_cpu.c` を単体リンクした C harness)

- harness は **未コミット (手元検証)**。`tools/flelift` にはコミットしていないため、再実行できない。
- 件数の数え方: 下表の**行数 6 件**がすべて ok (表の 6 行が検査の全件。「連番 0,1」は `TlsAlloc` 2 回の 1 行に含まれる)。

| 検査 | 結果 |
|---|---|
| 割当前の `TlsGetValue(0)` | 0 |
| `TlsAlloc` 2 回 | 0, 1 (連番) |
| `TlsSetValue(0, 0xdeadbeef)` → `TlsGetValue(0)` | TRUE → 0xdeadbeef |
| 割当済みで未設定の slot | 0 |
| 未割当 slot の `TlsGetValue` | 0 |
| 未割当 slot の `TlsSetValue` | FALSE |

harness は `fle_glue.c` を含めない (`ott_dispatch` が未定義で link できないため)。`fle_cpu.c` の TLS 関数だけを検査した。

### 14.3 DllMain 経路 (issue 本文が挙げた `tools/qfclift/qfc_count.sh`)

- **受入 3 は未達**。issue 本文の `qfc_count.sh` は repo に存在しない (`origin/main` で確認)。`tools/qfclift/REPORT.md` にも §10 は無い (§9 まで)。
  計数の確認は子 issue **#4307** (`[T-SH-116]`) で行う。
- 代わりに `tools/qfclift/qfc_boot.sh` で DllMain 経路の**停止点のみ**を確認した。これは計数の確認ではない。
- 測定 commit `973b85aca` (`QFC_BOOT_REBUILD=1`、素材 `fl-win64`・`toolchain-emsdk`、単発の real 43 s、load 0.80 → 0.55。`qfclift/REPORT.md` §7.3 の n=3 (26 s) とは別測定。下記の 43 s は HEAD `973b85aca` の単発 1 回。`qfclift/REPORT.md` §7.3 の n=3 (26–26 s) は別 HEAD `1fd48d2ce` の値で、差は未切り分け):
  - strict: `DllMain(PROCESS_ATTACH)=trap`・`[fle] MISSING IMPORT LocalAlloc`・soft 0 件 → FAIL
  - soft: `DllMain=trap`・`[fle] call to UNLIFTED function 0x59c210`・soft 呼出し 0 件 → FAIL
- REPORT §7.3 (HEAD `1fd48d2ce`) と停止点・停止理由が一致。TLS 変更で DllMain の停止点は変わらない。

## 15. x64c の addsubpd / vpmovsxdq / vshufps 追加の実測 (#3721)

- 測定 commit: `a9d238a14` (閉包・ネガコン・差分テストの PR 作成時の実測)。
- 閉包 (`KH_CORE=<HeartCore.core_64> OUT=<work/> bash tools/targets/kilohearts/scripts/ladder_x64c_closure.sh`・real 27.546 s): 改変前 functions 98 / insns 7,766 / unsup 38 (rcpps 34・addsubpd 2・vpmovsxdq 1・vshufps 1) / imports 17 / traps 0。改変後 unsup **34** (rcpps 34 のみ)。HeartCore sha256 先頭 16 hex `d55ce8b4c0ad7ebe` (76,642,304 B)。
- ネガコン (roots = process slot 14 のみ): functions 2 / insns 178 / unsup 0 (不変)。
- 差分テスト `python3 tools/flelift/tests/x64c_vex_diff.py`: pass 91 / fail 0 (rc 0)。
- addsubpd ネガコン (加減を入れ替え): `FAIL addsubpd xmm1, xmm2`・pass 90 / fail 1 (rc 1)。改変後に退避コピーから戻し、`cmp` で一致を確認してから再実行 (pass 91 / fail 0)。
- 再実行の範囲: fix モード (`ws-4056` worktree・commit 後の HEAD) では差分テストとネガコンのみ再実行。閉包 e2e は `plugins-kilohearts` 由来の `HeartCore.core_64` が `fl-win64` に無く再実行していない (上記は a9d238a14 の値)。


## 16. x64c の rcpps / vrcpps 実装 (#4054・閉包 unsup 34 → 0)

- 測定 commit: `a8d4b6e0d` (rcpps / vrcpps を `kh_rcp_exact` で実装。以後コード変更なし)。
- 閉包 (`KH_CORE=<HeartCore.core_64> OUT=<work/> bash tools/targets/kilohearts/scripts/ladder_x64c_closure.sh`): 改変前 (origin/main 6551d8b64) は real 25.877 s・functions 98 / insns 7,766 / unsup **34** (`rcpps:rcpps` 34 site)。改変後 (a8d4b6e0d) は real 25.402 s・functions 98 / insns 7,766 / unsup **0** / imports 17 / unlifted 0 / traps 0。関数数・命令数は前後で不変。
- ネガコン (roots = process slot 14 のみ): functions 2 / insns 178 / unsup 0 (前後で不変。生成 C は改変前後で `cmp` 一致)。
- 差分テスト `python3 tools/flelift/tests/x64c_vex_diff.py`: pass 100 / fail 0 (rc 0)。rcpps 3 件 (`rcpps xmm1, xmm2`・`rcpps xmm3, xmm3`・`vrcpps xmm1, xmm2`) を追加。(測定 commit `a8d4b6e0d` 時点は pass 94 / fail 0。main 取り込みで x64c の追加命令分が増えた。)
- rcpps ネガコン `python3 tools/flelift/tests/x64c_vex_diff.py --neg-rcp=0` (表 entry 0 を 1 bit 改変した C を生成): `FAIL rcpps xmm1, xmm2`・`FAIL vrcpps xmm1, xmm2`・pass 98 / fail 2 (rc 1)。(測定 commit 時点は pass 92 / fail 2。)
- HEAD `9c30210af` での実測 (main 取り込み後): 差分テスト pass 100 / fail 0 (rc 0)、ネガコン pass 98 / fail 2 (rc 1)。閉包 (real / functions / insns / unsup) の HEAD 再測定は未実施。素材 `plugins-kilohearts` が無く実行できないため。閉包値 98 / 7,766 / unsup 0 は測定 commit `a8d4b6e0d` の値。
- 測定 commit `a8d4b6e0d` から HEAD までの code 差分: `tools/flelift/x64c.py` と `tests/` に計 133 行 (main 取り込み分の vandps・vpsrld/vpslld・vcvtdq2ps・vcomiss・haddps を含む)。差分 0 ではないため、閉包の HEAD 再測定が必要。
- 生成 C の構文: `gcc -fsyntax-only fle_lifted.c` rc 0 (閉包 1,006,164 B)。
- 近似表の出所: `tools/targets/kilohearts/snapins/scripts/approx_tables.b64` (gen_simd.py の `kh_rcp_exact` と同一表・同一式)。表は rcpps を含む生成 C の先頭にだけ入る。
- 素材の取り出し: `plugins-kilohearts` → `HeartCore.core_64` (76,642,304 B)。手順は `tools/targets/kilohearts/REPORT_KH19D.md`。
