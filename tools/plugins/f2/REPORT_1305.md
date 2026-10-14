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
- 測定 HEAD: `0a1fdacd` (スクリプトの最終版。以降の commit は REPORT のみ)。実測 (block19148 のみ、逐次、`python3 tools/plugins/f2/slot_write_scan.py <block19148_PE.bin> 0x86b180 0x86b190`): 3 回の wall = 18.80 / 18.88 / 19.05 秒 (min–max 18.80–19.05 秒、RSS 約 220 MB、並列数 1、開始時 load average (1 分) 0.86 / 0.90 / 0.93)。
- 結果: `relocs overlapping: 1`・`direct accesses (rip/abs disp), excluding lea: 0`。同じ範囲の rip 相対・絶対 disp アクセスは `lea` を除き 0 件 (書込みも読出しも 0)。
- ネガティブコントロール (同じ検出器、同じ入力): (a) 正のコントロール: `0x8c3ca8`〜`0x8c3cb0` で `direct accesses: 1` (`0x411ba2 call qword ptr [rip + 0x4b2100]`、`relocs overlapping: 0`) — 検出器は rip 参照を数えられる。(b) 再配置のコントロール: 再配置の無い `0x86b189`〜`0x86b18a` で `relocs overlapping: 0`・`direct accesses: 0`。
- したがって `0x411330` が受け取る `rbx` (= `0x86b188`) の中身は、`.text` 内に rip/abs 形式の直接書込みが無い限りローダ設定の `0x41bf30` のまま。「直接書込みが無い」は rip/abs 形式の静的アクセスに限る。レジスタ経由の間接書込みは未除外で、unicorn での実行時確認が残件。
- 前段の誤り訂正 (scratch 検証で判明): 再配置の突き合わせは RVA と VA の取り違えで一度 0 件と誤判定した。RVA `0x46b188` で再確認し、VA `0x86b188` の再配置 1 件を確認。

## 10. PLG-F3-21 (#1807 子 A): unicorn による実行時確定 (測定 commit 4a4987bc)

- 道具: `tools/plugins/f2/unicorn_trace.py` (unicorn 2.1.4・pefile)。PE を preferred base 0x400000 に展開し、import (通常 IAT・遅延 IAT) を ret の stub に差し替え、指定関数を実行する。書込み監視範囲の書込み元 rip と、フォルト時の直前命令列を出す。
- 入力: `$RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block19148_PE.bin`)。
- 測定 (block19148、逐次、負荷 load 0.19 → 0.25):
  - T1 `0x41bf30` 単体 (`[0x86b188]` の初期化経路): 実行後 `[0x86b188] = 0x41bf30` (変化なし)・戻り値 `rax = 0x298`・監視範囲 `0x86b188:0x86b190` への書込み 0 件。wall 1.63 秒・RSS 約 227 MB。
  - T2 `0x411330` (呼出し元と同じ引数、r9=`0x86b188`、7 番目引数 1、r13 = `0x8c3c80` 系): `0x4113f2` で `[0x86b188] = 0x41bf30` が `0x8c3ca8` に書込まれる (rip=0x4113f2)。その後、同じ実行内で `0x41196b` が `0x8c3ca8` に `0` を書込む (rip=0x41196b、`rep movsq`)。最終値 `[0x8c3ca8] = 0`。フォルト (`rip=0`、`[rsp]=0`) で停止。直前は `0x4118f2`〜`0x411922` の命令列。wall 1.63 秒。
