# 付録: icall #5044 (ICALL-108) — 180cbb930 の r13 保存と間接呼出しの具象型 (部分達成)

> 親: #3941 (ICALL-92)。前 run の結論: #5044 のコメント (commit `3da603ce6`)。前付録: `REPORT_APPENDIX_3089.md` §6。
> 測定 commit: `8fb7ea222` (`tools/icall/r13_callee_check.sh` の判定修正。以後のスクリプト変更なし)。
> 素材: `plugins-freshair` の `Fresh Air.Win.zip` から `SlateCore.core_64` (36,285,952 B・sha256 `2cf759f712adf955a56684df4b24454690ac878105d4433de16c88626a45dd3b`) を `tools/targets/freshair/work/win/` に展開。全量 dsm は `tools/icall/work/core64.dsm` (gitignore)。

## 1. 結論

- 受入 2 の**直接**の呼出し先 `180cbcd90`・`180cb9890` は、実 binary で `r13` 書込み 0 件・`push r13` / `pop r13` 0 件 (本体に `r13` の文字列が 0 件)。`r13` を書かないため、呼出し元の `r13` は保存の条件を満たす。
- 間接の呼出し `180cbba21` (`call [rax+0x8]`)・`180cbba36` (`call [rax+0x10]`) の具象型は**静的に未特定**。`r13` の保存は未確認。受入 2 は部分達成。
- 受入 3 (`180703b7c` の届き判定) は、間接呼出しの `r13` 保存に依るため、本付録では結論を書かない。

## 2. 判定の方法

`tools/icall/r13_callee_check.sh` で行う。

1. `objdump -d -M intel` の全量を `tools/icall/work/core64.dsm` に出力 (初回のみ)。測定は dsm を消してから全量生成し、判定 3 関数までを含む全体を `time` で計測 (HEAD `8b1618e7c`・測定開始時の load average 0.71): `real 14.464 s`・`user 13.955 s`・`sys 0.409 s`。
2. 関数本体は、開始アドレス行から `ret` の直後に `int3` パディングが来るまでを切り出す。
3. 本体の命令のうち、宛先 (第 1 オペランド) が `r13`/`r13b`/`r13w`/`r13d` のものを、ニーモニックを限定せずに数える。`cmp`・`test`・`push`・`call`・`jmp`・`jcc` は書込みではないので除外する。`push r13`・`pop r13` は保存・復元として別に数える (`r13_saves`)。`xchg` は両オペランドを見る。

判定関数の期待値 (`r13_callee_check.sh --selftest`、objdump 実出力ではない手書きの 7 行): 書込み 3 件 (`bsf r13,rax`・`mov r13b,al`・`pop r13`)、`push r13` 1 件、`pop r13` 1 件。`cmp r13,rax`・`test r13,r13`・`mov QWORD PTR [r13+0x8],rax` (宛先が r13 のメモリ参照) は数えない。

旧版 (`8fb7ea222` より前) は宛先を `r13`/`r13d` に限り、ニーモニックを許可リストで絞っていたため、`bsf r13,rax`・`mov r13b,al` を取りこぼしていた。旧版の 0 件は保存の証拠にならないため、本付録では採らない。

切り出しの検証: 3 関数とも、切り出し行の先頭が開始アドレス、末尾が `ret` になることを確認した (`180cbb930` 76 行・`180cbcd90` 192 行・`180cb9890` 56 行)。本体の `r13` 文字列出現は 3 関数とも 0 件で、0 件が切り出しの失敗ではないことを確かめた。

## 3. 実測 (測定 commit `8fb7ea222`・実 binary)

| 関数 | 本体の行数 | 本体の `r13` 文字列 | `r13` 書込み | `push r13` / `pop r13` | 備考 |
|---|---|---|---|---|---|
| `180cbb930` (呼出し元) | 76 | 0 | 0 | 0 / 0 | `180cbb97f` で `180cbcd90`、`180cbb98e` で `180cb9890` を呼ぶ。`180cbba21`・`180cbba36` で間接呼出し |
| `180cbcd90` (直接) | 192 | 0 | 0 | 0 / 0 | 直接呼出し先 |
| `180cb9890` (直接) | 56 | 0 | 0 | 0 / 0 | 直接呼出し先 |

間接呼出し (実 binary で本文どおりを確認):

- `180cbba21`: `ff 50 08` = `call QWORD PTR [rax+0x8]`。直前は `mov rax,[rbx]`・`rbx` = `[rsp+0x28]` (= `[rdi+0xa80]` の control block 相当)。
- `180cbba36`: `ff 50 10` = `call QWORD PTR [rax+0x10]`。直前は `mov rax,[rcx]` (同上)。

`[rdi+0xa80]` の格納箇所は、全量 dsm で 48 件 (`mov QWORD PTR [r*+0xa80],` の数。`grep -c 'mov.*+0xa80'` は 133 件でこれは別の数え方)。格納元の関数 `180cbc77c` は直接の `call` が 0 件 (tail jump 等で呼ばれる)。`180cb5d3e` は `+0xa80` に `rbp` (0) を書く初期化。具象型の特定には、control block の vtable を辿って `[vtable+0x8]`・`[vtable+0x10]` の関数を確定する必要があり、この run では未着手。

## 4. 前 run との関係

前 run は直接呼出し 2 件の `r13` 保存を目視で確認していた。本付録の判定 (新版・実 binary) は、その目視と一致する (0 件)。前 run の判定 (受入 1・3 の結論) は変えない。

前 run が指摘した誤り (`0x180702f50` が out 引数 `[rsp+0x24]` に書く) は、以下の既存記述に残っている。本 PR では書き換えない (受入 2 の範囲外)。訂正は次の run で行う。

- `REPORT_APPENDIX_2900.md` §2.1 (`180703a47` `call 0x180702f50` が out 引数経由で書く、の記述)
- `REPORT_APPENDIX_3089.md` §3 (`0x180702f50` は out 引数 `[rsp+0x24]` を返す)

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接呼出し `180cbba21` (`[rax+0x8]`)・`180cbba36` (`[rax+0x10]`) の具象型 (control block の vtable) と `r13` の保存 | `180703913` の到達判定 (受入 2・3) | #5044 (本 issue の残件・次 run) |
| 受入 3 (`180703b7c` の届き判定の結論) | 間接呼出しの結果に依る | #5044 (次 run) |

## 6. 検証

- 測定 commit: `8fb7ea222` (判定の修正。以後 `r13_callee_check.sh` に変更なし)。
- 判定関数の確認: `bash tools/icall/r13_callee_check.sh --selftest` → `selftest: 書込み 3 件 (期待 3) / push r13 1 件 (期待 1) / pop r13 1 件 (期待 1)`。手書きの入力での確認で、objdump 実出力での確認ではない。
- 実 binary での再測定 (`SlateCore.core_64` sha256 `2cf759f712adf955a56684df4b24454690ac878105d4433de16c88626a45dd3b`・36,285,952 B、`plugins-freshair` と `work-icall` の素材を使用): `bash tools/icall/r13_callee_check.sh <SlateCore.core_64> tools/icall/work/core64.dsm` → `180cbb930`・`180cbcd90`・`180cb9890` の `r13` 書込み 0 件 (push 0 / pop 0)。間接 2 件は具象型未特定。`+0xa80` 格納箇所 48 件。
- 前 run の 5.78 秒・前 run の値は、本付録の数値の根拠にしない。
