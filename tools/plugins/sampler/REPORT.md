# tools/plugins/sampler/REPORT.md — PLG-G3 (#208) sampler 8 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/sampler/` のみ / 検証起点 commit: **53c2eb6** (スクリプト。 以降は REPORT.md のみ)
- 再現: `bash tools/plugins/sampler/sampler_e2e.sh` (Delphi 殻 7 本: lift + 判定 + 突合) / `bash tools/plugins/sampler/sampler_engines.sh` (engine 2 本) /
  `bash tools/plugins/sampler/sampler_nega.sh` (ネガティブコントロール)。 対象の定義は `targets.py` だけ
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `sampler/env.sh`
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (silent miscompile は差分試験を未実施のため確認していない)。
  §5 の `rep_stosb_memset` 未実装 helper は stub 化で実行時に値が変わるため、D 類型の候補として §8 に行案を置く
- 先行 PR #506 (dynamics) の reviewer 指摘 (判定が不合格でも exit 0 / 判定のネガコン欠如) への対応は §6

## 0. 結論 (先出し)

1. **#208 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** P0a #195 / P0b #196 / P0c #197 が OPEN で、
   Eff_Render 単位の native ⟷ wasm 差分 harness も repo に無い。 → PR は **`Refs #208`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は Delphi 殻 7 本で 7/7 通った** (FL Keys / FPC / Granulizer / Slicer / Slicer 2 殻 / Slicex / Soundfont Player)。
   RetDec+pass 鎖が完走 (lift_rc 0)・`emcc -c` rc 0・`x86_fp80` 関数 0。 合計 **1,021 関数 / 519,650 B** (§1)。
   `PLUGIN_MATRIX.json` の `lift` 欄 6 項目 × 7 本 + `batch` 欄 4 項目 × 3 本 = **54/54 項目一致**。 T2 の FPC・Slicex と T3 の Slicer 2 殻・Soundfont Player は今回が初の lift 実測。
3. **「固有閉包」は固有コードの一部でしかない** (§2、新規): vtable override から `call/jmp rel32` で辿る閉包は、framework 非共通の `.pdata` 関数の
   関数数で 10.2–34.9 %、バイトで 8.1–34.5 % に留まる (Soundfont Player は 13.4 % / 21.7 %、Slicer 2 殻は 10.2 % / 8.1 %)。 閉包外のうち関数開始 VA が qword としてデータ/コード節に載っている (vtable・コールバック表の到達先候補) 関数が
   7 本計 1,437 関数 / 478,062 B。 閉包 lift だけでは wasm リンクに足りない下限であり、**見積 57.5 人日 (T 規則) の前提が崩れうる**。
   Soundfont Player の「固有 1.08 MB の内訳要精査」への答えは §2: 非共通 3,240 関数 / 1,080,576 B のうち閉包 433 関数 / 234,911 B (21.7 %)、閉包外 2,807 関数 / 845,665 B (うちデータ参照あり 842 / 347,032 B)。
4. **host 呼出面は P0b の応答表で覆い切れない**: taint 版の即値 Dispatcher ID に `hs_ids.json` (35 ID) 未収載のものが **FPC の 88 と Granulizer の 101 (各 1 site)**、
   別算法の独立走査はさらに ID 1 / 63 / 64 (Granulizer・Slicer・Slicex) を検出した (§3)。 hostshim は未収載 ID に 0 を返す fail-soft で落ちないが、応答の意味は未解析。
5. **SIMD kernel 依存は 5 本**: FL Keys 1 / FPC 4 / Granulizer 11 / Slicer 11 / Slicex 11 site (Slicer 2 殻・Soundfont Player は 0)。 うち FPC 3 / Granulizer 4 / Slicer 4 / Slicex 2 site は
   Balance の 80 実装表に逆引きできない呼出先 (§4)。 Slicex は P0c の #331 未解決 kernel (0x5dee90 / 0x5df040) を使う。
