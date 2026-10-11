# tools/icall/landing — Delphi unwind landing pad の抽出と lift (CAB-227)

## 0. 結論 (先出し)

- **判定: 達成**。FLEngine_x64.dll の非到達コード (例外 cleanup path) から landing pad を全数抽出し、
  **仮想 dtor pad 493 本を LLVM IR に 1:1 lift し、native 実機械語 vs lift IR の差分検証で 493/493 pad・
  1,479/1,479 case 全て一致 (100%)** を実測した。`bash tools/icall/landing/landing_e2e.sh` (約 27 秒, exit 0) で再現。
- 監査数 879 gap site の内訳を確定: **landing pad 由来 = 507 site** (仮想 dtor `call [rbx-0x20]` 493 + 他 vtable call 3 +
  rip-data call 1 + `jmp reg` 10) + **IAT import thunk 372** (landing pad ではなく、.pdata を持たない thunk 群の
  recursive descent 漏れ)。REPORT.md (CAB-89) の「879 site」はこの両方を含む数値だった。
- scope table 抽出器を新規実装: FLEngine 全 57,816 関数の .pdata → UNWIND_INFO を読み、handler を持つ
  **10,837 関数から Delphi scope table 16,940 entry を抽出 (range 妥当性 invalid = 0)**。
  Delphi x64 の handler data は **UNWIND_INFO に inline** (MSVC の .rdata 経由ではない) こと、
  entry kind (0=handler 領域 / 2=catch-all / >2=typed except) の意味を実バイトで確定した。
- IR は **wasm 実行可能な形 (liftdiff 計装パイプラインで emcc 通過)** と、統合用の HR 形
  (`@__lp_icall` / `@__lp_resume` フック付き) の 2 形で出力。メタデータ (VA / 属する try 範囲 / kind /
  フレーム slot / callee / live-in) を JSON + `; LP-META:` 行の両方に持つ。
- wasm 例外戦略の推奨: **初回統合は setjmp/longjmp 形 (pad を「関数として呼ぶ」方式)**。
  根拠: pad は「Rip 設定で進入・フレーム intact・引数なし」で入口が longjmp 回収先と同形であり、
  本検証がその呼出し規約で native と 100% 一致している (§6)。

## 1. 成果物 (tools/icall/landing/)

| パス | 役割 |
|---|---|
| `xdata_scope.py` | .pdata 全数走査 → UNWIND_INFO (version/flags/prolog/unwind codes/handler) + **Delphi scope table** (inline: count + 16B entries) + typed-except descriptor list (8B entries {classRVA, handlerRVA}) 抽出。CHAININFO は親へ解決 |
| `gap_fragments.py` | audit_icall.py (tools/icall, 読取専用再利用) の recursive descent + gap sweep を再実行し、879 site を含む gap block を**断片へ分割** (jmp/ret + padding 境界) して分類 (dtor_pad / import_thunk / dispatch_stub / relay_thunk / other_pad) |
| `lift_pad.py` | 断片 → LLVM IR 1:1 lifter。基本ブロック化 + 多前駆 block の入口で全 GPR **phi** 敷設、flags 疑似レジスタ (eq/ne/lt/…) も block 間伝播。部分レジスタ書込み (mov dl 等) の上位ビット保存、 movzx/movsx/ALU/cmov/setcc/SSE 移動 対応 |
| `verify_pads.py` | native vs wasm 差分検証 driver (FORMAT.md 準拠 JSONL 出力) |
| `rt/lp_native.c` + `rt/lp_call.S` | native ランナ (tools/liftdiff `ld_core.h` 共有)。**rbp = 親フレーム** で pad 実機械語を直接実行、PATCHSET (callee 短絡) + TRACESET (INT3 で (VA, rcx, rdx, r8, r9) 記録) |
| `ott_extract.py` | OTT (MSVC) の funclet 抽出 (検証母数 ③) |
| `landing_e2e.sh` | 1 コマンド再現 (約 27 秒) |
| `work/` (gitignore) | 生成物: `fle_{fragments,xdata,scopes,pads_verify.ll,pads_lib.ll,pads_meta}.json/ll`、`verify/{native,wasm}_cases.json, verdicts{,_fn}.jsonl, summary.json`、`ott_*` |

## 2. 抽出器仕様 (実バイトで確定した Delphi x64 EH 構造)

