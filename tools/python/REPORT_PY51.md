# PY-51 (#1871): chan の +0x794 / +0x79c の意味と書込幅不一致

親: #1765。前段: `REPORT_PY50.md` (未確定 2 点)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- `+0x79c` (byte flag): `0xffa6d0` の gate として読まれ、chan の生成・初期化経路で byte として書かれる。byte 書込みの大半は chan 系の経路。FLP 側 `ChannelFlags51` の bit2 から書かれる箇所 (`0xf4c976`) がある。名前は暫定 `chan.flag51Bit2`。
- `+0x79c` の dword・qword 書込み (`0xdd2002`・`0xec7bb8`・`0xec6098`) は chan 生成経路ではなく、別構造体への書込みと判断した (推定)。書込幅不一致は「同じオフセットを別構造体が使う」として扱える。
- `+0x794` (dword): chan 配列の添字として使われる。`0xdbdec6` で chan の `+0x794` を配列に格納し、`0xdbdd50` が `0xfe8bb0(arr, value)` で添字として引く。名前は暫定 `pairedChanIndex`。chan 上でどこで書かれるかは未確定。
- 受入条件の達成: 1 (`+0x794`) は部分達成、2 (`+0x79c` 幅不一致) は部分達成、3 (未確定表の更新) は達成。

## 測定条件

- 素材: `fl-win64.tar.zst` → `flstudio_win64_26.1.7.5653.exe/extracted/block00031_PE.bin` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`、展開 2.8 秒・実測)。展開先は `tools/python/work/py50/` (gitignore)。
- 解析: capstone による線形走査は途中の不正命令で止まり、`.text` 全域を走査できなかった。そこで displacement のバイト列 (`0x794`・`0x79c` の LE 4 バイト) を検索し、各ヒット位置を含む命令を個別に復号した。ヒット数は `+0x794` が 470 件 (メモリ参照 466 件)、`+0x79c` が 90 件 (メモリ参照 83 件)。
- 測定 commit: `576c4976` (作業開始時の origin/main)。
- 鮮度の証跡: `git diff d3fe5a00 HEAD -- tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (実測・HEAD で確認)。解析のみで provider / host / tests は未変更のため、再測定は不要 (`docs/WORKFLOW.md` §6)。

## 1. `+0x79c` (byte flag)

### 1-1. 読出し

- `0xffa6d0` (chan 対応の戻り値関数): `cmp qword [rcx+0x718],0`、続けて `cmp byte [rcx+0x79c],0`。戻り値は 0 (`+0x718==0`)・1 (`+0x718!=0` かつ `+0x79c!=0`)・2 (`+0x718!=0` かつ `+0x79c==0`)。REPORT_PY50 の表と一致。
- 呼出し元: `0xd5d3a7`・`0xd5d403`・`0xd5d6a1`・`0xd5d741`・`0xdbe3d1`。`0xdbe3d1` では `0xfe8bb0` で取った要素を渡す。
- 他の byte 読出し (`cmp byte [rax+0x79c],0` 等) は別構造体の場合もあり、本件の範囲では分類しない。

### 1-2. byte 書込み (chan 系の経路)

| VA | 書込み | 文脈 |
|---|---|---|
| `0xdc1540` | `mov byte [rbx+0x79c],1` | chan 生成 (`0xdc1440`)。`0xfe8bb0` で取った要素 `rbx` に、直後 `[rbx+0x79d]=1`、`0xfeaab0` を呼ぶ |
| `0xdc107f` | `mov byte [rbx+0x79c],0` | chan 初期化 (`0xdc1060`)。`[rbx+0x714]` を global 値で設定した直後 |
| `0xdbe405` | `mov byte [rbx+0x79c],0` | `0xdbe3c0`。`rbx = 0xfe8bb0(...)`、`0xffa6d0` の結果が非 0 の分岐で 0 にする |
| `0xf4c976` | `mov byte [rax+0x79c],cl` (`cl = test(flags,4) != 0`) | FLP イベント `ChannelFlags51` のデコード。`[rbp+0x9e8]` は同じ分岐で `+0x738` (`0xf4c91e`)・`+0x79d` (`0xf4c94a`) にも書く |
| `0x130716f` | `mov byte [rax+0x79c],1` | 別経路 (未分類) |
| `0x130f821` | `mov byte [rbx+0x79c],0` | 別経路 (未分類) |

