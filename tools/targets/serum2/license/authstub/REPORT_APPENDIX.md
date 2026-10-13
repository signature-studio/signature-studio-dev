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

`python3 tools/targets/serum2/license/authstub/l1_census.py <PE> <raw.ll>` が出力するのは次の 4 指標のみ:
機械語側の直接 call site 数 (`sites`)・`edx=0x800010` 即値ロード数 (`edx_const`)・site への入口 edge 数 (`into`)、
および raw IR 側の `insn.addr` 被覆数とブロック `dec_label_pc_1800c2ef4` の有無。
IR 側の「直接 call」「`edx=0x800010`」「入口 edge」の件数は**スクリプトの出力に含まれない**。

| 指標 | 機械語 (スクリプト出力) | raw IR (スクリプト出力) | raw IR (手確認・スクリプト外) |
|---|---|---|---|
| 直接 `call [reg+0x30]` site (0x1800c2ef4–f05) | `sites` = 1 | — | 0 件 (9872–9900 行の `call` は `@function_180034560` の 1 件のみ。`add ..., 48` は 1461・2178・2649 行の 3 件で、いずれも本 site の範囲外) |
| `edx=0x800010` 即値ロード | `edx_const` = 1 | — | `i32 8388608` / `8388624` の即値は 0x800010 を含む `or` が 9878 行の 1 件のみ (rax≠0 の deferred 側) |
| 0x1800c2ef4 への入口 edge | `into` = 1 (`je` @0x1800c2d69) | — | `dec_label_pc_1800c2ef4` の参照 0 件 (grep `dec_label_pc_1800c2ef4`) |
| `insn.addr` が site 範囲を被覆 | — | 0 件 (`covered`) | — |
| ブロック `dec_label_pc_1800c2ef4` | — | 不在 (`has_block`) | — |

- 手確認の列は raw `.ll` を grep / sed で読んだ事実のみ。スクリプトの出力には含まれない (census 拡張は子 issue #1029)。
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

- 事実の範囲: 上記は raw lift 1 本での実測。復元 pass は未実装 (受入条件 2・3 は未達、子 issue に分割)。
- 未測定 (断定しない): 0x1800c2d59 の `je` は `[rsi+0x22792]` の bit で分岐し、その bit を 1 にする store は 0x1800c2d42 の 1 箇所のみ。N2a でこの store を 0 に置換した後の到達性は、本 census では測っていない。e2e の 23/23 との関係も未確認。
