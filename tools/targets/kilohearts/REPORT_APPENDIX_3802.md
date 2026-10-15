# REPORT 付録 (#3802 KH-66): Delay の未定義 identifier・未関数化 callee・スタブ衝突の規則

#3096 (KH-44) の付録 `REPORT_APPENDIX_3096.md` §10-7t の続き。前節の正本は同 §10-7t ②の census。

#### 10-7u. #3802 (KH-66) run: 未定義 identifier 15・未関数化 callee 5・衝突 2 を解消 (部分・emcc 556 → 534 件)
- 結論: Delay の emcc 残件 556 → **534** 件。下の 3 種を解消した: 未定義 identifier のうち `DAT_`・`uRam` の 15 件 (規則は下の EXT_CTYPE)、未関数化 callee 5 件 (fail-fast stub)、`FUN_18004cf20` の conflicting types 2 件 (本体がある VA の stub を出さない)。Gain/Haas/Gate の生成 C は origin/main と byte 一致、wasm の sha256 も一致、1000/1000 bit-exact。
- 残件 (子 issue): `LAB_180fd2aab`・`PTR__guard_dispatch_icall_1813a1d38` の 2 件 → #3835 [KH-70]。double のビット再解釈 `(ulonglong)dVarN` 98 行 (silent miscompile の疑い) → #3836 [KH-71]。
- 測定 commit (e2e を実測した converter): `6323671e7` (`tools/targets/kilohearts/ghidra_route/ghidra_to_c.py`)。比較元は origin/main `40d3a788d`。
  - その後のコード変更は 1 commit (レビュー差し戻しの対応: THUNK 表の見出し分割・同一 VA の `gd_` 重複定義の防止)。`git diff 6323671e7 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は ⑥b。e2e は HEAD で再測定していない (⑥b・⑦)。

**① 環境 (repo 外。`work/` は使わない)**
- 素材 `plugins-kilohearts` (`tar --zstd -xf` で `Kilohearts Offline Installer.zip` 3,833,108,300 B のみ取り出し → `payload.dat` 3,817,512,248 B → `windows.zip/1ccb1df8c8f10745` 55,114,108 B → `HeartCore.core_64` 76,642,304 B)。
- [GHIDRA] 12.1.4: 本 run で GitHub release から取得 (zip 569,649,598 B・sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。`GHIDRA_HOME` (repo 外) に展開 (本 run で作成)。[JDK21] `temurin-21-jdk-amd64`、[EMSDK] emcc 6.0.12。`toolchain-emsdk` は [EMSDK] を使用。`fl-win64` は未使用。
- decompile: Delay lift 141 件 → **141/141 OK** (`analyzeHeadless` wall 21.3 s、n=1)。gain・haas・gate の 10 関数 → **10/10 OK**。

**② Delay の census (origin/main `40d3a788d` → 測定 commit `6323671e7`・`emcc -c -ferror-limit=0`)**

| 分類 (census 行) | 前 (origin/main) | 後 (`6323671e7`) | 起票先 |
|---|---|---|---|
| 未関数化 callee | 5 | **0** | 本 PR で解消 (stub) |
| レーン型 | 191 | 191 | #3094 [KH-42] |
| 引数数不一致 | 108 | 108 | #3800 [KH-64] |
| SIMD・AVX・swi 疑似関数 | 46 | 46 | #3095 [KH-43] |
| code 型の間接呼出し | 0 | 0 | 解消済み (#3096) |
| 未定義 identifier | 17 | **2** | `LAB_`・`PTR__` → #3835 [KH-70]。他 15 件は本 PR |
| 演算・代入・ポインタの型不一致 | 187 | 187 | #3801 [KH-65] |
| その他 (conflicting types) | 2 | **0** | 本 PR で解消 |
| **合計** | **556** | **534** | |

- 差分の確認 (`error:` 行をメッセージ種別で数えた前後の差): `call to undeclared function` 51 → 46 (−5)・`conflicting types` 2 → 0 (−2)・`use of undeclared identifier` 17 → 2 (−15)。他の種別は増減 0。合計 −22。
- C の差分 (`diff`): 追加 24 行 (`gd_` 配列・`DAT_`/`uRam` の macro・stub)、削除 2 行 (衝突する `FUN_18004cf20` の STUB 宣言と定義)。行数 7,248 → 7,270。

**③ 規則 1: 下線なしの名前 (`DAT_<va>`・`uRam<16 桁>`) (`EXT_CTYPE`)**
- 規則: 同じ PE 実データを `gd_<va>[16]` (static 配列) で持ち、`#define <名前> (*(<型>*)gd_<va>)` で定義する。`_DAT_` (下線付き) の既存規則と同じ。
- Ghidra は型を出さないため、型は使用箇所から 1 件ずつ決めて `EXT_CTYPE` に根拠付きで書いた。表に無い名前が出たら停止する (推定の既定値は使わない)。

