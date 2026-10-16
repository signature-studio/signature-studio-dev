# #5491 (CI-228): COPY ERR_CAND の判定 (0x1280250 #1 の静的読み)

親 #4993 の残り。受入条件 2 (0x1280250 #1 の定数 0 の確認) を扱う。受入条件 1 (判定不能の分類) は部分達成。

## 1. 再現 (main `70a6f05db`・素材 fl-win64 `block00031_PE.bin`・work-m11 `boot_final3.ll`)

- scan: `COPY 49 関数 103 箇所` (issue 検証方法と一致)
- judge: `ERR_BARE 15 / UNCLEAR 14 / REWRITE_NOARG 4 / ERR_CAND 47 / MISMATCH 13 / OK_ARGK 10`
- classify (修正後): `ERR_CAND 47 件: 誤り 1 / 判定不能 44 / 正常な参照 2`
- 再現手順: `python3 tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/work/boot_final3.ll --pe <PE> --out S.json` → `python3 judge_copy_3382.py ... --scan S.json --out J.json` → `python3 classify_err_cand_4972.py J.json --md OUT.md`

## 2. 0x1280250 #1 (0x12802dd → 0x12802e2) の判定: 誤り (候補・静的読み)

IR は `%23 = call @function_73ca40(i64 0, i64 8)`。機械語は `rcx = [rsi]` (*arg2)。以下の逆アセンブル (PE 静的像) で、*arg2 が 0 でないことを示す。

1. `0x1280250`: `cmp qword [rsi],0` で *arg2 が null のときだけ `0x12802dd` 側の経路 (0x128027e → 0x12802dd) に入る。
2. `0x128028a`: `call 0x7372a0` (rcx = `[0x1280285 + rip-0xb4b63d]` = `[0x734c48]` = 0x734d10、dl=1、r8=0)。`0x128028f` で `*arg2 ← rax`。
3. `0x7372a0` (dl≠0): `0x7372c7` で `call 0x410320`。`0x410320` は dl ≥ 0 のとき `call [rax-0x30]` (rax = obj = 0x734d10)。`[0x734d10-0x30] = 0x40f960`。`0x7372cc` で `[rbp+0x60] ← rax`。
4. `0x737470`: `call 0x410360`。`0x410360` は vtable 呼出し (`[rbx-0x50]`) の結果を捨て、引数 rcx をそのまま返す。したがって `0x7372a0` の戻り値は step 3 の値 X。
5. `0x40f960(obj)` → `0x409410(movsxd [obj-0x80] = 0x500)` で X を得て、`0x40fb40(obj, X)` に渡す。`0x40fb40` は `mov rsi, rdx` (rsi = X) の後、`0x40fb66` で `[rsi] ← rdi` (obj) を無条件に書くので、X = 0 なら書込みで落ちる。`0x40fb40` は rsi (= X) を返す。`0x409410` は rcx > 0 なら間接 call `[0x13a5c90]` (静的値 0x407a50) で割当てる。割当失敗時のみ `0x409730` を経由する。
6. `0x12802dd`: `rcx = [rsi] = X` を `0x73ca40` の第 1 引数に渡す。

結論: 機械語が `0x73ca40` に渡すのは割当結果 X であり、IR の定数 0 とは一致しない見込み。

### 未確認 (この判定の限界)

- X の値は PE の静的像からの読み。実行時に 0x734c48 / 0x734d10 / [obj-0x80] が同じ値で初期化されるかは未実測。
- `0x407a50` の割当が成功するか、失敗時に `0x4096d0` がどう戻すかは未読。X=0 になるのは割当失敗経路だけと見ている。
- `0x410360` の vtable 呼出し `[rbx-0x50]` の副作用は読んでいない (戻り値は変わらない)。

### 0x73ca20 が *arg2 のスロットを書くか

`0x73ca20` は `[rcx+0x42c] ← edx` と `call [rbx+0x178]` (rcx = *arg2 の値) だけ。*arg2 の格納場所 (rsi が指す) は渡されないので、*arg2 の値を書き換えられない。受入条件 2 の後半 (0x73ca20 は書かない) は満たす。

## 3. 判定の変更

`tools/m11/ldfix/classify_err_cand_4972.py` の `SITE_VERDICT[('0x1280250','0x12802e2')]` を『保留』→『誤り (候補・静的読み)』にした。この 1 件のみ変更。

## 4. 残り (未達)

- 判定不能 44 件 (受入条件 1 の残り)。窓の外 (呼出し元・呼出し先の引数の意味) まで見る作業が要る。親 #4993 の本文にチェックリストとして残す。
- 0x1280250 #1 は『誤り (候補)』。X の実行時値を確かめる手段 (動的測定) は本 run では未実施。