- 静的解析の前提との差: §9 の「`0x8c3ca8` の格納値は `[0x86b188]` の実行時値」は `0x4113f2` の時点では正しいが、同じ実行内で `0x41196b` が `0x8c3ca8` を上書きする。よって「`0x8c3ca8` の最終値 = `0x41bf30`」とは言えない。
- `0x41196b` の書込みは `0x411940` 内の `rep movsq` (コピー元は引数 rcx が指す構造体)。T2 では rcx に scratch 領域を渡したため、0 の値は合成入力由来であり、実プログラムで同じ値になるとは言えない。
- 未確定: (1) `0x411940` の実呼出し元と、そのときの rcx (実データで `0x8c3c80` 系に当たるか)。(2) T2 のフォルト (`rip=0`) が合成引数によるものか。(3) `0x41bf30` の戻り値 `0x298` と `object_or_register_based` 14 件の関係。
- 判定 (受入条件): 1 (`0x41bf30` 呼出し後の `[0x86b188]` の確定) **達成** (`0x41bf30` のまま、書換えなし)。2 (レジスタ経由の書込みの実行時トレース) **部分達成** (T1 は関数単位で書込み 0 件。プログラム全体の実行は未実施)。3 (`[rbx]` → `0x8c3ca8` の確定) **未達** (`0x4113f2` で `0x41bf30` が入るが、`0x41196b` が後で 0 を書く)。4 (REPORT §9 への記録) **達成** (本節と §9 の注記)。waiver は変更しない。
- 静的側の照合 (issue 検証方法): `python3 tools/plugins/f2/slot_write_scan.py <block19148_PE.bin> 0x86b180 0x86b190` = `relocs overlapping: 1`・`direct accesses (rip/abs disp), excluding lea: 0` (wall 24.29 秒、load 0.12 → 0.42)。実行可能セクションは `.text` のみ。
- 再現: `python3 tools/plugins/f2/unicorn_trace.py <block19148_PE.bin> 0x41bf30 -q 0x86b188 -q 0x8c3ca8 -w 0x86b188:0x86b190 -m 100000` と `python3 tools/plugins/f2/unicorn_trace.py <block19148_PE.bin> 0x411330 -r rcx=0x40000000 -r rdx=0x40000100 -r r8=0x86b128 -r r9=0x86b188 -a 0 -a 0x40000200 -a 1 -a 0 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 200000`。

## 11. PLG-F3-23 (#2259): 0x8c3ca8 の最終値の実行経路 (測定 commit は本 PR の commit、block19148)

