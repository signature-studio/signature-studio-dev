# HOSTBRIDGE — Fruity Wrapper (外部 VST ホスト経路) 解析 + wasm 同梱モジュール表の設計

> 正本: `tools/hostbridge/HOSTBRIDGE.md` (設計書・上限 300 行)。
> **行数目安**: 269 行。設計書の上限は 300 行 (`docs/DOC_MAP.md` §1) なので超過していない。

対象: FL Studio 26.1.7.5653 (win64) / 根拠ファイルは `evidence/` (Ghidra 12.1.4 の decompile/disasm を commit 済み、
再生成 `analysis/reproduce.sh`、機械検査 `analysis/verify_evidence.py` 20 項目)。
アドレスは **ImageBase 0x400000 の Fruity Wrapper 2.7.0.5653** (`fw:`) / FLEngine_x64.dll (`fle:`) / OTT_vst2_win64.dll (`ott:`, base 0x180000000)。

## 0. 要点

1. FL 本体 (`FLEngine_x64.dll`) は **VST を直接ロードしない**。`Plugins\Fruity\{Effects|Generators}\Fruity Wrapper\Fruity Wrapper_x64.dll`
   を通常の Fruity プラグインとして `LoadLibrary`+`GetProcAddress("CreatePlugInstance")` し、VST2/VST3/AU/CLAP の実ホストは **Wrapper (Delphi, 6MB)** が担う (§1.2)。
2. VST2 のロードは `fw:0x7a9db0` (TVSTPlugin ctor) に集約: `SafeLoadLibrary(path, SEM_NOOPENFILEERRORBOX)` → 26 エントリの綴り表 (重複除き 25 種) で `GetProcAddress`
   (`VstPluginMain`,`VSTPluginMain`,`main`,… 大文字小文字全順列) → `main(audioMaster)` → `AEffect.magic=='VstP'` 検査 → `resvd1=this` →
   `dispatcher(effOpen…)` (§1.3)。AEffect は Win64 配置 (8B ポインタ, 0xC0 B) — OTT のネイティブ ctor で独立に確認 (§1.4)。
3. 32bit プラグイン / "Make bridged" 指定は `ilbridge.exe` を別プロセス起動し共有メモリ+イベントで同じ TVSTPlugin コードを遠隔実行 (§1.6)。**wasm では不要** (instance 分離で代替)。
4. 設計決定: **「プラグイン 1 DLL = 1 wasm instance = 専用 linear memory」+ VST2 境界の table 駆動 marshalling** (共有メモリ方式は不採用, §2.4)。
   LoadLibrary/GetProcAddress/FreeLibrary は「事前登録モジュール表」へ解決、関数ポインタは bridge が払い出す合成 VA (thunk slot) で返す (§2.2)。
5. PoC (`bash tools/hostbridge/hostbridge.sh`, 4〜10 s): FL 側の代役 mini VST2 host (freestanding wasm32 C) が Fruity Wrapper と同じ手順で
   M10 の lift 済み OTT wasm をロードし `processReplacing` を駆動する。**検収は全項目 PASS**で、bridge 越しに
   M10 到達水準 (bit-exact 未達・junk あり) をそのまま再現する。件数・bit 一致・junk census などの**実測値は
   `tools/hostbridge/REPORT.md` が正本** (§3)。

---

## 1. Fruity Wrapper 解析

### 1.1 構成物の特定

| 役割 | 実体 (win64 抽出ブロック) | 根拠 |
|---|---|---|
| Fruity Wrapper (FL plugin API 実装 + 外部形式ホスト) | `block19091_PE.bin` / `block23676_PE.bin` — x64 PE, Delphi, 5.99 MB, ProductName "Fruity Wrapper" 2.7.0.5653, export `CreatePlugInstance` (2 本は 0.2% 差の別ビルド。Effects 版/Generators 版と推定) | `pe_metadata.json`, mac にも Effects/Generators 各 `Fruity Wrapper_x64.dylib` |
| ILBridge | `block24766` (x64, 6.2 MB) / `block24765` (x86, 4.1 MB) ILBridge 1.5.114 | VST ホスト unit (`Create VST plugin`, `Call main`) を静的内包 + `-wrapper -address -processid` |
| Plugin Manager | `block25160` PluginManager.exe 7.2 MB (`-deepscan -vstpath -flpath -add -remove`; `FLEngine_x64.dll` をロード) | 同 unit 内包 (deep scan = 実ロードして問合せ) |
| VST3 ホスト | `QuickFontCache_x64.dll` (`block24350`) — export `CreateVST3Instance`/`CreateVST3Dummy`/`GetPluginFactory`/`InitDll` | Wrapper は `QuickFontCache_x64.dll` を参照、VST3 は別 DLL で C++ 実装 |
| AU / CLAP | mac: `System/Plugin Formats/auwrapper_x64.dylib` (`formats.txt`: `0=auwrapper.dylib`)。Win Wrapper の `System\Plugin Formats\formats.txt`+`CreateFormatList` が同機構 | 文字列 |

注意: `vstplugin` PE (block24724/25, "FL Studio VSTi") は *FL 自身を VST として出す* 側であり、ホストではない。

### 1.2 FL → Wrapper (第 1 段の LoadLibrary) — `fle:0xd8cab0` (`evidence/fle_load_fruity_plugin.c`)

