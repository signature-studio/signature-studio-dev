# PLG-P0b-64 (#5663, 親 #4940) — Dispatcher (0x13173a0) の HostTag 供給元

部分達成 (`Refs #5663`)。受入 1 は既測 (`REPORT_DISPATCHER_APPENDIX.md` §B-2)。受入 2 は未達 (供給元の呼出元を特定できず)。

## 1. 測定

- 基点: `origin/main` f195a93a9。追加は `hs_disp_callers.py`・`hs_disp_refs.py` と本ファイルのみ。
- ベースライン `hs_disp_emu.py` (`HS_DISP_PATH=1`・既定 0 埋め・全 256 ID): real 70.21 秒、終了時 load 1.04 (`uptime` 1 分平均)。distinct (rax, path) = 109、rbp_ok 229 / mismatch 0 / unreached 27 で、既存 §D と一致。

## 2. 確定した事実

| 項目 | 結果 | 測定 |
|---|---|---|
| Dispatcher への直接 E8/E9 | **0 件** | `hs_disp_callers.py` (全 .text を rel32 で走査) |
| Dispatcher を指す絶対 qword | **1 件**: `0x1314178` (vtable VMT+0x70 = slot 0) | `hs_disp_refs.py` (a) |
| Dispatcher を指す rip 相対参照 | 0 件 | `hs_disp_refs.py` (b) |
| 検算: `0x1321e12 call 0x40fe90` (REPORT の既知 call) | 生バイトの E8 rel32 走査で一致 | capstone の線形逆アセンブルは同じ call を 0 件と返した (解析器の走査が不完全)。直接呼出しの列挙は生バイト走査の値を採る |

- 直接呼出が無いので、Dispatcher は vtable slot 0 (間接) 経由でのみ呼ばれる。rdx (HostTag) は plugin 側 `[plug+0x08]` から来る (`tools/plugins/ABI.md` の Dispatcher 呼出列 (`rdx=this->HostTag([+8])`)・`hostshim.c` の `PLUG_HostTag`)。その値は `CreatePlugInstance(Host, Tag)` の Tag (ABI.md §1.1: `mov [rax+8], rcx(=Tag)`)。
- 注意: `hs_disp_refs.py` の初版は `ImageBase` を二重に足して 0 件を返した。修正後の値を上に載せた。

## 3. 未確定 (供給元不明)

- FLEngine (block00031) の plugin ローダで `CreatePlugInstance` を呼ぶ箇所は**未特定**。
  - 文字列 `CreatePlugInstance` (UTF-16) は block00031 に RVA `0x98ceee`・`0xf2c7c2` の 2 箇所あるが、この VA を指す絶対 qword・abs32・rva32・rip 相対のいずれも検出されなかった。
  - ASCII 版と `GetProcAddress` の ASCII 文字列は、block00031 で `GetProcAddress` が 1 箇所見つかっただけ。ローダの取得経路の本体は未解析。
- よって Tag の実値 (HostTag の値) と、その生成元 (定数・ファイル内の文字列・呼出し側の計算) は**未確定**。

## 4. 次に必要な作業

1. block00031 の `GetProcAddress` の IAT 参照 (`call [rip+...]`) を列挙し、その戻り値を呼ぶ箇所 (`call rax`・`call [reg+disp]`) を追う。
2. その呼出し側で `CreatePlugInstance` の第 2 引数 (rdx) を作る命令を、直前の書込みから逆向きに出す。
3. 得た供給元の値で `hs_disp_emu.py` の `TAG` を差し替えて再測定する (HostTag 依存の r8d・応答への影響を見る)。

## 5. 使い方

```
FL_WIN64_DIR=<fl-win64 展開先> PYTHONPATH=<pefile・capstone・unicorn 入り lib> \
  python3 tools/plugins/framework/hostshim/hs_disp_callers.py
FL_WIN64_DIR=... PYTHONPATH=... python3 tools/plugins/framework/hostshim/hs_disp_refs.py
```

