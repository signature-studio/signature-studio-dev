# #682 [M11-N28]: 4f9f40 系 5 unit の TList items 書込み元 = `function_47b260` の D4 (disp=0 deref 脱落)

**結論: 書込み元は `function_47b260` (TList の Add 系, VA 0x47b260)。IR の store (`store i64 %rdx.0.reload, ptr %14`) が、呼出元 `function_4f9f10` の stack 局所の番地を FItems 欄 (`T+8`) に書く。機械語の `mov rax,[rbx]` と `mov rcx,[rsi]` (disp=0) の deref 2 点が IR で落ちていた = 既知類型 D4 の新事例。C 転記 (`m11_ov.c`, `M11_FIX_682`) で 5 unit 中 291・296 が ok になる。ただしこの ok は notify (`call [rbx+0x20]`) を省略していることに依存する: notify を有効化すると 291・296 は miss になる (§7)。304・555 は closure 外の未 lift 関数で abort、923 は別箇所の OOB で未解決。受入 3 は部分達成 (条件付き)。**

- 検証起点: `8d883c3` (main)。作業 branch `682-m11-tlist-items-writer`。
- 既知類型との関係: **D4** (該当・新事例。新規 ID 不要)。同じ関数で **D15** (`call qword [rbx+0x20]` = notify の間接 call 欠落) も併発。D15 側は転記に入れると closure 外の呼出し先 (0x535cf0 / 0x536570) で miss 化するため**未解決**。
- DEFECTS.md への追記は PM 判断 (WORKFLOW §5)。行案は §6。

## 1. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 1. 書込み元の関数・命令を特定 | **達成** (probe 非依存の store 計装 + 逆アセンブル) | §2。値の由来は IR と逆アセで確定 (推定ではない)。値の数値は build 依存 (§2.3) |
| 2. 『unit 144 で消える』を再測 | **否定 (削除対象)** | §3。通常 build では 46 で書かれ **831 まで残る**。144 では変化しない。831 で `[g+8]` が 0 になり読めなくなるのが「消える」に見えた可能性 |
| 3. 修復で 5 unit が ok | **部分 (2/5、notify 省略つき)** | §4。291・296 = ok (notify 省略版のみ)。notify 有効版 (§7) では 291・296 = miss。304・555 = trap (`function_535c2e` 未定義 → fail-fast abort)、923 = trap (`function_410b10` の OOB)。ネガコン §5 で 291・296 が trap に戻ることを数値で確認 |

## 2. 書込み元の特定 (受入 1)

### 2.1 観測 (probe 非依存の store 計装)
- `trap_triage/watch_store_682.py`: boot_final3.ll の **全 54,041 store** の直後に `m11_sw(addr, val, site)` を入れた build を作る (call の追加のみ。IR の値・分岐は不変)。`site` → `work/probe682/sites.json` で fn・IR 行に戻す。
- `trap_triage/watch_store_682.c`: `[esc]` = **値が shadow stack の範囲 (`emscripten_stack_get_end..get_base`) を指し、書込み先が stack の外**の store (配置非依存の判定。実行時の stack 位置で判定)。`[sw]` = 監視番地 `[[g+8]+8]` への書込み。
- 実行: `bash trap_triage/store_watch_682.sh w2` (計装 build → 全 942 unit の survey。`unit N` 行と `[esc]`/`[sw]` を stderr に出す)。

抜粋 (修復なし版 `M11_FIX_682=0 bash trap_triage/store_watch_682.sh <tag>` の計装 build の unit 45 の出力。既定の修復ありでは出ない):
```
unit 45 [esc] site=19821 addr=10bc4d78 val=10a9f8f8 esc=5 | function_47b260 176830 store i64 %rdx.0.reload, ptr %14
unit 45 [esc] site=19821 addr=10bb6708 val=10a9f8b8 esc=4 | function_47b260 176830 ...
```
- `addr=10bc4d78` = `T+8` (T = 10bc4d70 = `[g+8]`、後の unit で `[[g+8]+8]` を読むのと同じ欄)。
- `function_47b260` の IR 行 176830 は `store i64 %rdx.0.reload, ptr %14` (`%14 = arg1 + 8*Count`)。値は呼出元の stack 番地。
- 同じ 47b260 の store が unit 95・101・114・302 でも stack 番地を書く (他 unit の同型 escape)。

