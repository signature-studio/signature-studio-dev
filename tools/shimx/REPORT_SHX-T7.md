# REPORT (SHX-T7 / #173) — 署名正規化 IR pass + ゲート

> 正本: `tools/shimx/REPORT.md` §16 から分割移動した付録 (内容は無変更)。親: `tools/shimx/REPORT.md`。
> § 番号は親 `REPORT.md` のもの (本付録内の「§4」「§13」「§14」は親の節を指す)。

## 16. 署名正規化 IR pass + ゲート (#173, SHX-T7)

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1〜D16 は命令レベルの miscompile。本件は declare 署名の揺れによる wasm-ld mismatch → 実行時 trap で、§4 項 4 の 5 件が実害例)。

**結論**: 案A (IR pass) + 案B (ゲート) を実装した。`sig_normalize.py` が lift IR の外部 declare を shimx 定義署名 (`data/sigs.json`) へ正規化し、`sig_gate.sh` が「正規化 → `verify_sig.sh` mismatch 0」を強制する (unresolved が 1 件でもあれば exit 1)。`test.sh` 6b は実 IR をこのゲート経由で検査し、合成 fixture の回帰 `test/sig/sig_test.sh` を追加した。実 IR (M11 / OTT) での実測は下の「レビュー対応後の再検証」。

