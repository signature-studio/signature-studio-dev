# REPORT — [SR-44 #2175] slot 7 (getState) → slot 17 (Splice 生成) の呼出連鎖 (静的・部分達成)

- 日付: 2026-10-15 / 親: #2135 (SR-41) / 前段: `REPORT_SR41.md` §3・`REPORT_SR43.md`
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。間接 call の受信型は解かない (SR-43 と同じ限界)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-41・SR-43 と一致)。作業用 dir はリポジトリ外。
- 数値の測定 commit: `7d54ba9b7` (旧版 `slot_reach.py` の出力。§2・§3 の数値はこの版)。
- 版の差: 本 PR で `slot_reach.py` を変えた (§6 の完全性出力・BFS 深さ・`--drop-edge`)。**新版の Serum2 での実測は未取得**。本 run の素材に `plugins-serum2` が無かった (§7)。閉包の計算ロジックは変えていない (閉包 291・854 は旧版と同じ式)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. slot 7 `0x1800c6090` から slot 17 `0x1800c9680` への呼出連鎖の有無 | **direct 閉包の範囲で非到達 (旧版の測定)**。direct call / tail jmp の閉包 (291 関数) に slot 17 も Splice 生成 `0x180498090` も無い。閉包内の `call [reg+0x88]` は 0 件 (全 `.text` では 148 件)。閉包内の間接 call 149 件の宛先は未解決 (§3.1・#3398)。**閉包の深さは未測定**: 旧 REPORT の「深さ 15」は `slot_reach.py` の出力で再現できなかったため撤回。新版の BFS 深さ (§6) は Serum2 で未取得 |
| 2. slot 17 のゲート入力とデモ bit の関係 | **達成 (静的)**。ゲート入力 `[rcx+0x20408]`・`[rsi+0x227a0]`・`[rsi+0x22798]` は、デモ bit `+0x22792` とは別フィールドで、デモ bit を参照する関数 (`0x1800c2b50`・`0x1800c6090`) と書込元・読出元が交わらない (§4)。`[rax+0xb8]` の全 `.text` 列挙は本 PR の受入から外し、子 #3399 へ移した (§6(c)) |
| 3. patch 後 (demo bit ≡ 0) で Splice 表示が偽になる経路、または非到達の静的証明 | **未確定**。setState `0x1800c2b50` (デモ bit 書込元) の direct 閉包 (854 関数) に `call [rax+0x88]` が 2 件あり、受信型が解けないため経路の有無が決まらない (§3.2・#3399) |
| 4. REPORT に測定 commit と再現手順 | **達成** (測定 commit・再現手順は本ファイル §1・§5。新版の Serum2 実測は §7 の通り未取得) |

本 run で得たもの: direct 閉包と逆閉包の交わりを出すツール (`slot_reach.py`)、間接 call の種類と受信レジスタの定義元の分類、ゲート入力フィールドの全 `.text` 参照表、閉包の完全性の検査 (BFS 深さ・pdata 外の `.text`・開始点でない direct call/jmp の件数。新版の出力・Serum2 では未取得)。
slot 7 から slot 17 への経路は direct 閉包の内側には見つからなかった。閉包の外へ出る間接 call は解いていないので、「経路なし」は direct と vtable 呼出しを数えない範囲の結論である。

## 1. 再現手順・実測 (旧版 `7d54ba9b7`)

```sh
# S: リポジトリ外の作業用 dir。P: 本ディレクトリ (tools/targets/serum2/gui)
cd $S
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
A7="--target 0x1800c9680 --target 0x180498090 --target 0x1804986d0 --vtable-head 0x180a2bf58 --offset 0x227a0 --offset 0x22798 --offset 0x20408 --disp 0x88"
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c6090 $A7 > slot7.txt          # §2・§3.1・§4
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --target 0x1800c9680 --target 0x180498090 --target 0x1803573f0 --disp 0x88 > setstate.txt   # §3.2
venv/bin/python $P/splice_disasm.py Serum2_win64.vst3 0x1800c9680 8 4 0x180498090     # §4 ゲート
```

- 依存: `pefile` `capstone` `zstandard`。
- 実測 (n=3・逐次・nproc=4・測定 commit `7d54ba9b7`)。load は `/proc/loadavg` の 1 分値 (実行直前):

| 実行 | real (s) | load 開始 | 出力 md5 |
|---|---|---|---|
| slot7 1 | 20.91 | 0.53 | `3b203c55…` |
| slot7 2 | 21.03 | 0.69 | `3b203c55…` |
| slot7 3 | 20.91 | 0.78 | `3b203c55…` |

- setState 側 (`setstate.txt`) の所要時間は測定していない (n=1 で load 未取得のため REPORT から外した)。出力 md5 `83862665…` (1 回)。
- 陽性対照 (ツールが既知の辺を検出すること): `slot_reach.py ... 0x1800c9680 --target 0x180498090` → `REACHED, path 0x1800c9680 -> 0x180498090` (直接呼出し 1 辺)。`slot_reach.py ... 0x180988250 --disp 0x88` → `call [r8+0x88]` を検出 (`0x1809885e3`)。

## 2. 呼出閉包と逆閉包 (受入 1・旧版)

| root | direct 閉包 C | slot 17 `0x1800c9680` | Splice 生成 `0x180498090` | C 内の `call [reg+0x88]` |
|---|---|---|---|---|
| getState slot 7 `0x1800c6090` | 291 関数 (深さ**未測定**・§6) | C ∩ R = 0 (非到達) | C ∩ R = 0 (非到達) | **0 件** |
| setState `0x1800c2b50` (デモ bit 書込) | 854 関数 | C ∩ R = 0 (非到達) | C ∩ R = 0 (非到達) | **2 件** (§3.2) |

- R = direct 逆閉包 (target へ direct call / tail jmp で届く関数の集合)。`0x1800c9680` の R は自身だけ。`0x180498090` の R は `0x1800c9680` を含む 2 関数。
- Splice 側のラッパ 10 件 (`0x1804a3210`・`0x1804a3250`・`0x1804a3290`・`0x1804a3340`・`0x1804a3390`・`0x1804a33d0`・`0x1804a3450`・`0x1804a3490`・`0x1804a34d0`・`0x1804a3510`) は `0x1804986d0` の R (11 関数) に入る。
- 関数ポインタとして取られるのは slot 17 (`.rdata` 上の `0x180a2bfe0` = vtable head `0x180a2bf58` の index 17) と、ラッパ 10 件。ラッパの格納先は、`0x180a869b8` (head `0x180a86998` の index 4)・`0x180a86af8` (head `0x180a86ac8` の index 6)・残り 8 件 (各 head の index 0)。`lea` で関数アドレスを取る箇所は無い。
- vtable head の参照元: `0x180a2bf58` は ctor `0x1800a9f40` だけ (C の外)。ラッパ側 10 個の head は `0x180498090` と `0x1804986d0` だけが参照する (Splice オブジェクトの生成元)。

## 3. 間接 call の内訳 (受入 1・3 の未解決)

### 3.1 getState 閉包 (291 関数・旧版)

- 間接 call 195 件: `[reg+disp]` 126・`call reg` 23・IAT 呼出し (`call [rip+...]`) 46 (Windows API。plugin の関数ではない)。
- `[reg+disp]` の disp: `0x0`:47 / `0x8`:50 / `0x10`:3 / `0x18`:2 / `0x20`:7 / `0x50`:2 / `0x58`:1 / `0x60`:3 / `0x70`:7 / `0x78`:1 / `0xa8`:1 / `0xe8`:1 / `0x1458`:1。**`0x88` は 0 件**。
- `call reg` 23 件の宛先の定義元: 戻り値 (`call-ret`) 7・vptr 読み `mov rax,[rax]` 5・`mov rax,[rax+8]` 1・`mov r8,[r8]` 1・`mov rax,[rcx]` 1・フィールド `[rsi+N]` 2・`[rdi+N]` 1 (disp `0x17a0`)・スタック spill `[rsp+N]` 2・グローバル `[rip+N]` 1・`cmove` 1・`sub rax,rdi` 1。どれも `+0x88` の読み出しではない。
- 残る未解決: `[reg+disp]` の受信オブジェクトが閉包の外へ出る経路 (disp `0x0` 47 件などは、閉包の外の関数で `[reg+0x88]` を呼ぶ関数を指し得る)。受信型を解くまで「経路なし」は direct 閉包の範囲に限る。

### 3.2 setState 閉包 (854 関数): `call [rax+0x88]` 2 件

| 呼出し | 所属 | 経路 (direct) | 受信 |
|---|---|---|---|
| `0x18049e656` `call [rax+0x88]` | `0x18049e5d0` | setState `0x1800c2ed3` → `0x18049e5d0` (1 辺) | `rsi = rcx`。setState が渡す `rcx = [rdi]` で、`rdi` は `[rsi+0x22380]`〜`[rsi+0x22388]` の範囲を走る要素 (要素の型は未確定) |
| `0x1804bda03` `call [rax+0x88]` | `0x1804bcff0` | setState `0x1800c2cd2` → `0x1800c3080` → `0x1804bcff0` | setState は `rcx = rbx = rsi-0x30` を `0x1800c3080` に渡す (`rsi-0x30` が SC の一次 this かは未確認)。`0x1800c3080` と `0x1804bcff0` が rcx をどう運ぶかは未解決 |

- 2 件とも直前の `mov rax,[rsi]` で vptr を読む。その vptr が SC の vtable head `0x180a2bf58` かどうかは未確定 (受信オブジェクトの型が決まるまで不明)。
- 2 件目は、setState が SC 由来と推定される `rbx` を渡す経路 (setState → `0x1800c3080` → `0x1804bcff0`) の上にある。SC の this がこの経路で届くかを排除できない。これが受入 3 の未解決の中心。

## 4. slot 17 のゲート入力とデモ bit (受入 2・旧版)

slot 17 `0x1800c9680` (`mov rsi, rcx` で `rsi` = 受信 this):

| 命令 | 内容 |
|---|---|
| `0x1800c96a8` `mov rax,[rcx+0x20408]` → `0x1800c96af` `test byte [rax+0x30],1` → `0x1800c96b3` `je 0x1800c9941` | 条件 1: 子オブジェクトの flag bit0 = 0 なら Splice 生成へ行かない |
| `0x1800c96b9` `mov rax,[rsi+0x22798]` → `0x1800c96c5` `cmp byte [rsi+0x227a0],1` → `0x1800c96cc` `jne` / `0x1800c96d2` `cmp byte [rax+0xb8],1` → `0x1800c96d9` `jne` | 条件 2・3: 既存の Splice オブジェクトがあるときだけ、フラグと `+0xb8` を見る (`+0xb8` の側は #3399 へ移管) |
| `0x1800c992c` `mov byte [rsi+0x227a0],1` / `0x1800c9925` `mov [rsi+0x22798],r14` | 生成後の状態更新 |
| `0x1800c995b` `call 0x180498090` | Splice 生成 (`0x3a0` byte の領域を確保して呼ぶ) |

全 `.text` での参照 (`--offset`・旧版):

| フィールド | 読み | 書き | デモ bit 関数との関係 |
|---|---|---|---|
| `+0x20408` (条件 1) | `0x1800c96a8` (slot 17) | `0x180357931` (`0x1803573f0`) | なし。`0x1803573f0` の direct 逆閉包 (8 関数) は setState・getState の閉包と交わらない |
| `+0x22798` (Splice オブジェクト) | slot 17 の 3 箇所。`lea` が ctor `0x1800a9f40`・dtor `0x1800ac190` | `0x1800c9925` (slot 17)・`0x1800ac6e9` (dtor) | なし |
| `+0x227a0` (フラグ byte) | `0x1800c96c5` (slot 17) のみ | `0x1800c992c` (slot 17) のみ | なし |
| デモ bit `+0x22792` | — | `0x1800c2cfe`・`0x1800c2d42` (`0x1800c2b50`) | 参照する関数は `0x1800c2b50`・`0x1800c6090` の 2 件だけ |

結論 (受入 2): slot 17 はデモ bit を読まず、ゲート入力 3 件はいずれもデモ bit と別のフィールドである。デモ bit とゲートを結ぶ直接の読み書きは無い。残るのは `+0x20408` の書込元 `0x1803573f0` の呼出元と、`+0x22798` に入った Splice オブジェクトの escape (#3399)。`+0xb8` は本 PR の範囲外 (#3399)。

## 5. 検証と再現

- 数値の測定 commit `7d54ba9b7`。スクリプトの履歴: `a6c55283e` (追加)・`d2b83776a` (`--offset`)・`79efb3823` (10 進の disp を読む修正。修正前は `[rax + 8]` を誤分類していた)・`7d54ba9b7` (`--disp`)・本 PR の commit (完全性の出力・`--drop-edge`)。
- `git diff 7d54ba9b7 HEAD -- tools/targets/serum2/gui/slot_reach.py` の出力は本 PR 本文の「検証結果」に載せる (本ファイルは自 commit の hash を書けないため)。差分は 0 行ではない。
- 動作確認 (Serum2 ではない): `pnpm` 同梱 vendor の `fastlist-0.3.0-x64.exe` (`.pdata` あり・`.text` 167,516 B) で新版を実行した。
  - `root` = エントリポイント `0x140008e44`: 閉包 C = 196 関数、BFS 深さ max 20 (深さ 20 の関数 1 件・`reached == C`: True)。
  - pdata で覆われない `.text` = 10,547 B / 563 gap (最大 819 B)。線形走査で、gap 内の direct call/jmp が関数開始点を指すものは 96 件 (うち C の内側へ 13 件)。
  - 開始点でない direct call/jmp: 関数内 1,419・他関数の途中 3・pdata 外 457 (うち閉包 C 内の関数から 111 件・例 `0x140001329` → `0x1400012f0`)。
  - ネガティブコントロール (1 辺を落とす): `--target 0x140001320` は経路 `0x140008e44 → 0x140008cc8 → 0x140001fa0 → 0x140004a80 → 0x140001e80 → 0x1400014f0 → 0x140001320` で REACHED。辺 `0x140008cc8 → 0x140001fa0` を `--drop-edge` で落とすと `not in C` (同様に `0x140008e44 → 0x140008cc8` でも `not in C`)。
  - この数値は Serum2 の結論ではない。新版の出力形式と `--drop-edge` の動作を確かめるための確認である。
- Serum2 の新版で同じ確認を行う再現コマンド (未実施・§7):

```sh
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c6090 $A7 > slot7_v2.txt   # BFS 深さ・pdata 外・開始点でない宛先の件数
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c9680 --target 0x180498090 --drop-edge 0x1800c9680:0x180498090 > negctl_drop.txt   # 期待: target not in C
```

- 20MiB 超の blob なし (`find tools/targets/serum2/gui -size +20M` 0 件)。

## 6. 完全性の検査 (新版で追加・Serum2 では未取得)

閉包 C は pdata の関数開始点への direct call / tail jmp だけで作る。次の 3 点は「経路なし」の完全性に効くので、新版 `slot_reach.py` が出す。

| 検査 | 出力 | Serum2 の値 |
|---|---|---|
| (a) 閉包の BFS 深さ | `BFS depth from root: max N` と深さの分布 | **未取得** (旧「深さ 15」は撤回) |
| (a) pdata で覆われない `.text` | `pdata coverage: ... uncovered B in N gaps` と、gap 内の direct call/jmp が開始点を指す件数 (線形走査・参考) | **未取得** |
| (b) 開始点でない direct call/jmp | `non-start direct call/jmp`: 関数内 / 他関数の途中 / pdata 外。閉包 C 内からの件数と例 | **未取得** |

- (b) の扱い: 開始点でない宛先は閉包に入れず (旧版と同じ式を保つ)、件数として未解決に数える。件数が 0 でなければ、その宛先の扱いは本表の件数で示す。
- 未解決 (件数が 0 でない場合): pdata 外・他関数の途中への辺は、閉包の外に届く経路として扱う。「経路なし」は、これらの件数を含めて「direct 閉包 (pdata 関数の開始点へ届く辺だけ)」の範囲に限る。

## 7. 未取得の数値と理由 (AGENTS 規範 6・素材)

- 本 run の素材 `$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみで、`plugins-serum2` が無い。PR 本文に `oc_artifacts:` 行が無かったため (WORKFLOW §11: レビュー run の素材は PR 本文の行で決まる)。PR 本文に `oc_artifacts: plugins-serum2` を入れた。
- そのため、新版 (§6・`--drop-edge`) の Serum2 での実測と、§1 の setState 所要の n=3 再測定は未実施。

## 8. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) getState 閉包の間接 call 149 件 (`[reg+disp]` 126・`call reg` 23) の受信型解決。閉包の外へ出る呼出しで `[reg+0x88]` に達するものの有無 | 受入 1 (slot 7 → slot 17 の経路の確定) | [SR-53] (#3398) |
| (b) setState 閉包の `call [rax+0x88]` 2 件 (`0x18049e656`・`0x1804bda03`) の受信型解決 (SC の this か)。デモ bit=0 で Splice 表示が偽になる経路、または非到達の証明 | 受入 3 | [SR-54] (#3399) |
| (c) `+0x22798` の Splice オブジェクトの escape (slot 17 の `r14`)、`+0x20408` の書込元 `0x1803573f0` の呼出元、`+0xb8` (`[rax+0xb8]`) の全 `.text` 列挙 | 受入 2 の後段・(b) の入力 | [SR-54] (#3399) |
| (d) 新版の Serum2 実測 (§6 の 3 点・ネガティブコントロール・setState の n=3 所要) | 受入 1 の深さ・完全性、測定作法 | 本 PR の再測定 (素材 `plugins-serum2` を PR 本文の `oc_artifacts:` で指定) |
</content>
