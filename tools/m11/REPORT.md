# M11 REPORT — FLEngine_x64.dll 部分起動 PoC (audio/GUI なし)

**判定: 部分達成** (到達 stage 4/6)。`entry_point`(DllMain attach) → `_StartLib` → `_InitLib` → `InitUnits` が
wasm 上で動作し、**FastMM4 が実際に GetMem → VirtualAlloc でプールを確保するところまで**は実測で到達。
ただし 942 unit の初期化は通常起動で **unit 57 (VA 0x16fde0) の後に Halt0 → longjmp で停止** (完了 56 unit = units_run 53 + units_skipped 3。§14, #134)。stage 5 (survey trap 無し完走) と stage 6 (DllMain 正常 return) は未達。
(下の §1 表と §2〜§8 は #132 以前 = unit #18 OOB 時点の実測。最新値は §14、survey の OOM/clobber 分離後の値は §12、#516 qstore 後は §13。§10 は #132 時点 (`b760fa2`) の記録。)

再現: `bash tools/m11/m11_e2e.sh` (work/ があれば増分 build。実測値は §14)。`--full` は RetDec lift から全再生成 (旧記載「約 10 分」は本 PR で未再測定)。常に exit 0。
gen_ir2 の ldfix は capstone+pefile が無いと黙ってスキップされる (§10 未解決の末尾)。PE は `M11_PE` / `FL_WIN64_DIR` で指定する (`docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin`。`m11_e2e.sh` の既定値だけが repo 外の固定パス)。

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

* 通常起動 unit #18 以降: `446400` (ロケール/書式設定読込) 内の `_UStrAsg` が OOB。`0x450560` の誤 lift は修正済だが停止位置は不変 (#2556: 本番 IR は fix_450560 を常設し C 転記は既定 OFF。`REPORT_2556.md`)。
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

RTL の範囲確定と RetDec/x64c 別の liftdiff 採点 (#129): `tools/m11/rtl/REPORT.md`。

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

0 詰め 1,049 site / 2,064 引数 (単位: sigfix が callee 定義より実引数の少ない call を書換えた site / 補った引数数)。うち 18 引数を機械語突合で実値に復元 (`M11_SIGFIX_RECOVER=1`)、survey の数値は不変。
**全文 (計測表・分類・検算・退行の二分探索・新規類型の行案・未解決) は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) に分割移動 (250 行上限, 内容は無変更)。** 差分ハーネスによる 0 詰め site の判定 (一致 174 / 不一致 289 / 未到達 586) は [REPORT_N55.md](REPORT_N55.md)。#953 の理由別分類と退行検査 (ok 870 = 870, 18/18 検算) は [REPORT_N53.md](REPORT_N53.md)。

## 10. #132: unit #18 OOB の真因解消 (通常起動 17 → 22 unit)

既知類型との関係: DEFECTS.md D7/D10 (alloca 縮退) の変種 (callee へ escape した stack_var) + D1 系 (旧値 load 脱落, `_UStrAsg` と同型) + D4 (`410b10` の `[obj]` deref 脱落)。

**起点 commit `b760fa2`** (本 PR の最終コード = origin/main `c1e4105` + 本 PR; 以降の commit は docs のみ)。`bash tools/m11/m11_e2e.sh` (work-m11 / work-liftdiff 展開済み, PE は fl-win64 の
`block00031_PE.bin`, capstone+pefile 入り venv で gen_ir2 の ldfix が有効, 4 vCPU runner)。load average = `/proc/loadavg` の 1 分値 (開始→終了; 開始値は直前の作業を含む)。

commit 別の測定表 (`2c23bef`〜`b760fa2`・NC) と注記は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §10a に分割移動 (250 行上限, 内容は無変更)。

**真因・修正 4 点・NC・次 blocker (unit #23)・外した内容 (#490 で追跡) の全文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §10b に分割移動 (250 行上限, 内容は無変更)。** 要点: 44bb70 の record 破壊 (44bae0 の `alloca i64` が callee へ escape) を R8 で拡幅、`412d60`/`418190`/`410b10` を C 転記して通常起動 17 → 22 unit。次 blocker は unit #23 (0x467f00) の Delphi 例外 → Halt0 (#490)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit #23 (0x467f00) の Delphi 例外 → Halt0 (467c40 の脱落した間接 call 0x467cc9 / 0x467d5d の復元・boot5) | 通常起動 22 で停止、stage 5/6 未達 | **#490** (旧 4c3baa4 の内容) |
| 417b70 / 409470 の転記・BSTR alloc スタブ (旧 faee5b6) | main 側の転記と重複のため外した。整合の確認が要る | #490 |
| survey の VirtualFree no-op による leak と OOM (`used=1490MB` で NULL → Halt0, 最終 HEAD 55 回) | survey の ok/trap 数がメモリ上限依存で、意味の退行と区別できない | #132 に継続 (VirtualFree の実解放を提案) |
| survey trap 79 (halt0 65 / OOB 14)・closure 外 46 | stage 5 判定 (survey trap 無し) 未達 | #132 に継続 |
| 巨大 VirtualAlloc 要求 (355MB×2, unit #18 のサイズ算出の未初期化値) | 通常起動で 711.7MB 確保 (`alloca/REPORT.md` 残置 #5) | #132 に継続 |
| `m11_site` 型の診断 (IR へ guest VA を埋める) が m11 に無い | 反復が手作業 | boot/dbg_lift.py (flelift/boot) の m11 版を要検討 |
| 素材 tarball に `ir_lb_base.stamp` が無く初回 e2e は必ず gen_ir2 が走る。gen_ir2 は capstone/pefile が無いと ldfix を黙ってスキップする (WARNING のみ) | 素材展開直後の数値が ldfix 有無で変わる (`6ad441d` で無し: survey 839/56/46/1、有り: 841/54/46/1) | #132 に継続 (e2e の前提チェック追加を提案) |

## 11. #572 [M11-N21]: m11_data_gen.py の DIR64 補正境界 = off-by-one (確定・修正済み)

`lo <= r < lo+len-8` は `<=` が正しい。DIR64 278,531 件のうち落ちるのは `.data` 末尾 RVA `0x11e5000` (値 `0x425f00`, 実行時に unit #12 が表経由で読む `TResStringRec` 風データへのポインタ) の 1 件のみ。`<=` に修正し、`m11_reloc_gate.sh` (ネガコン付き, 不合格で非 0) で補正漏れ 0 を確認。e2e の `M11_SUMMARY` は修正前後で完全一致 (units_run 22 / survey ok 816 trap 79 miss 46)。実行時に観測できた結果 (dest の最終値) は修正前後で同じで、現時点では潜在バグ。全文・実測・未解決 (m6 / liftlib に同条件が複製) は **`REPORT_N21.md`**。

## 12. #513: survey の VirtualFree 実解放・OOM/clobber 分離と「ok 849→816」の切り分け

既知類型との関係: DEFECTS.md に直接の行なし (測定バイアス = 新規類型案を末尾)。unit 87/898 は D1 系 (旧値 load 脱落を C 転記で直した副作用), 巨大 alloc の size は D15 (間接 call 脱落) の疑い (推定)。
**起点**: PR #411 (`132-m11-stage5`) の上で作業した (#411 は merge 済み `6a0a8c8`。測定の起点は #411 の最終 HEAD `8059197`)。コード commit `c4a3f72` (= `8059197` + 本 issue の 3 commit; 以降は docs と診断スクリプト `m11_unit_imgdiff.mjs` の追加のみ)。比較対象 main = `c1e4105`。runner 4 vCPU, work-m11/work-liftdiff 展開済み, PE は fl-win64 の `block00031_PE.bin`, capstone+pefile 入り venv。

**結論**: (1) 見かけの退行の主因は VirtualFree の leak ではない。**survey 中 `VirtualFree` は 0 回** (実解放 0 / 表に無い解放 0 / decommit 0) で、実解放だけでは数値は動かない。(2) 真因は **unit 101 (VA 0x1de960) 1 本が VirtualAlloc 1,477,181,440 B (survey 累計 1,490,026,496 B の 99.14%) を消費**
(GetMem 23,056,285 回・FreeMem 0 回・1 回あたり 64.07 B) して wasm 上限を使い切り、後続 54 unit が巻き添えで OOM→NULL→Halt0 になっていたこと。(3) unit 単位の上限 + oom/clobber 分類で分離すると **ok 816 → 852** (36 unit は OOM の巻き添えだった)。

実装 (`m11_rt.c` / `m11_survey.mjs` / `m11_judge.py`): ① `VirtualAlloc` が (基底, calloc 生ポインタ, 長さ) を表に持ち, `VirtualFree(MEM_RELEASE)` で実際に free (DECOMMIT は no-op, 表に無い解放は 1 を返して計数)。② unit ごとの VA 累計上限 `M11_VA_UNIT_BUDGET_MB` (既定 256, 0 = 旧挙動)。超過は NULL (OOM) で, unit 実行中に NULL が出た trap を `oom` に分類 (`trap_oom` / `trap_other` / `oom_units`)。
③ unit 実行後に InitTable (先頭・末尾 proc VA) が壊れていたら実行前の image を書き戻し `clobber` に分類 (検出は InitTable のみ)。④ 診断: `M11_SURVEY_COST` (unit 別 VA/GetMem), `M11_SURVEY_STACK`, `M11_VA_BIGTRACE`, `m11_unit_imgdiff.mjs` (unit 前後の image 差分), `m11_wasmnames.py` (wabt 無しの関数名注釈)。

### 実測 (survey 単体 `node m11_survey.mjs`。PR HEAD 既定 7.27〜7.36 秒 (n=5, load 0.59→0.93) / 上限 0・1024MB 19.7〜19.9 秒 (n=5) / main 1024MB 7.00〜7.11 秒 (n=3))
| 構成 | ok | trap = oom + 他 | clobber | miss | noproc | VA 累計 / peak | OOM |
|---|---:|---|---:|---:|---:|---|---:|
| PR HEAD・上限なし (= 旧測定 NC) | 816 | 79 = 55 + 24 | 0 | 46 | 1 | 1,490.0 MB | 55 |
| PR HEAD・既定 256MB (n=3 完全一致) | **852** | 42 = 1 + 41 | 1 | 46 | 1 | 556.2 MB | 1 |
| PR HEAD・1024MB | 852 | 42 = 1 + 41 | 1 | 46 | 1 | 1,362.3 MB | 1 |
| PR HEAD・既定 + `M11_VFREE_NOOP=1` (NC) | 852 | 42 = 1 + 41 | 1 | 46 | 1 | 556.2 MB (実解放 0 = 差なし) | 1 |
| main `c1e4105`・上限なし / 1024MB | 849 | 43 = 0 + 43 | 0 | 49 | 1 | 822.4 MB | 0 |
| main・既定 256MB | 848 | 44 = 1 + 43 | 0 | 49 | 1 | 87.7 MB | 1 (unit 368 の 700.7MB 要求が上限超過) |

`m11_e2e.sh` (増分 build): コード HEAD `c4a3f72` で 25.54 秒 (load 0.38→0.59, n=1)、直前 `08cc36c` (差は survey の stack 出力のみ) で 25.55 / 25.52 / 25.44 秒 (load 0.24→0.91, n=3)。いずれも stage 4/6・通常起動 22 unit・survey 852/42(oom 1)/clobber 1/46/1。通常起動の VirtualAlloc は 1 回 (1.3 MB)。**origin/main `ef3608c` を取り込んだ merge 後 HEAD `ec4807f`** (4 vCPU, PE=fl-win64 `block00031_PE.bin`, capstone+pefile 入り venv): 全 obj 再生成 45.87 秒 (load 0.50→0.83) / 増分 20.86・20.71 秒 (load 0.78→0.89, n=2) で結果は上と完全一致 (wasm 6,025,415 B)。`m11_vfree_test.mjs` PASS (OOM 0, 解放 301 回) / `M11_VFREE_NOOP=1` NC_OK (OOM 116, 解放 0)、survey 上限なし (`M11_VA_UNIT_BUDGET_MB=0`) は ok 816 / trap 79 = oom 55 + 24 / 13.65 秒 (n=1)。
検算 (別算法): unit 別 VA の総和 = 全体 1,490,026,496 B (差 0), `oom>0` の unit 55 = 'oom' ラベル 55 = `va_oom` 55, 次に大きい unit は 11,534,336 B (0x145d10)。

### unit 単位の比較 (main と PR HEAD, どちらも上限 1024MB = OOM 無し側に揃える。942 本中 933 本同一)
| unit (idx / RVA) | main → PR | 内容 |
|---|---|---|
| 17 / 0x55790 | trap → ok | #411 の本題 (unit #18 OOB 解消) |
| 138 / 0x243270 | trap → ok | 原因未確認 (main→PR で ok 化) |
| 86 / 0x19b100, 357 / 0x55b400, 496 / 0x6de4d0 | miss → ok | closure 外 call が出なくなった。原因未確認 |
| **87 / 0x19f9a0** | **ok → trap** | OOB @ `function_418190` (#411 の C 転記) — OOM 無関係の**実退行** |
| **898 / 0xf06110** | **ok → trap** | OOB @ `function_412d60` (#411 の C 転記, 呼出元 12f98f0←1305fd0) — **実退行** |
| 101 / 0x1de960 | trap → oom | main は OOB @ 4fa210。PR は進んで 4fa210 (list 走査 loop) → 47a250 (例外生成: `TList.Error` 相当) → 448d40 (`Exception.Create`→`_ClassCreate`→GetMem) の連鎖で GetMem 23M 回 (loop が毎周回 例外 object を作る**推定**; 機械語は逆アセンブルで確認, 周回は未観測) → OOM で Halt0 |
| 144 / 0x25c540 | trap → clobber | main は OOB @ 414ad0。PR は進んで **image の InitTable (ptr/count/units) を 0 に**し (`m11_unit_imgdiff.mjs 144`: image 14,873,449 B / 1,638,708 range が変化, 範囲 0x8〜0x1579044。対照 unit 143 は 5 B / 2 range。main 取込み後の merge HEAD では 14,873,452 B / 1,638,707 range・対照 143 は 5 B / 2 range で不変, 3 B 差の原因は未切り分け (#572 の DIR64 補正が image 初期値を変えた影響と推定)), 最後は FastMM で OOB。**旧測定では OOM で Halt0 になり隠れていた** |

つまり ok→非 ok の退行は **OOM 除外後 2 本 (87, 898)** のみで, 849→816 の 33 本差は大半が OOM の巻き添えだった (旧 `6ad441d→a71a404` の ok→trap 33 本の内訳も同型と推定。未再測)。

### 巨大 VirtualAlloc の呼出元と必要性 (確定: 全文は `REPORT_APPENDIX.md` §12b) — 現 HEAD では通常起動の VirtualAlloc は 1 回 (1.3 MB) で 355MB×2 は再現しない。survey の 64MB 以上の要求は 2 unit だけで、**どちらも lift 欠陥の産物で不要**:
* unit 368 (`980ed0` → `981000` → `409470`): 190.6 MB (本 HEAD) / 700.7 MB (main `c1e4105`)。`980ed0` の `inttoptr i64 22954112` が VA→LVA 未 remap (正しくは 18759808) で、n = linear 0 の残骸 (0x2fa020 / 0x10af2ba8) → 式 8×((8n+31)&~31) の 64KB 丸めが両値と一致。1 行直すと要求が消える。
* unit 888 (`129f140` → `417fc0` → `417b70`): 71.3 MB。`ptrtoint(inttoptr 18683649)` = 変数 [0x11d1700] のアドレス+1 を count に渡す load 脱落 (正しい値 65 → 260 B)。3 行直すと要求が消える。両方直しても survey の unit 別ラベル 942 本は不変。#516/PR #552 (qstore) の検出 420 行に該当関数なし、#418 (409470 ハング) は 410320 脱落で無関係。

### ネガティブコントロール (実測)
* 単体 `node m11_vfree_test.mjs` (3 周 × 8MB × 100 = 累計 2.4 GB を確保→解放): 実解放 = **PASS** (OOM 0, 解放 301 回, 周ごと live 0 MB, 二重解放と未知 ptr は 2 回計数)。`M11_VFREE_NOOP=1` (解放しない) = **OOM 116 回・live 1,544.6 MB** (期待どおり NC_OK)。0.51 秒 (load 0.88)。
* survey: 上限を外す (`M11_VA_UNIT_BUDGET_MB=0`) と OOM 55 / ok 816 / VA 1,490.0 MB に戻る (NC)。`M11_VFREE_NOOP=1` は survey では**差が出ない** (VirtualFree が呼ばれないため。受入条件「解放を無効化すると OOM が戻る」は survey では成り立たず, 単体テストで成立)。
* 検証範囲外: FastMM が大ブロック/プール解放で VirtualFree を呼ぶ経路の実行 (survey では FreeMem 37 回中 0 回), 全 unit を通した clobber 検出 (InitTable 以外の破壊は未検出)。

新規類型の行案 (DEFECTS.md 形式; 直接編集は PM 判断) は 250 行上限のため `REPORT_APPENDIX.md` §12 に無変更で分割移動した。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 101 の `4fa210` list 走査が `47a250` (例外生成) を 23M 回繰り返す根因 (list の index/Count の誤 lift か, raise が戻る経路か) | PR HEAD の survey が 1 unit で 256MB (上限なし 1.48GB) 消費 | 新規子チケット案 [M11-N17] (PM 起票), #132 にコメント |
| unit 144 の image 破壊 (書込み元関数と, 0 埋めの範囲・値) | clobber 1 unit。他 unit の結果に影響し得る | 同上 |
| #411 の `418190` / `412d60` 転記が unit 87 / 898 で OOB (ok→trap 2 本) | main に入っている実退行 (#411 は merge 済み) | #132 に継続 (#411 は merge 済みで「PR 内で修正」は不可。新規子チケットを PM が起票) |
| 10 進 `inttoptr` 命令 4,364 件 (942 関数) の VA→LVA 未 remap (368 の n の原因と同類型)。`M11_M2P=1` は survey が 90 秒で完走しない。仕分けは [REPORT_N1318.md](REPORT_N1318.md) (VA→LVA 4363 件・QPF 整数 1 件は remap してはならない) | 巨大 alloc 2 件は上の個別修正で消える。全件 remap は未解決 | #417 |
| survey の clobber 検出は InitTable のみ | 他の image 破壊は ok に見える | #132 |

## 13. #516 [M11-N18]: 64bit スタック局所の即値 store が 4B に縮む欠陥 (DEFECTS.md D17, idx 87/898)

機械語 `mov qword [rbp+X], imm` (8B) が IR で `store ptr null` / `store i32 imm` (wasm32 で 4B) に縮み、上位 4B 未初期化のまま C 転記 `Q(dest)` が読んで OOB (idx 87 = `418190`, idx 898 = `412d60`, idx 58–63 = `417b70` の `Q(a)`、後者は `function_8cbb00` の 2 site)。`qstore/m11_qstore.py` が 279 site / 158 関数を `store i64` に戻す (`M11_QSTORE=0` で無効)。**#513 取り込み後の HEAD `8e5f760` の実測 (n=3 一致)**: survey NC 856/38/46/1 (clobber 1) → 修復 864/31/46/1 (clobber 0)、ラベル差 9 unit (58–63・87・898 が trap→ok、144 が clobber→trap)。58–63 は `8cbb00` の 2 site だけを除外すると trap に戻り (858/37/46/1) qstore の効果と確定、144 は別 site (未切り分け)。数値・site 一覧・再現・未解決は [qstore/REPORT.md](qstore/REPORT.md)。

## 14. #134 [M11-N5]: unit 23 の IntToStr 表構築 OOB を解消 (通常起動 22→53 unit), judge を Halt0 早期終了と分離
通常起動 22→53 unit。judge は Halt0 早期終了と正常終了を分離 (`--require-stage`)。本文・数値表は [REPORT_N134.md](REPORT_N134.md) §14。

## 15. #680: survey 測定基準の固定化 (ldfix/qstore の fail-closed・PE パス env 化) → 本文は [REPORT_APPENDIX.md](REPORT_APPENDIX.md) §15

## 16. #490 [M11-N15]: main HEAD の 4c3baa4 / faee5b6 状態 (部分達成, 詳細は [REPORT_N15.md](REPORT_N15.md) §16)

## 17. #748 [M11-N41]: 652500 の 1 段 deref 復元 (gate 付き, 既定 0, 部分達成)
unit 149 は OFF/ON とも oob のまま。ON で kind が変わるのは unit 895 (halt0 → oob) の 1 件のみ (N748 の再測定で訂正)。既定 0 のまま。測定値・未解決・起票先は [REPORT_N748.md](REPORT_N748.md)。

## 18. #134 [M11-N5]: main `93307cc6a` の停止点 (unit 101 = VA 0x5de960 の 535c11 OOB) と e2e 期待値の更新 (部分達成)
通常起動 98 unit + skip 3 = 101 で停止 (stage 4/6)。e2e 期待値 (完了 56→101・survey 872→873) を実測へ更新。本文・切り分け・未解決は [REPORT_N134.md](REPORT_N134.md) §18。

## 19. #4011 [WIN-42]: vtable[0] 復元 `function_41a800` (gated `M11_M2V`) と QueryInterface `0x41c180` の C 転記 (部分達成)

- 変更: `m11_passes.py` `pass_m2s_fn41a800_vtable0` (既定 OFF・`M11_M2V=1` で有効)・`m11_ov.c` に `tr_41c180` / `tr_4467ac` を `disp_find` 登録。`tr_41c180` の戻り値は `test al,al` で非 0 → 0・0 → `0x80004002` (機械語 `41c180`〜`41c191` と一致)。
- 測定 commit: `71f6e449ac2218f3bff31a61e64da58c30dcee47`。以後の差分は REPORT.md のみ (`m11_ov.c` / `m11_passes.py` は差分 0)。以下は作者が同 commit で測定した値。**本 review 修正 run では再測定していない** (`work-m11` / `toolchain-retdec` が未取得で `tools/m11/work/` が無いため実行不可)。

| コマンド | rc | 所要 | 備考 |
|---|---|---|---|
| `m11_wndseed.sh` | 0 | 3 分 26 秒 | WNDCLASS-CHECK PASS |
| `m11_gen_ir2.sh` | — | 1 分 10 秒 | `ir_conditions.json` ldfix=applied |
| `m11_build.sh` (既定 OFF / `M11_M2V=1`) | 0 / 0 | 25 秒 | 両方 rc 0 |
| `tools/gui/flengine/build.sh` | 0 | 42 秒 | |
| `boot_halt_probe.mjs` | — | 0.56 秒 | |

- 製品 KPI (`M11_M2V` 既定 OFF / `=1`): units_run 109 / 109・last_unit.index0 114 (Halt0) / 114 (OOB)・icall_miss 7 / 7・threw null / `memory access out of bounds`・最初のウィンドウ 未到達 / 未到達。
- stage ログ: `[M2v] function_41a800 vtable0 restore: 1 sites` (pass が 1 箇所に適用)。
- 対応の根拠 (未独立確認): pass は `%arg2` を this (vtable 読出し元 `[rsi]`)・`%arg3` を IID として `m11_icall(vtva, arg2, ptrtoint arg3, out, ...)` に渡す。`%arg3` の下位 32 bit を判定に使っていた旧 IR と対応する。IR (`work/`) は本 run に無く、1 site 適用は作者の stage ログの記載のみで、本 run では独立確認していない。
- 受入: 1 (`last_unit.index0 > 114`) 未達 (114 で OOB)。2 (vtable[0] の戻り値判定) 部分達成 (`0x41c180` 以降の戻り値経路は未実測)。
- 未解決: unit 114 以降の OOB・`function_40fcf0` の AddRef `call [rax+8]` (`40fd3a`) 未復元 → 次の run (#4011)。受入 3 (CS-INIT 0x12bd390) は範囲外で #4031。

## 20. #4011 段 2: `pass_m2v_fn40fcf0_arg1` (gated `M11_M2V`, 既定 OFF, 受入 1 未達)

`function_40fcf0` の `function_40fd90` 呼出しの第 1 引数を `[self]` (VMT) に直す。`M11_M2V=1 M11_M2S=1` で last_unit 114→144 に前進したが OOB が残り、icall miss 7→16。「偽の前進」の疑いがあり、受入 1 は未達。測定・測定 commit・差分 0 の証跡・未解決は [REPORT_N4011.md](REPORT_N4011.md)。

## 21. #5358 [FLE-44]: function_409c80 の tail jump 誤 lift 修正 (部分達成) → [REPORT_5358.md](REPORT_5358.md)