- 入力: `PE=$RUNNER_TEMP/extracted/block19148_PE.bin` (`cd $RUNNER_TEMP && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block19148_PE.bin`、5,904,384 bytes)。依存: `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。以下のコマンドは `export PATH=$RUNNER_TEMP/f2venv/bin:$PATH` の下で、リポジトリ直下から実行。
- 受入 1 (`0x411940` の実呼出し元と `rcx`): `callsite_scan.py <PE> 0x411940 0x8c3ca8 0x8c3c80` の結果は直接呼出し元 2 件 `0x411acf` (`rcx = lea 0x8c3da8`、`0x411ac8`) と `0x411bb8` (`rcx = lea 0x8c3c80`、`0x411bb1`)。両方 `0x411a80` の pdata 範囲 [0x411a80,0x411c05) 内。`0x411acf` の `rcx=0x8c3da8` は `callsite_scan` の `lea` 由来で、動的トレースでは未到達 (`0x8525f0`・`0x83efb0` の両経路で `-t 0x411acf` が 0 件)。実行時に実測した rcx は `0x411bb8`・`0x411940` の `0x8c3c80` のみ。`0x411940` 本体は、`rcx` が指す構造体の +0x38 から 0x1e qword をローカルへ退避し、`rsi = [rcx]` として `rep movsq` で `rcx` 自身へ 0x25 qword コピーする (コピー元は `[rcx]` が指す領域)。よって `0x8c3ca8` (= `0x8c3c80+0x28`) は `[[rcx]+0x28]` で上書きされる。`0x411bb8` 経路では `rcx = 0x8c3c80`、`[0x8c3c80]` は `0x411330` が格納したスタック上の構造体ポインタ。
- 受入 2 (実データ経路で最終値): **未達**。DLL エントリ `0x8525f0`・export `CreatePlugInstance` (`0x83efb0`) の両方から unicorn で実行したが、ホストの実引数 (rcx = plugin host 構造体) が無く、
  - `0x8525f0` 経由: `0x41c740` の第 1 引数はスタック上のゼロ領域。`0x411940` が `0x8c3c80` にコピーする元は 0 で、`0x41196b` が `0x8c3ca8` に書く値は 0 (`0x4113f2` の `0x41bf30` は直後に上書きされる)。実データの値ではない。
  - `0x83efb0` 経由: 引数を与えないと `UC_ERR_FETCH_PROT` (rip=0x0・`rax=0x0`) で停止する。最後に実行された命令は `0x7772be` で、`[rsp]=0x7772c0` の間接 call がゼロの関数ポインタを呼んでいる (読み出し違反ではない)。`-r rcx=0x400000` を与えたときだけ `UC_ERR_READ_UNMAPPED` (rip=0x7772be・`rax=0x400000`) になる。どちらの場合も `0x411a80` (`0x411940`・`0x411bb8` の親) には届かない。
- 再現コマンド (`$PE` は入力の PE):
  - 受入 1: `python3 tools/plugins/f2/callsite_scan.py $PE 0x411940 0x8c3ca8 0x8c3c80`
  - 受入 1 (動的): `python3 tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -t 0x411940 -t 0x411bb8 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000` (rcx=0x8c3c80 で各 1 回・`0x41196b` が 0 を書く)
  - 受入 2 (`0x8525f0`・書込み): 上と同じコマンド (watch writes 2 件: `rip=0x4113f2` が 0x41bf30、`rip=0x41196b` が 0)
  - 受入 2 (`0x83efb0`・引数なし): `python3 tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -t 0x411940 -t 0x411bb8 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000` → `UC_ERR_FETCH_PROT rip=0x0 rax=0x0`
  - 受入 2 (`0x83efb0`・rcx 指定): `python3 tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -r rcx=0x400000 -t 0x411940 -t 0x411bb8 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000` → `UC_ERR_READ_UNMAPPED rip=0x7772be rax=0x400000`
- 追加した道具: `unicorn_trace.py -t <VA>` (そのアドレスに入るたびに rcx/rdx と [rcx]・[rcx+0x28] を最初の 20 回まで出す)。
- 判定: 受入 1 **達成**、受入 2 **未達** (実引数が無い)、受入 3 (プログラム全体の経路の書込み追跡) **未達** (`0x83efb0` 経路が合成入力で止まる)。waiver は変更しない。
- 未解決 (起票先: 本 issue の残件。実引数を与える経路の確定が必要): `CreatePlugInstance` のホスト引数 (`0x777290` の読み出し先) を実 FL の呼出し値で与えること、またはホストが `CreatePlugInstance` に渡す構造体の形を決めること。これが決まるまで `0x8c3ca8` の最終値は確定しない。

## 12. PLG-F3-25 (#2284): 合成 host による CreatePlugInstance の到達範囲 (測定 commit 656932d2、block19148)

- 道具: `unicorn_trace.py -H` を追加。rcx・rdx に合成 host (`SCRATCH+0x10000`) を置き、`[host]` を vtable とする。`vtable[0]` は戻り値として第 2 の合成 obj (`SCRATCH+0x12000`) を返す。vtable の各スロットは ret stub。`-H` 無指定時は従来どおりで、§11 の結果 (`0x8525f0` の書込み 2 件、`0x83efb0` の `UC_ERR_READ_UNMAPPED` rip=0x7772be) を再現した。
- 実測 (`python3 tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -t 0x411940 -t 0x411bb8 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000`、2 回、逐次、wall 1.38 / 1.40 秒、RSS 約 227 MB、load 0.31 → 0.39):
  - `0x777290` の `call [rbx]` (host.vtable[0]) は通過する。
  - `0x83cad7` の `call [rax+0x30]` (obj.vtable[0x30]) も通過する。
  - `0x407a5e` の `and rcx, [rax-8]` で `UC_ERR_READ_UNMAPPED` (rip=0x407a5e・rax=0)。直前の `0x407a20` は `[rbx+8]`・`[rdx+0x18]`・`[rax-8]` を読むアロケータ状の処理。
- 判定: 受入 1 (`0x411a80` 到達) **未達**。受入 2 (`0x411bb8` 呼出し時の記録) と受入 3 (`-w` によるプログラム全体の書込み追跡) は受入 1 が前提のため未実施。waiver は変更しない。
- 残件 (子 issue に移す): `0x407a20` が読むブロック構造 (`[rax-8]` のヘッダ形式、`[rbx]`・`[rbx+8]`・`[rdx+0x18]` の初期化) を PE 内の初期化コードから復元し、合成 host/obj に入れる。

## 13. PLG-F3-24 (#2272): CreatePlugInstance (0x83efb0) の実引数による到達 (部分、測定 commit cdfa8bda)

- 道具の追加 (114843e2): `unicorn_trace.py` に `-d addr=val` (実行前の qword 書込み。ホスト構造体の合成用) と `-t hex` (番地に入るたびに rcx/rdx/r8/r9 を出す) を追加。既存の `-r`/`-w`/`-q` の挙動は不変。
- 入力: `block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst extracted/block19148_PE.bin`、`TMPDIR=$RUNNER_TEMP` 下に展開)。fl-win64 には実行時のメモリダンプが無く、host の実データは PE から得られない。
- 静的確認: `0x83efb0` は `call 0x777290` (r8=0x9876、r9=`0x8bbc04`) の結果が真なら `0x83cb50` → `0x8402b0` の経路。`0x777290` は第 1 引数 `[rcx]` を vtable として `call qword ptr [rbx]` (0x7772be) を行う。
- 実測 (head cdfa8bda、block19148、逐次、uptime load 1 分 0.53、各実行 wall 数秒):
  - 試行 1 (`-r rcx=0x40000000`): `UC_ERR_FETCH_PROT` rip=0x0・rax=0x40000000。`0x7772be` の `call [rbx]` が 0 を呼ぶ (呼出し元の戻り番地 `[rsp]=0x7772c0`)。Issue の `UC_ERR_READ_UNMAPPED` (rip=0x7772be) は**再現しない**。
  - 試行 1' (`-r rcx=0x400000`): `UC_ERR_READ_UNMAPPED` rip=0x7772be・rax=0x400000。Issue と一致するのはこちら。
  - 試行 2 (`-r rcx=0x40000000 -d 0x40000000=0x40000200 -d 0x40000200=0x100ffff0`): `0x777290` は通過し、`0x83cad7` (`call qword ptr [rax+0x30]`) で `UC_ERR_READ_UNMAPPED` rip=0x83cad7・rax=0x100ffff0 (vtable 項目 `+0x30` が未マップ)。
  - 試行 3 (`-H`、合成 host・vtable の全 slot は ret stub): `0x777290` → `0x83cb50` → `0x83cca0` → `0x407a20` (rcx=0x48・rdx=0x9) を経て、`0x407a5e` (`and rcx, [rax-8]`) で `UC_ERR_READ_UNMAPPED` rip=0x407a5e・rax=0x0。stub hits は host.vtable[0x0] 2 回・obj.vtable[0x30] 1 回。`0x411bb8`・`0x411940` には届かず、`[0x8c3ca8]` の書込みは 0 件。
- 判定 (受入条件): 1 (実引数で `0x411a80` に届く) **未達**。`0x407a20` 系が読むヒープ/リンク構造を PE 内の静的情報から合成する必要がある。2 (`0x411bb8` の `[0x8c3c80]`・`[[rcx]+0x28]` の確定) **未達**。3 (`0x83efb0` 起点の `-w 0x8c3ca8:0x8c3cb0`) **未達** (受入 1 が前提)。REPORT の結論 (§9・§10) は変更しない。waiver は変更しない。
- 残件 (#2272 で追跡): host 構造体の合成を `0x407a20` 系まで行い、`0x411a80` に届かせる。届いた後に `0x411bb8`・`0x411940` の trace と `0x8c3ca8` の最終値を確定する。

## 14. PLG-F3-26 (#2295): 0x407a20 の入力状態と呼出し経路 (測定 commit 6d471846、block19148)

- 測定 commit: **6d471846** (この節の `-t`・`-d`・走査の件数・`esi`/バイトの読み値は、すべて 6d471846 で取得した)。e53d845b の測定 (1.68 s、同じ fault) は旧測定として残すだけで、判定の根拠にしない。e53d845b からの差分は `unicorn_trace.py` +9 行 (main 側の `-d` 追加) と `jump_scan.py` 新規。`tools/plugins/f2/` の差分は `git diff e53d845b 6d471846 -- tools/plugins/f2/` で確認できる。
- 入力: `$RUNNER_TEMP/ex/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`、5,904,384 B)。依存: `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。
- 再現 (逐次、`PE=$RUNNER_TEMP/ex/extracted/block19148_PE.bin`): `python3 tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -t 0x411940 -t 0x411bb8 -q 0x8c3ca8 -w 0x8c3ca8:0x8c3cb0 -m 2000000` = `UC_ERR_READ_UNMAPPED rip=0x407a5e rax=0x0`。§12 と一致。
- 走査の再現 (リポジトリ内の script):
  - `python3 tools/plugins/f2/callsite_scan.py $PE 0x407a00 0x867100` = `0x407a00` への e8/e9 直接呼出し元 9 件、`0x867100` への rip 相対 lea 4 件 (`0x407a19`・`0x408933`・`0x40909a`・`0x409216`)、読み書き 0 件。
  - `python3 tools/plugins/f2/jump_scan.py $PE 407a20 407a00 867100` = jcc/jmp 0 件 (3 アドレスとも)。
