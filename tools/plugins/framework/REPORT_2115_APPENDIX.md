# #2115 REPORT 付録 — §10 (TLS index 未設定の確認と stand-in 版の実験)

> **測定値の正本**: 本書 (§10.3)。結論と受入の判定は `REPORT_2115.md` が正本。本書は同 REPORT の §10 を 250 行上限のため分割移動したもの (本文は改訂済み・改訂前の節は Git 履歴にある)。

## 10. TLS index 未設定の確認と stand-in 版の実験 (未採用・測定 commit 91308efd)

前提: §8 の `return 0` 版も注釈削除版も Phase B は同じ OOB。TLS 経路 (`gs:[0x58][[0x6d6e70]]`) の未設定を確認した。既定の注釈は `return 0` のまま (本節の stand-in 版は未採用)。

### 10.1 確認事実

- `block18983_PE.bin` に TLS directory は無く、TLS index 変数 `0x6d6e70` の初期値は `0xFFFFFFFF` (`.data`)。
- `[0x7162d8]` は `.bss` で 0 のため、`function_4181e0` は TLS 経路を通る。`idx = -1` は `zext` 後に線形メモリ外のアドレスになる (canon3 `dec_label_pc_7d8a61`)。
- `[0x6d6e70]` を設定するのは `function_418120` (`TlsAlloc` → store) のみ。canon3 と hs_flat3 に直接 call は 0 件、hs_e2e の dispatch ログにも `0x418120` は 0 件 (注釈版・stand-in 版とも)。
- **訂正 (§11.1)**: 「headless chain で `0x418120` は呼ばれない」は誤り。`0x418120` は E8 では呼ばれず、`_InitLib` の hooks 表からの間接 call で実行される。dispatch ログは `fw_call_cur` 経由を記録しないため、0 件は不在の根拠にならない。
- 呼出元は戻り値を `[BLK+0x80]` から読み `+568` を deref する (§8 の注釈記述・hs_dbg 実測)。

### 10.2 未採用の実験: stand-in 版 (`fw_hostfix.py` 0x4181e0)

- 未採用。コードは commit 91308efd に残す。HEAD の `fw_hostfix.py` は 3b581236 と同一 (注釈 `return 0`)。戻した commit は 8858cc0f。
- `idx == -1` なら `TlsAlloc()` で確保し `[0x6d6e70]` に store する。
- TLS スロットが 0 なら 4096 byte の 0 埋めブロック `@fw_tls_block` を割り当てて書く。戻り値は SSA と `[BLK+0x80]` の両方に store する。
- フラグ `[0x7162d8]` != 0 の経路 (418030・4180d0・`[0x7162d0]`) は未モデル (初期値 0 の前提)。

### 10.3 実測 (fix round 3・2026-10-14・各 n=1)

- 素材: `work-fw-stage1` を `tools/plugins/work/fw/` に展開 (12 ファイル)。[EMSDK]・[RETDEC] (`docs/REFERENCES.md` の ID) は runner に存在。fl-win64 は展開していない (`fw_stage2.sh`・`hs_e2e.sh` は `$FL_WIN64_DIR` を読まない)。
- 実行: 逐次 (並列数 1・nproc 4)。`fw_stage2.sh` は増分 (`--fresh` なし。stage-1 の RetDec は再実行しない)。`hs_e2e.sh` は両回 `--fresh`。
- 対照 = 注釈 `return 0` 版 (コミット 3b581236 の `fw_hostfix.py`。現 HEAD と同一コード)。stand-in 版 (未採用) = 91308efd の `fw_hostfix.py` (ca85489e の同ファイルと同一)。

