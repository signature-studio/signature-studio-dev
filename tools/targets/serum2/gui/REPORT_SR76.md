# REPORT — [SR-76 #4484] Serum 2 Splice オブジェクト (`+0x22798`) と `+0x20408` の escape (静的・部分達成)

- 日付: 2026-10-15 / 親: #4242 (SR-63) / 前段: `REPORT_SR63.md` §3・§4・§5(b)
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外。FLEngine 起動・GUI は**動かしていない** (製品 KPI は測っていない)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3` (x86_64-win)。本 run で展開し、`Serum2_win64.vst3` の sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` を実測 (REPORT_SR63 §0 と一致)。作業用 dir はリポジトリ外。
- 測定 commit (解析に使ったコード): `4d24bea3f` (`indirect_upper_bound.py` の追加 commit)。`slot_reach.py` は base の `e87c2ef27` (origin/main) から変更していない。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. `+0x22798` のスロットを渡された callee (ctor `0x1800a9f40` の `lea` 先 `0x180010c60`・dtor `0x1800ac190` の `lea` 先 `0x1800120a0`) が、そのスロットへ書くか | **達成**。`0x180010c60` は `[rcx]` に vptr `0x180a1e038` を書き (`mov [rax], rcx`)、`[rcx+8]=1`・`[rcx+0x10]=0`・`[rcx+0x20]=0` も書く (§2)。`0x1800120a0` は `ret` だけで書かない (§2)。dtor 本体 `0x1800ac6e9` も同じ vptr `0x180a1e038` を書き直す (§3) |
| 2. `+0x20408` の書込元 `0x1803573f0` の呼出元を、間接 call を含めて列挙し demo bit 関数との交わりを示す | **部分達成**。直接の逆閉包 R (8 関数) と setState・getState の閉包 C は交わり 0。`[reg+disp]` の間接 call の上界は 532 件で、demo bit 関数との交わりは 0。ただし demo bit 関数は .text 全体で 2 件 (根そのもの) しかなく、『交わり 0』は弱い結果。レジスタ値の間接 call は解決していない (§4・§5) |
| 3. REPORT に測定 commit と再現手順 | **達成** (§1・§6) |

## 1. 再現手順と実測

```sh
# S: リポジトリ外の作業用 dir。P: tools/targets/serum2/gui
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
uv venv -q venv --python 3.14 && uv pip install -q -p venv/bin/python pefile capstone zstandard
venv/bin/python $P/slot_reach.py Serum2_win64.vst3 0x1800c2b50 --offset 0x22798 --offset 0x20408 --offset 0x227a0 > offs.txt
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x1800aa2f0 0x1800aa3b0   # ctor の lea 周辺
venv/bin/python $P/disasm_range.py Serum2_win64.vst3 0x1800ac760 0x1800ac7c0   # dtor の lea 周辺
venv/bin/python $P/indirect_upper_bound.py Serum2_win64.vst3 0x1803573f0 0x1800c2b50
venv/bin/python $P/indirect_upper_bound.py Serum2_win64.vst3 0x1803573f0 0x1800c6090
```

| 実行 | 所要時間 (実測) | 結果 |
|---|---|---|
| `slot_reach.py` `--offset 0x22798 --offset 0x20408 --offset 0x227a0` | 12.4 秒 (user 12.2 秒) | rc 0・88 行。`0x22798` 7 箇所 (3 関数)・`0x20408` 2 箇所 (2 関数) は REPORT_SR63 §4・§3 と一致 |
| `indirect_upper_bound.py` root `0x1800c2b50` | 7.63 秒 (user 7.52 秒) | rc 0。R=8・C=854・C∩R=0・S=532・S∩demo=0 |
| `indirect_upper_bound.py` root `0x1800c6090` | 7.46 秒 (user 7.32 秒) | rc 0。R=8・C=291・C∩R=0・S=532・S∩demo=0 |

実行環境: 本 run の runner。同 run 内で逐次実行 (並列なし)。実行前の load average 0.11 (1 分平均)。

## 2. 受入 1: `+0x22798` の lea 先 callee の書込み

ctor `0x1800a9f40` (`0x1800aa341` `lea rcx, [rsi+0x22798]` → `0x1800aa34c` `call 0x180010c60`):

