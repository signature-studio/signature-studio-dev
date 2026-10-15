# PY-178 (#3268): setChannelPitch の同期 owner thread id の PE 確定

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3214 (PY-171)・#2576 (PY-77)。

## 結論 (先出し)

- **(1) 同期比較の基準値 `*(0x15e4f18)` の指す dword: 格納位置と初期化 store は確定。** スロット `0x15e4f18` (`.data`) の生値は `0x15e6080` (`.data` に DIR64 再配置あり) で、指す先は `.bss` の VA `0x15e6080` (RVA `0x11e6080`)。この dword への store は PE 全体で **1 件**: `0x41cee9 mov dword ptr [rip+0x11c9191], eax`。直前の `0x41cee4 call 0x406f90` は `jmp [IAT]` で、IAT は `GetCurrentThreadId` (`0x19714f0`)。よって dword の値は **初期化を実行したスレッドの ID**。store は `0x41ce10` (初期化ガード付きの関数。ガードの型は未確定) の中。**未確定**: `0x41ce10` の呼出し元が PE 上に無く、どのスレッドが実行するかは静的に決まらない。
- **(2) `X` (`0x525940()` の戻り値) の `[X+8]` = X を持つスレッド自身の ID。** `[X+8]` の書込みは 2 経路あり、どちらも持ち主 (X を TLS `+0x238` に持つスレッド) の ID になる。(A) `0x525940` が呼出しスレッド T で作る X: `0x525557`〜`0x52556d` で `GetCurrentThreadId()` (T の ID) を書く。(B) worker の TLS に入る X: CreateThread の `lpThreadId` (`&X+8`) が worker の ID を書く。**旧版の『CreateThread の lpThreadId = worker の ID (T 自身ではない)』の読みは誤り** (レビュー B1 の指摘で訂正。`0x525940` が作る X は `[X+0x40]=1` で CreateThread 経路に入らない)。
- **(3) setChannelPitch 呼出しでの同期条件: `ID(T) == dword(0x15e6080)` の 1 つだけ。** `0x526190` が `r8=r9=0` で `0x525ec0` を呼ぶため、`(r8b & r9b)==0` は常に成立し、判定は ID 比較のみ。よって同期が成立するのは、呼出しスレッド T が `0x41ce10` を実行したスレッドと同じ (ID が一致) のときだけ。T は実行時に決まり、PE からは決まらない。

受入条件:

- [x] `*(0x15e4f18)` の指す dword の初期化 store を PE で確定 (`0x41cee9`・値は `GetCurrentThreadId`)。実行スレッド (`0x41ce10` の呼出し元) は未確定 → 未解決表 1。
- [x] X (`0x525940`) の `[X+8]` の設定元を確定: (A) `0x525557`〜`0x52556d` (GetCurrentThreadId)、(B) CreateThread の `lpThreadId` (`0x5254eb`・`[X+0x40]==0` の X だけ)。
- [x] setChannelPitch 呼出しで同期条件の入力がどう決まるかを記述 (3 の通り)。実行時にどのスレッドが呼ぶかは未解決表 4。

## 測定

- 測定 commit: `e4cc24cd4` (probe に到達条件の検査を足した commit。コードを変えた最後の commit)。`git diff e4cc24cd4 HEAD -- tools/python/analysis/flapi/pe_owner_thread_probe.py tools/python/analysis/flapi/pe_disasm.py tools/python/analysis/flapi/pe_xref.py tools/python/analysis/flapi/pe_callgraph.py tools/python/analysis/flapi/pe_scan_store.py` の出力は 0 行。後続の差分は本 REPORT の文書と main 取り込みの merge (`tools/python/analysis` に main の新規ファイル `py86_*.py`・`pe_chain_stores.py`・`pe_launchmap_entries.py` が増えただけ) で、測定に使ったファイルは変わっていない。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` の `extracted/block00031_PE.bin` を repo 外 `${RUNNER_TEMP}/fl-win64` に展開 (2.9 秒・終了 0)。依存 `pefile 2024.8.26`・`capstone 5.0.7` は実在を確認。
- 使用ツール: `pe_owner_thread_probe.py` (本測定)。逆アセの独立確認は capstone の範囲指定ダンプ (repo 外のスクラッチ)。
- 再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_owner_thread_probe.py` (約 65 秒・`RESULT: PASS`・終了 0)。

