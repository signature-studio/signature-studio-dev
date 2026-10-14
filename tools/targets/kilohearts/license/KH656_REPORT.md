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

313 集合は §7.1 の round 6 (build 失敗 `1813846e0`) に memset shim を登録して再 build した集合。round 6 の失敗そのものはこの表には載せていない。313 集合の wasm は REPORT 上の `1,543,901 B` と 48 B 異なる (emcc 環境差)。入口の症状は一致。

### 7.3 OOB の発生 VA (wasm 関数名: `-g` 版で特定)

`emcc -g` (同 `final.ll`・同 flags、名前付き wasm) で入口を実行した stack (313 集合):

```
kh_180ef7fc0 → kh_18012e420 → kh_1801d3b60 → kh_180138750 → kh_180138a30 → kh_180f88394 → kh_180fa7678 (trap)
```

- **OOB の発生 VA: `0x180fa7678` (wasm 関数 `kh_180fa7678`)**。この関数は 409 行、store/load 174 件、`@rsp` の書換え 10 件。
- trap は関数内部の memory 命令 (オフセット未特定)。命令単位の VA は未確定。
- 入口の `@rsp` は `kh_stack + 65464` (`kh_stack[65536]`)。`kh_stack_ptr()` の base は wasm 内 `0x39a0` (実測)。

### 7.4 原因の判定 (未確定)

- DEFECTS.md の類型 (D1a〜D22) で**該当 ID は未判定**。`D11` (絶対 VA が wasm32 で切り捨て → OOB) と `D17` (ポインタ局所の縮小) が形の上で近いが、本件は trap 命令を未特定のため当てはめできない。
- 「lift の誤り (silent miscompile) か、メモリ配置・stack の問題か」は**本 run では判定できなかった**。`kh_180fa7678` が 10 箇所で `@rsp` を書換えるため、stack 方向の誤りの可能性が高いが、未確認。
- 閉包 313 の入口経路は `kh_180fa7678` までで停止する (fail-fast の `unlifted callee` には届かない)。

### 7.5 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `kh_180fa7678` 内の trap 命令 (VA 単位・wasm 命令オフセット) の特定 | 原因 (lift 誤り / 配置) の判定不能 | #1821 継続 |
| 原因の判定 (silent miscompile か配置/stack か) と DEFECTS 類型 ID | 受入 2 未達 | #1821 継続 |
| `kh656_closure.py` の `i256_defs()` の誤判定 (memset `1813846e0` を i256 扱い) | 閉包の自動化が round 6 で止まる | #1817 (KH-28) |
| 閉包の収束 (未 lift 40 → 154) | 受入 1 未達 | #1817 (KH-28) |

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
