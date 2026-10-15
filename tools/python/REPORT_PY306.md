# PY-306 (#4150): 効果関数 `0x1046a30` の負の key 残り 7 枝の n 書込み先

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #4107 (PY-299)。前段: `tools/python/REPORT_PY299.md` §4・§5。

## 結論

- 確定 (式): 7 枝の n の書込み先の式を、枝ごとに store 命令まで確定した (表 2)。
- 未確定 (VA): `0x104ae3d`・`0x104b1fd` の base は `[[rip+0x15e06a0]]` (`.data` の静的値 `0x16bd564` = `.bss`・zero-fill) を経由するため、実行時の値が無いと VA に落とせない。`0x104c2a6`・`0x104c64f`・`0x104c919` は静的 slot の値で VA が決まるが、その slot への PE 内の書込みは無いので、静的値を採る (実行時の書換えは PE 外の可能性として残る)。
- 確定 (式・store 先が呼出し先): `0x104ae3d` 枝の n は `call 0x12bdd40` の引数で渡り、callee が `*(int32*)(obj+0x138)` に書く。obj は chan 配列の要素。
- 確定 (固定 VA): `0x104c4af` 枝の n は `call 0x1311030` で固定 VA `0x196ec34` (.bss) に書かれる。`REPORT_PY299.md` §4 の「候補なし」は誤り。
- 確定 (固定 VA): `0x104c919` 枝の宛先 VA `0x15d8930` (`.data`) には、関数外の `0x1312c3e` に直接の書込みがある (`mov [rip+0x2c5cec], eax`)。この書込みの意味は未確認。
- 訂正: `REPORT_PY299.md` §4 の `0x104c2a6`「rax は `0x4232e0` の戻り値」は誤り。store の rax は lock の前に `[rip+0x15e36d8]` (値 `0x15c26e8`) から取る。
- 未確定 (子へ): global slot の実行時の値。`.text` 全体の走査で、7 枝が参照する slot への直接書込みと `lea` は 0 件。ただし slot の実行時の値を決める書込みが PE の外 (ロード後の初期化・別 block) にあるかは未確認。

## 測定

- 測定 commit: `681b9b3b9` (解析スクリプト `pe_py306_slot_writers.py` を追加した commit)。基点は `origin/main` = `c2f0e7ebf`。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2,324,302,252 バイト) から `extracted/block00031_PE.bin` (22,227,016 バイト) のみ展開。
- 走査: `analysis/flapi/pe_py306_slot_writers.py`。`.text` の全命令 (5,183,833 件)。測定 (HEAD `afb4b0218` 上で再実行): real 1m3.367s・user 59.093s・sys 4.267s・load 1 コア。終了 0。
- 逆アセ: `analysis/flapi/pe_disasm.py` と、解決用の一時 probe (`work/py306/`・gitignore 対象)。

## 1. 静的初期値 (`.data`)

| slot (link VA) | 初期値 (8 バイト) | 参照数 | 参照箇所 |
|---|---|---|---|
| `0x15e06a0` | `0x16bd564` | 26 | 0x104ae3d 枝・0x104b1fd 枝 (`0x104b2c5`・`0x104b023`・`0x104b065`) |
| `0x15e2198` | `0x14188a8` | 1 | 0x104b1fd 枝の添字上限 (`0x104b2b0`)。値は dword `502` |
| `0x15e2eb8` | `0x16ba6d0` | 7 | 0x104c2a6・0x104c64f 枝の vtable 呼出し用オブジェクト (`[[slot]]+0x9e0`・`+0xb28`)。store 先ではない |
| `0x15e36d8` | `0x15c26e8` | 3 | 0x104c2a6 枝の store 先 (`0x104c328`〜`0x104c335`) |
| `0x15e2110` | `0x16bcc84` | 1 | 0x104c2a6 枝の store 先 (`0x104c3bd`〜`0x104c3ca`) |
| `0x15e2c50` | `0x16bcc88` | 2 | 0x104c64f 枝の store 先 (`0x104c6dd`〜`0x104c6ea`) |
| `0x15e28c8` | `0x15d8930` | 3 | 0x104c919 枝の store 先 (`0x104c9b3`〜`0x104c9c0`) |
| `0x15e3d40` | `0x16b6aa8` | 12 | lock (`0x4232e0`・`0x423980`) の引数 |

