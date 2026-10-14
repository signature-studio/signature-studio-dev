# tools/python REPORT: PY-121 general の log・rec 系 4 件の PE 根拠 (#2979, 親 #2830)

> 前段: `tools/python/REPORT_PY87.md` (general 状態読出しゲッター 4 件)・`tools/python/REPORT_PY39.md` / `REPORT_PY70.md` (processRECEvent の書式)。
> issue #2979 が参照する `tools/python/REPORT_PY94.md` は repo に存在しない (main `eec639a3` で確認)。本付録は PY-121 の実測のみ。
> 既知類型との関係: 該当なし (lift ではなく PE の直接逆アセンブル。docs/DEFECTS.md の類型は対象外)。

## 結論

- 4 関数 (`general.clearLog`・`general.dumpScoreLog`・`general.processRECEvent`・`general.getRecPPB`) の**ハンドラ VA・書式・呼出し鎖**を PE (`block00031_PE.bin`) から確定した。書式と引数個数は flapi 表 (`analysis/flapi/flapi_table.json`) と一致した。
- **戻り値の意味と副作用は 4 件とも未確定**。clearLog・dumpScoreLog は共通の dispatch `0xd843d0` の先の下位関数 (`0x11eb5f0`・`0x124c020`) の意味が要る。processRECEvent は `0xd84740`、getRecPPB は実行時にどちらの経路が生きているかが要る。
- 未確定の意味を mock/C に書くと silent miscompile になる。**本 PR は mock・C provider を変えない** (実装数・未実装数の変化 0、`general_diff.mjs` の対象 0)。残りは子 issue #3001・#3002・#3003 に移した。

## PE 根拠 (VA)

| 関数 | PyMethodDef entry | fn (VA) | flags | 書式 (kwlist) | 確定した呼出し鎖 | 未確定 |
|---|---|---|---|---|---|---|
| `general.clearLog` | 0x151ac80 | 0xd6a1f0 | 4 (NOARGS) | なし | `0xd6a8e0` で eng 取得 → dispatch `0xd843d0` (out=[rbp+0x78]・callback `0xd6a1a0`・sync=1) → `0xd82c20(code)` で Python 値へ | `0xd6a1a0` 先の `0x11eb5f0(V(0x15e0ff8), 1)` の効果 |
| `general.dumpScoreLog` | 0x151ac60 | 0xd6a060 | 3 (VARARGS\|KEYWORDS) | `i\|i` (time, silent) | PyArg 解析 → dispatch `0xd843d0` (time・silent を task に複製・callback `0xd69ff0`) → callback が `0x124c020(V(0x15e0ff8), time, silent==1)` | `0x124c020` の効果・time の単位 |
| `general.processRECEvent` | 0x151ac40 | 0xd69f00 | 1 (VARARGS) | `Iii` (eventId, value, flags) | PyArg 解析 → `0xd84740(eng, &out, eventId, value, flags)` → out の第 1 qword ≠ 0 なら error、0 なら第 2 の dword を `0x15e4280` (int 変換) へ | `0xd84740` の意味・out の型と範囲 code |
| `general.getRecPPB` | 0x151aa40 | 0xd69310 | 4 (NOARGS) | なし | `0xd68d90` の戻り値 X の `dword [X+0xb20]` を `0x15e4280` へ | X の切替 (下節) |

- 書式は `pe_handler_probe.py` が引いた文字列 (clearLog は無し、dumpScoreLog は `i|i` 、processRECEvent は `Iii`) と flapi 表の `kwsig` が一致した。
- `processRECEvent` の channels 版 (entry 0x15171c8・fn 0xd58e00) は同じ `0xd84740` を呼ぶ (REPORT_PY39 の既知点と一致)。
- 変換スロット `0x15e4280` は REPORT_PY87 の既知点と一致 (getRecPPB・processRECEvent の両方で確認)。

## dispatch `0xd843d0` と述語 (clearLog・dumpScoreLog 共通)

- 引数: `rcx=eng`・`rdx=out`・`r8=callback`・`r9=userdata (0)`・5 番目以降はスタック。入口で `*out = -2` (`0xfffffffffffffffe`、0xd843e9)。
- 5 番目以降の引数を task (`eng` 系の構造) の `+0x18`〜`+0x40` へ複製 (0xd84429〜0xd84467)。callback を `+0x58` に置く (0xd8446b)。11 番目の引数 (`[rbp+0xb0]`) が sync flag (0xd84471)。
- callback の規約 (両 callback 共通の形): 先頭で `task[+0x60] = -2`。述語 `pred = vtbl(this)[+0x98]()` が真なら `task[+0x60] = 0` を書いて本体を呼ぶ。偽なら -2 のまま。
  - `this = *(*(*(0x15e4790)) + 8)` (`0xd6a1b0`〜`0xd6a1c1`)。`general.safeToEdit` (0xd6a2c0) と同じ読み方 (REPORT_PY87 の観察と一致)。
  - 本体の対象 `V(0x15e0ff8)` (`0xd6a1d6`・`0xd6a026` で同じ global)。
