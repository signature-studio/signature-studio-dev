# liftdiff フォーマット仕様 (v1)

`tools/liftdiff` が入出力する形式。`tools/icall` (間接 call 復元 pass) と `tools/liftlib` (共通 pass 統合) など他の担当が、
同じ JSON を **生成/消費** できるように定義する。キーはすべて小文字スネークケース。数値は `"0x..."` の 16 進文字列
(u64 が JS の double に収まらないため)、例外は件数など明記したもののみ。

## 1. target 記述 (`targets/<name>.json`)

lift 成果物と実機械語の対応を宣言する。`liftdiff.py build|run|batch` はこれだけを入力にする。

| キー | 意味 |
|---|---|
| `name` | target 名 (work/<name>/ 以下に生成物) |
| `pe` | 実 PE (x64) の絶対パス。native 側は **ImageBase に mmap** して機械語をそのまま実行 |
| `ir` | lift した LLVM IR (.ll)。`define @function_<VA16進>(...)` を関数単位の検証対象とする (`fn_prefix` で変更可) |
| `image` | wasm メモリに載せる生イメージ (offset 0 = RVA 0、reloc 補正済)。`null` なら `init_exports` が敷設 |
| `wasm_origin` | wasm アドレス空間での RVA 0 の位置 (m11 = `0x0`, OTT 旧 chain = `0x30000000`) |
| `extra_sources` | IR と一緒にリンクする C (SIMD helper、手書き stub 等)。ここで定義される名前は自動 stub から除外 |
| `simd` | `__asm_*` helper 生成コマンド (`{ir}` を置換) と include dir |
| `init_exports` | wasm 起動直後に呼ぶ export (データ敷設等) |
| `init_table_rva` | (任意) Delphi InitTable の RVA。`bootstate` が unit 初期化を native で実行する |

**アドレス規約**: native の ImageBase と wasm の RVA 0 のずれを `delta = ImageBase - wasm_origin` とする。
arena/heap も同じ `delta` だけ native 側へずらして mmap するため、**ポインタ値は native = wasm + delta** で常に対応する
(比較器はこれを許容する。スタック上のポインタは「スタック同士」として同一視)。

## 2. ランナ プロトコル (1 行テキスト、native/wasm 共通)

stdin に 1 行 1 コマンド、stdout に 1 case 1 行の JSON。

```
LAYOUT <delta> <arena_w> <arena_size> <heap_w> <heap_size>   # native のみ (hex)。wasm 側の静的アドレスを +delta で mmap
WR <rva> <len>                       # 差分比較する書込可能範囲 (.data/.bss 等; .idata は除外)
BLOB <name> <hex> / FIX <name> <off,off,...>   # arena 初期内容。FIX の qword には arena base を加算 (ptr-rich random)
SNAPSHOT                              # 現在の image/arena/heap を pristine とする -> {"ready":true}
TRACESET <va,va,...>                  # native: これらの関数 entry に INT3 を仕込む (wasm は IR 計装済)
SIMG <rva> <hex> / SHEAP <hex> / SMODEL <used> <hw> / SSNAP   # boot 状態の移送 (pointer は送信側が rebase)
STATE                                 # 現在状態の image 差分 + heap を JSON で返す
PEEK <i:rva|a:off|h:off|addr> <n>     # デバッグ用メモリ読出し (hex)
CASE id=.. fn=<va hex> blob=<name|-> args=<k>:<v>,... [trace=1] [xfill=1] [stkfill=<hex byte>] [keep=1] [p=<region>:<off>:<hex>;...] [sig=.. rt=..]
```

- `args`: 位置引数。`k` = `i`(整数/ポインタ) `d`(f64 bits) `f`(f32 bits)。値は `0x..` / `a:0x<off>`(arena) / `h:0x<off>`(heap) / `i:0x<rva>`(image)。
  Win64 ABI: 位置 0..3 → `rcx,rdx,r8,r9` (整数) または `xmm0..3` (浮動小数)、位置 4.. → スタック (`[rsp+0x28+8*(i-4)]`)。
  **Delphi x64 の register 規約は Win64 ABI と同一** (rcx,rdx,r8,r9。Self が第 1 引数)。32bit Delphi の `eax,edx,ecx` は x64 PE には無く、
  この環境の native ランナ (x86-64 のみ、`-m32` 不可) では実行できない — 仕様上は `abi=delphi32` を予約 (eax,edx,ecx → 位置 0,1,2)、未実装。