- 入口: `0x407a20` は pdata 関数 `[0x407a00,0x407dc1)` の内側で、`0x407a00` から fall-through で入る。`0x407a00`〜`0x407a19` が `rbx`・`r8`・`rdx` を設定する (`rdx=(ecx+7)>>3`・`r8=0x8bfa3c`・`rbx=0x867100`)。入力は `rcx` のみ。
- `-t` の実測 (`-H` 実行): `0x407a00` で `rcx=0x48 rdx=0x1`、`0x407a20` で `rcx=0x48 rdx=0x9` (`[rcx]=0`)。
- `0x407a20` の処理: `esi=[0x8bf0a9]` (rip 相対 `0x407a27+0x4b7682`) = 0 (分岐 `test esi,esi; jne 0x407ab1` は不成立)。`byte[r8+rdx]` = `byte[0x8bfa45]` = 0 → `rbx = 0x867100 + 0`。`rdx=[rbx+8]=0`、`rax=[rdx+0x18]=[0x18]=0` (page 0 は 0x2000 B マップ済みで読める)、`cmp rdx,rbx` 不成立で `add dword [rdx+0x20],1` (page 0 への書込み)。最後の `and rcx,[rax-8]` が `rax=0` で `[-8]` を読み `UC_ERR_READ_UNMAPPED`。
- 直接原因: `rbx`=`0x867100` の bin で `[rbx+8]=0`。`0x867100` の初期内容は `00 00 10 00 00 00 00 00` (qword 0 = `0x100000`、qword 1 = 0)、`0x867110`〜`0x86713f` は 0、`0x867140` は `00 00 20 00 ...` (qword = `0x200000`)。`[rbx+8]` が自己ポインタでないため空リストとして扱われず、`rax=0` の `[rax-8]` 読出しに進む。
- 自己参照 seed の実測 (`-d` で書込み): `-d 0x867108=0x867100` では `0x407a94` の `mov [rax-8],rdx` (rax=0) で `UC_ERR_WRITE_UNMAPPED`。`0x867110` も併せて seed しても同じ。つまり `0x867100` の自己参照だけでは不足で、`[rax-8]` が指す有効なチャンクヘッダ (ヒープ/アリーナ領域) が要る。
- 呼出し経路: `0x407a00` への直接 call 9 件 (上記)。`-H` 実行での上流経路は §13 (PLG-F3-24) の試行 3 (`0x777290` → `0x83cb50` → `0x83cca0` → `0x407a20`)。`.data`/`.rdata` の関数ポインタ経由の到達は未確認。
- 判定: 受入 1 (`0x407a20` が読むブロック構造の復元) **未達**。受入 2〜4 は受入 1 が前提のため未実施。waiver は変更しない。
- 未解決 (#2303 で追跡): (1) `0x407a20` の間接呼出し元 (`.data`/`.rdata` の関数ポインタ・vtable から逆引き)、(2) `0x867100` を指すアリーナ構築関数 (`-w 0x867100:0x867200` で書込み元 rip を取る)、(3) `[rax-8]` のチャンクヘッダ形式 (`0x407a94`・`0x407b98` の使用から逆算)。
- 再現: 上記 unicorn コマンドと callsite_scan.py / jump_scan.py。

## 15. PLG-F3-27 (#2303): 0x407a20 の間接呼出し元と arena 初期化 (部分、測定 commit 4048b18a、block19148)

- 道具: `tools/plugins/f2/fn_refs.py` を追加 (4048b18a)。`fn_refs.py <block19148_PE.bin> <VA>...` で、囲む pdata 関数・rel32 call/jmp 元・絶対 qword 格納・rip 相対参照 (lea/mov/call) を出す。入力は `$RUNNER_TEMP/ex/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/ex extracted/block19148_PE.bin`)。
- 注: `0x407a20` は関数先頭ではなく、pdata 関数 `0x407a00` の内側 (fall-through)。`0x407a20` を指す rel32・qword・rip 参照は 0 件。実際に読まれる関数は `0x407a00`。
- 受入 1 (0x407a20 / 0x407a00 の間接呼出し元): **部分達成**。
  - `0x407a00` の格納元は `.data` の qword 表 `0x867c88` (要素 0 = `0x407a00`) の 1 件のみ。
  - 表 `0x867c88` を `call qword ptr [rip+...]` で呼ぶのは `0x4093ae`・`0x409455`・`0x41b294` の 3 件。`0x41b294` は thunk `0x41b290` (直接呼出し元 `0x41b2cc`)。
  - `0x41b2cc` を含む `0x41b2c0` (wrapper) の直接呼出し元は `0x847159`・`0x847178`・`0x847197` (いずれも関数 `0x847120`)。`0x847120` の直接呼出し元は `0x83f637`。
  - 残りの `0x407a00` 直接 call 元 (`0x40796b`・`0x4079b9`・`0x408038`・`0x40807f`・`0x4081bd`・`0x408303`・`0x408371`・`0x418ecd`・`0x41a1e0`) は一覧のみ。
  - CreatePlugInstance (`0x83efb0 -H`) の実経路: `0x4093a0` (`call qword ptr [0x867c88]` を含む関数) → `0x4093ae` → 表経由で `0x407a00` (`rcx=0x48`・`rdx=1`・`[rcx]=0`) → `0x407a5e` で `UC_ERR_READ_UNMAPPED` (`-t` 出力、各 1 回)。`0x409370`・`0x4093d0` は経路外。`0x41b2c0`・`0x847120`・`0x83f637`・`0x409090`・`0x41bc60` は未到達 (`-t` 出力なし)。
