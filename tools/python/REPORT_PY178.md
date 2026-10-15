# PY-178 (#3268): setChannelPitch の同期 owner thread id の PE 確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3214 (PY-171)・#2576 (PY-77)。

## 結論 (先出し)

- **(1) 同期比較の基準値 `*(0x15e4f18)` の指す dword: 格納位置と初期化 store は確定。** スロット `0x15e4f18` (`.data`) の生値は `0x15e6080` (`.data` に DIR64 再配置あり) で、指す先は `.bss` の VA `0x15e6080` (RVA `0x11e6080`)。この dword への store は PE 全体で **1 件**: `0x41cee9 mov dword ptr [rip+0x11c9191], eax`。直前の `0x41cee4 call 0x406f90` は `jmp [IAT]` で、IAT は `GetCurrentThreadId` (`0x19714f0`)。よって dword の値は **初期化を実行したスレッドの ID**。store は `0x41ce10` (once ガード付きの初期化関数) の中。**未確定**: `0x41ce10` の呼出し元が PE 上に無く (E8 直接 call 0 件・RIP 相対参照 0 件・絶対ポインタ 0 件)、どのスレッドが実行するかは静的に決まらない。
- **(2) `X` (`0x525940()` の戻り値) の `[X+8]`: CreateThread の `lpThreadId` (作られた worker スレッドの ID) で、呼出し元スレッドの ID ではない。** `[X+8]` は `0x5254eb`/`0x5254b8` の `lea rax,[rax+8]` で取った `&X+8` を 6 番目の引数として `0x412b50` (CreateThread wrapper) に渡して書かれる。`0x412bc6 call 0x406f80` は `jmp [IAT]` = `CreateThread`。スレッド関数は `0x5251b0` で、引数は X。worker は起動時に自スレッドの TLS `+0x238` に X を入れる (`0x5251ca`)。
- **(3) setChannelPitch 呼出しでの同期入力: 静的に決まるのは「比較式」だけで、入力値は呼出しスレッドの TLS で決まる。** `0xd843d0` → `0x526190` (item = {owner=this, fn=`0xd84290`, ctx=task}) → `0x525ec0(sched, &item, r8=0, r9=0)`。`r8=r9=0` なので `(r8b & r9b)==0` は常に成立し、同期条件は `[X_T+8] == dword(0x15e6080)` の 1 つだけ。`X_T = *(TLS_T+0x238)` は呼出しスレッド T の X で、T 自身の ID ではなく **T に紐づく worker の ID** との比較になる。T が X の worker 自身なら一致しうる。どのスレッドが呼出すかは実行時の値で、PE からは決まらない。

受入条件:

- [x] `*(0x15e4f18)` の指す dword の初期化 store を PE で確定 (`0x41cee9`・値は `GetCurrentThreadId`)。実行スレッド (`0x41ce10` の呼出し元) は未確定 → 未解決表 1。
- [x] X (`0x525940`) の `[X+8]` の設定元を確定 (`0x525400` → CreateThread の `lpThreadId`)。フック分岐の注意は下の 2.2。
- [x] setChannelPitch 呼出しで同期条件の入力がどう決まるかを記述 (3 の通り)。実行時にどのスレッドが呼ぶかは未解決表 4。

## 測定

