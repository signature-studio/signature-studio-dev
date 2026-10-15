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
- 測定 commit `6323671e7` から HEAD までの `ghidra_route` の差分 (main 取り込み分を含む・3 files・+80 −7) の全文は `tools/targets/kilohearts/REPORT_APPENDIX_3802_DIFF.md` (`git diff 6323671e7 HEAD -- tools/targets/kilohearts/ghidra_route` の出力・159 行)。
- 検証 (取り込み後・合成のみ): `thunk_map_check.py` **7/7 PASS**。`ghidra_to_c.py` の `py_compile` OK。
- 未実施 (素材なし): 取り込み後の Delay の emcc 件数・Gain/Haas/Gate の生成 C の cmp・wasm sha256・1000 trial。`$ARTIFACTS_DIR` は `fl-win64` のみで、`plugins-kilohearts`・`toolchain-emsdk`・Ghidra・emsdk が無い。
- 注意: ⑥ の件数 (556 → 534) は測定 commit `6323671e7` (main 取り込み前) の値。main の Delay ABI 規則 (#3800) が入った HEAD の件数ではない。
