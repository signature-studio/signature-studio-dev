# PY-181 (#4109 / 親 #3282): `0x1050f90` の本体・`0xffac50` の判定条件・マスク `[rip+0x5d]` の実値

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3282 (PY-181)。関連: `tools/python/REPORT_PY175.md` (未確定の一覧)・`tools/python/REPORT_PY73.md` §8-2 (事象表の遅延キャッシュ)・`tools/python/REPORT_PY72_APPENDIX_3213.md` (sil=0 / bb=0 枝の式)。

## 結論

- 確定 (`0x1050f90(key=ecx, &lo=rdx, &hi=r8)` の本体): 事象表 (件数 `[0x15e4868]→[+0x10]`、配列 `[0x15e4868]→[+8]`、要素 `[item+0]`=key・`[+4]`=lo・`[+8]`=hi・`[+0xc]`=flags) を key で二分探索する。見つかれば lo・hi・flags をそのまま返す。
- 確定 (not-found 時、0x105103e〜0x1051161): flags = `0x104d0d0(key)`。flags & 2 なら lo=0・hi=0x100000。そうでなければ lo = `0x1046a30(key, 0, 0x20)`、hi = `0x1046a30(key, 0x40000000, 0x20)` (ただし hi ≥ lo+1 に丸める)。その後、表の挿入位置を再探索して `0x664090` で要素を追加し、key・lo・hi・flags を書く (0x105112f〜0x1051155)。戻り値は flags (`al`)。
- 確定: lo・hi は `0x10469f0(n1, lo, hi)` (目標値) の入力。`0x1050f90` 自身は n を変換しない。
- 確定 (n → n1 → n2 の入口。呼び出し元の式で確認): `n1 = 0xf824b0(ptr, n)` は ptr が null なら `n` をそのまま返す (0xf8250b)。非 null なら `n` を float に換算して `0xf823f0` で範囲を挟み、`0x40c660` で丸めて返す (0xf824b4〜0xf82504)。`n2 = 0x1051c90(obj, n1)` は `obj[0x60]` の下位 16bit = 4 かつ `obj[0x70] & 0x20` かつ `obj[0x60] >> 16` が有効範囲のときだけ `0x661450` で写像し、それ以外は `n1` をそのまま返す (0x1051c96〜0x1051d0e)。
- 確定: `0xffac50(obj=rcx)` は、`obj[0x160]` (id) が {1,4,5} のいずれか (マスク `0x32` の bit) なら 0 を返す。それ以外は `0x12f9ed0()` の件数 count 個について `0xffaea0(obj, i) ≥ 0` となる i が 1 つでもあれば 1、無ければ 0。
- 確定: `0xffaea0(obj, i)` は、`obj[0x794] < 0` なら -1。そうでなければ `0x12f9ec0(i)` の配列を走査し、`entry[+0xe0] == obj[0x794]` かつ `entry[+0xd8] == 3` となる最初の配列要素の値 (`ecx`) を返す。無ければ -1。
- 確定: マスク `byte [rip+0x5d]` (VA `0xffacd8`。読出し命令 `0xffac73` の次命令 `0xffac7b` + 0x5d) の実値は **`0x32`** (bit 1・4・5)。`.text` 内の 4 byte は `32 cc cc cc`。
- 確定: `0x12f9ed0()` は `[0x196eb60]` の件数 (`[ptr-8]`、null なら 0) を返す。`0x12f9ec0(i)` は `[0x196eb60]` の配列の i 番目の要素を返す。
- 未確定: `0xf823f0` と `0x40c660` の正確な変換式、`0x661450` の写像、`0x10469f0` の係数 `[rip+0x1d]` の値。`0x1046a30` の本体 (効果関数) は PY-175 の範囲。key 8 の書込み条件 (`(eventId & 0xffff) == 8`) とマスク `0x32` の対応は、本 issue の範囲では確定していない。

## 測定

- 測定 commit: `6b7ca07b4` (コードを変えた最後の commit)。本 PR はアナリシス・コードを変更していない (追加は REPORT のみ)。`git diff 6b7ca07b4 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` は 0 行。
- 素材: `fl-win64.tar.zst` の `block00031_PE.bin` (22,227,016 byte) を `$RUNNER_TEMP/fl/extracted` に展開 (`tar --zstd -xf ... extracted/block00031_PE.bin`)。
- 逆アセ (`analysis/flapi/pe_disasm.py`、`FL_WIN64_DIR=$RUNNER_TEMP/fl`): `0x1050f90` 200 命令・`0xffac50` 60 命令・`0xffaea0` 80 命令・`0x12f9ed0` 80 命令・`0x12f9ec0` 30 命令・`0xf824b0` 45 命令・`0x1051c90` 45 命令・`0x10469f0` 40 命令。全て終了 0。
- 定数 (`pe_rip_consts.py 0xffac50 40`): slot `0xffacd8` を解決。f32 の表示は `-107372944.0` だが、マスクは byte として使われるので、バイトの実値 `32` を採る。

## 0x1050f90 の要点 (アドレスは PE の VA)

| 区間 | 動作 |
|---|---|
| 0x1050fb4〜0x105103c | 事象表の二分探索。見つかった要素 (0x1051019) は lo・hi・flags を返して終わる (0x1051161) |
| 0x105103e〜0x1051068 | not-found。`0x104d0d0(key)` で flags。flags & 2 なら lo=0・hi=0x100000 |
| 0x105106e〜0x10510a8 | not-found (flags & 2 == 0)。lo = `0x1046a30(key,0,0x20)`、hi = `0x1046a30(key,0x40000000,0x20)` を lo+1 以上に丸める |
| 0x10510aa〜0x105112f | 挿入位置の再探索。`0x664090` で要素を確保して key・lo・hi・flags を書く |
| 0x1051161 | 戻り値 `edi` = flags |

## 0xffac50 の判定

- 0xffac59〜0xffac7d: id = `[obj+0x160]`。id ≤ 7 かつ `(1 << id) & 0x32` ≠ 0 なら戻り 0 (0xffacc9)。
- 0xffac8d〜0xffacc6: `count = 0x12f9ed0()`。i を 0 から count−1 まで走らせ、`0xffaea0(obj, i) ≥ 0` で戻り 1。

## 解けなかったこと (子 issue へ)

- `0xf823f0`・`0x40c660`・`0x661450`・`0x10469f0` の係数の具体値 (n → n1 → n2 の式の確定)。→ #4181 (PY-307)
- key 8 の書込み条件とマスク `0x32` の対応 (`0xffac50` の id 1・4・5 の意味づけ)。→ #4182 (PY-308)
