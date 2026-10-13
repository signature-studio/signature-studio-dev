# tools/plugins/synth/REPORT.md — PLG-G2 (#207) synth 14 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/synth/` のみ / 検証起点 commit: §6 の表に記載 (lift 段は 21f74d4 のスクリプトで実行。 以降の差分は §6)
- 再現: `bash tools/plugins/synth/synth_e2e.sh` (lift + 判定 + 実測。非 0 で終わることがある: §0-2) / `bash tools/plugins/synth/synth_nega.sh` (ネガティブコントロール)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `synth/env.sh`
- 方法は PR #506 (`tools/plugins/dynamics/`、未マージ) と同じ。 #506 の reviewer 指摘 (不合格でも exit 0 の gate・ネガコン欠如) は最初から塞いだ (§0-2, §6)。
  #506 が未マージのため、共通の補助 (`engine_*.py`・`mk_blockmap.py`・`env.sh`) は複製した。 マージ後の共通化は PM 判断
- 既知類型との関係 (`docs/DEFECTS.md`): **D2 の修復 (`fix_asm_stores.py` の `SX_CALL`) の副作用と見られる 1 件を新規観測** (E4、§5)。 他は loud な IR 型エラーで silent miscompile ではない。
  差分試験を未実施のため D1〜D16 / batch_plan §4 の ARG・IND に該当するかは未確認

## 0. 結論 (先出し)

1. **#207 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** Gen_Render 単位で native (DLL を VA 敷設して ms_abi 実行) と
   wasm を比べる harness が repo に無く、PLG-P0a #195 / P0b #196 / P0c #197 も OPEN。 → PR は **`Refs #207`** (Closes しない)。 harness は #533 に起票。
2. **判定は fail-closed にした。** `synth/judge.py` は不合格・行欠落・数値不正・baseline 食い違いのいずれでも **exit 1**、`[synth_e2e] OK` は全検査が 0 のときだけ出る。
   実測の結果、**`synth_e2e.sh` は現状の HEAD で 21 モジュール中 PASS 9 / KNOWN 12 (起票先付きの既知不合格) で、strict (known 無視) では exit 1**。
   known.json 付きの通常実行は exit 0。 baseline にない不合格が出るか、baseline にある不合格が解消すると exit 1 (§6 の NC)。
