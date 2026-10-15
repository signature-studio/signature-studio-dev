# #594: 8cc190 系 OOB の「NewInstance 後の入力不正」調査 — 入力は不正ではなく、417b70 の `Q(a)` 上位 4B (D17 型)

**判定: 原因は実測で特定 (受入 1 達成)。修復は本 PR では入れない — 58–63 は #552 (qstore, merge 済み) で解消を実測で確認し、残る unit 56 は別原因 (受入 2: 解消できない理由を記録)。**
issue 本文の前提「8c7a10 の入力が不正 (`[g+0x410]` / 8cbfa0 の cls 引数)」は**否定**された。
検証起点 = `c26b41d` (PR head, main `8d64067` の #552 込み、merge base `6bb4028`)。追加物は `trap_triage/negctl_594.sh` と本 REPORT のみ (`m11_ov.c` は不変)。

既知類型との関係 (`docs/DEFECTS.md` の D17 行): **D17 と同型**。`8cbb00` の局所スロット `stack_var_-56` が IR で `store ptr null` (wasm32 の ptr = 4B) になり、
上位 4B が未初期化のまま C 転記 `function_417b70` が `Q(a)` (8B) で読む。unit 56 の残りは D4 型 (deref 脱落, §4)。

## 1. 現況 (qstore 無しの base、issue 本文との差)

issue は「8cc190 系 11 unit」。`M11_QSTORE=0` の base では #503 (辞書比較器の転記) 等が入った後で、**`frames` に `function_8cc190` と `function_8c7a10` を両方含む OOB は 7 unit (56, 58–63)** (`negctl_594.sh` の G1)。main の既定 (qstore 有り) では 58–63 は ok で、OOB は qbase で `n=0` (info 行)。
issue の 11 unit のうち 53, 54 は main で ok、307, 311 は halt0 (`412a40←4096b0←4096d0←409730←409470`、base の survey JSON で確認)。この 4 unit は OOB ではなく本 PR の対象外 (§3 の mask / #552 では 307, 311 が halt0→ok)。

## 2. 入力不正の否定 (受入 1)

| 観測 (`M11_TRACE` probe を `function_8cc190` 先頭に追加) | 値 |
|---|---|
| `8c7a10` が `[g+0x410]` に格納する辞書 self | 全 118 回の Add で 1 種 (`0x10bc4de0`) |
| 辞書 `[self]` (VMT) | `0x4c0178`。`8c7a10` が `8cbfa0` に渡す cls 定数 `4981112` = `0x4c0178` と一致 |
| FComparer `[self+0x18]` | 1 種 (`0xfb2bf0`) |
| cnt / cap / items | cnt 0→0x64、cap 0,2,4,8,0x10,0x20,0x40,0x80 と倍々、items は Grow ごとに新アドレス (正常な成長) |
| OOB 時点 (unit 56, 58–63 共通) | cnt=cap=**0x40**, items=`0x10b72400`, `[items-8]`=128 (正常) |

probe の透過性は qstore 有り構成でのみ実測で保証される (`qprobe` と `qbase` の kind 差 0 = G12)。qstore 無し構成では probe が 10 unit の kind を変える (56 oob→halt0、58–63 oob→ok、307/311/917 halt0→ok。gate の info 行)。したがって上の表の値は「OOB が消える摂動付き run からの観測」であり、「摂動なしの OOB 時点の値」とは言えない。辞書 self / FComparer の一意性 (G3) と Grow の存在 (G4) は摂動付きでも観測された事実として残す。

OOB の入口は `8cc190`→`8cbcb0` (cnt==cap の Grow)→`8cbb00` (SetCapacity)→`417fc0`→**`417b70`**。`8cbcb0` / `8cbb00` の IR は逆アセンブルと意味一致 (`8cbcb0`: `[rcx+8]`→len×2→`8cbb00`)。
`8cbb00`→`417b70` の引数は正常 (a=スタック slot, ti=`0x4bec80`, dimcnt=1, lengths 指す値 `0x100`)。ところが `*a` が **`0x0061002000000000`** (下位 4B=0、上位 4B=UTF-16 文字列の残骸)。
`417b70` は `p=Q(a)` を既存配列として `hdr=p-0x10` を読み OOB する。これは `8cbb00` の `stack_var_-56` が IR で 4B しか 0 初期化されない D17 型。
→ 辞書 (`[g+0x410]`) も cls 引数も正しく、**呼び出し先 `8cbb00` 内の局所スロットが原因**。`8cbcb0` 系 REPORT (`alloca/REPORT.md` §6 の「上流 `8c5cc0` のポインタ破壊」) の帰属は不正確だった。

注意 (実測): probe に素の `fprintf` を使うと shadow stack の残骸が変わり survey の kind が 7 unit 変わる (53, 54 が ok→oob など)。必ず `M11_TRACE` (#495 で透過化) を使う。

## 3. 解消できるか (受入 2)

| 構成 (全 942 unit survey, 数値は HEAD `c26b41d` の `negctl_594.sh` 実測) | ok / oob / halt0 / miss / noproc | 58–63 | 備考 |
|---|---|---|---|
| #552 前 (qstore 無し, `M11_QSTORE=0`) = base | 818 / 21 / 56 / 46 / 1 | oob ×6 | 56 も oob |
| `417b70` の `Q(a)` を下位 4B に mask (実験, `negctl_594.sh mask`) | 827 / 14 / 54 / 46 / 1 | ok ×6 | ok 退行 0。56 は oob→halt0、307/311/917 が halt0→ok |
| SP 直下 8 KiB を 0x00 で埋める (`SV_STK_FILL=00`) | 826 / 15 / 54 / 46 / 1 | ok ×6 | 残骸依存の裏取り |
| 同 0xff で埋める | 812 / 29 / 54 / 46 / 1 | oob ×6 | 残骸が非 0 だと落ちる |
| **main 込み (#552 merge 済み, qstore 常設 = `qbase`)** | 828 / 13 / 54 / 46 / 1 | ok ×6 | base 比 oob→ok 7 (58–63, 87), oob→halt0 1 (56), halt0→ok 3, **ok 退行 0** (G11–G13) |

結論: **58–63 は #552 (merge 済み, `191ed7b`) で解消済み** (qstore 有りの既定構成で ok, G13)。本 PR は同じ修復を重複して入れない。mask は同じ効果を C 側で出す代替案だが、#552 は IR 側で 279 site を直すため不採用。

### unit 56 (別原因, 本 PR では未修復)

main (#552 込み) でも 56 は halt0: `8c5eb0`→`8c67a0`→`8c7c80`→`8c7710`→`8cbde0` (GetItem) の「キー未発見」→`411e80`。`8cbde0` 先頭の probe は key=`0x10b698c0` (heap のオブジェクト) で、辞書のキーは TClass。
`8c7710` の機械語は `rax=[arg2]` (オブジェクトの VMT=TClass) を `8cbde0` の key にするが、IR は `arg2` をそのまま渡す (**D4 型: 1 段 deref 脱落**)。
実験 (`m11_ov.c` に `function_8c7710(self,obj){return function_8cbde0(Q(self+0x410), Q(obj));}` を足す, main (#552 込み) 上, 一回きりで `negctl_594.sh` には含めない): 56 が halt0→oob (最上位 `8c5eb0`) に進むだけで ok は 828 のまま、他 unit の差分 0。
→ 次の欠陥は `8c5eb0` (`8c67c0` の戻りへの書込み等, 未調査)。採用せず、起票 (§6)。

## 4. 副次的な発見: `survey_units.mjs` の oob は最上位 frame を捨てる

oob の `frames` は `.slice(1)` で先頭 frame を落とす (REPORT_495 §の「疑い」)。実測: unit 56 の生スタックは `function_417b70, function_417fc0, function_8cbb00, …`、survey JSON は `function_417fc0, …`。
`annotate.py` の「最上位 frame `function_417fc0` ×7」は実際には `function_417b70` ×7 (1 段上を数えている)。**疑いは確定**。本 PR では直さない (直すと全 oob の frames が変わり `survey_diff.py` の基準が動く, 起票 §6)。

## 5. 再現 + ネガコン + gate

```sh
FL_WIN64_DIR=<fl-win64 の展開先> bash tools/m11/trap_triage/negctl_594.sh   # 前提: work/ に work-m11, PE (extracted/block00031_PE.bin), capstone/pefile。欠ければ exit 1 (fail-closed)。全 3 構成 (base / qbase / qprobe) を survey し G11–G13 を判定 (G1–G10 は #1041 で廃止, §7)。1 つでも FAIL なら exit 1
```

| gate | 内容 | 結果 (現行 gate。測定値は §7) |
|---|---|---|
| G1–G10 | (廃止。定義・外す理由・復活条件は §7) | 廃止 (#1041 PM 判断 (b)) |
| G11 | [qstore あり] qstore 適用 site 数 = 前提の検出数 (pristine) | §7 |
| G12 | [qstore あり] probe と qbase の kind 差 0 (probe 透過) | §7 |
| G13 | [qstore あり] 58–63 が ok | §7 |

実測 (HEAD `c26b41d`, 4 vCPU runner, 1 回目, PE 展開済み): 全体 **4 分 29 秒** (`real 4m29.328s`)、survey 1 回 13.8–21.2 秒、load average (1 分値) 1.07–1.57、直列。SUMMARY ALL PASS、exit 0。
旧版 (qstore 無しのみ, 7 構成, G1–G10) の計測は 2 分 44 秒。現版との比較ではない。
`gate` は FAIL で `exit 1` (終了時に `m11_ov.c` 由来の `ov.o` を再生成)。

### 6-1. 2 回目の実測 (main `d7cf3c77f94050d705d5718e87431240fce392e7` 上で計測, 素材を展開し直し, `m11_gen_ir2.sh` で ir_conditions.json を作成)
- 前提 (qstore 検出 pristine) = 279 site、survey 1 回 6.4–7.5 秒、load 0.59–0.94、全体 175 秒、exit 1。
- SUMMARY: FAIL (G1, G5, G8, G10, G12)。SUMMARY の行まで出力される (fail-closed は機能)。
- 原因 (実測): main の ldfix 適用済み IR では、qstore 無し (`M11_QSTORE=0`) の base で 58–63 が既に `ok` (base の oob 19 = 87,144,149,158,275,280,304,477,484,492,513,520,555,659,745,830,880,898,923)。
  unit 56 は `other` (`function_8c5eb0` の unreachable)。`8cc190←8c7a10` 系 OOB は base で n=0。
  よって G1/G5/G8/G10 の前提 (base で 58–63 が oob) は main の ldfix 適用後の IR では成立しない。ldfix 版 IR の残す 58–63 修復を外す ldfix=disabled 比較は、build 拒否 (`ldfix=disabled` は fail-closed) のため未測定。
- G12 は probe 透過で差 2 件 (304, 555 が oob→ok)。probe の追加で trap の出方が変わる = probe は透過でない。
- ゲートの期待値は緩めていない。ゲート判定の修正は未実施 (前提の作り直しは子 issue #1041)。
- 現状の期待結果は FAIL (exit 1)。`negctl_594.sh` ヘッダにも同じ内容を書いた。

### 6-2. 既知の制約
- `m11_e2e.sh` の全再生成経路 (lift_pe.sha256 無し) は `m2/work/ghidra_dll/functions_dll.csv` を要求する。runner に Ghidra が無いため `m11_bounds` が fail-closed で止まる。units_run (`m11_e2e.sh` 全体) はこの経路では未測定。子 issue #1042。

### 6-3. #1041 での実測 (main `dc7c11df`・ldfix 有無の 2 状態)
- ldfix=applied (`m11_gen_ir2.sh` rc 0, 43 秒): base (qstore 無し) の oob 集合を再測定し §6-1 と一致。
- ldfix=disabled (`M11_LDFIX=0 m11_gen_ir2.sh` rc 0, 9.6 秒): `m11_build.sh` は `ldfix=applied` 以外を拒否する (line 43) ため、一時コピーで**この 1 行だけ外して**リンク (rc 0, 12.5 秒)。survey (1 回, 12.2 秒): 58–63 は全て ok、56 は other。**58–63 について**は ldfix の有無で状態は変わらない。一時コピーは削除済み・commit していない。
- 未解決 (起票先 #1041): oob 集合は ldfix の有無で変わる。applied にあって disabled に無いのは 144、disabled にあって applied に無いのは 895 (共通は 18 件)。58–63 の結論には影響しないが、この 144 ↔ 895 の差の原因は本 REPORT では未調査。
- `negctl_594.sh` を HEAD で foreground 実行: **exit 1**、所要 **4 分 35 秒** (`real 4m34.926s`)、survey 1 回 12.1–13.1 秒、load 0.87–1.17、SUMMARY FAIL (G1, G5, G8, G10, G12)。FAIL の内訳: G1 n=0 (期待 7)、G5 oob→ok 0 件、G8 maskneg の 58–63 が ok、G10 fillff の 58–63 が ok。G12 は probe 透過差 2 件 (304, 555 が oob→ok)。
- 判断: base で 8cc190 系の OOB が 0 件のため、mask 実験は救済する対象を持たない。G1/G5 の前提を満たす IR 状態は、本 main では再現できない。gate の期待値は緩めていない。
- 再設計の判断 (期待値を残すか・gate を廃止するか・8cc190 系の別の再現源を使うか) は PM 判断。下記 §6 の表 #1041 行の解消は未了。

### 6-4. #1041 受入 1: ldfix=disabled の測定経路 (拒否を外さず既存 opt-in で測る)
- 経路: `trap_triage/measure_ldoff_594.sh`。`M11_LDFIX=0 m11_gen_ir2.sh` → `M11_ALLOW_LDFIX_DISABLED=1 M11_QSTORE=0 m11_build.sh` → `survey_units.mjs`。
  `m11_build.sh` の拒否 (#680) は外していない。opt-in は #1165 で既に存在し、§6-3 の「一時コピーで拒否を外した」手順は不要だった。
- 測定: 検証 HEAD `8483b900` (origin/main)。IR は ldfix=disabled、build は `M11_QSTORE=0` (qstore 無し = base)。
  gen 7.8 秒 (rc 0)、build 22.1 秒 (rc 0, `wasm-ld signature mismatch: 0, undefined symbol: 0`)、survey 9.4 秒 (rc 0)、load 0.72–0.98。
  kind: 56=other、57–63=ok (**58–63 は全て ok**)。SURVEY `ok=867 oob=18 halt0=8 miss=47 other=1 noproc=1`。
- 結論: 58–63 は ldfix の有無で ok のまま (§6-3 と一致)。ldfix=disabled を測る正式な手順が確定した。
- 同じ HEAD で `negctl_594.sh` を foreground 実行: rc 1、**3 分 47 秒** (`real 3m47.164s`)、survey 9.2–10.3 秒、load 0.85–1.09。
  SUMMARY FAIL (G1, G5, G8, G10, G12)。§6-1 / §6-3 と同じ FAIL 集合。期待値は変更していない (受入 2 は PM 判断待ち)。

## 6. 検証範囲 / 範囲外 / 未解決

範囲: `m11_ov.c` + `work-m11` スナップショットの survey 942 unit を、qstore 無し (`M11_QSTORE=0`) と qstore 有り (main の既定) の両方で測定。範囲外: `m11_e2e.sh` 全体 (units_run は未測定)、`M11_OV_CLASSCREATE` (#419 / PR #446 の opt-in。main に無いため対象外)。
PE (`extracted/block00031_PE.bin`) と capstone/pefile が無い環境では qstore が skip され、既定構成の数値が変わる。gate はその場合 exit 1 する。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (解決) 58–63 の修復 (qstore) は #552 として main に merge 済み | main で 58–63 は ok (G13) | — |
| (解決) negctl 前提の再設計: 前提が成立しない G1–G10 を廃止し G11–G13 のみ残す | 旧 gate の FAIL 集合 (G1/G5/G8/G10/G12) は消えた (§7) | #1041 (M11-N59) |
| units_run 測定経路 (`functions_dll.csv` の入手) | `m11_e2e.sh` 全体が未測定 | #1042 (M11-N60) |
| unit 56: `8c7710` の D4 型 deref 脱落は #662 (closed)。`8c5eb0` の 0 件ガードは #717 (merged) で IR に復元。残る fail-fast の到達可否 | 56 の未解決部分 | #856 (M11-N36, open) |
| `survey_units.mjs` oob の `.slice(1)` (§4 は c26b41d 時点の記述) | 現 main の `survey_units.mjs:74` は `.slice(0, 30)` で先頭 frame を残す (#663 closed) | #663 (closed) |
| `alloca/REPORT.md` §6 / `m11/REPORT.md` の「上流 8c5cc0 のポインタ破壊」帰属は誤り (本 REPORT §2) | 調査の誤誘導 | 本 PR で REPORT_594 を索引に追加。元 REPORT の訂正は PM 判断 |

## 7. #1041: gate の再設計 (PM 判断 (b))。G1–G10 を廃止し、G11–G13 を残す

- **判断**: #1041 の PM 判断 (2026-10-15)。受入 2 は期待値を緩めず、前提が main で成立しない gate を外して満たす。別 fixture への移植 (a) は採らない。
- **外す理由**: §6-3 のとおり、ldfix 適用済み main の IR では qstore 無しの base でも 58–63 は既に ok。G1/G5/G8/G10 の前提 (base で 58–63 が oob) が成立しない。G2・G3・G4・G6・G7・G9 は同じ base 構成 (または base 構成の probe・mask・fill) に依存するため、同時に外す。
- **廃止した gate** (旧版: 基準 commit `fc3883358` (origin/main) の `negctl_594.sh`。旧版の HEAD 実測の FAIL 集合は G1/G5/G8/G10/G12):

| gate | 旧定義 | 復活条件 |
|---|---|---|
| G1 | [qstore 無し] base の `8cc190←8c7a10` 系 OOB = [56, 58–63] | base で 8cc190 系 OOB が再び現れ、その集合を確定できた時 (再定義して新 gate にする) |
| G2 | [qstore 無し] 決定性: base と base2 の kind 完全一致 | base 構成を gate に戻す時 |
| G3 | probe (qstore 無し): 辞書 self / FComparer が各 1 種、Add ≥ 64 回 | probe 観測を gate に戻す時 |
| G4 | probe (qstore 無し): cnt==cap==0x40 の Grow を観測 | 同上 |
| G5 | [qstore 無し] mask: 58–63 が oob→ok | base で 58–63 が oob に戻る時 (救済対象が生まれる) |
| G6 | [qstore 無し] mask: ok 退行 0 | 同上 |
| G7 | ネガコン: mask 値を全 bit 1 にすると base と kind 完全一致 | 同上 |
| G8 | ネガコン: 同構成で 58–63 は oob のまま | 同上 (旧版の FAIL 集合に含む) |
| G9 | [qstore 無し] fill00: 58–63 が ok | base で 58–63 が oob に戻る時 |
| G10 | [qstore 無し] fillff: 58–63 は oob のまま | 同上 (旧版の FAIL 集合に含む) |

- **除いた構成**: base2 / probe (qstore 無し) / mask / maskneg / fill00 / fillff。**残した構成**: base (遷移 info の基準のみ。gate には使わない) / qbase / qprobe。
- **残した gate** (判定は G11–G13 だけ): G11 qstore 適用 site 数 = 前提の検出数 / G12 probe 透過 (qprobe と qbase の kind 完全一致) / G13 58–63 が ok (qbase)。
- **旧 G12 の失敗の訂正 (§6-1・§6-3)**: 旧版は qbase・qprobe の前に IR と指紋を戻さなかった。直前の qstore 無し build が後処理 (alloca 等) を加えた IR に qstore を重ねていて、main の build 順 (qstore → alloca) と違っていた。現版は構成ごとに pristine IR と `ir_conditions.json` を対で戻す。`m11_build.sh` は後処理の結果を指紋に記録するため、IR だけ戻すと指紋検査 (`--check`) で拒否される。この修正で G12 の差は 0。したがって §6-1・§6-3 の「304・555 が oob→ok」は probe 非透過の確証としては扱わない (単発の実測で、probe 透過の一般的な証明ではない)。
- **実測 (測定 commit `5dd9edf8f`、HEAD で foreground 実行)**: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/trap_triage/negctl_594.sh` → **rc 0、SUMMARY ALL PASS**、`real 3m5.368s`。load (1 分値) は開始 0.14 → 終了 1.02、各 survey 中 0.81〜1.06。survey 1 回 13.1〜13.3 秒。
  - 前提: qstore 検出 (pristine) = 279 site。G11 applied = 279 (PASS)。G12 qprobe と qbase の kind 差 0 (PASS)。G13 58–63 は全て ok (PASS)。
  - survey: base (qstore 無し) ok 870 / miss 47 / oob 17 / halt0 7 / noproc 1。qbase (main 既定) ok 873 / miss 47 / oob 14 / halt0 7 / noproc 1。qprobe は qbase と同一。base→qbase は oob→ok 3、oob→halt0 0、halt0→ok 0、ok 退行 0。8cc190←8c7a10 系 OOB は qbase で 0 件。
  - 1 回目の試行 (指紋を戻さない版) は qbase の link で `ir_conditions.json` の指紋不一致により停止した。この修正を測定 commit に含めた。測定は単発 (同一 HEAD の 1 回)。
- **戻し方**: 本 PR を revert する (変更先は `tools/m11/trap_triage/negctl_594.sh` と本 REPORT の §5・§6・§7)。旧版の gate を復活させるなら、上の「復活条件」が成立した時点で `git show fc3883358:tools/m11/trap_triage/negctl_594.sh` から該当 gate を戻す。