- `xfill=1`: native 側で、wasm 署名に無い位置のレジスタ (整数位置の `xmm_i`、fp 位置の `gpr_i`) にも決定値を入れる (引数脱落の検出用)。
- `keep=1`: 復元せず状態を引継いで連続実行 (unit 初期化の順次実行用)。
- `sig`/`rt`: wasm ランナ専用 (IR 署名: `i64,ptr,double,...` / 戻り型)。native は無視。
- 外部 import (IAT) は両側とも `ld_core.h` の同一応答モデルで応答 (VirtualAlloc/HeapAlloc は bump allocator、他は 0)。呼出しは `calls` に記録。

### 2.1 case 結果 (ランナ → 1 行 JSON)

```json
{"id":"4133f0:p01","fn":"0x4133f0","status":"ok",
 "rax":"0x..","rdx":"0x..","x0":"0x..","x1":"0x..",
 "calls":[{"n":"GetLocaleInfoW","a":["0x0","0x100b","0x..","0x100"],"r":"0x0"}],
 "trace":[["0x4133f0",2,"<a0>",...,"<a7>","<x0>","<x1>","<x2>","<x3>"]],   // [va, nparams(wasm 署名のみ有効), a0..a7, x0..x3]
 "mem":[{"r":"image|arena|heap","o":"0x<8B 整列 offset>","b":"<pre 16hex>","a":"<post 16hex>"}],
 "mem_blocks":N, "mem_trunc":0, "heap_used":N, "rtype":"i64"}
```

native の case 結果には呼出し所要 `ms` (ld_ms_call 前後の CLOCK_MONOTONIC、ミリ秒) が入る (wasm 側には無い)。
`status` — native: `ok|segv|bus|sigill|sigfpe|timeout|abort|bad_fn`(+`fault:{addr,rip}`)、wasm: `ok|trap|timeout|no_export`(+`detail` = trap 種別 + wasm スタック先頭)。
`mem` は pristine との差分を 8 バイトブロックで列挙 (`b`=呼出し前, `a`=呼出し後, little-endian hex)。

## 3. 差分レポート (関数単位、JSONL 1 行 = 1 関数) — **共有フォーマット**

`liftdiff.py run --json` / `batch --out` が出力。他 subagent は同じキーで書けば `summary` がそのまま集計できる。

```json
{"liftdiff_version":1,"target":"m11",
 "function":{"va":"0x4133f0","name":"function_4133f0","sig":{"ret":"i64","params":["i64","i64"],"defined":true}},
 "verdict":"match|mismatch|unexec",
 "unexec_reason":"native_fault_all_patterns|native_null_deref_all_patterns|native_timeout|native_sigill|hang|wasm_timeout_native_long|unsupported_sig|no_wasm_definition",
 "tags":[{"tag":"load_dropped","confidence":"high|medium|low","evidence":"..."}],
 "cases":[{"id":"4133f0:p01","pattern":"p01","outcome":"equal|diff|wasm_trap|wasm_timeout_native_long|native_fault|both_fault|hang",
           "native_status":"ok","wasm_status":"ok",
           "diffs":{"ret":{...},"mem":{"count":1,"first":[{"r":"arena","o":"0x..","native":"0x..","wasm":"0x.."}]},
                    "calls":{"kind":"call_arg|call_name|native_extra_call|wasm_extra_call","index":0,...},
                    "trace":{"kind":"entry_arg|entry_va|native_extra_entry|wasm_extra_entry","index":1,"va":"0x..","pos":0,"native":"0x..","wasm":"0x.."}},
           "wasm_uninit_dependent":false,"leaf":true,"raw":{...}}],
 "static":{"machine":{"ins":..,"icall":..,"ijmp":..,"fpcmp":..,"arity_gpr":..,"arity_x":..,"stack_args":[..],"repstr":..},
           "ir":{"icalls":..,"fcmp":..,"asm_calls":..,"allocas":..,"regslot_deref":..}}}
```

- **verdict**: `match` = native が完走した case が 1 つ以上あり、完走した全 case で一致 (戻り値 / 書換えメモリ / import 呼出し列 / 関数 entry 列)。
  `mismatch` = 完走 case のどれかで差分、または native 完走 / wasm trap。`unexec` = native が完走する case が無い (比較不能)。
- **outcome**: `wasm_timeout_native_long`(wasm が `wasm_timeout_ms` で打切られ、かつ native 自身の実行 `ms` × `wasm_slowdown_bound` ≥ `wasm_timeout_ms`
  = wasm が正常でも間に合わない長時間 case。欠陥ではなく比較不能: verdict は `unexec` 側、`unexec_reason` = 同名。target JSON の任意キー `wasm_timeout_ms` (既定 1000)・`wasm_slowdown_bound` (既定 20) で調整)、`native_fault`(native のみ落ちた = wasm は NULL 等で落ちない仕様差、比較不能)、`both_fault`(両方落ちた)。
