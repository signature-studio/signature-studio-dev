# tools/plugins/f2 REPORT_1305 — PLG-F3-7 (#1305): waiver 4 site の間接 call 23 件の解決と例外到達の判定

- 測定 commit: **892a5c7d** (f2 の `.py` 3 本を初めて追加した commit)。f2790047 には `raise_root_reach.py`・`indirect_resolve.py` が無いため、数値はこの commit 以降でのみ出せる。HEAD 以降の差分は REPORT_1305.md のみ (§6)。
- 既知類型との関係: (DEFECTS.md) 該当なし。W の間接 call は icall_gate で被覆済み (icall §4 D1 の対象外)。waiver の対象は (icall §4) D12 landing pad (#529 §7.7)。新規類型なし。
- 担当 dir: `tools/plugins/f2/` のみ。生成物は `tools/plugins/work/f2/` (gitignore)。
- 範囲: 静的解析のみ。DSP 実行・native 実行による到達の実測は範囲外。

## 0. 結論 (先出し)

1. 間接 call 23 件 (19148・19245 とも同一構成) のうち、**3 件が `kernel32!RaiseException` の thunk を格納する slot 経由で例外送出 API に解決**された。残る 20 件は未解決 (内訳 §1)。
2. waiver の 4 root (`0x780d00`・`0x78a660`・`0x77a550`・`0x783eb0`) は、いずれも **D12 pad 範囲内の `call 0x411070`** から `0x410220` を経て RaiseException に届く (直接 call のみの最短経路長 3)。
3. pad 範囲内の経路は fallthrough では入らない (pad 直前の `jmp` が飛び越す) が、pad が実行されれば先頭の `call 0x41bf60` (戻り値を `[rax+0x208]` で逆参照) → `0x410220` (フラグ分岐付き) → `0x410ef0` (分岐に関わらず `0x411017` で RaiseException) の順に進む。**`0x41bf60` が有効なポインタを返す前提で、pad 実行時は必ず例外 API に届く**。その前提と `0x41bf60` 内の未解析部分 (§3) は未証明。`0x410ef0` 内の `call [0x8bf040]` (関数ポインタ) の戻らない可能性も未解析。pad が DSP 実行で実行されないことも未証明。waiver の reason の未検証箇所は残る。
4. **受入条件 2 (waiver 削除または reason 更新) は未達**。本 PR では waiver を変更しない。判断は #529 に委ねる (§3)。

## 1. 測定 (測定 commit 892a5c7d)

| 項目 | 19148 | 19245 |
|---|--:|--:|
| waiver root (`icall_gate_waivers.json`) | 2 | 2 |
| 直接 call BFS の到達関数 (`raise_reach_frontier.py`) | 31 | 31 |
| 間接 call site | 23 | 23 |
| 直接 call の .pdata 範囲外先 | 1 (0x407190) | 1 (0x407190) |
| raise_reach_frontier の raise_api | 1 (0x411bdd `ExitProcess`、`0x411a80` 内) | 同左 |

`indirect_resolve.py` の `classification` (19148 実測、`work/f2/indirect_resolve_19148.json`):

| 分類 | 件数 | 意味 |
|---|--:|---|
| raise_via_slot | 3 | slot の store 値が `kernel32!RaiseException` の thunk (0x406f80) |
| slot_no_store | 5 | `[rip+slot]` だが、ファイル上 0 かつ PE 内に store が無い (実行時に格納 / 別経路) |
| object_or_register_based | 15 | `[rbx-0x20]`・`[rbx+8]`・`call rbx` 等、レジスタ経由。vtable 解決が要る |

- raise_via_slot の 3 件: 0x410ffa 系ではなく `0x411017` (`call [0x8bf030]`)・`0x410354`・`0x41023a`。slot `0x8bf030` は store 2 箇所 (`0x4113c4`・`0x41bcae`) で同じ thunk を格納。
- 19245 は slot が `0x8aa030` にずれるのみで、構成は同一。

## 2. 例外経路の判定 (`raise_root_reach.py`、19148 / 19245)

- raise 関数 (RaiseException を IAT 直接または raise slot 経由で呼ぶ関数): 7 本 (`0x410220`・`0x410250`・`0x410290`・`0x410300`・`0x410330`・`0x410360`・`0x410ef0`)。
- 各 root から直接 call で届く最短経路 (19148 / 19245 で同一構造):
  - `0x780d00` → `0x411070` (call@0x780d90) → `0x410220` (call@0x411098)
  - `0x78a660` → `0x411070` (call@0x78a733) → `0x410220` (call@0x411098)
  - `0x77a550` → `0x411070` (call@0x77a5e0) → `0x410220` (call@0x411098)
  - `0x783eb0` → `0x411070` (call@0x783f83) → `0x410220` (call@0x411098)
- 4 つの `call 0x411070` はいずれも D12 pad の範囲内 (19148: [0x780d6a,0x780d96)・[0x78a70d,0x78a739)、19245: [0x77a5ba,0x77a5e6)・[0x783f5d,0x783f89))。
  - pad 直前の制御移動 (fallthrough を飛び越す `jmp`): 19148 は `0x780d66: jmp 0x780d96` (0x780d6a の pad の直前)・`0x78a709: jmp 0x78a739` (0x78a70d の pad の直前)。19245 は `0x77a5b6: jmp 0x77a5e6`・`0x783f59: jmp 0x783f89`。19148 では pad 先頭 (0x780d6a・0x78a70d) を直接 jmp/call する命令が PE 内に 0 件 (objdump 全走査)。pad へ別経路で入る可能性は未証明 (§3)。
- `0x411070` (19148、pdata 境界 [0x411070,0x4110b2)) は先頭で `call 0x41bf60` (0x411076) を呼び、戻り値を `mov rax,[rax+0x208]` で逆参照して `[rax+0x10]` に 0 を書いてから、`call 0x410220` (0x411098) の後、**分岐なしで** `call 0x410ef0` (0x4110a6) を呼ぶ。つまり pad が実行されれば両経路を通る。
  - 前段 `0x41bf60`: `cmp byte [0x8c52d8],0` で分岐する。非 0 側は `call 0x41bdb0` (引数 `[0x86b100]`) の戻りが非 0 なら返し、0 なら `call 0x41be50` → `call 0x41bdb0` を試し、なお 0 なら `[0x8c52d0]` を返す。0 側は `gs:0x58` (TLS) の `[rcx*8]` (`rcx=[0x86b100]`) を返す。`0x41bdb0`・`0x41be50` の中身は未解析。返り値が 0 だと `[rax+0x208]` の逆参照は access violation となり RaiseException に届かない。
  - 経路 A: `0x410220` (pdata 境界 [0x410220,0x410245)) は `cmp byte [0x867058],1; jbe 0x410240` で囲まれ、ファイル上の初期値 0 では RaiseException (`call [0x8bf030]`・0x41023a) を飛ばす。値が 2 以上なら実行する。
  - 経路 B: `0x410ef0` (pdata 境界 [0x410ef0,0x411029)) の 0x410f63 で `cmp qword [0x8bf040],0; je 0x411000` と `test dil,dil; jne 0x411000` の 2 分岐がある。両方とも不成立 (`[0x8bf040]!=0` かつ `dil==0`) のとき fallthrough で `0x410f7a` に入り、`0x410ffa` で `call qword [0x8bf040]` を実行してから `0x411000` に落ちる。どの経路でも `0x411000` に届き、`0x411017` で `call [0x8bf030]` (RaiseException の slot) を実行する。`0x410ef0` の直接 call は `0x410f0e` (`call 0x411c30`、rbx==0 のときのみ)・`0x410ffa` (`call [0x8bf040]`)・`0x411017` (`call [0x8bf030]`) の 3 つだけ。
  - 結論: `0x41bf60` が有効なポインタを返す前提で、pad 実行時は**必ず例外 API に届く**。その前提は未証明。経路 A の分岐は pad の安全性の根拠にならない。未解析: (0) `0x41bf60` の戻り値 (§3)、(a) `call [0x8bf040]` (0x410ffa) が戻らない・途中で脱出する可能性 (指す関数の中身は未解析)、(b) `0x411c30` (rbx==0 のとき) の中身。いずれも途中で脱出すれば経路 B の RaiseException に届かない可能性がある。
- フラグ `0x867058` (経路 A の分岐変数) と関数ポインタ `0x8bf040` (経路 B で null 判定したうえで `call qword [0x8bf040]` する先) への rip 相対の直接書込みは、19148 の .pdata 関数単位の逆アセンブル走査で 0 件。これは**ファイル上の初期値 0 の下では経路 A が実行されない**ことを示すのみで、実行時に外部から書かれる可能性 (間接書込み・他 DLL 経由) は PE 内の直接書込み 0 件では否定できない。
- `0x411070` は PE 内の 745 関数から呼ばれる共通関数 (19148)。W 固有ではない。数え方: `.pdata` の RUNTIME_FUNCTION 範囲 (17543 関数) のうち、その範囲内に `call 0x411070` (直接 call のみ・objdump 全走査で 759 箇所、すべて pdata 範囲内) を持つ関数の数。19245 は 740 関数 (754 箇所)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pad 範囲に入る経路が DSP 実行で起きないこと (= 例外が DSP 内で送出されないこと) は未証明 | 起きれば `0x411070` → `0x410220`/`0x410ef0` → RaiseException。waiver の前提が崩れる (silent miscompile の可能性) | #529 (waiver 4 site の親)。本 PR は Refs #1305 |
| 間接 call 残り 20 件 (レジスタ経由 15・実行時 slot 等 5) の呼出し先 | 例外 API か未確定 | #1305 (本 issue。残件はこの issue で追跡し、解決後に reason を更新) |
| `indirect_resolve.py` の slot 格納値解析は「関数単位の直前 mov」の 1 段のみ | 2 段以上の間接経由は解決しない | #1305 (同上) |
| `0x410ef0` 内の `call qword [0x8bf040]` (0x410ffa) の戻らない可能性と、その指す関数の中身は未解析 | 途中で脱出すれば経路 B の RaiseException に届かない可能性。pad 実行時の「必ず届く」結論の前提に当たる | #1305 (本 issue) |
| `0x410ef0` 内の `call 0x411c30` (0x410f0e、rbx==0 のとき) の中身は未解析 | 同上 (rbx==0 の経路で脱出しうる) | #1305 (本 issue) |
| `0x411070` 先頭の `call 0x41bf60` (0x411076) の中身は未解析 (`call 0x41bdb0`・`call 0x41be50` を含む) | 戻り値が 0 または不正なポインタだと `[rax+0x208]` の逆参照で例外 API に届かない。「必ず届く」の前提に当たる | #1305 (本 issue) |
| 直接 call の .pdata 範囲外先 0x407190 | RaiseException 判定には影響なし (raise 関数は増えない) | #529 |

## 4. 受入条件の判定

| 受入条件 | 判定 |
|---|---|
| 1. 間接 call 23 件の呼出し先を解決 (不能は理由を REPORT に) | **部分達成**。3 件を RaiseException に解決。残り 20 件は分類と理由を §1 に記載 (未解決) |
| 2. 解決先の例外到達を判定し、waiver を更新/削除 | **部分達成**。到達は判定 (4 root すべて到達、pad 内経由)。waiver の削除・reason 更新は、§3 の未証明が残るため未実施 |
| 3. raise_reach_frontier.py 19148・19245 を再現 | **達成**。visited 31・indirect 23・unresolved 1・raise_api 1 |

## 5. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"     # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst
python3 tools/plugins/f2/raise_reach_frontier.py 19148    # 受入 3
python3 tools/plugins/f2/raise_root_reach.py 19148        # root ごとの例外経路
python3 tools/plugins/f2/indirect_resolve.py 19148        # 間接 call 23 件の分類
```

## 6. 検証の鮮度 (#1268)

- 測定 commit: 892a5c7d (f2 の `.py` 3 本の追加 commit)。
- 再実行 (HEAD、`FL_WIN64_DIR` は block19148/19245 のみ展開): `raise_reach_frontier.py 19148` = visited 31・indirect 23・unresolved 1・raise_api 1 (1.6 秒)、19245 も同値。`raise_root_reach.py` は 2 root ずつ `reaches_raise: true`。`indirect_resolve.py` は raise_via_slot 3 / slot_no_store 5 / object_or_register_based 15 (両 block)。
- `git diff 892a5c7d 6cfbac24 -- tools/plugins/f2/ --stat` の出力: `tools/plugins/f2/REPORT_1305.md | 30 +++++++++++++++++++++--------` / `1 file changed, 22 insertions(+), 8 deletions(-)`。`.py` は不変のため、数値は再測定不要。

## 7. PLG-F3-10 (#1499): 残り間接 call の解決の追加 (測定 commit 8a06cad5)

- 追加した解決段: (1) レジスタの直前代入が `mov reg,[rip+slot]` のとき、その slot を (A) と同じ格納元解析に通す。(2) `no store found` の slot は、その番地が `.data`/`.rdata` の qword として現れる箇所 (`data_ptr_to_slot`) を記録する。
- 測定 (8a06cad5、`FL_WIN64_DIR` は block19148/19245 のみ展開、Python 3.14・pefile・capstone):

| 分類 | 19148 (前) | 19148 (後) | 19245 (後) |
|---|--:|--:|--:|
| raise_via_slot | 3 | 3 | 3 |
| resolved_runtime_store | 0 | 1 | 1 |
| slot_no_store | 5 | 5 | 5 |
| object_or_register_based | 15 | 14 | 14 |

- 解決が増えた 1 件: `0x411a80` の `call rbx` (0x411af9)。`rbx` は `mov rbx,[rip+0x8bf0a0]` (19245 は `0x8aa0a0`) で、この slot の PE 内の格納は `imm 0` の 1 件のみ。よって呼出し先は PE 内の格納からは決まらず、実行時の書込みに依存する。例外 API ではないことは確認できたが、呼出し先の特定はできていない。
- 未解決 (残り 19 件): `slot_no_store` 5 件 (`0x8c3ca8`・`0x8bf068`・`0x8bf048`・`0x8bf3d8`・`0x8bf040`) は全て `.bss` にあり、PE 内の rip 相対参照は 0 件。`data_ptr_to_slot` は `0x8bf040` (`0x8bd2f0` の qword) の 1 件のみで、これは 2 段以上の間接経由なので本ツールの範囲外。`object_or_register_based` 14 件は `[rbx-0x20]`・`[rbx+8]`・`[rbp+0x38]`・`[rax-0x30]`・`jmp [rcx]` 等で、オブジェクトの vtable 参照のため、呼出し先はオブジェクトの型 (実行時値) に依存する。
- 受入条件の判定: 1 (間接 call の解決) **部分達成** (3 件は前回どおり RaiseException、1 件は格納 0 のみ確認、残り 19 件は未解決)。2 (`slot_no_store` の格納元まで辿る) **未達** (`.bss` 5 件は PE 内に格納が無く、「解決不能」の理由は上記)。3 (19245 も同じ判定) **達成** (同一構成)。4 (reason 反映・#529 へ報告) **未達**: 解決の範囲が 3 件 + 1 件の確認で、waiver の reason を書き換える根拠が不足するため、判断材料を本節に残し、waiver は変更しない。
- 再現 (8a06cad5): `python3 tools/plugins/f2/indirect_resolve.py 19148` / `19245` の `classification`、および `python3 tools/plugins/f2/raise_reach_frontier.py 19148` / `19245` (= visited 31・indirect 23・unresolved 1・raise_api 1)。
- 次の段 (未解決の起票先: #1499 の残件として本 issue で追跡): 実行時に slot へ書く経路 (`0x8bd2f0` の参照元の関数表、`0x8bf0a0` の書込み元) を 2 段以上追う解析。これは静的 1 段の範囲を超えるため、別の解析 (動的トレース) が要る。

## 8. PLG-F3-13 (#1656): slot_no_store の 2 段目解析 (部分)

- 道具: `tools/plugins/f2/slot_base_store.py` を追加。`.bss` slot を含むグローバル構造体の base を `lea reg,[rip+base]` で取り (base = slot - 0x100 .. slot)、同じ関数内の `mov [reg+disp], X` (disp = slot - base) の格納元を集める。unicorn は未使用 (導入はしたが、本段は静的で足りた)。
- 測定 (基準 origin/main 1c57d524、19148 と 19245 は同一構成):
  - 19148 `slot_no_store` 5 件: `0x8c3ca8` は base `0x8c3c80` (disp 40) の lea 3 件・同関数内の格納 1 件 (`0x4113f2`: `mov [r13+0x28], rax`、関数 `0x411330`)。`0x8bf3d8` は base `0x8bf3b0` の lea 3 件・格納 0 件。`0x8bf068`・`0x8bf048`・`0x8bf040` は base 候補 0 件。
  - 19245 `slot_no_store` 5 件: `0x8aeca8` (= `0x8c3ca8` と同型、格納 1 件 `0x4113f2`)、`0x8aa3d8` (格納 0 件)、`0x8aa040`・`0x8aa048`・`0x8aa068` は候補 0 件。
- `0x4113f2` の格納値は `rax = [rbx]` (呼出し元が渡すポインタ先の値) で、定数でも関数 VA でもない。格納先 r13 は `[rbp+0x170] < 2` で `0x8c3c80` か `0x8c3da8` に分岐する。よって `0x8c3ca8` の内容は呼出し元の引数で決まり、PE 内の静的解析からは決まらない。
- 判定: 受入条件 1 (slot_no_store の書込み元) は **部分達成**。書込み元 1 件 (`0x411330`) を特定したが、その値は実行時依存のため、呼出し先は未確定。残り 4 件 (`.bss`) は PE 内に格納 0 件で、2 段目でも書込み元なし。解決不能の理由: 格納は PE 外 (実行時の別モジュール・別経路) で行われる可能性が高い。
- 未達 (次の段): `object_or_register_based` 14 件の vtable 型確定 (受入条件 2・3) は未着手。実行時トレース (unicorn で `0x411330` の呼出し経路を再現) が必要で、本 run では時間が足りない。
- 再現: `python3 tools/plugins/f2/indirect_resolve.py 19148` / `19245` (classification は §7 と同じ) と、`python3 tools/plugins/f2/slot_base_store.py 19148 0x8c3ca8 0x8bf068 0x8bf048 0x8bf3d8 0x8bf040`。

## 9. PLG-F3-16 (#1807): 0x411330 の呼出し経路と格納値 (静的確定、19148)

- 測定: 19148 (block19148_PE.bin のみ展開)。`indirect_resolve.py 19148` = visited 31・indirect 23 (9.8 秒、§7 と一致)。
- `0x411330` の直接呼出し元は PE 内に 1 件: `0x41c7d4` (`call 0x411330`、関数 pdata 範囲 [0x41c740,0x41c7e3) 内、chain なし)。`e8`/`e9` の全バイト走査で確認。`qword` としての参照 (関数ポインタ) は 0 件。(旧記載の関数 `0x419860`・範囲 [0x419860,0x41d4df) は誤り。pdata 上で `0x419860` は関数先頭ではなく、`0x41c7d4` を含む entry は上記のみ。)
- 呼出し元の引数: `r9` (= 関数内の `rbx`) は `lea r9,[rip+0x44e9d7]` で `0x86b188` (`.data`) を指す。`r8` は `0x86b128`。`r13d` (7 番目引数、格納先の分岐用) は `0x41c752` の `mov r13d,r9d`。
- `0x411330` 内の格納: `rax = [rbx]` (= `[0x86b188]`) を `0x4113f2` で `[r13+0x28]` に格納する (§8 の `0x4113f2` と同一)。
- `[0x86b188]` の PE 内初期値: `0x41bf30` (関数の先頭。`sub rsp,0x28; lea rax,[0x298]; ...`)。PE 内の rip 相対の参照 (読み書き) は 0 件 (`[rip±d]` の有効アドレス走査)。
- したがって `0x8c3ca8` の格納値は **`[0x86b188]` の実行時値**。PE 内の初期値は `0x41bf30` だが、実行時の書換えは `.text` 内の直接書込み 0 件 (§9 追補) で否定できない (間接書込み・他経路は未証明)。
- 未達 (次の段): (1) `[0x86b188]` が実行時にどの値になるかの確定 (unicorn で `0x41bf30` 呼出し後の値を再現)、(2) `0x8c3ca8` の格納値 → 14 件の `object_or_register_based` の vtable 型確定、(3) 19245 の同判定 (`0x8aeca8`・`0x8aa0a0` 系)、(4) #529 への報告。いずれも実行時再現 (unicorn) が要る。
- 再現 (`slot_base_store.py` と別アルゴリズム = PE を VA 配置の平坦イメージに展開して生バイト走査、逆アセンブル不使用): `python3 tools/plugins/f2/callsite_scan.py <extracted/block19148_PE.bin> 0x411330 0x86b188 0x86b128`。期待出力: `[1] ... 1 件 0x41c7d4`・`[2] qword 参照: 0 件`・`[3] 0x86b188: lea 1 件 0x41c7aa / 読み書き 0 件`・`[3] 0x86b128: lea 2 件 0x41bfc4 0x41c7a3 / 読み書き 0 件`・`[4] ... [0x41c740,0x41c7e3)`・`[5] 0x86b188 の初期値 0x41bf30`。負のコントロール: target `0x411338` で 1 の件数が 0、rip `0x86b189` で lea/rw が 0。`0x8c3ca8` への rip 参照は `0x411ba2` の `call qword ptr [rip+...]` (読み出し) の 1 件のみで、格納 0 件とは矛盾しない。
- 追補 (#1807 2 回目 run、測定 commit は本 PR の commit): `0x86b188` の初期値 `0x41bf30` は、PE の `.reloc` に DIR64 (type 10) の再配置エントリ 1 件 (VA `0x86b188`) として載っており、再配置対象の絶対ポインタ (ロード時に補正される。値は `0x41bf30` の関数 VA)。`.data` のデータ値ではない。
- 入力の出所: `$ARTIFACTS_DIR/fl-win64.tar.zst` の `extracted/block19148_PE.bin` (5,904,384 B) を `tar --zstd -xf <fl-win64.tar.zst> extracted/block19148_PE.bin` で展開して使う (`TMPDIR=$RUNNER_TEMP` 下の scratch に置き、リポジトリには置かない)。
- 走査範囲: `slot_write_scan.py` は `IMAGE_SCN_MEM_EXECUTE` を持つ全セクションを走査する。19148 の実行可能セクションは `.text` のみ (`.data`・`.bss`・`.idata`・`.rdata`・`.reloc`・`.pdata`・`.rsrc` は非実行)。よって「PE 内の rip/abs 直接アクセス」は `.text` 内の直接アクセスと一致する。
- 実測 (block19148 のみ、逐次、`python3 tools/plugins/f2/slot_write_scan.py <block19148_PE.bin> 0x86b180 0x86b190`): 3 回の wall = 18.81 / 18.95 / 19.37 秒 (min–max 18.81–19.37 秒、RSS 約 220 MB、並列数 1、開始時 load average (1 分) 0.76 / 0.83 / 0.88)。
- 結果: `relocs overlapping: 1`・`direct accesses (rip/abs disp), excluding lea: 0`。同じ範囲の rip 相対・絶対 disp アクセスは `lea` を除き 0 件 (書込みも読出しも 0)。
- ネガティブコントロール (同じ検出器、同じ入力): (a) 正のコントロール: `0x8c3ca8`〜`0x8c3cb0` で `direct accesses: 1` (`0x411ba2 call qword ptr [rip + 0x4b2100]`、`relocs overlapping: 0`) — 検出器は rip 参照を数えられる。(b) 再配置のコントロール: 再配置の無い `0x86b189`〜`0x86b18a` で `relocs overlapping: 0`・`direct accesses: 0`。
- したがって `0x411330` が受け取る `rbx` (= `0x86b188`) の中身は、`.text` 内に rip/abs 形式の直接書込みが無い限りローダ設定の `0x41bf30` のまま。「直接書込みが無い」は rip/abs 形式の静的アクセスに限る。レジスタ経由の間接書込みは未除外で、unicorn での実行時確認が残件。
- 前段の誤り訂正 (scratch 検証で判明): 再配置の突き合わせは RVA と VA の取り違えで一度 0 件と誤判定した。RVA `0x46b188` で再確認し、VA `0x86b188` の再配置 1 件を確認。