直接書込みの確認 (`.text` 全体): slot 側 (上表の `0x15e...`) への直接書込みと `lea` は 0 件。store 先の VA 側 (`0x14188a8`・`0x15c26e8`・`0x16bcc84`・`0x16bcc88`) も 0 件。例外: `0x15d8930` に 1 件 (`0x1312c3e`)、`0x196ec34` に 1 件 (`0x1311030`)。

## 2. 7 枝の store 先

| 枝 | store 命令 (枝の範囲内) | 式 | 状態 |
|---|---|---|---|
| `0x104ae3d` | `call 0x12bdd40` (`0x104b051`・`edx = [rbp+0x5b8]` = n)。`0x104af9d je 0x104b023` の経路 | `*(int32*)(obj+0x138) = n`。`obj = *([[rip+0x15e06a0]] + (chan·0x28f)·8 + 0x134c + sub·8)`。`chan=[rbp+0x578]`・`sub=[rbp+0x574]` | 式確定。obj の実値は未確定 (base の実値が必要) |
| `0x104b1fd` | `mov [rax], ecx` (`0x104b3bc`)。`rax = [rbp+0x3d8]`、`[rbp+0x3d8] = [rbp+0x3e0] + [rbp+0x580]·8 + 0x394`、`[rbp+0x3e0] = [[rip+0x15e06a0]] + (chan·0x28f)·8` | `*(int32*)([[rip+0x15e06a0]] + (chan·0x28f)·8 + [rbp+0x580]·8 + 0x394) = n`。添字 `[rbp+0x580] = key_low16 − 0x70002000` (`0x104b2aa`)。上限は `cmp ecx, [[rip+0x15e2198]]` (= 502) | 式確定・上限の静的値確定。base の実値は未確定 |
| `0x104c2a6` | `mov [rax], ecx` (`0x104c335`・`0x104c3ca`) | `rax = [rip+0x15e36d8]` (`0x15c26e8`) または `[rip+0x15e2110]` (`0x16bcc84`) | 式確定。宛先は静的値。ただし `0x15c26e8` は PE 内の書込みなし |
| `0x104c4af` | `call 0x1311030` の引数 `ecx` (n) → `mov [rip+0x65dbfe], ecx` | 固定 VA `0x196ec34` (.bss)。`0x1311030` の呼出し元経路の確認は未了 | 式確定 (固定 VA) |
| `0x104c64f` | `mov [rax], ecx` (`0x104c6ea`)。`rax = [rip+0x15e2c50]` | `*(int32*)0x16bcc88 = n` | 式確定 |
| `0x104c919` | `mov [rax], ecx` (`0x104c9c0`)。`rax = [rip+0x15e28c8]` | `*(int32*)0x15d8930 = n`。`0x1312c3e` に直接書込みあり | 式確定・宛先の別書込みを確認 |
| `0x104caae` | 終端。`0x104cb89`・`0x104cc10` は配列 push | n の格納ではない | REPORT_PY181 §3 と同じ |

## 3. 未確定と子

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `[[rip+0x15e06a0]]` (`0x16bd564`・`.bss`) の実行時値 | `0x104ae3d`・`0x104b1fd` の obj・base の VA | 未起票 (PY-299 #4107 の残件として PM 判断) |
| `0x15d8930` への `0x1312c3e` の書込みの意味 | `0x104c919` 枝の宛先が n か | 未起票 (同上) |
| `0x1311030` の呼出し元経路 (`0x104c4af`) | 固定 VA `0x196ec34` に書く n の意味 | 未起票 (同上) |
| 静的 slot の実行時書換え (PE 外の初期化) の有無 | `0x104c2a6`・`0x104c64f`・`0x104c919` の VA | 未起票 (同上) |
