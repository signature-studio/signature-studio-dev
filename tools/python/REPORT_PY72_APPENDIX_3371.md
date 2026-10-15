# REPORT_PY72 の付録 (#3371 / PY-190): slot 35 (VMT+0x118) の仮想呼出しの受け手

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3267 (PY-177)。前段: `REPORT_PY72_APPENDIX_3267.md` (PR #3378 で merge 済み)。

## 結論 (部分達成・受入 2・3 は未確定)

- `call qword ptr [reg+0x118]` (slot 35 の仮想呼出し) は `.text` 全体で **151 箇所** (再測定で一致)。
- うち、その箇所を含む関数に chan の VMT・クラス参照スロットが直接現れるのは **2 箇所のみ**:
  - `0xf48290` (関数 `0xf46490`): 受け手 `rbx = [rbp+0x9e8]`。同関数は `0xf48115` で `[rax+0x4490]` のオブジェクトに対し `0x40fe90` (型判定) を `[0xf48115 の rdx = [0xfe2c30]]` で呼ぶ。ただし slot 35 を呼ぶ受け手は、直前に `0x10041f0` の戻り値として作られたオブジェクト。判定対象と受け手が同一かは未確認。
  - `0x1002084` (関数 `0x1001ef0`): 受け手 `rsi = [rbp+0x30]->vptr`。直前の判定はなく、`this` が chan かは未確定。`0x1001ef0` の呼出し元は 4 件 (`0xff4c17`・`0x100198a`・`0x1190858`・`0x1190e4f`)。`0x1190e4f` は、前段 #3267 で TPreviewChannel の生成・格納を確認した関数 `0x1190d20` の内側の呼出し (`0x1190e20` 付近のループ内)。
- 残り **149 箇所**: 含む関数に chan の VMT・スロット参照が無い。受け手の型は、この解析では決められない (呼出し元をたどる解析は未実施)。
- `0x40fe90` の意味: VMT 値 (`[0xfe2c30]` など) を第 2 引数に取り、第 1 引数の `[rcx]` (オブジェクトの vptr) から `[vmt-0x78]` (親クラス) をたどり、その VMT と一致するかを返す **is-a 判定** (派生を含む)。前段の「型判定と推定」は、この読みで確定した。
- 受入 3 (一覧 A `0x15e2218`・B `0x15e0128` の容器 Q への要素追加箇所と要素型 T): 未着手。`pe_xref.py` で A の RIP 参照は多数 (`load` のみの列挙を確認したが、Q への `add` の所有者は未分類)。

## 測定

- 測定 commit: `b40721add` (`pe_slot35_sites.py` のコードを変えた最後の commit。素材パスの文言修正)。
- 測定 HEAD: `b40721add`。`git diff b40721add HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本付録の commit は REPORT だけを変える)。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-3371 --wildcards '*block00031_PE.bin'` (2.9 秒。`extracted/block00031_PE.bin`。repo 外)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-3371 python3 analysis/flapi/pe_slot35_sites.py` を同一 HEAD で連続 3 回。終了コード 3 回とも 0。出力は 3 回ともバイト単位で同一 (md5 `7d1816a0a5a7f324cef8a441d450d400`)。

| 回 | 所要 | load (1 分値・開始時) |
|---|---|---|
| 1 | 11.92 s | 0.13 |
| 2 | 17.05 s | 0.68 |
| 3 | 17.01 s | 0.68 |

- 所要は 11.9 秒と 17.0 秒の 2 水準に分かれた。load は 0.13〜0.68 で、負荷では説明できない。原因は未確認。秒数は性能の主張に使わない。
- 参考: 前段 (`dcb38d210`) の同スクリプトの 3 回は 11.6〜11.8 秒 (load 0.17〜0.45)。`pe_vmt_probe.py 0xfe2cf8 0xfe2e10 --disp 0x118` (前段の再現) は 13.2 秒 (load 0.45)。
- 再現: TPublicChannel の VMT (`0xfe2cf8`) で `pe_vmt_probe.py` を実行し、slot 35 `0xffe290`・仮想呼出し 151 件・`0x40fe90` の is-a 判定を確認 (rc 0)。

## 解析の範囲と限界

- 検証した: 151 箇所の列挙、各箇所を含む関数 (`.pdata`) での chan の VMT・スロット参照の有無。2 箇所の周辺逆アセ (`0xf46490`・`0x1001ef0`)、`0x40fe90`・`0x10041f0`・`0x1003be0`・`0xffe290` の読解。
- 検証しなかった: 受け手オブジェクトの生成元 (`0x10041f0` の戻り値) の型、`0x1001ef0` の `this` の由来の全経路、149 箇所の受け手の型。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 151 箇所のうち 149 箇所の受け手の型 (含む関数に chan 参照が無い) | 受入 2 (`0xfe9090` が chan に呼ばれるか) | #3371 |
| `0xf48290` の受け手が chan か (判定対象と生成オブジェクトの関係) | 受入 2 | #3371 |
| `0x1001ef0` の `this` の由来 (呼出し元 4 件) | 受入 2 | #3371 |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 |

## 追補 (2026-10-15 run・受入 2 の後半を確定)

- `0xfe9090` (reset) の直接 `call rel32` (E8) 元は **2 件のみ**: `0xffe29b` (関数 `0xffe290`)・`0x1001b7b` (関数 `0x1001b70`)。`.text` 全体の `E8` 走査で確認。`jmp rel32` (E9) による `0xfe9090` への直接ジャンプは 0 件。
- その 2 関数は、それぞれ TPublicChannel (VMT `0xfe2cf8`) の slot 35 (スロット `0xfe2e10`) と TPreviewChannel (VMT `0xfe2fc8`) の slot 35 (スロット `0xfe30e0`) に、VMT 値のみで格納されている。`0xfe2e10` / `0xfe30e0` の格納は各 VMT の slot 35 の 1 箇所だけ。
- 上記 2 関数を経由して chan に届く経路は、slot 35 の仮想呼出し (151 箇所) の受け手が chan の場合に限られる。受け手の型は未確定。
- **未検証**: `0xfe9090` は `.text` 内の関数ポインタ表 (先頭 VA `0xfe2a90`) の slot 0 に絶対アドレスで格納されている。この表を経由する間接呼出しは本付録では検査していない。よって「`0xfe9090` が chan に呼ばれるか」の経路は確定していない。
- `pe_slot35_sites.py` に、`0xfe9090` の直接 call 元の列挙を追加した (受入 2 の確定に使う)。

### 測定 (追補)

- 測定 commit: `a53ed0561` (本 PR で `tools/python/analysis/flapi/pe_slot35_sites.py` を変えた最後の commit)。
- 測定 commit から本付録の commit までの差分: `git diff a53ed0561 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行。`tools/python` 全体では本付録 (REPORT) の変更だけが差分になる (`git diff --stat a53ed0561 HEAD -- tools/python`)。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-3371 --wildcards '*block00031_PE.bin'` (2.27 s)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-3371 python3 analysis/flapi/pe_slot35_sites.py` を同一ワークツリーで 3 回。終了コード 3 回とも 0。出力は `/usr/bin/time` の時間行を除いてバイト単位で同一。

| 回 | 所要 (wall) | load (1 分値) |
|---|---|---|
| 1 | 7.15 s | 0.66 |
| 2 | 7.83 s | 0.36 |
| 3 | 8.09 s | 0.15 |

- 前回付録の 11.9〜17.0 s とは水準が異なる。原因は未確認。秒数は性能の主張に使わない。

### 未解決 (追補後)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 151 箇所のうち 149 箇所の受け手の型 | 受入 2 (N=2 の適用元) | #3371 |
| `0xf48290` の受け手が chan か | 受入 2 | #3371 |
| `0x1001ef0` の `this` の由来 (呼出し元 4 件) | 受入 2 | #3371 |
| `0xfe9090` を参照する関数ポインタ表 (先頭 VA `0xfe2a90`・19 エントリ) 経由の間接呼出し | 受入 2 (`0xfe9090` が chan に呼ばれるかの経路) | #3371 |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 |

## 追補 2 (2026-10-15 run・受入 2 の受け手の出どころを分類)

- 補助 probe `analysis/flapi/pe_slot35_recv_src.py` を追加した。151 箇所の受け手レジスタを、呼出し箇所より前の同一関数内で逆向きにたどり、出どころの連鎖を出す (`rip@<大域>`・`stack`・`call`・`deref<-…`・`reg<-…`)。型は決めない。
- 結果 (151 箇所の連鎖の形): `rip@0x15e0c40` を起点とする連鎖が 54 件 (行に含まれる数)。`stack` 起点は 41 件 (`stack` 直 5・`deref<-stack` 26・`deref<-deref<-stack` 10)。`call` 起点は 4 件。`none` (窓内に定義なし) で終わる連鎖は残りのほとんど。
- 大域 `0x15e0c40` (`.data` の初期値 `0x16babe8`・RIP 相対の参照 308 箇所) は、RIP 相対の `mov` による store が **0 件**。受け手の型は、この大域を初期化する経路 (`lea` での間接アドレス計算など) を追わないと決まらない。
- 大域 `0x15e4790` (参照 2422 箇所)・`0x15e0ff8` (1079)・`0x15e2218` (一覧 A・1563)・`0x15e0128` (一覧 B・181) も store 0 件。一覧 A・B の要素追加箇所 (受入 3) は、この 2 大域の参照の中から `add` 相当を分類する必要がある。
- 大域 `0x16bcae0` の store は 2 件 (`0x11c3817`・`0x11c7f25`)。`0x16bcae8` の store は 0 件 (`.data` 初期値は文字列データ `"\nMemo..."` 相当)。前段 #3267 で TPreviewChannel 生成の格納先として見た `0x16bcae8` は、この解析の受け手の起点とは関係しない。

### 測定 (追補 2)

- 測定 commit: `a53ed0561` (`pe_slot35_sites.py` の最後の変更)。補助 probe は本付録と同じ PR で追加 (解析補助のみ・既存の測定スクリプトは変えていない)。
- 素材: `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-3371b --wildcards '*block00031_PE.bin'` (2.93 s)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-3371b python3 analysis/flapi/pe_slot35_sites.py` (12.07 s・rc 0・151 箇所・`0xfe9090` の直接 call 元は `0xffe29b`・`0x1001b7b` の 2 件で前回と一致)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-3371b python3 analysis/flapi/pe_slot35_recv_src.py` (11.41 s・rc 0)。

### 未解決 (追補 2 後)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 151 箇所のうち受け手の型 (出どころは分類済み・大域 `0x15e0c40` の初期化経路が未確定) | 受入 2 | #3371 |
| 大域 `0x15e0c40`・`0x15e4790`・`0x15e0ff8` の初期化・格納経路 (RIP 相対の store は 0 件) | 受入 2・3 | #3371 |
| `0xf48290` の受け手が chan か | 受入 2 | #3371 |
| `0x1001ef0` の `this` の由来 (呼出し元 4 件) | 受入 2 | #3371 |
| `0xfe9090` を参照する関数ポインタ表経由の間接呼出し | 受入 2 | #3371 |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 |
