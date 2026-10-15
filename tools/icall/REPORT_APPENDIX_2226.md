# 付録: icall #2226 (ICALL-66) — encoded slot 表 T1/T2 の境界と動的な最大 index

> 親: #2197 (ICALL-62)。前付録: `REPORT_APPENDIX_2225.md` (T1/T2 の終点・entry 数を CRT の初期化・終了関数から静的に確定。本付録はその再確認と動的部分)。
> 測定 commit: `c748b6fb` (`tools/icall/diff/slot_trace.sh`・`slot_trace.c` の変更。前 commit `26f90ada` からの差分はこの 2 ファイルのみ)。

## 1. 結論

- **境界 (静的・測定 commit で再確認)**: T1 = `0x181307100`〜`0x1813071a0` (20 entry、index 0〜19)、T2 = `0x1813071a0`〜`0x1813072b0` (34 entry、index 0〜33)。確定の根拠は `REPORT_APPENDIX_2225.md` §2.5。
- **動的な最大 index (既定条件 `SLOT_ENC_INIT=1`)**: 読まれた T2 index は 5 と 6 の 2 件だけで、**最大 6**。T1 は 0 件。静的上限 (T2 は 33) との差は **27**。
- **この最大は下限**: 既定 harness では、dispatcher の最初の T2 読出し (`0x18105deaf`) の直後に、T2 を読んだ 7 関数すべてが fatal で止まる。また 131 関数のうち dispatcher の T2 を読んだのは 7 関数だけ。したがって「index 7〜33 は使われない」とは言えない (§3)。
- **条件を変えても T2 の最大は 6 のまま**: stub (`SLOT_STUB_VA=1810806a0`) と T2 初期化 (`SLOT_T2_INIT=1`、新設) の両方で、T2 の読出しは index 5・6 だけだった。T2 初期化では T1 が index 1 で初めて読まれた (最大 1、静的上限 19 との差 18)。
- **受入条件の判定**: 1 (境界の確定と記録) 達成。2 (読まれた最大 index と静的上限との差の記録) 達成。値は §3 の通り下限。3 (測定) 達成。ただし zero-fill VA の基準値は issue 本文の 7 ではなく実測 10 (§2.2)。

## 2. 実測

### 2.1 測定条件

- 測定 commit `c748b6fb`。`git diff 26f90ada c748b6fb --stat -- tools/icall/diff` の出力:

  ```
   tools/icall/diff/slot_trace.c  |  5 +++++
   tools/icall/diff/slot_trace.sh | 16 ++++++++++++++++
   2 files changed, 21 insertions(+)
  ```

  `tools/ott`・`tools/targets/freshair` は測定 commit までの差分 0 (入力は変わらない)。
