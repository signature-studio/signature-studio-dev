# REPORT — [SR-44 #2175] slot 7 (getState) → slot 17 (Splice 生成) の呼出連鎖 (静的・部分達成)

- 日付: 2026-10-15 / 親: #2135 (SR-41) / 前段: `REPORT_SR41.md` §3・`REPORT_SR43.md`
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。間接 call の受信型は解かない (SR-43 と同じ限界)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-41・SR-43 と一致。本 run で取得して照合)。作業用 dir はリポジトリ外。
- 測定 commit: `917e48fc7` (新版 `slot_reach.py`)。本ファイルの数値はすべてこの版の出力。`git diff 917e48fc7 HEAD -- tools/targets/serum2/gui/slot_reach.py` は差分 0 行。
- 旧版: `7d54ba9b7` の `slot_reach.py` の数値は §1 の参考として残す。閉包 (291・854) と非到達の結論は新旧で一致。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. slot 7 `0x1800c6090` から slot 17 `0x1800c9680` への呼出連鎖の有無 (閉包の大きさ・深さ・閉包内の `call [reg+0x88]` 件数つき) | **達成 (direct 閉包の範囲)**。direct 閉包 C は 291 関数 (BFS 深さ max 15)。C に slot 17 も Splice 生成 `0x180498090` も無い。C 内の `call [reg+0x88]` は 0 件 (全 `.text` では 148 件)。「経路なし」は pdata 関数の開始点への direct call / tail jmp だけで閉包を作った範囲の結論。C から pdata 外へ出る辺 171 件と他関数の途中へ出る辺 3 件は宛先を追っていない (閉包の外に届く経路。§6・#3398)。閉包内の間接 call 149 件の受信型も未解決 (#3398) |
| 2. slot 17 のゲート入力とデモ bit の関係 | **達成 (静的)**。ゲート入力 `[rcx+0x20408]`・`[rsi+0x227a0]`・`[rsi+0x22798]` は、デモ bit `+0x22792` とは別フィールド。デモ bit を参照する関数 (`0x1800c2b50`・`0x1800c6090`) と書込元・読出元が交わらない (§4)。`[rax+0xb8]` の全 `.text` 列挙は本 PR の受入から外し、#3399 へ移した (§9 (c)) |
| 3. patch 後 (demo bit ≡ 0) で Splice 表示が偽になる経路、または非到達の静的証明 | **未確定**。setState `0x1800c2b50` (デモ bit 書込元) の direct 閉包 (854 関数) に `call [rax+0x88]` が 2 件あり、受信型が解けないため経路の有無が決まらない (§3.2・#3399) |
| 4. REPORT に測定 commit と再現手順 | **達成** (§1・§5)。新版の Serum2 実測は §1・§2・§6 |

本 run で得たもの: direct 閉包と逆閉包の交わりを出すツール (`slot_reach.py`)、間接 call の種類と受信レジスタの定義元の分類、ゲート入力フィールドの全 `.text` 参照表、閉包の完全性の数値 (BFS 深さ・pdata 外の `.text`・開始点でない宛先の件数。§6)。
slot 7 から slot 17 への経路は direct 閉包の内側には見つからなかった。閉包の外へ出る間接 call は解いていないので、「経路なし」は direct と vtable 呼出しを数えない範囲の結論である。閉包の外へ出る非開始点への辺 (174 件) も未解決として残る。

## 1. 再現手順・実測 (測定 commit `917e48fc7`)

```sh
# S: リポジトリ外の作業用 dir。P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
A7="--target 0x1800c9680 --target 0x180498090 --target 0x1804986d0 --vtable-head 0x180a2bf58 --offset 0x227a0 --offset 0x22798 --offset 0x20408 --disp 0x88"
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c6090 $A7 > slot7.txt          # §2・§3.1・§4・§6
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --target 0x1800c9680 --target 0x180498090 --target 0x1803573f0 --disp 0x88 > setstate.txt   # §2・§3.2
venv/bin/python $P/splice_disasm.py Serum2_win64.vst3 0x1800c9680 8 4 0x180498090     # §4 ゲート
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c9680 --target 0x180498090 --drop-edge 0x1800c9680:0x180498090 > negctl_drop.txt   # ネガティブコントロール
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c9680 --target 0x180498090 > posctl.txt   # 陽性対照
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x180988250 --disp 0x88 > posctl_disp.txt   # 陽性対照 (--disp)
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (slot 7 の `slot7.txt`・n=3・逐次・nproc=4)。load は `/proc/loadavg` の 1 分値 (実行直前 → 直後):

| 実行 | real (s) | load (前 → 後) | 出力 md5 |
|---|---|---|---|
| slot7 1 | 21.73 | 0.64 → 0.84 | `c4c99c27…` |
| slot7 2 | 21.53 | 0.75 → 0.82 | `c4c99c27…` |
| slot7 3 | 21.50 | 0.82 → 0.88 | `c4c99c27…` |

  min–max は 21.50–21.73 s。3 回の出力は同一 (md5 一致)。
- setState 側 (`setstate.txt`): 出力 md5 `434362cc…` (1 回)。所要は測っていない (REPORT から外した)。
- 陽性対照 (`posctl.txt`): `target 0x180498090: REACHED, path 0x1800c9680 -> 0x180498090` (直接呼出し 1 辺)。
- ネガティブコントロール (`negctl_drop.txt`): 陽性対照と同じ問い合わせで辺 `0x1800c9680 → 0x180498090` を `--drop-edge` で落とすと `existed=True` の後、`target 0x180498090: not in C` (REACHED が消える。閉包は 523 → 94 関数)。
- 陽性対照 (`posctl_disp.txt`): `--disp 0x88` は `0x180988250` の `call [r8+0x88]` を 2 件検出 (`0x1809885e3`・`0x180988607`)。
- 旧版 `7d54ba9b7` (参考): slot 7 の閉包 291・setState の閉包 854・C 内 `call [reg+0x88]` 0・2 件は新版と一致。旧版の出力 md5 (`3b203c55…`) と所要 (n=3 で 20.91–21.03 s) は旧版のもの。

## 2. 呼出閉包と逆閉包 (受入 1・新版 `917e48fc7`・Serum2)

| root | direct 閉包 C | BFS 深さ max (reached == C) | slot 17 `0x1800c9680` | Splice 生成 `0x180498090` | C 内の `call [reg+0x88]` |
|---|---|---|---|---|---|
| getState slot 7 `0x1800c6090` | 291 関数 | 15 (深さ 15 は 2 関数・True) | C ∩ R = 0 (非到達) | C ∩ R = 0 (非到達) | **0 件** |
| setState `0x1800c2b50` (デモ bit 書込) | 854 関数 | 24 (深さ 24 は 1 関数・True) | C ∩ R = 0 (非到達) | C ∩ R = 0 (非到達) | **2 件** (§3.2) |

- slot 7 の BFS 深さ分布 (深さ:関数数): 0:1 1:13 2:50 3:41 4:38 5:23 6:36 7:24 8:22 9:16 10:16 11:4 12:1 13:1 14:3 15:2。
- 旧 REPORT の「深さ 15」は旧版の出力からは再現できなかったため撤回した。新版の BFS で測り直した値が上表の 15 である。
- R = direct 逆閉包 (target へ direct call / tail jmp で届く関数の集合)。`0x1800c9680` の R は自身だけ。`0x180498090` の R は `0x1800c9680` を含む 2 関数。
- Splice 側のラッパ 10 件 (`0x1804a3210`・`0x1804a3250`・`0x1804a3290`・`0x1804a3340`・`0x1804a3390`・`0x1804a33d0`・`0x1804a3450`・`0x1804a3490`・`0x1804a34d0`・`0x1804a3510`) は `0x1804986d0` の R (11 関数) に入る。
- 関数ポインタとして取られるのは slot 17 (`.rdata` 上の `0x180a2bfe0` = vtable head `0x180a2bf58` の index 17) と、ラッパ 10 件。ラッパの格納先は、`0x180a869b8` (head `0x180a86998` の index 4)・`0x180a86af8` (head `0x180a86ac8` の index 6)・残り 8 件 (各 head の index 0)。`lea` で関数アドレスを取る箇所は無い。
- vtable head `0x180a2bf58` の rip 相対参照は ctor `0x1800a9f40` の 1 件だけ (C の外)。

## 3. 間接 call の内訳 (受入 1・3 の未解決)

### 3.1 getState 閉包 (291 関数)

- 間接 call 195 件: `[reg+disp]` 126・`call reg` 23・IAT 呼出し (`call [rip+...]`) 46 (Windows API。plugin の関数ではない)。
- `[reg+disp]` の disp: `0x0`:47 / `0x8`:50 / `0x10`:3 / `0x18`:2 / `0x20`:7 / `0x50`:2 / `0x58`:1 / `0x60`:3 / `0x70`:7 / `0x78`:1 / `0xa8`:1 / `0xe8`:1 / `0x1458`:1。**`0x88` は 0 件**。
- `call reg` 23 件の宛先の定義元: 戻り値 (`call-ret`) 7・vptr 読み `mov rax,[rax]` 5・`mov rax,[rax+8]` 1・`mov r8,[r8]` 1・`mov rax,[rcx]` 1・フィールド `[rsi+N]` 2・`[rdi+N]` 1・スタック spill `[rsp+N]` 2・グローバル `[rip+N]` 1・`cmove` 1・`sub rax,rdi` 1。どれも `+0x88` の読み出しではない。
- 残る未解決: `[reg+disp]` の受信オブジェクトが閉包の外へ出る経路 (disp `0x0` 47 件などは、閉包の外の関数で `[reg+0x88]` を呼ぶ関数を指し得る)。受信型を解くまで「経路なし」は direct 閉包の範囲に限る。

### 3.2 setState 閉包 (854 関数): `call [rax+0x88]` 2 件

| 呼出し | 所属 | 経路 (direct) | 受信 |
|---|---|---|---|
| `0x18049e656` `call [rax+0x88]` | `0x18049e5d0` | setState `0x1800c2ed3` → `0x18049e5d0` (1 辺) | `rsi = rcx`。setState が渡す `rcx = [rdi]` で、`rdi` は `[rsi+0x22380]`〜`[rsi+0x22388]` の範囲を走る要素 (要素の型は未確定) |
| `0x1804bda03` `call [rax+0x88]` | `0x1804bcff0` | setState `0x1800c2cd2` → `0x1800c3080` → `0x1804bcff0` | setState は `rcx = rbx = rsi-0x30` を `0x1800c3080` に渡す (`rsi-0x30` が SC の一次 this かは未確認)。`0x1800c3080` と `0x1804bcff0` が rcx をどう運ぶかは未解決 |

- 2 件とも直前の `mov rax,[rsi]` で vptr を読む。その vptr が SC の vtable head `0x180a2bf58` かどうかは未確定 (受信オブジェクトの型が決まるまで不明)。
- 2 件目は、setState が SC 由来と推定される `rbx` を渡す経路の上にある。SC の this がこの経路で届くかを排除できない。これが受入 3 の未解決の中心。
- setState の BFS 深さは 24 (§2)。

## 4. slot 17 のゲート入力とデモ bit (受入 2・新版でも旧版と同じ件数)

slot 17 `0x1800c9680` (`mov rsi, rcx` で `rsi` = 受信 this):

| 命令 | 内容 |
|---|---|
| `0x1800c96a8` `mov rax,[rcx+0x20408]` → `0x1800c96af` `test byte [rax+0x30],1` → `0x1800c96b3` `je 0x1800c9941` | 条件 1: 子オブジェクトの flag bit0 = 0 なら Splice 生成へ行かない |
| `0x1800c96b9` `mov rax,[rsi+0x22798]` → `0x1800c96c5` `cmp byte [rsi+0x227a0],1` → `0x1800c96cc` `jne` / `0x1800c96d2` `cmp byte [rax+0xb8],1` → `0x1800c96d9` `jne` | 条件 2・3: 既存の Splice オブジェクトがあるときだけ、フラグと `+0xb8` を見る (`+0xb8` の側は #3399 へ移管) |
| `0x1800c992c` `mov byte [rsi+0x227a0],1` / `0x1800c9925` `mov [rsi+0x22798],r14` | 生成後の状態更新 |
| `0x1800c995b` `call 0x180498090` | Splice 生成 (`0x3a0` byte の領域を確保して呼ぶ。`splice_disasm.py` の出力と一致) |

全 `.text` での参照 (`--offset`・新版。件数は旧版と同じ):

| フィールド | 読み | 書き | デモ bit 関数との関係 |
|---|---|---|---|
| `+0x20408` (条件 1) | `0x1800c96a8` (slot 17) | `0x180357931` (`0x1803573f0`) | なし。`0x1803573f0` の direct 逆閉包 (8 関数) は setState・getState の閉包と交わらない |
| `+0x22798` (Splice オブジェクト) | slot 17 の 3 箇所。`lea` が ctor `0x1800a9f40`・dtor `0x1800ac190` | `0x1800c9925` (slot 17)・`0x1800ac6e9` (dtor) | なし |
| `+0x227a0` (フラグ byte) | `0x1800c96c5` (slot 17) のみ | `0x1800c992c` (slot 17) のみ | なし |
| デモ bit `+0x22792` | — | `0x1800c2cfe`・`0x1800c2d42` (`0x1800c2b50`) | 参照する関数は `0x1800c2b50`・`0x1800c6090` の 2 件だけ |

新版の `offset` 出力では、ゲート入力フィールドの参照 11 箇所 (`+0x20408` 2・`+0x227a0` 2・`+0x22798` 7) の `demo-bit function` 列がすべて False。

結論 (受入 2): slot 17 はデモ bit を読まず、ゲート入力 3 件はいずれもデモ bit と別のフィールドである。デモ bit とゲートを結ぶ直接の読み書きは無い。残るのは `+0x20408` の書込元 `0x1803573f0` の呼出元と、`+0x22798` に入った Splice オブジェクトの escape (#3399)。`+0xb8` は本 PR の範囲外 (#3399)。

## 5. 検証と再現

- 測定 commit `917e48fc7`。スクリプトの履歴: `a6c55283e` (追加)・`d2b83776a` (`--offset`)・`79efb3823` (10 進の disp を読む修正。修正前は `[rax + 8]` を誤分類していた)・`7d54ba9b7` (`--disp`)・`917e48fc7` (完全性の出力・`--drop-edge`)。
- 旧版 → 新版: `git diff 7d54ba9b7 917e48fc7 -- tools/targets/serum2/gui/slot_reach.py` = `73 insertions(+), 4 deletions(-)`。閉包の式は変えていない (C の 291・854 は両版で一致)。
- 測定 commit → 現 HEAD: `git diff 917e48fc7 HEAD -- tools/targets/serum2/gui/slot_reach.py` は空 (差分 0 行)。PR 本文の検証結果にも同じ出力を載せる。
- 20MiB 超の blob: `find tools/targets/serum2/gui -size +20M` 0 件。
- 範囲外: 動的な確認 (FLEngine 起動・Serum2 の GUI 実行) は行っていない。
- 対照の範囲: 完全性の検査 (§6 (a)(b)) の件数は Serum2 で実測したが、件数そのものに対する対照 (既知の非開始点宛の辺を 1 本落として件数が 1 減ることの確認) は未実施 (§9 (d))。

## 6. 完全性の検査 (新版 `917e48fc7`・Serum2 実測)

閉包 C は pdata の関数開始点への direct call / tail jmp だけで作る。次の 2 点は「経路なし」の完全性に効く。

| 検査 | slot 7 閉包 (root `0x1800c6090`) | setState 閉包 (root `0x1800c2b50`) |
|---|---|---|
| (a) BFS 深さ | max 15 (reached == C: True) | max 24 (reached == C: True) |
| (a) pdata で覆われない `.text` | 全 `.text` 10,593,334 B のうち 463,290 B (4.4%)・29,354 gap (最大 3,918 B)。閉包に依らない | 同左 |
| (a) gap 内の direct call/jmp が開始点を指す件数 (線形走査・参考) | 954 件 (うち C 内を指す 20 件) | 954 件 (うち C 内を指す 72 件) |
| (b) 開始点でない direct call/jmp (全 `.text`) | 関数内 51,947・他関数の途中 38・pdata 外 25,491 | 同左 |
| (b) 同 (C 内の関数から) | 関数内 1,457・**他関数の途中 3・pdata 外 171** | 関数内 4,204・**他関数の途中 3・pdata 外 866** |

- (b) の扱い: 開始点でない宛先は閉包に入れない (旧版と同じ式を保つ)。件数として未解決に数える。関数内の宛先は同じ関数内の分岐なので、閉包の外へ出る辺ではない。
- 閉包の外に届く辺: slot 7 の C からは 他関数の途中 3 件と pdata 外 171 件 (計 174 件)。宛先は追っていない。したがって「経路なし」は『pdata 関数開始点への辺だけで閉包を作った範囲』の結論である。pdata 外の宛先 (`.text` 内の 463,290 B) の中身は未検査で、#3398 の入力に含める。
- 全 `.text` の件数 (51,947・38・25,491) は、本ツールの 4 回の実行 (slot 7・setState・negctl・posctl) で同一。C に依るのは「C から」の列だけ。

## 7. 素材と未実施 (AGENTS 規範 6・素材)

- 本 run で `$ARTIFACTS_DIR/plugins-serum2.tar.zst` を使った (`$ARTIFACTS_DIR` の実在を確認。展開した exe の sha256 は §0 の入力と一致)。
- 未実施: setState の所要の測定 (REPORT から外した)。件数の対照 (§5・§9 (d))。

## 8. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) slot 7 閉包の間接 call 149 件 (`[reg+disp]` 126・`call reg` 23) の受信型解決。閉包の外へ出る呼出しで `[reg+0x88]` に達するものの有無。閉包から出る非開始点宛の辺 174 件 (他関数の途中 3・pdata 外 171) の宛先の中身 | 受入 1 (slot 7 → slot 17 の経路の確定) | [SR-53] (#3398) |
| (b) setState 閉包の `call [rax+0x88]` 2 件 (`0x18049e656`・`0x1804bda03`) の受信型解決 (SC の this か)。デモ bit=0 で Splice 表示が偽になる経路、または非到達の証明 | 受入 3 | [SR-54] (#3399) |
| (c) `+0x22798` の Splice オブジェクトの escape (slot 17 の `r14`)、`+0x20408` の書込元 `0x1803573f0` の呼出元、`[rax+0xb8]` の全 `.text` 列挙 (旧受入 2 の原文を #3399 の受入条件に移した) | 受入 2 の後段・(b) の入力 | [SR-54] (#3399) |
| (d) 完全性の件数 (§6) の対照: 既知の非開始点宛の辺を 1 本落として件数が 1 減ることの確認 | §6 の件数の信頼性 | 本 PR の未解決表 (子 issue は起票しない) |