```
path = <Fruity plugin path> (末尾が "_x64.dll" で無ければ付与)
h    = SafeLoadLibrary(path, 0x8000)            ; fw:0x449770 と同形 = SetErrorMode(SEM_NOOPENFILEERRORBOX)+LoadLibraryW+SetErrorMode(old)
f    = GetProcAddress(h, "CreatePlugInstance")  ; wrapper の唯一の実 export (fw:0x86ab10)
plug = f(host=param_1, tag=slot)                ; TFruityPlug 実装を返す (vtable: +8 Dispatcher(id,index,value), +0x28 …)
plug->Dispatcher(3|4|1|0x15|0xc, 0, value)      ; スロット初期値 (≠0x7fffffff の時のみ)
失敗 → FreeLibrary ; "<path> is missing." のエラー
```
→ Fruity プラグイン (全 *_x64.dll) と Wrapper は **同じ "LoadLibrary+CreatePlugInstance" 機構**。モジュール表は VST だけでなく Fruity プラグイン全般の LoadLibrary 置換として働く。

### 1.3 Wrapper → VST2 (第 2 段) — `fw:0x7a9db0` TVSTPlugin ctor (`evidence/fw_tvstplugin_create.c`)

ログ文字列がそのまま手順書になっている (`Create VST plugin: file=%s id=%s` → `loading dll` → `dll loaded` → `found main function` → `Call main` → `Finished (call main)`):

| 段 | 動作 | 根拠 |
|---|---|---|
| 0 | **事前検査 `fw:0x7a9030(path, hint)`**: `fw:0x5c0200` が DLL *ファイル*を `CreateFileMappingW/MapViewOfFile` で開き PE export 名一覧を取得、小文字化 (`fw:0x437ab0`) した名前が `main` / `vstpluginmain` / `hint` (DB 側が持つ entry export 名, TVSTPlugin ctor 第 6 引数) のいずれかなら VST2 と判定。偽ならロードしない | `evidence/fw_tvstplugin_create.c` (`FUN_007a9030`)|
| 1 | `hmod = SafeLoadLibrary(path, 0x8000)` (this+0x8ac)。0 なら `Failed to load plugin dll (handle=0)` | `fw:0x449770` |
| 2 | vtbl[+0xa0](hmod) pre-hook → **FindMain(this,hmod,hint) = vtbl[+0x3b8] (= `fw:0x7ad370` と推定)**: `hint` があれば先に `GetProcAddress(hmod,hint)`、無い/失敗なら `fw:0x7a8f90`: 名前表 `0x8e5d08` の **26 エントリ**を先頭から `GetProcAddress` (case-sensitive)。最初の非 NULL を採用 | `evidence/fw_main_name_table.txt`: `VstPluginMain, VSTPluginMain, main, maiN, maIn, … MAIN(16 通り), vstpluginmain, VSTPluginMain, VSTPluginmain, VSTpluginmain, VSTpluginMain, vstPluginMain, vstPluginmain, vstpluginMain` |
| 3 | FPU/MXCSR 保存 (`fw:0x5bf650`/`0x5bf680`) → **`eff = main(audioMaster = fw:0x7a87c0)`** → 復帰 | `(*local_30)(FUN_007a87c0)` |
| 4 | `eff->magic == 'VstP'` 検査 (4 バイトを `FUN_00784de0` で組立てて比較)。不一致なら `eff=0` | |
| 5 | `eff->resvd1 (+0x40) = this` (host 所有欄)。shell 用に `uniqueID (+0x70)` を this+0x9bc から上書き/退避 | |
| 6 | `dispatcher(+8)(eff, effOpen=0, 0,0,0,0)` → vtbl[+0x130/+0x138] (host 側 SetSampleRate/BlockSize 相当) → `effMainsChanged` 系 (vtbl +0x2a0) | |
| 7 | 問合せ: `effGetEffectName(45)` `effGetVendorString(47)` `effGetPlugCategory(35)` (==10 → shell) `effGetVstVersion(58)` `effSetEditKnobMode(61, value=2)`、`flags&1` (HasEditor) なら editor panel 生成、`flags&0x20` (ProgramChunks)、非 shell かつ vstVersion<2 なら `effGetParamName(8)` で名前列挙 | |

**host 側 audioMaster (`fw:0x7a87c0`, `evidence/fw_audiomaster.c`)**: `audioMasterVersion(1)=0x960 (2400)`, `CurrentId(2)`=shell の選択 ID, `GetVendorString(0x20)="Image-Line"`,
`GetProductString(0x21)="Fruity Wrapper"`, `GetVendorVersion(0x22)=0x271a`, `UpdateDisplay(0x2a)`, `CanDo(0x25)` は {sendVstEvents, sendVstMidiEvent, supportShell, sendVstTimeInfo, supplyIdle,
acceptIOChanges, receiveVstMidiEvent, shellCategory, sizeWindow}→1、{receiveVstEvents, receiveVstTimeInfo, reportConnectionChanges, asyncProcessing, offline}→-1。他は汎用ハンドラ `fw:0x7abca0`。

