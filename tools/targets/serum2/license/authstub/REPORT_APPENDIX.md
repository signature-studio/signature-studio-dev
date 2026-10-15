> **正本**: `tools/targets/serum2/license/authstub/REPORT.md` §13 (§13b)・§14 (付録 §14b)。本書は REPORT の 250 行上限のため、旧 §13 の全文と旧 §14 の詳細を分割移動した付録。

## 13b. L1 脱落条件の特定 (#823, 機械語 ↔ raw IR の突合)

- 本節は旧 §13 の内容で、§13 の原因の根拠 (機械語の分岐構造・raw IR の該当ブロック・census 手順と実測) を記録する。§13 の結論と矛盾しない。

- 対象 PE: `Serum2_win64.vst3` sha256 `501e7bb3…5283` (19,236,864 B)。raw lift: `work/lift/authstub.drc.ll` (e2e.sh [1])。
- 機械語 (capstone 実測):

  ```
  0x1800c2d66 test rax, rax            ; rax = [rsi+0x90] (deferred 通知先)
  0x1800c2d69 je   0x1800c2ef4         ; ★ 唯一の入口 (rax==0 の枝)
  0x1800c2d6f or   dword ptr [rax+8], 0x800010   ; rax!=0 の枝 (deferred)
  0x1800c2ef4 mov  rcx, [rsi+0x10]     ; host handler
  0x1800c2ef8 test rcx, rcx
  0x1800c2efb je   0x1800c2f08
  0x1800c2efd mov  rax, [rcx]
  0x1800c2f00 mov  edx, 0x800010
  0x1800c2f05 call [rax+0x30]          ; ★ 直接 vtable 通知
  ```

- 脱落の機構: raw IR で `[rsi+0x90]` の null 判定 (`%110 = icmp eq i64 %109, 0`, `br i1 %110, label %dec_label_pc_1800c2f08, ...`, authstub.drc.ll 行 9870–9872) の**null 枝の飛び先が 0x1800c2f08 (skip) になっている**。機械語の `je` は 0x1800c2ef4 (直接通知) へ飛ぶ。このため 0x1800c2ef4 の基本ブロックは IR に生成されない。
- 枝の向きは逆: IR の null 枝は「通知しない」、機械語の null 枝は「host へ直接通知する」。

### 数え方 (census)

