# REPORT — N hostbridge (Fruity Wrapper の VST2 ロード経路解析 + wasm 同梱プラグイン表の設計 + mini VST2 host PoC)

## 0. 結論 (先出し)

- **検収 1 コマンド**: `bash tools/hostbridge/hostbridge.sh` → **65/65 PASS** (evidence 21 / PE スタブ 3 / marshal 単体 13 / PoC 28)、build 込み 4〜10 s。
- **Fruity Wrapper の正体と経路を確定** (Ghidra decompile 根拠付き, `evidence/` + `HOSTBRIDGE.md` §1):
  FL 本体は VST を直接ロードせず、`Fruity Wrapper_x64.dll` (win64 `block19091/23676`, Delphi 6 MB, export `CreatePlugInstance`) を Fruity プラグインとして `SafeLoadLibrary`+`GetProcAddress`
  (`fle:0xd8cab0`)。VST2 の実ホストは Wrapper の `fw:0x7a9db0` (TVSTPlugin ctor): 事前 export 検査 → `SafeLoadLibrary(path,0x8000)` → **26 エントリの綴り表** (VSTPluginMain が 2 回登場するため重複除き 25 種) で `GetProcAddress` →
  `main(audioMaster=fw:0x7a87c0)` → `'VstP'` 検査 → `resvd1=this` → `dispatcher(effOpen)` …。32bit/"Make bridged" は `ilbridge.exe` を別プロセス起動する別経路 (wasm では instance 分離で代替)。
- **AEffect の Win64 配置を OTT ネイティブ ctor で独立確認**し、Wrapper 側アクセスと完全整合 (`poc/vst2_abi.h` に `_Static_assert` で固定, 公開 SDK ヘッダ不使用)。
- **設計決定**: 「1 DLL = 1 wasm instance = 専用 linear memory」+ VST2 境界の table 駆動 marshalling (共有メモリ方式は VA 焼付け/関数名 `function_<VA>` 衝突で不採用)。
  `LoadLibrary/GetProcAddress/FreeLibrary` は事前登録モジュール表へ解決し、関数ポインタは bridge 払い出しの合成 VA (thunk slot)。詳細 `HOSTBRIDGE.md` §2。
- **PoC**: FL 側の代役 mini host (freestanding wasm32 C, 3.7 KB) が Wrapper と同手順で **M10 の lift 済み OTT wasm** をロードし `processReplacing` を駆動。
  bridge 経由出力は直接呼出と **512/512 bit 一致**。`obj+0x248=0` (M10 e2e 条件) では **M10 の出力と 512/512 一致 (junk census は `tools/ott/REPORT.md` §2.3 の旧 chain 行と同値)** = 「M10 到達水準をそのまま bridge 越しに再現」。音質正当性は別チケット。
  **注意 (参照の性質)**: この 512/512 一致の両辺はどちらも **RetDec lift 済み wasm (M10 chain) の出力**であり、native 機械語実行との比較ではない。M10 chain の出力は junk (census: junkHi 175 / junkTiny 136 / 512) を含むため、これは「bridge が lift 済み plugin の挙動を変えない (透過性)」の証明であって **DSP 正当性の証明ではない** (junk 同士の一致)。tools/ott (R, f4e0514) が native OTT 機械語の VA 敷設実行を参照に、RetDec lift の間接 call 脱落 (D1) 等が junk の主因と結論済み (正解出力は junk 0/512)。bridge を R の x64c lift 版 closure へ差し替えての native 照合は未実施 → 下流 H2 で実施。

## 1. 実測 (全て `work/poc_result.json` / `work/e2e.log` 由来)

