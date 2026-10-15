# tools/plugins/reverb_delay/REPORT.md — PLG-F4 (#201) reverb-delay 9 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/reverb_delay/` のみ (生成物は `tools/plugins/work/` = gitignore) / 検証起点 commit: **8a68603** (e2e 3 回・nega 1 回。 §8 の表は 8a68603 の実測。 以降の commit で判定・鎖の設定を変えており、最終 HEAD の再実測は §8 の別行)
- 手法: 先行 PR #506 (`tools/plugins/dynamics/`、b1480188 で merge 済み) の e2e・matrix 突合・ID 検算を移植し、#506 の reviewer 指摘 (判定が不合格でも exit 0 / 判定そのものの NC 欠如) を**最初から**避けた (§2)。#506 のファイルには依存しない
- icall 鎖 (2 つ): 既定の `batch_lift.sh` は `PLUG_ICALL=1` (icall 復元あり)、`lift_ranges.sh` (engine / nega の L2) は既定 `PLUG_ICALL=0` (従来鎖)。 本書の e2e・nega は `PLUG_ICALL` を明示する。 §0・§5 の「IR の間接 call」は**従来鎖 (`PLUG_ICALL=0`) の結果**であり、既定鎖では `__icall_dispatch` 呼出として現れる (§5)
- 再現: `bash tools/plugins/reverb_delay/reverb_delay_e2e.sh` (gate 付き。不合格なら exit 1) / `bash tools/plugins/reverb_delay/reverb_delay_nega.sh` (NC 22 件)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。環境は `reverb_delay/env.sh`
- 既知類型との関係: (icall §4) **D1 (間接 call 脱落)** が 9 閉包すべてで再現 (§5)。(icall §4) **D12 (Delphi unwind landing pad が CFG 非到達)** を 3 site で再現 (§5)。
  (`docs/DEFECTS.md`) D1〜D16 に該当する silent miscompile は未確認 (差分試験を未実施のため)。engine で loud な新類型 E4 / E5 / E6 を見つけた (§7、行案は §10)

## 0. 結論 (先出し)

1. **#201 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** 前提の PLG-P0a #195 / P0b #196 / P0c #197 が OPEN。
   Eff_Render 単位で native (DLL を VA 敷設して ms_abi 実行) と wasm を比べる harness も repo に無い。 → PR は **`Refs #201`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は Delphi 殻 9/9 本で通った**: `lift_rc` 0・`emcc -c` rc 0・`x86_fp80` 関数 0・未実装 `__asm_*` helper 宣言 0・`define` 数 = 閉包関数数。
   合計 **341 関数 / 188,119 B**。 T3 の殻 2 本 (Delay 3 / Multiband Delay) は `PLUGIN_MATRIX.json` に batch 欄が無く**今回が初測定**。 閉包 6 項目 + batch 4 項目の matrix 突合は **82/82 一致** (§1)。
3. **ただし通過 ≠ 正しさ**: 9 閉包の機械語には非 IAT の間接 call が計 **514 site** あるが、従来鎖 (`PLUG_ICALL=0`) の lift 後 IR (`p.final.ll`) では間接 call は **0**。 入口スロット (`Eff_Render` 等) を含む。
   (icall §4) D1 は従来鎖の結果である。 既定鎖 (`PLUG_ICALL=1`) では 514 site が `__icall_dispatch` 呼出として IR に残る (§5)。 既定鎖でも回帰ゲート `f2/icall_gate.py` は 9 閉包のうち Convolver 2 site・Delay Bank 1 site (計 3 site、D12 と推定) で F1 (missing) になる (§9)。 差分試験の前提はこの 3 site の扱いの決定。 → #514 ([PLG-F2-2]) に従来鎖の件数を追記 (既定鎖の訂正も必要。§9)。
4. **host 呼出面は P0b の応答表で覆える**: 閉包の即値 Dispatcher ID は {2, 14, 36, 50, 67} の 5 種 (計 14 site)、すべて `hs_ids.json` の 35 ID に含まれる。 別算法の独立走査も 9/9 本で取りこぼしなし (§3)。 動的 ID は Convolver の 2 site。
5. **SIMD kernel 依存は 5 本、うち 4 本 (Convolver / Delay 2 / Delay Bank / Reeverb 2) の閉包が #331 ([P0c-7]) 未解決の 0x5dee90 / 0x5df040 を呼ぶ** (§4)。 Delay 3 / Reeverb / LuxeVerb / Multiband Delay の殻は閉包内 kernel 呼出 0 site。
6. **Convolver の FFT は IPP 経由ではない (静的調査)**: IPP 関数ポインタ 420 変数のうち DLL 全体で参照する関数は Convolver 5 / LuxeVerb 4 / 他 7 本 0 で、名前は Move / Zero / Add / MulC のみ。 FFT 系 (`fft`/`dft`/`conv`/`corr`) の参照は 0。 → #38 ([IPP-10]) 側の FFT 代替は Convolver に不要と推定 (§6、範囲は§6 の但し書き)。
7. **T3 の C++ engine 2 本は `emcc -c` 未通過**: Delay 3 engine (19000) は RetDec 完走だが IR 型エラー (E1 → E4) で止まる。 **Multiband Delay engine (19165) は RetDec が `.text` の 78/2,078 関数で落ちる (`Should not be possible.`) ため IR が出ない。** 78 関数を除いても E6 / E1 / zext 定数式で止まる。
   78 関数は AVX2/AVX-512 命令 (`vpermpd` / `vpermd` / `vpexpandd` / `vshufi32x4` / `valignd`) を含み、残り 2,000 関数は 1 本も含まない (§7)。 さらに 272 関数 / 513,403 B は静的リンクされた Intel IPP (`IPPCODE` section)。