- `0xd843d0` が `task[+0x60]` を `*out` へ写す箇所は**未確認** (推定。写す処理を見ないと、out が -2 のまま返る経路の有無が言えない)。
- 結果変換 `0xd82c20(code)` (入口で `[rbp+0x24]` = code、戻り値 rax は `[rbp+0x28]`。`pe_disasm.py d82c20` で確認):
  - (a) `code == 0` (`0xd82c35`〜`0xd82c3a`): `0xd82c3c` で関数ポインタ (`call [rax]`、`[rip+0x860485]` 経由) を呼び、戻り値 rax の null を見る (真偽の述語ではなくポインタ返し)。非 null なら `0xd82c4a` で戻り値を 0 とし、`0xc38bc0` を呼ばずに `0xd82dda` へ戻る。null なら (b) と同じ経路 (`0xd82c55` → `0xd82c5c`)。
  - (b) `code ≥ 0` (`0xd82c58`〜`0xd82c5a` の `jl` が成立しない。(a) の null を含む): `0xd82c5c` で `0xc38bc0` を呼び、その戻り値を `0xd82c61` で戻り値とする。
  - (c) `code < 0` (`0xd82c5a` の `jl 0xd82c6a` が成立): `0xd82c6a`〜`0xd82c84` で `this` (`*(*(*(0x15e4790))+8)`) の `vtbl[+0x88]()` を呼ぶ。
    - 偽なら `0xd82dd0` で引数を設定せず `0xc38bc0` を呼ぶ (rcx は述語呼出し後で未定義。(b) と同じ `0xc38bc0`)。
    - 真なら `0xd82c8c`〜 の code 別の分岐へ進む。`-1`〜`-3` は `0xd82cce`〜、`-4` は `0xd82d3c`、`-5`〜`-8` は `0xd82d4e`〜`0xd82d84`、`-9` 以下は `0xd82d96`。どの分岐も RIP 相対の文字列を `0x4135e0` で `[rbp+0x38]` に書いたのち `0xd82da6` へ進み、`0x414000` → `call [rbx]` (rcx = `*(*(0x15e1140))`、rdx = 文字列。例外設定の形に見えるが、関数名と引数の意味は未同定) → `0xd82dc8` で戻り値 0 を返す。
- 戻り値の意味は未確定 (`0xc38bc0` の戻り値は None と推定・推定と明記)。よって、述語偽 (`code < 0` かつ `vtbl[+0x88]` が偽) のときに Python 側が None を返すか例外を投げるかは、`0xc38bc0` の同定まで確定しない。述語真の経路 (c-真) は、code 別のメッセージを設定して 0 を返す形。

## getRecPPB の切替 (`0xd68d90`)

- `P = *(0x15e4558)` (`0xd68d90`)。
- `*(P) != 0` なら `X = *(P)` (`0xd68d97`〜`0xd68da7`)。
- `*(P) == 0` なら `X = *(*(0x15e35c8))` (`0xd68da9`〜`0xd68db3`)。
- 戻り値は `dword [X + 0xb20]` (`0xd69319`)。
- どちらの経路が FLEngine の実行時に生きているかは PE の静的解析では決まらない。`0x15e4558` の値、`*(P)` が 0 になる条件 (プロジェクト・エンジンの状態)、`0x15e35c8` の指す struct の役割の同定が要る。

## 手段

- 実行の cwd は全て `tools/python/` (`analysis/flapi/` は `tools/python/analysis/flapi/`)。
- 展開: `mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (2.9 秒・`extracted/block00031_PE.bin`)。
- probe: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_handler_probe.py clearLog dumpScoreLog processRECEvent getRecPPB` (entry と fn が `analysis/flapi/flapi_kwargs.json` の `fn_va` と一致。`flapi_table.json` には `fn_va` が無い)。
- 逆アセンブル: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA 16 進> <命令数>` (本文の VA は全て、このコマンドで読んだもの)。
- RIP 相対の絶対アドレス = 次命令のアドレス + disp32 で手計算。検算: `0xd68d90`・`0xd68d9d` の 2 命令が同じ `0x15e4558` を指すこと、`0xd6a1b0`・`0xd6a000`・`0xd6a1d6`・`0xd6a026` の指す先が各々 `0x15e4790`・`0x15e0ff8` で一致すること。

## 検証

- コード変更なし。測定の基点は main `eec639a3`。コード差分 (`tools/python` の .md 以外): `git diff eec639a3 HEAD -- tools/python ':!*.md'` の出力は空。
- e2e (`general_diff.mjs`・`provider_check.mjs`・`all_tools.mjs`) はコードを変えていないため対象外。件数 (実装 / 未実装) は変えていない。
- ネガティブコントロールは対象外 (RE の記述のみ。実装の検査が無い)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| clearLog・dumpScoreLog: `0xd843d0` の out の写し方・`0x11eb5f0`・`0x124c020` の効果・述語偽 (-2) の Python 側の挙動 | 2 関数の mock/C 実装ができない | #3001 (PY-125) |
| processRECEvent: `0xd84740` の意味と out の構造・範囲 code | 1 関数の mock/C 実装ができない。channels 版と共有 | #3002 (PY-126) |
| getRecPPB: `0xd68d90` の切替条件 (`0x15e4558`・`0x15e35c8` の実行時の値) | 1 関数の値が確定しない | #3003 (PY-127) |
| issue #2979 が参照する `tools/python/REPORT_PY94.md` が repo に存在しない | 既知点 (PY-94) の出典が確認できない | #2979 のコメント |
| `[PY-121]` の題名が 3 件ある (#2979・#2982・#2985) | 題名の重複 (番号の衝突) | PM (題名の正規化。実装 subagent はリネームしない) |
