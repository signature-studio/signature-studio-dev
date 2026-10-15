# REPORT_APPENDIX_2880 (WIN-11 #2880)

REPORT_APPENDIX.md §9 の全文 (250 行上限のため分割移動)。外部絶対パスのみ ID 参照 (`[EMSDK]`・`[RETDEC]`) に直した (AGENTS §4-1)。測定 commit `ae963e28`。

## 9. WIN-11 (#2880): EnterCriticalSection の失敗 CS と初期化経路 (部分達成)

既知類型との関係: 該当 DEFECTS 行なし。原因は未確定 (lift 欠陥か init 列の扱いか) のため、類型は追加しない。
測定 commit: `ae963e28` (コードを変えた最後の commit。shim の診断 1 行のみ)。後続の commit は docs のみ (本節・REPORT_APPENDIX の要約・DOC_MAP)。REPORT.md は変えていない。§9-3 は現 HEAD `adad27ad` で再測定した (§9-8)。
差分の証跡 (WORKFLOW §6): `git diff adad27ad HEAD -- tools/shim tools/gui/flengine/cfi_probe.mjs` は §9-8 に出力を付す。本節の 9-1・9-4〜9-7 は `ae963e28` 時点の実測で、現 HEAD の実測ではない。

### 9-1. 受入条件の状態 (#2880 の 3 項目)

| 受入 | 状態 | 根拠 |
|---|---|---|
| 1 呼出元 VA と CS の登録経路を実測で特定 | 部分達成 | CS = `0x12bd390` (実測)。呼出元 VA は未特定。boot 中に `0x12bd390` の登録は無い (§9-4・§9-5) |
| 2 類型照合・shim の修復 | 未達 | 原因未確定。shim 側の欠陥は見つからず。shim の変更は失敗時の CS キー表示 1 行 |
| 3 `cfi_probe.mjs` が EnterCriticalSection を越える | 未達 | 同じ地点で fail-fast (§9-3) |

### 9-2. 素材と再現 (boot7 の取込)

