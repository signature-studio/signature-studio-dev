# REPORT — CAB-68 [SR-1] Serum 2 最小 VST3 host (native / wine 駆動)

- 日付: 2026-10-10 / 対象: Win x64 `Serum2.vst3` (19,236,864 B, 実 DLL) / 方針: bc07970 (無条件アクティベーション) + CAB-237 authstub 適用 DLL
- 範囲: 本 dir (`tools/targets/serum2/host/`) 新設。`license/` は REPORT 末尾メモ追記のみ。`work/` (実 DLL・展開物・ビルド物・wine prefix) は gitignore。
- 再現: `bash tools/targets/serum2/host/e2e.sh` (1 コマンド。build → authstub DLL → seed → case 生成 → 6 run → 判定 **23/23 OK** (#255 で 14→23))

## 0. 結論 (先出し)

1. **最小 VST3 host (C++ 単一ファイル ~1,260 行, `vst3host.cpp`) で Serum2 実 DLL を native 駆動した**。mingw-w64 で PE host をビルドし wine64 上で実行 (Linux native 実行は DLL が Win64 PE のため wine 経由 = native x64 機械語をそのまま実行)。LoadLibrary → InitDll → GetPluginFactory → **4 CID 列挙 (moduleinfo.json と一致)** → IComponent (SerumDSP) / IEditController (SerumController) 生成 → initialize / 接続点接続 / bus 構成 / setupProcessing (kRealtime, kSample32, 128 frames, 48 kHz) → **setState→getState 往復 → process 64 ブロック完走 → 非ゼロ音声出力** (16,380/16,384 cell 非ゼロ, peak 0.691)。
2. **CAB-71 §7 の med ABI slot を実測確定** (実メモリの vtable dump, host/work/out_*/summary.json `*_slots`):
   | vtable (RVA) | interface | 確定 slot |
   |---|---|---|
   | 0xa24048 | SerumDSP の IComponent (CAB-71: ctor obj+0x30) | **slot12 (0x60) = setState 0x4fad0** / slot13 = getState 0x53150 |
   | 0xa240c8 | SerumDSP の IAudioProcessor | **slot9 (0x48) = process 0x56670** |
   | 0xa2bf58 | SerumController の IEditController (CAB-71: slot6/7) | **slot6 = setState 0xc2b50 / slot7 = getState 0xc6090** (CAB-71 どおり実測) |
   - **`call [vtbl+0x30]` with 0x800010 = IComponentHandler::restartComponent (slot6)** — IComponentHandler は beginEdit(3)/performEdit(4)/endEdit(5)/restartComponent(6) の 4 メソッドで restartComponent が slot6 (+0x30)。CAB-71 §7 の「slot5 (+0x28) と +8 ずれ」の謎は **SDK ヘッダ実測で解消** (med → 確定)。host は 0x800010 を直接受信できていない (→ §3-3)。
3. **状態ファイル形式を実測解明** (host 往復 + 逆アス 0x1801bf1c0/0x1801bdcd0): `"XferJson\0"` + **u64** meta JSON 長 + meta JSON + payload (`u32 展開後長 + u32 版本(=2) + zstd`)。**meta だけでは復元されず (S_FALSE)、payload が必要** (V1/V2 実測)。plugin 自身の保存物は meta (component/hash/preset*/product/productVersion/url/vendor/**version:11.0**) + payload。
4. **E2E (2×2 matrix + 2): patched/unpatched × licensed/demo 合成 state** — 全 6 run で (a) 復元 kResultOk (0)、(b) save→restore→save **バイト一致**、(c) 保存 controller state に demo マーカ無し (= demo bit 0)、(d) demo bit 直接 probe (IEditController this+0x22792) = 0、(e) process 非ゼロ出力。**corrupt payload 対照で setState が S_FALSE に変化** → payload は setState 内で実際に処理されることを実証。
5. **未達 (→ 引継)**: demo 経路の発火観測。meta の `demoVersion` は 0x18004fad0 / 0x1800c2b50 の分岐に**届かない** (payload 側 DOM を参照すると推定, §3-2)。controller の demo bit / 0x800010 経路は内部フラグ **+0x10c == 1 が前提で、全 headless 構成で 2 のまま** (§3-3)。よって 0x800010 の受信観測と demo bit = 1 → マーカ保存の E2E は未成立 (CAB-237 の wasm ハーネス 23/23 が IR レベルで担保済み、実 DLL 経路は下流へ)。

## 1. 成果物 (tools/targets/serum2/host/)

| パス | 役割 |
|---|---|
| `vst3host.cpp` | 最小 VST3 host 本体。host 側 COM 実装 (HostApp / Handler(IComponentHandler+2) / MemStream(IBStream+ISizeableStream) / EventList / ParamChanges / AttrList / HostMsg) + **全呼出の vtable slot ログ** + **vtable 実読みダンプ (slotmap)** + demo bit probe (+0x22792 直読み) |
| `build.sh` / `setup_sdk.sh` | mingw-w64 ビルド / vst3sdk ヘッダ取得 (work/vst3sdk, gitignore) |
| `make_cases.py` | case 生成: CAB-237 合成 meta (licensed) + demo マーカ追加 (demo) を XferJson コンテナに封入 (payload は seed run 由来) |
| `e2e.sh` | 1 コマンド E2E (6 run + 判定) |
| `summarize.py` | summary.json 解釈 + 判定 (14 checks) |
| work/ (gitignore) | DLL (patched)、cases、out_* (log/summary/saved state/audio)、wineprefix、vst3sdk |

## 2. 初期化シーケンス実測 (host → plugin)

| 手順 | 実測 |
|---|---|
| export | `InitDll` / `ExitDll` / `GetPluginFactory` の 3 つ。InitDll/ExitDll を呼出 (正常返回) |
| getFactoryInfo (slot3) | kResultOk, vendor "Xfer Records", url xferrecords.com, flags 0x10 |
| countClasses (slot4) / getClassInfo2 (slot6) | **4 class**: Audio Module "Serum 2" / Controller "Serum 2" / Audio Module "Serum 2 FX" / Controller "Serum 2 FX" |
| CID | in-memory CID = moduleinfo.json hex を **FUID(l1,l2,l3,l4) 引数順** (4 dword) として from4Int 変換したものと一致 (`cid_moduleinfo_fuid_conv_match=1`)。moduleinfo の hex はメモリ順**ではない** |
| createInstance → initialize | component/controller とも kResultOk。**plugin は host context に IVst3ToAUWrapper / IVst3ToAAXWrapper を queryInterface** (kNoInterface で継続, 正常) |
| getControllerClassId (IComponent slot5) | controller CID を返す (moduleinfo 一致) |
| setComponentHandler (slot16) / IConnectionPoint | 両者 IConnectionPoint 実装あり。connect 時に plugin は host の createInstance で **IMessage** を要求し 'Connected' ×3 を送信 |
| bus | **audio in=0 / out=1 ("Audio Output", 2ch, kDefaultActive) / event in=1**。setBusArrangements(0in, kStereo out) = kResultOk。チケット記載の「2in2out」は实际は「out 2ch + MIDI in 1」(Serum 2 instrument の入力 audio bus 無し) |
| setupProcessing (slot7) | kResultOk (kRealtime / kSample32 / 128 / 48000) |
| getParameterCount (slot8) | **2,623 param** |
| plugin が host に問合せた非標準 IID | Handler に `88688A2F-C960-B54B-9D63-4444E613D66A` (現行 vst3sdk ヘッダに無し, kNoInterface で継続) |

## 3. 状態復元・demo 経路の実測

### 3-1. 往復 E2E (確定)
- 合成 licensed state (CAB-237 §3 の meta: `component`/`productVersion:"2.1.5"`/`version:2.1`、demo マーカキー無し) を正しいコンテナで封入 → **comp.setState / ctrl.setComponentState / ctrl.setState すべて kResultOk (0)**。VST3 の戻り値语义に注意: **kResultFalse = 1 = S_FALSE (部分/打切り), kResultOk = 0 = 成功** (初期の解析で逆に読んだのはこれが原因)。
- save→restore→save がバイト一致 (proc/ctrl とも)。保存 controller state に demo マーカ無し → **demo bit == 0 で保存される** (patched)。demo bit 直接 probe (this+0x22792) も 0。
- corrupt payload (zstd 1B 破壊) → 3 setState すべて S_FALSE に変化 → **payload は setState 中に実際に展開・検証される**。
- audio: 全ケースで 16,380/16,384 cell 非ゼロ (peak 0.691) — **音声経路は認可 stub に依存しない** (patched/unpatched 同一統計, process 0x56670 実測)。NoteOn(pitch60) を投げると出力、NoteOff(block24) 後は減衰。

### 3-2. demoVersion は payload 側 DOM を参照 (med → 実測による限定)
- meta JSON に `demoVersion` を置いても DSP setState (0x18004fad0) の demo 分岐は発火しない (戻り・dialog queue 領域 +0x139bc8 の probe・保存結果のすべてが licensed と同一, unpatched/patched 両方)。
- 一方 payload を壊すと S_FALSE になる (= payload は読まれる)。0x1801bf1c0 は meta JSON と payload を**別々に parse** し (0x1801bf5f0 / 0x1801bfb00 の 2 DOM)、demoVersion / タグ等の lookup は **payload 由来 DOM 側**に働くと推定 (med)。
- → demo 経路を発火させるには **payload (Serum 独自 binary、fixstr 風 [type][len][str] 構造) への demoVersion 注入**が必要 = **payload writer (0x1801be2e0 系) の解読が前提**。SR-3 (DSP/JSON closure lift) の領域。

### 3-3. controller demo bit / 0x800010 のゲート (実測)
- 0x1800c2b50 の demo bit 書込 + 0x800010 通知ブロックは **`*(int*)(controller_base+0x10c) == 1` をゲートに持つ** (decomp 実測。IEditController this + 0xdc)。
- 本 host の全構成 (initialize / connect / createView('editor') 取得まで) で +0x10c は **2 のまま不変** (3 秒ポーリングで変化なし, 5 run 実測)。+0x10c の writer は 167 関数 decomp 集合に無い (copy ctor 風 0x18000d1b0 が config+0x30 → obj+0x10c を写すのが近傍)。
- 推定: +0x10c = DSP↔controller の shared-data リンク ("SerumDSPSharedData" 0x1800b61b0 経由) や editor open 完走など、更に深い初期化完了フラグ (med)。
- 実測された通知: `restartComponent(flags=0x10 = kParamTitlesChanged)` が 1 run に 3 回 (comp.setState 後 / setComponentState 後 / getState 後)。**0x800010 (= 0x10 kParamTitlesChanged | 0x800000 独自ビット) は未受信** — 発火条件が §3-2/3-3 の未達成部に依存。

### 3-4. host として観測した demo 関連挙動 (memo)
- unpatched + licensed 合成 state でも demo 化しない (bit 0, マーカ無し)。CAB-237 §3 の「productVersion 2.1.5 ≥ 2.0.20 → store 無し」契約と整合。
- prefs singleton (N8): plugin が wine prefix の `%APPDATA%/Xfer/Serum 2/Serum2Prefs.json` を**実ファイルとして生成・保存**することを実確認 ("Automatically Check for Updates": true 等)。2 回目以降の起動はこれを読む。
- 通信系 (N5): 更新チェックは prefs 有りの起動で走る可能性があるが、本 e2e (WINEDEBUG=-all, タイムアウト付き) では停止・遅延なし。wasm shim 側の no-op/fail-fast 受口は未実装 (CAB-237 §4 の設計どおり下流)。

### 3-5. [SR-1b #255] payload 解読 + demoVersion 注入 A/B (実測 2026-10-12, wine 9.0 / Actions runner)
- **payload の正体 = CBOR (RFC 8949)**。zstd 展開後の先頭 `0xb8 0xa4` は msgpack 風ではなく CBOR の map(1B 長=164) / `0xb8 0x3b` = 59 entries、続く `0x64 'Arp0'` は text(4)、`0xa2` = map(2)、`0xa0` = 空 map。key は text・辞書順昇順。processor 164 key / controller 59 key。
  - float は float32 (`0xfa`) 無損失なら `0xfa`、でなければ `0xfb` (nlohmann::json::to_cbor の挙動と一致。DLL に nlohmann json v3.12 の型名あり)。
  - 最上位に meta JSON と同名キー (component/product/productVersion/tags/version…) が重複。**setState が見る DOM = この CBOR 側**。
  - コンテナ: `u32 展開後長 + u32 版本(=2) + zstd`。0x1801bf1c0 は版本 2 → 0x1801bf480 (0x176e0 B ctx + BMI2 cpuid 検査 = zstd 展開と推定, med) → 0x1801bfb00、版本 0/1 → 0x180571dc0 → 0x1801bf5f0。**どちらが CBOR parser かは未特定** (writer 0x1801be2e0 は `"XferJson"` + 版本 2 + `hash` を組む箇所までを確認、lift は未実施)。
- **`payload_codec.py`** (decode/encode/split_state/join_state): seed の既定 state で **processor 5,364 B / controller 1,878 B とも encode(decode(x)) がバイト一致**。zstd 再圧縮は processor 1,053 B 一致 / controller は 651 B vs 元 647 B (zstd 内部差。展開後は一致)。
- **demo 注入 A/B** (`make_cases.py` v3 に `lic_sent` / `demo_payload` 追加、sentinel = processor `mpePitchBendRange` 24 (既定 48) / controller `presetName` "SENTINEL"):

  | run | processor sentinel 適用 | controller sentinel 適用 | 解釈 |
  |---|---|---|---|
  | patched + lic_sent | 適用 | 適用 | 対照 (復元は走る) |
  | unpatched + lic_sent | 適用 | 適用 | 対照 |
  | patched + demo_payload | 適用 | 適用 | authstub が demo 分岐を無効化 |
  | **unpatched + demo_payload** | **非適用 (48 のまま)** | 適用 | **0x18004fad0 の demo 分岐発火 = 復元打切り** |

  - setState 戻りはすべて kResultOk (0)。**demo 分岐は戻り値には出ず、状態が適用されないことでのみ観測できる** (#69 で戻り値・dialog queue 無変化だったのはこのため。meta 注入は no-op)。
  - demoVersion は payload 最上位キー `demoVersion` (text) で効く。meta のみに入れる従来の `demo` case は引き続き無変化。
- **未達 (本チケット範囲だが成立せず)**:
  1. dialog queue probe (+0x139bc8 の xor) は run ごとに値が揺れ (heap 未初期化領域を含む、unpatched+lic_sent と unpatched+demo_payload で setState 前後とも同値) **dialog 発火の判定には使えない**。
  2. controller 側: payload に `kAudioUnitParameterFlag_IsHighResolution=false` を入れても **demo bit (this+0x22792) = 0、0x800010 未受信、保存 state にマーカ無し**。ゲート +0x10c == 2 のまま (§3-3 と同じ。SR-1c)。
  3. writer/reader の lift・型タグ体系の IR 化は未実施 (CBOR と判明したため独自 binary の型表は不要。nlohmann 相当は OSS 境界として扱える可能性 — 要判断)。
- #238 契約との突合: 「demoVersion 検出 → 復元打切り」は **実 DLL で processor 側のみ確認**。「productVersion 2.1.5 ≥ 2.0.20 → store 無し」は §3-4 (meta) のとおり変化なし、payload 側 productVersion を下げる A/B は未実施。
- e2e: `bash tools/targets/serum2/host/e2e.sh` = **23/23 OK, 39.7 s** (ベースライン 14/14 は 43.0 s)。

## 4. 受け入れ条件との対合 (CAB-68)

| # | 条件 | 実測 |
|---|---|---|
| 1 | factory が 4 CID を返す | **達成** (moduleinfo.json と一致, FUID 変換規則も確定) |
| 2 | setupProcessing が成功し process を N ブロック無例外で完走 | **達成** (kResultOk, 64 ブロック × 128f, 非ゼロ出力付き。44.1/48 kHz は 48 kHz 実施) |
| 3 | 未実装 import / 呼ばれた shim の一覧 | wine が 13 DLL 332 import を全て解決 (実測で不足なし)。plugin → host の拡張 queryInterface 一覧は §2 表。API レベルのトレース (WINEDEBUG=+relay) は次項 |
| + | (本チケット範囲) med ABI slot 確定 / 認可 stub 適用 DLL 駆動 / 0x800010 観測 | slot 確定 **達成** / stub DLL 駆動 **達成** / 0x800010 **未達** (§3-3, 引継) |

## 5. 引継ぎ (CAB-74 / SR-3 系)

1. ~~payload の解読~~ — **完了 (#255, §3-5): CBOR と判明**。残: writer/reader の lift 要否判断、payload 側 productVersion 下げ A/B。
2. **controller +0x10c の setter 特定** — 0x800010 観測の前提。候補: IConnectionPoint notify ("SerumDSPSharedData") 処理部 / editor open 完走 / FX-class 区別。gdb watchpoint (wine) か lift で特定。
3. ~~demoVersion 注入後の A/B E2E~~ — **processor 側は完了 (#255, §3-5)**。controller demo bit / 0x800010 は SR-1c。
4. **WINEDEBUG=+relay による呼出 API 一覧化** — CAB-68 受け入れ #3 の API レベル証跡 (wine 固有の代役を除くリスト化)。
5. mac 版 (universal2) 未実施 — Win を正とする方針どおり。

## 6. 再現

```sh
bash tools/targets/serum2/host/setup_sdk.sh      # vst3sdk ヘッダ (初回のみ)
bash tools/targets/serum2/host/e2e.sh            # 全工程 → work/e2e_result.txt に 14/14
# 個別
bash tools/targets/serum2/host/build.sh          # host ビルド (mingw-w64)
python3 tools/targets/serum2/host/make_cases.py host/work/state host/work/out_seed host/work/cases
WINEPREFIX=host/work/wineprefix wine64 host/work/build/vst3host.exe \
  'Z:\...\Serum2_win64.authstub.vst3' 'Z:\...\cases\licensed' 'Z:\...\out_x' 64 'Z:\...\exe_extract'
```
- 前提: `wine64`, `g++-mingw-w64-x86-64`, `xvfb`(任意), CAB-71/237 資産 (`license/authstub/mpatch.py`, `synth_state.py`), 実 DLL `work/Serum2_win64.vst3`。
- 成果物: `work/out_*/{log.txt, summary.json, saved_*_state.bin, audio_f32_interleaved.raw}` (gitignore)。

## 7. 制限

1. wine 経由 (Linux に Win64 PE をそのままロードする手段が無いため)。音声・COM・SEH は native x64 実行だが、Win32 API は wine 実装。
2. GUI (IPlugView open/frame) は未実施 — createView 取得まで。demo dialog は modal の可能性があり headless では opened にしない選択。
3. 44.1 kHz / 512 frames 等の他サンプルレート未網羅 (48 kHz / 128f 固定)。
4. 0x800010 受信観測と demo bit = 1 経路は未達 (§3-2/3-3)。CAB-237 wasm ハーネス (23/23) が IR レベルの担保を維持。