- 方式: 署名が wasm スロット粒度 (i1/i8/i16/i32/ptr = i32, i64, float, double) で異なる declare `@N` に対し、IR 側署名の adapter `@__shx_sig_N` を IR 末尾に定義して基名を shimx 署名で呼び、`@N` の全参照 (call・関数ポインタ) を adapter へ向ける。呼出 site の命令は書換えない。`NAME.1` / `NAME_D1` 形式の重複 declare も同じ経路で基名へ統合する。変換は 整数の縮小 (trunc) / i1 の拡張 / 整数↔ptr / float↔double、余る引数は捨て・足りない引数は 0。**i8 以上の整数を広い整数へ拡張する場合は符号 (zext/sext) が型から決まらないため既定で `unresolved`** (zext 固定だと `lstrcmpA` の -1 が 4294967295、`SetFilePointerEx` の負のシーク距離が巨大な正値に黙って化け、gate は mismatch 0 で通ってしまう)。拡張は `data/sig_ext.json` に API・スロット (`p<i>` / `ret`) 単位で `zext` / `sext` を根拠付きで明示したものだけ許可する。float↔整数・構造体・vector・可変長も `unresolved`。`c"..."` 文字列定数と `;` コメント内の `@NAME` は置換しない。
- `data/sigs.json`: `src/*.c` を `emcc -S -emit-llvm` して外部リンケージの `define` から生成 (731 関数。main の SEH ランタイム #171 取込で `shimx_seh_*` 6 関数が増え 725 から再生成)。`gen_sigs.py --check` が shimx 側署名変更の取りこぼしを検出し、`sig_gate.sh` が毎回実行する。
- 再現: `bash tools/shimx/test/sig/sig_test.sh` / `bash tools/shimx/scripts/sig_gate.sh <ir.ll> <tag>` (どちらも冒頭で `EMSDK_ENV` (既定 `/opt/emsdk/emsdk_env.sh`) を source するため、`emcc` が PATH に無い素のシェルで動く)。

| 検証 (2026-10-13, Actions runner, 検証起点は PR HEAD) | 結果 |
|---|---|
| `test/sig/sig_test.sh` (load average 0.10, 1 run) | **ALL PASS**, 10 s |
| (a) 陰性対照: 合成 fixture (§4 項 4 の 5 件の逆向き揺れ) を正規化せず `verify_sig.sh` | mismatch **5** 検出 |
| (b) 正規化後 | 5 adapter + 重複統合 1 → mismatch **0** |
| (c) adapter 経由の実行 (node) | `midiOutShortMsg` が 5 (MMSYSERR_INVALHANDLE)、`acmMetrics` が out に 0 を書く = shimx 定義まで届く |
| (d) 未対応型 (float 引数) | `UNRESOLVED` で `sig_gate.sh` exit 1 |
| (e) `sigs.json` の acmMetrics 第1引数を i64→i32 に壊す | `gen_sigs.py --check` exit 1 |
| `bash tools/shimx/test.sh --quick` (load average 0.19) | **exit 0**, 26 s (MT 5 グループ / ST PASS / fail-fast 8 / M4 互換 PASS / 未実装 0) |
| GUI declare fixture (`tools/gui/integ/fixtures/boot_final_gui_declares.ll`) | adapter 0 (wasm スロットで既に一致。偽陽性なし) |

- 検証範囲外: M11 closure (`boot_final2/3.ll`)・OTT (`ott_m8.ll`) と各プラグイン lift 成果物での実測。`work-m11` / `work-m6-ott` 素材が無く、`test.sh` 6b は SKIP。

**main 取込後の再検証 (2026-10-13, Actions runner, 検証起点 = merge commit f6379b3 を detached worktree に展開, 各 n=3)**: §14 (SEH, #171) と本節の両方を含む HEAD で実行。

| 検証 | 結果 |
|---|---|
| `test/sig/sig_test.sh` | 3 run とも exit 0 (ALL PASS), 11.9–12.7 s, load average (1 分値, run 開始前〜終了後) 0.34–0.63 |
| `test.sh --quick` | 3 run とも exit 0, 33.3–33.7 s, load average (1 分値, run 開始前〜終了後) 0.58–1.09。MT 6 グループ PASS (`seh` 含む) / ST PASS / fail-fast 10 モード (`sehnomatch` `sehbadtarget` 含む) / M4 互換 PASS / 公開関数 680 / sig_test 内蔵 ALL PASS |
| 陰性対照: merge 前の `sigs.json` (725 関数) を HEAD のソースに対して `gen_sigs.py --check` | exit 1 (main の `seh.c` が増やした `shimx_seh_*` 6 関数を検出)。再生成後 (731 関数) は exit 0 |

- `test.sh` が再生成した inventory.md / BACKLOG.md / coverage.json / inventory.csv / exports.txt は m11 closure 不在で内容が変わるため、§13 と同様にコミットしていない。


**レビュー対応後の再検証 (2026-10-13, Actions runner, コード = commit 866caec。素材 work-m11 / work-m6-ott 展開済み)**: oc-reviewer / Copilot の指摘 (整数拡張が zext 固定、`sig_gate.sh` / `sig_test.sh` が emsdk 未有効化) を修正。`emcc` が PATH に無い素のシェル (`env -u EMSDK`) で実行。

| 検証 | 結果 |
|---|---|
| `test/sig/sig_test.sh` (n=3) | 3 run とも exit 0 (ALL PASS), 19.3 / 19.3 / 19.3 s, load average (1 分値, 開始前→終了後) 0.62→0.81 / 0.81→0.85 / 0.85→0.90。(f) 符号不明の拡張 2 件 (`lstrcmpA` 戻り i32→i64、`SetFilePointerEx` 引数 i32→i64) が `UNRESOLVED` exit 1、(g) `sext` 明示時 `lstrcmpA("a","b")` が **-1** のまま届く (zext 固定だった修正前は 4 294 967 295、レビュアー再現値)、(h) 文字列定数・`;` コメント内 `@NAME` は不変 |
| 実 IR `tools/m11/work/boot_final2.ll` (`sig_gate.sh`, 11.3 s) | 正規化前 mismatch 0 / adapter 0 / 重複統合 1 (`SHGetFolderPathW.1`) / unresolved 0 / 正規化後 mismatch **0** |
| 実 IR `tools/m11/work/boot_final3.ll` (12.5 s) | adapter 0 / 重複統合 1 (`SHGetFolderPathW_D1`) / unresolved 0 / mismatch **0** |
| 実 IR `tools/m8/work/ott_m8.ll` (5.5 s) | adapter 0 / 重複統合 0 / unresolved 0 / mismatch **0** |
| `test.sh --quick` (実 IR あり、6b は SKIP でない, 76.0 s, load average 終了後 0.92) | exit 0, 7/7 完了 (MT / ST / M4 互換 / fail-fast 全 PASS, 公開関数 680) |

- 実 IR で `SHGetFolderPathW.1` / `_D1` は戻り値 `i64` で declare され、shimx 定義は `HRESULT` (`i32`)。新方針ではこの戻り拡張が unresolved になるため、`data/sig_ext.json` に `SHGetFolderPathW` ret = `sext` を根拠付きで登録した (呼び元 `function_81bca0` は `trunc i64 → i32` 後に 0 比較のみで、拡張の符号は結果に影響しない)。
- `retdec_drift.ll` の `GetComputerNameExW` (enum i32→i64 / BOOL ret i32→i64 拡張) と `GetFileAttributesExW` (enum) は fixture を変えず、`sig_ext.json` で非負 enum / BOOL として `zext` を明示して mismatch 0 を維持。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 IR のうち M11 closure (`boot_final2/3.ll`) と OTT (`ott_m8.ll`) は実測済み (下記)。FreshAir / Serum2 / MassiveX / Kilohearts 等の各プラグイン lift 成果物は未実測 | 受入条件「lift 成果物で mismatch 0」の残り範囲 | #173 (`work-liftlib-targets` ほか素材を指定して再実行) |
| GitHub Actions に `test.sh` を常時回す job が無い (現状の workflow は opencode のみ) | 案B の「CI で常時」は test.sh 経由 (手動 / レビュー run) に留まる | #284 系 `[CI-n]` に提案 (要 素材取得 + emsdk 展開を含む job) |
| adapter 経由になるため RetDec 側が i64 で渡す HANDLE の上位 32bit は落ちる (trunc) | 実 IR (M11 / OTT) の adapter は 0 件のため該当なし。他プラグインで adapter が出た時に `normalized` 一覧で確認 | #173 |
| `data/sig_ext.json` の拡張方針は 3 API 分を手で書いた (`GetComputerNameExW` / `GetFileAttributesExW` = 非負 enum・BOOL の zext、`SHGetFolderPathW` ret = HRESULT の sext)。新しい API で adapter が必要になるたび符号の根拠を人が判断して追記する | 既定は unresolved (fail-loud) なので silent miscompile にはならないが、追記は手作業 | #173 |