- **`leaf`**: native/wasm とも callee entry 無し (関数 entry trace が各側 ≤1) の case で true。`liftdiff.py summary` の「自己欠陥確定」
  (callee 不在の差分 = その関数自身の欠陥) 集計に使う。**他担当が同形式を出力する場合はこのキーも必ず出す** (欠けると自己欠陥数が 0 と集計される)。
- `function.sig.c` = true の関数は C 定義 (extra_sources / hand port) 由来 (check_ott.py の D4/D5 突合で使用)。
- 戻り値比較: native が実際に書いたバイトのみ (rax の sentinel `0xCAFEBABE0BADF00D` と同じバイトは「未書込」)、wasm 署名の戻り幅で比較。
- 関数 entry 列は IAT thunk (`jmp [iat]` のみの関数) を両側から除外して比較。引数は wasm 署名の型/個数のみ比較 (多い分は arity 診断へ)。

## 4. 原因タグ (`tags[].tag`)

自動分類。信頼度は `high`(実測の挙動が直接示す) / `medium`(静的特徴 + 挙動の整合) / `low`(静的特徴のみ)。

| tag | 意味 | 判定 |
|---|---|---|
| `load_dropped` | グローバルの load が脱落しアドレスが値として使われた (`inc [g]` → `&g+1`) | wasm が書いた値の上位/下位 32bit が自分の RVA ±16 |
| `spill_slot_deref` | レジスタ退避 alloca 自体を `load` (`[rcx]` が alloca `%rcx` を直接読む) | IR に `bitcast ptr %<reg>` があり mem/ret 差分 |
| `icall_drop` | 間接 call/jmp が IR から脱落 | 機械語に非 IAT の間接 call/jmp があり IR の間接 call が 0。native trace に wasm に無い callee があれば high |
| `arg_drop` | 引数(レジスタ/スタック)が IR 署名から脱落 | 機械語の「未定義で読む arg レジスタ/スタック slot」数 > IR 署名の引数数 |
| `xmm_arg_drop` | xmm 引数が脱落 | 機械語が xmm0..n を入力として読む > IR の fp 引数数 |
| `unresolved_callee` | wasm が closure 外の関数 (`function_X` 未定義) を呼んだ | wasm の呼出しログに `function_*` |
| `zero_init_drop` | local のゼロ初期化落ち (未初期化 stack を読む) | wasm の結果が stack fill 0x00 と 0xa5 で変わる |
| `fp_flag_unreflected` | ucomisd/comisd の flag が分岐に反映されない | 機械語に comis/ucomis があり IR に fcmp が無い (結果差分と併発) |
| `import_arg_diff` / `import_call_seq` | import 呼出しの引数 / 列の相違 | calls 差分 |
| `rep_string_helper` / `simd_helper` | `rep movs/stos` / `__asm_*` helper が関連する疑い | 静的特徴 (low) |
| `callee_divergence` | 差分が callee 境界 (entry 引数 / 列) で初めて観測された | trace 差分 |
| `wasm_trap` | native 完走 / wasm trap (`oob`,`unreachable`,`hang` ...) | outcome |
| `memory_semantics` / `ret_only` / `other` | 上記以外の書換えメモリ / 戻り値のみ / 不明 | フォールバック |

## 5. 他担当との共有方法

- `tools/icall` (間接 call 復元): 新 IR を `targets/<x>.json` の `ir` に指定して `batch` を回し、`tags[].tag == "icall_drop"` の件数が減ることと、
  `verdict` が `mismatch → match` に変わることを回帰判定に使う (`liftdiff.py summary` が集計)。
- `tools/liftlib` (共通 pass): `harness/` の diff 出力を本形式の `function`/`verdict`/`cases[].diffs` に合わせれば、`summary` と
  `docs/FORMAT.md §4` のタグで横断集計できる。独自タグは `x-` プレフィクスで追加可。
- 関数 VA を持つ他 target (Fresh Air / Kilohearts / plugin kernel) は `targets/*.json` を足せば同じ native ランナで検証できる
  (PE x64 + `define @function_<VA>` の IR + `wasm_origin`)。

## 6. C 転写 lift (clift) ルート — `targets/flelift.json` (x64c, CAB-232)

LLVM IR を持たない lift 産物 (x64c = C 転写, tools/flelift) を同じハーネスで採点するモード。target JSON に `"clift": true` を置くと
`build_wasm.build()` が `ldlib/clift.py` に分岐する。