| 項目 | 値 |
|---|---|
| ロード手順の再現 | LoadLibraryW→GetProcAddress 2 回目で命中 (`VstPluginMain` 不在→`VSTPluginMain`)→main→magic→effOpen…(T2a-j 全 OK) |
| AEffect (host 側 proxy) | name/vendor/product=OTT/Xfer Records/OTT, uniqueID=0x58665454 ('XfTT'), in/out=2/2, numParams=20, numPrograms=1, flags=0x18 (CanReplacing, HasEditor 無) |
| upcall | audioMasterVersion×1 (VSTPluginMain 内, ネイティブ同様 NULL→0 なら失敗), GetSampleRate×1 (effOpen 内) |
| bit 一致 (bridge vs 直接) | `processReplacing` 256f×2ch: **0/512 diff**。A/B 2 本交互 2×128f: diffA=0, diffB=0。2 本目 instance 出力 = 1 本目 (同一 HMODULE, refcount=2, 別 AEffect) |
| bit 一致 (vs M10 e2e) | `[0x248]=0` 条件: **0/512 diff** (census は `tools/ott/REPORT.md` §2.3 の旧 chain 行 = M10 と同値) |
| 自然フローの経路 | `obj+0x248` 既定値 = **1** (ctor 直後も 1)。census zero 4 / normal 254 / junkHi 252 / junkTiny 2 (= M10 REPORT §3.3 の `[0x248]=1`)。M10 は手で 0 に強制 |
| bridge オーバーヘッド | getParameter 往復の bridge 経由絶対値 **0.39–0.44 µs/call** (静穏時の最良値; 直接呼出 0.11 µs → 純増 ≈0.3 µs)。検収で 5 回再実測すると CPU 共有のため 0.77–1.62 µs (純増 0.48–1.33 µs) まで変動。128f processReplacing の bridge−直接差は静穏時 −21〜−4 µs だが再実測では −303〜+92 µs (予算 2902 µs の −10.4%〜+3.2%) とばらつく = 測定誤差大で「±1% 未満」は静穏時のみ。RT 予算比では概ね 10% 未満 (T7) |
| DSP 自体 (参考) | `-O0 -g1` 版 lift で 128f あたり 395–887 µs (予算比 14–31%) |
| marshal 規則 | opcode 規則 9 kind (instr/outstr/struct_out/rectpp/chunk_out/chunk_in/events_in/speaker_in/handle) + audioMaster 規則 (ret_struct/events_in/outstr/instr) を FakeGuest で網羅 (13/13)。規則の無い ptr は guest へ渡さず計上 |
| メモリ | 3 instance prewarm で node RSS 62 MB (instance 毎 864 MiB は仮想予約のみ, 現状 `initial=max=0x36000000`)、全試験後 110 MB。prewarm 48 ms |
| 解析規模 | Wrapper 20,654 関数を Ghidra 自動解析 (3 分), VSTPlug unit 188 関数を decompile して host が発行する dispatcher opcode **36 種**を集計 |

## 2. 成果物 (tools/hostbridge/)

| パス | 内容 |
|---|---|
| `HOSTBRIDGE.md` | §1 Fruity Wrapper 解析 (FL→Wrapper→VST2, audioMaster, opcode 表, AEffect 根拠, bridged, Plugin Manager/DB, VST3/AU/CLAP 概要) / §2 wasm 置換設計 / §3 PoC / §4 制約 / §5 下流チケット |
| `evidence/` | Ghidra decompile/disasm の抜粋 (18 ファイル, 計 ~75 KB)。`analysis/verify_evidence.py` が主張 21 項目を機械検査 |
| `analysis/` | `reproduce.sh` (素材→Ghidra→evidence 再生成, 初回 ~3 分/以降 ~80 s)、`opcode_census.py`、`dump_name_table.py`、`check_pe_stub.py` |
| `ghidra_scripts/` | `Query.java` (xrefstr/refsto/decomp/disasm/decompall/grepins)、`run.sh`、`DumpFunctions.java` |
| `poc/vst2_abi.h` | 自前 AEffect (Win64, 0xC0 B)/opcode 定義 |
| `poc/host_vst2.c` | mini VST2 host (Wrapper §1.3 の手順と audioMaster を再現) |
| `poc/hb_bridge.mjs` | `ModuleTable`+`HostBridge` (LoadLibrary/GetProcAddress/FreeLibrary shim, thunk slot, AEffect 鏡像, marshal 規則表, upcall) |
| `poc/plugin_ott_entry.c`, `hb_lib.js` | OTT 用入口 surrogate (VSTPluginMain/dispatcher/AEffect thunk の SDK glue) + plugin→host import |
| `poc/ott_module.mjs`, `build_*.sh` | OTT module descriptor (prewarm pool)、wasm ビルド (m10 の `ott_m10.ll` を **コピー**して使用, m6〜m10 は読取のみ) |
| `poc/pe_stub.mjs` | 仮想 FS 用の最小 PE スタブ生成 (1 KB, pefile で検証) |
| `poc/test_marshal.mjs`, `poc/run_poc.mjs` | 単体試験 / PoC 検収 |
| `hostbridge.sh` | 1 コマンド検収 |

