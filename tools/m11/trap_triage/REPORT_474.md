# #474: 410320 補完後に unit 114 でハングする原因 (5c00e0 のリスト循環) と修復

**判定: 受入条件 3 件すべて達成。** 検証起点 commit `1bf4ce3` (base = #444 の `93a11c8`)。
**issue の仮説 (InitInstance 0x40fb40 の転記が次の手) は原因ではなかった**: 循環の原因は兄弟関数
**`function_5c0270` (キャッシュ node の Release) の unlink が 2 箇所とも deref 脱落**していたこと。
InitInstance は 410320 が本物のオブジェクトを返すために必要だったが、ハングの有無には影響しない (§4 ablation)。

既知類型との関係 (`docs/DEFECTS.md`): 5c0270 の unlink は **D4 (DEFECTS.md)** の再発 (disp=0 の 1 段 deref 脱落)、
末尾の `call [[self]]` は **D15 (DEFECTS.md)** の再発。新規類型なし。40fb40/40f960/41c160 が closure 外だった理由も
同根 (vtable 経由でしか到達しない関数は、間接 call 全滅の結果 closure に入らない。`tools/m11/REPORT.md` §2)。

## 1. 原因 (実測)

`function_5c00e0` は `{+0 next, +8 refcount, +0xc key 先頭 qword, +0x14 hash(word), +0x18 tid(dword), +0x1c payload}` の
単方向リスト (`self+8` が head) を find-or-insert する参照カウント付きキャッシュ。`5c0270(self, node)` が Release
(refcount-- → 0 なら unlink + `424090(key)` + `call [[self]]` + `FreeMem(node)`)。

| 観測 (410320 補完版 = §4 の `no5c0270` 構成, 最小集合 {1,17,45,95,114}) | 値 |
|---|---|
| `5c00e0` 7 回目の node 確保 (`409410`) が 1 回目の node と**同一番地** | 1 回目の node は `5c0270` で FreeMem 済 (呼出鎖 `5c0270 ← 5c03d0 ← 5c0fc0 ← 5c1360`) |
| 8 回目の走査で循環 | `head → … → node[5].next == head` (node[5] は rc=0, 解放済 node の旧番地を指したまま) |

原因は IR (`boot_final3.ll` の `function_5c0270`) の 2 箇所 + 1 脱落:

| 機械語 | 本来 | RetDec 出力 |
|---|---|---|
| `5c02fe mov rcx,[rcx]` (= node.next); `5c0301 mov [self+8],rcx` (node が head) | `head := node.next` | `store %arg2, [self+8]` (`head := node` 自身) |
| `5c032c mov rcx,[rcx]` (= node.next); `5c032f mov [prev],rcx` (前任走査後) | `prev.next := node.next` | `store %arg2, [prev]` (`prev.next := node` 自身) |
| `5c037e call [rbx]` (vmt slot 0, 解放フック) | 呼ぶ | 脱落 |

→ 解放した node を指す stale ポインタがリストに残り、同じ番地が再配分されると循環する。
410320 が TClass 自身を返していた間はオブジェクトが生成されず、この Release 経路が実行されなかったため表面化しなかった。

## 2. 修正 (`tools/m11/m11_ov.c`, 逆アセンブルと突合した C 転記)

| 関数 (VA) | 内容 |
|---|---|
| `function_5c0270` | Release を転記 (unlink の `[node]` deref 復元, `call [[self]]` を `m11_icall` で復元)。node 不在時の走査は null で打ち切る |
| `function_40fb40` InitInstance + 入れ子 `40fac0` (`ov_initinst_nested`) | FillChar(InstanceSize) / vptr / 親クラスを辿る IntfTable の VTable 設定 / tkMRecord (0x16) の `417150` 呼出 |
| `function_40f960` | TObject.NewInstance (`GetMem(InstanceSize)` + InitInstance) |
| `function_41c160` | TInterfacedObject.NewInstance (`40f960` + `FRefCount := 1`)。無いと 2 unit (42, 45) が ok→miss |
| `function_410320` | `_ClassCreate`: `m11_icall([self-0x30], self)` (vmtNewInstance を復元) |
| `function_409470` | ReallocMem (#418 の試作を再採用) |
| `disp_find` | closure 外で C 転記した `40f960` / `41c160` / `5c04a0` (`ret` 1 命令) を icall から解決する追加 switch |

`40fb40` は survey 中 18405 回呼ばれ、うち IntfTable 経由の vptr 設定は 55 回、tkMRecord (`417150` 呼出) は 0 回。
(計測: 一時的に `fprintf` を入れた ablation コピーの `[probe]` 行を集計。コミットには含めない。)

## 3. 検証 (コミット済み HEAD `1bf4ce3`, `bash tools/m11/m11_build.sh` + `node tools/m11/trap_triage/survey_units.mjs`)

分母 = 942 unit。`trap` = oob + halt0 + abort。`miss`/`noproc` は trap に含めない。ビルドは wasm-ld signature mismatch 0 / undefined symbol 0。

| 構成 | ok | oob | halt0 | abort | miss | noproc | trap | 所要 (min–max) | load (1 分値) |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 転記なし (#444 HEAD `93a11c8`) | 830 | 44 | 20 | 1 | 46 | 1 | **65** | 0.4–0.5 s (n=3) | 未記録 |
| **本 PR** | **839** | 24 | 32 | 0 | 46 | 1 | **56** | 5.98–6.02 s (n=3, 全回同一結果) | 0.55–0.62 |

受入条件 2 の閾値 (ok 829 以上 / trap 66 以下) は、issue 記載の snapshot (829/66) でも本 runner の snapshot (830/65) でも満たす。
unit 単位の遷移 (`survey_diff.py` で `93a11c8` 版 JSON と突合。SURVEY_UNITS の行とは別の集計):

| 遷移 (転記なし → 本 PR) | unit 数 |
|---|---:|
| ok→ok | 830 |
| oob→ok | 8 (884 を含む) |
| halt0→ok | 1 |
| abort→halt0 (114) | 1 |
| oob→halt0 | 12 |
| halt0→halt0 / oob→oob / miss→miss / noproc→noproc | 19 / 24 / 46 / 1 |
| **ok→非 ok (回帰)** | **0** |

- 受入条件 1: 最小集合 `SV_ONLY=1,17,45,95,114` は 0.34–0.36 s (n=3, load 0.15) で完走し ok 2 / oob 2 / halt0 1
  (#444 の構成は `timeout 10` でも終わらない)。`chk_5c00e0.c` で `5c00e0` を転記 + Floyd 循環検出に差替えて全 survey を実行:
  **5c00e0 呼出 18 回, 最長走査 9 step, CYCLE 0 件**。
- `SV_ONLY=884` 単独は転記なし構成も本 PR も OOB (#418 の記録と同じ)。unit 順実行 (全 survey) では ok。単独実行は先行 unit の状態に依存する。

## 4. ネガコン (`bash tools/m11/trap_triage/negctl_474.sh`, 1 構成ずつ転記を外して全 survey, ハング判定 30 s)

| 構成 (外すもの) | 結果 | 判定 |
|---|---|---|
| `no5c0270` | **ハング (timeout 30 s)** | **ハング復帰** (受入条件 3) |
| `chkneg` (`no5c0270` + 循環検査) | CYCLE 検出 2 件 (call#8, #9)。node[5] (rc=0) の next が head を指す | 原因の直接証拠 |
| `no410320` (409470 は有り) | ハング (timeout 30 s) | #418 の症状の再現 |
| `no409470` | ok 835 / oob 40 / halt0 20 | 409470 は ok +4 / oob −16 / halt0 +12 を担う |
| `noinitinst` (FillChar + vptr のみの試作版) | ok 839 / oob 24 / halt0 32 (本 PR と同一) | **InitInstance の詳細実装は survey 結果を変えない** |
| `chk` (本 PR + 循環検査) | 本 PR と同一結果, CYCLE 0 | — |

`noinitinst` が本 PR と同一な理由は未調査 (推定: IntfTable の vptr 設定後に呼ばれる interface メソッドが closure 外で、`m11_icall` が miss/0 を返すため差が出ない)。
`40fb40` の忠実転記は正しさのために入れたが、ハング解消の因子ではない。

## 5. 検証範囲 / 範囲外

- 範囲: survey (942 unit を各 1 回, 先頭から順に実行) の分類と、`5c00e0` 呼出 18 回での循環の有無。
- 範囲外: `M11_LB_BASE != 0` のビルド (転記は LVA 座標のみで書いたが未実行)、`m11_e2e.sh` (PE を要するため runner では #444 同様に
  既存 work スナップショットで build + survey のみ実行)、tkMRecord 経路 (`417150`) の実行 (survey で 0 回)。
- 本 runner の `work-m11` スナップショット (2026-10-10 生成) の ok 830 と #414 本文の 829 の 1 unit 差は未確認 (#444 と同じ)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `5c03d0` の `call [rbx+0x18]` (node 差替え時の通知, `5c0437`) が脱落したまま | node が変わるときの通知が無い。survey の分類には現れない | 新規子チケット (M11, D15 の closure 内全数と同時) |
| oob→halt0 の 12 unit (うち 11 は `411d20 ← 411e80 ← 8cc190` = unit 53–63 のうち 9 と 307・311, 残り 1 は 898 の `40a1c0`) の Error() 原因 | 上流 `8cc190` の OOB が Error に変わっただけで trap は減っていない | #447 の `411d20` 系 (halt0 6) と合わせて新規子チケット |
| 本 PR 後の trap 56 (#130 の完了条件 < 20 は未達) | #130 の完了条件 | #130 / #447 に実測を追記 |
| `5c0270` の D4 脱落が `boot_final3.ll` に残っていた (`tools/m11/ldfix` が適用済みかは未確認) | 同型の脱落が closure 内に他にもある可能性 | 新規子チケット (ldfix の検出漏れ全数) |
| #447 (`417-halt0-residual`) との併用 | `git merge-tree` で `m11_ov.c` に conflict なし (実測)。併用時の survey は未実行 | PM のマージ後に再実行 |

DEFECTS.md 行案: 新規類型なし。D4 の観測例に「`5c0270` (Delphi 参照カウントキャッシュ Release): unlink の `mov rcx,[node]` 脱落 →
解放済 node を指す stale ポインタ → 同番地の再配分でリスト循環・無限ループ (silent hang)」を足す (編集は PM 判断)。

## 7. 再現手順

```sh
cd tools/m11   # work/ = work-m11 展開済み。emsdk (/opt/emsdk) が要る。disasm_fn.py は capstone/pefile (pip) と LD_M11_PE が要る
bash m11_build.sh && node trap_triage/survey_units.mjs work/after.json            # 本 PR: ok 839 / trap 56
python3 trap_triage/survey_diff.py <転記なし survey.json> work/after.json 884 114   # 遷移表と ok 退行 unit
SV_ONLY=1,17,45,95,114 timeout 10 node trap_triage/survey_units.mjs /dev/null    # 最小集合 (完走)
bash trap_triage/negctl_474.sh [head full no5c0270 chk chkneg ...]                # ablation + 循環検査 (終了時 ov.o を再生成)
```