### 2.2 呼出し元と機械語 (逆アセ `disasm_fn.py`、受入 1 の「命令」部分)
```
function_4f9f10 (呼出元):  mov rax,[rcx+0x18]        ; L = [self+0x18] = T
                          mov [rbp+0x28],rdx        ; 値を stack 局所に置く
                          lea rcx,[rax+8]           ; arg1 = &T.FItems  (= T+8)
                          lea rdx,[rbp+0x28]        ; arg2 = 局所の番地 (値そのものではなく番地)
                          call 0x47b260
function_47b260 (機械語):  mov rbx,rcx                ; rbx = &FItems
                          mov rdi,[rbx+8]           ; Count
                          mov rax,[rbx]             ; ★ FItems (disp=0 の deref)
                          test rax,rax; je ..; mov rax,[rax-8]   ; cap
                          cmp rdi,rax; jne ..; call 0x47a3e0      ; grow
                          mov rax,[rbx]             ; ★ FItems
                          mov rcx,[rsi]             ; ★ 値 = *(arg2) (disp=0 の deref)
                          mov [rax+rdi*8],rcx       ; FItems[Count] := 値
                          add qword [rbx+8],1
                          cmp qword [rbx+0x20],0; je ..; mov rcx,[rbx+0x18]; mov rdx,rsi; mov r8b,1
                          call qword [rbx+0x20]     ; ★ notify (間接 call)
```
IR (boot_final3.ll 行 176793 以降) は `%13 = arg1 + 8*Count` (= `rbx + rdi*8`、★の `[rbx]` を欠く) と `store ptr-value rsi` (★の `[rsi]` を欠く) で、notify の `call qword [rbx+0x20]` も無い。

### 2.3 build 依存の部分 (明記)
- 計装 build の unit 45 の値は `0x10a9f8f8`、通常 build (store 計装なし) の chain 観測は `0x10a9f888`。**0x70 ずれる** (計装が stack 配置を変えるため。build 依存)。
- 「値は 4f9f10 のフレーム内の局所の番地」は配置に依らない構造 (IR の `%stack_var_-16` と機械語 `[rbp+0x28]`) から導いた。数値そのものは build 依存。
- 596 の入口 probe の数値 (`0x10a9f948`、窓 `410360`〜`536c20`) も別 build。本件の窓は 47b260 の内部で、入口単位の probe では「直前の入口」として 410360 が出ただけで書込み命令は見えない (REPORT_596 §3 の未特定をここで解消)。
- 計装の透過性: 計装 build の survey は通常 build と ok/trap/miss/noproc が一致 (864/31/46/1)。`trap_oom` だけ 1→0 (unit 101 の OOM 分類が配置で変わる)。修復後の計装 build は 870 ok (通常 868) で、ok の内訳が配置で 2 unit 動く (未解決 §7)。

## 3. 『unit 144 で消える』の再測 (受入 2)

`trap_triage/chain_682.sh` / `negctl_682.sh` で、各 unit の**開始前**に `g = [0x11f26a0]`, `T = [g+8]`, `items = [T+8]`, `cnt = [T+0x10]` を読んだ (survey は m11_survey.mjs と同一判定)。変化点だけを出す:

| build | 変化点 (unit 開始前の値) |
|---|---|
| 通常 (修復なし, NC) | unit 46: `g=10bcc0c0 T=10bc4d70 items=10a9f888 cnt=1` → **unit 831: T=0** (以降 0) |
| 修復あり | unit 46: `items=18960030` (heap の正しい値, cnt=1) → unit 831: T=0 |

