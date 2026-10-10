# FruityPlug ABI (FL Studio 26.1.7 同梱 Fruity プラグイン) — 実バイナリ逆アセンブル根拠付き

結論先出し:

1. **プラグインの入口は `CreatePlugInstance(Host, Tag)`** (win64/mac 共通の export 名)。`CreateFruityInstance` は **FLEngine_x64.dll 自身の export** (FL64.exe ランチャが呼ぶアプリ起動点, §1.2) でプラグイン ABI ではない。→ 依頼文の「CreateFruityInstance を参照する x64 258 個」は「x64 PE 258 個のうち CreatePlugInstance を export するもの 160 個 (プラグイン tree 内 159 + `Shared/SG_x64.dll` 1)」と読み替える。
2. インタフェースは公開 FL SDK の `TFruityPlug` (仮想 20 スロット) / `TFruityPlugHost` と**同一の C++ 互換 vtable**。実測で 20 スロット (Image-Line 版 Delphi は TObject 仮想を vptr の**負側**に置く, §3)。
3. ホスト側 (FLEngine) の `TFruityHost` は **46 仮想スロット**を実装 (公開 SDK より多い)。`slot0 = Dispatcher(HostTag, ID, Index, Value)` がほぼ全ての窓口。
4. 呼び出し規約は win64 では Microsoft x64 (stdcall = 同一), 全 `int`/`ptr` 引数は 64bit レジスタ幅で渡る。float 引数は xmm / スタック (§4)。
5. 実バイナリ根拠は全て `inventory/pedis.py` / `delphi_vmt.py` / `win_abi.py` で再現可能 (§8)。 全 133 Delphi プラグイン DLL で vtable 構造を機械確認: 132/133 で `TTestPlug` 系 26 スロット (=基底 20 + Delphi 側 6), 124/133 で `TFruityPlugInfo` を抽出。

---

## 1. エントリポイント

### 1.1 `CreatePlugInstance` (全プラグイン, win64 + mac 共通名)

win64 `Fruity Balance_x64.dll` (block18983, ImageBase 0x400000, export RVA 0x2bdde0):

```
6bdde0: push rsi / push rbx / sub rsp,0x28
6bdde6: mov rbx,rcx          ; rcx = Host (TFruityPlugHost*)
6bdde9: mov rsi,rdx          ; rdx = Tag  (host が付ける識別 = THostTag, 64bit 幅で受領)
6bddf2: xor r8,r8 ; lea r9,[rip+..] ; call 6b8a60   ; (host version check ヘルパ: r8>0 の時のみ Dispatcher(ID=0x1a) を発行; ここでは r8=0 で no-op → al=1)
6bde01: test al,al ; jne → else return NULL
6bde0f: call 6bd210          ; (rcx=Host, rdx=Tag) 初期化: Host->Dispatcher(Tag, ID=0x47, 0, 0) を呼びグローバル設定を保存
6bde14: mov rcx,[rip-0x223]  ; クラス参照 (= vtable 先頭, §3)
6bde1b: mov dl,1 ; mov r8,rsi (Tag) ; mov r9,rbx (Host)
6bde23: call 6be800          ; TTestPlug.Create(Tag, Host) — Delphi コンストラクタ: (rcx=class, dl=alloc flag, r8=Tag, r9=Host)
6bde28: add rsp,0x28 ; pop ; ret   → rax = TFruityPlug* (戻り値 = 生成オブジェクト; 版チェック失敗時は NULL)
```

mac x86_64 (FPC 3.2.3, SysV) `Fruity Balance_x64.dylib` `_CreatePlugInstance`@0x4bf0 → jmp 0x52130: `rdi=Host, rsi=Tag` → check(0x6dd40) → init(0x16ff40) → ctor(`rdi=class VMT, esi=1, rdx=Tag, rcx=Host`) と**同一構造** (`inventory/macdis.py`)。mac 側は他に `_SetExternalAppHandle` を export。

export の実測 (全 141 プラグインフォルダ): win 側 `CreatePlugInstance` export を持つ PE は 160 個 (うち 18 プラグインは Delphi 殻 + C++ engine の 2 個が両方 export)、mac も 141/141 フォルダで ≥1 (export trie 経由; symtab は strip 済みで 7 個欠落するため trie 必須)。

