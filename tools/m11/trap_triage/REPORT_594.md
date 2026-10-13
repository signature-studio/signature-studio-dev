# #594: 8cc190 系 OOB の「NewInstance 後の入力不正」調査 — 入力は不正ではなく、417b70 の `Q(a)` 上位 4B (D17 型)

**判定: 原因は実測で特定 (受入 1 達成)。修復は本 PR では入れない — #552 (qstore) が 58–63 を直すことを実測で確認し、残る unit 56 は別原因 (受入 2: 解消できない理由を記録)。**
issue 本文の前提「8c7a10 の入力が不正 (`[g+0x410]` / 8cbfa0 の cls 引数)」は**否定**された。
検証起点 = `0865903` (main)。追加物は `trap_triage/negctl_594.sh` と本 REPORT のみ (`m11_ov.c` は不変)。

既知類型との関係 (`docs/DEFECTS.md`): **D17 (DEFECTS.md は #552 で追記予定) と同型**。`8cbb00` の局所スロット `stack_var_-56` が IR で `store ptr null` (wasm32 の ptr = 4B) になり、
上位 4B が未初期化のまま C 転記 `function_417b70` が `Q(a)` (8B) で読む。unit 56 の残りは D4 型 (deref 脱落, §4)。

## 1. 現況 (main `0865903`、issue 本文との差)

issue は「8cc190 系 11 unit」。main では #503 (辞書比較器の転記) 等が入り、**最上位 `8cc190` を frames に持つ OOB は 7 unit (56, 58–63)** (`negctl_594.sh` の G1、`frames` に `function_8cc190` と `function_8c7a10` を両方含む oob の数)。
issue の 11 unit のうち 53, 54 は main で ok、307, 311 は halt0 (`412a40←4096b0←4096d0←409730←409470`、base の survey JSON で確認)。この 4 unit は OOB ではなく本 PR の対象外 (§3 の mask / #552 では 307, 311 が halt0→ok)。

## 2. 入力不正の否定 (受入 1)

| 観測 (`M11_TRACE` probe を `function_8cc190` 先頭に追加, 透過化済み) | 値 |
|---|---|
| `8c7a10` が `[g+0x410]` に格納する辞書 self | 全 118 回の Add で 1 種 (`0x10bc4de0`) |
| 辞書 `[self]` (VMT) | `0x4c0178`。`8c7a10` が `8cbfa0` に渡す cls 定数 `4981112` = `0x4c0178` と一致 |
| FComparer `[self+0x18]` | 1 種 (`0xfb2bf0`) |
| cnt / cap / items | cnt 0→0x64、cap 0,2,4,8,0x10,0x20,0x40,0x80 と倍々、items は Grow ごとに新アドレス (正常な成長) |
| OOB 時点 (unit 56, 58–63 共通) | cnt=cap=**0x40**, items=`0x10b72400`, `[items-8]`=128 (正常) |

OOB の入口は `8cc190`→`8cbcb0` (cnt==cap の Grow)→`8cbb00` (SetCapacity)→`417fc0`→**`417b70`**。`8cbcb0` / `8cbb00` の IR は逆アセンブルと意味一致 (`8cbcb0`: `[rcx+8]`→len×2→`8cbb00`)。
`8cbb00`→`417b70` の引数は正常 (a=スタック slot, ti=`0x4bec80`, dimcnt=1, lengths 指す値 `0x100`)。ところが `*a` が **`0x0061002000000000`** (下位 4B=0、上位 4B=UTF-16 文字列の残骸)。
`417b70` は `p=Q(a)` を既存配列として `hdr=p-0x10` を読み OOB する。これは `8cbb00` の `stack_var_-56` が IR で 4B しか 0 初期化されない D17 型。
→ 辞書 (`[g+0x410]`) も cls 引数も正しく、**呼び出し先 `8cbb00` 内の局所スロットが原因**。`8cbcb0` 系 REPORT (`alloca/REPORT.md` §6 の「上流 `8c5cc0` のポインタ破壊」) の帰属は不正確だった。

注意 (実測): probe に素の `fprintf` を使うと shadow stack の残骸が変わり survey の kind が 7 unit 変わる (53, 54 が ok→oob など)。必ず `M11_TRACE` (#495 で透過化) を使う。

## 3. 解消できるか (受入 2)

| 構成 (全 942 unit survey) | ok / oob / halt0 / miss / noproc | 58–63 | 備考 |
|---|---|---|---|
| main (base) | 818 / 21 / 56 / 46 / 1 | oob ×6 | 56 も oob |
| `417b70` の `Q(a)` を下位 4B に mask (実験, `negctl_594.sh mask`) | 827 / 14 / 54 / 46 / 1 | ok ×6 | ok 退行 0。56 は oob→halt0、307/311/917 が halt0→ok |
| SP 直下 8 KiB を 0x00 で埋める (`SV_STK_FILL=00`) | 826 / 15 / 54 / 46 / 1 | ok ×6 | 残骸依存の裏取り |
| 同 0xff で埋める | 812 / 29 / 54 / 46 / 1 | oob ×6 | 残骸が非 0 だと落ちる |
| **#552 head `64b697b` (qstore 常設)** (clean worktree, n=3 一致) | 828 / 13 / 54 / 46 / 1 | ok ×6 | base 比 oob→ok 7 (58–63, 87), oob→halt0 1 (56), halt0→ok 3, **ok 退行 0** |

結論: **58–63 は #552 を merge すれば解消する** (本 PR は同じ修復を重複して入れない)。mask は同じ効果を C 側で出す代替案だが、#552 は IR 側で 279 site を直すため不採用。

### unit 56 (別原因, 本 PR では未修復)

#552 head でも 56 は halt0: `8c5eb0`→`8c67a0`→`8c7c80`→`8c7710`→`8cbde0` (GetItem) の「キー未発見」→`411e80`。`8cbde0` 先頭の probe は key=`0x10b698c0` (heap のオブジェクト) で、辞書のキーは TClass。
`8c7710` の機械語は `rax=[arg2]` (オブジェクトの VMT=TClass) を `8cbde0` の key にするが、IR は `arg2` をそのまま渡す (**D4 型: 1 段 deref 脱落**)。
実験 (`m11_ov.c` に `function_8c7710(self,obj){return function_8cbde0(Q(self+0x410), Q(obj));}` を足す, #552 head 上, 一回きりで `negctl_594.sh` には含めない): 56 が halt0→oob (最上位 `8c5eb0`) に進むだけで ok は 828 のまま、他 unit の差分 0。
→ 次の欠陥は `8c5eb0` (`8c67c0` の戻りへの書込み等, 未調査)。採用せず、起票 (§6)。

## 4. 副次的な発見: `survey_units.mjs` の oob は最上位 frame を捨てる

oob の `frames` は `.slice(1)` で先頭 frame を落とす (REPORT_495 §の「疑い」)。実測: unit 56 の生スタックは `function_417b70, function_417fc0, function_8cbb00, …`、survey JSON は `function_417fc0, …`。
`annotate.py` の「最上位 frame `function_417fc0` ×7」は実際には `function_417b70` ×7 (1 段上を数えている)。**疑いは確定**。本 PR では直さない (直すと全 oob の frames が変わり `survey_diff.py` の基準が動く, 起票 §6)。

## 5. 再現 + ネガコン + gate

```sh
bash tools/m11/trap_triage/negctl_594.sh   # 前提: work/ に work-m11 (m11_build.sh が通ること)。全 7 構成を survey し G1–G10 を判定。1 つでも FAIL なら exit 1
```

| gate | 内容 | 結果 (実測) |
|---|---|---|
| G1 | base の `8cc190←8c7a10` 系 OOB = [56, 58–63] | PASS (n=7) |
| G2 | 決定性: base と base2 の kind 完全一致 | PASS (差 0) |
| G3 | probe: 辞書 self / FComparer が各 1 種、Add ≥ 64 回 | PASS (Add=118) |
| G4 | probe: cnt==cap==0x40 の Grow (OOB の入口) を観測 | PASS |
| G5 | mask: 58–63 が oob→ok | PASS |
| G6 | mask: ok 退行 0 | PASS |
| G7 **ネガコン** | mask 値を全 bit 1 (無加工と同義) にすると base と kind 完全一致 | PASS (差 0) |
| G8 **ネガコン** | 同構成で 58–63 は oob のまま | PASS |
| G9 | fill00: 58–63 が ok | PASS |
| G10 | fillff: 58–63 は oob のまま | PASS |

所要 (1 回目, 作業ツリー = コミット前の同一ファイル): 全体 **2 分 44 秒**、survey 1 回 13.8–21.4 秒、load average (1 分値) 0.40→0.94、直列 1 並列、4 vCPU runner。
`gate` は FAIL で `exit 1` (終了時に `m11_ov.c` 由来の `ov.o` を再生成)。

## 6. 検証範囲 / 範囲外 / 未解決

範囲: main `0865903` の `m11_ov.c` + `work-m11` スナップショットの survey 942 unit。範囲外: `m11_e2e.sh` 全体 (units_run は未測定)、`M11_OV_CLASSCREATE` (#419 / PR #446 の opt-in。main に無いため本 PR の「既定 OFF ベースライン」比較は main 自体が基準)。
#552 head の数値は clean worktree で `m11_build.sh`+`survey_units.mjs` ×3 (一致) の実測だが、`negctl_594.sh` 自体は #552 を含まない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 58–63 の修復 (qstore) は #552 の merge 待ち | main では 6 unit が oob のまま | #552 (merge) |
| unit 56: `8c7710` の D4 型 deref 脱落 + その先の `8c5eb0` の OOB | 56 が halt0/oob のまま | 新規子チケット [M11] (本 PR 作成時に起票) |
| `survey_units.mjs` oob の `.slice(1)` が最上位 frame を捨てる (確定) | `annotate.py` の最上位集計が 1 段ずれる | 新規子チケット [M11] (survey_diff の基準更新込み) |
| `alloca/REPORT.md` §6 / `m11/REPORT.md` の「上流 8c5cc0 のポインタ破壊」帰属は誤り (本 REPORT §2) | 調査の誤誘導 | 本 PR で REPORT_594 を索引に追加。元 REPORT の訂正は PM 判断 |