FLEEngine_x64.dll (.pdata 57,856 entry / UnwindData 無し 40): UNWIND_INFO は .xdata section を持たず
独立領域に置かれる。flags (byte0>>3): UHANDLER 8,021 / E|U 2,816 / CHAININFO **0** (OTT は 2,096) / E のみ 0。

言語別 handler は **全 10,837 関数が同一関数 (VA 0x4112c0, System の Delphi frame handler)**。
handler の逆汇编 (0x4112c0, 949B) から動作を 2 相に分離して確定した:

- **検索相** (ExceptionFlags==0): handler data (= DispatcherContext+0x38 が指す **UNWIND_INFO inline 領域**) を
  `count + count×{beginRVA, endRVA, kind, jumpTarget}` の scope table として読む。kind==2 (catch-all) で
  ControlPc が [begin,end) なら jumpTarget へ targeted unwind を起動。kind==0 は検索相ではスキップ。
  kind>2 は kind 値自体が **例外 descriptor list の RVA** (`count + count×{classVMT_RVA, handlerRVA}`,
  0 = catch-all) を意味し、例外クラス照合 (0x4111d0, VMT parent 鎖 + 名字比較) に使う。
- **unwind 相** (Flags & UNWINDING): kind==0/1 の範囲に例外アドレスが在れば
  `jumpTarget` を **`pad(&{ExceptionRecord, Context}, EstablisherFrame)` の 2 引数関数として CALL** する
  (0x411824/0x4118bc)。kind==2 は TARGET_UNWIND 時のみ jumpTarget へ分岐。
- **実測のレイアウト規則**: Delphi は try 本体直後 (nop 整列) に handler コードを置き、
  try 本体に `jmp` で飛び越えさせる。scope table は (1) kind=2 [try本体, 本体end) jt=本体end、
  (2) kind=0 [handler領域, handler領域end) jt=reraise thunk — の **2 entry 1 組** (493 組で確認)。
  reraise thunk = `sub rsp,0x28; call 0x411ef0(_Reraise); add rsp,0x28; ret` (14B) の共有複製。

## 3. 879 site の内訳 (dtor / finally / filter)

| 分類 | site | 説明 (実測) |
|---|--:|---|
| **仮想 dtor call** | **493** | `mov rbx,[rax]; call [rbx-0x20]` = VMT vmtDestroy (x64 Delphi)。493 pad とも同一 13 命令テンプレート: flag/NULL check → Destroy → FreeMem 系 (0x410340) → reraise (0x411ea0)。呼先は全 pad で 2 関数 + 間接 1 に統一 |
| 他の間接 call | 3 + 1 | `call [rbx+他]` 2 / `call [rax+0x10]` 1 / `call [rip+data]` 1 (0x524f96 の vtable 分岐) |
| `jmp reg` | 10 | Delphi except dispatch stub (`push rcx; lea rcx,[rip+data]; push r8; push r9; sub rsp,0x68; movapd xmm0-3; call 0x41cfc0; ...; jmp rax`) |
| `jmp [rip+IAT]` | 372 | import thunk (.pdata 無し thunk 群)。**landing pad ではない** — 監査の gap site 数からの差引を推奨 |
| 合計 | **879** | |

pad の属する scope (メタデータ): 493 pad 全てが **kind=2 (try 本体) + kind=0 (handler 領域) の組** に所属。
typed except (kind>2, filter 付き) は全体で 183 entry / 216 descriptor / 29 class VMT — この pad 集合には
含まれず (typed except の handler は到達可能コードとして配置される)。catch-all (kind=2) 2,722 / kind=0 14,035。

## 4. IR 化率

| 対象 | 断片 | lift 成功 | 割合 | 備考 |
|---|--:|--:|--:|---|
| **FLEngine gap 断片** | **879** | **879** | **100%** | dtor_pad 493 は実行検証済 (§5)。thunk 372 + dispatch 10 + relay 3 + other 1 は静的 lift |
| OTT (MSVC) funclet | 2,094 | 1,088 | 52.0% | 未達 = ループ含む (474, backedge phi の反復解決が未実装) + SSE 演算/lock/xchg 等 (532)。**抽出台帳と構造分析は 100%** (§7) |
| IR 検証 | — | llvm-as (LLVM 21) 通過 | — | pads_verify.ll 43,891 行 / pads_lib.ll 54,881 行 |