## 1. 閉包 lift 結果 (Delphi 殻 9 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Eff_Render ほか) から `call/jmp rel32` で到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。
frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。 vcall / ptr = 間接呼出 site 数。 iat = IAT 経由 Win32 呼出 site。 lift 秒 = `status.csv` の seconds (`lift_ranges.sh` のみ)。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Fruity Convolver | 18992 | T1 | 99 / 56,026 | 240 / 47,536 | 135 | 45 | 1 | 99 | 0 | 0 | 0 | 5 |
| Fruity Delay | 18996 | T0 | 17 / 5,088 | 36 / 4,493 | 15 | 7 | 0 | 17 | 0 | 0 | 0 | 2 |
| Fruity Delay 2 | 18998 | T0 | 18 / 12,988 | 58 / 10,540 | 16 | 5 | 2 | 18 | 0 | 0 | 0 | 2 |
| Fruity Delay 3 (殻) | 18999 | T3 | 24 / 11,468 | 55 / 10,349 | 29 | 5 | 0 | 24 | 0 | 0 | 0 | 2 |
| Fruity Delay Bank | 19002 | T1 | 37 / 19,447 | 75 / 12,378 | 50 | 16 | 4 | 37 | 0 | 0 | 0 | 2 |
| Fruity Reeverb | 19067 | T1 | 14 / 9,977 | 42 / 5,049 | 8 | 3 | 0 | 14 | 0 | 0 | 0 | 2 |
| Fruity Reeverb 2 | 19069 | T1 | 24 / 16,707 | 72 / 13,323 | 21 | 15 | 0 | 24 | 0 | 0 | 0 | 2 |
| LuxeVerb | 19146 | T1 | 53 / 37,849 | 85 / 18,404 | 61 | 9 | 0 | 53 | 0 | 0 | 0 | 3 |
| Multiband Delay (殻) | 19164 | T3 | 55 / 18,569 | 78 / 16,061 | 64 | 6 | 0 | 55 | 0 | 0 | 0 | 2 |
| 計 | | | **341 / 188,119** | | | | | 341 | 0 | 0 | 0 | 22 |

