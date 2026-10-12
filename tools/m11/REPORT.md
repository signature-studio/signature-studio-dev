# M11 REPORT — FLEngine_x64.dll 部分起動 PoC (audio/GUI なし)

**判定: 部分達成** (到達 stage 4/6)。`entry_point`(DllMain attach) → `_StartLib` → `_InitLib` → `InitUnits` が
wasm 上で動作し、**FastMM4 が実際に GetMem → VirtualAlloc でプールを確保するところまで**は実測で到達。
ただし 942 unit の初期化は通常起動で **22 本完走後、unit #23 (VA 0x467f00) が Delphi 例外 → Halt0 (§9, #132 で #18 の OOB を解消)**、stage 5 (survey trap 無し完走) は未達。
(下の §1 表と §2〜§8 は #132 以前 = unit #18 OOB 時点の実測。最新値は §9。)

再現: `bash tools/m11/m11_e2e.sh` (増分約 10 秒 / `--full` で RetDec lift から全再生成 約 10 分)。常に exit 0。

## 1. 結論と実測 (m11_e2e.sh 出力)

| 項目 | 実測 |
|---|---|
| 到達 stage | 4/6 (1 image 敷設 / 2 `_InitLib` / 3 `InitUnits` 開始 / 4 FastMM4 実行 は達成; 5 全 unit 完走 / 6 DllMain 正常終了は未達) |
| 停止理由 (通常起動) | unit #18 (`function_455790`→`44bb70`→`446400`→`4133f0`=`_UStrAsg`) で `memory access out of bounds`。直前呼出は `UStrAsg(dest=呼出元 `44bb70` の local record, src=0)`、dest 旧値が不正。**原因 (検収で実証)**: `44bb70` の 0x188 byte record (`rep stosq` ×49) を RetDec が `alloca i64` (8 byte) に潰し、memset/フィールド書込がスタックを破壊 (ゼロ初期化は落ちていない) |
| 初期化 unit | 通常起動 17 / 942 本完走。**隔離 survey** (InitUnits 抑止し 942 本を try/catch で 1 本ずつ): **ok 812** / trap 83 / closure 外 46 / proc 無し 1 (trap 無し=意味正しい、ではない) |
| survey trap 内訳 | OOB 34, Halt0→longjmp 48 (unit が Halt を呼ぶ), abort 1 (sigfix 前は `unreachable` 43 / OOB 12 / Halt 40 / abort 8, ok 792) |
| FastMM4 状態 (通常起動) | GetMem 13 / FreeMem 1 (FastMM_GetMem 実体 `0x407a50` も 13)。最初の `VirtualAlloc` size=1,310,704 (0x13FFF0) = **FastMM4 MediumBlockPoolSize (1.25MB−16)** |
| 同 (survey 通算) | GetMem 258 / FreeMem 19 / VirtualAlloc 33 回 (約 1.46 GB; 巨大要求は誤 lift の疑い) |
| lift closure | lift 入力 7,380 関数 (base 7,361 + tail/間接 seed 19) → IR 定義 7,421 (RetDec が内部入口 41 個を別関数化), 1.41 MB code → IR 約 49.1 万行 → wasm 6.0 MB (wasm-ld 署名不一致 0 / 未定義 symbol 0) |
| 間接 call 表 | 7,399 トランポリン (`m11_tr_function_X`, VA 二分探索) |
| 実行時間 | 起動〜停止 約 0.2 秒 (-O0) |

**「FastMM4 heap 初期化完走」は未証明**。到達しているのは「GetMem が medium pool を VirtualAlloc して返す」までで、
FastMM4 の初期化関数群 (InitializeMemoryManager 相当) を単体で検証してはいない。state は probe 計数 (GetMem/FreeMem/VirtualAlloc 量) のみ。

## 2. 最大の発見: RetDec `--select-decode-only` 出力は Delphi RTL では意味が壊れる

`closure → 一括 lift → 機械 patch` 方式の根本的な限界が実測で判明した。

1. **間接 call が IR から全滅**: closure 全体 (IR 定義 7,421 関数) の IR 中、間接 call は **0 件**。capstone による独立監査 (`m11_icall_audit.py`) で、同 closure の機械語には `call [reg+off]` 4,123 + `call reg` 48 + `call [base+idx*s]` 4 = **間接 call 4,175 件 (1,631 関数)** が実在 (別に `call [rip+x]` 166 / `jmp [rip+x]` 401 は IAT・静的ポインタ経由)。脱落率 100% = ott D1 と同根。`System.InitUnits` は
   ループ本体 (`call [rbp+0x38]`) が丸ごと消え、Count 読出しだけ残る。VMT・TLS hook・DllProc 呼出しも同様。
2. **stack 渡し引数 (第5引数以降) の取りこぼし**: `_InitLib`(`0x412160`) は 8 引数だが 5 引数に切詰められ、
   第7引数 Reason が未初期化 alloca(=0 固定)になり `Halt0` に直行した。
3. **メモリ意味の誤 lift**: `_UStrAsg`(`0x4133f0`) は `mov rax,[rbx]; mov [rbx],rsi` の旧値読出しが消え (store→load 転送を逆順適用)、
   `0x412510`(再配置表適用) は `mov r8d,[rcx]` が `mov r8d,ecx` 化 (Count=ポインタ下位32bit)。
4. **call site/callee の署名不一致**: closure 内 call 27,714 件中 **約 6,600 件** (24%) で引数数・戻り型が食い違う。LLVM-wasm は表現不能な差を
   `body=unreachable` の thunk にし、実測 **132 thunk / 2,431 call site** が実行時 trap だった (→ `sigfix` pass で 0 に)。
5. **スピルしたポインタ経由の 2 段 deref を 1 段落とす**: `0x450560` (`mov [rsp+0x60],rcx … mov rax,[rsp+0x60]; mov rdx,[rax]`) は
   `UStrAsg(dest, *src)` が `UStrAsg(dest, dest)` になり、以降 stack アドレスが文字列値として流れた。Delphi の非最適化コードに多いパターンで再発しうる。
6. **RetDec が .data の静的初期値から解決した間接 call** (例 `Random` の `call [RandomPtr]` → `function_40a120`) は IR 上で直接 call になるが、
   disasm ベースの call graph には現れず closure から漏れる。

→ これらは「抽出漏れ」でも「API 未対応」でもなく **lift 品質の問題**。関数単位で逆アセンブルと突合して手修正 (下記) するしか現状手が無い。

## 3. 解除した fail-fast / 修正の一覧 (反復 16)

| # | 症状 | 原因分類 | 対処 (ファイル) |
|---|---|---|---|
| 1 | `unresolved function_412680` (setjmp) | (a) closure 漏れ: `412760` の **`jmp` 末尾呼出し**を辿っていなかった | `m11_tail.py` が `call`/`jmp` 即値を closure 内関数から直接 disasm で再走査 |
| 2 | `__asm_rep_movsq_memcpy` OOB | (c) helper 意味誤り: count を byte 扱い (実際は qword 数) / stosq も誤り | `m11_simd2.py` (qword×8, stosq は 64bit fill) |
| 3 | `Halt0` 直行 (Reason=0) | 2.2 stack 引数脱落 | `m11_ov.c`: `_StartLib`/`_InitLib` を逆アセンブルから C 転記 (`function_41d8f0`, `m11_InitLib`) |
| 4 | unit 初期化ループ消滅 | 2.1 間接 call 脱落 | `m11_ov.c`: `InitUnits` 転記 + `m11_icall()`(VA→トランポリン表) |
| 5 | `InitTable` Count=0 | (a') `.text` 内の定数表 (Delphi は InitTable/PackageInfo を .text に置く) が未敷設 | `m11_image_gen.py` → `work/m11_image.bin` (.text/.data/.rdata, reloc 補正) をホストが HEAPU8 に載せる (wasm へ実バイナリ非埋込) |
| 6 | `unreachable` (signature thunk) | (b) C 側署名が IR の wasm 署名と不一致 → wasm-ld が trap thunk 生成。**215 件**中 215 件が Win32 stub (genstubs の引数 parse バグ: `"ptr,"` を未知型 i64 扱い) | `m11_genstubs.py` 修正 + `m11_post.py` が IR 署名の C prototype (`*_sigs.h`) を生成。**mismatch 215 → 0** |
| 7 | `__asm_cpuid` が `unreachable` | (c) struct 返し helper 未定義 | `m11_simd2.py` が署名駆動で全 200 helper を定義 (SSE2 までを広告する cpuid) |
| 8 | `__asm_*` 141 名が既定値 stub (semantic 欠落) | (c) 旧 gensimd は名前+出現順 suffix 依存 | `m11_simd2.py`: base 名+型で意味決定 (200 中 196 実装 / 4 は AVX i256 → 呼ばれたら abort) |
| 9 | `0x412510` が OOB | 2.3 誤 lift | `m11_ov.c` 転記 |
| 10 | `_UStrAsg` 旧値読出し欠落 | 2.3 誤 lift | `m11_ov.c` 転記 |
| 11 | Halt0 が `ExitProcess` まで進む | longjmp を lift で表現できない | `function_412770` を JS 例外 (`m11_dllmain_done`) に置換、ハーネスが「attach 完走」と判定 |
| 12 | `RegEnumValueW` が 1,101,264 回ループ | (b) stub が 0(=SUCCESS) を返した | `m11_win.c`: レジストリ空扱い / 列挙は 259 |
| 13 | `function_40a120` 他 unresolved | closure 漏れ (2.6) | `m11_extra_seeds.txt` に IR の「宣言のみ function_*」を累積追加 (固定点, 19 関数) |
| 14 | VirtualAlloc 339MB 要求で arena 外ポインタ | rt のバグ | `m11_rt.c`: 要求ごとに calloc + 64KB 整列 |
| 15 | **`unreachable` thunk 132 個 / 2,431 call site** | 署名不一致 (2.4) | `m11_post.py` `sigfix`: 6,675 call site を callee 定義署名へ書換え (不足引数は 0 詰め=意味未保証)。thunk 132 → 0、survey ok 792 → 812 |
| 16 | `0x450560` が dest を src に誤用 / `LCMapStringW` stub=0 | 2.5 誤 lift + (b) | `m11_ov.c` 転記 + `m11_win.c` に LCMapStringW (ASCII) |

## 4. 未解決

* 通常起動 unit #18 以降: `446400` (ロケール/書式設定読込) 内の `_UStrAsg` が OOB。`0x450560` の誤 lift は修正済だが停止位置は不変で、
  dest は `44bb70` の local record で、**「local ゼロ初期化落ち」仮説は反証済** (`446400` の 18 個の `mov [rbp+x],0` は IR に全て有り、`44bb70` も memset 有り)。真因は record の `alloca i64` 縮退 (§1)。`44bb70` を 392 byte 配列で C 転記する実験 (revert 済・未コミット) で OOB は消え、unit #18 は Halt0→longjmp に進む (survey: OOB 34→33 / Halt0 48→49 で ok 812 不変)。aggregate local の alloca 縮退は他関数にも及ぶ可能性 (`rep stos` 定数長で 8 byte 超のサイト 4 件を確認、全数は未調査)。
  同時に 339MB×2 の巨大 `VirtualAlloc` 要求 (サイズ算出の誤 lift と推定) が出る。
* survey の trap 83 本: OOB 34 (最多は `function_8cbcb0` 系 9 unit が共通: `8cc190`←`8c7a10`←`8c5cc0`; 1 箇所の修正で複数 unit が通る見込み) /
  Halt0 48 (unit が失敗時に Halt を呼ぶ: Win32 stub 品質由来の可能性) / abort 1。個別未調査。
* 46 unit は closure 外関数を呼ぶ (間接 call 先 `0x41d0e0` 等)。1 unit は proc 無し。
* 浮動小数比較 (`ucomisd/comisd`) の flag を IR に反映する pass (m6 `ir6_pass [P1]`) は未移植 → FPU 比較分岐は**意味未保証**。
* `GetLocaleInfoW` 等ロケール API は 0 を返す stub のまま。SEH(.pdata) は未対応 (stub 方針、例外発生で停止)。
* **lift 結果の正しさ検証手段が無い**: 関数単位の差分テスト (実機/エミュ比較) が未整備。

## 5. 次の一手 (下流チケット案)

1. **lift 検証ハーネス**: 関数入出力を native 実行 (wine/unicorn) と wasm で比較し、誤 lift を機械検出 (本 PoC の手作業突合を自動化)。最優先。
2. **RTL 専用 lifter**: Delphi RTL (System/SysUtils: `_UStrAsg` 等 約 数百関数) は Ghidra P-code か remill 系で再 lift、または FastMM4/RTL を OSS ソースから wasm ビルドして**差し替え**
   (RTL は FL 固有コードでなく差し替え可能。M11 の方針「FL 側は極力変更しない」に反しない)。
3. **間接 call の復元**: Ghidra の vtable/jump-table 解析結果で `m11_icall` 相当を IR パスとして自動挿入 (現状は手転記)。
4. **unit #18 以降の原因特定**: `446400`/`450540` を逆アセンブルと突合 → override 追加 → survey の trap 83 を減らす (目標 < 20)。
5. **stage 6 到達**: 全 unit 完走 → Halt0/longjmp → `DllMain` が TRUE を返す。その後 `FLEngine` export (`FL_*`) の初期化 API 呼出しへ。
6. 不足引数 0 詰め (sigfix) の意味補完: RetDec が落とした stack 引数を callee 側の逆アセンブルから復元する pass。
7. Win32 shim の拡充 (tools/shim へ還元するのは shim 担当; ここでは `m11_win.c` に限定)。

## 6. ブロッカー / ユーザ依頼

* ブロッカー: RetDec 出力の意味保証が無い (上記 §2)。以降の進捗は lift 検証ハーネス or 別 lifter の導入に依存。
* ユーザ依頼事項: **なし** (素材は `docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin` で足りた)。
  将来 RTL を OSS ソースから差し替える場合は Delphi (FPC 可否含む) toolchain の選定判断が必要。

## 7. 成果物 (tools/m11/)

| ファイル | 役割 |
|---|---|
| `m11_e2e.sh` / `m11_judge.py` | 1 コマンド再現 + 機械判定 (到達 stage / 停止理由 / FastMM 状態 / 数値) |
| `m11_scan.py` `m11_bounds.py` `m11_tail.py` `m11_extra_seeds.txt` | closure 決定 (call graph + tail-jmp + 間接 seed 固定点) |
| `m11_lift.sh` `m11_lift_all.sh` `m11_merge.py` `m11_asmfix.py` `m11_passes.py` `m11_gen_ir2.sh` | RetDec lift → IR 整形 (m2/m5 pass の copy+拡張) |
| `m11_post.py` | IR 後処理: weak 化 / 間接 call トランポリン+表 / C 署名 header / FastMM probe |
| `m11_simd2.py` | `__asm_*` 署名駆動 helper 生成 (SSE2 まで; cpuid) |
| `m11_genstubs.py` `m11_win.c` `m11_rt.c` | Win32/CRT stub と実装、VirtualAlloc 等 |
| `m11_ov.c` | **lift-fix override** (手転記 6 関数 + 間接 call dispatch + unit survey 入口) |
| `m11_image_gen.py` `m11_data_gen.py` | PE イメージ敷設 (実行時ロード / .data/.rdata 埋込) |
| `m11_build.sh` | emcc 増分 build (TU ごとに .o キャッシュ) |
| `m11_run.mjs` `m11_survey.mjs` `m11_trap.py` | 実行ハーネス / unit survey / trap の関数名注釈 |
| `m11_icall_audit.py` | capstone による closure 内間接 call 数 vs IR 間接 call 数の監査 (ott D1 の FLEngine 版; `work/icall_audit.json`) |

`work/` (RetDec 出力・IR・wasm・image) は `.gitignore`。実バイナリ由来の image は wasm に埋め込まず実行時に読込む。

## 8. LB_BASE=0x10000 適用 (#222, 達成: 静的層 + `m11_e2e.sh` 実行で LB=0 と同水準を確認)

既知類型との関係: 該当なし (関連: DEFECTS.md D11 = PE VA リテラルの wasm32 切捨て。本件は VA→LVA 規約の変更で別件)。

`M11_LB_BASE` (既定 0 = 従来 LVA=RVA / `0x10000` で LVA=RVA+0x10000) で全層を切替可能にした。既定 0 は従来と byte 一致。

| 層 | 変更 |
|---|---|
| `lb_base.py` | `M11_LB_BASE` の単一定義 (64KiB 境界を assert) |
| `m11_image_gen.py` / `m11_data_gen.py` | reloc 補正 `-0x400000` → `-0x400000+LB`、image 先頭に LB 分の 0 領域 / data の memcpy 先に +LB |
| `m11_passes.py` | IR の VA→LVA remap (M1/M2/M2b) の差分 `BASE_VA = 0x400000 - LB` |
| `m11_ov.c` `m11_rt.c` `shimx_link/trace_rt.c` | 手書き RVA 定数 (`R()` 経由)・icall 表引き `target+(0x400000-LB)`・`hinst` を `-DM11_LB_BASE` で補正 |
| `ldfix/ldfix.py` `ldfix/halt0_map.py` `shimx_link/analyze.py` `run_trace.mjs` | LVA↔VA 換算に LB を反映 |
| `m11_build.sh` / `m11_e2e.sh` | `-DM11_LB_BASE`・stamp 不一致時の再生成/拒否・GLOBAL_BASE 衝突 assert・`lb_check.py` 実行 |

`m11_bounds.py` / `m11_tail.py` / `m11_icall_audit.py` は VA 空間 (LB 非依存) なので変更不要。GLOBAL_BASE 0x10000000 は image 終端 0x18c0000+0x10000 より後ろで変更不要 (assert 済み)。initial 288MiB / max 1.8GiB も未変更。

### 実測 静的層 (コミット済み HEAD `95054de`, FLEngine_x64.dll 22,227,016 B)

| 項目 | 実測 |
|---|---|
| DIR64 reloc 総数 / 指す先 RVA<0x10000 (LB 適用前) | 278,531 / 55,929 (`lb_check.py` が別実装で再計算し `audit_va.py` と一致) |
| LB=0x10000 適用後 linear<0x10000 の reloc 先 | **0** (全 278,531 が >=0x10000; 値は `v-0x400000+0x10000` と全件一致, 不一致 0) |
| 非 reloc バイト不一致 / 先頭 64KiB の非 0 バイト | 0 / 0 |
| LB=0 の image | 旧 `m11_image_gen.py` 出力と `cmp` 一致 (22,515,781 B) |
| LB=0x10000 の image | 22,581,317 B (+65,536 B) |
| 実行 (HEAD, n=3, load 0.17–0.36, 直列) | image_gen + lb_check: 8.21–8.40 秒, 3/3 PASS |
| ネガティブコントロール | reloc 1 件の LB 補正を落とすと `dir64_value_mismatch=1` で FAIL; LB=0 image を LB=0x10000 で検査すると FAIL (長さ不足) |
| IR remap pass 単体 | 試料 IR で store 即値 4096 (LB=0) → 69632 (LB=0x10000) を確認 (全 IR での件数は未計測) |

再現: `M11_LB_BASE=0x10000 python3 tools/m11/m11_image_gen.py <PE> && uv run --with pefile python tools/m11/lb_check.py <PE> work/m11_image.bin 0x10000`

### IAT 738 スロット (要確認項目 4)
全 738 スロットは `.idata` 内の hint/name RVA を持ち (IAT==ILT 738/738, by-name 738)、`.reloc` に載るのは 0 件、image 範囲値に見えるのは RVA を VA と誤認しているだけ。m11 の image は `.idata` を敷設せず (`KEEP` に無し)、`m11_genstubs.py` / `m11_win.c` は IAT を参照しない (grep 0 件; Win32 は IR の declare 名で stub 化)。**LVA 化への追従は不要**。`audit_va.py` の IAT 判定 (exit 1) は Delphi 側ではなく PE 標準の bound 前 IAT の誤検知で、FLEngine には不適。

### 実測 `m11_e2e.sh` (LB=0 vs LB=0x10000; コミット済み HEAD `3162415`)
GitHub Actions runner (4 core, load 0.6–0.9)。素材は work-m11 スナップショット (lift 成果物 `boot*.lift.ll` は LB 非依存で再利用; `gen_ir2` で IR の VA→LVA remap・data/image・emcc 増分ビルド・実行 A/B を再実行)。各 1 回, 直列。

| 項目 | LB=0 | LB=0x10000 |
|---|---|---|
| `m11_e2e.sh` 所要 (実行 A/B 込み) | 38 秒 (boot/data 等の全 obj を emcc; gen_ir2 は直前の失敗実行で済) | 61 秒 (gen_ir2 + 全 obj を emcc) |
| lb_check | PASS | PASS (linear<0x10000 の reloc 先 0) |
| 到達 stage | 4/6 | 4/6 |
| 通常起動 | unit 17/942 完走後 `memory access out of bounds` | 同 |
| FastMM4 (通常起動) GetMem / FreeMem / VirtualAlloc | 13 / 1 / 3 | 13 / 1 / 3 |
| survey ok / noproc / miss / trap | 812 / 1 / 46 / 83 | 812 / 1 / 46 / 83 |
| trap 内訳 (OOB / Halt0 / abort) | 34 / 48 / 1 | 34 / 48 / 1 |
| wasm サイズ / image | 6,010,298 / 22,515,781 B | 6,010,681 / 22,581,317 B |

**stage 進行・survey 集計は一致**。unit 別 (942 本) に結果種別 (ok / noproc / miss / trap 種別) を比較すると差 0 (frame idx は unit 477 の `5385`→`5386` のみ。LB 依存の関数番号ずれで、同一 unit 477 の trap 種別は OOB のまま)。unit 別の副次カウンタ (GetMem / VirtualAlloc / stub 呼出) の差は 2 unit のみ:
* unit 745 (VA 0xacb3b0, `function_ebb3b0`): LB=0x10000 だけ `SelectObject` stub が 3 回追加で呼ばれる (stub は 0 を返して継続; どちらも後続で OOB trap し種別は同一)。呼出元は未特定。原因 (LB 依存の分岐か、未初期化読みの値差か) は未調査。
* unit 873 (VA 0xe61210): LB=0 は `VirtualAlloc` 1914MB 要求が 2GiB 上限で OOM → NULL → `Halt0`、LB=0x10000 は VirtualAlloc 要求自体が無く `Halt0` (どちらも Halt0→longjmp で種別同一)。要求サイズが LB で変わる原因は未調査。
どちらも終了種別は不変で、集計 (ok 812 / trap 83) には影響しない。

ネガティブコントロール (wasm と image の LB 不一致が実行で検出できること = 比較が鈍感でないこと):
| 組合せ | 通常起動 | survey |
|---|---|---|
| wasm LB=0x10000 + image LB=0 | `init_count` 0, `units_run` 0, icall_miss 717 | ok 0 / miss 920 / noproc 21 |
| wasm LB=0 + image LB=0x10000 | `units_run` 8, icall_miss 12,213, OOB | ok 2 / miss 939 |

再現 (m11_build.sh は `llvm-nm` を PATH から引くので `export PATH=/opt/emsdk/upstream/bin:$PATH` 相当が要る。runner では emsdk_env.sh が `llvm-nm` を PATH に載せず build が rc=127 で FAILED になるため `llvm-nm` の symlink を PATH に置いた): `M11_LB_BASE=0x10000 bash tools/m11/m11_e2e.sh` (PE パスは `/home/ubuntu/work/...` ハードコードのため symlink で回避)。

### 軽微修正 (本 PR の同梱)
* `lb_check.py`: image が `LB + 節末` より短いとき `struct.error` になっていたのを、先に長さを判定して `errors` を出し FAIL (exit 1) するよう修正 (長さ 1000 B の image で FAIL 出力を確認)。
* `ldfix/ldfix.py` / `ldfix/halt0_map.py`: `M11_LB_BASE` の個別 parse をやめ `lb_base.py` (`LB`, `IMG_BASE`) を使う。`M11_LB_BASE=0x10000` で `ldfix.BASE == 0x3f0000` を確認。

### 未検証 / 範囲外
* 全 IR での remap 件数・実行後の guest ポインタ assert は未計測 (stage / survey が一致することで代替確認)。IR の VA→LVA remap の regex (`m11_passes.py` M2b) は VA 側を見るので LB 非依存の見立ては、e2e 結果と整合 (補正漏れがあれば上記ネガティブコントロールのように崩れる)。
* `#221` (liftlib `dataimage.py:37` フィルタ) は別 issue のまま。
* 上記 unit 745 / 873 の副次差の原因調査は未実施 (集計に影響しないため本 PR の範囲外)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 745 / 873 の副次カウンタ差 (SelectObject 3 回 / VirtualAlloc 要求有無) の原因 | 集計には無影響。LB 依存の分岐が残っていないかの確認 | #222 コメントに記録 (未起票。要なら PM が起票) |
| `audit_va.py` の IAT 判定が FLEngine で常に exit 1 | CI 検査に使えない | #91 にコメント (PE 標準 IAT は除外すべき) |

## 9. #132: unit #18 OOB の真因解消 (通常起動 17 → 22 unit)

既知類型との関係: DEFECTS.md D7/D10 (alloca 縮退) の変種 (callee へ escape した stack_var) + D1 系 (旧値 load 脱落, `_UStrAsg` と同型)。

| 項目 | 変更前 (HEAD 0a9e9d3) | 変更後 (HEAD 499bdfa) |
|---|---|---|
| reached_stage (m11_e2e.sh) | 4/6 | **4/6 (不変, stage 5 未達)** |
| 通常起動 units_run | 17 / 942 (unit #18 OOB) | **22 / 942** (unit #23 = 0x467f00 が Halt0、例外なし) |
| survey ok / trap / miss / noproc | 812 / 83 / 46 / 1 | **817 / 78 / 46 / 1** (trap = halt0 39 + OOB 39) |
| m11_e2e.sh 所要 | 39.5 s | 86.5 s (build 増分 + alloca pass 毎回適用) |
| 負荷 (load average, 終了時) | 0.91 | 1.08 |

**真因 (実測)**: 44bb70 の record (392B, CAB-129 で拡幅済) の +16 が、直前に呼ぶ `function_44bae0` の呼出し前後で 0 → 0x100000000 に変化
(`m11_site` を IR に埋めて前後値を実測)。44bae0 の `stack_var_-88` が `alloca i64` (8B) だが、`call 44ba50(ptr)` で escape し
callee が `[rcx+0x2c..0x3e]` (GetCPInfo の LeadByte 表) に書くため、呼出し元フレーム (= 44bb70 の record) を破壊していた。

修正 (3 点, すべて通常起動 17→22 に必要):
1. `alloca/m11_alloca.py` **R8**: escape する `stack_var_-N` を「次の stack_var までの間隔」に拡幅 (4,077 サイト → 2,417 alloca / 1,355 関数, +1.15 MB stack)。
   R8 だけでは OOB 解消のみ (units_run 17 のまま, unit #18 が Halt0 へ)。
2. `m11_build.sh`: alloca pass を build 時に常設 (idempotent, 内容が同じなら mtime を触らない)。`m11_e2e.sh` の既定経路で pass が掛かる。
3. `m11_ov.c`: `function_412d60` (`_UStrClr`) / `418190` (`_LStrArrayClr` 系) / `416db0` (`_CopyArray`) を C 転記。いずれも RetDec が
   `mov rax,[rbx]` 型の旧値/kind の load を脱落 (D1 系)。**416db0 は `movzx rcx,[r8]` の kind 読出しが脱落し常に未知 kind → Error → Halt0** だった
   (unit #18: TFormatSettings の string フィールド kind=18)。逆アセンブル 0x416db0〜0x416f65 の分岐表 (10/11/12/13/14/15/17/18/22) と突合。

ネガティブコントロール: HEAD から修正 3 点 (m11_ov.c の 3 関数と build の alloca pass) を外して同手順で再ビルド → units_run 17 / OOB に戻ることを確認 (同環境)。

**次 blocker (unit #23 = 0x467f00)**: `467f00 → 467c40 → 45a640 → 45a2a0 → 411e80 → 411d20 → 412a60 → Halt0`。467c40 は
`call [rax]` (IAT 経由の Win32 API, `mov ecx,eax` で戻り値を 45a640 に渡す) の結果で `45a640(ecx, dx=11, r8w=8)` を呼び、ecx が 0 以外・
`0x7ffdfffb` 系でない値のとき 45a2a0 (例外送出, 0xEEDFADE) に進む。`467c40` の IR には間接 call が **0 件** (機械語 0x467cc9 `call [rax]` / 0x467d5d `call [rax]` が丸ごと脱落 = D15 型, `work/icall_audit.json` の
`capstone_fns_with_indirect_call` 系と同じ現象)。脱落した戻り値の代わりに `45a640` へ未定義値 (ecx) が渡り例外送出へ進む可能性が高い。
`[rip+0x117be27]` の指す IAT スロットの import 名は未特定 (capstone/pefile が runner に無く本 run では未解決。次ラウンドで venv を用意して特定)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit #23 (0x467f00) の Halt0 (467c40 の IAT 呼出し戻り値) | 通常起動 22 で停止、stage 5/6 未達 | #132 に継続 |
| survey trap 78 (halt0 39 / OOB 39)・closure 外 46 | stage 5 判定 (survey trap 無し) 未達 | #132 に継続 |
| `m11_site` 型の診断 (IR へ guest VA を埋める) が m11 に無い | 反復が手作業 | boot/dbg_lift.py (flelift/boot) の m11 版を要検討 |
| `wasm-objdump` が runner に無く m11_judge/m11_trap の関数名注釈が `?` になる | trap frame 名が出ない | exports の index→名前を node で引く簡易版で代用 (本 run) |
