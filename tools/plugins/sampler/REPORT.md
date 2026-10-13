# tools/plugins/sampler/REPORT.md — PLG-G3 (#208) sampler 8 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/sampler/` のみ / 検証起点 commit: **@@HEAD@@**
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
   関数数で 13.4–67.2 %、バイトで 21.8–63.4 % に留まる。 閉包外のうち関数開始 VA が qword としてデータ/コード節に載っている (vtable・コールバック表の到達先候補) 関数が
   7 本計 1,437 関数 / 478,062 B。 閉包 lift だけでは wasm リンクに足りない下限であり、**見積 57.5 人日 (T 規則) の前提が崩れうる**。
   Soundfont Player の「固有 1.08 MB の内訳要精査」への答えは §2: 閉包 433 関数 / 234,911 B (21.7 %)、閉包外 2,807 関数 / 845,665 B (うちデータ参照あり 842 / 347,032 B)。
4. **host 呼出面は P0b の応答表で覆い切れない**: taint 版の即値 Dispatcher ID に `hs_ids.json` (35 ID) 未収載のものが **FPC の 88 と Granulizer の 101 (各 1 site)**、
   別算法の独立走査はさらに ID 1 / 63 / 64 (Granulizer・Slicer・Slicex) を検出した (§3)。 hostshim は未収載 ID に 0 を返す fail-soft で落ちないが、応答の意味は未解析。
5. **SIMD kernel 依存は 5 本**: FL Keys 1 / FPC 4 / Granulizer 11 / Slicer 11 / Slicex 11 site (Slicer 2 殻・Soundfont Player は 0)。 うち FPC 3 / Granulizer 4 / Slicer 4 / Slicex 2 site は
   Balance の 80 実装表に逆引きできない呼出先 (§4)。 Slicex は P0c の #331 未解決 kernel (0x5dee90 / 0x5df040) を使う。
6. **Granulizer・Slicer の未実装 helper `rep_stosb_memset` は各 1 call site**。 `m11_simd2.py` は `rep_stosq_memset` しか実装せず、`stosb` は「呼ばれたら stderr に出して 0 を返す」stub になる (memset されない)。 `emcc -c` は通るので judge の `declares_unimpl` 許容 (上限 1 + 名前の許可リスト) でのみ検出できる (§5)。
7. **C++ engine / 単体 DLL**: @@ENGINE_SUMMARY@@ (§5)。
8. **GMS (MSVC C++ 単体) は Delphi 殻の閉包方式が使えない**: vtable 規約が違い `plugin_closure.py` の対象外 (framework 一致 0)。 全 `.pdata` lift を行った (§5)。

