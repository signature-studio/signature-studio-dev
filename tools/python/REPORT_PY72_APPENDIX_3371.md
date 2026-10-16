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
- 結果 (151 箇所の連鎖の形): `rip@0x15e0c40` を起点とする連鎖が 54 件 (行に含まれる数)。`stack` 起点は 42 件 (`stack` 直 5・`deref<-stack` 26・`deref<-deref<-stack` 10・`deref<-deref<-deref<-stack` 1)。`call` 起点は 4 件 (`deref<-call` 3・`reg<-call` 1)。`none` (窓内に定義なし) で終わる連鎖は 42 件 (`deref<-none` 18・`reg<-none` 12・`deref<-reg<-none` 8・`deref<-deref<-none` 2・`deref<-deref<-reg<-none` 2)。
- 制限: `trace()` が定義として拾う命令は `mov/lea/movzx/movsxd/movsx/xchg` だけ。`pop`・`xor`・`add`・`sub`・32bit 書込み (`mov ebx, …`) は定義として扱わない。そのため `none` と分類された連鎖は「窓内に上記の命令での定義が無い」ことしか言わず、実際の出どころが無いとは限らない。
- 大域 `0x15e0c40` (`.data` の初期値 `0x16babe8`・RIP 相対の参照 308 箇所) は、RIP 相対の `mov` による store が **0 件**。受け手の型は、この大域を初期化する経路 (`lea` での間接アドレス計算など) を追わないと決まらない。
- 大域 `0x15e4790` (参照 2422 箇所)・`0x15e0ff8` (1077)・`0x15e2218` (一覧 A・1563)・`0x15e0128` (一覧 B・181) も store 0 件。一覧 A・B の要素追加箇所 (受入 3) は、この 2 大域の参照の中から `add` 相当を分類する必要がある。
- 大域 `0x16bcae0` の store は 2 件 (`0x11c3817`・`0x11c7f25`)。`0x16bcae8` の store は 0 件 (`.data` 初期値は文字列データ `"\nMemo..."` 相当)。前段 #3267 で TPreviewChannel 生成の格納先として見た `0x16bcae8` は、この解析の受け手の起点とは関係しない。

### 測定 (追補 2)