**ホストが発行する dispatcher opcode** (`fw` VSTPlug unit 188 関数を decompile して `+8` 呼出を集計 → `evidence/fw_dispatcher_opcodes.txt`):
0 Open / 1 Close / 2-5 Program / 6-8 ParamLabel/Display/Name / 10 SetSampleRate / 11 SetBlockSize / 12 MainsChanged / 13-15 EditGetRect/Open/Close / 19 EditIdle /
23-24 Get/SetChunk / 25 ProcessEvents / 29 ProgramNameIndexed / 33-34 In/OutProperties / 35 PlugCategory / 45,47 EffectName,VendorString / 50 VendorSpecific / 51 CanDo / 53 Idle /
58 VstVersion / 61 EditKnobMode / 67-68 Begin/EndSetProgram / 70 ShellGetNextPlugin / 0x10000 (FL 独自)。この集合が **marshal 規則表の最小要件** (§2.5)。

**音声/パラメータ経路** (`evidence/fw_process_params.c`):
`fw:0x7ad040` — `FUN_007b2280` (MIDI 蓄積) → 蓄積があれば先に `dispatcher(effProcessEvents=25, ptr=VstEvents*)` → `flags&canReplacing ? eff->processReplacing(+0x78) : eff->process(+0x10)` (in/out は `float**`)。
`fw:0x7afab0` setParameter = `eff->setParameter(+0x18)(eff, idx, value)` を FPU 保存で挟む / `fw:0x7ac960` getParameter = `(+0x20)`。

### 1.4 AEffect レイアウト (Win64) の独立証拠

OTT_vst2_win64.dll の `AudioEffect::AudioEffect` (`ott:0x180126920`, `evidence/ott_audioeffect_ctor.asm`) は `cEffect = this+0x30` に次を書く:
`+0x00 magic=0x56737450 ('VstP')`, `+0x08 dispatcher=0x180126c00`, `+0x10 process`, `+0x18 setParameter`, `+0x20 getParameter`, `+0x28 numPrograms=R8D`, `+0x2c numParams=R9D`,
`+0x30 numInputs=1`, `+0x34 numOutputs=2`, `+0x38 flags|=0x10`, `+0x5c ioRatio=1.0f`, `+0x60 object=this`, `+0x70 uniqueID='NoEf'`, `+0x74 version=1`, `+0x78 processReplacing`, `+0x80 processDoubleReplacing`。
これは Wrapper 側アクセス (`+8`,`+0x18`,`+0x20`,`+0x38`,`+0x40`,`+0x70`,`+0x78`) と全て整合 → `poc/vst2_abi.h` の `HbAEffect` (0xC0 B, `_Static_assert` 付き)。

OTT の実フロー (`ott:0x180128ba0` VSTPluginMain → `0x180125b40` createEffectInstance): ① `audioMaster(NULL, audioMasterVersion=1,…)` が 0 なら NULL を返す ② `operator new(0x328)` → `OTTProcessor` ctor (`0x18011d400`:
`AudioEffectX(audioMaster, numPrograms=1, numParams=0x14)`) → vftable=OTTVST, `uniqueID='XfTT'` ③ `OTTEditor` を `new(0x248)` ④ `0x180120800(obj)` ⑤ `vtbl[+0xf0]` (getAeffect) を返す。
dispatcher `0x180126c00` は `dispatchEffectClass`: `obj=eff->object; return obj->vtbl[1](opcode,index,value,ptr,opt)` (= AudioEffectX::dispatcher の巨大 switch)。

### 1.5 Win64 ABI 上の引数の乗り方 (lift 済みコードと共通の契約)

`dispatcher(AEffect*, i32 op, i32 index, intptr value, void* ptr, float opt)`: 第 1-4 引数は rcx,rdx,r8,r9、**第 5,6 引数 (ptr,opt) はスタック** (`ott:0x180128bb8` で `[rsp+0x20]=0`, `[rsp+0x28]=opt`)。
`setParameter(AEffect*, i32, float)` の float は xmm2 (位置基準)。lift 側 (M7〜M10) は xmm 引数を **同位置の i64 スロットに f32 ビットで載せる** 規約 (`f32b()`) → 本設計も全関数ポインタ呼出を `(u64 fn, u64 a0..a5)`、float は下位 32bit とする (§2.3)。

### 1.6 bridged 経路 (`fw:0x770a80`/`0x7729c0`/`0x76f3f0`, `evidence/fw_bridge_kind.c`)

- プラグインごとに `this+0x761` = bridge 種別: **2 = 32bit, 3 = 64bit**, それ以外 = bridge 無し。ctor `fw:0x76f550` が `FUN_0076f3f0(format, info)` で決定: フォーマット id が bitmask `DAT_0076f4d8` に該当 → 2、
  ファイル形式なら `FUN_005bfe50(path)` → `fw:0x5bfc30` が **PE ヘッダ (`MZ` 0x5a4d, machine 0x14c など) を読み 6/7 (=x64/x86)** を返す。
- クラスが `TBridgedPlugin` のとき (UI 表示 "bridged"/"native", 設定 "Make bridged") のみ `32bit\ilbridge.exe` / `64bit\ilbridge.exe` を
  `<cmd> -wrapper <wrapper dll> -address <id> -processid <FL pid> -dpiaware` で `CreateProcessW` (`fw:0x74c8e0`)、`CreateFileMappingW/MapViewOfFile` (`fw:0x74ca60`) + 名前付きイベント
  (`%s_memory`, `%s_e_a/_e_s/_e_r/_e_w`) で IPC。ブリッジ側は同じ TVSTPlugin コードで §1.3 を実行する。切断時 UI: "The connection to this plugin was lost" / "Bridge process destruction timed out"。