- 最右から 2 列目は `emcc -c -O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ** (§5)。
- T3 の 2 本は殻のみ。 engine は §7。 殻の直接 Win32 API は `PLUGIN_MATRIX.json` `win_direct_api` を参照 (本書は再集計していない)。
- matrix 突合 (`matrix_check.py`): 閉包 6 項目 (関数数・バイト・frontier 関数・frontier バイト・vcall・ptr) × 9 本 = 54、batch 4 項目 (lift_rc・emcc_c_rc・f80・unimpl) × 7 本 (T0/T1 のみ batch 欄あり) = 28、計 **82/82 一致**。 T3 の 2 本は閉包 6 項目のみ比較。

## 2. gate の設計 (#506 の reviewer 指摘への対応)

| gate | 何を落とすか | exit |
|---|---|---|
| `judge.py` (lift 直後) | block ごとに `lift_rc` / `emcc_c_rc` / `f80_funcs` / `declares_unimpl` が 0 でない、`defines` が 0 以下または `closure_funcs` と不一致 (`work/closure/block*.json` の `unique_funcs` とも照合)、指定 block の行欠落、非数値、列数不足、ヘッダ違い、重複行 (最後の行を採用して警告) | 不合格 1 件でも 1 |
| `matrix_check.py` | `PLUGIN_MATRIX.json` との不一致・欠落 (82 項目) | 1 |
| `ids_crosscheck.py` | 独立走査が taint 版を再現できない、ID が `hs_ids.json` に無い、検算が走らない (closure/PE 欠落) | 1 |
| `xcheck_icall.py` | audit_icall の間接 call site (VA) が線形 sweep に無い、線形 sweep だけが見える site の VA 集合が `icall_linear_only.expected` と違う | 1 |

- `reverb_delay_e2e.sh` は `set -euo pipefail` で上記が非 0 なら即終了し、最終行の `OK` は全 gate 通過後にだけ出る。 `status.csv` は追記式なので e2e 冒頭で削除する (stale 行を合格に使わない)。
- engine 2 本と IPP 調査・icall 件数表は**測定のみで gate に含めない** (出力に「測定のみ・gate 外」と明記)。

## 3. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡を閉包 ranges に限定 (`closure_facts.py`)。 slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 即値 ID (site 数) | 動的 ID | 他 slot (offset: site) |
|---|--:|---|--:|---|
| Fruity Convolver | 15 | 2 (1), 14 (1), 67 (1) | 2 | 0x100: 5, 0x108: 5 |
| Fruity Delay | 1 | 2 (1) | 0 | — |
| Fruity Delay 2 | 3 | 2 (1) | 0 | 0x100: 1, 0x108: 1 |
| Fruity Delay 3 | 2 | 2 (1), 36 (1) | 0 | — |
| Fruity Delay Bank | 11 | 2 (1) | 0 | 0x100: 5, 0x108: 5 |
| Fruity Reeverb | 1 | 2 (1) | 0 | — |
| Fruity Reeverb 2 | 3 | 2 (1) | 0 | 0x100: 1, 0x108: 1 |
| LuxeVerb | 7 | 2 (1), 50 (1) | 0 | 0x100: 2, 0x108: 2, 0x120: 1 |
| Multiband Delay | 12 | 2 (1), 36 (1) | 0 | 0x100: 5, 0x108: 5 |

- 即値 ID の distinct = {2, 14, 36, 50, 67}。 `hs_ids.json` (35 ID) に**不足 0**。 gate (`ids_crosscheck.py`) は taint 版の全 ID の被覆も判定する。
- **別算法の検算** (`ids_crosscheck.py`): taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う。 9/9 本で taint 版の ID 件数を取りこぼしなく再現し、**本走査だけが見つける ID は 0** (#506 の dynamics 7 本では ID 59 が 2 本で出た)。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 0x120 (LuxeVerb 1 site) は P0b では fail-soft + 呼出記録のみ (意味未解析)。 動的 ID 2 site (Convolver) の値は未判別。

## 4. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` で call site の所在関数を閉包 ranges / frontier に分類。 kernel 番号は Balance (block 18983) の VA に正規化済み。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site 数) | frontier 内 site | DLL 固有関数走査 site / kernel 種 |
|---|--:|---|--:|---|
| Fruity Convolver | 5 | 0x5dee50 (1), 0x5dee90 (1), 0x5df040 (2), 0x635b80 (1) | 4 | 48 / 16 |
| Fruity Delay | 4 | 0x5de5c0 (2), 0x5de790 (2) | 0 | 26 / 3 |
| Fruity Delay 2 | 2 | 0x5de820 (1), 0x5dee90 (1) | 0 | 24 / 3 |
| Fruity Delay 3 | 0 | — | 0 | 22 / 1 |
| Fruity Delay Bank | 9 | 0x5de390 (2), 0x5dee90 (2), 0x5df040 (1), 0x5df240 (1), 0x5df750 (1), 0x5dfaa0 (1), 0x5e0860 (1) | 4 | 35 / 9 |
| Fruity Reeverb | 0 | — | 0 | 22 / 1 |
| Fruity Reeverb 2 | 4 | 0x5df040 (2), 0x5df860 (1), 0x5dfc10 (1) | 2 | 29 / 7 |
| LuxeVerb | 0 | — | 0 | 27 / 5 |
| Multiband Delay | 0 | — | 0 | 22 / 1 |

- 22 site の 0x5de390 は 9 本すべてに共通し、閉包にも frontier にも属さない (framework 側の深い関数と推定、未確認)。 閉包内 site が 0 の 4 本でも DSP 本体が閉包に載っていないとは限らない (Delay 3 / Multiband Delay は engine 側 = T3、Reeverb / LuxeVerb は frontier の先は未追跡)。
- P0c の記録 (`p0c/REPORT.md` §14.4): #331 の対象は 0x5de3e0 / **0x5dee90 / 0x5df040** / 0x5e02b0 / 0x5e12b0。 該当する閉包は Convolver (両方)・Delay 2 (0x5dee90)・Delay Bank (両方)・Reeverb 2 (0x5df040) の 4 本。 0x5de390 は f64mem で 300,000 case 差分 0 (P0c §3)。 他の kernel の現状は本 PR で再測定していない。
- 0x635b80 (Convolver 1 site) は kernel 表の VA 帯 (0x5de…〜0x5e1…) の外。 `kernel_matrix.py` の正規化結果で、意味は未確認。

## 5. 間接 call 監査 ((icall §4) D1 / D12)

`tools/icall/audit_icall.py --funcs <閉包関数 VA> --ir work/batch/<block>/p.final.ll`。 「静的 site」= 閉包 ranges の非 IAT 間接 call、「IR」= `p.final.ll` で callee が `@name` でない call。 関数単位の件数比較 (`insn.addr` が無い IR のため)。
**この表は従来鎖 (`PLUG_ICALL=0`) の結果。** 既定鎖 (`PLUG_ICALL=1`) では `callee が @name でない call` が 0 のまま変わらず、間接 call は `call void @__icall_dispatch(` として現れるため、この列は既定鎖の脱落量を表さない。 既定鎖の件数は `icall_summary.py` の 2 鎖表で併記する (§8 の最終 HEAD 行)。