| 手順 | 結果 | 所要 (real) | load average (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (増分・canon3 生成・HEAD ca85489e) | rc 0・`SMOKE PASS` (dispatch=38 units_done=0 ff=0) | 426.1 秒 | 0.13 / 0.24 / 0.11 (13:46:53) → 2.11 / 2.17 / 1.06 (13:53:59) |
| `hs_e2e.sh --fresh` 対照 (3b581236) | Phase A `dispatch=38 ff=0` / Phase B OOB / `rec=7` / `E2E FAIL: 1 項目` | 157.4 秒 | 1.87 / 2.12 / 1.05 (13:54:11) → 1.13 / 1.69 / 1.05 (13:56:48) |
| `hs_e2e.sh --fresh` stand-in 版 (91308efd・未採用) | Phase A `dispatch=38 ff=0` / Phase B OOB / `rec=7` / `E2E FAIL: 1 項目` | 159.3 秒 | 0.95 / 1.63 / 1.04 (13:56:57) → 1.09 / 1.42 / 1.05 (13:59:36) |

- `hs_flat3.ll` (各 run の終了時点): 対照は mtime 13:56:30・sha256 `8a5f2608ea46c2d35cf569a9c4664876b5e8cb940586e5afc0d72fec1487be22`、stand-in 版は mtime 13:59:18・sha256 `95e4ddd11521a24b7d0a6b4e66e938b3515538035e606f339262df359dd3ee80`。両 sha256 が異なるため、各 run が自分の `fw_hostfix.py` で作り直されたことを確認した。
- `hs_hostfix.json` の `0x4181e0`: 両回とも `old_lines: 79`・`injected: false` (既存 define を置換した記録。新規注入ではない)。
- 失敗位置 (両回とも同じ順序): `0x40d807` の soft-miss (target 0) → OOB。`0x4e5fa6` の soft-miss target は、対照が `0x0`、stand-in 版が `0x1712`。この差は両回で再現した。変動は未評価のため、効果とは断定しない。
- 中間版 (TLS 割当のみ・`[BLK+0x80]` store なし): dev 観測・未記録 (rc・所要・load・値は未記録、n=1)。戻り値の受け渡し先を `[BLK+0x80]` に揃えるため store を追加した。
- §8 との食い違い: 本節の 2 回はいずれも `rec=7` で、§8 の結果 (件数は REPORT_2115.md §8 が正本) は再現しなかった。原因は未確定。

### 10.4 再測定の扱い (fix round 3)

- 旧版の対照 (plain 実行・load 未記録) の数値は使わない。対照と stand-in 版を `--fresh` で測り直し、load average と `hs_flat3.ll` の mtime・sha256 を §10.3 に書いた。
- 各条件は n=1 のみ。WORKFLOW §5 の min–max (n≥3) は未実施。所要 157.4 秒・159.3 秒は n=1 の値として扱う。
- `hostshim/hs_e2e.sh` の増分判定 (49 行目) は本測定に影響しない (両回 `--fresh`)。plain 実行は影響を受けるため、REPORT_2115.md §9 に未解決として残す。

### 10.5 結論

- 受入 2 は未達。既定の注釈は `return 0` のまま。0 埋めブロックの stand-in は未採用で、正しい戻り値 (TLS ブロックの中身・`+568` の意味) は未確定。OOB は解消していない。
- 受入 3 は n=1 の実測と対照で部分達成。変動 (n≥3) と §8 との食い違いは未評価。
- 既定の値は対照 (3b581236・`--fresh`・§10.3) の実測をそのまま引用する。HEAD は対照と同一コードのため、追加の再測定は行わない (WORKFLOW §6)。
- 未解決の一覧は `REPORT_2115.md` §9 に置く (本節では重複させない)。

## 11. TLS 経路の確定と注入実験 (fix round 5・測定 commit 4c00ec24)

### 11.1 `0x418120` の実行経路 (訂正)

- `_InitLib` (native 0x40db20) は `reason ∈ {1,2}` で `call qword ptr [rbx + rsi*8]` (0x40dbfe・`rbx` = hooks 表・`rsi` = reason) を行う。`reason==3` も同形 (0x40dc2d)。
- hooks 表 `0x6d6ef8`: `[+0]=0x4181b0`・`[+8]=0x418120`・`[+0x10]=0x4180d0`・`[+0x18]=0x418160` (`block18983` の .data)。reason=1 の `[+8]` が `0x418120` (TLS 初期化)。E8 走査 (68 件) に現れないのは、間接 call のため。
- 実行の確認 (Phase A・`fw_boot.c` の診断行): `[fw][ov] hooks[1]=0x418120` → `TlsAlloc -> 1` → `hooks[1] done: tls_idx=1`。TLS idx は設定されている。出典: 測定 commit 4c00ec24 の §11.4 の実行 (`fw_stage2.sh` と `hs_e2e.sh --fresh`・15:09–15:11) の stderr。log ファイルは保存していない (本 run の環境に無い)。再現は同じ実行で `grep '\[fw\]\[ov\]\|\[fw\]\[tls\]'` する。

### 11.2 native の意味 (逆アセンブル・block18983)

| 関数 | 意味 |
|---|---|
| `0x418120` (hooks[1]) | `[0x6d6e70] = TlsAlloc()`。`0x4180d0()`。`[0x7162d0] = TlsGetValue([0x6d6e70])` |
| `0x4180d0` | `ebx = 0x4180c0()` (= 0x288 固定・`lea rax,[0x288]; ret`)。`blk = LocalAlloc(0x40, ebx)`。`blk != 0` なら `TlsSetValue(idx, blk)` |
| `0x4181e0` (TLS getter・引数なし) | 分岐は `[0x7162d8]` (1 バイトの flag) で決まる。idx は `[0x6d6e70]`。`[0x7162d8] == 0` なら `gs:[0x58][idx*8]` を返す (idx = -1 なら範囲外)。`[0x7162d8] != 0` なら `TlsGetValue(idx)` を呼ぶ: 0 でなければ返す。0 なら `0x4180d0` を呼んでから `TlsGetValue(idx)` を再度呼び、0 でなければ返す。2 回目の `TlsGetValue` が 0 なら `[0x7162d0]` を返す |
| `0x4189c0` (_StartLib) | `reason==1` で `[0x716290]=1`・`[0x7162d8]=1` 等 (fw_boot.c の既存実装と一致) |

- 上の分岐は `block18983_PE.bin` の逆アセンブル (capstone) で確認した。`0x418030`・`0x418010`・`0x418040` は IAT 名で `TlsGetValue`・`TlsAlloc`・`TlsSetValue` に対応する。`0x4180a0` は `LocalAlloc(0x40, ecx)` (`0x417ff0` = `LocalAlloc`)。idx の `[0x6d6e70]` は、分岐の 3 箇所の rip 相対参照で確認した。
- したがって getter の正しい戻り値は、per-thread block (0x288 byte・`LocalAlloc` のゼロ初期化) のポインタ。caller はその `+568` を deref する (§8・§10)。
- `return 0` 注釈は、この block の代わりに 0 を返す。

### 11.3 lift の欠陥 (実測)

- `function_4180c0` の lift は `ret i64 648` で正しい。
- `function_4180a0` の lift は引数 `ecx` (= 0x288) を `ptrtoint @683` に fold する。`LocalAlloc(0x40, 0x10000880)` になり、wasm の定数アドレスが size に入る。
- `function_4180d0` の lift では、`TlsSetValue(1, 0x1)` の値が LocalAlloc の戻り (`0x118b60a8`) ではなく `1` になる。この戻り値の受け渡しも lift 側の欠陥と判断した (原因の IR 行は未特定)。
- その結果 `[0x7162d0] = 1`。TLS 値の不正は、TLS の意味論ではなく lift の fold 由来。
- 起票先: `#2510` (生成側で定数の `ptrtoint` が値に fold される欠陥。同じ類型の別インスタンスとして `#2510` にコメントで追記する)。`docs/DEFECTS.md` D21 と同型の可能性はあるが未確認。`#1890`・`#2008` は close 済みのため使わない。

### 11.4 実測

#### 11.4.1 測定 commit 058c2049 (本 fix・実行は HEAD fa128b1b)

- 測定 commit は `058c2049` (実行コードの最終 commit)。実行は `fa128b1b` のクリーンな worktree (`ws-2115`) で行った。`git diff 058c2049 fa128b1b -- tools/plugins/framework ':!*.md'` は 0 行。
- 素材: `work-fw-stage1` を repo ルートで展開 (`tools/plugins/work/fw/` の 12 ファイル)。`toolchain-emsdk` は [EMSDK] (emcc 6.0.12) を使用。`fl-win64` は展開していない (`fw_stage2.sh`・`hs_e2e.sh` は `FL_WIN64_DIR` を読まない)。`toolchain-retdec` は呼ばれない (`r2`・`r3` の restored.ll は素材に含まれ、`--fresh` を使わない)。
- 順序: `fw_stage2.sh` (stage-1 の 12 ファイルだけの状態から全段) → `hostshim/hs_e2e.sh --fresh`。逐次・並列数 1 (nproc 4)。

| 手順 | 結果 | 所要 (real) | load average (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (中間物なしの全段) | rc 0・`SMOKE PASS` (dispatch=38 units_done=0 va=1 heap=1 ff=0)・`fw_route.wasm` 15,063,364 B | 278 秒 | 0.19 / 0.37 / 0.18 (16:05:41) → 2.63 / 1.66 / 0.75 (16:10:19) |
| `hs_e2e.sh --fresh` | rc 1・Phase A `dispatch=38 ff=0`・Phase B `memory access out of bounds`・`status=0xffffffff plug=0x0 rec=7`・`E2E FAIL: 1 項目`・`hs_route.wasm` 15,038,486 B | 91 秒 | 2.12 / 1.60 / 0.74 (16:10:34) → 1.25 / 1.44 / 0.77 (16:12:05) |

- n=1 (min–max は未取得)。Phase A の dispatch は 38 で、Phase B は §11.4.2 と同じ失敗形 (OOB・rec=7・1 項目)。Phase A が外れなかったため、切り分けは不要。
- TLS trace (Phase A の stderr) は §11.1 と一致: `hooks[1]=0x418120` → `TlsAlloc -> 1` → `LocalAlloc(0x40, 0x10000880) -> 0x118b60b8` → `TlsSetValue(1, 0x1)` → `TlsGetValue(1) -> 0x1` → `hooks[1] done: tls_idx=1`。
- 終端の `Aborted(Runtime error: The application has corrupted its heap memory area (address zero)!)` は smoke.log の 47 行目に出る (基準 4c00ec24 も同じ位置に同じ行)。SMOKE PASS の判定は変わらない。`REPORT_2115.md` §9 に未解決として記録。

**基準 4c00ec24 との比較** (同じ worktree・同じ手順。基準の `fw_rt.c` を一時的に入れ、`fw_stage2.sh` は `fw_route.cjs`・`fw_route.wasm` を削除して emcc のみ再ビルド (増分)、`hs_e2e.sh --fresh` は同じ。実行後に HEAD 版へ戻した):

| 手順 | 結果 | 所要 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (増分) | rc 0・SMOKE PASS (dispatch=38 ff=0)・`fw_route.wasm` 15,063,331 B | 20 秒 | 0.89 / 1.34 / 0.75 (16:12:30) → 0.93 / 1.31 / 0.76 (16:12:50) |
| `hs_e2e.sh --fresh` | rc 1・Phase A `dispatch=38 ff=0`・Phase B OOB・`rec=7`・1 項目・`hs_route.wasm` 15,038,453 B | 90 秒 | 0.85 / 1.29 / 0.75 (16:12:56) → 0.97 / 1.21 / 0.78 (16:14:26) |

- 差分は表示行の heap アドレスだけ: `[fw][ov] _StartLib ctx` `0x118b6098` → `0x118b60a8` と `[fw][tls] LocalAlloc(0x40, 0x10000880) -> ` `0x118b60a8` → `0x118b60b8` は smoke.log (48 行) と hs_e2e のログ (126 行) の両方に出る。hs_e2e のログには、さらに hostshim の soft-miss `target 0x118b6388` → `0x118b6398` (site `0x5e018a`) の 1 行が加わる。`0x118b6xxx` を `HEAP` に置換すると両ログは一致する。Phase A/B・`rec` の値・失敗位置は同じ。
- wasm は fw_route・hs_route とも +33 B (同じ worktree パス内の比較)。wasm の絶対値は worktree パスの文字列を含む (`ws-2115` が wasm 内に 4 回出現) ため、別パスで作った値とは比べない。
- 推定 (未検証): heap アドレスのずれは、`fw_rt.c` に static 変数 (`g_local_trace`) を 1 つ足して .bss が伸び、heap の開始位置が 16 B 動いたため。戻り値・分岐に関わるログ行は変わらない。

#### 11.4.2 測定 commit 4c00ec24 (旧測定・表示行を入れた時点)

| 手順 | 結果 | 所要 (real) | load (開始 → 終了) |
|---|---|---|---|
| `fw_stage2.sh` (増分・emcc 再ビルド) | rc 0・`SMOKE PASS` (dispatch=38 units_done=0 ff=0) | 18.5 秒 | 0.41 / 0.64 / 0.63 (15:09:24) → 0.91 / 0.76 / 0.67 (15:11:15) |
| `hs_e2e.sh --fresh` | Phase A `dispatch=38 ff=0` / Phase B `memory access out of bounds` / `rec=7` / `E2E FAIL: 1 項目` | 92.6 秒 | (上と同じ区間) |

- 対照 (§10.3 の 3b581236) と同じ失敗形 (Phase B OOB・rec=7・1 項目)。1 回測定 (n=1)。
- 表示行 (`[fw][ov] hooks[...]`・`[fw][tls] ...`) の追加は dispatch 数を変えない (smoke の dispatch=38 は維持)。
- 測定 commit `4c00ec24` の framework コードは、表示行を入れた `86b6bdc2` の親 `9f403c97` に対して表示行のみ (`git diff 9f403c97 4c00ec24 -- tools/plugins/framework ':!*.md'`: `fw_boot.c` +3 と `fw_rt.c` の trace 行)。基点 `9f403c97` から `origin/main` (fix round 5 の取得時点 `064af0d8`) までに framework の 5 ファイルが変わった: `fw_smoke_check.py` (+42/-10)・`hostshim/hs_irfix.py` (+64)・`hostshim/hs_plug.c` (+17・`hs_fw_init_tls`・#2571)・`fw_269_verify.sh`・`fw_pack_stage1.sh` (各 1 行のコメント)。本 PR はこれを取り込んでいない。merge 後の挙動は未測定 (REPORT_2115.md §9・起票先 #2115)。
- 測定後の実行コード差分 (fix round 6・commit `058c2049`・`fw_rt.c` の表示カウンタを分離): `git diff 4c00ec24 058c2049 -- tools/plugins/framework ':!*.md'` の出力は次の 23 行。LocalAlloc の trace は `g_local_trace`、TLS 関数の trace は `g_tls_trace` で数える。戻り値と分岐は変わらない (表示のみ)。

```diff
diff --git a/tools/plugins/framework/fw_rt.c b/tools/plugins/framework/fw_rt.c
index 1ae5159c..641239e2 100644
--- a/tools/plugins/framework/fw_rt.c
+++ b/tools/plugins/framework/fw_rt.c
@@ -103,8 +103,8 @@ long long fw_call_cur(uint32_t va) {
 #include "fw_rt.h"
 
 /* ---- Local 系, Global 系メモリ API (RetDec が IAT thunk を名前解決して直接 call する) ---- */
-static int g_tls_trace = 0;
-void *LocalAlloc(unsigned flags, unsigned bytes) { void *r = HeapAlloc(0, flags, bytes); if (g_tls_trace++ < 16) fprintf(stderr, "[fw][tls] LocalAlloc(0x%x, 0x%x) -> 0x%llx\n", flags, bytes, (unsigned long long)(uintptr_t)r); return r; }
+static int g_local_trace = 0;
+void *LocalAlloc(unsigned flags, unsigned bytes) { void *r = HeapAlloc(0, flags, bytes); if (g_local_trace++ < 16) fprintf(stderr, "[fw][tls] LocalAlloc(0x%x, 0x%x) -> 0x%llx\n", flags, bytes, (unsigned long long)(uintptr_t)r); return r; }
 void *LocalReAlloc(void *p, unsigned bytes, unsigned flags) { (void)flags; return HeapReAlloc(0, 0, p, bytes); }
 void *LocalFree(void *p) { HeapFree(0, 0, p); return p; }
 void *LocalLock(void *p) { return p; }
@@ -184,6 +184,7 @@ __attribute__((used)) void __frontend_reg_store_fpr(uint32_t idx, double v) { fw
 /* ---- TLS (gs:[0x58] = ThreadLocalStoragePointer) ---- */
 static uint64_t g_tls_slots[128];
 static uint32_t g_tls_next = 1;
+static int g_tls_trace = 0;
 int TlsAlloc(void) { int r = (int)(g_tls_next++); if (g_tls_trace++ < 16) fprintf(stderr, "[fw][tls] TlsAlloc -> %d\n", r); return r; }
 int TlsFree(int i) { (void)i; return 1; }
 void *TlsGetValue(int i) { void *r = (i >= 0 && i < 128) ? (void *)(uintptr_t)g_tls_slots[i] : 0; if (g_tls_trace++ < 16) fprintf(stderr, "[fw][tls] TlsGetValue(%d) -> 0x%llx\n", i, (unsigned long long)(uintptr_t)r); return r; }
```

- この差分 (`058c2049`) は実行コードのため WORKFLOW §6 の再測定の対象。**§11.4.1 で再測定済み** (測定 commit 058c2049・Phase A `dispatch=38 ff=0`・Phase B は §11.4.2 と同じ失敗形)。構文は `clang -fsyntax-only` (`emscripten.h` を空スタブ) で修正前後ともエラー 0 (fix round 6 時点の確認)。
- 再現手順: §11.4.1 の順序 (`bash tools/plugins/framework/fw_stage2.sh` → `bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh`)。Phase A が `dispatch=38 ff=0` から外れた場合は、表示カウンタ分離 (`058c2049`) との切り分けのため、同じ手順で `4c00ec24` の `fw_rt.c` を対照に測る (§11.4.1 の比較の方法)。

### 11.5 注入実験 (未採用)

| 条件 | commit | Phase A | Phase B |
|---|---|---|---|
| E1: `0x4180d0` を native の意味に注釈 (`0x4181e0` の `return 0` は残す) | 未コミット (未採用・本 PR に含めない) | — | 数値は報告しない (未コミットの WIP のため WORKFLOW §6 により判定に使わない)。採用する場合はコミットして HEAD 上で再測定する |
| E3: Phase B の `hs_e2e_run` で `fw_hs_install()` の直後に `fw_call_cur(0x418120)` を 1 回呼ぶ + `0x4180d0` を native の意味に置換 + `0x4181e0` の注釈 (`return 0`) を削除 | `f850508a` (revert `4c00ec24` で戻し)。所要・load は未記録 (ログも時刻も保存していない。WORKFLOW §5 の未充足。未採用のため再測定しない) | `dispatch=38 ff=0` | Phase B は OOB のまま (main の #2571 と同じ失敗形。詳細は `REPORT_2571.md` §3)。E3 固有の観測: TLS は `TlsAlloc → 1`・`TlsSetValue(1, 0x118b6628)`・`TlsGetValue(1) → 0x118b6628` (正しい block)。失敗位置は `0x40d807` の soft-miss から `0x4e5fa6` の文字列 target へ変わる。main (#2571) との違い: 注入位置は同じ (`fw_hs_install()` の直後)。E3 のコードは `[0x7162d8]` を明示的に立てず、`0x4181e0` の注釈を外して block を返させる。main は `[0x7162d8]=1` を立ててから `0x418120` を呼び、注釈 (常に 0 を返す) を残す |

### 11.6 結論

- 受入 2 は未達。戻り値の内容は次の形で確定した: getter は、`[0x7162d8]` が 1 なら `TlsGetValue(idx)`、0 なら `g_tls_slots[idx]` を返し、どちらも `0x4180d0` が確保した 0x288 byte の per-thread block を指す。`return 0` 注釈は、この block の代わりに 0 を返す。
- Phase B は、基点 `9f403c97` では framework 初期化を通らない (`hs_plug.c` `hs_e2e_run` → `CreatePlugInstance`)。TLS 値を正しくしても OOB は消えず、block の内容 (`+568`) の native 初期化元が次の壁。main では #2571 (PR #2595) が TLS 初期化 (`hs_fw_init_tls`) を入れたが、`REPORT_2571.md` §3 では初期化ありでも OOB が残る。残る OOB の起票先は #2115 (継続)。
- 注釈の変更 (E3) は Phase B の失敗形を変えるだけで、E2E は PASS にならない (E3 の実測は §11.5)。E1 は未コミットのため判定に使わない。採用はしない。
