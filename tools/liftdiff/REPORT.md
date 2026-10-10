# liftdiff — 関数単位 native-vs-wasm 差分ハーネス (CAB-121)

**判定: 達成**。実 PE の機械語を VA 敷設して Linux 上で直接実行した結果と、lift 済み wasm の結果を、同一引数・同一メモリ初期イメージ・同一
外部呼出し応答で関数単位に差分でき、M11 closure **7,421 関数全数**のバッチ差分 (約 10 分) と、OTT 既知欠陥 D1〜D6 の検出、M11 unit #18 OOB の
原因特定を実測で示した。`bash tools/liftdiff/liftdiff_e2e.sh` が 1 コマンドで再現 (exit 0 = PASS、約 5 分、`--full` で M11 全数 約 11 分)。

## 1. 結論 (実測)

| 項目 | 実測 |
|---|---|
| M11 closure (FLEngine_x64.dll) | `function_*` 定義 **7,421** (closure 7,380 + `__lifted` 等 41)。**一致 2,275 / 不一致 2,885 / 実行不能 2,261** |
| 比較可能 (native が完走した case あり) | 5,160 関数 (69.5%)。そのうち不一致 **55.9%** (2,885)。うち **1,281 は callee を一切呼ばずに差分** = その関数自身の欠陥と確定 |
| wasm trap (native は完走) | 578 関数 (OOB 232 / unreachable 218 / 無限ループ 42 / その他 86) |
| OTT 旧 RetDec chain (ott.ll + C 定義) | 212 関数: 一致 37 / 不一致 108 / 実行不能 67。D1〜D6 すべて検出 (§4) |
| unit #18 OOB の原因 | `_UStrAsg` が旧値を `[dest]` でなく **dest ポインタ自身**として解放、`Move` が `[rcx]` で spill alloca を読む、資源文字列表初期化ループ脱落 (§5)。M11 の「zero-init 落ち」仮説は **反証** (446400 の局所 18 slot は全て 0 初期化済) |
| 性能 | 1 case ≈ native 0.5 ms / wasm 1 ms。M11 全数 (7,421 関数 × 9 pattern × 2 側) を 14 shard で 602 秒 |

## 2. 仕組み

```
target.json (PE, lift IR, wasm_origin, extra_sources)
   │
   ├─ build_wasm.py : IR の各 function_<VA> entry に ld_trace() を挿入 (意味不変) / IR の declare から外部 stub (応答モデル+呼出しログ) を自動生成
   │                  / ld_wasm.c (共有コア) と一緒に emcc → ld_wasm.cjs   (関数は export-all で個別に呼べる)
   ├─ ld_native.c   : PE を ImageBase に mmap → IAT を thunk 化 → MS x64 ABI trampoline (ld_ms_call.S) で任意 VA を実行
   │                  SIGSEGV/SIGILL/SIGFPE/タイムアウトを case 単位で捕捉、関数 entry を INT3+単歩で記録 (trace)
   ├─ rt/ld_core.h  : **native/wasm 共通**のコア。領域(image 書込可能範囲/arena/heap)の pristine 復元・8B ブロック差分・応答モデル・JSON 出力
   └─ liftdiff.py   : case 生成 → 両ランナ駆動 (ハング/クラッシュ時は再起動) → compare.py (ポインタ正規化) → classify.py (原因類型)
```

- **同一入力**: 引数 (整数/ポインタ/f32/f64/スタック引数) とメモリ初期イメージ (ptr-rich random blob, seed 固定) を text プロトコルで両側に渡す。
  ポインタは native = wasm + delta (`delta = ImageBase − wasm_origin`) で常に対応し、比較器が正規化する (スタックは「スタック同士」)。
- **外部呼出し (IAT import)**: 両側とも `ld_core.h` の**同一の応答モデル** (VirtualAlloc/HeapAlloc は bump、BSTR、TLS、QPC 等。他は 0) で応答し、
  (名前, 引数 4 個, 戻り) を記録して比較。引数個数は IR 署名の範囲のみ比較。
- **ABI**: Win64 (rcx,rdx,r8,r9 / xmm0-3 / スタック `[rsp+0x28+8i]`)。Delphi x64 の register 規約は Win64 ABI と同一 (Self=rcx)。32bit Delphi の
  eax,edx,ecx は x64 PE に無く、この環境は `-m32` 不可のため native 側は未実装 (`abi=delphi32` を仕様に予約、docs/FORMAT.md §2)。