## 6. 逆向き追跡 (測定 commit: 8a96c570c・base: origin/main e5261de58)

測定 commit `8a96c570c` (`hs_tag_chain.py` の段 1 表示を直した commit。コードを変えた最後の commit)。base (main) は `e5261de58`。`git diff 8a96c570c HEAD -- tools/plugins/framework/hostshim ':!*.md'` は 0 行。測定出力は `hs_tag_chain.py` 再実行で 65 行・rc=0 (直前の `6d540293c` の版は段 1 が `LOADER_FN` 先頭だけを出していた)。

スクリプト: `hs_tag_chain.py` (生バイト走査 + capstone の線形逆アセンブル。`0x132c711` は呼出し箇所から逆アセンブルして確認)。

| 段 | 確定した事実 | 根拠 |
|---|---|---|
| 1 | `0x132c711`: `lea rdx,[rip+0xaa]` (UTF-16 名) → `call 0x4235f0` (名前で関数を引く wrapper) → `mov rcx,[rip+0x6425f7]`・`mov rdx,[rbp+0x30]` → `call rax` (CreatePlugInstance 相当) | 逆アセンブル |
| 2 | 関数先頭は `0x132c680` (`push rbp; sub rsp,0x60`)。`[rbp+0x30] = r8` で保存。第 3 引数 r8 がそのまま Tag 候補 | 逆アセンブル |
| 3 | `0x132c680` の直接 E8 呼出元は **1 件** `0x132eea0`。そこで `r8 = [rbp+0x38]` | 生バイト走査 |
| 4 | `[rbp+0x38]` の書込みは `0x132ee0c` の **1 件** `mov [rbp+0x38], rcx`。関数先頭 `0x132ee00` の第 1 引数 rcx | 逆アセンブル |
| 5 | `0x132ee00` の直接 E8 呼出元は **5 件**: `0x10f2372`・`0x10f24b2`・`0x10f2cc4`・`0x10f2d90`・`0x132f43f` | 生バイト走査 |

### 訂正

以前の版の「`[rbp+0x30]` が Tag の候補 (定数・文字列の可能性)」は中間段の値で、実値の候補ではない。引数の対応は次のとおり (段 1〜4 の逆アセンブルで確認)。

- `0x132c680` の引数: rcx → `[rbp+0x20]`、rdx → `[rbp+0x28]`、r8 → `[rbp+0x30]`。
- 段 1 の `call rax` は rcx = `[rip+0x6425f7]` (Host 相当の大域)、rdx = `[rbp+0x30]` (= 第 3 引数 r8)。よって Tag 候補は `0x132c680` の第 3 引数。
- 段 4 で `0x132ee00` の rcx は object ポインタとして使われる (`mov rbx,[rax]; call [rbx+0x30]`)。Tag は定数ではなく object ポインタの値と読める。
- Dispatcher 側の HostTag (`[plug+0x08]`) との接続は、ABI.md §1.1 の `mov [rax+8], rcx(=Tag)` に従う。段 1〜5 は CreatePlugInstance の Tag 引数までの鎖であり、plugin 側 `[+8]` へ届く経路は未追跡。

### 未確定 (供給元不明)

1. **5 件の呼出元 (段 5) の rcx** が何の object か。4 件 (`0x10f2372`・`0x10f24b2`・`0x10f2cc4`・`0x10f2d90`) は rcx が `[rbp+0x98]` / `[rbp+0x88]` / `[rbp+0x90]` 系の実行時ローカルか、`[rax+0x134c]` 等のグローバル由来で、ファイル内の定数では決まらない。
2. `0x132f43f` は rcx = `[rbp+0x20]`、rdx = `[rbp+0x38]` (`call 0x41c650` の結果)。`[rbp+0x20]` の供給元は未追跡。
3. `0x4235f0` が GetProcAddress 相当であることは、名前引数の使い方からの推定。IAT 参照としては未検証。
4. `0xd8cb86` (`lea rdx,[rip+0x361]`) 経路は、今回の追跡対象に入れていない。