- 受入 2 (0x867100 を構築するアリーナ初期化): **部分達成**。
  - `0x867100` を指す rip 相対 `lea` は 4 件 (`0x407a19`・`0x408933`・`0x40909a`・`0x409216`)。`0x407a19` は `0x407a00` 内の `rbx` 初期化。`0x867100` 自体への rip 相対の読み書きは `lea` 以外 0 件 (`fn_refs.py`)。
  - arena 初期化の候補は `0x409090` (`0x867100`・`0x8671xx` を `lea r8` で構築)。直接呼出し元は `0x41bc8c` のみ (`0x41bc60` 内)。`0x41bc60` は `.data` 表 `0x8526c0` の要素で、`0x8526c0` への参照は PE 内に 0 件 (実行時に埋まる)。
  - unicorn: `0x409090` を単体 (`-H -w 0x867100:0x867200`) で実行すると arena が構築される (`0x867190`・`0x867188`・`0x8671a0` 等に書込み)。`0x8525f0` と `0x83efb0 -H` のどちらでも `0x409090` には到達しない。`0x83efb0 -H -w 0x867100:0x867200` の書込みは 0 件。
- 判定: 受入 1 **部分達成** (間接の連鎖は静的に追えた。実経路に乗るかは未確定)。受入 2 **部分達成** (構築関数 `0x409090` を特定、呼出し経路は未確定)。受入 3 (`[rax-8]` のヘッダ形式の復元) **未達**。受入 4 (`0x83efb0` が `0x411a80` に届く) **未達** (`0x407a5e` で停止)。受入 5 (`0x411bb8` 呼出し時の記録) **未達**。waiver は変更しない。
- 再現 (4048b18a):
  - `python3 tools/plugins/f2/fn_refs.py $PE 0x407a00 0x867c88 0x41b290 0x41b2c0 0x847120 0x409090 0x867100` (wall 18.4 秒、単独逐次。load は未計測)
  - `python3 tools/plugins/f2/unicorn_trace.py $PE 0x83efb0 -H -w 0x867100:0x867200 -m 2000000` (wall 1.4 秒、`UC_ERR_READ_UNMAPPED` rip=0x407a5e)
  - `python3 tools/plugins/f2/unicorn_trace.py $PE 0x409090 -H -q 0x867100 -w 0x867100:0x867200 -m 2000000` (arena 構築の書込みを出す)