再現: `bash tools/hostbridge/hostbridge.sh` (前提: `tools/m10/work/ott_m10.ll`。無ければ `bash tools/m10/m10_e2e.sh`。node は `~/.local/share/pnpm/bin` を自動で PATH に追加)。
解析の再生成: `bash tools/hostbridge/analysis/reproduce.sh`。

## 3. 設計の要点 (詳細は HOSTBRIDGE.md §2)

1. **表**: `modules[]` (wasm 実体・refcount) と `plugins[]` (LoadLibrary される名前/alias → module + export 名) を分離。Kilohearts の 47 stub→共有 core、Fresh Air の shell→core は **stub elision** (alias のみ)。
2. **shim**: path 正規化→alias 引き→HMODULE (合成値, 126/127 エラー再現)。`GetProcAddress` は PE 同様 case-sensitive。`FreeLibrary` refcount 0 で instance 破棄。
3. **関数ポインタ**: bridge 払い出し VA (`0x7ff700000000+16n`) を lift 済みコードの間接呼出が `icall(fn,a0..a5)` に落とす 1 点。float は Win64 の xmm 位置スロットに f32 ビット (M7〜M10 の規約と同じ)。
4. **AEffect 鏡像**: host 所有欄 (resvd1/2, user, uniqueID) と plugin 所有欄 (numPrograms..flags, delay/ioRatio, object, version) の同期点を明示。
5. **GUI**: G0 (HasEditor を立てず Wrapper の generic editor を使わせる, PoC 実装) → G1 (manifest 宣言 web UI) → G2 (本来の GUI を lift)。
6. **VST3 (Serum 2 は VST3 のみ)**: 境界が C++ vtable なので opcode 表は流用不可。plugin module 内に最小 VST3 host を同梱し VST2 風 facade を見せる案を推奨 (§2.9)。
7. **新発見の制約**: Wrapper は LoadLibrary 前に DLL ファイルを 2 回読む (export 名検査/PE bitness 判定) → 仮想 FS に **最小 PE スタブ**が必要 (生成器は実装・検証済)。DB は entry export 名 hint を保持でき、多製品 core 用の機構が元からある。

## 3-b. HB-H17 (#787): PE 事前検査を仮想 FS に結合 (実測)

- 対象: Fruity Wrapper の事前検査 `fw:0x7a9030` (export 名に main / vstpluginmain / hint の一致) と bitness 判定 `fw:0x5bfc30`。
- 結合: `poc/pe_stub.mjs` の PE スタブ (1024 B) を `tools/assets/wvfs` の `Wvfs` (`/c/home`、`pathreg` 写像 `C:\Users\webstudio\...\OTT_x64.dll` → `/Documents/...`) に書き、閉じて開き直した後の読み戻しバイト列を検査する。
- 実 Wrapper: fl-win64 素材の `extracted/block19091_PE.bin` (x64 DLL, export `CreatePlugInstance` / `__dbk_fcall_wrapper` / `dbkFCallWrapperAddr`)。
- 再計算: `bash tools/hostbridge/analysis/pe_precheck_vfs.sh` (`analysis/pe_precheck_vfs.mjs`, `pefile` 照合を含む)。

| 区分 | ID | 内容 | 結果 |
|---|---|---|---|
| 正 | P-route | pathreg 写像で `/c/home/...` へ振り分け | PASS |
| 正 | P-persist | reopen 後の読み戻し sha256 一致 (1024 B) | PASS |
| 正 | P-precheck | 読み戻しバイトが事前検査を通過 (export `main`) | PASS |
| 正 | P-pefile | pefile の machine / DLL / export 名と一致 | PASS |
| ネガ | N1 | PE が仮想 FS に無い → ENOENT、事前検査も不合格 | FAIL 検出 (期待どおり) |
| ネガ | N2 | export が `Foo`/`Bar` → 不合格 | FAIL 検出 |
| ネガ | N3 | 実 Wrapper を VST として検査 → 不合格 (export 名に main 無し) | FAIL 検出 |
| ネガ | N4 | machine を x86 (0x14c) に変更 → 不合格 | FAIL 検出 |
| ネガ | N5 | 先頭 64 B に切り詰め → 不合格 | FAIL 検出 |

