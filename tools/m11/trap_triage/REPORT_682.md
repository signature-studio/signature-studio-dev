# #682 [M11-N28]: 4f9f40 系 5 unit の TList items 書込み元 = `function_47b260` の D4 (disp=0 deref 脱落)

**結論: 書込み元は `function_47b260` (TList の Add 系, VA 0x47b260)。IR の store (`store i64 %rdx.0.reload, ptr %14`, boot_final3.ll 行 176830) が、呼出元 `function_4f9f10` の stack 局所の番地を FItems 欄 (`T+8`) に書く。機械語の `mov rax,[rbx]` と `mov rcx,[rsi]` (disp=0) の deref 2 点が IR で落ちていた = 既知類型 D4 の新事例。修復 (`m11_ov.c` の 47b260 転記) で 291・296 が ok になり、5 unit 中 2 が ok (304・555 は closure 外の未 lift 関数 abort、923 は別箇所の OOB で未解決)。受入 3 は部分達成。**

- 検証起点: `8d883c3` (main)。作業 branch `682-m11-tlist-items-writer`。
- 既知類型との関係: **D4** (該当・新事例。新規 ID 不要)。同じ関数で **D15** (`call qword [rbx+0x20]` = notify の間接 call 欠落) も併発。D15 側は転記に入れると closure 外の呼出し先 (0x535cf0 / 0x536570) で miss 化するため**未解決**。
- DEFECTS.md への追記は PM 判断 (WORKFLOW §5)。行案は §6。

## 1. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 1. 書込み元の関数・命令を特定 | **達成** (probe 非依存の store 計装 + 逆アセンブル) | §2。値の由来は IR と逆アセで確定 (推定ではない)。値の数値は build 依存 (§2.3) |
| 2. 『unit 144 で消える』を再測 | **否定 (削除対象)** | §3。通常 build では 46 で書かれ **831 まで残る**。144 では変化しない。831 で `[g+8]` が 0 になり読めなくなるのが「消える」に見えた可能性 |
| 3. 修復で 5 unit が ok | **部分 (2/5)** | §4。291・296 = ok (n=3 の survey で再現)。304・555 = trap (`function_535c2e` 未定義 → fail-fast abort)、923 = trap (`function_410b10` の OOB)。ネガコン §5 で 291・296 が trap に戻ることを数値で確認 |

## 2. 書込み元の特定 (受入 1)

### 2.1 観測 (probe 非依存の store 計装)
- `trap_triage/watch_store_682.py`: boot_final3.ll の **全 54,041 store** の直後に `m11_sw(addr, val, site)` を入れた build を作る (call の追加のみ。IR の値・分岐は不変)。`site` → `work/probe682/sites.json` で fn・IR 行に戻す。
- `trap_triage/watch_store_682.c`: `[esc]` = **値が shadow stack の範囲 (`emscripten_stack_get_end..get_base`) を指し、書込み先が stack の外**の store (配置非依存の判定。実行時の stack 位置で判定)。`[sw]` = 監視番地 `[[g+8]+8]` への書込み。
- 実行: `bash trap_triage/store_watch_682.sh w2` (計装 build → 全 942 unit の survey。`unit N` 行と `[esc]`/`[sw]` を stderr に出す)。

抜粋 (通常 build = 修復なし。計装 build の unit 45 の出力):
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

- 修復: `tools/m11/m11_ov.c` に `function_47b260` の C 転記を追加 (`#ifndef M11_FIX_682 / #define M11_FIX_682 1`)。逆アセンブルどおり `[rbx]` (FItems) と `[rsi]` (値) を deref し、grow・Count 更新・戻り値は IR と同じ。**notify の間接 call は転記に入れていない** (理由 §6 の未解決)。既定 ON。
- 既存の挙動変化: 通常 build の survey で変わった unit は 4 件のみ (全て非 ok → ok): **95 trap→ok, 101 oom→ok, 291 trap→ok, 296 trap→ok**。回帰 0。

### 4.1 survey 実測 (通常 build、`m11_survey.mjs`、判定ロジックは既存のまま)

| 構成 | ok | noproc | miss | trap (oom) | clobber | 5 unit (291/296/304/555/923) |
|---|---:|---:|---:|---|---:|---|
| 基準 (main `8d883c3`) | 864 | 1 | 46 | 31 (1) | 0 | trap×5 (45=ok, 144=trap) |
| **修復 (既定)** | **868** | 1 | 46 | 27 (0) | 0 | **ok, ok, trap, trap, trap** |
| ネガコン (`M11_FIX_682=0`) | 864 | 1 | 46 | 31 (1) | 0 | trap×5 |

- 基準の値は REPORT §13 (`864/31/46/1`、clobber 0) と一致。
- 所要 (秒): 基準 8.18 (n=1, load 0.26→0.45)。修復 8.37 / **16.23** / 8.43 (n=3, load 0.28→0.56、16.2 は外れ値で原因未確認)。
- 並列数: 1 (survey は単一プロセス)。CPU 4 vCPU。

## 5. ネガコン (判定スクリプトは不合格で非 0)

`trap_triage/check_682.py <units.json> [--units ...]` は指定 unit が 1 つでも非 ok なら **exit 1**。

