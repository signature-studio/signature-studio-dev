# tools/plugins/f2 REPORT_1305 — PLG-F3-7 (#1305): waiver 4 site の間接 call 23 件の解決と例外到達の判定

- 検証起点 commit: **f2790047** (origin/main。`1305-plg-f3-7` の基点)。数値は同 HEAD で `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` を設定して実行。
- 既知類型との関係: (DEFECTS.md) 該当なし。W の間接 call は icall_gate で被覆済み (icall §4 D1 の対象外)。waiver の対象は (icall §4) D12 landing pad (#529 §7.7)。新規類型なし。
- 担当 dir: `tools/plugins/f2/` のみ。生成物は `tools/plugins/work/f2/` (gitignore)。
- 範囲: 静的解析のみ。DSP 実行・native 実行による到達の実測は範囲外。

## 0. 結論 (先出し)

1. 間接 call 23 件 (19148・19245 とも同一構成) のうち、**3 件が `kernel32!RaiseException` の thunk を格納する slot 経由で例外送出 API に解決**された。残る 20 件は未解決 (内訳 §1)。
2. waiver の 4 root (`0x780d00`・`0x78a660`・`0x77a550`・`0x783eb0`) は、いずれも **D12 pad 範囲内の `call 0x411070`** から `0x410220` を経て RaiseException に届く (直接 call のみの最短経路長 3)。
3. pad 範囲内の経路は fallthrough では入らない (pad 直前の `jmp` が飛び越す) が、pad が実行されれば `0x410220` (フラグ分岐付き) と `0x410ef0` (分岐に関わらず `0x411017` で RaiseException) の両方を通り、**pad 実行時は必ず例外 API に届く**。ただし `0x410ef0` 内の `call [0x8bf040]` (関数ポインタ) の戻らない可能性は未解析。pad が DSP 実行で実行されないことも未証明。waiver の reason の未検証箇所は残る。
4. **受入条件 2 (waiver 削除または reason 更新) は未達**。本 PR では waiver を変更しない。判断は #529 に委ねる (§3)。

## 1. 測定 (HEAD f2790047)

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
- `0x411070` (19148、pdata 境界 [0x411070,0x4110b2)) は `call 0x410220` (0x411098) の後、**分岐なしで** `call 0x410ef0` (0x4110a6) を呼ぶ。つまり pad が実行されれば両経路を通る。
  - 経路 A: `0x410220` (pdata 境界 [0x410220,0x410245)) は `cmp byte [0x867058],1; jbe 0x410240` で囲まれ、ファイル上の初期値 0 では RaiseException (`call [0x8bf030]`・0x41023a) を飛ばす。値が 2 以上なら実行する。
  - 経路 B: `0x410ef0` (pdata 境界 [0x410ef0,0x411029)) の 0x410f63 で `cmp qword [0x8bf040],0; je 0x411000` と `test dil,dil; jne 0x411000` の 2 分岐がある。両方とも不成立 (`[0x8bf040]!=0` かつ `dil==0`) のとき fallthrough で `0x410f7a` に入り、`0x410ffa` で `call qword [0x8bf040]` を実行してから `0x411000` に落ちる。どの経路でも `0x411000` に届き、`0x411017` で `call [0x8bf030]` (RaiseException の slot) を実行する。`0x410ef0` の直接 call は `0x410f0e` (`call 0x411c30`、rbx==0 のときのみ)・`0x410ffa` (`call [0x8bf040]`)・`0x411017` (`call [0x8bf030]`) の 3 つだけ。
  - 結論: pad 実行時は**必ず例外 API に届く**。経路 A の分岐は pad の安全性の根拠にならない。未解析: (a) `call [0x8bf040]` (0x410ffa) が戻らない・途中で脱出する可能性 (指す関数の中身は未解析)、(b) `0x411c30` (rbx==0 のとき) の中身。いずれも途中で脱出すれば経路 B の RaiseException に届かない可能性がある。
- フラグ `0x867058` (経路 A の分岐変数) と関数ポインタ `0x8bf040` (経路 B で null 判定したうえで `call qword [0x8bf040]` する先) への rip 相対の直接書込みは、19148 の .pdata 関数単位の逆アセンブル走査で 0 件。これは**ファイル上の初期値 0 の下では経路 A が実行されない**ことを示すのみで、実行時に外部から書かれる可能性 (間接書込み・他 DLL 経由) は PE 内の直接書込み 0 件では否定できない。
- `0x411070` は PE 内の約 300 関数から呼ばれる共通関数。W 固有ではない。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pad 範囲に入る経路が DSP 実行で起きないこと (= 例外が DSP 内で送出されないこと) は未証明 | 起きれば `0x411070` → `0x410220`/`0x410ef0` → RaiseException。waiver の前提が崩れる (silent miscompile の可能性) | #529 (waiver 4 site の親)。本 PR は Refs #1305 |
| 間接 call 残り 20 件 (レジスタ経由 15・実行時 slot 等 5) の呼出し先 | 例外 API か未確定 | #1305 (本 issue。残件はこの issue で追跡し、解決後に reason を更新) |
| `indirect_resolve.py` の slot 格納値解析は「関数単位の直前 mov」の 1 段のみ | 2 段以上の間接経由は解決しない | #1305 (同上) |
| `0x410ef0` 内の `call qword [0x8bf040]` (0x410ffa) の戻らない可能性と、その指す関数の中身は未解析 | 途中で脱出すれば経路 B の RaiseException に届かない可能性。pad 実行時の「必ず届く」結論の前提に当たる | #1305 (本 issue) |
| `0x410ef0` 内の `call 0x411c30` (0x410f0e、rbx==0 のとき) の中身は未解析 | 同上 (rbx==0 の経路で脱出しうる) | #1305 (本 issue) |
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