- **戻り値**: native が実際に書いたバイトのみ比較 (rax sentinel `0xCAFEBABE0BADF00D` との差) → `al/eax` 戻りや void の誤検出を除去。
- **entry トレース**: native は INT3、wasm は IR 計装で (callee VA, 引数) 列を取り、**最初の乖離点**を callee 境界で特定。IAT thunk (`jmp [iat]`) は両側から除外。
- **boot 状態の移送**: M11 では wasm 側が起動不能なため、native で InitTable の unit 0..16 を実行 → その時点の image(.data/.bss)差分+heap を取得 →
  pointer を `−delta` で rebase して wasm の pristine にも載せる (`liftdiff.py bootstate`)。300 関数サンプルで native 失敗の最多要因だった FastMM GetMem 内 (0x407a97, 127 case) を解消。
- **未初期化 stack 検出**: 差分があった case を wasm で stack fill 0x00/0xa5 の 2 通り再実行し、結果が変わるなら `zero_init_drop`。
- 静的特徴: capstone (間接 call/jmp・comis・rep・arg レジスタ/スタック arity)、IR (間接 call 数・fcmp・`__asm_*`・spill alloca 参照・短い global への広い load)。

## 3. M11 closure 差分表 (`results/m11_closure_verdicts.tsv` に全関数)

boot 状態あり、9 pattern (`z` 全 0 / `s` 小整数 / `p0,p1,p01,pall,pall2` ptr 引数 / `q0,qall` ほぼ全ポインタ領域) × 全関数。

| 区分 | 関数数 | 内訳 |
|---|---|---|
| 一致 | 2,275 | native が完走した全 pattern で 戻り値/書換えメモリ/import 呼出し/callee entry 列が一致 |
| 不一致 | 2,885 | 下表 |
| 実行不能 | 2,261 | native が全 pattern で落ちる 1,267 + 全て NULL 参照 689 + ハング 255 + 署名未対応 (vector/struct) 50 |

不一致の原因類型 (主因 = 優先順位最上位 1 つ / 該当 = 重複あり)。**確信度 high = 実測の挙動が直接示す**:

| 類型 | 主因 | 該当 | 確信度 | 意味 / 判定根拠 |
|---|---|---|---|---|
| `load_dropped` | 892 | 892 | high | Delphi unit 初期化 proc の `add dword [g],1` が `store (&g+1)` に化ける (global load が脱落しアドレスが値に) — wasm の書込値が自分の RVA±16 |
| `wasm_trap` | 380 | 578 | high | native 完走 / wasm が OOB 232・unreachable 218・無限ループ 42 |
| `callee_divergence` | 374 | 881 | medium | 差分が callee 境界 (entry の VA/引数) で初めて観測 (原因は自身か先行 callee) |
| `callsite_arg_drop` | 310 | 312 | high | call site の引数が 0 詰め (native≠0, wasm=0): 引数脱落 / sigfix の 0 詰め |
| `memory_semantics` | 208 | 212 | medium | 書換えメモリが異なる (`_UStrAsg` 等 RTL を含む)。個別調査要 |
| `ret_only` | 183 | 183 | low | 戻り値のみ差 (void 風関数の rax 残り値の疑い) — 要精査 |
| `icall_drop` | 150 | 186 | high 22 / medium 164 | 機械語に間接 call/jmp があり IR の間接 call は **全関数で 0**。native が呼ぶ callee が wasm に無ければ high |
| `import_arg_diff` | 122 | 174 | high | import 呼出しの引数が相違 |
| `xmm_arg_drop` | 70 | 121 | medium | 機械語が xmm0..n を入力として読む vs IR の fp 引数 0 |
| `simd_helper` | 64 | 64 | low | `__asm_*` helper 経由 (静的特徴のみ) |
| `fp_flag_unreflected` | 31 | 93 | medium | comis/ucomis あり、IR に fcmp **0 件** (全 closure で flag 未反映) |
| `arg_drop` | 28 | 48 | high | 機械語の arg slot (レジスタ/スタック 5 番目以降) > IR 署名 |
| `zero_init_drop` | 27 | 43 | high | wasm 結果が stack fill 0x00/0xa5 で変化 |
| `spill_slot_deref` | 17 | 17 | medium | IR が退避 alloca (`%rcx`) 自体を load (`bitcast ptr %rcx`)。静的には closure 67 関数に存在 |
| `import_call_seq` / `rep_string_helper` / `unresolved_callee` | 12/10/7 | 129/12/19 | — | import 列相違 / rep 系 / closure 外関数 (`function_X` 未定義) を呼ぶ |

主要 RTL: `GetMem` ラッパ 412c20・`FastMM_GetMem` 407a50・`InitUnits` 4120c0 は一致 (InitUnits は InitTable 未設定のため**空振りの一致**で、間接 call 脱落は検出できていない: §6)。
`_UStrAsg` 4133f0・`Move` 409c80・`412d60`・`446370` は不一致 (原因 §5)。`_StartLib`/`_InitLib` は実行不能 (TLS・InitContext 前提)。

