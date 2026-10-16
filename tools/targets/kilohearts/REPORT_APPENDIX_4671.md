# REPORT 付録 (#4671 KH-106): Delay の関数ポインタ global 9 件 (`_DAT_1813a1d40`)

上位の経緯は `REPORT_APPENDIX_3801.md` §10-7x (P1 行)。本付録は #3849 [KH-80] の子 issue #4671 の結果。

#### 10-7y. #4671 (KH-106): 関数ポインタ global `_DAT_1813a1d40` の型規則 (部分・9 → 3)

- 結論: 関数ポインタ global 9 件のうち **6 件** を `GTYPE` の型 `FNPTR` (`void (*)()`・到達時 abort) で解消した。census の型不一致は **119 → 113** (`FX=…,gtype,lanes`・同一入力の直前比較)。残りの **3 件** (戻り値を代入する呼出し 3 箇所) は #4693 (KH-112) で戻り値型 `int` を機械語で決め、型を `int (*)()` に直して解消 (型不一致 312 → 309)。Gain/Haas/Gate の `.o` は 3 本とも不変。
- 測定 commit (コードを変えた最後の commit): `c0c75890f` (`git log -1 --format=%h -- tools/targets/kilohearts/ghidra_route` の結果)。測定は作業ツリーの `ghidra_route` (差分込み) で行い、その後 `git commit` した内容と同一。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B)・`toolchain-emsdk` (emcc 6.0.12)・Ghidra 12.1.4 (zip sha256 `ddac49f9…d2db` 一致)・JDK 21 (temurin-21)。すべて `$RUNNER_TEMP/kh` (repo 外)。n=1。

**機械語の確認 (実機 `HeartCore.core_64`)**

- slot `0x1813a1d40` の PE 初期値は `0x181383e50` (CFG thunk: `jmp [rip+..]` → `jmp rax`)。`0x1813a1d38` と同じ値で、`REPORT_KH19.md` の thunk 経路と一致。issue 本文の『PE 上の値は 0x1813e3850』は誤り (`0x1813e3850` の 8 byte は `9f662c96da41c855` で関数ポインタではない)。
- 9 件の呼出しは全て `call/jmp QWORD PTR [rip+...] # 0x1813a1d40` (CFG dispatch)。呼び先は呼出し直前に `rax` へ入る値で決まる (例: `180fd0867` の `mov rax,r8`・`180fe27e1` の `mov rax,rdx`)。slot の値は実行時に呼出元で決まるため、C の値として再現しない。
- 同じ slot を使う呼出しは delay 閉包外を含め 44 箇所 (`objdump` の `# 0x1813a1d40` の数)。本付録の 9 件は delay.c の `_DAT_1813a1d40` 参照 (9 行)。

**規則 (`patches.py` の `GTYPE`・`ghidra_to_c.py` の `FNPTR` 分岐)**

- 型 `FNPTR`: `static void FNPTR_1813a1d40() { abort(); }` と `static void (*fp_1813a1d40)() = FNPTR_1813a1d40;` を生成し、`_DAT_1813a1d40` を `fp_1813a1d40` に置換する。PE の thunk 値は C に持ち込まない。
- 置き場: 型の上書きなので `GTYPE` (ABI 表ではない)。`ghidra_to_c.py --fix gtype` を付けたときだけ効く。規則が使われなければ `assert` で停止する (既存の仕組み)。
- 引数・戻り値を `void (*)()` (prototype なし) にした理由: 呼出し 9 件の引数数はそれぞれ 0・1・2・3・5 で揃わず、戻り値を使う呼出しと使わない呼出しが混在するため、1 つの prototype を決めると他の呼出しがエラーになる。`prototype なし` の呼出しは emcc で warning (`-Wdeprecated-non-prototype`) のみになる。

**census (`gtype_census.sh`・`FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes`・HEAD=本 PR の作業ツリー)**