- 再測定 (測定 commit **458a92f2**、main (84932c5a) 取り込み後、逐次、uptime load 0.45〜0.58):
  - 鮮度: `git diff 4048b18a 458a92f2 -- tools/plugins/f2/fn_refs.py tools/plugins/f2/unicorn_trace.py` = 0 行 (測定対象の `.py` は不変)。
  - `fn_refs.py $PE 0x407a00 0x867c88 0x41b290 0x41b2c0 0x847120 0x409090 0x867100`: rc=0、wall 12.96 秒。出力は上記の結論と一致 (`0x407a00` の格納元は `0x867c88` のみ、`0x867c88` の rip 参照は `0x4093ae`・`0x409455`・`0x41b294`、`0x407a00` への rel32 は 9 件、`0x867100` への lea は 4 件)。
  - `unicorn_trace.py $PE 0x83efb0 -H -w 0x867100:0x867200 -m 2000000`: rc=0、wall 1.32 秒、`UC_ERR_READ_UNMAPPED rip=0x407a5e rax=0x0`、書込み 0 件。
  - `unicorn_trace.py $PE 0x409090 -H -q 0x867100 -w 0x867100:0x867200 -m 2000000`: rc=0、wall 1.32 秒、書込み 28 件 (rip=0x4090a1〜0x4090f9)。
