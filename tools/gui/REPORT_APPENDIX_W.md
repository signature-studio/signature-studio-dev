# REPORT 付録 W — #3460 [WIN-23] FL 非依存の W 版 Win32 テストゲスト・headless surface 統計

親: `tools/gui/REPORT.md` §21 (要約)。対象 issue: #3460 (親 #2712 / 関連 #2716)。

## 結論
- **受入 2 (headless surface 統計) は完了**: `gui_hl_stats` (w×h・非背景画素数・厳密な色数・sha256) と単体テスト 21/21 PASS、ネガコン 2 種 (1 bit 反転で sha が変わる / 全面背景は非自明でない) を実測。
- **受入 1 は一部**: W 版ゲスト `gui_app_w.c` は mingw でビルドでき、RetDec で lift できる (`lifted.c` まで)。
- **受入 1・3 は未達**: lift 後の `SetWindowLongPtrW` の引数 (関数 VA) が **32 bit に切り詰められ**、native 実行が SEGV する (下記「発見」)。よって最終 surface は得られず、オラクル比較・native sha256 は未取得。
- 副産物: `gui_lift_post.py` の後処理が関数ポインタ型の大域 `T (*gN)(...)` を落とす欠陥を直した (それまではコンパイルエラー)。既存の gui_app の native 通しは回帰せず (EXACT MATCH 0/64,000 px)。

## 検証 (コミット `0705571e4`、クリーン worktree `ws-3460`、4 vCPU)
| 項目 | 結果 | 数え方・条件 |
|---|---|---|
| `bash tools/gui/test/stats_test.sh` | **21 passed, 0 failed** | SHA-256: FIPS 180-4 の既知値 (空・abc・448bit・100 万 a) と境界 55/56/64 byte。期待値は Python `hashlib` で求めた定数。統計: 全面背景 4x3 → nonbg 0・色 1・非自明でない / 1 画素 → nonbg 1・色 2 / 矩形 2 枚 → nonbg 7・色 3 / 1000 色 → 色 1000 (上限で打ち切らない) / 24bit 端 (白と黒) → 色 2 / alpha が sha に入らない |
| ネガコン (sha) | 画素 1 の B の 1 bit 反転 → sha が `c2b05675…` (全面背景の sha `6a64a6d5…` と不一致) | `stats_test.c` 内で判定 |
| `gui_app.c` の native 通し (`native_e2e.sh`、後処理変更後) | rc 0・**EXACT MATCH 0/64,000 px** | 回帰確認 (変更前の基準も同値) |
| `gui_app_w.c` の lift (`gui_lift.sh … WndProc SubWndProc`) | rc 0 (PE32+ → RetDec → 後処理 `lifted.c`) | 自動検出は `WndProc` のみ。`SubWndProc` は fnmap に入るが明示指定が安全 |
| `native_w_e2e.sh` (native 通し) | **FAIL** (AddressSanitizer SEGV at `0x0000400011f8`) | 後述の発見。最終 surface 未取得 |

## 発見 (lift 欠陥。DEFECTS.md 形式の行案 — DEFECTS.md の直接編集は PM 判断)
- **症状**: `SetWindowLongPtrW(hWnd, GWLP_WNDPROC, <関数 VA>)` を呼ぶと、shim が受けた関数 VA は 0x400011f8 (正しくは 0x1400011f8)。呼出し先が不正アドレスになり SEGV。
- **最小再現**: `tools/gui/test/gui_app_w.c` の `SetWindowLongPtrW(happ, GWLP_WNDPROC, (LONG_PTR)SubWndProc)`。
- **根本原因 (推定。RetDec の出力で確認)**: `lifted.c` で `SetWindowLongPtrW(hWnd, -4, 0x400011f8)` となり、関数アドレスの即値が 32 bit に畳まれている。fnmap `gui_lift_fnmap` には `0x1400011f8` が入っているため一致しない。
- **検出信号**: `lifted.c` の関数 VA 定数 (`0x4000xxxxx`) が fnmap の上位 32 bit 欠けの値と一致する。ASan の SEGV の pc が image の範囲外の小さい値になる。
- **修復案**: 未実施 (子 issue)。候補は (a) 後処理で切り詰め VA を fnmap の完全 VA に戻す、(b) RetDec の関数アドレス取得 (lea) を 64 bit で扱う設定。どちらも検証が要る。
- **実施した修正 (本 PR)**: `gui_lift_post.py` が `T (*gN)(...) = NULL;` を宣言せず `gN` が未宣言になる欠陥 (loud: コンパイルエラー) を直した。整数 → 関数ポインタ → 整数のキャストは `(int64_t)` へ畳む。

