# M11 REPORT — FLEngine_x64.dll 部分起動 PoC (audio/GUI なし)

**判定: 部分達成** (到達 stage 4/6)。`entry_point`(DllMain attach) → `_StartLib` → `_InitLib` → `InitUnits` が
wasm 上で動作し、**FastMM4 が実際に GetMem → VirtualAlloc でプールを確保するところまで**は実測で到達。
ただし 942 unit の初期化は通常起動で **22 本完走後、unit #23 (VA 0x467f00) が Delphi 例外 → Halt0 (§10, #132 で #18 の OOB を解消)**、stage 5 (survey trap 無し完走) は未達。
(下の §1 表と §2〜§8 は #132 以前 = unit #18 OOB 時点の実測。最新値は §10。)

再現: `bash tools/m11/m11_e2e.sh` (work/ があれば増分 build: 実測 29.3〜29.6 秒 (§10, 4 vCPU, n=3) / `--full` で RetDec lift から全再生成: 旧記載「約 10 分」で本 PR では未再測定)。常に exit 0。
gen_ir2 の ldfix は capstone+pefile が無いと黙ってスキップされる (§10 未解決の末尾)。PE は `/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin` 固定 (runner では symlink)。

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

survey の ok / trap 数は `function_417b70` 転記 (#130) 前の値。転記後の件数と trap の個別原因は [trap_triage/REPORT.md](trap_triage/REPORT.md)。

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

`M11_LB_BASE` (既定 0 = LVA=RVA / `0x10000` で LVA=RVA+0x10000) で全層 (image_gen / data_gen / passes / ov.c / rt.c / build / ldfix) を切替可能にした。既定 0 は従来と byte 一致。
**全文 (層ごとの変更表・静的層実測・IAT 738 スロット・LB=0 vs 0x10000 の `m11_e2e.sh` 実測・未検証) は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) に分割移動 (250 行上限, 内容は無変更)。**

## 9. sigfix 0 詰めの計測・機械語分類・定数復元 (#131, 部分達成)

既知類型との関係: 該当 (icall §4 の `callsite_arg_drop` = liftdiff 分類、`ldfix/REPORT_APPENDIX_AB.md` 優先 1)。`docs/DEFECTS.md` D1〜D16 に直接の行は無く、D7 (stack 引数のずれ) は別件 (新規行案は下記)。

### 計測 (コミット済み HEAD `3e49295`, `bash tools/m11/m11_sigfix_stats.sh`, 3.50 / 3.49 / 3.48 秒, load 0.52, n=3 直列)
単位: **0 詰め site** = `m11_post.py` sigfix が「call site の実引数数 < callee 定義の引数数」で書換えた call (分母: sigfix 書換え 6,675 site)。**0 詰め引数** = 補われた引数の総数。集計は `m11_post.py --pads`。

| 項目 | 実測 |
|---|---|
| 0 詰め site / 0 詰め引数 | **1,049 site / 2,064 引数** (217 callee / 475 caller。位置 0..3 = 1,892、位置 4 以降 (stack) = 172) |
| 既定出力 | 従来の `work/boot_final3.ll` と `cmp` byte 一致 (計測追加で出力不変) |
| 機械語と突合できた site | 1,004 / 1,049 (`no_pdata` 23 = caller が .pdata 区間外、`unmatched` 22 = IR の callee 呼出し数と機械語の直接 call 数が不一致で k 番目の対応が取れない) |

突合済み 1,004 site の 0 詰め引数 1,963 の分類 (`m11_argrecover.py`, capstone の線型 disasm。Win64: rcx/rdx/r8/r9 → `[rsp+0x20+8(i-4)]`):

| 分類 | 引数数 | 意味 |
|---|---:|---|
| callee_unused | 313 | callee 入口の直線部で読む前に全幅書込み (stack 引数は callee 全体に読出し無し)。**0 詰めは無害** |
| set_const | 18 | caller の直前窓 (同一基本ブロック) で定数代入。**復元済み** (`M11_SIGFIX_RECOVER=1`) |
| set_const_xmm_callee | 48 | 定数代入だが callee が xmm0..3 を引数に読む。復元しない (下記退行) |
| set_other | 378 / stack_set_other 32 | 窓内で非定数 (reg/メモリ由来) を代入。SSA 値との対応づけが必要で**未復元** |
| inherit | 1,172 | 窓内で未代入 (caller 引数の素通し/遠方 def)。**未復元** |
| callee_nopdata | 2 | callee が .pdata 外 |

**削減**: 0 詰め引数 2,064 のうち 18 (0.87%) を実値に置換、313 (15.2%) は無害と判定。残り (set_other 378 + stack_set_other 32 + inherit 1,172 + xmm 48 + nopdata 2 + 未突合 101) は意味未保証のまま。残りの site 別一覧: `results/sigfix_zeropad_remaining.tsv` (1,049 行, 引数ごとの分類付き)。1 site が全引数 callee_unused or set_const で**完全解決**するのは 31 site。

### 検証 (実測)
| 項目 | 結果 |
|---|---|
| 別アルゴリズム検算 `m11_argrecover_verify.py` (capstone の regs_access を使わず op_str の文字列で後ろ向き走査) | 復元 18 件が 18/18 一致 (初版 63 件では xor r9,r9 の 64bit 形を検算側が拾えず 10 件不一致 → 検算側の誤りと機械語で確認して修正し 63/63) |
| ネガティブコントロール (値を 3 件 +1) | 15/18 一致・不一致 3 で exit 1 |
| `m11_e2e.sh` (HEAD `3e49295`, `M11_SIGFIX_RECOVER=1`, 31.3 秒 (増分), load 0.88) | stage 4/6, 通常起動 17/942, survey **ok 812 / trap 83 / miss 46 / noproc 1** = 復元なし (60.6 秒, 全 obj 再生成) と同一。trap 内訳 OOB 34 / Halt0 48 / abort 1 も同一。unit 別 (942 本) 比較で差 0 |
| 初版 (定数 63 件復元) | survey **ok 809 / trap 86** に**退行** (unit 838, 882, 885: ok → OOB)。二分探索で `function_c349a0` → `function_6a3d50` の 1 site (rcx=`lea` の ptr 定数) に特定。callee は xmm1..3 を引数に読むが IR に xmm 引数が無く 0 になる (推定: 実在オブジェクトへ xmm=0 で書込みが進み OOB)。xmm 引数を読む callee は部分復元しない規則を追加し、同等に戻った |

つまり**定数復元は survey の数値を改善しなかった** (18 件は ok/trap どの unit にも影響しない)。意味補完の本体 (set_other / inherit の 1,550 引数) は未達。

### 使い方・成果物
* `m11_post.py --pads P.json` (0 詰め site 一覧出力) / `--fixes F.json` (復元適用)。`m11_argrecover.py` (分類+fix 生成)、`m11_argrecover_verify.py` (検算)、`m11_sigfix_stats.sh` (1 コマンド再現)。
* `M11_SIGFIX_RECOVER=1 bash m11_e2e.sh` で復元を有効化 (既定 0 = 従来と byte 一致)。`M11_SURVEY_UNITS=<path>` で survey が unit 別結果 JSON を出す。
* runner では `m11_e2e.sh` の PE パスが `/home/ubuntu/work/analysis/win64/extracted` ハードコードのため symlink で回避 (`m11_build.sh` は `FL_WIN64_DIR` 参照)。

### 新規類型の行案 (DEFECTS.md 形式; 直接編集は PM 判断)
| 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| 0 詰め引数を一部だけ実値化すると退行 | callee が xmm 引数 (IR に現れない) を読むのに整数引数だけ実値化し、callee が実オブジェクトを触って OOB | unit 838/882/885 ok→OOB (survey) | survey の unit 別差分 + 二分探索 | xmm 引数を読む callee は復元対象外 (本 PR) |

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| set_other 410 / inherit 1,172 引数の復元 (機械語 reg → IR SSA 値対応のデータフロー; #90 の間接 call 復元と共通基盤) | 0 詰めの大半が意味未保証のまま | #131 に残 (Refs)。新規子チケットは PM 起票 |
| xmm 引数 (xmm_arg_drop) の復元 (IR に xmm 引数が無い) | xmm を読む callee では整数引数だけ復元できない (48 引数) | #131 コメントで PM に提案 |
| `unmatched` 22 / `no_pdata` 23 site | 突合不能 | 同上 |
| #122 差分ハーネスで 0 詰め箇所を優先検証 | 未実施 (本 PR は survey の unit 比較まで) | #131 コメント |

## 10. #132: unit #18 OOB の真因解消 (通常起動 17 → 22 unit)

既知類型との関係: DEFECTS.md D7/D10 (alloca 縮退) の変種 (callee へ escape した stack_var) + D1 系 (旧値 load 脱落, `_UStrAsg` と同型) + D4 (`410b10` の `[obj]` deref 脱落)。

**起点 commit `b760fa2`** (本 PR の最終コード = origin/main `c1e4105` + 本 PR; 以降の commit は docs のみ)。`bash tools/m11/m11_e2e.sh` (work-m11 / work-liftdiff 展開済み, PE は fl-win64 の
`block00031_PE.bin`, capstone+pefile 入り venv で gen_ir2 の ldfix が有効, 4 vCPU runner)。load average = `/proc/loadavg` の 1 分値 (開始→終了; 開始値は直前の作業を含む)。

| commit | 内容 | units_run | 停止理由 (通常起動) | survey ok/trap/miss/noproc | trap 内訳 | GetMem/FreeMem | 所要 / load |
|---|---|---|---|---|---|---|---|
| `2c23bef` | 本 PR 初版 (旧 main 0a9e9d3 上) | 22/942 | DllMain attach 完走 (longjmp 経路) | 817/78/46/1 | halt0 39 + OOB 39 | 28/20 | 100 s / 1.06→1.26 (並行 2 本) |
| `0f22d9c` | main (#414/#447/#481 後) | 17/942 | OOB | 839/56/46/1 | halt0 32 + OOB 24 | 16/1 | 46 s / 1.06→1.65 (並行 2 本) |
| `6ad441d` | 0f22d9c + R8 + 3 override (410b10 無し) | 17/942 | OOB | 841/54/46/1 | halt0 32 + OOB 22 | 8/1 | 45.7 s / 0.26→0.72 |
| `a71a404` | 6ad441d + 410b10 転記 | 22/942 | DllMain attach 完走 | 809/86/46/1 | halt0 72 + OOB 14 | 33/20 | 50.6 s / 0.12→0.66 |
| `c1e4105` | main (#491/#496/#500 後 = 現 origin/main) | 17/942 | OOB | 849/43/49/1 | halt0 17 + OOB 26 | 16/1 | 43 s / 0.51→1.97 (手動 gen_ir2 と並行) |
| **`b760fa2`** | **最終 HEAD** (c1e4105 + 本 PR) | **22/942** | **DllMain attach 完走 (longjmp 経路)** | **816/79/46/1** | halt0 65 + OOB 14 | 33/20 | 50.5 s (gen_ir2+ldfix+alloca+build 込み) / 1.36→1.77; 以降 29.3 / 29.4 / 29.6 s / 1.77→1.54, 1.54→1.32, 1.32→1.20 |
| (NC) `b760fa2` − 410b10 | ネガティブコントロール | 17/942 | OOB | 850/45/46/1 | halt0 20 + OOB 25 | 8/1 | 49 s / 1.18→1.28 |

reached_stage は全行 4/6 (stage 5 未達)。最終 HEAD は 5 回測定 (gen_ir2 から 2 回 + 増分 3 回) すべて units_run 22 / survey 816/79/46/1 / halt0 65 + OOB 14 で一致 (変動なし)。

- 解消したのは **unit #18 の OOB** であり、unit #23 (0x467f00) の **Delphi 例外 (45a2a0, 0xEEDFADE) → Halt0 は未解消** (旧版の表の「例外なし」は誤り)。停止理由「DllMain attach 完走」は Halt0 → longjmp 経路の判定。
- PR 本文の「コードは 499bdfa と同一」は誤りだった。数値の測定コードは上表の commit ごとに別物 (`2c23bef` = 499bdfa と REPORT のみ差。最終は main merge + `410b10` 転記を含む)。
- 最終 HEAD の survey ok (816) は main (849) より少ない。survey は 942 unit を 1 プロセスで通算実行し `VirtualFree` が no-op (leak) のため、VirtualAlloc 累計が上限 (1,490〜1,502 MB) に達すると
  `[m11][VA] OOM` (calloc 失敗 → NULL) になる。この OOM の回数は NC 3 回 (VirtualAlloc 1,101 回) に対し最終 HEAD 55 回 (1,199 回)。`6ad441d` → `a71a404` の unit 別比較 (`M11_SURVEY_UNITS`) は
  ok→trap 33 本 / trap→ok 1 本で、ok→trap の 4 本 (unit 235/265/276/313) のスタックは 409410/409470 (GetMem/ReallocMem) → 409730 (Error) → 412a40 → 4128b0 (Halt0) = GetMem 失敗 → Error → Halt0 と整合。
  unit #18 が完走して消費が増えたためと**推定**するが、OOM を除いた意味の退行の有無は**未切り分け** (起票: #132)。

**真因 (実測)**: 44bb70 の record (392B, CAB-129 で拡幅済) の +16 が、直前に呼ぶ `function_44bae0` の呼出し前後で 0 → 0x100000001 に変化
(`m11_site` を IR に埋めて前後値を実測)。44bae0 の `stack_var_-88` が `alloca i64` (8B) だが、`call 44ba50(ptr)` で escape し
callee が `[rcx+0x2c..0x3e]` (GetCPInfo の LeadByte 表) に書くため、呼出し元フレーム (= 44bb70 の record) を破壊していた。

修正 (4 点):
1. `alloca/m11_alloca.py` **R8**: escape する `stack_var_-N` を「次の stack_var までの間隔」に拡幅 (**サイズを供給しない推定型の規則**; 契約・数値・過大拡幅の注意は `alloca/REPORT.md` §2)。
   gen_ir2 の素の IR に適用して 4,077 サイト → 2,408 alloca / 1,347 関数, +1,153,849 B stack (最終 HEAD で実測)。R8 だけでは OOB 解消のみ (units_run 17 のまま, unit #18 が Halt0 へ)。
2. `m11_build.sh`: alloca pass を build 時に常設 (idempotent, 内容が同じなら mtime を触らない)。`m11_e2e.sh` の既定経路で pass が掛かる。
3. `m11_ov.c`: `function_412d60` (`_UStrClr`) / `418190` (`_LStrArrayClr` 系) を C 転記 (RetDec が `mov rax,[rbx]` 型の旧値 load を脱落, D1 系)。
   `_CopyArray` 416db0 も初版で転記したが (kind の `movzx rcx,[r8]` 脱落が unit #18 の Halt0 原因)、main の #417 (#496) が同関数を kind 12 (416720 の間接 call) 込みで転記したため、
   merge で本 PR 側を削除し main 版を採用した (kind 12 が src を渡さない Copilot 指摘は main 版で解消)。
4. `m11_ov.c`: `function_410b10` (TMonitor の GetMonitor 相当) を C 転記 (`a71a404`)。RetDec が `mov rax,[rcx]` (obj → VMT) を落とし `[obj-0x80]` を読む (D4)。
   旧 main は `_ClassCreate` が TClass 自身を返したため偶然 InstanceSize になっていた。40fb40 で実オブジェクトが作られると `[obj-0x80]` がヒープ上の任意値になり、
   `410820` (TMonitor.Enter) が LockCount=1 / Recursion=1 / Owner を FastMM の小ブロックプールヘッダ (0x10bd1990: BlockType 0xfa5148 → 0x100000001) に書き、後の `_UStrClr` → FreeMem が OOB (`6ad441d` の停止)。
   逆アセンブル 0x410b10〜0x410b81 と突合。

ネガティブコントロール (実測): (a) 本 PR 無しの main `c1e4105` = units_run 17 + OOB。(b) 最終 HEAD から 4 の `410b10` だけ外した (NC) = units_run 17 + OOB (停止は 455790 → 44bb70 → 446400 → 447860 → 412d60 → 409440 → 407e20; `6ad441d` で同じ停止を確認)。
修正 1〜3 を個別に外した切り分けは**現 main 上では未実施** (旧 main 上の実測: 3 点を外すと units_run 17 + OOB)。検証範囲外: 417b70 / 409470 / 410320 / 40fb40 / 416db0 の機械語突合 (main 側の転記; 本 PR の差分ではない)。

**次 blocker (unit #23 = 0x467f00)**: `467f00 → 467c40 → 45a640 → 45a2a0 → 411e80 → 411d20 → 412a60 → Halt0`。467c40 は
`call [rax]` (IAT 経由の Win32 API, `mov ecx,eax` で戻り値を 45a640 に渡す) の結果で `45a640(ecx, dx=11, r8w=8)` を呼び、ecx が 0 以外・
`0x7ffdfffb` 系でない値のとき 45a2a0 (例外送出, 0xEEDFADE) に進む。`467c40` の IR には間接 call が **0 件** (機械語 0x467cc9 `call [rax]` / 0x467d5d `call [rax]` が丸ごと脱落 = D15 型, `work/icall_audit.json` の
`capstone_fns_with_indirect_call` 系と同じ現象)。脱落した戻り値の代わりに `45a640` へ未定義値 (ecx) が渡り例外送出へ進む可能性が高い (推定)。
`[rip+0x117be27]` の指す IAT スロットの import 名は未特定。

外した内容 (4c3baa4 の 467c40 間接 call 復元・boot5 25 関数 lift・配線 / faee5b6 の 417b70・409470 転記・BSTR スタブ) は #414/#447/#481 と重複するため本 PR に含めない。**#490 ([M11-N15]) で追跡**。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit #23 (0x467f00) の Delphi 例外 → Halt0 (467c40 の脱落した間接 call 0x467cc9 / 0x467d5d の復元・boot5) | 通常起動 22 で停止、stage 5/6 未達 | **#490** (旧 4c3baa4 の内容) |
| 417b70 / 409470 の転記・BSTR alloc スタブ (旧 faee5b6) | main 側の転記と重複のため外した。整合の確認が要る | #490 |
| survey の VirtualFree no-op による leak と OOM (`used=1490MB` で NULL → Halt0, 最終 HEAD 55 回) | survey の ok/trap 数がメモリ上限依存で、意味の退行と区別できない | #132 に継続 (VirtualFree の実解放を提案) |
| survey trap 79 (halt0 65 / OOB 14)・closure 外 46 | stage 5 判定 (survey trap 無し) 未達 | #132 に継続 |
| 巨大 VirtualAlloc 要求 (355MB×2, unit #18 のサイズ算出の未初期化値) | 通常起動で 711.7MB 確保 (`alloca/REPORT.md` 残置 #5) | #132 に継続 |
| `m11_site` 型の診断 (IR へ guest VA を埋める) が m11 に無い | 反復が手作業 | boot/dbg_lift.py (flelift/boot) の m11 版を要検討 |
| 素材 tarball に `ir_lb_base.stamp` が無く初回 e2e は必ず gen_ir2 が走る。gen_ir2 は capstone/pefile が無いと ldfix を黙ってスキップする (WARNING のみ) | 素材展開直後の数値が ldfix 有無で変わる (`6ad441d` で無し: survey 839/56/46/1、有り: 841/54/46/1) | #132 に継続 (e2e の前提チェック追加を提案) |