- 通常 build では `items` (stack 番地) は **unit 45 の処理で書かれ、unit 46 の開始時点で既に居る**。unit 144 では変化しない。
- 「unit 144 で消える」は**再現しなかった**。見かけ上 0 になるのは unit 831 の `[g+8]` の変化 (T 自体が 0) で、`[[g+8]+8]` の読みが 0 になるためと推定。
- 596 の 'unit 144 で消える' は 596 の probe build (入口 probe, `survey_units.mjs`) の観測で、本件の通常 build とは build も survey 版も違う。**本 REPORT の数値を正とし、受入 2 は「否定 (削除)」**。

## 4. 修復 (受入 3)

- 修復: `tools/m11/m11_ov.c` に `function_47b260` の C 転記を追加 (`#ifndef M11_FIX_682 / #define M11_FIX_682 1`)。逆アセンブルどおり `[rbx]` (FItems) と `[rsi]` (値) を deref し、grow・Count 更新・戻り値は IR と同じ。**notify の間接 call は既定で省略** (`M11_NOTIFY_682=0`)。有効化の切替 (`M11_NOTIFY_682=1`) は §7 の実測用に入れた。
- 既存の挙動変化 (修復 vs ネガコン): 変わった unit は 4 件のみ (全て非 ok → ok): **95 trap→ok, 101 oom→ok, 291 trap→ok, 296 trap→ok**。回帰 0 (§4.2)。

### 4.1 survey 実測 (通常 build、`m11_survey.mjs`、判定ロジックは既存のまま)

- 2026-10-13 の再測 (本 PR の HEAD、IR は `m11_gen_ir2.sh` で作り直し、ldfix=applied)。

| 構成 | ok | noproc | miss | trap (oom) | clobber | 5 unit (291/296/304/555/923) |
|---|---:|---:|---:|---|---:|---|
| 修復 (既定: notify 省略) | 869 | 1 | 47 | 25 (1) | 0 | ok, ok, trap, trap, trap |
| ネガコン (`M11_FIX_682=0`) | 865 | 1 | 47 | 29 (2) | 0 | trap×5 |
| 修復 + notify 有効 (§7) | 863 | 1 | 53 | 25 (1) | 0 | miss, miss, trap, trap, trap |

- 前版 (`c922c19` 時点の IR) の値は 基準 864/31/46/1、修復 868/27/46/0。今回の IR 再生成で ok 件数が 1〜2 ずれた。どちらも 5 unit の判定は同じ。ずれの原因 (IR の差分) は未特定 (§7)。
- 所要 (秒): 修復 14.29 (n=1, 単一 survey)。store 計装 build 込みの 1 回は 64.6 秒 (`store_watch_682.sh`, `M11_FIX_682=0`)。

### 4.2 unit 別の差分 (同一 IR での実測)

| 比較 | 差分 unit (変化) |
|---|---|
| ネガコン → 修復 (既定) | 95 trap→ok, 101 oom→ok, 291 trap→ok, 296 trap→ok (4 件、回帰 0) |
| 修復 (既定) → 修復 + notify 有効 | 45 ok→miss, 95 ok→miss, 101 ok→miss, 291 ok→miss, 296 ok→miss, 302 ok→miss (6 件) |

- 上の 2 行目が notify 省略への依存の実測。notify を入れると、修復で ok になった unit (291・296) と、基準で ok だった unit (45・95・101・302) が miss になる。ok 数の差 6 件はこの 6 unit。
- 呼出先 (`0x535cf0`・`0x536570` 等) は IR に定義も宣言も無く、closure 外。notify の実行は miss 化の直接の原因。

## 5. ネガコン (判定スクリプトは不合格で非 0)

`trap_triage/check_682.py <units.json> [--units ...]` は指定 unit が 1 つでも非 ok なら **exit 1**。