## 範囲外・未達
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 関数 VA の 32 bit 切り詰め (上記) の修復と、W 版ゲストの native 通し (受入 1 の実行・受入 3 のオラクル画素一致・ネガコン) | W 版ゲストが動かない | 子 issue [WIN-30] (本 PR の範囲外) |
| wasm / Chrome の OffscreenCanvas 読み戻しの sha256 一致 (受入 5) | native と wasm の一致は未確認 | 子 issue [WIN-31] |
| `GUI-REACH` の順序検査 (受入 4) と `tools/gui/e2e.sh` への組込み (受入 6) | trace の機械検査は未実施 | 子 issue [WIN-32] |
| `gui_lift_post.py` の変更の wasm 経路 (`gui_wasm.sh`・`e2e.sh` 全体) の回帰 | emcc 未展開のため未実行 | [WIN-31] の e2e 再実行に含める |

## 測定: lift 後処理の変更の既存利用者への影響 (差し戻し対応・測定 HEAD `f6a2619f3`)
- 比較: `tools/gui/lift/gui_lift_post.py` の base (`6ef4ef958`) と head (`f6a2619f3`) を、同じ `retdec.c` と同じ PE に適用し、出力 `lifted.c` の sha256 を比べた。`gui_lift_post.py` は main (`origin/main`) でも `6ef4ef958` と同一 (`git diff 6ef4ef958 origin/main` 0 行)。
- 素材: mingw は `apt` で導入 (`x86_64-w64-mingw32-gcc` 13)。RetDec は上流 v5.0 Linux 配布物 (`RetDec-v5.0-Linux-Release.tar.xz`) を本 run で取得した。R2 の `toolchain-retdec` は本 run に展開されていない (`$ARTIFACTS_DIR` は `fl-win64` のみ)。版は `docs/REFERENCES.md` の `toolchain-retdec` (v5.0) と同じ。
- PE の作り方: `gui_app.c`・`gui_app_ff.c`・`gui_nc_app.c` は `lift/gui_lift.sh` (WndProc 指定無し・自動検出)。`pe_image_app.c` は `test/pe_image_e2e.sh` と同じ mingw 行 (`-Wl,--dynamicbase`)。
- 判定: 4 PE 全てで base と head の `lifted.c` は**バイト一致**。wasm 経路 (`gui_wasm.sh`) が受ける `lifted.c` も変わらない。4 PE の retdec.c には `(*gN)(` 形の関数ポインタ大域も `(T (*)(...))(int64_t)` のキャストも無く、変更した 2 分岐は通らない。

| PE | retdec.c (B) | sha256 (base 後処理) | sha256 (head 後処理) | 判定 |
|---|---|---|---|---|
| `gui_app.c` | 24537 | `2bf479fe686fc05e95ef64af1414df7ec7577f2c6f8adb77fb00515e14bbef62` | `2bf479fe686fc05e95ef64af1414df7ec7577f2c6f8adb77fb00515e14bbef62` | 一致 |
| `gui_app_ff.c` | 5501 | `09f88d1417f147ef350159bc5d4e413174bfc8d61e337307df214c186799b4a4` | `09f88d1417f147ef350159bc5d4e413174bfc8d61e337307df214c186799b4a4` | 一致 |
| `gui_nc_app.c` | 11262 | `a473260e28bdefa2767a1d6a1d949de78aed70c0f92e0e4d33fe5ce065c38e9c` | `a473260e28bdefa2767a1d6a1d949de78aed70c0f92e0e4d33fe5ce065c38e9c` | 一致 |
| `pe_image_app.c` | 1871 | `e79071048ffb033bf0d54a4be1cfa3c1f29e73e1c2cf0a2356ea80c59528d481` | `e79071048ffb033bf0d54a4be1cfa3c1f29e73e1c2cf0a2356ea80c59528d481` | 一致 |