## 1. 同期比較 `0x525ec0` の入力

- `0x525ec0` の同期判定 (`0x525ee9` の hook 分岐の後): `0x525f3d call 0x525940` → `0x525f42 mov rcx,[rip+0x10befcf]` (= `*(0x15e4f18)`) → `0x525f49 mov eax,[rax+8]` → `0x525f4c cmp eax,[rcx]` → `0x525f4e jne 0x525faf`。`0x525f50`〜`0x525f5e` で `(r8b & r9b)==0` を見て、成立時は `0x525f60`〜`0x525f7d` で `[task+8]` があれば `call [task+8]`、無ければ `[task+0x18]` を呼ぶ (同期実行)。不成立は `0x525faf` 以降の待ち行列経路 (未読)。
- 呼出し元 `0x526190` (`0x5261d6 xor r8,r8`・`0x5261d9 xor r9,r9`・`0x5261dc call 0x525ec0`。rdx = item `[rbp+0x30]`、item は `0x525380` で {owner=this, fn・ctx} を作る) で r8=r9=0 を確認。
- `0x525ee9`: `cmp qword [rip+0x10cc767],0` が非 0 のとき `0x525940` と `[rbx+0x18]` の間接 call を行う (観測用の分岐と推定。未読)。

## 2. X と `[X+8]`

### 2.1 X の生成 (`0x525940` → `0x522710` → `0x5252d0` → `0x525400`)

- `0x525940`: `*(0x41d110()+0x238)` が 0 なら `0x52595b mov dl,1`・`0x52595d call 0x522710` で X を作り、`0x53ce10` で登録し、`[TLS+0x238]=X` (`0x525979`)。
- `0x41d110`: `mov rax,gs:[0x58]` で TLS 配列を引き、`[rax + tlsIndex*8]` (`0x41d15a`)。TLS は呼出しスレッドごとに異なる。
- `0x522710`: dl≠0 なので `0x410320` を呼んで X を得る (`0x522733`)。`0x522741 mov byte [X+0x40],1` (= 1)、`[X+0x18]=1` の後、`0x522751 xor edx,edx`・`0x522753 xor r8,r8`・`0x522756 call 0x5252d0` (dl=0・r8=0)。
- `0x5252d0` → `0x525300` で `0x525400(X, dl=0, r8=0, r9=0)`。
- `0x525400`: `0x52544a call 0x40f9e0` (dl=0 では `0x411ea0` だけ。X の `+0x40` は書かない) → `0x525453`〜`0x52545e` が `[X+0x1b]`、`0x52547a` が `[X+0x19]` に書く → **`0x525485 cmp byte [X+0x40],0`・`0x525489 jne 0x525557`**。`[X+0x40]==1` なので jne が成立し、CreateThread 経路 (`0x52548f` 以降) には行かない。

### 2.2 (A) `0x525557`〜`0x52556d`: `[X+8]` = GetCurrentThreadId

- `0x525557 call 0x423460` (= `jmp [IAT]` = GetCurrentThread) → `0x525560 mov [X+0x10],rax` (疑似ハンドル)。
- `0x525564 call 0x423470` (= `jmp [IAT]` = GetCurrentThreadId) → `0x52556d mov dword [X+8],eax`。
- `0x525940` が作る X (dl=1 の経路) は呼出しスレッド T 自身が作り、T の TLS に入る。よって `[X+8]` = ID(T)。

### 2.3 (B) CreateThread 経路: `[X+8]` = worker の ID

