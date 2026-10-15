# PY-176 (#3253): 0x1051720 の状態 bb の生成元 (0xf82a10・0xf82c20・10519c6 枝) の PE 確定

親: #3213 (PY-170)・#2576 (PY-77)。前段: `tools/python/REPORT_PY72.md` の「追加解析 (PY-170 / #3213)」節 (0x1051720 の戻り値 2 の分岐条件は確定済み)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

## 結論 (PE 実測で確定した範囲)

- 0x1051720 の戻り値 bb (`[rbp+0xbb]`) は、0xf82a10 が G の保存値から decode した bb で決まる。値域は 0xff (見つからず・初期値)・0 (保存値の不整合で reset)・1 (保存時点で変化あり)・2 (保存時点で変化なし)。受入 1 は**確定** (下記 §2・§4)。
- 0xf82c20 は (G, key, dir, flag, bb) を受け、`bb | ((dir+1)<<8)` を保存する。書込み先は G の item (`+0xc`)、大域 V (`0x16bacec`)、表 `[0x16bacd8]` の 3 系統。受入 2 は**確定** (§3)。
- 10519c6 枝は G・V・K に**直接の書込みをしない**。枝内で通知文字列を組み、大域 `0x16bd1a0` (文字列) と `0x16bd1a8` (フラグ) を更新して UI 通知 `0xbd68e0(0xa)` を出す。受入 3 のうち枝の命令列と呼出し順は確定。`0x104f580`・`0x104d2b0`・`0x43dd60`・`0x414c70`・`0xbd68e0` の本体は未読 (§5)。
- 受入 4 (表 `[0x16bacd8]` の hook の実体) は未着手。`0xf8e4e0` が表の vtable `+0x18` を 2 回呼ぶことだけ確認 (§3)。残りは子 #3287 [PY-182]。10519c6 枝の呼出し先の本体は子 #3288 [PY-183]。
- 未確定: K (`0x16bacf0`) の書込み元、item の tag (`0xf8ca50`) の意味、表の要素型 (36 バイト)、`.bss` 上の大域の実行時値。

## 測定