- 差が出た PE は W 版ゲスト `gui_app_w.c` の 1 つだけ (意図した変更)。差分は 6 行 (`#define g39` の追加と `g39 = ...` の 1 行)。base の `lifted.c` は `g39` が未宣言で gcc が 2 箇所でエラーになる (`error: 'g39' undeclared`)。head は 0 エラー。
- gate (差が出た PE の検証): `bash tools/gui/test/native_w_e2e.sh` を head で実行。lift は rc 0 で、native 実行は `SEGV on unknown address 0x0000400011f8` の rc=1。変更前の記録 (本付録の上の節) と同じ既知の欠陥 (関数 VA の 32 bit 切り詰め・子 #3508) で、変更の影響ではない。
- 測定の証跡 (`git diff --stat 0705571e4 f6a2619f3 -- tools/gui`。付録に置く: REPORT.md は 250 行上限のため):
```
 tools/gui/REPORT.md            |  3 +++
 tools/gui/REPORT_APPENDIX_W.md | 34 ++++++++++++++++++++++++++++++++++
 2 files changed, 37 insertions(+)
```

## #3508 [WIN-30]: 関数 VA の切り詰め修正・独立オラクル (測定 commit `51a6881f7`)

上の「発見」「範囲外・未達」の表のうち、関数 VA 切り詰め (WIN-30) と W 版の画素比較は本節で解消した。wasm / Chrome は子 #3509 (WIN-31)、GUI-REACH と `e2e.sh` 組込みは子 #3510 (WIN-32)。

### 結論
- 受入 1: 関数 VA の 32 bit 切り詰めを後処理で直した。`bash tools/gui/test/native_w_e2e.sh` が PASS (3 回とも)。
- 受入 2: 最終フレームを `golden/gen_golden_w.py` と比較し EXACT MATCH (0/64,000 px)。オラクルはゲストの描画規約だけから計算し、フォントは `src/gui_font8x8.h` だけを共有する。ネガコン 2 種は下表。
- 受入 3: 窓・メッセージ系は W 版だけを呼ぶ。`build/lift_w/lifted.c` の API 呼出しに `*A(` は 0 件。
- 受入 4: 欠陥は RetDec 側。DEFECTS.md 形式の行案は下 (直接編集せず、PM 判断)。
- 受入 5: 既存の `native_e2e.sh` (gui_app.c) は EXACT MATCH のまま。

### 原因と修正
1. **関数 VA の切り詰め (RetDec 側)**: `share/retdec/support/generic/types/windows.json` は `LONG_PTR` (型 ID 12922) を `long` (型 ID 15827・32 bit) と定義している。そのため `SetWindowLongPtrW` の第 3 引数が `i32` の IR になり (`call i32 @SetWindowLongPtrW(i64* %2, i32 -4, i32 1073746424)`)、関数 VA 即値 `0x400011f8` の上位 32 bit が欠ける。`retdec.config.json` の `parameters` を `i64` に書き換えても出力は `int32_t` のままだったため、ツール側の上書きは使わなかった。
   修正: `gui_lift_post.py` の `fix_fn_va`。引数位置の 8 桁即値が、fnmap の関数 VA の下位 32 bit と一致する場合だけ完全 VA へ戻す (`0x400011f8` → `0x1400011f8`)。どの関数 VA とも一致しない即値には触らない。`[post] restored truncated function VA: 1 (0x1400011f8)` を出す。限界: 8 桁の整数定数が偶然 fnmap の下位 32 bit と一致すると、その即値も完全 VA へ書き換わる (silent)。現状の検出は W guest で 1 件・4 PE で 0 件のみ。
2. **W 文字列の幅 (RetDec 側)**: RetDec は W 文字列を `L"..."` で出す。Linux / wasm では `wchar_t` が 4 byte なので、UTF-16 を読む shim の `OutputDebugStringW` が 1 文字目で止まり `[gui] w` だけになった。
   修正: `gui_lift_post.py` の `fix_wstr`。`L"` を `u"` (char16_t, 2 byte) へ置き換える。狭義の `"..."` と `'...'` は素通しする (`"Ctrl+L"` の末尾 L は変えない)。
3. **ゲストの順序 (ゲスト側の不具合)**: `gui_app_w.c` は `ltext` へ文字を入れる前に `UpdateWindow` を呼んでいた。`UpdateWindow` は WM_PAINT を同期で送るので、最初の描画は NUL 12 個を描き、テキストが出なかった。文字の代入を `ShowWindow` の前へ移した。
4. **harness の穴**: 修正前、`native_w_run` は FAIL 行を出した後も rc 0 で終わった。ゲストの `ExitProcess` が先に走るため。`native_w_e2e.sh` は `PASS` 行を必須にし、オラクル比較も行う。

### 検証 (測定 commit `51a6881f7`・4 vCPU・load 0.32〜0.55・同一 run 内の再測定)
| 項目 | 結果 | 数え方・条件 |
|---|---|---|
| `bash tools/gui/test/native_w_e2e.sh` ×3 | rc 0・PASS ×3・8.37 / 8.36 / 8.37 s | `native_w_run` の `PASS` 行 + オラクル EXACT MATCH |
| 最終フレーム | `w=320 h=200 bg=182838 nonbg=12625 colors=6403 sha256=6f809bdf4f348903edba334442193a0290cc537721191aaf71088c2eea596bc6` | `native_w_run` の surface 行 (RGB 3 バイト列の sha256) |
| オラクル比較 `golden/gen_golden_w.py compare` | EXACT MATCH (0/64,000 px) rc 0 | `build/w_actual.ppm` と期待画像の画素比較 |
| ネガコン 1: 期待画像を 1 画素改竄 | MISMATCH (1/64,000 px) rc 1 | `compare --tamper`。`native_w_e2e.sh` が rc 1 を要求 |
| ネガコン 2: shim の欠陥 | MISMATCH (290/64,000 px) rc 1 | 作業コピー (`$RUNNER_TEMP`) の `tch()` の wide 添字を `[i + 1]` にずらした。リポジトリは変更せず |
| `bash tools/gui/test/native_e2e.sh` (gui_app.c) | EXACT MATCH (0/64,000 px) rc 0・8.36 s | 既存の回帰 |
| W 版ゲストの API 呼出し | `CreateWindowExW` `RegisterClassW` `PeekMessageW` `DispatchMessageW` `DefWindowProcW` ほか W 接尾辞のみ。`*A(` は 0 件 | `grep -oE '\b[A-Za-z]+A\(' build/lift_w/lifted.c` |
| 既存 PE への影響 | `gui_app.c` `gui_app_ff.c` `gui_nc_app.c` `pe_image_app.c` の 4 PE で、`origin/main` の `gui_lift_post.py` と本 PR の `lifted.c` は sha256 一致 (差 0)。`L"` も `u"` も 0 件、復元 VA 0 件 | 同じ `retdec.c` に両版の後処理を適用して比較 |

測定に使った RetDec は素材 `toolchain-retdec` (v5.0・commit `53e55b4b`) を `$RUNNER_TEMP` に展開したもの。[RETDEC] (`docs/REFERENCES.md`) の版と一致。

### RetDec 欠陥の行案 (`docs/DEFECTS.md` 形式・直接編集は PM 判断)
| ID | 担当 | 区分 | 症状 | 原因 | 検出信号 | 検出器 | 修復 |
|---|---|---|---|---|---|---|---|
| 新規類型 (仮・番号は PM 割当) | RetDec (Win32 型 DB) | 新規 (#3508 発見) | `LONG_PTR` 引数が 32 bit 扱いになり、関数 VA 即値の上位 32 bit が欠ける。native で SEGV (silent な 1 bit 欠け) | `share/retdec/support/generic/types/windows.json` の `LONG_PTR` → `long` (15827) | `SetWindowLongPtrW(h, -4, 0x400011f8)` (正 `0x1400011f8`)。ASan SEGV at `0x0000400011f8` | `lifted.c` の引数位置の 8 桁即値が fnmap の下位 32 bit と一致 | `gui_lift_post.py` `fix_fn_va` (fnmap 一致時のみ完全 VA へ) |
| 新規類型 (仮・番号は PM 割当) | RetDec (文字列) × Linux/wasm の wchar_t | 新規 (#3508 発見) | W 文字列 `L"..."` が wchar_t (4 B) で出るため、UTF-16 を読む W API が 1 文字目で切れる (silent) | RetDec が W 文字列を `L"..."` で出力 | `OutputDebugStringW` の出力が `[gui] w` (1 文字) | `lifted.c` の `L"` の出現 | `gui_lift_post.py` `fix_wstr` (`u"`) |

D11 (wasm32 の PE VA 切り捨て) とは機構が違うため、D11 の変種にはしていない。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| wasm / Chrome の OffscreenCanvas 読み戻しと native の sha256 一致 (受入の範囲外) | `gui_lift_post.py` の変更の wasm 経路 (`gui_wasm.sh`) は未実行 (emsdk 素材未取得) | #3509 [WIN-31] |
| GUI-REACH の順序検査と `tools/gui/e2e.sh` への組込み (範囲外) | trace の機械検査は未実施 | #3510 [WIN-32] |
| RetDec 欠陥の新規類型 2 件 (番号は PM 割当) の DEFECTS.md への登録 | 行案のみで、表には未登録 | PM 判断 (本 PR では編集しない) |

### レビュー round 1 への対応 (修正 commit `74942e399`・再測定は round 2 節)
- 修正: `fix_wstr` は狭義の `"..."` と `'...'` を素通しし、`L"..."` だけを `u"..."` にする。改竄ネガコンは `MISMATCH` 行の grep で判定する (Python 例外の rc 1 でも通らない)。
- 測定鮮度: 測定 commit は `51a6881f7` のまま。以後のコード差分は下の 2 ファイル 6 行で、WORKFLOW §6 により再測定が要る (round 2 節で再測定済み)。
```
git diff 51a6881f7 74942e399 -- tools/gui/lift tools/gui/test tools/gui/golden tools/gui/src
```
```diff
-        return re.sub(r'(?<!\w)L"', 'u"', s)
+        return re.sub(r"""(?<!\w)L"((?:[^"\\\n]|\\.)*)"|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'""",
+                      lambda m: 'u"%s"' % m.group(1) if m.group(1) is not None else m.group(0), s)
-if python3 "$ROOT/golden/gen_golden_w.py" compare "$BUILD/w_actual.ppm" --tamper; then echo "[native_w_e2e] FAIL: ネガコン (改竄オラクル) が不一致にならなかった" >&2; exit 1; fi
+tamper_log="$(python3 "$ROOT/golden/gen_golden_w.py" compare "$BUILD/w_actual.ppm" --tamper || true)"
+echo "$tamper_log"
+grep -q '^\[golden_w\] MISMATCH' <<< "$tamper_log" || { echo "[native_w_e2e] FAIL: ネガコン (改竄オラクル) が MISMATCH を出さなかった (例外・終了コードだけでは判定しない)" >&2; exit 1; }
```
- 狭義リテラルの検査 (`gui_lift_post.py` の `fix_wstr` を AST で取り出して照合・9/9 一致): `SetText("Ctrl+L");`→不変 / `SetText(L"Wide");`→`u"Wide"` / `x = L"";`→`u""` / `p = "a\"L\"b";`→不変 / `c = '"'; SetText(L"x");`→`u"x"` / `c = '"'; y = "Ctrl+L" ; z = "x";`→不変 / `foo(L"A", "B+L", L"C");`→`u"A"`・`"B+L"`不変・`u"C"` / `c = '\'';  y = L"ok";`→`u"ok"` / `wcscpy(p, L"x\n");`→`u"x\n"`。reviewer 案 (文字リテラルの選言肢なし) は `'"'; y = "Ctrl+L" ; z = "x";` を `"Ctrl+u"` に壊すため、`'...'` の選言肢を足した。
- ネガコンの判定: 期待画像 (`oracle()` の出力) を PPM にした偽 `w_actual.ppm` で、`native_w_e2e.sh` の比較部と同じ行を実行。実 PPM は `EXACT MATCH (0)` → `[tamper]` は `MISMATCH (1 px)`。ネガコン側だけ例外を出す偽スクリプトでは FAIL (rc 1) になる。旧判定 (`if ... --tamper; then FAIL; fi`) は rc 1 のとき何も出さず通る。
- 再測定: 完了 (下の round 2 節)。

### レビュー round 2 への対応: 再測定 (測定 commit `6db8b1fe8`)

- 測定 commit は `6db8b1fe8` (測定時の HEAD)。`tools/gui/{lift,test,golden,src}` のコードは `74942e399` から変えていない (`git diff 74942e399 6db8b1fe8 -- tools/gui/lift tools/gui/test tools/gui/golden tools/gui/src` の出力 0 行)。
- 素材: `$ARTIFACTS_DIR` に `toolchain-retdec.tar.zst` が実在。RetDec は [RETDEC] (v5.0・commit `53e55b4b`) を使った。素材の展開先と [RETDEC] の同一性は `[未確認]`。mingw は apt-mingw の `x86_64-w64-mingw32-gcc` (GCC 13)。`native_w_e2e.sh` は `fl-win64` を使わない。
- 測定環境: 4 vCPU・load 0.22〜0.36 (測定開始時)。

| 項目 | 結果 | 数え方・条件 |
|---|---|---|
| `bash tools/gui/test/native_w_e2e.sh` ×3 | rc 0 ×3・`PASS` 行 3/3・11 s / 7.41 s / 7.17 s | 1 回目は build の冷えた状態 |
| 最終フレーム (3 回とも同一) | `w=320 h=200 bg=182838 nonbg=12625 colors=6403 sha256=6f809bdf…` | `native_w_run` の surface 行 |
| オラクル比較 | EXACT MATCH (0/64,000 px) 3/3 | `golden/gen_golden_w.py compare` |
| ネガコン 1 (期待画像 1 px 改竄) | MISMATCH (1/64,000 px) 3/3 | `native_w_e2e.sh` は MISMATCH 行の grep で判定 |
| ネガコン 2 (shim の欠陥: `gui_gdi.c` の `tch()` の wide 添字を `[i + 1]`) | rc 1・MISMATCH (290/64,000 px)・7 s | `git archive HEAD tools/gui` の作業コピー (`$RUNNER_TEMP`) で改変。リポジトリは変更せず。`51a6881f7` と同じ 290 px |
| `bash tools/gui/test/native_e2e.sh` (gui_app.c) | rc 0・PASS 行・EXACT MATCH (0/64,000 px)・7.12 s | 既存の回帰 |
| 4 PE の後処理 | head・`origin/main` (`89e0631e9`)・`51a6881f7` の 3 版で `lifted.c` が cmp 一致 (差 0)。`L"` 0 件・復元 VA 0 件 | 同じ `retdec.c` に 3 版を適用。各版の `tools/gui/lift`・`tools/gui/integ` は `git archive` で展開 |
| W guest の後処理 | head と `51a6881f7` の後処理が cmp 一致 (差 0)。`L"` 0 件・`u"` 14 件・`*A(` 0 件 | 同じ `retdec.c`・`--wndproc WndProc --wndproc SubWndProc` |

`origin/main` の `gui_lift_post.py` は #3460 の版で、#3508 の 2 修正 (`fix_fn_va`・`fix_wstr`) を持たない。4 PE では両修正が発火しないため、3 版の出力は同一になる。

`lifted.c` の sha256 (4 PE は head・`origin/main`・`51a6881f7` で同一、W は head と `51a6881f7` で同一):

| ゲスト | sha256 |
|---|---|
| gui_app | `2bf479fe686fc05e95ef64af1414df7ec7577f2c6f8adb77fb00515e14bbef62` |
| gui_app_ff | `09f88d1417f147ef350159bc5d4e413174bfc8d61e337307df214c186799b4a4` |
| gui_nc_app | `a473260e28bdefa2767a1d6a1d949de78aed70c0f92e0e4d33fe5ce065c38e9c` |
| pe_image_app | `e79071048ffb033bf0d54a4be1cfa3c1f29e73e1c2cf0a2356ea80c59528d481` |
| gui_app_w (W 版) | `3233c6f7e79b04a2039d462f48253d753b428fcea8a5867ee047d31a90bf74f5` |

差分の証跡: `git diff 6db8b1fe8 HEAD -- tools/gui/lift tools/gui/test tools/gui/golden tools/gui/src` は 0 行 (本節を入れた commit は文書のみ)。

限界 (round 1 m1): `fix_wstr` は、コメント内の閉じていない `"` (例: `/* say "hi */ x = L"y"; */`) を文字列の開始と見なし、同じ行の後続の `L"..."` を変換しない。測定した 5 本の `retdec.c` (W 1 本・4 PE) のコメント行に `"` は 0 件 (`grep -cE '(//|/\*).*"'`)。現行の入力では発火しない。
