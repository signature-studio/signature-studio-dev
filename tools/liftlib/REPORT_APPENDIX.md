# 付録: HB-H3 (#93) iargs pass / LIFTLIB #241 (ymm・pcmpistri・F2 xmm 戻り) の実装・実測 — tools/liftlib/

> **正本**: `tools/liftlib/REPORT.md` (結論・§1〜§18)。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため
> 本体から**そのまま分割移動**した §17・§18 の全文 (節番号は本体の参照と一致)。移動後の修正は §17.7 (#427) と §18.6 (#241 検証記述の更新) に追記。

## 17. HB-H3 (#93): 整数引数脱落 (D3) の機械検出・復元 pass `iargs` + getParameter xmm0 戻りの実測

既知類型との関係: `tools/ott/REPORT.md` §2.2 **D3** (call site の r8/r9 脱落) と `docs/DEFECTS.md` D5 (xmm 引数落ち = f2) の**整数版**。DEFECTS.md の D1a〜D16 に同型なし → 新類型として本節に記録 (DEFECTS.md への転記は PM 判断)。
検証起点: `origin/main` = 0a9e9d3。素材: `plugins-ott toolchain-retdec toolchain-emsdk work-m6-ott work-liftlib analysis-ott-binaries` (`ANALYSIS_DIR` = `[ANALYSIS-PLUGINS]` の親 (`docs/REFERENCES.md`) に `analysis-ott-binaries` を展開、`tools/{m6,ott,liftlib,m8,m9,m10}/work` は素材展開物 (repo 相対の `work/`・gitignore))。

### 17.1 実装 (`liftlib/passes/iargs.py`, pipeline の `passes.iargs`, 既定 off)
- 機械語を正本に、関数ごとの整数引数位置 live(f) = 自前 live-in (rcx/rdx/r8/r9) ∪ 直接 call・関数外 tail-jmp 先の live(g) のうち**入口値のまま素通しする位置** (推移閉包)。
- 検出 `iargs.scan()`: IR の仮引数が `max(live)+1` 未満の define / 引数が足りない call site を列挙。
- 復元 `iargs.run()`: define/declare に `i64 %argN` を追加 → 全 call site で (a) 入口値素通し位置は呼出元自身の `%argN` (b) 不足位置は到達定義から bind (IR 値 / 即値 / `lea` 合成 / rip 相対 `mov r32,[rip+x]` の load 合成)。bind 不能は 0 を渡し `site_unbound` と site VA をログ (黙って 0 にしない)。冪等。
- f2 (xmm 引数) の**前**に流す (f2 は仮引数末尾へ `%xmmK_bits` を足すため)。f2 と同じ機械語 live-in 方式の兄弟 pass とし、#50 の共通 pass 群 (liftlib) に統合した。#90 (icall) 経路は別 (§17.4)。
- harness: `diff.py` に spec の `mask_ranges` (環境依存値 = vtable の絶対 VA を比較から除く) を追加。

### 17.2 実測 (OTT `ott.drc.ll` raw, base 正規化後。runner 4 core, 直列)
| 項目 | 結果 |
|---|---|
| 検出 (`iargs.scan`) | 169 関数中 **define 15 / call site 15** が不足 (function_180127550 は IR 1 引数 vs 機械語 4 引数 (rcx..r9 を callee `180126920` へ素通し) ほか) |
| 復元 | define 15・declare 3 修正、call site 24 書換 (入口素通し 26 引数 + 追加 14 引数)。再走査 **0 / 0**、2 回目は変更 0 (unit T16) |
| 核心事例 | `function_18011d400` (OTTProcessor ctor) の呼出し `function_180127550(%arg1)` → `(%arg1, %arg2, 1, 20)` = numPrograms=1 / numParams=0x14 (`mov r9d,0x14; lea r8d,[r9-0x13]`) |
| native 突合 (`leafspec targets/ott_iargs.json --n 200`, 実機機械語 VA 敷設・乱数 ctor 引数 (audioMaster/numPrograms/numParams) × 200) | iargs **ON: 200/200 一致** (this バッファ全 byte、vtable 絶対 VA 欄のみ mask)。**ネガコン (iargs OFF): 0/200 一致** (+0x20/+0x24 等 numPrograms/numParams 欄が 0) |
| 既存 leaf 5 spec (`ott_leaf.json`, n=40) の ON/OFF 比較 | exp 40/40・log 32/32 (crash 8 除外)・tan 11/40・svf 2/40・cvt 11/40 — **ON/OFF で完全に同一** (回帰なし。tan/svf/cvt の不一致は本 pass と無関係な既存状態) |
| unit | `tests/test_unit.py` T7〜T16 ok (T6 以前の FA 依存 test は素材 `work-liftlib-targets` 未取得で未実行 — T1〜T5 は ok) |
| 残 unbound | 3 site: `1801a3117` (rdx = `movzx edx,dl` の合成未対応), `1801c162b` / `1801c1752` (r8 = `mov r8d,[rbp+0x5f]` の rbp 相対 load) → 0 を渡す。いずれも memset/stos 系 CRT と GUI 周辺で OTT の ctor/DSP 経路外 |

### 17.3 getParameter の xmm0 戻り (`function_18011e5a0`, RetDec route): **未達**
- 機械語は `ret_in_xmm0()=True` (jump table 31 path が `movss xmm0,[rcx+off]; ret`)。leafabi (`ret_xmm0`) を当てた lift の native 突合 (`idx` 0..19 × 200): **0/200** (wasm 側 xmm0 は常に 0)。
- 原因は xmm0 ではなく**上流**: RetDec が `jmp r8` の jump table (D10, `tools/icall/REPORT.md` §4) を落とし、`idx<31` 経路を `ret sext(idx)` に潰している (IR 実測: `ret i64 %4` = 引数の符号拡張)。xmm0 を拾う ret は stack 経路 (`[rsp+0x38]`) 1 本だけ残る。→ jump table 復元が先に必要 (icall の `icall_rewrite.py` D10 展開が既に対処)。
- x64c route (tools/ott/lift) では getParameter の xmm0 返値は #92 で native と 20/20 bit 一致済み (REPORT h2 §3 G2)。

### 17.4 統合判断 (#50 / #90 / x64c)
| 経路 | D3 (整数引数脱落) | 備考 |
|---|---|---|
| x64c (tools/ott/lift) | **発生しない** (1:1 lift; #92 で ctor の numPrograms=1/numParams=20/flags=0x18 を実値で確認) | hostbridge の本命。H3 の「補正」は x64c では不要 |
| RetDec + icall (#90) | ABI 仮想化 (BLK 経由) で全関数 `i64 f(void)` 化し**迂回** (icall REPORT §3.1-5) | 引数復元 pass 不要 |
| RetDec + liftlib (#50 系) | **本 pass で修復** (f2 の兄弟、`passes.iargs`) | plugin closure 用に残す経路 |
→ 共通 pass への統合先は liftlib (f2/f7/p1 と同居)。icall 経路とは機構が違い (書換え vs IR 後付け) 統合しない。

### 17.5 受入条件の状況と未解決
| 項目 | 状況 |
|---|---|
| call site の整数引数脱落の機械検出 | 達成 (`iargs.scan`, 15/15 を検出) |
| 復元 pass と native 突合 | 達成 (ctor 200/200、ネガコン 0/200) |
| 戻り値 (xmm0) 復元 | **未達** (RetDec route では jump table 欠落が先 = §17.3)。x64c route は #92 で達成済み |
| #50 / #90 との統合判断 | 達成 (§17.4) |
| 未解決 | ①RetDec route の getParameter: jump table 復元 + leafabi の組合せ検証 → 新規 issue で起票 ②`iargs` 未対応の 3 site (§17.2) ③スタック渡し (5 引数目〜) は対象外 ④`liftlib_e2e.sh` 全体は未実行 (FA/KH 素材 `work-liftlib-targets` 未取得) |

### 17.6 再現
```sh
python3 tools/liftlib/tests/test_unit.py            # T16 = iargs の検出/復元/冪等 (素材: work-m6-ott, analysis-ott-binaries)
cd tools/liftlib && python3 -m liftlib leafspec targets/ott_iargs.json --n 200   # ctor 200/200 (emsdk 要)
```

### 17.7 レビュー指摘 4 点の是正 (#427, PR #416 merge 後の Copilot 指摘)
検証起点: `origin/main` = 578fa45 + 本 PR の差分。素材: §17 冒頭と同じ。`/home/ubuntu` の symlink は作らずに実行 (`ANALYSIS_DIR` = runner の `analysis-ott-binaries` 展開先)。

| # | 指摘 | 是正 |
|---|---|---|
| 1 | `scan()` の `sites_entry` が常に空 | **実装を選択** (検出不能が意図ではない: `run()` は同じ判定 `defs_before(C, reg) == {0}` で修理している)。`scan()` が各 call site の callee live 位置 k について、IR に引数 k があり・機械語の到達定義が入口のみで・IR 引数が呼出元自身の `%arg{k+1}` でも `run()` 生成の `%ia_*` でもないものを `sites_entry` に列挙 |
| 2 | `targets/ott_iargs.json` の `/home/ubuntu` 固定 | target json の `image` を `${OTT_DLL}` にし、`pipeline.rpath()` が `liftlib/env.py` の `PATH_VARS` (`ANALYSIS_DIR` / `PLUGINS_DIR` / `OTT_DLL`) で展開。同じ固定パスを持つ `targets/ott_leaf.json`・`tests/test_unit.py`・`p1_residual_census.py`・`xmm0_ret_census.py` も `env.OTT_DLL` に統一 (`lowbase_e2e.sh` は範囲外: 未解決) |
| 3 | REPORT.md が 250 行上限超過 | §17 を本書へ**そのまま分割移動** (削除なし)。REPORT.md 側は要約 + link。**REPORT.md は 644 → 600 行 (実測 `wc -l`) で 250 行上限には未達** (§1〜§16 が先行 PR で既に 550 行超。追加の分割移動は別チケット) |
| 4 | REPORT の外部絶対パス | §17 冒頭の runner 絶対パスを `[ANALYSIS-PLUGINS]` と repo 相対 `work/` の記述に置換 |

実測 (runner 4 core, 直列):
- `iargs.scan()` (OTT `ott.drc.ll`, base 正規化後): define_short **15** / sites_short **15** / sites_entry **17** (7 caller / 引数位置のべ 17)。`run()` 後の再走査は **0 / 0 / 0**。sites_entry はすべて引数個数は足りているが入口素通し位置の IR 引数が別値の site (`function_180127550` → `function_180126920` の k=1..3 ほか)。なお引数不足 site (sites_short) 内の入口素通し位置は 9 (`run()` の `args_entry_fixed` 26 = 17 + 9)。
- unit T16 に被覆追加: 検出前 17 件、復元後 0 件、復元済み ctor 呼出しの rcx を `undef` に戻すと `sites_entry` が検出 (逆方向)。
- unit: T7〜T16 **PASS** (T1〜T5 も ok。T6 は FA の SlateCore を要し `work-liftlib-targets` 未取得のため未実行)。T7〜T16 一括 160 s / load 0.97。コミット済み HEAD `2db928d` での T16 単体 **123.4 s** / load 0.94 (scan を 4 回走らせるため)。
- `python3 -m liftlib leafspec targets/ott_iargs.json --n 200`: **match=200 mismatch=0 (200/200)**, gate PASS, 23.6 s。
- ネガコン (同 json の `passes.iargs=false`): **match=0 mismatch=200 (0/200)**, 2.9 s。

未解決: `tools/liftlib/lowbase_e2e.sh` の `DLL=/home/ubuntu/...` 固定 (bash。`tools/shared/env.sh` の `PLUGINS_DIR` 経由への置換が要る。#427 の 4 点の範囲外) → 起票先は PR 本文に記載 (PM が `[LIFTLIB-n]` で起票)。

## 18. LIFTLIB #241 — ymm(i256) helper ABI + pcmpistri + F2 xmm 戻り搬送

- 既知類型との関係: **該当なし** (`docs/DEFECTS.md` D1a〜D16 / `icall §4` とも未登録。新類型行案は §18.7)
- 検証起点 commit: `main` = `400d546` (着手時)。初回の数値はコミット済み HEAD `8476a82` の clean worktree (`git worktree add --detach`) で再現して取得。
  その後 main 取り込みの merge commit が入ったため、`8476a82` の数値が有効かと再測定は §18.6。
- 環境: GitHub Actions runner (nproc=4, emcc 6.0.12, gcc `-mavx2 -mfma`)。初回 run は **`tools/m6/work` / `targets/*/work` が未展開**で
  FA/KH/OTT の回帰 (`liftlib_e2e.sh` の (a)(b)(c)(f)) は未実施だった。後続の review run (素材あり) と本更新 run で実施済み (§18.6)。

### 18.1 結論

| 項目 | 着手前 | 本 run (実測) |
|---|---|---|
| `simd report` 未被覆 (効果/共通基盤/合算/host 込) | 1/1/2/2 (`pcmpistri` / `vinsertf128`) | **0/0/0/0** |
| `simd test` mismatch | 0 (192 mnemonic / 281 form / 95,400 vec) | **0** (223 mnemonic / 347 form / 182,400 vec: exact 181,895 / approx_ok 505) |
| ymm(i256) 形の helper | 未対応 (stub = trap) | **生成 + 実機突合** (64 mnemonic・179 命令インスタンス) |
| `pcmpistri` | 未対応 | **imm8 全 128 値 × 2 形 (void / i32) = 256 命令インスタンスを実機突合 mismatch 0** |
| F2 xmm 戻り搬送 (OTT 実 DLL leaf 3 callee) | 検出器なし | 検出 3 callee / 11 ret → 搬送 9 → 残 2。注入 **9/9 検出** (偽陽性 0) |

### 18.2 ymm(i256) の ABI (wasm32 の実測に基づく)

C は `i256` を表現できないが、LLVM IR の i256 は wasm32 で **引数 = i64 ×4 に分割 / 戻り値 = sret (先頭 i32 引数)** に lower される
(`clang --target=wasm32-unknown-emscripten -S` の `.functype` で実測: `f (i32, i64×8) -> ()` ← `i256 f(i256, i256)`,
`h (i32, i64×6)` ← `i128 h(i128, i256)` は sret を持たず `i128` 戻りは別規約に注意)。
- `gen.py`: i256 引数は `u64 pN_0..pN_3` に平坦化し prologue で `Y` (= `struct{u64 q[4]}`) に束ねる。戻り値は C の `Y` 返し (wasm32 の C ABI は
  struct 戻りを sret にするので IR の i256 戻りと一致)。`liftlib_simd.h` に `Y`/`YLO`/`YHI`/`MKY`。
- 128bit レーン独立の packed 命令 (`YMM_LANEWISE` 62 mnemonic) は xmm 版 kernel を下位/上位に適用 (`Spec.lanes`)。レーン横断は個別実装:
  `vinsertf128` / `vextractf128` / `vperm2f128` / `vshufpd` (ymm 版は上位レーンが imm bit[3:2] を使う — 実機突合で判明し個別化)。
- **突合方法**: C は i256 を書けないので `simdtest.wasm_ir()` が **LLVM IR wrapper** (`load i256` → `call i256 @helper` → `store i256`) を生成し、
  emcc で C と一緒にリンクする。native 側は gcc inline asm (`v256` / `-mavx2`) の実 ymm 命令。ABI 不一致は mismatch として現れる (§18.4 NC2)。

### 18.3 pcmpistri

`liftlib_simd.h: ll_pcmpistr()` に SSE4.2 implicit-length 文字列比較の全 imm8 (要素幅 ub/uw/sb/sw × 集約 4 種 × 極性 4 種 × 出力 LSB/MSB) を実装。
RetDec は `void(i128,i128,i8)` と lift し ECX/EFLAGS を捨てる → **void 形は shadow global (`ll_pcmpistr_ecx` / `ll_pcmpistr_fl`)** に結果を残す
(フラグ消費は P1 系 pass が担う方針は不変。ECX/フラグを後続が読む配線は未実装 — §18.7)。`d` 形 (ECX を返す) も同一実装。
実機突合は ECX + EFLAGS[CF,ZF,SF,OF] (pushfq) を比較、imm8 0..127 全値。

### 18.4 ネガティブコントロール (1 件を壊して FAIL を確認)

| 検査 | 壊し方 | 結果 (`simd test --n 200`) |
|---|---|---|
| NC1 | `vinsertf128` の imm 解釈を反転 | **BAD 1 form** (mismatch 検出) |
| NC2 | i256 戻りの hi/lo 反転 (`MKY`) | mismatch **29,752** / bad_forms 56 (ABI・レーン順の破壊を検出) |
| NC3 | `pcmpistri` の極性 (negative) 処理を無効化 | mismatch **12,800** / bad_forms 2 |

### 18.5 F2 xmm 戻り搬送 (`f2.xmm_ret_scan` / `run_xmm_ret`)

- 検出: 機械語の**到達可能な全 ret で xmm0 が関数内定義** (`MFunc.ret_in_xmm0`、LIFTLIB-3) なのに、IR の `ret i64/i32` が leafabi の差した
  `%lf_<va>_t*` (xmm0 由来) でない callee。修復は `leafabi.run` (ret → xmm0 bits / call 直後の最初の xmm0 読み → call 戻り) を該当 callee に適用。
- 入力 (再現): OTT インストーラ (`plugins-ott` 素材) から `OTT_x64.dll` を 7z 展開し、`retdec-decompiler -m bin --select-ranges
  0x1801b4220-0x1801b4615,0x1801a9be0-0x1801aa193,0x1801aa1a0-0x1801aa378 -o leaf OTT_x64.dll` (実測 54 s) → `leaf.ll` (5 define)。
  `LL_XRET_LL=leaf.ll LL_XRET_DLL=OTT_x64.dll` を設定すると `inject-eval` と unit T17b が走る (未設定なら skip)。
- 実測 (定義: 1 件 = 1 ret 命令 / 1 callee = 1 define): 検出 **3 callee (exp 1801b4220 8 ret / tan kernel 1801aa1a0 2 ret / 1801b4610 1 ret) = 11 ret**
  → 搬送 **9 ret** (exp 7 + tan kernel 2) → 修復後も未搬送 **2 ret**。
- 注入評価 (`inject.eval_f2_xret`): 搬送済み 9 ret を `ret i64 0` に 1 件ずつ戻し scan が検出するか → **9/9 検出**。`inject-eval` 全体 RESULT
  `injected=9 detected=9 false_positive_on_clean=0` (この run は FA/KH/OTT 入力が無く xret のみ)。
- 残 2 ret (実測: `ret_unbound 2`, 機械語 VA で特定): (1) `function_1801b4220` の `ret` @`1801b4474` — 複数経路 (@1801b43db/43fb/4430 ほか) が
  `jmp 0x1801b4470` で合流する共有 ret で、xmm0 の到達定義が複数 (多定義 phi) のため leafabi の bind が値を 1 つに決められない
  (IR 側は `ret i64 %rax.0.reload`)。(2) `function_1801b4610` の `ret` @`1801b4614` — RetDec が関数全体を `ret i64 (xor 0,0)` 1 本に
  退化させており (機械語は `vpxor xmm0` + 合流先)、xmm0 の元値が IR に無い。どちらも「合流先 ret の多定義 xmm0」で LIFTLIB-4 の領域 phi 合成と同系 (**未解決表へ**)。
- `tan` 本体 `1801a9be0` は `ret_in_xmm0()` が False (entry/call の phi が ret に混ざる、LIFTLIB-4 §14.7 と同件) のため対象外。

### 18.6 検証 (実測秒・load average・並列数)

**(1) 初回実装 run** — clean HEAD `8476a82`、素材は `fl-win64` のみ:

| 検証 | 結果 | real | load average (nproc=4) |
|---|---|---|---|
| `python3 -m liftlib simd test --n 200` (clean HEAD `8476a82`) | 223 mnemonic / 347 form / 182,400 vec: exact 181,895 / approx_ok 505 / **mismatch 0** | 5.8 秒 | 0.33 / 0.37 / 0.24 |
| `python3 -m liftlib simd report` | 未被覆 0/0/0/0 | — | — |
| `python3 -m liftlib inject-eval` (`LL_XRET_*` 設定) | injected 9 / detected 9 / false_positive 0 | — | — |
| unit T5 / T17a / T17b | 全 ok | — | — |
| 着手前ベースライン `simd test` (400d546) | 192 mnemonic / 281 form / 95,400 vec / mismatch 0 | 2.8 秒 | — |

**(2) review run の独立再実行 (reviewer 実測)** — HEAD `fb5ef01` (merge commit 2 本の後)、素材あり (`plugins-ott`・`toolchain-*`・`work-*`・`analysis-ott-binaries`):

| 検証 | 結果 | real |
|---|---|---|
| `simd test --n 200` | 223 mnemonic / 347 form / 182,400 vec: exact 181,895 / approx_ok 505 / **mismatch 0** | 7.5 秒 (load 0.4) |
| `simd report` | 4 分類すべて 未被覆 0 | — |
| unit T1〜T17 (`LL_XRET_*` なし) | **全 PASS** (T17b は skip) | — |
| T17b + `inject-eval` (`OTT_x64.dll` を `plugins-ott` から 7z 展開 → RetDec `--select-ranges` で `leaf.ll` 再生成) | 検出 3 callee / 11 ret → 搬送 9 → 残 2。注入 **9/9**。`inject-eval` 全体 `injected=103 detected=103 false_positive=0` | — |
| `liftlib regress` FA Gain | **BIT-EXACT 400/400** | — |
| `liftlib regress` KH Gain | **BIT-EXACT 366/366** | — |
| `liftlib regress` OTT (既定 auto f7,p1) | checks 8 / broken 0 / census junkHi 104 ≤ 104 → **PASS** | — |
| leafspec | RESULT: PASS (exp 40/40, log gate PASS) | — |
| 同 HEAD の 2 回目 review run: `simd test` / `simd report` / unit T5・T17a / ネガコン NC2 | mismatch 0 / 未被覆 0 / ok / NC2 は BAD で検出し復元後 mismatch 0 | 4.9 秒 (load 0.85 / 0.74 / 0.32) |

`regress` の `ott_auto_none` (旧既定 `--auto none`) は FAIL (census junkHi 175)。reviewer が origin/main `89a1a30` でも census 値まで同一の FAIL を確認しており、**本 PR 起因ではない** (追跡: #478)。

**#478 の調査結果 (本 run の再測定: 現 main では `ott_auto_none` は再現しない。元の FAIL の環境差は未特定)**:

検証起点 HEAD `58be557` (origin/main `c4404a7` を merge 済み。`tools/liftlib` の差分なし)、nproc=4、並列なし。素材は PR 本文の `oc_artifacts` 7 本 (`plugins-ott`・`toolchain-emsdk`・`toolchain-retdec`・`work-liftlib`・`work-liftlib-targets`・`work-m6-ott`・`analysis-ott-binaries`)。
`tools/{m6,m8,m9,m10,ott,liftlib}/work` と `OTT_vst2_win64.dll` の実在を `ls` で確認した (`tools/m10/work` は `work-m6-ott` が供給する)。

| 実行 | 結果 | real (load 実行前) |
|---|---|---|
| `python3 -m liftlib ott --auto none` (依存未導入) | `liftlib/pe.py:10 import pefile` で `ModuleNotFoundError` (ott.drc.ll の読込には到達しない) | — |
| 同 (pefile/capstone/numpy を `$RUNNER_TEMP` の uv venv に導入、node は `/opt/emsdk/node/24.19.0_64bit/bin`) | **RESULT: PASS (rc 0)**。IR 一致 O1/O2a/O2b/O2c/O3a/O3b/O4 全て `true`、checks 8 / broken 0、maxdev 0.0 / nbad 0、trap rc 0、census[0x248]=0 junkHi 175、outhash 42/42 equal (f0 21/21) | 9.207 秒 (load 1.25) |
| `python3 -m liftlib regress` | `{"fa_gain":"PASS","kh_gain":"PASS","ott":"PASS","ott_auto_none":"PASS"}`、rc 0 | 31.283 秒 (load 1.09) |

- コード読み (`cli.py` `cmd_ott`): `--auto none` の合否に census 閾値は無い。`r["pass"]` (checks/maxdev/nbad/trap) と `all(v is True for v in ident.values())` (7 段 IR 一致) と outhash 突合のみ。junkHi 175 は表示値で FAIL 条件ではない。
- コード読み (`recipes/ott.py:57-60`・`cli.py:179`): 参照 `.ll` (`tools/m6/work/{ott_lift,ir7e_p1..p3,ott_memfix0,1}.ll`・`tools/m10/work/ott_m10.ll`) が無いと `same()` が `None` を返し FAIL する。これは参照欠落時の挙動で、**元の FAIL の説明としては未確認** (本 run は欠落状態を再現していない)。
- 元の FAIL (census junkHi 175 を伴う FAIL 報告) は、素材・依存が揃った現 main では再現しない。元の run の素材構成・依存・HEAD との差は未特定 (推定: 素材欠落または依存未導入。未実測)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 元の FAIL の環境差の切り分け (素材構成・依存・当時の HEAD の突合) | #478 の受入条件 1 の「FAIL 原因」は現 main で再現しないため確定できない。ott_auto_none を PASS にする修正 (条件 2) は現 main では不要 | #478 (not-reproducible で閉じるか環境差を追加調査するかは PM 判断) |

**(3) 本更新 run の再測定** — HEAD `e86e6e8` (origin/main `91a83a5` を merge 済み)、nproc=4、並列なし。素材は `plugins-ott`・`toolchain-retdec`・`toolchain-emsdk`・`work-liftlib`・`work-liftlib-targets` のみ
(RetDec の raw `.ll` は `work-liftlib` のキャッシュで `--fresh` ではない):

| 検証 | 結果 | real | load average (実行前) |
|---|---|---|---|
| `simd test --n 200` | 223 mnemonic / 347 form / 182,400 vec: exact 181,895 / approx_ok 505 / **mismatch 0** / bad_forms 0 | 5.115 秒 | 0.47 / 0.48 / 0.23 |
| `simd report` | 5 行すべて 未被覆 after = 0 | — | — |
| `lift targets/fa_gain.json` (FA 実機差分) | scenarios 400 / match 400 / mismatch 0 / crash 0 / trap 0 → **BIT-EXACT 400/400** | 8.695 秒 | 0.11 / 0.36 / 0.20 |
| `lift targets/kh_gain.json` (KH 実機差分) | scenarios 61 / steps 366 / match 366 / mismatch 0 → **BIT-EXACT 366/366** | 1.393 秒 | 0.25 / 0.38 / 0.21 |
| `plugins-ott` → 7z 展開 → RetDec `--select-ranges` (§18.5 の手順) | `leaf.ll` 5 define | 43.6 秒 | 0.19 / 0.36 / 0.21 |
| unit T17a + T17b (`LL_XRET_*` 設定) | 検出 3 callee / 11 ret → 搬送 9 → 残 2、注入 **9/9** 検出 | 0.576 秒 | 0.73 / 0.48 / 0.26 |
| `inject-eval` (FA / KH / xret。OTT 入力なし) | injected 27 / detected 27 / false_positive 0 (FA 5+1+2, KH 9+1, xret 9) | 1.163 秒 | 0.75 / 0.49 / 0.26 |
| unit T5 / T6 / T8 | ok | 0.0〜0.1 秒 | — |

**本更新 run で再実施できなかったもの** (reviewer 実測 (2) を根拠にする): `tools/m6/work` (`work-m6-ott`) と `$ANALYSIS_DIR` 配下の `OTT_vst2_win64.dll` (`analysis-ott-binaries`。
`[ANALYSIS-DIR]`、`docs/REFERENCES.md` §4) が無いため、OTT の regress・leafspec・`liftlib_e2e.sh` 全体 (`need` で exit 2)・unit T1〜T4 / T7 は実行不可。
T10〜T16 は `skip (OTT raw .ll 無し)` を出して return する実装で、実行されたことにならない (PASS とは数えない)。
T9 は skip ガードが `m6_rt.c` の有無だけを見るため、`m6/work/m6_stubs_hand.c` が無いと期待値 4 件が成立せず AssertionError になる (素材欠落起因。本 PR は t9 を変更していない)。

**検証起点 `8476a82` は merge commit の後も有効か**:
- 本 PR の実装 6 ファイル (`simd/gen.py`・`simd/kernels.py`・`simd/liftlib_simd.h`・`simd/simdtest.py`・`passes/f2.py`・`inject.py`) は `8476a82` と `e86e6e8` で**差分なし**
  (`git diff --quiet 8476a82 HEAD -- <6 ファイル>` が 0)。`cli.py` の差は REPORT の節参照を書いたコメント/docstring のみ。
  よって `simd test` / `simd report` / F2 xmm 戻りの `8476a82` の数値は有効で、(2)(3) の再測定でも同値だった (mismatch 0、9/9)。
- merge で main から入った変更は `passes/iargs.py` (新規。`passes.iargs` は既定 off)・`pipeline.py`・`harness/diff.py` (`mask_ranges`)・`recipes/ott.py`・targets/specs/`test_unit.py` (t16)。
  `pipeline.py` / `harness/diff.py` は FA/KH の lift 経路に載るため、`8476a82` の数値は流用せず、FA/KH は `fb5ef01` (2) と `e86e6e8` (3) で再測定した (400/400・366/366)。
  `8476a82` の時点では FA/KH/OTT 回帰は未実施だったので、その根拠はこの再測定に置く。
- `fb5ef01` → `e86e6e8` の liftlib の py 差分は `cli.py`・`recipes/ott.py` のコメント (REPORT §12 → `REPORT_APPENDIX_A.md` §12) のみで、挙動は不変。

`gen.py` の変更は i256/pcmpistri を含む宣言だけに効く分岐で、既存形の生成コードは不変 (`simd test` の既存 477 命令インスタンスが全て mismatch 0 で維持)。
FA/KH の実 IR への影響は上記の再測定で無し。OTT の実 IR は reviewer 実測 (2) のみ。
liftdiff の 4 スナップショット (`ir_instr.ll`) の declare で C 生成 → emcc コンパイルを試行: `ott_old` は 156/156 生成・emcc OK、`m11*` 4 本は
**未知型 (`?` 型: cpuid / rep_movsq 等) の stub が `void` 変数宣言で emcc 失敗** (既存 stub 経路の欠陥、本 #241 の範囲外・§18.7)。

### 18.7 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **解消**: FA/KH/OTT 回帰を本変更で再実行できていない (初回 run 時点) | §18.6 (2)(3) で FA 400/400・KH 366/366・OTT PASS を確認 (OTT は reviewer 実測のみ)。`work-liftlib` / `work-liftlib-targets` は R2 allowlist 済み (`docs/WORKFLOW.md` §11) | 新規子チケットは不要になった (最終判断は PM)。`liftlib_e2e.sh` 全体・OTT・unit T1〜T4 / T7 / T9〜T16 の再現には `oc_artifacts` に `work-m6-ott` + `analysis-ott-binaries` が要る |
| `pcmpistri` の ECX/フラグを後続命令へ配線 (void 形は shadow global に残すのみ) | KH/OTT の実 IR で pcmpistri 結果を消費する経路は未接続 | 新規子チケット (P1 系 pass の flags 配線) |
| F2 xmm 戻り 残 2 ret (合流先 ret の多定義 xmm0 phi: 1801b4474 / 1801b4614) | 該当経路で xmm0 を返さない | 既存 #272 系 (領域 phi 合成) へコメント |
| F2 xmm 戻りのスタック引数・GPR 引数個数不一致 | issue 記載の F2 未対応面のうち本 run は xmm 戻りのみ | 新規子チケット |
| `gen.py` stub が未知型 (`?`) で `void` 変数宣言になり emcc 失敗 (m11 snapshot 4 本で実測) | 未知型を含む IR の helper 生成 | 新規子チケット |
| ymm 幅変更/レーン横断の命令 (vcvtdq2pd ymm・vpmovmskb ymm・vperm*d・vbroadcast*) は未実装 | Convolver / Filter Table の実 closure で必要になる可能性 | 親 #50 に提案 |

### 18.8 新類型行案 (DEFECTS.md 形式)

| 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 | 修復 |
|---|---|---|---|---|
| xmm0 で結果を返す関数が `ret i64 <rax 側ゴミ>` に lift され caller に garbage が流れる | RetDec は戻りレジスタを rax/xmm0 で区別せず `ret i64` に一律化 | OTT exp 1801b4220: 8 ret 中 8 が未搬送 / tan kernel 2/2 | 機械語の全 ret で xmm0 が関数内定義かつ IR の ret が xmm0 由来でない | `f2.run_xmm_ret` → `leafabi.run` |
| ymm 引数を C helper の `u128` 2 個と誤宣言すると wasm ABI がずれ上位レーンが落ちる | wasm32 は i256 を i64×4 に分割し戻りは sret | 本 run NC2 (レーン順反転で mismatch 29,752) | helper 署名と IR declare の i256 数の不一致 | `gen._params` (u64×4 平坦化 + Y 戻り) |