負の対照試験: pad 1 本の IR の obj slot offset を 80→88 に改変 → 当該 pad の verdict が `equal → diff`
(trace_arg 不一致 + trace_len 不一致) に変化し、他 pad は equal のまま (= 検証系は空振りでない)。

## 5. 実行検証 (native vs wasm, 100%)

方式: **pad を「rbp = 親フレームの関数」として両側で同一規約実行**し、(1) callee 呼出し列と引数
(INT3 trace vs IR 計装, ポインタは delta=0x10000000 正規化) (2) rax (3) arena 差分 を比較。

- native: 実機械語。callee 4 種 (0x410340, 0x411ea0=reraise, 0x416480=合成 VMT の固定 target) を
  `31 c0 c3` (xor eax,eax; ret) に entry patch → 両側で「記録のみ・戻り 0」に対称化。
  reraise のみ `58 31 c0 c3` (pop rax; xor eax,eax; ret) — pad の戻り番号を捨てて trampoline へ直接復帰
  (= wasm IR の call 後 ret と等価。pad 末尾の nop + エピローグ落下を両側でスキップ)。
- wasm: `pads_verify.ll` を tools/liftdiff `build_wasm.py` (entry 計装) → emcc → node ランナ
  (`ld_runner.mjs`, sig=`i64,i64,i64,i64,i64`)。IR の callee は `ret i64 0` スタブ定義。
- case: pad × 3 pattern (full: flag=1+obj≠0 / flag0 / obj0)。frame は arena blob
  (obj slot は FIX で arena base 加算 → 両側で同一オフセットの別実アドレス)。
- **結果: 493 pad × 3 = 1,479 case 全て equal** (native 1,479 ok / wasm 1,479 ok / verdict match 493/493)。
  full path の trace は `[0x416480(obj,0x81), 0x410340(obj,0x81), 0x411ea0(obj,0x81)]` で
  ポインタ引数 2,955 個が delta 正規化の上で一致。
- 実行時間: 1,479 case × 2 側 約 1.2 秒 (wasm ビルド約 25 秒は別)。

## 6. wasm 例外戦略への推奨 (判断材料)

**推奨: 初回統合は setjmp/longjmp 形 (pad = 回収先関数)。wasm EH (exnref) は後段最適化。**

1. **入口規約が一致**: Delphi pad は「OS が Rip を設定して進入、フレーム intact、引数なし」。
   これは `longjmp` の回収先と同形で、本検証はその規約で native と 100% 一合した。
   setjmp/longjmp 形なら lift 済み IR 片を**そのまま**呼べる (verify 形 `@function_<pad>(frame, ...)`)。
2. **wasm EH (try_table/exnref) の必要物**: 例外オブジェクトの identity (Delphi は 0xEEDFADE + obj ポインタ)、
   scope table を辿る検索/unwind 2 相の runtime (0x4112c0 の移植)、Rip 設定に相当する「任意 PC への resume」—
   wasm EH は unwind 先を try_table の catch 節に限定するため、pad 連鎖の再送出 (reraise) 毎に
   try_table を張る変換 (invoke/landingpad 形への全関数書換) が必要。CAB-226 の x64c 1:1 路線と相性が良いのは
   「関数呼出で pad を実行する」SjLj 形 (CFG を書換しない)。
3. **コスト観測**: dtor pad は 13 命令の uniform テンプレートで、pad 呼出し = 関数 1 呼出し分の
   オーバーヘッドのみ。Emscripten SjLj は setjmp 毎に状態保存するが、try 本体関数の入口 1 回で足りる
   (Delphi の scope table が既に「関数単位の try 構造」を持つため)。
4. **残る runtime 課題** (後段): (a) RaiseException 相当の大域脱出 (wasm は stack unwind を JS 側か
   SjLj で実装) (b) 0x41d110 の TLS getter (gs:[0x58]) — shim の偽 TEB で置換可 (liftdiff ld_core が実装済)
   (c) 例外オブジェクトの種別照合 (VMT parent 鎖) は lift IR で動く (0x4111d0 相当の移植)。

## 7. OTT (MSVC) 抽出 — 検証母数 ③

