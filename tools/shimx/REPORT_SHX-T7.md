# REPORT (SHX-T7 / #173) — 署名正規化 IR pass + ゲート

> 正本: `tools/shimx/REPORT.md` §16 から分割移動した付録 (内容は無変更)。親: `tools/shimx/REPORT.md`。
> § 番号は親 `REPORT.md` のもの (本付録内の「§4」「§13」「§14」は親の節を指す)。

## 16. 署名正規化 IR pass + ゲート (#173, SHX-T7)

既知類型との関係: 直接の既知類型は無し (`docs/DEFECTS.md` D1a〜D17 は命令・ABI・データ層の miscompile。本件は declare 署名の揺れによる wasm-ld mismatch → 実行時 trap で、§4 項 4 の 5 件が実害例)。ただし下記「未解決」の引数欠落 (M11 `function_593450`) は D5 (ABI 解析による引数喪失) / D7 (呼出規約による引数ずれ) と同族の疑いがあり、同一かは未確定。新規類型の行案は未解決表の直後に置いた。

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
| 実 IR `tools/m11/work/boot_final2.ll` (`sig_gate.sh`, 11.3 s) | 正規化前 mismatch 0 / **adapter 1** (`@__shx_sig_SHGetFolderPathW.1`。重複統合名の adapter。サマリ行の「正規化 N (adapter)」は重複統合分を含まない) / 重複統合 1 (`SHGetFolderPathW.1`) / unresolved 0 / 正規化後 mismatch **0** |
| 実 IR `tools/m11/work/boot_final3.ll` (12.5 s) | **adapter 1** (`@__shx_sig_SHGetFolderPathW_D1`。重複統合名の adapter) / 重複統合 1 (`SHGetFolderPathW_D1`) / unresolved 0 / mismatch **0** |
| 実 IR `tools/m8/work/ott_m8.ll` (5.5 s) | adapter 0 / 重複統合 0 / unresolved 0 / mismatch **0** |
| `test.sh --quick` (実 IR あり、6b は SKIP でない, 76.0 s, load average 終了後 0.92) | exit 0, 7/7 完了 (MT / ST / M4 互換 / fail-fast 全 PASS, 公開関数 680) |

- 実 IR で `SHGetFolderPathW.1` / `_D1` は戻り値 `i64` で declare され、shimx 定義は `HRESULT` (`i32`)。新方針ではこの戻り拡張が unresolved になるため、`data/sig_ext.json` に `SHGetFolderPathW` ret = `sext` を根拠付きで登録した (呼び元 `function_81bca0` は `trunc i64 → i32` 後に 0 比較のみで、拡張の符号は結果に影響しない)。
- `retdec_drift.ll` の `GetComputerNameExW` (enum i32→i64 / BOOL ret i32→i64 拡張) と `GetFileAttributesExW` (enum) は fixture を変えず、`sig_ext.json` で非負 enum / BOOL として `zext` を明示して mismatch 0 を維持。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 IR のうち M11 closure (`boot_final2/3.ll`) と OTT (`ott_m8.ll`) は実測済み (下記)。FreshAir / Serum2 / MassiveX / Kilohearts 等の各プラグイン lift 成果物は未実測 | 受入条件「lift 成果物で mismatch 0」の残り範囲 | #173 (`work-liftlib-targets` ほか素材を指定して再実行) |
| GitHub Actions に `test.sh` を常時回す job が無い (現状の workflow は opencode のみ) | 案B の「CI で常時」は test.sh 経由 (手動 / レビュー run) に留まる | #284 系 `[CI-n]` に提案 (要 素材取得 + emsdk 展開を含む job) |
| adapter 経由になるため RetDec 側が i64 で渡す HANDLE の上位 32bit は落ちる (trunc) | 実 IR で出た adapter は `SHGetFolderPathW.1` / `_D1` の 1 件ずつのみで、いずれも引数 0 個・戻り値 i64 (sext)。HANDLE 引数の trunc は実 IR では未発火。他プラグインで adapter が出た時は `normalized` / `dup_merged` 一覧で確認 | #173 |
| lift 側の引数欠落 (M11): `function_593450` は引数 0 個で lift されるが、呼出元 `function_81bca0` は boot_final2 で `function_593450(i32 0)` を渡し、boot_final3 では引数なしで呼ぶ。SHGetFolderPathW の 5 引数 (hwnd・csidl・hToken・flags・path) は IR に残っていない。正規化 adapter と R6 `--normalize-dup` は足りない引数を 0 / null で補完し、shimx は `csidl 0` / `path NULL` で `E_INVALIDARG` を返す。`function_81bca0` は戻り値 ≠ 0 として fallback `function_81bb20` へ分岐する。**silent** (`--emit-stubs` 経路の「名前を出して abort」は loud)。「従来のスタブと同等」は誤り | #173 (lift 欠陥。引数欠落の扱い = unresolved 化 / lift 側修正 / 許容 は PM 判断) |
| `data/sig_ext.json` の拡張方針は 3 API 分を手で書いた (`GetComputerNameExW` / `GetFileAttributesExW` = 非負 enum・BOOL の zext、`SHGetFolderPathW` ret = HRESULT の sext)。新しい API で adapter が必要になるたび符号の根拠を人が判断して追記する | 既定は unresolved (fail-loud) なので silent miscompile にはならないが、追記は手作業 | #173 |