| プラグイン | 静的 site | call あり関数 | IR の間接 call | 入口スロットの静的間接 call (slot=n) | 入口の IR 間接 call |
|---|--:|--:|--:|---|--:|
| Fruity Convolver | 179 | 44 | 0 | Dispatcher=1, SaveRestoreState=33, ProcessParam=4, Eff_Render=8 | 0 |
| Fruity Delay | 22 | 8 | 0 | Dispatcher=2, SaveRestoreState=6, ProcessParam=2, Eff_Render=3 | 0 |
| Fruity Delay 2 | 23 | 9 | 0 | DestroyObject=1, Dispatcher=2, SaveRestoreState=4, ProcessParam=2, Eff_Render=5 | 0 |
| Fruity Delay 3 | 34 | 10 | 0 | Dispatcher=10, SaveRestoreState=6, ProcessEvent=1, ProcessParam=4, Eff_Render=3 | 0 |
| Fruity Delay Bank | 69 | 16 | 0 | SaveRestoreState=20, ProcessParam=2, Eff_Render=10 | 0 |
| Fruity Reeverb | 11 | 5 | 0 | Dispatcher=1, SaveRestoreState=6, ProcessParam=2 | 0 |
| Fruity Reeverb 2 | 36 | 13 | 0 | DestroyObject=1, Dispatcher=2, SaveRestoreState=10, ProcessParam=2, Eff_Render=3 | 0 |
| LuxeVerb | 70 | 19 | 0 | Dispatcher=6, SaveRestoreState=31, ProcessParam=2, Eff_Render=4 | 0 |
| Multiband Delay | 70 | 20 | 0 | Dispatcher=10, SaveRestoreState=24, ProcessEvent=1, ProcessParam=4, Eff_Render=3 | 0 |
| 計 | **514** | | **0** | | 0 |

- **別算法の検算** (`xcheck_icall.py`、gate): 閉包 ranges を capstone の線形 sweep で数えた非 IAT 間接 call は**合計 517**、audit の 514 より 3 site 多い。 audit にあって線形 sweep に無い site は 0。
  差の 3 site は VA を固定して gate にした (`icall_linear_only.expected`): `0x793207` / `0x875dd7` (Convolver)・`0x6d938c` (Delay Bank)。 いずれも `jmp` の直後 + `nop nop` の後にある `call [rbx-0x20]` / `call [rax+0x28]` で、
  (icall §4) D12 の Delphi unwind landing pad (try/finally の例外経路コピー; CFG の辺から到達しない) と推定する。 recursive descent の audit も RetDec も辿らないため、仮想 dtor 呼出がこの 3 site 分 IR から消える。
- 件数の等式ではなく VA 集合で比較している。 初回の件数一致版は 517 ≠ 514 で FAIL し、原因の 3 site を上記のとおり特定して gate を VA 固定に改めた。

## 6. IPP (`dsp_ippv2.dll`) の実使用 — Convolver の FFT 依存 (#201 手順の確認事項)

`ipp_use.py` (測定のみ)。 方式: framework の IPP ローダ (Delphi UnicodeString literal `dsp_ippv2.dll` / `ipp*` を参照する関数) を特定し、`lea rdx,[rip+VAR]; lea r8,[rip+"ippXxx"]` の対から関数ポインタ変数 VAR の表 (420 個) を作る。
全 `.pdata` 関数を走査して、ローダ以外で VAR を rip 相対参照する関数を求め、閉包 / frontier / 閉包から直接 call/jmp rel32 で到達できる関数 (BFS) に分類する。

| プラグイン | DLL 全体で IPP 変数を参照する関数 | 閉包内 | frontier 内 | 参照する IPP 関数名 |
|---|--:|--:|--:|---|
| Fruity Convolver | 5 | 0 | 0 | ippsMove_8u, ippsMove_32f, ippsZero_8u, ippsAdd_32f_I, ippsMulC_32f_I (5 関数は閉包の外 = 直接 call 到達のみ) |
| LuxeVerb | 4 | 0 | 0 | ippsMove_8u, ippsMove_32f, ippsZero_8u, ippsMulC_32f_I |
| 他 7 本 | 0 | 0 | 0 | — |

- **FFT 系の名前 (`fft` / `dft` / `conv` / `corr`) を参照する関数は 9 本とも 0。** ローダの 420 変数のうち FFT 系の関数ポインタを読む命令がどこにも無い。 補助確認: 変数表の範囲 [min, max+8) 内で個別変数に一致しない rip 相対参照 (添字参照の疑い) は 9 本とも 0 関数。
- ローダ関数 (13,200 B) は 9 本とも 420 変数を埋めるだけで framework 共通。 IPP が「存在するが使われない」ことの根拠は上記の参照 0 件。
- 検出器の positive control: Convolver の既知 IPP 利用関数 (`0x5c7070`) を閉包に加えた closure json で `users_in_closure` が 0 → 1 になる (NC P1)。
- **限界**: vcall / 関数ポインタ経由の呼出は辿らない (到達しない = 不使用ではない)。 ただし「DLL 全体で FFT 系変数の参照 0」は到達性に依らない。 Convolver の畳み込み本体 (`elastique` ヒントあり) が閉包内か framework 内かは未特定。
  **T3 の Multiband Delay engine (19165) は IPP を静的リンクしている** (§7)。 これは殻とは別の話で、#38 ([IPP-10]) の対象になりうる。

