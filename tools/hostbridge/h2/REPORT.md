# REPORT — HB-H2 (CAB-91): hostbridge surrogate — lift 済み VST entry の hostbridge 駆動と ott_run→hb_icall 接続

親チケット: CAB-23 / 土台: CAB-90 (lowbase, Done), CAB-137 (tools/ott/entry, 本コミット) / 関連: CAB-45 (Fruity Wrapper 結線, 下流)

## 0. 結論 (先出し)

- **判定: 要件を満たす。** `bash tools/hostbridge/h2/h2_e2e.sh` = **PASS**。
  surrogate ハーネス (mini VST2 host wasm ⇄ HostBridge ⇄ lowbase module) で **lift 済み VSTPluginMain を起動し、
  実 AEffect 構造を bridge 経由で駆動** — 15 checks 全 PASS。native 実機械語との値突合を含む。
- **native 突合 (junk 0 / 0 bit 差)**: bridge 経由 processReplacing 128f = **256/256 cell bit 一致** (native 実機械語参照、junk 0)。
  getParameter 20 値 (xmm0 返値) / effGetParamName 20 件 / effGetParamLabel 20 件 / effect・vendor・product 文字列 /
  vendorVersion も全て native と一致。**旧 PoC の「lift wasm 同士の junk 同士比較」を native 参照比較に置換済み**。
- **round-trip 検証**: setParameter→getParameter 往復 6 値 × 2 param (f32 bit exact)、effGetChunk/effSetChunk 往復
  (OTT は effFlagsProgramChunks 非搭載 → base 既定の 0 返し、native と一致)、effClose→再ロード。
- **lowbase 併用**: module は **LB_BASE=0x10000 / initial 16 MiB / max 64 MiB** で敷設 (CAB-90 の方式そのまま)。
  更に **OTT(h2 module)×2 + Balance kernel (別 DLL・別 lift 系統)** の同時ロードを流用構成で実施 —
  500blk×128f 交互駆動 4/4 checks PASS (sha256 全 module 一致 / Balance は native 機械語と 768/768 cell 一致 /
  linear memory 合計 36 MiB)。
- **性能** (node, bridge 経由 processReplacing 128f): **83.3 µs/call** = 128f RT 予算 (2902 µs) の **2.9%**。
  guest 直 (ott_run 直接) は tools/ott/entry 版で 202.6 µs/256f — bridge marshal 差は PoC (CAB-89/90 時点) と同規模で RT 予算内。
- **旧 surrogate (poc/plugin_ott_entry.c) の役割置換完了**: AEffect の関数ポインタは lift 済み ctor が書いた
  **実 guest VA** になり、host からの全呼出が `hb_icall → ott_run` で lift 済み機械語に落ちる
  (surrogate の shadow params / opcode switch は撤去)。差し替え点は `hb_icall` 1 箇所 (§2 が確定版手順)。
- **副次知見 (実 lift による訂正)**: 実機械語の effGetParamName(0) = **"Bypass"** — 旧 surrogate の名前表
  (先頭 "Depth") は誤りだった。実コードが正 (native 参照と一致)。OTTVST::setParameter は editor 通知を
  editor!=NULL 時のみ行い、editor NULL surrogate では skip される (CAB-137 REPORT §2.4)。

## 1. 成果物 (tools/hostbridge/h2/)

| パス | 役割 |
|---|---|
| `h2_e2e.sh` | 1 コマンド検収 (module build → native 参照取得 → harness → lowbase 既存 e2e 継続確認) |
| `build_h2_lb.sh` | lowbase (LB_BASE=0x10000) x64c **入口拡張版** module のビルド。tools/ott/entry の coverage/entries を再利用し `lb_x64c.py --base 0x10000` で V-shift (既存ファイルは読取のみ) |
| `vst_module_entry.c` | module 側 glue: `hb_plugin_init / hb_scratch / VSTPluginMain / hb_icall` = **ott_run 接続の本体** (§2) |
| `hb_rt_entry.c` | override body: `ovr_editor_null` (GUI 対象外 surrogate) + `ovr_am_shim_hb` (audioMaster 仮想入口 → import hb_host_call) |
| `h2_scen.py` | native 参照 scenario 集 (entry_scen.py の語彙で host.load 相当の呼出列 `h2_full` を追加 + 既存 scenario 流用) |
| `surrogate_harness.mjs` | HostBridge + host_vst2.wasm による駆動と検証 (15 checks)。native 参照値との突合を含む |
| work/ (gitignore) | ott_h2.cjs / host_vst2.wasm / natref.json / h2_result.json |

