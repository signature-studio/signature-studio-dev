# REPORT_2408 — list B `+8/+16` の書込み主体: 窓内全関数の網羅と欠落 IR (#2408, 親 #2369、REPORT_1676 §14)

既知類型との関係: **`docs/DEFECTS.md` D15 と同類型** (メモリ間接 `call [reg]` の脱落)。`call [r13]` (disp 0) と、直前の `cmp; jne` ごと分岐が畳まれる点が D15 の記述に無い追加形 (§4 に行案)。

## 0. 結論

1. **§12・§13・§13b の「計装が unit 106 で止まる」原因は、監視関数 `m11_sw` を `-O0` でコンパイルしていたこと**。同一ソース (`watch_addr_2408.c`) の最適化レベルだけを変えると、379 関数 (3,127 store) の計装が `-O0` では unit 106 で停止 (rc=124)、`-O2` では unit 114 まで完走 (rc=0) する (§2)。`-O0` の `m11_sw` は引数を C の線形スタックへ退避する。機構は推定 (§2 末尾)。
2. **IR に定義のある全 14,881 関数 (54,342 store) を計装して unit 114 を完走できた** (wall 46 s・rc=0)。窓内の全関数の網羅は「全 store 計装」で足りる。unit 114 全体 (窓に限らない) で list B `[0x10bd4c20, +32)` に当たる IR の store は **1 件だけ**: `function_50a830` の `store i64 %10, ptr %1` (IR 185786 行、addr `0x10bd4c30` = **+16**、val 1)。**+8 を書く IR の store は 0 件** (§3)。
3. **list B の `+8` (FItems) が 0 のままなのは、`function_50a830` (VA `0x50a830`、リストの Add) の仮想 `Grow` 呼出しが IR から落ちているため** (§4)。機械語では `cmp rdi,[rbx+0x18]; jne; call qword ptr [r13]` (`r13=[rbx]`=VMT、slot 0 = VA `0x50aac0` = Grow、call は VA `0x50a84f`) があり、list B は書込み時点で Count=0・Capacity=0 のため Grow が呼ばれる。Grow の経路 `0x50aac0` → `0x50ade0` → `0x417fc0` → `0x417b70` で、`[this+8]` (FItems) への store は **VA `0x417f96`** (`mov qword ptr [rax], rcx`、`rax=&FItems`、関数 `function_417b70` の末尾) である。`0x417b70` は IR に定義があるが、経路の `0x50aac0`・`0x50ade0` が IR に無いため、unit 114 の list B の実行では `0x417f96` に到達しない。IR は `cmp/jne` も `call` も無い単一ブロックで、`[0 + 0*8]` = `mem[0]` に書く (REPORT_881 §10 の `mem[0]` 一致と同じ)。
4. 欠落 IR 箇所: `function_50a830` の VA `0x50a84f` (`call [r13]`、Grow) と VA `0x50a87d` (`call [rbx+8]`、Notify。slot 1 = VA `0x50b3f0` は `ret` 1 命令)。`0x50aac0`・`0x50ade0` は `boot_final3.ll` に定義が無い (§4)。修復は子 issue #2439 (§6)。
5. **40fac0 は list B の `+8` を書かない** (静的判定、§3)。VMT `0xc9bc0` の InitTable (`Q(0xc9bc0-0xb0)` = `0xc9be0`) は kind `0x0e` (tkRecord) で、親鎖 (`0x1a38`) を含めて kind `0x16` が無いため `flag`=0 となり、`40fb40` は `40fac0` を呼ばない。IntfTable (`Q(cls-0xc0)`) も chain の全クラスで 0 件のため、`40fb40` の C 側の書込みは `memset` (0) と `Q(inst)=self` の 2 つだけである。

## 1. 実測の基準

- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff`。`work/lift_pe.sha256` は PE 指紋で手記録 (REPORT_1676 §6 と同じ)。
- 基準の e2e (`m11_e2e.sh` 非 `--full`、起点 `fec12353` = main、foreground): rc=0、wall 2m47s、user 2m40s、load average 1.57/0.94/0.40 (1/5/15 分)。reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (REPORT_1676 §6〜§13 と一致)。
- baseline `probe1676_watch.mjs` (n=1): unit 114 `halt0`、`after [icall 0x1c04a0] before [icall 0xf960]: L 0x0->0x10bd4c20 base -->0x0 cnt -->1` (REPORT_1676 §8 と一致)。
- 測定 commit: `877bd23f` (§2・§3 の全計装 run。本 PR のコード差分は `trap_triage/` の 4 ファイルのみ: `store_watch_2408.sh`・`watch_addr_2408.c`・`reach_2408.py` の追加と `watch_store_682.py` の `--fns-file` 追加)。`git diff fec12353 877bd23f --stat -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行 (e2e の測定対象コードと同じ)。
- 測定 commit から HEAD までのコード差分 (HEAD = `36a8f155`): `git diff 877bd23f 36a8f155 -- tools/m11 ':!tools/m11/trap_triage/REPORT_1676.md' ':!tools/m11/trap_triage/REPORT_2408.md'` の出力は `store_watch_2408.sh` 1 行 (`1ac2952d`。`source` の emsdk の置き場を `EMSDK_HOME` の既定値にした。既定値は従来と同じ) と、新規 `trap_triage/vmt_chain_2408.py` (`36a8f155`、51 行。PE の静的データを読むだけで、計装・e2e・wasm build の入力ではない)。`1ac2952d` でこの commit の E を再実行した: rc=0、wall 46 s、load 0.53、`[aw]` 1 件 (`function_50a830` IR 185786 行、addr `10bd4c30` val 1)、unit 114 `halt0` (E と同じ)。他の run (B・F・G・H・I) は `877bd23f` の測定のまま。以後に増えるのは REPORT_2408.md と PR 本文だけで、上の範囲のコード差分は増えない。
- 各計装 run の終了時に `m11_build.sh` で clean な wasm へ復元。復元後 `boot_final3.ll` の `m11_sw` は 0 件、wasm 6,043,394 byte (e2e 直後と同じ)、`probe1676_watch.mjs` の出力は baseline と同じ。