| 実行 | 判定 | rc |
|---|---|---:|
| 修復あり (notify 省略), 5 unit | `units ok 2 / 5: 291=ok 296=ok 304=trap 555=trap 923=trap` | **1** |
| 修復あり, 291,296 | `units ok 2 / 2` | 0 |
| ネガコン (修復外し), 5 unit | `units ok 0 / 5: 291=trap 296=trap 304=trap 555=trap 923=trap` | **1** |
| 修復 + notify 有効, 5 unit | `units ok 0 / 5: 291=miss 296=miss 304=trap 555=trap 923=trap` | **1** |

- 上の表は 2026-10-13 の再測 (IR 再生成後)。ネガコンの 291・296 は trap (前版の記録も trap)。

ネガコンの chain 差 (§3) も同じ build 対で確認 (`items` が stack 番地 ↔ heap 番地)。

## 6. D 類型への判定と DEFECTS.md 行案 (PM 判断)

- 47b260 の欠陥 = D4 (`mov r64,[argreg]` (disp=0) の deref 脱落 → `rD := argreg`) の**新事例** (同型 2 点: `[rbx]`・`[rsi]`)。既存の D4 行の「再発例」に追記する形が妥当 (新 ID 不要)。
- 同関数の notify `call qword [rbx+0x20]` 欠落は **D15 の新事例** (IR に call が無い)。転記で入れると closure 外 (0x535cf0 / 0x536570) の miss になるため、D15 行に「未解決 (呼出し先の closure 外れ)」として併記する。
- 行案 (D4 の再発例に追記。PM が docs/DEFECTS.md へ反映):
  > M11 #682 (TList Add 系 `47b260`): `mov rax,[rbx]` (FItems) と `mov rcx,[rsi]` (値) の disp=0 deref 2 点が脱落し、FItems 欄 (T+8) に呼出元 `4f9f10` の stack 番地が入る。症状は 4f9f40 系 5 unit (291 296 304 555 923) の OOB/abort の起点。検出: 値が stack 範囲で書込み先が stack 外の store (`watch_store_682`)。修復: `m11_ov.c` の `function_47b260` 転記 (`M11_FIX_682`)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 304・555: `function_535bf2` が **IR 未定義の `function_535c2e`** を呼び fail-fast (`m11_unresolved_function` → abort)。closure 外の関数 | 2 unit が trap | #714 (M11 closure 欠け) |
| 923: `4fb910`→`410730`→`410b10` (C 転記, モニタスロット解決) の `[obj-0x80..]` 系 OOB。原因未切り分け | 1 unit が trap | #714 (同上) |
| 47b260 の notify 間接 call (D15) を有効化 (`M11_NOTIFY_682=1`) すると、呼出先 0x535cf0 / 0x536570 / 537220 / 53d290 / 537a40 が closure 外で miss。ok→miss は **45・95・101・291・296・302 の 6 unit** (§4.2)。291・296 の修復 ok はこの省略に依存する | 既定は省略 (`M11_NOTIFY_682=0`)。PM 判断 (DEFECTS D15 行に併記・closure 拡張の要否) |
| 再生成 IR の ok 件数が前版より 1〜2 ずれる (基準 864→865、修復 868→869、miss 46→47) | 5 unit の判定は一致。絶対値の比較は同一 IR 内で行うこと | 原因未特定 (前版の IR と今回の gen_ir2 出力の差分は未比較) | PM 判断 (IR 再生成の再現性) |
| DEFECTS.md への D4 再発例の追記 (§6 行案) | 受入条件「D 類型なら追記」 | #716 (DOCS-9)。本 PR では docs/DEFECTS.md を変更しない (WORKFLOW §5) |
| 計装 build の ok が 870 (通常 868)、oom 内訳が配置依存 | 計装の透過性は ok/trap 単位で 2 unit ぶれる | PM 判断 (計装は診断専用) |
| 16.23 秒の外れ値 (survey n=3) の原因 | 計測の信頼性 | 未確認 |
| 596 の入口 probe 結論 (書込み元の未特定、窓 410360〜536c20) の訂正 | 596 REPORT の §3 は本件で解消 | #596 にコメント済み (PM) |
| `m11_e2e.sh` の PE 固定パス (`[WIN64]` の `extracted/block00031_PE.bin` を直書き) と合否に使えない exit 0 固定 (§11) | e2e 単体で合否判定できない。本 run は PE 行を差し替えて実行 | #715 (M11 e2e の exit 仕様・PE 固定) |