今回の素材: `fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。work-m11 は boot7 を含まないため、WIN-4 の手順で boot7 を作り直した。

| 手順 | 結果 (実測) |
|---|---|
| `gf_seed_closure.py --ir tools/m11/work/boot_final3.ll` | closure 6,591 関数 / 1,965,676 B・既存 4,520・新規 2,071 / 761,038 B (§7-2 と一致) |
| `m11_lift.sh <絶対パスの ranges> boot7 780` | rc 0・2 分 45 秒・`boot7.lift.ll` 222,014 行 (§7-3 と一致) |
| `m11_gen_ir2.sh` | rc 0・1 分 06 秒・`boot_final.ll` 707,524 行・ldfix / ld108 applied |
| `m11_build.sh` | rc 0・34.1 秒・signature mismatch 0 / undefined 0 |
| `gui/flengine/build.sh` | rc 0・22.8 秒・`m11_gui.cjs` (signature 0 / undefined 0 / duplicate 0) |

再現の注意: (1) `m11_lift.sh` は ranges を相対パスで渡すと `cd` 後に解決できず、文字列として扱われる。絶対パスで渡す。(2) flengine の build は `x86_64-w64-mingw32-gcc` を要する (`gen_api.py` の arity 表)。今回の oc_artifacts に `apt-mingw` が無かったため、`sudo apt-get install gcc-mingw-w64-x86-64` を手で入れた (agent-setup の apt-mingw と同じパッケージ)。(3) `EMSDK_ENV=（[EMSDK] の emsdk_env.sh）` と `RETDEC=（[RETDEC] の bin/retdec-decompiler）` を環境に入れる。

### 9-3. 実測: CreateFruityInstance の呼出し (`cfi_probe.mjs`・commit `adad27ad`)

| 項目 | 結果 |
|---|---|
| `boot_enter` | `unreachable` (§7-4 と同じ) |
| `CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` | `Aborted`・1 ms・`iface` = 0x0 |
| 最後の shim 行 | `[shim] CS-MISS key=0x12bd390` → `FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (未初期化/未登録)` |
| GUI-REACH / icall_miss | `LoadStringW` ×3 のみ / 5 (§7-4 と同じ) |

表の値は `ae963e28` で測定した値と同じ (§9-8)。`CS-MISS` の行は commit `ae963e28` で追加した (失敗時の 1 行のみ。挙動は変えない)。§7-4 の記録は CS のアドレスを出さないため、キーは `ae963e28` で初めて得た。

### 9-4. boot 側の測定 (同じ build・一時診断)

一時診断 (`InitializeCriticalSection` の登録ログ。コミットしない) と、boot 直後のメモリ読取の結果:

| 項目 | 結果 |
|---|---|
| boot の停止 | `unreachable`・`init_count` 54・`boot_stage` 1 (`entry_point` は戻らない) |
| boot 中に登録された CS | `0x11eaf00`・`0x11f0800`・`0x10c63a50` (いずれも `ok=1`)。`0x12bd390` は登録されない |
| boot 中に出た stub | `GetLocaleInfoW`・`EnumCalendarInfoW` (`stub-notimpl`)。その後に trap |
| 後始末フラグ `0x11e6a38` (boot 後) | -1 |
| `G = 0x15e1db8` (boot 後) | 0 (`P = *G` = 0) |

### 9-5. IR の読取 (boot7 込み・`boot_final3.ll`)

- `EnterCriticalSection` の呼出し: 定数 CS は `function_419560` の `0x11EAF00` のみ。残りは引数が動的な呼出し (`function_4232e0`、ラッパ `function_406f50` 経由)。失敗した `0x12bd390` は動的な引数なので、呼出元はこの候補のどれか。**呼出元 VA は未特定** (wasm に name section が無く、JS の stack は wasm 関数 index しか出ない)。
- 初期化と解放の対: `function_41ce10` は init 列の 3 番目 (`inits_text.txt`)。フラグ `0x11e6a38` を `dec` し、結果が 0 のときに初期化本体に入る。本体は `function_418e10` (= `InitializeCriticalSection(0x11EAF00)`) を呼ぶ。`function_41cd70` は init 列の 4 番目で、`add 1` の結果が 0 のとき `function_418f20` → `DeleteCriticalSection(0x11EAF00)` を呼ぶ。解放側が init 列に入る理由は未確認 (`m11_bounds.py` の抽出規則)。
- trap の候補: `unreachable` を持つのは `function_447860` のみ。`G` → `P` → `*P` が 0 のとき `function_409730` の後に `unreachable` へ落ちる。ただし実測では `G = 0` → `P = 0` → `*P` = `load [0]` = 0x4bdb50 ≠ 0 なので、この分岐は通る。**trap 地点は未特定**。

### 9-6. e2e (`bash tools/gui/flengine/e2e.sh`・commit `ae963e28`)

| 項目 | 結果 |
|---|---|
| 所要 | wall 7 分 13 秒 (スクリプト表示 433 s)・load 0.49 0.48 0.46 → 1.10 0.94 0.71・nproc 4・exit 0 |
| judge | JUDGE PASS (14/14 gates) |
| S1 (soft) | `872/1/47/22/0` (base `872/1/47/22/0`) |
| B1 boot parity | PASS (units_run 52 = base 52) |
| R1・R2 | PASS (R2 reached 33 / floor 19) |
| P1〜P5・W1・A1・L1 | PASS (P4 `hwnd=0x110000f`・P5 `hwnd=0x110000e`) |
| ネガコン N1〜N9 | 9 件すべて期待どおり FAIL |
| selftest / pe_image | 506 passed 0 failed / PASS |

WIN-13 (`37cc1097`) の記録は 13/14 (S1 `870/1/47/24/0` で FAIL)。今回は 14/14 (S1 = base)。IR 入力が同じかは **未確認** (下記)。差の原因は未切り分け (§9-7)。

IR 指紋 (fix で追記。e2e は再実行していない): 素材展開直後の `tools/m11/work/` (`work-m11` の tar を展開) の sha256 は、`boot_final.ll` `69c774ded8aaf717c66d765925ff7435c65771ba63db952243daf5c5a7932a43`・`boot_final3.ll` `010451add5147d37cd06d8d0043255fcb2e65a536c4eadeff17e7ce43de7cb9e`。展開直後の `boot_final3.ll` には `CreateFruityInstance` の定義が無い (boot7 取込前)。この 2 値は main の素材 raw の記録 (`REPORT_APPENDIX.md` §7-7 の `69c774…`・`010451…`) と一致する。一方、`results/ir_sha256.txt` の material 行 (`7bf7a29a…`・`c763f8b9…`) とは一致しない。§7-7 によれば、この material 行は boot7 なし run で `m11_gen_ir2.sh` により再生成された後に残った値で、素材 raw ではない。よって『IR 入力の差ではない』とは言えない。e2e の build 入力 (gen_ir2 後の IR) の sha256 はこの fix では取得していないため、一致は未確認。

### 9-7. shim の検査と未解決

- `bash tools/shim/test.sh`: rc 0・2.5 秒・53 API × MT/ST 全 PASS。`gcc -Wall -c tools/shim/src/sync.c` の警告 3 件は既存 (`emscripten_get_now` の暗黙宣言ほか)。変更行には無い。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot の `unreachable` の地点と理由 | `CreateFruityInstance` の前に boot が止まる | 子 issue `[WIN-16]` (`親: #2880`) |
| `0x12bd390` の登録経路 (どの unit が初期化するか) | 呼出しの完了 (受入 3) | 同上 |
| 呼出元 VA (wasm name section 無し) | 受入 1 の呼出元 VA | 同上 |
| 解放側 `function_41cd70` が init 列に入る理由 | boot が 41cd70 に届くと `0x11EAF00` を削除する (推定) | 同上 |
| S1 の差 (§9-6 の 13/14 と 14/14) | 判定の再現性 | PR 本文の未解決表のみ (再測定) |
| (解消) 現 HEAD での `cfi_probe.mjs` の再測定 | `adad27ad` で再測定し、9-3 と同じ値 (§9-8) | — |