数え方: 正 = `P-*` 4 件の PASS 数。ネガ = `N1`〜`N5` のうち「期待どおり不合格になった」件数 (5 件)。実測は `SUMMARY P=4/4 NEG=5/5 failed=0`。
範囲外: 本ハーネスは事前検査の JS 実装 (`precheck`) で判定する。Wrapper 本体 (lift 済み) が仮想 FS の読込を実際に呼ぶ経路の結線は H4 の本体作業 (wasm 側)。`tools/assets/wvfs/test/wvfs-node.test.ts` の既存 `tmp routing` 行は `user` プロファイルが `pathmap` 既定表外のため既存で失敗 (本件と無関係・未修正)。

## 4. 未解決・ブロッカー

1. **surrogate (SDK glue) 依存**: lift closure (M6〜M10, 166 関数) に `VSTPluginMain`/`createEffectInstance`/`dispatchEffectClass`/static thunk/`AudioEffectX::dispatcher` が無く、`plugin_ott_entry.c` が代行 (差し替え点は `hb_icall` のみ)。Chunk/Program/MIDI 等 opcode は OTT で未実装。
2. **lift 起因の欠陥**: lift 済み `AudioEffect` ctor は r8d/r9d (numPrograms=1, numParams=0x14) を落とし AEffect の両欄が 0 (PoC は native 値で補正)。getParameter の xmm0 戻りの lifted 表現は未確認 (shadow 値で代替)。audioMaster の実 callback は lift 済み ctor には 0 を渡す (M10 と同じ)。
3. **メモリ**: 現状の lift は instance 毎 864 MiB 予約 (PE image=`0x30000000+RVA`)。複数 plugin 同時ロードには低位 base 化が必須 (H1)。
4. **`.nfo/.fst` の書式未確認** (インストーラに実物なし; キー集合のみ文字列から復元)。
5. Fruity Wrapper 2 ビルド (19091/23676) の差分の意味 (Effects/Generators 版) は推定。実ブラウザの同期 instance 生成・AudioWorklet 配置は node で代替しており未検証。
6. 音質・bit-exact は対象外 (§0 注意の通り参照は lift 済み wasm 同士で native 比較ではない。tools/ott の native 参照によれば M10 chain の出力は正解と別物) (M10 到達水準を再現するのみ)。**自然フロー既定の `[0x248]=1` 経路は junk がより多い** (252/512) — DSP 側チケットの前提情報として要共有。

## 5. ユーザ依頼事項

- 特に無し (Windows 実機/Wine は不要だった)。`.nfo` 書式を確定したい場合は、FL Studio for Windows の実機で生成された `Presets\Plugin database\Installed\**\*.nfo` を数個 (VST2 1 個・VST3 1 個) 提供してもらえると H9 が即解決する (任意)。

## 6. 次タスク提案 (下流チケット案; 優先順)

| # | チケット | 要点 |
|---|---|---|
| H1 (P0) | lift base 可変化 | `ir6_shift`/globals/memory を plugin 毎に低位 base・小 memory (≤64 MiB) へ、`function_<VA>` に module prefix |
| H2 (P0) | OTT closure を VSTPluginMain まで拡張 | `ott:0x180128ba0/0x180125b40/0x180126c00/0x180127430..` + `AudioEffectX::dispatcher` を lift し surrogate 撤去、audioMaster 実 callback |
| H4 (P0) | Fruity Wrapper の lift + shim 結合 | Wrapper 自体を lift (Delphi, M5 の FastMM/try-finally 資産)、`SafeLoadLibrary` 系/PE 事前検査 (仮想 FS+PE スタブ)/`bridged` 無効化/`CreateProcessW` fail-fast、PluginManager 代替走査 |
| H3 (P1) | 整数引数/戻り値復元 pass | ctor r8d/r9d 落ち、getParameter xmm0 戻り (M7 f32 引数 PoC の拡張) |
| H5 (P1) | VST3 方式 spike | Serum 2 向け: module 内同梱の最小 VST3 host + VST2 風 facade (IComponent/IAudioProcessor のみで process 駆動) |
| H7 (P1) | shell/core 入れ子 | Kilohearts HeartCore (76.6 MB)/Fresh Air SlateCore (36 MB) の共有 module+alias、遅延ロード・起動時間計測 |
| H9 (P1) | `.nfo/.fst` 書式解読 | `fle:0x9db5b0` 周辺の decompile から書式確定→DB 生成器 |
| H6 (P2) | web UI G1 | OTT `.rsrc` PNG 抽出 + 宣言的ノブ UI + `effEdit*` 結線 |
| H8 (P2) | ブラウザ実機 | 同期 `WebAssembly.Instance`、worker/AudioWorklet 配置、SAB RPC (§2.7) |
| (DSP) | OTT 自然経路 `[0x248]=1` の junk | M11 の「per-sample 破れ」課題に、natural flow が `[0x248]=1` である事実を追記 |

