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
- 既存の子 issue への紐付け (2026-10-13 時点の状態): census 拡張 (受入 2 の IR 側指標) は #1029 [SR-13] で、PR #1205 (`Closes #1029`) により完了・closed (merge commit `9d1c632f`、本ブランチは取り込み済み)。復元 pass の前後表・ネガコンの正式化 (受入 2〜3 の残り) は #1030 [SR-14] (open)、LF 規則の導出は #1213 [SR-11] (open、`1007-sr-11-authstub-binding`)、global 名の規則化は #1208 [SR-15] (open)。
- LF 束縛の詳細 (REPORT §14 旧版の LF5/LF6/LF7 節): `fp_bind.bind_load_slot_at(lines, fn, va, expect_slot, glob, tag)` で束縛。slot は IR 行 (`%stack_var_<slot>`) から読み、`expect_slot` (`'-72'`/`'-80'`/`'-152'`) と不一致なら `SystemExit` で失敗する (照合)。slot 値・global 名は literal のまま (導出は #1208 / #1213)。LF4 の定数は `verify_lf4_const.py` で PE 上の定数と IR の値の一致を確認 (`LF4 const OK`, 11.00001・bits 4622382073171892366)。機械語の slot 参照は IR の slot 名と一致しない (例: 機械語 `[rbp-0x10]` ↔ IR `stack_var_-72`) ため、slot は IR 行を正とした。ネガコン: `negctl_slot.py` (rc 0 = 全条件一致。誤 slot 期待 `-80` → FAIL、誤 VA `0x1800c2c95` → FAIL)。
