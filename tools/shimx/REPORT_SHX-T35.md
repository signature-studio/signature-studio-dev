# SHX-T35 (#3023): HeapFree の範囲外ポインタを M4 契約に揃えた判断と測定

結論: `bash tools/shimx/test.sh` の step 5 (M4 互換 MT/ST) が PASS に戻った。HeapFree の不正ポインタは M4 契約 (`ERROR_INVALID_FUNCTION`) に揃え、`blk_ok` に wasm linear memory の範囲検査を入れた。対象 issue: [#3023](https://github.com/signature-studio/signature-studio-dev/issues/3023)。REPORT.md は 250 行上限のため本付録に分けた (`docs/DOC_MAP.md` §1)。

## 1. 背景

- 失敗箇所: `tools/shim/test/test_main.c:204` `CHECK(GetLastError() == ERROR_INVALID_FUNCTION);` (HeapFree に範囲外ポインタ `0x1` を渡した直後)。`CHECK` は失敗時に `exit(1)` する。
- 原因: `tools/shimx/src/heap.c` の `HeapFree` は `!blk_ok(p)` のとき `ERROR_INVALID_PARAMETER` (87) を設定していた。M4 テストは `ERROR_INVALID_FUNCTION` (1) を期待する。テストは無改変で使う。
- 範囲検査の欠落: `blk_ok` は NULL とアライメントだけを見ていた。テストの範囲外値 `0x1`・`0x3`・`0xFFFFFFF0`・`0xFFFFFFFC` のうち、`0xFFFFFFF0` は 16 の倍数のため、範囲検査が無いと `raw_of` で linear memory の外を読む (§4 のネガティブコントロール 2 で trap を確認)。
- 再現コマンド: `bash tools/shimx/test.sh` (基点は origin/main `940c0d6a`。issue 記載の `0064cfbc` 系から進んでいるが、`tools/shimx` と `tools/shim` は `git diff --stat 0064cfbc 940c0d6a -- tools/shimx tools/shim` が 0 行で、対象コードは同一)。

## 2. 契約の判断

| 対象 | M4 テスト (`test_main.c`) | 変更前 shimx | 変更後 shimx | 判断 |
|---|---|---|---|---|
| `HeapFree` 不正ポインタ | `ERROR_INVALID_FUNCTION` (1) を検査 | `ERROR_INVALID_PARAMETER` (87) | `ERROR_INVALID_FUNCTION` (1) | M4 互換を優先して変更 |
| `HeapFree` 不正ポインタの戻り値 | `FALSE` を検査 | `FALSE` | `FALSE` | 変更なし |
| `HeapReAlloc` 不正ポインタ | 戻り値 `NULL` のみ検査 (errcode は未検査) | `ERROR_INVALID_PARAMETER` | 変更なし | テストが検査していない。M4 とは異なるが今回は触らない |
| `GlobalLock` / `GlobalUnlock` / `GlobalFree` 不正ハンドル | 戻り値のみ検査 (errcode は未検査) | `ERROR_INVALID_HANDLE` | 変更なし | 同上 |

- Win32 の実仕様: `HeapFree` の不正ポインタは `ERROR_INVALID_PARAMETER` と推定 (未検証。Win32 実機では確認していない)。今回は M4 互換を優先したため、Win32 実仕様との差は残る。
- 変えなかった理由: M4 テストが検査している errcode は `HeapFree` だけで、他の関数は戻り値だけを検査している。他関数を揃えると、テストに無い挙動まで変わる。
- LD 側の論点: native と wasm の HeapFree 応答表の統一は #2821 で扱う。

## 3. 変更内容

`tools/shimx/src/heap.c` の 2 箇所のみ (測定 commit `8fdaee48`)。

- A. `blk_ok` に範囲検査を追加。`tools/shim/src/heap.c` の `block_ok` (#2802 / LD-132) と同じ考え方。
  - `u < HEAP_HDR`: 16B ヘッダ `[user-16, user)` が負のアドレスにならないため。
  - `u > mem`: `user == mem` は `[mem-16, mem)` が範囲内なので許容する。
  - `mem` は 64bit で計算する (wasm32 の上限 4GiB は uint32 に収まらないため)。`__builtin_wasm_memory_size` は同ファイルの `mem_bytes()` が既に使っている。
- B. `HeapFree` の不正ポインタ分岐の errcode を `ERROR_INVALID_PARAMETER` → `ERROR_INVALID_FUNCTION` に変更。`ERROR_INVALID_FUNCTION` は `tools/shimx/src/shimx.h:125` で定義済みで、コンパイルも通った。

差分 (`git diff 940c0d6a 8fdaee48 -- tools/shimx/src/heap.c`):

```diff
 static int blk_ok(void* user) {
-    if (!user || ((uintptr_t)user & 15u)) return 0;
+    /* ヘッダ 16B が wasm linear memory の内に収まるかを先に確かめる (範囲外は読まない / LD-132 #2802) */
+    uint64_t u = (uintptr_t)user;
+    uint64_t mem = (uint64_t)__builtin_wasm_memory_size(0) * 65536u;
+    if (!user || ((uintptr_t)user & 15u) || u < HEAP_HDR || u > mem) return 0;
     return ((Hdr16*)raw_of(user))->magic == HEAP_MAGIC;
 }
@@ BOOL HeapFree(HEAP_HANDLE heap, DWORD flags, LPVOID p) {
     if (!p) return TRUE;
-    if (!blk_ok(p)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
+    if (!blk_ok(p)) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
```

## 4. 測定

環境: `nproc` = 4。load average は `uptime` の 1 分平均 (開始 → 終了)。所要秒は `date +%s` の差。測定ログは作業用の一時ディレクトリ (repo 外・commit 対象外) に置いた。

### 4.1 基点 (ステップ 1、変更前 `940c0d6a`)

- rc=1、所要 19 秒、load 0.11 → 1.08。
- 出力: step 4 (fail-fast) の全項目が `✓` まで進んだ後、`[shimx] 5/7 M4 互換 ...` の直後に
  - `[M4-test] FAIL <worktree>/tools/shimx/../shim/test/test_main.c:204: GetLastError() == ERROR_INVALID_FUNCTION`
  - `[shimx] FAIL: M4 互換 MT 失敗`
  - `[shimx] FAILED: 実行中断 (exit=1)`
- 再現した (issue の報告と一致)。

### 4.2 修正版 (測定 commit `8fdaee48` と同じ heap.c、n=3)

| run | rc | 所要 (秒) | load (開始 → 終了) | PASS 行 |
|---|---|---|---|---|
| 1 | 0 | 39 | 0.71 → 0.93 | `[shimx]     M4 テスト (MT/ST) PASS` / `[shimx] 7/7 完了: shimx 697 公開関数 × MT/ST × M4 互換 × fail-fast 全 PASS` |
| 2 | 0 | 38 | 0.86 → 0.93 | 同上 |
| 3 | 0 | 37 | 0.93 → 0.91 | 同上 |

- n=3 の所要: min 37 秒、max 39 秒。
- 測定 commit の HEAD で再実行 (手順 6): rc=0、所要 38 秒、load 0.28 → 0.60、同じ PASS 行。
- step 2 (emcc) は本測定の 6 run (基点 1・修正版 3・ネガティブコントロール 2 の 1・HEAD 1) すべてで成功し、`emcc` の出力欠落は再現しなかった。

### 4.3 ネガティブコントロール 2 (範囲検査 `u < HEAP_HDR || u > mem` だけを外す、1 回)

- rc=1、所要 17 秒、load 0.71 → 0.72。
- step 5 の MT で失敗。`m4_mt.err` の 4 行目に `RuntimeError: memory access out of bounds` (wasm trap)。
- 推定: trap の契機は `0xFFFFFFF0`。`0x1`・`0x3` は整列検査で返るため読まない。trap 時の正確なアドレスは出力されていないので未確認。
- ST 側は step 5 の MT で止まったため未実行。
- 後で範囲検査を元に戻した。戻した heap.c は測定 commit の内容と一致 (バックアップとの `cmp` が一致し、commit 後の `git diff` も 0 行)。

### 4.4 生成物 (test.sh step 6 の再生成)

- step 6 は `tools/shimx/BACKLOG.md`・`data/coverage.json`・`data/inventory.csv`・`inventory.md` を再生成する。修正版の実行のたびに同じ 4 件が変化した。
- commit しなかった。理由:
  - (a) gitignore 対象の入力 `tools/m11/work/`・`tools/m8/work/` が本環境に無い。`gen_inventory.py` は `work/ir_m11.json`・`work/ott/result.json` が無いと M11 closure と OTT 列を空にする。`coverage.json` の `m11_closure` は 3 集合から `{}` に、`ott_api_resolved` は 24 から 0 に、`inventory.md` の M11 外部参照は 557 件から 0 件に変わった。
  - (b) `shimx_*` 運用フック数 69 → 78 は、committed inventory と現ソースの既存のずれ。この変更で公開シンボルは増減せず、`tools/shimx/exports.txt` は不変。
- 生成物は worktree に未コミットのまま残し、PR には含めない。

### 4.5 測定 commit と差分

- 測定 commit: `8fdaee48f6cf8c47794a9379f2b855dbac8a2960` (`fix(shimx): HeapFree の範囲外ポインタを M4 契約に揃え blk_ok に範囲検査を入れる (SHX-T35, #3023)`)。
- `git diff 8fdaee48 HEAD -- tools/shimx/src` の出力: **0 行** (測定 commit 時点で HEAD = `8fdaee48`)。
- `git diff --stat 8fdaee48 HEAD -- tools/shimx`: 測定 commit 時点では 0 行。この後の差分は本 REPORT の追加 1 件 (`tools/shimx/REPORT_SHX-T35.md`・118 行) のみ。

## 5. 検証範囲 / 範囲外

- 検証した (test.sh): step 0〜5 (MT/ST・fail-fast・M4 互換)、step 6 の `sig_test.sh` (合成 fixture 8 項目が ALL PASS)、coverage gate (未実装 0、M4 53 API 継承 53/53)。
- 検証していない (SKIP / 入力なし):
  - step 6b の `sig_gate` (M11 IR `boot_final2.ll`・`boot_final3.ll` が無く、ループが空振り)
  - step 6c R6 (`boot_final3.ll` が無い)
  - step 7 OTT (`[verify_ott] SKIP: tools/m8/work/ott_m8.ll または tools/m6/work が無い`)
  - 本 PR は IR 経路 (M11・OTT) には触れていないが、そこで検出される回帰は本測定では見ていない。
- 範囲外: 他関数の errcode 統一 (`HeapReAlloc`・`GlobalLock`/`GlobalUnlock`/`GlobalFree`)、step 2 の emcc 別症状、Win32 実仕様の実機確認、ST 側のネガティブコントロール 2。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| step 2 の emcc が exit 0 のまま `build/shimx_test_mt.js` を出さない事象 (元 issue で 4 回中 1 回。本測定の 6 run では再現せず、原因未特定) | test.sh が偽の失敗・成功を出し得る | #2916 へのコメント |
| 他関数のエラーコード差: `HeapReAlloc` (ERROR_INVALID_PARAMETER)、`GlobalLock`/`GlobalUnlock`/`GlobalFree` (ERROR_INVALID_HANDLE) は M4 テストが未検査 | native と wasm で不正入力時の errcode が揃わない | #2821 |
| `HeapFree` の Win32 実仕様 errcode (推定 ERROR_INVALID_PARAMETER・未検証) | M4 優先の判断の根拠が推定のみ | #2821 |
| test.sh step 6 が M11/M8 入力欠落の環境で inventory・BACKLOG・coverage を空の値で再生成する。`shimx_*` フック数の既存ずれ (69 → 78) も含む | 生成物を commit すると M11/OTT 列が消える。commit 判断を誤りやすい | #2916 へのコメント |

関連: #2916 (親)・#2802 (`block_ok` の範囲検査の元)・#2821 (native/wasm の応答表統一)。