## 7. T3: C++ engine DLL 2 本 (測定のみ・gate 外)

| engine | block | サイズ B | `.text` B | `.pdata` 関数 / B | export | import |
|---|--:|--:|--:|--:|---|---|
| Delay 3 `engine_x64.dll` | 19000 | 1,195,008 | 798,182 | 3,632 / 757,316 | CreateEngine / MAIN / VSTPluginMain / main | KERNEL32 95・USER32 59・GDI32 14・OPENGL32 36・d3d9・ole32 ほか (GUI を内蔵) |
| Multiband Delay `engine_x64.dll` | 19165 | 3,090,432 | 1,966,885 | 2,350 / 2,417,902 | VSTPluginMain / main | KERNEL32 73 のみ。 section に **IPPCODE 543,565 B / IPPDATA** |

`engine_lift.sh <block>` で全 `.pdata` 関数を RetDec+pass 鎖 → `emcc -c` (3 回の min–max は §8):

| engine | RetDec rc | final.ll define | `.pdata` で define 無し (B) | f80 関数 | 未実装 helper | `emcc -c` | `engine_fixcmp.py` 後 |
|---|--:|--:|--:|--:|--:|--:|--:|
| 19000 Delay 3 | 0 | 4,107 | 2 / 3,632 (404 B) | 1 | 93 | 1 (E1) | 1 (E4) |
| 19165 Multiband Delay | **1** (IR 出力なし) | — | — | — | — | — | — |
| 19165 (78 関数 + IPPCODE を除外) | 完走 (`m11_simd2.py` で rc 1) | 2,608 | 2 / 2,000 (445 B) | 6 | 算出不能 (-1) | 1 (E1) | 1 (zext 定数式) |

- 19000: 最初のエラーは #506 の E1 と同型 (`'%arg3' defined with type 'i64' but expected 'ptr'`)。 `engine_fixcmp.py` で 7 operand を直すと **E4** `use of undefined value '%20'` に進む。
  E4 は `function_180013107` で、`e.rp.ll` にあった `%20 = call i64 @__asm_movaps(i128 %16)` の定義が `fix_asm_stores.py` (`e.rp.ll` → `e.st.ll`) で消え、`%23 = and i64 %20, ...` の使用だけが残る (dangling SSA use)。
  range 内部に別 define が増えた件数 (RetDec が range 内部に切り出した関数) は 475。
- 19165: RetDec が 0.35 s で `[capstone2llvmir]: Should not be possible.` を出して終了する (**E5**)。 `.pdata` を `.text` 2,078 関数に絞っても同じ (`engine_ranges.py --exclude IPPCODE`)。
  `engine_bisect.py` の二分探索 (349 試行) で、**単独で RetDec を落とす関数が 78/2,078 (286,914 B / 1,904,499 B)** と特定した。 `bisect_census.py` の命令比較: `vpermpd` (64 関数)・`vpermd` (56)・`vpexpandd` (22)・`vshufi32x4` (4)・`valignd` (2) のいずれかを含む関数は
  落ちる 78 関数では **78/78**、落ちない 2,000 関数では **0/2,000**。 相関であり、単一命令での因果確認は未実施 (RetDec の capstone2llvmir が AVX2 permute / AVX-512 を未変換と推定)。