### 1.2 `CreateFruityInstance` (FLEngine_x64.dll の export, プラグイン ABI ではない)

FLEngine_x64.dll (block00031) の export は `CreateFruityInstance` (0x1375990) / `__dbk_fcall_wrapper` / `dbkFCallWrapperAddr` の 3 個のみ。`CreateFruityInstance(rcx,rdx,r8,r9)`: 巨大フレーム (0x5f8) で `[r8+8]`,`[r8+0xc]` を読み Application 初期化へ進む = FL64.exe → エンジン起動点。plugin 側から参照する文字列ではない (ASCII 文字列 "CreateFruityInstance" が出るのは FLEngine と FL64 系 3 PE のみ)。

---

## 2. オブジェクトレイアウト (win64, Fruity Balance で確認)

### 2.1 TFruityPlug インスタンス

| offset | サイズ | 内容 | 根拠 |
|---:|---:|---|---|
| +0x00 | 8 | vptr → vtable (§3) | NewInstance 後に設定; 仮想呼びは `mov rax,[rcx]; call [rax+8*slot]` |
| +0x08 | 8 | `HostTag` (CreatePlugInstance の Tag) | TDelphiFruityPlug ctor 6b8e80: `mov [rax+8],rcx(=Tag)` |
| +0x10 | 8 | `Info` → `TFruityPlugInfo` (static 構造体) | TTestPlug ctor 6be800: `lea rcx,[rip+..]; mov [rax+0x10],rcx` → 0x70e3cc |
| +0x18 | 8 | `EditorHandle` (HWND) | Dispatcher ID0 の戻り: `mov [rcx+0x18],rax` |
| +0xbc | 8 | `Host` (TFruityPlugHost*) — **packed 非整列** | 6b8f1a: `mov [rcx+0xbc],rax(=Host)`; 以降 `mov rax,[this+0xbc]; mov rax,[rax]; call [rax]` |
| +0xe0 | 4 | MaxPoly (ProcessEvent ID1 で保存) | 既定 ProcessEvent 6b97d0: `if EventID==1: [rcx+0xe0]=r8d` |
| +0xc4/+0xcc | 8 | 派生クラス用内部ポインタ (param 管理 / DSP コンテキスト) | Balance: `[this+0xc4]`=param 配列 (+0x760+idx*8), `[this+0xcc]`=host 共通コンテキスト |
| (派生) | | `TTestPlug` instance size = **0x1b8 (440)** | VMT−16 |

(全 TTestPlug 系の instance size は 312B〜約 500B, 最頻 488/392/312B。ZGE のみ別クラス。)

### 2.2 TFruityPlugInfo (packed, 実測: 0x70e3cc)

```
+0x00 i32  SDKVersion        = 1
+0x04 ptr  LongName  (PAnsiChar)  "Fruity Balance"
+0x0C ptr  ShortName (PAnsiChar)  "Balance"
+0x14 u32  Flags             = 0x10400000   (Balance)
+0x18 i32  NumParams         = 2
+0x1C i32  DefPoly           = 0
+0x20 i32  NumOutCtrls       = 0
+0x24 i32  NumOutVoices      = 0
+0x28 ...  Reserved[30]
```

`inventory/win_abi.py` で 124 プラグインから抽出 (work/win_abi.json): NumParams は 0〜4560 (中央値 13; Control Surface=2048, EQUO=842)。Flags 最頻: 0x10400000 (52), 0x10600011 (8), 0x04600070 (5)… (SDK 名への割当は未検証: bit 0=Generator, bit 4/5=NewTick/GetNoteInput 系と推定。)

### 2.3 TFruityHost (FLEngine 側, `TFruityPlugHost` 派生)

* 抽象基底 `TFruityPlugHost` (FLEngine VMT 0x7b6760, instance size 264) と実装 `TFruityHost` (VMT 0x1314108, instance size 296)。
* **vtable は 46 スロット** (基底は全て abstract stub 0x40c820, TFruityHost が全 46 を実装; `host_vtable.txt` 相当を §8 のコマンドで再生成可)。
* slot 0 = `Dispatcher`, 実装 0x13173a0 (巨大: ローカル 0x1838B, ID は `cmp/sub` 連鎖の二分木で分岐 — jump table ではない)。