- 未解決 (#2303 の残件。起票先は本 issue。実経路で `0x847120`・`0x409090` を呼ぶ上位関数を確定する必要あり): (a) `0x847120` の呼出し元 `0x83f637` が `0x83efb0` の経路に乗るか、(b) `0x409090` の呼出し元 `0x41bc60` (表 `0x8526c0`) が実行時に埋まる経路、(c) `[rax-8]` のチャンクヘッダ形式 (受入 3)、(d) `0x411bb8` 記録 (受入 5)。

## 16. PLG-F3-27 続き (#2303): arena の前処理と chunk header 形式 (部分、測定 commit a70461d6、block19148)

- 訂正 (a70461d6): 8eda24a9 の `-V` は import 名の完全一致で判定していたため、DLL 名の大文字小文字が違う PE では無音で無効になった。同一 PE の大文字化コピーで旧版は B と同じ `rip=0x41bfaa`、新版は C と同じ結果になることを確認。`POOL_SIZE` (128 MiB) 超過は `error:` を出して 0 を返す (`POOL_SIZE` を 1 MiB に縮めた一時コピーで確認)。既定の挙動と C の出力は 8eda24a9 版 (= origin/main の `unicorn_trace.py`) と A・C の出力が全文一致。
- 道具 (a70461d6): `unicorn_trace.py` に `-p hex` (本体の前に同じメモリで実行する関数。arena 初期化 `0x409090` 用) と `-V` (VirtualAlloc が 0x50000000〜 の pool を 64KB 境界で返す) を追加。既定の挙動は不変。
- 測定 (逐次、n=3、load 0.36→0.46): wall A 1.22〜1.27 秒・B 1.23〜1.37 秒・C 1.24〜1.31 秒、RSS A/B 約 227 MB・C 約 237 MB。A `-H` は `UC_ERR_READ_UNMAPPED rip=0x407a5e` (§15 と一致)。B `-H -p 0x409090` は `0x407a20` を通過し、`VirtualAlloc` の戻り 0 で `rip=0x41bfaa` (エラー経路)。C `-H -V -p 0x409090` は初回確保 (`0x407630`→`0x407c21`) まで進み、pool への書込み 44 件の後、`UC_ERR_INSN_INVALID rip=0x50138d06` (pool 内) で停止。
- 受入 3 (chunk header) **部分達成** (使用中ヘッダは実測、空きリンクは推定): blk=`0x50138cc0`。`[blk-8]`=size+6 (`0x407c25`)、`[blk+0]`=所有 bin `0x867200` (`0x407c31`)、`[blk+0x18]`=空きリスト先頭 0、`[blk+0x20]`=使用数 1 (`0x407c34`・`0x407c38`)。最初の obj (`blk+0x30`) の `[obj-8]`=blk (`0x407c60`)。空き obj の `[obj-8]` は次の空き obj へのリンクと推定 (読取り側 `0x407a5e` の `and rcx,[rax-8]` から)。`[blk+0x18]`=0 のため書込み側は未観測で、検証は子 #2468 に移す。
- 受入 4 (0x411a80 到達) **未達**: 停止点 `0x50138cf0`→`0x50138d06` (pool)。`0x5da06d` (`mov rax,[rax]`) は 1 回実行され、そのときの rcx (this) は 0。停止と this の対応は未確定。`0x407520` が `[blk+0]` を `0x867200`→`0x8c02c0` に書換える (`0x407553`) ことも確認。
- 受入 5 (0x411bb8 の記録) **未達** (受入 4 が前提)。残件は子 #2468 に移した。
- 再現 (a70461d6。依存 `uv venv f2venv && uv pip install unicorn==2.1.4 pefile capstone`。リポジトリ直下から、`PE` は block19148_PE.bin): A `unicorn_trace.py $PE 0x83efb0 -H -m 2000000`、B `unicorn_trace.py $PE 0x83efb0 -H -p 0x409090 -m 2000000`、C `unicorn_trace.py $PE 0x83efb0 -H -V -p 0x409090 -w 0x50000000:0x50200000 -m 2000000`。
- 鮮度: `git diff a70461d6 HEAD -- 'tools/plugins/f2/*.py'` = 0 行 (a70461d6 以降の commit は REPORT のみ)。

## 17. PLG-F3-30 (#2493): 0x867100 を構築するアリーナ初期化関数 (書込み元 rip、測定 commit da16bc06、block19148)

- 道具: `write_origin.py` (1b8b7eb1) は watch writes の書込み元 rip を囲む pdata 関数ごとに集計し、命令を逆アセンブルする。`write_origin_2493.sh <PE>` (da16bc06) が以下を一括で再現する (`bash tools/plugins/f2/write_origin_2493.sh $PE`、逐次、wall 7.00 秒、load 0.10→0.18、PE と venv は §11)。
- 結果: `0x409090 -H -q 0x867100 -w 0x867100:0x867200` の書込み 28 件 (`0x867101`〜`0x8671e0`) は全件が pdata 関数 `[0x409090,0x4091d4)` 内の 7 命令 (rip `0x4090a1`〜`0x409159`) から出た。unmapped 0。3 回の出力は md5 一致 (`e20906a7…`)。関数は `mov r9d,0x2e` の 46 回ループ (`r8 += 0x40`) で、監視 0x867100:0x867200 は 4 ブロック×7 = 28 件、0x867100:0x867300 は 8 ブロック×7 = 56 件 (実測) と整合する。
- 負の対照: `-w 0x867d00:0x867e00` は 0 件。アリーナを構築しない全経路 `0x83efb0 -H -w 0x867100:0x867200` も 0 件 (`UC_ERR_READ_UNMAPPED rip=0x407a5e`、§15 と一致)。
- 判定: 受入 **達成**。アリーナ初期化関数は `0x409090`。呼出し経路 (`0x41bc8c` ← `0x41bc60`・表 `0x8526c0` が実行時に埋まる) は §15 のとおり未確定で、未解決は #2303 (親) に残す。
- 鮮度: `git diff da16bc06 HEAD -- tools/plugins/f2/*.py tools/plugins/f2/*.sh` = 0 行 (以後の commit は本節のみ)。