読み取りのみで使用した既存資産: `tools/ott/lift/x64c.py`, `tools/ott/rt/*`, `tools/ott/entry/*` (coverage・runner),
`tools/hostbridge/lowbase/{lb_layout.py, x64c/lb_x64c.py, x64c/lb_data_gen.py, multi/multi_load.mjs}`,
`tools/hostbridge/poc/{hb_bridge.mjs, hb_lib.js, host_vst2.c, vst2_abi.h}`。**改変 0 行**。

## 2. ott_run → hb_icall 接続手順 (確定版 — CAB-90 検収コメントの下書きを更新)

低メモリ lift module を hostbridge の plugin 契約 (`hb_plugin_init / hb_scratch / VSTPluginMain / hb_icall` +
import `hb_host_call`) に載せる手順。**旧 surrogate の plugin ロジック再現は不要**で、glue は ABI 変換だけ。

1. **lift**: tools/ott/entry の coverage/entries (入口拡張済) を `lowbase/x64c/lb_x64c.py --base 0x10000` に渡して
   V-shift lift する。override 6 件 (CRT 数学 4 + `ovr_editor_null`@0x180120ff0 + `ovr_am_shim_hb`@0x1802f8000)。
   trampoline VA は image 末尾パディング (.reloc 後 0x307c00) を使う — data 敷設と衝突しない。
2. **data 敷設**: `lb_data_gen.py DLL out.c meta 0x10000` (DIR64 13,000 件を LB_BASE 基準に補正)。
   `hb_plugin_init()` で `ott_data_install()` + arena zero 初期化。
3. **VSTPluginMain export** (host → plugin entry):
   ```c
   uint64_t VSTPluginMain(uint64_t audioMasterSlot) {   // bridge は token を渡すが使わない (upcall は別経路)
     hb_plugin_init();
     return ott_run(LB_BASE + 0x128ba0 /* VSTPluginMain RVA */, LB_BASE + 0x2f8000 /* audioMaster 仮想入口 */, 0,0,0, 0,0,0,0);
   }
   ```
   lift 済み VSTPluginMain は audioMaster を `call rbx` で呼ぶ → lift されると `ott_dispatch(token)` に落ちる。
   token には **lift 集合に override で登録した仮想入口 VA (LB_BASE+0x2f8000)** を渡す。override body が
   MS x64 ABI の引数置き場 (R[RCX..R9] + stack [RSP+0x28]/[RSP+0x30]) から読んで `hb_host_call(eff, op, idx,
   vlo, vhi, ptr, opt)` (emscripten import → hb_lib.js → bridge.upcall) に転送する。eff は lift 側が渡す値をそのまま
   使う (entry 中は NULL → bridge は entryCtx で解決、以後は guest AEffect* → byPe で解決)。
4. **hb_icall export** (host → plugin の全間接呼出の受け口)。AEffect の関数ポインタ欄には lift 済み ctor が書いた
   **実 guest VA (LB_BASE+RVA)** が入るので、fn 下位 32bit を RVA として VST2 署名に従って ott_run へ振り分ける:
   ```c
   uint64_t hb_icall(uint64_t fn, uint64_t a0..a5) {
     switch ((uint32_t)(fn - LB_BASE)) {
     case 0x126c00: /* dispatcher (eff,op,idx,val,ptr,opt) — 5/6 引数は stack */
       ott_set_stackarg(0, a4); ott_set_stackarg(1, a5);
       return ott_run(fn, a0, a1, a2, a3, 0,0,0,0);
     case 0x127520: /* setParameter — float(第3位置) → xmm2 */
       return ott_run(fn, a0, a1, 0, 0, 0,0, a2 & 0xffffffff, 0);
     case 0x1271a0: /* getParameter — **OTT は float を xmm0 で返す** (CAB-137 実測) → rax に載せ替え */
       ott_run(fn, a0, a1, a2, 0, 0,0,0,0); return ott_xmm0();
     case 0x127450: case 0x127430: case 0x127440: /* processReplacing/process/processDouble */
       return ott_run(fn, a0, a1, a2, a3, 0,0,0,0);
     default:       /* その他: dispatcher と同形で汎用転送 */
       ott_set_stackarg(0, a4); ott_set_stackarg(1, a5);
       return ott_run(fn, a0, a1, a2, a3, 0,0,0,0);
     }
   }
   ```
   実装: `vst_module_entry.c`。float 引数は ott_run の x0..x3 (XMM0-3 低 64bit)、5/6 引数は `_ott_set_stackarg`
   (guest stack の MS ABI 5/6 引数位置) へ載せる規約は tools/ott/diff/api.mjs と同一。
5. **ARENA**: `hb_scratch()` は `lb_layout.py` の `LB_ARENA` (build 時 `-DLB_ARENA_ADDR`) を返す
   (bridge marshal scratch 1 MiB)。guest heap (emscripten malloc) は GLOBAL_BASE 以降で衝突しない。