## 8. 検証範囲 / 範囲外

- 範囲内: 通常 build の survey 全 942 unit、5 unit の個別ラベル、unit 45/144 の chain 観測、store 計装 (全 store)、ネガコン (転記の on/off)。
- 範囲外: gen_ir2 (ldfix/qstore の再実行) は未実施 (work/ の既存 IR を使用)。`m11_e2e.sh` の stamp (`*_lb_base.stamp`) が snapshot に無かったため `0` を書いて補った。`m11_e2e.sh` の全体実行は §11 (PE の固定パスだけ差し替え)。
- 計装 build は診断専用 (`store_watch_682.sh` が終了時に通常 build へ復元)。
- 修復の影響範囲: 47b260 の 25 call site 全て。survey の 942 unit では回帰 0。

## 9. 再現コマンド

```sh
# 素材: work-m11 はアーカイブ内が tools/m11/work/ 始まりなので、repo 直下で `tar --zstd -xf work-m11.tar.zst` して tools/m11/work/ に置く
#       fl-win64 は PE 1 本だけで足りる (extracted/block00031_PE.bin)
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" PE="$FL_WIN64_DIR/extracted/block00031_PE.bin"
python3 -m pip install capstone pefile
cd tools/m11
mkdir -p work/probe682                                                    # 以降の出力先 (未作成だと書込みに失敗する)
bash m11_gen_ir2.sh                                                      # work/ir_conditions.json (ldfix=applied) を作る (fail-closed: 無いと build は拒否。約 21 秒で完了)
bash m11_build.sh && M11_SURVEY_UNITS=work/probe682/units_fix.json node m11_survey.mjs
python3 trap_triage/check_682.py work/probe682/units_fix.json            # rc=1 (2/5)
bash trap_triage/negctl_682.sh nc && python3 trap_triage/check_682.py work/probe682/units_nc.json   # rc=1 (0/5)
bash trap_triage/chain_682.sh fix                                        # unit 前の [[g+8]+8] 変化点
M11_FIX_682=0 bash trap_triage/store_watch_682.sh nc_w                   # 全 store 計装 (修復なし版): §2.1 の [esc] site=19821 が出る
bash trap_triage/store_watch_682.sh fix_w                                # 同 (修復あり版): unit 45 に [esc] site=19821 は出ない
```

- `M11_NOTIFY_682=1` で notify (`call [rbx+0x20]`) を有効化できる (既定 0)。§7 の実測はこの切替による。
- stamp の補完 (`echo 0 > work/<s>.stamp`) は書かない。`m11_build.sh` は `ir_lb_base`・`img_lb_base` を「存在する時だけ」照合する (L28 `[ -f ... ] &&`)。`lb_base` は build 自身が書く (L22–25)。stamp を補うのは `m11_e2e.sh` の経路 (§11) のみ。

## 10. 検証起点 commit

- 検証起点: `8d883c3` (main)。修復 commit はこの branch の次の commit (本 PR)。
- 変更ファイル: `tools/m11/m11_ov.c` (47b260 転記と `M11_NOTIFY_682` を追加。他は不変)、`tools/m11/trap_triage/{REPORT_682.md, watch_store_682.{py,c}, store_watch_682.sh, chain_682.sh, negctl_682.sh, check_682.py}`、`docs/DOC_MAP.md` (§3 の索引 1 行)。
- work/ 配下の成果 (`work/probe682/`、sites.json 5.6 MB 等) は git 管理外 (`tools/m11/.gitignore: work/`)。