6. **Granulizer・Slicer の未実装 helper `rep_stosb_memset` は各 1 call site**。 `m11_simd2.py` は `rep_stosq_memset` しか実装せず、`stosb` は `m11_simd_unimpl_once("__asm_rep_stosb_memset")` を呼ぶだけの空 stub になる (初回だけ stderr に出し、memset されない)。 `emcc -c` は通るので judge の `declares_unimpl` 許容 (上限 1 + 名前の許可リスト) でのみ検出できる (§5)。
7. **C++ engine / 単体 DLL** ([PLG-G3-2] #540): Fruity Slicer 2 の engine (5,160 関数) と GMS (2,355 関数) は RetDec の `.ll` 出力 + pass 鎖が完走 (lift_rc 0、define 5,993 / 2,525) し、共有鎖 3 pass の修正 + 既存 `f80_lower.py` で最終 IR が **`emcc -c` rc 0** になった (§5)。 `judge.py engines` は最終 `emcc -c` rc 0 と `missing_ref` 0 を合格条件にした (exit 1 で落ちる)。 RetDec の C バックエンドが 10 分超・8 GiB 超かかるため `.ll` 出力後に止める方式にした。
8. **GMS (MSVC C++ 単体) は Delphi 殻の閉包方式が使えない**: vtable 規約が違い `plugin_closure.py` の対象外 (framework 一致 0)。 全 `.pdata` lift を行った (§5)。 直接 Win32 API は registry 6 / dynload 3 / file_io 17 / gdi_direct 6 / clipboard_dnd 3 / threads 1 (`PLUGIN_MATRIX.json` `win_direct_api`)。

## 1. 閉包 lift 結果 (Delphi 殻 7 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Gen_Render 等) から `call/jmp rel32` で到達する、
framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ)。 iat = IAT 経由 Win32 呼出 site。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 22386 | T1 | 29 / 18,986 | 77 / 14,479 | 34 | 4 | 0 | 29 | 0 | 0 | 0 | 4–5 (n=3) |
| FPC | 23617 | T2 | 141 / 71,528 | 201 / 38,083 | 198 | 31 | 0 | 141 | 0 | 0 | 0 | 9 (n=3) |
| Fruity Granulizer | 23658 | T1 | 90 / 26,101 | 98 / 11,229 | 46 | 51 | 2 | 90 | 0 | 1 (rep_stosb_memset) | 0 | 4 (n=3) |
| Fruity Slicer | 23662 | T1 | 119 / 40,560 | 131 / 21,827 | 78 | 54 | 2 | 121 | 0 | 1 (rep_stosb_memset) | 0 | 6 (n=3) |
| Fruity Slicer 2 | 23663 | T3 | 51 / 23,778 | 94 / 19,595 | 72 | 9 | 0 | 51 | 0 | 0 | 0 | 5 (n=3) |
| Slicex | 24172 | T2 | 158 / 103,786 | 275 / 55,779 | 295 | 72 | 1 | 158 | 0 | 0 | 0 | 15–23 (n=3) |
| Soundfont Player | 24175 | T3 | 433 / 234,911 | 159 / 22,017 | 247 | 37 | 0 | 433 | 0 | 0 | 0 | 33–57 (n=3) |
| 計 | | | **1,021 / 519,650** | | | | | 1,023 | | | | |

