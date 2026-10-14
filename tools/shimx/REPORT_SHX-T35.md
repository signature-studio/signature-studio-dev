# SHX-T35 (#3023): HeapFree の割当てのない p を main 現行の M4 テスト契約に揃えた判断と測定

結論: `bash tools/shimx/test.sh` の step 5 (M4 互換 MT/ST) が PASS する。HeapFree の割当てのない p (範囲外・magic 不一致) は、main 現行の `tools/shim/test/test_main.c` の契約 (native 参照: `TRUE` / `ERROR_SUCCESS`、#3049 で確定) に揃えた。`blk_ok` には wasm linear memory の範囲検査を入れた。対象 issue: [#3023](https://github.com/signature-studio/signature-studio-dev/issues/3023)。

## 1. 背景

- 失敗箇所 (修正前): `tools/shim/test/test_main.c:204` の `ERROR_INVALID_FUNCTION` 検査。shimx の HeapFree は `ERROR_INVALID_PARAMETER` を返していた。範囲外ポインタ `0x1` などを読むと、範囲検査が無いため wasm が trap し得た。
- 契約の変化: #3049 (#2821) が main に merge された (`521b0e9a`)。`tools/shim/test/test_main.c:203-204` と `:212-213` は、HeapFree の範囲外ポインタと割当ての無い範囲内ポインタに `TRUE` / `ERROR_SUCCESS` を期待する。shimx の step 5 は同じ test_main.c を無改変で使うため、shimx もこの契約に揃える。前版は M4 の旧契約 (`FALSE` / `ERROR_INVALID_FUNCTION`) に揃えていたが、#3049 の取り込みで合わなくなったため撤回した (旧版の測定値は本ファイルから外した。履歴は Git に残る)。
- 取り込み: main `3e8c8d25` を merge commit `4be68ee6` で取り込んだ。取り込み後の HeapFree は旧版のままで、step 5 が `test_main.c:203` で FAIL した (§4.2 の基点)。
- 再現コマンド: `bash tools/shimx/test.sh`。

## 2. 契約の判断

| 対象 | main 現行の `test_main.c` (native 参照) | 修正前 shimx | 修正後 shimx | 判断 |
|---|---|---|---|---|
| `HeapFree` 割当てのない p (範囲外・magic 不一致) | 戻り値 `TRUE` (`:203` `:212`)、GetLastError `ERROR_SUCCESS` (`:204` `:213`) | `FALSE` / `ERROR_INVALID_FUNCTION` | `TRUE` / `ERROR_SUCCESS` | main 現行の契約に揃える。native 参照 (`tools/liftdiff/rt/ld_core.h` の HeapFree は引数を見ず 1) と同じ応答 |
| `HeapReAlloc` 不正 p | 戻り値 `NULL` のみ検査 (errcode は未検査) | `ERROR_INVALID_PARAMETER` | 変更なし | テストが検査していない。#3070 で扱う |
| `GlobalLock` / `GlobalUnlock` / `GlobalFree` 不正ハンドル | 戻り値のみ検査 (`:205` `:207`) | `ERROR_INVALID_HANDLE` | 変更なし | 同上。#3070 で扱う |

- Win32 の実仕様: `HeapFree` の不正 p は `ERROR_INVALID_PARAMETER` と推定 (未検証。Win32 実機では確認していない)。今回の契約は native 参照と M4 テストに従うため、Win32 実仕様との差は残る。#3070 で扱う。

## 3. 変更内容

`tools/shimx/src/heap.c` の 2 箇所。PR 全体の差分 (main `3e8c8d25` から測定 commit `5b75b8c2` まで) は次のとおり。

- A. `blk_ok` に範囲検査を追加 (commit `8fdaee48` 由来・契約変更なし)。`u < HEAP_HDR || u > mem` (`mem` は wasm linear memory の byte 数、64bit で計算)。`tools/shim/src/heap.c` の `block_ok` (#2802 / LD-132) と同じ考え方。範囲外のポインタを読まずに 0 を返す。
- B. `HeapFree` の割当てのない p の分岐を `FALSE` / `ERROR_INVALID_FUNCTION` から `TRUE` / `ERROR_SUCCESS` に変更 (commit `5b75b8c2`)。解放せず、TRUE を返す。`tools/shim/src/heap.c` の HeapFree と同じ応答。

差分 (`git diff 3e8c8d25 5b75b8c2 -- tools/shimx/src`):

```diff
 static int blk_ok(void* user) {
-    if (!user || ((uintptr_t)user & 15u)) return 0;
+    /* ヘッダ 16B が wasm linear memory の内に収まるかを先に確かめる (範囲外は読まない / LD-132 #2802) */
+    uint64_t u = (uintptr_t)user;
+    uint64_t mem = (uint64_t)__builtin_wasm_memory_size(0) * 65536u;
+    if (!user || ((uintptr_t)user & 15u) || u < HEAP_HDR || u > mem) return 0;
     return ((Hdr16*)raw_of(user))->magic == HEAP_MAGIC;
 }
@@ HeapFree(HEAP_HANDLE heap, DWORD flags, LPVOID p) {
     if (!p) return TRUE;
-    if (!blk_ok(p)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
+    /* 割当てのない p (範囲外 / magic 不一致) は解放せず TRUE。tools/shim/src/heap.c と同じ応答 (native 参照 #2821 / #3049) */
+    if (!blk_ok(p)) { SetLastError(ERROR_SUCCESS); return TRUE; }
```

(B だけの差分は `git diff 4be68ee6 5b75b8c2 -- tools/shimx/src`。A は取り込み基点 `4be68ee6` に既に含まれ、この範囲では HeapFree の 1 行を置き換えるだけになる。)

## 4. 測定

環境: `nproc` = 4、load average は `/proc/loadavg` の 1 分平均 (開始 → 終了)。所要秒は `date +%s` の差。emcc は `[EMSDK]` (emsdk 6.0.12。`emsdk install 6.0.12` で上流から取得し、run 内で `[EMSDK]` の位置に配置)。素材の `toolchain-emsdk` は使っていない。`llvm-nm` は emsdk 同梱版を PATH に置いた。測定ログは作業用の一時ディレクトリ (repo 外・commit 対象外) に置いた。

### 4.1 測定 commit

- 測定 commit: `5b75b8c2` (`fix(shimx): HeapFree の割当てのない p を native 参照と同じ TRUE に揃える (SHX-T35, #3023)`)。
- `git diff 5b75b8c2 HEAD -- tools/shimx/src` (HEAD = 測定 commit 以降の REPORT 修正のみ): 0 行。コード差分は無く、測定結果は HEAD でも有効。

### 4.2 基点 (修正前、main 取り込み merge `4be68ee6`)

- rc=1、所要 23 秒、load 0.99 → 1.07。
- 出力: step 4 (fail-fast) の全項目が ✓ まで進んだ後、step 5 で `[M4-test] FAIL tools/shim/test/test_main.c:203: HeapFree(heap, 0, p) == TRUE`、`[shimx] FAIL: M4 互換 MT 失敗`。
- main の契約 (TRUE) に対して shimx が FALSE を返すため失敗する。B1 の事象 (#3049 取り込み後に step 5 が FAIL) の再現。

### 4.3 修正版 (測定 commit `5b75b8c2`、n=3)

| run | rc | 所要 (秒) | load (開始 → 終了) | PASS 行 |
|---|---|---|---|---|
| 1 | 0 | 53 | 0.16 → 0.59 | `M4 テスト (MT/ST) PASS` / `7/7 完了: shimx 697 公開関数 × MT/ST × M4 互換 × fail-fast 全 PASS` |
| 2 | 0 | 50 | 0.50 → 0.88 | 同上 |
| 3 | 0 | 50 | 0.88 → 1.07 | 同上 |

- n=3 の所要: min 50 秒、max 53 秒。run 1 は emsdk 導入直後の初回実行。

### 4.4 ネガティブコントロール (範囲検査 `u < HEAP_HDR || u > mem` だけを外す、1 回)

- 測定 commit の `blk_ok` から範囲検査の 1 条件だけを `sed` で外して実行し、直後に `git checkout -- tools/shimx/src/heap.c` で測定 commit の内容に戻した (復元後 `git diff 5b75b8c2 -- tools/shimx/src` は 0 行)。
- rc=1、所要 23 秒、load 1.14 → 1.19。step 5 MT で `RuntimeError: memory access out of bounds` (`build/m4_mt.err`)。範囲検査が wasm trap を防いでいる。
- ST 側は step 5 の MT で止まったため未実行。

### 4.5 生成物 (test.sh step 6 の再生成)

- step 6 は `tools/shimx/BACKLOG.md`・`data/coverage.json`・`data/inventory.csv`・`inventory.md` を再生成する。本環境には gitignore 対象の入力 (`tools/m11/work/`・`tools/m8/work/`) が無く、M11 closure と OTT 列が空の値になる。
- commit していない。実行後は HEAD の内容に戻した。PR にも含めない。生成物の入力欠落ガードは #3069 で扱う。

## 5. 検証範囲 / 範囲外

- 検証した (test.sh rc=0): step 0〜5 (MT/ST・fail-fast・M4 互換)、step 6 の `sig_test.sh` (合成 fixture 8 項目が ALL PASS)、coverage gate (rc=0)。
- 検証していない (SKIP / 入力なし): step 6b の `sig_gate` (M11 IR 無し)、step 6c R6 (`boot_final3.ll` 無し)、step 7 OTT (`SKIP: tools/m8/work/ott_m8.ll` 無し)。本 PR は IR 経路 (M11・OTT) に触れていないが、そこで検出される回帰は本測定では見ていない。
- 範囲外: 他関数の errcode (`HeapReAlloc`・`GlobalLock`/`GlobalUnlock`/`GlobalFree`、#3070)、Win32 実仕様の実機確認、step 2 の emcc 無出力事象 (#3069)、ST 側のネガティブコントロール。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| step 2 の emcc が exit 0 のまま `build/shimx_test_mt.js` を出さない事象 (元 issue で 4 回中 1 回。本測定の 6 run では再現せず、原因未特定) | test.sh が偽の失敗・成功を出し得る | #3069 (`[SHX-T36]`) |
| test.sh step 6 が M11/M8 入力欠落の環境で inventory・BACKLOG・coverage を空の値で再生成する。`shimx_*` フック数の既存ずれ (69 → 78) も含む | 生成物を commit すると M11/OTT 列が消える | #3069 (`[SHX-T36]`) |
| `HeapReAlloc` (ERROR_INVALID_PARAMETER)、`GlobalLock`/`GlobalUnlock`/`GlobalFree` (ERROR_INVALID_HANDLE) の errcode は M4 テストが未検査。`HeapFree` の Win32 実仕様 errcode (推定 ERROR_INVALID_PARAMETER・未検証) | native と wasm で不正入力時の errcode が揃うかは未確認 | #3070 (`[SHX-T37]`)。LD 側の応答表は #2821 |
| PM 確認: #3049 の native 参照 (TRUE) を既定とする。覆すなら #3049 の戻しが要る | 本 PR は #3049 の契約に揃えた。覆す場合は本 PR と #3049 の両方の変更が要る | PM 判断 |

関連: #2916 (親 issue。CLOSED のため追跡は #3069・#3070 に移した)・#2802 (`block_ok` の範囲検査の元)・#2821 (native/wasm の HeapFree 応答表の統一)・#3049 (merge 済み `521b0e9a`。HeapFree の契約を native 参照 TRUE に確定)。