## 11. `m11_e2e.sh` 全体の実行 (HEAD `c922c19`)

- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP` の下で、`m11_e2e.sh` の `PE=` 行だけを `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` に差し替え、`sed ... | bash -s` で実行 (リポジトリのファイルは変更していない)。
- 結果: rc=0 / 所要 35.5 秒 / load 0.33→0.63 / 4 vCPU / n=1。
- `M11_SUMMARY`: reached_stage 4 (DllMain attach 完走・longjmp 経路、stage 5 未達) / units_run_full 22 / survey ok 868・trap 27 (oom 0)・clobber 0・miss 46 / getmem 33・freemem 20 / VA 1.3 MB / wasm 6,027,631 B。
- survey の ok・trap・clobber・miss は §4.1 の修復行と一致。stage と units_run は §10 の最終 HEAD と一致。
- 注意: `m11_e2e.sh` は未達・前提欠如でも `exit 0` を返す (スクリプト冒頭の注記どおり)。rc=0 は合否の根拠にしない。合否は `check_682.py` (不合格で rc=1) で判定する。
- 未解決: `m11_e2e.sh` の PE 固定パス (`[WIN64]` の `extracted/block00031_PE.bin` を直書き) と exit 0 固定は、本 PR の範囲外として残す (起票先 #715、§7 の表)。

## 12. レビュー指摘の修正 commit の検証 (#706、対象 HEAD `8be7b5d`)

- 変更: `REPORT_682.md` (§7・§9・§11 の表記)、`docs/DOC_MAP.md` (§3 索引行)、`trap_triage/store_watch_682.sh` (第 2 引数・`SV_TRACE_AT`・no-op の `cp` を削除。`m11_survey.mjs` に対応処理が無かったため)。`m11_ov.c` と判定スクリプトは不変。
- 環境: `fl-win64` は `extracted/block00031_PE.bin` (22 MB) のみ展開、`work-m11` は `tools/m11/work/` に展開。`toolchain-emsdk` は展開せず、runner の既存の `[EMSDK]` (emcc 6.0.12、pin と一致) を使用。node v22.23.3。capstone・pefile は pip で導入。
- 実測 (n=1、いずれも 8be7b5d のツリーで実行):

| 手順 | 結果 | 所要 | load (1 分平均) |
|---|---|---:|---|
| `m11_build.sh` | rc=0、signature mismatch 0・undefined 0、qstore 実行 (警告 0) | 17.99 s | — |
| `m11_survey.mjs` (修復あり) | ok 868・noproc 1・miss 46・trap 27 (oom 0)・clobber 0 | 4.79 s | 0.66→0.69 |
| `check_682.py units_fix.json` | 2/5 (291=ok 296=ok 304=trap 555=trap 923=trap)、**rc=1** | — | — |
| `store_watch_682.sh w2` (修正後の引数) | rc=0、計装 store 54,041 件、計装 build の survey ok 870・noproc 1・miss 46・trap 25 (oom 6)・clobber 0、`[sw]` hits 15 | 71.72 s | 0.58→0.87 |
| `negctl_682.sh nc` (`M11_FIX_682=0`) | rc=0、survey ok 864・noproc 1・miss 46・trap 31 (oom 1)、`check_682.py units_nc.json` 0/5・**rc=1** | 32.26 s | — |

- §9 の stamp 補完の削除: `work/` に `ir_lb_base`・`img_lb_base`・`lb_base` の stamp が無い状態 (展開直後は `msimd.stamp` のみ) で `m11_build.sh` が rc=0 で通ったことを確認した。
- 各数値は §4.1・§5・§7 の値と一致 (survey の unit 合計は 942 で、ok+noproc+miss+trap が一致)。
- 未実施: `chain_682.sh` (本 commit で変更なし。REPORT §3 の値は再測していない)。`m11_e2e.sh` 全体 (§11 は前 HEAD `c922c19` での実測のまま。本 commit で挙動は変わらない)。

## 13. notify 分岐の実測と store 計装の修正 (#706 の 2 回目の差し戻し対応)

- 対象: 本 PR の HEAD (`9952e60` を取り込んだ後の commit)。素材: `work-m11` を `tools/m11/work/` に展開、`fl-win64` は PE 1 本 (`extracted/block00031_PE.bin`, 22 MB) のみ展開。node v22.23.3、capstone・pefile は pip 導入。
- IR: `m11_gen_ir2.sh` で作り直し (`ir_conditions.json` が snapshot に無く、build が #680 の fail-closed で拒否されたため)。gen_ir2 は 20.9 秒 (`ldfix` F1=902 / F2=30 / F3c=16、errors 0)。
- 所要: 修復 survey 14.29 秒 (n=1、コミット前)・14.32 秒 (HEAD)。計装込みの所要は下表 (HEAD 再測)。load は未計測。
- 変更: `m11_ov.c` に `M11_NOTIFY_682` (既定 0) を追加。`store_watch_682.sh` は `M11_FIX_682` / `M11_NOTIFY_682` を受け取り、`ov.o` を明示的に再コンパイルする。`watch_store_682.{py,c}` は store 幅を渡し `[addr, addr+width)` で判定する。`store_watch_682.sh` / `negctl_682.sh` / `chain_682.sh` は Node 失敗で exit する。
- 検証 (同一 IR):
  - 修復 (既定) survey: ok 869 / miss 47 / trap 25 (oom 1)。`check_682.py` は 2/5、rc=1。
  - 修復 + notify 有効: ok 863 / miss 53 / trap 25。5 unit は 0/5、rc=1。
  - ネガコン (`M11_FIX_682=0`): ok 865 / miss 47 / trap 29 (oom 2)。0/5、rc=1。
  - 計装 build (`M11_FIX_682=0`): `unit 45` の `[esc] site=19821 addr=10bb6708 val=10a9f918` / `addr=10bcc0a8 val=10a9f958` を確認 (§2.1 と同じ site。値は build 依存)。`[sw]` 8 hit。
  - 計装 build (既定 `M11_FIX_682=1`): §2.1 の抜粋は出ない (修復で書込みが起きないため)。
- コミット済み HEAD `2b793ae` での再測 (n=1、各 build は `m11_build.sh` rc=0、signature mismatch 0・undefined 0):

| 構成 (HEAD `2b793ae`) | survey ok/noproc/miss/trap (oom) | 5 unit (291/296/304/555/923) | check_682 rc | 所要 |
|---|---|---|---:|---:|
| 修復 (既定: notify 省略) | 869 / 1 / 47 / 25 (1) | ok, ok, trap, trap, trap | 1 (2/5) | 14.32 s |
| ネガコン (`negctl_682.sh headnc`) | 865 / 1 / 47 / 29 (2) | trap×5 | 1 (0/5) | 47.64 s (build 込み) |
| 修復 + notify 有効 (`M11_NOTIFY_682=1`) | 863 / 1 / 53 / 25 (1) | miss, miss, trap, trap, trap | 1 (0/5) | — |
| 計装 修復なし (`store_watch_682.sh head_nc_w`) | 863 / 1 / 47 / 31 (1) | — | — | 63.03 s |
| 計装 修復あり (`store_watch_682.sh head_fix_w`) | 869 / 1 / 47 / 25 (1) | — | — | 98.32 s |

- HEAD の修復 survey は、コミット前の run と全 942 unit が一致した (差分 0)。
- 計装 修復なし版の unit 45: `[esc] site=19821` が 2 件 (§2.1 と同一 site)。修復あり版: 0 件。`[sw]` hits は両方 8。
- 計装 build は配置が変わるため、ok 件数はネガコン本体と一致しない (§2.3 の注記どおり)。
- 未検証: `chain_682.sh` と `m11_e2e.sh` 全体の再実行 (本 13 節の範囲外)。