| 測定 (`FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes`・origin/main `325cf6a4d` 基点) | 型不一致 | 合計 (`emcc error 行`) |
|---|---|---|
| FNPTR なし (`GTYPE` は #3801 の 13 件のみ) | 119 | 342 |
| 本 PR (`FNPTR` 追加) | **113** | **336** |

- 本 run の値は `325cf6a4d` (main) 基点の再測定。#3801 の表 (`fe5fa8215`) の合計 418 とは一致しない (型不一致 119 は一致)。差の原因は未確認 (main 側の変更か census の数え方)。合計の比較は本 run の 2 行の間でだけ行う。
- 型不一致 -6 の内訳: 9 件のうち 6 件は emcc の型不一致 (`Wincompatible-pointer`・`int-conversion`) から消えた。
- 残り 3 件は戻り値を代入する箇所 (`int`・`undefined8` に `void` を代入) の型不一致 (`assigning to ... from incompatible type 'void'`) として残る。
- prototype なしの呼出し 7 行 (2546・4648・4769・4875・4936・5948・6731) は、emcc では `-Wdeprecated-non-prototype` の warning になり、error 行には数えられない (census は error 行だけを数える)。

**残件 3 件の戻り値型 (#4693 KH-112 で決定)**

生成 C の行は現在 4916・5928・6711 (issue 本文の 4936・5948・6731 は旧版の行)。囲む関数は `FUN_180fd1ac4`・`FUN_180fd7f54`・`FUN_180fe27b0`。issue 本文の呼出元名 `FUN_180fd1b00`・`FUN_180fd7d94`・`FUN_180fe2788` は slot を呼ぶ関数ではない。

| delay.c (現行) | 囲む関数 | 呼出し直後の読み方 (機械語) | 決定 |
|---|---|---|---|
| 4916 | `FUN_180fd1ac4` (issue 4936) | 呼出元 `180fd1ae4` の後で `test eax,eax` (32bit) | **int** |
| 5928 | `FUN_180fd7f54` (issue 5948) | 末尾 jump で戻る。呼出元 `180fe029f` は rax を読まず `[rsp+0x30]` を読む | 読み手なし。9 件共通の **int** に合わせる (値は使われない) |
| 6711 | `FUN_180fe27b0` (issue 6731) | 呼出元 `180fd6016`・`180fd89d1` の後で `test eax,eax` (32bit) | **int** (issue の undefined8 は誤り。機械語は 32bit で読む) |

- 規則: `patches.py` の `'1813a1d40': 'FNPTR'` の型を `int (*)()` にし、`ghidra_to_c.py` の `FNPTR` 分岐の戻り型を `int` にした。9 件の slot 全体で 1 つの型。
- 型不一致 (census): **312 → 309** (`assigning to ... from incompatible type 'void'` の 3 件が消えた)。残る 309 は別の分類 (128bit レーン型・引数数不一致・演算の型不一致)。
- 規則を入れたあとの確認: Gain/Haas/Gate の `.c` と `.o` は変更前と `cmp` 一致。
- 未確認: 呼出元 2 箇所 (`180fd6016`・`180fd89d1`) が返す値の使い道は、この付録の範囲外。型を int に決めたのは rax の下位 32bit が読まれることだけに基づく。

**Gain/Haas/Gate の `.o` 不変**

- `cmp` で基準 (`FX` から `gtype` を外さず、`FNPTR` 追加前の `ghidra_route`) と一致: gain 1,435 B・haas 3,217 B・gate 3,756 B (3 本とも `cmp` 一致)。

**再現**

- `FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>` (`<work>` は repo 外。`win/HeartCore.core_64`・`emsdk/`・`ghidra/ghidra_12.1.4_PUBLIC/` を置く)。
- 注: `gtype_census.sh` は `emsdk/emsdk_env.sh` を前提にするが、`toolchain-emsdk` の展開は `emsdk/emsdk/` 配下になり、`emsdk_env.sh` が emcc を PATH に載せない。`PATH=<emsdk>/upstream/emscripten:<emsdk>/upstream/bin:$PATH EMSDK=<emsdk>` で emcc を直接通す (本 run の手順)。