## 2. 「unit 106 で停止」の原因切り分け (計装の分割は不要)

窓の根 5 関数 (`function_8651a0`・`40f9e0`・`410320`・`410360`・`409410`) から直接 call で到達する定義済み関数を `trap_triage/reach_2408.py --stores` で数えた: `roots=5 reached=379 stores=3127` (§13b と一致)。以下は全て `trap_triage/store_watch_2408.sh` の `w114` (窓 ON/OFF は §13 と同じ)。wall は emcc の build を含む。

| run | 計装 | `m11_sw` の C | `RUN_TIMEOUT` | rc | wall | 結果 | `[aw]` |
|---|---|---|---|---|---|---|---|
| B | 379 関数 (3,127 store) | `watch_addr_2408.c` `-O2` | 300 s | 0 | 45 s | unit 114 `halt0`、`unit` 行 114 本 | 0 |
| H | 同上 | `watch_addr_2408.c` `-O0` (`SW_OPT=-O0`) | 40 s | 124 | 84 s | 最後の行が `unit 106` | 0 |
| I | 同上 | `watch_addr_2099.c` `-O0` (`SW_LEGACY=1`、§13b までの旧版) | 60 s | 124 | 104 s | 最後の行が `unit 106` | 0 |

- 予算の違い: B は `RUN_TIMEOUT=300`、H は 40 s、I は 60 s で、同じ条件の比較ではない。H・I の rc=124 は「40〜60 s 以内に unit 106 を超えない」ことしか示さない。停止位置の同一性は、予算を延ばした既存の測定で裏付ける: `tools/m11/trap_triage/REPORT_1676.md` §13 (行 215) は全 store 計装 (`store_watch_2217.sh`、54,342 store) で `w114` 10 分 45 秒・rc=124・`unit 106` で停止、§13b (行 234) は 379 関数 (`store_watch_2270.sh`、3,127 store) で 600 s・rc=124・`unit 106` で停止。H・I は同系統の旧測定の範囲 (`-O0` の `m11_sw`) を超えない、という位置づけに留める。

- H と B は **C ソースが同一で `-O0` / `-O2` だけが違う**。旧版 (I) の停止も同じ unit 106。IR 側は同一 (379 関数・3,127 store)。
- 全 store 計装の旧記録 (§10・§11・§13: 54,342 store が unit 106 で停止) と、379 関数の旧記録 (§13b) の停止位置は同じ。全 14,881 関数の run は §3 の E (`-O2`) で完走した。
- 機構 (**推定**): `-O0` の `m11_sw` は引数 4 個を自分のフレームへ退避する (毎回、IR の呼出し元の下のスタックを書く)。IR の関数は未初期化の alloca を読むため、スタック残骸が変わると分岐が変わり得る。unit 106 で止まる具体の関数・ループは本 run では未特定 (停止の機構の検証は上の表の範囲外)。`-O2` 版は監視 OFF / 範囲外で線形スタックに何も書かない (fast path + `noinline` の `sw_hit`)。
- 計装の分割は不要だった。`reach_2408.py` の 379 関数が目的の「直接 call の到達集合」だが、間接 call 先 (`m11_icall` 経由) は含まない。そのため §3 では IR 全関数を計装した。

## 3. IR 全関数の store 計装: list B `[0x10bd4c20, +32)` への書込み

`WATCH_ALL=1 bash trap_triage/store_watch_2408.sh <tag> full`。`full` は監視を unit 114 の開始から ON にし、icall 行ごとに list B の 4 qword と `[aw]` 行を時系列に出す (窓 ON/OFF に依らない)。`WATCH_ALL=1` は `boot_final3.ll` の `define` 全 14,881 関数 (`work/probe2408/fns_all.txt` の行数) を計装する。

| run | 条件 | 計装 store | rc | wall | load | `[aw]` | 内容 |
|---|---|---|---|---|---|---|---|
| E | `WATCH_ADDR` 既定 (list B) | 54,342 | 0 | 46 s | 0.91 | **1** | `function_50a830` IR 185786 行 `store i64 %10, ptr %1` addr `10bd4c30` val 1 width 8 |
| F | E から `function_50a830` を除外 (`WATCH_EXCLUDE`、14,880 関数) | 54,340 | 0 | 46 s | 0.92 | **0** | ネガティブコントロール: 除くと list B の hit が消える |
| G | `WATCH_ADDR=0x10be9160` (陽性対照) | 54,342 | 0 | 46 s | 0.97 | 4 | `function_5c0d40` 3 件 (`10be9168`・`10be9178`・`10be917c`) と `function_8651a0` IR 333679 行 addr `10be9160` val `10b58160` (§13b の site 19 の書込みと同じ番地・値) |