| 追加キー | 意味 |
|---|---|
| `clift` | true = C 転写ルート |
| `clift_sources` | lift 産物 C (各 `void f_<VA16進>(void)` が 1 関数。entry に `ld_fle_trace(0xVA)` を自動挿入して計装) |
| `clift_data` | image 敷設 C (`init_exports` の `fle_data_install` が wasm linear に恒等写像で敷設) |
| `clift_meta` | x64c lift 実績 JSON (`functions` = lift 済 VA 列, `imports_used` = import 名)。`lifted.json` に書き出され、非 lift 関数は `unexec/no_wasm_definition` |
| `clift_rt` | lift runtime dir (`fle_cpu.c/h`)。既定 import (`imp_*`, `ott_unlifted`) は `-D` リネームで無効化し、生成 `imps.inc` (全 IAT 名の強い定義, `ld_core.ld_stub` 経由 = native と同一応答モデル+呼出しログ) とブリッジの `ott_unlifted` (ret-0 継続) で置き換える |
| `runner_js` | ランナ JS (既定 `rt/ld_runner.mjs`。clift は `rt/fle_runner.mjs`: case 実行を `_fle_ld_run()` = Win64 ABI → CPU 状態 `R[RCX..]/X[0..3]`/guest stack → `ott_dispatch(va)` に差し替え) |
| `ir` | **署名ソース**としてのみ使用 (case の引数パターンと callee 引数比較を m11 route と同一にし、比較可能性を保つ)。コンパイルはしない |

**アドレス規約**: 恒等写像 (`wasm_origin` = ImageBase = 0x400000, `delta = 0`)。`heap` (= TEB/gs 領域) を 0x1D00000、
`arena` (blob/a: 引数領域) を 0x20000000 に置く。

**case 結果の追加フィールド**: `"unlifted":N, "unlifted_va":"0x.."` — dispatch が lift 集合外 VA (VMT/関数ポインタ経由) に着地し、
m11 route と同じ「ret 0 で継続」をした回数と最終 VA (native は実 callee を実行する)。分類タグ `unlifted_callee` (high)。

**clift ルートの分類タグ差分**: lift 産物に IR が無いため IR 由来タグ (`icall_drop`/`spill_slot_deref`/`short_global`/
`fp_flag_unreflected`/`rep_string_helper`/`simd_helper`) は出ない (静的特徴のみの低確信度タグは誤検出防止のため route='ir' に限定)。
代わりに x64c 由来のタグを追加: `simd_int_semantics` (packed-int 命令を持ち結果が不一致 — packus/pmulhuw/MMX 非エイリアス等),
`xmm_result` (xmm0 戻りのみ差), `unlifted_callee` (上記)。

## 7. boot 状態の生成モード (CAB-233)

`liftdiff.py bootstate <target> [--mode units|entry|hybrid]` は native 実機械語で Delphi InitTable の unit 初期化を実行し、
その時点のメモリ (image diff / heap) を `work/<target>/boot_state.json` に保存する (wasm 側の pristine)。

| mode | 動作 | 用途 |
|---|---|---|
| `units` (既定) | unit 0 から 1 本ずつ `CASE keep=1` で実行し、最初の失敗で止める (`--upto N` で本数指定) | 従来動作。m11 の unit #18 分析 (TLS 修正後は 22 unit 完走) |
| `entry` | `entry_point(hinst,1,0)` を 1 case で直接実行 (実 InitUnits ループが unit を進める)。止まっても到達時点の状態を採用 | 起動経路の実物再現 |
| `hybrid` | entry 実行 → その到達 unit (`System.InitCount` = image 0x11eac98) の次から残りを unit 単位で継続。unit 実行は実 InitUnits と同じ「proc && *proc」判定 (PEEK で先頭 8B が 0 の unit は呼ばない)、失敗 unit は記録して続行 (tolerant) | **native 全起動の参照化**。flelift target で 928/942 unit |

**仮想モジュール / 仮 proc (応答モデル、CAB-233)**: `LoadLibraryW` 系は名前で同一視した仮 module handle (0x50000000+0x10000*i)、
`GetProcAddress` は (module, 名前) で同一視した仮 proc を返す。proc は native では **実行可能 thunk** (0x50010000+i*32 に
`mov r10, MARK|i; mov r11, ld_stub_common; jmp r11` を敷く → native は本当に呼べて応答を返す)、wasm では同じ番地を
`ott_dispatch` が捕捉して同一 `ld_stub` 応答に振り向ける (未対応 index は従来どおり unlifted ret-0)。

**TLS の置き場所 (CAB-233)**: 偽 TEB は heap 先頭 (`LD_HEAP_RESERVED` 64KB)、TLS 配列は heap+0x1000 (`LD_TLS_OFF`)。
TlsAlloc のインデックスで heap 内のスロットを読み書きするため、boot 状態の heap 移送 (SHEAP) で wasm 側にも TLS 値が写る
(m11 の unit #17 = 0x455790 が wasm 側でも通るようになる)。