---

## 3. vtable / クラスレイアウト (Image-Line 版 Delphi)

```
class ref slot (CreatePlugInstance が読む)  = VMT - 0x58   [例 0x6bdbf8]
 [slot] = &vtable[0] = VMT + 0x70                           [例 0x6bdcc0]
VMT ヘッダ (負 offset, Delphi x64 標準): -0x18 ClassName(shortstring), -0x10 InstanceSize, -0x08 Parent
TObject の仮想 14 個は vtable[-14..-1] (= VMT+0 .. VMT+0x68); NewInstance は [vptr-0x30]
  (40bce0: `call qword ptr [rax-0x30]`)
```

→ C++ の `TFruityPlug` と同じく **vptr が指す先の [0] から SDK 仮想メソッドが並ぶ**。これにより FL ホスト/他社 C++ プラグイン/Delphi プラグインが同一 vtable を共有できる。
mac (FPC 3.2.3) では標準 FPC VMT (`call [class+0x68]` = vNewInstance) なので同論理インタフェースだが vtable 内 offset は別 (§7)。

### 3.1 TFruityPlug vtable (20 スロット, 実測)

基底 `TFruityPlug` (win VMT 0x6439a8): slot0 = 既定 DestroyObject (0x643b60), slot1..19 = 全て abstract stub (0x409ec0)。
`TDelphiFruityPlug` (FP_DelphiPlug, 26 スロット) が slot 0,1,2,5 を既定実装し slot 20..25 を Delphi 専用に追加。
個別プラグインの `TTestPlug` (26 スロット, 129 本) が override (Fruity Balance の例):

| slot | offset | 名称 (SDK 順) | Balance 実装 | 引数 (win64 レジスタ) 実測 |
|--:|--:|---|---|---|
| 0 | 0x00 | DestroyObject | 0x6b92f0 | rcx=this |
| 1 | 0x08 | Dispatcher | 0x6bde30 | rcx=this, rdx=ID, r8=Index, r9=Value → rax=Result (§5.1) |
| 2 | 0x10 | Idle_Public | 0x6ba140 (`ret`) | rcx=this |
| 3 | 0x18 | SaveRestoreState | 0x6be740 | rcx=this, rdx=IStream*, r8d=Save (Balance: Save 時 `Stream->Write(this+0x198, 8, 0)` = `[rbx+0x20]`; Load 時 `[+0x18]` Read) |
| 4 | 0x20 | GetName | 0x6bee90 | rcx=this, edx=Section, r8d=Index, r9d=Value, [rsp+0x28]=PAnsiChar buf |
| 5 | 0x28 | ProcessEvent | 0x6b97d0 (既定) | rcx=this, edx=EventID, r8d=EventValue, r9d=Flags → eax (ID1: MaxPoly を this+0xe0) |
| 6 | 0x30 | ProcessParam | 0x6beaa0 | rcx=this, edx=Index, r8d=Value, r9d=RECFlags → eax=Value (§5.2) |
| 7 | 0x38 | **Eff_Render** | 0x6befc0 | rcx=this, rdx=SourceBuffer, r8=DestBuffer, r9d=Length (frames) |
| 8 | 0x40 | Gen_Render | abstract | (rcx=this, rdx=DestBuffer, r8=&Length) — Generator のみ override |
| 9 | 0x48 | TriggerVoice | abstract | |
| 10 | 0x50 | Voice_Release | abstract | |
| 11 | 0x58 | Voice_Kill | abstract | |
| 12 | 0x60 | Voice_ProcessEvent | abstract | |
| 13 | 0x68 | Voice_Render | abstract | |
| 14 | 0x70 | NewTick | abstract | |
| 15 | 0x78 | MIDITick | abstract | |
| 16 | 0x80 | MIDIIn | abstract | |
| 17 | 0x88 | MsgIn | abstract | |
| 18 | 0x90 | OutputVoice_ProcessEvent | abstract | |
| 19 | 0x98 | OutputVoice_Kill | abstract | |
| 20-25 | 0xA0-0xC8 | Delphi 専用 (HintText 生成 `[+0xb0]` 他) | 6ba150,6ba1e0,6b9ce0,6b9c30,6b9cc0,6be6e0 | |

