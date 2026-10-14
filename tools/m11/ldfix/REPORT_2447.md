# #2447 (LD-115): function_666a60 のループの修復 (ループ内 store と回数初期値)

親: #2402 (LD-112)。前段: #1091 (LD-33、CLOSED)、#2316 (LD-108) の範囲外。

**判定: 達成** (受入条件 4 件すべて)。修復は `fix_ld115.py` の検証用単独パッチで、本番の IR 生成経路 (`m11_gen_ir2.sh`) には未配線 (配線は子 #2527 (LD-117))。

既知類型との関係 (DEFECTS.md): **D20** (wrong-value reuse) の 666a60 への延長 (ループ内 store、§2.2)。加えて同関数のループ回数の初期値が 0 に化ける別の欠陥を見つけた (§2.3。D20 とは別の候補、§7)。

測定 commit: `f049fe44` (コードを変えた最後の commit)。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| 666a60 のループ内 store の機械語 (666b0c〜666b13) と IR の対応を突合し、誤りの形を REPORT に書く | **達成**。§2。ループ内 store は slot+16 に `*arg1` (= N) を書くべきところ、スロットのアドレスを書いている。加えて回数の初期値 (666ada) も IR で 0 に化けている |
| 41a670 と同じ方式で修復し、wasm 直接呼びで期待値を実測する | **達成** (検証用単独パッチ)。`fix_ld115.py`。修復後の wasm 直接呼びで 3 スロットすべて期待値と一致 (§4) |
| 修復後の survey 942 unit を修復前と突合し、ok 退行 0 を示す | **達成**。ok 869 → 869、ok 退行 0、kind 以外の差分 0 unit (§5)。ただし 666a60 は survey で実行されない (§5) |
| DEFECTS.md の該当類型に結論 1 行 + リンク | **達成**。D20 行に 1 文と本 REPORT へのリンク (測定値は本 REPORT だけ) |

## 2. 機械語と IR の対応 (受入条件 1)

関数 `function_666a60` (VA 0x666a60、`.pdata` 上 size 215)。機械語は `block00031_PE.bin` を `tools/m11/ldfix/ldmach.py` の `Machine.disasm_fn` で逆アセンブルした (capstone 5.0.7 / pefile 2024.8.26)。IR の行番号は `tools/m11/work/boot_final.ll` (work-m11 の現在の snapshot) の値。

### 2.1 前提 (関数の入口〜ループ直前)

- `666a6f`: `mov [rbp+0x28], rcx` (rcx = arg1 = P。P は「N へのポインタ」の場所)。
- `666a92`: `call 0x409470` (確保。`*P` に新しい object N を書く。実測で `*P` ← 確保結果)。
- `666a9b`: `mov rax,[rbp+0x28]; mov r14,[rax]` (r14 = N = `*P`)。
- `666a9e`: `mov dword [r14], ebx` (`N.count` = arg2)。
- IR `L225121` (snapshot): `store i32 %10, ptr %15` (`%10` = trunc arg2)。snapshot では `%15 = inttoptr %arg1` (P を指す。N の代わりに使う consumer 形の欠陥)。現行 ldfix 出力では `%15 = inttoptr %ldfxu18` (`%ldfxu18` = `load [arg1]` = N) で、この欠陥は ldfix の consumer 修復で直っている。

### 2.2 ループ内 store (誤り)

| 機械語 | 意味 | IR (`boot_final.ll`) | 判定 |
|---|---|---|---|
| `666aeb`〜`666af7`: `movsxd rcx,eax; shl rcx,2; lea rcx,[r14+rcx*8+0x40]; mov [rcx],0` | slot(i) = N+0x40+32i、+0 ← 0 | `L225147` `%29 = add %26,%28` (`%26 = arg1+64`)・`L225149` `store 0, %30` | IR の基底は arg1 のまま (ldfix の consumer 修復で `%26 = N+64` に直る。現行ldfix 出力で確認) |
| `666afe`〜`666b08`: `lea r8,[r8+r9]; mov [rcx+8],r8` | +8 ← arg3+i | `L225151`〜`L225154` `store %32, %34` | 一致 |
| `666b0c`〜`666b10`: `mov r8,[rbp+0x28]; mov r8,[r8]` | r8 = `*P` = N | (対応する load が無い) | **IR に N の load が無く、代わりに `%29` を使う** |
| `666b13`: `mov [rcx+0x10], r8` | +16 ← N | `L225156` `%36 = inttoptr %35`・`L225157` `store i64 %29, ptr %36` | **誤り: 値が `%29` (スロットの番地 N+0x40+32i) になっている** |
| `666b17`: `mov qword [rcx+0x18],0` | +24 ← 0 | `L225160` `store 0, %38` | 一致 |

誤りの形: 値の取り違え (wrong-value reuse、D20 と同型)。`%29` (スロットの番地) が、機械語の `*P` (N) の位置に入っている。現行 ldfix の出力 (`cur.ll`) でも `store i64 %29, ptr %36` は残る (consumer 修復は値を直さない)。

### 2.3 ループ回数の初期値 (誤り、別の欠陥)

| 機械語 | 意味 | IR | 判定 |
|---|---|---|---|
| `666ada`: `mov edx, dword [r14]` | edx = `N.count` (= arg2、`666a9e` で書いた値) | `L225139` `store i64 0, ptr %rdx.0.reg2mem` | **誤り: 値が 0 のリテラル** (load が消えている) |
| `666add`: `sub edx,1` / `666ae6`〜`666ae8`: `sub edx,ecx; add edx,1` | edx = count | 無し | (初期値が 0 なので IR のループは `rdx-1` が 0xffffffff となり、i32 の `trunc` が 0 になるまで 2^32 回回る) |

推定 (IR からの導出): IR のループ判定 `L225163`〜`L225170` は rdx を 1 ずつ減らして 0 で抜けるので、初期値 0 では 2^32 回回る。wasm では途中で `store` がメモリ外に出て trap する (実測: §4 の BASE)。

### 2.4 IR に無い分岐 (別の欠陥、子 issue)

機械語 `666ae0`〜`666ae4` (`mov eax,ecx; cmp eax,edx; jg 0x666b29`) は回数 0 のとき即座に抜けて `rax=0` で返す。IR の entry ブロックは無条件 `br label %dec_label_pc_666aeb` で、この分岐が無い。`arg2=0` を wasm 直接呼びすると trap する (post build で実測: `memory access out of bounds`)。機械語の想定は 0 を返して書き込み無し。→ 子 **#2513 (LD-116)**。

## 3. 修復 (受入条件 2)

`tools/m11/ldfix/fix_ld115.py` (標準ライブラリのみ。`fix_ld108.py` と同じ単独パッチ方式)。入力 IR は `ldfix/ldfix.py` の出力に `fix_ld108.py` を掛けた IR (`work/boot_final.prealloca.ll` から。本番 `m11_gen_ir2.sh` と同じ順序)。2 箇所を直す。

本番配線の現況: #2402 (LD-112) は 14:42 に COMPLETED で閉じ、`fix_ld108.py` は `m11_gen_ir2.sh` に配線済み (main `3dbb35e0`、`ld108=applied` を `m11_build.sh` が要求)。`fix_ld115.py` は未配線 (子 #2527)。

- **count**: entry の `store i64 0, ptr %rdx.0.reg2mem` を、`load i32 [%15]` (N.count を読み直す。機械語の `mov edx,[r14]` と同じ) の zext に置換。
- **store**: ループ本体の `store i64 %29, ptr %36` を、ループ内で読む `load i64 [%arg1]` の値 (`*P` = N) に置換。

IR の差分 (`ld115_e2e.sh` の出力 `ir_post.diff`、commit `f049fe44`):

```
225177c225177,225179
<   store i64 0, ptr %rdx.0.reg2mem
---
>   %ldfx115c = load i32, ptr %15, align 4
>   %ldfx115z = zext i32 %ldfx115c to i64
>   store i64 %ldfx115z, ptr %rdx.0.reg2mem
225195c225197,225199
<   store i64 %29, ptr %36, align 8
---
>   %ldfx115p = inttoptr i64 %arg1 to ptr
>   %ldfx115 = load i64, ptr %ldfx115p, align 8
>   store i64 %ldfx115, ptr %36, align 8
```

(行番号は修復前 IR `cur.ll` の値。他の行は変えない。diff は 12 行。)

## 4. 動的確認 (受入条件 2)

`tools/m11/ldfix/dyn_ld115.mjs`。3 版の wasm を同じ入力で直接呼ぶ。

- 初期化: `m11_set_survey(1)` → `m11_boot_enter(0,1)` (DllMain 相当) → `m11_call_unit(0)` と `m11_call_unit(1)`。unit 0 を流しただけでは `function_409470` (確保) が heap 未初期化で trap する (実測。unit 0 のみ = trap、unit 0・1 = 正常)。
- 入力: P = 0x11f00000 (`*P` は 0 に初期化。確保が書く)、arg2 = 3、arg3 = 5、arg4 = 0x11f00100。
- 期待 (機械語から決定): N = `*P` (確保結果)、`N.count` = 3、`N.tag` = 2、戻り値 = 3 (eax = count)、各 i ∈ {0,1,2} で slot(i) = `N+0x40+32i` の { +0: 0, +8: 5+i, +16: N, +24: 0 }。

| 版 | 内容 | 結果 (実測) |
|---|---|---|
| BASE | 現行 ldfix → fix_ld108 (本番と同じ順序。41a670 は修復済み、666a60 は未修復) | **TRAP** `memory access out of bounds` (回数初期値の欠陥、§2.3) |
| MID | BASE + 回数初期値のみ (`fix_ld115.py --only count`) | 完走 (`ret=0x3`、`count=0x3`)。**slot(i).+16 = N+0x40+32i (slot アドレス) で FAIL** (`slot0.f16=0x10be8d30`、`slot1.f16=0x10be8d50`、`slot2.f16=0x10be8d70`)。store の欠陥を単独で示す (negctl) |
| AFTER | 両方 (`fix_ld115.py`) | **PASS** (`N=0x10be8cf0`、`ret=0x3`、`count=0x3`、3 スロット × 4 欄すべて期待値と一致、`slot{0,1,2}.f16=0x10be8cf0`) |

判定: `DYN_SUMMARY after_fail=0/1`。

## 5. survey 942 unit (受入条件 3)

`ld115_e2e.sh` の 4/5・5/5。修復前 (BASE の IR) と修復後 (AFTER) を同じ build 条件で測った。

| 項目 | 修復前 | 修復後 |
|---|--:|--:|
| ok | 869 | 869 |
| miss / other / halt0 / oob / noproc | 47 / 1 / 8 / 16 / 1 | 47 / 1 / 8 / 16 / 1 |
| 遷移 (A → B) | 全 942 unit で kind 不変 (ok → ok 869、oob → oob 16、other → other 1、noproc → noproc 1、miss・halt0 も対角) | — |
| ok 退行 unit | **0** | — |
| kind 以外も含めた差分 unit (frames は深さのみ) | **0** | — |
| icall sites・targets の [ok, miss] 差 | 0 件 | 0 件 |

限界: 666a60 は survey の 942 unit で実行されない (REPORT_509 §4.3 で入口通過 0 件。本 run では再測定していない)。このため survey で ok 退行 0 となるのは、関数が実行されないことによる。修復の波及は survey では測れない (§8)。

## 6. DEFECTS.md

D20 の行に、666a60 の 2 箇所 (ループ内 store は確定、回数の初期値は別欠陥) と本 REPORT へのリンクを書いた。測定値は本 REPORT だけに置いた。

## 7. DEFECTS 行案 (新規候補、編集は PM 判断)

- **回数初期値の脱落 (新規候補、D20 とは別)**: 「`666a60` の entry: 機械語 `mov edx,[r14]` (r14 = N、直前に `mov [r14],ebx` で書いた count の読み直し) が IR で `store i64 0` になる。症状: ループ回数 0 → 2^32 回。wasm で trap。検出信号: 機械語の `mov r32,[rB]` (rB が直前に書いた値) に対し、IR の同じレジスタの初期化が定数 0 のもの。修復: `fix_ld115.py` (検証用、非本番)。観測: BASE で trap、AFTER で PASS (REPORT_2447 §4)。根本原因: 不明 (lift 段で既に入る可能性。未確認)」。
- arg2=0 の早期脱出欠落 (§2.4) は別の欠陥で、子 #2513 (LD-116) で扱う。

## 8. 検証 (WORKFLOW §6)

- 検証起点: `origin/main` = `3dbb35e0`。
- 測定 commit: `f049fe44` (コードを変えた最後の commit。`ld115_e2e.sh` の順序を本番に合わせた commit `7d0c3cc9` の後に、前提コメントの repo 外パスを ID に直した commit)。以後の commit は本 REPORT と DEFECTS.md・DOC_MAP.md のみ。
- 差分 0 の証跡: `git diff f049fe44 HEAD -- tools/m11/ldfix/fix_ld115.py tools/m11/ldfix/dyn_ld115.mjs tools/m11/ldfix/ld115_e2e.sh` の出力は空 (0 行、本文執筆時点の HEAD)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/ldfix/ld115_e2e.sh` (前提: `tools/m11/work` に work-m11、`[EMSDK]`、`capstone`・`pefile`)。
- 所要: **138.0 s** (`f049fe44`、2m18.019s。並列数 1、4 コア)。同じ検証を `7d0c3cc9` (`f049fe44` の直前、差分はコメント 1 行) で 137.1 s (2m17.097s)、fix_ld108 を入れる前の順序 `3b783145` で 137.2 s と 137.1 s (2m17.238s・2m17.146s) で実行し、DYN 行と survey の数値は全回で同一だった。load average は実行ごとに 0.06〜0.39 から 1.17 程度。
- 出力: BASE / MID / AFTER の DYN 行 (§4)、survey 2 本 (§5) は `f049fe44` の実行で §4・§5 の値と一致。
- 20 MiB 超の blob: `find tools/m11/ldfix -type f -size +20M -not -path '*/work/*'` は空 (実行済み)。
- 検証範囲: work-m11 の snapshot (`boot_final.prealloca.ll`、2026-10-10 生成、ir_conditions 無し) から現行 ldfix で作った IR。本番の `m11_gen_ir2.sh` 全体 (RetDec からの再生成) は未実施。`ir_sha256` の照合は snapshot に ir_conditions が無いので不可 (`m11_build.sh` は ir_conditions に `ldfix=applied` と指紋を記録してから build した)。
- 検証範囲外: 本番配線 (§9)、arg2=0 (§2.4)、他の 666a60 以外の関数 (fix_ld115 は関数名で限定)。
- 測定の記録: `ldfix` の `F3b(count-load)=5`・`F3c(store-arg)=36` は現行 ldfix の全体の集計 (666a60 の 2 箇所は未修復のまま出る)。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 回数 0 の早期脱出 (機械語 `666ae0`〜`666ae4`) が IR に無い (§2.4) | arg2=0 で wasm が trap する。実際の呼び出し元の arg2 分布は未調査 | 子 #2513 (LD-116) |
| `fix_ld115.py` の本番配線 (`m11_gen_ir2.sh` の fix_ld108 直後。`ld115=applied` の記録と build の要件を含む) | 通常 build の wasm は 666a60 が未修復 | 子 #2527 (LD-117) |
| 欠陥の根本原因 (RetDec のどの段で、値番号付けか・ループ回数の load が落ちるか) | 修復は後追いの単独パッチ。同型の別関数の探索は未実施。既存の追跡先 #911・#1091 は CLOSED | 本 PR の未解決表で追跡 (起票せず。原因調査のみのため) |
| survey で 666a60 が実行されない (REPORT_509 §4.3) ため、修復の波及を測れない | ok 退行 0 は「関数が実行されない」ことによる。`reach_509.sh` の再測定は未実施 | 本 PR の未解決表で追跡 (起票せず。再測定のみのため) |
| `audit_lsf_disp.py` / `audit_lsf.py` が 666a60 の 2 欠陥を検出しない (既存の検出信号の外) | 回帰の自動検出が無い | 本 PR の未解決表で追跡 (#2396 は CLOSED。検出信号の追加は実装に直結するが、今回の受入条件外) |
