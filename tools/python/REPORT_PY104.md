# PY-104 (#2906): triggerLiveClip のコア後半・refreshLiveClips・zone 系の作用を逆アセンブルで確定 (#2809 の残り)

親: #2809。前段: `tools/python/REPORT_PY91.md` (§1-1 の未読部分)。既知類型との関係: 該当なし (lift 作業ではない)。
zone の型・`zone->vtbl[+0x148]`・`e5abd0` の内部は子 #3624 (PY-222) へ移した (§5・§6)。

## 結論

- **flags の意味** (`0x1221bc0`): K = `(flags>>16)&7` が書込みの系統を決める。K=0 は直接指定、K=1〜3 は現在 key のリセットと選択、K=4〜7 は mode の書込みだけ。bit0 は記録の 0x20 flag、bit1 は表示通知 (推定)、bit2 は保留時刻の採用、bit3-4 は発火位置の量子化 mode (S+0xa8)、bit5 は前回確定 key (S+0xd4) の更新を抑止し、確定 (S+0xd0) を trig mode ごとに条件付きにする、bit7 は単独指定の後に所属グループへ再帰する (推定を含む)。M = `(flags>>8)&3` は現在 key と trig mode の前提判定 (失敗は status -2)。
- **S+0xa0** = 現在のライブクリップ key (`block<<16 | block 内の clip 番号`)。-1 = なし。**S+0xa8** = 発火位置の量子化 mode (0 = 格子、1 = FL のスナップ、2・3 = 量子化なし。格子の値は未確定)。
- **refreshLiveClips** = `0x1221bc0(-1, 0, 0x30000, -1.0f)`。K=3・範囲 1〜499・量子化 mode 0 (S+0xa8 ← 0)・commit あり。全 track の現在 key (S+0xa0) と走査カーソル (S+0xa4) を -1 に戻し、記録 (item) の 0x20 flag が立っていないものから現在 key を選び直し、確定 key (S+0xd0) を現在 key に揃える。量子化 mode S+0xa8 は 0 に戻した後、S+0xd4<0 かつ S+0xd0<0 の track で 2 になる (§4)。velocity・bit1・bit2・bit7 は 0x30000 では立たないので作用しない。
- **REPORT_PY91 の訂正 2 件**: (a) velocity の mask は `movzx` のデータ `[rip+0x913]` = VA `0x1222b80` (値 0x05、K∈{0,2})。`0x1222265` は命令の位置。(b) liveDisplayZone の `vtbl[+0x80]` の判定は zone ではなく `[[0x608132]+8]` のオブジェクトに対するもの (§5)。
- **zone**: `zone+0x58 = duration ÷ *(*0x6070bf)`、`0x420b00` は rect が空かの判定、`0x737020` は遅延呼出しの登録 (bl=0 では直接呼ばない) を確定。zone の型と `zone->vtbl[+0x148]` は未確定 → #3624。
- 実装は行わない。`provider/`・`host/`・`tests/` は変更しない。

## 1. flags の解釈 (`0x1221bc0` の前半と後半)