## 5'. Win32 shim 表 (#784 / H4 分割 b)

- **実装**: `poc/hb_bridge.mjs` に `SafeLoadLibrary(path, mode)` (SetErrorMode → LoadLibraryW → 旧モード復元, fw:0x449770 と同形)、`SetErrorMode`、`timeGetTime` (起動からの経過 ms, DWORD 折返し)、`CreateProcessW` (呼ばれたら原因付き throw = fail-fast)、`ModuleTable.register` での bridge 種別の native 強制 (`bridge`→0, 要求値は `bridgeRequested` に保持)。`GetProcAddress`/`FreeLibrary`/`LoadLibraryW` は既存実装を流用。
- **試験**: `poc/test_shim.mjs` (OTT 非依存)。`hostbridge.sh` の [3c] で実行。
- **前提**: `poc/test_marshal.mjs` は `tools/hostbridge/work/host_vst2.wasm` を読むため、`hostbridge.sh` [2] (build) 実行後にのみ動く (clean checkout では ENOENT)。PR 記載の「checks 13 / broken 0」は build 後の結果。
- **数え方の定義**: `checks` = 実装側の試験 S1〜S8 に含まれる check 行 (`OK`/`FAIL` の行、`S[0-9]+[a-z]? ` 形式) の件数。`ネガコン` = 実装を外した mutant 6 種 (SafeLoadLibrary のモード非復元 / GetProcAddress の大小無視 / FreeLibrary の refcount 無視 / timeGetTime 定数 / CreateProcessW 黙って成功 / bridged 強制の素通し) のうち、対応 check が 1 件以上 FAIL した数。期待値は 6/6。
- **再計算**: `bash tools/hostbridge/poc/recount_shim.sh` (`test_shim.mjs` を実行し OK/FAIL 件数と negative controls caught を出力)。
- **実測** (`recount_shim.sh`, HEAD = 784 ブランチ): real checks OK=18 FAIL=0; negative controls caught=6/6; `[shim] ALL PASS`。
- **OTT e2e (受入 1) 実測** (HEAD b7d7c018, 素材 `oc_artifacts: fl-win64 toolchain-emsdk toolchain-retdec analysis-ott-binaries work-m6-ott` を取得して展開。`ANALYSIS_DIR=$HOME/analysis`):
  - `bash tools/hostbridge/hostbridge.sh` (foreground): exit=0, 所要 4 秒 (build 済み `HB_SKIP_BUILD=1` での再実行。初回は [2] build を含めて実行)。[1] E1〜E20 OK / [3b] `checks 13 / broken 0` / [3c] `[shim] ALL PASS`・ネガコン 6/6 / [4] `[run_poc] checks 28 / broken 0` → `[hostbridge] ALL PASS`。
  - 比較対象 `d78208de^` (shim 追加前, 同じ素材・同じ build 手順で `[2]`→`[4]`): exit=0, `[run_poc] checks 28 / broken 0`。
  - 前後比較: `run_poc.mjs` の出力を時間・RSS・ビルド時刻・アドレス以外で diff → 差分なし (`bridge stats`・`T5c`〜`T8b` の結果行・`checks 28` が一致)。OTT 経路は shim 追加で不変。
  - 前提の補足: `analysis/check_pe_stub.py` は `pefile` を要する。runner に未導入だと [3a] で `ModuleNotFoundError` により停止する (`pip install --user pefile` で解消)。`hostbridge.sh` 自体は依存を入れない。