```
0x180010c60: mov rax, rcx
0x180010c63: mov dword ptr [rcx + 8], 1
0x180010c6a: lea rcx, [rip + 0xa0d3c7]      ; = 0x180a1e038
0x180010c71: mov qword ptr [rax], rcx        ; slot+0 ← vptr 0x180a1e038
0x180010c74: xorps xmm0, xmm0
0x180010c77: movups xmmword ptr [rax + 0x10], xmm0
0x180010c7b: mov qword ptr [rax + 0x20], 0
0x180010c83: ret
```

→ callee はスロットへ書く (vptr と 0x10・0x20 の初期化)。書かれる vtable `0x180a1e038` は 14 エントリで、R (`+0x20408` 書込元の逆閉包) の関数は含まない (実測)。

dtor `0x1800ac190` (`0x1800ac798` `lea rcx, [rsi+0x22798]` → `0x1800ac79f` `call 0x1800120a0`):

```
0x1800120a0: ret
```

→ callee は書かない (`ret` のみ)。

## 3. 受入 1 (続き): dtor 本体の書込みと vptr の確定

- `0x1800ac6e9` `mov qword ptr [rsi+0x22798], rax` の直前は `0x1800ac6e2` `lea rax, [rip + 0x97194f]` で、`0x1800ac6e2 + 7 + 0x97194f = 0x180a1e038`。ctor と同じ vptr を書き直す。
- `0x180a1e038` を指す rip 相対参照は 3 件 (`0x180014550`・`0x1800ac010`・`0x1800ac190`)。`0x1800ac190` は dtor 自身。`0x1800ac010` の所属関数は本 run では未確認。

## 4. 受入 2: `0x1803573f0` の呼出元

- `+0x20408` の書込 `0x180357931` (`mov [rsi+0x20408], rax`) は `0x1803573f0` 内。読出 `0x1800c96a8` (`0x1800c9680` = slot 17 内)。
- `0x1803573f0` の direct 逆閉包 R = 8 関数 (`0x18004fad0`・`0x1800506b0`・`0x180064d60`・`0x18006fc80`・`0x1800709e0`・`0x180353080`・`0x180353400`・`0x1803573f0`)。R の関数アドレスを格納する vtable スロットは 3 件 (`0x180a24030`・`0x180a240a8`・`0x180a24180`)。その disp は `0x28`・`0x60`。
- 間接 call の上界: `call qword ptr [reg+0x28]`・`[reg+0x60]` (disp が R と一致) の全 .text 中の件数 532。このうち setState 閉包 C 内は 22、getState 閉包 C 内は 3。
- rip 相対で R の関数アドレスを materialise する箇所: 0 件。direct 呼出元 (R の外から): 0 件。
- **demo bit 関数 (`0x22792` を参照する関数) との交わり: 0**。ただし .text 全体で `0x22792` を参照する関数は 2 件 (`0x1800c2b50` setState・`0x1800c6090` getState) のみで、どちらも根そのもの。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) `0x1803573f0` の呼出元。レジスタ値の間接 call (`call reg`・`call [rsp+disp]` の宛先) は宛先を解決していない。上界 532 は disp 一致のみ | 受入 2 の完全な列挙。『交わり 0』は R への経路が間接 call で閉じているという前提に依存 | #4610 [SR-79] |
| (b) demo bit 関数が .text で 2 件 (根のみ) しかない。`0x22792` の読出しは別の経路 (オブジェクト経由の間接読出し) の可能性 | 受入 2 の『交わり 0』の意味 (demo bit 0 の経路を示せていない) | #4610 [SR-79] (同じ子で扱う) |
| (c) `0x180a1e038` (`+0x22798` に書かれる vptr) の vtable 先の関数群の動作と、`0x1800ac010` (同 vptr を参照する所属関数) の未確認 | `+0x22798` の object が Splice 生成の経路に入るか | #4474 [SR-73] |

## 6. 測定 commit・HEAD 再現

- 測定 commit (スクリプトを追加した commit): `4d24bea3f`。HEAD では `indirect_upper_bound.py` のコードは変わっていない (REPORT_SR76.md の追加のみ)。
- `indirect_upper_bound.py` の出力 md5 (root `0x1800c2b50` と `0x1800c6090` の 2 回の出力を連結したもの): `a34fb99a087eaa8fc7e5c7a749044a34`。HEAD で再実行して一致 (§1 の所要時間もこの HEAD 上の実行)。

## 7. 起動・GUI への影響 (AGENTS 規範 2)

- 静的解析のみ。FLEngine 起動・GUI の実行は**動かしていない**。製品 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) の前後は測っていない。