| フィールド | 定義 (VA) | 作用 (VA) | 確度 |
|---|---|---|---|
| K = bit16-18 | `0x1221c18` | K=0: S+0xa0 ← subNum<<16 (subNum<0 なら -1)、S+0xa8 ← mode (`0x1221d77`〜`0x1221dc6`)。K=1〜3: 範囲の全 track で S+0xa0・S+0xa4 ← -1、S+0xa8 ← mode。K=2 は index 自身を除く (`0x1221e56`〜`0x1221e6b`)。K=4〜7: S+0xa8 ← mode のみ (`0x1221dea`〜`0x1222028`) | 確定 |
| M = bit8-9 | `0x1221bfb` | M bit0 (flags bit8): S+0xa0 < 0 なら status=-2 (`0x122221f`〜`0x1222231`)。M bit1 (flags bit9): S+0x20 ≠ 基準 track の trig mode (`0x1221c91` で elem+0x44 を [rbp+0x60] に保存) なら -2 (`0x1222233`〜`0x1222243`) | 確定 |
| bit0 (0x1) | `0x1221d21` | 記録 (item) の 0x20 flag を更新する。item の track の S+0xa4 と S+0xd0 を比べ、不一致なら 0x20 を立て、一致なら下ろす (`0x12226ad`〜`0x12226cc`)。bit0 真は [rbp+0x57] にも保存し、範囲の前後に `0x4232e0`・`0x423980` を呼ぶ (`0x12224f6`・`0x1222739`) | 確定 (分岐・呼出し)、意味は推定 |
| bit1 (0x2) | `0x1221d47` | 真なら終端で `0x11c9a70(cl=3)` (`0x1222b3f`)。さらに `*(0x3be29f)≥1` なら `0x1311f70(20.0)`→`0x40c660`→`0x4232e0` (`0x1222752`〜`0x1222799`) | 確定 (呼出し)、表示更新・スクロール要求と推定 |
| bit2 (0x4) | `0x1222853` | `[S+0x28]>0` なら常に `0xd2a550(track)` を保留時刻に採用。`S+0x28≤0` のとき bit2 真なら採用、偽なら sentinel 0x80000001 (`0x1222849`〜`0x1222862`) | 確定 (分岐)、`0xd2a550` は保留時刻の最小値と推定 |
| bit3-4 (0x18) | `0x1221d52`〜`0x1221d58` | S+0xa8 ← (flags>>3)&3。`0x12228bf` で `0x100b890` の mode 引数になる | 値は確定、意味は §2・§3 |
| bit5 (0x20) | `0x1221c09` | sil=1 (`0x1221c0e`)。確定 (S+0xd0) は trig mode で分岐する: mode 0 は status=-2 (`0x12223ca`)。mode 1〜2 は S+0xa0 ≠ S+0xd0 で status=-2 (`0x1222439`)、等しければ mode 1 は S+0xd0 ← -1 (`0x122242d`)、mode 2 は `call 0x100bb90` の戻り値を S+0xd0 に入れる (`0x1222420`・`0x1222425`)。mode≥3 は status=-2 (`0x122244a`)。S+0xd4 は更新しない (`0x122247f`)。sil=0 の分岐は §2 | 分岐は確定、「確定を伴わない試行」と推定。`0x100bb90` の意味は §6 |
| bit7 (0x80) | `0x12220fc` | start==end かつ K≤1 かつ bit31=0 のとき、track 処理の後に再帰 (`0x1222113`〜`0x122218a`)。subNum = (記録 +0xe>0 ならその値、else S+0xa0>>16)。flags = (flags & 0xffff & ~0x80) \| 0x80000000 \| (記録 +0xe>0 なら 0x20000 = K=2)。velocity = -1.0f (`0x1222182`) | 呼出し形は確定、「単独指定を所属グループ全体へ広げる」と推定 |
| bit31 (group) | `0x1221c2d` | index≥0 かつ bit31 真は `0x12e8210(index, flag=1)` で [first,last] を得て、[1..E] と交わす (`0x1221cb6`〜`0x1221d11`)。index<1 または index>500 は範囲計算を飛ばす (`0x1221c6a`・`0x1221c7c`)。**first==last のときは絞らず [1..E] のまま** (`0x1221cc7` の je) | 分岐は確定、単一グループでの意味は未確定 (§6) |
| bit30 (0x40000000) | `0x1222b49` | 偽のとき終端で `0xbd68e0(0x16, 0)` (`0x1222b57`) | 呼出しは確定、意味は推定 |
| E (終端) | `0x1221c3e`〜`0x1221c58` | flags & 0x30000 ≠ 0 なら E=0x1f3 (=499)。else `*(count)` (track 数) | 確定 |
| 範囲 (単独) | `0x1221c25`・`0x1221d13` | bit31=0 かつ index≥0 は [index,index] (範囲計算なし) | 確定 |

## 2. track ループ (`0x12227f8`〜`0x1222b23`) の作用

各 track (S = elem+0x24) について。

