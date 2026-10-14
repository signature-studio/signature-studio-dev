# PY-124 (#2999): general.saveUndo の PE 確定 (引数・既定値・戻り値・失敗経路・核への受け渡し)

親: #2978 (PY-120)。前段: `tools/python/REPORT_PY15.md` (kw 名・既定値の推定)、`tools/python/REPORT_PY61.md` (`0xd843d0` job 投入・`0xd82c20` status→PyObject の確定)。既知類型との関係: 該当なし (lift 作業ではない)。

## 結論

- **引数を確定**: 書式 `si|i`・kwlist `undoName` / `flags` / `updateHistory`・`updateHistory` の既定値 1。`undoName` と `flags` は必須、`updateHistory` は任意 (§1)。
- **戻り値は None**。準備不可のときは status -2 になる。その後の `0xd82c20` が文言付きの例外 (「Operation unsafe at current time」) を出すか None を返すかは、`0xd82c7e` の判定の結果で決まる (判定の意味は未確定。§3)。引数の型違い・必須欠落は CPython の ParseTuple が立てた例外をそのまま返す (§3)。
- **核 `0xd69860` の受け渡しを確定**: `flags` と、`updateHistory == 1` の真偽 (核が `sete r9b` で書く 1 バイト) を job 経由で `0x1017ad0` へ渡し、そこで履歴 record を作る。`[obj+8]` が有れば `0x1019b70` で末尾に追加、無ければ `0x1019dd0` で record の要素を後始末する (解放と推定、§4)。
- **未確定**: record の中身 (`0x101b780` 本体・`flags` のビットの意味・`r9b`/`r9d` の読み方)、準備不可時の報告判定 (`0xd82c7e`) の意味。ここが決まらないと、履歴の実体を再現できない。**provider・host・tests は変更しない** (mock にも C にも saveUndo は無く、未実装 code 2 のまま)。no-op の成功は返さない。残りは子 issue `[PY-137]` (#3026) へ移す (§5)。

## 0. 素材と前提

- 素材: `fl-win64` を `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64` で展開 → `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`。
- PE の ImageBase は `0x400000` (実測)。文字列と表のポインタは絶対 VA で書かれている。
- 検証起点: `origin/main` = `798bbb67`。

## 1. 引数 (wrapper `0xd69900`)

| 項目 | VA | 根拠 |
|---|---|---|
| PyMethodDef | entry `0x151ab40` → fn `0xd69900` (flags=3 = METH_VARARGS \| METH_KEYWORDS) | `analysis/flapi/pe_handler_probe.py saveUndo` |
| 書式文字列 | `lea r8,[rip+0x128]` (`0xd69955`) → `0xd69a84` = `'si\|i'` | `analysis/py124_saveundo.py` |
| kwlist | `lea r9,[rip+...]` (`0xd6995c`) → 表 `0x151a928`: `0xd698d4` (undoName), `0xd698dd` (flags), `0xd698e3` (updateHistory), `0` (NULL) | 同上 |
| undoName | `s` → `[rbp+0x98]` (char*)。`0x41c6e0(&[rbp+0xa0], char*)` で name object を作る (`0xd69998`〜`0xd699a6`) | 同上 |
| flags | `i` 必須 → `[rbp+0xac]`。`0xd6996f` で `&[rbp+0xac]` を渡し、`0xd699c3` の `movsxd` で 8 バイト化 | 同上 |
| updateHistory | `i` 任意。既定値 1 を `mov dword [rbp+0xa8],1` で先に入れる (`0xd69943`)。`[rbp+0xa8]` → `movsxd` (`0xd699cf`) | 同上 |

- `si|i` の `|` より後ろが任意なので、flags は必須、updateHistory は省略可。
- 途中の引数だけ省略する呼び方 (kw で途中を飛ばす等) は ParseTuple の規則に従う。実装時は `REPORT_PY15.md` §16 追補 (a) の方針どおり、途中の省略は TypeError、末尾の省略だけ既定値 1 を使う。

## 2. 核への受け渡し (wrapper → `0xd843d0` → 核 `0xd69860`)

- **wrapper** (`0xd699ae`〜`0xd69a04`): `obj = *(0xd6a8e0(self))` (`0xd6993b`〜`0xd69940`)。`call 0xd843d0(rcx=obj, rdx=&[rbp+0x80] (結果), r8=0xd69860 (核), r9=name, 5 番目=flags, 6 番目=updateHistory, 7〜10 番目=0, 11 番目=1 (byte))`。
- **job 配置** (`0xd843d0` の `0xd84429`〜`0xd84467`、`analysis/py124_saveundo.py` で assert): `job+0x18` = 5 番目 (flags)・`job+0x20` = 6 番目 (updateHistory)・`job+0x28`〜`job+0x40` = 0・`job+0x48` = name (`call 0x4133f0(job+0x48, r13=r9)`)・`job+0x58` = 核。`0x526190` で実行。終了後 `*(結果) = [job+0x60]` (`0xd844d7`)。
- **核 `0xd69860`** (`0xd6986c`〜`0xd698c8`):
  1. `[job+0x60] = -2` (初期値)。
  2. 準備判定: `**G1 + 8` のオブジェクトの `call [vtbl+0x98]` (`0xd69874`〜`0xd69888`)。偽なら status -2 のまま (`0xd69890` の `je 0xd698cd`。`test al, al` は `0xd6988e`)。(`G1` = global `0x15e4790`。`0xd82c20` の報告判定 (§3) も同じ global の `+8` オブジェクトを使う。)
  3. 真なら status 0 (`0xd69892`)。`0x409c80(src=&job+0x18, dst=&tmp, 8)` で flags の 8 バイトを tmp へ読む (`0x409c80` の本体で src=rcx・dst=rdx を確認)。
  4. `0x1017ad0(rcx=**G2 (obj), rdx=job+0x48 (name), r8=&tmp, r9b = (job+0x20 == 1))` (`0xd698c8`)。`cmp qword [rbx+0x20],1` → `sete r9b` (`0xd698bf`〜`0xd698c4`)。核が書くのは下位 1 バイトで、**updateHistory が 1 のときだけ 1** (0・2・-1 では 0)。受け側 `0x1017ad0` が `r9d` 全体を読むため、真偽の読み方は §4 の未確定。

## 3. 戻り値と失敗 code

| 経路 | 条件 | 戻り値 | 根拠 |
|---|---|---|---|
| 成功 | 書式が通る・準備真 | status 0 → `0xd82c20(0)` → **None** (保留例外が無いとき) | `0xd69a09`〜`0xd69a12`・`REPORT_PY61.md` §4-1 |
| 引数不正 | 型違い・flags 欠落・不明 kw | ParseTupleAndKeywords が 0 を返す → `0xd69a10` で `0xd82c20(0)` → ParseTuple が立てた保留例外があるので **NULL** | `0xd69996` `jle 0xd69a10`・`REPORT_PY61.md` §4-1 |
| 準備不可 | `G1+8` の準備判定 (`0xd69888` の `call [vtbl+0x98]`、`0xd69890` の `je`) が偽 | status -2 → `0xd82c20(-2)`。`0xd82c6a`〜`0xd82c84` で global `0x15e4790` → `[obj]` → `+8` のオブジェクトの `call [vtbl+0x88]` (`0xd82c7e`) を呼ぶ。その戻りが 0 なら **None** (`0xd82dd0`・`call 0xc38bc0`)。非 0 なら文言 「Operation unsafe at current time」 (FL の文言表) の例外を立てて **NULL** (`0xd82c8c`〜`0xd82dc8`。例外投入は `0xd82dc6`)。`0xd82c7e` の判定の意味は未確定 (§5) | `REPORT_PY61.md` §4-1 (文言表・報告判定の分岐) |
| flags 範囲外 | — | **核に範囲判定は無い** (`0xd69860`〜`0xd698d3` を全部読んだ)。失敗 code は出ない | — |

- 成功時の Python 戻り値は None (`REPORT_PY61.md` の `0xc38bc0` 経由)。
- 「履歴の登録に失敗したときの code」は核の中では見えない。`0x1017ad0` の戻り値は使われていない (`0xd698c8` の後は status を変えない)。

## 4. 履歴の登録 (`0x1017ad0`) の内訳

| 段 | 呼び出し | 確定度 | 内容 |
|---|---|---|---|
| a | `0x1016ca0(obj)` → `r13` | 先頭のみ確定 | `0x1017150(obj)` を呼ぶ分岐 (`0x1016cbb`)。真なら `0x1019e30`・`0x1019da0`、偽なら別経路。本体は未読 |
| b | `0x101b780(r13, name, &tmp, r9d)` | **未確定** | record への書込み。引数の意味 (flags の値域・bool の読み方) は本体未読 |
| c | `0x1017150(obj)` | 確定 | `cmp qword [rcx+8],0 / setne al` (`0x1017150`〜`0x1017155`)。つまり「履歴管理オブジェクトの有無」 |
| d | 真: `0x1019b70([obj+8], r13)` | 確定 (配列追加) | `[obj+8]+0x20` の配列末尾へ `r13` を追加。count は `qword [ptr-8]`。伸長は `0x417fc0` (未読) |
| e | 偽: `0x1019dd0(r13)` | 確定 (ループ) | record の配列 `[r13+0x20]` の各要素に `0x40faa0` を呼ぶ (解放と推定。`0x40faa0` は本体未読) |

- `0x409c80` (8 バイト複写): `src=rcx`・`dst=rdx`・`n=r8`。`n=8` は 4 バイト 2 本の重なり読み (`0x409cb5`)。
- **r9b の上位ビット**: 核は `sete r9b` で下位 1 バイトだけ設定する。`0x1017ad0` は `mov edi, r9d` で 32 ビット全体を受けるため、上位ビットが残ると真偽の読み方が変わりうる。`0x101b780` の読み方 (r9b か r9d か) が未確定なので、この影響は未確定。

## 5. 未確定と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x101b780` 本体 (record の書込み項目・flags の意味・r9b/r9d の読み方) | 履歴 record の構造が決まらない。実装できない | 子 `[PY-137]` (#3026) |
| `0x1016ca0` の生成分岐・`0x1019e30`・`0x1019da0`・`0x417fc0`・`0x40faa0` | record の生成・伸長・解放の実体 | 子 `[PY-137]` (#3026) |
| `0x41c6e0` (char* → name object の所有権・寿命) | name の寿命と解放時期 | 子 `[PY-137]` (#3026) |
| mock / C の undo 履歴モデル (`getUndoHistoryCount` 等・PY-70 の getter との整合) | 実装の状態を決める根拠 | 子 `[PY-137]` (#3026) |
| 保留例外の Python 例外型 (`0xd82c20` の `[rip]` 先) | 引数不正時の例外型 | `REPORT_PY61.md` §4-2 の未確定。親 #2978 へ提案 (本 PR では扱わない) |
| `0xd82c20` の報告判定 (`call [vtbl+0x88]`・`0xd82c7e`。global `0x15e4790` の `+8` オブジェクト) の意味 | 準備不可時に、文言付き例外 (「Operation unsafe at current time」) と None のどちらになるかが決まらない | 本 PR の未解決表。`REPORT_PY61.md` §4-1 に注記 |

## 6. 検証

- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py124_saveundo.py` → `PASS` (実測 0.06 秒。load average 0.02 / 0.22 / 0.15 は uptime の実測)。出力: `fmt='si|i' kwlist=['undoName', 'flags', 'updateHistory'] default_updateHistory=1 core_ready_check=call[vtbl+0x98] update_eq_1=sete_r9b`。
- ネガティブコントロール: 期待書式を `si|ii` に変えたコピー → `AssertionError: si|i` で停止 (実測。検査が書式を見ていることの確認)。
- 逆アセンブル補助 (1 コマンドで再現): `python3 analysis/py41_disasm.py <block00031_PE.bin> d69900 d69860 d843d0 1017ad0` (`py41_disasm.py` は最初の `ret`/`int3` で止まる)。
- **範囲外**: 実機の FL で saveUndo を呼んだ結果 (履歴の見え方・例外の型) は未実測。`provider/`・`host/`・`tests/` は変更していない。`tests/general_diff.mjs`・`provider_check.mjs`・`all_tools.mjs` は本 PR のコード変更が無いので未実行 (provider の wasm build も行っていない)。
- 測定 commit: `3a53c9f9` (`analysis/py124_saveundo.py` を追加した commit。コードを変えた最後の commit)。`git diff 3a53c9f9 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 REPORT の commit 前後で実行して確認)。HEAD との差分は REPORT と DOC_MAP だけ。

## 7. 子 issue

- `[PY-137]` (#3026, 親 #2999): `0x101b780`・`0x1016ca0` の本体を確定し、mock と C provider へ `general.saveUndo` を実装する。受入条件は #2999 から移した 4 件 (REPORT §4 の確定・general_diff 差分 0・provider_check 期待値・all_tools 48/48)。