スロット名は公開 SDK の順序 (FP_Def.h) に基づく。**実測で確認できた意味**: slot0/1/2/3/4/5/6/7 (上の引数規約で関数本体を逆アセンブル確認), その他は「override の有無」のみ実測 (名称は SDK 順で割当)。

override 実測 (132 DLL, `win_abi.py`):

| 組合せ | 本数 | 例 |
|---|--:|---|
| Eff_Render のみ (エフェクト) | 62 | Balance, Compressor… |
| Gen_Render+TriggerVoice+Voice_* (ジェネレータ) | 23 (+NewTick 13 / +MIDIIn 3) | 3x Osc… |
| Eff_Render+NewTick | 8 | |
| Voice_*+NewTick (render 無し: Sampler/Wrapper 系) | 8 | |
| Eff+Gen+Voice+NewTick+MIDIIn (Wrapper/Patcher) | 3 | Fruity Wrapper, Patcher |
| 何も render しない (コントローラ/ノート系) | 4+4 | NoteBook, Peak Controller… |

個別 slot 採用数: Eff_Render 75, Gen_Render 42, TriggerVoice 52, Voice_ProcessEvent 43, NewTick 37, MIDIIn 8, Voice_Render 7, MIDITick 3, MsgIn 3。

---

## 4. 呼び出し規約・データ型

* win64: Microsoft x64。`this`=rcx。整数/ポインタ引数は rcx,rdx,r8,r9, 以降は `[rsp+0x20+8*n]`。`stdcall` は x64 では同一。戻り値 rax / xmm0。**xmm6-15 は callee-saved** (peak 計測 0x5df940 が `movdqa [rsp],xmm6/7` で退避, §6)。
* `int` 引数でも上位 32bit は未定義 (Delphi は `mov dword [..],edx` で 32bit 保存, `Tag` のみ `mov [rax+8],rcx` で 64bit 保存)。lift 時は i32 に切る。
* `PWAV32FS` = `array[0..n-1] of array[0..1] of single` = **ステレオ interleaved float32 (L,R,L,R…)**。根拠: Balance の peak 計測 0x5df940 が `movaps xmm0,[rax]` を 4 本 (=16 float=8 frame) ずつ処理し `Length>>3` 回ループ; 最後に `shufps xmm7,xmm7,1` で L/R ピークを `*r8`,`*r9` に出力。
* Eff_Render は in-place 可 (Source==Dest 可)。Length = frame 数 (Balance: 0x5dfef0 の ramp が `r9d=Length` を `cvtsi2ss` で使用)。
* 補間用 ramp: `0x5dfef0(rcx=pStep, rdx=pCur, r8=pPrev, xmm3=target, [rbp+0x40]=maxstep, [rbp+0x48]=Length)` — 4 つのゲイン (this+0x170..0x17c) を 1 ブロック内で線形に遷移させる (framework 共通 DSP 部品)。
* 実際のミックスは **関数ポインタ変数** 経由: `mov rax,[rip+..]; call [rax]` (Balance 0x6bf0cd)。変数 (VA 0x71e4f0, .bss) は framework 初期化 0x5e19f0 (CPUID 判定) が SIMD 実装へのアドレスを設定する (`lea rax,[rip-0x2e1e]` = 0x5dee90 など)。→ lift では静的に解決して direct 化可能 (§9)。

---

## 5. プラグイン ← ホスト方向 (パラメータ / イベント)

### 5.1 Dispatcher (slot 1) — `FPD_*` ID

Balance の Dispatcher (0x6bde30): 先に framework 既定 `TDelphiFruityPlug.Dispatcher` (0x6b97f0) を呼び、戻りが 0 なら派生側の `switch(ID)`。実測した case と挙動:

