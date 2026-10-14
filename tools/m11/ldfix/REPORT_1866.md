# REPORT_1866 — dest 追跡監査の再実行 (#1866 / 親 #1647・#564)

## 1. 測定条件

- 測定 commit: `8b0fee41` (main)。コードは変更していない (本 PR は REPORT と結果 JSON のみ)。
  `git diff 8b0fee41 HEAD -- tools/m11` は本 PR 作成時点で 0 行の想定 (REPORT と results のみ追加)。
- 入力 IR: `tools/m11/m11_gen_ir2.sh` 由来 (`bash` で scan → bounds → lift_all → tail×2 → boot4 → boot5 → gen_ir2 の順に再生成)。
  `work-m11` (#680 で旧素材) は**使っていない**。
- `work/ir_conditions.json`: `ldfix=applied` / `qstore=not-applied` / `ir_sha256=63bb4a75d2b7f318641765dbe0c2ac3257a5497e9d8e981f209a1b385b691657`
- PE: `fl-win64` の `block00031_PE.bin` (素材 fl-win64 `flstudio_win64_26.1.7.5653`)。
- Ghidra: `Ghidra 12.1.4` (`ghidra_12.1.4_PUBLIC_20260921.zip`) / JDK 21 で `functions_dll.csv` を再生成 (9 分 54 秒, rc 0)。
  `analyzeHeadless` は `-Xmx` を受け付けないため `MAXMEM=12G` を環境変数で渡した。
- 再生成 (gen_ir2 を含む) 8 分 38 秒 (rc 0)。ldfix: F1=902 / F2=30 / F3a=3 / F3b=5 / F3c=36 / **F4=10** (errors=0)。
- 監査 `audit_undefload_dest.py` (6 入力 norm0): **69 秒**、load average 0.96〜0.98 (4 vCPU)、rc 0。
- 比較用の旧監査 `audit_undefload.py` (同じ 6 入力): 69 秒、rc 0、sites 2,854。

## 2. 結果

結果 JSON: `tools/m11/ldfix/results/audit_undefload_dest_1866.json` (旧 `results/audit_undefload_dest_1647.json` は存在せず、本ファイルが正)。

| 監査 | sites | 主な分類 | FRAME_IN_ESCAPED (site / 関数) |
|---|---|---|---|
| `audit_undefload.py` (旧) | 2,854 (REGLIVE 2,513 / NOADDR 161 / MEMREAD 92 / FRAME_IN_ESCAPED 56 / FRAME_NOT_ESCAPED 19 / RIPREAD 13) | 53 関数 | 56 / 53 |
| `audit_undefload_dest.py` (dest 追跡) | 2,737 (REGLIVE 2,506 / NOADDR 196 / DEST_FRAME_IN_ESCAPED 18 / DEST_FRAME_OTHER 10 / DEST_MEMREAD 6 / DEST_RIPREAD 1) | 18 関数 | 18 / 18 |

**注意 (件数は直接比べられない)**: dest 追跡版は、consumer 命令が直接メモリを読む site を `continue` で
集計から外す (`audit_undefload_dest.py` の main)。したがって dest 版の sites は「REGLIVE だった site だけ」を見ている。
旧監査の FRAME_IN_ESCAPED 56 site のうち、直接 memop の site は dest 版では数えられない。
2 つの監査は**相補的**で、和集合を取らない限り全体の検出件数にならない。

## 3. F4 修復 10 関数の検出 (受入条件 3)

| 関数 | 旧監査 | dest 版 | 機械語上の消費者 (dest 版の分類) |
|---|---|---|---|
| 132e8e0 | 無 | 無 | 両監査とも、この関数の site が 0 件 (norm0 の undef load の consumer が無い) |
| 44d1c0 | 無 | 無 | `44d1d0 mov sil,1` → REGLIVE |
| 69c360 | 無 | 無 | `69c381 not eax` → REGLIVE |
| 865020 | 無 | **検出** (`86503f test eax,1` ← `86503c mov eax,[rbp+0x4c]`) | DEST_FRAME_IN_ESCAPED |
| 977e40 | 無 | 無 | `977e4b movdqa [rbp+0x30],xmm6` → REGLIVE |
| 52a7f0 / 71dd80 / 41ca30 / 666c30 / 864f60 | 有 | 無 | 旧監査では検出 (F4 修復済みだが REPORT_1647 §6 では未確認) |

**判定: 受入条件 3 は未達** (F4 偽陰性 5 件のうち、dest 版で検出できたのは 865020 の 1 件)。
REGLIVE に落ちる 3 件 (44d1c0 / 69c360 / 977e40) は、`trace_dest` が memory read に届かなかった。原因 (遡り範囲 `BACK_MAX=16`・
`call/ret/jmp` での停止・書き手の形) は未切り分け。132e8e0 は site 自体が無く、監査では判定できない。
ネガコン (F4 を外した IR での検出数差) は未実施。

## 4. 受入条件の状況

| # | 受入条件 | 状態 |
|---|---|---|
| 1 | 再生成 IR で再実行し、commit・sha256・sites・by_class・秒・load を記録 | **達成** (§1・§2) |
| 2 | 既存 `audit_undefload.py` を dest 追跡に置き換える (または並列の理由を書く) | **未達** → 子 issue。理由は §2 (相補的。和集合での置換が必要) |
| 3 | F4 修復 10 関数の偽陰性が新監査で検出されることを確認 (ネガコン付き) | **未達** → §3 (1/5 検出)・ネガコン未実施 → 子 issue |
| 4 | FRAME_IN_ESCAPED 未修復 48 関数の真偽を判定し REPORT に一覧 | **未達** → 子 issue |
| 5 | SUSPECT 件数を再計測し、測定 commit と HEAD までの差分を書く | **未達** (本 run では dest 版の SUSPECT 定義を決めていない) → 子 issue |
| 6 | ポインタ値 read (`DEST_FRAME_IN_ESCAPED` の 4425f0 / e9d8a0 / 783d00) を分類として分けるか決め根拠を書く | **未達** → 子 issue |

## 5. ポインタ値 read の候補 (参考・未判定)

dest 版の DEST_FRAME_IN_ESCAPED 18 関数のうち、本 issue が名指しした 3 件の機械語:

- `4425f0`: `442655 movsd [rax],xmm0` ← `442651 mov rax,[rbp+0x60]` (frame 値をポインタとして使用)
- `e9d8a0`: `e9d8f3 movsq [rdi],[rsi]` ← `e9d8ef mov rsi,[rbp+0x68]` (frame 値をポインタとして使用)
- `783d00`: `78417b mov word [rax+0x2c],0x3d` ← `784174 mov rax,[rbp+0xb0]` (frame 値をポインタとして使用)

3 件とも、frame read の結果が**次の memory 操作のアドレス**になっている。値の read (`cmp`・`test` 等) とは型が違う。
分類を分けるかは本 run では決めない (子 issue で、ポインタ read を別クラスにするかを根拠付きで決める)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 旧監査と dest 版の置換 (和集合・並列理由) | 監査が 2 本並存 | #2141 [LD-78] |
| F4 偽陰性 4 件 (132e8e0 / 44d1c0 / 69c360 / 977e40) の検出と F4 ネガコン | 偽陰性の残存を確定できない | #2143 [LD-79] |
| FRAME_IN_ESCAPED 未修復 48 関数の判定・SUSPECT 再計測・ポインタ read 分類 | 本件型の脱落が残る可能性 | #2144 [LD-80] |

## 7. 参照

- 親の経緯: `REPORT_1647.md` (dest 版の新設)・`REPORT_564.md` (F4・旧監査の 56 site)。
