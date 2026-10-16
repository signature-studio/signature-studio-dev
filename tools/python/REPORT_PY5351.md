# PY-5351 (#5489): plugins.getPadInfo の PE 意味論 (引数・戻り値) の確定

親: #5106 (分割元 #4861)。device.getName (#3569・#4663) とは別の関数。

## 1. 結論

- **引数**: 確定。`index`・`slotIndex`・`paramOption`・`paramIndex`・`useGlobalIndex` の既定値と格納先を逆アセンブルで確認した (§2)。
- **解決 (channel・slot)**: 確定。PY-228 (getParamValueString) と同じ並び (slot -1 は `0x1005730`、slot ≠ -1 は mixer 配列) であることを VA 単位で確認した。
- **範囲外・空 slot の code**: 確定。-4 (範囲外)・-8 (空 slot)。
- **戻り値の値の核**: 一部確定。組替えの条件は経路で違う。slotIndex == -1 は `paramOption == 2` (`[rbp+0xa0]`)、slotIndex ≠ -1 は `paramIndex == 2` (`[rbp+0xa4]`) のとき、`eax` の byte0 と byte2 を入れ替える (マスク `0xff00ff`・`0xff00ff00`)。整数を `[0x15e4280]` が指すオブジェクトの vtbl[0] に渡す形まで確認。**vtable 先 (`[obj]->vtbl[+0x20]`・`[obj]->vtbl[+8]`) の実体は未確認。`[0x15e4280]` の指す先は `.bss` 内で、静的な PE には中身が無い。作られると推定 (作る箇所は未確認)**。
- C provider・mock の実装は、未確認点を残したまま行わない (親 #5106 の受入 4)。

## 2. PE の逆アセンブル (根拠)

`block00031_PE.bin` を capstone で読んだ。VA は ImageBase 基準。
`analysis/flapi/plugins_padinfo_facts.py` が下表の 47 行を assert する (実行結果: PASS 47 / FAIL 0)。

| 対象 | VA | 逆アセンブルの事実 |
|---|---|---|
| 引数 | `0xd811c0`・`flapi_kwargs.json` | fmt `i\|iiii`、kwlist `index, slotIndex, paramOption, paramIndex, useGlobalIndex`。`index` は必須 |
| 既定値 | `0xd811e6`〜`0xd81204` | slotIndex `0xffffffff` (-1)・paramIndex `0`・paramOption `0`・useGlobalIndex `0` |
| PyArg 解析 | `0xd81260`〜`0xd81267` | `call [0x15e45a8]` 相当 (間接呼出し)。格納先は `[rbp+0xac]`(index)・`[rbp+0xa8]`(slot)・`[rbp+0xa0]`(paramOption)・`[rbp+0xa4]`(paramIndex)・`[rbp+0x9c]`(useGlobalIndex) |
| 失敗時 | `0xd81271` | `jle` で `ebx ≤ 0` なら `0xd81492` へ (code を `0xd82c20` に渡す) |
| slot 判定 | `0xd81277`〜`0xd8127e` | `cmp [rbp+0xa8], -1` → `jne 0xd81374` (slot ≠ -1 は別経路) |
| channel 解決 (slot -1) | `0xd81284`〜`0xd812a2` | code -4 を仮置き、`ecx = index`、`dl = (useGlobalIndex > 0)`、`call 0x1005730`。偽なら `0xd81492` |
| 有効性 | `0xd812af`〜`0xd812bb` | `call 0x132f780` (`cmp [rcx+0x64], 0` の `setge`)。偽なら code -8 (`0xd81368`) |
| 値の取得 (slot -1) | `0xd812c3`〜`0xd812e1` | `call 0x1331340` で `obj` を得て、`[obj]->vtbl[+0x20]` を呼び、結果を `[rbp+0x88]` へ |
| 戻り値 (slot -1) | `0xd812f8`〜`0xd8135f` | 組替えの条件は `paramOption` (`[rbp+0xa0]`、`cmp` は `0xd812f8`)。`paramOption == 2` なら `[vtbl+8](obj, 0x35, paramIndex, paramOption)` の結果 `eax` を `and 0xff00ff`・`and 0xff00ff00`・`shl 0x10`・`shr 0x10` で組み替えて加算。それ以外は組替えなし。結果を `[0x15e4280]` が指すオブジェクトの vtbl[0] に `ecx` で渡し `[rbp+0x68]` へ |
| slot ≠ -1 の件数検査 | `0xd81374`〜`0xd8139d` | code -4。`index` が `[0..件数-1]` (件数は `[0x860e06]` 経由で読む `[0x15e2198]` 相当) の外なら `0xd81492` |
| slot の範囲 | `0xd813a3`〜`0xd813b7` | `slot < 0` または `slot > 9` なら `0xd81492` (code -4) |
| mixer 配列の参照 | `0xd813bd`〜`0xd813dd` | `[rip+0x85f2dc]` の指す基底、stride `0x28f*8` (`index*0x28f`)、オフセット `[rax+rcx*8+0x134c]` (`rcx = slot`) から `plugin` を取る |
| 値の取得 (slot ≠ -1) | `0xd813e8`〜`0xd813ff` | `0x1331340` → `[obj]->vtbl[+0x20]` → `[rbp+0x80]`。有効性は `0x132f780` (偽なら `0xd8148b` で code -8) |
| 戻り値 (slot ≠ -1) | `0xd8141e`〜`0xd81489` | slot -1 と同じ形 (組替え・`[0x15e4280]` のオブジェクトの vtbl[0])。ただし組替えの条件は **paramIndex** (`[rbp+0xa4]`、`cmp dword ptr [rbp + 0xa4], 2` は `0xd8141e`、`jne 0xd8145e` は `0xd81425`)。slot -1 の `paramOption` (`[rbp+0xa0]`) とは比較対象が違う |
| 終端 | `0xd81492`〜`0xd814b8` | `ebx` を `0xd82c20` に渡し、結果を `[rbp+0x68]` へ。`0x416230` を `[rbp+0x70]` 付きで呼んでから `[rbp+0x68]` を返す (`0x416230` の用途は未確認) |

## 3. 追加で確定した事実 (PY-5351 続き・2026-10-16)

| 対象 | VA | 逆アセンブルの事実 |
|---|---|---|
| 値の取得の補助 | `0x1331340`〜`0x133137f` | `Q = [plugin+0x38]` (`rax`)。`0x41a7b0(slot, Q ? Q+0x48 : Q)` を呼んで出力 slot (`rbx` = 呼出し側の `[rbp+0x78]` または `[rbp+0x70]` の位置) に代入し、その値が 0 なら既定値 `[0x63d9c6]` を代入する。`rax = rbx` を返す。`0x41a7b0` の中身は未確認 (代入と推定)。呼出し元は `0xd812ce` と `0xd813ec` |
| `[0x15e4280]` の格納値 | `.data` (VA `0x15e4280`、RVA `0x11e4280`。RVA `0x15e4280` は `.reloc` なので取り違えない) | 静的値 `0x016b8298` が入っている。この値は `.bss` (VA `0x15e6000`〜`0x196ee9c`) の内側を指す。`.bss` はファイル上 0 なので、オブジェクトは作られると推定 (作る箇所は未確認)。`rip` 相対の読出しは `0xd81356` と `0xd8147c` の 2 箇所で確認。rip 相対の書込みは簡易走査 (rel32 の総当たり。誤検出が多く確度は低い) では検出していない。間接書込みは未確認。`0xd81356` で `rax = [0x15e4280]`、`0xd8135d` で `call [rax]` (vtbl[0] を呼ぶ) |
| code 受けの関数 `0xd82c20` | `0xd82c20`〜`0xd82ded` | code == 0 は `[0x860485]` の判定 (`0xd82c3c`) を通り、真なら 0 を返す。code >= 0 で判定が偽のときは `0xc38bc0` で値を返す (`0xd82c55` → `jl` 不成立 → `0xd82c5c`)。code < 0 は `[obj]->vtbl[+0x88]` (`0xd82c7e`) の判定が偽なら `0xc38bc0`、真なら code の比較連鎖 (`cmp eax, -4` の `je` など) でコード別の文字列を作る。code -4 は `"Index out of range"` (`0xd82e8c`)、code -8 は `"Plugin not valid"` (`0xd82f3c`)。ただし -8 は vtbl[+0x88] が真のときの分岐で、`0xd82c20` 側の文字列の対応は比較連鎖から読んだもので、実行時の確認はしていない |
| 文字列 (コード別) | `0xd82e14`〜`0xd82f5c` | `OK`・`Unspecified error`・`Operation unsafe at current time`・`Range error`・`Index out of range`・`Wrong number of function parameters or wrong parameter type`・`Linked device not assigned`・`Device not assigned`・`Plugin not valid`・`Unknown error` (比較連鎖で選ぶ) |

## 4. 未確認 (推測で実装しない)

| 点 | 理由 | 起票先 |
|---|---|---|
| `[obj]->vtbl[+0x20]` (`0xd812de`) の関数の戻り値の型と意味。`obj` は `0x1331340` の `rdx` | 間接呼出しの先を読んでいない | 親 #5106 |
| `[obj]->vtbl[+8]` (`edx = 0x35`・`0xd8131a`) の実体。`0x35` が何を表すか | 同上 | 親 #5106 |
| `[0x15e4280]` の指す `0x16b8298` (`.bss`) の vtbl[0] (`0xd8135d`) の実体。オブジェクトを作る箇所 | `.bss` は静的に 0。作る箇所は実行時の書込みで、静的には特定していない | 親 #5106 |
| 組替え (`and 0xff00ff`・`0xff00ff00`) の**値の出所** (vtbl[+8] の戻り値)。条件は slot -1 が `paramOption == 2`、slot ≠ -1 が `paramIndex == 2` | 変換そのものは確定 (byte0 と byte2 の入替え)。入力の値は未確認 | 親 #5106 |

## 5. 再現

```
FL_WIN64_DIR=<fl-win64 の展開先> python3 tools/python/analysis/flapi/plugins_padinfo_facts.py
```

展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>`。