| 実行 | 判定 | rc |
|---|---|---:|
| 修復あり, 5 unit | `units ok 2 / 5: 291=ok 296=ok 304=trap 555=trap 923=trap` | **1** |
| 修復あり, 291,296 | `units ok 2 / 2` | 0 |
| ネガコン (修復外し), 5 unit | `units ok 0 / 5` (全 trap) | **1** |
| ネガコン, 291,296 | `units ok 0 / 2: 291=trap 296=trap` | **1** |

ネガコンの chain 差 (§3) も同じ build 対で確認 (`items` が stack 番地 ↔ heap 番地)。

## 6. D 類型への判定と DEFECTS.md 行案 (PM 判断)

- 47b260 の欠陥 = D4 (`mov r64,[argreg]` (disp=0) の deref 脱落 → `rD := argreg`) の**新事例** (同型 2 点: `[rbx]`・`[rsi]`)。既存の D4 行の「再発例」に追記する形が妥当 (新 ID 不要)。
- 同関数の notify `call qword [rbx+0x20]` 欠落は **D15 の新事例** (IR に call が無い)。転記で入れると closure 外 (0x535cf0 / 0x536570) の miss になるため、D15 行に「未解決 (呼出し先の closure 外れ)」として併記する。
- 行案 (D4 の再発例に追記。PM が docs/DEFECTS.md へ反映):
  > M11 #682 (TList Add 系 `47b260`): `mov rax,[rbx]` (FItems) と `mov rcx,[rsi]` (値) の disp=0 deref 2 点が脱落し、FItems 欄 (T+8) に呼出元 `4f9f10` の stack 番地が入る。症状は 4f9f40 系 5 unit (291 296 304 555 923) の OOB/abort の起点。検出: 値が stack 範囲で書込み先が stack 外の store (`watch_store_682`)。修復: `m11_ov.c` の `function_47b260` 転記 (`M11_FIX_682`)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 304・555: `function_535bf2` が **IR 未定義の `function_535c2e`** を呼び fail-fast (`m11_unresolved_function` → abort)。closure 外の関数 | 2 unit が trap | 新規 (M11 closure 欠け。PM 起票) |
| 923: `4fb910`→`410730`→`410b10` (C 転記, モニタスロット解決) の `[obj-0x80..]` 系 OOB。原因未切り分け | 1 unit が trap | 新規 (同上) |
| 47b260 の notify 間接 call (D15) を入れると 0x535cf0 / 0x536570 が closure 外で miss (試行: unit 45・302 が ok→miss、95・101 が miss) | 転記は notify を省略中 | PM 判断 (DEFECTS D15 行に併記) |
| 計装 build の ok が 870 (通常 868)、oom 内訳が配置依存 | 計装の透過性は ok/trap 単位で 2 unit ぶれる | PM 判断 (計装は診断専用) |
| 16.23 秒の外れ値 (survey n=3) の原因 | 計測の信頼性 | 未確認 |
| 596 の入口 probe 結論 (書込み元の未特定、窓 410360〜536c20) の訂正 | 596 REPORT の §3 は本件で解消 | #596 にコメント (PM) |

## 8. 検証範囲 / 範囲外

- 範囲内: 通常 build の survey 全 942 unit、5 unit の個別ラベル、unit 45/144 の chain 観測、store 計装 (全 store)、ネガコン (転記の on/off)。
- 範囲外: `m11_e2e.sh` 全体の実行 (PE の固定パス `/home/ubuntu/work/analysis/win64/extracted/` が無く、`m11_e2e.sh` は前提不足で即終了する。代わりに `m11_build.sh` と `m11_survey.mjs` を直接実行)。gen_ir2 (ldfix/qstore の再実行) は未実施 (work/ の既存 IR を使用)。`m11_e2e.sh` の stamp (`*_lb_base.stamp`) が snapshot に無かったため `0` を書いて補った。
- 計装 build は診断専用 (`store_watch_682.sh` が終了時に通常 build へ復元)。
- 修復の影響範囲: 47b260 の 25 call site 全て。survey の 942 unit では回帰 0。

## 9. 再現コマンド

```sh
# 素材 (work/ は展開済み前提): PE を fl-win64 から展開し FL_WIN64_DIR を指す (m11_build.sh の qstore 用)
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"; python3 -m pip install capstone pefile
cd tools/m11
for s in ir_lb_base img_lb_base lb_base; do echo 0 > work/$s.stamp; done   # 旧 snapshot に stamp が無い場合のみ
bash m11_build.sh && M11_SURVEY_UNITS=work/probe682/units_fix.json node m11_survey.mjs
python3 trap_triage/check_682.py work/probe682/units_fix.json            # rc=1 (2/5)
bash trap_triage/negctl_682.sh nc && python3 trap_triage/check_682.py work/probe682/units_nc.json   # rc=1 (0/5)
bash trap_triage/chain_682.sh fix                                        # unit 前の [[g+8]+8] 変化点
bash trap_triage/store_watch_682.sh w2                                   # 全 store 計装 ([esc]/[sw], sites.json)
```

## 10. 検証起点 commit

- 検証起点: `8d883c3` (main)。修復 commit はこの branch の次の commit (本 PR)。
- 変更ファイル: `tools/m11/m11_ov.c` (47b260 転記を追加。他は不変)、`tools/m11/trap_triage/{REPORT_682.md, watch_store_682.{py,c}, store_watch_682.sh, chain_682.sh, negctl_682.sh, check_682.py}`。
- work/ 配下の成果 (`work/probe682/`、sites.json 5.6 MB 等) は git 管理外 (`tools/m11/.gitignore: work/`)。
