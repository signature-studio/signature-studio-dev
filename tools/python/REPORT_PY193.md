# PY-193 (#3380): 表示通知 0xbd68e0 の受け手 (0x666780・0x666680・0x423980) とフラグ表の立つ条件の PE 確定

親: #3288 (PY-183)。前段: `tools/python/REPORT_PY176.md` §5・§6、`REPORT_PY175.md`、`REPORT_PY91.md`。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論 (PE 実測で確定した範囲)

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. `0x666680` の本体と `0x666780` の枠の形 | **確定** (書込み側)。消費側は未解析 | §2・§3 |
| 2. `0x423980`・`0x4232e0` の本体 | **確定**。どちらも `EnterCriticalSection` / `LeaveCriticalSection` の IAT 薄いスタブ。issue 本文の「表示オブジェクト `[0x15e0d10]` の前処理」は誤り | §4 |
| 3. フラグ表 `0x16b6dcc+0xa` の書込み元と通知条件 | **block00031 内で、非 0 の直接書込みは 0 件**。F を指す rip 相対の lea は 2 件 (0xbd68e7・0xbd68f5、どちらも 0xbd68e0 内)。F への store は 0xbd68fc の `mov byte ptr [r8+rax], 0` (0 を書く clear) の 1 箇所だけ。通知は F[0xa] ≠ 0 のときだけ出るため、直接経路では 10519c6 枝の通知は発火しない。間接書込み (`.data` の `0x15e0550` 経由) は未確定 | §5 |
| 4. 通知先 `0x16b6e00` の書込み元 | **block00031 内で、直接の store は 2 箇所 (確保・解放)** で確定。確保・解放関数の呼出し元と `.data` 経由の書込みは未確定 | §6 |

受入は本 PR の 4 件に縮めた (issue #3380 本文も同じ範囲に縮めた)。縮めた issue は `Closes #3380` で閉じる。未達の範囲は子 #3433 [PY-196] へ移した。未解決は §8 の表。

## 測定

- 測定の commit 履歴: `814363a2a` で `analysis/flapi/pe_py193_refs.py` を追加。`4b8ecc73d`・`6d404849a` でチャンク境界の行送りを直した (後述)。本 PR の残りの commit は REPORT と DOC_MAP だけ。
- 測定 commit (コードを変えた最後の commit): `6d404849a`。このコミットで、`pe_py193_refs.py` と `pe_xref.py` のチャンク境界の行送りを直した (旧 `off = end + 1` は、チャンク上限で切れた命令の先頭 1 バイトを飛ばしていた。修正後は `off = end`)。この PE では修正の前後で件数が変わらないことを確認した (`pe_py193_refs.py 16b6dc0 16b6e40` は修正前後で出力が同一 (hits 38・命令数 5022467)、`pe_xref.py` は 41 件)。
- 差分の証跡: `git diff 6d404849a HEAD -- tools/python/analysis` の出力は 0 行 (本 REPORT の commit は docs のみ)。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` (real 2.902 秒・1 回)。`$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) の実在を `ls` で確認済み。展開先は repo 外の一時領域で `FL_WIN64_DIR=<展開先>` で指定。
- 所要・load (測定中の 1 分値 0.52〜0.99、並列 1、nproc 4。`6d404849a` で実行): `pe_py193_refs.py 16b6dc0 16b6e40` 64.7 秒 (hits 38)・`pe_py193_refs.py 16b5000 16b6e40` 65.4 秒 (hits 204)・`pe_xref.py 0x15e0550,0x15e2e18,0x1378b10` 63.4 秒 (hits 41, stores 0。内訳 0x15e0550 が 6・0x15e2e18 が 35・0x1378b10 が 0)・`pe_slot_writers.py 0x15e0550` 64.4 秒 (slot_loads 6・candidates 0)。`pe_callgraph.py callers` と逆アセは未計時。e2e ではない。
- 数え方: 「hits」は `pe_py193_refs.py` が出力する行数。範囲内を指す rip 相対・絶対 disp・即値・base+disp の全オペランドを数える。命令数 5,022,467 (`.text` の線形走査。無効バイトは 1 バイト進めて再同期)。
- ポジティブ・コントロール: `pe_py193_refs.py 16b6dc0 16b6e40` の出力に `0xbd68e7` と `0xbd68f5` (フラグ表 `0x16b6dcc` を指す `lea`) が含まれる。既知の 2 件を検出できる。
- ネガティブ・コントロール: **未実施** (時間制限)。代わりに `pe_py193_refs.py 16b5000 16b6e40` の 204 件が全て rip 相対であることを確認 (即値・絶対 disp・base+disp の範囲内ヒットは 0 件)。