| 名前 | 型 | 根拠 (delay.c の使用) |
|---|---|---|
| `DAT_182280d00`・`DAT_182280d70` | `ulonglong` | `(ulonglong)DAT_x` の bit マスク (`FUN_180fc4590`) |
| `DAT_184161fb0` | `unsigned char` | `!= '\0'` と `= '\x01'` (once フラグ・`FUN_180fd08d0`) |
| `DAT_1829899e0` | `unsigned char` | `== '\0'` (`FUN_180fd622c`) |
| `DAT_182989850` | `unsigned char` | `(DAT_x & 2) != 0` の読み出しのみ。byte 読みでも bit 1 は同じ (`FUN_180fd2a60`) |
| `DAT_182989680` | `undefined` | `*(undefined **)… != &DAT_x` のアドレス比較 (`FUN_180fe3310`) |
| `DAT_184162358` | `undefined` | `puStack_28 = &DAT_x` (`puStack_28` は `undefined *`・`FUN_180fd2d38`) |
| `uRam1829899cc`・`d0`・`d4` | `uint` | `undefined4` 変数 (`uStack_2c`・`uStack_28`・`uStack_24`) への読み出し (`FUN_180fb5dd0`) |
| `uRam18436cc00` | `ulonglong` | `FUN_181327120` の書込み (`= 2`)。GS 失敗報告経路 (`swi(0x29)` で fail-fast)。同関数の `*(longlong*)(puVar3 + 0x20)` と同じ 8 byte の ExceptionInformation 相当。この値を読む箇所は closure 内に無い |

- 注意 (残るリスク): `uRam18436cc00` の書込みは gd の複製に入り、`_DAT_18436cbf8` の実データには反映されない。closure 内に読み出しは無いが、読む側がある場合は直す必要がある。読み出しのみの名前 (`uRam1829899cc` 等) は実データの複製で足りる。

**④ 規則 2: 未関数化 callee 5 件 (fail-fast stub)**
- 閉包: 呼出しは 5 件、VA は 4 種 (`0x180fbdef4` ×2・`0x180fbdd78`・`0x180fe5c74`・`0x180fe2508`)。decompile は追加しない。`also` に入れると閉包が広がり emcc 件数が増える (§10-7s の 7 → 54 と同じ傾向)。
- 規則: `longlong <名前>() { abort(); return 0; }`。`()` の非プロトタイプなので呼出しの arity を問わない。到達時に abort し、突合 (1000 trial) で検出する。`func_0x000<va>` 形は `THUNK`、`FUN_<va>` 形は `STUB` に入れる。
- Stereo・Resonator の生成 C は未測定 (起票先は ⑦)。STUB・THUNK は、その名前が出る C にだけ出る。Resonator は `also` に `0x180fbdef4` を含むため、その THUNK は出ない。EXT_CTYPE に無い `DAT_`/`uRam` 名が出ると生成は停止する (従来は emcc の undeclared identifier で止まっていた箇所)。
- 既知の名前と既存 shim: `0x180fbdd78` = `dint`・`0x180fbdef4` = `fint` (`snapins/snapins.json` に名前がある。既存 shim 実装の直接差分は `snapins/REPORT.md` の dint/fint 行が正本)。`0x180fe2508` は CRT atexit/terminate ランナで、`snapins/REPORT.md` は fail-fast stub のまま残す記録。Delay では既定案の現状の stub (abort) のまま。既存 shim を使うかは PM の判断。

**⑤ 規則 3: スタブと本体の衝突 (`FUN_18004cf20`・conflicting types 2)**
- 原因: Delay は `FUN_18004cf20` を `also` で decompile している (本体あり) のに、`STUB` の宣言 (`void* a, void* b, void* c`) も出していた。
- 規則: STUB は本体を decompile していない VA にだけ出す (`va not in vas`)。THUNK も同じ条件。Gain/Haas/Gate は `FUN_18004cf20` の本体を持たないため、stub がそのまま出る。