1. **準備判定** (`0x1222814`): status (S+0x9c) < -1 なら飛ばす。
2. **位置 esi** (`0x1222822`〜`0x12228dd`): esi = `[rbp+0x88]` (= cur+1、state==2 のとき offset を加える) − `*(0x3bd8f7)`。保留時刻 `[rbp+0x70]` が sentinel (0x80000001) より大きければ `esi = 保留時刻 − [rbp+0x84]` として量子化を飛ばす (`0x1222874`〜`0x122287f`)。そうでなければ、status≥0 のとき一致記録の長さ (`rec+8`、`0x1222a91` と同じ読み)、else 0x7fffffff を len として `0x100b890(S, mode=S+0xa8, pos=esi, len)` で量子化し、`esi += *(0x3bd847)`。
3. **量子化 `0x100b890`** (`0x100b89f`〜`0x100b95a`): mode≥2 は pos をそのまま返す (`0x100b95a`)。mode=1 は `0xe59e90` (FL のスナップ値に応じた関数、未確定)。mode≤0 は track 種別 (S+0x24) の表で格子長を決め、切り上げた位置を返す。
4. **時刻 T** (`0x12228e0`〜`0x12228f3`): `T = max(esi, [rbp+0x88])`。`T < *(0x3bd81d)` なら S+0xd0 ← -1 (`0x1222a34`〜`0x1222a43`)。
5. **未リンク記録の移動** (`0x122296e`〜`0x1222a2b`): 保留記録の配列の各要素について、`(+8)>>16` が track に等しく、+0x10 == -1、+0x6c ≥ T のとき、別の配列の要素と入れ替える (`0x12229c9`〜`0x1222a10`)。不一致なら +0x68 を max で更新 (`0x1222a12`〜`0x1222a21`)。
6. **状態の確定** (`0x1222a4e`〜`0x1222b13`): status ≥0 かつ `S+0x30` (posSnap) > 0 なら `0x100b970(S, T, len)` で位置を求め (`0x1222aae`〜`0x1222ad2`)、`0xd2a3c0` で保留記録を作る (`0x1222b0e`、推定)。

velocity による選択 (`0x122227e`〜`0x12223b9`、K∈{0,2} のみ。S+0xa0 ≥ 0 が前提):
- velocity ≥ 0 (`0x122228b`〜`0x122231b`): block (`S+0xa0>>16`) の clip 数 `count = qword[ptr-8]` に対し、`clamp(int(velocity × count), 0, count-1)` を S+0xa0 に加える (`0x63a690` で整数化、推定)。
- velocity < 0 (`0x1222326`〜`0x12223b9`): S+0xd4 が同じ block なら、`p` = S+0xd4 の clip 番号として `(p+1) mod count` を S+0xa0 に加える。

確定 key の commit (`0x12223bf`〜`0x122247c`): S+0x20 (trig mode) と sil (bit5) で分岐する。sil=0 のとき、mode 0 は S+0xd0 ← S+0xa0 (`0x12223d9`)、mode 1〜2 も S+0xd0 ← S+0xa0 (`0x12223f5`)、mode≥3 は S+0xa0 と S+0xd0 が等しければ -1、違えば S+0xa0 (`0x1222456`〜`0x1222476`)。sil=1 の分岐は §1 の bit5 行。`0x122247f` 以降は sil=0 のときだけ実行される: S+0xd4<0 かつ S+0xd0<0 なら S+0xa8 ← 2 (`0x1222481`〜`0x1222493`)、続けて S+0xd4 ← S+0xd0 (`0x12224a3`)。

## 3. 状態フィールド (S = elem+0x24)