| ID | 挙動 (実測) | SDK 名 (公開 SDK の記憶と整合) |
|--:|---|---|
| 0 | `Value`(HWND 親) でエディタ生成 → `this+0x18 = EditorHandle` | FPD_ShowEditor |
| 2 | `[this+0x130..0x148]`(double×4) を `[this+0x120..0x12c]`(float×4) へ cvtsd2ss コピー = スムージング状態のフラッシュ | FPD_Flush |
| 4 | `[this+0xcc]->vtable[0](Value)` 呼出 = sample rate 通知 | FPD_SetSampleRate |
| 5 | (min/max サイズ返却系) | FPD_WindowMinMax |
| 11, 21(0x15), 0x33.. | 追加 case | (未確認) |

### 5.2 ProcessParam (slot 6) — `REC_*` フラグ (r9d)

Balance 0x6beaa0 の `test r9d, imm` 実測:

| bit | 意味 (関数本体から確認) |
|---|---|
| 0x01 | update value: `this[Index*4+0x198]=Value`、内部係数 (pan: 0x150/0x158, vol: 0x160) を再計算 |
| 0x02 | get value: `Value = this[Index*4+0x198]` |
| 0x04 | show hint: 文字列生成 → `this->vtable[+0xb0]` (Delphi 専用 slot 22) |
| 0x10 | update control: `control->vtable[+0x1f0](Value)` (GUI ノブの更新) + コントロール同期 `0x6bfb20` |
| 0x20 | from MIDI: Value を `[param+0x3a8](min)..[param+0x3ac](max)` へスケール (`mulsd`, round 0x409d00) |

SDK では REC_UpdateValue=1, REC_GetValue=2, REC_ShowHint=4, REC_UpdateControl=16, REC_FromMIDI=32 で完全に一致。

### 5.3 MIDI / イベント

* ProcessEvent(slot5): EventID=1 (MaxPoly) は framework 既定 (0x6b97d0); 132/132 DLL で slot5 は非 abstract (既定継承を含む)。
* MIDIIn(slot16) / MIDITick(15) / MsgIn(17) / NewTick(14) は少数プラグイン (VFX 系・Wrapper・Sampler) が override (上表)。

---

## 6. プラグイン → ホスト方向 (TFruityPlugHost vtable)

* ホストは `[this+0xbc]`、vtable は `[Host]`。呼出は `mov rax,[Host]; call qword ptr [rax+8*slot]`。
* **slot0 Dispatcher(Host, HostTag, ID, Index, Value)** — Delphi 呼出列 (6b8f36..6b8f4b):
  `rcx=Host, rdx=this->HostTag([+8]), r8d=ID, r9=Index, [rsp+0x20]=Value → call [rax]`。戻り rax。
* TFruityHost の slot 数 = 46 (offset 0x00..0x168)。プラグイン側で観測された vtable offset は全て ≤ 0x168 に収まる (`host_calls.json`)。

framework 共通コード (Balance) が発行する Dispatcher ID: 0x0d(13), 0x12(18), 0x1d(29), 0x2e(46), 0x3b(59), 0x47(71), 0x1a(26; 版チェック)。
133 DLL のプラグイン固有コードが発行する Dispatcher ID (r8 が即値で識別できた 894 サイト, 他 632 サイトは動的値): 計 **71 種類**。上位 (サイト数/使用プラグイン数): **2 (163/115), 33 (118/114), 3 (71/22), 36 (47/35), 29 (44/23), 50 (36/22), 91 (31/12), 23 (25/25), 46 (24/22), 71 (22/22), 48 (20/12), 30 (19/17)**。上位 30 ID で識別可能サイトの 87% (上位 20 で 80%)。
vtable offset 使用 (固有コード): 0x00 Dispatcher (1526), 0x100 (618), 0x108 (664) — 後二者は同一 `+0xbc` パターンを持つ別オブジェクト由来の偽陽性を含む可能性 (taint 追跡の近似; 精密化は下流 T-ABI-3)。
→ **wasm 側 Host shim は上位 30 ID から実装** (`work/host_calls.json` に per-plugin 集計。残りは fail-fast)。

---

## 7. mac 版 (FPC 3.2.3) との差分