**⑥ 回帰 (Gain / Haas / Gate・測定 commit `6323671e7` の converter)**
- 生成 C: origin/main の converter の出力と **byte 一致** (`cmp`・3 本とも)。
- wasm: sha256 先頭 16 桁 Gain `57d8b9a34c5bcc28`・Haas `af100316c19d5b34`・Gate `95bcc2bd7d1b802f` (origin/main と同一)。サイズ 15,161 B・16,878 B・17,367 B。
- 突合 (`native_ref` 1000 trial・seed 7・`compare.mjs`): Gain **1000/1000** (calls 4999/4999)・Haas **1000/1000** (calls 5500/5500)・Gate **1000/1000** (calls 4999/4999)。
- 未実施: Delay の突合・1000 trial (emcc が通らないため。#3073 [KH-41])。

**⑥b 最後のコード変更 (commit `9588011ed`) の確認**
- `git diff 6323671e7 HEAD -- tools/targets/kilohearts/ghidra_route` の出力 (33 行・`ghidra_to_c.py` のみ):

```diff
diff --git a/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py b/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py
index f6d277c82..a173889f6 100644
--- a/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py
+++ b/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py
@@ -40,12 +40,13 @@ STUB = {  # 未 decompile の callee → C 実装 (RetDec stage-0 + kh_lower ル
     0x180fe5c74: 'longlong FUN_180fe5c74() { abort(); return 0; }',
     0x180fe2508: 'longlong FUN_180fe2508() { abort(); return 0; }',
 }
-# IAT thunk (jmp [rip+disp] → KERNEL32 の import) → fail-fast stub。Ghidra は thunk の引数を落として `func_0x000<va>(...)` と呼ぶ。
-# 引数無しの定義 (`()`) は呼出の arity を問わない。Win API の意味は実装しない (到達時に abort し、突合で検出する)。
+# THUNK: Ghidra が `func_0x000<va>(...)` と呼ぶ callee → fail-fast stub。引数無しの定義 (`()`) は呼出の arity を問わない。
+# 到達時に abort し、突合で検出する。2 種類ある: (a) IAT thunk (jmp [rip+disp] → KERNEL32 の import)・(b) 未関数化 callee (本体を decompile していない VA)。
 THUNK = {
+    # (a) IAT thunk。Win API の意味は実装しない
     0x180fd81e4: 'longlong func_0x000180fd81e4() { abort(); return 0; } /* KERNEL32!FlsGetValue */',
     0x180fd81ec: 'longlong func_0x000180fd81ec() { abort(); return 0; } /* KERNEL32!FlsSetValue */',
-    # 未関数化 callee (delay 閉包の外)。decompile せず fail-fast stub にする。`func_0x000<va>` 形の呼出が残る。
+    # (b) 未関数化 callee (delay 閉包の外)。decompile せず fail-fast stub にする
     0x180fbdef4: 'longlong func_0x000180fbdef4() { abort(); return 0; } /* 未関数化 callee (stub) */',
     0x180fbdd78: 'longlong func_0x000180fbdd78() { abort(); return 0; } /* 未関数化 callee (stub) */',
 }
@@ -197,8 +198,10 @@ def main():
         if n not in EXT_CTYPE:
             raise SystemExit('未定義 identifier の型が未確定 (停止): ' + n)
         ext[n] = int(n[4:], 16)
+    gd_done = set(gtypes)  # 同じ VA を指す名前 (例 DAT_x と uRam0000000x) があっても gd 配列は 1 回だけ定義する
     for n, va in sorted(ext.items(), key=lambda kv: kv[1]):
-        if va not in gtypes:
+        if va not in gd_done:
+            gd_done.add(va)
             d = pe_bytes(pe, va, 16)
             out.append('static unsigned char gd_%x[16] __attribute__((aligned(16))) = {%s};' % (va, ','.join(str(x) for x in d)))
         out.append('#define %s (*(%s*)gd_%x)' % (n, EXT_CTYPE[n], va))
```

- 出力不変の根拠 (実データなし): (1) THUNK 表の変更はコメントだけ。(2) `gd_done` の分岐が動くのは、同じ VA を指す 2 名が `EXT_CTYPE` に共存するときだけ。`EXT_CTYPE` の 11 名は VA が相異なる (検査済み) ので、現在の表では新旧の出力が同一になる。
- 合成入力で確認 (fake PE・delay 閉包の全 VA の合成 decompile 出力。旧 = `a2a4a942a` の ghidra_route、新 = `9588011ed`): 表どおりの名前だけの入力は生成 C が **cmp 一致**。`uRam0000000182280d00` を `EXT_CTYPE` に足して `DAT_182280d00` と同じ VA を参照させた入力では、`gd_182280d00` の配列定義が **2 → 1** 件になった (旧は同名の配列を 2 回定義し C では再定義エラー)。`thunk_map_check.py` は **7/7 PASS**。
- 未実施: 実データの e2e (Delay の emcc 件数・Gain/Haas/Gate の byte 一致・1000 trial) を HEAD で再実行していない。素材 `plugins-kilohearts`・`toolchain-emsdk` が本 run の `$ARTIFACTS_DIR` に無い (`fl-win64` のみ)。

**⑦ 未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `LAB_180fd2aab` (コード番地を値に書く継続点) | Delay の emcc が通らない | #3835 [KH-70] |
| `PTR__guard_dispatch_icall_1813a1d38` (CFG 間接呼出しの呼出先) | 同上 | #3835 [KH-70] |
| `(ulonglong)dVarN` の double ビット再解釈 98 行 | emcc は通るが、数値変換として誤る可能性 (Delay が通った後に効く) | #3836 [KH-71] |
| Stereo・Resonator の生成 C (STUB・THUNK・EXT_CTYPE の影響は未確認) | 名前が出る C の emcc 結果が変わるか未確認 | Stereo #3108 [KH-45]・Resonator #3764 [KH-63] (既存) |
| `9588011ed` での Delay・Gain/Haas/Gate の e2e 再測定 | 出力不変は合成入力で確認 (⑥b)。実データの再測定は未実施 | レビュー判断 (子 issue は作らない。素材 `plugins-kilohearts`・`toolchain-emsdk` を付けた再実行) |

**⑧ main 取り込み後 (merge `0524501f7`・競合 2 件の解消)**
- origin/main (`396f9f8b6`) を取り込んだ。main 側の変更は `ghidra_to_c.py` (Stereo の `cfg['stubs']`・`stubs` への統合・V128OPS の件数 assert)、`patches.py` (Delay の ABI 規則・#3800)、`ghidra_shim.h`。
- 競合は 2 件。`docs/DOC_MAP.md` は両側の行 (3802・3800) を残した。`ghidra_to_c.py` の stub 出力部は main の `stubs` (STUB + cfg stubs) を使い、本 PR の「本体を decompile している VA には stub・THUNK を出さない」条件 (`va not in vas`) を両方の出力に適用した。
- 測定 commit `6323671e7` から HEAD までの `ghidra_route` の差分 (main 取り込み分を含む。`git diff 6323671e7 HEAD -- tools/targets/kilohearts/ghidra_route`・3 files・+80 −7):

```diff
diff --git a/tools/targets/kilohearts/ghidra_route/ghidra_shim.h b/tools/targets/kilohearts/ghidra_route/ghidra_shim.h
index 0e792738a..5aeb67671 100644
--- a/tools/targets/kilohearts/ghidra_route/ghidra_shim.h
+++ b/tools/targets/kilohearts/ghidra_route/ghidra_shim.h
@@ -98,4 +98,21 @@ static inline V128 vpsrldq_avx(V128 s, int n) {
     for (int i = 0; i + n < 16; i++) r.b[i] = s.b[i + n];
     return r;
 }
+/* x86 `mul r64` (rdx:rax = rax × r64) を 128bit ベクタの `*` と印字した形 (stereo 180fdc470・180fdfdb0)。
+ * 呼出し直前に両オペランドの上位 qword は 0 (`_8_8_ = 0`) なので、積は 64×64→128 の符号なし積。 */
+static inline V128 v128_mul64(V128 a, V128 b) {
+    unsigned __int128 p = (unsigned __int128)a._0_8_ * b._0_8_;
+    V128 r; memcpy(r.b, &p, 16);
+    return r;
+}
+/* 128bit 整数加算 (機械語の add/adc の繰上がりを含む)。 */
+static inline V128 v128_add(V128 a, V128 b) {
+    unsigned __int128 x, y;
+    memcpy(&x, a.b, 16); memcpy(&y, b.b, 16);
+    x += y;
+    V128 r; memcpy(r.b, &x, 16);
+    return r;
+}
+/* Ghidra SUBPIECE: SUB168(x, 0) = 下位 8 バイト, SUB168(x, 8) = 上位 8 バイト。 */
+static inline ulonglong SUB168(V128 v, int off) { ulonglong r; memcpy(&r, v.b + off, 8); return r; }
 #endif
diff --git a/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py b/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py
index f6d277c82..2ef9ab8f0 100644
--- a/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py
+++ b/tools/targets/kilohearts/ghidra_route/ghidra_to_c.py
@@ -29,7 +29,11 @@ SNAPINS = {
     'haas': {'proc': 0x1804d0280, 'exports': [0x1804d0280, 0x1804d0180, 0x1804cff00, 0x1804cff90, 0x1804d0720], 'stubs': {}},
     'gate': {'proc': 0x1804c2f50, 'exports': [0x1804c2f50], 'stubs': {}, 'also': [0x180295f20, 0x180020e70]},
     'resonator': {'proc': 0x180743390, 'exports': [0x180743390], 'stubs': {}, 'also': [0x180fbc1f4, 0x180fbbfb8, 0x180fbdfcc, 0x180fbe018, 0x180fcf904, 0x180fd54cc, 0x180fd62dc, 0x180fd6320, 0x180fb6ce0, 0x180fd648c, 0x180fbdef4, 0x180fe5dfc, 0x180fd6498, 0x180fd662c, 0x180fe5f40, 0x180fd3144]},
-    'stereo': {'proc': 0x18080d4d0, 'exports': [0x18080d4d0], 'stubs': {}, 'also': [0x180fcd690, 0x180fce0d0, 0x180fdc470, 0x180fdc660, 0x180fdc700, 0x180fdfdb0, 0x180fdc6d8]},
+    'stereo': {'proc': 0x18080d4d0, 'exports': [0x18080d4d0], 'stubs': {
+        # 未関数化 callee (#3108 KH-45・2 件)。FP 例外の報告経路で、Inf 入力 (180fdc6d8 の指数全 1・仮数 0) でのみ到達する。
+        # also へ足すと閉包が広がる (§10-7j・§10-7l の前例) ため stub にする。到達時は abort (突合で検出)。
+        0x180fd8aac: 'void FUN_180fd8aac() { abort(); }',
+    }, 'also': [0x180fcd690, 0x180fce0d0, 0x180fdc470, 0x180fdc660, 0x180fdc700, 0x180fdfdb0, 0x180fdc6d8]},
     'delay': {'proc': 0x1802ed7f0, 'exports': [0x1802ed7f0], 'stubs': {}, 'also': [0x180005c50, 0x18004cf20, 0x180289ea0, 0x1802ecfc0, 0x1802ed3b0, 0x1802ed490, 0x1802ed550, 0x1802ed640, 0x1802ed790, 0x180f878e0, 0x180f8791c, 0x180f87cac, 0x180f87d40, 0x180f87f24, 0x180f88084, 0x180f880a4, 0x180f880e4, 0x180f88104, 0x180fa8534, 0x180fb5b4c, 0x180fb5bb4, 0x180fb5c20, 0x180fb5c6c, 0x180fb5dd0, 0x180fb5e6c, 0x180fb5f3c, 0x180fb5f5c, 0x180fb5f8c, 0x180fb6bf8, 0x180fb6c0c, 0x180fb6ce0, 0x180fbbfb8, 0x180fbc1f4, 0x180fbde90, 0x180fbdfcc, 0x180fbe018, 0x180fc1920, 0x180fc4590, 0x180fc61dc, 0x180fc61e4, 0x180fc6870, 0x180fc6d70, 0x180fc7468, 0x180fcce40, 0x180fcd400, 0x180fcd690, 0x180fcdbfc, 0x180fcde58, 0x180fce0d0, 0x180fcf904, 0x180fd0898, 0x180fd08d0, 0x180fd099c, 0x180fd0a64, 0x180fd0a98, 0x180fd0ac8, 0x180fd0b50, 0x180fd1540, 0x180fd172c, 0x180fd185c, 0x180fd1ac4, 0x180fd1b00, 0x180fd1b34, 0x180fd1f30, 0x180fd1f84, 0x180fd27a8, 0x180fd2a60, 0x180fd2ba0, 0x180fd2c10, 0x180fd2c90, 0x180fd2d38, 0x180fd2f20, 0x180fd2fcc, 0x180fd3144, 0x180fd320c, 0x180fd4f30, 0x180fd51cc, 0x180fd5250, 0x180fd54cc, 0x180fd5bcc, 0x180fd5bf4, 0x180fd5f04, 0x180fd5f30, 0x180fd620c, 0x180fd622c, 0x180fd62a8, 0x180fd62c8, 0x180fd62dc, 0x180fd6320, 0x180fd648c, 0x180fd6498, 0x180fd662c, 0x180fd66a0, 0x180fd7d94, 0x180fd7f54, 0x180fd8988, 0x180fd89f0, 0x180fd8aac, 0x180fd8bd4, 0x180fd8d08, 0x180fdb6e0, 0x180fdc320, 0x180fdc470, 0x180fdc660, 0x180fdc6d8, 0x180fdc6ec, 0x180fdc700, 0x180fdc714, 0x180fdc7b8, 0x180fdc844, 0x180fdc858, 0x180fdc880, 0x180fdfdb0, 0x180fe027c, 0x180fe2470, 0x180fe24b8, 0x180fe2788, 0x180fe27b0, 0x180fe3284, 0x180fe3310, 0x180fe3488, 0x180fe34b0, 0x180fe34e8, 0x180fe3510, 0x180fe3690, 0x180fe3cd0, 0x180fe4020, 0x180fe4394, 0x180fe5c6c, 0x180fe5dfc, 0x180fe5ef0, 0x180fe5f00, 0x180fe5f0a, 0x180fe5f40, 0x181327120, 0x181327314, 0x181327348, 0x18132753c]},
 }
 STUB = {  # 未 decompile の callee → C 実装 (RetDec stage-0 + kh_lower ルート (snapins/lift/kh_lower.py) の shims/fail-fast stub と同じ扱い)
@@ -40,12 +44,13 @@ STUB = {  # 未 decompile の callee → C 実装 (RetDec stage-0 + kh_lower ル
     0x180fe5c74: 'longlong FUN_180fe5c74() { abort(); return 0; }',
     0x180fe2508: 'longlong FUN_180fe2508() { abort(); return 0; }',
 }
-# IAT thunk (jmp [rip+disp] → KERNEL32 の import) → fail-fast stub。Ghidra は thunk の引数を落として `func_0x000<va>(...)` と呼ぶ。
-# 引数無しの定義 (`()`) は呼出の arity を問わない。Win API の意味は実装しない (到達時に abort し、突合で検出する)。
+# THUNK: Ghidra が `func_0x000<va>(...)` と呼ぶ callee → fail-fast stub。引数無しの定義 (`()`) は呼出の arity を問わない。
+# 到達時に abort し、突合で検出する。2 種類ある: (a) IAT thunk (jmp [rip+disp] → KERNEL32 の import)・(b) 未関数化 callee (本体を decompile していない VA)。
 THUNK = {
+    # (a) IAT thunk。Win API の意味は実装しない
     0x180fd81e4: 'longlong func_0x000180fd81e4() { abort(); return 0; } /* KERNEL32!FlsGetValue */',
     0x180fd81ec: 'longlong func_0x000180fd81ec() { abort(); return 0; } /* KERNEL32!FlsSetValue */',
-    # 未関数化 callee (delay 閉包の外)。decompile せず fail-fast stub にする。`func_0x000<va>` 形の呼出が残る。
+    # (b) 未関数化 callee (delay 閉包の外)。decompile せず fail-fast stub にする
     0x180fbdef4: 'longlong func_0x000180fbdef4() { abort(); return 0; } /* 未関数化 callee (stub) */',
     0x180fbdd78: 'longlong func_0x000180fbdd78() { abort(); return 0; } /* 未関数化 callee (stub) */',
 }
@@ -197,8 +202,10 @@ def main():
         if n not in EXT_CTYPE:
             raise SystemExit('未定義 identifier の型が未確定 (停止): ' + n)
         ext[n] = int(n[4:], 16)
+    gd_done = set(gtypes)  # 同じ VA を指す名前 (例 DAT_x と uRam0000000x) があっても gd 配列は 1 回だけ定義する
     for n, va in sorted(ext.items(), key=lambda kv: kv[1]):
-        if va not in gtypes:
+        if va not in gd_done:
+            gd_done.add(va)
             d = pe_bytes(pe, va, 16)
             out.append('static unsigned char gd_%x[16] __attribute__((aligned(16))) = {%s};' % (va, ','.join(str(x) for x in d)))
         out.append('#define %s (*(%s*)gd_%x)' % (n, EXT_CTYPE[n], va))
@@ -215,6 +222,10 @@ def main():
     protos = []
     bodies = []
     abi_hits = {}
+    from patches import V128OPS
+    v128_hits = {}
+    stubs = dict(STUB)
+    stubs.update(cfg['stubs'])
     for va in vas:
         t = src[va]
         t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
@@ -247,6 +258,9 @@ def main():
         for nm, rx, rp in ABI.get(name, []):
             t, k = re.subn(rx, rp, t)
             abi_hits[nm] = abi_hits.get(nm, 0) + k
+        for nm, rx, rp, _ in V128OPS.get(name, []):
+            t, k = re.subn(rx, rp, t)
+            v128_hits[nm] = v128_hits.get(nm, 0) + k
         m = re.search(r'^([\w \*]+?)\s*\n?\s*FUN_%x\((.*?)\)\s*\n\s*\{' % va, t, re.S | re.M)
         if not m:
             m = re.search(r'^([\w \*]+?)\s+FUN_%x\((.*?)\)\s*\{?' % va, t, re.S | re.M)
@@ -255,12 +269,14 @@ def main():
         bodies.append(t)
     for nm, _, _ in ABI.get(name, []):
         assert abi_hits.get(nm) == 1, 'ABI rule hit %s: %s' % (abi_hits.get(nm), nm)
+    for nm, _, _, n in V128OPS.get(name, []):
+        assert v128_hits.get(nm) == n, 'V128 rule hit %s (want %d): %s' % (v128_hits.get(nm), n, nm)
     # スタブは本体を decompile していない callee にだけ出す (本体がある VA に出すと宣言が衝突する: FUN_18004cf20・delay)
-    for va, s in STUB.items():
+    for va, s in stubs.items():
         if ('FUN_%x' % va) in alltxt and va not in vas:
             protos.append(s.split('{')[0].strip() + ';')
     out += protos
-    out += [STUB[v] for v in STUB if ('FUN_%x' % v) in alltxt and v not in vas]
+    out += [stubs[v] for v in stubs if ('FUN_%x' % v) in alltxt and v not in vas]
     out += [THUNK[v] for v in THUNK if ('func_0x000%x' % v) in alltxt and v not in vas]
     # --- 呼出名の統一: Ghidra は未命名 callee を func_0x<va> で呼ぶが、定義側は同一 va を FUN_<va> で出す (also 追加分)
     defined = set(vas)
diff --git a/tools/targets/kilohearts/ghidra_route/patches.py b/tools/targets/kilohearts/ghidra_route/patches.py
index b41d98fc5..58f905b45 100644
--- a/tools/targets/kilohearts/ghidra_route/patches.py
+++ b/tools/targets/kilohearts/ghidra_route/patches.py
@@ -46,4 +46,44 @@ ABI = {
         ('stereo 186 FUN_180fcd690 2nd arg xmm1 unset (placeholder 0.0)', r'dVar12 = \(double\)FUN_180fcd690\(dVar12\);', 'dVar12 = (double)FUN_180fcd690(dVar12, 0.0);'),
         ('stereo 567 FUN_180fdc660 arg double = param_1 bits (movq xmm0,r9 180fce528; ulonglong uVar1 を数値変換しない)', r'uVar3 = (?:func_0x000|FUN_)180fdc660\(uVar1\);', 'uVar3 = FUN_180fdc660(param_1);'),
     ],
+    # delay (#3800 KH-64): 引数過不足のうち、呼出先 FUN_180fd4f30 (longlong 1 引数) の 22 件 = FUN_180fe3690 13 件・FUN_180fe3310 4 件・FUN_180fe3cd0 5 件。
+    #   呼出元の機械語 (180fe3690 の capstone): `mov rcx,[rbx+off]` → `cmp rcx,[global]` → `je` → `call FUN_180fd4f30` (rbx = 入力 param_1)。
+    #   rcx = *(param_1 + off)。off は C の条件式の添字と一致 (0x18〜0x48・0x68〜0x90 の 13 個、番地順 = C 行順)。
+    #   FUN_180fe3310: 直線部 6779・6783 は `mov rcx,[rbx+0xf0]`・`[rbx+0xe8]`。ループ部 6801・6805 は `mov rcx,[rdi]`・`[rdi-8]` (rdi = puVar6、
+    #   ループ末 `add rdi,0x20` まで不変)。FUN_180fe3cd0: `mov rcx,[rcx]` (= *param_1)・`[rbx+8]`・`[rbx+0x10]`・`[rbx+0x58]`・`[rbx+0x60]` (= param_1[1]・[2]・[0xb]・[0xc])。
+    #   規則 1 件 = 呼出し 1 件 (件数 1 を assert)。残り 86 件は REPORT_APPENDIX_3800.md の分類を参照。
+    'delay': [
+        ('delay 6939 FUN_180fe3690 rcx=[param_1+0x18]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x18\) != _DAT_182989698\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x18));'),
+        ('delay 6942 FUN_180fe3690 rcx=[param_1+0x20]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x20\) != _DAT_1829896a0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x20));'),
+        ('delay 6945 FUN_180fe3690 rcx=[param_1+0x28]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x28\) != _DAT_1829896a8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x28));'),
+        ('delay 6948 FUN_180fe3690 rcx=[param_1+0x30]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x30\) != _DAT_1829896b0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x30));'),
+        ('delay 6951 FUN_180fe3690 rcx=[param_1+0x38]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x38\) != _DAT_1829896b8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x38));'),
+        ('delay 6954 FUN_180fe3690 rcx=[param_1+0x40]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x40\) != _DAT_1829896c0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x40));'),
+        ('delay 6957 FUN_180fe3690 rcx=[param_1+0x48]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x48\) != _DAT_1829896c8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x48));'),
+        ('delay 6960 FUN_180fe3690 rcx=[param_1+0x68]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x68\) != _DAT_1829896e8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x68));'),
+        ('delay 6963 FUN_180fe3690 rcx=[param_1+0x70]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x70\) != _DAT_1829896f0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x70));'),
+        ('delay 6966 FUN_180fe3690 rcx=[param_1+0x78]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x78\) != _DAT_1829896f8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x78));'),
+        ('delay 6969 FUN_180fe3690 rcx=[param_1+0x80]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x80\) != _DAT_182989700\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x80));'),
+        ('delay 6972 FUN_180fe3690 rcx=[param_1+0x88]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x88\) != _DAT_182989708\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x88));'),
+        ('delay 6975 FUN_180fe3690 rcx=[param_1+0x90]', r'(if \(\*\(longlong \*\)\(param_1 \+ 0x90\) != _DAT_182989710\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0x90));'),
+        ('delay 6779 FUN_180fe3310 rcx=[param_1+0xf0]', r'(if \(\(\*\(int \*\*\)\(param_1 \+ 0xf0\) != \(int \*\)0x0\) && \(\*\*\(int \*\*\)\(param_1 \+ 0xf0\) == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0xf0));'),
+        ('delay 6783 FUN_180fe3310 rcx=[param_1+0xe8]', r'(if \(\(\*\(int \*\*\)\(param_1 \+ 0xe8\) != \(int \*\)0x0\) && \(\*\*\(int \*\*\)\(param_1 \+ 0xe8\) == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*(undefined8 *)(param_1 + 0xe8));'),
+        ('delay 6801 FUN_180fe3310 loop rcx=*puVar6', r'(if \(\(\(puVar6\[-2\] != 0x1829899d8\) && \(\(int \*\)\*puVar6 != \(int \*\)0x0\)\) && \(\*\(int \*\)\*puVar6 == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*puVar6);'),
+        ('delay 6805 FUN_180fe3310 loop rcx=puVar6[-1]', r'(if \(\(\(puVar6\[-3\] != 0\) && \(\(int \*\)puVar6\[-1\] != \(int \*\)0x0\)\) && \(\*\(int \*\)puVar6\[-1\] == 0\)\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(puVar6[-1]);'),
+        ('delay 6990 FUN_180fe3cd0 rcx=*param_1', r'(if \(\*param_1 != _DAT_182989680\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(*param_1);'),
+        ('delay 6993 FUN_180fe3cd0 rcx=param_1[1]', r'(if \(param_1\[1\] != _DAT_182989688\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[1]);'),
+        ('delay 6996 FUN_180fe3cd0 rcx=param_1[2]', r'(if \(param_1\[2\] != _DAT_182989690\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[2]);'),
+        ('delay 6999 FUN_180fe3cd0 rcx=param_1[0xb]', r'(if \(param_1\[0xb\] != _DAT_1829896d8\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[0xb]);'),
+        ('delay 7002 FUN_180fe3cd0 rcx=param_1[0xc]', r'(if \(param_1\[0xc\] != _DAT_1829896e0\) \{\n\s*)FUN_180fd4f30\(\);', r'\1FUN_180fd4f30(param_1[0xc]);'),
+    ],
+}
+# V128 演算 (#3108 KH-45): Ghidra は x86 の `mul r64` (rdx:rax = rax × r64) と 128bit 加算 (add/adc) を、128bit ベクタの
+# `*` `+` と `SUB168(x, n)` (下位・上位 8 バイトの切出し) で印字する。stereo 180fdc470 (mul 180fdc4ba・4c8・4e6 / add 4d4)・
+# 180fdfdb0 (mul 180fdfdfa・fe08・fe26 / adc fe17) で確認。両オペランドの上位 qword は 0 (`_8_8_ = 0`) なので、
+# 積は 64×64→128 の符号なし積 (v128_mul64)、`+` は 128bit 整数加算 (v128_add)。件数 (第 4 要素) を assert する。
+V128OPS = {
+    'stereo': [
+        ('stereo mul64 + add128 (180fdc470 l37, 180fdfdb0 l36)', r'(auVar\d+) = (auVar\d+) \* (auVar\d+) \+ (auVar\d+);', r'\1 = v128_add(v128_mul64(\2, \3), \4);', 2),
+        ('stereo mul64 inside SUB168 (180fdc470 l29-30, 180fdfdb0 l29-30)', r'SUB168\((auVar\d+) \* (auVar\d+),', r'SUB168(v128_mul64(\1, \2),', 4),
+    ],
 }
```

- 検証 (取り込み後・合成のみ): `thunk_map_check.py` **7/7 PASS**。`ghidra_to_c.py` の `py_compile` OK。
- 未実施 (素材なし): 取り込み後の Delay の emcc 件数・Gain/Haas/Gate の生成 C の cmp・wasm sha256・1000 trial。`$ARTIFACTS_DIR` は `fl-win64` のみで、`plugins-kilohearts`・`toolchain-emsdk`・Ghidra・emsdk が無い。
- 注意: ⑥ の件数 (556 → 534) は測定 commit `6323671e7` (main 取り込み前) の値。main の Delay ABI 規則 (#3800) が入った HEAD の件数ではない。