- **注意**: bridged 強制は `ModuleTable.register` 経由の全 descriptor に効くが、現行 descriptor に `bridge` 欄は無く実効値は常に 0。Wrapper 側 `this+0x761` の本物の制御 (Wrapper を lift した後) は H4 本体の範囲。

## 5-c. HMODULE 採番の解放後衝突 (RT-14, #2520)

- **既知類型との関係**: 該当なし (DEFECTS.md の lift 類型ではなく、hostbridge ハーネス内の採番不具合)。検証起点 = origin/main `6505235b`。
- **原因 (実測で再現)**: `LoadLibraryW` の採番 `HMODULE_BASE + (loaded.size + 1) * 0x10000` は、`FreeLibrary` で `loaded` が縮むと生存中の handle と一致する。
- **再現 (修正前 = hb_bridge.mjs を未修正のまま S9 のみ追加)**: `test_shim.mjs` S9a FAIL。A・B・C をロード → A を解放 → A を再ロード で `hA2 = hC = 0x7ff6a0030000`、`byHandle=2 loaded=3` (B の handle が C に上書きされる)。S9b FAIL: 9 回の解放・再ロードのうち `clash=9` (全回で衝突)。
- **修正**: 採番を単調増加カウンタ `allocHandle()` (`++this.hseq`) に変更。修正後は S9a `hA2=0x7ff6a0040000 byHandle=3 loaded=3` PASS、S9b `clash=0` PASS。
- **ネガコン**: 採番を旧式 (`loaded.size` 基準) に戻す mutant `SizeHandle` → 2 FAIL (期待 FAIL)。ネガコン計 7/7 caught。
- **実測 (測定 commit `8d6fbf0e`。load average 0.01 / 0.11 / 0.07、4 CPU、並列 1)**:
  - `node tools/hostbridge/poc/test_shim.mjs`: rc=0、0.036 s。real 20 件 OK / FAIL 0、`[shim] ALL PASS`、ネガコン 7/7。
  - `node tools/hostbridge/poc/test_marshal.mjs`: rc=0、0.031 s。`checks 13 / broken 0` (`work/host_vst2.wasm` を `build_host.sh` で作ってから実行)。
  - `bash tools/hostbridge/hostbridge.sh`: [1] E1〜E20 OK の後、[2] `build_plugin_ott.sh` が `tools/m10/work/ott_m10.ll 無し` で rc=1 停止。**[2] build と [4] `run_poc` (28 checks) は未実施**。素材 `work-m6-ott` が未取得のため (m6/m8/m9/m10/ott の work が無い)。直前の正常実行は §5' (素材取得時、`[run_poc] checks 28 / broken 0`)。`run_poc` は handle の数値を assert しない (T5a は同一 module の refcount 比較) ので影響は想定されるが、未実測。→ [RT-15] で検証。
- **数え方**: real = 試験 S1〜S9 の check 行 (OK/FAIL) の件数。ネガコン = mutant 7 種のうち、対応 check が 1 件以上 FAIL した数 (期待 7/7)。
- **再計算**: `node tools/hostbridge/poc/test_shim.mjs` (OTT 非依存) と `node tools/hostbridge/poc/test_marshal.mjs`。

## 6'. 規約遵守メモ

- 書込は `tools/hostbridge/` のみ。`tools/m2,m6..m10` は読取 (Ghidra project は `work/` へコピー、`ott_m10.ll` も `work/` へコピー)。README/docs/・ルート package.json 無改変。
- 外部通信・認証系・Vital/Surge/Dexed は不使用。`work/` (471 MB: Ghidra project コピー/抽出 PE 等) は `.gitignore`、再生成は `analysis/reproduce.sh`。
- EULA: 事実整理のみ — 本成果物は **lift 済み wasm/PE 実体をコミットしない** (評価時にユーザ手元のインストーラから生成)。`evidence/` には FL 実バイナリの Ghidra decompile/disasm 抜粋 (~75 KB) を含む。VST2 SDK ヘッダ不使用 (ABI は binary 証拠から自作)。