| 項目 | 実測 |
|---|---|
| .pdata | 7,680 entry (flags: UHANDLER 1,049 / E\|U 656 / **CHAININFO 2,096** / E のみ 17) |
| funclet (landing pad 候補) | **2,096 全てが CHAININFO で親を指す独立 .pdata entry**。2,093 は親の後ろ、3 は前 (cold) |
| 構造の対比 | **MSVC = pad は別 entry (funclet)** / **Delphi = pad は親範囲内の非到達コード (scope table 管理)** — 同一「landing pad lift」課題の 2 形態 |
| handler 分布 | 0x1801a2928 ×1,207 (__CxxFrameHandler 系) / 0x1801a0530 ×264 / 0x1801a05ac ×178 / 0x1801a3d1c ×71 |
| 断片化 + 静的 lift | 2,094 断片 → **1,088 lift (52.0%)**。未達: ループ 474 (backedge phi 反復解決 未実装) + SSE 演算/lock/xchg 等 532 |
| 実行検証 | 未実施 (MSVC funclet ABI と C++ EH オブジェクトの整形が別途必要 — 次タスク §9-3) |

## 8. CAB-226/228 への統合手順

1. **成果物の受け口**: `work/pads_lib.ll` (879 断片, HR 形) + `work/pads_meta.json`
   (pad VA ↔ kind ↔ 属する try 範囲 ↔ scope entry ↔ callee ↔ live-in ↔ フレーム slot)。
   断片の機械語は `work/fle_fragments.json` の `bytes`。
2. **x64c ルート (CAB-226)**: ①パレント関数の lift 時に recursive descent へ「scope table の
   kind-0 範囲 (pad 領域) を追加の basic block 群として取り込む」処理を足す (断片一覧で可能)。
   ②pad 本体は本成果物の IR/C をそのまま貼る (1:1 対応)。
   ③pad 内の間接 call `call [rbx-0x20]` は dispatch 表 (VA→関数) で解決 — icall 路線の
   `__icall_dispatch` と同じ経路が使える。
3. **例外 runtime (CAB-228)**: §6 の setjmp/longjmp 形 — `@__lp_icall(target, rcx, rdx, r8, r9)` を
   dispatch 呼出しに、`@__lp_resume(va)` を「親 CFG の当該 VA への合流」に接続。
   Delphi frame handler 相当 (scope table walk) を runtime C で移植し、pad 進入を longjmp で行う。
4. **回帰判定**: 本検証の `verify/{verdicts,verdicts_fn}.jsonl` (FORMAT.md §3) をベースラインに、
   CAB-226/228 の統合後 IR を同 driver で再実行して match 率を比較する。

## 9. 未解決と次タスク提案

- (未解決) OTT funclet の静的 lift 52% — ループ backedge の phi 反復解決 (474 断片) と
  SSE 演算命令 (532) が未実装。lift_pad.py は形式を追加するだけで伸びる。
- (未解決) OTT funclet の実行検証 — MSVC funclet ABI (catch funclet の引数, C++ EH オブジェクト) の整形。
- (未解決) Delphi 例外オブジェクトの生成/照合経路 (0x4111d0, 0x40f530) の lift 検証 — pad 単体検証では
  スタブ化したため、RaiseException → pad 進入までの通し実行は未達。
- 次タスク案:
  1. **[ICALL-2b] x64c への pad 統合 (CAB-226 への PR)** — §8-2 の 3 工程 + 回帰 (match 493/493 維持)。
  2. **[ICALL-2c] Delphi frame handler の runtime 移植 + setjmp/longjmp 統合 (CAB-228)** — §6/§8-3。
     検収: 例外を投げる unit 初期化関数 1 本の native vs wasm 通し一致。
  3. **OTT funclet の実行検証** — MSVC funclet ABI 整形 + `__CxxFrameHandler` スタブ、母数 +2,094。
  4. **lift_pad.py のループ対応** — backedge phi 反復解決で OTT +474 断片 (静的)。
- ユーザ依頼事項: なし (素材は `docs/REFERENCES.md` `[WIN64]` / `[MAC]` / `[DOWNLOAD]` の既設抽出物を使用)。

## 10. 再現

```sh
bash tools/icall/landing/landing_e2e.sh          # 約 27 秒, exit 0 = PASS (①〜④全検証 + OTT 抽出)
python3 tools/icall/landing/verify_pads.py --pe <FLEngine PE> \
  --fragments work/fle_fragments.json --meta work/pads_meta.json \
  --ir work/pads_verify.ll --out work/verify --max 20   # 検証のみ (サンプル)
前提: python3 (pefile, capstone), emsdk 6.0.12, node, /usr/bin/llvm-as
```
