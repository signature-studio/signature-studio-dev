# PY-262 (#3860): 戻り値 `[rbp+0x584]` の書込み経路と式 (部分・REPORT_PY41.md の PY-65 節の受入 2 の付録)

親: #2034 (PY-65)。前段: `REPORT_PY41.md` の PY-65 節 (受入 2 は未達)・PY-60 (戻り値の書込みと早期 exit の入辺 9 件)。
測定 commit: §4 は `a6ce09858` (`analysis/py262_ret584_paths.py` を追加し、§4 の数値を測ったコードの最後の commit)。§9 は `031d81296` (`analysis/py341_ret584_dominators.py` を追加した commit)。main 取り込み後の HEAD `aca656b8d` で再測定した。測定に使う 5 本 (`py53_dispatch.py`・`py65_ret584_reach.py`・`py262_ret584_paths.py`・`py341_ret584_dominators.py`・`py65_r8d_bits.py`) は `git diff 031d81296 HEAD -- <5 本>` の出力が空 (差分 0)。`git diff 031d81296 HEAD --stat -- tools/python/analysis/` は main 由来の 4 本の追加のみ (`flapi/pe_py183_probe.py`・`flapi/pe_py340_kind1_dispatch.py`・`py235_0xc61250_write.py`・`py342_r8d_ret_cross.py`、計 392 行・測定対象外)。`py65_ret584_reach.py` は main (`ea7f810ca`・`8706f8e89`) で入ったもので、本 PR の commit ではない。
素材: `oc_artifacts: fl-win64` (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`・`block00031_PE.bin` 22,227,016 B)。
再現: `python3 tools/python/analysis/py53_dispatch.py <PE> <work/py53>` → `fn=4664 dispatch=13 r8d_tests=174` (本 run で再現)。続けて `python3 tools/python/analysis/py65_ret584_reach.py <work/py53/fn.txt> 0x104cc65`。

## 1. `[rbp+0x584]` への書込み (関数 0x1046a30〜0x104ccca 内)

| VA | 命令 | 役割 |
|---|---|---|
| 0x1046d79 | `mov dword ptr [rbp+0x584], 0xffffffff` | 初期値 `-1` (0x1046d8d の `jne 0x104cc72` で早期 exit 側へ) |
| 0x104cc6b | `mov dword ptr [rbp+0x584], eax` | 戻り値 (0x104cc65 の `mov eax, [rbp+0x5b8]` を写す) |

読出しは 0x104ccba の `mov eax, [rbp+0x584]` の 1 箇所。0x104cc65 の直前は 0x104cc2e〜0x104cc60 の分岐の合流点で、0x104cc72 は `-1` の早期 exit 側から入る。

## 2. 0x104cc65 に届く `[rbp+0x5b8]` の書込み (後ろ向き CFG 到達・72 件)

経路条件を分けずに、0x104cc65 から前向きの predecessor を辿って `mov dword ptr [rbp+0x5b8], *` に当たった所で止めた。`py65_ret584_reach.py` の出力 (72 件) と、各書込みの値の出どころ:

| 値の出どころ (直前の命令・`py65_ret584_reach.py` の出力と突合) | 件数 | 代表 VA |
|---|---|---|
| `call 0x10469f0` (補間の戻り値。PY-99 の式) | 7 | 0x1047719・0x1047969・0x1047d98・0x1049b31・0x104a494・0x104b305 など |
| `add ecx, eax` (`[reg+0x3b8]` + 値) | 24 | 0x1047c18・0x1047f42・0x1048894・0x104c311・0x104c984 など |
| `mov eax, dword ptr [...]` (構造体フィールド・グローバル・`[rbp+X]` の読み) | 30 | 0x1047e09 (+0x174)・0x1047f9c (+0x180)・0x1048655 (+0x258)・0x104c3f0・0x104c769 など |
| `call qword ptr [rax+0x30]` (vtable 呼出しの戻り値) | 3 | 0x104a8a3・0x104a95f・0x104a9c7 |
| `call 0x40c660` (浮動小数の変換の戻り値) | 4 | 0x10483d3・0x1048ed3・0x104906e・0x10491ed |
| `setge al` / `movzx rax, byte` (bool) | 3 | 0x1048152・0x104821e・0x104ad2e |
| 関数入口 (`mov [rbp+0x5b8], edx`・`edx` は呼出し側引数) | 1 | 0x1046d6b |

合計 72 件 (= 7+24+30+3+4+3+1)。

## 3. 74 件と 72 件の差分 (受入 2・確定)

直接書込み `mov dword ptr [rbp+0x5b8], *` は関数内 74 件。`py65_ret584_reach.py <fn.txt> 0x104cc65 --gap` で 0x104cc65 に届く 72 件との差分を機械的に出した。

| 書込み VA | 直後の書込み (上書き元) | 直線区間 (分岐・ret なし) | 上書き元は 0x104cc65 に届くか |
|---|---|---|---|
| 0x104a876 (`cvtsi2sd`・`mulsd`・`call 0x40c660` の戻り値) | 0x104a8a3 (`call qword ptr [rax+0x30]` の戻り値) | はい | はい |
| 0x104a999 (`call 0x40c660` の戻り値) | 0x104a9c7 (`call qword ptr [rax+0x30]` の戻り値) | はい | はい |

- 0x104a876 と 0x104a999 は、0x104a889 と 0x104a9ac で `r8d` 引数として読まれるだけで、戻り値 (`[rbp+0x584]`) には届かない。
- よって戻り値式に入る `[rbp+0x5b8]` 書込みは 72 件 (§2 の一覧と一致)。74 件のうち差分 2 件は確定。
- 注意: 上書き元 2 件 (0x104a8a3・0x104a9c7) は vtbl 呼出しの戻り値で、呼出し先は未確定 (§2 の「vtbl 呼出しの戻り値 3 件」に含まれる)。

## 4. 代表経路の分岐条件 (run 3・`analysis/py262_ret584_paths.py`)

関数入口 0x1046a30 から各直接書込み (74 件) への CFG 上の最短 1 本を求め、その経路上の jcc と直前のフラグ設定命令を出した (出力は `work/py262/ret584_paths.tsv`・gitignore 対象)。

- 直接書込み 74 件はすべて入口から到達可能 (`writes_total=74 reachable_from_entry=74`)。
- 経路長 (命令数) の最小は 82、最大は 203 (`path_len` 列の最小値・最大値)。
- 条件なしは 1 件: 0x1046d6b (関数入口の `mov [rbp+0x5b8], edx`・引数の退避)。
- 最短経路の条件は**代表 1 本**であり、同じ書込みに至る別経路の条件は含まない。経路ごとの式 (受入 1 の完全形) は未了。
- 直前のフラグ設定命令は、jcc の直前 7 命令の中で後ろから見て最初に見つけた設定命令。jcc と無関係な命令を拾う可能性がある。

## 5. 未確定 (受入 1・3 の残り)

- **受入 1 (分岐ごとの式・経路条件 + 書く値)** は部分達成。§4 の代表経路の条件は機械的に出せた。§9 で、書込みごとに「必ず通る分岐」(必要条件) を支配関係で確定した。書込みごとの全経路の式 (十分条件の組合せ) と書く値の式は未確定 (§9)。
- 72/74 の切り分けは §3 で確定 (戻り値に届かない 2 件は上書きされる)。
- **受入 3 (判定の行き先と戻り値分岐の突合)** は §7 で実施 (PY-342)。
  `py65_r8d_bits.py` の objdump 照合 (174 件 mismatch 0) は判定の取り直しの一致であり、本節の突合とは別物。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 72 件の書込みそれぞれの全経路の式 (分岐の立ち/落ちの組合せ・書く値) | 受入 1 | #4574 (PY-341) |
| 「戻り値分岐に入る/入らない」を経路条件つきで分ける (本節の到達は path-insensitive で、判定 174 件は全件 0x104cc65 に届く) | 受入 3 の split の意味 | #4574 (PY-341) |

## 7. 判定の行き先と戻り値分岐の突合 (受入 3・PY-342)

測定 commit: `37b08a9d7` (`analysis/py342_r8d_ret_cross.py` を追加した commit)。
`git diff 37b08a9d7 HEAD -- tools/python/analysis/` の出力は空。
再現: `py53_dispatch.py` → `py65_r8d_bits.py` (`agree=174 mismatch=0`) の後に
`python3 tools/python/analysis/py342_r8d_ret_cross.py work/py53/fn.txt work/py65/r8d_sites.tsv work/py342`。
素材は冒頭の素材行と同じ `block00031_PE.bin` (22,227,016 B)。

定義:
- **入る / 入らない**: 判定命令の VA が、後ろ向き CFG 閉包 (`py65_ret584_reach.py` の `preds`) で 0x104cc65 に届く集合に含まれるか。
- **行き先**: `je`/`jz` は落ちで飛ぶ・`jne`/`jnz` は立ちで飛ぶ、として `fn.txt` の命令から独立に決める。`r8d_sites.tsv` の「立ち→」の行き先との一致を見る。
- **mismatch**: 上の行き先が `r8d_sites.tsv` と 1 件でも違えば 1 件。
- **分類 (戻り値側)**: 立ち・落ちのどちらの行き先が 0x104cc65 に届くか (both / bitset (立ちだけ) / bitclear (落ちだけ) / none)。

| 区分 | 件数 |
|---|---|
| 判定 全件 | 174 |
| 入る | 174 |
| 入らない | 0 |
| 入る / both (立ち・落ち両方が届く) | 169 |
| 入る / bitclear (落ちだけ届く) | 2 (0x1048465 `test 0x800`・0x1048476 `test 0x20`、どちらも行き先 0x104cc72) |
| 入る / 分岐なし (`setne`) | 2 (0x104a821・0x104a835) |
| 入る / `and` 書換え | 1 (0x104a8a9) |
| mismatch (行き先の突合) | 0 (jcc を持つ 171 件で比較) |

- **mismatch 0 の意味**: 独立計算と TSV の一致。両者とも同じ jcc の意味付けを使うため、jcc の立ち・落ちの取り違えは見えない (取り違えの検出は下の negctl が担う)。
- **入る 174 / 入らない 0 の意味**: 関数内の全判定が path-insensitive に 0x104cc65 へ届く。この定義では分けられない。「戻り値式に効く」かは経路条件 (§4・#4574) が要る。
- negctl: `--negctl` は TSV の 1 件の立ち・落ちを入れ替える。`不一致 1 件` (exit 0 = 検出)。

## 8. 測定値 (run 4575)

| 項目 | 値 |
|---|---|
| `py53_dispatch.py` | fn=4664 dispatch=13 r8d_tests=174 |
| `py65_r8d_bits.py` | sites capstone=174 objdump=174・agree=174 mismatch=0 |
| `py65_r8d_bits.py --negctl` | 不一致 1 件 (検出) |
| `py342_r8d_ret_cross.py` | 判定 174・mismatch 0・入る 174 |
| `py342_r8d_ret_cross.py --negctl` | 不一致 1 件 (検出) |
| 所要 | wall=0.16s・maxrss=54,280 KB (`py53` → `py65` → `py342` の 1 回・測定 commit `37b08a9d7`・load 0.07) |

## 9. 書込みごとの必須分岐 (PY-341・#4574・受入 1 の部分)

測定: `analysis/py341_ret584_dominators.py` (支配関係・1 秒未満)。入力は `py53_dispatch.py` の `fn.txt` (fn=4664・writes_total=74・reachable=74 を本 run で再現)。72 件の VA は `py65_ret584_reach.py` の出力と一致 (72/72)。

- **全経路の列挙は打ち切り**。単純パスを後ろ向きに列挙すると、74 件中 73 件が上限 2000 経路に達した (残り 1 件は入口書込みで経路 1 本・条件なし)。614 個の jcc を持つ CFG では全経路数が指数的に増えるため、この方式では全経路の式は求まらない。
- **確定したのは必須分岐 (必要条件)**。辺 `d→s` を外すと入口から書込みへ届かない jcc の辺を、支配関係で求めた。71 件 (書込み 1 件は入口直後のため該当なし) で、件あたり 3〜16 本・計 780 本。
- **全 71 件に共通する必須分岐は 1 本**: `0x1046d8d jne(落ち) after [0x1046d8a cmp byte ptr [rax], 0]`。`jne` が飛ばない側 (`[rax]` が 0) へ進む辺が、書込みに至る必須の辺。`jne` が立つ側 (`[rax]` が 0 でない) は早期 exit (0x104cc72) 側へ行く。
- 必須分岐の数の分布: 最小 3 (0x104a9c7)・最大 16 (0x1047f9c)。
- 書く値の式の出どころは 72 件の表 (付録 `REPORT_APPENDIX_PY341.md`)。内訳は §2 の分類と一致 (call 0x10469f0 が 7・add ecx, eax が 24・構造体フィールド読みが 30・vtbl 呼出しが 3・call 0x40c660 が 4・bool が 3・入口 1)。

**未確定**: 十分条件 (どの jcc の組合せで実際に書込みに至るか) と、書く値の式 (`add ecx, eax` の `ecx` と `eax` の由来・構造体フィールドの値) は未確定。必須分岐だけでは「どの経路で書かれるか」は決まらない。

**依頼の残り (次 run)**: 十分条件は、経路の全列挙をやめ、書込みごとに「その書込みへ至る分岐の組合せ」を記号的に求める方式が要る (例: 分岐条件を `cmp`/`test` の式として束ね、書込みの支配域ごとに畳み込む)。これは本 run の範囲を超えるため、PY-341 の残りとして起票先を #4574 に残す。