- 測定 commit (`pe_slot35_sites.py`): `a53ed0561` (そのスクリプトの最後の変更)。測定 commit (`pe_slot35_recv_src.py`・補助 probe): `a695c41ef` (probe を追加した commit)。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <repo 外の展開先> --wildcards '*block00031_PE.bin'` (2.93 s)。
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

## 追補 3 (#5205・受入 2 の表経由: 復号できた範囲で 0 件・部分達成)

- 表 `0xfe2a90` の slot 0 は `0xfe9090` (reset)。表の先頭 VA `0xfe2a90` を 8 バイト値として格納する箇所は **0 件** (4 バイト値では `0xfe2a90` 自身の 1 件のみ)。
- `.text` 内で表の VA を disp (絶対・rip 相対) とする命令は **0 件**。ただし走査範囲は限定されている。`pe_fe9090_table.py` は `.text` を線形に復号し、復号不能バイトは 1 バイト飛ばして再同期する方式に直した (修正前は `md.disasm` を 1 回だけ呼んで先頭 4 命令で止まっていた)。走査は **命令 5,022,299 件・復号不能 161,366 バイト** (`.text` 16,397,488 バイト中)。この範囲の外にある命令は見ていない。
- 結果: `0xfe9090` を呼ぶ直接 `call` は 2 件 (`0xffe29b`・`0x1001b7b`)。`.text` の `E9` (jmp rel32) での直接ジャンプは 0 件。表の VA を格納する 8 バイト値・表の VA を disp とする命令は、上記の走査範囲で 0 件。よって表経由の経路は、**復号できた範囲では見つからなかった**。復号不能 161,366 バイトの中に表参照があるかは、この方式では確定できない。「表経由の経路は 0 件と確定」とは書かない。受入 2 は部分達成。
- 同じ逆アセンブル方式の欠落確認: `analysis/flapi/pe_decode_coverage.py` で slot 35 の 151 箇所を確認。`.text` の線形復号は 5,022,299 命令・復号不能 161,366 バイト (上と同じ)。151 箇所は全て、含む関数の先頭から単独に復号したときに箇所へ正しく届き (届かない 0 件)、含む関数 98 件の中に復号不能バイトは 0 件。よって `pe_slot35_sites.py` の 151 箇所と `pe_slot35_recv_src.py` の 54 件 (連鎖の形) は、復号欠落の影響を受けていない。
- 補助 probe `analysis/flapi/pe_fe9090_table.py` を追加した (表の内容・格納・参照を列挙)。

### 測定 (追補 3)

- 測定 commit (コードを変えた最後の commit。`pe_fe9090_table.py` の修正 `353a8e950` と main 取り込みの merge `bd7a1a17c`): `bd7a1a17c`。`git diff bd7a1a17c HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (この commit の後は REPORT だけを変える)。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-5212 --wildcards '*block00031_PE.bin'` (展開先 `$RUNNER_TEMP/fl-5212/extracted/block00031_PE.bin`)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-5212 python3 analysis/flapi/pe_fe9090_table.py` を 2 回。rc 0・25.70 s (1 回目の wall 時間)・出力は `cmp` で一致。load (1 分値) は 0.36。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-5212 python3 analysis/flapi/pe_decode_coverage.py` rc 0 (出力は上記の値)。
- 参考: `pe_slot35_sites.py` と `pe_slot35_recv_src.py` は本 PR では再実行していない (両者の復号方式は `pe_decode_coverage.py` で確認済み)。

### 未解決 (追補 3 後)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 151 箇所のうち受け手の型 (大域 `0x15e0c40` の初期化経路が未確定) | 受入 2 (`0xfe9090` が chan で走るか) | #5205 |
| 表 `0xfe2a90` 経由の間接呼出し: 復号不能 161,366 バイトの中の表参照は未検査 (線形走査は復号できた 5,022,299 命令の範囲のみ) | 受入 2 | #3371 |
| 大域 `0x15e0c40`・`0x15e4790`・`0x15e0ff8` の初期化・格納経路 | 受入 2・3 | #3371 |
| `0xf48290` の受け手が chan か | 受入 2 | #3371 |
| `0x1001ef0` の `this` の由来 (呼出し元 4 件) | 受入 2 | #3371 |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 |

## 追補 4 (#5580・受入 1 の初期化経路を確定: ローダの再配置・コードによる store は 0 件)

- 大域 `0x15e0c40` は `.data` (`0x13a5000`〜) の 8 バイト値 `0x16babe8` を持つ静的なポインタ。`0x16babe8` は `.bss` (`0x15e6000`〜) 内のオブジェクトを指す。
- `.reloc` に `0x15e0c40` の DIR64 再配置 (type 10・page `0x11e0000`) が 1 件ある。よって初期値はローダが再配置で書き、コードによる store は要らない。
- コードによる格納は 0 件。確認したこと (`pe_global_init_probe.py`):
  - RIP 相対の参照: load 308 件・store 0 件・`lea` 0 件 (`0x15e0c40` 本体)。
  - 近傍 ±0x40 の RIP 相対参照: `0x15e0c00`〜`0x15e0c80` の全番地で store 0 件。
  - 既知の定数 (`lea rip` と `mov reg, imm`) を基底とする `[reg+disp]` 書込み: `0x15e0c40-0x100`〜`+8` の範囲で 0 件。
  - 絶対 index 付き `[disp+reg*s]` (`disp` が `0x15e0c40±0x400`): 0 件。
  - `.text` 内の即値・8 バイト値・rva32 として `0x15e0c40` を持つ命令: 0 件。
  - 指し先 `0x16babe8` への RIP 相対 store: 0 件。基底付き書込み: 0 件。
- 制限: 逆アセンブルは `.pdata` の関数単位。`.text` の復号不能 161,366 バイト (追補 3) の中は見ていない。`rep movs`・`memcpy` 等の一括コピーで `.data` の範囲を書く経路は未検査。基底が関数内で既知の定数にならない `[reg+disp]` も未検査。
- 受入 1 の判定: 「大域 `0x15e0c40` の初期化・格納経路を PE で確定する」は、上記の範囲で満たす。初期化はローダの再配置で、格納は 0 件。151 箇所の受け手の型 (受入 2) は、この結論だけでは決まらない。その判定は #5205 の受入 1 に残す。

### 測定 (追補 4)

- 測定 commit (コードを変えた最後の commit。`pe_global_init_probe.py` の `--reloc` 追加): `5456dc8c8`。`git diff 5456dc8c8 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (この commit の後は本付録だけを変える)。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-5580 --wildcards '*block00031_PE.bin'` (2.71 s。`extracted/block00031_PE.bin`。repo 外)。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-5580 python3 analysis/flapi/pe_global_init_probe.py 15e0c40` を 2 回 (wall 37.96 s・37.64 s、rc 0、出力は `cmp` で一致)。load (1 分値・開始時) 0.92〜0.96。
- 実行 (同一 commit): `--near` (rc 0)・`--base` (rc 0)・`--reloc` (rc 0)・`16babe8 --base` (rc 0)。

