# Kilohearts REPORT 付録 (分割移動)

> 本付録は `tools/targets/kilohearts/REPORT.md` §10-7b・§10-7c の全文を、250 行上限のため分割移動したもの。内容は削除していない。

### 10-7b・10-7c (#556 2 回目・3 回目 run)

#### 10-7b. #556 2 回目 run (Resonator の emcc 再現・callee 追加 decompile)
- 素材: `plugins-kilohearts` の Windows Installer zip のみ展開 (`extract_installer.sh` は dmg を必須とするため HeartCore 抽出を手で再現)。Ghidra 12.1.4 は GitHub release から再取得 (sha256 一致)。`pefile`・`capstone` は pip 導入。
- Resonator 7 関数 (修復なし) → `ghidra_to_c.py` → emcc: **失敗を再現** (`resonator.c` 21 件)。内訳: 128bit レーン `_8_8_`/`_4_12_`/`_0_8_` (V128 未定義)、`ushort` 型未定義、`rcpps` 未実装、`func_0x…` 形式の未解決 callee。
- callee 5 関数 (`0x180fd62dc` `0x180fd6320` `0x180fb6ce0` `0x180fd648c` `0x180fbdef4`) を追加 decompile: 計 12 件 OK。ただし Ghidra 出力の `func_0x…` は未関数化アドレスのため、emcc の未解決は残る。
- shim に `ushort` を追加 (機械的な型定義のみ)。128bit レーンと `rcpps` は未対応。
- 突合・ablation・ネガコンは未実施。Stereo / Delay は未着手。

#### 10-7c. #556 3 回目 run (callee 6 関数を converter の `also` に追加 = also 計 12 件)
- 素材: `plugins-kilohearts` の Windows Installer zip → payload.dat → windows.zip → HeartCore.core_64 を手で展開 (dmg 不要)。Ghidra 12.1.4 = GitHub release, sha256 `ddac49f9…d2db` 一致。emsdk 6.0.12 は [EMSDK] で動作。
- Ghidra 再 decompile: 13 関数 (Resonator + callee 12) すべて OK。import 込み 17.8 s (n=1)。
- `ghidra_to_c.py` の `resonator.also` は既存 6 件 (`0x180fbc1f4` `0x180fbbfb8` `0x180fbdfcc` `0x180fbe018` `0x180fcf904` `0x180fd54cc`) に、本 PR で 6 件 (`0x180fd62dc` `0x180fd6320` `0x180fb6ce0` `0x180fd648c` `0x180fbdef4` `0x180fe5dfc`) を追加し、計 12 件 (commit 本 PR)。emcc は **依然失敗** (`-ferror-limit` 20 件で打ち切り)。
- 件数の注意: 10-7b の記録は `resonator.c` 21 件、本 run は 20 件で打ち切りのため、件数は同一基準の比較ではない。件数の増減は退行ではなく、callee を足したことで未解決 callee が見えた切り分けの進展と解釈するが、前 run と同一基準での再計測は未実施。
- 起票先: Resonator の emcc 残件 → #1215 [KH-23] / Stereo・Delay の実ビルド・突合 → #1216 [KH-24]。
- 残る未解決 (emcc 出力): (a) V128 lane `_8_8_`/`_4_12_`/`_0_8_`、(b) `rcpps` 未実装 (`gen_simd.py` の `kh_rcp_exact` 系を移植すれば入る見込み。未検証)、(c) 引数なし呼出の `param_1` 不足、(d) 推移的な未関数化 callee `0x180fd6498`・`0x180fd662c`・`0x180fe5f40`・`0x180fd3144`、(e) `UNK_182280000` 未定義。
- 突合・ablation・ネガコンは本 run でも未実施。Stereo / Delay は未着手。