| フィールド | elem offset | 書込み・読込み (VA) | 意味 | 確度 |
|---|---|---|---|---|
| S+0x9c | +0xc0 | 0x1222194 で `setne` → -1 (block あり) か -2 (`0x12221a6`)。失敗は -2 (`0x1222245`・`0x1222439`・`0x12223ca`)。一致した記録では記録 index (`0x12226b9`) | status: -2 失敗 / -1 準備済み / ≥0 一致した記録の index | 値域は確定、≥0 の意味は推定 |
| S+0xa0 | +0xc4 | `0x1221dc0` (K=0、subNum<<16)・`0x1221e6b` (K=1〜3 で -1)・`0x122231b`・`0x12223b9` (velocity 加算)・`0x1222062`・`0x122209f` (記録から S+0xa4 を写す) | **現在のライブクリップ key** = (block<<16) \| clip 番号。-1 = なし | 確定 (`0x100bb30` の decode と書込み箇所、REPORT_PY91 §3) |
| S+0xa4 | +0xc8 | `0x1222033` (max(S+0xa4+1, ord<<16)、ord は記録走査の順番)・`0x1221e75` (K=1〜3 で -1)・`0x12224c3` (-1) | 記録走査のカーソル key | 推定 |
| S+0xa8 | +0xcc | `0x1221dc6` (K=0 の mode)・`0x1221e12`・`0x1221e7f`・`0x1222493` (S+0xd4<0 かつ S+0xd0<0 のとき 2。sil=0 のみ)。読込み `0x12228bf` (`0x100b890` の mode) | 発火位置の量子化 mode: 0 = 格子、1 = FL スナップ (`0xe59e90`)、2・3 = 量子化なし | dispatch は確定、格子 (`0x5399e7`・`0x5d6e62`) の値は未確定 |
| S+0xd0 | +0xf4 | `0x12223d9`・`0x12223f5`・`0x1222470`・`0x1222476`・`0x1222a43` (-1) | 確定 key (前回 commit) | 書込みは確定、意味は推定 |
| S+0xd4 | +0xf8 | 書込み `0x12224a3` (S+0xd0 の写し。sil=0 のとき)。読込み `0x12222a0` (`& 0xffff` = 前回の clip 番号)・`0x1222333`〜`0x1222347` (block 一致判定) | 前回 key の写し (velocity<0 の基準) | 確定 (読込み)、意味は推定 |
| S+0x20 | +0x44 | `0x1221c91` (基準 track の trig mode)・`0x1222240` (M bit1)・`0x12223bf` 以降の commit 分岐 | trig mode (0・1〜2・≥3 で commit 規則が違う) | 確定 |
| S+0x28 | +0x4c | `0x1222849` | 保留件数 (>0 なら `0xd2a550` を採用) | 推定 |
| S+0xf8 | +0x11c | `0x1222194`・`0x12222bc`・`0x122237d` (block 配列: 要素は 8 B のポインタ、件数は `qword[ptr-8]`) | block 配列。要素 (0x58 B の clip) への `0x100bb30` の入口 | 推定 (stride 未確定)。**elem+0x11c は stride 0x114 を越える (§6)** |

記録 (item) の項目 (`L = [[*(g)]+0xd2c]+0x57c`。要素は `0x12df530(L, i)` で `[L+8] + i*[L+0x10]`、件数は `[L+0x14]`):
- +0x00 dword: 開始 (`0x1221ee4`・`0x1222545` で sentinel と比較)
- +0x04 dword: track 番号 (`0x1221f70`・`0x12225d1` で `[g+0x3f4]`〜`[g+0x3f8]` と範囲比較)
- +0x08 dword: 長さ (`0x1222a91`)
- +0x0e word: グループ (subNum と比較、`0x1222074`・`0x1222140`)
- +0x13 byte: 状態。0x20 は「非選択」 (`0x1222094`・`0x12226bf`・`0x12226f4` で判定)
- status は一致した記録の index (`0x12226b9`)

## 4. refreshLiveClips = `0x1221bc0(-1, 0, 0x30000, -1.0f)` (0xd579d0 → 0x1222b90)

呼出し (`0x1222b90`〜`0x1222ba7`): ecx=-1、edx=0、r8d=0x30000、xmm3=-1.0f (定数 `0x1222bb4`)。フラグ 0x30000 は K=3、M=0、bit0/1/2/5/7/30 は 0。範囲は [1..499] (E=0x1f3)。