- E の icall 時系列 (各行の ` | mem@WA` は list B の `[+0] [+8] [+16] [+24]`)。要点だけ抜粋:
  - icall 行は計 38 本。1〜10 本目 (`icall 0x223840` と `icall 0xf960` 9 本) の入口は `0 0 0 0`、11 本目 (10 本目の `icall 0xf960`) の入口で `c9bc0 0 0 0` (VMT 設定 + FillChar 0)。この間の IR の store は `[aw]` 0 件で、書いたのは C の `function_40fb40` (`memset`・`Q(inst)=self`) と考えられる (根拠は icall 境界の snapshot と、次項の静的判定)。
  - `icall 0x85df70` の次の `icall 0xf960` の入口から、その次の `icall 0xf960` の入口までの間に `[aw] site=20922 addr=10bd4c30 val=1` が出て、後者の入口で `c9bc0 0 1 0`。
  - 以降、末尾の `halt0` まで 4 qword は `c9bc0 0 1 0` のまま (11〜38 本目の 28 行で `+8` はすべて 0。内訳: `c9bc0 0 0 0` が 3 行、`c9bc0 0 1 0` が 25 行)。
  - `0x40fb40`・`0x40fac0` の C 実装 (`m11_ov.c`) の書込み: `function_40fb40` (行 460) は (1) `memset(inst, 0, D(self-0x80))`、(2) `Q(inst)=self`、(3) 親鎖の各クラスの IntfTable `[vmt-0xc0]` の VTable を `Q(inst + IOffset) = vt` (行 479)、(4) 途中で InitTable `[vmt-0xb0]` が kind `0x16` なら `flag=1`、末尾で `flag` なら `ov_initinst_nested` = `0x40fac0` を呼ぶ (行 487)。`0x40fac0` は kind `0x16` の chain でのみ `function_417150(inst, ti)` を呼ぶ (行 433-449)。
  - **40fac0 は list B の `+8` を書かない (判定)**: `trap_triage/vmt_chain_2408.py c9bc0` は PE の静的データで、VMT `0xc9bc0` の InitTable kind `0x0e`、`flag(40fb40)=0`、`40fac0 -> 417150 calls: 0` を出す。IntfTable は `0xc9bc0` と親 `0x1a38` の両方で 0 件のため、`40fb40` の VTable 書込みも起きない。したがって list B の inst に対する C 側の書込みは `memset` (0) と `Q(inst)=self` の 2 つだけで、`+8` に非 0 を書くものは無い。動的にも、`40fb40` の完了後 (icall 11 本目 `c9bc0 0 0 0` の入口) 以降、`+8` は 28 行すべて 0 のまま。
- 計装が挙動を変えていない確認 (別 run との突合): E の icall 行 38 本の列は、計装なしの `probe1676_u114.mjs` の icall 行 38 本 (stderr 84 行中) と **完全一致** (`diff` 出力 0 行)。unit 114 も同じ `halt0`。
- 陽性対照 G: 既知の窓内書込みを 4 件拾った。E の 1 件 (list B の `+16`) の値 1 は、baseline の `cnt -->1` と一致する。
- 範囲外: C で実装された関数 (`m11_ov.c`・`m11_rt.c`・shim) は IR の store 計装の対象外。list B の `+8` については、icall 境界 28 行の snapshot で 0 のままであることまでしか示していない (icall の間の C の書込みは、境界の間で戻る場合は見えない)。`+8` の書込みが無いことは、§4 の機械語と合わせて説明する。

## 4. 欠落 IR の特定 (`function_50a830`、VA `0x50a830`)

IR (`boot_final3.ll`、`define weak i64 @function_50a830(i64 %arg1, i64 %arg2)`、13 命令・分岐なし):

```
%2 = load [arg1+16]   ; Count
%5 = load [arg1+8]    ; FItems (= list B の +8)
store arg2 -> [%5 + %2*8]
store ([arg1+16] + 1) -> [arg1+16]
ret %2
```

機械語 (`trap_triage/disasm_fn.py 50a830`、capstone、93 byte): 

```
50a83f: mov rdi,[rbx+0x10]          ; Count
50a843: cmp rdi,[rbx+0x18]          ; Capacity
50a847: jne 0x50a853
50a849: mov rcx,rbx
50a84c: mov r13,[rbx]               ; VMT
50a84f: call qword ptr [r13]        ; VMT slot 0 = Grow   ← IR に無い
50a853: mov rax,[rbx+8]             ; FItems
50a857: mov [rax+rdi*8],rsi
50a85b: add qword ptr [rbx+0x10],1  ; Count += 1  ← IR の site 20922 (唯一の [aw])
50a860: test rsi,rsi ; je 0x50a880 ; mov rax,[rbx] ; cmp rax,[rip-0x40d77] ; je 0x50a880
50a87d: call qword ptr [rbx+8]      ; VMT slot 1 = Notify  ← IR に無い
```