3. **手順 1 (固有閉包の lift) は shell 12 本すべてで通った。** RetDec+pass 鎖が完走 (lift_rc 0)、`emcc -c` 通過、`x86_fp80` 関数 0、`.pdata` 範囲の define 欠落 0。
   合計 **1,200 関数 / 729,929 B**。 ただし**厳格基準 (未実装 helper 0 かつ i256 trap 0) を満たすのは 9 本**。 Harmless (helper 5 + i256 trap 6)・Kepler Exo (helper 1)・
   Wave Traveller (helper 1) は未実装 helper を宣言した (#207 本文の Harmless の記載 5 件・i256 trap 6 箇所を再現)。 **#535 (§10) で 3 本とも 0 にした: 厳格基準を満たすのは shell 12 本全部**。
   PLUGIN_MATRIX.json の記録とは 91/91 項目一致 (shell 11 本の閉包 6 項目 + batch 4 項目 ×4 本、C++ DLL 9 本の `.pdata` 関数数)。 BooBass の殻は PLUGIN_MATRIX に lift 欄が無く今回初測定。
4. **C++ x64 DLL 9 本は RetDec まで通るが 9 本とも `emcc -c` は未通過** (§5、#534)。 全 `.pdata` 関数を lift すると define 欠落が 1〜211、未実装 helper が 18〜144 (うち VEX が 10〜94)。
   Morphine は RetDec の C 生成 (HLL) 段が終わらず、IR 出力から後段を再開した (§5)。 T2/T3 の見積にはこの未知工数が残る。
5. **host 呼出面は P0b の応答表で覆える。** shell 12 本の閉包が即値 ID で発行する Dispatcher ID は {2, 3, 14, 20, 21, 36} の 6 種 (taint 版)。 `hs_ids.json` の 35 ID に**不足 0**。
   別算法 (`ids_crosscheck.py`) は 12/12 本で取りこぼしなし (§3)。 動的 ID は Wave Traveller の 2 site のみ。
6. **SIMD kernel 表への依存は Autogun / Ogun (各 5 site) と Harmless (2 site) の 3 本に限られる** (§4)。 他 8 本は閉包・frontier とも 0 site。 Wave Traveller は kernel 初期化を検出できず未測定。
7. **FL Slayer の `Slayer_Engine.dll` (x86 32bit、`.pdata` 無し) は鎖の対象外**として外形のみ記録した (#536)。

## 1. 対象と役割分類 (PLUGIN_MATRIX.json から導出: `synth/targets.py`)

14 本 = 22 モジュール。 役割は `lang` / `machine` で機械的に決める (block 番号を手書きしない)。 `targets.py --check` が 14 本・役割不明 0 を検査する。

| 役割 | 数 | モジュール | 扱い |
|---|--:|---|---|
| shell (Delphi `FP_DelphiPlug` の x64 殻) | 12 | 全 12 本 (BooBass・FL Slayer 含む) | 固有閉包を lift (`lift/batch_lift.sh`) |
| cpp-engine (MSVC C++ の x64 engine) | 7 | BooBass_Eng, Kepler, Kepler Exo, PoiZone, Sakura, Sawer, Transistor Bass | 全 `.pdata` 関数を lift (`synth/cpp_lift.sh`) |
| cpp-single (MSVC C++ の x64 単体) | 2 | Morphine, Toxic Biohazard | 同上 |
| x86 (x64 の `.pdata` 無し) | 1 | `Slayer_Engine.dll` block 22434 (179,512 B、`.text` 73,728 B、machine 0x14c) | 対象外。 外形のみ `facts.json` に記録 |

#207 本文は「engine DLL は Kepler / Kepler Exo / Transistor Bass」と書くが、PLUGIN_MATRIX では **BooBass・PoiZone・Sakura・Sawer も engine 分離型** (engine 計 7 本)。 本書は PLUGIN_MATRIX に従う。

## 2. shell 12 本: 閉包 lift 結果

定義: 閉包 = vtable override 実装から `call/jmp rel32` で到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数
(P0a の共有 wasm 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ記録)。 iat = IAT 経由 Win32 呼出 site。 lift 秒 = `batch_lift.sh` の seconds (逐次、並列数 1)。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | 未実装 helper | i256 trap | f80 関数 | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Autogun | 21151 | T1 | 186 / 87,806 | 163 / 23,993 | 170 | 105 | 3 | 190 | 0 | 0 | 0 | 0 | 14 |
| BooBass | 21204 | T2 | 15 / 4,863 | 41 / 7,372 | 23 | 2 | 0 | 15 | 0 | 0 | 0 | 0 | 2 |
| FL Slayer | 22433 | T1 | 21 / 4,812 | 28 / 3,193 | 33 | 2 | 0 | 21 | 0 | 0 | 0 | 0 | 3 |
| Harmless | 23738 | T1 | 141 / 99,087 | 148 / 29,266 | 121 | 147 | 10 | 141 | 0 | 0 | 0 | 0 | 34 |
| Kepler | 23913 | T3 | 34 / 17,897 | 64 / 11,342 | 37 | 1 | 0 | 34 | 0 | 0 | 0 | 0 | 3 |
| Kepler Exo | 23915 | T3 | 81 / 61,178 | 114 / 23,274 | 84 | 4 | 0 | 81 | 0 | 0 | 0 | 0 | 18 |
| Ogun | 24146 | T1 | 200 / 104,955 | 199 / 36,548 | 181 | 113 | 3 | 202 | 0 | 0 | 0 | 0 | 17 |
| PoiZone | 24158 | T2 | 37 / 43,590 | 69 / 22,022 | 51 | 2 | 0 | 37 | 0 | 0 | 0 | 0 | 25 |
| Sakura | 24162 | T2 | 25 / 57,607 | 68 / 18,185 | 139 | 2 | 0 | 25 | 0 | 0 | 0 | 0 | 20 |
| Sawer | 24165 | T2 | 32 / 55,355 | 76 / 18,972 | 93 | 2 | 0 | 32 | 0 | 0 | 0 | 0 | 12 |
| Transistor Bass | 24297 | T3 | 34 / 34,004 | 102 / 23,054 | 50 | 5 | 0 | 34 | 0 | 0 | 0 | 0 | 5 |
| Wave Traveller | 24315 | T2 | 394 / 158,775 | 129 / 15,299 | 199 | 139 | 3 | 396 | 0 | 0 | 0 | 0 | 41 |
| 計 | | | **1,200 / 729,929** | | | | | 1,208 | 0 | 0 | 0 | 0 | 93 |

- 最右から 2 列目は `emcc -c -O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- define が閉包関数数より多いのは Autogun (+4)・Ogun (+2)・Wave Traveller (+2) で、RetDec が range 内部に別 define を切り出したため。 閉包の開始 VA に対応する define が無い range は 12 本とも 0 (`missing_define`)。
- 未実装 helper の中身 (`work/synth/unimpl_names.txt`): Harmless = `prefetcht0` / `vaddps` (AVX) / `vmovaps` (AVX) / `cmpnltps` / `movmskps`、Kepler Exo = `rep_movsd_memcpy`、Wave Traveller = `rep_stosb_memset`。
  Harmless の i256 trap 6 箇所は #207 本文では「CPUID 分岐で SSE 路に固定」と想定されていたが、機械語を見ると分岐で守られていない (§10)。 表の 3 行は #535 後の値 (旧値は §10 の表)。
- 直接 Win32 API (`PLUGIN_MATRIX.json` の `win_direct_api`) はプラグイン単位の集計で、殻と engine の内訳が無いため本書では扱わない。
- FL Slayer の殻は 21 関数 / 4,812 B と最小。 engine (x86) 側にある DSP は本書で未追跡 (#536)。

## 3. host 呼出面 (shell 閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 即値 ID (site 数) | 動的 ID | 他 slot (offset: site) |
|---|--:|---|--:|---|
| Autogun | 47 | 36 (1) | 0 | 0x28: 2, 0x30: 4, 0x100: 19, 0x108: 19, 0x128: 2 |
| BooBass | 1 | 2 (1) | 0 | — |
| FL Slayer | 6 | — | 0 | 0x18: 1, 0x28: 1, 0x100: 2, 0x108: 2 |
| Harmless | 35 | 2 (2) / 36 (1) | 0 | 0xf8: 1, 0x28: 2, 0x30: 5, 0x100: 11, 0x108: 11, 0x128: 2 |
| Kepler | 1 | 2 (1) | 0 | — |
| Kepler Exo | 3 | 2 (1) | 0 | 0x100: 1, 0x108: 1 |
| Ogun | 51 | 2 (2) / 36 (1) | 0 | 0x28: 2, 0x30: 4, 0x100: 20, 0x108: 20, 0x128: 2 |
| PoiZone | 1 | 2 (1) | 0 | — |
| Sakura | 1 | 2 (1) | 0 | — |
| Sawer | 1 | 2 (1) | 0 | — |
| Transistor Bass | 3 | 2 (2) / 3 (1) | 0 | — |
| Wave Traveller | 23 | 2 (1) / 14 (1) / 20 (1) / 21 (1) | 2 | 0x10: 1, 0x28: 8, 0x60: 1, 0xf8: 3, 0x100: 1, 0x108: 1, 0x128: 2 |

- 即値 ID の distinct = {2, 3, 14, 20, 21, 36}。 `hs_ids.json` (35 ID) に**不足 0** (`facts.json` の `ids_not_in_hs_ids` が 12 本とも空)。
- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 12/12 本で taint 版の ID 件数を取りこぼしなく再現した。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 0x28 / 0x30 / 0x128 / 0xf8 などは P0b では 44 slot 共通の fail-soft + 呼出記録のみ (意味未解析)。
  ctor 完走 (P0b 未達部) の後に Gen_Render 到達で初めて意味が決まる (#196)。

## 4. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` を再利用し、call site の所在関数を閉包 ranges / frontier で分類 (kernel 番号は Balance の VA に正規化済み)。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site 数) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |
|---|--:|---|--:|---|
| Autogun | 5 | 0x5de390, 0x5df040, 0x5df860, 0x5dffc0, 0x5e0330 (各 1) | 2 | 48 / 16 |
| Harmless | 2 | 0x5df860, 0x6114e0 (各 1) | 0 | 36 / 11 |
| Ogun | 5 | 0x5de390, 0x5df040, 0x5df860, 0x5dffc0, 0x5e0330 (各 1) | 2 | 47 / 16 |
| BooBass, FL Slayer, Kepler, Kepler Exo, PoiZone, Sakura, Sawer, Transistor Bass | 0 | — | 0 | 22–23 / 1–2 |
| Wave Traveller | 未測定 | kernel 初期化 (`init_found`) を検出できない (framework 別構成: PLUGIN_MATRIX の一致 44% の 3 本の 1 つ) | — | — |

- 「DLL 固有関数走査」の 22 site は BooBass・Autogun・Harmless・Ogun を除く 8 本のうち 7 本に共通する数で、閉包にも frontier にも属さない (所在関数は未特定)。
- 閉包に kernel 呼出が無い 8 本は、DSP 本体が **engine DLL (別 DLL・C++)** または frontier の先にあると推定する。 kernel 単位の差分試験 (P0c) では保証できず、
  **Gen_Render 単位の差分試験が必須** (#533)。

## 5. C++ x64 DLL 9 本 (engine 7 + 単体 2)

`synth/cpp_lift.sh <block>` で全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通した結果。 RetDec rc は 9 本とも 0。 lift 秒は RetDec の C 生成段の待ち (最大 300 s) を含み、
Morphine は後段のみの秒 (下記)。

| DLL | block | 種別 | `.pdata` 関数 | サイズ B | define | 欠落 define | 未実装 helper (うち VEX) | i256 trap | f80 関数 | `emcc -c` | 局所修復後 | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| BooBass_Eng | 21202 | engine | 1,579 | 851,968 | 1,393 | **211** | 18 (10) | 3 | 0 | 1 | 1 | 64 |
| Kepler engine | 23914 | engine | 3,194 | 2,717,696 | 3,697 | 2 | 122 (79) | 3 | 0 | 1 | 1 | 223 |
| Kepler Exo engine | 23916 | engine | 3,193 | 2,717,696 | 3,694 | 2 | 123 (79) | 3 | 1 | 1 | 1 | 224 |
| Morphine | 23944 | 単体 | 3,050 | 1,745,408 | 3,321 | 1 | 144 (94) | 24 | 0 | 1 | 1 | 95 |
| PoiZone engine | 24159 | engine | 1,638 | 632,320 | 1,790 | 1 | 119 (74) | 3 | 0 | 1 | 1 | 68 |
| Sakura engine | 24163 | engine | 1,644 | 639,488 | 1,707 | 1 | 102 (68) | 3 | 1 | 1 | 1 | 81 |
| Sawer engine | 24167 | engine | 1,676 | 653,824 | 1,833 | 1 | 101 (66) | 3 | 1 | 1 | 1 | 79 |
| Toxic Biohazard | 24216 | 単体 | 1,841 | 755,200 | 1,927 | 1 | 112 (73) | 3 | 1 | 1 | 1 | 43 |
| Transistor Bass engine | 24298 | engine | 3,257 | 1,630,720 | 3,741 | 2 | 101 (72) | 3 | 0 | 1 | 1 | 206 |

- `欠落 define` = `.pdata` 関数のうち、開始 VA の `function_<VA>` define が final.ll に無い数 (`engine_defs.py`)。 BooBass_Eng は 211 件 (25,828 B) で突出し、うち 67 件が call 先として参照される (link 時に未解決)。
  他は 1〜2 件 (61〜111 B)。 `i256 trap` は m11_simd2 の宣言、`未実装 helper` は distinct 宣言数 (`work/synth/unimpl_names.txt`)。 VEX = 名前が `asm_v*`。
- **Morphine の lift**: RetDec は IR 出力 (`e.drc.ll` 44,712,059 B) まで 60 s で終えたが、続く C 生成段が 691 s (kill 時点で RetDec 開始から 751 s) 経っても終わらず、RetDec だけを kill して `e.drc.ll` から後段 pass 鎖を再開した
  (後段 95 s)。 後段は `.ll` しか使わない。 `cpp_lift.sh` は `e.drc.ll` の最終更新から `HLL_CAP` 秒 (既定 300) で同じ処理を自動で行う。 検証: Toxic Biohazard に `HLL_CAP=2` を与えて kill→再開させ、
  全ての結果列が通常経路 (run 1) と一致 (lift 秒のみ 115 → 43)。 Morphine を通常経路 (kill 無し) で最後まで回した実測は無い。
- 失敗の連鎖 (clang は最初のエラーで止まるため 1 件ずつ露見)。 `局所修復` = `engine_fixcmp.py` (icmp の ptr/i64 混在を `inttoptr` で直す。 共有鎖には未組込):

| 類型 | 症状 | 最初に当たる DLL | 修復後に当たる DLL |
|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) → "defined with type 'i64' but expected 'ptr'" | 21202, 23914, 23916, 23944, 24159, 24163, 24167, 24216 (8 本) | — (局所修復で解消) |
| E2 SSA 値入りの定数式 | `bitcast (i64 %ce0n11_function_… to double)` (24298)。 23944 では hoist された `zext 0 to i64` が壊れた形 (`expected type`) | 24298 (修復前から) | 23944 (修復後) |
| E3 i32 仮引数の i64 使用 | `inttoptr i64 %arg2` で arg2 は i32 | — | 21202 |
| E4 def だけ消えて use が残る | `%18 = call i64 @__asm_movaps(i128 %14)` / `%19 = sext …` の def が消え `and i64 %18, …` が残る → "use of undefined value" | — | 23914 (原因特定済み)、23916 (同じ値番号 `%18`)、24159, 24163, 24167, 24216 (同じエラー種別。 原因が同型かは未確認) |

  E4 は 23914 の `function_1800280c7` で追跡した。 `e.rp.ll` には def 2 行があり、`fix_asm_stores.py` (`rp` → `st`) の段で消える (`SX_CALL` は D2 の `movaps` 符号拡張の修復)。
- engine は KERNEL32 に加え USER32 / GDI32 / OPENGL32 (36 import) / d3d9 / WINMM を import する engine がある (Kepler・Kepler Exo・Transistor Bass: OPENGL32 36・d3d9 1)。 UI 描画を含む DLL を
  全 `.pdata` で lift しており、DSP のみの閉包ではない。 DSP の閉包抽出は未実施 (#534)。
- 以上は到達性の実測で、正しさは何も示していない。

## 6. 検証 (HEAD は下表。 4 core / 15 GiB の Actions runner)

| 項目 | 実測 |
|---|---|
| 前提 inventory (初回のみ。 `win_scan` / `mk_blockmap` / `win_funcs` / `win_unique` / `win_abi` / `kernel_table`) | 616 s (`win_funcs.py` が 14 プロセスを 4 core に立てる。 実行中の load average (1 分) 16.5〜16.8)。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため、`mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |
| lift 段の全体実行 (`synth_e2e.sh`、`JOBS=2`、スクリプトは 21f74d4。 `known.json` は空) | 1,326 s。 開始時 load average 10.84 (inventory 直後)、終了時 1.27。 shell 12 本の lift 秒の合計 149 s (逐次)。 C++ DLL 8 本は §5 の秒。 Morphine は 751 s の時点で RetDec を手動 kill し、`RESUME=1` で後段を再開 (後段 95 s)。 この run の judge は baseline が空のため NEW-FAIL 12 で **exit 1** (§0-2 の通り、不合格を落とす) |
| Morphine 後の再実行 (`synth_e2e.sh --skip-lift`、HEAD 92a7762) | exit 0、191 s。 `facts.json` / `status.csv` を保存 |
| **コミット済み HEAD 39d0200 の `synth_e2e.sh --skip-lift`** | **exit 0、189 s** (開始時 load average 0.45)。 matrix_check 91/91、ids_crosscheck 12/12、judge: PASS 9 / KNOWN 12 / NEW-FAIL 0 / FIXED 0 / MISSING 0。 strict: PASS 9 / NEW-FAIL 12 (**exit 1**)。 `facts.json` は 92a7762 の run と**バイト一致** (sha256 先頭 7dc1c45a6450d97a)、`status.csv` は lift 秒の列を除いて一致 |
| **HEAD 39d0200 の `synth_nega.sh`** | **exit 0、11 s**: NC1〜NC5 すべて期待通り (下記) |
| `--skip-lift` の意味 | lift 結果は前回の `work/` を使う。 lift 段そのもの (shell 12 本 + C++ 8 本の通常経路) を HEAD で再実行した実測は無い。 21f74d4 以降に変わった lift 段のスクリプトは `cpp_lift.sh` の HLL_CAP 処理のみで、結果列の一致を Toxic Biohazard で確認した (§5)。 Morphine を HLL_CAP 経路で通した実測は無い (手動 kill + `RESUME=1`)。 全工程のクリーン worktree 再現は未実施 (60 分の上限内に収まらない: inventory 616 s + lift 約 1,300 s) |

ネガティブコントロール (`synth_nega.sh`、FL Slayer 22433 ほか。 数値は上の HEAD の実行ログ):
- NC1: `final.ll` の関数 1 つの `ret` を除去 → `emcc -c` が **rc 1** (無改変は rc 0)。
- NC2: 閉包 ranges の末尾 1 つ (`function_853e90`) を落として再 lift → ranges 20 → 19、その define は 1 → 0、全体の define は 21 → 19。
- NC3: define 1 件を別名化 → `engine_defs.py` の missing が 0 → **1**。 final.ll 欠落は **-1** (judge は -1 を不合格とする)。
- NC4 (`nega_judge.py`、`synth_e2e.sh --judge-only` 経由 = 配線ごと): 実測 status.csv を 1 箇所だけ壊した 15 ケースすべてで **rc 1・`[synth_e2e] OK` が出ない**。 control は rc 0・OK 行あり。
  ケース: `emcc_c_rc=1` / `lift_rc=1` + `f80_funcs=3` / `declares_unimpl=5` / `i256_trap=2` / `missing_define=1` / `defines=0` / `declares_unimpl=-1` (ログ欠落の印) / 行削除 / 行重複 / 数値でない値 /
  baseline に載っているのに解消した行 (FIXED) / KNOWN 行の `ref` 欠落 / KNOWN 行への未登録の不合格追加 / KNOWN の登録削除 / `--strict`。 各ケースで judge の集計行に期待した種別 (NEW-FAIL / MISSING / FIXED) の件数が 1 以上であることも確認する。
- NC5: `matrix_check.py` は Autogun の `closure_funcs` を +1 すると 91/91 → **90/91、rc 1**。 `ids_crosscheck.py` は Autogun の ID 36 の件数を +1000 すると 12/12 → **11/12、rc 1**。
- **ネガコン自身の欠陥を 1 件見つけて直した**: 初回 (92a7762) の NC4 は合成 CSV を `close` せずに judge へ渡したため、全ケースで judge は「行 0 件 = MISSING 21」を見て rc 1 を返し、
  全ケースが偽の「期待通り」になりかけた (control だけが NG になって露見)。 修正 (39d0200) で `with open` にし、さらに「期待した種別の件数が 1 以上」の検査を足した。
  rc だけを見るネガコンは、別の理由で落ちても緑になる。

別系統の突合: Dispatcher ID の独立走査は §3 の通り。 閉包 6 項目と batch 4 項目・C++ DLL の `.pdata` 関数数は PLUGIN_MATRIX.json と 91/91 一致 (§0-3)。

検証範囲: 閉包・C++ DLL の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)、host / kernel 依存の静的な数え上げ、判定の識別力。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp。 範囲外の項目について、本書は何も主張しない。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Gen_Render 単位の native / wasm harness が無く、P0a/P0b/P0c 未完 | #207 を閉じられない | #533 (新規)。 前提 #195 / #196 / #197 |
| Render test .flp の E2E (出口条件 4)。 対象 RT 列 Y は Autogun / BooBass / Harmless / Ogun / PoiZone / Sakura / Sawer / Wave Traveller | 同上 | FLEngine 統合待ち。 親 #14 / #207 |
| C++ DLL 9 本の `emcc -c` 未通過 (E1〜E4、VEX helper、define 欠落、UI/GL を含む engine) | T2/T3 の 7 本 + Morphine / Toxic | #534 (新規) |
| (解消) 未実装 helper 7 件と Harmless の i256 trap 6 箇所 | shell 3 本 | #535 で解消 (§10)。 C++ DLL 9 本の helper は #534 |
| FL Slayer の x86 engine | FL Slayer の DSP | #536 (新規) |
| Morphine を通常経路 (HLL 段まで) で最後まで回した実測が無い | Morphine の lift 秒 | #534 |
| host slot (0x28 / 0x30 / 0x128 / 0xf8 ほか) と動的 ID 2 site の意味 | Autogun / Harmless / Ogun / Wave Traveller | #196 作業 5 |
| Wave Traveller の kernel 依存 (初期化未検出) | §4 | #197 / #195 の統合時 |
| 22 site (0x5de390) の所在 (閉包外・frontier 外) | §4 の解釈 | #197 / #195 の統合時 |
| `nsis_names.py` が Actions 上で動かない (`block_manifest.json` 不在) | inventory の再現性 | `mk_blockmap.py` で回避済み。 `docs/WORKFLOW.md` §11 への追記は PM 判断 |
| `synth/` と #506 の `dynamics/` の補助スクリプト複製 | 保守 | #506 マージ後に共通化 (PM 判断) |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 |

## 8. DEFECTS.md 行案 (候補。 追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | C++ DLL 9 本中 8 本 (#506 の engine 2 本と同型) | emcc "defined with type 'i64' but expected 'ptr'" | `synth/engine_fixcmp.py` (局所)。 `fix_ptr_params.py` の拡張が本筋 |
| E2 SSA 値入りの定数式 | 定数式 (`bitcast`/`zext`) の中に関数ローカルの SSA 値、または hoist 後に型が欠けた `zext 0 to i64` | Transistor Bass engine (24298)、Morphine (23944 は E1 修復後) | emcc "invalid use of function-local name" / "expected type" | 未修復 |
| E3 i32 仮引数の i64 使用 | `inttoptr i64 %arg2` で arg2 は i32 | BooBass_Eng (E1 修復後) | emcc "defined with type 'i32' but expected 'i64'" | 未修復 |
| E4 D2 修復の副作用 | `fix_asm_stores.py` の `SX_CALL` が `movaps` の `call`+`sext` の def を消し、その値を使う命令が残る | Kepler engine の `function_1800280c7` ほか 5 本 (計 6 本、E1 修復後) | emcc "use of undefined value" | 未修復 (def を消す条件に「全 use が store 経路」を加える) |

## 9. 成果物

| ファイル | 内容 |
|---|---|
| `synth_e2e.sh` | 対象導出 → shell 12 閉包 batch_lift → C++ DLL 9 本 cpp_lift → `mk_status.py` → `closure_facts.py` → `matrix_check.py` / `ids_crosscheck.py` / `judge.py`。 `--skip-lift` / `--judge-only <csv>` |
| `judge.py` `known.json` | 判定 (PASS / KNOWN / NEW-FAIL / FIXED / MISSING)。 不合格で exit 1。 `known.json` = 既知不合格の baseline (起票先 `ref` 必須) |
| `synth_nega.sh` `nega_judge.py` | ネガティブコントロール (emcc / ranges / define 監査 / judge 16 ケース / matrix_check / ids_crosscheck) |
| `helper_diff/` (`helper_diff.sh` `helper_diff.c` `synth.ll`) | #535: helper の native 差分試験 + ネガコン 8 件 (§10)。 `bash tools/plugins/synth/helper_diff/helper_diff.sh` |
| `targets.py` `mk_status.py` `cpp_lift.sh` `simd_stats.py` `f80_count.py` | 対象導出 / 判定用 CSV 統合 / C++ DLL の lift / 補助 |
| `closure_facts.py` `matrix_check.py` `ids_crosscheck.py` | 閉包・host ID・kernel・外形 → `work/synth/facts.json` / PLUGIN_MATRIX 突合 / Dispatcher ID の別算法検算 |
| `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` `mk_blockmap.py` `env.sh` | #506 から複製した補助 (`engine_defs.py` は引数を一般化) |

## 10. #535: 未実装 helper 7 件と i256 trap の解消

既知類型との関係 (`docs/DEFECTS.md`): 該当なし (silent miscompile ではなく、helper 未実装を loud に宣言していた欠落の補完。 差分試験で命令単位の bit 一致を確認した)。 検証起点 commit: aef6120 (下表の `--skip-lift` / `synth_nega.sh` / `helper_diff.sh` は aef6120 で再実行して同じ結果。 f251ca6 以降の変更は helper_diff の 128bit vaddps 検査の追加のみ)。

| 旧 (§2 の記録) | 原因 | 対処 |
|---|---|---|
| Harmless `prefetcht0` / `cmpnltps` / `movmskps` | `m11_simd2.py` に実装が無い | `m11_simd2.py` に実装: `prefetcht*` (no-op) / `cmp{eq,lt,le,unord,neq,nlt,nle,ord}{ps,pd}` / `movmsk{ps,pd}` |
| Harmless `vaddps__8` / `vmovaps__9` (128bit VEX) と ymm の i256 trap 6 箇所 (`vmovaps` / `vsubps` / `vmulps` / `vaddps` / `vextractf128` / `vmovaps__10`) | `function_745c00` (VA 0x745c00) が **ymm を無条件に使う** AVX 関数。 呼出元は 0x7467f8 の 1 箇所で、`[rip+..]` の機能 bit 0x40000 が立っている時だけ到達する。 この bit は 0x5a39a4 で CPUID (`ecx & 0x18000000`) と `xgetbv` (0x5a37b3、`eax & 6`) の両方を通った時に立つ | **CPUID 固定ではなく IR へ lower** (新 pass `lift/passes/fix_avx256.py`、`lift_ranges.sh` の `m11_passes` 直後): ymm の `v{add,sub,mul,div,min,max}ps`・`vmov*`・`vextractf128`・VEX store 形を `<8 x float>` 演算 / `store` へ。 C の i256 ABI (wasm の sret / 引数分割) に依存しない。 128bit の VEX `v{add,..}ps` / `vmov*` は `m11_simd2.py` の SSE 実装に合流 |
| Kepler Exo `rep_movsd_memcpy` | 実装無し | `m11_simd2.py`: dst が src の直後で重なる場合も前方コピー意味を保持 |
| Wave Traveller `rep_stosb_memset` | 実装無し | `m11_simd2.py` の `memset(a, b & 0xff, c)` (al のみ有効)。 これは本 PR と並行して #538 (main) が同内容で実装済みで、マージ (146f168) で 1 箇所になった。 本 PR の `helper_diff` はこれも native `rep stosb` と比較する |

- #207 本文は「CPUID 分岐で SSE 路に固定」を想定していたが、0x745c00 自体は分岐を持たない (呼出元の機能 bit が分岐)。 CPUID 側の返値表 (`m11_simd2.py` の `CPUID_BODY` は SSE2 まで、`xgetbv` は 0) は維持したので、wasm では通常 0x745c00 に到達しない。 lower 済みなので到達しても trap しない。
- `synth/cpp_lift.sh` は `PLUG_AVX256=0` (既定) で C++ DLL 9 本の結果列を #535 の pass で変えない (#534 の領分)。 実測: 9 本は KNOWN のまま (judge: NEW-FAIL 0 / FIXED 0)。

実測 (4 core / 15 GiB の Actions runner):

| 項目 | 実測 |
|---|---|
| `[simd2]` 行 (Harmless / Kepler Exo / Wave Traveller) | declares 62 / 36 / 44: implemented 62 / 36 / 44、**unimplemented 0 / 0 / 0、i256 trap 0 / 0 / 0**。 `fix_avx256` (Harmless): ymm 演算 lower 32 件 / VEX store 復元 8 件 / 不要 declare 除去 7 件。 3 本とも `emcc -c` rc 0 |
| `bash synth/helper_diff/helper_diff.sh` (native 実命令との差分。 `-mavx2`、N=200000、HEAD aef6120) | **checks=12,040,001 mismatches=0**、exit 0、7 秒。 検査: cmpnltps / movmskps (NaN・±0・inf 混在) / prefetcht0 / rep movsd (重なり・長さ 0 含む) / rep stosb (al の上位ビットを無視) / ymm の 6 演算 / 128bit `vaddps__8` / vmovaps / vextractf128 0,1 / VEX store (256・128bit) |
| 差分試験のネガティブコントロール (実装を 1 箇所壊す) | **8/8 が rc 1 で mismatch > 0**: cmpnltps (`!(x<y)` → `x>=y`) 308,280 / movmskps (sign bit の位置) 395,374 / stosb (長さ −1) 19,822 / movsd (重なりでも memmove) 11,059 / 128bit vaddps (`x+y` → `x-y`) 306,390 / min (`olt` → `ogt`) 1,019,814 / vextractf128 1 (上位 → 下位) 199,997 / VEX 128bit store (`store i256 0`) 200,000。 sed が当たらなかった変異は FAIL にする |
| `synth_e2e.sh` 全工程 (`JOBS=4`、スクリプト a824a1d) | exit 1、958 秒。 judge: PASS 12 / KNOWN 9 / NEW-FAIL 0。 strict: PASS 12 / NEW-FAIL 9。 **`matrix_check` が 90/91 で rc 1**: PLUGIN_MATRIX の Harmless `batch.unimpl_helpers` 5 と実測 0 の食い違い。 → `PLUGIN_MATRIX.json` を 5 → 0 に更新 (f251ca6)。 gate は意図通り不一致で落ちた |
| **コミット済み HEAD aef6120 の `synth_e2e.sh --skip-lift`** | **exit 0、194 秒** (開始時 load average 0.57、終了時 0.99、並列 1)。 matrix_check 91/91、ids_crosscheck 12/12、judge: PASS 12 / KNOWN 9 / NEW-FAIL 0 / FIXED 0 / MISSING 0。 `[synth_e2e] OK` |
| HEAD aef6120 の `synth_nega.sh` | exit 0、11 秒。 NC1〜NC5 すべて期待通り (§6) |
| main (#538 ほか) をマージした 146f168 + helper_diff の stosb 変異を #538 の実装に合わせた 4f9fb12 | `synth_e2e.sh --skip-lift` exit 0 / 191 秒 (開始時 load average 0.43、終了時 1.00)、judge PASS 12 / KNOWN 9 / NEW-FAIL 0、matrix_check 91/91。 `synth_nega.sh` exit 0。 `helper_diff.sh` exit 0 (12,040,001 checks / 0 mismatch、NC 8/8)。 マージ直後は stosb の変異が当たらず helper_diff が FAIL した (「変異が当たらなければ FAIL」の設計どおり) |
| `known.json` | 3 本の `#535` 行を削除。 baseline に載ったまま解消した行は FIXED で落ちるため、削除が必須 |
| shell 3 本の lift 秒 (逐次) | 34 / 18 / 41 (旧 §2: 20 / 9 / 19)。 `fix_avx256` 自体は 1 秒未満で、増加の原因は未調査 (同一 HEAD での反復無し。 全工程の run は 4 並列で RetDec と同時に走る別条件) |

検証範囲: 3 本の lift 出力に未実装 helper / i256 trap が無いこと、各 helper の命令単位の bit 一致 (native 実命令との比較)。
範囲外: Gen_Render の中でこれら helper の結果が正しく使われること。 `rep movsd` / `rep stosb` の DF=1 (後方) 方向 (呼出元は DF の追跡をしていない)。 `cmp*pd` / `movmskpd` / `prefetcht1,2,nta,w` は実装したが 3 本は使わず、差分試験の対象外 (`cmp*ps` / `movmskps` と同じ生成器)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x745c00 (AVX 路) の Gen_Render 単位の実走差分 | lower した ymm 経路の正しさは命令単位までしか示していない | #533 |
| `rep movsd/stosb` の DF=1 | 3 本では未使用 | #197 (SIMD kernel 差分試験と共通の基盤) |
| `cmp*pd` / `movmskpd` の差分試験 | 3 本では未使用 | #197 |
| shell 3 本の lift 秒の増加 (旧 20/9/19 → 34/18/41) の原因 | 所要の見積のみ | #207 |
| C++ DLL 9 本の helper (18〜144 件、VEX を含む) | #534 の領分。 `fix_avx256` は `PLUG_AVX256=1` で適用できるが、未検証 | #534 |
