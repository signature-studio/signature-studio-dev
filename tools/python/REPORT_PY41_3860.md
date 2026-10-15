# PY-262 (#3860): 戻り値 `[rbp+0x584]` の書込み経路と式 (部分・REPORT_PY41.md の PY-65 節の受入 2 の付録)

親: #2034 (PY-65)。前段: `REPORT_PY41.md` の PY-65 節 (受入 2 は未達)・PY-60 (戻り値の書込みと早期 exit の入辺 9 件)。
測定 commit: 本 PR の commit (`analysis/` 同梱の `tools/python/analysis/py65_ret584_reach.py` を追加した commit)。
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

## 4. 未確定 (受入 1・3 の残り)

- **受入 1 (分岐ごとの式・経路条件 + 書く値)** は未確定。§2 の 72 件は経路条件を分けない後ろ向き到達の集合で、各書込みに対する「どの jcc の立ち/落ちでその書込みに至るか」は本 run で求めていない。
- **受入 3 (判定の行き先と戻り値分岐の突合)** は未実施。`py65_r8d_bits.py` の照合 (objdump 対 capstone) は 174 件 mismatch 0・negctl 1 件で、これは判定の取り直しの一致であり、「行き先と戻り値分岐の対応」の突合ではない。突合の定義と実施は未了。`REPORT_PY41.md` の PY-65 節の受入 3 とは別物。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 72 件の書込みそれぞれの経路条件 (分岐ごとの式・書く値) | 受入 1 | #3860 (PY-262) |
| 判定の行き先と戻り値分岐の突合 (mismatch 数・negctl の定義と実施) | 受入 3 | #3860 (PY-262) |
