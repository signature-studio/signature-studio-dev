# #699: `8c5eb0` の件数 0 ループ先頭ガードを IR に復元 (unit 56: OOB → ok) と、同型の全 IR 関数走査

**判定 (b' 版, §3-6)**: 受入 1 (ガード復元) とネガコンは実測で達成。unit 56 は ok にならず、0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 の経路を fail-fast (`llvm.trap`) に落とした。unit 56 の ok 化は未達 (旧版の ok 化は未証明の rdx 仮定に依存していたため撤回)。「退行 0」は survey ラベルの比較のみで、出力の同一性は未確認。Closes ではなく Refs (未達 = RetDec の脱落機構の記録, §6)。
件数 0 の空リストを `8c6530` へ渡す経路は塞がり、unit 56 は trap から ok になった。

既知類型との関係 (DEFECTS.md): **D1b と同型の症状・検出信号** (機械語の jcc に対応する IR `br` が無く、飛び先が無条件実行になる)。ただし **根本原因は未切り分け** (D1b は stage-0 のフラグが定数に畳まれる機構。本件は生 lift の段階で既に jcc が無く、同じ機構かは未確認。§2, §6)。新規番号は付けず、行案 (§5) は PM 判断。番号は (DEFECTS.md) 体系。

検証起点: `8d883c3` (main)。作業 branch は `d9bcc52` (親 PR #700 の head) から切った。修正 commit `9dd4d55`。
**検証 HEAD: `bcc605d2` (本版 = `f3d5341` に `origin/main` を merge した commit)**。negctl (§3-1) は本 HEAD で rc 0・3 構成 PASS。e2e (§3-3) は本 HEAD で rc 0 だが、停止理由が `main` 取り込み前と変わった (本版で未切り分け、§3-3 参照)。
rdx.1 の値と `8c60df` の戻り値不一致は **未解決のまま** (§1, §6)。approve 判断に影響する。本版でもこれらの解消は行っておらず、PM 判断を要求する。

## 1. 修復の内容

> **approve 判断への影響 (PM 判断 (b') 採用)**: 0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 の経路は `llvm.trap` に落とす (値の正しさは主張しない)。他の 0 件経路は rdx.1 を読まれない (IR CFG で確認)。rax.0=0 は arg3==0 の戻り値に届くため、§6 (ii) の戻り値不一致が未解決で残る。

機械語 (`8c5eb0`, capstone 実測):

```
8c5f0c: mov ebx, [rcx+0x14]     ; ebx = 件数
8c5f0f: sub ebx, 1
8c5f12: mov [rbp+0x4c], eax     ; i = 0
8c5f15: cmp [rbp+0x4c], ebx     ; i > 件数-1 (件数 <= 0) なら本体を飛ばす
8c5f18: jg 0x8c6066
```

IR (`dec_label_pc_8c5ef5`) は `%9 = load i32 [rcx+0x14]` (件数) の後、無条件 `br label %dec_label_pc_8c5f23` に進む。
修復はこの末尾の `br` を、ガード辺専用ブロックを挟む形に置換する (`tools/m11/guard699/m11_guard699.py`):

```llvm
  %g699 = icmp sle i32 %9, 0
  br i1 %g699, label %dec_label_pc_8c5ef5_g699, label %dec_label_pc_8c5f23
dec_label_pc_8c5ef5_g699:
  %g699a = and i64 %arg2, 255
  %g699b = icmp ne i64 %g699a, 0
  %g699t = icmp eq i64 %arg3, 0
  %g699c = and i1 %g699t, %g699b
  br i1 %g699c, label %dec_label_pc_8c5ef5_g699_t, label %dec_label_pc_8c5ef5_g699_e
dec_label_pc_8c5ef5_g699_t:            ; 0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 (8c608d → 410360 の経路) は fail-fast
  call void @llvm.trap()
  unreachable
dec_label_pc_8c5ef5_g699_e:
  store i64 0, ptr %rax.0.reg2mem          ; rax.0 := 0 (機械語 8c5f06 xor eax,eax で確定)
  store i64 0, ptr %rdx.1.reg2mem          ; 読まれない (上記 §1 冒頭)
  br label %dec_label_pc_8c6066
```

- **件数 > 0 の経路は元 IR と一致する**: 件数 > 0 は `dec_label_pc_8c5f23` への枝を取るため、store は通らない。元 IR との差分は末尾 `br` 1 行の置換 (`diff` で確認: `br label %dec_label_pc_8c5f23` → 上記 6 行)。store は専用ブロック `_g699` にだけ置く (前版は分岐の前に置いていたため件数 > 0 でも rdx を上書きした。レビュー指摘 2 の 2 回目)。
- 分岐条件: `count <= 0` は機械語の `jg` と件数 ∈ [INT_MIN+1, 0] で一致する。**count = INT_MIN のみ不一致**: 機械語は `sub ebx,1` が wrap して `0x7FFFFFFF` と比較し jg が立たず本体を実行、IR は飛ばす。件数は非負の list 長なので本件では到達しないと見なすが、確認はしていない (厳密化 `sub` + `icmp slt` は未実施)。
- **ガード辺の値**: ガードで飛ばすと、元 IR で `%rax.0.reg2mem`・`%rdx.1.reg2mem` を store するのは `dec_label_pc_8c6034`・`dec_label_pc_8c603f` だけで、飛び先 `dec_label_pc_8c6066` が両方を load する (phi は無い)。このままでは 0 件経路で未定義値になるため、専用ブロックで明示 store する。
  - **rax.0 := 0 (機械語で確定)**: `8c5f06: xor eax,eax` の後、`8c5f18: jg` まで rax は書かれない (`8c5f08`〜`8c5f15` は rcx・ebx・[rbp+0x4c]・flags のみ)。0 件経路は rax=0 のまま `8c6066` に入る。
    - **訂正 (f3e9950 で確認)**: 前版の「`8c60df` で上書きされるため結果に効く経路は無い」は誤り。IR の `dec_label_pc_8c60df` は `ret rax.2` で、rax.2 は `8c6084` で rax.1 (= ガード辺の 0) を受ける。一方、機械語 `8c60df: mov rax,[rbp+0x80]` は [rbp+0x80] を返す。よって 0 件 ∧ arg2 下位 byte == 0 (`8c608b je 8c60df`) の経路では、IR は 0 を返し、機械語は entry の rcx (= [rbp+0x80], `8c5ebd` で保存、`8c5eee` は arg2 下位 byte ≠ 0 の枝でのみ書く) を返す。**ガード辺の rax.0 := 0 は戻り値に届き、この経路で機械語と食い違う。** この食い違いは `8c60df` の戻り値不一致 (§6) の一部で、件数 > 0 の経路も同じ構造だが、ガード無しでの再現は未実測 (前版の「ガード無しでも再現」は機械語の比較のみに基づく)。ガード辺の rax 値は未確定。
  - **rdx.1 (旧版の zext(arg2) 仮定は撤回、(b') で置換)**: 0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 の経路は trap に落とす。それ以外では rdx.1 は読まれない (§1 冒頭)。以下は旧版の調査記録: 機械語では `8c5efd: call 8c67a0` の後の rdx は callee 依存。`8c67a0` は中で `8c7c80` を呼び (`mov rdx, rbx` 後), `8c5eda` の `410320` は `call qword ptr [rax-0x30]` (vtable 間接 call、target は IR から決まらない) を呼ぶ。rdx の出力は IR から確定できない。`8c5ee1: movzx rdx, byte [rbp+0x88]` を経由する値として、既存 IR の `8c6071` (`8ca670` 後の rdx を引数 rdx と同じとする) と同じ pass-through 規約に合わせた。**410320 と 8c67a0 が rdx を変えないことは確認していない**。
  - **機械語での確認 (head b47f7f7, capstone 5.0.7, `block00031_PE.bin` を VA 直接逆アセンブル)**:
    - `8c5efd: call 8c67a0` → `8c67a0` は `call 8c5c90` の後 `call 8c7c80` して `ret` のみ (rdx を書かない)。8c5f02 時点の rdx は `8c7c80` の ret 時の rdx と同じ。
    - `8c7c80` の ret 時の rdx は末尾の経路で決まり、`8c7710` の戻り・`40f9e0` の戻り・vtable 間接 call (`call qword ptr [rbx]`) の戻りのいずれかになる。callee 依存で、逆アセンブルだけでは確定しない。
    - 0 件 ∧ arg3 == 0 ∧ arg2 下位 byte ≠ 0 の経路 (`8c608d: call 410360`): `410360` は rdx を読まず、rcx だけ設定して `call qword ptr [rbx-0x50]` (vtable 先) へ rdx をそのまま渡す。vtable 先が rdx を読むかは未確認。したがってこの経路で rdx は参照されうる。
    - **結論: rdx.1 の正しい値は未確定。0 件経路で結果に影響しないことも未証明。** 仮定 `zext(arg2)` は未証明のまま残す。approve 判断に影響する。
    - **rdx の由来 (機械語, head f3e9950 で再確認, capstone 5.0.7, `block00031_PE.bin` を VA 直接逆アセンブル)**:
      - `8c5ee1` で `movzx rdx, byte [rbp+0x88]` (仮定の元) → `8c5efd: call 8c67a0` がこの rdx を上書きする。
      - `8c67a0`: `call 8c5c90` の後に `mov rdx, rbx` して `call 8c7c80`、`ret`。`8c67a0` 自身は rdx の出力を決めない。
      - `8c7c80` の ret 経路 (3 本): (a) rsi≠0 かつ `[rdi+0x4c]==0` (`8c7cc4`→`8c7ce8`): rdx は `call 8c7710` の戻り値のまま。(b) `[rdi+0x4c]≠0` (`8c7cc8`〜`8c7ce6`): `call 8c73b0` の後に `call qword ptr [rbx]` (vtable 先)。(c) rsi=0 (`8c7c9e`〜`8c7cbc`): `call 40f9e0` の後に `call qword ptr [rbx]`。(b)(c) の ret 時の rdx は vtable 先が返す値。
      - `8c5f02`〜`8c608d` の 0 件経路 (`8c5f18 jg` → `8c6066`): rdx への書き込みは無い。`8c6067` の `je 8c6084` (arg3 == 0) で `8c6071`〜`8c607f` (`mov rdx, [rbp+0x80]` を含む) も飛ばす。よって `8c608d` 時点の rdx = `8c67a0` の戻り時点の rdx = 上記 (a)〜(c) のいずれかの戻り値。
      - `8c608d: call 410360`: `410360` (`410360`〜`410380`) は rdx を変えず、`call qword ptr [rbx-0x50]` (rbx = `*rcx`) へ渡す。**rdx は vtable 先の第 2 引数として参照される。** vtable 先の実体は未特定。
      - IR 対応: `dec_label_pc_8c6066` は `%rdx.2 = %rdx.1` を経て、`dec_label_pc_8c608d` の `call function_410360(…, %rdx.2)` へ渡す (`fn8c5eb0` 抜粋)。
      - **結論 (再確認): 参照の有無 = 有り (`8c608d` → `410360` → `[rbx-0x50]` の第 2 引数)。値の由来 = callee 依存 ((a) `8c7710` の戻り、(b)(c) vtable 先の戻り)。`zext(arg2)` の正しさは未証明のまま。** 未確認: `8c7710` の rdx 出力、`[rbx-0x50]` と `[rbx]` の vtable 先の実体と rdx の扱い。
    - **head 11091dc での再確認 (capstone 5.0.7, `block00031_PE.bin`, VA 直接)**: `8c5eda`〜`8c5f18` と `8c6057`〜`8c60ec` を逆アセンブルし、上記の経路を確認した。`8c608d: mov rcx,[rbp+0x80]; call 410360` で rdx は設定されない。`8c60df: mov rax,[rbp+0x80]` (`8c608b je` の 0 件 ∧ arg2 下位 byte == 0 の枝)。IR の `dec_label_pc_8c6084`〜`8c608d` とは対応する。
    - 今回の確認で rdx の値は決まらなかった。`8c7710` / vtable 先の逆アセンブルは未実施 (VA の特定と rdx の出力規約の確定に時間が要るため本版では行わない)。
    - **要求 (b) への対応**: 本版は仮定 `zext(arg2)` を IR に残したまま。PM 判断: 仮定を外す (0 件経路の rdx を guard で store しない) と、0 件経路の `8c6066` が未定義値を読むため、外す案は採らない。残す場合の影響は「0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 の経路の戻り値が、仮定と異なる rdx の影響を受けうる」。この経路の実測 (戻り値の比較) は未実施 (§6)。
  - **残る未証明の経路**: 0 件 ∧ arg3 (r8) == 0 ∧ arg2 下位 byte ≠ 0 のとき `8c608d: call 410360` の第 2 引数 (rdx) が、この仮定値と一致するか。同経路は `8c608d` まで到達する (arg2 下位 byte = 0 では到達しない)。上記の確認で、この rdx は callee 依存と分かった。未確定のまま残す (§6)。
  - 上記の未証明により、**「unit 56 ok」は件数 0 経路が正しいことの証拠ではない**。unit 56 は survey のラベル (ok/trap) が変わったことを示すだけで、出力の同一性は比較していない。
- pass は冪等で、`--mode off` が逆変換する (`on → off` で元の IR にバイト一致, `on → on` で無変更を確認)。
- `m11_build.sh` は alloca 修正の後に pass を適用する (既定 on)。`M11_GUARD699=off` で脱落状態に戻す。`M11_GUARD699_COND` で条件を差し替える (ネガコン用)。

## 2. 機構の切り分け (RetDec 段)

脱落は自前の IR 後処理より**前**で起きている。根拠: 生の RetDec 出力 `work/boot2.lift.ll` (関数 `function_8c5eb0`) の `dec_label_pc_8c5ef5` ブロックには、`cmp` のフラグ計算も `jg` も無く、無条件 `br` だけが残る。自前の後処理 (`m11_merge`/`numfix`/`asmfix`/`passes`/`genstubs`/`dotfix`/`ldfix`/`qstore`/`alloca`) はすべてこの後に走る。
RetDec の CFG 復元 (jcc の終端化) と命令翻訳 (フラグ) のどちらで落ちたかは**未切り分け** (§6)。

## 3. 実測

### 3-1. negctl (`bash tools/m11/trap_triage/negctl_699.sh`)

比較元は **同一の m11_ov.c** (main 取り込み後, #700 の 8c7710 転記を含む) に固定し、guard のみ変える 3 構成。構成: off = guard 無効 (基準) / fix = guard 有効 (既定) / ng = 偽ガード (`icmp eq i32 %9, 123456789`)。

検証 HEAD `bcc605d2` (1 回, r7):

| 構成 | ok | trap (oom 除く) | oom | miss | noproc | 計 | unit 56 |
|---|---|---|---|---|---|---|---|
| off | 870 | 24 | 1 | 46 | 1 | 942 | trap |
| fix | **871** | 23 | 1 | 46 | 1 | 942 | **ok** |
| ng | 870 | 24 | 1 | 46 | 1 | 942 | trap |

- 判定 G1〜G3 は PASS、rc=0 (**115 秒** real, 3 構成の build + survey 合計)。差分は `off→fix` が unit 56 の trap→ok の 1 件のみ、`off→ng` は 0 件。
- 検証 HEAD `f3d5341` (main 取り込み前, 1 回, r6'): off 866 / fix 867 / ng 866 (unit 56: trap / ok / trap)。rc=0 (**102 秒**)。
- 実行環境: `$RUNNER_TEMP/run*` (`tools/` のコピー + `work-m11` 展開)、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、capstone 5.0.7 / pefile を venv から使用。`tools/m11/work/` は使っていない。
- 注: スナップショット (`work-m11`) に `ir_conditions.json` が無かったため、最初の `m11_e2e.sh` (`f3d5341`) が `gen_ir2` で IR を作り直した。この IR 作り直しを経て negctl が通った。
- 同じ head での数値差 (r6 の 865 系 / 866 系, r7 の 870 系) は main 取り込みの影響 (`tools/m11` 34 ファイルの変化) を含み、guard 単独の揺らぎとは切り分けていない (§6)。
- **survey は戻り値を出力しない** (`M11_SURVEY` の項目は ok/trap/miss/oom の件数のみ)。0 件 ∧ arg2 下位 byte == 0 経路の戻り値比較は、この negctl では測れない (§3-5)。
- qstore 有効 (`capstone` 5.0.7 / `pefile` 2024.8.26 導入後)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、node v22.23.3。
- 参考 (r5, `22a0f22`): off 863 / fix 864 / ng 863。同じ guard 条件の 2 回で ok が動く (r5 と r6 の揺らぎ)。原因は未切り分け (§6)。
- **旧版からの変更点**: 前版の G1 (cur vs base) は、`origin/main` の取り込みで `m11_ov.c` が変わったため比較が成立しなくなった。比較元を同一 m11_ov.c に固定し直した。前版の base/cur/fix/ng の数値 (864/865 等) はこの版と比較できないため、採用しない。
- 失敗した試行 (記録): r1 = `FL_WIN64_DIR` 未設定で PE を読めず qstore が skip された (unit 56 は trap のまま)。r4 = qstore は有効だが `capstone`/`pefile` 未導入の環境で、fix は unit 56 ok だが G1 / G3 は旧 base との比較で FAIL。r4 のスクリプトは比較元を変えたため廃止。
- 限界: 1 回の実測のみ。再現性 (n≥3) は未測定。survey の揺らぎ (#662 reviewer 観測の base 856/38, 859/36) は本環境では再現していない。node は v22.23.3 (e2e 想定の v26 ではない)。
- 「退行 0」は **survey の ok/trap ラベルの比較のみ** に基づく。出力 (unit の戻り値・メモリ) の同一性は未比較。fix で unit 56 以外の unit の出力が変わっている可能性は本件では排除していない。

### 3-2. 全 IR 関数の分岐突合走査 (`guard699/scan_guard.py`)

規則: 機械語 (`.pdata` 区間の線型 disasm) の各 jcc (VA `A`, 絶対 target `T`) について、A を含む IR ブロック `B` の後続集合 `succ(B)` と突合する。
- `dropped`: `T ∉ succ(B)` (jcc が IR から消えている候補)。
- `strict` (ループ先頭ガード型): dropped かつ、A の直前 2 命令に `cmp/test`、`T > A`、`B` の終端が無条件 `br` で後続 `L` が `B` より後方、`L` に後方ブロックからの back-edge がある。

| 入力 IR | 関数 | jcc | dropped | dropped (target がラベルでない) | strict | 8c5eb0 |
|---|---|---|---|---|---|---|
| ガード無し (`--mode off`) | 6969 | 25618 | 1423 | 7058 | **406** | **strict (8c5f18 jg → 8c6066, L=8c5f23)** |
| ガード有り (`--mode on`) | 6969 | 25618 | 1422 | 7058 | **405** | 消える |

- 関数数は機械語 (`.pdata`) が取れた IR 関数。`fn_nomach` 452 と `jcc_noblock` 6 は対象外。
- ガード有り/無しの strict 差分は `function_8c5eb0` の `8c5f18` の 1 件だけ (`strict` 集合の差, 集合演算で確認)。
- 同じ入力で 2 回実行し、JSON が一致 (決定的)。実行時間は約 4 秒。
- **走査の範囲**: 全 IR 関数 (= 全 unit の閉包を含む上位集合)。unit への帰属は行っていない。
- **限界 (重要)**: strict の 405 件は**未検証の候補**。規則は heuristic で、偽陽性の率は未測定。405 件のうち miscompile である件数は本件では言えない。`dropped_target_not_label` の 7058 は内訳 (関数外への tail jump か否か) 未調査。

### 3-3. e2e (`bash tools/m11/m11_e2e.sh`)

- 作業コピーは `$RUNNER_TEMP/run*` (`tools/` のコピー + `work-m11` 展開、`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`、PATH に capstone/pefile の venv)。repo の `tools/m11/work/` は使用していない。
- **検証 HEAD `bcc605d2` (1 回, r2'): rc 0, 53 秒 real**。`reached_stage 4`、`ir_conditions`: `ldfix=applied`・`qstore=applied`・`ir_sha256=8d966a8d…`。停止理由は `Halt0 経由の早期終了 (units_run=110/942)`。survey `ok 871 / trap 23 (うち oom 1) / clobber 0 / miss 46`。
- 同じ head を `M11_GUARD699=off` で 1 回 (r2'-off): rc 0, 51 秒。停止理由は `function_8c6530 <- function_8c5eb0 <- function_56fde0` の OOB。survey `ok 870 / trap 25 (うち oom 1)`。
- **検証 HEAD `f3d5341` (main 取り込み前, 1 回, r1'): rc 0, 103 秒**。停止理由は `function_47ad70` の OOB。survey `ok 867 / trap 28 (うち oom 2) / miss 46`、`wasm_bytes 6042615`。
- 未切り分け: `f3d5341` → `bcc605d2` で停止理由が「OOB」から「Halt0 早期終了」に変わった。guard の効果か main 取り込みの効果か、本版では切り分けていない。`bcc605d2` で guard を外すと `function_8c6530 <- function_8c5eb0` の OOB が出る (§3-3 の off 実行)。
- 初回の試行 (記録): `capstone/pefile 無し` で `reached_stage 0` の rc 1 (0.05 秒)。PATH に venv を加えて解消。
- 同一 head での survey の揺らぎは §6 の揺らぎ項目と同じ扱い。他 HEAD の e2e 実測は本版の数値と混ぜない。
- `lift boot5 (RetDec)` の停止は、runner に既存の RetDec (`[RETDEC]`) を使うため今回は発生しなかった。
- **survey の揺らぎ**: 同一 head で (`negctl` 同一 build の別 run) ok が 866/867 と動く。§6 の揺らぎ項目を参照。
- 「退行 0」は survey ラベル比較のみ。出力の同一性は未比較 (§3-1 の限界)。
- 所要の数え方: `date +%s.%N` の差 (`m11_e2e.sh` の開始から終了まで)。4 vCPU。
- 検証範囲: e2e の survey は `unit 56 = ok` を含めて 942 unit 全件。e2e 末尾の `m11_icall_audit.py` の出力 (`脱落率 100.0%`) は本件と無関係の既存監査で、本件では判定していない。

### 3-5. 0 件 ∧ arg2 下位 byte == 0 経路の戻り値 (未測定)

- 機械語 (§1 の逆アセンブル): `8c608b je 8c60df` → `8c60df: mov rax,[rbp+0x80]` → `ret`。IR は `dec_label_pc_8c60df` が `ret rax.2` で、rax.2 は `8c6084` で rax.1 を受ける。
- 0 件経路 (ガード辺) では rax.1 = rax.0 = 0 (ガード辺の store)。よって IR は 0 を返し、機械語は [rbp+0x80] を返す。**IR と機械語で戻り値が食い違う経路がある。**
- この食い違いは guard の無い IR にも存在する (IR の `ret rax.2` の構造は guard 前から同じ。guard は 0 件経路を `8c6066` に直接飛ばすため、この経路に入る件数が変わるだけ)。ただし **実測はしていない**。
- 測定できない理由: survey / negctl は unit の戻り値を出力しない。戻り値の比較には、0 件 ∧ arg2 下位 byte == 0 の呼出しを持つ unit を特定し、呼出し元の戻り値を比較する追加計測が要る。本版では実施していない。
- 本版の結論: 「0 件経路の戻り値は機械語と一致しない可能性がある (IR 構造から)。測定は未実施。」 approve 判断に影響する。起票先は #718 (`[M11-N35]`、コメント 6146067294 で追記済み)。

### 3-6. (b') 版の実測 (head = 本 commit, n=3)

- 変更: rdx 経路を trap に落とした (`_t`)。negctl・e2e を n=3 で実行。
- **negctl_699.sh (n=3)**: 3 回とも rc=1、build+survey 95・96・95 秒。counts は 3 構成とも `ok 869 / trap 24 / oom 1 / miss 47 / noproc 1`、unit 56 は全構成で `trap`。G1 PASS / **G2 FAIL** / G3 PASS。`diff off->fix: n=0`, `diff off->ng: n=0`。
- **G2 FAIL の扱い**: 期待値 (unit 56 のみ trap→ok) は、ok 化する版 (旧 rdx 仮定) を前提にしている。(b') は unit 56 を fail-fast で trap のまま残すため、この期待値は (b') では成立しない。判定基準の改訂は PM 判断 (スクリプトは変更していない)。
- **unit 56 の trap 種別 (実測の食い違い)**: 全 trap unit の stack 取得 (`M11_SURVEY_STACK=<trap 全件>`) では unit 56 = `RuntimeError: unreachable` (`8c5eb0` の `_t`)。unit 56 単独の stack 取得 (`M11_SURVEY_STACK=56`) では `RuntimeError: memory access out of bounds`。同じ build で観測が異なる。原因は未切り分け。
- **fail-fast 到達 unit 数 (限定)**: 全 trap 24 件の stack 取得では `unreachable` は unit 56 の 1 件のみ。ただし unit 56 の単独取得では OOB と出るため、到達 unit 数を 1 と断定しない。他 unit が `_t` に到達する可能性は未除外。
- **e2e (`m11_e2e.sh`, n=3)**: 3 回とも rc=0。r1 85〜88 秒 (実測 88.2・85.1・85.0 秒)。停止理由は 3 回とも `trap "unreachable" @ function_8c5eb0 <- function_56fde0 <- ...` (fail-fast)。`survey_ok 869 / survey_trap 25 (うち oom 1)`。
- 実行環境の補足: runner に `[RETDEC]` が無いため、`toolchain-retdec` を `$RUNNER_TEMP` に展開して代替 (`m11_lift.sh` は `[RETDEC]` の固定パス参照のまま。#680 の範囲)。`tools/m2/ir_normalize.py`・`tools/m6/ottlib.py` を作業コピーに追加した (欠落時は `m11_e2e.sh` が fail-closed)。
- **最終 HEAD `93382f48` での再実測 (n=3)**: negctl_699.sh は rc=1 (G2 FAIL, 上記と同じ)、95 秒。G1・G3 PASS、`diff off->fix: n=0`、`diff off->ng: n=0`。e2e (`m11_e2e.sh`) は 3 回とも rc=0、所要 88.2・86.1・86.3 秒。停止理由は 3 回とも `trap "unreachable" @ function_8c5eb0`、`survey_ok 869 / survey_trap 25 (うち oom 1)`。
- 限界: survey の ok/trap ラベル比較のみ。出力の同一性は未比較。

## 3-4. 判定の表 (受入条件との対応)

| 受入条件 (#699) | 結果 | 根拠 |
|---|---|---|
| 8c5eb0 の件数 0 ガードを復元 (IR pass) | 達成 | §1, `m11_guard699.py`, `m11_build.sh` 組込み |
| unit 56 が ok。off 比の退行 0 (survey ラベルのみ。56 のみ trap→ok) | **未達** (b' 版は fail-fast で trap のまま。off 比の差 0)。旧版の ok 化は rdx 仮定に依存していたため撤回 | §3-6 (n=3)。G2 の期待値の改訂は PM |
| ネガコン (ガード条件を壊すと 56 が trap に戻る) を数値で残す | 達成 | §3-1 G3 (ng: 865/27, unit 56 trap, off 比 0) |
| 同型の脱落を全 unit 走査し件数を測る | 達成 (件数のみ。真偽は未検証) | §3-2 (strict 406 / 405) |
| RetDec がなぜ分岐を落としたかの機構を記録 | **未達** (生 lift 段で既に欠落まで。CFG 復元か翻訳かは未切り分け) | §2, §6 → #718 |

## 4. 再現

```sh
cd tools/m11
bash trap_triage/negctl_699.sh                         # §3-1 (G1〜G5, exit 1 で不合格)
python3 guard699/m11_guard699.py work/boot_final.ll work/v699/ir_off.ll --mode off
python3 guard699/m11_guard699.py work/boot_final.ll work/v699/ir_on.ll  --mode on
python3 guard699/scan_guard.py work/v699/ir_off.ll --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin"  # §3-2
bash m11_e2e.sh                                        # §3-3
```

前提: `tools/m11/work/` に work-m11 が展開済み。`FL_WIN64_DIR` に fl-win64 が展開済み (`extracted/block00031_PE.bin`)。`capstone`・`pefile` を import できること (無いと qstore が skip される)。
`m11_e2e.sh` / `m11_gen_ir2.sh` は `FL_WIN64_DIR` (既定は固定パス。#680 の範囲) 配下の `extracted/block00031_PE.bin` を読む。`FL_WIN64_DIR` を設定すれば固定パスは不要。前提の `capstone`・`pefile` は導入済みであること (無いと qstore / ldfix が skip される)。

## 5. DEFECTS.md 行案 (PM 判断。直接編集はしない)

| ID | 分類 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| (番号は PM 採番。D1b と同型の疑い) | fe または opt (未切り分け) | 件数 0 のループで本体が 1 回以上実行される。空リストの `Items[0]` を読み、不正レコードを OOB に渡す | ループ先頭の `cmp; jg exit` が RetDec の生 IR から脱落 (機構は未特定。D1b の「jcc が IR から消える」と症状・検出信号は一致、根本原因は同一か未確認) | `8c5eb0` (unit 56, #662/#699): `8c5f15-8c5f18` ↔ `dec_label_pc_8c5ef5` の無条件 `br`。生 lift `boot2.lift.ll` で既に欠落 | 機械語 jcc に対応する IR 後続が無い (§3-2 の dropped)。strict 規則 (ループ head 型) | `m11_guard699.py` (IR pass, 冪等・双方向) で `icmp sle count,0` 分岐を復元し、ガード辺の rax/rdx を明示 store (§1) |

## 6. 未解決

**PM 判断 (b') 採用時点の注記 (#717)**:
- (ii) 8c60df の戻り値: `8c60df` では IR が `ret rax.2` でガード辺の 0 を返し、機械語は `mov rax,[rbp+0x80]` で戻り値を決める。**戻り値が一致しない可能性がある。survey は戻り値を比較しないため未測定。** 追跡は #718。ガード無しの経路との比較は #718 の仕事。

**先頭の結論 (head `11091dc` 時点)**: 以下 2 件は approve 判断に影響する未解決であり、本 PR では解消していない。PM 判断 (仮定を残すか、guard の対象を絞るか) を要する。
(i) (b') で解消: 0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 は trap に落とした。旧記述: ガード辺の rdx.1 (`zext(arg2)`) は仮定のまま。0 件 ∧ arg3==0 ∧ arg2 下位 byte≠0 の経路 (`8c608d` → `410360` → `[rbx-0x50]`) の第 2 引数として参照されうる。値は callee 依存で、`8c7710` / vtable 先の rdx 出力は未確定 (§1)。
(ii) `8c60df` の戻り値不一致 (0 件 ∧ arg2 下位 byte==0 の経路で、IR は 0 を、機械語は [rbp+0x80] を返す) は **未測定** (§3-5)。survey は戻り値を出力しないため現行の計測では比較できない。IR 構造 (`ret rax.2`) から guard 前の IR にも存在すると読めるが、実測はしていない。
「unit 56 ok」は件数 0 経路が正しいことの証拠ではない (§3-1 の限界)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec が先頭 `cmp/jg` を落とす機構 (CFG 復元か命令翻訳か) の切り分け | 同型の再発防止 (修復は IR pass で済んでいるが原因は未特定) | #718 (`[M11-N35]`) |
| strict 候補 405 件の真偽 (偽陽性率を含む) | 他 unit の miscompile の有無。survey の trap 29 本との関係も未確認 | #718 (`[M11-N35]`) |
| `dropped_target_not_label` 7058 の内訳 | 走査の見落とし/偽陽性の見積もり | #718 (`[M11-N35]`) |
| `m11_e2e.sh` の PE 固定パス (`[WIN64]`) と node v26 前提 | runner では `FL_WIN64_DIR` と node v22 で動かしている | #680 |
| 同一 guard 条件での survey の揺らぎ (f3d5341: off 866 / fix 867、bcc605d2: off 870 / fix 871) | 1 unit 単位で ok 数が動く。main 取り込みの影響と guard 単独の揺らぎは未切り分け | #718 (`[M11-N35]`) へ追記 |
| e2e の完走の前提 (本版では完走: rc 0, 101 秒。前段の失敗は PATH 上の capstone/pefile 不在) | runner の e2e 実行には capstone/pefile が PATH に必要。runner 既存の `[RETDEC]` で代替 | なし (手順として §4 に記載) |
| `docs/DEFECTS.md` の行案 (D1b との関係の判定を含む) | PM 判断 | PM (§5) |
| ガード辺の rdx.1 の値 (0 件 ∧ arg3==0 ∧ arg2 下位≠0 の `8c608d` 経路) | 仮定 (zext(arg2)) を置いた。410320 の vtable target と 8c7c80 の rdx 出力を確認するまで正しさは未証明 | #718 (`[M11-N35]`) へ追記 |
| `8c60df` の戻り値不一致 (ガード辺の rax=0 がこの経路で戻り値に届く。guard 前の IR にも構造上存在するが未測定) | 機械語 `8c60df: mov rax,[rbp+0x80]` は [rbp+0x80] を返す。IR `dec_label_pc_8c60df` は `ret rax.2`。arg2 下位 byte == 0 (`8c608b`) の経路で、IR は rax.1 を返し、機械語は arg1 を返す (§3-5)。戻り値は呼出側で使われる (例: `56fde0`)。今回の 2 呼出しは arg2 下位 byte = 1 のため `8c60df` 経路に入らない | #718 (`[M11-N35]`) へ追記済み (コメント 6146067294) |
| `count = INT_MIN` の不一致 (§1) | 件数の不正値。到達可否は未確認 | #718 (`[M11-N35]`) |

## 7. 次タスク提案

- strict 候補 405 件を、1 件ずつ survey (guard 有効化の ablation) で検証する。対象は 8c5eb0 と同型のガード脱落 IR pass の適用可否。
- RetDec の CFG 復元で jcc の条件辺が落ちる条件を、`8c5eb0` と同型の最小再現で切り分ける。

## 8. 範囲 / 範囲外

- 範囲: `tools/m11/m11_build.sh` (pass の組込み), `tools/m11/guard699/` (pass と走査), `tools/m11/trap_triage/negctl_699.sh`, 本 REPORT。
- 範囲外: `m11_ov.c` (変更なし。`8c7710` 転記は #700)。`docs/DEFECTS.md` (PM 判断)。
- 20 MiB 超の blob: 追加なし。`work/` は gitignore。
