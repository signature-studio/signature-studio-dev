# PY-124 (#2999): general.saveUndo の PE 確定 (引数・既定値・戻り値・失敗経路・核への受け渡し)

親: #2978 (PY-120)。前段: `tools/python/REPORT_PY15.md` (kw 名・既定値の推定)、`tools/python/REPORT_PY61.md` (`0xd843d0` job 投入・`0xd82c20` status→PyObject の確定)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- **引数を確定**: 書式 `si|i`・kwlist `undoName` / `flags` / `updateHistory`・`updateHistory` の既定値 1。`undoName` と `flags` は必須、`updateHistory` は任意 (§1)。
- **戻り値は None**。準備不可のときは status -2 になる。その後の `0xd82c20` が文言付きの例外 (「Operation unsafe at current time」) を出すか None を返すかは、`0xd82c7e` の判定の結果で決まる (判定の意味は未確定。§3)。引数の型違い・必須欠落は CPython の ParseTuple が立てた例外をそのまま返す (§3)。
- **核 `0xd69860` の受け渡しを確定**: `flags` と、`updateHistory == 1` の真偽 (核が `sete r9b` で書く 1 バイト) を job 経由で `0x1017ad0` へ渡し、そこで履歴 record を作る。`[obj+8]` が有れば `0x1019b70` で末尾に追加、無ければ `0x1019dd0` で record の要素を後始末する (解放と推定、§4)。
- **未確定**: record の中身 (`0x101b780` 本体・`flags` のビットの意味・`r9b`/`r9d` の読み方)、準備不可時の報告判定 (`0xd82c7e`) の意味。ここが決まらないと、履歴の実体を再現できない。**provider・host・tests は変更しない** (mock にも C にも saveUndo は無く、未実装 code 2 のまま)。no-op の成功は返さない。残りは子 issue `[PY-137]` (#3026) へ移す (§5)。

## 0. 素材と前提

- 素材: `fl-win64` を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` で展開 → `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`。
- PE の ImageBase は `0x400000` (実測)。文字列と表のポインタは絶対 VA で書かれている。
- 検証起点: `origin/main` = `798bbb67`。

## 1. 引数 (wrapper `0xd69900`)

| 項目 | VA | 根拠 |
|---|---|---|
| PyMethodDef | entry `0x151ab40` → fn `0xd69900` (flags=3 = METH_VARARGS \| METH_KEYWORDS) | `analysis/flapi/pe_handler_probe.py saveUndo` |
| 書式文字列 | `lea r8,[rip+0x128]` (`0xd69955`) → `0xd69a84` = `'si\|i'` | `analysis/py124_saveundo.py` |
| kwlist | `lea r9,[rip+...]` (`0xd6995c`) → 表 `0x151a928`: `0xd698d4` (undoName), `0xd698dd` (flags), `0xd698e3` (updateHistory), `0` (NULL) | 同上 |
| undoName | `s` → `[rbp+0x98]` (char*)。`0x41c6e0(&[rbp+0xa0], char*)` で name object を作る (`0xd69998`〜`0xd699a6`) | 同上 |
| flags | `i` 必須 → `[rbp+0xac]`。`0xd6996f` で `&[rbp+0xac]` を渡し、`0xd699c3` の `movsxd` で 8 バイト化 | 同上 |
| updateHistory | `i` 任意。既定値 1 を `mov dword [rbp+0xa8],1` で先に入れる (`0xd69943`)。`[rbp+0xa8]` → `movsxd` (`0xd699cf`) | 同上 |

- `si|i` の `|` より後ろが任意なので、flags は必須、updateHistory は省略可。
- 途中の引数だけ省略する呼び方 (kw で途中を飛ばす等) は ParseTuple の規則に従う。実装時は `REPORT_PY15.md` §16 追補 (a) の方針どおり、途中の省略は TypeError、末尾の省略だけ既定値 1 を使う。

## 2. 核への受け渡し (wrapper → `0xd843d0` → 核 `0xd69860`)

- **wrapper** (`0xd699ae`〜`0xd69a04`): `obj = *(0xd6a8e0(self))` (`0xd6993b`〜`0xd69940`)。`call 0xd843d0(rcx=obj, rdx=&[rbp+0x80] (結果), r8=0xd69860 (核), r9=name, 5 番目=flags, 6 番目=updateHistory, 7〜10 番目=0, 11 番目=1 (byte))`。
- **job 配置** (`0xd843d0` の `0xd84429`〜`0xd84467`、`analysis/py124_saveundo.py` で assert): `job+0x18` = 5 番目 (flags)・`job+0x20` = 6 番目 (updateHistory)・`job+0x28`〜`job+0x40` = 0・`job+0x48` = name (`call 0x4133f0(job+0x48, r13=r9)`)・`job+0x58` = 核。`0x526190` で実行。終了後 `*(結果) = [job+0x60]` (`0xd844d7`)。
- **核 `0xd69860`** (`0xd6986c`〜`0xd698c8`):
  1. `[job+0x60] = -2` (初期値)。
  2. 準備判定: `**G1 + 8` のオブジェクトの `call [vtbl+0x98]` (`0xd69874`〜`0xd69888`)。偽なら status -2 のまま (`0xd69890` の `je 0xd698cd`。`test al, al` は `0xd6988e`)。(`G1` = global `0x15e4790`。`0xd82c20` の報告判定 (§3) も同じ global の `+8` オブジェクトを使う。)
  3. 真なら status 0 (`0xd69892`)。`0x409c80(src=&job+0x18, dst=&tmp, 8)` で flags の 8 バイトを tmp へ読む (`0x409c80` の本体で src=rcx・dst=rdx を確認)。
  4. `0x1017ad0(rcx=**G2 (obj), rdx=job+0x48 (name), r8=&tmp, r9b = (job+0x20 == 1))` (`0xd698c8`)。`cmp qword [rbx+0x20],1` → `sete r9b` (`0xd698bf`〜`0xd698c4`)。核が書くのは下位 1 バイトで、**updateHistory が 1 のときだけ 1** (0・2・-1 では 0)。受け側 `0x1017ad0` が `r9d` 全体を読むため、真偽の読み方は §4 の未確定。

## 3. 戻り値と失敗 code

| 経路 | 条件 | 戻り値 | 根拠 |
|---|---|---|---|
| 成功 | 書式が通る・準備真 | status 0 → `0xd82c20(0)` → **None** (保留例外が無いとき) | `0xd69a09`〜`0xd69a12`・`REPORT_PY61.md` §4-1 |
| 引数不正 | 型違い・flags 欠落・不明 kw | ParseTupleAndKeywords が 0 を返す → `0xd69a10` で `0xd82c20(0)` → ParseTuple が立てた保留例外があるので **NULL** | `0xd69996` `jle 0xd69a10`・`REPORT_PY61.md` §4-1 |
| 準備不可 | `G1+8` の準備判定 (`0xd69888` の `call [vtbl+0x98]`、`0xd69890` の `je`) が偽 | status -2 → `0xd82c20(-2)`。`0xd82c6a`〜`0xd82c84` で global `0x15e4790` → `[obj]` → `+8` のオブジェクトの `call [vtbl+0x88]` (`0xd82c7e`) を呼ぶ。その戻りが 0 なら **None** (`0xd82dd0`・`call 0xc38bc0`)。非 0 なら文言 「Operation unsafe at current time」 (FL の文言表) の例外を立てて **NULL** (`0xd82c8c`〜`0xd82dc8`。例外投入は `0xd82dc6`)。`0xd82c7e` の判定の意味は未確定 (§5) | `REPORT_PY61.md` §4-1 (文言表・報告判定の分岐) |
| flags 範囲外 | — | **核に範囲判定は無い** (`0xd69860`〜`0xd698d3` を全部読んだ)。失敗 code は出ない | — |

- 成功時の Python 戻り値は None (`REPORT_PY61.md` の `0xc38bc0` 経由)。
- 「履歴の登録に失敗したときの code」は核の中では見えない。`0x1017ad0` の戻り値は使われていない (`0xd698c8` の後は status を変えない)。

## 4. 履歴の登録 (`0x1017ad0`) の内訳

| 段 | 呼び出し | 確定度 | 内容 |
|---|---|---|---|
| a | `0x1016ca0(obj)` → `r13` | 確定 (§4-2) | `0x1017150(obj)` が真なら新規 record (`0x1019e30`・`0x1019da0`)、偽なら ring のスロットを取る (pos・count・last の更新)。ring の要素は §4-2 |
| b | `0x101b780(r13, name, &tmp, r9d)` | VA の構造は確定 (§4-2)、**中身は未確定** | record への書込み。カテゴリ mask の判定と各カテゴリの書込み関数は確定。書込みの中身 (vtbl+0x10・+0x40 の実体) は未読 |
| c | `0x1017150(obj)` | 確定 | `cmp qword [rcx+8],0 / setne al` (`0x1017150`〜`0x1017155`)。つまり「履歴管理オブジェクトの有無」 |
| d | 真: `0x1019b70([obj+8], r13)` | 確定 (配列追加) | `[obj+8]+0x20` の配列末尾へ `r13` を追加。count は `qword [ptr-8]`。伸長は `0x417fc0` (未読) |
| e | 偽: `0x1019dd0(r13)` | 確定 (ループ) | record の配列 `[r13+0x20]` の各要素に `0x40faa0` を呼ぶ (解放と推定。`0x40faa0` は本体未読) |

- `0x409c80` (8 バイト複写): `src=rcx`・`dst=rdx`・`n=r8`。`n=8` は 4 バイト 2 本の重なり読み (`0x409cb5`)。
- **r9b の上位ビット**: 核は `sete r9b` で下位 1 バイトだけ設定する。`0x1017ad0` は `mov edi, r9d` で 32 ビット全体を受けるため、上位ビットが残ると真偽の読み方が変わりうる。`0x101b780` の読み方 (r9b か r9d か) が未確定なので、この影響は未確定。

## 4-2. PY-137 (#3026) の追補: 履歴スロットと record 書込みの VA 事実

検査: `analysis/py137_saveundo_record.py` (PASS。§6)。履歴オブジェクト `H = [[0x15e1c78]]` の字段は `REPORT_PY94.md`・`REPORT_PY123.md` と同じ (`+0x1c` = Pos、`+0x20` = Last、`+0x24` = Count)。ここで新たに確定したのは `+0x8` (list 所有者。0 なら無し)・`+0x14` (ring の record ポインタ配列。長さは配列ヘッダ `-8` の qword)。

| 関数 (VA) | 確定した事実 | 検査 |
|---|---|---|
| `0x1016ca0` (スロット取得) | `[H+8] == 0` のとき ring 方式。`ebx = 1 - Last`、`Pos = (Pos + ebx + len) % len` (`cdq`/`idiv`)、`Count = min(Count + ebx, len)`、`Last = 0`。`ring[Pos]` を `[rbp+0x28]` に保存してから後処理 (次の行) を行い、その `ring[Pos]` を返す。`[H+8] != 0` のときは `0x1019e30(G, dl=1)` で新規 record を作り、`0x1019da0` で reset してから返す (`0x1016cd9`) | `RING_STEP` |
| `0x1016ca0` の ring 後処理 (`0x1016d54`〜`0x1016dc1`) | 順に: (1) `0x418210(&tmp, [H+0x14], type)` で ring 配列を一時変数 `tmp` (`[rbp+0x38]`) へ代入。(2) `tmp` の各要素 `e` について `byte [e+0x34] != 0` なら `0x1019da0(e)` を呼ぶ。(3) `0x418190(&tmp)` で `tmp` を破棄。(4) `0x1016e00(H)` (次の行)。(5) `0x418190(&tmp)` (`tmp` は NULL のため no-op)。`[H+8] != 0` の経路は `0x1016cde` で `0x1016db5` へ飛び、(1)〜(4) を行わない。**(2) は ring の record そのものを reset する**: 配列を共有する経路では要素 (record のポインタ) が ring と同じ (`0x418210` の行)。複写の経路では要素の複写の仕方に依る (未確定) | 本文のみ |
| `0x1019da0` | `0x101d180(rcx=e, rdx=0 (名前 NULL), r8=0x1019dbc (その 8 バイトは 0 と実測), r9b=0)` を呼ぶ wrapper。reset (`r9b == 0` の経路) になる | 本文のみ |
| `0x418210` (配列の代入 `dst = src`。名前は推定だった) | `src` が NULL または `[src-0xc] >= 0` のとき `0x418260(src)` で参照を共有 (refcount +1)。その後 `0x418190(dst)` で dst の旧値を破棄し、`dst = src`。`[src-0xc] < 0` のとき `0x418000(dst, src, type)` で複写 (dst の旧値の破棄を含む) | 本文のみ |
| `0x418000` → `0x418030` (配列の複写) | `src` が NULL なら `0x418190(dst)` のみ。それ以外は `0x418030` が新しい配列を作る (`[arr+4]` = refcount を `1`、`[arr+8]` = 長さ)。要素は型の helper `0x416db0` (型が持つとき) か `0x409c80` (memcpy) で複写し、`0x418190(dst)` の後で `dst` に入れる。helper `0x416db0` の本体は未読 | 本文のみ |
| `0x418190` (配列の参照解放。名前は推定だった) | `dst` の値を 0 にし、値が非 NULL で refcount > 0 のとき `lock xadd -1`。旧 refcount が 1 だったときだけ要素を `0x416230` で破棄し、`0x409440` で解放する | 本文のみ |
| `0x418260` (参照の共有) | `rcx` が非 NULL かつ `[rcx-0xc] >= 0` のとき `lock xadd +1` | 本文のみ |
| `0x1016e00` → `0xfdef70` | `0x1016e00` は `call 0xfdef70` だけの wrapper。`0xfdef70` の本体は `or dword ptr [rip+0x6dbf06], 0x20000` の 1 命令と `ret` で、global `0x16bae80` の bit `0x20000` を立てるだけ。flag の意味は未確定 | 本文のみ |
| `0x1019dd0` (record+0x20 の項目解放) | 配列 `[record+0x20]` の各要素 (件数 `[arr-8]`) に `0x40faa0` を呼び、`0x418190(&record+0x20)` で配列を破棄する (§4 の行 e の「解放と推定」の中身) | 本文のみ |
| `0x1017150` | `setne(cmp [rcx+8], 0)`。つまり `[H+8] != 0` | `IS_LIST` |
| `0x1016e50` | ring の長さ。`[H+0x14]` が null なら 0、そうでなければ `[ptr-8]` | `RING_LEN` |
| `0x1017ad0` (核) | 呼出し順: `0x1016ca0` → `0x101b780` → `0x1017150` → (真) `0x1019b70([H+8], r13)` で list へ追加 / (偽) `0x1019dd0(r13)` で項目解放。flags は `mov rax,[r8]` で 8 バイト読む | `REC_ADD` |
| `0x101b780` (書込み) | 先頭で `0x101d180(r13, name, &flags, 0)` (reset)。`record+0x28` に global の dword (系列番号)。文字列 `\x0b\x0d\x23` と `\x06\x07\x09\x2d\x30\x32` の各文字 c について、`(1 << c) & record+0x54` が真なら `0x102bb20(record+0x40, c)` で得た要素の `vtbl+0x10(elem, r9b)`。`record+0x54` の bit 0・bit 1 のときは `+0x0c`・`+0x14` の object の `vtbl+0x40` を呼ぶ (索引は `record+0x28` の 192 バイト要素)。`(mask & A) == B` (A・B は global) のとき `+0x80` の大配列 (0x870a*8 バイト要素) への書込みを飛ばす。`r9b != 0` のとき最後に `0x101a080` | `REC_FILL` |
| `0x101d180` (reset・設定) | `record+0x54 = *[r8]` (mask)、`0x4133f0` で名前を `record+0x2c` に代入 (`r9b` の値によらず行う)。`r9b == 0` のときは、その前に次を順に行う: (1) `0x1019dd0(record)` (record+0x20 の項目解放)。(2) `record+0x54` の bit0 で `0x12df0f0(+0xc)`、bit1 で `0x12df0f0(+0x14)`。(3) `(mask & A) == B` (A・B は global) でないとき、`+0x80` の大配列の各要素 (stride `0x870a*8`) の先頭 qword を `0x40faa0` で解放し、配列を `0x418190` で破棄。(4) `+0x4c` の配列の件数が 1 以上のとき、作業 object を `0x511fe0` で作り `vtbl+0xb8` を呼んだ後、各要素を `0x1014d60` で処理し、作業 object を `0x40faa0` で解放、配列を `0x418190` で破棄。(5) `+0x68` の先頭 qword を `0x40faa0` で解放して 0 にする。(6) `+0x70 = -1`。(7) `0x412d60(+0x74)`。(8) `0x102ba00(+0x40)`。`0x101d469` 以降の末尾 (`0x101a5f0`、`0x101d853` への分岐) は未読 | `REC_RESET` |
| `0x102bb20` | `c` を索引にして registry の要素を返す (索引が負なら null)。索引の計算 `0x102b6c0`・`0x102b610` は未読 | 本文のみ |

**未確定 (残り。子 issue へ移す)**:

- カテゴリ c とカテゴリ名の対応 (`0x102b6c0`・`0x102b610` の索引の意味)、registry の要素の型。
- `vtbl+0x10`・`vtbl+0x40` の書込み内容 (record に何を保存するか)。`0x12f9ed0`・`0x416750` の大配列の意味。
- mask ゲート `(mask & A) == B` の A・B の global 値 (PE の data 参照は未実施)。
- `[H+8]` が実行時に非 0 になるか。`REPORT_PY123.md` の boot 時点の観測では H の値が 0 のまま (停止点は unit 209)。実機の値は未実測。
- **ring 後処理 (`0x1016d54`〜) の残り**: (a) `record+0x34` の意味と、その flag を書く箇所 (未検索)。(b) ring 配列 `[H+0x14]` の refcount の実行時の符号。負なら複写の経路 (`0x418000`) になる。`0x418030` が作る配列は 1 で始まる。実行時の値は未実測。(c) 複写の経路で要素を型の helper `0x416db0` が複製するか (型記述子 global `0x100d3c0` 経由。本体は未読)。(d) `0xfdef70` が立てる global `0x16bae80` (bit `0x20000`) の意味と、それを読む箇所 (未検索)。
- **子 object の本体**: `0x1019e30` (新規 record の ctor)・`0x417fc0` (配列の伸長)・`0x40faa0` (項目解放)・`0x12df0f0`・`0x102ba00`・`0x412d60`・`0x1014d60`・`0x511fe0`・`0x416230`、`0x101d180` の末尾 (`0x101a5f0`、`0x101d853` への分岐)。これらが H (`+0x1c`・`+0x20`・`+0x24`) を書くかは未確定。
- 準備不可のとき: `0x101d180`・`0x101a080` の判定が `G1+8` 側の `call [vtbl+0x98]` と同じ式か、`0xd82c7e` の意味。§3 の未確定から継続。

**実装への含意**: ring の Pos・Count・Last は PE の式どおりに決まった。`mock` と C で数値だけ更新すると、`general.getUndoHistory*` の 3 件 (H の `+0x1c`・`+0x20`・`+0x24` を読む) は PE と一致しうる。ただし、ring 方式のスロット取得のたびに ring の要素のうち `+0x34 != 0` のものが `0x101d180` で reset される (共有の経路。要素は ring と同じ record)。この reset は数値だけの mock では再現されず、`+0x34` の意味が未確定なので再現条件も決まらない。後処理 loop 自体は H の `+0x1c`・`+0x20`・`+0x24` を書かない (前半の `0x1016ca0` で書き終わる)。ただし loop が呼ぶ `0x101d180` 経由の子 object 解放 (`0x12df0f0`・`0x102ba00` など) の本体は未読なので、子が H を書くかは未確定。一方、record の中身 (カテゴリごとの保存) は未確定なので、中身の無い履歴は `restoreUndo` 系で別の結果になる。よって、中身を再現できるまで `saveUndo` は実装しない (no-op の成功も返さない)。

## 4-2b. #4770 (PY-378) の追補: 未確定一覧の PE 確定

検査: `analysis/py4770_saveundo_open.py` (PASS。§6)。#3733 の一覧を 1 項ずつ書く。「確定」は PE の VA から事実を読めたもの、「部分」は一部だけ、「未確定」は理由を付けて残したもの。

| 項目 (#3733 の一覧) | 結果 | VA と事実 | 残り (理由) |
|---|---|---|---|
| カテゴリ c の索引 | 部分 | `0x102bb20(registry, c, &out)` は `0x102b6c0` (ハッシュ。`vtbl+0x20` の戻りを `&0x7fffffff`・`+1`・`&0x7fffffff`。c に依らない) と `0x102b610` (16 バイト要素の線形探索。dword key がハッシュと一致し、`vtbl+0x18(registry+0x18 の object, entry の byte, c)` が真になった位置の索引を返す。空の key (-1) に当たると負の値を返す) で索引を取り、`0x102bb20` は索引が負なら NULL、そうでなければ要素の `+8` を返す | `vtbl+0x18` の実体と、c の値から名前への対応は未読 |
| registry 要素の型 | 部分 | 要素は `0x102bb20` が返す object。`0x102ca60` が `0x102b8b0` で登録し、その前に `0x448ee0` (factory。`0x410320` で生成し `0x41c820` で名前を設定する) を呼ぶ。`0x102ca60` の 2 経路 (bit0・bit1) は、第 1 引数 `0x430df0` と名前 `[0x15e4c18]` が同じで、呼出し前の guard だけが違う (`0x100c1b0`・`0x100d098`。先頭バイトが 7 なら呼ばない)。`0x102b8b0` は `0x41a7b0`・`0x102b3e0` を呼ぶ (`0x102b3e0` は配列の伸長) | 要素の型記述子・vtbl は未特定。guard 先の global の型は未読 |
| `vtbl+0x10` (`0x101b780` 内、`(elem, r9b)`) の書込み内容 | 未確定 | 呼出し位置 `0x101b8f6`・`0x101bc18` 付近。r9b は `0x1017ad0` が渡す `updateHistory == 1` の真偽 (§2) | 呼ぶ vtbl の実体を未読 |
| `vtbl+0x40` (`record+0x0c`・`+0x14` の object、`0x101b98e`・`0x101b9d4`) | 部分 | 引数は `record+0x28` (系列番号・`0x15e4018` の dword) を 192 バイト (24 qword) 間隔で索引した global `0x15e2aa0` の要素 | 呼ぶ vtbl の実体と、`+0x0c`・`+0x14` の object の型は未読 |
| 大配列 `0x12f9ed0`・`0x416750` の意味 | 部分 | `0x12f9ed0` は `[0x196eb60]` (.bss。実行時に埋まる配列) の要素数 (`[arr-8]`)。`0x12f9ec0` は同配列の要素。`0x416750` は冒頭で `[r8]` の型 tag (0x16) を見て、22 の要素なら `[rbx+0x19]` の関数ポインタを呼ぶ (分岐の先頭のみ読了) | 配列の中身は .bss のため PE だけでは決まらない。`0x416750` の本体の後半は未読 |
| mask ゲート `(mask & A) == B` の A・B | **確定** | `0x101b9e2`・`0x101b9e9` が `.text` 内の定数 (RIP 相対 `0x101bd54`・`0x101bd5c`。`.text` は読取専用) を読む。A = `0x10000000004` (bit 2 と bit 40)、B = `0`。`je 0x101bb0c` は `(mask & A) == B` のときの飛び先を確認した (飛び先の確認のみ。「`+0x80` への書込みを飛ばす」という意味付けは検査していない) | — |
| `0x1019e30` (record ctor) | 部分 | `+0x48`・`+0x64`・`+0x7c`〜`+0x7f`・`+0x68` を 0、`+0x35` を 1、`+0x34` を 0、`+0x0c`・`+0x14`・`+0x40` に object を入れる (`0x105f460`・`0x10601e0`・`0x102c9b0`) | `0x105f460`・`0x10601e0` 未読 |
| `0x102c9b0` (registry 生成) | 部分 | `0x102ca60` を呼び、bit 0 (`test al,1`) と bit 1 (`test al,2`) の 2 経路で `0x448ee0` を呼ぶ | `0x102b8b0` 未読 |
| `0x1019dd0` (record+0x20 項目解放) | **確定** | `[rbx+0x20]` が NULL でなければ件数 `[arr-8]` を求め、各要素に `0x40faa0` を呼ぶ (件数分のループ)。ループの後、`lea rcx,[rbx+0x20]` と `[rip-0xca5e]` の global を渡して `0x418190` で配列を破棄 | — |
| `0x40faa0` | **確定** | `[vtbl-0x20](obj, 1)` (仮想削除) | — |
| `0x418210` (配列の代入) | **確定** | 経路は 2 つ。(a) `src` が NULL または `[src-0xc] >= 0` のとき `0x41823b` へ飛び、`0x418260` で共有 (refcount +1) → `0x418190(dst)` で旧値を破棄 → `dst = src` (`0x41824e`)。(b) それ以外 (`src` が非 NULL かつ `[src-0xc] < 0`) は `0x418000` で `dst` へ直接複写し (`0x418234`)、`0x418239` で `0x418251` へ jump する。(b) は `0x418190` も `dst = src` も通らない | — |
| `0x418190` (配列の参照解放) | **確定** | `dst` を 0 にし、refcount を `lock xadd -1`。旧 refcount が 1 のとき要素を `0x416230` で破棄し、`0x409440` で解放 | — |
| `0x41c6e0` (char* → name object) | 部分 | 引数 `char*` が NULL か空なら `0x412d60`。そうでなければ `0x413660` で長さを得て、`0x414ad0`・`0x414850`・`0x41c360` で複写 | 所有権と寿命 (`0x41c360`・`0x414ad0` 未読)。§5 の未解決 |
| `+0x34` フラグ (ring 後処理の (a)) | 部分 | `.text` 全体の `+0x34` への byte 書込みを検索 (69 件)。record に関わるのは 2 箇所: `0x101a5f0` (独立した関数。`mov byte [rcx+0x34], 0; ret`。呼び出し元は `0x101d180` 内の `0x101d49c`)、`0x101b516` (関数の途中の断片。直前のバイトが関数の区切りではないので、先頭は特定していない。`cmp [rcx+0x34],0; sete cl; mov [rax+0x34], cl`。ループで `0x101a6e0` を呼んだ後に書く) | 意味 (dirty 等) は未確定。`0x101b516` の含む関数の先頭と `0x101a6e0` は未読 |

**この一覧で確定しなかった理由の要約**: 残りは (1) vtbl の実体 (`+0x10`・`+0x18`・`+0x40` が指す型)、(2) 大配列 `0x196eb60` の中身 (.bss)、(3) 未読の子 object (`0x448ee0`・`0x105f460`・`0x10601e0`・`0x102b8b0`・`0x416750`・`0x414ad0`・`0x41c360`)。(1)(3) は逆アセンブル範囲を広げれば読めるが、本 issue の範囲外として子 #4796 ([PY-385]) へ移す。(2) は PE だけでは決まらず、実機での観測が要る。

## 4-2c. #5292 (PY-4904) の追補: vtbl 3 本の呼出し箇所と未確定の理由

検査: `analysis/py4904_saveundo_vtbl.py` (PASS。§6)。`vtbl+0x10`・`+0x18`・`+0x40` の**呼出し箇所**は PE で確定した。**呼ばれる実体 (型) は確定しなかった**。

| 項目 | 結果 | VA と事実 | 残り (理由) |
|---|---|---|---|
| `vtbl+0x10` の呼出し | 呼出し箇所は確定 | `0x101b8f6`・`0x101bc1f` の `call [rbx+0x10]`。`rbx` = `[elem]`、引数 `rcx = elem`・`dl = [rbp+0xc8]` (= r9b、updateHistory==1 の真偽) | 呼ばれる実体は未確定 (下) |
| `vtbl+0x40` の呼出し | 呼出し箇所は確定 | `0x101b98e` (`record+0x0c`) と `0x101b9d4` (`record+0x14`) の `call [rbx+0x40]`。引数の `rdx` は (未検証: 本検査は呼出し位置だけを確認) `[global 0x15e2aa0 + 24*(record+0x28)*8 + 0x20]` と読める。`0x15e2aa0` は `.data` (RVA 0xfa5000 の範囲内) で、先頭 6 qword の初期値は `0x193fce0`・`0x13e9458`・`0x1403bdc`・`0x6a8030`・`0x425bb0`・`0x15d3296` | 同上 |
| `vtbl+0x18` の呼出し | 呼出し箇所は確定 | `0x102b690` の `call [rax+0x18]`。`rcx` = registry+0x18 の object、`dl` = entry の byte (`[r14+4]`)、`r8d` = c。`0x102b610` の線形探索で真になった位置の索引を返す | c と名前の対応は未確定 (下) |

**実体が確定しなかった理由 (PE の静的な読みの範囲)**:

- registry 要素の型 global `0x430df0` (`0x102caca`・`0x102cb01` の `mov rcx,[rip+..]`) の値は `0x430eb8` で `.text` 内。その先頭 qword は `0x449240` (これも `.text`)。vtable ポインタとして読むと、`+0x10`・`+0x18`・`+0x40` のどれも命令列のバイトになり、vtable として読めなかった。`.rdata` は 0x45 バイトしか無く、vtable の置き場所が別にあるかもしれない。要素の型は特定しなかった (静的 object の形を別途読む必要がある)。
- record 要素の table `0x15e2aa0` は `.data` にあり、先頭 6 qword の初期値は上の表のとおり (PE から読める)。table 自体は静的に読めるが、要素が指す先の object の型は PE だけでは決まらない (要素の vtable は未読)。
- name 引数の global `0x15e4c18` の値 `0x425c60` は `.text` 内の名前 object で、`0x15ec298` を指す (vtbl の確定には不要)。

**未確定 (子へ移す)**: `vtbl+0x10`・`+0x40` の実体 (record に何を書くか) と、`vtbl+0x18` の c→名前の対応。`0x430eb8` の object layout (静的 object の読み方) と、`0x15e2aa0` が指す要素 object の型・vtable (table 自体は静的に読めるので、要素の読み先を辿れば決まる)。

**検査の範囲**: `analysis/py4904_saveundo_vtbl.py` が assert するのは call 命令の位置 (`0x101b8f6` 等) だけ。`rbx = [elem]`・`dl = [rbp+0xc8]`・`rdx` の式は本検査では確認していない (上の表で「未検証」と書いたもの)。

## 4-2d. #5603 (PY-5371) の追補: vtbl 3 本の判定表 (PE 単独の結論)

親 #5292 の受入 1 を子 #5603 で扱った結果。素材 `fl-win64` (ImageBase 0x400000・`.text` RVA 0x1000) を逆アセンブルした観測 (run 38847796652 の停止報告。本節では再測定していない)。検査スクリプトは commit していない。

| vtbl | 呼出し箇所 | 判定 | 事実 (VA) | 確定できない理由 |
|---|---|---|---|---|
| `+0x10` | `0x101b8f6`・`0x101bc1f` の `call [rbx+0x10]` | 未確定 | `rbx = [elem]`。elem は `0x102bb20` が返す registry 要素。要素は `0x102ca60` → `0x102b8b0` で登録され、その前に factory `0x448ee0` (→ `0x410320`・`0x41c820`) で生成される | 要素は実行時に生成される。その vtable を指す静的な値が PE の `.data`・`.text` に無い。factory の生成先の型は `[obj-0x30]` の仮想呼出しで実行時に決まる |
| `+0x18` | `0x102b690` の `call [rax+0x18]` | 未確定 | `rax = [registry+0x18]`。registry は静的 object `0x430df0` (vtable `0x430eb8`)。その `+0x18` は `0x102cb90` → factory `0x479b40` の結果を `0x41a7b0` で格納したもの。`0x479b40` は `.text` の型表 (添字 `cl*0x2e`・要素 8 バイト×2) から実装を選ぶ | 添字は `0x102cb90` が渡す global `[rip-0x209ed]` (`[rbx]` の型バイト) で決まり、その値は実行時に確定する。PE 単独では実装 VA が 1 つに定まらない |
| `+0x40` | `0x101b98e` (`record+0x0c`)・`0x101b9d4` (`record+0x14`) の `call [rbx+0x40]` | 未確定 | 受け手は `0x15e2aa0` (192 バイト間隔・`record+0x28` で索引) の要素。先頭 6 要素の `+0x20` object を確認した: k=0・4 は vtable `0x15ec298` で、これは `.bss` (ファイル上ゼロ・実行時に埋まる)。k=1・2・6・7 は vtable を読めず、k=3・5 は vtable 位置が `.data` の非ポインタ値 | 受け手の型の大半が `.bss` の実行時値で、PE だけでは確定しない |

**結論**: 3 本とも、PE だけでは呼ばれる実装 VA を 1 つに定められない。確定には実行時の観測が要る (vtable の実値・`0x102cb90` の global `[rip-0x209ed]` の値・`0x15e2aa0` 要素の型)。これは §4-2b・§4-2c の結論と同じ。

**未解決の追跡**: 実行時観測の手段は本節の範囲外。子 issue は起票しない (PM 判断 R7・既存の関連子 #4796・#5604 を優先)。

## 5. 未確定と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| カテゴリ c の対応・`vtbl+0x10`/`+0x40` の書込み内容・mask ゲートの A・B (§4-2) | record の中身が決まらない。`saveUndo` の実装ができない | 子 (下の §7) |
| §4-2 の未確定 (ring 後処理の (a)〜(d)、子 object の本体 `0x1019e30`・`0x417fc0`・`0x40faa0` など) | record の生成・伸長・解放の実体、ring の reset 対象 (`+0x34`)、子 object が H を書くか | 子 (§7) |
| `0x41c6e0` (char* → name object の所有権・寿命) | name の寿命と解放時期 | 子 (§7) |
| mock / C の undo 履歴モデル (`getUndoHistoryCount` 等・PY-70 の getter との整合) | 実装の状態 (Pos・Count・Last の更新) の根拠は §4-2 で確定済み。実装は子 | 子 (§7) |
| 保留例外の Python 例外型 (`0xd82c20` の `[rip]` 先) | 引数不正時の例外型 | `REPORT_PY61.md` §4-2 の未確定。親 #2978 へ提案 (本 PR では扱わない) |
| `0xd82c20` の報告判定 (`call [vtbl+0x88]`・`0xd82c7e`。global `0x15e4790` の `+8` オブジェクト) の意味 | 準備不可時に、文言付き例外 (「Operation unsafe at current time」) と None のどちらになるかが決まらない | 本 PR の未解決表。`REPORT_PY61.md` §4-1 に注記 |

## 6. 検証

- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py124_saveundo.py` → `PASS` (実測 0.06 秒。load average 0.02 / 0.22 / 0.15 は uptime の実測)。出力: `fmt='si|i' kwlist=['undoName', 'flags', 'updateHistory'] default_updateHistory=1 core_ready_check=call[vtbl+0x98] update_eq_1=sete_r9b`。
- ネガティブコントロール: 期待書式を `si|ii` に変えたコピー → `AssertionError: si|i` で停止 (実測。検査が書式を見ていることの確認)。
- 逆アセンブル補助 (1 コマンドで再現): `python3 analysis/py41_disasm.py <block00031_PE.bin> d69900 d69860 d843d0 1017ad0` (`py41_disasm.py` は最初の `ret`/`int3` で止まる)。
- **範囲外**: 実機の FL で saveUndo を呼んだ結果 (履歴の見え方・例外の型) は未実測。`provider/`・`host/`・`tests/` は変更していない。`tests/general_diff.mjs`・`provider_check.mjs`・`all_tools.mjs` は本 PR のコード変更が無いので未実行 (provider の wasm build も行っていない)。
- 測定 commit: `3a53c9f9` (`analysis/py124_saveundo.py` を追加した commit。コードを変えた最後の commit)。`git diff 3a53c9f9 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 REPORT の commit 前後で実行して確認)。HEAD との差分は REPORT と DOC_MAP だけ。
- PY-137 (#3026) の検証: 測定 commit `5f4caf673` (`analysis/py137_saveundo_record.py` の docstring だけを直した commit。コードの最後の変更はこの commit)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py137_saveundo_record.py` → `PASS: py137 saveUndo record PE facts` (実測 0.082 秒。`uptime` の load average 0.08 / 0.16 / 0.10)。ネガティブコントロール: `(1 << c)` の判定の期待行 `idiv ecx` を `idiv edx` に変えたコピー → `AssertionError: pos = (pos + ebx + len) % len` (実測)。`git diff 5f4caf673 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (HEAD は本 REPORT を含む commit。その hash は同じ commit の中には書けないため、PR 本文に記載)。
- 逆アセンブル補助 (PY-137): `python3 analysis/py41_disasm.py <block00031_PE.bin> 1016ca0 1017ad0 101b780 101d180 418210 418190 418000 418030 418260 1019da0 1019dd0 1016e00 fdef70` (`py41_disasm.py` は各 VA から最初の `ret` で止まる。`0x1016ca0` の後処理 loop は最初の `ret` (`0x1016dd1`) より前にある)。
- #4770 (PY-378) の検証: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py4770_saveundo_open.py` → `PASS: py4770 saveUndo open facts` (実測 0.071 秒。`uptime` の load average 0.17 / 0.26 / 0.14)。測定 commit `2efd1b12d` (main 取り込み後の HEAD。その時点の `tools/python/analysis` の差分は main 由来の 240 行を含むが、検査は取り込み後の HEAD で実行)。確定した A・B の定数 (`0x10000000004`・`0`) と、registry flags (`byte[0x1019f70] = 2`)、`0x40faa0`・`0x418190`・`0x418210`・`0x102bb20` の本体の形を assert する。`capstone` は `lock xadd` を mnemonic `'lock xadd'` として出すので、検査はその文字列で照合している。
- #4770 の未実施: `[H+8]`・`0x101d180` の実行時の挙動、大配列 `0x196eb60` の中身は PE だけでは決まらないので、実機で観測しないと確定しない。
- PY-385 (#4796): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py4796_saveundo_pe.py` → `PASS: py4796 saveUndo PE facts (PY-385)`。確定した 6 本 (`0x41c360`・`0x414850`・`0x414ad0`・`0x448ee0`・`0x102ca60`・`0x102b8b0`) の形と、`0x102ca60` の global (`0x430df0`・`[0x15e4c18]`・guard `0x100c1b0`・`0x100d098`) を assert する。ネガティブコントロール: `0x102ca60` の第 1 引数の期待値 `0x430DF0` を `0x430DF1` に変えたコピー → `AssertionError: ['0x430df0', '0x430df0']` で停止 (実測)。
- PY-385 の未実施: vtbl の実体 (`+0x10`・`+0x18`・`+0x40`)、`0x416750` の後半、`0x12f9ed0`・`0x12f9ec0` の配列内容、`0x101a6e0`・`0x101d180` は未読。`0x101d180` の reset と `+0x34` の意味は PE だけでは決まらない。
- PY-137 の未実施: `tests/general_diff.mjs`・`provider_check.mjs`・`all_tools.mjs` は本 PR で `host/`・`provider/`・`tests/` を変えていないので未実行。`saveUndo` の実機での挙動は未実測。

## 7. 子 issue

- #3026 (PY-137, 親 #2999): 本 PR で、履歴スロットの式と record 書込みの VA 構造を §4-2 に確定した。issue の範囲は §4-2 の確定 1 件に縮め、`Closes #3026` とする。
- #4796 (PY-385, 親 #4770): §4-2b の未確定のうち、`0x41c360`・`0x414850`・`0x414ad0`・`0x448ee0`・`0x102ca60`・`0x102b8b0` の 6 本を PE から確定し `analysis/py4796_saveundo_pe.py` で assert した。vtbl の実体 (`+0x10`・`+0x18`・`+0x40`)・`0x416750` の後半・大配列の内容は未確定のまま (理由は §4-2b の表)。
- 残り → `[PY-242]` #3733 (親 #3026): record 内容の PE 確定、mock と C provider への `general.saveUndo` 実装、general_diff 差分 0・provider_check 期待値・all_tools 48/48 (#3026 の受入条件のうち #2〜#4 と、§4-2 の残りの PE 未確定。ring 後処理の `+0x34`・refcount・flag、子 object の本体を含む)。