## 1. 0x666680 (枠を借りる。ロックを保持したまま返す)

```
Enter(obj+0x38)                         0x666688  call 0x4232e0
P = [obj+0x18]          (カーソル)      0x666691
Q = [P+8]                               0x666695
if Q != [obj+0x10]: return Q            0x666699  (ロック保持のまま)
else if 0x666470(obj, P): return [P+8]  0x6666a8  (増設後の新枠。ロック保持)
else: Leave(obj+0x38); return 0         0x6666bb  (満杯)
```

- `obj+0x10` は番兵 (リングの先頭ノード。`0x6664c0` で `[obj+0x10] = [obj+8]` と初期化)。`obj+0x18` はカーソル (最後に書いた枠)。`node+8` は次ノード。
- `0x666470(obj, P)` (増設): `[obj+0x30] < [obj+0x34]` なら `new = 0x40f9e0([obj+0x28], dl=1)`、`P+8 = new`、`new+8 = 旧 P+8 (番兵)`、`[obj+0x30]++`、戻り値 1。上限到達なら 0 (増設しない)。`obj+0x30` が件数、`obj+0x34` が上限。

## 2. 0x666780 (枠を書く。引数は obj・v1 (rdx)・v2 (r8)・v3 (r9))

```
Q = 0x666680(obj)
if Q != 0:
    Q.+0x10 = v1          (rsi)
    Q.+0x18 = v2          (rdi)
    Q.+0x20 = v3          (r13)
    obj.+0x18 = [obj.+0x18 + 8] = Q   (カーソルを Q へ進める)
    Leave(obj+0x38)
```

