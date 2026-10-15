# PY-72 付録 (#3213 / PY-170): setChannelPitch の書込み先 `0x1046a30`・登録表・`0x1051720` の戻り値

親: `tools/python/REPORT_PY72.md` の「追加解析 (PY-170 / #3213)」節。本文の行数上限 (250 行) のため分割移動 (内容は削除していない)。
前段: `tools/python/REPORT_PY72.md` の「追加解析 (PY-75 / #2562)」節。

## 追加解析 (PY-170 / #3213): 書込み先 (`0x1046a30`)・登録表・`0x1051720` の戻り値

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2576 (PY-77)。前段: 本ファイル「追加解析 (PY-75 / #2562)」節。

### 測定

- 測定 commit: `653d1603` (`origin/main` (`c6eca3e1`) を取り込んだ PR HEAD。取り込み前の測定 commit `80fb2fd0` からは解析コードが変わったため、本 HEAD で再測定した。`git diff 80fb2fd0 653d1603 -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 413 行)。本 run でコードは変更していない。本 PR は本ファイルだけ。`git diff 653d1603 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin` (2.8 秒。`block00031_PE.bin` は 22,227,016 バイト)。
- 実行: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <N>` (VA は `1046a30 1500`・`f8ecd0 1500`・`f8eb10 1500`・`f8ea80 1500`・`f8e3c0 400`・`f824b0 1500`・`1051720 1500`・`104cf90 260`・`1051c90 1500`・`f81ce0 1500`・`1051d20 330`・`f82a10 260`・`f82c20 200`・`10469f0 40`・`104a9ec 14`・`104aa87 12`・`104cc72 12`)、`pe_rip_consts.py 10469f0 10`・`pe_rip_consts.py 1047d75 40`。計 19 呼び出し (`pe_disasm.py` 17 + `pe_rip_consts.py` 2)、全て終了 0・Traceback 0 件。1 呼び出し 0.08〜0.09 秒 (合計 1.64 秒)。load average (1 分値) 0.92 (開始時 00:06 UTC)。出力は `tools/python/work/meas/` (gitignore)。

### 結論

**受入 1 (`0x1046a30` の n の書込み先): setChannelPitch の key (下位 16bit = 4) の枝について確定。書込み先は `[chan+0x174]`。`[chan+0x2f4]` (N) ではない。** `0x1046a30`・`0x104cf90` に `0x2f4` の直接参照は無い。
- 連鎖: `0x104cf90(key, n, flags)` → `0x1046a30(key, n, flags & ~0x14)` (`0x104cfa1`・`0x104cfa5`)。`0x104cf90` は後で flags&0x10 → `0x6667f0(…, 6, key, 0)`、flags&4 → `0x6667f0(…, 0x13, key, eax)` を呼ぶ (通知のみ)。PY-75 節の「最終書込み候補 `0x104cf90`」は、本節でラッパと確定した。
- 分岐: key < 0x10000000 (上位 16bit のチャンネル番号 < 0x1000) のとき `0x1047497` を経て `0x1047564` の switch (`key & 0xffff`) に入る。id 4 は `0x10475b9` (`sub 2; cmp 2; jb`) の後 `sub 2; je 0x1047d75`。`[rbp+0x4e8]` はチャンネル配列の `key>>16` 番目 (`0x10474d8`)。
- id 4 (`0x1047d75`): flags&0x20 のとき `n := 0x10469f0(n, -4800, 4800)` (`0xffffed40`・`0x12c0`)。flags&1 のとき `[chan+0x174] := n` (`0x1047dc4`) の後 `chan.vtbl[+0x128](chan)` を呼ぶ (前後を `0x4232e0`・`0x423980` で挟む。役割は未読)。flags&1 が 0 で flags&2 のとき `n := [chan+0x174]` (読出し、`0x1047e09`)。
- `0x10469f0(n, lo, hi)` は `lo + round((hi − lo) · n · 2^−30)` の線形写像 (定数 `[0x1046a20]` = 2^−30 を `pe_rip_consts` で確認)。n は 0〜2^30 の正規化値 (PY-75 の unit 0/1 の出力) で、範囲 [lo, hi] へ写す。
- 0x3fd からの呼出しの flags は `0x3e9` (= `0x3fd & ~0x14`)。bit 0x20 と bit 0x1 を持つので、この枝では `[chan+0x174]` への書込みになる。

**受入 2 (`0xf8ecd0`・`0xf8eb10`・`0xf8ea80` と pickupMode 0/1/2): 確定。** 3 箇所 (`0xf81cef`・`0xf81d06`・`0xf81d46`) が読む大域 `[0x16bacd8]` は同一で、登録表 T は 1 つ (名称は PE 文字列で未確認のため仮称しない)。
- `0xf8ecd0(T, key)` = contains: `0xf8e3f0(T, key, 0xf8e4a0(T, key)) ≥ 0`。
- `0xf8e3f0` = 探索: 線形探査。エントリは 36 バイト `{int h (−1 = 空); int key; byte payload[28]}`。見つかれば index (≥0)、無ければ `~空き位置` (<0)。一致判定は `T+0x18` の仮想関数 `[+0x18]`。
- `0xf8e4a0(T, key)` = h: `(T+0x18)->vt[+0x20]()` を `& 0x7fffffff`、`+1`、`& 0x7fffffff`。**key を使わない** (edx 未参照)。
- `0xf8eb10(T, key)` = erase: `0xf8e5f0(T, &out, key, h, flag=5)`。見つかれば payload を out へ写し、エントリを詰めて count−1、`T.vt[+0x10](T, key, flag)`・`T.vt[+0x18](T, &out, flag)` を呼ぶ。無ければ out を 0 埋め。
- `0xf8ea80(T, key, value*)` = insert: 満杯なら `0xf8e3c0` で拡張。呼出し側は未登録を前提 (登録済みのときは `0x448ee0`・`0x411e80` の経路に入る。未読)。空き位置に `0xf8e590` で payload を書き、count+1、`T.vt[+0x10](T, key, 1)`・`T.vt[+0x18](T, value, 1)`。
- `0xf81ce0(key, mode)` (`0xd5a720` の pitchUnit 0/1 で `mode = byte[ctx+0x30]` を渡して呼ばれる):

| T に key が | mode 0 | mode 1 | mode 2 | mode ≥ 3 |
|---|---|---|---|---|
| 有る | erase(T, key) | 何もしない | 何もしない | 何もしない |
| 無い | 何もしない | insert(T, key, payload) | 大域 `[[0x15e13b8]+0xf30]+0x49e` ≠ 0 のときだけ insert | 何もしない |

- insert する payload は `{+0x0c: 0, +0x10: key}` (`0xf81d3c`〜`0xf81d53`。先頭 0x0c バイトは未初期化)。
- 未確定: T の hook (`vt[+0x10]`・`vt[+0x18]`) の中身、大域 `0x15e13b8` の意味。

**受入 3 (`0x1051720(rbp, 0)` の戻り値 2 と flags&0x20 経路の書込み): 分岐は確定。`0x1051720` が戻り値を決める bb の生成元は未確定。**
- `0x1051d20` (ebx = bool = 0 の経路、0x3fd 呼出し): sil は `[[G_a]+0xf30]+0x49e ≠ 0` または `[[G_b]+0x10] > 0` (`0x1051e7e`)。
  - sil = 0: `n1 = f824b0([rbp+0x90], n)`・`n2 = 0x1051c90(rbp, n1)`・`0x104cf90(key, n2, flags)` (`0x1051f98`)。**書込みあり (`[chan+0x174]`)**。`0xf82c20` は呼ばない。
  - sil = 1 かつ flags&0x20 = 0: 同じ chain (書込みあり) の後、`0xf82c20(G, key, 0, edi, 0)` (`0x1051fcc`) で通知。
  - **sil = 1 かつ flags&0x20 ≠ 0 (0x3fd はこちら)**: `0x1051720(rbp, 0)` の戻り値 al が **2 のときだけ** chain (`0x1051f67`〜`0x1051f91`) で書込み。0 と 1 のときは書込み無しで終了 (`0xf82c20` も呼ばない)。
- `0x1051720` の戻り値は `[rbp+0xbb]` (bb)。初期値 0xff。`0xf82a10(G, key, dl, &ac, &bb)` の後:
  - bb = 0: `ac = bc − bx` (bc = `0x1046a30(key, 0, 2)` = 現在値。id 4 では読出しのみ。bx = `0x10469f0(n1, lo, hi)` = 目標値)。`bb = (ac == 0) ? 2 : 1`。`0xf82c20(G, key, sign(ac), flag, bb)` を呼び、bb を返す。
  - bb = 2 (`0xf82a10` の設定): `0xf82c20` を呼び 2 を返す。
  - bb = 1 かつ `sign(bc − bx)` と ac の符号が不一致: bb = 2 → `0xf82c20` → 2。一致: `0x10519c6` 枝 (`0x104f580`・`0x414c70`・`0x104d2b0`・`0x414e70`・`0x43dd60`・`0x414da0`・`0x11f1a20` 等を呼ぶ) → 1。
  - よって 2 を返すのは「現在値 = 目標値 (ac = 0)」・`0xf82a10` が 2 を設定・符号不一致の 3 通り。ac = 0 で chain (書込み) が走る点は意図と逆に見えるため、`0xf82a10`・`0xf82c20` の読解で確認する。
- `0x1046a30(key, 0, 2)` は id 4 で flags&1 = 0・flags&0x20 = 0 のため、`[chan+0x174]` の読出し (`0x1047dfc`) だけになる。ただし `0x1047e0f` の枝 (`[rbp+0x52e]` のとき `[[rbp+0x520]+0x940]` の vtbl `+0x1f0` を呼ぶ) は未確認。
- 未確定: `0xf82a10` の (ac, bb) 出力、`0xf82c20` の引数の意味、`0x10519c6` 枝の副作用、`0x1050f90` (lo/hi の出所)。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1046a30` の pitch 以外の id 枝・負の key・flags 0x3e9 の全経路・戻り値 eax・`0xf824b0`・`0x1051c90`・`0x1050f90` | pitch 以外の状態モデル・n の変換の確定 | #3252 (PY-175) |
| `0x1051720` の bb 生成元 `0xf82a10`・`0xf82c20`・`0x10519c6` 枝・登録表 T の hook | 戻り値 2 の意味と flags&0x20 経路の書込み条件の確定 | #3253 (PY-176) |
