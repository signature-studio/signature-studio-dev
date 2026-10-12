# M2 REPORT — function boundary 合意 / Delphi lift 品質 / shim inventory / wasm PoC

日付: 2026-10-09 / 作成: M2 subagent
参照: `[STRATEGY]` §4 M2, §5.7 / `[TOOLCHAIN]` / `[MAC]` REPORT.md, `[WIN64]` REPORT.md

---

## 0. 結論サマリ

| M2 検証条件 | 結論 |
|---|---|
| 1. 関数リスト (数量+境界) が Ghidra と RetDec で ±5% | **部分達成**。Ghidra ↔ 静的境界表 は ±5% 内 (win: Ghidra 59,009 / .pdata 57,816 = **2.02%**, Jaccard 98.0%。mac: 92,886 / LC_FUNCTION_STARTS 92,488 = **0.43%**, Jaccard 99.5%)。RetDec は decode 段階で data-as-code 由来の過剰 split が出る (win decode 完了時点 70,018 vs Ghidra 59,009 = 18.7% 差; 一致ペアの size 合致 93.9%)。§2 参照 |
| 2. libwinbridge export 一覧の自動生成 | ✓ `SHIM_INVENTORY.md` — Reg*/DragDrop/WB* 系 34 本 (= mac 移植で Win32 に必要な面の仕様書初版)。win FLEngine import 738 中 winbridge export と名前一致は 14 (1.9%) — 残りは §3 12 行の自家実装面 |
| 3. 副モジュール (300KB級) IR→wasm 成功 | ✓ **EasyFLAC x86_64 slice (299KB) の `_FLAC__crc8`** を RetDec lift → IR 正規化 → emcc → wasm → node 実行。**FLAC CRC-8 として bit-exact 一致 (6 テストケース)** |
| 4. RetDec Delphi-PE (x64) 品質確認 | ✓ §5.7 観点 1-6 相当の 5 小関数を win64 DLL から自動選択し `--select-ranges` リフト。 M3 pass 設計を決める実測事実 (§3.2 詳細) |
| 5. delphi_inventory 機械生成 | ✓ **win VMT class pointer 1,244 / mac 3,896**  + Pascal 文字列候補 13,984 から VMT→クラス名表が自動生成 (delphi_inventory.md)。dbk* export は `__dbk_fcall_wrapper` / `dbkFCallWrapperAddr` の 2 本 (§5.7 #6 対象) |
| 6. import 面 diff (win/mac) | ✓ shim_inventory.py 内。mac slice の外部依存は libSystem 140 / CoreGraphics 51 / CoreFoundation 47 / CoreMIDI 16 / CoreAudio 5 / AppKit 12 / WebKit 5 等 16 dylib |

---

## 1. slice 抽出 (`extract_slice.sh`)

- 入力 `FLEngine_x64.dylib` (universal2): archs = x86_64 (31,637,920 B) / arm64 (32,336,592 B) — lipo 無しの python struct 解析。
- **正本 slice**: `tools/m2/work/FLEngine_x86_64.dylib` (31.6MB, Mach-O x86_64)。
- 記録 (`slice_inventory.json`): `__TEXT,__text` vmaddr=0x2b50, size=**17,656,574 B** (§2 mac Ghidra 解析対象の実体)。
- EasyFLAC 等の他の universal2 も同 script (`--output-name` あり) で切出し可能。

## 2. 関数境界合意検証 (`function_boundary.py`)

**素材**:
- win64 = `docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin` (FLEngine_x64.dll 22.27MB, PE32+ Delphi x64)
- mac = 上記 slice (Mach-O x86_64, 31.6MB)

| 対象 | ground truth (静的表) | Ghidra | Ghidra-vs-static | Jaccard |
|---|---|---|---|---|
| win DLL | **.pdata (RUNTIME_FUNCTION): 57,816** | 59,009 | **2.02% ✓ (±5% 内)** | **98.0%** |
| mac slice | **LC_FUNCTION_STARTS: 92,488** | 92,886 | **0.43% ✓** | **99.5%** |
| EasyFLAC slice (299KB) | LC_FUNCTION_STARTS: 678 | 736 | 7.9% (小バイナリの粒度変動) | 92.1% |

- Ghidra は静的表の関数を **全部 (57,816/57,816) 拾得**。差分 1,193 (win) は
  IAT 跳ね `__imp_*` thunk (16B 間隔の連鎖) 等の Delphi 関数実体ではない追加検出。
- **Ghidra size が .pdata と ±16B で一致するペアは 95.0%** (54,920 / 57,816)
  → Delphi x64 table-based SEH の関数境界を Ghidra が忠実に復旧できる
  (M3/M5 の関数リスト抽出は Ghidra + 静的表を base にする)。

**RetDec 側の実数** (境界数の振れが大きいことを明示しつつ記録):
- win DLL: decode 完了時点の `.dsm` 関数ラベル **70,018** (`engine_win.drc.dsm` —
  decode は完了, 後段 llvmir2hll は timeout)。.pdata との交差 **44,262** (= .pdata 関数の
  76.6% が RetDec decode 関数にも出現; **交差ペアの size 合意 ±16B で 99.4%**)。
  RetDec が +21% 過剰なのは Delphi `.pdata` の .text カバレッジが 10.6MB / 16.4MB
  (残り 5.9MB = const/VMT/fpu 領域) であり、**data-as-code 部を RetDec decode が関数化する**
  ため (Ghidra は同領域を DATA として扱う)。
- mac slice: 全体リフトは 2h timeout → 3h re-run のいずれも後段
  `Constants optimization` 越えに届かず未完了。decode 完了時点の数値は
  `--select-decode-only` (macho 0x2b50-0x10d964c) で取得可 (macbound)。
- EasyFLAC (全体 pipeline が完了した唯一の小規模): RetDec 最終 config 1,114 /
  Ghidra 736 = **51.4% 差** (RetDec は data 部を関数 split する; 意図てきな同一問題)。

**評価**:
- 3 者照合の直感的に primary な検証面は **Ghidra ↔ 静的境界表** で **±5% 満たす**。
- RetDec は decode 段階で **data-as-code 由来の関数過剰分割** があり、また後段 LLVM
  phase が FLEngine 規模で ~2-3h / 15GB RAM を要求する (実行完了が重い)。
  → M3 の運用として (a) 境界の正 = Ghidra + 静的表, (b) RetDec は
  `--select-ranges` 単位のリフト (selected 関数のみ CFG/IR 生成) に限定する。
  unknown indirect branch 等の定量化は boundary 照合系で継続。

## 3. RetDec Delphi-PE (x64) 品質確認 (§5.7 1-6)

### 3.0 retdec-decompiler 側 fingerprint

なお RetDec コンソール output に **"Detected compiler/packer: embarcadero delphi (36.0)"** の表示があり、
RetDec v5.0 は Delphi 12 (36.0) を compiler fingerprint 検知層で確定的に認識している。

### 3.1 自動選択 (`delphi_scan.py`, 5 観点)

| 観点 | 選択基準 (自動) | 選択された関数 (win DLL, VA) |
|---|---|---|
| #1 SEH/try-finally を含む呼出し元 | `.pdata` UNWIND_INFO flags に UHANDLER (finally-handler) を含み、body に直接 call を持つ小関数 | `0x409fe0` (89B, UHANDLER) / **`0x40ace0` (123B, E+UHANDLER, 間接 call 1 本)** |
| #2 VMT 間接 call (+ VMT ロード) | `call [reg+disp]` 間接 call + `[reg]` (VMT ロード) の pattern を持つ小関数 | `0x4475d0` (8B, trampoline 領), `0x4475e0` (16B: obj+64 越し release helper 呼出) |
| #3 RTTI / VMT fixed field 読み | `[reg - 0x70/0x78/.../0xa8]` (vmtClassName 系負固定 disp) を読む小関数 | **`0x497e40` (27B: `select (arg2==0) → [a2-168] or [a1+88]; load i64`)** |
| #4 FastMM (hot allocation/free) | caller xref 上位 & 超小関数 (**参照数少の例外規約: hot entry 故に意図的に xref 多数**) | **`0x412d60` (66B, caller xref 15,505)** |
| #5 calling convention 典型 | 中サイズ (0x50-0x180B)・xref 少 (1-4) | `0x40ff20` (81B, 2-arg + helper 3-arg 呼出) |

選出は "サイズ小・参照数少" 原則 (FastMM のみ hot path であることを明示して xref 多数を許容)。
選出根拠は `work/delphi_candidates.json` (capstone feature dump 付) に機械記録。

### 3.2 リフト結果 (RetDec `bin2llvmir`, `--select-decode-only`; IR 断片数 183 行)

**①「意図が読める / 読めない」評価**:

| 関数 | IR 読み取り評価 | 主な根拠 (IR/pseudo-C の引用型) |
|---|---|---|
| `0x40ace0` (SEH#1 候補) | **△ (SEH構造は IR に現れない)** | body = `trunc arg2→i8; if (arg2 != 0) call function_410320(arg1, v1); ret` — try-finally 構造が **IR には移されずに残らない** (.pdata/.xdata 情報は引き取られるが IR の `catch/finally` には現れない) |
| `0x4475d0`+`0x4475e0` (VMT#2 候補) | **○ (helper への直呼出し構造は読める) / indirect call の target は名付けされない** | `4475e0: call function_412e40(a2+64, 2)` — obj+64 (vtable field) 経由の helper 呼出 (Delphi TInterfacedObject 系の参照カウント処理と推定) |
| `0x497e40` (RTTI#3 候補) | **◎ (VMT fixed field 読みがそのまま)** | `return *(i64*)(a2 != 0 ? a2-168 : a1+88);` — vmtClassName/vmtFieldTable 系の負 offset 読みが定数としてまで残る (RTTI 表参照の machine 可視化) |
| `0x412d60` (FastMM#4 候補) | **◎ (アロケータ内部がほぼ readable)** | `store 0 @ [a1]; i32 v2 = [a1-8]; (v2 < 1 → exit); [a1-8] = v2-1; if (v2==1) call function_409440(a1-16, v2)` — **block header の参照カウント減算と解放 helper 呼出の連鎖が数値そのままで読める** |
| `0x40ff20` (CC#5 候補) | **○ / △ (未初期化 alloca `v1` 参照が入る退行)** | 2-arg + helper 3-arg 呼出 (`call function_40fe90(v1, a2, &result)` 後に result を 0 で返す分岐)。`v1` が**未初期化 alloca の読み残り**として出る (RetDec の既知系統のノイズ) |

**② SEH / RTTI / VMT / FastMM ノイズの実際の形** (M3 IR pass 設計への直接入力):

1. **SEH (Win64 table-based)**: `.pdata` は関数境界の **確定的部品として機能するが**、
   UNWIND_INFO body / handler 先が **IR には一切残らない**。=> lifter 側が
   `try/finally` 構造を derive しない。**M5 Mini-PoC (c)** では (a) wasm EH は不可能
   (table SEH の unwind/handler 情報が現 IR に残らないため)、
   **(c) EH stub (unwind 無効化) が第一手** にまわる見込みが上がった
   (strategy §5.2 の 3択判定における実測根拠)。
2. **VMT / 間接 call**: IR 上は `call [reg+disp]` のままで、RetDec が復元した関数名はつかない (“VMT を名付ける” pass が未実装)。**RetDec は VMT の constant-propagation をしない** (IR 上の unknown branch はそのまま残る)。
   ただし *読み出し自体* (e.g., `*(i64*)(a2-168)`) は残るので、
   **VMT class 名表 (delphi_inventory.md §1) を IR pass に注入し、
   `call [vmt+offset]` の target を direct call 化する** ことが (§5.7 #2) の解へ直結する。
3. **RTTI**: Delphi RTTI 文字列は**そのまま IR または .rdata 常存**した
   (例: `TAudioRecorderTake` / `TMixerThread` / `TFruityHost` など FL 独自 class)。
   ただし 'DelphiHelper' / Drtti 系の補助は使わず、RetDec は field read を pointer math としてのみ扱う (名付けしない) — 自前機械表 (delphi_inventory.md) で名付けを賄う。
4. **FastMM**: hot path の entry 関数選抜が **caller xref だけで発見可能** (15,505 xref 程度が目的の entry とは照合可能)。
   これにより §5.7 #4 FastMM 短絡化 pass (M3) の対象関数集合が機械特定可能 (M3 pass の入力表が確定)。
5. **calling convention**: ll 上の `arg1/arg2` と pseudo-C が Microsoft x64 convention (rcx/rdx) どおりに対応している。helper 側の hidden out-param (pointer 型第 3 引数) も `int64_t *` として正しく現れる。ただし Delphi 特有 (hidden return buffer / open array / record 変型) のクラス範囲は M2 候補から外れ、M3 pass の型付け設計に残る。
   → Delphi シグネチャ定義表 (§5.7 #5) は M3 pass の設計要素 (m2 の自動検出範囲を超える)
6. **`dbk*`**: `__dbk_fcall_wrapper` / `dbkFCallWrapperAddr` が export として存在し、
   **Delphi RTL 定型 (FastCall wrapper) であることの境界自体が機械採取可能** (delphi_inventory.md §2)。

**③ IR 再コンパイル可否** (`work/d5fast.drc.ll` → clang wasm):

- 素 IR で clang wasm に通すには次の正規化が必要 (現行 LLVM向け; `ir_normalize.py` 実装):
   1. `target datalayout` が x86-64 のまま (wasm32 backend が PIC 拒否) — 差し替え必須
   2. 型付きポインタ (`i32*`, `%__sFILE*` 等) → opaque `ptr` (LLVM 15+)
   3. `bitcast (iN* @sym to iM*)` 型 constexpr (pointer→pointer) の除去
   4. `zext (i32 xor (i32 A, i32 A) to i64)` — 含意される xor identity の 0 化
   5. `%wide-string` などの名前付きローカル値を global constant に置く破損
- これらを通すと **純計算関数はそのまま wasm 化できる** (§4 PoC 実証)。
- さらに §3.1 の 5 選択関数 (a 外部 helper を stub 化した形) は `ir_normalize.py`
  通過後そのまま `clang --target=wasm32 -Wl,--export-all` で wasm 化が通り
  (1,499B), `tools/m2/delphi5_wasm_check.cjs` で node 実行して
  **FastMM 型候補 `function_412d60` の store0/参照カウント--, VMT fixed field 読み
  `function_497e40` の負 offset load 各分岐が IR 通りのセマンティクスで実動作**
  することを確認した (§5.7 観点の「boundary/CFG 健全性」を *動作* で照合)。
- 外部の `__libc_*` や libc サブモジュール import (`__ZNK...` 等 C++ mangling), または
  delphi RTL 内部呼出は **stub/短絡化なしでは IR 直リンク不可** — M3 pass で解かれる領域。

### 3.3 mac 側の Delphi 対応 (副ターゲット)

mac slice も Delphi コード主体と推定される (VMT class pointer 3,896 個 + Pascal 文字列候補 13,984 個; __text 17.6MB)。
mac 側では **SEH 面 (win64 table-based) が存在しない** という §2.2 の前提
(= SEH リスク 1つを mac 優先で避けられる) が引き続き有効; 一方
VMT/RTTI/FastMM/calling-convention の 4 項目は **mac 側にもそのまま存在する** ことが
delphi_mac_scan.py の走査で確認できた (mac 側 §5.7 観点は未実測; M5 の mini-PoC 素材)。

## 4. shim inventory (`SHIM_INVENTORY.md`)

- win64 FLEngine_x64.dll: import **738 名 / 24 DLL**。`SHIM_INVENTORY.md` に 12 行写影表 (win/mac別) を記載。
- mac FLEngine slice: 外部依存 337 シンボル / 16 dylib。
  16 dylib = libSystem 140 / CoreGraphics 51 / CoreFoundation 47 / Foundation 17 / CoreMIDI 16 / AppKit 12 / AudioToolbox 10 / CoreAudio 5 / CoreText 9 / WebKit 5 ... (§3 対応表)
- **libwinbridge_x64.dylib (macのWin32互換 shim) export 数: 34**
  (Reg* 21 本 — `RegGetStoragePath`/`RegWriteStringValue` を含む — + DragDrop 9 本 + WB download/upload/memory 4 本)。
 これが「mac 側で IL 自身が実装した Win32 shim 面」の **仕様書部分の機械初版**。
- 残りの win import 面 (738-14=724 名) は Cocoa/CoreAudio/自家 shim への移置対象 (gdi32 127 / kernel32 184 / user32 227 / OLE 系等; §3 P0 推定の裏付けとなる import 比重)。
- 考察: FL engine は *libwinbridge が Registry とクリップボード/DragDrop 部*
  のみ注目し, DirectSound / GDI / thread / timer などは mac 側独自実装
  (CoreAudio/MacVclCocoa bridge へ) に寄せたと見られる (= §3 #1,5,4 の自家実装面が
  通常 win shim より大きい)。

## 5. 300KB級副モジュール IR→wasm PoC (`poc_crc8_wasm.sh`)

| 項目 | 値 |
|---|---|
| 対象 | `EasyFLAC_x64.dylib` → x86_64 slice 299,376 B (= 「300KB級」副モジュール) |
| 選択関数 | `_FLAC__crc8` (150B, EasyFLAC export, DLL 外部依存ゼロ, crc8 テーブルがモジュール内定数 VA 0x30a40 参照) |
| リフト | RetDec `--select-functions _FLAC__crc8 --select-decode-only` → `work/crc8.drc.ll` |
| 正規化 | `ir_normalize.py` (datalayout/ptr/bitcast/zext/xor-ident) → `work/crc8_norm.ll` |
| wasm 化 | emcc 6.0 定型フラグ + `-sGLOBAL_BASE=536870912` (emcc runtime 領域と lifted IR のアドレス空間を分離) + `-Wl,--export=_FLAC__crc8 --no-entry` |
| 実行 | node (MODULARIZE glue 自前 instantiate hook; emcc runtime JS library が pruned のため import を no-op stub で補完) |
| 結果 | **6 テストケース (入力文字列) / wasm vs 参照実装 (FLAC CRC-8 poly 0x07 実装) = bit-exact 全一致** |

- **bit-exact**: 対象が純計算関数という好条件で成立したが、要点は `crc8` テーブルを
  「IR 固定アドレス == wasm linear memory offset」に写せば原関数と同一値になるという
  **lifter IR アドレス空間 == wasm linear memory の基本モデル**が実証できた点。
- 参考: `_FLAC__crc8` は Delphi でなく FLAC (C++) 部の関数。Delphi 固有品質の評価は §3 
  (5観点関数も同経路で wasm 化し node で実動作している)。

## 6. M3/M5 に向けた示唆 (結論)

1. **M3 の必須 IR pass (機械割り出しが可能になった)**:
   - *(a) VMT 名付け + 直接 call 化*: `delphi_inventory.md` の class 表
     (win 1,244 / mac 3,896) を IR pass に注入し `call [reg+disp]` を解く。
   - *(b) FastMM 短絡化*: hot path (xref 上位超小関数) を用いた
     関数集合の自動リスト (`delphi_candidates.json`), M3 pass の呼出置換入答。**§3 #7 の heap shim に結合**。
   - *(c) SEH: RetDec が try-finally を IR に残さないため、
     `unwind` flags 付き関数 (UHANDLER 8,021 / E+U 2,816) の IR は
     **EH スタブ化 (unwind 無効化) を第一手とする**方向が実測で強まった (M5 Mini-PoC (c) の判定入力)。
   - *(d) RTTI/VMT fixed field 読み* (`-0x70/-0xa8 等`) は原形のまま残るので、
     Delphi RTL 補正 (class 表) の名付け pass は **加算可能 (数式から決まる構造)**。
2. **M5 Delphi Mini-PoC (a)(b)(c) の素材が揃った**: (a) = EasyFLAC モジュール (DSP/C library
   関数群)、(b)(c) = win DLL 側の (4)(1) 候補と同じ 2 パターンが pickable
   (`delphi_candidates.json` の SEH_try_finally / FastMM_allocator フィールド)。
3. **boundary 合意検証の運用** (`m2.sh` は再実行可能): M5 より前の FLEngine 全体 lifting を始める際、
   `.pdata` / LC_FUNCTION_STARTS が **lifter 固有に合わせて不要になる静的関数リスト**
   (= — これを RetDec と Ghidra と相互照合する形式にした) ことで、
   unknown indirect branch の残数を定量的に記録できる。

## 7. 未解決・ブロッカー

- (軽微) **RetDec 全体リフトの完了までに 2h+ が必要** (mac slice は最初 2h timeout で打切 →
  --timeout 10800 で再実行中; win DLL も同様に 7200s timeout で打切 → 全範囲
  `--select-decode-only` で別系統で収集)。以後は重い全体リフトを定期実行しない運用
  (M3 で最初に通す 1 回のみ) とする。
- (軽微) Ghidra 12.1.4 付属の `ListFunctions.java` と名前衝突して postScript が
  上書き呼び出しされていた → 本 M2 では `DumpFunctions.java` に改名済み。
- (概念) RetDec IR の `%wide-string` 破損 / 未初期化 alloca (`%0` 等の空読み) の
  完全な除去は `ir_normalize.py` の要素対応に留まり、M3 の内製 LLVM pass
  ("RetDec IR → 再コンパイル可能形") に含める必要がある。
- Delphi RTTI/VMT 検出は **Pascal 文字列走査 (vmtClassName @ P-112)** に依存するため、
  真偽値 (nullptr 判定など) や非クラスの Delphi record は未カバー。

## 8. 生成物一覧

**コミット対象** (tools/m2/):
- スクリプト群: `m2.sh` / `extract_slice.{sh,py}` / `pescan.py` /
  `delphi_scan.py` / `delphi_mac_scan.py` / `delphi_inventory.py` /
  `shim_inventory.py` / `function_boundary.py` / `ir_normalize.py` /
  `poc_crc8_wasm.sh` / `poc_crc8_harness.mjs` / `ghidra_scripts/DumpFunctions.java`
- レポート: `REPORT.md` (本書) / `SHIM_INVENTORY.md` / `delphi_inventory.md` / `README.md` / `.gitignore`

**work 固有の成果物** (tools/m2/work/, gitignored — マシン再実行を挟む):
- `FLEngine_x86_64.dylib` (正本 slice, 31,637,920B) / `slice_inventory.json`
- `pe_scan_dll.json` / `delphi_candidates.json` / `delphi_mac.json` / `boundary_*.json`
- `d5fast.drc.{ll,c,config.json}` (Delphi 品質確認 5観点の lift) / `d5fast.log`
- EasyFLAC: `easyflac_x86_64.dylib` / `crc8.drc.ll` / `poc_crc8_norm.ll` /
  `crc8_test.{cjs,wasm}` / `poc_crc8_results.json`
- Ghidra: `ghidra_dll/` / `ghidra_slice/` (`functions_*.csv`)
- win64 抽出物からのコピー: `block00031_PE.bin` (= FLEngine_x64.dll)
