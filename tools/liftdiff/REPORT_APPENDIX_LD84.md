# liftdiff REPORT 付録: LD-84 (#2193) 残り 5 関数の native 命令と wasm block 列の対応

親 #1907 (LD-68)。前提は `REPORT_APPENDIX_LD68.md` §3・§4 (IR 依存の対応は未検証だった)。
既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 に import 応答の契約差の類型は無い。D12 (比較範囲) とは別。新類型の行案は §4 末尾)。

## 結論

- 受入条件 1 (5 関数 × vm0/u16 の対応を示す): **達成** (対応表は §3、1 入口ごとの対応は `results/ld84/block_map_*.tsv`)。
  - `1ab1d0`・`1ab258` は vm0/u16 とも wasm 4 入口と native 4 入口が**完全一致**。
  - `1c621c`・`1c682c`・`1c69cc` と `1c5e84` (参照) は、最初の 4〜32 入口までは一致し、**最初の不一致はすべて `1c0b71` の HeapFree 呼出しの戻り値**で起きた (§4)。
- 不一致の原因は block 構造ではなく **import 応答の契約差**である。native 参照の HeapFree は常に 1 を返し、wasm の HeapFree (`tools/shim/src/heap.c`) は割当て外のポインタに FALSE を返す (u16 では範囲外読みで trap)。
- **LD-57 付録の訂正**: `REPORT_APPENDIX_LD57.md` の「vm0 は `rcx=0` で `1c0b6f` の je が早期 return」は、`results/ld57/insn_1801c5e84_vm0.txt` の `1c0b6f` の行 (rcx=`1720f3000`) と合わない。je は vm0 でも not taken で、vm0 も HeapFree 経路に入る (§4)。LD-57 本文は未修正 (§7)。
- **LD-68 §2 の訂正**: `1ab1d0`・`1ab258` の計装 blk 件数「0 件」は記録の誤り。`trim_case` が equal の case の raw を捨てていたため 0 に見えた。`liftdiff.py run -v` で取り直すと 4 件 (§2)。
- 受入条件 2 (測定 commit と `git diff`): §5。

## 1. 測定条件

- 測定 commit: `38ae268d` (`feat(liftdiff): native CreateFruityInstance reference spike (#2718)`。liftdiff・ott rt・m6/m8/m9/shim のコード差分の最終 commit)。`git diff` の結果は §5。
- 作業ツリー: `ws-2193` (branch `2193-ld84-block-insn-map`、base `origin/main` の `26f90ada`)。
- 素材 (本 run で確認): `work-m6-ott` → `tools/{m6,m8,m9,m10,ott}/work/` (`ott.ll` 957,145 B)、`work-liftdiff` → `tools/liftdiff/work/` (`ott_old` 既定 build 入り)、`analysis-ott-binaries` → `$ANALYSIS_DIR/plugins/ott/binaries/` (`[ANALYSIS-DIR]` 配下。`OTT_vst2_win64.dll`)、`toolchain-emsdk` → `[EMSDK]` (既存展開を使用)。`fl-win64`・`plugins-ott`・`work-liftlib` は本件の実行に使っていない (ott target の PE は analysis の DLL)。
- 環境変数: `ANALYSIS_DIR` (`[ANALYSIS-DIR]`) と `PLUGINS_DIR=$ANALYSIS_DIR/plugins`。
- 実行コマンド (n=1。所要は参考値で、結論には使わない):
  - 計装版 (build あり): `python3 liftdiff.py run targets/ott_old_blk.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --notrace -v --json work/ld84/blk_all.json` (build+run 11.26 s)
  - 既定版 (`--nobuild`): 同上で `targets/ott_old.json`・`work/ld84/def_all.json` (5.78 s)
  - 比較: `python3 results/ld67/compare_blk.py work/ld84/def_all.json work/ld84/blk_all.json`
  - 対応表: `python3 results/ld84/ld84_block_map.py` (出力は `work/ld84/map_summary.txt`、TSV は `results/ld84/`)
- load average: 測定終了時 `0.01 0.28 0.30` (`uptime` 19:30 UTC)。並列数 1。

## 2. 既定版と計装版の比較 (12 case・`-v` で raw 取得)

`compare_blk.py` の出力: `cases=12 diff=0` (outcome・diffs・wasm_status・rax/x0 が全 case 一致)。

| 関数 | pattern | outcome (既定 = 計装) | 計装 blk 件数 |
|---|---|---|---|
| 1ab1d0 | vm0 / u16 | equal / equal | 4 / 4 |
| 1ab258 | vm0 / u16 | equal / equal | 4 / 4 |
| 1c5e84 | vm0 / u16 | diff / wasm_trap | 27 / 4 |
| 1c621c | vm0 / u16 | diff / wasm_trap | 287 / 6 |
| 1c682c | vm0 / u16 | diff / diff | 42 / 43 |
| 1c69cc | vm0 / u16 | diff / wasm_trap | 304 / 10 |