## 4. OTT 旧 RetDec chain: 既知欠陥 D1〜D6 の検出 (`tests/check_ott.py`, `results/ott_old_defects.json`)

target `ott_old` = `tools/ott/work/ott.ll` + 旧 chain の C 定義 (`m6_stubs_hand`/`m8_rt`/`ott_rt` 等) を wasm 化、実機械語は `OTT_vst2_win64.dll`。

| 欠陥 | 検出 (関数) | 根拠 |
|---|---|---|
| D1 間接 call/jmp 脱落 | **4** (`18011d400`=ctor, `1801a1cb0`, `18011e7b0`, `180120af0`) | ctor は機械語の間接 call/jmp 22 (OTT REPORT と同数) vs IR 0。native trace に wasm に無い callee entry |
| D2 小さすぎる global | **6** (`1801a9be0` ほか) | IR が `[8 x i8]` の global を 16B/広い型で load |
| D3 call site の引数脱落 | **12** (`180127550`, `18011d400` ほか) | callee `180126920` の arg1: native=5 / wasm=0。署名より多い arg を機械語が使用 (`arg_drop` 6) |
| D4 CRT 数学 libm 置換 / D5 hand port 値誤り | C 定義 **18** 関数が native と不一致 | native 実機械語 (DLL 自身の CRT) と C 定義の戻り/メモリ差 |
| D6 processReplacing/SVF 層 | **26** (`1801260c0` = SVF の xmm1 脱落、`1801a9be0`, `1801aa1a0` 等) | `xmm_arg_drop` / `fp_flag_unreflected` / `zero_init_drop` / `spill_slot_deref` |

判定: 旧 chain の欠陥類型 6 つすべてを**自動で**検出 (人手の stage dump 比較・alloc 再生は不要)。D4/D5 は C 定義側なので区別せず一括 (C 定義の個別原因までは分類しない)。

## 5. M11 unit #18 (`455790` → `44bb70` → `446400` → `4133f0` _UStrAsg) の原因 (`tests/check_unit18.py`, `results/unit18.json`)

boot 状態 = native で unit 0..16 実行後。各関数を native vs wasm で差分した結果:

1. **`function_4133f0` (_UStrAsg)**: native は dest が保持していた旧文字列 P の参照カウントを減らす (P−8: 2→1)。wasm は **減らない** (P−8 は 2 のまま)。戻り値は
   `dest−0x10` で、旧値の load (`mov rax,[rbx]`) が **dest ポインタ自身**に化けている (IR: `store i64 %arg1, ptr %rcx.0.reg2mem`)。
   → `UStrAsg(dest=スタック slot, src=0)` では「旧値」= スタックアドレスとなり `[dest−8]` を refcount として解放 → FastMM FreeMem(スタックアドレス) → **OOB**。
   これが M11 の `dest 旧値が不正` の正体 (**未初期化 local ではない**: 446400 は局所 18 slot を全て 0 初期化済、IR も 18/18 の store を保持)。
2. **`function_409c80` (Delphi `Move`)**: 2 バイト以上のコピーが全て誤り。`movups xmm0,[rcx]` が `load i128, ptr %rcx` = **退避 alloca `%rcx` 自体**を読み、
   dest にデータでなく dest ポインタ値 (`0x16872000`) が書かれる (n=2: 0x8b→0x0、n=8: ret 0x8b→0x16872000、n=20: 3 qword 相違)。文字列コピーの基盤なので 446370 の heap に 0x31('1') でなく 0xcc が入る。
3. **`function_4123c0` (resourcestring 表の初期化, 455790 が最初に呼ぶ)**: `mov rcx,[rbp+0x20]; mov edi,[rcx]` (件数 load) が `xor 0,0` に化けループが丸ごと消える。
   native は callee entry 53 (LoadStringW ×7 …)、wasm は 4 — 資源文字列が全て未設定のまま後続へ。
4. **`455790` 全体**: wasm は `412510` (再配置表適用, M11 では m11_ov で手転記して回避) の OOB で止まる。native 側は unit #17 内 `41d110` の TLS 取得
   (`gs:[0x58]` + TlsIndex=0xFFFFFFFF) で SIGSEGV — これは**環境**: `_StartLib` (TlsAlloc) 未実行の InitUnits 単独実行のため。
   参考: native で `entry_point` を直接呼ぶと InitCount=171 unit まで進む (stub 拡充で更に進む見込み)。native が M11 の wasm (17 unit) より深く起動できる。

M11 の修正案との対応: (1)(2)(3) はいずれも RetDec の **load の取り違え (値↔アドレス/1 段 deref 脱落)** という同一系統で、`load_dropped` 892・`spill_slot_deref` 67 関数 (IR 静的)・
`callsite_arg_drop` 312 に広がる。個別の hand 転記でなく IR レベルの機械的修復 pass の対象 (§7)。

