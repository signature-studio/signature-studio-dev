# REPORT_564 — function_52a7f0 (AllocateHWnd) の `cmp [TempClass.lpfnWndProc]` 脱落 (#564 / M11-N19)

**判定: 部分達成 (Refs #564, Closes しない)**。欠陥の型を特定し、ldfix に **F4** を追加して 10 関数を機械語突合で修復した。
修復後、指向呼出 (JS から `function_52a7f0` を直接呼ぶ) で `RegisterClassW` に到達する (ret hwnd 0 → 0x110000f)。自然起動での到達ではない
(自然起動は unit #23 で Halt0 のため #134/#490 の先)。全数走査は実施したが検出器に偽陰性があり (§3)、F4 が直した 10 関数のうち
動的に効果を確認したのは 52a7f0 だけ (§5)。依存: PR #563 (`tools/gui/flengine` の probe を使う。#563 未 merge のため同ブランチを取り込み済み)。

## 1. 型の特定 (機械語 × IR)

機械語 (`52a7f0`, PE の .pdata 区間 disasm):
```
52a7f0 push rbp ; ... sub rsp,0xb0 ; mov rbp,rsp          ; rbp = entry rsp - 200
52a81c lea r8,[rbp+0x68]  ; call GetClassInfoW(hInst, name, &WNDCLASS)   ; WNDCLASS = [rbp+0x68..) = stack_var_-96
52a835 cmp qword ptr [rbp+0x70], rcx   ; rcx = &DefWindowProc ; [rbp+0x70] = WNDCLASS.lpfnWndProc (= stack_var_-96 + 8)
52a839 je 0x52a85e                     ; 登録済みで WNDPROC 一致なら RegisterClass を飛ばす
```
IR (最終 `boot_final.ll`): `%1 = xor i64 0, 0` / `%8 = icmp eq i64 %1, 4344096` / `%or.cond = icmp eq i1 %8, %7` (`%7` = GetClassInfoW 成功)。

連鎖 (stage ごとの実測): `boot0.drc.ll` (RetDec 直後) で既に `%0 = alloca i64` + `%1 = load i64, ptr %0` (store の無い alloca の load = **undef**)。
`[rbp+0x70]` は callee が書く escape 済み `%stack_var_-96` の内部 (+8) だが、RetDec はそれを別 alloca の load にした。
undef の自由度で LLVM が分岐条件を `icmp eq i1 (v==K), registered` に畳み (`skip = registered && v==K` の意味が壊れる)、m5 `ir5_patch` B1 が undef を 0 に固定して最終 IR の `xor i64 0, 0` になる。
**RetDec frontend (層 fe) + 我々の B1 (ours) の複合**。DEFECTS.md の既存類型では D4 (deref 脱落) / D1b (定数に畳まれた分岐) の近縁だが、原因 (callee が書く frame 内部 read の undef 化) が違うため **D18 として新規行を追加**した。
F3 系の門 (G1〜G5) が対象外の理由: F3c は `mov rD,[argN-base]` (引数ポインタ経由) の load→store 形を見る。本件は rbp 相対 (frame) の read で base が引数でない (G1/G2 で落ちる)。

## 2. 修復 (ldfix F4, `ldfix.py` / `ldframe.py`)

`xor i64 0, 0` (B1 の残骸) を機械語と突合し、全条件が揃ったときだけ `ptrtoint %stack_var_-N + off` からの load に置換する:
IR に使用ゼロの無名 alloca (B1 の痕跡) が有る / ブロック内 xor-0-0 が 1 本 / 機械語の当該区間に自己 xor 無し (入口ブロックの hoist は関数全体で突合) /
frame read が恰好 1 本で、prologue を追った `rsp/rbp` モデル (`frame_model`) で escape 済み stack_var の gap 内に解決 / 同番地への機械語 store 無し /
使用が最初の使用と同一 IR ブロックで、その前に stack_var を渡す call がある。
さらに consumer: `cmp [frame],K; je T` の形で IR が `icmp eq i1 (v==K), X` に畳まれていれば `and i1 (v==K), X` に戻す (`f4_consumer_and`: 52a7f0 と 71dd80)。
load だけ直しても到達しない (§4 D2)。`m11_gen_ir2.sh` が `--pe` を `FL_WIN64_DIR` から引くよう変更 (従来は `` `[WIN64]` `` の固定パスで、runner では ldfix が黙ってスキップされた)。`LDFIX_ARGS` で F4 を外せる (ネガコン用)。

## 3. 全数走査 (`audit_undefload.py`, 別算法)

`boot0〜4.norm0.ll` (B1 前) の「store の無い無名 alloca の load」2,846 site を、消費者の `!insn.addr` が指す機械語命令で分類 (結果: `results/audit_undefload_564*.json`):
REGLIVE 2,509 (関数入口 live-in 等で脱落でない) / **FRAME_IN_ESCAPED 56 site・53 関数** (escape 済み stack_var 内部の read = 本件の型) / FRAME_NOT_ESCAPED 19 / MEMREAD (非 frame) 91 / RIPREAD 13 / NOADDR 158。
- F4 の修復 10 関数のうち監査の FRAME_IN_ESCAPED に出るのは 5 関数。残り 5 関数 (132e8e0 / 44d1c0 / 69c360 / 865020 / 977e40) は監査が出せない:
  消費者命令が read 命令と別 (`mov eax,[rbp+x]; and ...`) の site は消費者側の memop を見る本監査では REGLIVE になる (4 関数で確認: 44d1c0/69c360/865020/977e40)。132e8e0 は監査に出ない (未調査)。**監査は偽陰性あり**で SUSPECT 0 の根拠にならない。
- FRAME_IN_ESCAPED のうち F4 が未修復の 48 関数は、門 (ブロックに frame read が複数 / 自己 xor / store 衝突 / 使用が別ブロック) で落ちている。本当の脱落かは未判定。
- ldfix の F3 系の門 (#509 / PR #518 の G1〜G5 拡張を含む) は base が引数経由の load→store を見るため、この型は**検出しない** (F3c の `f3c_no_store` とは別形)。#518 は `ldfix.py` を編集しており、本ブランチと **ldfix.py で textual conflict** (`git merge-tree` で確認)。どちらが先でも他方の rebase が要る。

## 4. 検証 (実測。`bash tools/m11/ldfix/f4_e2e.sh`)

3 構成を `m11_gen_ir2.sh` → `m11_build.sh` → gui 結合 build → probe/起動/survey まで実測: pre (`--no-f4`) / noand (`--f4-no-consumer`) / post。

| 項目 | pre | noand (load だけ直す) | post |
|---|---|---|---|
| F4 修復関数 | 0 | 10 | 10 |
| `RegisterClassW` 到達 (probe 通算) | 2 | 2 | **3** |
| `function_52a7f0` の戻り | 0x0 (CreateWindowExW NULL) | 0x0 | **0x110000f** |
| 通常起動 units_run / init_count | 22 / 23 | 同 | 同 |
| survey ok / noproc / miss / trap | 816 / 1 / 46 / 79 | 同 | 同 |

`f4_judge.py` 6 gate (F1 修復対象 / F2 IR 形 / D1 到達 / D2 load だけでは未到達 / P1 起動・survey 不変 / A1 監査分類) 全 PASS。
ネガコン 4/4 が「期待した FAIL 行」付きで FAIL: N1 pre を post として判定 (D1) / N2 noand を post として判定 (D1) / N3 到達増分 ≥5 を要求 (D1) / N4 survey 1 unit を ok→trap に改竄 (P1)。

実測 (4 vCPU, `f4_e2e.sh`): コミット済み HEAD `7be6bab` で **175 s, rc 0, 6 gate 全 PASS / ネガコン 4/4** (開始時 load average 0.31 は初回。本回は終了時 0.99)。
同一コード・初回実装時の再実行は 172 s / rc 0 (1 回目は監査集約の `riperead` キー誤記で rc 1・173 s。修正済み)。**n=2 (rc 0 の回)**、分散は未評価。

**main 取り込み後の再実測** (merge commit `8637316`、Refs #577。`bash tools/m11/ldfix/f4_e2e.sh`、4 vCPU、開始 load 0.86 / 終了 1.00): **294 s, rc 0**、6 gate 全 PASS、ネガコン 4/4 が期待行付きで FAIL。RegisterClassW 2→3、ret 0x0→0x110000f は上の表と同じ。
survey は **ok 864 / noproc 1 / miss 46 / trap 31** (pre・post 同一、units_run 22 / init_count 23 / icall_miss 0) で、上の表 (816/1/46/79) と一致しない。差 48 件のうち 36 件は main 取り込みで入った `m11_survey.mjs` の unit 別 VirtualAlloc 上限 (#513、既定 256 MB) の効果: 上限 0 (旧挙動) で再実行すると 828/1/46/67。残る 12 件 (828 vs 816) は未分離 (main 側 `m11_build.sh` 等の寄与の可能性)。`results/f4_564_{pre,noand,post}.json` は 8637316 の実行出力で上書きした。上の表の値は PR 時点 (7be6bab) の実測として残す。

**main 取り込み後の再実測** (`bash tools/m11/ldfix/f4_e2e.sh`、`FL_WIN64_DIR` = `$RUNNER_TEMP/fl-win64`、4 vCPU、merge commit 後の head): **371 s, rc 0**、6 gate 全 PASS、ネガコン 4/4 が期待行付きで FAIL。
pre / noand / post は **units_run 52 / init_count 54 / icall_miss 5** (main 取り込みで unit 数が 22→52 に増えた)、survey ok / noproc / miss / trap = **869 / 1 / 47 / 25** (3 構成とも同一)。RegisterClassW 2 → 2 → 3、`function_52a7f0` ret 0x0 → 0x0 → 0x110000f。
`results/f4_564_{pre,noand,post}.json` は本回の出力で上書きした。`ok 864 / miss 46 / trap 31` (8637316 時点) とは別の値。main の F3c 等の取り込み後の変化と見られるが、原因は未分離。
**現 head `c262c44e` の実測** (`bash tools/m11/ldfix/f4_e2e.sh`、`EMSDK_ENV=[EMSDK]/emsdk_env.sh FL_WIN64_DIR=<fl-win64 展開先>`、4 vCPU、開始 load 0.79 / 終了 1.04): **382 秒, rc 0**。6 gate 全 PASS、ネガコン 4/4 が期待行付きで FAIL。pre / noand / post とも units_run 52 / init_count 54 / icall_miss 5、survey ok / noproc / miss / trap = **869 / 1 / 47 / 25**。RegisterClassW 2 → 2 → 3、`function_52a7f0` ret 0x0 → 0x0 → 0x110000f。監査 sites 2,846 / FRAME_IN_ESCAPED 56 (変化なし)。
監査 (`audit_undefload.py`): sites 2,846 / FRAME_IN_ESCAPED 56 (本回も同一)。
(参考) 取り込み直後の一時的な実測として `62659d4` 時点の 865/1/47/29 がある (merge 解消前の ldfix.py 使用、rc 0)。

## 5. 未解決 / 限界

| 未解決 | 影響 | 起票先 (PM 採番) |
|---|---|---|
| F4 が直した他 9 関数 (71dd80 以外) の動的確認なし | 機械語突合 + survey 不変のみ。誤修復なら survey 外で顕在化 | [M11] liftdiff で F4 10 関数を動的差分 (work-liftdiff + fl-win64) |
| 監査の偽陰性 (消費者が別命令) と FRAME_IN_ESCAPED 未修復 48 関数 | 本件型の脱落が残る可能性 | [LD] 監査を「機械語 read 命令の dest → IR 値」追跡に改め SUSPECT を再計測 |
| 自然起動での `RegisterClass*` 到達 | 受入の「自然到達」は未 | #134 / #490 |
| `TLightweightLayeredControl` の WNDPROC 0x31dd10 が closure 外 (71dd80 は F4 で登録分岐は直ったが CreateWindowExW は NULL のまま) | その class の窓生成 | #563 REPORT §7 の seed 自動生成 |
| #518 (ldfix.py) との conflict | 後 merge 側が rebase | PM |
