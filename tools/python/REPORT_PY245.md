# tools/python REPORT: PY-245 0xfdd2c0 の送出ゲート (0x60c220・0x728f50・0xfdeaf0) と mode 源 (0xfdd270) の同定 (#3758, 親 #3035)

> 依存: 前段の `tools/python/REPORT_PY140.md` と probe `analysis/flapi/pe_ui_dispatch_probe.py` は PR #3768 (`3035-py140-ui-ops`、未 merge) にあり、main には無い。PR #3788 も同じ 2 ファイルを追加する。本 REPORT は依存解消前の草稿で、PR はまだ作っていない (規約: 前提の別 PR が未 merge の作業は着手しない)。
> 素材は fl-win64 の `extracted/block00031_PE.bin` (capstone 5.0.7・pefile)。VA は block00031 の絶対 VA。逆アセンブルは `pe_ui_ops_probe.py` と同じ方式。

## 結論

- 送出ゲートの判定順と式を VA 付きで確定した (`0xfdd2c0`・`0xfdd3e9`〜`0xfdd77a`)。mode 源 `0xfdd270` の式も確定した。
- **ゲート 3 (`0xfdeaf0` を呼んで status 5) が先に効く。** 式は `S ∧ fifth==0`、`S = bl ∨ (mode&0x20 ∧ ¬Q(op))`。`0xd84680` は fifth=0 を渡すので、ui 系の呼出しは S が真なら必ず status 5 で止まる。
- **ゲート 1 (`0x60c220`) は fifth=0 の経路では到達しない。** G1 ブロックは bl≠0 を要するが、bl=1 なら S=1 で G3 が先に抜ける。G1 に届くのは fifth≠0 の呼出しだけ (probe の `--fifth 1` で確認)。
- ゲート 2 (`0x728f50`) は **flags** の bit 0x4 (r9d。`0xd84680` では 0xf) で有効になり、`[0x15f6158]≠0` かつ `0x72afa0` が 1 を返す op (集合 S2 = {0,1,3,7,10,11,13,14,40,41,42,43}) で status 4。
- mode 源 `0xfdd270` は `vtbl[+0x80]` の戻り値を添字とする表 `0x1542bec` (byte) を引き、`0x81c0a0()==0` のとき 0x20 を OR する。式は確定。添字の実値と `0x423470` は実行時値で、静的には未確定 (下の未解決表)。
- `0xd84680` は `0xfdd2c0` の戻り値を **-1 かそれ以外かでしか** `out.status` に写さない (`0xd846b2`〜`0xd846c7`)。status 1/2/4/5 (ゲートで止まった) と 0 (switch 経路) は呼出し側から区別できない。
- issue 本文との差 (PE で訂正):
  1. `[0xfdd2b9]` → 正しくは `0xfdd2b8` (`or bl, byte [rip+0xa]` at `0xfdd2a8` の解決先。byte は 0x20)。
  2. ゲート 2 の bit は mode の 0x4 ではなく **flags** の 0x4。mode の 0x4 は switch 内の arm 毎のゲート (`test al, 4`)。
  3. `0x60c220` は vtbl 呼出しではなく `[obj+0x80]` の関数ポインタ呼出し (`call qword ptr [rbx+0x80]`)。vtbl 呼出しは `0xfdd270` のみ。
  4. ゲート 1 の status は 1 ではなく **ebx** (1 または 2。`0xfdd766` の `imul eax, ebx`)。
  5. S2 は 0x1b〜0x1e ではなく **0x28〜0x2b** (`0x72afa0` の `sub` の連鎖は前段の `sub eax, 0xd` の後の値に対して続くため。probe の DFS で確認)。
  6. 「送出 leaf (15 関数)」という数は再現できなかった。probe の到達 call 先は mode 0x06 で 100 件。どれが「送出」かは未確定 (#3035 の範囲)。

## 確定事項 (VA)

### 入口と引数 (`0xfdd2c0`)

| 引数 | 格納 | 出所 |
|---|---|---|
| op | `[rbp+0x40]` (ecx) | 0xfdd2ce |
| arg | `[rbp+0x44]` (edx) | 0xfdd2d1 |
| flags | `[rbp+0x48]` (r9d) | 0xfdd2d4。0xd6a9c5 / 0xd846 系は 0xf |
| mode | `[rbp+0x1a0]` (r8b) | 0xfdd3d9 |
| fifth | `[rbp+0x1b0]` (stack 第 5 引数) | 0xfdd535。0xd846a8 が `mov byte [rsp+0x20], 0` で 0 を渡す |

### 判定順

| 順 | 条件 (VA) | 結果 |
|---|---|---|
| 1 | `mode & 2 == 0` (0xfdd3e9〜0xfdd3f3) | 戻り値 -1 |
| 2 | `S ∧ fifth==0` (0xfdd4ef〜0xfdd546)。`S = bl ∨ (mode&0x20 ∧ ¬Q(op))` | `0xfdeaf0(op,arg)` を呼び status 5 (0xfdd553)。0xfdeaf0 の戻り値は使わない |
| 3 | `flags&4` (0xfdd568) ∧ `0x728f50(op,arg) > 0` (0xfdd575〜0xfdd583) | status 4 (`setg`・`shl 2`) |
| 4 | status 0 ∧ `bl≠0` (0xfdd594) ∧ ((ebx==1 ∧ flags&1) ∨ (ebx==2 ∧ flags&2)) (0xfdd5bb〜0xfdd5d6) | `0x60c220(rsi,0x57f,op,arg) > 0` で status = ebx (0xfdd766〜0xfdd769) |
| 5 | status 0 ∧ `flags&8 == 0` (0xfdd77a) | status 0 で終了 |
| 6 | 上記すべて 0 | switch (0xfdd788〜、eax = op) |

G1 ブロック内の op 別の sub-gate (0xfdd616〜0xfdd763、`0x60c220` を r8 = 7・0x16・0x1e・0x21 で呼ぶ) は本 PR では解析していない。probe は 0 と仮定する。

### Q(op) と S2

- Q(op): `0xfde910` の byte が `0x0c` (0xfdd514)。`8≤op≤15 ∧ bit(op-8)` なので Q は op∈{10,11}。
- S2 (`0x72afa0`、ctx・op・arg): op∈{0,1,3,7,10,11,13,14,40,41,42,43} で 1、それ以外は 0 (`0x72b0c2` の `xor ebx,ebx`)。arg は 0x72af60 を呼ぶかだけを決める。arm は B {0,1,3,7} (0x72b003)・E {10} (0x72b09a)・D {11} (0x72b0ae)・A {13,14,40,41} (0x72b02d)・C {42,43} (0x72b077)。
- `0x728f50(op,arg)`: `[0x15f6158] ≠ 0` なら `0x72afa0([0x15f6158], op, arg)`、そうでなければ 0 (0x728f54〜0x728f7b)。

### ゲート 1 (`0x60c220`)

- `0x60c220(rcx=obj, edx=sel, r8=a, r9=b)`: 局所 {sel→+0x20, a→+0x28, b→+0x30, 結果→+0x38=0} を作り、`obj≠0` なら `call [obj+0x80](rcx=[obj+0x88], rdx=&局所)`、結果 (+0x38) を返す (0x60c229〜0x60c25f)。結果は callee が書く。
- callee は `obj+0x80` の関数ポインタで vtbl ではない。obj = rsi (0xfdd5e1 の rcx)。callee の実体は静的に決まらない (rsi が実行時値のため)。

### rsi と bl

- rsi = `[[ [0x15e4c80] ] + 0xcc]` (0xfdd3f8〜0xfdd402)。0xfdd41b〜0xfdd4ce で `[0x15e4b10]`・`0x809260` の結果に置き換わりうる (実行時)。
- bl = `rsi≠0 ∧ 0x40fe90(rsi, [0x801c98])≠0` (0xfdd4d1〜0xfdd4ed)。`0x40fe90(rcx)` は `rcx≠0 ? 0x410010(*rcx)≠0 : 0` (0x40fe90〜0x40feaf。rdx は未使用)。
- ebx: `0x40fe90(rsi, [0xf55e80]) ≠ 0 ? 1 : 2` (0xfdd59c〜0xfdd5b6)。

### mode 源 (`0xfdd270`)

- `obj2 = [[ [0x15e4790] ] + 8]`、`idx = vtbl(obj2)[+0x80]()` (0xfdd275〜0xfdd289、`call qword ptr [rax+0x80]`)。
- `bl = byte[0x1542bec + idx]` (0xfdd28f〜0xfdd29a)。表は 256 byte、distinct 48 種。bit 0x02 を持つ値は 02 03 06 07 0b 0e 12 32 42 62 d3 f2 f3 (13 種)。
- `0x81c0a0() == 0` なら `bl |= byte[0xfdd2b8]` (= 0x20) (0xfdd29f〜0xfdd2a8)。
- `0x81c0a0` (0x81c0a4〜0x81c0bc): `[0x15f70a8] == 0` なら 1、そうでなければ `0x423470() == [0x15f70a8]` で 1、else 0。よって mode の 0x20 は `[0x15f70a8]≠0 ∧ 0x423470() ≠ [0x15f70a8]` のとき立つ。`0x423470` は未同定。

### 呼出し元 (ui 系)

- `0xd6a960` (ui.jog): 0xd6a9ae で `call 0xfdd270` → `al` を `[rsp+0x20]` (mode)、0xd6a9c5 で `[rsp+0x28]` = 0xf (flags)、r8 = 0 (op)、r9d = `[rbp+0x6c]` (arg)、0xd6a9cd で `call 0xd84680`。
- `0xd84680` の直接呼出し元は e8 走査で 40 件 (0xd6783c〜0xd6c1b0。偽陽性を含みうる)。
- `0xd84680` (0xd84687〜0xd846ad): 前提 `0x11d1430` が偽なら戻り値 -2 (0xd84695〜0xd846c9)。真なら `[rsp+0x20] = 0` (fifth) を置いて `0xfdd2c0` を呼ぶ。`eax == -1` のとき `out.status = -1` (0xd846c0)、それ以外は `out.status = 0` (0xd846b7)。
- `0xfdd2c0` の直接呼出し元は e8 走査で 275 件 (`0xd846ad` を含む)。第 5 引数の値は未確定 (下の未解決表)。

### switch の mode 依存

- arm 内の `test al, 4` (mode の 0x04): 0xfdddea・0xfddfc2・0xfddff1・0xfde030・0xfde295・0xfde303。
- epilogue (0xfde862〜0xfde899) は `0x412e40` ×3・`0xfdee80`・`0x412d60` を呼ぶ。全 op で共通に到達する。

## probe (`analysis/flapi/pe_ui_dispatch_probe.py`)

- 上の式をゲート順に書き、switch (0xfdd788〜) は capstone で読んだ分岐を `eax`・`flags`・mode の定数で辿る到達解析。arg に依る分岐は両方を辿る。
- 実行時値は引数で与える: `--bl` `--ebx` `--ctx` `--g1` (既定 0)。`--fifth` の既定は 0 (`0xd84680` の値)。
- 出力: op ごとの結論 (status 5・4・ebx・-1・switch の固有 call 先)。switch の共通 call (epilogue) は差し引き、先頭行に共通 call を出す。
- 解析値の正本はこの probe の出力。REPORT の表は probe の出力から転記した。

### 実測 (測定 commit `c08418484`)

| コマンド (`FL_WIN64_DIR` 設定済み) | 結果 | wall |
|---|---|---|
| `--modes` | 表 distinct 48 種・OR 0x20・Q 0x0c | 3.2 s |
| `--mode 0x22 --bl 1 --ebx 1 --ctx 1` | 全 op status 5 | 3.2 s |
| `--mode 0x22 --bl 0 --ebx 1 --ctx 1` | op 0x00-0x09・0x0c-0xff status 5、op 0x0a-0x0b status 4 | 3.2 s |
| `--mode 0x02 --bl 0 --ebx 1 --ctx 1` | S2 の op は status 4、他は switch。mode&4 が 0 で arm の多くは閉じる | 3.2 s |
| `--mode 0x06 --bl 0 --ebx 1 --ctx 1` | mode&4 の arm が開く。op 別の固有 call 先の異なり 100 件 | 3.2 s |
| `--mode 0x02 --fifth 0 --bl 1 --ebx 1 --ctx 1 --g1 1` | 全 op status 5 (G1 に届かない) | 3.2 s |
| `--mode 0x02 --fifth 1 --bl 1 --ebx 1 --ctx 1 --g1 1` | S2 の op は status 4、他は G1 で status 1 (ebx=1) | 3.2 s |

`--mode 0x02 --fifth 1 --bl 1 --ebx 2 --ctx 0 --g1 1` の出力では G1 で status 2 (= ebx) になる (`--ops 0x00-0x10` で確認)。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| fifth≠0 の直接呼出し元 (`0xfdd2c0` の呼出し元 275 件のうち `0xd84680` 以外) の第 5 引数。G1 の callee (`rsi+0x80`) と戻り値 | G1 ブロック (status = ebx) に届くか。届かなければ G1 の判定は不要 | 未起票 (候補 PY-254。#3768 の merge 後に起票) |
| `obj2` の vtbl[+0x80] の戻り値 (表添字)、`0x423470` と `[0x15f70a8]`、`bl` の rsi 連鎖、`[0x15f6158]` の初期化元 | mode の実値 (0x20 の有無を含む)、送出 (status 5・4) と switch 到達の成否 | 未起票 (候補 PY-255。#3768 の merge 後に起票) |
| 「送出 leaf」の同定 (probe の到達集合 100 件のうち送出はどれか) | 送出の観測 | #3035 (親。作用先の確定は親の範囲) |

## 検証

- 測定 commit: `c08418484` (probe の追加。`tools/python` のコードを変えた最後の commit)。
- 差分の証跡 (`docs/WORKFLOW.md` §6): `git diff c08418484 HEAD -- tools/python ':!*.md'` は空 (本 REPORT と `docs/DOC_MAP.md` の commit は文書のみ)。
- `python3 -m py_compile analysis/flapi/pe_ui_dispatch_probe.py` rc 0。上の 7 コマンドは rc 0 (各 3.2 s)。load average は 0.13〜0.43 (`uptime`、04:02)。
- ネガティブコントロール: `--fifth 0` と `--fifth 1` の対比 (上の表の 6 行目と 7 行目) で、G1 の到達が fifth だけで切り替わることを示した。
- e2e: 本 PR は解析補助と REPORT のみ。起動・GUI に関わらないので製品 KPI は書かない。
