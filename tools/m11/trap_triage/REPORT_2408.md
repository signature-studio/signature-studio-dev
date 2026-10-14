# REPORT_2408 — list B `+8/+16` の書込み主体: 窓内全関数の網羅と欠落 IR (#2408, 親 #2369、REPORT_1676 §14)

既知類型との関係: **`docs/DEFECTS.md` D15 と同類型** (メモリ間接 `call [reg]` の脱落)。`call [r13]` (disp 0) と、直前の `cmp; jne` ごと分岐が畳まれる点が D15 の記述に無い追加形 (§4 に行案)。

## 0. 結論

1. **§12・§13・§13b の「計装が unit 106 で止まる」原因は、監視関数 `m11_sw` を `-O0` でコンパイルしていたこと**。同一ソース (`watch_addr_2408.c`) の最適化レベルだけを変えると、379 関数 (3,127 store) の計装が `-O0` では unit 106 で停止 (rc=124)、`-O2` では unit 114 まで完走 (rc=0) する (§2)。`-O0` の `m11_sw` は引数を C の線形スタックへ退避する。機構は推定 (§2 末尾)。
2. **IR に定義のある全 14,881 関数 (54,342 store) を計装して unit 114 を完走できた** (wall 46 s・rc=0)。窓内の全関数の網羅は「全 store 計装」で足りる。unit 114 全体 (窓に限らない) で list B `[0x10bd4c20, +32)` に当たる IR の store は **1 件だけ**: `function_50a830` の `store i64 %10, ptr %1` (IR 185786 行、addr `0x10bd4c30` = **+16**、val 1)。**+8 を書く IR の store は 0 件** (§3)。
3. **list B の `+8` (FItems) が 0 のままなのは、`function_50a830` (VA `0x50a830`、リストの Add) の仮想 `Grow` 呼出しが IR から落ちているため** (§4)。機械語では `cmp rdi,[rbx+0x18]; jne; call qword ptr [r13]` (`r13=[rbx]`=VMT、slot 0 = VA `0x50aac0` = Grow → `0x50ade0` SetCapacity) があり、list B は書込み時点で Count=0・Capacity=0 のため Grow が呼ばれて `+8` に配列が入る。IR は `cmp/jne` も `call` も無い単一ブロックで、`[0 + 0*8]` = `mem[0]` に書く (REPORT_881 §10 の `mem[0]` 一致と同じ)。
4. 欠落 IR 箇所: `function_50a830` の VA `0x50a84f` (`call [r13]`、Grow) と VA `0x50a87d` (`call [rbx+8]`、Notify。slot 1 = VA `0x50b3f0` は `ret` 1 命令)。`0x50aac0`・`0x50ade0` は `boot_final3.ll` に定義が無い (§4)。修復は子 issue #2439 (§6)。

## 1. 実測の基準

