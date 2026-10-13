# #699: `8c5eb0` の件数 0 ループ先頭ガードを IR に復元 (unit 56: OOB → ok) と、同型の全 IR 関数走査

**判定: 受入 1・3・4 と 2 (unit 56 ok・退行 0) を達成。Closes ではなく Refs (未達 1 件 = RetDec の脱落機構の記録は未了、§6)。**
件数 0 の空リストを `8c6530` へ渡す経路は塞がり、unit 56 は trap から ok になった。

既知類型との関係 (DEFECTS.md): **D1b と同型の症状・検出信号** (機械語の jcc に対応する IR `br` が無く、飛び先が無条件実行になる)。ただし **根本原因は未切り分け** (D1b は stage-0 のフラグが定数に畳まれる機構。本件は生 lift の段階で既に jcc が無く、同じ機構かは未確認。§2, §6)。新規番号は付けず、行案 (§5) は PM 判断。番号は (DEFECTS.md) 体系。

検証起点: `8d883c3` (main)。作業 branch は `d9bcc52` (親 PR #700 の head) から切った。修正 commit `9dd4d55`。
e2e 実測は `9dd4d55` の清潔な作業ツリーで実行した (§3-3)。

## 1. 修復の内容

機械語 (`8c5eb0`, capstone 実測):

```
8c5f0c: mov ebx, [rcx+0x14]     ; ebx = 件数
8c5f0f: sub ebx, 1
8c5f12: mov [rbp+0x4c], eax     ; i = 0
8c5f15: cmp [rbp+0x4c], ebx     ; i > 件数-1 (件数 <= 0) なら本体を飛ばす
8c5f18: jg 0x8c6066
```

IR (`dec_label_pc_8c5ef5`) は `%9 = load i32 [rcx+0x14]` (件数) の後、無条件 `br label %dec_label_pc_8c5f23` に進む。
修復はこの末尾の `br` を次の形に置換する (`tools/m11/guard699/m11_guard699.py`):

```llvm
  store i64 0, ptr %rax.0.reg2mem          ; rax.0 := 0 (機械語で確定, 下記)
  %g699rdx = and i64 %arg2, 255            ; rdx.1 := zext(arg2 下位 byte) (未検証の仮定, 下記)
  store i64 %g699rdx, ptr %rdx.1.reg2mem
  %g699 = icmp sle i32 %9, 0
  br i1 %g699, label %dec_label_pc_8c6066, label %dec_label_pc_8c5f23
```

- 分岐条件: `count <= 0` は機械語の `jg` と件数 ∈ [INT_MIN+1, 0] で一致する。**count = INT_MIN のみ不一致**: 機械語は `sub ebx,1` が wrap して `0x7FFFFFFF` と比較し jg が立たず本体を実行、IR は飛ばす。件数は非負の list 長なので本件では到達しないと見なすが、確認はしていない (厳密化 `sub` + `icmp slt` は未実施)。
- **ガード辺の値 (レビュー指摘 2)**: ガードで飛ばすと、元 IR で `%rax.0.reg2mem`・`%rdx.1.reg2mem` を store するのは `dec_label_pc_8c6034`・`dec_label_pc_8c603f` だけで、飛び先 `dec_label_pc_8c6066` が両方を load する。このままでは 0 件経路で未定義値になる。次のように明示 store する。
  - **rax.0 := 0 (機械語で確定)**: `8c5f06: xor eax,eax` の後、`8c5f18: jg` まで rax は書かれない (`8c5f08`〜`8c5f15` は rcx・ebx・[rbp+0x4c]・flags のみ)。0 件経路は rax=0 のまま `8c6066` に入る。
  - **rdx.1 := zext(arg2 下位 byte) (未検証の仮定)**: 機械語では `8c5efd: call 8c67a0` の後の rdx は callee 依存。`8c67a0` は中で `8c7c80` を呼び (`mov rdx, rbx` 後), `8c5eda` の `410320` は `call qword ptr [rax-0x30]` (vtable 間接 call、target は IR から決まらない) を呼ぶ。rdx の出力は IR から確定できない。`8c5ee1: movzx rdx, byte [rbp+0x88]` を経由する値として、既存 IR の `8c6071` (`8ca670` 後の rdx を引数 rdx と同じとする) と同じ pass-through 規約に合わせた。**410320 と 8c67a0 が rdx を変えないことは確認していない**。
  - **残る未証明の経路**: 0 件 ∧ arg3 (r8) == 0 ∧ arg2 下位 byte ≠ 0 のとき `8c608d: call 410360` の第 2 引数 (rdx) が、この仮定値と一致するか。同経路は `8c608d` まで到達する (arg2 下位 byte = 0 では到達しない)。機械語の値を確定するには vtable target と `8c7c80` の rdx 出力の確認が要る。未確定のまま残す (§6)。
- pass は冪等で、`--mode off` が逆変換する (`on → off` で元の IR に一致, `on → on` で無変更を確認)。
- `m11_build.sh` は alloca 修正の後に pass を適用する (既定 on)。`M11_GUARD699=off` で脱落状態に戻す。`M11_GUARD699_COND` で条件を差し替える (ネガコン用)。

## 2. 機構の切り分け (RetDec 段)

脱落は自前の IR 後処理より**前**で起きている。根拠: 生の RetDec 出力 `work/boot2.lift.ll` (関数 `function_8c5eb0`) の `dec_label_pc_8c5ef5` ブロックには、`cmp` のフラグ計算も `jg` も無く、無条件 `br` だけが残る。自前の後処理 (`m11_merge`/`numfix`/`asmfix`/`passes`/`genstubs`/`dotfix`/`ldfix`/`qstore`/`alloca`) はすべてこの後に走る。
RetDec の CFG 復元 (jcc の終端化) と命令翻訳 (フラグ) のどちらで落ちたかは**未切り分け** (§6)。

## 3. 実測

### 3-1. negctl (`bash tools/m11/trap_triage/negctl_699.sh`, 3 回)

4 構成の build + survey を各 1 回、計 3 回実行。構成: base = `8d883c3` の `m11_ov.c` + guard 無効 / cur = 現 `m11_ov.c` (8c7710 転記) + guard 無効 / fix = cur + guard 有効 (既定) / ng = cur + 偽ガード (`icmp eq i32 %9, 123456789`)。

| 構成 | ok | trap (oom 以外) | oom | miss | noproc | 計 | unit 56 | 3 回の一致 |
|---|---|---|---|---|---|---|---|---|
| base | 864 | 30 | 1 | 46 | 1 | 942 | trap | 3/3 同一 |
| cur | 864 | 30 | 1 | 46 | 1 | 942 | trap | 3/3 同一 |
| fix | **865** | 29 | 1 | 46 | 1 | 942 | **ok** | 3/3 同一 |
| ng | 864 | 30 | 1 | 46 | 1 | 942 | trap | 3/3 同一 |

- 集計の定義: `units_<cfg>.json` の値を数えた (942 unit, trap と oom は排他)。survey 行の `trap` は oom を含む合計 (base 31 / fix 30)。e2e のサマリも同じ定義 (§3-3)。
- 判定 G1〜G5 は 3 回とも PASS (exit 0)。
  - G1 cur vs base: unit 差 0 (回帰 0)。
  - G2 cur: unit 56 は trap。
  - G3 fix vs base: 差は unit 56 の trap→ok のみ。
  - G4 fix vs cur: 差は unit 56 の trap→ok のみ。
  - G5 ng vs cur: unit 差 0 かつ unit 56 は trap (ネガコン)。
- 所要: 4 構成の build + survey 合計 103 秒 (r1)。r2・r3 は各 `negctl699_r*.log` を参照。load は 4 vCPU で約 0.2〜1.0。
- **限界**: 3 回とも一致した。#662 のレビュー (reviewer 実測) で観測された base の揺らぎ (856/38, 859/36) は、この環境では再現しなかった。揺らぎの原因は未特定で、#680 の範囲。「回帰 0」は**この環境で安定して再現した範囲**での主張。node は v22.23.3 (e2e 想定の v26 ではない)。

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

### 3-3. e2e (`bash tools/m11/m11_e2e.sh`, コミット済み HEAD `9dd4d55`, 3 回)

| 回 | 所要 (秒) | load (開始→終了) | rc | 備考 |
|---|---|---|---|---|
| 1 | 55.5 | 0.92→0.97 | 0 | `gen_ir2` で IR を再生成 (stamp 無し) を含む |
| 2 | 32.0 | 0.97→0.98 | 0 | 増分 |
| 3 | 32.2 | 0.98→0.99 | 0 | 増分 |

- 3 回とも同一のサマリ: `reached_stage 4/6` (FastMM4 が VirtualAlloc でプールを確保)、`stop_reason` = DllMain attach 完走、`units_run_full 22 / 942`、survey `ok 865 / trap 30 (うち oom 1) / clobber 0 / miss 46`、`wasm_bytes 6027656`。
- 変更前 (`8d883c3`) は #662 の REPORT で 69.2 秒・survey 864/31 (oom を含む)。本 e2e は unit 56 が ok になった分だけ survey が変わる (865/30)。到達 stage は変わらない (4/6)。unit 56 の後段の停止点は本件の範囲外。
- 所要の数え方: `date +%s.%N` の差 (`m11_e2e.sh` の開始から終了まで)。4 vCPU。
- 検証範囲: e2e の survey は `unit 56 = ok` を含めて 942 unit 全件。e2e 末尾の `m11_icall_audit.py` の出力 (`脱落率 100.0%`) は本件と無関係の既存監査で、本件では判定していない。

## 3-4. 判定の表 (受入条件との対応)

| 受入条件 (#699) | 結果 | 根拠 |
|---|---|---|
| 8c5eb0 の件数 0 ガードを復元 (IR pass) | 達成 | §1, `m11_guard699.py`, `m11_build.sh` 組込み |
| unit 56 が ok。`8d883c3` 基準の退行 0 (56 のみ trap→ok) | 達成 | §3-1 G1・G3 (3/3), §3-3 (865/30) |
| ネガコン (ガード条件を壊すと 56 が trap に戻る) を数値で残す | 達成 | §3-1 G5 (ng: 864/30, unit 56 trap, cur 比 0) |
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
`m11_e2e.sh` は `[WIN64]` (`docs/REFERENCES.md`) の `extracted/block00031_PE.bin` を固定パスで参照する (#680 の範囲)。runner では展開先 (`fl-win64` 展開物の `extracted/`) への symlink を作って合わせた。

## 5. DEFECTS.md 行案 (PM 判断。直接編集はしない)

| ID | 分類 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| (番号は PM 採番。D1b と同型の疑い) | fe または opt (未切り分け) | 件数 0 のループで本体が 1 回以上実行される。空リストの `Items[0]` を読み、不正レコードを OOB に渡す | ループ先頭の `cmp; jg exit` が RetDec の生 IR から脱落 (機構は未特定。D1b の「jcc が IR から消える」と症状・検出信号は一致、根本原因は同一か未確認) | `8c5eb0` (unit 56, #662/#699): `8c5f15-8c5f18` ↔ `dec_label_pc_8c5ef5` の無条件 `br`。生 lift `boot2.lift.ll` で既に欠落 | 機械語 jcc に対応する IR 後続が無い (§3-2 の dropped)。strict 規則 (ループ head 型) | `m11_guard699.py` (IR pass, 冪等・双方向) で `icmp sle count,0` 分岐を復元し、ガード辺の rax/rdx を明示 store (§1) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec が先頭 `cmp/jg` を落とす機構 (CFG 復元か命令翻訳か) の切り分け | 同型の再発防止 (修復は IR pass で済んでいるが原因は未特定) | #718 (`[M11-N35]`) |
| strict 候補 405 件の真偽 (偽陽性率を含む) | 他 unit の miscompile の有無。survey の trap 29 本との関係も未確認 | #718 (`[M11-N35]`) |
| `dropped_target_not_label` 7058 の内訳 | 走査の見落とし/偽陽性の見積もり | #718 (`[M11-N35]`) |
| `m11_e2e.sh` の PE 固定パス (`[WIN64]`) と node v26 前提 | runner では symlink と node v22 で動かしている | #680 |
| survey の揺らぎ (#662 reviewer 観測: 856/38, 859/36) | 再実行で同じ値 (856/38) が出た (§3-1)。原因未特定 | #680 |
| `docs/DEFECTS.md` の行案 (D1b との関係の判定を含む) | PM 判断 | PM (§5) |
| ガード辺の rdx.1 の値 (0 件 ∧ arg3==0 ∧ arg2 下位≠0 の `8c608d` 経路) | 仮定 (zext(arg2)) を置いた。410320 の vtable target と 8c7c80 の rdx 出力を確認するまで正しさは未証明 | #718 (`[M11-N35]`) へ追記 |
| `8c60df` の戻り値不一致 (別件・ガード無しでも再現) | 機械語は `8c60df: mov rax,[rbp+0x80]` で [rbp+0x80] (arg1 / 8c608d の 410360 結果) を返す。IR は `ret rax.2` (`8c608d` の結果も `rax.2` へ store) で、arg2 下位 byte == 0 経路は arg1 でなく rax.1 を返す。戻り値は呼出側で使われる (例: `56fde0`)。今回の 2 呼出しは arg2 下位 byte = 1 のため `8c60df` 経路に入らない。他の呼出しで同経路に入るかは未確認 | 新規 issue (PM 採番) または #718 |
| `count = INT_MIN` の不一致 (§1) | 件数の不正値。到達可否は未確認 | #718 (`[M11-N35]`) |

## 7. 次タスク提案

- strict 候補 405 件を、1 件ずつ survey (guard 有効化の ablation) で検証する。対象は 8c5eb0 と同型のガード脱落 IR pass の適用可否。
- RetDec の CFG 復元で jcc の条件辺が落ちる条件を、`8c5eb0` と同型の最小再現で切り分ける。

## 8. 範囲 / 範囲外

- 範囲: `tools/m11/m11_build.sh` (pass の組込み), `tools/m11/guard699/` (pass と走査), `tools/m11/trap_triage/negctl_699.sh`, 本 REPORT。
- 範囲外: `m11_ov.c` (変更なし。`8c7710` 転記は #700)。`docs/DEFECTS.md` (PM 判断)。
- 20 MiB 超の blob: 追加なし。`work/` は gitignore。
