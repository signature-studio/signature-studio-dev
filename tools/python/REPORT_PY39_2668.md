## 8 回目 run: selectAll の `*p` (0x154528c) の書込み候補を列挙

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_rip_refs.py 0x154528c 0x15e3a60` (本 run で追加)。展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` (2.3 秒)。
- 測定 commit `09df3f91` (コード変更の最後の commit。`pe_rip_refs.py` の docstring 例を `0x15e3a60` に直した。解析ロジックは変更していない)。実測: 終了 0・hits 50・25.763 秒・load average (1 分値) 0.23 → 0.49 (4 core)・並列数 1 (単一プロセスの線形走査)。
- 参考 (PR 時点の commit `63304ec6`): hits 50・25.8 秒・load average 2.21 (4 core)・並列数 1。
- docstring の旧例 `0x154528c` 単独: hits 0 (終了 0・25.961 秒)。
- `0x154528c` を直接参照する RIP 相対命令は 0 件。`0x15e3a60` (`*p` を格納するスロット) を参照する 50 件はすべて読込み (`mov rax|rcx, qword ptr [rip+…]`) で、スロットへの書込みは無い。よって `*p` の書込みは、このスロットを読んだ後の間接書込みになる。
- 読込み直後の `mov dword ptr [reg], …` (`*p` への書込み候補。読込み後 14 命令内・call 前までの走査):

| 書込み VA | 命令 | 読み取れた内容 |
|---|---|---|
| 0x103b781 | `mov [rcx], eax` | 所属関数の先頭・引数は未読 |
| 0x103b9ec / 0x103ba02 | `mov [rax], esi` / `mov [rax], ebx` | 関数 0x103b950 (引数 ecx=ebx・edx=esi)。`*p == ebx` なら `*p = esi`、それ以外で `*p == esi` なら `*p = ebx` (入替え)。呼出元は E8 走査で 0x103bb1a・0x103bc1b (別関数の内部) |
| 0x103be3a | `mov [rax], ecx` | 所属関数は未読 |
| 0x103c01c | `mov [rax], esi` | 所属関数は未読 |

