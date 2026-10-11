# REPORT — OTT-T4 (CAB-137): x64c lift の入口拡張 — VST entry 関数群の lift と native 実機械語との bit 突合

親チケット: CAB-7 (Done) / 関連: CAB-91 (HB-H2, host 結線側) / 対象外(別チケット): AVX/FMA CRT 経路 (CAB-135)、CRT 初期化 override 置換 (CAB-138)、AudioWorklet ABI (CAB-122 系)

## 0. 結論 (先出し)

- **判定: 要件を満たす。** `bash tools/ott/entry/entry_e2e.sh` = **PASS**。scenario matrix **85 本** (dispatcher op 網羅 **69 op 値** / getParameter×20 idx / getChunk・setChunk round-trip / program・文字列系 / processReplacing thunk / effClose) で **native 実機械語と全突合項目一致** (rax・xmm0・文字列 buffer・obj 0x328B 全 qword・HeapAlloc 配置・audioMaster 呼出回数)。FAIL 0。
  数え方 (再計算: `python3 tools/ott/accept/acc_scen_count.py`)。
  - **85 scenario** = `entry_scen.scen_list()` が生成する 86 エントリのうち runner / `cmp_entries` が dict キーで保持した**一意名**の数。`op12` を (op=12,val=1) と (op=12,val=0) の 2 本で使い、両者が同名のため 1 件に統合される。64 dispatcher op 値 (op* 名 64 個) + GUI 4 op (op13/14/15/19) + op1 (effClose) + op0 (full_cycle/close) = 全 69 op 値。
  - 実装報告時の「63 op」は根拠を辿れないため **訂正** (上記の定義で 69 op 値。nat_crash 0 のため 69 すべてが突合対象)。
- **lift 拡張**: lift 関数 75 → **207** (命令 5,790 → **13,690**)。入口 roots 41 関数を追加 (VSTPluginMain / createEffectInstance / dispatcher 両 switch / AEffect 静的 thunk 群 / getParameter・setParameter override / getChunk・setChunk / program・文字列系 / getAeffect / dtor / operator new・delete)。
  数え方 (再計算: `python3 tools/ott/accept/acc_lift_set.py`): 関数 = `work/entrylift/lift_meta.json` の `functions` 配列長 (override 対象は lift しないため除外)。命令 = `ninsn`。DSP 版 75/5,790 は `bash tools/ott/ott_e2e.sh` の `[x64c] functions 75, insns 5790`。
  ※ **コミット済み scenario 定義から再現した値**。実装報告時の 209/13,694 は、coverage の `getp_range` が idx 25..30 まで実行された状態 (uncommitted) で採られたもので、コミット済み `entry_scen.py` (`getp_range` = idx 0..19) では到達しない経路の +2 関数 / +4 命令を含む。詳細は検収 REPORT (tools/ott/ACCEPTANCE_CAB137_CAB138.md §3.1)。
- **既存 DSP e2e は継続 PASS**: `bash tools/ott/ott_e2e.sh` = 89 scenario / 50,236 cell **max_ulp 0 / state 差 0** (x64c.py・data_gen.py の改変後も再確認済)。
- **性能** (node 24.19, 256f×2000 block, tools/ott/diff/perf.mjs; 共有 16 コア・load average 2.1〜4.4 で 5 回実測の範囲): DSP 版 **203.1〜223.5 µs/blk** (実時間 **26.0〜28.6x**) → 入口拡張版 **202.8〜228.3 µs/blk** (**25.4〜28.6x**)。単発値 202.6 µs/blk (28.7x) は実測範囲内 (bit-exact build のまま)。
  数え方: µs/blk = 2000 block × 256 sample の計測区間 / block 数。実時間 x = 11.61 s 音声 / 実測秒数。負荷で振れるためレンジで記載 (規則 38)。再計算: `MOD=<cjs> REPEAT=7 node tools/ott/accept/acc_perf.mjs`。
- **新規入手の実測知見**: ① OTT の getParameter (vtbl+0x58) は SDK 署名 (index, float* value) と異なり **float を xmm0 で返す** (31 path 全て実測、float* は未書き) — hostbridge PoC が疑っていた「戻り xmm0」を確定。② dispatcher は op 0..24 を 0x180126c60、op 25..79 を 0x180127800 の 2 段 switch で処理 (vtbl[1]=0x180127800 → 既定を 0x180126c60 へ委譲)。③ getParamLabel は **byte permutation 表 + dword 表の 2 段 jump table** (image base 相対 data-in-code) で、data 敷設に新仕組みが必要だった (§3)。

