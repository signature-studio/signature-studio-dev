# tools/python REPORT: PY-131 ui のブラウザ移動 3 件 (navigateBrowser・navigateBrowserMenu・navigateBrowserTabs) の PE 根拠と保留 (#3012, 親 #2982)

> 前段: `tools/python/REPORT_PY121_2982.md` (3 件の PyArg 書式と保留の記録)・`tools/python/REPORT_PY125.md` (dispatch `0xd843d0`・述語・結果変換 `0xd82c20` の読み方)。
> 解析の一次データ: `block00031_PE.bin` (`$RUNNER_TEMP/fl-win64/extracted/`)。解析補助: `analysis/flapi/pe_handler_probe.py`・`analysis/flapi/pe_disasm.py`。
> 既知類型との関係: 該当なし (PE の直接逆アセンブル。`docs/DEFECTS.md` の類型は対象外)。

## 結論

- 3 件とも **保留**。mock・C provider は変更していない (実装数・未実装数の変化 0)。
- 保留の理由: 戻り値 `str` の中身 (ブラウザの項目名) と、作用先の状態 (項目の並び・選択位置) の同定が未了。mock/C に既定値 (`""` など) を置くと、FL の実値と違う文字列を返す silent miscompile になる。
- 確定したのは、引数書式 (`ii`・`ii`・`i`)、3 件に共通の骨格 (dispatch → callback → str 化。引数は書式ごとに 2 形)、成功・失敗の分岐、callback が呼ぶ作用先の関数 (navigateBrowser: `0x107eb10`、navigateBrowserTabs: `0x107eab0` → `0xa88f90`)、名前の取得元の候補 (`0xa89600`・`0xa89010`)。
- 未確定の一覧と起票先は「未解決」節。実装は子 issue PY-239 (#3720) に分けた。

## PE 根拠 (VA)

| 関数 | PyMethodDef entry | fn (VA) | PyArg 書式 | callback (VA) | callback が呼ぶ作用先 | 名前の取得 |
|---|---|---|---|---|---|---|
| `ui.navigateBrowser` | 0x151b988 | 0xd6dad0 | `ii` (direction, shiftHeld) | 0xd6d9b0 | `0x107eb10(obj, key, shift==1)` | `0xa89600` |
| `ui.navigateBrowserMenu` | 0x151b9e8 | 0xd6dad0 (navigateBrowser と同一 fn) | `ii` | 0xd6d9b0 (同一) | 同上 | 同上 |
| `ui.navigateBrowserTabs` | 0x151b9c8 | 0xd6ded0 | `i` (direction) | 0xd6ddf0 | `0x107eab0(obj, direction)` | `0xa89010` |

- `pe_handler_probe.py navigateBrowserMenu` の出力で、entry 0x151b9e8 の fn が 0xd6dad0 と一致することを確認した。
- 書式は `flapi_kwargs.json` (`fmt`: `ii` / `i`) と、PE の `lea rdx,[rip+X]` 先の文字列 (`str@0xd6db13` → `'ii'`) が一致する。

## 呼出し形 (dispatch `0xd843d0` への引数と前後の処理)

書式で 2 形に分かれる。engine 取得・status 判定・str 化は両形で同じ。

### 形 A: navigateBrowser・navigateBrowserMenu (fn 0xd6dad0・書式 `ii`)

1. `0xd6fd10(self)` で engine を得て、その `[rax]` を dispatch の第 1 引数に渡す (0xd6db07〜0xd6db0c)。
2. `PyArg` 解析: direction を `[rbp+0xac]`、shiftHeld を `[rbp+0xa8]` に受ける (`lea r8` / `lea r9`、0xd6db1a・0xd6db21)。戻り ≤ 0 は error 経路 (`0xd6dbea`)。
3. dispatch `0xd843d0` を呼ぶ (0xd6db92)。第 5 引数 (`[rsp+0x20]`) = direction、第 6 引数 (`[rsp+0x28]`) = shiftHeld (いずれも `movsxd` で符号拡張)、第 11 引数 (`[rsp+0x50]`) = 1。callback は `r8` に渡す (0xd6db47 の RIP 相対から 0xd6d9b0)。

### 形 B: navigateBrowserTabs (fn 0xd6ded0・書式 `i`)

1. 形 A の 1 と同じ (0xd6df07〜0xd6df0c)。
2. `PyArg` 解析: direction を `[rbp+0xac]` に受けるのみ (`lea r8` のみ。`r9` は渡さない、0xd6df1a)。shiftHeld の引数は無い。戻り ≤ 0 は error 経路 (`0xd6dfe0`)。
3. dispatch `0xd843d0` を呼ぶ (0xd6df88)。第 5 引数 (`[rsp+0x20]`) = direction (`movsxd`)、第 6 引数 (`[rsp+0x28]`) = 0 (`mov qword ptr [rsp+0x28], 0`、0xd6df56)、第 7〜10 引数 = 0、第 11 引数 (`[rsp+0x50]`) = 1。callback は `r8` に渡す (0xd6df40 の RIP 相対から 0xd6ddf0)。

### 形 A・B 共通: status と str 化

4. `[rbp+0x88]` = status。0 以外なら `0xd82c20(低 32bit)` で例外化 (PY-125 と同じ未同定の経路)。
5. status == 0 かつ `[rbp+0x90]` ≥ 0 のとき、`[rbp+0x98]` の文字列を `0x41c420` で `[rbp+0xa0]` に写し、`0x414000` と PyUnicode 生成の関数ポインタ (`call [rax]`) で str にする。`[rbp+0x90]` < 0 なら `[rbp+0xa0]` は初期値 0 のまま `0x414000(0)` を通る (null 時の既定文字列は未確認)。
   - `[rbp+0x90]`・`[rbp+0x98]` は dispatch の out 構造の 2・3 番目と読める (callback の task+0x10 = 結果 int、task+0x50 = 名前、に対応する推定)。`0xd843d0` が書く側は未確認。

### 第 11 引数 (flag): 事実と解釈

- 事実: 形 A・B とも第 11 引数は `1` (`mov byte ptr [rsp+0x50], 1`)。呼出し先 `0xd843d0` は、その byte (`[rbp+0xb0]`) を 0xd84471 と 0xd844de で読み、非 0 のとき vtable 経由の呼出しを行う (0xd84481 `call [rax]`、0xd844f6 `call [rdi]`)。
- 解釈 (未確認): REPORT_PY121 はこの flag を `sync` と呼んだ。呼出し先の中身を読んでいないため、同期実行かどうかは断定しない。

## callback の共通形 (0xd6d9b0・0xd6ddf0)

- 先頭で `task[+0x60] = -2`。述語 `pred = vtbl(this)[+0x98]()` の `this` は `*(*(0x15e4790)+8)` (0xd6d9d1〜0xd6d9e5・0xd6de11〜0xd6de25。PY-125 の述語と同じ読み)。
- pred 偽: `task[+0x60]` が -2 のまま返り、status -2 として error 経路に入る。
- pred 真: `task[+0x10] = -1` → 作用の関数を呼ぶ → 戻り値 (int) を `task[+0x10]` に入れる → 戻り ≥ 0 のとき名前を `task[+0x50]` に入れる → `task[+0x60] = 0`。

### navigateBrowser・navigateBrowserMenu (callback 0xd6d9b0)

- direction の写像 (0xd6d9ff〜0xd6da27): x = direction について、x が 0x28〜0x2b なら x のまま、x == 0x7f なら 0x28、それ以外は 0x29。
- `0x107eb10(obj, key, shift==1)` (0xd6da45) の戻り値: 0x107eb2b の `or eax,-1` で `-1` を入れ、0x107eb2e の `cmp qword ptr [0x63ce1a], 0` が 0 のとき `je 0x107ec3b` (0x107eb36) で epilogue に抜けて `-1` を返す。それ以外は 0x107ec36 の `mov eax,1` で成功 `1` を返す。
- `0x107eb10` の内部: 先頭で `vtbl[+0x260](obj)` を呼ぶが結果は `or eax,-1` で捨てる。key ∈ 0x28〜0x2f のとき bit マスク (`[rip+0x56]`) を見て分岐 (0x107ebd4〜0x107ebf1)。以降は `0xfdd2c0`・`0x86a220`・`0xa890c0`・`0xbd68e0` を呼ぶが効果は未同定。
- 名前: `0xa89600(obj, &name)` は `vtbl[+0x100](obj, 0)` の戻り項目 (null でなければ)、その `+0x48` の object の `vtbl[+0x88](object, &name)` で名前を書く (0xa89614〜0xa8962e。各 vtable の実体は未同定)。

### navigateBrowserTabs (callback 0xd6ddf0)

- direction は写像せず、そのまま `0x107eab0` の第 2 引数に渡す (0xd6de49)。
- `0x107eab0` (0x107eab0〜0x107ead6): `[0x63ce91]` == 0 なら戻り -1。非 0 なら `0xa88f90(obj, direction)` を呼んで戻り 1。
- `0xa88f90` (0xa88f90〜0xa89003) の選択規則 (PE の分岐を直接読んだ):
  - direction == 42 (0x2a): 前へ。`max(index-1, 0)` (0xa88fab〜0xa88fc0)。
  - direction == 43 (0x2b): 次へ。`index+1` が `count-1` を超えるなら `count-1` (0xa88fc4〜0xa88fe7。count は `0xa523d0`)。
  - それ以外: 先頭 (0)。
  - 結果が現在の index と違えば `0xa7ee90(obj, 新 index, 0)` で選択する (0xa88ff1〜0xa88ffe。0xa7ee90 の効果は未同定)。
- 名前: `0xa89010(obj, &name)` は `obj+0x160` の一覧から `0xa51f50` で項目を得て、項目 `+0x20` の文字列を書く (0xa89010〜0xa8902d)。`0xa51f50` の index の出所 (`0xa52140`) は未同定。

## 手段 (再現コマンド)

- 展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (2.9 秒)。`fetch_inputs.sh` のため `*block24429_DATA.bin`・`*block24430_DATA.bin`・`*block25159_DATA.bin`・`*block24618_DATA.bin` も展開する。
- probe: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_handler_probe.py navigateBrowser navigateBrowserMenu navigateBrowserTabs`。
- 逆アセンブル: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA 16 進> <命令数>`。本文の VA は全て、このコマンドで読んだもの。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x107eb10` の内部: `[0x63ce1a]` の意味、`0xfdd2c0`・`0x86a220`・`0xa890c0`・`0xbd68e0` の効果、成功 1 の内訳 | navigateBrowser・navigateBrowserMenu の作用が確定しない | 子 issue PY-239 (#3720) |
| `0x107eab0` の `[0x63ce91]` の意味、`0xa7ee90` の副作用 (選択の通知)、`0xa523d0` (件数) | navigateBrowserTabs の作用が確定しない | 子 issue PY-239 (#3720) |
| `0xa51f50`・`0xa52140` (一覧の index の出所)、`0xa89600` の `vtbl[+0x100]`・`[+0x48]`・`[+0x88]` の実体 | 名前 (戻り値 str) の取得元が未確定 | 子 issue PY-239 (#3720) |
| `0xd843d0` の out の書込み (out+0x8・out+0x10 の出所)、第 11 引数 flag の呼出し先 (0xd84481・0xd844f6) の中身 | 戻り値 str の経路が推定のまま。flag の意味 (`sync` の名前) も未確定 | 子 issue PY-239 (#3720) (PY-125 の未解決と共通) |
| pred `vtbl[+0x98]` (gate `0x15e4790`) の意味と偽時の挙動 (`0xd82c20(-2)`) | error 経路の Python 側の例外型が未確定 | 子 issue PY-239 (#3720) (PY-125 と共通) |
| `navigateBrowserTabs` の direction の値域: PE は 42・43 以外を先頭選択とする | Python が渡す値の意味 (FL 側の API 文書) が未確認 | 子 issue PY-239 (#3720) |

## 検証

- 測定 commit: `77f804e70` (main。本 PR はコードを変えていない)。`git diff 77f804e70 HEAD -- tools/python ':!*.md'` の出力は空。
- 環境: runner 4 core、測定時 `uptime` は `load average: 0.91, 1.37, 0.73` (03:29:33)。`$RUNNER_TEMP/fl-win64` に展開。emsdk は `[EMSDK]` (既存・`docs/REFERENCES.md` §4)。

| コマンド | 結果 | wall |
|---|---|---|
| `bash fetch_inputs.sh` | rc 0 (`work/` に midi.py・utils.py・MCPTools.pyc・device script・fl-stubs) | 0.3 秒 |
| `bash build_cpython_wasm.sh` | rc 0 (`python.wasm` 5,927,852 B) | 4 分 4 秒 |
| `FLPY_SKIP_TABLE=1 bash build_flpy.sh` | rc 0 (`flpy.wasm` 5,924,680 B) | 6.1 秒 |
| `bash provider/build.sh` | rc 0 (`dist/flprov.wasm` 64,121 B・ハンドラ 155) | 1.4 秒 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 48/48 ok、host_calls 37,425、callback_roundtrip true | 2.1 秒 |
| `node tests/provider_check.mjs` | PASS (functions 435 / implemented 155 / unimplemented 280 / MCP static 60) | 0.36 秒 |

- 差し戻し対応 (review round 1) での再読: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA> <命令数>` で `0xd6ded0` (75 命令)・`0xd6dad0` (75 命令)・`0x107eb10` (52 命令)・`0x107ec10` (52 命令)・`0xd6da20`・`0xd6de30`・`0xd84400`・`0xd84290`・`0xd84486`・`0xd844de` を読み、呼出し形 (形 A・B)・`0x107eb10` の `je`/`or` の位置・第 11 引数の読み先を本文と照合した。全て一致。
- ネガティブコントロールは対象外 (RE の記録のみで、実装の検査は無い)。

## 製品 KPI (起動・GUI に関わる PR の記載)

- FLEngine 起動の dispatch 数・通過 unit 数 (`tools/flelift/boot/REPORT.md`)・最初のウィンドウの有無: **動かしていない**。本 PR はコードを変えず、起動経路にも触れていない。