**新規類型の行案 (DEFECTS.md 形式・PM 判断の入力。DEFECTS.md 本体は未編集)**:

| 項目 | 内容 |
|---|---|
| ID | D18 (案。既存 D1a〜D17 と非衝突) |
| 層 | fe (lift で引数が欠落) + ours (正規化の補完) |
| 新旧 | 新規 (M11 closure, #173 の実 IR 実測で発見) |
| 症状 (silent) | 呼出元が渡した引数の一部が declare / call から失われ、足りない引数を `0` / `null` で補うと、呼出先は想定外の入力で動く。M11 `function_593450` は引数 0 個で lift され、`function_81bca0` は boot_final2 で `(i32 0)` を渡す。shimx `SHGetFolderPathW` は csidl 0 / path NULL で `E_INVALIDARG` を返し、gate は mismatch 0 / unresolved 0 で通る |
| 根本原因 | (未確定) lift 時の呼出規約・引数回収の欠落。`sig_normalize.py` の「余る引数は捨て・足りない引数は 0」と、既存 R6 `ir_undef.py --normalize-dup` の同一方針が silent 化の入口 |
| 観測 (証拠) | `tools/m11/work/boot_final2.ll` / `boot_final3.ll` の `function_593450` と呼出元 (本節 SHX-T7 実測) |
| 検出信号 (機械的) | 外部 declare の引数個数が呼出 site の引数個数と一致しない (補完が発生した site) |
| 修復方針 (案・PM 判断) | (a) 補完を unresolved に変える (現在の fail-loud 既定と整合。実 IR の `test.sh` 6b は exit 1 になる) / (b) lift 側で引数を回復する (別起票) / (c) 許容して理由を残す。推奨は (a) |
| 既知との関係 | D5・D7 と同族の疑い (未確定)。命令レベルの D1a〜D4 とは別系統 |

`sig_normalize.py` の `DECL` 正規表現の未使用グループ `post`、`FLT` 定数は未使用のため本節の修正では削除していない (挙動に影響しない nit)。

**main 競合解消後の再検証 (2026-10-13, Actions runner, 検証起点 = コミット 3d75d44 (merge 629837b + sigs.json 再生成), n=1, 素材 work-m11 / work-m6-ott 展開済み, emcc 6.0.12 (`/opt/emsdk`))**: main の SHX-T8 (#175) を取り込んだ merge 直後は shimx 関数が増えて `sigs.json` が陳腐化していたため、再生成してから検証した。

| 検証 | 結果 |
|---|---|
| merge 直後 629837b の `test/sig/sig_test.sh` | **exit 1**: `gen_sigs.py --check` が不一致 (sigs.json は 731 関数のまま) → (b) FAIL。main 取込で増えた shim 関数を取りこぼしていた |
| `gen_sigs.py` 再生成 → 3d75d44 | 731 → **738 関数** (差分 +53 行・削除 0)。増えた 7 関数: `CryptReleaseContext` `QISearch` `SHCreateMemStream` `SHCreateStdEnumFmtEtc` `shimx_drag_accepts` `shimx_hdrop_create` `shimx_set_notify_hook`。`gen_sigs.py --check` exit 0 |
| `test/sig/sig_test.sh` (3d75d44) | exit 0, **ALL PASS**, 14.35 s, load average (1 分値) 0.58→0.67 |
| `test.sh --quick` (3d75d44, 実 IR あり) | exit 0, 54.2 s, load average 0.57→0.90。6b 実 IR: m11 / m11_3 / ott いずれも mismatch **0** (正規化前 0 件)。7/7 完了, 公開関数 687 |

- `test.sh --quick` が再生成した inventory.md / BACKLOG.md / coverage.json / inventory.csv / exports.txt は**コミットしていない** (差分 257 行追加・254 行削除)。素材あり run の再生成物だが、コミット可否は別判断 (本 PR の競合解消の範囲外)。
- `sigs.json` の再生成は `gen_sigs.py --check` (sig_gate.sh が毎回実行) の要件。main 取込のたびに再生成が必要。

**修文後の再検証 (2026-10-13, Actions runner, 検証起点 = commit 4e77193, 素材 work-m11 / work-m6-ott 展開済み)**: レビュー 5501305157 の文書訂正 (adapter 記録・零補間の silent 性・PIPESTATUS) を反映。

| 検証 | 結果 |
|---|---|
| `test/sig/sig_test.sh` (n=3, `env -u EMSDK`) | 3 run とも exit 0 (ALL PASS, OK 8 件・FAIL 0), 16.17 / 15.89 / 15.49 s, load average (1 分値, 開始前→終了後) 0.02→0.30 / 0.30→0.52 / 0.48→0.60 |
| 実 IR `tools/m11/work/boot_final2.ll` (`sig_gate.sh`, exit 0, 8.44 s, load 0.55→0.59) | 正規化 0 (adapter) + 重複統合 1 / 未解決 0 / adapter 定義 1 (`@__shx_sig_SHGetFolderPathW.1`, 呼出 1 site) / `signature mismatch = 0` |
| 実 IR `tools/m11/work/boot_final3.ll` (`sig_gate.sh`, exit 0, 9.08 s, load 0.49→0.54) | 正規化 0 (adapter) + 重複統合 1 / 未解決 0 / adapter 定義 1 (`@__shx_sig_SHGetFolderPathW_D1`) / `signature mismatch = 0` |
| 実 IR `tools/m8/work/ott_m8.ll` (`sig_gate.sh`, exit 0, 4.22 s, load 0.45→0.50) | 正規化 0 (adapter) + 重複統合 0 / 未解決 0 / adapter 定義 0 / `signature mismatch = 0` |
| `bash tools/shimx/test.sh --quick` (実 IR あり, exit 0, 57.54 s, load 0.46→0.78) | 7/7 完了, 公開関数 687, MT 6 グループ PASS / ST PASS / M4 互換 PASS / 未実装 0。6b は SKIP 0 件で、m11・m11_3・ott とも sig_gate 経由で mismatch 0 |
| 負の対照 (手順: `set -euo pipefail` 下で失敗コマンドを sed へ流し `\|\| die`) | `DIE x` を出して exit 1、後続は実行されない |

- `test.sh --quick` が再生成した inventory.md / BACKLOG.md / coverage.json / inventory.csv / exports.txt はコミットしていない (§13・§14 と同様)。

**実 IR 実測 (2026-10-13, Actions runner, HEAD 36edc993 = main。素材 work-m11 / work-m6-ott / work-liftlib / work-liftlib-targets 展開済み, `env -u EMSDK`, emcc 6.0.12)**: 各 IR を `sig_gate.sh` (正規化 → `verify_sig.sh`) に通した。

| IR | 正規化前 mismatch | 正規化 adapter / 重複統合 | unresolved | 正規化後 mismatch | 所要 |
|---|---|---|---|---|---|
| `tools/m11/work/boot_final2.ll` | 0 | 0 / 1 (`SHGetFolderPathW.1`) | 0 | **0** | 13.7 s |
| `tools/m11/work/boot_final3.ll` | 0 | 0 / 1 (`SHGetFolderPathW_D1`) | 0 | **0** | 13.6 s |
| `tools/m8/work/ott_m8.ll` | 0 | 0 / 0 | 0 | **0** | 6.9 s |
| `tools/liftlib/work/ott_lb10000/work/ott_m8.ll` | 0 | 0 / 0 | 0 | **0** | 6.8 s |
| `tools/targets/freshair/work/lift_gain/gain_fixed.ll` | 0 | 0 / 0 | 0 | **0** | 6.4 s |
| `tools/liftlib/work/fa_gain/fa_gain_fixed.ll` | 0 | 0 / 0 | 0 | **0** | 6.5 s |

- 正規化前後とも mismatch 0 (M11 の adapter は重複統合名のみ。§16 の既存結果と一致)。
- 素材の `work-liftlib-targets` は HeartCore / SlateCore の lift IR を含まない (freshair `lift_gain` と kilohearts `winpkg` のみ)。HeartCore / SlateCore の lift IR は未実測。

**Kilohearts snap-in 13 本の sig_gate 実測 (#1170, 2026-10-16, Actions runner, 検証起点 = 1170 ブランチ (origin/main b51786338 起点), `EMSDK_ENV` = `[EMSDK]` の env (`docs/REFERENCES.md` §4), emcc は同 toolchain, 素材 plugins-kilohearts / toolchain-retdec / toolchain-emsdk 展開済み, `lift/build.py <n> --path s0 --trials 200 --seed 1`)**:

| snap-in | build compare (native 突合) | 正規化前 / adapter / 重複統合 | unresolved | 正規化後 mismatch | sig_gate 結果 |
|---|---|---|---|---|---|
| gain | 200/200 bit-exact | 0 / 0 / 0 | 0 | **0** | exit 0 |
| matrix | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| haas | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| clipper | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| gate | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| quickeq | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| resonator | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| stereo | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| disperser | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| formant | 200/200 | 0 / 0 / 0 | 0 | **0** | exit 0 |
| phaser | 200/200 | 未測定 / 14 / 0 | 1 (`GetCurrentProcess`) | 未測定 | **exit 1** |
| delay | 200/200 | 未測定 / 18 / 0 | 1 (`GetCurrentProcess`) | 未測定 | **exit 1** |
| limiter | 200/200 | 未測定 / 18 / 0 | 1 (`GetCurrentProcess`) | 未測定 | **exit 1** |

- 正規化前の mismatch: gain / matrix / haas / clipper / gate / quickeq / resonator / stereo / disperser / formant は `正規化前 0 件` (sig_gate 情報行を確認)。phaser / delay / limiter は `sig_normalize --strict` が raw 検証より前に止まるため **未測定**。
- `data/sig_ext.json` に 11 API を追記 (根拠は各 `why`)。`ret` = `zext`: `HeapFree` / `IsProcessorFeaturePresent` / `TerminateProcess` / `UnhandledExceptionFilter` / `LoadLibraryExW` / `GetLastError` / `IsDebuggerPresent` / `FreeLibrary` / `GetModuleHandleW` / `GetModuleHandleExW` / `FlsSetValue` (shimx 定義の値域が非負: BOOL / DWORD / HMODULE)。既存は `GetComputerNameExW` / `GetFileAttributesExW` / `SHGetFolderPathW`。
- **未解決 (本 issue の残件)**: `GetCurrentProcess` の `ret` 符号。shimx 定義は擬似ハンドル `(HANDLE)-1` を返すため、zext (4294967295) と sext (-1) で値が変わる。呼出側 IR の用途を読んで決める必要があり、本 run では確定できず silent に決めなかった。phaser / delay / limiter はこの 1 件で止まっている (他の未解決は全て解決)。
- `sig_test.sh` ALL PASS は HEAD で再現 (24.6 s)。
- 受入条件「SlateCore の未測 lift 対象」は本 run で未実測 (素材 `work-liftlib-targets` は SlateCore の lift IR を含まない。`plugins-freshair` の `tools/targets/freshair/` 側の build は未着手)。
- 除外: `tools/liftlib/work/cab238/p1_only/work/ott_m8.ll` は正規化前の時点で `%p1r_1801209c9_cl1` が未定義 (clang error)。診断用の派生物で正規の成果物ではないため対象外。
- `sig_test.sh` (HEAD 36edc993, `env -u EMSDK`): **ALL PASS**, 24.1 s, load average 0.65→0.75。(a)〜(h) すべて OK

**実 IR 再実測 (2026-10-13, Actions runner, HEAD dee0e1ee = origin/main 起点の `173-sig-verify-ci`, `env -u EMSDK` 無し・emsdk source 経由, 素材 work-m11 / work-m6-ott / work-liftlib / work-liftlib-targets / fl-win64 / toolchain-* 展開済み)**:

| IR | 正規化前 mismatch | adapter / 重複統合 | unresolved | 正規化後 mismatch | sig_gate 所要 |
|---|---|---|---|---|---|
| `tools/m11/work/boot_final2.ll` | 1 | 1 / 1 | 0 | **0** | 9.96 s |
| `tools/m11/work/boot_final3.ll` | 1 | 1 / 1 | 0 | **0** | 11.27 s |
| `tools/m8/work/ott_m8.ll` | 0 | 0 / 0 | 0 | **0** | 5.66 s |
| `tools/liftlib/work/ott_leaf/ott_leaf_fixed.ll` | 0 | 0 / 0 | 0 | **0** | — |
| `tools/liftlib/work/fa_gain/fa_gain_fixed.ll` | 0 | 0 / 0 | 0 | **0** | — |
| `tools/targets/freshair/work/lift_gain/gain_lift.ll` | — | — | — | **対象外** (下記) | — |
| `tools/liftlib/work/fa_gain/fa_gain.drc.ll` | — | — | — | **対象外** (下記) | — |

- **前回 (36edc993 時点) と差が出た点**: boot_final2/3 で adapter `@__shx_sig_midiOutShortMsg` が 1 件ずつ発火した。`midiOutShortMsg` の shimx 署名は、36edc993 の `(i64, i32)` から #179 (winmm midi 実装, main 取込) で `(i32, i32)` に変わっている (`data/sigs.json`)。IR は `declare i32 @midiOutShortMsg(i64, i32)` のため、adapter は `%a0` を `trunc i64 → i32` する。
- **未解決 (本 issue の残件)**: この `trunc` は HANDLE の上位 32bit を落とす。shimx 側 `midiOutOpen` は `uintptr_t` (wasm32 で 4 バイト) で HANDLE を発行するため、発行元と IR 側の値が 32bit に収まる限り実害は無いと推定されるが、**未検証**。実 IR の値域は本 run の IR 静的解析では確定できない。検証には IR 実行 (trap・値の追跡) が要る。
- **対象外 (gate 以前の失敗)**: `tools/targets/freshair/work/lift_gain/gain_lift.ll` は `declare i64 @function_1803ded20` が 7 行目と 359 行目で重複し、raw 段階で `invalid redefinition` (IR 不正・署名とは無関係)。`tools/liftlib/work/fa_gain/fa_gain.drc.ll` は target と合わない datalayout で clang が backend crash (raw 段階)。どちらも `fa_fix_gain` / `ir5_patch` 等の前処理を通した派生物 (`*_fixed.ll`) で代替して検証した (上表の fixed 版は mismatch 0)。
- `test/sig/sig_test.sh` (HEAD dee0e1ee, `env -u EMSDK`): **ALL PASS**, 15.3 s, load average 0.14→。(a)〜(h) すべて OK。

**Kilohearts / Fresh Air plugin lift IR の実測 (#966, 2026-10-13, Actions runner, HEAD cf0a08bf (origin/main), `env -u EMSDK`, 素材 plugins-kilohearts / plugins-freshair / toolchain-retdec / toolchain-emsdk 展開済み)**:

| IR (RetDec 生成) | 前処理 | 正規化前 mismatch | adapter / 重複統合 | unresolved | 正規化後 mismatch | sig_gate 所要 |
|---|---|---|---|---|---|---|
| SlateCore `process` (Fresh Air gain, `0x180afe090`) | `gain_e2e.sh` と同じ `ir_normalize`→`ir5_patch`→`fa_fix_gain` | 0 | 0 / 0 | 0 | **0** | 7.3 s |
| HeartCore `process` (Kilohearts Gain, `0x1804b0380`) | `ir_normalize`→`ir5_patch` + **`declare` の完全一致行の重複除去** (下記) | 0 | 0 / 0 | 0 | **0** | 6.7 s |
| HeartCore Matrix (`kh_lower` stage-0 `final.ll`) | `build.py --path s0 --no-compare` の出力 | 0 | 0 / 0 | 0 | **0** | 6.0 s |
| HeartCore Haas | 同上 | 0 | 0 / 0 | 0 | **0** | 7.0 s |
| HeartCore Clipper | 同上 | 0 | 0 / 0 | 0 | **0** | 7.0 s |
| HeartCore Gate | 同上 | 0 | 0 / 0 | 0 | **0** | 7.0 s |

- 正規化前の mismatch も全件 0 で、adapter は 0 件。今回の IR では署名の揺れが発生していない。
- **注意 1 (手作業の前処理)**: Gain (HeartCore) の RetDec 出力は `function_18004cf20` の `declare` が同一内容で 2 回出ており、`emcc` が `invalid redefinition` で落ちた。同一行の 2 つ目を除く (awk で完全一致行のみ) ことで解消した。これは既存の lift パイプライン (`ir5_patch` / `kh_lower`) に無い手作業であり、恒常化するなら該当 pass への組み込みが必要 (#1170 の受入条件 5 項目目に起票済み)。
- **注意 2**: Fresh Air gain は `gain_e2e.sh` 同様の修復 pass (`fa_fix_gain`) を通した IR で検証した。修復前の生 RetDec IR は `emcc` で 'linking' 段が失敗するため、gate の対象は修復後 IR。
- **未実測 (受入条件の残り)**: SlateCore / HeartCore の snap-in 残り (Kilohearts 42 効果のうち gain・matrix・haas・clipper・gate 以外、SlateCore の他 snap-in) は本節では未実測 (#1170 に起票済み)。`sig_test.sh` ALL PASS は HEAD cf0a08bf で再現した (25 s, load 0.77→0.85)。
