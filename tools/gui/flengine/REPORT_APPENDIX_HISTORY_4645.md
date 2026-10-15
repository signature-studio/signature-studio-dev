# REPORT 付録 — 旧 HEAD の実測 (REPORT §6 から分割移動。#4645 PR)

以下は REPORT.md の「### 旧 HEAD の実測 (参考)」節の全文 (内容は削除していない)。現 HEAD の値ではない。

### 旧 HEAD の実測 (参考・現 HEAD の値ではない)

以下の表と箇条書きは旧 HEAD `a927ac87` と `de8d603e` 時点の実測。現 HEAD の実測は上の表を正とする。
前提: 素材 `fl-win64` ([WIN64] = `$ANALYSIS_DIR/win64` に展開)、`work-m11` (`tools/m11/work/` に展開。e2e は読取のみで、複製 `tools/gui/work/flengine/snap/` 側で使う)、`toolchain-emsdk` ([EMSDK])、`toolchain-retdec` ([RETDEC])、`apt-mingw` (`x86_64-w64-mingw32-gcc`)、Python の pefile・capstone (runner の system python は PEP 668 で pip 不可のため venv を作って PATH の先頭に置いた)。`m11_gen_ir2.sh` を素材の `tools/m11/work/` で 1 回実行して `ir_conditions.json` の `ldfix=applied` を作った。

以下の表は main 取込み前の HEAD `a927ac87` の実測 (参考)。現 HEAD `de8d603e` の実測は上の箇条書きを正とする。

| 回 | rc | 所要 (e2e.sh の done) | load 開始 → 終了 | judge | native selftest (`tools/gui/test`) | pe_image parity / e2e | ネガコン |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 211 s | 1.13 1.02 0.60 (終了時) | 12/12 PASS | 433 passed / 0 failed | P1 LB=0・LB=0x10000 PASS、N1〜N3 PASS / pe_image P1・P2・N1・N2 PASS | 5/5 期待どおり FAIL |
| 2 | 0 | 212 s | 1.06 1.02 0.70 (終了時) | 12/12 PASS | 433 passed / 0 failed | 同上 | 5/5 期待どおり FAIL |
| 3 | 0 | 212 s | 1.02 1.01 0.77 (終了時) | 12/12 PASS | 433 passed / 0 failed | 同上 | 5/5 期待どおり FAIL |

- 3 回の一致: B1 `units_run 52 (base 52)` / `threw memory access out of bounds (base 同じ)`、L1 undefined/sigmismatch/duplicate `0/0/0`、A1 `177 = 177 (impl 159 / stub 18)`、S1 `871/1/47/23/0 (base 871/1/47/23/0)`、S2 `LoadImageW` のみ fail-fast (ff 1 unit) = soft STUB、R1 first `LoadStringW` (calls=3)、R2 reached 32 (floor 19)、P1 atoms `[-16383, -16382]` / `RegisterClassW=2 CreateWindowExW=3`、P4 hwnd `0x210000e`。
- parity (`pe_image_parity.py --pe block00031_PE.bin`): `.data` 補正 10,284 件 = m11 `m11_data_gen.py` の 10,284 件 (LB=0 / LB=0x10000 とも一致)。PR 側の旧 off-by-one (`<`) は `c39ca16` で `<=` に直済み (レビュー必須 1)。DIR64 末尾 slot 境界の是正 (#3832) の before/after は [REPORT_APPENDIX_3832.md](REPORT_APPENDIX_3832.md)。
- 所要は 211–212 s (e2e.sh の done 行)。
- IR provenance (`results/ir_sha256.txt`): 今回は素材の `boot_final.ll` を `m11_gen_ir2.sh` で作り直した (ldfix=applied)。material `boot_final.ll` = `995351f5…` (旧記録 `69c774de…` は素材そのままの IR の指紋)。`boot_final3.ll` は `010451ad…` (不変)。`m11_build.sh` 後は `boot_final.ll` `2be93e55…`・`boot_final3.ll` `ac64ad01…`。
- 親 `bash tools/gui/e2e.sh` (受入条件 2): **ALL PASS / rc 0** (HEAD `de8d603e`、1 回・wall 194 s、load 2.37 1.69 1.31 (終了時))。前提 `tools/e2e` の `npm ci` (rc 0)・`pnpm install --frozen-lockfile` (rc 0) を先に実行。初回 run は前提不足 (`tsc`・`agent-browser` 不在) で落ちたため、前提を入れてから再実行した。
- HEAD `de8d603e` (main `6aa4b397` 取込後) の flengine e2e (n=3): rc 0 / 0 / 0、所要 **215 / 219 / 219 s** (done 行)、judge 12/12 PASS ×3、native selftest 500 passed / 0 failed (main の追加テスト込み)、ネガコン N1〜N5 期待どおり FAIL ×3。
- `results/probe.json` の `gui_shared_ptr` は実行ごとに変わる値 (ヒープ位置。3 回目の実行の値を残した)。判定は `gui_shared_ptr_ge_0x10000` (範囲チェック) なので PASS には影響しない。
- `results/*.json` と `IMPORTS.md` は今回の 3 回目の run で再生成。`IMPORTS.md` は `CharLowerW`・`CreatePalette`・`EnumFontFamiliesExW`・`MessageBoxA` が「P2/P3 昇格候補」から外れた (実装済みのため)。

ネガティブコントロール (全て「期待した FAIL 行が出る」まで検査。judge のクラッシュを FAIL 確認と誤認しない。run1 で確認):

| NC | 壊し方 | 結果 |
|---|---|---|
| N1 | 到達ログ無し (`--plain`) ビルドの起動を判定 | R1 FAIL, exit 1 |
| N2 | baseline の units_run 期待値を 23 に | B1 FAIL, exit 1 |
| N3 | 到達 floor に未到達 API `NoSuchGuiApi` を 1 つ追加 | R2 FAIL (floor 20 / reached 32), exit 1 |
| N4 | survey の 1 unit を ok→trap に改竄 | S1 FAIL, exit 1 |
| N5 | `GetDC(NULL)` を元の fail-fast に戻した shim で native selftest | `FAIL-FAST: unimplemented Win32 API: GetDC`, exit 134 |

- 範囲外: 実ブラウザ・Canvas 描画、audio、UI スレッドのスタック量、`gui_reach` の性能影響 (INTEGRATION §4-12 の未計測は継続)。
