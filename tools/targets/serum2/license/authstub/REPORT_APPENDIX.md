> **正本**: `tools/targets/serum2/license/authstub/REPORT.md` §13。本書は REPORT の 250 行上限のため、旧 §13 の全文を無変更で分割移動した付録。

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

### 13.2 L1 復元 pass (`serum2_l1.py`, #1030 / PR #1227) の実測 (REPORT.md §13.2 から分割移動)

- 復元の対象と処置: null 枝 (`br i1 %110`) の skip 先を `dec_label_pc_1800c2f08` から `dec_label_pc_1800c2ef4` へ戻し、機械語 `0x1800c2ef4–f05` を IR に書き起こす。直接 vtable 呼出しは `@__vcall_notify(vt, 48, this, 0x800010)` の 1 件に畳む。
- `%arg1` = `this` (rsi) の根拠: `authstub_irpass.py` の demo bit 検出 `add i64 %arg1, 141202` (= 0x22792) と、§1 N2a の機械語 `mov [rsi+0x22792],al` が同じ bit を指す。よって `%arg1` が rsi に対応する (`[rsi+0x10]` は `add i64 %arg1, 16`)。
- ポインタ型: opaque pointer 形式 (`inttoptr i64 %x to ptr` / `load i64, ptr %p, align 8`) に統一 (`fp_bind.py` / `base.py` と同形)。
- `llvm-as-18`: 挿入ブロックを含む単体モジュールで exit 0 (pass 出力の完全な `.ll` は本 run で raw lift が無く未実施)。
- 実測 (HEAD `531acc80`, raw lift `authstub.drc.ll`) — **未再現の申告値**。本 run では raw lift と `plugins-serum2` が `$ARTIFACTS_DIR` (fl-win64 のみ) に無く、再実行していない。

  | 指標 | 復元前 | 復元後 | ネガコン |
  |---|---|---|---|
  | 直接 call (`@__vcall_notify`) | 0 | 1 | 0 |
  | edx=0x800010 即値 | 0 | 1 | 0 |
  | 入口 edge (`label %dec_label_pc_1800c2ef4`) | 0 | 1 | 0 |
  | insn.addr 被覆 (0x1800c2ef4–f05) | 0 | 9 | 0 |
  | 機械語側 (`l1_census.py`) | sites=1 / edx=1 / into=1 | | |

  - `dec_label_pc_1800c2ef4` の到達性: 復元前 False / 復元後 True / ネガコン False。
  - raw lift の sha256: 未記録 (本 run で取得できず)。再現時に記録する。
  - 再現コマンド (`authstub/` で実行): `python3 l1_restore.py work/lift/authstub.drc.ll work/lift/authstub.l1.ll` (適用・census)。ネガコン: `python3 l1_restore.py work/lift/authstub.drc.ll work/lift/authstub.negctl.ll --negctl`。raw lift の sha256 は再現時に本節へ記録する。
- 未達: patched 経路では効かない (N2b-2 が `d59→f08` を強制し、`d5f` が到達不能のまま)。N2b (通知抑止) と L1 (通知復元) は仕様衝突で、採否は PM 判断。e2e.sh 未組込み・23/23 未再測定。
