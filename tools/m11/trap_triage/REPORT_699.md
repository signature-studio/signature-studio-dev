# #699: `8c5eb0` の件数 0 ループ先頭ガードを IR に復元 (unit 56: OOB → fail-fast) と、同型の全 IR 関数走査

**判定 (c 版, 本 HEAD)**: 受入 1 (ガード復元) は達成。改訂後の受入 2 (guard 有無で unit 56 の OOB `function_8c6530` が消える) は達成 (off=OOB → on=`function_8c5eb0` の fail-fast)。ガード辺は `8c6066` へ合流させず、機械語 `8c6067`〜`8c60ec` に合わせた (§1)。これにより rax.0 / rdx.1 の未定義値と、`8c608d` の rdx 依存の仮定が消えた。
**残る未解決**: `8c60df` の戻り値が機械語と食い違う経路は、本版で**解消した** (ガード辺は `[rbp+0x80]` を返す)。ただし既存 IR の別経路 (件数 >= 1 かつ arg2 下位 byte == 0) の戻り値は、本 PR の対象外として未測定 (§6, #718)。
検証 HEAD: `6948c5b7` (guard pass の修正 commit)。実測は同 HEAD で n=3 (§3-1, §3-3)。
既知類型との関係 (DEFECTS.md): **D1b と同型の症状・検出信号** (機械語 jcc に対応する IR `br` が無く、飛び先が無条件実行になる)。ただし **根本原因は未切り分け** (D1b は stage-0 フラグが定数に畳まれる機構。本件は生 lift の段階で既に jcc が無く、同じ機構かは未確認。§2, §6)。
件数 0 の空リストを `8c6530` へ渡す経路は塞がり、unit 56 は OOB から fail-fast に変わった。

## 1. 修復の内容

機械語 (`8c5eb0`, capstone 5.0.7, `block00031_PE.bin` を VA 直接逆アセンブル):

```
8c5f06: xor eax, eax            ; rax = 0
8c5f0c: mov ebx, [rcx+0x14]     ; ebx = 件数
8c5f0f: sub ebx, 1
8c5f12: mov [rbp+0x4c], eax     ; i = 0
8c5f15: cmp [rbp+0x4c], ebx     ; i > 件数-1 (件数 <= 0) なら本体を飛ばす
8c5f18: jg 0x8c6066
...
8c6066: cmp qword [rbp+0x90], 0 ; arg3
8c606f: je 0x8c6084
8c6071: mov rcx, [rbp+0x90]; mov rdx, [rbp+0x80]; call 0x8ca670   ; arg3 != 0 のみ
8c6084: cmp byte [rbp+0x88], 0  ; arg2 下位 byte
8c608b: je 0x8c60df
8c608d: mov rcx, [rbp+0x80]; call 0x410360 ; arg2 下位 byte != 0 (rdx は設定されない)
8c60df: mov rax, [rbp+0x80]     ; 戻り値
8c60ec: ret
```

IR (`dec_label_pc_8c5ef5`) は `%9 = load i32 [rcx+0x14]` (件数) の後、無条件 `br label %dec_label_pc_8c5f23` に進む。修復 pass (`tools/m11/guard699/m11_guard699.py`, `--mode on`) はこの末尾の `br` を次の形に置換する。

```llvm
  %g699 = icmp sle i32 %9, 0
  br i1 %g699, label %dec_label_pc_8c5ef5_g699, label %dec_label_pc_8c5f23
dec_label_pc_8c5ef5_g699:                ; 件数 0 ガード辺 (8c6066 へ合流させない)
  %g699a = and i64 %arg2, 255
  %g699b = icmp ne i64 %g699a, 0
  br i1 %g699b, label %..._g699_t, label %..._g699_e
..._g699_t:                              ; arg2 下位 byte != 0: fail-fast (機械語 8c608d は vtable 呼出し)
  call void @llvm.trap()
  unreachable
..._g699_e:                              ; arg2 下位 byte == 0 (機械語 8c608b je 8c60df)
  %g699c = icmp eq i64 %arg3, 0
  br i1 %g699c, label %..._g699_r, label %..._g699_c
..._g699_c:                              ; arg3 != 0: 機械語 8c6071 の 8ca670 (戻り値は捨てる)
  %g699d = call i64 @function_8ca670(i64 %arg3, i64 %stack_var_8.0.reload)
  br label %..._g699_r
..._g699_r:                              ; 機械語 8c60df: mov rax,[rbp+0x80]; ret
  ret i64 %stack_var_8.0.reload
```

- **件数 > 0 の経路は元 IR と一致**: `dec_label_pc_8c5f23` への枝は store を通らない。元 IR との差分は末尾 `br` 1 行の置換のみ (`diff` で確認)。
- **ガード辺の値の扱い**: ガード辺は `rax.0` / `rdx.1` / `rax.2` / `rdx.2` のどれも読まない。`8c6066` に入るのは件数 >= 1 の経路 (`8c6057` からの枝) だけで、その経路では `rax.0` (`8c6034`/`8c603f`) と `rdx.1` が必ず store される (§1-a)。前版 (b') の `rdx.1 := 0` の store と、`rdx` 仮定 `zext(arg2)` は、この版では存在しない。
- **分岐条件**: `count <= 0` と機械語の `jg` は件数 ∈ [INT_MIN+1, 0] で一致する。**count = INT_MIN のみ不一致** (機械語は `sub ebx,1` の wrap で jg が立たず本体を実行、IR は飛ばす)。件数は非負の list 長で、到達可否は未確認 (§6)。
- **戻り値**: arg2 下位 byte == 0 の 0 件経路は `[rbp+0x80]` を返す。機械語 `8c60df: mov rax,[rbp+0x80]` と一致する。`[rbp+0x80]` は `8c5ebd` で rcx (= 関数の arg1) を保存した値で、`8c5eee` は arg2 下位 byte ≠ 0 の枝でしか書かないため、この経路では arg1 のまま。IR の `%stack_var_8.0.reload` は `%0 = ptrtoint arg1` の store を読む (`8c5eb0`, `dec_label_pc_8c5eb0`) ので同じ値。
- **arg2 下位 byte != 0 の 0 件経路 (fail-fast)**: 機械語は `8c608d: call 410360` で vtable 呼出しを行い、正常値を返しうる。本版は trap に落とす。**これは機械語からの挙動変更** で、正常値を返す機械語と一致しない。ただし trap は fail-fast であり、件数 0 の空リストを処理する経路が黙って誤った値を返すことを防ぐ。本版でこの経路が実際に到達する unit は、§3-1 の unit 56 (`unreachable`) のみを観測している (§6)。
- **mode off**: 逆変換 (脱落状態に戻す。ネガコン用)。`on → off` で元の IR にバイト一致、`on → on` で無変更 (冪等) を確認 (§3-0)。
- `m11_build.sh` は alloca 修正の後に pass を適用する (既定 on)。`M11_GUARD699=off` で脱落状態に戻す。`M11_GUARD699_COND` で条件を差し替える (ネガコン用)。

### 1-a. rax.0 / rdx.1 / rdx.2 の読み書き全件 (`function_8c5eb0`, 元 IR `work-m11` の `boot_final.ll`)

`%rdx.1.reg2mem` / `%rdx.2.reg2mem` / `%rax.0.reg2mem` を読む・書く全ブロック (`grep` 抽出, `awk` で行の所属ブロックを付与):

```
dec_label_pc_8c6034: store i64 %rdx.0.reload, ptr %rdx.1.reg2mem     ; store rdx.1 (件数>=1 経路)
dec_label_pc_8c6034: store i64 %12, ptr %rax.0.reg2mem               ; store rax.0 (件数>=1 経路)
dec_label_pc_8c603f: store i64 %12, ptr %rdx.1.reg2mem               ; store rdx.1 (件数>=1 経路)
dec_label_pc_8c603f: store i64 %64, ptr %rax.0.reg2mem               ; store rax.0 (件数>=1 経路)
dec_label_pc_8c6066: %rdx.1.reload = load i64, ptr %rdx.1.reg2mem    ; load rdx.1 (合流点)
dec_label_pc_8c6066: %rax.0.reload = load i64, ptr %rax.0.reg2mem    ; load rax.0 (合流点)
dec_label_pc_8c6066: store i64 %rdx.1.reload, ptr %rdx.2.reg2mem     ; store rdx.2
dec_label_pc_8c6071: store i64 %stack_var_8.0.reload, ptr %rdx.2.reg2mem ; store rdx.2 (arg3 != 0)
dec_label_pc_8c608d: %rdx.2.reload = load i64, ptr %rdx.2.reg2mem    ; load rdx.2
dec_label_pc_8c608d: call i64 @function_410360(..., %rdx.2.reload)  ; rdx.2 を引数として渡す
```

- 読みの要点: `dec_label_pc_8c6066` (合流点) に入るのは `8c6057` からの枝だけ (件数 >= 1)。`8c6034`/`8c603f` は件数 >= 1 の経路でのみ rax.0 / rdx.1 を store する。よって合流点の load は必ず初期化済み。
- ガード辺 (`_g699_*`) は `8c6066` を経由しないため、`rax.0`/`rdx.1`/`rdx.2` を読まない (上記 grep にガード辺のブロックは現れない)。
- `8c608d` の `rdx.2` は `8c6066` 経由でしか到達しない。ガード辺はこの経路を通らない (arg2 下位 byte != 0 は trap、== 0 は `8c60df` で返す)。
- 検証: 本 HEAD の IR 全体で `rdx.1` / `rdx.2` / `rax.0` を読む命令は上表の全件 (`on.ll` と `boot_final.ll` で同一)。

## 2. 機構の切り分け (RetDec 段)

脱落は自前の IR 後処理より**前**で起きている。根拠: 生の RetDec 出力 `work/boot2.lift.ll` (関数 `function_8c5eb0`) の `dec_label_pc_8c5ef5` ブロックには、`cmp` のフラグ計算も `jg` も無く、無条件 `br` だけが残る。自前の後処理 (`m11_merge`/`numfix`/`asmfix`/`passes`/`genstubs`/`dotfix`/`ldfix`/`qstore`/`alloca`) はすべてこの後に走る。
RetDec の CFG 復元 (jcc の終端化) と命令翻訳 (フラグ) のどちらで落ちたかは**未切り分け** (§6)。

## 3. 実測

検証 HEAD `6948c5b7` (guard pass の修正 commit)。素材は `$RUNNER_TEMP` に展開 (`fl-win64` = `$RUNNER_TEMP/fl-win64`, `work-m11` = `$RUNNER_TEMP/m11src/tools/m11/work`)。作業コピーは `$RUNNER_TEMP/run717/tools/` で、repo の `tools/m11/work/` は使っていない。capstone 5.0.7 / pefile は `$RUNNER_TEMP/venv`。node は v22.23.3。

### 3-0. pass の性質 (`m11_guard699.py`)

- `on → on`: 無変更 (冪等)。`on → off`: 元の `boot_final.ll` にバイト一致。
- `on` の差分は `function_8c5eb0` 内の末尾 `br` 1 行の置換 (上記 §1 の 15 行の追加のみ)。`clang -x ir -fsyntax-only` で構文 OK (rc 0)。

### 3-1. negctl (`bash tools/m11/trap_triage/negctl_699.sh`, HEAD `6948c5b7`, n=3)

比較元は同一の `m11_ov.c`。構成: off = guard 無効 (基準) / fix = guard 有効 (既定) / ng = 偽ガード (`icmp eq i32 %9, 123456789`)。

| run | rc | build+survey 所要 | off | fix | ng | unit 56 (off / fix / ng) | G1 | G2 | G3 | diff off→fix | diff off→ng |
|---|---|---|---|---|---|---|---|---|---|---|---|
| r1 | 0 | 121 秒 | ok 870 / trap 24 / oom 1 / miss 46 / noproc 1 | 同左 | 同左 | trap / trap / trap | PASS | PASS | PASS | n=0 | n=0 |
| r2 | 0 | 115 秒 | 同左 | 同左 | 同左 | trap / trap / trap | PASS | PASS | PASS | n=0 | n=0 |
| r3 | 0 | 116 秒 | 同左 | 同左 | 同左 | trap / trap / trap | PASS | PASS | PASS | n=0 | n=0 |

- G2 の trap 種別 (`M11_SURVEY_STACK=56`): off = `memory access out of bounds` (`function_8c6530`)、fix = `unreachable` (`function_8c5eb0` のガード辺 `_t`)。ネガコン ng = off と同じ (OOB)。
- 注 (前版との差): 前版 (b') の旧 G2 (unit 56 が ok) は、`rdx.1 := zext(arg2)` の仮定を前提にしていた。本版は ok にならない。改訂後の受入 2 (OOB の消失) で判定する (§3-4)。
- 前版 (`a2190b26`, `57ea5ada`) の数値とは HEAD が違うため比較しない。
- **後続 (#3077 後の現版, 測定 commit `6049203d2`, §9)**: fail-fast 辺は `function_410360` の戻り値を返す形になった。よって上表の fix=`unreachable` は当時の版の値。現版の fix は `returned` (`negctl_699.sh` の G2 も `returned` に更新済み)。

### 3-2. 全 IR 関数の分岐突合走査 (`guard699/scan_guard.py`, HEAD `6948c5b7`)

規則: 機械語 (`.pdata` 区間の線型 disasm) の各 jcc (VA `A`, 絶対 target `T`) について、A を含む IR ブロック `B` の後続集合 `succ(B)` と突合する。
- `dropped`: `T ∉ succ(B)` (jcc が IR から消えている候補)。
- `strict` (ループ先頭ガード型): dropped かつ、A の直前 2 命令に `cmp/test`、`T > A`、`B` の終端が無条件 `br` で後続 `L` が `B` より後方、`L` に後方ブロックからの back-edge がある。

| 入力 IR | 関数 | jcc | dropped | dropped (target がラベルでない) | strict | 8c5eb0 |
|---|---|---|---|---|---|---|
| ガード無し (`--mode off`) | 6969 | 25618 | 1423 | 7058 | **406** | strict (8c5f18 jg → 8c6066) |
| ガード有り (`--mode on`) | 6969 | 25618 | 1423 | 7058 | **405** | 消える |

- 差分は `function_8c5eb0` の `8c5f18` の 1 件だけ (strict 集合の差)。`dropped` は両方 1423 (ガード辺は新しい jcc を持たないため、dropped の集合は変わらない)。
- **限界 (重要)**: strict の 405 件は**未検証の候補**。規則は heuristic で、偽陽性の率は未測定。405 件のうち miscompile である件数は本件では言えない。`dropped_target_not_label` の 7058 は内訳 (関数外への tail jump か否か) 未調査。

### 3-3. e2e (`bash tools/m11/m11_e2e.sh`, HEAD `6948c5b7`, n=3)

3 回とも rc=0。

| run | rc | 所要 | reached_stage | 停止理由 | survey (942 unit 個別隔離) |
|---|---|---|---|---|---|
| r1 | 0 | 50 秒 | 4 | `trap "unreachable" @ function_8c5eb0 <- function_56fde0 <- m11_tr_function_56fde0 <- m11_icall <- function_4120c0` | ok 870 / trap 25 (oom 1) / clobber 0 / miss 46 / noproc 1 |
| r2 | 0 | 45 秒 | 同左 | 同左 | 同左 |
| r3 | 0 | 44 秒 | 同左 | 同左 | 同左 |

- 停止理由は `function_8c5eb0` の fail-fast (`unreachable`)。full InitUnits run はここで止まる。
- **停止時点の `units_run` と未検証 unit 数は、本 HEAD (`6948c5b7`) の 3 run では記録していない**。e2e のログ (`work/e2e_steps.log` 等) は本 run の環境に残っておらず、`work/` は未展開、素材 `work-m11` / `toolchain-retdec` は未取得のため、再取得もできない。よって「停止後に検証されなかった unit 数」は本 HEAD では確定しない。e2e が unit 56 の fail-fast で早期終了した可能性を否定しない。
- 参考 (別 HEAD・別コード版): guard 実装が `6948c5b7` より前の `a2190b26` では `units_run=53/942` (停止後 889 未検証) を記録している。guard の書き換えで停止位置が変わり得るため、この値を本 HEAD に流用しない。
- survey (下表の 942 unit 個別隔離) と e2e の full run は別の測定。survey の `ok 870 / trap 25` は全 942 unit の独立実行結果で、fail-fast の影響を受けない。
- 所要は `date +%s` の差 (`m11_e2e.sh` の開始から終了まで, 4 vCPU)。
- 前提: `ir_conditions.json` を `m11_e2e.sh` が作り直した (`ldfix=applied`, `qstore=applied`)。
- 限界: survey の ok/trap ラベル比較のみ。出力 (戻り値・メモリ) の同一性は未比較。

### 3-4. 判定の表 (受入条件との対応)

| 受入条件 (#699) | 結果 | 根拠 |
|---|---|---|
| 8c5eb0 の件数 0 ガードを復元 (IR pass) | 達成 | §1, `m11_guard699.py`, `m11_build.sh` 組込み |
| **改訂後 (PM 判断 #699 コメント 6147966392)**: guard 有/無で unit 56 の OOB (`function_8c6530`) が消える | 達成 (off=OOB、on=`function_8c5eb0` の fail-fast `unreachable`) | §3-1 (n=3)。G2 |
| 当初条件: unit 56 が ok。off 比の退行 0 (survey ラベルのみ) | 未達 (別原因で trap)。本版の fail-fast 版では ok にならない | §3-1。子 issue #856 |
| ネガコン (ガード条件を壊すと 56 が trap に戻る) を数値で残す | 達成 | §3-1 G3 (ng: off と同じ unit 差 0, unit 56 trap) |
| 同型の脱落を全 unit 走査し件数を測る | 達成 (件数のみ。真偽は未検証) | §3-2 (strict 406 / 405) |
| RetDec がなぜ分岐を落としたかの機構を記録 | 未達 (生 lift 段で既に欠落まで。CFG 復元か翻訳かは未切り分け) | §2, §6 → #718 |

## 4. 再現

```sh
# 素材: fl-win64 は $RUNNER_TEMP/fl-win64 に展開 (extracted/block00031_PE.bin)。work-m11 は tools/m11/work に展開 (作業コピーで実行)
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd tools/m11
bash trap_triage/negctl_699.sh                         # §3-1 (G1〜G3, exit 1 で不合格)
python3 guard699/m11_guard699.py work/boot_final.ll work/v699/ir_off.ll --mode off
python3 guard699/m11_guard699.py work/boot_final.ll work/v699/ir_on.ll  --mode on
python3 guard699/scan_guard.py work/v699/ir_off.ll --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin"  # §3-2
bash m11_e2e.sh                                        # §3-3
```

前提: `capstone`・`pefile` を import できること (無いと qstore / ldfix が skip され fail-closed)。`m11_e2e.sh` / `m11_gen_ir2.sh` は `FL_WIN64_DIR` 配下の `extracted/block00031_PE.bin` を読む。`ir_conditions.json` の PE パスと一致しないと build が fail-closed で止まる (`m11_gen_ir2.sh` で作り直す)。

## 5. DEFECTS.md 行案 (PM 判断。直接編集はしない)

| ID | 分類 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| (番号は PM 採番。D1b と同型の疑い) | fe または opt (未切り分け) | 件数 0 のループで本体が 1 回以上実行される。空リストの `Items[0]` を読み、不正レコードを OOB に渡す | ループ先頭の `cmp; jg exit` が RetDec の生 IR から脱落 (機構は未特定。D1b の「jcc が IR から消える」と症状・検出信号は一致、根本原因は同一か未確認) | `8c5eb0` (unit 56, #662/#699): `8c5f15-8c5f18` ↔ `dec_label_pc_8c5ef5` の無条件 `br`。生 lift `boot2.lift.ll` で既に欠落 | 機械語 jcc に対応する IR 後続が無い (§3-2 の dropped)。strict 規則 (ループ head 型) | `m11_guard699.py` (IR pass, 冪等・双方向) で `icmp sle count,0` 分岐を復元。0 件経路は機械語の戻り値 (`[rbp+0x80]`) に合わせた独立ブロックへ分ける (§1) |

## 6. 未解決

本版 (`6948c5b7`) で解消した項目:
- **rax.0 / rdx.1 の未定義値**: ガード辺は `8c6066` へ合流させないため、両スロットを読まない (§1, §1-a)。
- **`8c60df` の戻り値不一致 (ガード辺の経路)**: ガード辺の arg2 下位 byte == 0 の経路は `[rbp+0x80]` を返す (機械語 `8c60df` と一致)。前版の「IR は rax.1 = 0 を返す」は、この版では起きない。

本版でも未解決 (approve 判断に影響しうる):
- **(i) 件数 >= 1 かつ arg2 下位 byte == 0 の経路の戻り値**: 既存 IR の `dec_label_pc_8c60df` は `ret rax.2` を返す (`rax.2` は `8c6084` で `rax.1` を受ける)。`rax.1` は件数 >= 1 の経路では `8c6066` の `rax.0` (`8c6034`/`8c603f` の結果) か `8ca670` の結果になる。機械語は `8c60df` で `[rbp+0x80]` を返す。よって件数 >= 1 の経路でも IR と機械語の戻り値は食い違いうる。ガード無しでの再現は**未測定**。survey は戻り値を出力しないため、比較手段が無い。**guard の変更対象外 (件数 >= 1) の既存の食い違い。#718 へ起票依頼。**
- **(ii) 件数 0 ∧ arg2 下位 byte != 0 の経路 (fail-fast)**: 機械語は `8c608d` の vtable 呼出しで値を返す。本版は trap。挙動変更として記録する。この経路が他 unit で到達するかは未確認 (本版の survey では unit 56 の `unreachable` のみ観測)。**(#3077 後の現版では trap ではなく `function_410360` の戻り値を返す。§9)**
- **(iii) count = INT_MIN**: 機械語の jg と不一致 (§1)。到達可否は未確認。
- **RetDec の脱落機構** (CFG 復元か命令翻訳か) の切り分け (§2)。 #718 (`[M11-N35]`)。
- **strict 候補 405 件の真偽** (偽陽性率を含む)。#718。
- **`dropped_target_not_label` 7058 の内訳**。#718。
- **同一 guard 条件での survey の揺らぎ** (前版の f3d5341 / bcc605d2 では 866/867・870/871 と動いた)。本 HEAD の 3 回 (negctl 3 回 + e2e 3 回) では ok 870 で一致。揺らぎの原因は未切り分け。#718。
- **`m11_e2e.sh` の PE 固定パス (`[WIN64]`)** と node v26 前提。runner では `FL_WIN64_DIR` と node v22 で動かす。#680。
- **`docs/DEFECTS.md` の行案 (D1b との関係の判定)**: PM 判断。

## 7. 次タスク提案

- 件数 >= 1 かつ arg2 下位 byte == 0 の戻り値 (§6 (i)) を、呼出側の戻り値を観測する計装で測る。これは survey の拡張 (戻り値の記録) を要するため、本 PR の範囲外。
- strict 候補 405 件を 1 件ずつ survey (guard 有効化の ablation) で検証する。
- RetDec の CFG 復元で jcc の条件辺が落ちる条件を、`8c5eb0` と同型の最小再現で切り分ける。

## 8. 範囲 / 範囲外

- 範囲: `tools/m11/m11_build.sh` (pass の組込み), `tools/m11/guard699/` (pass と走査), `tools/m11/trap_triage/negctl_699.sh`, 本 REPORT。
- 範囲外: `m11_ov.c` (変更なし。`8c7710` 転記は #700)。`docs/DEFECTS.md` (PM 判断)。
- 20 MiB 超の blob: 追加なし。`work/` は gitignore。

## 9. #3077 後の現版の再測定と init 列の解放側 `function_41cd70` (#3246)

測定 commit: `6049203d2` (`negctl_699.sh` の G2 を `returned` に更新した commit)。素材: `fl-win64`・`work-m11` を展開し、`m11_gen_ir2.sh` で `work/ir_conditions.json` を作り直した (rc 0)。

### 9-1. negctl (`bash tools/m11/trap_triage/negctl_699.sh`, HEAD `6049203d2`)

| 項目 | 結果 |
|---|---|
| rc / 所要 | rc 0 / 72 秒 (build+survey 3 構成) |
| load | 0.10 0.49 0.37 → 0.72 0.60 0.41 |
| unit 56 (off / fix / ng) | trap (OOB `function_8c6530`) / ok (`returned 1`) / trap (OOB) |
| counts off | ok 872 / trap 22 / miss 47 / noproc 1 |
| counts fix | ok 873 / trap 21 / miss 47 / noproc 1 |
| counts ng | ok 872 / trap 22 / miss 47 / noproc 1 |
| G1 | PASS |
| G2 | PASS (off=OOB → fix=`returned`) |
| G3 | PASS (ng vs off: diff n=0) |
| diff off→fix | n=1 `[(56, 'trap', 'ok')]` |
| diff off→ng | n=0 |

G2 の期待値を当時の `unreachable` から現版の `returned` に変えた。`unreachable` は #3077 で消えた (fail-fast 辺は `function_410360` の戻り値を返す)。fix で unit 56 が ok になるのは、G2 の条件ではなく観測結果である (§3-4 の「当初条件」は従来どおり未達)。

### 9-2. `function_41cd70` が init 列の 4 番目に入る理由

- 機構: `m11_bounds.py` は `array1` (`0xf768e0`, 942 entry) の各 entry の `(init, final)` の両列を、並び順に `work/inits_text.txt` へ書く。`inits_text.txt` は `m11_passes.py --init-list` が読み、列挙された関数に init prologue counter を入れる。
- `array1` entry 1 は `(init=0x41ce10, final=0x41cd70)`。`function_41cd70` は entry 1 の **final 列**なので、列挙の 4 番目 (`41ce10` の直後) に入る。init 呼出しではない。
- 中身 (`boot_final.ll`): `0x11E6A38` のフラグを +1 し、結果が 0 のとき解放本体へ進む。解放本体は `function_41bad0` 等と `function_418f20` を呼び、`function_418f20` は `DeleteCriticalSection(0x11EAF00)` を呼ぶ。`function_41ce10` は同じフラグを −1 し、結果が 0 のとき `function_418e10` (`InitializeCriticalSection(0x11EAF00)`) を呼ぶ。対になる init / final の組。
- 従来の記録 (`REPORT_APPENDIX_2880.md` の「推定」) は、この対応で確定した。解放の早期実行の有無 (#3077 受入 4 の残り) は、boot が `41cd70` に届く条件の実測で別に確かめる (未計測・追跡先は未決。§9 末尾)。本節は掲載理由の確定まで。

### 9-3. `410360` の戻り値 (参照)

`function_410360` の vtable 呼出し脱落 (D15 型) は `REPORT_699` 本体 §6 (ii) と `REPORT_APPENDIX_3077.md` §4-1 が正本。本節では変更しない。

未解決 (本 PR の範囲外): 解放の早期実行の有無 (boot の `41cd70` 到達条件)。起票先: 未決。親 #3077 は CLOSED (2026-10-15 確認) で、open な追跡 issue は無い。PM の判断待ち (子 issue の起票は `docs/WORKFLOW.md` §3 の「未解決の追跡だけの子は起票しない」に従い見送り)。