- 素材: `plugins-freshair` (`FA_DL` に展開し `tools/targets/freshair/fetch.sh`)・`work-icall` (`tools/icall/work/`)。`SlateCore.core_64` と `ott_native` だけを使うため、他の素材は使っていない。
- 再現 (4 条件):
  - (a) 既定: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`
  - (b) stub: `SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`
  - (c) T2 初期化: `SLOT_ENC_INIT=1 SLOT_T2_INIT=1 bash tools/icall/diff/slot_trace.sh`
  - (d) 境界: `python3 tools/icall/diff/dispatcher_ids.py <SlateCore.core_64>`
- 所要と load (uptime の 1 分値): (a) real 12.266 s (load 0.28 → 0.44)。(c) real 12.268 s (load 0.41 → 0.50)。(d) real 30.629 s (load は未記録)。(b) は所要を記録していない。

### 2.2 slot_trace 集計 (4 条件)

| 条件 | funcs (rc) | zero-fill VA | 既知 12 hit | T1 読出し (distinct・index・静的上限 19 との差) | T2 読出し (distinct・index・最大・静的上限 33 との差) |
|---|---|---|---|---|---|
| (a) 既定 | rc=0 69 / rc=124 1 / rc=95 53 / rc=98 8 | 10 | 3/12 | 0・なし・差 n/a | 2・{5, 6}・6・差 27 |
| (b) stub | rc=0 72 / rc=124 1 / rc=95 47 / rc=97 3 / rc=98 8 | 11 | 4/12 | 0・なし・差 n/a | 2・{5, 6}・6・差 27 |
| (c) T2 初期化 | rc=0 69 / rc=124 1 / rc=95 53 / rc=98 8 | 11 | 3/12 | 1・{1}・1・差 18 | 2・{5, 6}・6・差 27 |

- 基準値 (issue 本文の baseline) との照合: rc=95 は 53 で一致、既知 12 hit は 3 で一致。zero-fill VA は issue 本文が 7 と書くが、実測は 10。`REPORT_APPENDIX_2225.md` §2.2・`REPORT_APPENDIX_2262.md`・`REPORT_APPENDIX_2280.md` も 10 で一致する。
  7 は #2170 (ICALL-61) の baseline 値で、`REPORT_APPENDIX_2197.md` (27〜28 行) と `REPORT_APPENDIX_2198.md` (33 行) が記録している (測定時の `slot_trace.c` は `ce200f95`・`fe6f0acc` 相当)。その版は fatal 時の ACC 出力を持たず、後の修正 (fatal 時 ACC 出力 +3 行) で `0x1813062e0`・`0x1813071c8`・`0x1813071d0` の 3 件が加わって 10 になった。#2120 (ICALL-59) は `slot_trace.c` の初版で、7 の出典ではない。
- T2 の読出し (7 件・count は各 1): index 6 は関数 `0x18103d37c`・`0x18103d42c`・`0x18103d44c`・`0x181040f64`・`0x181057f48`・`0x18105e380`、index 5 は関数 `0x18105e338`。いずれも RIP は dispatcher `0x18105deaf` (T2 読出し命令)。
- 表の「読出し」の分類について: `slot_trace.c` の `record` は SIGSEGV のアクセス種別 (読み/書き) を区別せず、アドレスと RIP だけを記録する。分類は RIP の命令で裏付ける。表の全件の RIP は dispatcher の load 命令 (`0x18105deaf`: `mov rcx,[r14+r15*8+0x13071a0]`、`0x18105def5`: `mov rbx,[r14+rsi*8+0x1307100]`) で、いずれも読出しである。
- (a) で読出しを行った 7 関数の fatal は、すべて `rip=0x1810806a0 addr=(nil)` (`slot_trace_fatal.txt`)。

### 2.3 dispatcher の読出し経路 (機械語・`objdump -d` で確認)

dispatcher `0x18105de80` の要点 (r14 = `0x180000000` は関数先頭の `lea`):

| VA | 命令 | 意味 |
|---|---|---|
| `0x18105deaf` | `mov rcx,[r14+r15*8+0x13071a0]` | T2 読出し (r15 = function id) |
| `0x18105dec8`〜`0x18105ded0` | `rdx = T2 ^ cookie` → `ror rdx,cl` (cl = cookie & 0x3f) | decode (cookie = `0x2b992ddfa232`、rot 50) |
| `0x18105ded3`・`0x18105ded6` | `cmp rdx,-1`・`je 0x18105e037` | -1 なら `eax = 0` で返す |
| `0x18105dedc`〜`0x18105dee4` | `test rdx,rdx`・`je` → 非 0 なら `mov rax,rdx`・`jmp 0x18105e039` | 非 0 なら decode 値を関数ポインタとして返す |
| `0x18105dee9`〜`0x18105def5` | `cmp r8,r12`・…・`mov rbx,[r14+rsi*8+0x1307100]` | 0 なら解決経路に入り T1 読出し (rsi = module id) |

- 解決経路 (T1 読出し) に入るのは decode 値が 0 のとき、つまり T2 entry が cookie のとき。CRT 初期化 `0x18105ea78` は T2 の 34 entry を cookie で敷くので、CRT 後の状態ではこの経路に入る。
- 既定 harness は T2 を敷かない (`SLOT_ENC_INIT` は既知 12 slot だけ)。このとき decode 値は `ror(cookie,50)` で 0 でも -1 でもなく、関数ポインタとして返る。その後の fatal が `0x1810806a0` である理由 (返り値の扱い) は未追跡。
- (c) は T2 を cookie で敷いたので解決経路に入り、T1 index 1 (`0x181307108`・RIP `0x18105def5`) を読んだ。T1 の entry は 0 のままなので module load の呼出し (`call [0x1810c4340]`) に進み、7 関数とも `rip=0x...96f` で止まる。`0x..96f` 形は `REPORT_APPENDIX_2198.md` の harness の `missing_import` (`slot_trace+0x296f`) と同じ。
- 1 件の fatal `fn=0x18105de80 rip=0x18105deaf addr=0x401307220` は、harness が dispatcher 自身を closure 関数として直接呼んだ結果。ecx に heap 引数 `0x50000010` が入り、`0x180000000 + 0x50000010×8 + 0x13071a0 = 0x401307220` を読んだ。T2 の範囲外で harness 由来のため、index には数えていない。

### 2.4 境界の再確認 (`dispatcher_ids.py`・測定 commit `c748b6fb`)

- call site 31 件。T2 の function id (即値) の最大は 29 (distinct 20)。T1 の module id の最大は 18 (distinct 9: 0, 1, 3, 4, 6, 7, 9, 16, 18)。
- T2 初期化関数 `0x18105ea78`: `lea rdi,[0x1813071a0]`・`lea rax,[0x1813072b0]`・`and ecx,0x22` (= 34)・`rep stosq`。
- T1 終了関数 `0x18105eaac`: `lea rbx,[0x181307100]` から 8 B ずつ進み、`lea rax,[0x1813071a0]` で止まる (20 entry)。
- `module_names` (`0x181134720`) の有効ポインタは 20 件 (終端 `0x1811347c0`)。
- 上記は `REPORT_APPENDIX_2225.md` §2.5 と一致。

## 3. 解釈と限界

- 最大 index 6 は、この harness が観測した下限であって、表の実際の最大ではない。
  - 到達: 131 関数それぞれを 1 回・固定引数で呼ぶ。dispatcher の T2 読出しに届いたのは 7 関数。
  - 読出し回数: 既定 harness では、T2 を読んだ関数は最初の読出しの後に止まる (§2.3)。
  - T2 初期化 (c) を入れても到達関数数は増えず、T1 の読出しが 1 件増えただけ。
- 静的な call site の値の上限は、T2 の function id が 29、T1 の module id が 18。動的に観測したのは T2 index 5・6 と T1 index 1 だけで、T2 index 7〜29 と T1 index 2〜18 は未観測。
- 既定条件の表記について: `slot_trace.sh` は `SLOT_ENC_INIT` が未指定でも空文字を渡す。C 側の `getenv` は空文字でも非 NULL を返すので、12 slot は常に敷かれる。`SLOT_ENC_INIT` を付けない実行 (`bash tools/icall/diff/slot_trace.sh`) は (a) と同一の結果になった (確認済み)。その値は rc=0 69 / rc=124 1 / rc=95 53 / rc=98 8、zero-fill VA 10、既知 12 hit 3/12 で、§2.2 の (a) の行と一致する。この値は作成時の確認で、差し戻し対応の run では素材不足のため再測定していない (§5)。本付録の測定は全て `SLOT_ENC_INIT=1` で行ったので影響はない。`#2231` の群 C (`SLOT_ENC_INIT` 依存) の判定に関わるため、挙動の変更は本 PR では行わない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| dispatcher に届いた関数が 7 件のため、読出し最大 index は下限 (T2 6)。T2 index 7〜33・T1 index 2〜19 の到達は未確認 | 受入 2 の値の意味 (本付録 §3)。静的上限との差 27 は未検証 | PM 判断 (到達範囲の拡大は別作業) |
| 既定 harness で T2 読出し後の fatal `0x1810806a0` の機構 (decode 値の返り値の扱い) が未追跡 | 群 C の因果 | #2231 (ICALL-67) |
| `slot_trace.sh` の `SLOT_ENC_INIT="${SLOT_ENC_INIT:-}"` により、未指定でも 12 slot が敷かれる | 既定条件の表記。`SLOT_ENC_INIT` 依存の判定 | #2231 (ICALL-67)。挙動の変更は PM 判断 |
| zero-fill VA の基準値: issue 本文の 7 と実測 10 の不一致 | 基準の記載のみ (実測と既存付録は 10 で一致) | 本 issue の本文を PM が更新 |