- CreateThread 経路は `[X+0x40]==0` のときだけ (`0x525497 je 0x5254d0` は `0x525489` の fall-through 側)。r9=0 側 (`0x5254d0`): `0x5254d4 lea r8,[rip-0x32b]` (→ `0x5251b0`)、`mov dword [rsp+0x20],4`、`0x5254eb lea rax,[rax+8]` → `[rsp+0x28]` (lpThreadId = `&X+8`)、`call 0x412b50` (`0x5254f4`)。r9≠0 側 (`0x5254a1`・flags `0x10004`・`0x5254b8` lpThreadId = `&X+8`) も同じ `0x5251b0` と `&X+8` を使い、引数は X。
- `0x412b50` は薄い wrapper: `0x412b81 call 0x409410` (16 バイトの引数構造 {fn, arg} を確保)、`0x412ba4 lea r8,[rip-0xcb]` (= trampoline `0x412ae0`) を start に使う。`0x412bb9 mov rax,[rsp+0x98]` (呼出し側の 6 番目 = `&X+8`) → `[rsp+0x28]`、`0x412bc6 call 0x406f80`。
- `0x406f80` = `ff 25 ..` の `jmp [0x19713f0]` = **CreateThread** (IAT 照合済み)。CreateThread は lpThreadId に新スレッドの ID を書く → `[X+8]` = その worker の ID。
- worker は trampoline `0x412ae0` 経由で `0x5251b0(X)` を実行し、`0x5251ca mov [TLS+0x238],rcx` で自分の TLS に X を入れる。よって X の持ち主は worker で、`[X+8]` = ID(持ち主)。
- 注意: `0x5252d0` の呼出し元のうち `0x522756` 以外の 33 件は未調査。ただし (B) の結論は呼出し元に依らない。`0x525400` は `[X+0x40]==0` のとき必ず CreateThread へ進み、どちらの r9 側も `&X+8` と X を渡すため。
- **注意 (未確定 2.3)**: `0x412b50` は `[0x13a5060] ≠ 0` のとき (`0x412b66 cmp`・`0x412b76 call [0x13a5060]` の同一 slot) フック関数を呼ぶ。`0x13a5060` の raw 値は 0 (`.data`) だが、PE 内の store 元は未走査。フック設定時は (B) の `[X+8]` が CreateThread の返値とは限らない。(A) は影響を受けない。

### 2.4 X の一覧

- 呼出し: `0x525940` の直接 E8 は 25 件 (21 関数。`pe_callgraph.py callers`)。X は呼出しスレッドごとに 1 つ (`TLS+0x238` が空のときだけ作る)。

## 3. 基準値 dword `0x15e6080` の初期化

- 格納位置: スロット `0x15e4f18` は `.data` (VA `0x15e4f18`、RVA `0x11e4f18`)。生値 `0x15e6080` (DIR64 再配置 `0x11e4f18` あり)。指す先は `.bss` (RVA `0x11e6080`、`.bss` の 0x80 番目)。
- スロットの RIP 参照は 23 件すべて load (`pe_xref.py`)、store 0。スロットは静的初期値のまま。
- dword `0x15e6080` の RIP 参照 (`pe_xref.py 0x15e6080`): **store 1 件**、load 0 件。`0x41cee9 mov dword ptr [rip+0x11c9191], eax`。
- `0x41cee4 call 0x406f90` → `0x406f90` は `jmp [0x19714f0]` = `GetCurrentThreadId` (IAT 照合済み)。値は 0x41ce10 を実行するスレッドの ID。
- `0x41ce10` は初期化ガード (`sub dword [rip+0x11c9c18],1`・`cmp dword [rip+0x11c9c11],-1`。once 型か再入防止かは未確定) を持つ関数。直接 E8 の呼出し元 0 件、RIP 相対の参照 0 件 (`pe_xref.py 0x41ce10`)、`.data`/`.rdata`/`.idata`/`.didata` の絶対ポインタ 0 件。よって呼出し元は間接経路 (E9 jmp・関数ポインタの動的格納) と推定。**未確定**。

## 4. 同期が成立する条件 (受入 3 の詳細)