## 1. 閉包 lift 結果 (Delphi 殻 7 本)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Gen_Render 等) から `call/jmp rel32` で到達する、
framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数 (`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ)。 iat = IAT 経由 Win32 呼出 site。

@@TABLE1@@

- 最右列の lift 秒は `lift_ranges.sh` 単独の秒 (`status.csv` の seconds、4 core の Actions runner、逐次)。 e2e 全体の秒は §6。
- `emcc -c` は `-O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- Fruity Slicer は define 121 > 閉包 119 (RetDec が range 内部に別 define を 2 つ切り出した)。 他 6 本は define 数 = 閉包関数数。 judge は define>0 だけを要求し等値は要求しない。
- 殻の直接 Win32 API (`PLUGIN_MATRIX.json` `win_direct_api`): Slicer 2 殻 = file_io 13 / dynload 4 / threads 6 / clipboard_dnd 3 / gdi_direct 6、Soundfont Player = gdi_direct 43 / threads 6 / clipboard_dnd 3 / dynload 1 / process 1、FPC = file_io 2、Slicer = process 1。 他は 0。

## 2. 閉包の取りこぼし (新規): 閉包外の固有関数

閉包は間接呼出 (vtable 経由・関数ポインタ) を辿らない。 `unreached_unique.py` で、閉包に入らない非共通関数が `.pdata` 以外の節に qword として載っているかを数えた
(非共通 = ハッシュの出現 DLL 数が 13 未満。 データ参照 = 関数開始 VA が節先頭から 8 バイト整列の qword として存在。 Delphi は vtable を `.text` に置くため `.text` も走査する)。

@@TABLE2@@

- 正の対照: 各殻の vtable override entry (最右列の分母) が全てデータ参照として検出された (検出できなければスクリプトが exit 1)。
  当初 `.text` を走査対象から外した版では 0/9〜0/11 で、対照が落とすことを確認したうえで `.text` を含めた (実測の経緯)。
- データ参照なし = 他の閉包外関数から直接呼ばれる関数・未参照関数・qword 以外の形で参照される関数のいずれか (未判別)。 データ参照あり関数からの直接呼出先 (推移閉包) は未計算で、真の追加量はこの表より大きい。
- 含意: MATRIX の `lift.closure_*` は「vtable override の直接呼出閉包」であり、Eff_Render / Gen_Render が間接呼出で到達するプラグイン内クラス (Slicex 289 / Soundfont Player 842 関数など) を含まない。 見積の再検討と推移閉包の lift は §7 の新規起票対象。
  dynamics (#506) の 7 本にも同じ制約があるが、そちらは未測定。

## 3. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

@@TABLE3@@

- **Soundfont Player は taint 版が host call 0 site** だが、独立走査は ID 2 を 1 site 検出する。 閉包 433 関数で host 呼出 0 は不自然で、taint (`this+0xbc`) が当てはまらない経路がある (taint の過小計上と推定; 原因未調査)。
- **別算法の検算** (`ids_crosscheck.py`: taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 7/7 本で taint 版 45 site を取りこぼしなく再現。
  独立走査のみが拾った差 (host 呼出か別オブジェクトの slot0 呼出かは未判別): Granulizer ID 64 × 4、Slicer ID 64 × 4、Slicex ID 1 × 1 / 63 × 3 / 64 × 4 (いずれも `hs_ids.json` 未収載)、Soundfont Player ID 2 × 1 (収載)。
- `hs_ids.json` (35 ID / 894 site) 未収載の taint 版 ID: FPC の 88、Granulizer の 101。 `hostshim.c` の `hs_dispatcher` は未収載 ID で `default: return 0` (fail-soft)。 応答の意味は P0b の case 別解析 (#196 作業 5) 待ち。
- 0x28 / 0x30 / 0x68 / 0x78 / 0xb8 / 0xf0 / 0xf8 / 0x128 などは dynamics の 7 本に出ていない slot。 P0b では 44 slot 共通の fail-soft + 呼出記録のみ (意味未解析)。 0x100 / 0x108 は ABI.md §6 が偽陽性を含みうるとする offset。

## 4. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類。 kernel 番号は Balance (block 18983) の VA に正規化済み
(`kernel_va_map` に逆引きできない呼出先は DLL 固有 VA のまま表示)。

@@TABLE4@@

- DLL 固有 VA のまま残った呼出先: FPC 0x62f4b0 (2) / 0x62f680 (1)、Granulizer 0x60b380 / 0x60b550 / 0x60b780、Slicer 0x60d1e0 / 0x60d3b0 / 0x60d5e0、Slicex 0x635770 (2)。
  Granulizer と Slicer は開始 VA の差が一定 (0x1e60) の同形 3 関数。 sampler 固有の補間 kernel と推定 (未解析)。 P0c の 80 実装表に無いので P0c の差分試験対象外。
- P0c (`p0c/REPORT.md`) の現状 (本 PR では再測定していない): 0x5df240 は f32 mul 系で出力バッファ bit-exact (§3・§12)。 0x5dee90 / 0x5df040 は #331 の未解決対象 (§14.4、Slicex が使う)。
  0x5dee50 / 0x5de410 / 0x5dffc0 / 0x5dfff0 / 0x5de540 は `p0c/REPORT.md` に VA の言及が無い (grep)。
- DLL 固有関数走査の site 数 (最右列) は閉包外も含む。 閉包 / frontier 外にある分は framework の深い関数か閉包外の固有関数 (§2) と推定 (未確認)。

## 5. C++ engine / 単体 DLL (engine 2 本相当)

@@SECTION5@@

## 6. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner)

@@SECTION6@@

## 7. 未解決 (起票先付き)

@@SECTION7@@

## 8. DEFECTS.md 行案 (候補・追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| H1 stos 系 helper 未実装 stub | `__asm_rep_stosb_memset(ptr, i8, i64)` が `m11_simd2.py` で未実装 → 呼ばれると stderr に出して 0 を返し memset されない | Fruity Granulizer / Slicer 各 1 call site (`rep_stosq_memset` は実装済み) | `p.simd.log` の `unimplemented: ... rep_stosb_memset`。 `emcc -c` は通る (silent) | `m11_simd2.py` に `rep_stosb_memset` を足す (memset へ写像)。 `judge.py` は許容リストで名指しして検出 |
| H2 閉包の過小計上 | vtable override の直接呼出閉包が固有コードの 22–63 % しか含まず、間接呼出の到達先が lift から漏れる | §2 (7 本計 閉包外・データ参照あり 1,437 関数 / 478,062 B) | リンク時の未解決シンボル / 実行時 `call` 先の欠落。 差分試験の不一致 | データ参照ありの関数を root に足した推移閉包で lift |

## 9. 成果物

| ファイル | 内容 |
|---|---|
| `sampler_e2e.sh` | 7 閉包 → batch_lift → **判定 (`judge.py`)** → `closure_facts.py` → `matrix_check.py`。 不合格で exit 1。 `--skip-lift` / `--judge-only` |
| `judge.py` | 判定 (gate)。 `shells` (lift_rc / `emcc -c` / f80 / 未実装 helper / define) と `engines` (計測成立)。 不合格 exit 1・入力不正 exit 2 |
| `sampler_engines.sh` `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` `lift_from_ll.sh` | engine / 単体 DLL の全 `.pdata` lift・欠落監査・局所修復・RetDec 後段のみの再開 |
| `sampler_nega.sh` | ネガティブコントロール NC1–NC7 (§6) |
| `closure_facts.py` `matrix_check.py` `ids_crosscheck.py` `unreached_unique.py` `report_tables.py` | 閉包 / host / kernel / engine 外形 → `facts.json` / `PLUGIN_MATRIX.json` 突合 / Dispatcher ID の別算法検算 / 閉包外の固有関数 / 表の機械生成 |
| `targets.py` `env.sh` `mk_blockmap.py` | 対象の唯一の定義 / 環境 / `block_manifest.json` 不要の inventory 前提 |