LD-64 §4 の「計装版は vm0 の戻り値を変える」は、この 12 case では再現しなかった (戻り値は既定版と一致)。

## 3. 対応表 (native 入口 ↔ wasm 入口)

native 入口 = 実行トレース (`results/ld57/insn_<fn>_<pat>.txt`) の命令のうち、VA が IR label (`dec_label_pc_<VA>:`、`tools/ott/work/ott.ll` に 1,882 個) と一致したもの。wasm 入口 = `raw.wasm.blk`。両者を先頭から比較する。

| 関数 | pattern | wasm 入口数 | native 入口数 | 共通接頭辞 | 最初の不一致 (k: wasm / native) | 原因 |
|---|---|---|---|---|---|---|
| 1ab1d0 | vm0 / u16 | 4 / 4 | 4 / 4 | 4 / 4 | 完全一致 | — |
| 1ab258 | vm0 / u16 | 4 / 4 | 4 / 4 | 4 / 4 | 完全一致 | — |
| 1c5e84 (参照) | vm0 | 27 | 18 | 4 | k=4: `1c0b8c` / `1c0ba8` | §4 |
| 1c5e84 (参照) | u16 | 4 | 22 | 4 | wasm trap (k=4 で終端) | §4 |
| 1c621c | vm0 | 287 | 278 | 6 | k=6: `1c0b8c` / `1c0ba8` | §4 |
| 1c621c | u16 | 6 | 283 | 6 | wasm trap (k=6 で終端) | §4 |
| 1c682c | vm0 | 42 | 33 | 32 | k=32: `1c0b8c` / `1c0ba8` | §4 |
| 1c682c | u16 | 43 | 34 | 33 | k=33: `1c0b8c` / `1c0ba8` | §4 |
| 1c69cc | vm0 | 304 | 286 | 10 | k=10: `1c0b8c` / `1c0ba8` | §4 |
| 1c69cc | u16 | 10 | 291 | 10 | wasm trap (k=10 で終端) | §4 |

- 全ての trap・不一致の case で、**最初の `1c0b71` (HeapFree 呼出しの block) の入口までは block 列が一致し、その次の入口で分岐する** (最初の `1c0b71` の k は vm0 で 1c5e84=3・1c621c=5・1c682c=31・1c69cc=9、u16 で 1c69cc=9)。1c5e84 vm0 の k=0〜3 は `1c5e84 → 1c5eb8 → 1c0b6c → 1c0b71`。
- 1c5e84 vm0 の 1 入口対応 (`results/ld84/block_map_1801c5e84_vm0.tsv` の抜粋):

| k | wasm | native | native の実行命令 (先頭→末尾) | 末尾命令 |
|---|---|---|---|---|
| 0 | 1c5e84 | 1c5e84 | 14 命令 (`1c5e84`〜`1c5eb6`) | `je 0x1801c5ecc` |
| 1 | 1c5eb8 | 1c5eb8 | 2 命令 (`1c5eb8`〜`1c5ebb`) | `call 0x1801c0b6c` |
| 2 | 1c0b6c | 1c0b6c | 2 命令 (`test rcx,rcx`; `je`) | `je 0x1801c0ba8` (not taken) |
| 3 | 1c0b71 | 1c0b71 | 8 命令 (`push rbx`〜`jne`、途中で `call [HeapFree]` 1c0b82) | `jne 0x1801c0ba3` (taken) |
| 4 | 1c0b8c | 1c0ba8 | 1 命令 (`ret`) | `ret` |

## 4. 最初の不一致の原因: HeapFree の import 応答

- IR (`tools/ott/work/ott.ll`、`function_1801c0b6c`): block `1c0b71` は `%4 = call i1 @HeapFree(ptr %2, i32 0, ptr %3)` の後、`br i1 %7, label %1c0ba8, label %1c0b8c` で分岐する。
- native (`insn_1801c5e84_vm0.txt`): `1c0b82` で `call [IAT]` (HeapFree)、直後の行 `1c0b88` では rax=1。`1c0b8a` の `jne 0x1801c0ba3` が成立し、`ret` (1c0ba8) へ進む。native の HeapFree 呼出しの引数は `hHeap=0, flags=0, p=0x1720f3000`、戻り値 1 (`raw.native.calls` と一致)。
- wasm: 分岐の向きから HeapFree の戻り値は FALSE と推定する (wasm 側は HeapFree を import stub でなく shim の関数として呼ぶため、呼出しログ `raw.wasm.calls` には出ず、戻り値は直接観測していない)。その結果 `1c0b8c` (fall-through) → `function_1801bafb0` → `GetLastError` → `function_1801baef8` (未定義 import、戻り値 0) と進む。
- 応答の出所:
  - native 参照: `tools/liftdiff/rt/ld_core.h:430` が HeapFree に**引数を見ず 1 を返す**。
  - wasm: `targets/ott_old.json` の `extra_sources` に `tools/shim/src/heap.c` があり、HeapFree は `block_ok(p)` を検査する (`heap.c:136`)。割当てのない p は FALSE、範囲外の p は `block_ok` 内の読取りで OOB trap。trap の連鎖 `block_ok < HeapFree < function_1801c0b6c` で確認した。
  - `ld_core.h` の冒頭は「IAT import スタブの応答モデル (native/wasm で同じ応答を返す)」だが、wasm 側は HeapFree だけ shim 実装に置き換わっており、この意図と食い違う。