- 素材: `fl-win64` (`block00031_PE.bin` sha256 `b2c64da4…`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`)・`toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff`。`work/lift_pe.sha256` は PE 指紋で手記録 (REPORT_1676 §6 と同じ)。
- 基準の e2e (`m11_e2e.sh` 非 `--full`、起点 `fec12353` = main、foreground): rc=0、wall 2m47s、user 2m40s、load average 1.57/0.94/0.40 (1/5/15 分)。reached_stage 4、survey_ok 872、survey_trap 23、miss 46、IR sha256 `6909f85d…` (REPORT_1676 §6〜§13 と一致)。
- baseline `probe1676_watch.mjs` (n=1): unit 114 `halt0`、`after [icall 0x1c04a0] before [icall 0xf960]: L 0x0->0x10bd4c20 base -->0x0 cnt -->1` (REPORT_1676 §8 と一致)。
- 測定 commit: `877bd23f` (§2・§3 の全計装 run。本 PR のコード差分は `trap_triage/` の 4 ファイルのみ: `store_watch_2408.sh`・`watch_addr_2408.c`・`reach_2408.py` の追加と `watch_store_682.py` の `--fns-file` 追加)。`git diff fec12353 877bd23f --stat -- tools/m11 ':!tools/m11/trap_triage'` の出力は 0 行 (e2e の測定対象コードと同じ)。
- 測定 commit から HEAD までのコード差分: `git diff 877bd23f HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_1676.md' ':!tools/m11/trap_triage/REPORT_2408.md'` の出力は 0 行 (HEAD は REPORT・DOC_MAP の追記のみを足した commit。再測定は不要)。
- 各計装 run の終了時に `m11_build.sh` で clean な wasm へ復元。復元後 `boot_final3.ll` の `m11_sw` は 0 件、wasm 6,043,394 byte (e2e 直後と同じ)、`probe1676_watch.mjs` の出力は baseline と同じ。

## 2. 「unit 106 で停止」の原因切り分け (計装の分割は不要)

窓の根 5 関数 (`function_8651a0`・`40f9e0`・`410320`・`410360`・`409410`) から直接 call で到達する定義済み関数を `trap_triage/reach_2408.py --stores` で数えた: `roots=5 reached=379 stores=3127` (§13b と一致)。以下は全て `trap_triage/store_watch_2408.sh` の `w114` (窓 ON/OFF は §13 と同じ)。wall は emcc の build を含む。

| run | 計装 | `m11_sw` の C | `RUN_TIMEOUT` | rc | wall | 結果 | `[aw]` |
|---|---|---|---|---|---|---|---|
| B | 379 関数 (3,127 store) | `watch_addr_2408.c` `-O2` | 300 s | 0 | 45 s | unit 114 `halt0`、`unit` 行 114 本 | 0 |
| H | 同上 | `watch_addr_2408.c` `-O0` (`SW_OPT=-O0`) | 40 s | 124 | 84 s | 最後の行が `unit 106` | 0 |
| I | 同上 | `watch_addr_2099.c` `-O0` (`SW_LEGACY=1`、§13b までの旧版) | 60 s | 124 | 104 s | 最後の行が `unit 106` | 0 |

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
  - icall 行は計 38 本。1〜10 本目 (`icall 0x223840` と `icall 0xf960` 9 本) の入口は `0 0 0 0`、11 本目 (10 本目の `icall 0xf960`) の入口で `c9bc0 0 0 0` (VMT 設定 + FillChar 0)。この間の IR の store は `[aw]` 0 件で、書いたのは C の `function_40fb40` (`memset`・`Q(inst)=self`) と考えられる (推定: icall 境界の snapshot だけが根拠)。
  - `icall 0x85df70` の次の `icall 0xf960` の入口から、その次の `icall 0xf960` の入口までの間に `[aw] site=20922 addr=10bd4c30 val=1` が出て、後者の入口で `c9bc0 0 1 0`。
  - 以降、末尾の `halt0` まで 4 qword は `c9bc0 0 1 0` のまま (11〜38 本目の 28 行で `+8` はすべて 0。内訳: `c9bc0 0 0 0` が 3 行、`c9bc0 0 1 0` が 25 行)。
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
- IR 上の呼出し元: `grep -c 'call [^@]*@function_50a830('` は 27 件。他の呼出し元も同じ脱落を受ける。
- `docs/DEFECTS.md` 行案 (D23 案。**DEFECTS.md の直接編集は PM 判断**):

| ID | 層 | 新旧 | 症状 (silent) | 根本原因 | 観測 (証拠) | 検出信号 (機械的) | 修復 |
|---|---|---|---|---|---|---|---|
| D23 (案) | fe | D15 の追加事例 | リスト Add の仮想 `Grow` / `Notify` が IR から消え、`cmp cnt,cap; jne` も畳まれる。Add が `FItems=0` のまま `mem[0+cnt*8]` に書く (unit 275 は `mem[8]` を破壊) | メモリ間接 call (`call [r13]` disp 0、`call [rbx+8]`) の脱落 (D15 と同じ)。call だけの条件ブロックが空になり、その前の分岐も消える | `function_50a830` (27 call site)、list B で `[aw]` は `+16` の 1 件のみ (E)、`+8` は 0 のまま (§3)、PE の VMT slot 0/1 = `0x50aac0`/`0x50b3f0` (§4) | 機械語に `call [mem]` があり IR に call も分岐も無い関数 (`m11_icall_audit.py`: capstone の間接 call 4,175 件 / 1,631 関数に対し IR 間接 call 0) | `function_50a830` を `m11_ov.c` に C で転記し slot 0 の Grow を `ICALL_AT` で呼ぶ (Grow 実体 `0x50aac0`・`0x50ade0` は IR 外のため転記も要る)。[icall] pass で空ブロックを復元する案は D15 の修復と同じ |

## 5. 検証範囲と範囲外

- 検証範囲: unit 114 の IR の全 `store` (14,881 関数) と、icall 境界の list B の snapshot。n: HEAD `877bd23f` の run は B・E・F・G・H・I が各 1 回。script 確定前 (同じ計装・同じ条件) の run が B・E・H・I に各 1 回あり、結果 (rc・停止 unit・`[aw]` の件数と site) は同じ (n=2)。F・G は n=1。baseline・e2e も n=1。
- 範囲外: C 実装の関数内の書込み (§3)、停止機構の検証 (§2)、`function_50a830` を C に転記したときの unit 114・survey への影響 (子 issue #2439)、IR 上の 27 件の呼出し元それぞれの個別確認。

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
```

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_50a830` の Grow / Notify の復元 (転記 + `ICALL_AT`) と、unit 114・survey への影響の測定 | list B の `+8` が 0 でなくなるかの確認。unit 114 の `halt0` と unit 275 の oob が変わるか | 子 issue #2439 (親 #2408) |
| unit 106 で止まる機構の検証 (`-O0` の `m11_sw` が書くスタック残骸を読む関数の特定) | §2 の機構は推定のまま | PR 本文の未解決表 (診断のみで実装を伴わないため起票しない) |
| DEFECTS.md への D23 追記 | 横断正本の更新 | PM 判断 (`docs/WORKFLOW.md` §5) |