### 9-8. 差分の証跡と再測定の状況 (#3191 差し戻し)

`git diff --stat ae963e28 7a8fe50c -- tools/shim tools/gui/flengine/cfi_probe.mjs` の出力 (`7a8fe50c` は main 取り込み後の commit。以後の commit は shim と `cfi_probe.mjs` を変えない):

```
tools/shim/REPORT.md        | 52 +++++++++++++++++++++++++++++++++++++++++++-
tools/shim/src/heap.c       |  5 +++--
tools/shim/test/test_main.c | 11 +++++++---
3 files changed, 61 insertions(+), 7 deletions(-)
```

- 差分の中身: `tools/shim/src/heap.c` の HeapFree は、割当てのない p を FALSE・`ERROR_INVALID_FUNCTION` から TRUE・`ERROR_SUCCESS` に変えた (commit `7278e857`・#2821)。`tools/shim/test/test_main.c` は同じ変更の検査。`cfi_probe.mjs` に差分は無い。`tools/shim/src/sync.c` (CS-MISS の出力元) にも差分は無い。
- cfi_probe の GUI 実行は `tools/shim` を使う (`tools/gui/flengine/e2e.sh` の複製元) ため、9-3 の結果は HeapFree の変更の影響を受け得る。影響の有無は未測定。
- 差分の証跡 (`ae963e28` → `adad27ad`): `git diff --stat ae963e28 adad27ad -- tools/shim tools/gui/flengine/cfi_probe.mjs` は上の 3 ファイル (61+/7-) と同じ。
- 再測定 (commit `adad27ad`・#3191 差し戻し round 2): 素材 `fl-win64 toolchain-retdec toolchain-emsdk work-m11` (`work-liftdiff` は未使用)。toolchain は `/opt/` に展開済みのものを使った (`EMSDK_ENV=/opt/emsdk/emsdk_env.sh`・`RETDEC=/opt/retdec/bin/retdec-decompiler`)。fl-win64 は `FL_WIN64_DIR` へ手で展開し、work-m11 は作業ツリーの `tools/m11/work` へ複製した (gitignore)。`apt-mingw` は oc_artifacts に無いため `gcc-mingw-w64-x86-64` を apt で入れた (§9-2 (2))。

| 手順 (`adad27ad`) | 結果 (実測) |
|---|---|
| `gf_seed_closure.py --pe $FL_WIN64_DIR/extracted/block00031_PE.bin --ir tools/m11/work/boot_final3.ll --seed 0x1375990` | 3 秒・closure 6,591 / 1,965,676 B・既存 4,520・新規 2,071 / 761,038 B (§9-2 と一致) |
| `m11_lift.sh <絶対パス>/boot_ranges_cfi.txt boot7 780` | rc 0・3 分 19 秒・`boot7.lift.ll` 222,014 行 |
| `m11_gen_ir2.sh` | rc 0・1 分 20 秒 |
| `m11_build.sh` | rc 0・37 秒・signature mismatch 0 / undefined 0 |
| `gui/flengine/build.sh` | rc 0・28 秒・`m11_gui.cjs` (signature 0 / undefined 0 / duplicate 0) |
| `node tools/gui/flengine/cfi_probe.mjs` | rc 0・0.5 秒 |

- 結果 (9-3 の表と同じ): boot_enter `unreachable`・`CreateFruityInstance` は `Aborted`・1 ms・iface `0x0`・最後の shim 行 `[shim] CS-MISS key=0x12bd390` → `FAIL-FAST: unimplemented Win32 API: EnterCriticalSection`・GUI-REACH `LoadStringW` ×3・icall_miss 5。値は変わらないので、`boot_metric.py` の再生成は出典の `file_last_commit` だけが変わる。
- `m11_image.bin` は work-m11 の展開物 (10 月の値) をそのまま使った。`m11_build.sh` はこれを書かない (`m11_e2e.sh` 等が書く)。PE 由来の画像で、boot7 の IR 追加では変わらないと推定する (未確認)。
- 差分の確認 (WORKFLOW §6): `git diff adad27ad HEAD -- tools/shim tools/gui/flengine/cfi_probe.mjs` の出力は 0 行 (本 PR の最終 commit で確認)。
- 扱い: 9-3 の表は `adad27ad` の実測 (値は `ae963e28` と同じ)。`flengine-cfi-probe` の record の `commit`・STATUS 先頭行・REPORT §8-6 は `adad27ad` に合わせた。以後、tools/shim か cfi_probe.mjs に差分が出たら再測定する (WORKFLOW §6)。