- 最右列の lift 秒は `lift_ranges.sh` 単独の秒 (`status.csv` の seconds、4 core の Actions runner、逐次)。 e2e 全体の秒は §6。
- `emcc -c` は `-O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- Fruity Slicer は define 121 > 閉包 119 (RetDec が range 内部に別 define を 2 つ切り出した)。 他 6 本は define 数 = 閉包関数数。 judge は define>0 だけを要求し等値は要求しない。
- 殻の直接 Win32 API (`PLUGIN_MATRIX.json` `win_direct_api`): Slicer 2 殻 = file_io 13 / dynload 4 / threads 6 / clipboard_dnd 3 / gdi_direct 6、Soundfont Player = gdi_direct 43 / threads 6 / clipboard_dnd 3 / dynload 1 / process 1、FPC = file_io 2、Slicer = process 1。 他は 0。

## 2. 閉包の取りこぼし (新規): 閉包外の固有関数

閉包は間接呼出 (vtable 経由・関数ポインタ) を辿らない。 `unreached_unique.py` で、閉包に入らない非共通関数が `.pdata` 以外の節に qword として載っているかを数えた
(非共通 = ハッシュの出現 DLL 数が 13 未満。 データ参照 = 関数開始 VA が節先頭から 8 バイト整列の qword として存在。 Delphi は vtable を `.text` に置くため `.text` も走査する)。

| プラグイン | 非共通 関数 / B | 閉包 関数 / B | 閉包外 関数 / B | うちデータ参照あり 関数 / B | データ参照なし 関数 / B | 正の対照 (entry のデータ参照検出) |
|---|--:|--:|--:|--:|--:|--:|
| FL Keys | 153 / 77,996 | 29 / 18,986 | 124 / 59,010 | 35 / 4,432 | 89 / 54,578 | 9/9 |
| FPC | 801 / 413,955 | 141 / 71,528 | 660 / 342,427 | 104 / 30,147 | 556 / 312,280 | 10/10 |
| Fruity Granulizer | 264 / 99,246 | 90 / 26,101 | 174 / 73,145 | 46 / 9,722 | 128 / 63,423 | 11/11 |
| Fruity Slicer | 341 / 117,576 | 119 / 40,560 | 222 / 77,016 | 47 / 6,714 | 175 / 70,302 | 11/11 |
| Fruity Slicer 2 | 498 / 293,562 | 51 / 23,778 | 447 / 269,784 | 74 / 22,023 | 373 / 247,761 | 10/10 |
| Slicex | 1,172 / 508,391 | 158 / 103,786 | 1,014 / 404,605 | 289 / 57,992 | 725 / 346,613 | 10/10 |
| Soundfont Player | 3,240 / 1,080,576 | 433 / 234,911 | 2,807 / 845,665 | 842 / 347,032 | 1,965 / 498,633 | 10/10 |

- 正の対照: 各殻の vtable override entry (最右列の分母) が全てデータ参照として検出された (検出できなければスクリプトが exit 1)。
  当初 `.text` を走査対象から外した版では 0/9〜0/11 で、対照が落とすことを確認したうえで `.text` を含めた (実測の経緯)。
- データ参照なし = 他の閉包外関数から直接呼ばれる関数・未参照関数・qword 以外の形で参照される関数のいずれか (未判別)。 データ参照あり関数からの直接呼出先 (推移閉包) は未計算で、真の追加量はこの表より大きい。
- 含意: MATRIX の `lift.closure_*` は「vtable override の直接呼出閉包」であり、Eff_Render / Gen_Render が間接呼出で到達するプラグイン内クラス (Slicex 289 / Soundfont Player 842 関数など) を含まない。 見積の再検討と推移閉包の lift は §7 の新規起票対象。
  dynamics (#506) の 7 本にも同じ制約があるが、そちらは未測定。

## 3. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| プラグイン | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) | hs_ids.json に無い ID |
|---|--:|---|--:|---|---|
| FL Keys | 10 | 2 (1) | 0 | 0x28: 2, 0xf8: 1, 0x100: 2, 0x108: 2, 0x128: 2 | 無し |
| FPC | 35 | 2 (3) / 3 (4) / 17 (1) / 50 (1) / 88 (1) | 3 | 0x28: 2, 0x30: 1, 0xf8: 3, 0x100: 7, 0x108: 7, 0x128: 2 | {'88': 1} |
| Fruity Granulizer | 23 | 2 (4) / 3 (3) / 36 (1) / 90 (1) / 101 (1) | 1 | 0x28: 3, 0x68: 1, 0xb8: 1, 0xf0: 1, 0x100: 3, 0x108: 3 | {'101': 1} |
| Fruity Slicer | 26 | 2 (6) / 3 (1) / 10 (1) / 17 (1) / 36 (1) / 90 (1) | 1 | 0x28: 3, 0x68: 2, 0x78: 1, 0xb8: 1, 0xf0: 1, 0x100: 3, 0x108: 3 | 無し |
| Fruity Slicer 2 | 6 | 2 (1) / 3 (1) / 17 (1) | 1 | 0x100: 1, 0x108: 1 | 無し |
| Slicex | 52 | 2 (2) / 3 (1) / 10 (2) / 14 (1) / 17 (1) / 36 (2) / 67 (1) | 1 | 0x28: 2, 0x30: 3, 0x100: 15, 0x108: 15, 0x128: 6 | 無し |
| Soundfont Player | 0 | — | 0 | — | 無し |

- **Soundfont Player は taint 版が host call 0 site** だが、独立走査は ID 2 を 1 site 検出する。 閉包 433 関数で host 呼出 0 は不自然で、taint (`this+0xbc`) が当てはまらない経路がある (taint の過小計上と推定; 原因未調査)。
- **別算法の検算** (`ids_crosscheck.py`: taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 7/7 本で taint 版 45 site を取りこぼしなく再現。
  独立走査のみが拾った差 (host 呼出か別オブジェクトの slot0 呼出かは未判別): Granulizer ID 64 × 4、Slicer ID 64 × 4、Slicex ID 1 × 1 / 63 × 3 / 64 × 4 (いずれも `hs_ids.json` 未収載)、Soundfont Player ID 2 × 1 (収載)。
- `hs_ids.json` (35 ID / 894 site) 未収載の taint 版 ID: FPC の 88、Granulizer の 101。 `hostshim.c` の `hs_dispatcher` は未収載 ID で `default: return 0` (fail-soft)。 応答の意味は P0b の case 別解析 (#196 作業 5) 待ち。
- 0x28 / 0x30 / 0x68 / 0x78 / 0xb8 / 0xf0 / 0xf8 / 0x128 などは dynamics の 7 本に出ていない slot。 P0b では 44 slot 共通の fail-soft + 呼出記録のみ (意味未解析)。 0x100 / 0x108 は ABI.md §6 が偽陽性を含みうるとする offset。

## 4. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類。 kernel 番号は Balance (block 18983) の VA に正規化済み
(`kernel_va_map` に逆引きできない呼出先は DLL 固有 VA のまま表示)。

| プラグイン | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査の site / kernel 種 |
|---|--:|---|--:|---|
| FL Keys | 1 | 0x5dee50 (1) | 0 | 28 / 6 |
| FPC | 4 | 0x5dee50 (1), 0x62f4b0 (2), 0x62f680 (1) | 0 | 46 / 16 |
| Fruity Granulizer | 11 | 0x5de410 (1), 0x5df240 (4), 0x5dffc0 (1), 0x5dfff0 (1), 0x60b380 (1), 0x60b550 (1), 0x60b780 (2) | 1 | 44 / 14 |
| Fruity Slicer | 11 | 0x5de410 (1), 0x5df240 (4), 0x5dffc0 (1), 0x5dfff0 (1), 0x60d1e0 (1), 0x60d3b0 (1), 0x60d5e0 (2) | 3 | 44 / 16 |
| Fruity Slicer 2 | 0 | — | 0 | 42 / 13 |
| Slicex | 11 | 0x5de540 (1), 0x5dee50 (1), 0x5dee90 (1), 0x5df040 (2), 0x5df240 (4), 0x635770 (2) | 4 | 52 / 16 |
| Soundfont Player | 0 | — | 0 | 22 / 1 |

- DLL 固有 VA のまま残った呼出先: FPC 0x62f4b0 (2) / 0x62f680 (1)、Granulizer 0x60b380 / 0x60b550 / 0x60b780、Slicer 0x60d1e0 / 0x60d3b0 / 0x60d5e0、Slicex 0x635770 (2)。
  Granulizer と Slicer は開始 VA の差が一定 (0x1e60) の同形 3 関数。 sampler 固有の補間 kernel と推定 (未解析)。 P0c の 80 実装表に無いので P0c の差分試験対象外。
- P0c (`p0c/REPORT.md`) の現状 (本 PR では再測定していない): 0x5df240 は f32 mul 系で出力バッファ bit-exact (§3・§12)。 0x5dee90 / 0x5df040 は #331 の未解決対象 (§14.4、Slicex が使う)。
  0x5dee50 / 0x5de410 / 0x5dffc0 / 0x5dfff0 / 0x5de540 は `p0c/REPORT.md` に VA の言及が無い (grep)。
- DLL 固有関数走査の site 数 (最右列) は閉包外も含む。 閉包 / frontier 外にある分は framework の深い関数か閉包外の固有関数 (§2) と推定 (未確認)。

## 5. C++ engine / 単体 DLL (engine 2 本相当)

Fruity Slicer 2 は殻 (block 23663) とは別に C++ engine DLL (block 23664、export `CreatePlugInstance` / `DispatchToEngine`) を持つ。 GMS (block 23677) は Delphi 殻の無い MSVC C++ 単体 DLL
(framework 一致 0 のため `plugin_closure.py` の閉包方式は使えない)。 どちらも `.pdata` の全関数を RetDec+pass 鎖に通した (`sampler_engines.sh` → `engine_lift.sh`)。

| 対象 | block | サイズ B | `.text` B | `.pdata` 関数 / B | export | import DLL (関数数) |
|---|--:|--:|--:|--:|---|---|
| Fruity Slicer 2 engine | 23664 | 2,738,176 | 2,198,646 | 5,160 / 2,117,872 | CreatePlugInstance, DispatchToEngine | KERNEL32.dll (96), USER32.dll (49), GDI32.dll (14), SHELL32.dll (4), ole32.dll (7), WINMM.dll (4), dwmapi.dll (1), SHLWAPI.dll (1), d3d9.dll (1), OPENGL32.dll (36), RPCRT4.dll (1), WindowsCodecs.dll (1) |
| GMS (単体 DLL) | 23677 | 1,552,896 | 1,244,592 | 2,355 / 1,208,618 | CreatePlugInstance | KERNEL32.dll (95), USER32.dll (31), GDI32.dll (11), COMDLG32.dll (2), ADVAPI32.dll (3), SHELL32.dll (2), ole32.dll (3) |

| block | lift rc | final.ll define | `.pdata` で define 無し (B) | f80 関数 | 未実装 helper | `emcc -c` (final.ll) | fixcmp 後 `emcc -c` | **f80_lower 後 `emcc -c` (最終)** | lift 秒 |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 23664 | 0 | 5993 | 3 / 5160 (2239 B) | 2 | 215 | **0** | 0 (patched operand 0) | **0** | 382 (CPU 競合あり) |
| 23677 | 0 | 2525 | 1 / 2355 (61 B) | 1 | 151 | 1 (f80 の `fp_extend`) | 1 | **0** | 66 |

- 数え方: `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。 分母は `.pdata` 関数数、括弧は欠けた range の合計長)。 参照されている (link 時に未解決になる) 件数 (`missing_ref`) は 2 本とも 0。
  逆に range 内部に別 define が増えた件数は 23664 で 833、23677 で 170 (RetDec の関数境界統合・分割)。 f80 関数は 2 / 1 本。