- 測定 commit: `cf29660` (`origin/main` 起点の worktree `ws-3268` の HEAD。解析ツール `tools/python/analysis` は本 issue の変更前。`git diff cf29660 HEAD -- tools/python/analysis` の出力は 0 行 (計測後に commit するのは `pe_owner_thread_probe.py` 1 件のみ))。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) の `extracted/block00031_PE.bin` を repo 外 `${RUNNER_TEMP}/fl-win64` に展開 (2.8 秒・終了 0)。依存 `pefile 2024.8.26`・`capstone 5.0.7` は実在を確認。
- 所要: 開始 00:35:09 UTC → 終了 (本 REPORT 最終 commit 時) 約 00:55 UTC 程度。load average (1 分値): 開始 0.34 (00:35)、probe 実行前後 0.41〜0.91 (00:44〜00:46)。
- 使用ツール: `pe_disasm.py` (逆アセ)・`pe_xref.py` (RIP 参照の全走査 3 回、各 62 秒)・`pe_callgraph.py callers` (直接 E8 の呼出し元)。すべて終了 0。ツールの不具合は見つからなかった。
- 再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_owner_thread_probe.py` (約 64 秒・RESULT: PASS・終了 0)。

## 1. 同期比較 `0x525ec0` の入力 (受入 2・3 の前提)

- `0x525ec0` の同期判定 (`0x525ee9` の hook 分岐の後): `0x525f3d call 0x525940` → `0x525f42 mov rcx,[rip+0x10befcf]` (= `*(0x15e4f18)`) → `0x525f49 mov eax,[rax+8]` → `0x525f4c cmp eax,[rcx]` → `0x525f4e jne 0x525faf`。`0x525f50`〜`0x525f5e` で `(r8b & r9b)==0` を見て、成立時は `0x525f60`〜`0x525f7d` で `[task+8]` があれば `call [task+8]`、無ければ `[task+0x18]` を呼ぶ (同期実行)。不成立は `0x525faf` 以降の待ち行列経路 (未読)。
- `0x525ee9`: `cmp qword [rip+0x10cc767],0` が非 0 のとき `0x525940` と `[rbx+0x18]` の間接 call を行う (観測用の分岐と推定。未読)。

## 2. X と `[X+8]`

### 2.1 X の生成 (`0x525940` → `0x522710` → `0x5252d0` → `0x525400`)

- `0x525940`: `*(0x41d110()+0x238)` が 0 なら `0x522710` で X を作り、`0x53ce10` で登録し、`[TLS+0x238]=X` (`0x52594a`〜`0x525979`)。
- `0x41d110`: `mov rax,gs:[0x58]` で TLS 配列を引き、`[rax + tlsIndex*8]` (`0x41d15a`)。TLS は呼出しスレッドごとに異なる (フラグが立つ別経路 `0x41cf60` は未読。TLS 経路は `0x41d11b` の `je` で既定の分岐)。
- `0x522710`: 新規 X のフィールド初期化 (`[X+0x40]=1`・`[X+0x18]=1`) の後、`0x5252d0(X, 0, 0)`。
- `0x5252d0` → `0x525400(X, dl=0, r8=0, r9=0)`。`0x525400` のフラグ分岐 (r9 の有無) のうち、`0x525940` 経路の **r9=0 側** (`0x5254d0`): `0x5254d4 lea r8,[rip-0x32b]` (→ `0x5251b0`)、`mov dword [rsp+0x20],4` (`CREATE_SUSPENDED`)、`0x5254e7 lea rax,[rax+8]` → `[rsp+0x28]` (lpThreadId = `&X+8`)、`call 0x412b50` (`0x5254f4`)。`[X+0x10] = 戻り値 (ハンドル)` (`0x5254f9`〜`0x5254fd`)。r9≠0 側 (`0x5254a1`・flags `0x10004`) も同じ `0x5251b0` と `&X+8` を使う。

### 2.2 `[X+8]` の書込み (`0x412b50` → `0x406f80` → CreateThread)

- `0x412b50` は薄い wrapper: `0x412b81 call 0x409410` (16 バイトの引数構造 {fn, arg} を確保 → `[r13]=rsi`・`[r13+8]=rdi`)、`0x412ba4 lea r8,[rip-0xcb]` (= trampoline `0x412ae0`) を CreateThread の start に使う。`0x412bb9 mov rax,[rsp+0x98]` (呼出し側の 6 番目 = `&X+8`) → `[rsp+0x28]`、`0x412bc6 call 0x406f80`。
- `0x406f80` = `ff 25 ..` の `jmp [0x19713f0]` = **CreateThread** (IAT 照合済み)。CreateThread は lpThreadId に新スレッドの ID を書く → `[X+8]` = worker の ID。
- trampoline `0x412ae0` が `[r13]` の fn (= `0x5251b0`) を arg (= X) で呼ぶ。`0x5251b0` は `call 0x41d110` (その worker 自身の TLS) → `0x5251ca mov [rax+0x238],rcx` で `TLS+0x238 = X`。以後 `0x524de0`・`0x412bf0` 等で走る。
- **注意 (未確定 2.2)**: `0x412b50` は `[0x13a5060] ≠ 0` のとき (`0x412b66 cmp`・`0x412b76 call [0x13a5060]` の同一 slot) フック関数を呼ぶ。`0x13a5060` の raw 値は 0 (`.data`) だが、PE 内の store 元は本 run で未走査。フック設定時は `[X+8]` が CreateThread の返値とは限らない。

### 2.3 X の一覧

- 呼出し: `0x525940` の直接 E8 は 25 件 (21 関数。`pe_callgraph.py callers`)。X は呼出しスレッドごとに 1 つ (`TLS+0x238` が空のときだけ作る)。

## 3. 基準値 dword `0x15e6080` の初期化

- 格納位置: スロット `0x15e4f18` は `.data` (VA `0x15e4f18`、RVA `0x11e4f18`)。生値 `0x15e6080` (DIR64 再配置 `0x11e4f18` あり)。指す先は `.bss` (RVA `0x11e6080`、`.bss` の 0x80 番目)。
- スロットの RIP 参照は 23 件すべて load (`pe_xref.py`)、store 0。スロットは静的初期値のまま。
- dword `0x15e6080` の RIP 参照 (`pe_xref.py 0x15e6080`): **store 1 件**、load 0 件。`0x41cee9 mov dword ptr [rip+0x11c9191], eax`。
- `0x41cee4 call 0x406f90` → `0x406f90` は `jmp [0x19714f0]` = `GetCurrentThreadId` (IAT 照合済み)。値は 0x41ce10 を実行するスレッドの ID。
- `0x41ce10` は once ガード (`sub dword [rip+0x11c9c18],1`・`cmp dword [rip+0x11c9c11],-1`) を持つ初期化関数。直接 E8 の呼出し元 0 件、RIP 相対の参照 0 件 (`pe_xref.py 0x41ce10`)、`.data`/`.rdata`/`.idata`/`.didata` の絶対ポインタ 0 件。よって呼出し元は間接経路 (E9 jmp・関数ポインタの動的格納) と推定。**未確定**。

## 4. 同期が成立する条件 (受入 3 の詳細)

- 比較の両辺: 左 `[X_T+8]` = T に紐づく worker の ID (2.2)、右 `[0x15e6080]` = 0x41ce10 を実行したスレッドの ID (3)。
- 成立ケース (PE から分かる範囲): (a) 呼出し T が X_T の worker 自身で、その worker が 0x41ce10 を実行したスレッド、(b) 0x41ce10 の実行スレッドが、T が `0x525940` で作らせた worker と一致する場合。どちらも実行時のスレッド対応で決まる。
- `r8=r9=0` (`0x526190` の呼出し) なので、`0x525f58` の `test` は必ず 0 (成立)。判定は ID 比較のみ。
- `setChannelPitch` の経路 (`0xd5a720` callback・`0xd843d0` task 生成) は ID 比較の入力に触れない。入力は呼出しスレッドの TLS だけで決まる。

## 5. 再現スクリプト

`analysis/flapi/pe_owner_thread_probe.py` (追加)。

| 確認 | 期待 | 結果 |
|---|---|---|
| (i) `0x525f42`〜`0x525f4c` の比較 3 命令・`0x525f58` の test | 一致 | OK 4 件 |
| (ii) `0x5254b8` lea・`0x5254c1` call `0x412b50`・`0x412bc6` call `0x406f80`・`0x406f80`→CreateThread・`0x5251ca` 格納 | 一致 | OK 5 件 |
| (iv) スロット RIP 参照 load 23・store 0、生値 `0x15e6080` | 一致 | OK 2 件 |
| (v) `0x15e6080` への dword store 1 件 (`0x41cee9`)・直前 call `0x406f90` (GetCurrentThreadId) | 一致 | OK 3 件 |

ネガティブコントロール: `--expect-owner-stores 2` (期待を実測と違う 2 件に変更) → `FAIL 0x15e6080 への dword store が 1 件 (期待 2)`、`RESULT: FAIL (1)`、終了 1 (確認済み)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. `0x41ce10` の呼出し元 (E8 0・RIP 0・絶対ポインタ 0。E9 jmp と関数ポインタ経路は未検査) → どのスレッドが `0x15e6080` を書くか | 同期が成立するスレッドが静的に決まらない (受入 1 の「値の意味」) | 親 #3214 へ差し戻し・PM 判断 |
| 2. `[0x13a5060]` (`0x412b50` のフック関数ポインタ) の store 元 | フック設定時に `[X+8]` が CreateThread の返値でなくなる可能性 | 親 #3214 へ差し戻し |
| 3. `0x525faf` 以降の待ち行列経路 (不成立時の処理) と `0x5251b0` の `ResumeThread` 箇所 | worker の開始時点と不成立時の挙動 | 親 #3214 へ差し戻し |
| 4. 実行時に setChannelPitch を呼ぶスレッド (Python host 側) の同一性 | 同期するかどうかの実行時結果 | PM 判断 (実行時観測) |
