# REPORT 付録 (#3884 KH-76): FUN_180fdc470 の戻り xmm0 / rax の C 化

上位の経緯は `REPORT.md` の KH-74 (#3853) 系の節。本付録は #3884 の結果と、突合の再測定状況の正本。

#### 結論

- `FUN_180fdc470` の ret (180fdc65b) の xmm0 (縮約値) と rax (四分象限) を機械語の式で `kh_fn_180fdc470` として C 化し、native (`HeartCore.core_64`) と bit 一致を取った (測定 commit `99b367fc0`・正のみ 0<x<1 は未突合)。
- **HEAD (main 取り込み後) の再突合は、この run では未実施**。この run には素材 `plugins-kilohearts` が無く、`HeartCore.core_64` を得られなかったため。PR 本文の `oc_artifacts: fl-win64 plugins-kilohearts toolchain-emsdk` で再実行する。

#### 測定 1: 測定 commit `99b367fc0` (実装者の実測)

- 測定 commit (コードを変えた最後の commit): `99b367fc0`。
- 環境: `gcc -O1 -ffp-contract=off`・seed 7・1,000,000 試行・wall 0.100 s・load 0.14 0.08 0.05。
- 実行コマンド: `./xmm0_check <HeartCore.core_64> 1000000 7` (`xmm0_check.c` の 470 検査)。
- 結果:
  - `660`: rax 不一致 0・xmm0 不一致 0 (NaN 同士の payload 差 28,378 件は別計上)。
  - `470`: rax 不一致 0・xmm0 不一致 0。
  - `kh_xmm0_check RESULT: PASS` (rc=0)。
- ネガコン (作業コピーで `kK790` 項 `t4 = fma(x2, kK790, t4)` を外す): 470 の xmm0 不一致 214,381 件・`FAIL`・rc=1。

#### 測定 2: HEAD の差分 (main 取り込みによる差分)

- `git diff 99b367fc0 HEAD -- tools/targets/kilohearts/ghidra_route` = **288 行** (`ghidra_to_c.py` +28・`kh_xmm0.h` +88・`patches.py` +7・`xmm0_check.c` 49 行変更)。
- 差分の内訳: `kh_xmm0.h` の `FUN_180fdfdb0` (KH-77・#3885・`e2e31a569`) と `xmm0_check.c` の dfdb0 mode は main 側の変更。`ghidra_to_c.py`・`patches.py` の増分は main 側 (`c0c75890f` FNPTR・`a51ea1aa5` delay 規則) の取り込み。本 PR の変更は `kh_xmm0.h` の 470 block (`kh_tab470`・`kh_fn_180fdc470`・`kh_mul64`) を main 版に足し直したことと、`xmm0_check.c` の `470` mode 追加のみ。
- 470 block は `99b367fc0` と**バイト一致** (`sed`/Python で `KH-76` から `kh_fn_180fdc470` 閉じまでの 6143 B を比較)。
- 統合後の `kh_xmm0.h`・`xmm0_check.c` は `gcc -O1 -ffp-contract=off -Wall -Wextra` で警告なしに通る (rc=0)。

#### 再測定が必要な理由

- 規約 (`docs/WORKFLOW.md` §6): 差分が 0 行でないので、HEAD で再測定してから報告する。この run では `plugins-kilohearts` が無く再測定不可。
- 次回の review run は PR 本文の `oc_artifacts: fl-win64 plugins-kilohearts toolchain-emsdk` で素材を得て、`xmm0_check <HeartCore.core_64> 1000000 7` を HEAD で実行する。その結果を本付録へ追記する。

#### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD での native 再突合 (`plugins-kilohearts` 素材が必要) | 測定 1 は `99b367fc0` の値。HEAD の一致は未確認 | 本 PR の review run で再測定 (素材指定済み) |
| `FUN_180fdc470` の 0<x<1 の突合 | native が table 外を読んで SIGSEGV のため検証不能。機械語の式は同じ | #3884 の範囲外 (起票なし・本付録の注記) |

#### 測定 3: KH-113 (#4704) の呼出元適用と生成 C の実測

- 測定 commit: `2e16b4ea8` (コード変更は `ghidra_route/patches.py` の ABI 規則 2 件のみ)。HEAD と同じ commit で再現した。
- 規則: `stereo 502 caller 180fcd690` と `stereo 571 caller 180fce0d0`。呼出しと読出しを 1 組で `kh_fn_180fdc470(x)` + `kh_xmm0_180fdc470` に置換する。callee 本体の Ghidra 版は `kh_fn` を呼ばないため、読出しだけ置換すると xmm0 が未初期化になる (呼出し側だけ変えても効かない)。件数 1 を assert する。
- 生成 C (`ghidra_to_c.py stereo --fix bitcast,intload,stackpair,assoc,concat`、HEAD と `origin/main` で比較):
  - `extraout_XMM0_Qa_01` の代入読出し: **4 → 0** (宣言 2 行は残る)。
  - 行数: 2345 (HEAD) = 2345 (`origin/main`)。
  - 関数 `FUN_180fdc470` の 2 呼出し (852・921) は `kh_fn_180fdc470(...)` と `kh_xmm0_180fdc470` に変わった。
- emcc (`emcc -O1 -w`、HEAD と `origin/main`): **error 17 件 (両方)**。メッセージの内訳は一致。残る error は stereo の既存の型不一致 (`_DAT_1813a1d40` の関数ポインタ・`uint ^ float` 等) で、本 issue の範囲外。stereo 全体の wasm はまだ作れない。
- callee 単体の突合 (`ghidra_route/xmm0_check.c 470`、HeartCore.core_64 の native と比較): **1,000,000 試行で rax・xmm0・xmm1 すべて不一致 0 (PASS)**。`0<x<1` は native 側の制約で除外 (skipped 0 = 入力は負か |x|≥1 のみ)。
- 回帰 (Gain / Haas / Gate): 生成 C は `origin/main` と **バイト一致** (`cmp` 0 バイト ×3)。
- ネガティブコントロール: 規則の正規表現を壊すと `AssertionError: ABI rule hit 0: stereo 502 caller 180fcd690 reads xmm0 of 470 (extraout_XMM0_Qa_01)` で rc=1。
- 素材: `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 (`/tmp` 展開)、JDK 21。`ghidra_to_c.py stereo` は `also` の `0x180fd8aac` (stub 用の未関数化 callee) の `.c` を要求するため、同 VA を `DecompEach` で追加 decompile した (49 関数)。

#### 未解決

- stereo 全体の数値突合 (#3073): emcc が 17 error で通らないため wasm を作れず、native との全体突合は未実施。
- 戻り xmm1 (残差) は本 issue の範囲外 (#4705 [KH-114] の範囲)。