- 測定 commit (コードを変えた最後の commit): `d3bbceaa` (probe に定数・literal の値検査を追加)。測定 HEAD: `892efc7b` (main 取り込み merge。下の差分の証跡で差分があるため、この HEAD で再測定した)。ベースは origin/main `7c85004e`。作業は `3253-py176-bb-origin` の worktree。
- 展開: `cd <展開先> && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block00031_PE.bin` (2.2 秒・22,227,016 バイト・1 回。`fl-win64.tar.zst` (2.3 GB) の実在を `ls` で確認済み)。展開先は repo 外の一時領域で、`FL_WIN64_DIR` で指定する。gitignore の `tools/python/work/` は使わない (規約 4)。
- 逆アセ (HEAD で再実行。以下 24 回すべて終了 0): `pe_disasm.py` (0x1051720 400・0xf82a10 400・0xf82c20 400・0xf829c0 60・0xf8c9d0 40・0xf8ca50 40・0xf8ec70 90・0xf8e4e0 80・0x11f1a20 65・0x104f580 300・0x104d2b0 200・0x414e70 150・0x43dd60 250・0x414da0 250・0x414c70 120・0x104d0d0 100・0x1050f90 200・0x10469f0 150)、`pe_rip_consts.py` (0x1051720 240・0xf82a10 120・0xf82c20 110・0x11f1a20 40)、`pe_callgraph.py callers 0x1051720`、`pe_cstr.py <VA>` (狭い C 文字列として読むため UTF-16 の literal は 1 文字だけ出る。`0x1051bf0` → `' '`。全文は pefile で 2 byte ずつ読んだ)。
- probe (`FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_bb_state_probe.py`): 17 件すべて PASS・summary OK・終了 0。数え方: 構造 8 件 (呼出し順・slot・初期値・vtable 呼出し)・定数 3 件・literal 6 件。HEAD で n=3 の real は 0.07 秒 ×3 (min–max 0.07–0.07)、load average (1 分値) 0.67。
- 実測した定数・literal (probe が照合する値): 定数 `0x1051b78` = 0.05 (f64)・`0x1051b80` = 100.0 (f64)・`0x1051be0` = 0 (byte)。literal (UTF-16LE・NUL 終端まで): `0x1051bf0` = `" is waiting for pickup: "` (24 文字)・`0x1051c30` = `"%.2f"`・`0x1051c48` = `"%"`・`0x1051c58` = `" "`・`0x1051c68` = `" < "`・`0x1051c7c` = `" > "`。
- 所要・load: 逆アセ 1 回あたり 0.07 秒 (HEAD で 22 回を計測。並列 1)。`pe_callgraph.py callers 0x1051720` は 24.04 秒・24.16 秒 (n=2・並列 1・load 1 分値 0.26 → 0.57・nproc 4)。e2e ではない。
- 差分の証跡 (測定 commit `d3bbceaa` → 測定 HEAD `892efc7b`): `git diff --stat d3bbceaa 892efc7b -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行ではない。内訳は main 取り込み分で、`analysis/flapi/pe_flrack_flr_probe.py` +65・`analysis/py167_flr_pyc.py` +90 (別タスクの probe)、provider・host・tests 4 files +37/−10。本 probe `analysis/flapi/pe_bb_state_probe.py` の差分は 0 行。PE (`block00031_PE.bin`) は変わらないが、差分があるため HEAD で再測定した (上記)。
- ネガティブコントロール (HEAD で実行。1 バイトだけ壊した複製を repo 外の一時領域 `<neg>` に置き、`FL_WIN64_DIR=<neg>/<名前>` で probe を実行。`cmp -l` で差分 1 バイトを確認):

| 検査 | 壊し方 (VA・file offset・旧→新) | 出力 | 終了 |
|---|---|---|---|
| 構造: bb の初期値 0xff | VA `0x1051813` (`mov byte ptr [rbp+0xbb], 0xff` の末尾)・`0xc50c13`・`ff`→`fe` | `FAIL bb の初期値 0xff (0x105180d)`・`summary: 1 FAIL` | 1 |
| 定数: 0.05 | VA `0x1051b78` (f64 の下位 byte)・`0xc50f78`・`9a`→`9b` | `FAIL 定数 0x1051b78 = 0.05 (f64)`・`summary: 1 FAIL` | 1 |
| literal: `0x1051bf0` | VA `0x1051bf2` (2 文字目の `i`)・`0xc50ff2`・`69`→`78` | `FAIL literal 0x1051bf0 = ' is waiting for pickup: ' (UTF-16LE・NUL 終端)`・`summary: 1 FAIL` | 1 |

  再現 (bb の 1 件。他 2 件は offset と 1 バイトを変える): `N=<neg>/bb; mkdir -p $N/extracted && cp <展開先>/extracted/block00031_PE.bin $N/extracted/ && printf '\xfe' | dd of=$N/extracted/block00031_PE.bin bs=1 seek=$((0xc50c13)) conv=notrunc status=none; cmp -l <展開先>/extracted/block00031_PE.bin $N/extracted/block00031_PE.bin; FL_WIN64_DIR=$N python3 analysis/flapi/pe_bb_state_probe.py; echo "exit=$?"` → 出力は `FAIL` 1 件・`summary: 1 FAIL`・`exit=1`。正常系 (素材そのまま) は 17/17 PASS (上)。

## 1. 入口: 0x1051720 の呼出しと初期状態

- 直接 call 元は `0x1051d20` の 2 箇所 (0x1051ed1・0x1051f5a。`pe_callgraph.py callers`)。どちらも `mov edx, edi` で dl を渡す。`0x1051d20` の edi は REPORT_PY72 節 3 で 0 と確定しているため、本 run の経路では dl=0 (2 箇所目の edi は個別には未確認)。
- 冒頭で `[rbp+0xbb] = 0xff` (0x105180d)。`[rbp+0xac]` (ac) は初期化されない。
- 0xf82a10 の戻り値 (al) は 0x1051720 が見ない (0x105183d の後で bb だけを読む)。

## 2. 受入 1: `0xf82a10(G, key, dl, &ac, &bb)` の出力

引数 (0x105183d の呼出し): rcx = G (`[[0x15e0a00]]`)、edx = key (`[ctx+0x60]`)、r8b = dl、r9 = &ac (`[rbp+0xac]`)、stack[0x20] = &bb (`[rbp+0xbb]`)。

decode 関数 `0xf829c0(ctx, v)` (ctx = 0xf82a10 の frame):

- `*bb = (uint8)v`
- `*ac = (bb != 0) ? (((v >> 8) & 0xff) - 1) : 0` (dir ∈ {-1, 0, 1})
- `ctx.f5c = v >> 16`
- よって保存値 `v = bb | ((dir+1) << 8) | (tag << 16)`。

分岐 (dl=0 が本経路):

1. G の要素を走査 (`G+0x10` = 件数、`G+8` = 要素ポインタ配列)。`f8c9d0(item) == key` の item があれば `f829c0(ctx, item.+0xc)` で保存値を decode する。
   - `ctx.f5c ≠ 0` かつ `f8ca50(item) ≠ ctx.f5c` → `*ac = 0`・`*bb = 0`・`item.+0xc = 0` (**reset**)。戻り 1。
   - それ以外 → 保存値のまま。戻り 1。
2. 見つからず、`[0x15e47e8]` の参照先が非空なら `f783c0(key, &tmp)` を引き、真なら `f77330`・`f757a0`・`f75400(…, key)` の値を `f829c0` で decode。
3. それでも無ければ `f8ec70([0x16bacd8], key, &rec)` (表 T0。`f8e3f0` で引いて 36 バイト要素の 28 バイトを複写) が真のとき、`f829c0(ctx, rec の packed)` (`[rbp+0x48]`)。
4. いずれも無ければ `*bb`・`*ac` を書かずに戻る。`bb` は 0xff のまま。

bb の値の読み方 (0x1051720 側の分岐。確定):

| f82a10 が残した bb | 0x1051720 の経路 (行番号は 0x1051720 の listing) | f82c20 へ渡す bb | 戻り値 |
|---|---|---|---|
| 0 (reset) | path A: `ac = cur − new` (0x105184f)、`bb = (ac==0) ? 2 : 1` (0x1051869)、`dir = sign(ac)` で f82c20 | 1 または 2 | bb |
| 2 | 0x105194d の枝へ (al=1)・bb=2 のまま f82c20 | 2 | 2 |
| 1 | `sign(cur−new) ≠ ac` なら 11f1a20(null, 0) → bb=2 → f82c20。等しければ 10519c6 枝 (§5) | 2 / なし | 2 / 1 |
| 0xff (未発見) | 0x1051909 の枝。`al = (sign(cur−new) ≠ ac)`。**ac は未初期化** (下記注意) | 2 / なし | 2 / 0xff |

- `cur = 0x1046a30(key, 0, 2)` (0x105179e)、`new = 0x10469f0(0xf824b0(ptr, n), lo, hi)` (0x105180b)。`lo/hi` は `0x1050f90` が返す範囲 (`[rbp+0xb4]`・`[rbp+0xb0]`)。
- path A の符号決定: `|ac| < 0.05·(hi−lo)` のとき `ac` の符号を反転してから `sign` を取る (0.05 は `0x1051b78` の f64 値、0x1051896 の pand は絶対値)。

注意 (未確定・要確認): 0xff の経路で `ac` が初期化されていない。f82a10 の未発見経路は `ac` を書かないため、0x1051909 の比較は実行時の `[rbp+0xac]` の値に依存する。実行時値はこの解析では観測していない。

## 3. 受入 2: `0xf82c20(G, key, dir, flag, bb)` の引数と書込み先

引数 (0x10518ff・0x10519bc の呼出し): rcx = G (`*(*0x15e0a00)`)、edx = key、r8d = dir (sign ∈ {-1, 0, 1})、r9b = flag (= 呼出し元の dl)、stack[0x20] = bb。

- 保存候補 `v = (int)bb + ((dir+1) << 8)` (符号拡張 byte 加算。0xf82c20 の `movsx rdi, byte [rbp+0xb0]`)。
- 大域 **K = `0x16bacf0`** (dword) と **V = `0x16bacec`** (dword) (`pe_rip_consts.py` の解決。両方 `.bss`):
  - `key ≠ K` → V・K は変えず、以下の書込み値 `W = v`。
  - `key == K` かつ `flag ≠ 0` → `V ← v`、`W = (dir+1) << 8` (bb を落とす)。
  - `key == K` かつ `flag == 0` → `V ← (dir+1) << 8`、`W = v`。
  - (2 つの書込み命令 0xf82c55・0xf82c5f は同じ番地 V を指す)
- G の走査: `f8c9d0(item) == key` の item があれば `item.+0xc ← W + (f8ca50(item) << 16)` (`f8ca50 ≥ 0` のとき)。戻る。
- 見つからず、`[0x15e47e8]` の参照先が非空なら `f753f0(…, key, W)` (`f783c0` で真のとき)。
- 最後に表 T0 (`[0x16bacd8]`) で `f8ec70(T0, key, &rec)` を引き、真なら `[rbp+0x3c] ← W` の後 `f8e4e0(T0, key, &rec)` で更新する。`f8e4e0` は `T0` の vtable `+0x18` を 2 回呼ぶ (`call [rsi+0x18]` (rec, 5) と `call [rbx+0x18]` (payload, 1))。この呼出し先 (vtable の実体) は未読 (受入 4)。

production 呼出し (dl=0・flag=0) では `key == K` のとき `V ← (dir+1)<<8`、item / T0 へは `W = v` (bb 込み) が書かれる。

## 4. `f8c9d0` / `f8ca50` (item の key と tag)

- `f8c9d0(item)`: `id = item.+0x10` (dword)。上位 16bit が `0xfff` なら 0x11e83d0・0x11e8280 で解決し、`(id & 0xffff) | (解決値 << 16)`。上位 22bit が `0xff` なら `(id & 0x3fffff) + ([…] << 22) + 0x70000000` に変換。それ以外はそのまま。解決失敗は −1。
- `f8ca50(item)`: 同じ解決を行い、上位 16bit (解決値) を返す。`0xfff` で解決失敗なら −1。
- 0x1051720 の key は `((chan+0x794) & 0xffff) << 16 | 4` (REPORT_PY72 節 2)。上位 16bit = チャネル添字、下位 16bit = 4 (pitch 系の枝)。

## 5. 受入 3: 10519c6 枝 (0x10519c6〜0x1051b43)

枝に入る条件 (0x105194b): `bb == 1` (または 0xff) かつ `sign(cur−new) == ac`。枝内の命令列 (直接 store は `[rbp+...]` のみ。chan・G・V・K への store は無い):

1. `0x104f580(&[rbp+0x78], key, &[rbp+0x88], byte [0x1051be0] = 0)` — 表示用の対象オブジェクトを取得 (本体未読)。
2. `0x414c70(&[rbp+0xa0], [rbp+0x78], L" is waiting for pickup: ")` — 名前と文字列 `L" is waiting for pickup: "` (VA `0x1051bf0`・24 文字・NUL 終端) で文字列を組む。
3. `0x104d2b0(&[rbp+0x98], key, cur)` と `0x104d2b0(&[rbp+0x90], key, new)` — cur・new の値オブジェクトを作る (本体未読)。
4. `0x414e70([rbp+0x98], [rbp+0x90])` — 配列の要素数 (`[ptr−4]`) と要素を比べ、等しければ 0、違えば −1。
5. 等しい (eax = 0) なら: `v = new / hi × 100` (0x1051a43〜0x1051a53: `cvtsi2sd` で new と `[rbp+0xb0]` (hi) を割り、定数 0x1051b80 = 100.0 を掛ける) を `[rbp+0x58]` に置き、`0x43dd60(&[rbp+0x70], L"%.2f" (VA `0x1051c30`), &{v, tag 3}, 0)` で文字列化、`0x414c70(&[rbp+0x90], [rbp+0x70], L"%" (VA `0x1051c48`))` で連結。
6. `cur < new` なら `0x414da0(&[rbp+0xa0], 5, [rbp+0xa0], [rbp+0x98], L" " (0x1051c58), L" < " (0x1051c68), [rbp+0x90])`、`cur ≥ new` なら `0x414da0(&[rbp+0xa0], 5, [rbp+0xa0], [rbp+0x90], L" " (0x1051c58), L" > " (0x1051c7c), [rbp+0x98])`。`0x414da0` は 5 要素の引数ブロックを `0x4144a0(obj, id, block)` に渡す wrapper (0x414da0 の listing)。
7. `0x11f1a20(*(*0x15e0ff8), [rbp+0xa0], 0)` — 文字列を `[0x16bd1a0]` へ代入 (0x4133f0)、フラグ `[0x16bd1a8] = 0` (`sil`)、`0x423980`、`0xbd68e0(0xa, 0)` (UI 通知 id 0xa と推定。本体未読)。
8. `0x412e40` で `[rbp+0x70]`・`[rbp+0x88]` を解放し、`bb` (1 または 0xff のまま) を返す。f82c20 は呼ばれない。

副作用の結論 (枝の命令列に限る): 枝は値 (G・V・K・chan) を書かず、**表示用の文字列 (`L" is waiting for pickup: "`・`L"%.2f"` 等の組み立て) を作って UI の文字列とフラグを更新し、UI 通知を出す**。`0x104f580`・`0x104d2b0` の中身は未読のため、枝外への副作用 (オブジェクトの生成・解放) は未確定。

## 6. 未確定と移送先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 表 T0 (`[0x16bacd8]`) の vtable `+0x10`・`+0x18` の実体と、`0xf8e3f0`・`0xf8e4a0`・`0xf8ecd0`・`0xf8eb10`・`0xf8ea80` の本体 | 受入 4。`f8e4e0` の通知先が決まらない | 子 #3287 [PY-182] |
| item の tag `f8ca50` の意味 (`0x11e83d0`・`0x11e8280` の解決) と、保存 bb の運用 (reset の条件) | bb=0 (reset) の発生条件が確定しない | 子 #3287 [PY-182] |
| K `0x16bacf0` の書込み元 | V の意味 (どの key の保存値か) が確定しない | 子 #3287 [PY-182] |
| 10519c6 枝の `0x104f580`・`0x104d2b0`・`0x43dd60`・`0x414c70`・`0xbd68e0` と、`0x16bd1a0` の表示先 | 枝内の副作用の全量 (受入 3 の残り) | 子 #3288 [PY-183] |
| `0x414c70` で連結した表示文 (literal は §5 で確定済み。連結結果は未読) | 表示文の確定 | 子 #3288 [PY-183] |
| 0xff 経路の `ac` 未初期化読み | 実行時値に依存し、0 か 1 の分岐が変わり得る | 本 PR の注意 (§2)。経路上の判定は子 #3288 [PY-183] |