6. **host 側**: `poc/host_vst2.c` (無改造) を freestanding wasm32 でビルドし、`bridge.imports()` で instance 化。
   host_load_plugin の `(host_vst2 内の) audioMaster 関数テーブル index` が bridge の entryCtx/upcall の照合鍵
   になる (`__indirect_function_table` から実測で取得)。

## 3. 実測 (surrogate_harness 15 checks + multi_load 4 checks)

| 検査 | 結果 |
|---|---|
| G1 ロード (LoadLibraryW→GetProcAddress→VSTPluginMain→AEffect) | magic 'VstP' / numPrograms=1 / numParams=20 / numInputs=2 / numOutputs=2 / uniqueID='XfTT' / version=1 / **flags=0x18** — 全て lift 済み ctor が書いた実値。upcall (audioMasterVersion) が host に届く |
| G2 getParameter ×20 (ctor 既定) | **native 実機械語の xmm0 返値と 20/20 bit 一致** (bridge 経由) |
| G3 setParameter→getParameter 往復 | 6 値 × 2 param、f32 bit exact |
| G4 effGetParamName ×20 (op8, outstr marshal) | native (実機械語) と 20/20 一致 (**p0="Bypass"** — 旧 surrogate の名前表は誤り) |
| G5 effGetParamLabel ×20 (op6, 2 段 jump table) | native と 20/20 一致 |
| G6 effGetParamDisplay (整数系 7 param) | 文字列返りを確認 (float 系は CRT 未初期化で native 参照不能 = CAB-138 領域) |
| G7 effGetChunk/effSetChunk round-trip | set=0 / get=0 (base 既定) — native と一致。OTT は ProgramChunks 非搭載 (flags=0x18) |
| G8 processReplacing 128f | **256/256 cell が native 実機械語と bit 一致** (junk 0, nonzero 126) |
| G9 OTT×2 instance 交互 128f | 出力 diff 0/1024 (module 共有・状態漏れ無し) |
| G10 effClose → 再ロード | 正常 (dtor→operator delete→再 ctor) |
| 性能 | bridge 経由 128f = **83.3 µs/call** (RT 予算 2902 µs の 2.9%) |
| multi_load 流用 (OTT(h2)×2 + Balance kernel) | 4/4 PASS — 500blk×128f 交互 sha256 全 module 一致 / Balance は native 機械語と 768/768 cell 一致 / linear 16+16+4 MiB |

## 4. 関数別 差分表 (native 照合済 / 未済 / 理由)

`tools/ott/entry/fn_table.md` (CAB-137 産物) の全行が本構成でも同一の lift 集合を共有する:
**DSP closure 30 関数** (89 scenario matrix bit-exact) + **入口拡張 35 関数** (entry matrix 85 scenario 突合済) = 65 関数
「native 照合済」。本チケットではさらにそのうち bridge 経由で再突合した面が §3 の G1〜G8。
**未済**は以下の 2 系統 (理由付き):

| 経路 | 状態 | 理由 |
|---|---|---|
| effGetParamDisplay の float format 系 (param 0,1,2,3,5..10,16..18) / effGetOutputProperties (op34) | 到達確認のみ (native 参照不能) | DLL 内 CRT float formatter が CRT 未初期化で native も wasm も同一 fail-fast に落ちる。CAB-138 (CRT 初期化) の領域 |
| AVX/FMA CRT 経路 (unsup 72 種) / 未 lift callee 36 | 未 lift (実行時 fail-fast) | CAB-135 領域 + closure 3 で打切り。比較した 85 scenario・15 checks では未到達 |

## 5. 未解決・ブロッカー

1. **host 側は PoC host_vst2.wasm のまま** (FL/Fruity Wrapper 本体の lift は CAB-45/H4)。host_vst2.c は
   audioMaster 戻りを i32 で受ける bridge 仕様 (`upcall` が `Number(BigInt.asIntN(32, r))`) — VstIntPtr=i64 の
   戻り上位 32bit は未伝搬 (現行の応答は全て i32 域)。FL 結線時に bridge 側の拡幅要確認。
2. **同時ロードの Balance 構成は「流用検証」** — multi_load.mjs (lowbase 資産) を読み取り専用で実行したのみ。
   h2 module を恒久的な multi_load 対象にするなら alias 登録の自動化が残る (表に 1 行足すだけ)。
3. **editor NULL surrogate** — GUI (effEdit*) は op13/14/15/19 の戻り 0 経路のみ。manifest UI (CAB-122/G1) は別チケット。
4. 効果音: なし (ヘッドレス)。

## 6. ユーザ依頼事項

特に無し。

## 7. 再現

