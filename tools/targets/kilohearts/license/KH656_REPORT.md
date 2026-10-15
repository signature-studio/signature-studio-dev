# KH-13 (#656) — ブラウザ分類 0x180ef7fc0 の lift IR 検証: 未 lift callee の処理 (部分完了)

- 担当 dir: `tools/targets/kilohearts/license/` (前提 PR #329 のブランチ `249-kh11-group-host-license-lift` を取り込み済み、merge `f3b8056`)
- 既知類型との関係 (DEFECTS.md / icall §4): 該当 ID なし。今回の失敗 2 種は**いずれも loud failure** (例外・ビルドエラー) で silent miscompile ではない。(a) 閉包内の ymm (AVX2) 命令の `gen_simd.py` 未対応 (`KeyError: 'i256'`)、(b) Win32 import `@GetCurrentThreadId` の宣言欠落 (`use of undefined value`)。D15 ([icall]) は既存 pass で本 module でも 3 site 復元済み (変更なし)。
- 再現コマンド (license/ で実行): `python3 lic_build.py --module F` → `node kh249_check.mjs` → `python3 scripts/kh656_census.py`

## 0. 結論 (先出し)

| 受入条件 (#656) | 結果 |
|---|---|
| 1. 未 lift callee を列挙し、shim (または lift) を用意 | **部分達成**。kh_lower の unlifted callees 40 件を列挙・分類済 (§2・元の 41 件は shim/lift 追加前)。shim 4 件 (`new`/`delete`/`memcpy`/`getManager`) と lift 2 件 (`1800524e0`/`1800b4b10`) を追加し、未 lift は 40 件 (shim 4 + fail-fast 34 + AVX2 2)。残りは STL/EH/AVX2 で未達 |
| 2. function_180ef7fc0 を実行し分類結果・カテゴリを機械照合 (ネガコン付き) | **未達**。入口は依然として最初の未 lift callee `0x180112a30` で fail-fast (§3)。分類結果の lift IR 照合はできていない |
| 3. REPORT の『lift IR では未検証』を『検証済み』に更新 | **未実施** (検証できていないため、KH249_REPORT §6.2 の記述は変更しない) |

→ **Refs #656 のみ。Closes は付けない** (受入条件 2・3 が未達)。

## 1. 変更点

| ファイル | 内容 |
|---|---|
| `lic_config.json` modules.F | `shims` を追加 (`180f878e0`=new, `180f8791c`=delete, `181384040`=memcpy, `180107430`=getManager。E と同一の C 実装を流用)。`lift` に `1800524e0`・`1800b4b10` を追加 (E で lift 済みの実 IR を流用) |
| `scripts/kh656_census.py` | 未 lift callee の分類表 (shim / i256-AVX2 / fail-fast) と件数を出力 |
| `scripts/kh656_closure.py` | 閉包展開ドライバ (未 lift callee を反復的に lift へ追加)。**現状は §4 の 2 件の blocker で停止する** (ビルド失敗時は exit ≠ 0 で終了し、結果を握りつぶさない) |
| `KH656_REPORT.md` | 本報告 |
| `docs/DOC_MAP.md` | KH249 行に KH656_REPORT を追記 (行数欄は実数) |

## 2. 未 lift callee 40 件の内訳 (実測)

計測: `python3 scripts/kh656_census.py` (HEAD の lic_config・`lic_build.py --module F` の stat.json)。

| 分類 | 件数 | VA |
|---|---|---|
| shim (C 実装で置換、lift しない) | 4 | 0x180107430 (getManager) / 0x180f878e0 (new) / 0x180f8791c (delete) / 0x181384040 (memcpy) |
| AVX2 (ymm 命令を含む、lift 不可) | 2 | 0x180f89cf0 / 0x180fb6124 (`scripts/kh656_census.py` が PE 関数範囲の逆アセンブルで ymm 命令を検出して実測、§4) |
| fail-fast (未 lift、呼ばれると停止) | 34 | 0x180005000 0x180005c30 0x180005c50 0x18000caf0 0x18000f590 0x180021490 0x1800219b0 0x180021d40 0x1800448e0 0x1800541b0 0x18006ac50 0x18006c040 0x18010b6c0 **0x180112a30 (入口経路の先頭)** 0x18012e420 0x18012fba0 0x180130560 0x18013b9e0 0x18013c9c0 0x18024b2e0 0x1803965a0 0x180396b00 0x180396f40 0x18065bbd0 0x180c433b0 0x180c44b50 0x180c44d20 0x180c44d30 0x180c44d50 0x180c47b50 0x180ef8ef0 0x180ef92b0 0x180ef9b70 0x180fb5f5c |
| **合計 (未 lift 扱い)** | **40** | (元 41 − lift 追加 2 + 新規出現 1 `18000caf0`) |

注 (#709 で追記): 上表の「AVX2 (lift 不可)」「gen_simd 未対応」は基底 `8303a813` 時点の語彙による分類。#709 で gen_simd に ymm 整数語彙 (vpcmpeqb/w/d・vpmovmskb・vinsertf128) が加わり、2 件は i256 経路で emit されるようになった (ただし SSE 語彙不足で abort スタブとなり未 lift のまま。`KH709_REPORT.md` §3)。

注: `0x180021490` (key_init) と `0x1800219b0` (apply_key) は module A/E で C stub の seam (`lic_config.json` の stubs) として扱われている。module F では lift も stub もされず fail-fast。F の経路で実際に到達するかは未確認。

## 3. 実測 (コミット HEAD で実行。環境: nproc=4)

| 項目 | 変更前 (PR #329 HEAD `d238c27` 相当) | 変更後 (本 PR) |
|---|---|---|
| `lic_build.py --module F` wall time (n=3, min–max) | 変更前の計測 (PR #329 HEAD) は emcc キャッシュ条件が揃っていないため比較から除外 | cold (`KH_EM_CACHE` 空の新規 dir) **16.30–16.46 s** / warm (同 dir 再利用) **2.69–2.72 s**。両条件とも `work/retdec0` 既存 (retdec 再実行なし)。差は emcc キャッシュの有無のみ |
| wasm | 47,604 B | **54,394 B** (sha256 `7ba79e65ec158a711646316579e6f8bc3d8c12f47c61851710a5e2077b8c7707`) |
| undefined import | 0 | 0 |
| unlifted callee (kh_lower) | 41 | 40 (shim 4 を含む) |
| `kh249_check.mjs` | ok=17 ng=0 | **ok=17 ng=0** (入口 fail-fast 先 `0x180112a30` は不変) |
| 負律対照 (分類式 5 種・命令バイト照合) | 全 FAIL 検出 (KH249 §6.1) | 変化なし (本変更は分類式・thunk に触れない) |
| load average (終了時) | — | 0.09 / 0.45 / 0.36 (4 CPU) |

- **ネガティブコントロール: 新規 shim/lift については未実施**。追加した shim 4 件と lift 2 件は入口の実行経路で**呼ばれる前に**停止するため、壊して FAIL を確認できない。受入条件 2 のネガコンは入口を越えた後でのみ成立する。
- 本変更は module F の設定のみ。`run_all.sh` 全体 (module A/B/E・snapin 6 種) は**未実行**。module A/B/E の設定・コードは変更していない。

## 4. 閉包展開の試行と blocker (実測)

`scripts/kh656_closure.py` で未 lift 36 件 (shim・既 lift を除く) を一括追加して再 build した結果:

1. **gen_simd.py が失敗**: `KeyError: 'i256'`。閉包内の `0x180f89cf0` と `0x180fb6124` が ymm 命令 (`load i256` / `__asm_vpcmpeqd` / `__asm_vpmovmskb`) を含む。license 版の `lift/gen_simd.py` の `CT` 表に i256 が無い (snapins 版も同じで、既存 snapin の閉包には現れていない)。→ この 2 件を lift から除外 (`n1.ll` の define 単位で検出)。
2. **emcc が失敗**: `final.ll:12382:18: error: use of undefined value '@GetCurrentThreadId'`。閉包内の関数が Win32 import を呼ぶが、license 版の lift パイプラインには import の `declare` 生成も named-import shim 節も無い。snapins 版 `lift/gen_stubs_sigs.py` には `IMP_SHIM` (GetCurrentThreadId 含む 20 件) と named-import 節があり、**移植が必要**。

このため `kh656_closure.py` の実行結果は**不合格のまま**で、閉包展開の完了はしていない。`lic_config.json` は (1)(2) の試行で一時的に壊れた状態から、**ビルドが通る状態 (lift 8 件 + shim 4 件) に戻して**コミットする。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 入口経路 `0x180112a30` の fail-fast (STL map/shared_ptr 系の lift または shim) | 受入条件 2 (分類結果の lift IR 照合) 未達 | #656 継続 (本 PR は Refs) |
| 残り fail-fast 34 件 (STL map/string/vector、EH `0x180005c30`/`c50`/`0x180fb5f5c` 等) | 閉包の広がり量は未見積 (試行 1 回目で 36 件を一括追加し失敗) | #656 継続。大きければ子 issue を PM が起票 |
| ymm (AVX2) 命令の lift 未対応 (`0x180f89cf0` / `0x180fb6124`) | 閉包を広げられない | #709 [KH-14] |
| license 版 lift パイプラインの Win32 import 宣言・shim 節の欠落 (snapins 版から移植要) | 閉包を広げると emcc が失敗 | #710 [KH-15] |
| 0x180ef7fc0 の native oracle (ctx-fuzz) 未作成 | 出力の bit 照合ができない | #656 継続 |
| #329 merge 済み (main `4f33fdd`) | 本 PR の diff に含まれていた #329 の commit (merge `f3b8056`) は main 取り込みで解消 | 解消済み (起票不要) |
| shim 4 件 (E と同一実装) の妥当性は F の経路で未検証 | 入口を越えるまで検証不能 | #656 継続 |

## 6. 検証範囲 / 範囲外

- 範囲内: module F の build (lift→stub→emcc)・`kh249_check.mjs` (17 項目)・未 lift callee の census。
- 範囲外: 閉包展開の完了、分類結果の lift IR 照合、native oracle との突合、module A/B/E/snapin 6 種の再実行 (本変更は F のみ)。
- 作業ログ: 素材 (`plugins-kilohearts` の Windows installer zip 3.8 GB) は `$RUNNER_TEMP/kh_src` に展開し、`tools/targets/kilohearts/work/winpkg` (gitignore) に Windows 側のみ展開。emsdk/retdec は `[EMSDK]`・`[RETDEC]` (`docs/REFERENCES.md`) の既設を使用。Python 依存は `$RUNNER_TEMP/kh_venv` (pefile/capstone/numpy)。

## 7. 閉包 313 関数の入口 OOB の切り分け (#1821 / KH-29、実測)

測定 commit: `19fd9d73` (main)。コード差分は本節 (REPORT のみ) を除き 0 (`lic_config.json` は HEAD に戻した)。
環境: nproc=4・load average は実行中 0.1〜0.6。`plugins-kilohearts` は R2 から取得し installer 抽出 (`work/winpkg`)。
Windows 側の抽出は成功、macOS 側は `llvm-lipo` が無く rc=127 (本件は Windows 側のみ使用)。

### 7.1 閉包の再現

`python3 scripts/kh656_closure.py --rounds 6` (1 分 53 秒): round 1 (lift 8→40 未 lift) → round 2 build 失敗 (`i256`: `0x180f89cf0`・`0x180fb6124` 除外) → round 3 (lift 42) → round 4 (lift 80) → round 5 (lift 166) → round 6 build 失敗 (`i256` 判定で `1813846e0` を除外)。

round 6 の失敗の扱い: `kh656_closure.py` は `dropped_i256` に `1813846e0` を載せたが、`n1.ll` に `1813846e0` の定義は無く (確認済み)、i256 による除外の根拠は無い。`1813846e0` は memset で、module F の shims に未登録だったため閉包に入った。shim 登録 (module F shims に `1813846e0: memset`) を加えると 313 集合で build が通る。round 6 の失敗原因 (`dropped_i256` の判定経路) は未特定。

### 7.2 測定値 (HEAD 行はコミット HEAD の state、166・313 行は未コミットの `lic_config` 一時変更で実行)

166 行と 313 行は、閉包展開スクリプトが書き換えた未コミットの `lic_config` で測定した (測定後に HEAD へ戻した)。313 行は未コミットの `lic_config` 一時変更。

| 集合 | lift | wasm B | undefined import | 入口 `function_180ef7fc0` |
|---|---|---|---|---|
| HEAD (main) | 8 | §3 参照 | 0 | `unlifted callee 0x180112a30` (ok=17 ng=0) |
| round 5 集合 (§7.1 の round 5 = lift 166) | 166 | 876,174 | 0 | `unlifted callee 0x180138a30` (ok=16 ng=1) |
| round 6 相当 (+shim memset・313 行は未コミットの `lic_config` 一時変更) | 313 | 1,543,853 | 0 | **`memory access out of bounds` (再現)** |

313 集合は §7.1 の round 6 (build 失敗 `1813846e0`) に memset shim を登録して再 build した集合。round 6 の失敗そのものはこの表には載せていない。同じ集合の wasm は §7.6 (`9d491eb4`) で `1,543,901 B` と記録されており、本表の `1,543,853 B` と 48 B 異なる。`19fd9d73` と `9d491eb4` の license/ の tracked コードは差分 0 である。差の原因は記録から切り分けられず、未コミットの一時設定の差か実行環境の差かのいずれか (「環境差」とは断定しない)。入口の症状は一致。

### 7.3 OOB の発生 VA

- 発生 VA は native `0x180fa76a8` (wasm `kh_180fa7678`)。呼び出し鎖・trap 命令の対応・逆アセンブルは付録 §2 へ移した。

### 7.4 原因の判定

- 判定: DEFECTS **D11** (PE 絶対 VA の wasm32 切り捨て → OOB)。loud (trap)。lift の命令変換の誤りではなく、メモリ配置の問題。根拠は付録 §1・§3。

### 7.5 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.rdata` 等の生 VA ポインタを wasm 線形メモリで参照可能にする (D11 既定修正の拡張) | 313 集合の入口 OOB (原因は確定・解消は未) | #3866 (KH-75) |
| `0x1813d21e8` の出所と呼び出し経路 (付録 §3) | #3866 受入 2 の 5 件のうち 1 件が未確認 | #3866 (KH-75) |
| `i256_defs()` の誤判定 (`1813846e0` を i256 扱い) | 閉包の自動化が round 6 で止まる | #1817 (KH-28) |
| 閉包の収束 (未 lift 40 → 154) | 受入 1 未達 | #1817 (KH-28) |

### 7.6 trap 命令の特定 (#1821 / KH-29、実測・2 回目 run)

測定 commit: `9d491eb4` (main 取り込み後)。コード差分 (REPORT 除く) は本節追加時点で 0 (`lic_config.json` は HEAD に戻した)。
環境: nproc=4・load average 0.9 (測定時)。`plugins-kilohearts` は `Kilohearts Offline Installer.zip` から `work/winpkg` を再抽出。

- 閉包 313 の再現: `lic_build.py --module F` は shim `1813846e0: memset` を F の `shims` に追加した状態で 1,543,901 B・undefined import 0 (§7.2 の 1,543,853 B とは 48 B 異なる)。
- 入口 `function_180ef7fc0` は `memory access out of bounds` で再現 (`kh249_check` ok=16 ng=1)。
- trap の wasm 命令オフセット・native VA・逆アセンブル・`[rcx]` の値の出所は付録 §2・§3。

### 7.7 結論

- 受入 2 (原因と DEFECTS 類型) は達成: D11 (付録 §1)。解消は子 #3866 (KH-75) (§7.5)。
- 記録の訂正: 旧 PR 本文・旧付録の「修正前の emcc RSS 上限 kill・`globals.c` 681 MB」は裏付けが無いため撤回 (付録 §4)。

## 8. 閉包展開の再試行 (#1761 / KH-27、実測)

`scripts/kh656_closure.py --rounds 6` を実行した。`#710` (Win32 import 宣言) は closed、`#709` (ymm) は open。

検証起点 (commit の役割を分ける):

- **測定対象のコード**: `0eaf2989` (main 取り込み済みの license 版コード)。
- **本節を記録した commit (REPORT のみ)**: `98c0f477`。コードは `0eaf2989` と同一 (`git diff 0eaf2989 98c0f477 -- tools/targets/kilohearts/license ':!*KH656_REPORT.md'` = 0 行)。
- **本 commit (検証 HEAD)**: コード差分は 0 (`git diff 98c0f477 HEAD -- tools/targets/kilohearts/license ':!*KH656_REPORT.md'` = 0 行)。変更は本 REPORT のみ。
- コードの差分が 0 のため、`lic_build.py --module F` の再測定は不要 (`docs/WORKFLOW.md` §6)。

| ラウンド | lift 数 | 未 lift callee | 結果 |
|---|---|---|---|
| 0 (HEAD) | 8 | 40 | build 成功 (wasm 54,394 B・sha `7ba79e65…`) |
| 1 | 8 → +34 | 40 | build 失敗 (`i256` = AVX2 2 件を除外) |
| 2 (再 build) | 42 | 44 | build 成功 (wasm 192,136 B) |
| 3 | 80 | 92 | build 成功 (wasm 436,971 B) |
| 4 | 166 | 154 | build 成功 (wasm 876,222 B) |
| 5 | 313 | — | build 失敗 (記録上の結果。原因の分類は未確認) |

round 5 の扱い (確認結果):

- `1813846e0` は shim ではなく、**module F の shims に未登録の関数**である。`lic_config.json` で `memset` の C shim として登録されているのは module E (line 219) のみで、module F の `shims` は `180f878e0`・`180f8791c`・`181384040`・`180107430` の 4 件。そのため閉包 (`kh656_closure.py`) がこの番地を lift 対象として加えた。`scen_gate.h` の注記 (memset = C shim) は module E の設定と一致し、F の設定の漏れを示す。
- 「i256 (AVX2) の除外」という分類の根拠 (関数本体の命令) は、本記録では確認していない (`n1.ll` が保存されていない)。よって「i256 1 件」という分類は未確認の記述として扱う。
- 本 run には `work/` と `plugins-kilohearts` 素材が無く、round 5 の build 失敗は再現していない。表の round 5 の結果は、記録された元のログに基づく記述に留まる。
- 修正方針 (未実施): module F の `shims` に `1813846e0: memset` を追加すれば、閉包から除外され E と同じ扱いになる。この変更は閉包の再測定を伴うため、本 PR では行わず、#1817 で扱う。

- 閉包は**収束しない**。未 lift callee は 40 → 154 と増え、ラウンドごとに新しい callee が出る。6 ラウンドの上限でも `todo == []` に届かなかった。
- 「313 関数 lift・wasm 1,543,901 B・`kh249_check.mjs` の入口が `memory access out of bounds`」という結果は、**round 5 は build 失敗のため wasm が存在せず、この実行結果は測定値ではない**。round 2〜4 の build の入口 (`kh249_check.mjs`) 実行結果は本記録に残っていない。閉包を広げた状態の入口挙動は本記録では未確認であり、#1821 (KH-29) で切り分ける。
- 上記の変更は**コミットしていない** (`lic_config.json` は HEAD に戻した)。HEAD の状態は再 build で上記と一致 (wasm 54,394 B・sha `7ba79e65…`・undefined import 0・`kh249_check` ok=17 ng=0・入口 `unlifted callee 0x180112a30`)。
- 所要: 閉包 6 ラウンド 1 分 36 秒 (`time`)、HEAD の `lic_build.py --module F` 12.25 秒 (`time`)、終了時 load average 0.08 / 0.08 / 0.14 (4 CPU)。
- 測定 commit と HEAD の関係: HEAD の `lic_build.py --module F` の結果 (上記) は `0eaf2989` のコードで得た。`98c0f477` は本節の REPORT のみを追加した commit で、コード差分は 0。本 commit の `git diff 98c0f477 HEAD -- tools/targets/kilohearts/license ':!*KH656_REPORT.md'` も 0 行。
- 閉包 6 ラウンドの結果 (表の round 1〜4・5) は、ログ・`stat.json` が `work/` に残っておらず、本記録の値のみが根拠。再現には `plugins-kilohearts` 素材が必要 (`oc_artifacts: plugins-kilohearts toolchain-retdec toolchain-emsdk`)。

**受入条件の判定**: 2 (入口を越えた分類結果の照合) と 3 (ネガティブコントロール) は未達のまま。閉包の収束が取れないため、受入 1 も未完。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉包の収束 (未 lift callee 40 → 154 と増加。STL map/string/vector・EH の lift/shim 方針) | 受入 1・2 未達 | #1817 [KH-28] |
| 313 関数 lift 時の入口 `memory access out of bounds` | 閉包を広げた状態の実行検証不能 | #1821 [KH-29] |
| ymm (AVX2) 2 件 `0x180f89cf0` / `0x180fb6124` の lift | 閉包を広げると build 失敗 (記録上。round 5 の原因は未確認) | #709 (KH-14・既存) |
| 0x180ef7fc0 の native oracle (ctx-fuzz) | bit 照合不可 | #1761 継続 |

## 9. 閉包の各ラウンドの入口経路 (#3591 / KH-58、実測)

注: §8 の表は 313 集合の旧記録 (round 5 = 313 lift・build 失敗) で、lift 集合が本節の round 5 (314 lift・build 成功) と異なる。
測定 commit: `5db386d26` (`kh656_closure.py` に各ラウンドの入口結果 `entry_check()` を追加。`lic_build.py`・`lic_config.json`・`kh249_check.mjs` は HEAD と同一)。
その後のコード変更: commit `5bab5649c` の 1 件のみ。`entry_check()` に `subprocess.TimeoutExpired` の分岐 (`entry: 'timeout'` を記録) を追加した。正常系の処理は変えていない。
コード差分 (本節を除く): `git diff 5db386d26 HEAD -- tools/targets/kilohearts ':!*KH656_REPORT.md'` の出力:

```diff
diff --git a/tools/targets/kilohearts/license/scripts/kh656_closure.py b/tools/targets/kilohearts/license/scripts/kh656_closure.py
index c59421af9..7ac5ec4bf 100644
--- a/tools/targets/kilohearts/license/scripts/kh656_closure.py
+++ b/tools/targets/kilohearts/license/scripts/kh656_closure.py
@@ -66,7 +66,10 @@ def run_build():
 
 def entry_check():
     """入口 function_180ef7fc0 の実行結果 (kh249_check.mjs)。受入 2 の判定値: 最初の未 lift callee か trap 文言"""
-    r = subprocess.run(['node', os.path.join(LIC, 'kh249_check.mjs')], cwd=LIC, capture_output=True, text=True, timeout=300)
+    try:
+        r = subprocess.run(['node', os.path.join(LIC, 'kh249_check.mjs')], cwd=LIC, capture_output=True, text=True, timeout=300)
+    except subprocess.TimeoutExpired:
+        return {'entry': 'timeout', 'check': None}
     out = r.stdout + r.stderr
     e = re.search(r'entry run -> (.*)', out)
     s = re.search(r'kh249_check ok=\d+ ng=\d+', out)
```

環境: nproc=4・load average 0.6〜0.8。素材 `plugins-kilohearts` は installer zip (`HeartCore.core_64` 76,642,304 B) と `product_index.json` (46 plugins) を展開。

実行: `python3 scripts/kh656_closure.py --rounds 6` を 2 回 (1 回目は `kh656_closure.py` の変更を未コミットのまま、2 回目は `5db386d26` で実行)。所要 2 分 12 秒・load average 0.6〜0.8 は 2 回の実行 (n=2) の値で、WORKFLOW §5 の min–max レンジ (n≥3) は掲載しない。`work/kh656_rounds.json` に各ラウンドの結果を記録 (`work/` は gitignore のため commit されていない)。

| ラウンド (lift 集合の数) | 未 lift callee | wasm B (sha256 先頭 8 桁) | undefined import | 入口 `function_180ef7fc0` | `kh249_check` |
|---|---|---|---|---|---|
| 1 (HEAD 相当・8) | 40 | 54,394 (`7ba79e65`) | 0 | `unlifted callee 0x180112a30` | ok=17 ng=0 |
| 2 (42) | 44 | 192,136 (`0dac597b`) | 0 | `unlifted callee 0x1801d3b60` | ok=16 ng=1 |
| 3 (80) | 92 | 436,971 (`907a34bc`) | 0 | `unlifted callee 0x180138750` | ok=16 ng=1 |
| 4 (166) | 154 | 876,222 (`b7de032a`) | 0 | `unlifted callee 0x180138a30` | ok=16 ng=1 |
| 5 (314) | 144 | 1,687,866 (`ac0dc441`) | 0 | `memory access out of bounds` | ok=16 ng=1 |
| 6 (452・試行) | — | build 失敗 | — | — | — |

- sha256 の 64 桁は本記録に保存されていない (round 1 の 64 桁は §3)。作者の 2 回の実行では wasm sha256 が一致したと記録されているが、64 桁が無いため本 REPORT では照合できない。
- 本 fix run は素材 (`plugins-kilohearts`・`toolchain-emsdk`) が無く、閉包と HEAD の再測定を行っていない。`5bab5649c` の変更は stub 試験のみで確認した (`TimeoutExpired` で `{'entry': 'timeout', 'check': None}`。通常出力では `entry` と `check` を従来どおり抽出)。
- `ng=1` は `kh249_check.mjs` [2] の期待値 (`0x180112a30` で止まること) が、ラウンド 2 以降で外れたための判定。check 自体は変えていない。

**受入 2 の判定: 既定を適用して達成**。issue #3591 本文の既定 (入口が分類本体へ届かない場合は、最初の未 lift callee を REPORT に記録して終える) に従う。
- 入口 `0x180112a30` を越えた: 達成 (ラウンド 2〜4 で越える)。
- 分類本体への到達: **未達**。越えた先の最初の未 lift callee は、ラウンド 2 `0x1801d3b60`・ラウンド 3 `0x180138750`・ラウンド 4 `0x180138a30`。ラウンド 5 (314 lift) は `memory access out of bounds`。既定に従い上の表に記録した。trap VA は本節では再測定していない (#1821 の §7.6 を参照。ラウンド 5 の memset `1813846e0` は lift 扱いで、#1821 の 313 集合 (shim 版) とは wasm が異なる。入口の症状は一致)。

**ラウンド 6 の失敗 (#3590 の範囲)**: `dropped_i256` が 452 件で、ラウンド 5 の lift 314 + 新規 138 の全件に当たる。i256 判定 (`i256_defs()`) が機能しておらず、失敗時の自動除外が lift 集合を空にする。本 run では `lic_config.json` を HEAD に戻して測定した。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 入口経路の未 lift callee (`0x1801d3b60`・`0x180138750`・`0x180138a30`) の lift/shim 化 | 分類本体への到達 (受入 2) | #3590 (閉包の収束) |
| ラウンド 5 (314 lift) の入口 OOB の trap VA と原因 | 受入 2 の残り | #1821 |
| `i256_defs()` の全件誤判定と、失敗時に lift 集合が空になる自動除外 | 閉包の収束 (受入 1) | #3590 |
| `5bab5649c` 以降の HEAD での閉包再測定と、64 桁 sha256 の記録 | 測定値の照合 (本 fix run は素材不足で未実施) | 本 PR の review run (`oc_artifacts` 付き) |

## 10. 閉包の収束試行と round 6 失敗の切り分け (#3590 / KH-57、付録へ分割)

- 結論: `todo == []` には未収束 (受入 1 未達)。round 8 (lift 589) まで build が通り、round 9 は `kh_lower` の stage0 欠落 `0x180f88488` で停止。round 6 の失敗 (i256 判定の誤り・失敗時に lift 集合が空になる) は修正済み。module F に memset shim `1813846e0` を登録 (HEAD と同じ wasm 54,394 B・kh249 ok=17 ng=0 を維持)。
- 各ラウンドの実測・原因の切り分け・未解決: [`KH656_REPORT_APPENDIX_3590.md`](KH656_REPORT_APPENDIX_3590.md)
- 測定 commit: `0b487d4f2` (以後は REPORT のみ)。

## 11. 閉包 lift-8 / 313 窓化の HEAD 再測定 (#4670 / KH-105、実測)

測定 commit: `d3bb79581` (`scripts/kh656_window_measure.py` を main に取り込んだ commit。測定はこの HEAD で実施)。
素材: `plugins-kilohearts` (installer zip → `work/winpkg/HeartCore.core_64` 76,642,304 B)・`toolchain-retdec`・`toolchain-emsdk`。環境: nproc=4・load average 0.52〜0.67。

| 測定 | wasm B | globals | sha256 先頭 8 桁 | undefined import |
|---|---|---|---|---|
| lift-8 off (`rdata_str` 無し) | 54,394 | 9 | `7ba79e65…` | 0 |
| lift-8 on (`rdata_str` + `rdata_raw_allow`) | 54,487 | 10 | `3d2bc6fd…` | 0 |

- 受入 1 達成: wasm B と sha256 先頭 8 桁は測定 commit `091c68915` の記録 (`KH656_REPORT_APPENDIX_1821.md` §3: lift-8 on 54,487 B・`3d2bc6fd`、lift-8 off 54,394 B・`7ba79e65`) と一致する。globals は on の 10 のみ `091c68915` の記録 (10) と一致。off の globals 9 は `091c68915` では「未記録」だったため、今回が初回記録であり、一致の根拠にはしない。
- 注: `091c68915` の on 測定は `rdata_raw_allow` を渡さずに行われた。今回の on は `rdata_raw_allow` を渡して測ったが、sha は一致した。
- driver は `091c68915` の `scripts/kh656_window_measure.py` を取り込んだ後に改変している (単純な取り込みではない): `lift8` を `LIFT8` 固定、on 側で `rdata_raw_allow` を渡す、`set313` の停止条件追加、出力 tag `m4670_*`、docstring。
- lift 8 件は `LIFT8` で固定 (`lic_config.json` の F の現行 lift 集合は 1,305 件で、使わない)。`091c68915` 時点の F は lift 8 件。
- 313 集合: 元の源 `work/kh656_rounds.json` は gitignore で本 runner に無い。閉包を再実行して再生成し、`scripts/kh656_set313.json` (313 VA、commit `cd26429ed`) に tracked 化した。再生成は次の手順: `lic_config.json` の F を lift 8 件・`rdata_str` 無しにして `scripts/kh656_closure.py --rounds 4` を実行し、`work/kh656_rounds.json` の `new_lift` (305 件) と初期 8 件の和から memset shim `1813846e0` を除く。`lic_config.json` の F の lift (4 ラウンド後) と一致することを確認した。
- set313 の off (`rdata_str` 無し): HEAD で測定し、§8.2 の値と一致 (1,543,976 B・`422c129f…`・globals 82・undefined import 0)。
- set313 の on (`rdata_str` 有り): **HEAD 未測定 (ブロック)**。`lic_build` が `.rdata` 生 VA の検査で停止する: 許可外 129 件 (`rdata 生 VA が窓化されず残った (許可外・deref され得る)`)。この検査は `728eab8b9` (#4257) で入り、測定 commit `091c68915` には無い。旧 on 値 (1,547,172 B) は検査無しで測った値なので、HEAD で同じ条件では比べられない。許可外 129 件を `rdata_raw_allow` に足すと「deref されない」を仮定することになるため、足さなかった。129 件の扱い (窓の拡張か許可の根拠の確認か) は PM 判断。
- 閉包の再実行 (lift 8 から、HEAD `cd26429ed`・`rdata_str` 無し): round 1〜2 は §9 と一致 (54,394 B `7ba79e65`・192,136 B `0dac597b`・lift 42)。round 3〜4 の wasm B は §9 と違う (round 3: 437,094 B `1e922280`・§9 は 436,971 B `907a34bc`、round 4: 876,297 B `4c930f3a`・§9 は 876,222 B `b7de032a`)。lift 件数・入口の未 lift callee (`0x180138750`・`0x180138a30`) は一致。§9 の測定 commit は `5db386d26` で、差は未確認。
- 素材の再現性: 本 run の `$ARTIFACTS_DIR` には `plugins-kilohearts` が無く (`fl-win64` のみ)、`work/` も無い。driver の再実行による独立検証は行っていない。数値は `091c68915` の既存記録との照合のみ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 313 on (`rdata_str` 有り) の HEAD 測定: `.rdata` 生 VA 許可外 129 件で停止。許可外の扱い (窓の拡張か、deref されないことの確認か) | 受入 2 未達 (§8.2 の on 値は HEAD 未測定のまま) | PM 判断 (`.rdata` 検査の #4257 の扱い。起票先は PM が決める) |
| 閉包の round 3・4 の wasm B が §9 の値と違う (lift 件数は一致) | §9 の測定値の照合 | 本 PR の REPORT 記録。原因は未確認 |