## 1. 成果物 (tools/ott/entry/)

| パス | 役割 |
|---|---|
| `entry_e2e.sh` | 1 コマンド検収 (scen 生成 → native build → coverage → lift → matrix → 突合 → DSP e2e 継続確認)。`--quick` = coverage/lift 再利用 + matrix 縮小 |
| `entry_scen.py` | scenario 定義 (native / wasm 両ランナの唯一のソース)。85 scenario + buffer 配置 + 定数 || `entry_native.c` | native 参照ハーネス。`../native/ott_native.c` を **無改変 include** し audioMaster 実装 (MS x64 ABI) とカウンタだけ追加 |
| `am_host.h` | audioMaster 応答表の共有実装 (native / wasm で同一ソースを 2 コンパイル。LD/ST マクロで guest メモリ統一) |
| `rt_entry.c` | wasm 側 override body: `ovr_editor_null` (0x180120ff0) + `ovr_am_shim` (0x1802f8000 = audioMaster 仮想入口) |
| `entry_roots.py` | entries.json 生成 (DSP coverage + entry coverage + 入口 roots 41) |
| `lift_entry.sh` | lift → C → emcc (LIFT_OUT=work/entrylift, closure=3, override 6 件) |
| `entry_nat.py` | native scenario runner (fork 単位で crash 隔離 / alog replay / coverage 収集) |
| `entry_wasm.mjs` | wasm scenario runner (ott_run + stack args、entry_nat と同一 schema) |
| `run_matrix.py` | オーケストレーション: scenario 毎に node 起動 (instance 分離) → alog → native replay → 突合 |
| `cmp_entries.py` | 判定 + 関数別差分表生成 (fn_table.md / summary.json) |

生成物は `tools/ott/work/entrylift/` (gitignore)。**既存ファイルの改変は 2 件** (§3)。

## 2. 入口関数の突合結果 (native 実機械語 vs lift wasm)

### 2.1 突合対象と方式

- native: PE を 0x180000000 に敷設した実機械語を ms_abi trampoline で直接呼ぶ (tools/ott/native 方式の流用)。**wasm 側の HeapAlloc 列 (alog) を native 側に replay** して guest アドレスを完全一致させ、obj / heap / 文字列 / 戻り値を byte 比較する (tools/ott/diff/scen2_* と同じ規約)。
- wasm: x64c lift (ott_run)。整数引数 → R[RCX..R9]、float 引数 → X[xmm 位置]、5/6 引数 (dispatcher の ptr/opt) は `_ott_set_stackarg` で guest stack に置く。
- audioMaster: native は実 fn ポインタ、wasm は **trampoline VA (0x1802f8000, override=ovr_am_shim)** を渡す。`call rbx` は lift されると `ott_dispatch(t)` に落ちるため、trampoline を lift 集合に override で登録して解決する (CAB-91 の `ott_run→hb_icall` 接続と同型の仕組み)。応答ロジックは `am_host.h` 共有 → 呼出回数 (op 別 64 counter) まで一致を検証。
- 比較除外: ①obj+0x08 (audioMaster ポインタ: native=実アドレス / wasm=trampoline VA — 意味としては一致)、②void 関数の rax / xmm0 caller-saved 残値 (harness 差)、③image VA の RVA 正規化差 (native 0x180000000 基準 / wasm 0x30000000 基準)。

### 2.2 結果 (85 scenario 全 PASS)