- **受入条件 1/2: 根本原因と修正 (共有鎖 `tools/plugins/lift/passes/`)**。 修正前 HEAD 190f1d8 の再現: 23664 は `use of undefined value '%15'`、23677 は E1 → (`engine_fixcmp.py` 後) `zext 0 to i64`。 `emcc -c` は最初の型エラーで止まるため、1 件直すと次が出る (以下は出た順)。
  | # | 症状 (最小再現で確認) | 根本原因 | 修正 | 効いた block |
  |---|---|---|---|---|
  | 1 | 23664 `%15` dangling use (`function_18014f8a0`) | `fix_asm_stores.py` P-S1d が `call __asm_movdqu` + `sext` の定義行を空行化するが、`store i64 %15, ptr %r9.1.reg2mem` 等 store 以外の使用を数えない | 他の使用が残る定義は消さない (使用数を数える) | 23664 |
  | 2 | 23677 `zext 0 to i64` | `ir5_patch.py` A8 `fold_const_ops` が外側 (`trunc (add (zext (xor ..)))`) を畳めない時に `pos = j + 1` で次へ進み、内側の `zext (i32 0 to i64)` を走査しない。 A4 が xor を `0` にした後に残る。 `_src_pref` の型欠けではなく**畳み込み漏れ**で、A9L が型無しで命令化した | 外側が畳めなくても `pos = idx + 1` で内側へ入る (2 箇所) | 23677 |
  | 3 | 23677 `zext constexprs are no longer supported` (`rep_stosq_memset` 第 3 引数) | A9L 固定点反復 `lift_residual_constexpr` が、命令を挿入しない行書換 (`bitcast (ptr X to ptr)` の no-op 除去) を捨てて `changed` を立てず、外側の `icmp`/`zext` 定数式が残る | 行だけ書き換わった場合も採用して反復を続ける | 23677 |
  | 4 | 23664 `invalid use of function-local name` (`glOrtho` の `double bitcast (i64 ptrtoint (ptr @0 to i64) to double)`) | A9L が `bitcast (i64 %v to double)` の型を落として `double bitcast (i64 %ce.. to double)` を残す | `bitcast iN %v to double/float` は型付き命令として挿入 | 23664 |
  | 5 | 23677 E1 `icmp eq ptr %45, %arg1` | `fix_ptr_params.py` は `ptr %argN` を探すが `icmp P ptr %a, %argN` は型が先頭オペランドにしか付かず一致しない。 #523 E1 と同型 | `icmp` の `%argN` オペランドを `inttoptr` 経由にする | 23677 (23664 の `%arg3` も) |
  | 6 | 23677 `do not know how to soften fp_extend` (x86_fp80) | wasm バックエンドが f80 を扱えない (23677 は f80 関数 `function_18012d290` 1 本。 #197 の対象) | 既存 `p0c/f80_lower.py` (x86_fp80 → f64) を `engine_lift.sh` が fixcmp 後に適用して再度 `emcc -c` (f80 tokens 11 → 0) | 23677 |
  - `engine_fixcmp.py` は 5 により不要になった (修復 operand 数 23664: 7 → 0、23677: 11 → 0。 スクリプトは診断用に残す)。
  - 退行確認 (共有鎖を変えたため): Delphi 殻 7 閉包は `sampler_e2e.sh` が exit 0・7/7 `emcc_c=0` (§6)。 T0 バッチは §6。 修正前 pass での 23677 `.lift.ll` は `zext 0 to i64` 2 件・A9L 残存 53 件、修正後は 0 件。
- **受入条件 3: RetDec の C バックエンド省略の判断**。 共有 `lift_ranges.sh` には**入れない**。 理由: (a) `lift_from_ll.sh` は `lift_ranges.sh` を sed で切り出し RetDec をログ文字列 `LLVM IR -> HLL` で kill する。 RetDec 出力の文言に依存し、sed が RetDec 呼出行を特定できなければ exit 1 で止まる (本 PR の途中で段付き行に一致せず lift_rc 1 になった実例) ため、T0/T1 の全 lift (97 s / 163 s で C バックエンドが問題にならない規模) に常用するリスクが利得より大きい。
  (b) 規模が問題になるのは engine 級 (2.1 MB 超) だけで、`LIFT=sampler/lift_from_ll.sh` で使い分けられる。 (c) `--backend-enabled-opts` / `--no-memory-limit` は RetDec の help で存在を確認したが、未評価 (C 出力の段は `LLVM IR -> HLL` 後に残り、時間は短縮しても省略にならない。 `--no-memory-limit` は 15 GiB の runner で OOM の危険が増える。 評価は #540 の追加課題として未解決表に置く)。
- **RetDec の C バックエンドが支配的**: `lift_ranges.sh` 直行 (`sampler_e2e.sh` 初版、engine 2 本を並列) では、`LLVM IR -> HLL` 段の開始 (= `.ll` 出力後) は RetDec 開始後 23664 で 114.24 s・23677 で 69.49 s (スクリプト一本版の run では 93.05 s / 46.51 s) だったが、その後の C 出力段が終わらなかった。
  23664 は 614.57 s 時点 (`variable renaming`) で RSS 8.15 GiB、"out of memory; trying to recover" を 3 回出した (RetDec の既定メモリ上限は搭載 RAM の半分 = 約 8 GiB、`--no-memory-limit` で解除可)。 23677 は 758.98 s 時点 (`emission of the target code [c]`) で RSS 6.85 GiB。
  C は使わないので、`lift_from_ll.sh` で `.ll` 出力後に RetDec を止めて後段 pass 鎖だけ走らせる (`lift_ranges.sh` 本体から後段を切り出す)。 `.ll` の出力から `emcc -c` までの結果は、停止して再開した版とスクリプト一本の版で同一だった。
- **受入条件 4: 殻 (Slicer 2) と engine の結合方式** (静的解析、`vex_guard.py` とは別の逆アセンブル。 実行はしていない):
  - 殻 block 23663 の関数 `0x843790`–`0x84386b` が、文字列 `engine_x64.dll` (VA 0x843894) と `DispatchToEngine` (VA 0x8438b2) を `lea rip+` で参照する (全 `.text` の rel32 総当たりで参照元はこの 1 関数だけ)。
  - 同関数は `0x413db0` (文字列組立) → `0x83e200` の順に呼ぶ。 `0x83e200` は `0x734560` (引数が指すパスの存在確認と読めるが、中身は `0x4221d0` / `0x439050` を呼ぶだけで確認は浅い) の真偽で分岐し、真なら **`0x448930`** を呼ぶ。
    `0x448930` は内部で `0x422050` を呼び、`0x422050` は `jmp [IAT LoadLibraryW]` のスタブ (`.text` の `ff 25` 総当たりで確認。 `0x44895b` が `0x422050` の call)。 よって `0x448930` = **LoadLibraryW ラッパ** (確認済み)。
  - `0x83e200` はその返値 (HMODULE) を `[r9]` に格納し、`0x421d60` に (HMODULE, 文字列 `CreatePlugInstance`) を渡す。 `0x421d60` の末尾は `0x421d50` = `jmp [IAT GetProcAddress]` なので **GetProcAddress ラッパ** (確認済み)。
    得た関数ポインタに対し `call rax` (引数 `r8`→`rcx`、`rdx`→`rdx`)。 返値は殻の this+`0x1a8` へ。
  - 続けて `0x421d60` で `DispatchToEngine` を引き this+`0x1c0` に保存する。 engine 側は export 2 本 (`CreatePlugInstance` / `DispatchToEngine`) をそのまま公開している (§5 の表)。 this+`0x1a8` の返値を `[rax]` の vtable として `call [rax+8]` (引数 `0x10000` / `0x200000`) を 2 回呼び、返値を this+`0x1b8` へ保存する (第 2 回は this を渡す)。
  - 以上から、wasm では engine を静的リンクし、`LoadLibrary` + `GetProcAddress` の 2 呼出を `CreatePlugInstance` / `DispatchToEngine` の直接シンボル参照に置換する形になる。 `DispatchToEngine` の呼出規約・引数の意味、`0x83e200` の引数の意味、LoadLibrary される実パスは未解析 (未解決表)。
- **受入条件 5: 未実装 VEX helper を CPUID 分岐で SSE 路に固定できるか** (`vex_guard.py <block> [--list]`、capstone で全 `.pdata` 関数を逆アセンブル、mnemonic が `v` 始まりの命令を VEX、`cpuid` / `xgetbv` を分岐側として数える)。
  | block | `.pdata` 関数 | VEX 命令を持つ関数 | VEX 命令数 | `cpuid` 関数 | `xgetbv` 関数 | VEX 関数のうち caller 鎖 (深さ 3) に `cpuid`/`xgetbv` 関数がある数 |
  |--:|--:|--:|--:|--:|--:|--:|
  | 23664 | 5,160 | 229 | 21,761 | 29 | 4 | **0** |
  | 23677 | 2,355 | 94 | 15,225 | 28 | 3 | **0** |
  VEX 関数の直接呼出元 (深さ 3) に cpuid/xgetbv を含む関数は 1 本も無い。 つまり CPUID 判定は呼出しの上流で分岐として「関数ポインタ / vtable を選ぶ」形 (間接呼出) で効いている可能性が高く、直接呼出グラフだけでは分岐の両側を特定できない (推定。 未確認)。
  よって「CPUID を SSE 固定して VEX 側を呼ばない」は静的には言えない。 判断: **VEX helper を実装する方が確実** (未実装 215 / 151 件のうち VEX 系 `__asm_v*` は 139 / 101 件。 `m11_simd2.py` に追加する課題)。 `emcc -c` は未実装 helper が空 stub になっても通るので gate はこれを検出しない (silent)。
- gate: `judge.py engines` は合格条件を **最終 IR (`emcc_c_rc_after_f80`) の `emcc -c` rc 0 と `missing_ref` 0** に変えた (従来は `emcc -c` を判定外にしていた)。 不合格 = exit 1。 NC8 (§6) で 1 列ずつ壊して確認。
- 以上は到達性の実測で、engine の正しさは何も示していない (差分試験は #208 の出口条件)。 未実装 helper が空 stub のまま `emcc -c` が通る点も silent (§8 H1 と同型)。

## 6. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner)

検証起点 commit は **53c2eb6** (以降の commit は REPORT.md のみ)。 以下は全てコミット済み HEAD で実行した。

| 項目 | 実測 |
|---|---|
| `sampler_e2e.sh` 全体 (最終版、HEAD 53c2eb6、inventory 済みから) | exit 0、**211.95 s** (開始時 load average (1 分) 1.31)。 内訳: 7 閉包の lift 79 s、残りは `closure_facts.py` + `matrix_check.py` |
| 同 (HEAD aec2fac) | exit 0、276.46 s (開始時 load 1.97。 engine の後段 pass 2 プロセスと RetDec 1 本が同時に走っていた) |
| 初版 (engine 込み、HEAD 56aeefe) | **exit 1**、921.34 s。 RetDec の C 出力段が終わらず私が 2 本を停止したため engine 判定が FAIL (§5)。 現行版は engine を `sampler_engines.sh` に分離 |
| 7 閉包の lift 秒 (`status.csv` の seconds、3 回の合計) | 76 s / 109 s / 79 s (run 2 は並走プロセスがあり Slicex 15 → 23 s、Soundfont Player 33 → 57 s)。 プラグイン別の min–max は §1 の最右列 |
| 3 回の結果一致 | §1・§3・§4 の表 (判定列・閉包値・host・kernel) は run 2 と run 3 で完全一致 (`diff`)。 `declares_unimpl` と `unimpl_names` を含む 7 行の判定列は 3 回とも同一 |
| `sampler_engines.sh` (HEAD 53c2eb6、2 本並列) | exit 0、**287.04 s** (開始時 load 0.36)。 2 回目の実行 (1 回目は `lift_from_ll.sh` の sed が段付き行を拾えず lift_rc 1 → 判定が **exit 1** で止まった。 修正して再実行)。 結果は停止再開版と各列一致 (§5) |
| `matrix_check.py` | 54/54 項目一致 (閉包 6 項目 × 7 本 + `batch` 4 項目 × 3 本) |
| `ids_crosscheck.py` | exit 0、3.16 s。 7/7 本で取りこぼしなし (§3) |
| `unreached_unique.py` | exit 0、2.66 s。 正の対照 7/7 |
| 前提 inventory (初回のみ、`work/` 無しから) | 533 s (`win_scan`〜`kernel_table`。 `win_funcs.py` が並列 14 プロセス / 4 core で大半)。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため、`mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |

### gate の設計 (#506 の reviewer 指摘への対応)

- 判定は `judge.py` に切り出し、不合格が 1 件でもあれば **exit 1** (入力不正は exit 2)。 `sampler_e2e.sh` は `set -e` で判定の直後に中断し、`[sampler_e2e] OK` は全工程を通った時だけ出る。
- `declares_unimpl` も判定に含める。 許容は `targets.py` の `ALLOW_UNIMPL` (Granulizer・Slicer の各 1) と名前の許可リスト (`rep_stosb_memset`) だけ。 それ以外の block が 1 件でも未実装 helper を持てば不合格。 -1 (計測不能)・非整数・行欠落・header のみ・空は全て不合格。
- lift 実行時は、その run が `work/batch/status.csv` に追記した行だけを判定する (過去 run の合格行で通さない)。
- 突合 (`matrix_check.py` / `ids_crosscheck.py` / `unreached_unique.py`) は期待件数と照合した件数が一致しなければ不合格 (facts が空・欠落でも vacuous に通さない)。 `unreached_unique.py` は正の対照が落ちると exit 1。
- engine の判定は「計測が成立したか」(lift_rc 0・define>0・pdata>0・行が揃う) に限り、`emcc -c` の成否は不合格にしない (到達性の実測値であり §7 で起票)。 この区別をスクリプト冒頭と REPORT に明記した。

### ネガティブコントロール (`sampler_nega.sh`、exit 0、10.49 s、HEAD 53c2eb6)

| NC | 内容 | 対照 → 壊した入力 (実測) |
|---|---|---|
| NC1 | FL Keys の `final.ll` の関数 1 つの `ret` を除去 → `emcc -c` | rc 0 → **rc 1** |
| NC2 | FL Keys の閉包 ranges の末尾 1 つを落として再 lift | 落とした関数 `function_7268d0` が 1 → **0**、define 29 → 27 |
| NC3 | `judge.py shells` に合成 CSV 10 種 (emcc_c_rc=1 / lift_rc=1 / f80=3 / 許容 0 の block に未実装 1 / 許容 1 の block に未実装 2 / 未実装 -1 / 許可外の helper 名 / FPC の行欠落 / 全行欠落 / header 不正) | 対照 rc 0 → 9 種が **rc 1**、header 不正が **rc 2** |
| NC4 | e2e 本体 (`--skip-lift --judge-only`) に `emcc_c_rc=1` の行を足した status.csv を渡す | 対照 rc 0 → **rc 1**、不合格側の出力に `[sampler_e2e]` 行 0 本 (OK 行が出ない) |
| NC5 | `matrix_check.py` に壊した入力 4 種 (FPC の closure_funcs +1 / Slicex の facts 欠落 / 空 facts / FL Keys の batch emcc_c_rc=1) | 対照 rc 0 → **4 種とも rc 1** |
| NC6 | `ids_crosscheck.py` に taint 側の ID 件数を +1 (FL Keys ID 2: 1 → 2) した facts | 対照 rc 0 → **rc 1** |
| NC7 | `judge.py engines` に lift_rc=1 の行 / 末尾行欠落の engines.csv | 対照 rc 0 → **2 種とも rc 1** |

NC4 は #506 の reviewer が再現した「不合格行を追記しても exit 0」と同じ入力 (emcc_c_rc=1 の追記) で、本 PR は exit 1 になる。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)、host / kernel 依存の静的な数え上げ、閉包外の固有関数の静的な数え上げ。
範囲外 (本書は何も主張しない): wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp、
クリーン worktree (`env -i`・新規 `RUNNER_TEMP`) での全工程再現 (inventory は `work/` 無しから生成して run 1〜3 を実行したが、別 worktree での再現は時間切れで未実施)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件)。 Eff_Render 単位の native / wasm harness が無く、P0a/b/c が OPEN | #208 を閉じられない | #195 / #196 / #197 の完了後に #208 を再開 (Closes はその時)。 harness は #506 の REPORT §6 が提案した「[PLG-F3a]」と共用 (PM 判断) |
| Render test .flp の E2E (FL Keys / FPC / Granulizer / Slicer / Slicex / GMS の RT 列 Y) | 同上 | FLEngine 統合待ち。 親 #14 / #208 |
| 閉包外の固有関数 (§2): 推移閉包を含む lift と見積の再計算 | 見積 57.5 人日の前提・wasm リンク | 新規 #537 [PLG-G3-3] (起票済み)。 dynamics #200 / PR #506 にも同じ制約があるため #200 にコメント |
| `rep_stosb_memset` 未実装 stub (Granulizer / Slicer 各 1 call site) | silent な memset 欠落 | 新規 #538 [PLG-G3-4] (起票済み) |
| C++ engine / 単体 DLL 2 本の `emcc -c` 未通過 (E1・dangling use・`zext 0 to i64`)、未実装 helper 215 / 151、f80 2 / 1、RetDec C バックエンドの規模耐性 | Slicer 2 (T3) の engine、GMS (T3) | 新規 #540 [PLG-G3-2] (起票済み) (同型: #523 [PLG-F4-2]・#527 [PLG-F5-2]) |
| engine 内の f80 関数 (Slicer 2 engine 2 / GMS 1) | engine の wasm 化 | #197 (`f80_lower.py` の適用) にコメント |
| host の Dispatcher ID 88 (FPC)・101 (Granulizer) が `hs_ids.json` 未収載、独立走査のみの ID 1 / 63 / 64、slot 0x28 / 0x30 / 0x68 / 0x78 / 0xb8 / 0xf0 / 0xf8 / 0x128 の意味 | P0b の応答表の網羅性 | #196 作業 5 (0x13173a0 全 case 解析) にコメント |
| Soundfont Player の taint 版 host call が 0 site (独立走査は ID 2 を 1 site) | host 呼出面の過小計上 | #196 (ABI.md §6 の taint 精密化) にコメント |
| Balance の 80 実装表に逆引きできない kernel 呼出先 (FPC 3 / Granulizer 4 / Slicer 4 / Slicex 2 site) | P0c の差分試験対象外 | #197 にコメント |
| Slicex が使う 0x5dee90 / 0x5df040 | P0c の未解決 kernel | #331 にコメント |
| Slicer 2 殻と engine の結合方式 (LoadLibrary 経路・`DispatchToEngine`) が未解析 | engine を殻に結線できない | 新規 #540 [PLG-G3-2] (起票済み) の受入条件 4 |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 |

## 8. DEFECTS.md 行案 (候補・追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| H1 stos 系 helper 未実装 stub | `__asm_rep_stosb_memset(ptr, i8, i64)` が `m11_simd2.py` で未実装 → `p_simd.c` では `m11_simd_unimpl_once()` を呼ぶだけの空 stub になり memset されない | Fruity Granulizer / Slicer 各 1 call site (`rep_stosq_memset` は実装済み) | `p.simd.log` の `unimplemented: ... rep_stosb_memset`。 `emcc -c` は通る (silent) | `m11_simd2.py` に `rep_stosb_memset` を足す (memset へ写像)。 `judge.py` は許容リストで名指しして検出 |
| H2 閉包の過小計上 | vtable override の直接呼出閉包が非共通コードの 8–35 % (バイト) しか含まず、間接呼出の到達先が lift から漏れる | §2 (7 本計 閉包外・データ参照あり 1,437 関数 / 478,062 B) | リンク時の未解決シンボル / 実行時 `call` 先の欠落。 差分試験の不一致 | データ参照ありの関数を root に足した推移閉包で lift |

## 9. 成果物

| ファイル | 内容 |
|---|---|
| `sampler_e2e.sh` | 7 閉包 → batch_lift → **判定 (`judge.py`)** → `closure_facts.py` → `matrix_check.py`。 不合格で exit 1。 `--skip-lift` / `--judge-only` |
| `judge.py` | 判定 (gate)。 `shells` (lift_rc / `emcc -c` / f80 / 未実装 helper / define) と `engines` (計測成立)。 不合格 exit 1・入力不正 exit 2 |
| `sampler_engines.sh` `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` `lift_from_ll.sh` | engine / 単体 DLL の全 `.pdata` lift・欠落監査・局所修復・RetDec 後段のみの再開 |
| `sampler_nega.sh` | ネガティブコントロール NC1–NC7 (§6) |
| `closure_facts.py` `matrix_check.py` `ids_crosscheck.py` `unreached_unique.py` `report_tables.py` | 閉包 / host / kernel / engine 外形 → `facts.json` / `PLUGIN_MATRIX.json` 突合 / Dispatcher ID の別算法検算 / 閉包外の固有関数 / 表の機械生成 |
| `targets.py` `env.sh` `mk_blockmap.py` | 対象の唯一の定義 / 環境 / `block_manifest.json` 不要の inventory 前提 |