- **78 関数と `IPPCODE` を除いた 2,000 関数 (1,617,585 B)** で再 lift (`ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges work/reverb_delay/bisect19165.out" ENGINE_TAG=_noipp_nobad bash reverb_delay/engine_lift.sh 19165`、1 回のみ実測 367 s): RetDec と pass 鎖は `final.ll` (505,860 行・define 2,608・`.pdata` で define 無し 2 関数 (445 B)・range 内部の別 define 608) まで進むが、(a) 鎖の最終段 `m11_simd2.py` が `IndexError: string index out of range` (`'abc'[i]` に 4 個以上の引数型が来る = 4 引数以上の `__asm_*` helper と推定) で rc 1 (**E6**)、(b) `emcc -c` は E1 (`'%arg3' defined with type 'i64' but expected 'ptr'`) → `engine_fixcmp.py` 4 operand 後に `zext constexprs are no longer supported` (#506 の E2 と同型)、(c) `x86_fp80` 関数 6。 つまり E5 を回避しても engine は更に 3 類型で止まる。
- 19165 の `IPPCODE` section の関数数・呼出元の切り分けは `REPORT_APPENDIX_3445.md` (#3445) §1 が正本。 IPP の static link と推定 (関数名は未解析)。 殻との結合 (LoadLibrary 経路) は未解析。 殻からの直接参照は PE 上に無い。
- 以上は到達性の実測で、engine の正しさは何も示していない。

## 8. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner)

| 項目 | 実測 |
|---|---|
| `reverb_delay_e2e.sh` 全体 (3 回連続、HEAD 8a68603) | **248 s / 241 s / 246 s**、3 回とも exit 0 で `OK` 行 1 回。 開始時 load average (1 分) 1.10 / 1.18 / 1.02。 逐次実行 (並列数 1)。 1 回目は §7 の二分探索 (1 プロセス) と重なった (重なった時間の秒は未計測) |
| 最終 HEAD `reverb_delay_e2e.sh` (prep 込み・fresh 実走、検証起点 **7a92330**) | **rc 0、779 s**。 `OK: 全 gate 通過`。 開始時 load average (1 分) 0.59、終了時 1.02。 judge 9/9・matrix_check 82/82・ids_crosscheck 9/9・xcheck_icall OK (9 行 OK)。 `icall_gate.py` (既定鎖) は rc 1 (F1 missing=3、gate 外。§9)。 9 閉包の lift は PASS、engine 19000 は `emcc -c` rc 1 (E1→E4、§7) で測定のみ |
| 最終 HEAD `reverb_delay_nega.sh` (検証起点 7a92330) | **rc 0、229 s**、開始時 load average 0.93。 **22/22 DETECTED** (E1 の e2e 実走を含む) |
| 最終 HEAD の icall 2 鎖 (`icall_summary.py`) | 既定鎖 `PLUG_ICALL=1`: 非 IAT 間接 call 514 site に対し、IR の `__icall_dispatch` 呼出 **514**・non-@name 間接 call 514。 従来鎖 `PLUG_ICALL=0`: 同 514 site に対し、IR の間接 call **0**・dispatch 0。 9 閉包の `defines` は両鎖とも 341 |
| 最終 HEAD の e2e 実行 `xcheck_icall` | 9 本とも audit = 線形 sweep (差分 3 site は `icall_linear_only.expected` の VA 固定)。 既定鎖の `icall_gate` は Convolver 2 site・Delay Bank 1 site が未被覆 (F1 missing=2 + 1 = 3) |
| 上の 3 回と nega | 8a68603 の実測 (前行まで)。 judge の列名読みと `PLUG_ICALL` 明示は最終 HEAD の行で確認 | — |
| 内訳 (9 閉包 lift の `seconds` 合計 / engine 19000 の lift 秒) | 21–25 s / 106–111 s (19165 は 1 s で RetDec 終了)。 plugin 別 (min–max): Convolver 5–5 / Delay 1–2 / Delay 2 2–2 / Delay 3 1–2 / Delay Bank 2–3 / Reeverb 2–3 / Reeverb 2 2–2 / LuxeVerb 3–4 / Multiband Delay 2–3 |
| 3 回の結果一致 | 判定列 (`status.csv` の秒を除く 9 列)・`facts.json` (同一 runner 内でバイト一致。sha256 先頭 `b49a112e` は別 runner で `1d8b3090` だったため、ハッシュの値の一致は同一 runner 内に限る)・engine 行 (秒を除く)・`ipp_use.json` の集計値・gate の出力行は 3 回とも同一 |
| `reverb_delay_nega.sh` (HEAD 8a68603) | exit 0、**158 s**、開始時 load average 0.51。 **22/22 件 DETECTED** (対照は全て rc 0 / 壊した入力は全て rc 1。 内訳は下) |
| 前提 inventory (初回のみ・`prep.sh`) | 4 分 28 秒 (`win_funcs.py` が大半。 並列 14 プロセス / 4 core)。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため `f2/mk_blockmap.py` で blockmap を再構成 |
| 最終 HEAD (commit 2cc882a: コメントと `engine_ranges.py` の flag 追加のみ変更) | `reverb_delay_e2e.sh --skip-lift` exit 0、**107 s** (judge 9/9・matrix_check 82/82・ids_crosscheck 9/9・xcheck_icall OK)。 lift・engine 段は 8a68603 の 3 回の結果を採用 |
| 最初の e2e 実行 (記録) | 1 回目は `xcheck_icall.py` が件数一致を要求して **exit 1** (Convolver 181 vs 179、Delay Bank 70 vs 69)。 原因 3 site を特定し VA 固定の gate に改めた (§5)。 gate が実際に落とした実例 |

ネガティブコントロール (`reverb_delay_nega.sh`、すべて「対照 rc 0 / 壊した入力 rc 1」):

| NC | 壊し方 | 結果 |
|---|---|---|
| J1–J9 `judge.py` | Delay `emcc_c_rc=1` / Delay 3 `lift_rc=1` / Convolver `f80_funcs=3` / LuxeVerb `declares_unimpl=5` / Delay 2 `defines`=closure_funcs-1 / Reeverb の行削除 / `emcc_c_rc='x'` / 不良の追記行 (最後の行を採用) / ヘッダ違い | 9/9 rc 1 |
| E1 e2e 実走 | `work/batch/status.csv` の Delay 行を `emcc_c_rc=1` にして `reverb_delay_e2e.sh --skip-lift` | **exit 1・`OK` 行 0 回** (#506 で露見した「不合格でも exit 0」の再発防止)。 対照 (元の csv) は exit 0 |
| M1–M3 `matrix_check.py` | Delay `closure_funcs` +1 / status の `emcc_c_rc` を matrix と食い違わせる / matrix に無い plugin | 3/3 rc 1 |
| I1–I3 `ids_crosscheck.py` | LuxeVerb の ID 50 の taint 件数 +1 / `hs_ids.json` に無い ID 999 を注入 / 存在しない block | 3/3 rc 1 |
| X1–X3 `xcheck_icall.py` | audit の site を 1 つ捨てる / audit に存在しない site を足す / expected から `0x875dd7` を消す | 3/3 rc 1 |
| L1 `emcc -c` | Delay の `final.ll` の関数 1 つから `ret` を除去 | rc 0 → rc 1 |
| L2 ranges | Delay の閉包 ranges の末尾 1 本を落として再 lift (ranges 16 → 15、define 17 → 15) し、その define 数を Delay の行に入れて `judge.py` | rc 1 (`defines=15 != closure_funcs=17`) |
| P1 `ipp_use.py` | Convolver の IPP 利用関数 `0x5c7070` を閉包 ranges に加えた closure json | `users_in_closure` 0 → 1 |

別系統の突合: 閉包 6 項目 + batch 4 項目は `PLUGIN_MATRIX.json` (別時点の測定) と 82/82 一致 (§1)。 Dispatcher ID は taint 版と線形走査版 (§3)、間接 call は recursive descent 版と線形 sweep 版 (§5) の 2 算法。


検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)、host / kernel / IPP 依存の静的な数え上げ、IR の間接 call 件数 (関数単位)。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。 範囲外の項目について、本書は何も主張しない。

## 9. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Eff_Render 単位の native / wasm harness が無く、P0a/P0b/P0c 未完 | #201 を閉じられない | #195 / #196 / #197 の完了後に #201 を再開 (Closes はその時)。 harness は #506 REPORT §6 が提案した [PLG-F3a] と共通 (PM 未起票。重複起票しない) |
| Render test .flp の E2E (出口条件 4)。 RT 列が付くのは Convolver / Delay 2 / Delay Bank / Reeverb / Reeverb 2 の 5 本 | 同上 | FLEngine 統合待ち。 親 #14 / #201 |
| 非 IAT 間接 call 514 site の脱落 (D1、従来鎖の結果) と、audit が辿れない 3 site (D12) | 9 本すべて。 従来鎖では差分試験は必ず不一致 | #514 ([PLG-F2-2]) に従来鎖の件数を追記。 既定鎖での訂正は本 PR のコメントで扱う (#514 への訂正コメントは PM が起票先を判断) |
| 既定鎖 (`PLUG_ICALL=1`) の `icall_gate.py` F1 missing=3 (0x793207 / 0x875dd7 / 0x6d938c、D12 と推定) | `reverb_delay_e2e.sh` は `icall_gate.py` を gate 外 (`set +e`) で実行するため e2e は `OK` を出す。 waive は `f2/icall_gate_waivers.json` (18979 の 1 件のみ) に無い | 起票先 (PM 判断): #514 の子 issue として D12 の landing pad を追跡するか、既存 #514 に追記するか。 `icall_linear_only.expected` と `icall_gate_waivers.json` のどちらを正本にするかも同時に決める |
| C++ engine 2 本 (Delay 3 / Multiband Delay): E1・E4・E5・E6、19165 の `IPPCODE` (静的リンク IPP) | T3 の 2 本 | **#523 ([PLG-F4-2])** を起票 |
| #331 の 0x5dee90 / 0x5df040 に依存する閉包 4 本 | kernel の保証 | #331 に追記済み |
| 動的 ID 2 site (Convolver)・slot 0x120 ×1 (LuxeVerb)・ID 14 / 67 の応答 | host 呼出面の意味 | #196 に追記済み |
| Delay 3 engine の f80 1 関数・0x635b80 (Convolver)・0x5de390 22 site の所在 | kernel / f80 の網羅 | #197 に追記済み |
| Convolver の畳み込み本体の所在と、vcall / 関数ポインタ経由の IPP 利用の有無 (§6 の限界) | Convolver の工数 (T1 見積) | #38 に追記済み。 所在の特定は #201 の差分試験時 |
| `win_funcs.py` が 4 core で数分かかり Actions の 60 分枠を圧迫 (`prep.sh`) | 再実行コスト | `tools/plugins/f2/REPORT.md` §5 と同件。 work 素材化は #293 の allowlist 追加を PM が判断 |
| `PLUGIN_MATRIX.json` に T3 殻 2 本の batch 欄が無い (今回の lift_rc 0 / `emcc -c` 0 は未反映) | matrix 側の記録 | `tier.py` が `work/batch/status.csv` から生成する自動生成物。 反映は PM 判断 (人手編集禁止) |


## 10. DEFECTS.md 行案 (候補・いずれも loud。 追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | 19000 Delay 3 engine (#506 の E1 と同型) | emcc "defined with type 'i64' but expected 'ptr'" | `engine_fixcmp.py` (局所)。 `fix_ptr_params.py` の拡張が本筋 |
| E4 dangling SSA use | `fix_asm_stores.py` が `%N = call @__asm_movaps(i128)` の定義を消し、`%N` の使用が残る | 19000 の `function_180013107` | emcc "use of undefined value '%20'" | 未修復 (定義を消す条件に「使用が無い」確認を足す) |
| E5 RetDec capstone2llvmir 異常終了 | `[capstone2llvmir]: Should not be possible.` で IR 出力なし | 19165 の 78 関数 (AVX2/AVX-512 permute 系を含む) | RetDec rc 1 + `.ll` 無し | 未修復 (対象命令の変換追加、または該当関数の除外/別経路) |
| E6 m11_simd2 の helper 引数数 | `m11_simd2.py` が 4 引数以上の `__asm_*` helper で `'abc'[i]` の IndexError | 19165 (78 関数 + IPPCODE 除外後) | lift の終了コード 1 + `e.simd.log` の traceback | 未修復 (引数名を 3 個固定でなく生成する) |

## 11. 成果物

| ファイル | 内容 |
|---|---|
| `reverb_delay_e2e.sh` | prep → 9 閉包 → batch_lift → `judge.py` → `closure_facts.py` → `matrix_check.py` → `ids_crosscheck.py` → icall 監査 + `xcheck_icall.py` → `ipp_use.py` → engine 2 本 |
| `reverb_delay_nega.sh` | NC 22 件 (judge 9・e2e 実走 1・matrix 3・ids 3・xcheck 3・lift 鎖 2・ipp 1) |
| `judge.py` `matrix_check.py` `ids_crosscheck.py` `xcheck_icall.py` + `icall_linear_only.expected` | 各 gate |
| `closure_facts.py` `icall_summary.py` `ipp_use.py` | 閉包 / host / kernel / engine 外形、icall 集計表、IPP 実使用 (測定) |
| `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` `engine_bisect.py` `bisect_census.py` | engine の全 `.pdata` lift・欠落監査・局所修復・RetDec 落ち関数の二分探索と命令比較 |
| `prep.sh` `env.sh` | 前提 inventory (`f2/mk_blockmap.py` で blockmap 再構成) / 環境 |

## 12. #523 (PLG-F4-2) 追補: engine 再測定と E6 修復

- 日付: 2026-10-13 / 作業ブランチ `523-plg-f4-2-engine-lift` の起点は main 97f28539 (E6 修正 b5372ec3 はその後に積まれ、main 986e7415 に入った。§13 の測定起点は 986e7415)。 素材 `fl-win64` / `toolchain-*` / `work-*` / `plugins-ott` は `$HOME/artifacts` に実在確認。
- **E6 修復**: `lift/passes/m11_simd2.py` の仮引数名 `'abc'[i]` を `'abcdefghijklmnop'[i]` に変更 (4 引数以上の `__asm_*` helper で IndexError)。 synthetic IR (3 引数 2 本) で旧版と出力 byte 一致 (`cmp` IDENTICAL)、4 引数 helper が宣言として生成されることを確認。 共有 lift 鎖への影響は 3 引数以下の出力不変 (既存 T0/T1 の `emcc -c` 退行確認は未実施 — 次手で要)。
- **E1 / E4 は HEAD で再現せず**: Delay 3 engine (19000) を HEAD で再 lift (`engine_lift.sh 19000`、実測 165 s): RetDec rc 0 / define 4,107 / `emcc -c` rc 1。 `emcc` の最初のエラーは E1 でなく x86_fp80 の `do not know how to soften fp_extend` / `no libcall available for frem / fp_round with type f80` (`function_1800bcb00` ほか)。 `fixcmp` 後も同じ。 `PLUG_F80_LOWER=1` を足すと `emcc -c` rc 0 (到達性のみ。 f64 化で精度は落ちる)。 REPORT §7 の E1→E4 記述は現 HEAD では再現しない (要更新)。
- **19165 (Multiband Delay) の再測定**: 78 関数を mnemonic 基準 (`vpermpd`/`vpermd`/`vpexpandd`/`vshufi32x4`/`valignd`) で `reverb_delay/avx_bad_ranges.py` により列挙 → **78 件** (§7 の 78 と一致)。 `IPPCODE` 除外 + 78 除外で `engine_lift.sh` 実測 (10 分 23 秒、15:37:59–15:48:22 UTC): RetDec rc 0、define 2,608、unimpl helper 241、f80 関数 6、`emcc -c` **rc 139 (segfault)**。 (summary.csv 実測: `19165,2000,0,2608,6,241,139,0,139,606,...`) E5 は回避、E6 は解消。 segfault は新類型で未解析。
- **未解決 (起票先: #523 継続)**: (a) 19165 `emcc -c` segfault、(b) 19000 の f80 1 関数 (`function_1800bcb00`) (`PLUG_F80_LOWER` 無しでは通らない)、(c) 78 関数の AVX2/AVX-512 命令 (E5) の変換追加、(d) IPPCODE の扱い (#38 [IPP-10] との決定)、(e) 殻との LoadLibrary 結合 (未解析)。
- 2026-10-13 の再測定 (19000 は `PLUG_F80_LOWER=1` で `emcc -c` rc 0、19165 は segfault → 次の類型 E7 `bitcast double to i80`): 詳細は `REPORT_APPENDIX.md` §13。