### 未解決 (追補 4 後)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 151 箇所のうち受け手の型 (大域 `0x15e0c40` の初期化は確定。受け手の型は未決) | 受入 2 | #5205 |
| `.text` 復号不能 161,366 バイト・一括コピー・非定数基底の `[reg+disp]` による `.data` 書込みは未検査 | 受入 1 の確定範囲の外 | #5205 |
| `0xf48290` の受け手が chan か | 受入 2 | #3371 |
| `0x1001ef0` の `this` の由来 (呼出し元 4 件) | 受入 2 | #3371 |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 |

## 追補 5 (#5205・受入 1: chan の VMT を格納する箇所は PE に無い。受け手の型は静的には決まらない・部分達成)

- 方式: 受け手の型を「その型の VMT 値を格納する箇所 (コンストラクタ・class ref) から追う」方式を試した。VMT `TPublicChannel` (`0xfe2cf8`)・`TPreviewChannel` (`0xfe2fc8`) について、次の 3 形で PE 全体を探した。
  - abs64: 8 バイトの VA 値 (ファイル全体)
  - imm32: `.text` 内の 4 バイト即値
  - rip: `.text` の逆アセンブルで `[rip+disp]` が VA を指す命令
- 結果: 3 形とも、VMT 自身の slot 以外に 0 件。`block00031_PE.bin` の abs64 は各 2 件 (VMT 自身の slot `0xfe2c30`・`0xfe2ed8`・`0xfe2f00`・`0xfe31a9` を指す値。VMT 内の格納)。他の `*_PE.bin` (素材の PE block 全体) にも 0 件。
- 検出器の陽性対照: `0x16babe8` は abs64 1 件・rip 5 件、`0x1012e78` は rip 1 件を検出した (検出器は動いている)。
- 含意: VMT 値を直接格納する箇所が PE に無いので、「VMT 格納元から逆に追う」方式は使えない。受け手の型を決めるには別の手がかりが要る (未特定)。実行時の型の採取は FLEngine の起動が要るため、本 run では行っていない。
- 受入 1 の判定: 未達。151 箇所は全て「受け手の型は未確定」のまま。

### 測定

- 測定 commit: `fefde10b4` (`pe_vmt_store_refs.py` を追加した commit。コードを変えた最後の commit)。
- 測定 HEAD: `fefde10b4`。本節は REPORT だけを変える commit で、`git diff fefde10b4 HEAD -- tools/python/analysis` の差分は 0 行。
- 素材: `tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'` (2.8 秒。repo 外)。全 PE block の走査は `extracted/*_PE.bin` (素材内 PE 全体) に対して同じ abs64 / imm32 検索を行った。
- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_vmt_store_refs.py 0xfe2cf8 0xfe2fc8` を同一 HEAD で 2 回。rc 0・2 回とも出力が同一 (md5 `79831128a8a05021ba73ab436d2501d7`)。

| 回 | 所要 | load (1 分値・開始時) |
|---|---|---|
| 1 | 11.89 s | 0.28 |
| 2 | 11.94 s | 0.44 |

### 未解決 (追補 5 後)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 151 箇所の受け手の型 (VMT 格納元は PE に 0 件。実行時の型の採取が要る) | 受入 1・2 | #5205 |
| `0xfe9090` が chan で走るか (受け手の型に依存) | 受入 2 | #5205 |
| 一覧 A・B の容器 Q への要素追加箇所と要素型 T | 受入 3 | #3371 |
