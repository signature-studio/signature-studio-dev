# tools/plugins/sampler/REPORT.md — PLG-G3 (#208) sampler 8 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/sampler/` のみ / 検証起点 commit: **4c3ae00** (以降 209dc3c5 → cc35d4ef は docs のみ。 検証経路は無変更)
- 再現: `bash tools/plugins/sampler/sampler_e2e.sh` (Delphi 殻 7 本: lift + 判定 + 突合) / `bash tools/plugins/sampler/sampler_engines.sh` (engine 2 本) /
  `bash tools/plugins/sampler/sampler_nega.sh` (ネガティブコントロール)。 対象の定義は `targets.py` だけ
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `sampler/env.sh`
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (silent miscompile は差分試験を未実施のため確認していない)。
  `rep_stosb_memset` の空 stub (旧 #538) は #629 (`790d2f5`) で解消済み。 基底は `origin/main` (`3d86c3f`) を取り込んだ merge commit (§6)
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
6. **Granulizer・Slicer の `rep_stosb_memset` は #629 で memset に写像済み** (旧: 各 1 call site の空 stub で silent。 `emcc -c` は通るが判定の許容でのみ検出していた)。 本 PR の `targets.py` の許容は空にし、7 本の未実装 helper は 0 件 (§1・§6)。
7. **C++ engine / 単体 DLL**: Fruity Slicer 2 の engine (5,160 関数) と GMS (2,355 関数) は RetDec の `.ll` 出力 + pass 鎖が完走 (lift_rc 0、define 5,993 / 2,525) するが `emcc -c` は未通過 (dangling use・`zext 0 to i64`)。 RetDec の C バックエンドが 10 分超・8 GiB 超かかるため `.ll` 出力後に止める方式にした (§5)。
8. **GMS (MSVC C++ 単体) は Delphi 殻の閉包方式が使えない**: vtable 規約が違い `plugin_closure.py` の対象外 (framework 一致 0)。 全 `.pdata` lift を行った (§5)。 直接 Win32 API は registry 6 / dynload 3 / file_io 17 / gdi_direct 6 / clipboard_dnd 3 / threads 1 (`PLUGIN_MATRIX.json` `win_direct_api`)。

## 1. 閉包 lift 結果 (Delphi 殻 7 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Gen_Render 等) から `call/jmp rel32` で到達する、
framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ)。 iat = IAT 経由 Win32 呼出 site。

| プラグイン | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| FL Keys | 22386 | T1 | 29 / 18,986 | 77 / 14,479 | 34 | 4 | 0 | 29 | 0 | 0 | 0 | 4–5 (n=3) |
| FPC | 23617 | T2 | 141 / 71,528 | 201 / 38,083 | 198 | 31 | 0 | 141 | 0 | 0 | 0 | 9 (n=3) |
| Fruity Granulizer | 23658 | T1 | 90 / 26,101 | 98 / 11,229 | 46 | 51 | 2 | 90 | 0 | 0 | 0 | 4 (n=3) |
| Fruity Slicer | 23662 | T1 | 119 / 40,560 | 131 / 21,827 | 78 | 54 | 2 | 121 | 0 | 0 | 0 | 6 (n=3) |
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

## 2b. 推移閉包 (#537): データ参照あり関数を root に足した lift — 全文は `REPORT_INDIRECT.md`

- **結論**: §2 のデータ参照あり関数 (1,437 関数 / 478,062 B) を root に足した推移閉包は **7 本計 3,623 関数 / 1,344,182 B** (§1 の閉包の 3.55 倍 / 2.59 倍。 非共通に占める割合は関数 56.0 % / B 51.9 %)。
  lift は 7/7 通過 (lift_rc 0 / `emcc -c` rc 0 / f80 0、range 欠落 0)。 `lea [rip+X]` で開始 VA を取る 153 関数 / 38,656 B は root 未収載で、推移閉包もなお下限。
