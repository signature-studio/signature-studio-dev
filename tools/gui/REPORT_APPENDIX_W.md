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