- 型: `+8` = FItems、`+0x10` = Count、`+0x18` = Capacity。list B の VMT は LVA `0xc9bc0` (実行後メモリ `[0xc9bc0]=0x10aac0`、`[0xc9bc8]=0x10b3f0`)。**別算法の検算**: `pefile` で PE の RVA `0xc9bc0` の生の値を読むと `0x50aac0`・`0x50b3f0` (ImageBase `0x400000`、LVA = VA − `0x400000`)。
- slot 0 = VA `0x50aac0`: capstone 逆アセンブル (131 byte) は `[rbx+0x18]` (Capacity) を読み、0x40 超なら 3/2 倍、8 超なら +16、それ以下なら +4 で新容量を求めて `call 0x50ade0` (SetCapacity) に渡す。slot 1 = VA `0x50b3f0` は `ret` 1 命令 (size 1)。`grep -c '^define [^@]*@function_50aac0('`・`function_50b3f0(`・`function_50ade0(` は `boot_final3.ll` で **各 0 件** (`function_448d20` は 1 件)。
- 動的な根拠: §3 の snapshot で `[+0x10]` と `[+0x18]` は Add の直前に 0 と 0 (E の `c9bc0 0 0 0` → 書込み後 `c9bc0 0 1 0`)。`cmp` は等しく `jne` を通らず、実機では `call [r13]` (Grow) が実行される。IR は `cmp/jne` を持たず、必ず Grow を飛ばす。`FItems(+8)` が 0 のまま `store arg2 -> [0 + 0*8]` が `mem[0]` を書く。
- IR 上の呼出し元: `grep -c 'call [^@]*@function_50a830('` は 26 件 (定義行を含めた `grep -c '@function_50a830('` は 27)。他の呼出し元も同じ脱落を受ける。
- **`+8` の store の機械語** (`disasm_fn.py` で本 run に確認):
  - `50ade0` (78 B): `50ae0a lea rcx,[rbx+8]` (`&FItems`)、`50ae1e call 0x417fc0`。`50ae23 mov [rbx+0x18],rsi` は Capacity の store で `+8` ではない。
  - `417fc0` (56 B) は `call 0x417b70` (`417fec`) だけの thunk。
  - `417b70` (1,075 B、DynArraySetLength 相当): 引数 rcx を `[rbp+0xb0]` に退避し、新しい配列の data ポインタを `[rbp+0x78]` に持つ本流 (`417f8b`) で `417f96: mov qword ptr [rax], rcx` (`rax=[rbp+0xb0]`=`&FItems`)。newlen ≤ 0 の経路 (`417be0`) は store を通らない。
  - `50aac0` (131 B、Grow): `Cap=[rbx+0x18]=0`・`Count=[rbx+0x10]=0` で `rsi=1`、`rdi=0` → `+4` → `4`。`50ab36 call 0x50ade0` (newcap=4)。hook のポインタ (VA `0x15e4390` の値 `0x13a9b20`) が指す `0x9a9b20` の静的値は 0 のため、`50aaf0` の `call [rax]` は通らない (実行時値は未測定)。
  - IR: `function_417fc0`・`function_417b70` は定義あり、`function_50aac0`・`function_50ade0` は定義なし。`+8` の書込み命令は `0x417f96` に確定する。
- 行案の数値の出典: `4,175 件 / 1,631 関数` は `tools/m11/REPORT.md` 行 34 (`m11_icall_audit.py` の結果。本 run では再実行していない)、`unit 275 は mem[8] を破壊` は `trap_triage/REPORT_881.md` 行 142 (unit 275 の実行後 `mem[8]`=`0x10bd5280`)。
- `docs/DEFECTS.md` 行案 (D23 案。**DEFECTS.md の直接編集は PM 判断**):

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| D23 (案) | fe | D15 の追加事例 | リスト Add の仮想 `Grow` / `Notify` が IR から消え、`cmp cnt,cap; jne` も畳まれる。Add が `FItems=0` のまま `mem[0+cnt*8]` に書く (unit 275 は `mem[8]` を破壊) | メモリ間接 call (`call [r13]` disp 0、`call [rbx+8]`) の脱落 (D15 と同じ)。call だけの条件ブロックが空になり、その前の分岐も消える | `function_50a830` (26 call site)、list B で `[aw]` は `+16` の 1 件のみ (E)、`+8` は 0 のまま (§3)、PE の VMT slot 0/1 = `0x50aac0`/`0x50b3f0` (§4)、`+8` の store = `0x417f96` (§4) | 機械語に `call [mem]` があり IR に call も分岐も無い関数 (`m11_icall_audit.py`: capstone の間接 call 4,175 件 / 1,631 関数に対し IR 間接 call 0) | `function_50a830` を `m11_ov.c` に C で転記し slot 0 の Grow を `ICALL_AT` で呼ぶ (Grow 実体 `0x50aac0`・`0x50ade0` は IR 外のため転記も要る)。[icall] pass で空ブロックを復元する案は D15 の修復と同じ |

## 5. 検証範囲と範囲外