1. **初期化** (K∈{1,2,3} の経路、`0x1221e2e`〜`0x1221e95`): 全 track で S+0xa0 ← -1、S+0xa4 ← -1、S+0xa8 ← 0 (mode)。
2. **記録の走査** (`0x1221ec4`〜`0x12220b5`): K=3 の分岐 (`0x122208f`〜`0x12220a5`) で、記録の 0x20 flag が立っていないものについて、その track の S+0xa0 ← S+0xa4。K=1 (ordinal == subNum) と K=2 (group == subNum かつ S+0xa0<0) はこの呼出しでは使われない。
3. **各 track の commit** (`0x12220bc`〜`0x12224db`): K=3 は S+0xd0 ≠ S+0xa0 のときだけ本体を通す (入場条件 `0x122220e`〜`0x122221a`、経路 `0x1222200`〜`0x1222220`)。本体の確定は track の trig mode S+0x20 (`0x12223bf`) で分岐するが、refresh は sil=0 (0x30000 の bit5 = 0) なので、どの trig mode でも S+0xd0 ← S+0xa0 になる。mode 0 は `0x12223d9`、mode 1〜2 は `0x12223f5`、mode≥3 は入場条件より S+0xa0 ≠ S+0xd0 で `0x1222470`。続けて S+0xa8 ← 2 の判定 (`0x1222481`〜`0x1222493`) と S+0xd4 ← S+0xd0 (`0x12224a3`)。K=3 は velocity の経路 (K∈{0,2}) に入らない。最後に S+0xa4 ← -1 (`0x12224c3`)。
4. **記録の再計算** (`0x12226ad`〜`0x12226cc`): bit0 は 0 のため [rbp+0x50]=0 で 0x20 は変わらない。UI 通知 `0xe8fba0` は記録の状態が変わったときだけ (`0x12226cf`〜`0x12226d6`)。

**効果** (状態遷移は確定、意味づけは推定): 全 track (1〜499) の現在 key (S+0xa0)・走査カーソル (S+0xa4)・確定 key (S+0xd0/S+0xd4) を、未選択の記録から組み直す。量子化 mode S+0xa8 は初期化で 0 に戻された後、S+0xd4<0 かつ S+0xd0<0 の track で 2 になる (`0x1222481`〜`0x1222493`)。refresh は S+0xa8 を 0 に戻すだけではない。velocity・bit1・bit2・bit7 は 0x30000 では立たないので作用しない。

## 5. zone 系 (`liveDisplayZone` → `0xd84f70` → `0xfdc630`)