```sh
bash tools/hostbridge/h2/h2_e2e.sh                    # 全工程 (約 3 分; lowbase 既存 e2e の再確認を含む)
# 個別
bash tools/hostbridge/h2/build_h2_lb.sh               # module + host ビルド
python3 tools/hostbridge/h2/h2_scen.py tools/hostbridge/h2/work/scen.json
python3 -u tools/ott/entry/entry_nat.py --out tools/hostbridge/h2/work/natref.json --scen tools/hostbridge/h2/work/scen.json --only h2_full --only getp_range --only op45 --only op47 --only op48 --only op49 --only op35 --only op8 --only chunk_rt --only virt_plabel --only virt_pname
node tools/hostbridge/h2/surrogate_harness.mjs        # 15 checks
# 同時ロード (OTT×2 + Balance, lowbase 資産を流用)
node tools/hostbridge/lowbase/multi/multi_load.mjs --ott $PWD/tools/hostbridge/h2/work/ott_h2.cjs --bal $PWD/tools/hostbridge/lowbase/work/bal_lb/bal_hb.cjs --nmod 2 --label h2
# 前提: bash tools/ott/entry/entry_e2e.sh 済みの coverage (tools/ott/work/entrylift/cov_entry.json), emsdk, node ≥22
```

## 8. Actions (CI runner) 上での再現 (#92 再実行, 検証起点 main 0a9e9d3)

`oc_artifacts: plugins-ott toolchain-retdec toolchain-emsdk work-m6-ott work-liftlib analysis-ott-binaries` で
`ANALYSIS_DIR=$HOME/analysis` とし、h2_e2e.sh の [1/4]〜[3/4] を実行 (runner: 4 vCPU, node v22.23.3, load average 0.1〜0.7)。

- 修正 1: `build_h2_lb.sh` の DLL パス `/home/ubuntu/...` 固定を `tools/shared/env.sh` の `$PLUGINS_DIR` 経由へ (lowbase #365 と同方式)。
- 修正 2: `surrogate_harness.mjs` G8 の native 参照読込が `Buffer.from(hex).buffer` (Node の Buffer pool 共有 ArrayBuffer,
  byteOffset=8) を byteOffset 無視で `Uint32Array` 化していたため、Node 22 で native 参照が 8 byte ずれ **1/256 cell** の偽 FAIL になっていた
  (ずれた値: 先頭 cell が 0x30350025 等)。byteOffset を考慮して slice するよう修正し **256/256 cell 一致** に復帰。
  native 参照自体は 3 回再実行で sha256 先頭 12 桁が同一 (4bea16a22553) = 決定的。
- 実測 (コミット前の同一ソース内容): build_h2_lb.sh 6.3 s / harness 15 checks 全 PASS・broken 0 / bridge 経由 128f = 123.6 µs/call。
  同一 runner での `m10_e2e.sh` PASS (checks 7 / broken 0, 4.1 s)、`hostbridge.sh` ALL PASS (run_poc checks 28 / broken 0, 7.6 s)。
- ネガティブコントロール: natref の 1 bit (byte 40) を反転 → G8 = 255/256 cells で FAIL (checks 15 / broken 1)。
- 事前準備 (gitignore 済み `work/`): `tools/m8/work`・`tools/m9/work` を mkdir しないと `m10_build.sh` が FileNotFound で落ちる。
  python 依存 `pefile capstone numpy` は runner に無く pip install が必要。

| 未達 | 理由 | 起票先 |
|---|---|---|
**#92 再々実行 (fl-win64 付き, 検証 HEAD 6e5c8dac)**: 未達だった `h2_e2e.sh` [4/4] と Balance 同時ロードを解消。

- 素材: `oc_artifacts: fl-win64 plugins-ott toolchain-retdec toolchain-emsdk work-m6-ott work-liftlib analysis-ott-binaries`。
  `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (展開先そのもの)、`ANALYSIS_DIR=$HOME/analysis`、`PLUGINS_DIR=$HOME/analysis/plugins`。
- 前提の生成 (gitignore): `hostbridge.sh` / `m10_e2e.sh` / `t0_balance/t0_e2e.sh` / `ott/native/build.sh` を順に実行 (全 RC=0)。
- `bash tools/hostbridge/h2/h2_e2e.sh` = **PASS** (約 39 s, load 0.5〜0.6)。surrogate 15 checks / broken 0、lowbase_e2e ALL PASS。
- 同時ロード (multi_load): `multi_load lb` **4/4 PASS** (broken 0)、`multi_load 再配置前` 3/3 PASS、E3 PASS。
- runner 固有: `pefile capstone numpy` を `pip install --user` し、`wasm-objdump` (wabt) を apt 導入 (lowbase_e2e の名前空間チェックに必要)。