- 枠 (node) の形: `+0x8` = 次ノード (書込みは増設時のみ)、`+0x10` = v1、`+0x18` = v2、`+0x20` = v3。0x666780 はこの 3 フィールドだけを書く。
- 静的な呼出し元は 19 箇所 (16 関数。`pe_callgraph.py callers 0x666780`)。このうち `0xbd68e0` の `0xbd691d` だけを追う。`0xbd68e0` の引数は `rdx = 0` (`xor r8,r8` → `mov rdx,r8`)、`r8 = id` (`movsxd r9, ecx` → `mov r8, r9`)、`r9 = dl` (引数の flag)。よって `0xbd68e0` の枠は `(+0x10, +0x18, +0x20) = (0, id, flag)`。
- 消費側 (枠を読む関数) は未解析 (受入 1 の残り → 子 #3433)。

## 3. 0xbd68e0 (フラグ表の判定と発火。引数 ecx = id、edx = flag)

```
if F[id] == 0: return                      (F = 0x16b6dcc の byte 表)
F[id] = 0                                  (同じ base 0x16b6dcc へ 2 回目の lea で書く)
0x666780([0x16b6e00], 0, id, flag)
```

- F を指す rip 相対の lea は `0xbd68e7` と `0xbd68f5` の 2 箇所だけ (`pe_py193_refs.py`。範囲 `16b6dc0`〜`16b6e40` の rip 参照 38 件で確認)。どちらも base が `0x16b6dcc`。`0xbd68e7` の先の `0xbd68ee` が読み (`cmp byte ptr [r8+rax], 0`)、`0xbd68f5` の先の `0xbd68fc` が 0 を書く store (`mov byte ptr [r8+rax], 0`)。逆アセで確認 (`pe_disasm.py 0xbd68e0 40`)。
- 通知先 `[0x16b6e00]` は `0xbd6901` で読んで `rcx` に入れる。null の場合は `0x666680(null)` が `obj+0x38` (= 0x38) を Enter して落ちる。この経路は F が立つときだけ通る (推定。F を立てる経路は §5 で未確定)。

## 4. 0x423980 と 0x4232e0 (ロック・アンロック)

- `0x4232e0`: `jmp [rip+0x154e24a]` → スロット VA `0x1971530` の値 `0x1573a7e` (IAT のヒント/名前 RVA)。名前は `EnterCriticalSection`。
- `0x423980`: `jmp [rip+0x154dc72]` → スロット VA `0x19715f8` の値 `0x1573c64`。名前は `LeaveCriticalSection`。
- 確認: `pe_rip_consts.py 0x4232e0 2`・`0x423980 2`。ヒント/名前は `pefile` で VA `0x1973a7e`・`0x1973c64` から読んだ (`\x00\x00EnterCriticalSection`・`\x00\x00LeaveCriticalSection`)。
- 引数は `rcx` = `CRITICAL_SECTION*`。`0x666680`・`0x666780` では `rcx = obj+0x38` (キューの持ち主のロック)。issue 本文の「表示オブジェクト `[0x15e0d10]` の前処理」は当てはまらない (`0x15e0d10` は 0x4232e0 の引数に現れない)。

## 5. フラグ表 F = 0x16b6dcc の書込み元 (受入 3)

| 検査 (範囲は block00031) | 結果 |
|---|---|
| rip 相対で F を指す命令 (`pe_py193_refs.py 16b5000 16b6e40`) | 0xbd68e7 (lea)・0xbd68f5 (lea)。どちらも `0xbd68e0` の中。lea の先の store は 0xbd68fc の 1 箇所 (0 を書く) |
| 絶対 disp・即値・base+disp で F の範囲 (0x16b6dc0〜0x16b6e40) を指す命令 | 0 件 (`pe_py193_refs.py 16b6dc0 16b6e40` の内訳は `by_kind={'rip': 38}`) |
| F[0xa] (= 0x16b6dd6) を指す rip 参照 | 0 件 (上の rip 38 件の参照先に 0x16b6dd6 は無い) |
| `.data` に F のアドレスを格納するスロット | `0x15e0550` (qword `0x16b6dcc`、`.data` 内オフセット +0x23b550) |
| 上のスロットの読込み (`pe_xref.py`) | 6 箇所: 0x1192fe2・0x119909a・0x11fe887・0x11fe894・0x121f5d5・0x125a486 |
| 上のスロットを読んだ直後 0x40 バイトの `mov [reg+disp], ...` (`pe_slot_writers.py`) | 候補 0 件 (窓 0x40 の限界あり) |

結論 (受入 3):
- **直接経路** (block00031 内で F のアドレスを命令が直接持つ経路): F[id] を非 0 にする store は無い。F への store は 0xbd68fc の 0 を書く clear の 1 箇所だけ。よって直接経路では F[0xa] は常に 0 で、`0xbd68e0(0xa, 0)` (10519c6 枝) は 0x666780 に達せず通知を出さない。
- **間接経路**: `0x15e0550` 経由の 6 箇所の読込み先が F に書くかは未確定 (子 #3433)。書けば、その経路の F[id] が立つ条件が通知条件になる。

## 6. 通知先 `0x16b6e00` と確保・解放 (受入 4)

直接参照 (`pe_py193_refs.py 16b5000 16b6e40` で `0x16b6e00` を指す命令は 4 件。うち store 2 件):

| VA | 命令 | 所属関数 | 意味 |
|---|---|---|---|
| 0xbd69f0 | `mov [0x16b6e00], 0` | 0xbd69d0 (解放) | 解放後に null |
| 0xbd6a28 | `mov [0x16b6e00], rax` | 0xbd6a00 (確保) | 生成した枠キューを格納 |
| 0xbd6901 | `mov rax, [0x16b6e00]` | 0xbd68e0 | 発火の通知先 (§3) |
| 0xbd69e4 | `mov rcx, [0x16b6e00]` | 0xbd69d0 | 解放の対象 |

- 0xbd6a00 (確保): `cnt(0x16b6e08)--`; `cnt == -1` なら `[obj] = 0x6666d0([rip-0x57084b], dl=1, r8d=0x40)`。`0x6666d0` は 0x40 件のキューの生成 (`0x666570` が初期化。推定)。
- 0xbd69d0 (解放): `cnt++`; `cnt == 0` なら `0x40faa0([obj])` で解放し `[obj] = 0`。
- `cnt` (0x16b6e08) を触るのは 0xbd69d4・0xbd69db・0xbd6a04・0xbd6a0b の 4 箇所だけ (同じ 2 関数)。`.bss` で初期値 0 (PE に初期値は無い)。よって最初の確保で `cnt` が -1 になり生成される。
- 直接 call 元: 0xbd69d0・0xbd6a00 とも 0 件 (`pe_callgraph.py callers 0xbd69d0,0xbd6a00`)。
- 関数ポインタの組: `.text` の VA `0x1378b10` = `0xbd6a00`、`0x1378b18` = `0xbd69d0` (qword。`.text` 内オフセット +0xf77b10・+0xf77b18)。この組を指す rip 相対参照は 0 件 (`pe_xref.py 0x1378b10`)。参照元は未確定 (子 #3433)。
- `.data` の VA `0x15e2e18` に `0x16b6e00` (qword) が格納されている (`.data` 内オフセット +0x23de18)。このスロットの読込みは 35 箇所 (`pe_xref.py 0x15e0550,0x15e2e18,0x1378b10` の 41 件 = 0x15e0550 の 6 + 0x15e2e18 の 35 + 0x1378b10 の 0。HEAD `6d404849a` で再測定)。読んだ先が `0x16b6e00` へ書くかは未確定 (子 #3433)。

結論 (受入 4): block00031 内で `0x16b6e00` を rip 相対で指す store は 0xbd6a00 (確保) と 0xbd69d0 (解放) の 2 箇所だけ。確保・解放の呼出し元 (間接) と、`.data` 経由の書込みは未確定。

## 7. 通知の条件 (まとめ)

- 10519c6 枝 (`0x1051720` 側) の `0xbd68e0(0xa, 0)` は、F[0xa] ≠ 0 のときだけ `0x666780([0x16b6e00], 0, 0xa, 0)` を呼ぶ (`REPORT_PY176.md` §5 の 7)。
- block00031 内で F[0xa] を立てる直接の store は無い (§5)。よって直接経路では枝内の UI 通知は枠に乗らない。
- 枠の消費側と、F・通知先の間接書込みが確定すれば、通知が出る条件 (F[0xa] の立つ条件) を完全に言える。現時点では「block00031 内で非 0 の直接書込み 0 件」が確定事実。

## 8. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.data` 0x15e0550 の読込み 6 箇所の書込み有無 (F の間接書込み) | 受入 3 の通知条件 | 子 #3433 [PY-196] |
| `.data` 0x15e2e18 の読込み 35 箇所の書込み有無 (`0x16b6e00` の間接書込み) | 受入 4 | 子 #3433 [PY-196] |
| 関数ポインタの組 0x1378b10 (`0xbd6a00`・`0xbd69d0`) の参照元 | 確保・解放の呼出し元 | 子 #3433 [PY-196] |
| 枠 (+0x10・+0x18・+0x20) の消費側 | 受入 1 の「意味」 | 子 #3433 [PY-196] |
| `0x6666d0` の生成物 (`0x666570` の初期化) | キューの上限・初期化の確定 | 子 #3433 [PY-196] |
| 0xbd68c7〜0xbd68d7 の `dword [0x16b6dc8]` の計数 (F とは別) | 通知の別条件の有無 | 子 #3433 [PY-196] (受入に追加) |
| 同じ展開の他の `*_PE.bin` 312 本 (`0x16b6dcc`・`0x16b6e00` の参照) | 他ブロックからの書込みの有無 | 子 #3433 [PY-196] (受入に追加。ImageBase が同じかを含めて確認) |
| ネガティブ・コントロール (1 バイト改変で FAIL) | 検出器の感度の数値化 | 未実施。PR 本文に記載 |

## 9. 再現

```
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 0x666680 120     # §1
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 0x666470 120     # §1 増設
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py 0xbd68e0 90      # §3
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_consts.py 0x4232e0 2   # §4
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py193_refs.py 16b5000 16b6e40   # §5・§6 (rip 参照 204 件)
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_callgraph.py callers 0x666780    # §2 (19 箇所)
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_xref.py 0x15e0550,0x15e2e18,0x1378b10   # §5・§6 (41 件)
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_slot_writers.py 0x15e0550       # §5 (候補 0)
```

範囲外: 他の `*_PE.bin` (312 本) と、`.text` 以外の直接参照 (`.data` の値自体の意味)。