| 関数 | 作用 (VA) | 確度 |
|---|---|---|
| `liveDisplayZone` 0xd57150 | zone = `[[job+8]+0x50]` (0xd5718f)。`0x420980(&rect, left, top, right, bottom)` で rect を作る (0xd571ae)。rect は (+0 left, +4 top, +8 right, +0xc bottom) (`0x420980` の store)。`0xd84f70(zone, &rect, duration)` (0xd571be) | 確定 |
| `0xd84f70` | `0xfdc630(zone, &rect, duration)` の call (0xd84f74)。call の後に `add rsp,0x28`・`ret` が続く通常の call (tail call ではない) | 確定 |
| `0xfdc630` の 1 | `G1 = *(*(0x606f7d))`。`byte [G1+0xa9] == 0` なら戻る (0xfdc64e〜0xfdc655) | 確定 |
| `0xfdc630` の 2 | **O = `[[*(0x608132)]+8]` (zone ではない)**。`O.vtbl[+0x80](O)` が偽なら戻る (0xfdc657〜0xfdc673)。REPORT_PY91 の「zone->vtbl[+0x80]」は誤り (訂正) | 確定 |
| `0xfdc630` の 3 | `app = *(*(0x606f4c))`。`0xe5abd0(app, zone, &rect)` (0xfdc685) | 呼出しは確定 |
| `0xfdc630` の 4 | `0x420b00(&rect)` が真 (rect が空) なら戻る (0xfdc68d〜0xfdc694) | 確定 |
| `0xfdc630` の 5 | duration ≤ 0 なら戻る (0xfdc696〜0xfdc698)。`zone+0x58 = duration ÷ *(*(0x6070bf))` (idiv、0xfdc6a6) | 式は確定、単位 (ms か tick か) は未確定 |
| `0xfdc630` の 6 | `0x737020({fn=0xfdc560, zone}, bl=0)` (0xfdc6be)。`0x737020` は `*(0xebf15a)` を this として `**(0xebf14f)` の vtbl[+0x40] を呼び登録する。bl=0 では fn を直接呼ばない (0x737061〜0x737063) | 登録は確定、受け手の型は未確定 (#3624) |
| `0x420b00(rect)` | rect.right ≤ rect.left または rect.bottom ≤ rect.top なら真 (空) (0x420b00〜0x420b15) | 確定 |
| `e5abd0(app, zone, rect)` | frame = `app+0xd2c` (0xe5abeb)。`[rect]` (left) < 0 なら 0xe5acf2。`frame+0x400 == 0x14`、または `frame+0x400 == 0` かつ `frame+0x548 < 0` のとき進む (0xe5abfb〜0xe5ac21・0xe5ac13)。`0x1221aa0(rect.left)` で index を得る (0xe5ac35)。index<0 なら `0x4f2990` と再帰 (0xe5ac41〜0xe5ac67) | 分岐は確定、`0x1221aa0`・`0x4f2990` は未確定 (#3624) |

**lockDisplayZone** 0xd56fc0: zone = `[[job+8]+0x50]` (0xd56ffa) は REPORT_PY91 の通り。`zone->vtbl[+0x148](index, bool)` (0xd57012〜0xd57015) の先と zone の型は未確定 → #3624。

**#3624 の追補 (PY-222、静的解析で確定した分と未確定の分)**:

| 対象 | 確定した作用 (VA) | 確度 |
|---|---|---|
| `e5abd0` の `0x4f2990(out, a, b, c, d)` | `out[0..0xc]` に 4 個の int を書く (0x4f2990〜0x4f29a4)。`rect` 相当の書き込み | 確定 |
| `e5abd0` の `0x1221aa0(x)` | `ebx = x`。`x < 0` なら `-1`。`x ≥ 0` なら `0x12e1a20()` の表 `[rax+0x21c48]` の判定 (0x1221abc〜0x1221ad0) で 2 経路に分かれる。経路 A (表が無い・件数条件を外れる): `index = x × [0x15e0db8]` (0x1221ad2〜0x1221ad9)。経路 B: 表の要素 13 dword 刻み (0x1221af5〜0x1221af9) を `0x442c00` に渡し、戻り値を `[0x15e0120]` (int) と比べて index を返す (0x1221b01〜0x1221b10)。`0x442c00` は `rect` の 4 個の `word` を読んで `0x442670` に渡す (0x442c00〜0x442c26) | 経路 A/B の分岐と参照先は確定。経路 B の `0x442c00` への引数の渡し方・戻り値の意味、`[0x15e0db8]`・`[0x15e0120]` の値は未確定 |
| `0x737020` の受け手 | `0x737020` は `this = [0x15f61a8]`、`vtbl[+0x40]` の呼出し (0x737047〜0x73705c)。`0x15f61a8` は .bss の遅延初期化スロットで、`0x736ff0` が初回に `[0x15e1fc0]` の関数の戻り値を書く (0x736ffe〜0x737007)。スロットに入るオブジェクトは .bss 上で実行時に決まり、ファイル上の初期値は無い (`0x15f4658`・`not-in-file`) | スロットの位置は確定。オブジェクトの型は未確定 |

旧表記の訂正: `0x737020` の `*(0xebf15a)` などは RIP 相対の disp 値で、実アドレスは `0x15f61a8` (`pe_rip_refs.py` で全参照を検出)。

**未確定 (#3624 に残す)**: `lockDisplayZone` の `zone->vtbl[+0x148]` の先と zone の型。zone の型 (class 名・VMT) は PE 上に手がかりが無く、`0x15f61a8` の実行時オブジェクトの型から決まる。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `lockDisplayZone` の `zone->vtbl[+0x148]` の先と zone の型、`e5abd0` の `0x1221aa0`・`0x4f2990`、`0x737020` の受け手の型 | zone 系 C 実装の中身 | #3624 (PY-222) |
| 格子 (mode 0) の長さの値 (`0x5399e7` 表・`0x5d6e62` の global)、mode 1 の `0xe59e90` の snap 値 | S+0xa8 の数値の意味 | #2908 (PY-105)。時間 ↔ block の定数と同じ領域 |
| bit5 (sil=1) の mode 2 で `call 0x100bb90` (rcx=S・edx=S+0xa0) の戻り値を S+0xd0 に入れる (`0x1222420`・`0x1222425`)。`0x100bb90` の意味は未確定 | 確定 key (mode 2) の値の意味 | PM 判断 (本 REPORT §6 で提示) |
| bit1 の `0x1311f70(20.0)`・`0x40c660`・`0x11c9a70`、bit30 の `0xbd68e0` の作用 | 表示通知の中身 | #2908 (PY-105) |
| bit2 の `0xd2a550`・`0xd274c0` (保留時刻の最小値の定義)、`0xd2a3c0` (保留記録の作成) | bit2 と保留記録の意味 | #2908 (PY-105) |
| bit31 の group 範囲で first==last のときの挙動 (絞らず [1..E])。`0x12e8210` の戻り値の意味 | 単独 track 指定の group 挙動 | PM 判断 (本 REPORT §6 で提示。#2809 は CLOSED) |
| S+0xf8 (elem+0x11c) は stride 0x114 を越える。`0x12e1a20()` の要素の大きさ・stride の確認が要る | block 配列の位置の解釈 | PM 判断 (本 REPORT §6 で提示。#2809 は CLOSED) |

## 7. 変更範囲

- 追加: `tools/python/analysis/flapi/playlist_live_clip_facts.py` (検算)、本 REPORT、`docs/DOC_MAP.md` の索引行。
- 変更なし: `tools/python/analysis/flapi/` の既存スクリプト、`provider/`、`host/`、`tests/`。
- 起動・GUI の変更はない (解析のみ)。製品 KPI は書かない。

## 8. 検証

- 素材: `fl-win64` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'`)。
- 測定 commit (コードを最後に変えた commit): `44f02645c` (`feat(flapi): verify live clip trigger and zone facts (PY-104)`)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/playlist_live_clip_facts.py`。全 expectation が OK で終了 (exit 0)。主な出力: `0x1222b80` = 0x05 → K ∈ {0, 2}、`0x1222b70` = -1.0、`0x1222bb4` = -1.0 (refresh の定数)、`0x100b95a` (mode≥2 の戻り) など。
- 実測 (n=3、`/usr/bin/time`): real 0.06 s / user 0.04〜0.05 s / sys 0.01〜0.02 s。実行直前の load average `0.02 0.10 0.13` (`/proc/loadavg`)、nproc 4、並列 1。
- 差分: `git diff 44f02645c HEAD -- tools/python/analysis/flapi/playlist_live_clip_facts.py tools/python/analysis/flapi/pe_disasm.py` の出力は 0 行 (測定対象の 2 本は変更なし)。main 取り込み (merge commit) で `tools/python/analysis/flapi` には `pe_va_read.py`・`pe_mixer_wrappers.py` の追加のみが入ったが、測定対象 2 本は両者を import しない。
- 再測定 (修正後 HEAD `b184a77c3`、`/usr/bin/time`、n=3): real 0.08 s / user 0.06 s / sys 0.01〜0.02 s。実行直前の load average `0.02 0.14 0.08`、nproc 4、並列 1。全 expectation OK (exit 0)。
- 逆アセンブル (手動): 0x1221bc0〜0x1222b69 (全体)・0x1222b90・0x100b890・0x100b970・0xd2a550・0xd2a3c0・0x12df530・0xd84f70・0xfdc630・0x420980・0x420b00・0xe5abd0・0x737020 を `pe_disasm.py` で読んだ。実行による検証はしていない。差し戻し修正時に 0x12223bf〜0x12224a9・0x1222200〜0x122221a・0x1222300〜0x122231b・0x1222b90・0xd84f70・0x100bb90 を再読した。

- #3624 追補の実測: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_refs.py 0x15f4658 0x15f61a8` (既存スクリプト。.text 線形走査、n=3、`/usr/bin/time`): real 18.03〜18.61 s / user 18.00〜18.60 s。実行直前の load average `0.78 0.36 0.22`、nproc 4、並列 1。`0x15f61a8` のヒットは 41 件 (0x736ff4〜0x741753)。

## 9. 参照

- 逆アセンブル: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_disasm.py <VA> <命令数>`
- 前段: `tools/python/REPORT_PY91.md` (§1・§1-1 の訂正は本 REPORT の結論に記載)
