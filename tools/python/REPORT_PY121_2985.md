# tools/python REPORT: PY-121 screen 状態の 5 関数の PE 確定と C provider 実装 (#2985, 親 #2832)

> 正本: `tools/python/REPORT_PY87.md` (手順の雛形)。本付録は PY-121 の実測のみ。

## 結論

- #2985 の screen 28 件のうち **5 件** (`screen.isBlanked`・`isUnBlank`・`getScreenActiveCounter`・`setScreenActiveCounter`・`unBlank`) を PE で確定し、mock と C provider に実装した。mock と C の差分は 0 (`tests/screen_diff.mjs` 32 呼出し)。確認した引数は int・bool・float・str と個数違い。None (既定値扱い)・bytes は未確認 (未解決)。
- **値は未確定**。5 関数の初期値 (`blanked false` / `unBlank false` / `activeCounter 0`) は mock と C で揃えた仮置き。実機値は未実測。
- 残り **23 件** は子 issue 3 件 (#3021 PY-134・#3022 PY-135・#3025 PY-136) に分けた。引数名と書式の表記は #2952 (PY-116) の範囲で、子は意味論と実装だけを扱う。
- flapi 表の `returns` は 5 件とも `None` のままだが、PE の読み方では値を返す (getter)。表の型は未修正 (生成元 `analysis/flapi_kwargs.py` 系の対象外。未解決の表を参照)。

## 手段

- ハンドラ探索: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_handler_probe.py <名前...>` (`extracted/block00031_PE.bin`)。entry VA と関数先頭 VA を得る。引数は PyMethodDef の素名 (`isBlanked`・`unBlank` など)。`screen.isBlanked` のように接頭辞を付けると出力が空になる (実測)。screen の entry は `0x151e5b8`〜`0x151e918` の範囲に限る (`init` は別の名前衝突が `0x151e058` にある)。
- 逆アセンブル: `analysis/flapi/pe_disasm.py <VA>`。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` (全体展開 5.6 秒)。

## 確定した 5 関数 (PE 根拠)

共通の読み方: 関数先頭で `call 0xd7eca0` (間接呼出しで対象オブジェクトのアドレスを返す共通アクセサ) → `[rax]` → `+0x50` → `+0x3f8` で screen 状態 (以下 `scr`) を得る。`scr` が 0 の経路は下の「未確定」を参照。

| 関数 | PyMethodDef entry | fn (VA) | flags | 書式 | 処理 (PE) | 変換 |
|---|---|---|---|---|---|---|
| `screen.isBlanked` | 0x151e838 | 0xd7c7e0 | 4 (NOARGS) | — | `movzx rcx, byte [scr+0x1d0]` を変換して返す | `call [0x15e4280]` (bool) |
| `screen.isUnBlank` | 0x151e858 | 0xd7c830 | 4 (NOARGS) | — | `movzx rcx, byte [scr+0x1d1]` を変換して返す | `call [0x15e4280]` (bool) |
| `screen.getScreenActiveCounter` | 0x151e878 | 0xd7c880 | 4 (NOARGS) | — | `mov ecx, dword [scr+0x1cc]` を変換して返す | `call [0x15e4280]` (int) |
| `screen.setScreenActiveCounter` | 0x151e898 | 0xd7c8c0 | 1 | `i` (0xd7c94c) | 引数 `i` を `add dword [scr+0x1cc], ecx` (**加算**。名前は set だが PE は足す) | 戻りは `0xd82c20(0)` 経路 |
| `screen.unBlank` | 0x151e818 | 0xd7c740 | 1 | `i` (0xd7c7d0) | `byte [scr+0x1d1] = (arg == 1)` (`sete`) | 戻りは `0xd82c20(0)` 経路 |

- 変換スロットは 3 件とも絶対アドレス `0x15e4280` (PY-87 の `general.*` と同じ)。bool と int は PE から区別できない (変換は値 1 個を `rcx` で渡す)。型は下の表の判断。
- 型の判断 (stub の doc から): `isBlanked`・`isUnBlank` は bool、`getScreenActiveCounter` は int。flapi 表の `returns: None` は PE と食い違う。
- `isBlanked` と `unBlank` が参照する `+0x1d0` と `+0x1d1` は別の byte。`+0x1d0` の書込み元 (`blank` の候補) は未確定。`+0x1cc` の他の参照元は未確定。
- 引数の書式 `i` は flapi 表の `kwsig.fmt` と一致 (`setScreenActiveCounter`・`unBlank` とも `i`・必須 1)。書式 `i` は bool も int として受理する (CPython の bool は int の subclass)。C の `fl_a_int` が `'B'` を `'I'` と同じに受理するのと一致する。`'D'` (float) と `'S'` (str) は C で code 5 (`type_ok`)。

## 未確定 (本 run で確定できなかった点)

1. **`scr == 0` (screen 未初期化) の経路**: `isBlanked`・`isUnBlank`・`getScreenActiveCounter` は `or ecx,-1` → `call 0xd82c20` (負値の経路) へ入る。`setScreenActiveCounter`・`unBlank` は書込みを飛ばし、引数の書式 parse 結果 (成功時 1) をそのまま `0xd82c20` に渡す (成功経路は 0 を渡す)。**例外の型・code・Python 側の戻り値は未確定**。mock と C は初期化済み (`scr != 0`) の経路だけを模す。
2. **`0xd82c20` の分岐の意味**: 0 は None 相当、正は `0xc38bc0` (整数化)、負はエラー経路と読めるが、0 の経路の内部 (`[rip+0x860485]` の呼出し) は未読。
3. **bool / int の変換**: 同じ `0x15e4280` を使う。PE からは区別できない (PY-87 と同じ)。
4. **`+0x1d0` の書込み元**: `blank` (`0xd7c600`・書式 `ii`) は `0xd843d0` を描画側の引数で呼ぶだけで、`+0x1d0` を直接書いていない。子 PY-135 で確認する。
5. **`0xd7eca0` の中身**: 間接呼出しで対象オブジェクトのアドレスを返す。どの global かは未確定 (全 screen 関数で共通)。

## 子 issue (残り 23 件)

| 題名 | 件数 | 対象 |
|---|---|---|
| `[PY-134]` (#3021) | 6 | addTextLine・removeTextLine・findTextLine・displayText・displayTimedText・animateText |
| `[PY-135]` (#3022) | 7 | addMeter・displayBar・fillRect・drawRect・drawText・eraseRect・blank |
| `[PY-136]` (#3025) | 10 | init・setup・update・deInit・keepDisplayActive・hideMenu・menuShowing・menuItemClick・menuNext・menuPrev |

親の #2985 は、本 PR で 5 件を完了単位として題名と本文を縮めた。子の番号は各 issue を起票した後に PR 本文の未解決表へ書く。

## 検証

測定 commit: `a1cba13f` (コードを変えた最後の commit。`Merge origin/main into 2985-screen-state-pe (#2985)`)。以下の表はこの commit のクリーンな作業ツリーで、`provider/build.sh` を再実行してから測定した。mock の引数検査の修正 (`5b8c500f`) は、merge commit `2d333ec9` (main `f0c00334` の取り込み) を経て本 commit に含まれる。前回の測定 (`535dd91e`) の値は無効になったので残していない。
main は `f0c00334` と `e64cfc70` (#3010 の ui 状態) の 2 回を rebase せず merge した。main 側の `tools/python/REPORT_PY121.md` (#2979 の general log・rec 系の報告) と番号 PY-121 が衝突したため、本 PR の報告は `REPORT_PY121_2985.md` に置いた。
環境: runner 4 core、測定時の load average 0.08 (`uptime` 21:31:20)。`FL_WIN64_DIR` は `[WIN64]` の展開先 (fl-win64 を `$RUNNER_TEMP` 配下に全展開、5.4 秒)。emsdk は `[EMSDK]` と同じ 6.0.12 を初回セットアップした (`toolchain-emsdk` の素材は本 run に無かった)。`build_cpython_wasm.sh` は emsdk の場所を固定で読むため、`[EMSDK]` の場所へ同じ版を向けた。前提生成物: `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0、4 分 26 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0、5.9 秒)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash provider/build.sh` | rc 0・ハンドラ 97 | 0.9 秒 |
| `node tests/provider_check.mjs` | PASS (435 / 実装 97 / 未実装 338 / MCP 静的 60) | 0.34 秒 |
| `node tests/screen_diff.mjs` | calls 32 (順序どおり 16 + 個数違い 4 + 型違い 12)、diffs 0、型違いの期待値一致 (12 呼出し × 2 engine)、PASS | 0.05 秒 |
| `node tests/general_diff.mjs` | calls 9、diffs 0、PASS (回帰なし) | 0.05 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback 往復 true | 1.6 秒 |

型違いの 12 呼出し (`unBlank(True)`・`unBlank(1.5)`・`unBlank("1")`・`setScreenActiveCounter(1.5)`・`setScreenActiveCounter("1")`・`setScreenActiveCounter(True)` など) は、結果が状態に依存するので初期状態の新しいエンジン 2 つで流し、期待値 (上の表と同じ) と mock・C の両方を照合した。

件数の変化: main (`e64cfc70`) の実装 92 / 未実装 343 から、5 件を追加して 97 / 338 (main 側の `pe100` 2 件・`pe119` 6 件を含む)。

ネガティブコントロール (`docs/WORKFLOW.md` §5): 測定 commit `a1cba13f` の `host/fl_mock.mjs` に次の 2 種類を入れ、`node tests/screen_diff.mjs` が FAIL することを確かめてから commit 版へ戻した (戻した後の `cmp` と `git status` は一致・空)。
- (1) 整数だけを見る回帰: `unBlank` を `argI(a, 0, 0) === 1` から `argI(a, 0, 0) !== 0` にする → `AssertionError: screen 差分 1 件`、rc 1 (FAIL)。`unBlank(2)` の int 入力で検出。
- (2) 型検査を外した修正前の行: `unBlank` を `a[0] === 1` に戻す → `AssertionError: screen 型違い 期待値と不一致 4 件`、rc 1 (FAIL)。bool・float・str の入力で検出 (修正前の mock は int だけの `screen_diff` を通っていた)。
戻した後は calls 32・diffs 0・PASS (rc 0)。

コード差分 (測定 commit から PR HEAD まで、`tools/python` の .md 以外。本 REPORT を含む md のみの commit を後から足しても 0 行のまま):

```
$ git diff a1cba13f HEAD -- tools/python ':!*.md'
(空)
```

## 未解決

- 5 関数の値 (`blanked` / `unBlank` / `activeCounter` の初期値) は仮置き。実機の値は未実測。mock の値をそのまま正として扱わないこと。
- `scr == 0` の経路 (上の未確定 1)・`0xd82c20` の分岐 (上の未確定 2)・bool/int の区別 (未確定 3)。
- mock と C の型検査の照合は int・bool・float・str と個数違いだけ。None (既定値扱い)・bytes は呼出し列で未確認。
- flapi 表の `returns` (5 件とも `None`) の修正は、表の生成元を直す別作業 (起票先: #2952 (PY-116)。表の整理に含めることを依頼する)。
- 残り 23 件: 子 #3021 (PY-134)・#3022 (PY-135)・#3025 (PY-136)。