- 比較の両辺: 左 `[X_T+8]` = ID(T) (2.2・2.3。X_T は T の TLS の X で、その持ち主は T)、右 `[0x15e6080]` = `0x41ce10` を実行したスレッド Q の ID (3)。
- 同期が成立する ⇔ ID(T) == ID(Q) ⇔ T == Q (生存中のスレッド ID は一意)。`r8=r9=0` なので `0x525f58` の test は必ず 0 (成立) で、判定は ID 比較のみ。
- **訂正**: 旧版の『T に紐づく worker の ID との比較。T が X の worker 自身なら一致しうる』の読みは誤り。worker かどうかに関わらず、X_T の持ち主は T なので `[X_T+8]` = ID(T)。
- `setChannelPitch` の経路 (`0xd5a720` callback・`0xd843d0` task 生成) は ID 比較の入力に触れない。入力は呼出しスレッドの TLS だけで決まる。**未確認**: `setChannelPitch` から `0xd843d0` への呼出し (レビュー m2。`0xd843d0` → `0x526190` は確認済み)。未解決表 5。
- 不成立時 (T ≠ Q) の挙動 (`0x525faf` 以降) は未読 → 未解決表 3。

## 5. 再現スクリプト

`analysis/flapi/pe_owner_thread_probe.py` (追加)。確認の内訳:

| 確認 | 期待 | 結果 |
|---|---|---|
| (i) `0x525f42`〜`0x525f4c` の比較 3 命令・`0x525f58` の test | 一致 | OK 4 件 |
| (ii) `0x52595b` mov dl,1 → `0x52595d` call `0x522710`・`0x522741` `[X+0x40]=1`・`0x522756` call `0x5252d0` (dl=0・r8=0) | 一致 | OK 3 件 |
| (iii) `0x525485` cmp `[X+0x40]`・`0x525489` jne → `0x525557`・`0x525497` je `0x5254d0` (CreateThread は fall-through 側だけ) | 一致 | OK 3 件 |
| (iv) `0x525557` call GetCurrentThread・`0x525560` `[X+0x10]`・`0x525564` call GetCurrentThreadId・`0x52556d` `[X+8]` の store | 一致 | OK 4 件 |
| (v) `0x5254b8` lea (&X+8)・`0x5254c1` call `0x412b50`・`0x412bc6` call `0x406f80` = CreateThread・`0x5251ca` TLS = X | 一致 | OK 5 件 |
| (vi) スロット RIP 参照 load 23・store 0、生値 `0x15e6080` | 一致 | OK 2 件 |
| (vii) `0x15e6080` への dword store 1 件 (`0x41cee9`)・直前 call `0x406f90` (GetCurrentThreadId) | 一致 | OK 3 件 |

結果: HEAD `e4cc24cd4` で `RESULT: PASS`・終了 0 (全 24 件 OK)。

ネガティブコントロール (期待値を実測と違えて FAIL することを確認。両方とも終了 1):

- `--expect-jne-target 0x5254d0` (旧版の読み: `0x525489` が CreateThread 経路へ飛ぶ) → `FAIL 0x525489 jne → 0x525557 (期待 0x5254d0)`・`RESULT: FAIL (1)`。
- `--expect-owner-stores 2` (store 件数の期待を変える) → `FAIL 0x15e6080 への dword store が 1 件 (期待 2)`・`RESULT: FAIL (1)`。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. `0x41ce10` の呼出し元 (E8 0・RIP 0・絶対ポインタ 0。E9 jmp と関数ポインタ経路は未検査) → どのスレッドが `0x15e6080` を書くか | 同期が成立するスレッドを静的に決められない (受入 1 の「値の意味」) | 親 #3214 へ差し戻し・PM 判断 |
| 2. `[0x13a5060]` (`0x412b50` のフック関数ポインタ) の store 元 | フック設定時に (B) の `[X+8]` が CreateThread の返値でなくなる可能性。(A) は影響を受けない | 親 #3214 へ差し戻し |
| 3. `0x525faf` 以降の待ち行列経路 (不成立時の処理) と `0x5251b0` の `ResumeThread` 箇所 | worker の開始時点と不成立時の挙動 | 親 #3214 へ差し戻し |
| 4. 実行時に setChannelPitch を呼ぶスレッド (Python host 側) の同一性 | 同期するかどうかの実行時結果 | PM 判断 (実行時観測) |