| 項目 | win64 | mac x86_64 |
|---|---|---|
| コンパイラ | Embarcadero Delphi (linker 8.0; RetDec は Delphi 36.0 と判定) | **FPC 3.2.3 [2023/12/20] for x86_64-Darwin** (文字列実測; `fpc.resources` セクション) |
| 呼出規約 | MS x64 | SysV (rdi,rsi,rdx,rcx,r8,r9 / xmm0-7) |
| vtable | C++ 互換 (TObject 仮想は負側) | FPC 標準 VMT (ctor が `call [class+0x68]` = vNewInstance) |
| Info +0x10 | `[rax+0x10]=Info` | 同一 (ctor 0x52c20: `mov [rdx+0x10],rax`) |
| GUI | VCL + Blend2D/QuickFontCache | MacVclCocoa (Cocoa/WebKit リンク) |
| 入口 | `CreatePlugInstance` | `_CreatePlugInstance` + `_SetExternalAppHandle` |

mac で `CreatePlugInstance` を export する先頭モジュールが **FPC ではなく clang C++ (libc++)** のもの: 12 本 (Hardcore, Pitcher, GMS, MiniSynth, Morphine, Toxic Biohazard, DirectWave, FL Studio Mobile ×3 (Rack/Rack FX/本体), および engine 側が入口の BooBass/SimSynth)。 `_CreatePlugInstance` は export trie にのみ存在し symtab は strip 済み。 win の対応物は MSVC 14.29 の単体/engine DLL。 mac 全 177 Mach-O の言語内訳: FPC 134 / clang C++ 43 (nonsystem LC_LOAD_DYLIB 依存は 0 — 共有 lib は dlopen 名参照)。

---

## 8. 再現コマンド

```sh
cd tools/plugins
python3 inventory/win_scan.py           # 313 PE → work/win_pe_scan.json
python3 inventory/nsis_names.py         # NSIS ヘッダ復元 → block↔パス (work/nsis_blockmap.json)
python3 inventory/win_abi.py            # 全 Delphi プラグインの vtable/Info → work/win_abi.json
python3 inventory/delphi_vmt.py <PE> <vtable-0x70+0x58 で得た VMT VA>   # VMT ダンプ
python3 inventory/pedis.py <PE> <VA> 0x120 --until-ret                 # 任意関数の逆アセンブル
python3 inventory/host_calls.py         # Host vtable offset / Dispatcher ID 使用面 → work/host_calls.json
python3 inventory/macdis.py <dylib> 52130 0x100 --until-ret            # mac CreatePlugInstance
```

## 9. lift / wasm 化への含意

1. **Host shim が必須** (wasm 内に TFruityHost 相当の vtable 46 スロット = function table index の配列 + Dispatcher の ID 実装)。実装すべき ID は §6 の上位 ID から開始, 残りは fail-fast (M4 shim 方針)。
2. 仮想呼出は全て `mov rax,[obj]; call [rax+off]` の形 → IR pass で `call_indirect` (wasm table) に落とす。plugin vtable は DLL データ (`.text` 内 VMT) にあるため M6 の "DLL 実データ化" pass と同系の取込が必要。
3. 全プラグインが共通 framework (FP_DelphiPlug+VCL+RTL, **約 1.6 MB / 11.3k 関数** がハッシュ一致) を静的リンク → framework は 1 回 lift して共有 (P0)。plugin 固有部は 12〜400 KB (Tier 表参照)。
4. `Eff_Render` が SIMD 関数ポインタ変数経由 (§4) → framework 初期化 `0x5e19f0` の CPUID 分岐を「SSE 実装固定」に差し替えて direct 化 (wasm 側は SSE→wasm-simd128 の既存 `__asm_*` helper 路線)。
5. 実行時ロード: framework 文字列に `dsp_ippv2.dll` / `Blend2D.dll` / `QuickFontCache` / `ilvideo_x64.dll` / `FLEngine_x64.dll` / `FruityPlug_x64.dll` (全 133 DLL 共通, win)。DSP 経路 (Balance Eff_Render) は IPP を呼ばず DLL 内 SSE 実装のみ — IPP 依存の有無は個別確認が必要 (T2+ で顕在化する見込み, 推定)。
