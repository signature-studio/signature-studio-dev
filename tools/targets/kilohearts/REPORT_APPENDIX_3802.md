# REPORT 付録 (#3802 KH-66): Delay の未定義 identifier・未関数化 callee・スタブ衝突の規則

#3096 (KH-44) の付録 `REPORT_APPENDIX_3096.md` §10-7t の続き。前節の正本は同 §10-7t ②の census。

#### 10-7u. #3802 (KH-66) run: 未定義 identifier 15・未関数化 callee 5・衝突 2 を解消 (部分・emcc 556 → 534 件)
- 結論: Delay の emcc 残件 556 → **534** 件。下の 3 種を解消した: 未定義 identifier のうち `DAT_`・`uRam` の 15 件 (規則は下の EXT_CTYPE)、未関数化 callee 5 件 (fail-fast stub)、`FUN_18004cf20` の conflicting types 2 件 (本体がある VA の stub を出さない)。Gain/Haas/Gate の生成 C は origin/main と byte 一致、wasm の sha256 も一致、1000/1000 bit-exact。
- 残件 (子 issue): `LAB_180fd2aab`・`PTR__guard_dispatch_icall_1813a1d38` の 2 件 → #3835 [KH-70]。double のビット再解釈 `(ulonglong)dVarN` 98 行 (silent miscompile の疑い) → #3836 [KH-71]。
- 測定 commit (コードを変えた最後の commit): `6323671e7` (`tools/targets/kilohearts/ghidra_route/ghidra_to_c.py`)。比較元は origin/main `40d3a788d`。
  - `git diff 6323671e7 HEAD -- tools/targets/kilohearts/ghidra_route` の出力: 0 行 (本節の追記 commit は REPORT のみ)。

**① 環境 (repo 外。`work/` は使わない)**
- 素材 `plugins-kilohearts` (`tar --zstd -xf` で `Kilohearts Offline Installer.zip` 3,833,108,300 B のみ取り出し → `payload.dat` 3,817,512,248 B → `windows.zip/1ccb1df8c8f10745` 55,114,108 B → `HeartCore.core_64` 76,642,304 B)。
- [GHIDRA] 12.1.4: 本 run で GitHub release から取得 (zip 569,649,598 B・sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)。`GHIDRA_HOME` (repo 外) に展開 (本 run で作成)。[JDK21] `temurin-21-jdk-amd64`、[EMSDK] emcc 6.0.12。`toolchain-emsdk` は `/opt/emsdk` を使用。`fl-win64` は未使用。
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
- Stereo・Resonator の生成 C は本 run では再測定していない。この名前が出る場合だけ C が変わる。

**⑤ 規則 3: スタブと本体の衝突 (`FUN_18004cf20`・conflicting types 2)**
- 原因: Delay は `FUN_18004cf20` を `also` で decompile している (本体あり) のに、`STUB` の宣言 (`void* a, void* b, void* c`) も出していた。
- 規則: STUB は本体を decompile していない VA にだけ出す (`va not in vas`)。THUNK も同じ条件。Gain/Haas/Gate は `FUN_18004cf20` の本体を持たないため、stub がそのまま出る。

**⑥ 回帰 (Gain / Haas / Gate・測定 commit `6323671e7` の converter)**
- 生成 C: origin/main の converter の出力と **byte 一致** (`cmp`・3 本とも)。
- wasm: sha256 先頭 16 桁 Gain `57d8b9a34c5bcc28`・Haas `af100316c19d5b34`・Gate `95bcc2bd7d1b802f` (origin/main と同一)。サイズ 15,161 B・16,878 B・17,367 B。
- 突合 (`native_ref` 1000 trial・seed 7・`compare.mjs`): Gain **1000/1000** (calls 4999/4999)・Haas **1000/1000** (calls 5500/5500)・Gate **1000/1000** (calls 4999/4999)。
- 未実施: Delay の突合・1000 trial (emcc が通らないため。#3073 [KH-41])。

**⑦ 未解決**

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `LAB_180fd2aab` (コード番地を値に書く継続点) | Delay の emcc が通らない | #3835 [KH-70] |
| `PTR__guard_dispatch_icall_1813a1d38` (CFG 間接呼出しの呼出先) | 同上 | #3835 [KH-70] |
| `(ulonglong)dVarN` の double ビット再解釈 98 行 | emcc は通るが、数値変換として誤る可能性 (Delay が通った後に効く) | #3836 [KH-71] |