## 5. 再現

```
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh                          # (a) 既定
SLOT_STUB_VA=1810806a0 SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh   # (b) stub
SLOT_ENC_INIT=1 SLOT_T2_INIT=1 bash tools/icall/diff/slot_trace.sh           # (c) T2 初期化
python3 tools/icall/diff/dispatcher_ids.py <SlateCore.core_64>               # (d) 境界
```

- 集計は `slot_trace.sh` 末尾の Python が**標準出力**に出す (`$OUT` には出ない)。`$OUT` (`tools/icall/work/slot_trace_enc.txt`) に入るのは F 行 (関数ごとの rc と ACC 件数) と ACC 行だけ。標準出力の行は、`funcs` (件数と rc 内訳)・`distinct zero-fill addrs`・`known 12 hit`・`T1 index` / `T2 index` (読まれた index ごとの `(addr, rip)`)・`T1 static entry 20 ...` / `T2 static entry 34 ...` (distinct・max read・static max・gap)。§2.2 の表は、各条件の標準出力からの転記である。
- 各条件の実行は `$OUT` を上書きするので、標準出力は条件ごとにファイルへ保存してから次の条件を走らせる (例: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh > work/a.txt`)。
- `SlateCore.core_64` は `tools/targets/freshair/fetch.sh` が `tools/targets/freshair/work/win/Fresh Air/` に展開する。
- 集計部の静的検算 (素材を使わない): スクリプトの Python 部を抜き出し、既知の ACC 行 (T2 index 5・6、T1 index 1) を与えると、`T2 static entry 34 distinct read 2 max read 6 static max 33 gap 27`・`T1 static entry 20 distinct read 1 max read 1 static max 19 gap 18` が出る (本付録の表と一致)。

## 6. 測定 commit からの差分

- `git diff c748b6fb HEAD -- tools/icall/diff tools/ott tools/targets/freshair` の出力: 空 (差分 0。本付録と DOC_MAP の commit のみ)。