- 検証範囲: unit 114 の IR の全 `store` (14,881 関数) と、icall 境界の list B の snapshot。n: HEAD `877bd23f` の run は B・E・F・G・H・I が各 1 回。script 確定前 (同じ計装・同じ条件) の run が B・E・H・I に各 1 回あり、結果 (rc・停止 unit・`[aw]` の件数と site) は同じ (n=2)。F・G は n=1。baseline・e2e も n=1。
- 範囲外: C 実装の関数内の書込み (§3。`40fb40`・`40fac0` は静的判定で list B の `+8` を書かないことを示した)、`50aac0` の hook 分岐 (静的初期値 0 の既定経路のみ。実行時値は未測定)、停止機構の検証 (§2)、`function_50a830` を C に転記したときの unit 114・survey への影響 (子 issue #2439)、IR 上の 27 件の呼出し元それぞれの個別確認。

## 6. 再現と未解決

再現 (1 コマンド、`cd tools/m11` で実行。`FL_WIN64_DIR`・`work-m11` 展開・`work/lift_pe.sha256` 手記録は §1):

```
bash m11_e2e.sh                                                                # 基準 (非 --full)
WATCH_ALL=1 bash trap_triage/store_watch_2408.sh E full                       # §3 E: [aw] 1 件 (function_50a830)
WATCH_ALL=1 WATCH_EXCLUDE=function_50a830 bash trap_triage/store_watch_2408.sh F full   # §3 F: 0 件
WATCH_ALL=1 WATCH_ADDR=0x10be9160 bash trap_triage/store_watch_2408.sh G full           # §3 G: 4 件
python3 trap_triage/reach_2408.py --stores > work/fns379.txt                  # §2: 379 関数 / 3,127 store
WATCH_FNS_FILE=work/fns379.txt RUN_TIMEOUT=300 bash trap_triage/store_watch_2408.sh B w114                # §2 B: rc=0
SW_OPT=-O0 WATCH_FNS_FILE=work/fns379.txt RUN_TIMEOUT=40 bash trap_triage/store_watch_2408.sh H w114      # §2 H: rc=124
python3 trap_triage/disasm_fn.py 50a830 50aac0 50ade0 417fc0 417b70   # §4 機械語 (FL_WIN64_DIR 必須。+8 の store = 417f96)
python3 trap_triage/vmt_chain_2408.py c9bc0                           # §3 40fac0 の判定 (flag=0、40fac0 -> 417150 calls: 0)
python3 m11_icall_audit.py work/boot_final.ll                          # §4 間接 call 監査 (4,175 件 / 1,631 関数。本 run では再実行せず REPORT.md 行 34 を引用)
```

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_50a830` の Grow / Notify の復元 (転記 + `ICALL_AT`) と、unit 114・survey への影響の測定 | list B の `+8` が 0 でなくなるかの確認。unit 114 の `halt0` と unit 275 の oob が変わるか | 子 issue #2439 (親 #2408) |
| unit 106 で止まる機構の検証 (`-O0` の `m11_sw` が書くスタック残骸を読む関数の特定) | §2 の機構は推定のまま | PR 本文の未解決表 (診断のみで実装を伴わないため起票しない) |
| DEFECTS.md への D23 追記 | 横断正本の更新 | PM 判断 (`docs/WORKFLOW.md` §5) |

## 7. #2439: `function_50a830` の Grow/Notify 復元 (`M11_FIX_50A830`、既定 OFF)

既知類型との関係: **D15 同型** (§4 の行案 D23 案)。測定 commit `4efc5b82` (`m11_ov.c` +70 行、`m11_build.sh` +2/-1)。基点は origin/main `9f403c97`。

### 7.0 結論

1. ON (`M11_FIX_50A830=1`) で list B の `+8` は unit 114 で `0x0` → `0x10bc4f10` (非 0) になる (`probe1676_watch.mjs`)。受入条件 2 を満たす。
2. ON の survey は ok 872 → 871、trap 23 → 24。unit 144 (VA `0x25c540`) が **ok → oob の回帰 1 件**。unit 304・555 は oob → abort (IR 未定義 `function_535c2e` への到達)。回帰があるため既定は OFF のまま (受入条件 1 の「回帰が無ければ既定 ON」の分岐を採らない)。
3. unit 114 は halt0 のまま、unit 275 は oob のまま。e2e の回帰ゲート (`e2e_expect.env`: stage 4・survey ok 800) は ON・併用とも通る (rc=0)。
4. 未解決 (unit 144 の回帰・`function_535c2e` の既定化・既定 ON 化) は子 issue **#2521** (`[M11-19]`、親 #2439)。

### 7.1 転記の内容 (`tools/m11/m11_ov.c`、`#if M11_FIX_50A830` で囲む)

- `function_50a830(self, item)`: `cnt == [self+0x18]` なら `call [VMT+0]` (Grow)。`FItems[cnt] = item; Count++`。`item != 0` かつ VMT が `Q(RVA 0xc9af8)` と異なれば `call [VMT+8](self, item, 0)` (Notify)。VMT 経由は `ICALL_AT(0x50a84f / 0x50a87d, …)`。
- Grow 実体 `function_50aac0` (VA `0x50aac0`): hook 全域 `G` = RVA `0x11e4390` の指す `P` の `*P` が非 0 なら `call *P` で newcap を得る。静的値は 0 のため既定経路は容量の増分 (cap > 0x40 → `3*cap >> 1`、8 < cap ≤ 0x40 → +0x10、それ以外 → +4) を newlen まで繰り返す。
- SetCapacity `function_50ade0` (VA `0x50ade0`): newcap < Count なら `function_50a9a0` (エラー経路)。newcap ≠ Capacity なら `function_417fc0(&FItems, ti, 1, newcap)` の後 Capacity := newcap。`ti` = `Q(RVA 0xc9730)`。
- Notify 実体 VA `0x50b3f0` は `ret` 1 命令 (`disp_find` の `tr_ret0`)。Grow は `disp_find` の `tr_50aac0` で登録。
- RIP 相対の参照先は `ip + disp` を Python で計算して確認した (G = VA `0x15e4390`、VMT 比較の大域 = VA `0x4c9af8`、ti = VA `0x4c9730`、50ade0 の rdx = VA `0x15e2a30`)。

### 7.2 結果 (HEAD `4efc5b82` = 基点 `9f403c97` + 本変更。`m11_gen_ir2.sh` で `ld108=applied` に再生成してから測定)

| 項目 | OFF (既定) | ON (`M11_FIX_50A830=1`) | ON + `M11_FIX_535BF2=1` |
|---|---|---|---|
| e2e rc | 0 | 0 | 0 |
| reached_stage | 4 | 4 | 4 |
| survey ok / trap / miss / noproc | 872 / 23 / 46 / 1 | 871 / 24 / 46 / 1 | 871 / 24 / 46 / 1 |
| probe `base` (list B `+8`、unit 114 後) | `0x0` | `0x10bc4f10` | `0x10bc4f10` |
| unit 114 (VA `0x223840`) | halt0 | halt0 | halt0 |
| unit 275 (VA `0x40e170`) | oob | oob | oob |
| OFF からの変化 (unit 単位) | — | 144 ok→oob、304 oob→abort、555 oob→abort | 144 ok→oob (304・555 は oob に戻る) |
| `failfast_functions` (IR 未定義) | `{}` | `{function_535c2e: 2}` | `{}` |
| wall (`real`) | 52.5 s | 50.0 s | 未計測 |

- 負荷: OFF の直後の `uptime` は load average 0.95 / 0.74 / 0.51 (1/5/15 分)。並列 1 本 (e2e は直列)。
- 旧基点 `54bacdc0` (ld108 再生成前) でも同じ差分を得た (n=1): OFF 872/23/46、ON 871/24/46、併用 871/24/46、probe OFF `0x0` / ON `0x10bc4f10`。
- 測定の n: OFF は HEAD で 2 回 (同一結果)、ON は HEAD で 1 回 + 旧基点で 1 回、併用は HEAD で 1 回。

### 7.3 検証・ネガティブコントロール・同型の確認

- **フラグ依存のネガコン**: `cc()` (`m11_build.sh`) は更新時刻だけで再コンパイルを判定するため、フラグだけを変えても `work/obj/ov.o` は作り直されない。HEAD で最初に ON を実行したときは `rm` を忘れ、OFF と同一出力 (`base 0x0`、ok 872) になった。`ov.o` を削除して再実行すると `base 0x10bc4f10` になった。以後の全測定は `ov.o` を削除してから実行した。
- **受入条件 4 (同型の他関数)**: `function_47b260` (TList Add。`M11_NOTIFY_682` と同型) は機械語に `47b29d: cmp [rbx+0x20],0` / `47b2a2: je` / `47b2ae: call [rbx+0x20]` (Notify) がある。IR の本体には直接 call `@function_47a3e0` の 1 件だけで、間接 call は無い。`m11_icall_audit.py` は機械語の間接 call 4,175 件 / 1,631 関数に対し IR は 0 件 (脱落率 100.0%)。
- **IR sha256**: 旧基点 `54bacdc0` で `987f28f5…`、基点 `9f403c97` で `de46cada…`。§1 の `6909f85d…` とは一致しない (原因は未調査。survey の値は §1 と一致)。
- **素材の注意**: `work-m11` に `work/lift_pe.sha256` が含まれず、`m11_e2e.sh` が全再生成に入って `m2/work` 不足で失敗した。§1 と同じく PE 指紋 `b2c64da4…` を手で書いて回避した。

### 7.4 unit 単位の差分の詳細

- ON で変化: unit 144 (VA `0x25c540`) ok → `memory access out of bounds`、unit 304 (VA `0x483140`) と unit 555 `memory access out of bounds` → `Aborted`。
- 併用 (`M11_FIX_535BF2=1`) で変化: unit 144 のみ ok → oob。304・555 の abort は IR 未定義 `function_535c2e` の経路で、§4 の `M11_FIX_535BF2` が消す。
- 残りの 939 unit は OFF と同一。

### 7.5 再現

```
cd tools/m11                                       # 基点 9f403c97 の worktree (work/ は共有)
bash m11_gen_ir2.sh                                # ld108=applied の IR (51 s)。前提: work/lift_pe.sha256 を手記録
rm -f work/obj/ov.o && M11_SURVEY_DETAIL=<path> bash m11_e2e.sh           # 既定 OFF
rm -f work/obj/ov.o && M11_FIX_50A830=1 bash m11_e2e.sh                   # ON
rm -f work/obj/ov.o && M11_FIX_50A830=1 M11_FIX_535BF2=1 bash m11_e2e.sh  # 併用
node trap_triage/probe1676_watch.mjs                                      # base (OFF 0x0 / ON 0x10bc4f10)
```

### 7.6 測定 commit から HEAD までの差分

測定 commit `4efc5b82`。`git diff 4efc5b82 HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行 (本節の追記は `trap_triage/` のみのため、コード差分 0)。

### 7.7 検証範囲 / 範囲外

- 範囲内: list B `+8` (probe)、942 unit の分類、survey 集計、e2e 回帰ゲート、同型の機械語 (`function_47b260`)。
- 範囲外: 他の Add 呼出し元 (IR 27 件) の個別確認、unit 144 の回帰の原因 (子 #2521)、DEFECTS.md への D23 追記 (PM 判断)。

### 7.8 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 144 の ok → oob 回帰 (Grow 後の FItems・Capacity の状態が後続の添字アクセスを越える経路) | 既定 ON にできない (survey ok -1) | 子 issue #2521 (`[M11-19]`、親 #2439) |
| `function_535c2e` (IR 未定義。RetDec が `535bf2` の末尾 ret を落とした) の既定化 | ON 時の unit 304・555 の abort (併用で解消) | #2521 |
| 既定 ON 化と回帰ゲートの更新 | — | #2521 |
| DEFECTS.md への D23 追記 | 横断正本の更新 | PM 判断 (`docs/WORKFLOW.md` §5) |

## 8. #2521: `function_535c2e` の既定化 (`M11_FIX_535BF2` 既定 ON)・unit 144 の trap 経路

既知類型との関係: 該当なし (unit 144 の回帰は原因未特定。§8.2 は trap 位置まで)。

### 8.0 結論

1. **受入 3 (`function_535c2e`・unit 304/555 の abort)**: `M11_FIX_535BF2` の既定を 0 → 1 にした (commit `d80e9909f`)。ON (`M11_FIX_50A830=1`) では unit 304・555 が abort から oob に戻り、OFF の分類と一致する。OFF 経路は unit 単位で不変 (§8.1)。
2. **受入 1 (unit 144 の回帰の原因)**: 未特定。trap の関数チェーン (§8.2) まで。起票先: #3482。
3. **受入 2 (ON で unit 144 の回帰を解消)**: 未達。ON の survey ok は 872 (OFF 873 − 1) で「872 以上」は数値上満たすが、unit 144 は ok → oob のまま。起票先: #3482。
4. **受入 4 (既定 ON 化)**: 未達。`M11_FIX_50A830` は既定 OFF のまま (受入 1・2 が前提)。起票先: #3482。
5. e2e の rc は既定・ON とも **1**。origin/main `44a7f4465` (変更前) でも同じ値で、ゲートの期待値と実測が合わない (§8.1 の 3 件)。本 PR では期待値を変えていない。
6. **既定変更の到達先 (§8.4)**: `tools/gui/flengine/build.sh` は `m11_ov.c` を直接コンパイルするため、`-DM11_FIX_535BF2=0` で従来値に固定した (GUI 側の影響は §8.4 の前処理照合で 0)。

### 8.1 実測 (測定 commit `d80e9909f`。素材・環境は §1 と同じ。直列 1 本、load average は uptime の 1 分値 1.04 (基準 OFF の直後))

| 条件 | 環境変数 (`M11_FIX_50A830` / `M11_FIX_535BF2`) | e2e rc | wall | survey ok / trap / miss | 基準 (origin/main OFF) との unit 差 |
|---|---|---|---|---|---|
| 既定 (`d80e9909f`) | 未指定 (既定 `0` / `1`) | 1 | 1m11.5s | 873 / 22 / 46 | 0 |
| `M11_FIX_50A830=1` (`d80e9909f`) | `1` / 未指定 (既定 `1`) | 1 | 1m10.3s | 872 / 23 / 46 | 1 (144 ok → oob。304・555 は OFF と同じ oob) |
| 基準 OFF (`44a7f4465`、変更前) | 未指定 (既定 `0` / `0`) | 1 | 3m13s (初回の build を含む) | 873 / 22 / 46 | — |
| ON + `M11_FIX_535BF2=0` (変更前の既定、`44a7f4465`) | `1` / `0` | 1 | 1m11s | 872 / 23 / 46 | 3 (144 ok → oob、304・555 oob → Aborted) = 変更前の abort を再現 (ネガコン) |
| OFF + `M11_FIX_535BF2=1` (`44a7f4465` + フラグ) | `0` / `1` | 1 | 1m12s | 873 / 22 / 46 | 0 (535BF2 は OFF 経路の分類を変えない) |

再現: `cd tools/m11 && FL_WIN64_DIR=<展開先> [M11_FIX_50A830=… M11_FIX_535BF2=…] bash m11_e2e.sh`。unit 別の突合は `M11_SURVEY_DETAIL=<path>` を付ける。

- e2e rc=1 の内訳 (既定・ON 共通): (a) tolerant gate `通常起動の完了数 101 != 期待 56` (units_run_full 98 + skipped)、(b) `survey ok=873 != 期待 872` (OFF)、(c) ptrcheck survey `image_va_words_new 71005 > M11_EXPECT_PTR_SURVEY_NEW_MAX 71001`。期待値は変更していない (e2e_expect.env・m11_tolerant_gate.py)。
- 根拠ログ (M6): 原本 (`work/e2e_full.out`・`work/e2e_survey.out`・`work/judge.out`) は `tools/m11/work/` (gitignore) にあり repo に残らない。本 run は素材 `work-m11` が無く再採取できなかった。上の (a)〜(c) は作成者 run の値。出力形式はコードで確認済み: (a) `m11_tolerant_gate.py:46` `通常起動の完了数 %s != 期待 %d (strict の挙動が変わった)`、(b) `:51` `survey ok=%s != 期待 %d (survey の数値が変わった)`、(c) `m11_survey.mjs:161` `FAIL: survey ptrcheck image_va_words_new=%s > max=%s (%s)`。次の run で原本を採取して本節へ貼る (未解決表)。
- IR sha256 は `17a98d6e…` (`ir_conditions.json`)。§1 の `6909f85d…` と異なる。環境差か drift かは未切り分け。

### 8.2 unit 144 の trap 経路 (ON・`M11_SURVEY_STACK=144 node m11_survey.mjs`)

wasm スタック (内側→外側、`m11_wasmnames.py` で名前化): `function_407e20` (wasm 1877) ← `function_409440` ← `function_412d60` ← `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_414c70` ← `function_43c4c0` ← `function_653660` ← `function_6539e0` ← `function_653f40` ← `function_65c540` (unit 144 の本体)

- `407e20` は IR 先頭で `arg1 - 8` のヘッダを読み、trap はこの読み出しで起きる。`409440` は `arg1 ≠ 0` を確かめてから `407e20` を呼ぶ。つまり解放される値は nil ではなく、範囲外の非 0 値である (推定。値は未採取)。
- `412d60` は参照解放 (管理フィールドの減算と 0 判定) の形。`43c4c0` の呼出し先の一部 (`413760`) は `412d60` に至る。推定: Grow 後の list 関連の状態のうち、後の解放経路で参照される値が不正になっている。**未検証**。
- 照合済み (引数の取り違えは否定): `50ade0` の C 転記 (`m11_ov.c`) は機械語 (`50ade0` 78 B) と一致する。`417fc0` の IR シグネチャは `(ptr, ptr, i64, i64)` で、C 側の `(&FItems, ti, 1, newcap)` と一致する。

### 8.3 未解決 (次の一手: `407e20` に渡る arg1 を ON/OFF で採取し、FItems・Count・Capacity のどれかを判定する)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 144 の回帰の原因と修正 (受入 1・2・4) | 既定 ON (`M11_FIX_50A830`) 不可 | #3482 (#2521 の残り。本 PR で issue の範囲を縮めた) |
| e2e の期待値と実測の不一致 (8.1 の (a)〜(c)) と原本ログの採取 | e2e が既定でも rc=1 | PM 判断 (issue コメント) |
| 既定 ON の可否 (`M11_FIX_535BF2`。既定案: ON。survey は OFF と 0 差分) | 本 PR の既定変更を採るか | PM 判断 (`tools/m11/trap_triage/REPORT_1275.md` 52 行目の「既定 ON 化は PM 判断」への回答) |
| origin/main (`cf9dce6fe`。`44a7f4465` より後) は `tools/m11` に 20 ファイルの差分があり、本 PR は取り込んでいない。main 上の survey は未測定 | merge 後の既定の挙動 | PM 判断 (merge 後の再測定の要否) |
| `tools/m11/alloca/e2e.sh` の既定変更の影響 (既定の `m11_build.sh` を使う) | 未測定。影響の有無は未確認 (素材 `work-m11`・toolchain が本 run に無い) | 未解決 (次の run で `oc_artifacts` を付けて実行) |
| IR sha256 の差 (`17a98d6e…` と §1 の `6909f85d…`) | 基準の再現性 | PM 判断 |

### 8.4 既定変更の到達先

| 経路 | 既定 1 の影響 | 対処・結果 |
|---|---|---|
| `tools/m11/m11_build.sh` → `work/obj/ov.o` (m11 mainline) | `function_535bf2` / `function_535c11` の C 転記が入る | 本 PR の目的。m11 側の実測は §8.1 |
| `tools/gui/flengine/build.sh` (`m11_ov.c` を `$CF` で直接コンパイル) | 修正前は GUI の `m11_gui.cjs` にも入っていた | `CF` に `-DM11_FIX_535BF2=0` を足し、従来値 (0) に固定 (本 PR の修正 commit)。照合: `clang -E -P` の出力で、変更前 (`44a7f4465`) と修正後 HEAD の `m11_ov.c` は 1704 行で一致。修正前の `CF` を HEAD に当てると 17 行が増える (ネガコン)。GUI の e2e は再実行していない (素材 `work-m11` が本 run に無い)。GUI の実測値は `tools/gui/flengine/REPORT.md` §6j |
| `tools/m11/alloca/e2e.sh` (既定の `m11_build.sh` を使う) | 既定変更の影響を受ける | 未実行 (§8.3 の未解決) |
