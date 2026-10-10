# tools/icall — 間接 call/jmp 落ち監査 + 復元 pass (CAB-89)

## 0. 結論 (先出し)

- **判定: 達成**。RetDec route に「間接 call 復元 pass」を入れるだけで **OTT は native 実機械語と全 bit 一致**した (x64c.py 不使用)。
  `bash tools/icall/icall_e2e.sh` (約 85 秒) = **PASS**: scenario matrix **89/89 本, 50,236/50,236 cell が native と bit 一致 (max_ulp 0), 最終 heap/obj state 差 0 qword**
  (t1 標準 512 cell: zero 5 / normal 507 / **junkHi 0 / junkTiny 0**, |max| 0.2516 = native と同値)。旧 RetDec chain は同 matrix で 4,791 cell (9.5%) のみ一致。
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
- FLEngine **gap site 879** = control-flow 非到達コード (Delphi unwind landing pad: `mov rbx,[rax]; call [rbx-0x20]` = 仮想 dtor 呼出し等) で RetDec は decode しない。RetDec dsm にも無い (879 中 2)。**間接 call 以前に「例外経路の dtor が lift されない」欠陥**。
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
| matrix 89 scenario 出力 cell native 一致 | 4,791 / 50,236 (9.5%) | **50,236 / 50,236** | 50,236 / 50,236 |
| 最終 heap/obj state 差 (qword) | 260,657 | **0** | 0 |
| t1 std 512 cell | 全 0 (旧 chain は 0x326 で早期 return) | **512/512 bit-exact, junk 0** | 512/512 |
- 使う既存 pass: ir_normalize, ir5_patch (m2/m5)、SIMD helper は m11_simd2.py (署名駆動) + 補完 5 種 (`cmplesd cmpnltsd cvttpd2dq cvtpd2dq sqrtpd`)。**M8/M9/M10 の OTT 専用 hand port (ir7_argpass, ir8_valueflow, ir9_bootstraps, gate box C port 等) は不要**。
- CRT 数学 (exp/log/tan/pow) は libm 置換でなく DLL 自身の機械語を lift (D4 解消)。関数単位の native 差分 (`diff/fn_diff.py`, 乱数入力 120 点) は 8 関数中 4 が全 bit 一致、tan 本体 `1801a9be0` は 111/120 (残り 9 は 1 ulp 差: 大引数 ≈1e4 の reduction 経路)、
  2 本は誤差報告経路で fail-fast、`1801c1240` は 0/120 (xmm0 以外の戻り経路, 未調査)。leaf kernel (`1801aa1a0`) は隠れ入力 (xmm4/5 等) があり単独呼出しでは native 側も不定のため比較不能。**matrix 89 scenario は全 bit 一致**だが、
  OTT が踏まない CRT 経路 (大引数 tan 等) に 1 ulp 級の残差が有り得る — 子チケットで扱う。
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
| FLEngine 実測 | 書換え 7,421 関数 約 30 秒, RetDec 4 並列 約 1–2 分, 構造検証のみ (間接 call 87% 復元) | **7,031 関数 340,764 命令を 36 秒で lift, 未対応 1,105 site (0.32%)**, 全 C 34.9MB を emcc -O0 で 21 秒 → wasm 22.6MB。変更は定数 3 行 + 例外耐性 1 行 (`integration/x64c_fle.patch`) |
| 未対応/未知 | RetDec translator が黒箱: 既知 D7–D13 は差分試験でしか見つからない。x87/MMX/string 命令の意味は未検証 | 内訳が全列挙済: movsq 632 + stosq 122 + rep 系 (string 754 = 72%), lock 付き 91, SSE2 整数 pack ~110, x87 制御 ~10, bt mem 29, 他 ~60 | SLEIGH が x87/SSE/AVX flag まで意味定義済 (期待) |
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
- route build は -O0 (性能は評価していない)。CRT エラー経路 override 4 件 (R の `ott_ovr.c`) は未移植 (matrix 89 scenario は通る)。
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
前提: python3 (capstone, pefile), emsdk 6.0.12, /opt/retdec, node, setarch。keystone は raw 試験 (`work/probe`) のみ。