よって受入 2 の「実値の供給元」は、**機械語上は段 5 の 5 件の呼出元まで特定**し、その先の object の生成元は上記 1〜2 を未確定として残す。

## 7. 段 5 の rcx 由来 (測定 commit: 本節の commit・`hs_tag_rcx.py`)

`hs_tag_rcx.py` (新規) で段 5 の 5 件と、`0x132f3f0` の呼出元 `0x12ba5ec` の rcx を、関数先頭 (`push rbp` の直前が `int3`/`ret`/`nop` の位置) から呼出し直前まで逆アセンブルして出す。関数先頭は近似で、窓の外の書込みは見ていない。

| 呼出元 | 関数先頭 | rcx の直前の設定 | 由来 |
|---|---|---|---|
| `0x10f2372` | `0x10f2170` | `mov rcx,[rax+0x134c]` (`0x10f2358`) | グローバルオブジェクト `[[rip+0x4ee348]+0x134c]` |
| `0x10f24b2` | `0x10f2170` | `mov rcx,[rbp+0xa8]` (`0x10f2498`) | 直前の `call 0x10041f0` の戻り値 |
| `0x10f2cc4` | `0x10f2b20` | `mov rcx,[rax+0x134c]` (`0x10f2caa`) | グローバルオブジェクト `[[rip+0x4ed9f6]+0x134c]` |
| `0x10f2d90` | `0x10f2b20` | `mov rcx,[rbp+0x98]` (`0x10f2d76`) | 直前の `call 0x10041f0` (`0x10f2d20`) の戻り値 (`0x10f2d25` で `[rbp+0x98]` に格納) |
| `0x132f43f` | `0x132f3f0` | `mov rcx,[rbp+0x20]` (`0x132f437`) | 引数 rcx (第 1 引数) |

- `0x132f3f0` の呼出元は E8 で **1 件** `0x12ba5ec`。その rcx は `[rbp+0xa0]` で、`0x12ba440` の第 1 引数 rcx を `[rbp+0xa0]` に保存している (`0x12ba468`)。
- `0x12ba440` の直接 E8 呼出元は 2 件 (`0x12bd623`・`0x12bf722`)。どちらも rcx = `[rbp+0x20]` (引数)。
- `0x12ba440` を指す絶対 qword は 1 件 (`0x12b0380`)。そこは関数ポインタの表 (隣接エントリ `0x12bb450`・`0x12bb140`・`0x12ba8c0` …) の一部。表を引く側の参照は、絶対 qword・rip 相対のどちらでも検出できなかった。

### 結論 (受入 2 の判定)

- 段 5 の object (rcx) は、**グローバル (`[rip+X]+0x134c`)・実行時の戻り値 (`call 0x10041f0`)・関数引数**のいずれかで、ファイル内の定数に決まる箇所は無い。
- `0x12ba440` 系は関数表経由の呼出しで、表の引数の値は機械語だけでは決まらない。Tag の実値は **未確定 (供給元不明)**。
- 受入 2 は未達のまま。新しく確定したのは、`0x12ba440` の表経由の呼出しと、5 件の rcx の由来の分類 (上表)。

### 未確定 (本 issue に残す)

1. `0x12b0380` の関数表を引く呼出側 (表 + インデックス、または表の走査) の特定。
2. `0x10f24b2`・`0x10f2d90` の `call 0x10041f0` の戻り値の供給元。
3. unicorn 未導入のため `hs_disp_emu.py` の再測定は未実施。

## 8. `0x10041f0` の戻り値 (測定: `hs_tag_obj.py`・本節の commit)

`0x10f24b2` と `0x10f2d90` の rcx は `call 0x10041f0` の戻り値。`hs_tag_obj.py` (新規) で関数本体と直下の 2 関数を逆アセンブルした。

