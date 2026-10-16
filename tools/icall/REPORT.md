# tools/icall — 間接 call/jmp 落ち監査 + 復元 pass (CAB-89)

## 0. 結論 (先出し)

- **判定: 達成**。RetDec route に「間接 call 復元 pass」を入れるだけで **OTT は native 実機械語と全 bit 一致**した (x64c.py 不使用)。
  `bash tools/icall/icall_e2e.sh` = **PASS** (#5125: before `706147914` / after `e5261de58` とも PASS・所要 1 分 55 秒 / 2 分 2 秒。付録 `REPORT_APPENDIX_5125.md`): scenario matrix **89/89 本・全 cell が native と bit 一致 (max_ulp 0), 最終 heap/obj state 差 0 qword**
  (cell 総数・内訳の正本は `tools/ott/REPORT.md` §2) (t1 標準 512 cell: zero 5 / normal 507 / **junkHi 0 / junkTiny 0**, |max| 0.2516 = native と同値)。旧 RetDec chain は同 matrix で 4,791 cell (9.5%) のみ一致。
- 手法は「**RetDec の入力 PE を decode 専用に書換える (binary pre-rewrite)**」: 間接 call/jmp を memory-ABI (固定 BLK への引数 store → 共有 stub call → 戻り load) に展開 →
  RetDec が引数の SSA 配線を普通の store として保持 → 後段で stub call を `__icall_dispatch(site_va)` に置換 (VA→関数表 = call_indirect 相当)。
  IR 後付け挿入は RetDec が register→IR 値の対応を捨てるため不採用 (§3)。
- **監査**: RetDec は間接 call を IR に **出さないのでなく decoder 段で捨てる** (`--print-after-all` で decode 直後の IR に既に無いことを確認)。実測 落ち率:
  OTT 98.4% (全 DLL), Fruity Balance 100%, Fresh Air 95.6%, Kilohearts 91.5%, **FLEngine_x64.dll 99.7% (3,832/3,844)** → 復元後 OTT/Balance/KH **0**, Fresh Air 6, **FLEngine 382 (9.9%)**。
- 副産物の新規欠陥類型 (§4): **D7 = RetDec が「live-in レジスタ経由の zero-disp 参照」の load を黙って消す** (`mov rax,[rcx]` → `rax=rcx`)。M11 が見た `_UStrAsg` 旧値読出し欠落/`mov r8d,[rcx]`→`mov r8d,ecx` と同根で、
  FLEngine closure に 12,559 命令 (OTT F: 835)。ほか comis flag 未定義 (D8)・jump table 未解決 (D10)・chained .pdata 断片 (D11)・Delphi landing pad 非到達 (D12)・MSVC CFG thunk (D13)。
- **推奨ルート (FLEngine 全体)**: **x64c 拡張 (自作 1:1 lifter を Delphi 対応)**。理由: FLEngine 340,764 命令を定数 3 行の変更で 7,031 関数 lift 済み・未対応は 1,105 site (0.32%) で内訳が全て列挙可能、
  RetDec 側は上記のように不具合が 1 つずつ差分試験でしか見つからない (§5)。RetDec+icall pass は plugin closure (liftlib 統合) と x64c の第二実装/oracle として併存。

## 1. 成果物 (tools/icall/)

| パス | 役割 |
|---|---|
| `audit_icall.py` | capstone で関数ごとの間接 call/jmp を静的に数え (recursive descent + jump table 解決 + gap sweep)、raw IR の `!insn.addr` で **site 単位**に突合 (kept / resolved_direct / other_insn / dropped)。分類: iat / rip_data / vtable / indexed / abs_mem / reg / jmptable。`--dsm` で RetDec 自身の disasm との一致も出す |
| `icall_rewrite.py` | 本体。PE に `.icall` section を足し closure 関数を再配置 (branch / rip-rel / jump table / 断片を張り直し)。site 展開・derefix・ABI 仮想化・comis・jt-chain・CFG thunk・断片 inline |
| `ir_icall_restore.py` | RetDec IR を元 VA 体系へ戻し stub call → `__icall_dispatch(site)` / `__icall_comis()` |
| `ir_flatten.py` | `@global_var_*` を絶対アドレス化 (D2 根絶) + VA shift + dispatch 表 C 生成 |
| `closure.py` / `prep_targets.py` / `roundtrip.sh` / `audit_table.py` | closure 計算 / 監査対象準備 / before→after 一括 / 表出力 |
| `rt/icall_rt.c` `rt/icall_simd_extra.c` | runtime: BLK, `__icall_dispatch` (CFG thunk 対応・fail-fast で site VA 表示), `ott_run` (matrix 互換), comis, Win32 import 最小, SSE helper 補完 |
| `ott_route.sh` / `icall_e2e.sh` | OTT RetDec route の build / 1 コマンド検証 |
| `diff/fn_diff.py` `retdec_decode_dump.py` `x64c_census.py` `x64c_fle_probe.sh` | 関数単位 native 差分 / RetDec decode 段 dump 取出し / x64c 対応度 census / x64c の FLEngine 試験 |
| `integration/` | liftlib 統合 patch + 手順 + `x64c_fle.patch` |
| `tests/test_icall.py` | 回帰 (unit + rewriter 固定値) |

生成物は `tools/icall/work/` (gitignore)。tools/m*, ott, liftlib, targets は一切変更していない (読取/実行のみ)。

## 2. 監査表 (実測; `python3 tools/icall/audit_table.py`)

全数 = 非 IAT の間接 call (IAT 呼出しは RetDec が import 名の直接 call にするため別扱い)。落ち = IR に call が無い (dropped) または call 以外の命令だけ残る (`br`/`ret`)。

| 対象 | 非IAT間接call (全数) | RetDec 素通し 落ち | 復元後 落ち | tail-jmp 落ち | jump table | gap site |
|---|--:|--:|--:|--:|--:|--:|
| OTT 全 DLL (RetDec 8,786 関数, 復元前のみ) | 4,945 | 4,867 (98.4%) | — | 399/399 | 59 中 3 | 40 |
| OTT m6 closure 166 関数 (IR 残存 0) | 74 | 67 (90.5%) | — | 5/5 | 6 中 4 | 1 |
| **OTT F 282 関数** (native coverage ∪ closure) | 81 | 70 (86.4%) | **0** | 11/11 → **0** | 1/8 → 8 展開 | 2 |
| **Fruity Balance** (Delphi framework 67 関数) | 35 | 35 (100%) | **0** | 0/0 | 0/0 | 1 |
| **Fresh Air** SlateCore 131 関数 | 91 | 87 (95.6%) | 6 (6.6%) | 5/5 → 0 | 1/2 → 2 展開 | 2 |
| **Kilohearts** HeartCore (gain+infra 196 関数) | 118 | 108 (91.5%) | **0** | 12/12 → 0 | 0/2 → 2 展開 | 7 |
| **FLEngine_x64.dll** (M11 closure 7,421 関数 / 341,713 命令) | 3,844 | **3,832 (99.7%)** | **382 (9.9%)** | 1/1 → 0 | 0/1 | 879 |

- OTT の旧 "47 関数 54 site" (R) は native 実行 75 関数の部分集合。本監査は同 75 関数で非 IAT call 49 + tail-jmp 7 + 表 2 (`work/audit_ott_native75.json`)、IR 残存 0。
- FLEngine 復元後の残 382 のうち **366 は 2 本の巨大 GUI 構築関数** (`0xc589b0` 19.6KB / `0x128f9e0` 20.7KB, 各 183 site) で RetDec が本体を途中で捨てる。残り 16 site は別の小関数。
- FLEngine **gap site 879** = control-flow 非到達コード (Delphi unwind landing pad: `mov ebx,[rax]; call [rbx-0x20]` = 仮想 dtor 呼出し等, 実測 879 中 493 がこの形) で RetDec は decode しない。RetDec dsm にも無い (879 中 2)。**間接 call 以前に「例外経路の dtor が lift されない」欠陥**。
- 復元後 FLEngine: dispatch 3,462 / comis 830 / 書換え derefix 12,559 / direct call ABI 化 30,092 / ret 7,030 / tail-jmp 22 (`work/rt_flengine/rewrite.txt`)。**FLEngine は構造検証のみ (wasm 実行は未, §6)**。

## 3. 復元 pass の設計と OTT 検証

### 3.1 なぜ IR 後付けでなく PE 書換えか (実測根拠)
1. RetDec は decoder 段 (`Input binary to LLVM IR decoding` 直後) で間接 call を **PC 更新だけ残して捨てる**。後段 pass が消すのではない (`--print-after-all` で確認, `retdec_decode_dump.py`)。
2. IR にはレジスタ名が無く (`%arg1`, `reg2mem` alloca)、target 式 `[rax+off]` の rax や引数 rcx/rdx/r8/r9/xmm の定義値を IR から安全に引けない (load は dead として既に削除済み、xmm は param 化されず `alloca` の undef load)。
3. そこで decode 専用コピーの PE で各 site を `mov r11,<operand>` + **固定 BLK へ rcx/rdx/r8/r9/xmm0-3/rax を明示 store** + `call STUB` + rax/xmm0 reload に展開。RetDec は普通の store/load として保持するので配線が自動で正しくなる。
   BLK は IR 上 `inttoptr` 定数なので後処理が単純。stub は BLK を read/write する本体にして readnone 化 (=呼出し消去/load 巻上げ) を防ぐ。
4. 復元 = stub call を `call void @__icall_dispatch(i64 <site VA>)` に置換。dispatch は BLK[0] の target を VA→関数表 (`ir_flatten --table`) で引き、未登録は **site VA を表示して fail-fast**。
5. 同じ仕掛けで closure 内の direct call / ret / prologue も BLK 経由に**仮想化** → 全 lifted 関数は `i64 f(void)` の一様 ABI。RetDec の param/return 推定 (D3: r8/r9 脱落, xmm 引数脱落) を迂回し、dispatch は signature 適合不要。
   CFG thunk (`jmp rax`) は `mov r11,rax` + 実行時 rax-in で処理。

### 3.2 OTT 検証 (`icall_e2e.sh` [4/4])
| 指標 | 旧 RetDec chain (m6–m10) | **RetDec + icall pass (本回)** | x64c (R) |
|---|--:|--:|--:|
| matrix 89 scenario 出力 cell native 一致 | 4,791 cell (9.5%) | **全 cell 一致** | 全 cell 一致 |
| ※ cell 総数 (89 scenario × 出力 cell) は正本 `tools/ott/REPORT.md` §2 参照 | | | |
| 最終 heap/obj state 差 (qword) | 260,657 | **0** | 0 |
| t1 std 512 cell | 全 0 (旧 chain は 0x326 で早期 return) | **512/512 bit-exact, junk 0** | 512/512 |
- 使う既存 pass: ir_normalize, ir5_patch (m2/m5)、SIMD helper は m11_simd2.py (署名駆動) + 補完 5 種 (`cmplesd cmpnltsd cvttpd2dq cvtpd2dq sqrtpd`)。**M8/M9/M10 の OTT 専用 hand port (ir7_argpass, ir8_valueflow, ir9_bootstraps, gate box C port 等) は不要**。
- CRT 数学 (exp/log/tan/pow) は libm 置換でなく DLL 自身の機械語を lift (D4 解消)。関数単位の native 差分は **§8 (ICALL-5)** に移した (旧記述 = tan 111/120・`1801c1240` 0/120 は §8 で原因特定・修復済み)。**matrix 89 scenario は全 bit 一致**。
- 反復の過程 (全て修復済み): rewriter の capstone `disp_size` 誤り (66-prefix SSE の rip-rel 103/916 命令が定数誤参照) → tan が桁違い、jump table 未展開で setParameter 不動作、
  `mov r11,rax` を call 後に置いて rax 喪失、chained 断片 (`0x1801207f1`) の単独関数化、closure の条件 jmp 追従漏れ。各段で `ott/diff/cmp.py` の stage 差分が原因特定に効いた
  (例: ctor 直後 obj 差 2 qword → 0, setp 段の +0x248 差 → jump table)。

## 4. 欠陥類型 (D1–D6 に追加; 実測)
| # | 欠陥 | 証拠 / 対処 |
|---|---|---|
| D1 | 間接 call/jmp 脱落 | 上表。→ 書換え+復元 |
| **D7** | **live-in レジスタ経由の zero-disp メモリ読みが消える** (`mov rax,[rcx]`→`rax=rcx`, `movss xmm0,[rcx]`→undef, `cmp [rcx],rax`→undef)。disp≠0 や計算済み base では起きない。bin2llvmir の "Constants optimization" 後に発生 (`--print-after-all`)。 | raw 試験 `work/probe/t*.py`。OTT F 835 / FLEngine 12,559 命令。→ `lea B,[B+8]; op [B-8]; lea B,[B-8]` 補償 (flag 不変, scratch 不要; base を書く命令は restore 省略)。liftlib F7 は IR 側で同欠陥を後修復している |
| D8 | comis/ucomis が void helper で CF/ZF/PF 未定義 (m6 P1 は OTT 96 site 中 18 のみ修復, 68 は no_branch, 13 は br_other) | → 2 operand を BLK へ + `__icall_comis()` が AH 形式 flag を返し `sahf` (push/pop は stack 最適化が壊す → r11 退避) 。OTT 100 / FLEngine 830 site |
| D9 | **capstone `disp_size`/`disp_offset` が 66/F2 prefix 付き SSE rip-rel で誤る** (disp_size=2) | OTT F rip-rel 916 中 103 (11%)。modrm から自前計算。**tools/plugins の fw_overlap.py/win_funcs.py/kernel_matrix.py/fw_prep.py は `disp_size==4` で disp を 0 化しており同じ穴** (子チケット) |
| D10 | `jmp reg` jump table を RetDec が switch 化できない (OTT 8 中 1, FA 2 中 1) / 表がパッチ後に壊れる | → target 列挙 + `lea r11,[T]; cmp reg,r11; je` 列へ展開 (表は元 VA のまま) |
| D11 | chained `.pdata` 断片 (UNW_FLAG_CHAININFO; 2,096 件/OTT) を RetDec は単独関数として扱い frame が壊れる | → 参照元関数へ複製 inline |
| D12 | Delphi unwind landing pad が CFG 非到達 → decode されず仮想 dtor 呼出しが消える (FLEngine 879 site) | **未対応** (§6) |
| D13 | MSVC CFG `__guard_dispatch_icall` (`call [fptr]`→`jmp rax`) | → rax-in を BLK に保持、dispatch で thunk 経由を実 target に解決 |
| D2/D3/D4/D5/D6 | 小 global / 引数脱落 / libm 置換 / hand port / processReplacing 破れ | ir_flatten・ABI 仮想化・lift 済み CRT・手書き不要化で OTT matrix 上は全て消えた (個別因果の再切り分けはしていない) |

## 5. 代替ルート比較 (FLEngine 全体 lift)

| 観点 | RetDec + icall pass | x64c 拡張 (tools/ott/lift) | Ghidra pcode ベース |
|---|---|---|---|
| OTT 実績 | 89/89 bit-exact (本回) | 89/89 (R) | 未実施 |
| FLEngine 実測 | 書換え 7,421 関数 約 30 秒, RetDec 4 並列 約 1–2 分, 構造検証のみ (間接 call 90.1% 復元, 残存 382/3,844) | **7,031 関数 340,764 命令を 36 秒で lift, 未対応 1,105 site (0.32%)**, 全 C 34.9MB を emcc -O0 で 21 秒 → wasm 22.6MB。変更は定数 3 行 + 例外耐性 1 行 (`integration/x64c_fle.patch`) |
| 未対応/未知 | RetDec translator が黒箱: 既知 D7–D13 は差分試験でしか見つからない。x87/MMX/string 命令の意味は未検証 | 内訳が全列挙済: movsq 632 + stosq 122 + rep 系 (string 788 = 71%), lock 付き 91, SSE2 整数 pack ~110, x87 制御 ~10, bt mem 29, 他 ~60 | SLEIGH が x87/SSE/AVX flag まで意味定義済 (期待) |
| コード量 (実測) | pass 群 約 1,900 行 (本ディレクトリ) | x64c 998 行 + rt 約 600 行 (OTT) | pcode→C/IR 変換器を新規 (推定 1.5–3k 行) |
| 追加工数 (推定) | landing pad・stack 引数・巨大関数・Delphi 固有を RetDec 越しに手当て | 未対応 ~60 mnemonic の実装 + 7.4k dispatch + SEH/x87/TLS runtime = **推定 2–4 週** | 変換器 + 検証 = 推定 4–8 週 |
| 正確さ | 既に bit-exact だが不具合が顕在化するたび pass 追加 | 命令 1:1 で決定的。native 実機械語との差分枠組みが既存 | Ghidra 解析の誤り (関数境界/型) が混入 |
| 実行性能 | 未測 (本回 -O0) | OTT -O1 で実時間 29 倍 (R) | 未測 |
- **M11 unit #18 の連鎖** (`455790 → 44bb70 → 446400 → 4133f0=_UStrAsg`): x64c で 121 関数 lift 成功。`_UStrAsg(dest=&0, src=0)` は trap せず完走 (RetDec 版は OOB)。
  参照カウント経路は `lock xadd` で fail-fast (未対応 46 site の一つ)。リテラル経路は .data 未敷設で未解決 (data install は未実施)。
- **推奨: x64c 拡張**。未知の不具合源が無く、残作業が有限集合で見積れる。Delphi RTL の VMT/`call [rbx-0x20]` は dispatch 表でそのまま解ける。
  RetDec+icall pass は ①既に liftlib に載っている plugin closure (小規模) ②x64c の第二実装 (cross-check) として残す。D12 (landing pad) と stack 引数は**どちらのルートでも**必要な共通課題。

## 6. 未解決・制約 (実測ベースの正直な限界)
- FLEngine は監査と書換え/復元の構造検証まで。wasm ビルドと実行 (M11 boot) は未。残 382 site (巨大 2 関数 366) と gap 879 site は未復元。
- 5 引数目以降 (stack 渡し) は BLK 未対応 (`_InitLib` 8 引数など)。`jmp [idx*8+tbl]` 形 jump table、x87/MMX/AVX、`rep` 系は RetDec 任せ。
- OTT の F 集合は native coverage 由来 (x64c と同条件)。coverage 外の vtable target は `__icall_dispatch` が fail-fast する (未登録 target を site VA 付きで表示)。
- route build は -O0 (性能は評価していない)。CRT エラー経路 override は 4 件中 3 件を移植済み (§8)。残り `_handle_errorf` (1801c8cb8) は route の closure に無く lift 対象外。
- Fruity/KH/FA の wasm 実行検証は未 (監査のみ)。comis/derefix は OTT で bit-exact を確認したが他 PE では静的件数のみ。
- 作業中に `pkill -f retdec-decompiler` を実行してしまい、同時刻に他 subagent が走らせていた RetDec が落ちた可能性がある (原因は本担当の誤操作)。

## 7. 再現
```sh
bash tools/ott/ott_e2e.sh            # 前提 (native 参照 + coverage; 約 15 秒)
bash tools/icall/icall_e2e.sh        # 約 85 秒, exit 0 = PASS (OTT: 監査 + matrix 89 scenario bit 比較)
bash tools/icall/icall_e2e.sh --small   # + Balance / Fresh Air / Kilohearts の before/after 監査
bash tools/icall/icall_e2e.sh --full    # + FLEngine 7,421 関数 (RetDec 4 並列, 約 +10 分)
bash tools/icall/x64c_fle_probe.sh   # x64c を FLEngine に当てた対応度 (36 秒)
python3 tools/icall/tests/test_icall.py
```
前提: python3 (capstone, pefile), emsdk 6.0.12 (`[EMSDK]`), RetDec (`[RETDEC]`), node, setarch。keystone は raw 試験 (`work/probe`) のみ。

## 8. ICALL-5: CRT 経路の関数単位差分 (#231)

既知類型との関係 (`docs/DEFECTS.md` D1〜D16 / 本書 §4 D1〜D13 とは別体系): **新規 2 件 (下記 N1・N2)**。DEFECTS.md の D7 (silent miscompile 系) とは別。
検証起点 commit: `b82052e` (main) → 実装 `fd86159`。DLL = plugins-ott 内 NSIS インストーラの `OTT_x64.dll` (sha256 `ecd51e056860a37dbff4223c4dcab1a12f91e3f280161bec249fe8d97ab2378e`)。

### 8.1 結果 (route = RetDec + icall pass, native = 実機械語, 600 点/関数, seed 3, xmm0 raw 64bit の bit 比較)
| 関数 | 修復前 | 修復後 | 原因 |
|---|--:|--:|---|
| `1801a9be0` tan 本体 | 556/600 (max 1ulp, 差の x は 0.9 以上から) | **600/600** | N1 |
| `1801aa1a0` leaf kernel (r8=1 経路) | 555/600 | **600/600** | N1 |
| `1801c1240` (AVX/FMA 版 reduction) | 0/600 | **600/600** | N2 |
| `1801a9a6c` `1801b4154` `1801c12f4` | 600/600 | 600/600 | — |
| `1801a9b38` `1801c1398` (誤差報告経路) | wasm fail-fast, native も SIGSEGV | `1801a9b38` は override で動作 (§8.3) | CRT 未初期化 |

- **N1 (新規): RetDec が `and r64, 0xffffffff00000000` (Dekker 風の上位 32bit 切出し) を `select (x <u 0xFFFFFFFF00000001), x, x + 0xFFFFFFFF` に誤 lower する。** 症状: tan/atan 系の hi 部が 1ulp ずれる。
  発見の手がかり: issue 本文は「大引数 ≈1e4」としていたが、実測の差分入力は x = 0.908… から出ていた (reduction 経路ではない)。`oi.drc.ll` (RetDec 直後) に既に誤り。
  検出信号: `icmp ult i64 X, -4294967295` + `add i64 X, 4294967295` + `select`。修復: `ir_fix_mask.py` で `and i64 X, -4294967296` に戻す (OTT で 2 箇所)。
- **N2 (新規): `m11_simd2.py` の未実装 VEX helper は stderr を出して 0 を返す (silent)。** AVX/FMA 版 CRT (`1801c1240`) が xmm0=0 を返していた。修復: `vex_gen.py` が IR の宣言署名から VEX.128 helper 66 種を生成
  (FMA3 は `fma()` 単一丸め)、`vcomisd/vucomisd` は comis の flag 経路 (`icall_rewrite.py` の COMIS_KIND) に追加、残る未実装 stub は `simd_merge.py` で abort に変更 (残 6 種: int / int3 / movntps / pcmpistri / rep movsb / rep stosb)。

### 8.2 ネガティブコントロール
- `ICALL_FIX_MASK=0 bash tools/icall/ott_route.sh` (N1 補正を外す): gate が `1801a9be0` 556/600・`1801aa1a0` 555/600 で FAIL。
- `vex_gen.py` の FMA132 の被乗数を 1 箇所取り違え: `1801c1240` が 0/600 で FAIL (他は 600/600 のまま)。

### 8.3 CRT エラー経路 override (R の `ott_ovr.c` 移植)
`rt/icall_ovr.c` + `ir_override.py` で `1801c8c00` (_handle_error) / `1801a9a6c` (sqrt) / `1801a9b38` (sqrtf) を C 実装に置換。
native は CRT 未初期化で SIGSEGV するため突合不能 (UCRT の観測可能な意味から導出; 根拠は `tools/ott/rt/ott_ovr.c`)。
実行確認 (wasm): sqrt(-1) = `0xfff8000000000000`・sqrt(4) = 2.0・sqrt(-0.0) = -0.0・sqrtf(inf) = inf。置換前は未登録の間接 call target で fail-fast。
`1801a9a6c` の関数単位比較は xmm0 のみ 600/600 (rax は 0/600 一致: 原因は未調査。BLK 経由の rax と native の rax で意味が違う可能性があり、本 gate は xmm0 のみを判定に使う)。

### 8.4 検証 (clean HEAD `fd86159` の worktree, load average は開始→終了)
| コマンド | 結果 | 所要 | load |
|---|---|--:|---|
| `OTT_SKIP_INFO=1 bash tools/ott/ott_e2e.sh` | PASS: 89 scenario / 50,236 cell 全一致, max_ulp 0, state diff 0 | 20.9 s | 0.42→1.23 |
| `bash tools/icall/icall_e2e.sh` | PASS: 89 scenario / 50,236 cell 全一致, state diff 0, 監査 落ち 70→0, CRT gate PASS | 86.5 s | 1.13→1.62 |
| `bash tools/icall/diff/crt_fn_gate.sh` | PASS (6 関数 × 600 点) | 2.6 s | — |
| `python3 tools/icall/tests/test_icall.py` | PASS (0 failed; ICALL-5 追加 4 件を含む) | — | — |
(修復前の同 e2e: 80.9 s・PASS。cell 数は変わらず、差は関数単位 gate のみに現れる。)

### 8.5 範囲外・未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| **FMA3 経路 (`__use_fma3=1`) の `1801a9be0` が 42/600** (他 4 関数は 600/600)。RetDec が `vmovapd [rsp+0x40], xmm0` を void helper にして store を落とすため `[rsp+0x40]` の再読込 (`1801aa0d6`) が未初期化になる疑い (未確認) | OTT 既定 (`__use_fma3=0`) は無影響。AVX2 CPU で DllMain を通す経路のみ | 親 #90 に子チケット提案 (RetDec の VEX 256bit/stack store 落ち, D7 (本書 §4) 類似) |
| `1801a9b38` (sqrtf)・`1801c1398` 本体は native 突合不能 (CRT 未初期化) | override は UCRT 仕様由来で native bit 突合は無し | 親 #90 にコメント (x64c 側 `tools/ott/crtinit/REPORT.md` §7 が同じ限界を記載) |
| `_handle_errorf` (1801c8cb8) は route の closure F に無く未 lift | float 版エラー経路に到達すると fail-fast | #231 続報 (到達 scenario が構築できた時点で) |
| 関数単位 gate は SSE2 経路の 6 関数のみ。他の CRT 関数 (exp/log/pow の 1801b4220 等) は DSP matrix の bit 一致のみ | OTT が踏まない入力域の 1ulp は残り得る | #231 続報 (候補選別 `fn_diff.py` は rip/rsp 相対 leaf の 8 関数に限定) |
| #9 (OTT bit-exact 512/512) への反映: route でも 512/512 (t1 std 512 cell: zero 5 / normal 507 / junkHi 0 / junkTiny 0, |max| 0.2516) | — | #9 にコメントで報告 |
| `[ANALYSIS-DIR]` 直書き | runner で動かない | tools/icall の 8 本は #3604 で解決 (`REPORT_APPENDIX_3604.md`)。tools/ の残りは #294 |

### 8.6 再現
```sh
bash tools/ott/ott_e2e.sh && bash tools/icall/icall_e2e.sh      # 前提 + 全体 (関数単位 gate を含む)
bash tools/icall/diff/crt_fn_gate.sh                             # gate のみ (2.6 秒)
python3 tools/icall/diff/fn3_diff.py 1801a9be0 --n 600 --dump    # native / route / x64c の 3 者比較 (--kernel / --fma 0|1 / --wide)
```

## 9. #229 (ICALL-3) 統合適用 + stack 引数 BLK 拡張
既知類型との関係: 該当なし (新規: RetDec が rsp を stack_var 別 alloca に分割 → rsp 相対アドレスを BLK に渡せない)。検証起点 commit: `60a68c2` (branch `229-icall-liftlib-stack-blk`, base `400d546`)。

| 項目 | 結果 | 実測 |
|---|---|---|
| liftlib 統合 patch 適用 | **済** (`patch -p1 --dry-run` OK / pipeline.py hunk #2 は offset 23 行で成功) | `liftlib.passes.icall` import OK。`liftlib.pipeline.run_all('targets/ott_route.json', detect_only=True)` = prelift (280 関数・96 site・errors {}) → RetDec 17.5 s → restore (dispatch 96 / comis 100) → repair_ll、全体 29.9 s (load 0.74) |
| stack 引数 BLK (+0x48 / STKBUF 12 語) | **済 (静的 + OTT 回帰のみ)** | OTT F: site 96 中 stack 引数あり 2 (`0x1801a1ce6`・`0x1801aa528`, 各 1 語), 94 は 0 語。`function_1801aa4dc` の IR に STKBUF store を確認 |
| 回帰 `icall_e2e.sh` (HEAD `60a68c2`) | **PASS** 82.6 s (load 0.94, 4 core) | unit PASS 0 failed (新規 stk 6 件含む) / OTT F 落ち 70→0 / tail-jmp 11→0 / matrix 89 scenario・50,236 cell 全 bit 一致・max_ulp 0・state_diff 0 qword |
| 前提再現 (`ott_e2e.sh`) | PASS 23.4 s | OTT_x64.dll = `Install_Xfer_OTT_137.exe` の `$_13_/OTT_x64.dll` を `[ANALYSIS-DIR]`/plugins/ott/binaries/OTT_vst2_win64.dll に配置 (m6_scan.py で `tools/m6/work/ott_ranges.txt` 生成) |

- **設計の経緯 (実測)**: ① 当初案「BLK+0x48 = rsp+0x20 のアドレス」は、`ICALL_CHECK_STK` 計測で 1,337 dispatch 中 1 件が非整列値 (0x102cbecf, site 0x1801a03d3) になり不採用 (RetDec が rsp を連続領域として持たない)。
  ② 全 site 無条件に 12 語コピーすると leaf の `i64 f(void)` 一様 ABI が崩れ ctor entry が表から消えた (`ott_run: unknown entry 0x3011d400`) → 実際に store された語数だけコピー。
  ③ 初版の検出は `movaps [rsp+0x20], xmm6` (callee-saved xmm 退避) を引数と誤認し 6 site (うち 4 が実行され dispatch 252 回) → xmm/非整数サイズ store を除外して 2 site に。
- **ネガティブコントロール**: 上記 ③ の誤検出入力 (`movaps [rsp+0x20], xmm6`) が unit `stk: movaps ... 引数でない` で 0 語になること / 直前 call より前の store が無視されること。
- **検証範囲外 (正直な限界)**: OTT で stack 引数あり 2 site は matrix で**実行されない** (executed 0 / dispatch 1,337 中) ため、**stack 引数が実際に被呼側へ届くことの動的検証は未実施** (`tests/stk_check.mjs` は dispatch 総数 1,337・STKBUF 非 0 = 0 件を確認するのみ)。
  動的検証には 5 引数以上を取る間接 call 先を持つ PE (IPP 結合 or FLEngine) が必要。`ICALL_IPP_SHIM` フック (`__icall_dispatch` 先頭) は `-DICALL_IPP_SHIM` でのみ有効、shim とのリンクは未検証。
- **レビュー対応 (PR #326 Copilot 指摘 7 件, HEAD `4d30c1f` で実測, 4 core)**:
  ① `stk_slots_stored` は operand access に write を要求 (cmp/test の読み取りを除外)。unit 新規 3 件 (cmp/test は 0 語・cmp の後の mov は 1 語): 修正前 FAIL 2 (cmp/test) → 修正後 `RESULT PASS (0 failed)`。
  ② `ICALL_CHECK_STK` の dispatch ごとに BLK+0x48 の「期待値一致 / 8 byte 整列 / STKBUF 12 語が線形メモリ内」を runtime 検査 (`icall_stk_ptr_bad`)。`stk_check.mjs` は `dispatch>0 && ptr_bad==0` を終了コードで assert (nonzero_stkbuf は診断のみ)。
  実測: 正常 build `dispatch=1337 ptr_bad=0` rc=0 / ネガティブコントロール (pointer を +1 で非整列化) `dispatch=1337 ptr_bad=1337` rc=1。
  ③ `ott_route.json` の image を `${PLUGINS_DIR}/...` に (`pipeline.rpath()` が tools/shared/paths.py の変数を展開)。`run_all('targets/ott_route.json', detect_only=True)` 32.5 s 完走。
  ⑤⑥⑦ docs: integration/README.md は「再適用不可の履歴スナップショット」と明記し patch 適用コマンドを削除、実測値は本節へのリンクのみ。`passes/icall.py` の docstring は funcs ファイル必須に修正。
  回帰 `icall_e2e.sh`: PASS 91.5 s (load 1.28)、unit 0 failed / OTT F 落ち 70→0・tail-jmp 11→0 / matrix 89 scenario・50,236 cell 全 bit 一致 (max_ulp 0, state_diff 0 qword) / crt_fn_gate PASS。
- 追加 build オプション: `ICALL_EMCC_FLAGS` / `ICALL_EXTRA_EXPORTS` (`ott_route.sh`)、`stub_len` / `comis_stub_len` を map.json に出力 (stub 長が 78 固定でなくなったため ranges 計算 4 箇所を map 由来に変更)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| FLEngine 巨大 2 関数 (`0xc589b0`, `0x128f9e0`) の RetDec 範囲分割 lift | 残 366 site | 範囲分割では不変 (CHUNKS=2 でも 366)・棄却。実測は REPORT_APPENDIX.md §12 → #229 に残す |
| `jmp [idx*8+tbl]` / Delphi in-code 表の cmp/je 展開 | RetDec 任せのまま | 同上 (FLEngine/Balance 実バイナリで要検証) → #229 |
| Fruity Balance / Kilohearts / Fresh Air の wasm 実行 + 差分検証 | 監査のみのまま | 素材 `plugins-freshair plugins-kilohearts fl-win64` が必要 → #229 |
| plugin closure T0 42 本へ route バッチ適用 | 未着手 | #15 / #50 と連携、素材同上 |
| stack 引数の動的検証 (5 引数以上の間接 call を実行) | 本回は静的のみ | IPP 結合 (#246 系) で実行 → #229 |

## 10. #514: icall_rewrite.py の関数配置修正 (連続配置の回避)

既知類型との関係 (`docs/DEFECTS.md` / 本書 §4 とは別体系): **新規 1 件**。plugin 閉包 (eq-filter 11 block) を `tools/plugins/lift/lift_ranges.sh` の `PLUG_ICALL=1` で通したところ、書換え後の関数が 16 byte 整列でちょうど連続配置になる箇所 (関数終端が 16 の倍数) で、RetDec の `--select-ranges` が隣接 range `[a,b)+[b,c)` を 1 関数に併合し、後続関数の `define` が落ちた (4 block で 5 関数。dispatch 数は変わらないので site 突合では見えず、`define` 数 ≠ 閉包関数数で検出)。
修正: `icall_rewrite.py` の `next_slot()` で、直前の関数/stub と連続になる場合だけ 16 byte 空ける (連続しない配置はバイト一致)。stub・comis stub にも同じ処理。詳細な実測は `tools/plugins/f2/REPORT.md` §7。
### 10.1 #530: OTT 回帰の再実行 (素材付き)

`icall_e2e.sh` PASS (89 scenario / 50,236 cell 全一致, state_diff 0)・`test_icall.py` PASS。**e2e は #514 の連続配置を検出しない** (修正を外しても PASS) ため `tests/test_icall.py` に連続配置チェックを追加。全文・実測表は `REPORT_APPENDIX.md` §10.1。

### 10.2 #600: `liftlib_e2e.sh` の素材付き実走 (base `8f55002`、コード無変更)

素材: `work-liftlib-targets work-liftlib work-m6-ott plugins-ott analysis-ott-binaries toolchain-retdec toolchain-emsdk`。`bash tools/liftlib/liftlib_e2e.sh` = **ALL PASS, exit 0, 387 秒** (load 0.71 開始 → 1.01 終了、直列 1 本): unit ALL PASS / regress fa_gain 400/400・kh_gain 366/366 bit-exact・OTT 2 構成 PASS (census junkHi 104 ≤ 104, 出力 SHA 42/42 一致) / simd 205 mnemonic mismatch 0 / inject 94/94 検出・偽陽性 0 / leafspec gate (exp 40/40, log 32/32) PASS。icall pass は通らない経路 (§10.1) なので #514 の影響なしを実測で確認。leafspec の tan/svf/cvt は gate 無しの情報行 (mismatch 29/30/6、既存)。
実走の前提 2 点 (実測): ① python に `pefile` `capstone==5.0.7` が必要 (無いと exit 1 で fail-closed、1 回目 359 秒で FAIL)。② `work-liftlib` に `/home/ubuntu/...` を指す dangling symlink 133 本 (`ott_*/work/full_t1.drc.{ll,dsm}`) が含まれ、`recipes/ott.py` の `os.path.exists` が偽→`os.symlink` が FileExistsError で regress が落ちる。削除して再実行 (展開物のみ・commit 対象外)。素材側の修正は別途。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `work-liftlib` の dangling symlink 133 本 (runner で regress が FileExistsError) | 素材展開直後は liftlib_e2e.sh が FAIL (削除で回避) | #448 |
| FMA3 経路 `1801a9be0` が xmm0 42/600 (gate 外の INFO 行) | 本 PR と無関係 (既存の INFO 表示) → **#361 / PR #617 で解消 (§11)** | #229 (icall 親) |

## 11. ICALL-6: CRT 経路の残 (#361)

FMA3 経路 `1801a9be0` を 42/600 → **600/600** (N3: RetDec の `vmovapd xmm→stack` store 落ち、N4: closure 内 direct call の memory-ABI が戻り xmm1 を通さない)、`_handle_errorf` (1801c8cb8) を closure に入れ override 4/4、`1801a9a6c` の rax は呼出し元が読まないため gate は xmm0 のみ。FMA3 経路は gate に昇格。
結果表・ネガコン・rax 根拠 (`1801a9be0` の rax 不一致 558/600 も含む)・検証 (HEAD `b23593c`・所要・load)・未解決表の全文は `REPORT_APPENDIX.md` §11。再現: `bash tools/icall/icall_e2e.sh`。

## 12. ICALL-16: stack 引数の動的検証 (#1023)

結論・実測表・未解決は `REPORT_APPENDIX.md` §14 (250 行上限のため分割移動)。結論: OTT では stack 引数の値一致を動的に検証できない。起票先 #854 / #229。harness 直接注入による 12 語の値一致 (12/12) とネガコン (0/12 FAIL) は `REPORT_APPENDIX_5338.md` (部分達成、STKBUF/BLK 経路は未達)。

## 13. #1026 (ICALL-18): Fresh Air 残落ち 6 件

Fresh Air SlateCore の復元後の残落ち 6 件 (全て vtable 直接 call `call [rax+disp]`、2 関数) を分類。結論・実測表・未解決の全文は `REPORT_APPENDIX_1067.md` §13 (250 行上限のため分割移動)。RetDec 段の切り分け (#1298) は `REPORT_APPENDIX_1298.md`。wasm 実行と native 差分は未実施 (子 #1299)。段別の切り分け (RetDec 段で欠落したとする説明) は推定のみで未検証。根拠・再現手段の現状は `REPORT_APPENDIX_1067.md` §13.3 (#1067)。

## 14. #852 (ICALL-11): FLEngine jump table の取りこぼし修正

FLEngine の Delphi 表 (`sub rdx,8` 形) で 1 件しか解決していなかった欠陥を修正 (9 件に)。cmp/je 展開の効果は未実測 → REPORT_APPENDIX.md §16・§17 (#1206 の実測。§17 全文は `REPORT_APPENDIX_1206.md`)。

## 15. #1025 (ICALL-17): Kilohearts Gain icall 経路を wasm 化し native と bit 一致 (61 シナリオ / 366 step・差分 0)。原因は runner が `_ott_data_install()` を呼ばず data 未敷設だった点 (修正 `63e150e2`)。`bash tools/icall/kh_route_build.sh && bash tools/icall/kh_route_run.sh`。全文 `REPORT_APPENDIX_1025.md`・差分ゼロの節は `REPORT_APPENDIX_1025_FIX.md`。#1838 (ICALL-41): Fresh Air の CHAININFO 断片による範囲伸長 (`chain_end`) は `REPORT_APPENDIX_1838.md`。#2083 (ICALL-58): 残 3 件のうち `0x1803b3fc0`・`0x1803b5b60` は未実装 import `KERNEL32!RtlPcToFileHeader` の thunk で stack 整列がずれて落ちると特定、`0x1803b9ff0` は切り分けのみ (`REPORT_APPENDIX_2083.md`)。#2170 (ICALL-61): fatal RIP の採取と table 参照範囲の静的確認 (受入条件 3 のみ部分達成・結論と実測は `REPORT_APPENDIX_2170.md`)。#2197 (ICALL-62): T1/T2 の index 域と既知 12 slot の判定 (部分達成・`REPORT_APPENDIX_2197.md`)。#2198 (ICALL-63): fatal 経路の ACC 計上漏れを修正し fatal RIP を群別に切り分け (受入条件 3 は部分達成・結論と実測は `REPORT_APPENDIX_2198.md`)。#2231 (ICALL-67): 群 B〜H の引数由来を逆アセンブルと突き合わせ、群 I の整列違反の上流を特定 (受入条件 1 は部分達成・結論と実測は `REPORT_APPENDIX_2231.md`)。#2247 (ICALL-68): 群 B・E・H・G・D の faulting 値を単歩トレースと逆アセンブルで harness 引数由来と特定、群 I は `make_thunk` の整列欠落 (修復は子 issue)、群 C の `SLOT_ENC_INIT` 値は guest 初期化と一致 (結論と実測は `REPORT_APPENDIX_2247.md`)。#2696 (ICALL-82): dsm の data 区分に実コードを含む closure 関数の実測 (件数は候補で、非コード対照でも一部が通る)。修復は子 #2708 (ICALL-83)。全文 `REPORT_APPENDIX_2696.md`
