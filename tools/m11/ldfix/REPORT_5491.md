# #5491 (CI-228): COPY ERR_CAND の判定 (0x1280250 #1 の静的読み)

親 #4993 は CLOSED のため、残りの追跡先は #5491 とする。受入条件 2 (0x1280250 #1 の定数 0 の確認) を扱う。受入条件 1 (判定不能の分類) は部分達成。

## 1. 再現 (main `70a6f05db`・素材 fl-win64 `block00031_PE.bin`・work-m11 `boot_final3.ll`)

- scan: `COPY 49 関数 103 箇所` (issue 検証方法と一致)
- judge: `ERR_BARE 15 / UNCLEAR 14 / REWRITE_NOARG 4 / ERR_CAND 47 / MISMATCH 13 / OK_ARGK 10`
- classify (修正後): `ERR_CAND 47 件: 判定不能 45 (うち保留 1) / 正常な参照 2`。誤り 0。judge の JSON は `work-m11` が無いため再生成せず、スクリプトの集計 (`v.split(' (')[0]`) から算出
- 再現手順: `python3 tools/m11/ldfix/scan_spill_deref_3328.py tools/m11/work/boot_final3.ll --pe <PE> --out S.json` → `python3 judge_copy_3382.py ... --scan S.json --out J.json` → `python3 classify_err_cand_4972.py J.json --md OUT.md`

## 2. 0x1280250 #1 (0x12802dd → 0x12802e2) の判定: 保留

IR は `%23 = call @function_73ca40(i64 0, i64 8)`。機械語は `rcx = [rsi]` (*arg2)。逆アセンブルは PE の `.text` (file offset 0x400 = VA 0x401000) で行った (`objdump -D -b binary --adjust-vma=0x400c00`)。

確認できた機械語:

1. `0x1280261`: `cmp qword [rsi],0`。`*arg2 != 0` なら `0x128026e` の経路 (`0x1280170`)。`*arg2 == 0` なら `0x128027e` に入る。
2. `0x128028a`: `call 0x7372a0` (rcx = `[0x734c48]`、dl=1、r8=0)。`0x128028f` で `*arg2 ← rax`。
3. `0x7372a0` は `dl ≠ 0` のとき `0x7372c7` で `call 0x410320` (`rcx = obj`)。`0x410320` は `dl ≥ 0` のとき `call [rax-0x30]`。`0x7372cc` で戻り値を `[rbp+0x60]` に格納し、以降 `0x7c7ac0`・`0x8226a0` を呼ぶ。`0x737304` 付近で `rax ← [rbp+0x60]` を読むが、`0x7372a0` の最終的な戻り値の決定経路は `0x737300` 以降を読んでいない。
4. `0x40f960(obj)`: `movslq [obj-0x80]` を rcx として `0x409410` を呼び、その結果を `0x40fb40(obj, rax)` に渡す。`0x40fb40` は `[rsi] ← rdi` (obj) を書く。

未確認 (X=0 の排除に必要):

- `0x409410`: rcx > 0 なら `call [0x13a5c90]` (rax → rbx)。rbx = 0 なら `cl=1` で `0x409730` を呼ぶが、`0x409730` は `push rbp; sub rsp,0x20` で始まる別の関数で、その戻り値は rbx に反映されない (0x409433 は rbx を返す)。つまり割当が 0 を返せば X = 0 になる。`[0x13a5c90]` の実行時値と、`0x7372a0` の戻り値の決定経路は未確定。

### 0x73ca20 と 0x7372a0 が *arg2 のスロットを書くか

- `0x73ca20` は `*arg2` の値 (rcx) を受け取り、`[rcx+0x42c] ← edx` と間接 call を行う。*arg2 のスロット (rsi が指す `[rsi]`) は渡されないので書き換えられない (受入条件 2 の後半)。
- `0x7372a0` も同様に `*arg2` のスロット (`[rsi]`) を渡されない。`0x128028a` の呼出しは rsi を渡さず、`0x7372a0` は rcx・dl・r8 しか受け取らないので、`*arg2` の格納場所に到達しない。`0x128028f` の書込みは呼出し元 `0x1280250` 側の `[rsi]` であり、`0x7372a0` の内部からは書かれない。

## 3. 判定の扱い

`tools/m11/ldfix/classify_err_cand_4972.py` の `SITE_VERDICT[('0x1280250','0x12802e2')]` は『判定不能 (保留)』に戻した。理由は 2 節の未確認 (割当失敗後の戻り値・`[0x13a5c90]` の実行時値・`0x7372a0` の戻り値の末尾)。

## 4. 残り (未達)

- 判定不能 44 件 + 保留 1 件 (受入条件 1 の残り)。窓の外 (呼出し元・呼出し先の引数の意味) まで見る作業が要る。起票先は #5491 (本 issue)。
- 0x1280250 #1 の X の値 (定数 0 か否か) は未確定。`0x409410` の割当失敗時の戻り値の規則・`[0x13a5c90]` の実行時値・`0x7372a0` の戻り値の決定経路の確認が要る。起票先は #5491。