| 系統 | scenario | 結果 |
|---|---|---|
| dispatcher op (0..79 のうち native 実測 OK の **69 op 値** + GUI 4 op) | op0..op79, op30, op60 | 全 PASS (op7・op10・op34 は §2.3) |
| VSTPluginMain → AEffect 生成 | 全 scenario の共通 prefix | AEffect 全欄 (magic / thunk RVA / numPrograms=1 / numParams=20 / numInputs=2 / numOutputs=2 / **flags=0x18** / initialDelay=2 / ioRatio=1.0f / uniqueID='XfTT' / version=1) 一致 |
| setParameter / getParameter 往復 (AEffect thunk 経由) | getp0..19, getp_range, setp_all | xmm0 返値 (f32 bit) 含め全一致 |
| 直接 virtual 呼出 | virt_sr / virt_bs / virt_prog / virt_plabel / virt_pname / virt_pdisplay / virt_setp_ovr / virt_aeffect / virt_misc | 全一致 |
| chunk round-trip | chunk_rt (op23/op24 × preset/bank) | 戻り 0 (base 既定)・CKPT 未書き込み、一致。OTT は **effFlagsProgramChunks 非搭載** (flags=0x18) ゆえ chunk 実体なし |
| 実処理 | full_cycle (effOpen → param×19 → effMainsChanged(1) → processReplacing(128f) thunk 経由 → suspend) | process 出力 1,024 bit 含め一致 |
| effClose | close (dtor → operator delete) | dtor 後 obj / heap 状態一致 |
| GUI (到達確認) | gui_ops (op13/14/15/19), editor_null | editor=NULL 経路で戻り 0、一致 |

関数別: **DSP closure 30 関数** (cov_all 実行命令を含む関数; 89 scenario matrix で bit 突合済) + **入口拡張で新規に突合できた 35 関数** = 計 65 関数が「native 照合済」(`work/entrylift/fn_table.md` に全行リスト)。※チケット記載の「47 実行関数」はRetDec 検証時の数え方 (lift 対象 75 / calltgt 45) で、本表は .pdata 関数単位の実測 (30) で再計上。

### 2.3 native 参照が取得できなかった経路 (到達確認のみ・理由)

| 経路 | native 実測 | 理由 |
|---|---|---|
| effGetParamDisplay (op7 / 0x18011e770) の float→文字列 path (param 0,1,2,3,5,6,7,8,9,10,16,17,18) | native が SIGSEGV | DLL 内 CRT の float format 経路が **CRT 未初期化** (DllMain 未実行) のまま `_invalid_parameter` → guard thunk `jmp rax` に garbage。整数系 formatter (param 4,11,12,13,14,15,19) は CRT を通らず native OK → こちらのみ突合済。CAB-138 (CRT 初期化) の領域 |
| effGetOutputProperties (op34) | 同上 | 同経路 (getParameter + float format) |
| getProgramName の "Init %d" format 経路の一部 | native OK / wasm も OK | — (参考: op5 は "Init 1" 生成まで含めて bit 一致) |

これらは **wasm 側も同じ命令列・同じ未初期化データを実行する**ため、native と同一の fail-fast に落ちる (挙動は一致)。比較対象から外したのみ。

### 2.4 対象外 (GUI / エディタ) — チケット要件の列挙

| 関数 | VA | 扱い |
|---|---|---|
| OTTEditor ctor | 0x180120ff0 | **override (ovr_editor_null)**: `xor eax,eax; ret` 相当で editor=NULL を返す。native 側は同一箇所を 3 byte 機械語 patch (`48 31 C0 C3`)。createEffectInstance が editor=NULL を obj+0x10 に保存し、以降の非 GUI 経路は全て editor NULL 前提で整合 |
| AEffEditor base ctor (VSTGUI 初期化) | 0x180128c00 | 上記により未到達 (GetTickCount / OleInitialize 等 GUI import 群が必要になるため対象外) |
| effEditGetRect / Open / Close / Idle (op 13/14/15/19) | editor vtbl 経由 | editor=NULL → 0 を返す経路のみ到達確認 + 戻り突合。ERect 実体・HWND は CAB-122 (GUI) 領域 |
| OTTVST の editor 通知 (setParameter override 内 editor->vtbl+0x58) | 0x180125bd0 内 | editor NULL で skip される経路として包含 (比較済) |

## 3. 既存ファイルの改変 (最小限・計 2 ファイル)

