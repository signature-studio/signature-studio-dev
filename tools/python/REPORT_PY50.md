# PY-50 (#1829): chan フィールド・0xffa6d0 戻り値・status 写像の確定

親: #1765。前段: `REPORT_PY38.md` (未確定 3 点)・`REPORT_PY41.md` (分割元)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- 受入条件 3 件のうち **2 (0xffa6d0) と 3 (status 写像) は確定**。**1 (フィールド) は `+0x739` のみ確定**で、`+0x794`・`+0x79c` は未確定 (下記)。
- 0xffa6d0 の戻り値 2 は「`chan+0x718` が非 0 (対象あり) かつ `byte [chan+0x79c]` が 0」。
- `finish` の status 写像 (0 / -1〜-10) を分岐表から確定した。`-9`・`-10` と範囲外は `Unknown error`。
- 受入条件 1 (フィールドの意味) は `+0x739` のみ挙動で確定。`+0x794`・`+0x79c` の名前は未確定 (下記)。
- コード変更は 0 件。provider / host / tests は未変更。実装は本 issue の範囲外 (`REPORT_PY41` の [PY-41] 側)。

## 測定条件

- 素材: `fl-win64.tar.zst` → `flstudio_win64_26.1.7.5653.exe/extracted/block00031_PE.bin` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`、展開 3.0 秒・実測)。展開先は `tools/python/work/py50/` (gitignore)。
- 逆アセンブル: `python3 tools/python/analysis/py41_disasm.py <PE> <VA>` (capstone・pefile)。`ret` で止まるため、`finish` 分岐は全域を逆アセンブルして確認した。
- 測定 commit: `d3fe5a00` (コードを変えた最後の commit)。
- 鮮度の証跡: `git diff d3fe5a00 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (実測・HEAD で再確認)。provider / host / tests は未変更のため再測定は不要 (`docs/WORKFLOW.md` §6)。

## 1. `chan` のフィールド (PE 解析箇所)

| フィールド | 型 | 挙動 (PE 箇所) | 暫定名 |
|---|---|---|---|
| `+0x718` | qword (ポインタ) | `0xffa6d0` で `cmp qword [rcx+0x718],0` (0xffa6d0)。`0xdbde61` で非 0 を要求 | 対応オブジェクトへのポインタ |
| `+0x714` | dword | `0xdbde6b`〜: `[+0x714]` を global 値と比較して一致を要求 | 対応オブジェクトの ID |
| `+0x739` | byte (flag) | 書込 `0x10445a3` (`mov byte [rax+0x739], dil`)。`dil = 1` を基本とし、別配列要素の `+0x32c == 0` かつ引数 `[rbp+0x3f]` 非 0 のときだけ `dil = 0`。読出 `0xdbdd6f`・`0xdbde7c` (非 0 を要求) | reroll 対象フラグ (挙動から。名前は暫定) |
| `+0x738` | byte | `0xdbde85` で 0 を要求 | 除外フラグ (推定。書込箇所は未確認) |
| `+0x794` | dword | `0xdbdec6` で `mov eax,[rax+0x794]` を読み、配列 (`rbp+0x38`) に格納する。`0xdbdd50` の `edx` 引数も同じ値 (`REPORT_PY38` の記述) | 対応先の値 (ID か index か未確定) |
| `+0x79c` | byte 読出 / dword・qword 書込 | 読出は `0xffa6d0` の gate (`!= 0` で戻り値 1/2 を分ける)。書込は dword (`0xec7bb8`・`0xec6098`、TPlugListForm の所有域) と qword (`0xdd2002`、TPRBaseToolForm の所有域) の 2 型。**別構造体の同オフセット** (REPORT_PY59 §9-6・#2471) | 名前未確定。「starter 有効」は推定 |

`0xfe8bb0` は `arr[index]` (index 範囲 `0..count-1`、範囲外は NULL) と確認した。`+0x79c` の書込幅の不一致は、REPORT_PY59 §9-6 で**別構造体の同オフセット**と確定した (qword は TPRBaseToolForm、dword は TPlugListForm)。`0xffa6d0` の byte 読出しは chan の別系統で、chan の型は未同定 (REPORT_PY59 §9-7)。

## 2. `0xffa6d0` の戻り値

`0xffa6d0` は `chan` (rcx) を引数に取り、次の 3 値を返す (全命令を確認)。

| 戻り値 | 条件 |
|---|---|
| 0 | `chan+0x718 == 0` (対応オブジェクトなし) |
| 1 | `chan+0x718 != 0` かつ `byte [chan+0x79c] != 0` |
| 2 | `chan+0x718 != 0` かつ `byte [chan+0x79c] == 0` |

`rerollLoopStarterSteps` / `Sample` の `index == -1` 走査で「戻り値 2 の chan を選ぶ」は、「対応オブジェクトはあるが starter 無効」の chan を対象にすることを意味する (`REPORT_PY38` の記述と整合)。

## 3. status 写像 (`finish`、全分岐表)

`finish` は status (`[rbp+0x24]`) を分岐して文字列を組み立てる (`0xd82c8c`〜)。分岐の到達先を文字列の `lea` 先まで辿った結果:

| status | 文字列 | 分岐の根拠 |
|---|---|---|
| 0 | `OK` | status+3 を 3 回減算して 0 になる経路 (`0xd82cee`) |
| -1 | `Unspecified error` | `0xd82d03` |
| -2 | `Operation unsafe at current time` | `0xd82d18` |
| -3 | `Range error` | `0xd82d2a` |
| -4 | `Index out of range` | `cmp eax,-4; je 0xd82d3c` |
| -5 | `Wrong number of function parameters or wrong parameter type` | `0xd82d4e` |
| -6 | `Linked device not assigned` | `0xd82d60` |
| -7 | `Device not assigned` | `0xd82d72` |
| -8 | `Plugin not valid` | `0xd82d84` |
| -9・-10・その他 | `Unknown error` | `0xd82d96` (既定分岐) |

`finish` の分岐に現れる文字列は上表の 10 種。`Invalid value` は PE 内に 13 回出現するが `finish` の分岐には現れない (別箇所の用途は未確認)。`fl_api.h` の数値割当 (1〜8) は従来どおり暫定で、実エンジンの数値とは対応しない。
`status` が `finish` の第 1 引数 (`[rbp+0x24]`) であることは、関数の prologue を未確認のため推定 (分岐の整合性から妥当と判断)。

## 未確定 (残す)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `+0x794`・`+0x79c` の名前 (書込幅の不一致は REPORT_PY59 §9-6 で別構造体と確定) | 受入条件 1 が未達。rerollLoopStarter* の chan 対応付けが確定しない。[PY-51] で部分確定 (`+0x79c` は byte flag、`+0x794` は配列添字と判明。詳細は `REPORT_PY51.md`)。chan の型は REPORT_PY59 §9-7 | #1871 ([PY-51]) |
| `0x1046a30` の本体 (`setSwing` / `getSwing`) | `REPORT_PY41` の未確定 | [PY-41] (#1514 系) |
| C 実装・mock 差分 0・`all_tools.mjs` 48/48 | 受入条件は本 issue の範囲外 | [PY-41] |
