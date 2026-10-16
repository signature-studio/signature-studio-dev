# REPORT 付録 (#4917 KH-135): Delay の残り 6 件のうち `FUN_180fb5dd0` 2 件を規則化 (部分)

親 #4883 の残件 6 件 (`FUN_180fb5dd0` 2・`FUN_180fd5bf4` 2・`FUN_180fd8988` 2) のうち、今 run は `FUN_180fb5dd0` の 2 件だけを確定して規則化した。残る 4 件は未確定で、PR 本文の未解決表と #4917 本文のチェックリストに書く。

**結論**: `ABI['delay']` に規則 2 件を追加 (件数 1 を assert・通過)。測定 commit `74cee7ec5` で Delay の emcc error は **312** (引数数不一致 **63**)。origin/main (`e5261de58`) は 314 (引数数不一致 65)。Gain / Haas / Gate の生成 C と sigs.json は origin/main と cmp 0 差分。

**測定 commit**: `74cee7ec5` (`ghidra_route` を変える最後の commit)。
**比較対象**: `e5261de58` (origin/main)。同じ素材 (`HeartCore.core_64` 76,642,304 B)・同じ Ghidra 12.1.4・同じ emcc で測定。
**差分**: `git diff e5261de58 74cee7ec5 -- tools/targets/kilohearts/ghidra_route` = `patches.py` 5 行追加・`callsite_disasm.py` 新規 28 行 (逆アセンブル用の道具)。

## 規則 2 件 (`patches.py` の `ABI['delay']`)

| 呼出元 (VA・C 行) | 呼出先 | 機械語の根拠 |
|---|---|---|
| `FUN_180fb5f3c` (2535) | `FUN_180fb5dd0` 5 引数 (0) → 0 引数 | 180fb5f40〜180fb5f50: `[rsp+0x20]`・r9・r8・rdx・rcx を 0 にしてから `call 180fb5dd0` |
| `FUN_180fb5f5c` (2546) | `FUN_180fb5dd0` 5 引数 (0) → 0 引数 | 180fb5f60〜180fb5f70: 同上 |

callee の宣言は既に `void FUN_180fb5dd0(void)`。

**`REPORT_APPENDIX_4883.md` との関係 (再判定)**: 4883 は「callee 本体が `[rbp+0x30]` (= 呼出側 `[rsp+0x20]`) を読むので、引数を落とすと意味が変わる」として規則化を見送った。この記述は callee 側の事実として今も正しい。本付録が決めたのは別の点である。両呼出元が `[rsp+0x20]` に置く値は 0 で、宣言 `void (void)` に合わせて呼出側の引数を 0 件にしても、呼出側の規則としては矛盾しない。したがって 4883 の見送りは撤回しない。見送りの理由は、呼出側の値が未確定だったことだった。4917 でそれを確定し、呼出側の規則だけを入れた。

**本付録が言えないこと**: 規則は呼出側の 2 件だけを扱う。callee 本体の `[rbp+0x30]` 読出しは生成 C の本体に出ていない (Ghidra 出力から落ちている)。このため、生成 C の本体が `FUN_180fb5e6c` に渡す値は、機械語の意味と一致しているとは確認できていない。これは silent miscompile の疑いで、呼出側の規則では直らない。追跡は #5829 (KH-176)。

**根拠の出典と確度**: 両呼出元の `[rsp+0x20]` = 0 は、前 run の逆アセンブル (上の表の VA 範囲) の読みである。本 run では `plugins-kilohearts` が runner に無く (`$ARTIFACTS_DIR` に `fl-win64` のみ)、機械語を再実行していない。実行による突合は未実施 (Delay 全体は emcc が通らず、wasm として動かせない)。

**既存の欠陥類型との照合 (`docs/DEFECTS.md`)**: callee 本体の読出し欠落に当てはまる類型は確認できなかった。近いのは D4 (メモリ load の脱落) だが、D4 は disp=0 の引数レジスタ経由の deref 脱落で、本件は `[rbp+0x30]` のスタック読出しである。同型とは断定できないため、類型は未確定とし、#5829 で切り分ける。


## 残件 4 件 (未確定・次の run)

| callee | 呼出元 (C 行) | 状態 |
|---|---|---|
| `FUN_180fd5bf4` 2 件 (5512・5656) | `FUN_180fd5f04` (5656 の呼出し元 C 本体は引数 0)・`FUN_180fd5bcc` (5512) | 呼出元の機械語を読んだ: `FUN_180fd5bcc` は `[rsp+0x70]`・`[rsp+0x78]` (= さらに上位の呼出側が積んだ値) を `[rsp+0x20]`・`[rsp+0x28]` に写す。`FUN_180fd5f04` は `[rsp+0x78]`・`[rsp+0x70]` を同じく写し、`[rsp+0x30]` = 1。C 側は両者とも引数 0 で、この stack 値の源 (上位の呼出元) の C 宣言が未確定 |
| `FUN_180fd8988` 2 件 (6047・6100) | `FUN_180fd8aac`・`FUN_180fd8bd4` | 未着手。`FUN_180fd8aac` の関数境界が外れている (#4883 本文の注) ため、呼出元の範囲を先に確定する |

## 件数の推移 (Delay)

| commit | error | 引数数不一致 | 出典 |
|---|---|---|---|
| `e5261de58` (origin/main) | 314 | 65 | 本付録の測定 |
| `74cee7ec5` (本 PR) | 312 | 63 | 本付録の測定 |

残りの引数数不一致 63 件の内訳 (`FUN_180fd5bf4` 2・`FUN_180fd8988` 2 を含む) は、前 run の分類 (REPORT_APPENDIX_4883.md) と突き合わせて次 run で集計し直す。

## 測定の手順 (再現用)

1. `plugins-kilohearts` を `$RUNNER_TEMP` に展開し、`KH_SRC` で `extract_installer.sh` の入力にして `work/winpkg/HeartCore.core_64` を作る (実測 28 秒)。
2. Ghidra 12.1.4 を `m11_ghidra_dll.sh` と同じ zip・sha256 で取得して展開。
3. `closure.py delay` (実測 22.7 秒・139 関数・FAIL 0) → `ghidra_to_c.py delay --fix bitcast,intload,stackpair,assoc,concat` → `emcc -c -ferror-limit=0`。HEAD の生成 + emcc は実測 9.5 秒。
4. Gain / Haas / Gate は `closure.py` → `ghidra_to_c.py` の生成 C と sigs.json を origin/main と `cmp`。全件 0 差分。
5. 逆アセンブルは `ghidra_route/callsite_disasm.py <core> <start> <end>` (capstone)。

素材: `plugins-kilohearts`・`toolchain-emsdk` (R2 素材。`docs/REFERENCES.md` の `[EMSDK]` 等で参照)。`fl-win64` は本 PR の測定では使っていない。