| ファイル | 改変 | 理由 (入口拡張で closure に入った経路) |
|---|---|---|
| `lift/x64c.py` | ① `strip_prefix()`: `bnd `/`lock ` prefix を base mnemonic に正規化 ② `i_xadd` 追加 ③ `lift()`: `lea reg,[rip→IMG]` (image base anchor) を持つ関数で、mem operand の disp が .text RVA に見える場合 textref 窓に追加 | ① CRT 文字列 path に MPX 付き `bnd jne/ret`、locale refcount に `lock inc/xadd` (単 thread では no-op prefix / xadd は同一意味) ② getParamLabel (0x18011e7b0) が **byte permutation 表 (0x11e80c) + dword 表 (0x11e800) の 2 段 jump table** を image base 相対 (data-in-code) で持ち、従来の jt 検出では byte 表が敷設されず param 5 以降の label が誤る (実測: param4 = ' ' が '%' に化ける) |
| `lift/data_gen.py` | textref 窓 96 → **256 byte** | 上記 2 段表 (19B) とその周辺を 1 窓で確実に覆う。窓は PE 実 byte の追送なので余分は無害 |

改変後も `tools/ott/ott_e2e.sh` 89 scenario / 50,236 cell max_ulp 0 を再確認 (§0)。

## 4. lift 実装メモ (入口拡張の仕組み)

- **entries.json** = DSP roots (4) + 入口 roots (41: §1 `entry_roots.py` 参照) + coverage calltgt (DSP 45 + entry 61 → 重複統合 106→118 RVA) + closure=3。
- **override 6 件**: CRT 数学 4 件 (既存) + `ovr_editor_null` (0x180120ff0) + `ovr_am_shim` (0x1802f8000)。trampoline VA は .reloc 後の image 末尾パディング (0x307c00、data_gen も jump table 窓も使用しない領域)。
- **未対応命令の残**: unsup 72 種 / 約 500 箇所 — すべて AVX/VEX 系 (CAB-135) と `rcr`・`int` (未実行経路)。実行されれば `ott_unsup` fail-fast。bnd/lock は §3 で解消済み。
- **未 lift callee 36** (closure 3 で打ち切り): 実行されれば `ott_unlifted` fail-fast。比較 matrix の 85 scenario では 1 つも到達しなかった (全 PASS が証拠)。

## 5. 未解決・制約

1. float formatter 系 (§2.3) は CAB-138 (CRT 初期化の実行/置換) まで native 参照不能。wasm は到達こそするが正解値の検証は未済。
2. AVX/FMA 経路 (unsup 72 種) は未 lift — CAB-135。入口の dispatcher 自体は SSE2 のみで完結 (全 scenario PASS)。
3. `ott_run` は caller-saved 残値 (xmm4-7 等) を保存しない。void 関数の残値比較は harness 差を出すため非比較にした (§2.1)。AudioWorklet ABI (CAB-122) で型付き export にするときは戻り型だけ定義すればよい。
4. 性能 28.7x (§0) は node 値。AudioWorklet 結線時の実効性能は CAB-122 で再計上。

## 6. ユーザ依頼事項

特に無し (素材・認証・外部通信は不要。使用した DLL は既存の `docs/REFERENCES.md` `[ANALYSIS-PLUGINS]` の `plugins/ott/binaries/OTT_vst2_win64.dll`)。

## 7. 再現

```sh
bash tools/ott/entry/entry_e2e.sh            # 全工程 (coverage 取得含む 約 8 分)
bash tools/ott/entry/entry_e2e.sh --quick    # coverage/lift 再利用 + matrix 縮小 (約 2 分)
# 個別
python3 tools/ott/entry/entry_scen.py work/entrylift/scen.json
gcc -O1 -g -fPIC -shared -o work/entrylift/libottnatentry.so tools/ott/entry/entry_native.c tools/ott/native/ms_call.S -Itools/ott/rt -Itools/ott/entry
python3 -u tools/ott/entry/entry_nat.py --out work/entrylift/nat_covraw.json --cov work/entrylift/cov_entry.json
bash tools/ott/entry/lift_entry.sh work/entrylift/cov_entry.json
python3 -u tools/ott/entry/run_matrix.py work/entrylift/ottl_entry.cjs work/entrylift/matrix
python3 -u tools/ott/entry/cmp_entries.py work/entrylift/matrix/nat_result.json work/entrylift/matrix/wasm_result.json \
  --cov work/entrylift/cov_entry.json --covdsp tools/ott/ref/cov_all.json --out work/entrylift/summary.json --table work/entrylift/fn_table.md
# 前提: tools/ott/ott_e2e.sh が PASS する環境 (python3 capstone/pefile, gcc, emsdk 6.0.12, node ≥22)
```
