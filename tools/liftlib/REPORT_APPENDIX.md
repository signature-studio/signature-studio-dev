# 付録: HB-H3 (#93) iargs pass の実装・実測 — tools/liftlib/

> **正本**: `tools/liftlib/REPORT.md` (結論・§1〜§16)。本書は 250 行上限 (`docs/DOC_MAP.md` §1) のため
> 本体から**そのまま分割移動**した §17 の全文 (節番号は本体の参照と一致)。移動後の修正は §17.7 (#427) に追記。

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
| 3 | REPORT.md が 250 行上限超過 | §17 を本書へ**そのまま分割移動** (削除なし)。REPORT.md 側は要約 + link |
| 4 | REPORT の外部絶対パス | §17 冒頭の runner 絶対パスを `[ANALYSIS-PLUGINS]` と repo 相対 `work/` の記述に置換 |

実測 (runner 4 core, 直列):
- `iargs.scan()` (OTT `ott.drc.ll`, base 正規化後): define_short **15** / sites_short **15** / sites_entry **17** (7 caller / 引数位置のべ 17)。`run()` 後の再走査は **0 / 0 / 0**。sites_entry はすべて引数個数は足りているが入口素通し位置の IR 引数が別値の site (`function_180127550` → `function_180126920` の k=1..3 ほか)。なお引数不足 site (sites_short) 内の入口素通し位置は 9 (`run()` の `args_entry_fixed` 26 = 17 + 9)。
- unit T16 に被覆追加: 検出前 17 件、復元後 0 件、復元済み ctor 呼出しの rcx を `undef` に戻すと `sites_entry` が検出 (逆方向)。
- `python3 tools/liftlib/tests/test_unit.py` のうち T7〜T16: **PASS** (T1〜T5 も ok。T6 は FA の SlateCore を要し `work-liftlib-targets` 未取得のため未実行)。T7〜T16 の合計 160 s / load average 0.97。
- `python3 -m liftlib leafspec targets/ott_iargs.json --n 200`: **match=200 mismatch=0 (200/200)**, gate PASS, 23.6 s。
- ネガコン (同 json の `passes.iargs=false`): **match=0 mismatch=200 (0/200)**, 2.9 s。

未解決: `tools/liftlib/lowbase_e2e.sh` の `DLL=/home/ubuntu/...` 固定 (bash。`tools/shared/env.sh` の `PLUGINS_DIR` 経由への置換が要る。#427 の 4 点の範囲外) → 起票先は PR 本文に記載 (PM が `[LIFTLIB-n]` で起票)。