## 6. 限界・誤検出 (正直な注意)

- **一致 = 与えた状態・引数で一致 (必要条件)**。引数/状態が悪いと分岐が通らず「空振りの一致」になる (例: InitUnits)。pattern は 9 種で、this/VMT を持つ
  オブジェクト・文字列・配列を要する関数は実行不能になりやすい (実行不能 30.5%)。
- native が落ちて wasm が落ちない case (NULL 参照; wasm は低位アドレスを読める) は比較不能として扱う (`native_fault`)。
- 応答モデルは 0 返しが既定。`GetLocaleInfoW`/`EnumCalendarInfoW` 等を実装していないので、ロケール依存経路は native/wasm とも浅く通る。
- `callee_divergence` は連鎖の影響を含む (原因が callee 側のことがある)。**自身の欠陥と確定できるのは callee 不在の差分 (1,281)**。
- `ret_only` (183) は void 風関数の rax 残りが主で low。`icall_drop` の medium は静的特徴のみ。
- wasm 側の SIMD helper は m11 の `m11_simd2.py` 生成物をそのまま使う (その誤りは `simd_helper` として現れる)。
- 32bit Delphi (eax,edx,ecx) は native 実行環境が無く未実装。SEH/例外 (`RaiseException`) は復帰不能 (case が落ちる)。

## 7. 成果物

| パス | 役割 |
|---|---|
| `liftdiff.py` | CLI: `build / run / batch / bootstate / summary / export` |
| `rt/ld_core.h ld_native.c ld_ms_call.S ld_wasm.c ld_runner.mjs` | 共有コア / native ランナ / wasm ランナ |
| `ldlib/{build_wasm,irtool,pe,session,cases,compare,classify,boot,runners}.py` | ビルド・IR 計装/stub 生成・静的解析・case・比較・分類・boot 状態 |
| `targets/{m11,ott_old}.json` | target 記述 (他 target は json を足すだけ) |
| `docs/FORMAT.md` | **差分レポート JSON / ランナ プロトコル / タグ仕様** (tools/icall, tools/liftlib と共有) |
| `tests/check_ott.py check_unit18.py` | OTT D1〜D6 突合 / unit #18 原因特定 |
| `results/` | `m11_closure_verdicts.tsv` (全 7,421 関数の判定+主因) / `ott_old_*` / `unit18.json` / summary |
| `liftdiff_e2e.sh` | 1 コマンド再現 (OTT 欠陥検出 + _UStrAsg 例 + M11 サンプル/全数) |

```sh
bash tools/liftdiff/liftdiff_e2e.sh            # 約 5 分 (M11 は代表 800 関数)。--full で 7,421 全数 約 11 分
python3 tools/liftdiff/liftdiff.py run targets/m11.json --state auto --fn 4133f0 --args "i:a:0x1000,i:0x0" --patch "a:0x1000:q=a:0x3000;a:0x2ff8:02000000" -v
python3 tools/liftdiff/liftdiff.py batch targets/<t>.json --set closure --shards 14 --state auto --out work/<t>/batch.jsonl   # 新 IR の回帰判定
# 前提: tools/m11/work の boot_final3.ll/boot_final.ll/m11_image.bin (m11_e2e.sh --full)、tools/ott/work/ott.ll (ott_build.sh)、emsdk、node、capstone/pefile
```

## 8. 下流チケット案

1. **load 取り違えの IR 修復 pass** (`load_dropped` 892 / `spill_slot_deref` 67 / `_UStrAsg`/`Move`/4123c0): 機械語の `mov r,[mem]` ↔ IR の load を突合し、脱落/取り違えを再 lift。回帰は `batch` の verdict で判定。
2. **tools/icall・tools/liftlib の新 IR を liftdiff で採点**: `icall_drop` 186 / `callsite_arg_drop` 312 / `fp_flag_unreflected` 93 の減少と `mismatch→match` を指標化。
3. **native 全起動の拡張**: `entry_point` は stub 不足で unit 171 止まり。LoadLibrary/GetProcAddress/RegisterClass 等の応答を足し、全 942 unit 完走する native 参照を作る (M11 stage 6 の正解状態)。
4. **実行不能 2,261 の被覆拡大**: this/VMT 疑似オブジェクト・UTF-16 文字列 blob・native が落ちた RVA からの自動引数補正。
5. wasm_trap 578 (OOB 232 / unreachable 218 / 無限ループ 42) の個別トリアージ (`unreachable` は署名不一致 thunk 由来の疑い)。
6. 32bit Delphi register 規約 (eax,edx,ecx) の native 実行 (-m32 toolchain 導入が前提)。