`0xf4c976` は `tools/flp/src/events.ts` の ChannelFlags51 (`bit0 -> +0x738, bit1 -> +0x79d, bit2 -> +0x79c`) と一致する。

### 1-3. dword・qword 書込み (別構造体と判断)

| VA | 書込み | 判断 |
|---|---|---|
| `0xdd2002` | `mov qword [rax+0x79c],rcx` | `0xdd1fa3` の初期化。同じ関数で `+0x790` (qword)・`+0x798` (byte)・`+0x7ad` (byte) も書く。chan の既知フィールド (`+0x714`・`+0x718`・`+0x738`・`+0x739`) と重ならない。対象構造体は chan と同定していない |
| `0xec7bb8` | `mov dword [rax+0x79c],esi` | 対象 `[rbp+0x48]`。chan 生成経路 (`0xdc1440`) とは別の経路。構造体の同定は未確定 |
| `0xec6098` | `mov dword [rax+0x79c],ecx` | 対象 `[rbp+0x120]`。直前で `[rax+0x7e0]==1` を判定し、直後に `[rax+0x794]` も書く。chan 側の `0xfe8bb0` 由来ではない |

判断: dword・qword の書込みは、chan の `+0x79c` (byte) とは別構造体のフィールドと推定する。同一構造体の同一フィールドを幅違いで書いている証拠は見つからなかった。ただし `0xdd2002` と `0xec7bb8` は構造体の同定が未確定のため、推定に留まる。

### 1-4. 暫定名

- `chan.+0x79c` は byte flag。名前は暫定 `chan.flag51Bit2`。FLP 側の bit2 の意味は未確定で、PE 側の書込みは `0xf4c976` (上表) のみ確認した。
- 「starter 有効」は根拠が不足するため採用しない (REPORT_PY50 の推定を撤回)。

## 2. `+0x794` (dword)

### 2-1. 読出し

- `0xdbdec6`: `mov eax,[rax+0x794]` を配列 (`rbp+0x38`) の `rdx` 番目へ格納する。`0xdbde10` の走査で、`[+0x718]!=0`・`[+0x714]==global`・`[+0x739]!=0`・`[+0x738]==0` を満たす要素だけを対象にする。
- `0xdbdd50`: `edx` (= `+0x794` の値) を受けて `0xfe8bb0(arr, edx)` で要素を取り、その `+0x739` を判定する。その後 `0xdc27c0` に配列 (`rdx = &value`) を渡す。

`0xfe8bb0(arr, idx)` は `arr[idx]` (範囲外は NULL) であり、`+0x794` は配列の添字として使われる。

### 2-2. 書込み

- chan 生成経路 `0xdc1440`〜`0xdc1710` には `+0x794` への書込みがない。
- 他の書込み (`0x1306dbf`・`0x1307608` の global 系、`0xec60ae` の `[rbp+0x120]` 上の dword 書込み) は、対象が chan であることを確認していない。
- chan 上で `+0x794` が書かれる箇所は未特定。

### 2-3. 暫定名

- `pairedChanIndex` (暫定)。`0xdbdd50` で同じ配列の要素を引く点から、対応先の chan 添字と推定する。配列が `0xdbde50` の chan 配列と同一かは未確定 (`0xdbdd50` は別の global `0x8244b5` を使う)。

## 3. 未確定 (残す)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| chan 上で `+0x794` を書く箇所 (書込み元) | `pairedChanIndex` の値の由来が決まらない。rerollLoopStarter* の chan 対応付けが確定しない | #1916 ([PY-55]) |
| `0xdd2002`・`0xec7bb8`・`0xec6098` の構造体同定 | 書込幅不一致が推定に留まる | #1916 ([PY-55]) |
| `0xdbdd50` の配列 (`0x8244b5`) と `0xdbde10` の配列 (`0x8243c1`) が同一か | `pairedChanIndex` の添字の対象が確定しない | #1916 ([PY-55]) |
| `ChannelFlags51` の bit2 の FLP 側の意味 | `chan.flag51Bit2` の名前が暫定 | #1916 ([PY-55]) |