`python3 tools/targets/serum2/license/authstub/l1_census.py <PE> <raw.ll>` が出力する指標 (#1029 で raw IR 側を拡張):
機械語側は直接 call site 数 (`sites`)・`edx=0x800010` 即値ロード数 (`edx_const`)・site への入口 edge 数 (`into`)。
raw IR 側は `insn.addr` が site 範囲にある命令数・そのうち直接 `call`・site 範囲内の `0x800010` 即値・
`br`/`switch` で site ブロックを指す edge・`insn.addr` 被覆数・ブロック `dec_label_pc_1800c2ef4` の有無。

| 指標 | 機械語 (スクリプト出力) | raw IR (スクリプト出力) | raw IR (手確認) |
|---|---|---|---|
| 直接 `call [reg+0x30]` site (0x1800c2ef4–f05) | `sites` = 1 | `direct call in site range` = 0 | 0 件 (9872–9900 行の `call` は `@function_180034560` の 1 件のみ。`add ..., 48` は 1461・2178・2649 行の 3 件で、いずれも本 site の範囲外) |
| `edx=0x800010` 即値ロード | `edx_const` = 1 | `edx=0x800010 immediates in site` = 0 (ファイル全体の `8388624` は 1 件) | `i32 8388608` / `8388624` の即値は 0x800010 を含む `or` が 9878 行の 1 件のみ (rax≠0 の deferred 側、`insn.addr` は 0x1800c2d6f) |
| 0x1800c2ef4 への入口 edge | `into` = 1 (`je` @0x1800c2d69) | `edges (br/switch) into site block` = 0 | `dec_label_pc_1800c2ef4` の参照 0 件 (grep `dec_label_pc_1800c2ef4`) |
| `insn.addr` が site 範囲を被覆 | — | `insn.addr entries covering site` = 0 | — |
| ブロック `dec_label_pc_1800c2ef4` | — | `has_block` = False | — |

- 2026-10-13 実測 (#1029): 上記スクリプト出力と手確認列は一致。手確認列は突合の記録として残し、census の raw IR 側の列をスクリプト出力で併記した。
- 9872 行の `br i1 %110, label %dec_label_pc_1800c2f08, label %dec_label_pc_1800c2d6f` は、null 枝 (`%110` = true) が skip 先 `0x1800c2f08` を指す。`0x1800c2ef4` を指す枝は IR に無い。

### 実測の記録 (e2e・census)

- 実行: 2026-10-13 (UTC 17:45)・HEAD `c7fd0739` (main 取り込み後)・load average 0.06 (1 分平均、run 開始時)。
  PE は `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` から `7z x` で `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` を取り出した (19,236,864 B・sha256 `501e7bb3…5283`)。
- `bash tools/targets/serum2/license/authstub/e2e.sh` (`work/` を削除してから cold 実行): exit 0・**23/23 PASS**・real 34.8 s (lift は本実行で新規生成。`authstub.drc.ll` 710,975 B)。
- `python3 tools/targets/serum2/license/authstub/l1_census.py <PE> work/lift/authstub.drc.ll`: exit 0・real 0.16 s。
  `sites=1` / `edx_const=1` / `into=1` / `covered=0` / `has_block=False`。
- 同一 HEAD `4df84cd4` (main 取り込み前) でも 2026-10-13 17:40 に e2e 23/23 PASS・34.9 s、census は同じ 5 指標を確認。
- 前 run (HEAD `3afb7674`) の申告値 (3.2 s・23/23) は一次ログ無しのため本節には含めない。本節が一次の実測。
- 実行 (#823 再実行): HEAD `1ef8ccfb` (origin/main)・`work/` 無し (cold)・load average 1.08 (1 分平均、起動 5 分後)。PE は `plugins-serum2` から同手順で取り出し、sha256 `501e7bb3…5283` (19,236,864 B) を一致確認。
  - `bash e2e.sh`: exit 0・**23/23 PASS**・real 36.07 s (step [1] の RetDec lift を含む)。
  - `l1_census.py`: `sites=1` / `edx_const=1` / `into=1` / `covered=0` / `has_block=False` (上の 5 指標と一致)。
- 上記は復元 pass 適用前の基準値 (前後比較の「前」)。復元 pass は未実装のため「後」の値は無い。

- HEAD `08bb8f19` (#1029 PR 作成時・worktree `ws-1029`・出典: PR #1205 作成時の申告値。レビュー run では再実行していない)。
  - e2e (`bash tools/targets/serum2/license/authstub/e2e.sh`): exit 0・**23/23 PASS**・real **5.5 s** (lift は main 側で生成したものを再利用)。
  - e2e cold (main 側・lift 新規生成): real **35.4 s**・23/23 PASS。
  - census machine 側: `sites=1` / `edx_const=1` / `into=1`。
  - census IR 側 (`l1_census.py` 拡張後の 6 指標): `insns with insn.addr in site range=0` / `direct call in site range=0` / `edx=0x800010 immediates in site=0` / `edx=0x800010 immediates (whole file)=1` / `edges (br/switch) into site=0` / `covered=0` / `has_block=False`。census real 0.174 s。
  - 上記 IR 側の行番号 (9872 行の `br`・9878 行の `or ... 8388624`) の実物確認は、レビュー run で PE・raw `.ll` が無く未実施。

- 事実の範囲: 上記は raw lift 1 本での実測。復元 pass は未実装 (受入条件 2・3 は未達、子 issue に分割)。
- 未測定 (断定しない): 0x1800c2d59 の `je` は `[rsi+0x22792]` の bit で分岐し、その bit を 1 にする store は 0x1800c2d42 の 1 箇所のみ。N2a でこの store を 0 に置換した後の到達性は、本 census では測っていない。e2e の 23/23 との関係も未確認。

## 14b. L1 復元 pass の詳細 (#1009 / SR-12, 追跡 #823)

REPORT §14 の詳細。pass の仕様・結論は REPORT §14 が正本。

- 実装: `tools/liftlib/liftlib/passes/l1_restore.py`。raw IR の `br` (0x1800c2d69 の `je` の null 枝, IR 行 9872) の真の枝を新設ブロック `dec_label_pc_1800c2ef4` へ戻す。ブロックは `host=[rsi+0x10]` の null 判定と `call @__icall_dispatch(i64 0x1800c2f05)` (#228 の `ir_icall_restore.py` と同じ宣言) を持つ。site は機械語 VA で指定し、1 件でなければ失敗する。元行の `!insn.addr !N` は正規表現で捕捉して再利用する (番号の固定値は使わない)。
- `%arg1` = rsi の根拠: 同関数 0x1800c2b50 の demo bit `[rsi+0x22792]` (機械語 0x1800c2cfe) は IR で `%x = add i64 %arg1, 141202` (141202 = 0x22792) として現れる (`authstub_irpass.py` の demo bit 検出, L233)。よって IR の `%arg1` は関数引数 this = rsi。raw IR 行の直接確認は本 fix の run では未実施 (raw lift 無し)。
- census (`l1_census.py`, PE sha256 `501e7bb3…5283`)。pass 前 (raw) の値は §13b の表が正本 (機械語 `sites=1`/`edx_const=1`/`into=1`、IR 側 `covered=0`/`has_block=False` 等)。pass は IR のみを変え機械語は変えないため、pass 後に変わるのは IR 側だけ:

  | 指標 (IR 側・pass 後) | 値 (raw → restored) |
  |---|---|
  | `insn.addr` が site 範囲を被覆 | 0 → 2 |
  | 直接 `call` が site 範囲 | 0 → 1 |
  | 入口 edge (`br`/`switch`) into site block | 0 → 1 |
  | `edx=0x800010` 即値の site 範囲 | 0 → 0 (ファイル全体は 1 → 1) |
  | ブロック `dec_label_pc_1800c2ef4` | 不在 → 存在 |

- 到達性 (`authstub_irpass.reachable_set`): restored では `dec_label_pc_1800c2ef4` と `l1_call` が関数入口から到達可能。
- 実測 (測定 commit `27e2c48d` = origin/main。PR #1353 の作者が取得した値。fix run では再実行していない。素材 `plugins-serum2` は `$ARTIFACTS_DIR` に実在することを確認済み。RetDec v5.0 cold lift は 30.20 s・lift 出力 710,975 B。lift は pass に依存しない):
  - `bash e2e.sh` (`27e2c48d`): rc 0・**23/23 PASS**・warm **4.78 s** (lift キャッシュ利用)。cold の 30.20 s は lift 含む。pass は e2e チェーンに入っていないため、この e2e は不変確認であり pass の検証ではない。
  - ネガコン: pass を外した raw IR が脱落状態 (上表の左列) そのもの。二重適用は `l1_restore` が exit 1 で拒否 (`二重適用`)。
  - 構文: `base` 修復 (`liftlib.passes.base.run_base`) 後の raw / restored を `llvm-as-18` で検査、いずれも rc 0 (未修復の RetDec 出力は constexpr の `or` で `llvm-as-18` が落ちるため、検査は base 後で行う)。
- 旧実測 (いずれも e2e チェーン不変の確認であり本変更の検証ではない。cold と warm は実行条件が違い比較できない):
  - HEAD `a5adb2fc` (origin/main 取り込み時点, `plugins-serum2` 展開 sha256 一致): cold = **30.15 s**・23/23 PASS (rc 0, load 0.30→0.66)。warm = **3.72 s**・23/23 PASS (rc 0, load 0.15)。
  - HEAD `6d6726bb` (`work/` 無しから cold・load 0.42): cold = **26.57 s** (RetDec lift 含む)・exit 0・23/23 PASS。出力 IR sha256 は §12/§13 と一致 (`patched_base_lf.ll` `c62d9316…8793`、`raw_base_lf.ll` `79ab30ca…0d20`)。前 HEAD `5e7e26fa` でも cold 27.28 s・23/23 PASS。
- 未達 (受入条件のうち未完): (1) 復元した `call` の引数 (rcx=host, edx=0x800010) の実行時 ABI は #228 (icall の BLK 経由) の界面に従う別工程で、本 pass は site の VA と制御辺のみ復元する。(2) e2e チェーン (`e2e.sh`) への組込みは未実施。
- 正とする pass の決定 (#1030 / PR #1227, PM 判断事項): 正は `l1_restore.py` (#1226)。PR #1227 の別 pass `serum2_l1.py` と `authstub/l1_restore.py` は撤回。理由: (1) 同じ `br` を書き換えるため両方適用は `二重適用` で失敗する。(2) 0x1800c2f05 の `call [[rcx]+0x30]` は `icall.py` が間接呼出し `call [reg+off]` に適用する規則と同じく `__icall_dispatch(site_va)` へ落とすのが本パイプラインの扱いで、撤回した pass が出す `@__vcall_notify` は定義が無くリンクできない。(3) 撤回した pass の実測 (census) は本 pass の値ではないため REPORT から外した。覆す場合は PM が決め、`__vcall_notify` の定義と #228 の ABI との整合を先に示す。
- 既存の子 issue への紐付け (2026-10-13 時点の状態): census 拡張 (受入 2 の IR 側指標) は #1029 [SR-13] で、PR #1205 (`Closes #1029`) により完了・closed (merge commit `9d1c632f`、本ブランチは取り込み済み)。復元 pass の前後表・ネガコンの正式化 (受入 2〜3 の残り) は #1030 [SR-14] (2026-10-13 時点 open。現在は CLOSED で、受入 2・3 は本 PR (#1009・§14f) で完了)、LF 規則の導出は #1213 [SR-11] (open、`1007-sr-11-authstub-binding`)、global 名の規則化は #1208 [SR-15] (open)。
- LF 束縛の詳細 (REPORT §14 旧版の LF5/LF6/LF7 節): `fp_bind.bind_load_slot_at(lines, fn, va, expect_slot, glob, tag)` で束縛。slot は IR 行 (`%stack_var_<slot>`) から読み、`expect_slot` (`'-72'`/`'-80'`/`'-152'`) と不一致なら `SystemExit` で失敗する (照合)。slot 値・global 名は literal のまま (導出は #1208 / #1213)。LF4 の定数は `verify_lf4_const.py` で PE 上の定数と IR の値の一致を確認 (`LF4 const OK`, 11.00001・bits 4622382073171892366)。機械語の slot 参照は IR の slot 名と一致しない (例: 機械語 `[rbp-0x10]` ↔ IR `stack_var_-72`) ため、slot は IR 行を正とした。ネガコン: `negctl_slot.py` (rc 0 = 全条件一致。誤 slot 期待 `-80` → FAIL、誤 VA `0x1800c2c95` → FAIL)。

## 15. LF 束縛先 global の役割導出の詳細 (#1208 / SR-15)

- 方式: `authstub_irpass.derive_role(lines, fn, name, tag)` が、束縛 site の load 結果 (SSA 名) の**全使用行**を分類する。分類は 3 種のみ:
  - `tag_len`: `icmp eq i64 <v>, <即値>` (tag 文字列の長さ比較)
  - `dom`: `call i64 @function_…(i64 <v>, ptr getelementptr … @global_var_…)` の第 1 引数 (key 検索) または `inttoptr i64 <v> to ptr` (デリファレンス)
  - `dbl`: `@__asm_ucomisd…(i128 <v>, …)` の被演算子
  - `zero`: `@__asm_xorpd(<v>, <v>)` は 0 を作る idiom のため役割に数えない
  分類外の使用が 1 件でもある、または役割が 2 種以上、または使用 0 件なら `SystemExit` (fail-closed)。同じ LF の複数 site は全て同一役割でなければ失敗する。
- 役割 → global の対応は `ROLE_GLOBAL` (`dom`→`__authstub_doc_root`、`tag_len`→`__authstub_str_len0`、`dbl`→`__authstub_dbl_ret0`) の 3 行。`liftfix_report.json` の `roles` に導出結果を書き出す。
- 導出結果 (`work/liftfix_report.json`・HEAD `87cb462b` 実測):

| LF | 機械語 VA (site 数) | 導出した役割 | 束縛先 global | 根拠 (IR の使用) |
|---|---|---|---|---|
| LF1 | ctrl 0x1800c2c1f (1) | tag_len | `__authstub_str_len0` | `icmp eq i64 %36, 10` |
| LF2 | DSP `%3 = xor` (1) | dbl | `__authstub_dbl_ret0` | `__asm_ucomisd(%3, …)` (`xorpd` 1 件は zero として除外) |
| LF3 | DSP 0x18004fe46 (1) | dbl | `__authstub_dbl_ret0` | 比較前の ucomisd 被演算子 |
| LF4 | DSP 0x18004fe4c (1) | dbl | `__authstub_dbl_ret0` | `__asm_ucomisd__1(%3, …)` |
| LF5 | ctrl 0x1800c2c94, 0x1800c2ca4 (2) | dom | `__authstub_doc_root` | 第 1 引数 + `inttoptr` デリファレンス |
| LF6 | DSP 0x18004fbc6, 0x18004fbd6 (2) | dom | `__authstub_doc_root` | 同上 |
| LF7 | DSP 0x18004fb74 (1) | tag_len | `__authstub_str_len0` | `icmp eq i64 %28, 9` |

- 機械語 site の総数 9 (LF2 は `xor` 行なので VA ではなくパターン指定)。束縛行の数 (`LIFTFIX` タグ付き行): LF1 1 / LF2 1 / LF3 3 / LF4 6 / LF5 2 / LF6 2 / LF7 1。
- **出力不変**: 変更前後で `patched_base_lf.ll` / `raw_base_lf.ll` は `cmp` で完全一致 (sha256 `c62d9316…8793` / `79ab30ca…0d20`、REPORT §12-§14 と同じ)。
- **ネガコン (e2e)**: 役割→global 対応を故意に誤らせ (`tag_len`→`__authstub_doc_root`)、同じ harness をビルドして実行 → **12/23 PASS** (正しい対応は 23/23)。対応の誤りが harness で検出されることを確認。
- **ネガコン (導出単体)**: `negctl_role.py` — 正例 3 件 (tag_len / dom / dbl) → 一致。負例 3 件 (役割混在 / 未分類 1 件 / 使用 0 件) → 全て SystemExit。rc 0。
- **実測 (commit `87cb462b`・コード変更の最後の commit)**: `bash e2e.sh` cold (work 削除後) = **36.33 s** (real) → 23/23 PASS、load 0.19→0.55。warm = **5.52 s** → 23/23 PASS、load 0.08→0.15。素材: `plugins-serum2` の `Serum2_win64.vst3` sha256 `501e7bb3…5283` 19,236,864 B (展開後に一致確認)。baseline (変更前 HEAD `f7bebc7b`) は cold 36.27 s / 23/23 PASS / load 0.28→0.63 (同条件)。
- コード差分: `git diff f7bebc7b 87cb462b -- tools/targets/serum2/license/authstub` → `authstub_irpass.py` +109/-15 行 (役割導出), `negctl_role.py` 新規 64 行。他ファイル無変更。

- #1208 の受入条件 3 点は全て達成。範囲外の残り (起票なし・非ブロッカー): (1) `expect_slot` (-72/-80/-152) は照合用の literal のまま。slot 値そのものの導出は未実装。(2) 役割→global 対応 `ROLE_GLOBAL` は手書きの 3 行 (harness C が定義する名前に一致させるため)。
- 関連: #1213 [SR-11] (slot 照合の追加) は既に MERGED。

## 14c. faithful 経路への L1 適用・icall 界面確認・23/23 再測定 (#1265 / SR-17)

- 測定 commit: `a5ab78f2` (origin/main)。コード変更は無し (本節の追記のみ)。
- 素材: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` (19,236,864 B・sha256 `501e7bb3…5283` 一致)。
- faithful 経路の raw lift: `work/lift/authstub.drc.ll` (710,975 B・sha256 先頭 16 桁 `5ce6d287d370ef96`)。N2b は当てない (`authstub_irpass.py` を通さない)。
- L1 適用: `liftlib.passes.base.run_base` → `liftlib.passes.l1_restore.restore_l1` (`br_line` 8916、meta `[3049, 3050]`)。復元後 IR (`raw_base_l1.ll`) の sha256 先頭 16 桁 `f019ede0979ae1c7`。`llvm-as-18` で base 後の raw / restored の両方 rc 0。

### census (faithful 経路・前後)

| 指標 | raw (適用前) | restored (適用後) |
|---|---|---|
| machine: 直接 `call [reg+0x30]` sites | 1 | 1 |
| machine: `edx=0x800010` 即値ロード | 1 | 1 |
| machine: 入口 edge | 1 | 1 |
| IR: `insn.addr` 被覆 (site 範囲) | 0 | 2 |
| IR: 直接 call (site 範囲) | 0 | 1 |
| IR: `edx=0x800010` 即値 (site 範囲) | 0 | 0 |
| IR: 0x800010 即値 (ファイル全体) | 1 | 1 |
| IR: br/switch の入口 edge | 0 | 1 |
| IR: block `dec_label_pc_1800c2ef4` | 不在 | 存在 |

- raw 列は §13b・§14b の値と一致 (再現確認)。

### icall #228 界面の確認 (受入 4): 不一致 (未修正)

- 復元 call は `call void @__icall_dispatch(i64 0x1800c2f05)` のみで、BLK への前段 store を出さない。
- `tools/icall/rt/icall_rt.c` の `__icall_dispatch` は target を BLK+0x00、rcx を +0x08、rdx を +0x10 から読む。`icall_rewrite.py` の `st(...)` 規則も同じ BLK 配置。現状の復元 call は呼出し先も引数も渡さないため、意味として誤り (#1030 コメントと同じ結論)。
- 整合には `l1_restore` が BLK store (target=`[[rcx]+0x30]`・rcx=host・rdx=0x800010) を出す設計変更が要る。N2b との適用順 (#1228) と一体のため、本節では実装しない。

### 23/23 再測定 (受入 3)

- `bash tools/targets/serum2/license/authstub/e2e.sh` (`work/` 無し・cold・TMPDIR=`$RUNNER_TEMP`): rc 0・**23/23 PASS**・real **36 s**・load 0.56→0.73。
- 本 e2e は patched 経路 (N2b あり) で、L1 pass は組込まれていない。よって本値は不変確認であり、L1 適用後の 23/23 ではない。L1 を patched 経路に入れると #1228 の衝突 (`ef4` が到達不能) が起きるため、適用順規約は #1228 で決める。

### 未達 (Refs #1265)

- (a) icall 界面の整合 (BLK 前段 store): 未実装。子 issue #1497 (`[SR-22]`) に起票。
- (b) N2b との適用順規約の文書化・patched 経路への L1 組込み: #1228 (SR-16) の範囲。
- (c) 「faithful 経路」の定義と e2e 組込み先: リポジトリに定義が無い。本 run では raw lift + pass の census までを faithful 経路の測定とした。

## 14d. N2b と L1 の適用順規約の実測 (#1228 / SR-16)

- 判断の正本: REPORT §14d。本節は実測値のみ。
- 測定 commit: `cb3a89a6` (origin/main 取り込み後・本節の追記前、コード変更なし)。
- 素材: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` (19,236,864 B・sha256 `501e7bb3…5283` 一致)。`toolchain-retdec` (RetDec v5.0)・`toolchain-emsdk` 使用。
- raw lift: `work/lift/authstub.drc.ll` 711,017 B・sha256 先頭 16 桁 `05a6e15a8db8a92f`。§14c の値 (710,975 B・`5ce6d287…`) とは別 lift (RetDec cold 再生成による差。このため §14c の sha256 とは比較しない)。
- `patched_base.ll` sha256 先頭 16 桁 `1003435dfc805931`、`raw_base.ll` `e8a23ae3beb00f3c`。

### 到達性表 (`reach_l1.py`・0x1800c2b50)

| 入力 | d5f (0x1800c2d5f) | d6f (0x1800c2d6f) | ef4 (L1 復元先) | f08 |
|---|---|---|---|---|
| raw | REACHABLE | REACHABLE | absent | REACHABLE |
| raw + L1 | REACHABLE | REACHABLE | REACHABLE | REACHABLE |
| patched (N1/N2a/N2b/N3) | unreachable | unreachable | absent | REACHABLE |
| patched + L1 | unreachable | unreachable | unreachable | REACHABLE |

- 機構: N2b-2 (0x1800c2d59 の `br i1 %106` を f08 へ強制) で d5f への辺が消える。L1 の `br` (0x1800c2d69) は d5f の中にあるため、patched では復元 block も到達不能。
- ネガコン (受入 4): raw の L1 有無で ef4 が absent ↔ REACHABLE (pass が辺を戻すことの実測)。patched では L1 の有無で到達性が変わらない。よって「pass を外すと通知経路が patched から消える」は patched 経路では成立しない (通知経路は N2b により元から不達)。

### 23/23 (patched 経路・L1 無し)

- `bash e2e.sh` cold (`work/` 削除後・`TMPDIR=$RUNNER_TEMP`): rc 0・**23/23 PASS**・real **27.2 s** (RetDec lift 含む)・load 0.65→ (開始時 1 分平均 0.65)。
- 本 e2e は L1 を組み込まない。よって不変確認であり、L1 適用後の 23/23 ではない (faithful 経路への L1 組込みは #1265 で扱う)。

### 未達

- 受入 4 のうち「patched で pass を外すと通知経路が消える」は上記の理由で patched では成立しない。faithful (raw) 側のネガコンは上表で実測。
- icall #228 界面 (BLK 前段 store): 未実装。#1497 [SR-22]。
- faithful 経路への L1 組込みと適用順の e2e 反映: #1265 [SR-17]。

## 14e. L1 復元 call の BLK 前段 store (icall #228 界面の整合 / SR-22)

- 測定 commit: `fdef0aab` (`fix(liftlib): l1_restore の復元 call 前に BLK 前段 store を出す`)。コード変更は `tools/liftlib/liftlib/passes/l1_restore.py` のみ。
- 変更: `l1_call` の直前に BLK への store を 3 本追加 (icall_rewrite.py の `st(...)` と同じ配置・icall_rt.c の読み取り位置と一致):
  - `BLK+0x00` = target = `load [[host]+0x30]` (機械語 `mov rax,[rcx]; call [rax+0x30]`)
  - `BLK+0x08` = rcx = host
  - `BLK+0x10` = rdx = `0x800010` (機械語 `mov edx,0x800010`)
  - BLK 絶対アドレスは icall_rt.c の既定 `ICALL_BLK = 0x34308000`。引数 `blk` で差し替え可。
- 素材: `plugins-serum2` (Serum2_win64.vst3 19,236,864 B・sha256 先頭 `501e7bb3dd9cafe4`)。`$HOME/artifacts` の展開。
- 再現 (cold・`work/` 削除後・`TMPDIR=$RUNNER_TEMP`): `bash tools/targets/serum2/license/authstub/e2e.sh` rc 0・**23/23 PASS**・real **23.3 s**・load 0.35→0.58。raw lift sha256 先頭 `395732ca2eb5548a` (RetDec 再生成の差。§14c/§14d の `5ce6d287…`/`05a6e15a…` とは別 lift)。
- llvm-as-18 (cold lift 由来): raw_base / raw_l1 / raw_l1_nostore の全てで rc 0。raw_l1 の sha256 先頭 `57fd43ba1dd7fff8`。

### census (faithful 経路・cold lift 由来・`l1_census.py`)

| 指標 | raw_base (L1 無し) | raw_l1 (L1 + BLK store) | raw_l1_nostore (L1 のみ・store 外し) |
|---|---|---|---|
| machine: 直接 `call [reg+0x30]` sites | 1 | 1 | 1 |
| machine: `edx=0x800010` 即値ロード | 1 | 1 | 1 |
| IR: block `dec_label_pc_1800c2ef4` | 不在 | 存在 | 存在 |
| IR: `insn.addr` 被覆 (site 範囲) | 0 | 4 | 4 |
| IR: site 範囲の命令数 | 0 | 15 | 12 |
| IR: 直接 call (site 範囲) | 0 | 1 | 1 |
| IR: `edx=0x800010` 即値 (site 範囲) | 0 | **1** | **0** |
| IR: 0x800010 即値 (ファイル全体) | 1 | 2 | 1 |
| IR: br/switch の入口 edge | 0 | 1 | 1 |

### ネガコン (受入 2・3)

- store を外した版 (`raw_l1_nostore`) では site 範囲の `edx=0x800010` 即値が 0 件になり、復元 call の前段 store (rdx=0x800010) が消える。raw_l1 では 1 件 (BLK+0x10 への store)。BLK+0x00 / +0x08 も store 版でのみ生成される。
- 界面の不一致 (IR 上): store 無しの復元 call は `__icall_dispatch` が読む BLK+0x00 (target)・+0x08 (rcx)・+0x10 (rdx) を一切書かない。store 版はこの 3 箇所を書く。実行時 (wasm) での不一致の再現は未実測。

### 未達

- 実行時の検証 (wasm で BLK の値が call 先に渡ることの実測) は未実施。本節は IR の界面一致までを確認した。
- L1 を e2e の patched 経路に組込むこと: #1265 [SR-17] (適用順規約は #1265 本文の PM 判断のとおり patched は N2b 優先)。