| 項目 | 結果 |
|---|---|
| `0x10041f0` の直接 E8 呼出元 | **28 件** (`0xd9b19d` 〜 `0x12fe554`。`0x10f2449`・`0x10f2d20` を含む) |
| 本体の動き | 引数 ecx・edx・r8d を ebx・esi・edi に保存 → `call 0x1003be0` (ecx は `[[rip+X]]+0x10` と比較) → 戻り値 r13 に対し `call 0x1003c20`・`call 0x1003d40` (edx・r8d・r9d を渡す) → `r13` を返す |
| `0x1003be0` | 引数の index を比較して `call 0xff5aa0` (確保系と見られる) で領域を得る。実行時にだけ決まる |
| `0x1003d40` | 得た領域を `[rbp+0x30..]` に初期化。`call 0x12d0b90` の結果で分岐。値は実行時の状態に依存 |

結論: `0x10f24b2`・`0x10f2d90` の rcx は**実行時に作られるオブジェクトのポインタ**で、ファイル内の定数には決まらない。段 5 の 5 件は、グローバル (`0x10f2372`・`0x10f2cc4`)・実行時オブジェクト (`0x10f24b2`・`0x10f2d90`)・関数引数 (`0x132f43f`) のいずれかで、どれも定数ではない。よって Tag の実値 (受入 2) は**未確定 (供給元: 実行時の値)** のまま。

### 未確定 (本 issue に残す)

1. `0x12b0380` の関数表を引く呼出側 (表 + インデックス) の特定。
2. `0x12d0b90` の分岐条件 (`0x1003d40` 内)。Tag の選択に効くか未確認。
3. unicorn は `$RUNNER_TEMP` に導入済みだが、`hs_disp_emu.py` の TAG は実値が無いため差し替えず、再測定は未実施 (受入 1 への影響は未確認)。



## 9. 関数表 0x12b0380 の呼出側の走査 (PLG-P0b-67・#5871・測定: `hs_tbl_refs.py`・`hs_tbl_abs.py`)

表の範囲: `0x12b02e0` から 49 エントリ (`0x12b0468` まで。両端の隣接値は関数ポインタでない)。`0x12b0380` は index 20 で、値は `0x12ba440` (§6 の表経由の呼出しと一致)。

| 走査 | 対象 | 結果 | 測定 |
|---|---|---|---|
| RIP 相対の実オペランド (線形逆アセンブル 5,022,467 命令) | 表の先頭 ±0x100 | 4 件。すべて `0x12b0290` を指す (`0xd74f50`・`0xd9a8b7`・`0x10fc497`・`0x12497bb`)。表 `0x12b02e0` は 0 件 | `hs_tbl_refs.py` |
| 絶対 disp・即値 (同じ線形走査) | 表の先頭 ±0x188 | 4 件。いずれも条件分岐 (`jo`・`jne`・`jae`) の即値 (分岐先) で、表参照ではない | `hs_tbl_abs.py` |
| PE 全体のバイト列 | `0x12b0380`・`0x12b02e0` を 8 バイト・4 バイトで検索 | 0 件 | 直接の Python 検索 |

- 表を指す命令 (rip 相対・絶対) も格納された表ポインタも無い。よって呼出側は**表の先頭を一切参照せず、表の基底は別の経路で得られる** (レジスタ・構造体のフィールド・計算値)。
- `0xd74f50`・`0xd9a8b7` 系の 4 件は `0x12b0290` (表の手前 0x50) を指し、表 `0x12b02e0` とは別の表。本節では扱わない。
- 受入 1 は**未達** (呼出側を機械語から特定できず)。受入 2 は `hs_disp_emu.py` が Dispatcher (`0x13173a0`) の内側だけを実行し、関数外の呼出しを戻り値 0 で返すため、`0x132ee00` (プラグインのローダ経路) には届かず、rcx の採取は**この run では未実施**。