- 別フィールドへの書込み: 0x1003e32 の `mov dword ptr [rax+0x798], 0` は、直前の 0x1003e2e `mov rax, qword ptr [rbp+0x30]` で `rax` が再読込みされた値へのストアである。base は `[rbp+0x30]` の所属で未確定 (`*p` 由来の `p` (0x154528c) とは限らない)。`ffac20` の `item+0x798` との対応も未確認。
- 結論: `*p` の書込み候補 4 行 (VA 5 件) を列挙したが、selectAll の経路 (0xd5b150 → 0xd843d0 → 0xd5b100 → 0x11e8670) がこれらを通るかは未確認。実行時の値も未確定。`selectAll` の実装は見送る。
- 次に読む対象: 0x103b950 の呼出元 (0x103bb1a・0x103bc1b) の関数先頭、0x103b781・0x103be3a・0x103c01c の所属関数と引数、それらが selectAll の経路から呼ばれるかの call 連鎖。
- 受入条件 (#1527) の扱い: selectAll の未解決は本節の候補列挙までとし、残りは子 issue #2668 (`[PY-85]`) に移した。
- 検証 (測定 commit `12e711cc`・コミット済み HEAD): `fetch_inputs.sh` 0.98 秒 / `build_cpython_wasm.sh` 220 秒 / `FLPY_SKIP_TABLE=1 build_flpy.sh` 4.8 秒 / `provider/build.sh` 1.0 秒。`channels_diff` 69 呼出し diffs 0 PASS (0.15 秒)。`provider_check` 実装 71・未実装 364 PASS。`FL_ENGINE=wasm all_tools` 48/48 ok (1.34 秒)。`git diff 12e711cc HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行。
- 8 回目節の測定 commit `09df3f91` からの差分: `git diff 09df3f91 HEAD -- tools/python/provider tools/python/host tools/python/tests` は 0 行 (本 REPORT の commit 時点で確認)。

## 9 回目 run (PY-85 / #2668): `*p` の書込み元の到達性と status 写像

- 対象: `channels.selectAll` の選択値 (`*p` = `0x154528c` の int32) とゲートの確定 (子 #2668)。
- 結論: 選択値は**確定できなかった**。実装は行わない (受入条件 (5) の経路)。
  - `*p` の書込み元 4 関数 (5 VA) を所属関数に帰属させた (下表)。selectAll の**直接 call** の前進閉包 (566 関数・深さ 60 まで) からは到達しない。ただし閉包内に**間接 call が 191 箇所**あり、そこを解決していないため「到達しない」とは証明できていない。
  - 段 6 の status → 例外文言の写像 (`0xd82c20`) の対応を確定した (下表)。`c38bc0` の中身と、文言を出す分岐のゲート `[rax+0x88]` は未確定。
  - 通常時の `*p`・`obj+80`・`d84f30`・callback の状態 byte は静的解析では確定しなかった (残ゲート・下の未解決表)。
- 直接 call 元の数は `callers` mode で数え直した。`0x103b710` は 32 箇所・30 関数 (前版の「8 箇所・12 関数」は誤り)。
- 既知類型との関係: 該当なし (意味論の読解。lift 出力は実行に使っていない)。

### 測定

- 測定 commit: `e9d3a847` (main を取り込んだ merge commit)。`pe_callgraph.py` の最後の変更は `4fe5d043` (`callers` mode と `--callee-starts` を追加) で、`git diff 4fe5d043 e9d3a847 -- tools/python/analysis/flapi/pe_callgraph.py` は 0 行。`git diff e9d3a847 HEAD -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis` は本 REPORT の commit 時点で 0 行 (本 PR はこれらのコードを変えない)。main 取り込みで provider/host/tests に入った差分は他 PR のもので、解析は素材 (`block00031_PE.bin`) と `pe_callgraph.py` だけを読むため結果に影響しない。取り込み後の commit で測り直した。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` から `block00031_PE.bin` のみ展開 (`tar --zstd -xf ... --wildcards '*block00031_PE.bin'`・2.8 秒)。展開先はリポジトリ外 (`$RUNNER_TEMP/flpy39`)。`FL_WIN64_DIR=<展開先>` で `extracted/block00031_PE.bin` を読む。
- 再現 (`FL_WIN64_DIR=<展開先>` で実行):
  - 所属関数: `python3 analysis/flapi/pe_callgraph.py func 0x103b781 0x103b9ec 0x103be3a 0x103c01c`
  - 直接 call 元: `python3 analysis/flapi/pe_callgraph.py callers 0x103b710,0x103b950,0x103ba10,0x103bd60,0x103bec0 0xd5b150,0xd843d0,0xd5b100,0x11e8670,0xff8a90,0xffac20 60`
  - 前進閉包: `python3 analysis/flapi/pe_callgraph.py fwd 0xd5b150,0xd843d0,0xd5b100,0x11e8670,0xff8a90,0xffac20 0x103b710,0x103b950,0x103ba10,0x103bd60,0x103bec0 60`
  - 閉包の補正版: 上の `fwd` に `--callee-starts` を付ける
  - 段 6: `python3 analysis/flapi/pe_disasm.py 0xd82c20 70` と、各 `lea rdx, [rip+…]` 先の文字列 (下表)
- 実測 (`e9d3a847`・クリーンな worktree・コミット済み HEAD): `callers` 終了 0・36.9 秒。`fwd` 終了 0・36.8 秒 (閉包 566 関数・間接 call 191 箇所・標的 hit 0)。`fwd --callee-starts` 終了 0・37.0 秒 (閉包 665 関数・間接 call 208 箇所・標的 hit 0)。`func` は下表と一致。load average (1 分値) 0.11 → 0.92 (4 core)・並列数 1 (単一プロセスの線形走査)。同じ結果を `4fe5d043` でも得た。

### `*p` の書込み元の所属関数と直接 call

| 書込み VA | 命令 | 所属関数 (推定) | 直接 call 元 (`callers` の実測) |
|---|---|---|---|
| 0x103b781 | `mov [rcx], eax` | 0x103b710 | 32 箇所 (30 関数から)。閉包内は 0 |
| 0x103b9ec / 0x103ba02 | `mov [rax], esi` / `mov [rax], ebx` | 0x103b950 (`*p` の入替え。8 回目 run 節) | 2 箇所 (1 関数 0x103ba10 から: 0x103bb1a・0x103bc1b)。閉包内は 0 |
| 0x103be3a | `mov [rax], ecx` | 0x103bd60 | 3 箇所 (3 関数から: 0x103c000 (0x103bec0)・0x1041a95 (0x1041990)・0x11d3bde (0x11d3750))。閉包内は 0 |
| 0x103c01c | `mov [rax], esi` | 0x103bec0 | 直接 call 0 箇所 (関数ポインタ・vtable 経由のみ) |

- 直接 call 元の数え方: `callers <標的 VA csv>` は全 `.text` の E8 rel32 から標的 VA への呼出し箇所を集め、各箇所を所属関数 (`func` と同じ推定) へ帰属させる。関数数は帰属先の異なり数。根 VA を渡すと、各箇所の所属関数が根からの閉包 (`fwd` と同じ深さ 60) に入るかを出す。
- 前版の `0x103b710` の「8 箇所 (12 関数から)」は誤りで、上の数に直した。`0x103b950`・`0x103bd60`・`0x103bec0` の前版の数は実測と一致していた。
- 所属関数は CC パディング直後の命令を関数先頭とみなした推定。既知の関数 (`0xd5b150`・`0xd843d0`・`0xd5b100`・`0x11e8670`・`0xff8a90`・`0xffac20`・`0xd84f30`) は一致した。
- 標的は 5 関数 (書込み元 4 関数 `0x103b710`・`0x103b950`・`0x103bd60`・`0x103bec0` と、`0x103b950` の呼出元 `0x103ba10`)。いずれも、selectAll の経路 (`0xd5b150`・`0xd843d0`・`0xd5b100`・`0x11e8670`・`0xff8a90`・`0xffac20`) から直接 call の前進閉包で到達しない。
- 閉包の補正版 (`fwd ... --callee-starts`): 直接 call の先も関数先頭に加えると、閉包は 665 関数・間接 call 208 箇所に広がる。標的 5 関数は依然として届かなかった。ただし関数先頭は CC パディングと直接 call 先からの推定にすぎず、閉包の完全性は未証明 (未解決表)。

### 段 6: status → 例外文言の写像 (`0xd82c20`・PE 実測)

`0xd82c20` は `[rbp+0x24]` の status を受け、`0xd82c6a` 以降で分岐する。

| status | 分岐 (VA) | 文言 (`lea` 先の文字列) |
|---|---|---|
| 0 以上 | `0xd82c5c` `call 0xc38bc0` の戻り値を返す (`c38bc0` は未読) | なし |
| -1 | `0xd82d03` (`lea` at `0xd82d07`) | `Unspecified error` |
| -2 | `0xd82d18` (`lea` at `0xd82d1c`) | `Operation unsafe at current time` |
| -3 | `0xd82d2a` (`lea` at `0xd82d2e`) | `Range error` |
| -4 | `0xd82d3c` (`lea` at `0xd82d40`) | `Index out of range` |
| -5 | `0xd82d4e` (`lea` at `0xd82d52`) | `Wrong number of function parameters or wrong parameter type` |
| -6 | `0xd82d60` (`lea` at `0xd82d64`) | `Linked device not assigned` |
| -7 | `0xd82d72` (`lea` at `0xd82d76`) | `Device not assigned` |
| -8 | `0xd82d84` (`lea` at `0xd82d88`) | `Plugin not valid` |
| -9 以下 | `0xd82d96` (`lea` at `0xd82d9a`) | `Unknown error` |

- 負の status の経路: 先に `0xd82c6a` で global object の `[rax+0x88]` (vtable) を呼ぶ。真なら上表の文言を `0x4135e0` で文字列に設定し、`0x414000` で変換して `[rbx]` を呼んだ後、戻り値 0 (NULL) を返す。偽なら `0xd82dd0` で `call 0xc38bc0` の戻り値を返す。
- status 0 の経路: `0xd82c3c` で global object の vtable `[rax]` を呼び、非 0 なら戻り値 0 (NULL)。0 なら `0xd82c5c` で `c38bc0` を返す。
- 0 の判定と `0x4135e0` の中身は未読。上表の対応 (status と文言) は `lea` 先の文字列と分岐の比較値から確定。

### 受入条件 (#2668) の状態 (9 回目 run 時点)

- issue #2668 は (5) の範囲に縮めて `Closes` で閉じる。(1)〜(4) は未達のため issue 本文から外し、原文を下に移した。未達の子 issue は起票しない (未解決の追跡だけのため。下の未解決表)。
- [達成] (5) 理由と残ゲートを本 REPORT に残し、実装は行わない (`provider/fl_engine.c`・`host/fl_mock.mjs` は変更しない)
- 移した受入条件 (原文のまま):
  - (1) selectAll の経路 (0xd5b150 → 0xd843d0 → 0xd5b100 → 0x11e8670 → 0xff8a90 → 0xffac20) で、`*p` の通常時の値と、ゲート (`obj+80`・`d84f30`・状態 byte) が成立するかを PE 解析箇所つきで REPORT に残す。 → 部分。書込み元 4 関数の所属関数と、selectAll 閉包 (直接 call) からの非到達を PE 箇所つきで記録。通常時の `*p`・`obj+80`・`d84f30`・状態 byte は未確定
  - (2) 戻り値・範囲外 code (段 6 の写像 `0xd82c20`・`c38bc0`) を確定する。 → 部分。段 6 の status → 文言の写像は確定 (上表)。`c38bc0` と文言分岐のゲート `[rax+0x88]` は未確定
  - (3) 確定できたら `provider/fl_engine.c` と `host/fl_mock.mjs` に実装し、`tests/channels_diff.mjs` で mock と C の diffs 0。 → 条件不成立のため対象外 (選択値・ゲートが未確定。実装しない)
  - (4) `FL_ENGINE=wasm node tests/all_tools.mjs` が 48/48 ok を維持。 → 未実施。本 PR は provider/host/tests を変えない。直近の 48/48 は `12e711cc` (8 回目 run)

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `*p` (`0x154528c`) の通常時の値。書込み元 4 関数 (0x103b710・0x103b950・0x103bd60・0x103bec0) を実行時にどの経路で呼ぶか | 初期値 -1 のままなら `ffac20` は全 channel で 1 (全選択)。値が 0 以上なら `item+0x798 == *p` の channel だけが選ばれる | 同じ選択ゲート `0xffac20` を扱う #2642 [PY-82] (OPEN) へ参照を残す。子は起票しない。親 #1527 は閉じ済み |
| 書込み元への経路の非到達の証明: 閉包内の間接 call 191 箇所 (vtable・関数ポインタ) | 直接 call の閉包では到達しないが、間接 call の先は未解決のため、非到達は未証明 | 本表のみ |
| 段 2 の `obj+80` と `d84f30`、段 3 の状態 byte の通常時の値 | 通常時にゲートが通るかが未確認。通らないと selectAll は -2 で何もしない | 本表のみ |
| `c38bc0` の中身 (status 0 以上の戻り値) と、文言分岐のゲート `[rax+0x88]`・status 0 の `[rax]` | None 扱いと例外文言を出す条件が未確認 | 本表のみ |
| 関数先頭の推定の限界 (`pe_callgraph.py` は CC パディング後の先頭だけを検出する。`0xd82c20` は `0xd829f0` の内側と誤帰属)。`--callee-starts` の補正版 (665 関数) でも標的は届かなかったが、先頭の検出漏れは残る | 閉包が過小評価になる可能性。上の「到達しない」は暫定 | 本表のみ |
| 移した受入条件 (1)〜(4) の未達分 (原文は上の「受入条件」節) | 通常時の選択値とゲートが未確定のため、`channels.selectAll` の C provider / mock 実装 (`channels_diff` 0 と `all_tools` 48/48 の再確認) は行わない | 本表のみ (issue #2668 は (5) の範囲で閉じた) |

### 8 回目 run 節の分割移動 (250 行上限のため)

- 8 回目 run 節 (旧 `REPORT_PY39.md` の 222〜243 行) は本ファイルの先頭に全文を移した。内容は変えていない。`REPORT_PY39.md` には参照だけを残した。