- u16 は p が UTF-16 文字列の値 (`0x1400000001`・`0x530020004c0046` 等) で heap の block ではない。wasm の `block_ok` が範囲外を読んで trap し、native 参照は 1 を返して進む。

新類型の行案 (`docs/DEFECTS.md` は PM 判断で編集するため、ここに残す):

| D24 | ours (harness: import 応答) | **新規** (LD-84 / #2193 で発見) | native 参照 stub の HeapFree (`ld_core.h:430`: 引数を見ず 1) と wasm の shim (`heap.c:136`: `block_ok` 検査) が別実装で、戻り値の分岐が逸れる | import 応答を native と wasm で別々に持つ (wasm は extra_sources で上書き) | 両側で同じ応答表を使う (子 issue) |

ネガティブコントロール: 一致する case (1801ab1d0 vm0・wasm 4 入口) で `wasm[1]` を `wasm[0]` に置換すると、共通接頭辞は 4 から **1** に落ちる (`NEG-CONTROL ... prefix=1`)。対応判定は、1 入口の差を検出できる。

## 5. 測定 commit と差分

- 測定 commit: `38ae268d`。`git merge-base --is-ancestor 38ae268d HEAD` で HEAD の祖先であることを確認。
- `git diff 38ae268d HEAD -- tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt tools/liftdiff/ldlib tools/liftdiff/results/ld67/compare_blk.py tools/ott/rt tools/m6 tools/m8 tools/m9 tools/shim` の出力は **0 件** (差分なし)。よって計測コードに対する再測定は不要で、上の数値は HEAD の計測コードで得た値に等しい。

## 6. 検証範囲・範囲外

- 範囲内: 6 関数 (1c5e84 は参照) × vm0/u16 の計装版 wasm trace と、既存の native 実行トレース (`results/ld57/`)。native トレースは本 run で再取得していない (ld57 の記録を使用)。ただし `raw.native.calls` の HeapFree 引数 (`p=0x1720f3000`) がトレースの `r8` と一致し、記録と今回の実行の入力が一致することを確認した。
- 範囲外: 命令単位の wasm trace (IR に元の VA が無い。#2192 / LD-83)。
- 非 label への切替 (anomaly): 各 case の帰属で「call/ret 以外の命令の後に、IR label でない VA へ切り替わった」箇所は、`1ab1d0`・`1ab258` で各 1 (`jmp 0x1801ab20a`・`jmp 0x1801ab295` の飛び先)、`1c5e84` vm0 で 1・u16 で 5、`1c621c` で 1・6、`1c682c` で 1・1、`1c69cc` で 2・7。内訳: 飛び先 `1c0ba3` (`jne 0x1801c0ba3` の分岐。1c5e84・1c621c・1c682c・1c69cc の vm0/u16 計 8 case で発生) と、`jmp` の飛び先 `1ab20a`・`1ab295` (`1ab1d0`・`1ab258` で発生)。`1c0ba3`〜`1c0ba7` は `add rsp`・`pop rbx` で、IR の label `1c0ba8` (`ret` だけの block) へ向かう経路上にある。IR 側に対応する命令は見当たらない (推定)。label 一致法の入口定義は影響を受けない。
- 命令の mnemonic は PE の `.text` を capstone で逆アセンブルして付与した (`ld84_block_map.py`)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HeapFree 応答の契約差 (`ld_core.h:430` の固定 1 と `tools/shim/src/heap.c` の検査) | 1c5e84・1c621c・1c682c・1c69cc の分岐差、u16 の wasm trap。これより後の block の対応は未検証 | 解消 (#3049 後の再測定は `REPORT_APPENDIX_LD133.md`。block 列は全件一致)。残る outcome 差は同付録 §4 |
| 命令単位の wasm trace | native `1c0b6f`・`1c0b82` の wasm 側の位置を命令単位で示せない (LD-68 §5 の残り) | #2192 (LD-83) |
| LD-57 付録の「vm0 は rcx=0 で早期 return」 | 誤記 (本付録の結論で訂正)。LD-57 本文は未修正 | 文言修正のみのため子は起票せず、本 PR の付録に訂正を残す |
| 実機 Windows の HeapFree 戻り値 (割当て外ポインタ) | 応答モデルを決める根拠が未検証 | #2821 (LD-133) の受入で、根拠を示すか未検証として残す |