- **wasm 移植方針**: bridge 経路は無効化 (`this+0x761`=0 / "Make bridged"=false に固定、`CreateProcessW` は shim で fail-fast)。プロセス分離の目的 (クラッシュ隔離・32/64 混在) は §2.4 の instance 分離が満たす。

### 1.7 プラグイン走査 / DB (Plugin Manager)

- FL 起動時の DB 読込は `fle:0x9db5b0` (`Presets\Plugin database\`, `Data\Patches\Plugin database`, `Installed\{Generators|Effects}\<形式>\*.fst/*.nfo`, `VerifiedIDs.nfo`)、
  UI 側は `fle:0xec53b0` ("Scanning plugin database (generators/effects)…")。**走査自体は外部プロセス** `System\Tools\Plugin Manager\PluginManager.exe -flpath -flcaption -deepscan -vstpath <dir>`。
- VST2 探索パス (PluginManager 文字列): レジストリ `Software\VST\VSTPluginsPath`、`Steinberg\VST2`、`Steinberg\VstPlugins`、`VstPlugins`、`Plugins\VST\`、`HKLM\…\App Paths\Cubase.exe` の `plugins`、ユーザ追加 `Software\Image-Line\Shared\Plugin search paths`
  (`List/path/plugclass/selected/custom`)、VST3 は `VST - User\`/`VST - User factory\`/`VST - Shared\`、CLAP 対応 (`CLAP\`)、mac は `AudioUnit\`。
- `.nfo` のキー集合 (文字列): `ps_name, ps_vendorname, ps_file_filename, ps_file_magic, ps_file_guid, ps_file_date, ps_file_size, ps_file_plugclass, ps_file_type, ps_file_bitsize, ps_file_arch,
  ps_file_scanflags, ps_file_vendorname, ps_file_category, ps_file_idstring, ps_compatibility, ps_files, ps_presetfilename, ps_dummy64bit, fileversion, iconindex, color` (**書式は未確認** — インストーラに実 .nfo 無し。要: 実機生成物 or FLEngine reader の解読)。
- deep scan = 各 DLL を §1.3 と同手順で実ロードし `effGetEffectName/VendorString/PlugCategory`、`uniqueID` (`ps_file_magic`)、`flags` (synth 判定) を取る。

### 1.8 VST3 / AU / CLAP (概要)

| 形式 | 経路 | 境界の性質 |
|---|---|---|
| VST3 | Wrapper → `QuickFontCache_x64.dll!CreateVST3Instance` (C++ ホスト)。`.vst3` を LoadLibrary し `InitDll`→`GetPluginFactory`→IPluginFactory→IComponent/IAudioProcessor/IEditController 等の COM 風 vtable | 境界が **多数の C++ インタフェース**。opcode 表では marshal 不能 (§2.9) |
| AU (mac) | `auwrapper_x64.dylib` (formats.txt 経由) が AudioComponent を `dlopen` | Mac のみ。win 版 FL の同梱対象外 |
| CLAP | Wrapper 内 `CLAP (fx/gen)`; `clap_entry` 経由 (標準 C API, struct of fn ptr) | C ABI で VST2 に近い (拡張を使うため規則表は別) |

---

## 2. wasm 置換設計

### 2.1 要件 (解析から)

- R1: 第 1 段 (FL→Wrapper) と第 2 段 (Wrapper→プラグイン) で **同じ LoadLibrary/GetProcAddress/FreeLibrary** が使われる (`SafeLoadLibrary` 一種に正規化されている: `fw:0x449770`)。
- R2: `GetProcAddress` は **大文字小文字を区別して 26 回まで再試行**する → export 表は PE 同様 case-sensitive に引く (§3 T2b)。
- R3: ホストは AEffect を直接読み書きする (`flags`, `numParams`, `uniqueID`, `resvd1`) → ポインタ共有できない場合は構造体を **鏡像化**。
- R4: プラグインはホスト関数 (audioMaster) を `main()` の最中から呼ぶ (`VSTPluginMain` 冒頭で `audioMasterVersion`) → upcall が entry より前に動く。
- R6: ロード前に **DLL ファイルの PE を 2 回読む** (export 名検査 `fw:0x5c0200`、bitness 判定 `fw:0x5bfc30`)。ブラウザには実ファイルが無いので、
  仮想 FS 上の各 plugin パスに **最小 PE スタブ** (DOS+PE ヘッダ, `machine=0x8664`, export directory = manifest の `exports`) を置く必要がある (§2.2)。hint = DB に保持される entry export 名 (Kilohearts `VSTPluginMain_<id>` 等の多製品 core 用機構が元々ある)。
- R5: Fresh Air / Kilohearts は **shell DLL → 巨大 core DLL の入れ子 LoadLibrary** (`tools/targets/*/REPORT.md`)、Serum 2 は **VST3 のみ**。表は入れ子/共有 core/VST3 を前提にする。

### 2.2 事前登録モジュール表 + shim

```
registry.json                      modules[]  = 実体 (wasm バイナリ + instance 管理)   plugins[] = LoadLibrary される名前 → module+export への別名
 module : { id:"xfer.ott.vst2", wasm:"plugins/xfer.ott.vst2.wasm", abi:"hb-vst2-1", memory:{initial,max}, refcount }
 plugin : { path/alias:["OTT_x64.dll"], module:"…", exports:{ "VSTPluginMain":"VSTPluginMain", "main":"VSTPluginMain" }, name,vendor,uniqueId,format,arch,ui }
```
- 解決: パスを `\`→`/`・basename・小文字化して alias 表を引く → 失敗は NULL + `ERROR_MOD_NOT_FOUND(126)`。`ps_file_magic/guid` (DB 側) でも引ける (パスが仮想化されるため)。
- `LoadLibraryW` → module の refcount++ (初回のみ instance 生成 + `DllMain(PROCESS_ATTACH)` 相当の `hb_plugin_init`)。HMODULE は合成値 (`0x7ff6a0010000+n*0x10000`、n は LoadLibraryW ごとの単調増加。解放後も再利用しない (#2520))。
  `FreeLibrary` → refcount-- → 0 で instance 破棄 (= ネイティブ DLL の statics 寿命と一致)。`GetModuleHandle/GetModuleFileName` は仮想パスを返す。
- `GetProcAddress(h,name)` → **合成関数ポインタ (thunk slot VA, `0x7ff700000000+16*n`)**。FL/Wrapper (lift 済 x64) の間接呼出はこの VA を `icall(fn,a0..a5)` に落とす 1 点 (lift 側は `VA<THUNK_BASE` なら自モジュール関数表、以上なら bridge)。
- **仮想 FS の PE スタブ (R6)**: `ModuleTable` は plugin ごとに最小 PE (約 1 KB: MZ→PE→optional header→`.edata`) を生成して仮想 FS の plugin パスに置く。`export` 名検査・bitness 判定・`GetFileSize/ps_file_size/date` は stub に対して正しく動く。
  `LoadLibrary` は stub 内容ではなく表を引く (stub は **検査専用**)。生成器 `poc/pe_stub.mjs` (1 KB) を実装し pefile で S1-S3 検証済 (`analysis/check_pe_stub.py`)。PoC の host は事前検査呼出を省略、仮想 FS への結合は H4。
- **shell/core 分離 (R5)**: stub DLL (Kilohearts 47 本, Fresh Air shell) は lift せず **alias のみ登録**し core module の `VSTPluginMain_<id>` に直結 (stub elision)。core は 1 module = 1 instance を全製品で共有 (ネイティブの "1 プロセス 1 DLL" と同じ)。
- **instance の同期生成**: `LoadLibrary` は同期 API。ブラウザでは module を事前 `WebAssembly.compile` (async) 済みにし、`new WebAssembly.Instance(compiled, imports)` を同期実行する
  (メインスレッドでの大型 module 同期 compile は禁止されるが compile 済み instance 化は可)。PoC は emscripten glue が async のため prewarm 済み pool で代替 (`ott_module.mjs`)。

### 2.3 guest ABI "hb-vst2-1" (全プラグイン module 共通)

| export / import | 内容 |
|---|---|
| `hb_plugin_init()` | DllMain 相当 (データ敷設 `m6_data_install`, arena 初期化) |
| `hb_scratch()` | ≥1 MiB の bridge 専用 scratch (marshal バッファ。lift 側 heap と非衝突の領域) |
| `VSTPluginMain(u64 audioMaster) → u64 AEffect*` | PE export と同名・同意味 |
| `hb_icall(u64 fn, u64 a0..a5) → u64` | plugin が AEffect 等に公開した **全関数ポインタ**の呼出口。lift 済み DLL では lifted 間接呼出リゾルバ、surrogate では switch |
| import `hb_host_call(eff, op, idx, vlo, vhi, ptr, f32 opt) → i32` | plugin→host の audioMaster 呼出 (bridge が host 側 callback と marshal) |

規約: ポインタ = guest linear memory アドレス (zero-extend)、構造体は **Win64 配置**、float は下位 32bit にビット、戻り値は u64 (getParameter は下位 32bit に f32)。

### 2.4 メモリ空間: 共有 vs 分離 (決定: 分離 + marshalling)

| 観点 | A: 全 module を 1 linear memory に同居 | **B: instance・memory 分離 + marshal (採用)** | C: 別 instance + SharedArrayBuffer 共有 memory |
|---|---|---|---|
| アドレス衝突 | lift 済みコードは **絶対 VA を immediate に焼く** (OTT は image=`0x30000000+RVA`, 大域=`0x10000000+`, M6 `ir6_shift`)。module ごとに別 base で再 lift が必須、FL 本体の VA 帯とも調停 | **無し** (各 instance が自前の空間) | A と同じ (全員が同一 base 規約を共有) |
| シンボル衝突 | 関数名が `function_<VA>` → 2 DLL の同 RVA 関数が **link 時に衝突** (prefix 化 pass が要る) | 無し | 同左 |
| クラッシュ隔離 | trap で FL ごと死ぬ | **trap は instance 単位 → bridge が捕捉し "connection lost" 扱い** (ilbridge の UI と同挙動) | 同左 B と同等 |
| 実装コスト | lift パイプライン全体改造 | **marshal 規則表のみ (VST2 は境界が狭い)** | 両側を shared-memory build に |
| 実行コスト | 0 | 実測: **固定 0.44〜1.6 µs/call (CPU 共有で変動)、128f 処理は予算比 ±10% 内** (§3) | 小 |
| ブラウザ制約 | 1 memory 4 GiB 上限を全 plugin で共有 | **instance ごとに予約**: OTT は現状 `initial=max=864 MiB` (VA base が 0x30000000 のため) → **image を低位 base へ再配置しないと多数同時ロード不可** (§2.8-P0) | SAB は COOP/COEP 必須 (M12 前提とは整合) |
| スレッド | 単一 | worker 単位に plugin を置ける (RPC 化可) | 可 |

決定: **B**。PoC の ownership 規則は §2.5。C は「重い plugin の音声 buffer だけ SAB 化する最適化」として将来の差し替え点に留める (`GuestEndpoint.call` の transport 抽象)。
**A を採る例外**: 同一 core を共有する製品群 (Kilohearts) は core の内部で当然同居。FL 内蔵 Fruity プラグインの扱いは M11 側判断 (本チケット対象外)。

### 2.5 AEffect 鏡像化 と dispatcher marshal

- **proxy AEffect**: `VSTPluginMain` が返した guest の AEffect 0xC0 B を host memory に複製し、関数ポインタ 6 欄 (`dispatcher/process/setParameter/getParameter/processReplacing/processDoubleReplacing`) だけ **thunk slot VA に置換**。
- **所有権**: host 所有欄 `resvd1(0x40)/resvd2(0x48)/user(0x68)/uniqueID(0x70, shell 上書き)` は呼出前に host→guest へ、plugin 所有欄 `numPrograms..flags(0x28-0x3f)/initialDelay..ioRatio(0x50-0x67)/object/uniqueID/version` は呼出後に guest→host へ同期 (呼出毎 ≲100 B)。
- **dispatcher 規則表** (`DISPATCH_RULES`, Wrapper が実際に出す opcode 基準): `instr`(4,27,51) / `outstr`(5-8,29,45-48; FL の buffer は 0x201 B) / `struct_out`(33,34,56) / `rectpp`(13: `ERect**`) / `chunk_out`(23: `void**`+戻り値=size) / `chunk_in`(24: value=size) /
  `events_in`(25: `VstEvents` を要素ごと deep copy) / `speaker_in`(42: value と ptr の両方) / `handle`(14: 不透明 HWND)。**規則の無い opcode の ptr は guest に渡さず `unmarshalled` に計上** (別 memory ゆえ無効ポインタを流さない)。
- **audioMaster 規則** (`AM_RULES`): `ret_struct`(7 GetTime → `VstTimeInfo` 0x58 B を guest scratch に複製して guest ptr を返す) / `events_in`(8) / `outstr`(32,33) / `instr`(37)。`eff==NULL` の upcall (entry 内の version check) は entry context の callback を使う。
- **process**: `float**` を channel 毎に guest scratch へ複製 (入力) → `processReplacing` → 出力を host へ書戻し。128f ステレオで 2 KiB 往復。
- 実装 `poc/hb_bridge.mjs`、単体試験 `poc/test_marshal.mjs` (JS 製 FakeGuest + 実 host wasm で各 kind を網羅, 13/13)。

### 2.6 GUI (エディタウィンドウ)

Wrapper は `flags&effFlagsHasEditor` のとき `TVSTPanel` を作り `effEditGetRect(13)` → `effEditOpen(14, ptr=HWND)` → `effEditIdle(19)` (FL タイマ) → `effEditClose(15)`。plugin→host の `audioMasterSizeWindow(15)` でリサイズ。段階案:
- **G0 (PoC で実装済)**: surrogate が `HasEditor` を立てない → Wrapper は自前の **generic editor** (`TGenericPluginEditor`) を出す。パラメータ名/表示は `effGetParamName/Display` 往復で成立 (T2j/T3b)。
- **G1**: manifest 宣言の web UI (HTML/Canvas) — 画像資産は PE `.rsrc` から抽出 (OTT: PNG ~377 KB)。`effEditGetRect` は manifest の矩形、`effEditOpen` の HWND は M7 の仮想 window 識別子。操作は `setParameter/getParameter` に直結。
- **G2**: プラグイン本来の GUI (JUCE/VSTGUI/Skia) を lift し、HWND を M7 の描画 surface に結合 (GDI/D2D shim が前提。Serum 2=VSTGUI4+Direct2D, Kilohearts/Fresh Air=Skia CPU raster)。コストが桁違いなので G1 で足りない場合のみ。

### 2.7 スレッド / 実時間

- 想定: FL エンジン (lift 済み) が M8 の worker で音声を生成し SAB ring で AudioWorklet に渡す → **plugin instance は FL エンジンと同一スレッド**に置く (全呼出が同期のまま)。
- 重い plugin (Serum 2 級) は instance を別 worker に置き、bridge の `GuestEndpoint.call` を `Atomics.wait` RPC + SAB 音声 buffer に差し替える (規則表・AEffect 鏡像はそのまま)。

### 2.8 前提条件 (PoC で露呈した P0/P1 項目)

- **P0 低位 base 再配置**: M6〜M10 の lift は PE image を `0x30000000+RVA`、linear memory を 864 MiB (0x36000000) 固定で作る → instance 毎 864 MiB 予約。複数 plugin 同時ロードには image を数十 MiB 級の低位 base へ (`ir6_shift` の SHIFT を可変化)。
- **P0 closure の VSTPluginMain までの拡張**: 現 closure (166 関数) に `VSTPluginMain`(`ott:0x180128ba0`)/`createEffectInstance`/`dispatchEffectClass`(`0x180126c00`)/static thunk (`0x180127430,520,1a0`) が無い。本 PoC の `plugin_ott_entry.c` は
  その surrogate (差し替え点は `hb_icall` のみ)。
- **P1 引数復元**: lift 済み `AudioEffect::AudioEffect` は **r8d/r9d (numPrograms=1, numParams=0x14) を落とし AEffect の両欄が 0** になる (M7 の f32 引数落ちと同系の整数版)。PoC は native 値で補正 (`evidence/ott_ottprocessor_ctor.asm`)。
- **P1 audioMaster の lift 表現**: lift 済み ctor は audioMaster=0 で通している (M10 と同じ)。実 callback VA を渡した時の lift 済み間接呼出の落とし先を決める必要。
- **P1 getParameter の戻り値 (xmm0)** の lifted 表現 (i64 か別チャネルか) 未確認。PoC は surrogate の shadow 値。

### 2.9 VST3 / CLAP / AU 拡張

- **VST3 (Serum 2 は VST3 のみ)**: 境界は COM 風 C++ vtable (`IPluginFactory`/`IComponent`/`IAudioProcessor`/`IEditController`/`IPlugView`/`IHostApplication`/`IComponentHandler`/…)。opcode 表の方式は流用不可。方針: ①インタフェース IDL (公開ヘッダ由来) から proxy/stub を機械生成して instance 分離を維持
  ②または VST3 に限り「plugin module 内に最小 VST3 host を同梱」して FL からは VST2 風 facade (`effProcessEvents/processReplacing/Get/SetChunk`) だけ見せる (host 側 `QuickFontCache!CreateVST3Instance` 相当を module 内に置く) — ②のほうが境界が狭く現実的 (`tools/targets/serum2/REPORT.md` が「shim 側で最小 VST3 host を新規実装」と整合)。
- **CLAP**: C API (`clap_entry`, `clap_plugin_t`)。VST2 同様に fn-ptr 構造体だが拡張が可変 → 規則表を拡張 ID 単位で持つ。FL26 の CLAP 対応は Wrapper 側文字列で確認。
- **AU**: mac 専用 (`auwrapper`)。ブラウザ版 FL の同梱対象は Windows 系 (VST2/VST3/CLAP) に限定するのが妥当。

### 2.10 対象別メモ (他担当の REPORT を読取参照)

| 製品 | 形式 | 構造 | 表への載せ方 |
|---|---|---|---|
| OTT | VST2/VST3/AAX (win), 本 PoC=VST2 x64 | 単一 DLL, JUCE+VSTGUI, DSP~20 KB | 1 module=1 plugin。GUI=G0→G1 |
| Kilohearts | VST2/VST3/AAX (win) + AU | 47 stub (247 KB) → `HeartCore.core_64` (76.6 MB) を LoadLibrary、export `VSTPluginMain_<id>`, `KiloheartsSnapinMain` | core 1 module 共有 + stub 47 alias (stub elision)。巨大 wasm→起動コスト要計測 |
| Fresh Air | VST2/VST3 (同一 DLL), AAX | 250 KB shell → `SlateCore.core_64` (36 MB) | 同上 (入れ子 LoadLibrary) |
| Serum 2 | **VST3 のみ** | `Serum2.vst3` 19 MB, VSTGUI4+Direct2D | §2.9 VST3 方式が前提。VST2 PoC では不可 |

### 2.11 Plugin DB / 走査の置換

PluginManager.exe は外部プロセスなので移植せず、`ModuleTable.virtualPaths()` (仮想 `C:\Program Files\Common Files\VST2\<Vendor>\<Name>_x64.dll`) を列挙 → §1.3 の手順で deep scan →
`Presets/Plugin database/Installed/{Effects|Generators}/VST/<name>.nfo/.fst` を仮想 FS に生成 (ビルド時 or 初回起動時)。`ps_file_bitsize=64`/`ps_file_arch=x64` で Wrapper の bridge 判定 (§1.6) を native に固定。`.nfo` 書式は §1.7 の通り未確認。

---

## 3. PoC (tools/hostbridge/poc) — 構成と実測

構成: `host_vst2.c` (freestanding wasm32 3.7 KB, FL 側代役) ⇄ `hb_bridge.mjs` (表+shim+marshal) ⇄ `ott_hb.cjs/.wasm` (M10 lift 済み IR 848 KB + `plugin_ott_entry.c`)。
host は Wrapper の手順 (§1.3) を再現: `LoadLibraryW` → 26 名前表 → `main(audioMaster)` → magic → `resvd1` → `effOpen`/`SetSampleRate`/`SetBlockSize`/`MainsChanged` → 問合せ → `processReplacing`。

実測 (`work/poc_result.json`, ノード v26.10 / 本 VM, CPU は他 agent と共有):
- 検収は**全項目 PASS** (内訳と件数は `tools/hostbridge/REPORT.md` §0・§1 が正本)、全体 4〜10 s (build 込み)。
- **T4a**: bridge 経由 `processReplacing(256f×2ch)` = 直接 baseline と **全 bit 一致**。**T5c**: A/B 2 本交互 2×128f も直接 2×128 と一致 (diff 0/0)。**T5b**: 2 本目 instance 出力 = 1 本目 (instance 間漏れ無し)。(実測値の正本: `tools/hostbridge/REPORT.md`)
- **T4c**: `obj+0x248=0` (M10 e2e 条件) で M10 正規手順の出力と **全 bit 一致**、census は `tools/ott/REPORT.md` §2.3 の旧 chain 行と同値 (M10 と同値・数値は同 REPORT が正本)。→ **M10 到達水準 (bit-exact 未達・junk あり) をそのまま bridge 越しに再現**。参照は lift 済み wasm 同士で native 機械語実行との比較ではない (junk 同士の一致 = bridge 透過性のみ証明、DSP 正当性は未証明)。tools/ott (f4e0514) の native 参照では正解出力は junk 0/512、RetDec lift の間接 call 脱落が主因。
- 発見: **自然フロー (VSTPluginMain→…) では `obj+0x248` は 1** (ctor が立てる; M10 の `probe_flag` でも ctor 後=1)。この経路の census は zero 4 / normal 254 / junkHi 252 / junkTiny 2 (M10 REPORT §3.3 の `[0x248]=1` と同値)。M10 は手動で 0 に強制している → 実プラグインとして動かすと junk の多い側が既定。DSP 検証チケットの前提情報。
- 性能: 128f 処理 bridge 経由 395–884 µs vs guest 直 416–887 µs (差 −21〜−4 µs = 測定誤差内, 予算 2902 µs の ±1% 未満)。固定オーバーヘッド (getParameter 往復) は静穏時 **0.39–0.44 µs/call** (絶対値)、CPU 共有下の再実測で 0.77–1.62 µs。128f の bridge−直接差も再実測では予算比 −10.4%〜+3.2% とばらつく。DSP 自体は `-O0 -g1` 版で 13〜30% / 128f 予算。
- メモリ: 3 instance prewarm で node RSS 62 MB (864 MiB ずつ仮想予約のみ; 実 commit は遅延), 全試験後 110 MB。prewarm 48 ms。

## 4. 未解決・制約

1. surrogate は SDK glue の再現 (§2.8 P0)。dispatcher 本体 (`AudioEffectX::dispatcher`) は未 lift → effGetChunk/SetChunk/Program/MIDI 等は未実装 (OTT は chunk=nlohmann::json)。
2. `.nfo/.fst` の書式未確認 (§1.7)。
3. getParameter は shadow 値 (§2.8)。numParams=20 の #19 の名前は未回収 (AU 表は 19 件)。
4. Fruity Wrapper 2 ビルドの差分の意味 (Effects/Generators 版) は推定。
5. 実ブラウザ (AudioWorklet/Chrome) 上の同期 instance 生成は未検証 (node で代替)。

## 5. 下流チケット案

| # | チケット | 内容 | 優先 |
|---|---|---|---|
| H1 | lift base 可変化 | `ir6_shift`/globals/memory を plugin 毎に低位 base+小 memory へ (目標 ≤64 MiB/instance)、`function_<VA>` に module prefix | P0 |
| H2 | OTT closure を VSTPluginMain まで拡張 | `0x180128ba0/0x180125b40/0x180126c00/0x180127430..` + `AudioEffectX::dispatcher` を lift、surrogate 撤去、audioMaster 実 callback | P0 |
| H3 | 整数引数復元 pass | AudioEffect ctor の r8d/r9d 落ち等 (M7 f32 版の整数版)、getParameter xmm0 戻り | P1 |
| H4 | Fruity Wrapper の lift + shim 結合 | `SafeLoadLibrary`/`GetProcAddress`/`SetErrorMode`/`FreeLibrary`/`timeGetTime` 等を shim 表へ、`bridged` 無効化、`CreateProcessW` fail-fast、PluginManager 代替 (§2.11) | P0 |
| H5 | VST3 方式 spike | Serum 2 用: 最小 VST3 host 同梱方式 (§2.9②) の PoC (IComponent/IAudioProcessor のみで silence→process) | P1 |
| H6 | web UI G1 | OTT の `.rsrc` PNG 抽出 + 宣言的ノブ UI + `effEdit*` 結線 | P2 |
| H7 | shell/core 入れ子 | Kilohearts/Fresh Air の stub elision + 共有 core の module/alias 表、巨大 wasm の遅延ロード計測 | P1 |
| H8 | ブラウザ実機 | 同期 `WebAssembly.Instance` 生成、AudioWorklet/worker 配置、COOP/COEP 下の SAB RPC (§2.7) | P2 |
| H9 | `.nfo/.fst` 書式解読 | FLEngine reader (`fle:0x9db5b0` 周辺) の decompile から書式確定 → 生成器 | P1 |