- 検証 (HEAD 0f50a1b): `indirect_e2e.sh` 3 回 exit 0 (141 / 139 / 138 s)・`indirect_nega.sh` NC0–NC7 全て期待通り (19 s)。 再現: `bash tools/plugins/sampler/indirect_e2e.sh` / `bash tools/plugins/sampler/indirect_nega.sh`。
- PLUGIN_MATRIX / 見積 (57.5 人日) は書き換えていない (影響の記録は付録。 PM 判断)。

## 2c. lea 経路を root に足した閉包 (#627) — 全文は `REPORT_LEA.md`

- **結論**: `lea [rip+X]` 参照の固定点を足した閉包は **7 本計 3,816 関数 / 1,390,509 B** (#537 の total 比 +193 関数 / +46,327 B)。 1 巡目の lea root は 153 関数 / 38,656 B (issue 値と一致)。 lift は 7/7 通過 (range 欠落 0)。
  lea 由来の x87 関数で Granulizer / Slicer / Slicer 2 の raw `emcc -c` が rc 1 になるため、`p0c/f80_lower.py` を明示の段として通す (bit-exact 未検証)。 total2 外の非共通は 2,653 関数 / 1,200,793 B 残り、閉包はなお下限 (#667)。
- host 呼出面・kernel 依存を total2 で再計測 (§3b: host site 152 → 184 → 193、新規 kernel 呼出 3 site)。 C4 の補強 (反例注入 7/7 で検出、命令境界外 E8/E9 6,226 機会のうち閉包を偽に広げる先 0 件)。 検証 HEAD・実測秒・ネガコンは REPORT_LEA.md §6b。

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

| block | lift rc | final.ll define | `.pdata` で define 無し (B) | f80 関数 | 未実装 helper | `emcc -c` | fixcmp 後 `emcc -c` | lift 秒 |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 23664 | 0 | 5993 | 3 / 5160 (2239 B) | 2 | 188 | 1 | 1 | 287 |
| 23677 | 0 | 2525 | 1 / 2355 (61 B) | 1 | 128 | 1 | 1 | 139 |

- `.pdata` で define 無し = `function_<開始VA>` の define が final.ll に無い range 数 (`engine_defs.py`。 分母は `.pdata` 関数数、括弧は欠けた range の合計長)。 参照されている (link 時に未解決になる) 件数は 2 本とも 0。
  逆に range 内部に別 define が増えた件数は 23664 で 833、23677 で 170 (RetDec の関数境界統合・分割)。 f80 関数は 2 / 1 本 (#197 の `f80_lower.py` の適用対象)。
  未実装 `__asm_*` helper は 188 / 128 件 (#629 取り込み後の再測定。 旧版 215 / 151)。 CPUID 分岐で SSE 路に固定できるかは未確認。
- **根本原因と修正 (共有鎖 `tools/plugins/lift/passes/`)**。 修正前 HEAD 190f1d8 の再現: 23664 は `use of undefined value '%15'`、23677 は E1 → (`engine_fixcmp.py` 後) `zext 0 to i64`。 `emcc -c` は最初の型エラーで止まるため、1 件直すと次が出る (出た順)。
  | # | 症状 (最小再現で確認) | 根本原因 | 修正 | 効いた block | main の P-F1 / P-F2 との関係 |
  |---|---|---|---|---|---|
  | 1 | 23664 `%15` dangling use (`function_18014f8a0`) | `fix_asm_stores.py` P-S1d が `call __asm_movdqu` + `sext` の定義行を空行化するが、`store i64 %15, ptr %r9.1.reg2mem` 等 store 以外の使用を数えない | 他の使用が残る定義は消さない (使用数を数える) | 23664 | 無関係 (main の `fix_asm_stores.py` に使用数の数えは無い。 PR のみ) |
  | 2 | 23677 `zext 0 to i64` | `ir5_patch.py` A8 `fold_const_ops` が外側 (`trunc (add (zext (xor ..)))`) を畳めない時に `pos = j + 1` で次へ進み、内側の `zext (i32 0 to i64)` を走査しない。 A4 が xor を `0` にした後に残る。 `_src_pref` の型欠けではなく**畳み込み漏れ**で、A9L が型無しで命令化した | 外側が畳めなくても `pos = idx + 1` で内側へ入る (2 箇所) | 23677 | **同じ箇所の別修正ではなく統合済み**。 main (#545 `efcb0e3c`) が `[P-F1]` として同じ `pos = idx + 1` を入れており、PR はそれを取り込んだ。 PR が新たに足したのは行 7 の型幅マスクのみ |
  | 3 | 23677 `zext constexprs are no longer supported` (`rep_stosq_memset` 第 3 引数) | A9L 固定点反復 `lift_residual_constexpr` が、命令を挿入しない行書換 (`bitcast (ptr X to ptr)` の no-op 除去) を捨てて `changed` を立てず、外側の `icmp`/`zext` 定数式が残る | 行だけ書き換わった場合も採用して反復を続ける | 23677 | **同じ箇所の別修正ではなく統合済み**。 main が `[P-F2]` として同じ判定 (`if ins or newln != ln`) を入れており、PR はそれを取り込んだ |
  | 4 | 23664 `invalid use of function-local name` (`glOrtho` の `double bitcast (i64 ptrtoint (ptr @0 to i64) to double)`) | A9L が `bitcast (i64 %v to double)` の型を落として `double bitcast (i64 %ce.. to double)` を残す | `bitcast iN %v to double/float` は型付き命令として挿入 | 23664 | **main と別修正**。 `[P-F2]` は no-op 除去の判定だけで、`double/float` の型保持は main に無い。 PR 追加分 (`_lift_one_line` の 1 hunk) |
  | 5 | 23677 E1 `icmp eq ptr %45, %arg1` | `fix_ptr_params.py` は `ptr %argN` を探すが `icmp P ptr %a, %argN` は型が先頭オペランドにしか付かず一致しない。 #523 E1 と同型 | `icmp` の `%argN` オペランドを `inttoptr` 経由にする | 23677 (23664 の `%arg3` も) | **別修正** (E1 の 2 pass、下記)。 main の `fix_icmp_ptr.py` (#545) とは対象が違う |
  | 6 | 23677 `do not know how to soften fp_extend` (x86_fp80) | wasm バックエンドが f80 を扱えない (23677 は f80 関数 `function_18012d290` 1 本。 #197 の対象) | 既存 `p0c/f80_lower.py` (x86_fp80 → f64) を `engine_lift.sh` が fixcmp 後に適用して再度 `emcc -c` (f80 tokens 11 → 0) | 23677 | 無関係 (`p0c/f80_lower.py` の既存 pass を当てただけ) |
  | 7 | (#643 review 指摘 1) `zext (i8 -1 to i64)` が 2^64-1 になり、`sext` が元の符号ビットを見ない。 入れ子の cast を走査するようになって露出 | `fold_const_ops` の cast 畳みが宛先幅のマスクだけを使う | 元の型幅でマスクし、sext は符号拡張してから宛先幅に合わせる。 回帰テスト `passes/test_fold_const_ops.py` (旧版で 3 件 FAIL、修正後 4 件 PASS) | 実 block への効きは未計測 (後段の T0/T1 は rc のみ) | 行 2 の統合 (P-F1) で露出した誤りで、PR で追加 |
  - `engine_fixcmp.py` は 5 により不要になった (修復 operand 数 23664: 7 → 0、23677: 11 → 0。 スクリプトは診断用に残す)。
  - 退行確認 (共有鎖を変えたため): Delphi 殻 7 閉包は `sampler_e2e.sh` が exit 0・7/7 `emcc_c=0` (§6)。 T0 バッチは §6。 修正前 pass での 23677 `.lift.ll` は `zext 0 to i64` 2 件・A9L 残存 53 件、修正後は 0 件。
  - 同型の `v = k & ((1 << tid) - 1)` (元幅を使わない cast 畳み) は PR 外の `tools/m3/ir_patch.py`・`tools/m5/ir5_patch.py`・`tools/targets/kilohearts/snapins/lift/ir5_patch.py`・`tools/targets/kilohearts/poc_gain/ref/ir5_patch.py`・`tools/targets/freshair/ref/ir5_patch.py`・`tools/liftlib/liftlib/passes/base.py` にもある (行 7 と同型)。 本 PR では触らず、§7 に起票行は未作成 (PM 判断)。
- `emcc -c` は clang が最初の型エラーで止まるため 1 件ずつ露見する (到達性の下限)。
  - 23664 は `engine_fixcmp.py` 後も行 1 で止まる。 23677 は行 5 (E1) の後に行 2 が残る。
- **RetDec の C バックエンドが支配的** (経緯の全文は `REPORT_APPENDIX.md` §D): C 出力段が終わらず RetDec を止めた。 `lift_from_ll.sh` で `.ll` 出力後に止めて後段 pass 鎖だけ走らせる方式に変えた (共有鎖は変更していない)。
- 判定 (`judge.py engines`) = lift_rc 0 / defines>0 / pdata>0 / 行が揃う / 最終 IR の `emcc -c` rc 0 (`emcc_c_rc_after_f80`) / `missing_ref` 0。 不合格は exit 1。 以上は到達性の実測で、engine の正しさは示していない。 殻 (Slicer 2) との結合方式 (`DispatchToEngine`・LoadLibrary 経路) は未解析。

- E1 (`icmp P ptr %a, %argN` の i64 被演算子) は 2 pass で直す: `fix_ptr_params.py` (ptr 仮引数を i64 化し、その使用箇所に inttoptr・PR 追加) と main の `fix_icmp_ptr.py` (i64 被演算子に inttoptr・#545)。 合成 `.ll` で役割分担を確認: 片方だけでは残りが落ち、両方を順に通すと二重の inttoptr は出ない。 統合は別 issue。
- `fold_const_ops` (`ir5_patch.py`) は cast の元の型幅でマスクし、sext は符号拡張してから宛先幅に合わせる (5bc59f1)。 回帰テスト `passes/test_fold_const_ops.py` 4 件。 旧版では 3 件 FAIL (255 / 65535 / 2^64-1)。 19048 の i32 仮引数の型揃え (#1834) は [REPORT_APPENDIX_1834.md](REPORT_APPENDIX_1834.md)、 `emcc_c_rc_after_fixcmp` 1 → 0。

## 6. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner)

検証起点 commit は **4c3ae00** (origin/main 1358c61 = #551 merge 済み を取り込んだ merge commit)。 4c3ae00 → 209dc3c5 で検証経路 (`tools/plugins/lift/`・`sampler_e2e.sh`・`sampler_engines.sh`・`engine_lift.sh`・`judge.py`・`targets.py`・`report_tables.py`) は無変更。 追加は #537 の `indirect_*` 群のみで、e2e・engines の経路からは呼ばれない。 4 core / 15 GiB の Actions runner、逐次、`TMPDIR=$RUNNER_TEMP`。

| 項目 | 実測 (4c3ae00) |
|---|---|
| `sampler_e2e.sh` (inventory 込み、`work/` 無し) | exit 0、**886 s**。 judge shells **PASS 7/7** (`declares_unimpl` 全 0、許容 0 件)、matrix **54/54**、ids_crosscheck 7/7 |
| `sampler_engines.sh` | exit 0、**318 s**。 `judge engines` **PASS 2/2**。 23664: lift 295 s・define 5,993・最終 `emcc -c` 0・`missing_ref` 0 / 23677: lift 141 s・define 2,524・0・0 |
| `passes/test_fold_const_ops.py` / `test_ir5_constexpr.py` | OK / OK |
| `sampler_nega.sh` / T0 / T1 | **未測定** (本 run の時間上限)。 旧値は `REPORT_APPENDIX.md` §C (7ffab50 基準) |

以下は旧検証 (5abf4d5 以前) の記録。

| 項目 | 実測 |
|---|---|
| **HEAD 5abf4d5 (#629 取り込み後)** `sampler_e2e.sh` | exit 0、**349 s** (開始時 load 0.72)。 `judge shells` PASS 7/7、許容 (`ALLOW_UNIMPL` / 名前リスト) は空、`matrix_check` 54/54、`ids_crosscheck` 7/7 |
| **HEAD 5abf4d5** `sampler_engines.sh` | exit 0、**291 s**。 engine 2 本 `judge engines` PASS 2/2。 未実装 helper 188 / 128 |
| **HEAD 5abf4d5** `sampler_nega.sh` | exit 0、**11 s**。 NC1–NC7 は全て期待どおり (期待外の rc なし) |
| **HEAD 5abf4d5** `ids_crosscheck.py` / `unreached_unique.py` | exit 0、2 s / 2 s |
| 初回 (inventory 無し、HEAD 5abf4d5 の前段として `work/` を生成した run) | exit 0、**884 s**。 `win_funcs` 等の inventory 生成が大半 |
| 旧 (HEAD 53c2eb6、#629 取り込み前) `sampler_e2e.sh` | exit 0、**211.95 s** (開始時 load average (1 分) 1.31)。 内訳: 7 閉包の lift 79 s、残りは `closure_facts.py` + `matrix_check.py` |
| 同 (HEAD aec2fac) | exit 0、276.46 s (開始時 load 1.97。 engine の後段 pass 2 プロセスと RetDec 1 本が同時に走っていた) |
| 初版 (engine 込み、HEAD 56aeefe) | **exit 1**、921.34 s。 RetDec の C 出力段が終わらず私が 2 本を停止したため engine 判定が FAIL (§5)。 現行版は engine を `sampler_engines.sh` に分離 |
| 7 閉包の lift 秒 (`status.csv` の seconds、3 回の合計) | 76 s / 109 s / 79 s (run 2 は並走プロセスがあり Slicex 15 → 23 s、Soundfont Player 33 → 57 s)。 プラグイン別の min–max は §1 の最右列 |
| 3 回の結果一致 | §1・§3・§4 の表 (判定列・閉包値・host・kernel) は run 2 と run 3 で完全一致 (`diff`)。 `declares_unimpl` と `unimpl_names` を含む 7 行の判定列は 3 回とも同一 |
| `sampler_engines.sh` (HEAD 53c2eb6、2 本並列) | exit 0、**287.04 s** (開始時 load 0.36)。 2 回目の実行 (1 回目は `lift_from_ll.sh` の sed が段付き行を拾えず lift_rc 1 → 判定が **exit 1** で止まった。 修正して再実行)。 結果は停止再開版と各列一致 (§5) |
| `matrix_check.py` | 54/54 項目一致 (閉包 6 項目 × 7 本 + `batch` 4 項目 × 3 本) |
| `ids_crosscheck.py` | exit 0、3.16 s。 7/7 本で取りこぼしなし (§3) |
| `unreached_unique.py` | exit 0、2.66 s。 正の対照 7/7 |
| 前提 inventory (初回のみ、`work/` 無しから) | 533 s (`win_scan`〜`kernel_table`。 `win_funcs.py` が並列 14 プロセス / 4 core で大半)。 `block_manifest.json` が tarball に無く `nsis_names.py` が動かないため、`mk_blockmap.py` が `PLUGIN_MATRIX.json` から代替の blockmap (182 record) を合成 |

### gate の設計・ネガティブコントロール

全文は [REPORT_APPENDIX_GATE.md](REPORT_APPENDIX_GATE.md) (gate の判定条件・NC1〜NC7 の表)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)、host / kernel 依存の静的な数え上げ、閉包外の固有関数の静的な数え上げ。
範囲外 (本書は何も主張しない): wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp、
クリーン worktree (`env -i`・新規 `RUNNER_TEMP`) での全工程再現 (inventory は `work/` 無しから生成して run 1〜3 を実行したが、別 worktree での再現は時間切れで未実施)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件)。 Eff_Render 単位の native / wasm harness が無く、P0a/b/c が OPEN | #208 を閉じられない | #195 / #196 / #197 の完了後に #208 を再開 (Closes はその時)。 harness は #506 の REPORT §6 が提案した「[PLG-F3a]」と共用 (PM 判断) |
| Render test .flp の E2E (FL Keys / FPC / Granulizer / Slicer / Slicex / GMS の RT 列 Y) | 同上 | FLEngine 統合待ち。 親 #14 / #208 |
| 閉包外の固有関数 (§2): 推移閉包を含む lift と見積の再計算 | 見積 57.5 人日の前提・wasm リンク | **#537 (PR #624 で main に merge 済み) で推移閉包の算出と lift (7/7) は完了 (§2b)**。 見積の書き換えは PM 判断。 dynamics #200 / PR #506 にも同じ制約があるため #200 にコメント |
| 推移閉包でもなお total 外の非共通関数 2,846 関数 / 1,247,120 B (うち `lea [rip+X]` 参照 153 関数 / 38,656 B) の到達性 | 閉包は下限のまま | lea 経路は **#627 で root に足した (§2c)**。 total2 外の 2,653 関数 / 1,200,793 B は #667 [PLG-G3-6] |
| 推移閉包 (total) の host 呼出面・kernel 依存 (`closure_facts.py` は base のまま) | §3・§4 が base 限定 | **#627 で total2 版を再計測し #196 / #197 / #331 にコメント済み (REPORT_LEA.md §3b)** |
| `closure_indirect.py` の dynamics (#200 / PR #506) 等への適用 (受入条件 4) | 他ファミリの閉包も過小の可能性 | #200 にコメント (未検証)。 `plugin_closure.py` の仕様変更は不要だったため退行確認の対象なし |
| `rep_stosb_memset` 未実装 stub (Granulizer / Slicer 各 1 call site) | silent な memset 欠落 | #538 [PLG-G3-4] → #629 で解消済み (main 上で `declares_unimpl` 0 × 7 block の実測)。 本 PR で許容を撤去 |
| C++ engine / 単体 DLL 2 本の `emcc -c` 未通過 (E1・dangling use・`zext 0 to i64`)、未実装 helper 188 / 128、f80 2 / 1、RetDec C バックエンドの規模耐性 | Slicer 2 (T3) の engine、GMS (T3) | 新規 #540 [PLG-G3-2] (起票済み) (同型: #523 [PLG-F4-2]・#527 [PLG-F5-2]) |
| engine 内の f80 関数 (Slicer 2 engine 2 / GMS 1) | engine の wasm 化 | #197 (`f80_lower.py` の適用) にコメント |
| host の Dispatcher ID 88 (FPC)・101 (Granulizer) が `hs_ids.json` 未収載、独立走査のみの ID 1 / 63 / 64、slot 0x28 / 0x30 / 0x68 / 0x78 / 0xb8 / 0xf0 / 0xf8 / 0x128 の意味 | P0b の応答表の網羅性 | #196 作業 5 (0x13173a0 全 case 解析) にコメント |
| Soundfont Player の taint 版 host call が 0 site (独立走査は ID 2 を 1 site) | host 呼出面の過小計上 | #196 (ABI.md §6 の taint 精密化) にコメント |
| Balance の 80 実装表に逆引きできない kernel 呼出先 (FPC 3 / Granulizer 4 / Slicer 4 / Slicex 2 site) | P0c の差分試験対象外 | #197 にコメント |
| Slicex が使う 0x5dee90 / 0x5df040 | P0c の未解決 kernel | #331 にコメント |
| Slicer 2 殻と engine の結合方式 (LoadLibrary 経路・`DispatchToEngine`) が未解析 | engine を殻に結線できない | 新規 #540 [PLG-G3-2] (起票済み) の受入条件 4 |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | 本 PR で DOC_MAP §3 に `REPORT.md`・`REPORT_INDIRECT.md` の 2 行を追記して解消 (REPORT 側の PM 追記は不要) |
| `ALLOW_UNIMPL` (`rep_stosb_memset` 用の許容) の撤去 | 撤去後も既存 CSV に対する judge は PASS 7/7 (`--skip-lift`)。 stub が戻れば FAIL する | 本 PR で撤去 (main 8d883c3 以降の実測で 7 block とも `declares_unimpl` 0) |
| lowering (f80→f64) の bit-exact 差分 (3 block) | 通過 ≠ 正しさ。 差分試験の対象外 | #197 にコメント済み (REPORT_LEA.md §7b) |
| VEX の `vcomisd` / `vucomisd` / `vucomiss` (`__asm_v*comis*`) の flag が未反映 (同一ブロック内の読みのみ反映 #1774。 残りは消費条件が IR に無い) | 2 engine の unimpl に 3 種が残る (4 件)。 stub は 0 返却のため silent な flag 欠落経路 | 子 [PLG-F3-33] (起票)。 非 VEX は [PLG-F3-34] (起票) |

- §7b の実測と方式 (#1582 [PLG-F3-12]・VEX comis/ucomis の flag 方式の検討 2 案) は [REPORT_APPENDIX_1582.md](REPORT_APPENDIX_1582.md) §7b。
- §7c の実測 (#1774 [PLG-F3-14]: 同一ブロック内の flag 反映 pass・機械語の消費命令と IR の参照・icall 別案の不採用理由) は [REPORT_APPENDIX_1774.md](REPORT_APPENDIX_1774.md) §7c。
## 8. DEFECTS.md 行案 (候補・追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| H1 stos 系 helper 未実装 stub (解消済み・履歴) | `__asm_rep_stosb_memset(ptr, i8, i64)` が `m11_simd2.py` で未実装 → 空 stub で memset されない (silent) | Fruity Granulizer / Slicer 各 1 call site | `p.simd.log` の `unimplemented: ... rep_stosb_memset`。 `emcc -c` は通る | #629 で memset に写像して解消 (本 PR で gate の許容を除去)。 行案は履歴として残す |
| H2 閉包の過小計上 | vtable override の直接呼出閉包が非共通コードの 8–35 % (バイト) しか含まず、間接呼出の到達先が lift から漏れる | §2 (7 本計 閉包外・データ参照あり 1,437 関数 / 478,062 B) | リンク時の未解決シンボル / 実行時 `call` 先の欠落。 差分試験の不一致 | データ参照ありの関数を root に足した推移閉包で lift |

## 9. 成果物

| ファイル | 内容 |
|---|---|
| `sampler_e2e.sh` | 7 閉包 → batch_lift → **判定 (`judge.py`)** → `closure_facts.py` → `matrix_check.py`。 不合格で exit 1。 `--skip-lift` / `--judge-only` |
| `judge.py` | 判定 (gate)。 `shells` (lift_rc / `emcc -c` / f80 / 未実装 helper / define) と `engines` (計測成立)。 不合格 exit 1・入力不正 exit 2 |
| `sampler_engines.sh` `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` `lift_from_ll.sh` | engine / 単体 DLL の全 `.pdata` lift・欠落監査・局所修復・RetDec 後段のみの再開 |
| `sampler_nega.sh` | ネガティブコントロール NC1–NC7 (§6) |
| `closure_facts.py` `matrix_check.py` `ids_crosscheck.py` `unreached_unique.py` `report_tables.py` | 閉包 / host / kernel / engine 外形 → `facts.json` / `PLUGIN_MATRIX.json` 突合 / Dispatcher ID の別算法検算 / 閉包外の固有関数 / 表の機械生成 |
| `closure_indirect.py` `indirect_lift.sh` `indirect_defs.py` `indirect_e2e.sh` `indirect_nega.sh` `REPORT_INDIRECT.md` | #537: 推移閉包の算出 (4 検査) → lift → 判定 (`judge.py shells` + range 欠落監査) → ネガコン NC0–NC7。 不合格で exit 1 |
| `closure_lea.py` `lea_lift.sh` `lea_e2e.sh` `facts_total.py` `lea_nega.sh` `REPORT_LEA.md` | #627: lea 参照の固定点閉包 (7 検査) → lift (f80 検出 block は `f80_lower.py`) → 判定 (`judge.py shells` + range 欠落監査) → total2 の host/kernel 再計測 (4 検査) → ネガコン NC0–NC13。 不合格で exit 1 |
| `targets.py` `env.sh` `mk_blockmap.py` | 対象の唯一の定義 / 環境 / `block_manifest.json` 不要の inventory 前提 |
