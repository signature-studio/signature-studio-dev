# MX-58 (#5399) 付録: pdata_call 残 mismatch の判定 (REX 直後 F0・capstone 不正)

本付録は `REPORT_MX25.md` §5.5・§5.7 の残件を判定した記録。親 issue は #4981 (受入 1 の残り)。
REPORT_MX25 の本体は上限直前のため、判定の正本はここに置く。

## 1. 結論

- 未分類 (mismatch 24) は **全件を理由別に分類した** (§3)。内訳は REX 直後 F0 17 件 (REX→F2→F0 1 件を含む)・capstone 不正 6 件・`(bad)`/rex2 1 件。
- **REX 直後 F0 の正否は「未確認」のまま**。SDM Vol.2 §2.2.1 (REX 節) の本文を取得できなかった。
- 実機 (AMD EPYC 9V74) では、REX 直後の F0 は #UD にならず、REX.W も無視された (§2)。これは `mx_closure.py` の規則 (REX→F0 は #UD) と合わない。ただし Intel の挙動とは別の可能性があり、規則変更の根拠としては扱わない。
- `mx_closure.py` の規則・既定 `ENTRY=any` は変えていない。規則を変えると pdata_call の入口数が変わるため、SDM 本文の取得後に別 PR で判断する。

## 2. 実機観測 (`scripts/mx58_rex_probe.py`)

測定 commit: `097da5a69` (origin/main)・作業は `ws-5399`。CPU: AMD EPYC 9V74 80-Core Processor (x86_64)。
関数 `void f(u64 *p, u64 v)` を mmap の実行可能領域に置き、`mov rax, rsi` の後に `add [rdi], eax` (01 07) / `add [rdi], rax` を実行。初期値 `*p = 0x1_FFFFFFFF`, `v = 1`。

| ケース | 命令列 | rc | 結果 | 解釈 |
|---|---|--:|---|---|
| nolock_plain | `01 07 c3` | 0 | `0x1_00000000` | 32 bit 加算 (基準) |
| lock_plain | `f0 01 07 c3` | 0 | `0x1_00000000` | LOCK の効果は値に出ない (基準) |
| lock_then_rexw | `f0 48 01 07 c3` | 0 | `0x2_00000000` | 64 bit 加算 (REX.W が効く) |
| rexw_then_lock | `48 f0 01 07 c3` | 0 | `0x1_00000000` | REX.W が効かず 32 bit 加算 |
| rex_then_lock | `40 f0 01 07 c3` | 0 | `0x1_00000000` | SIGILL なし |
| rexb_then_lock | `41 f0 01 07 c3` | 0 | `0x1_00000000` | SIGILL なし |
| rexw_f2_lock | `48 f2 f0 01 07 c3` | 0 | `0x1_00000000` | SIGILL なし |
| rex_f2_lock | `40 f2 f0 01 07 c3` | 0 | `0x1_00000000` | SIGILL なし |
| rexw_f3_lock | `48 f3 f0 01 07 c3` | 0 | `0x1_00000000` | SIGILL なし |

読み取り: REX の直後に F0 が来ても、この CPU では #UD にならない。REX.W は直後の F0 があると効かなくなる (`48 f0` で 32 bit 加算)。
つまり REX は F0 の直後で無視されている、と見られる。ただし Intel の仕様そのものを示すものではない。

## 3. mismatch 24 件の理由別分類 (測定 commit `097da5a69`)

検算 `mx_flow_recheck.py` (`cl_sets.pkl` + `cl.json` + PE) の出力: BFS == loop True・added 合計 一致・入口 169,752・(i) 0・(ii) 21,168・(iii) 160,259・取りこぼし 23・過剰 1・mismatch 24・RESULT=FAIL。
(前回 §5.7 の値 mismatch 26・(ii) 21,170・(iii) 160,257・過剰 3 とは一致しない。素材 md5 は一致している。)

| 区分 | 件数 | 番地 (例) | 判定 |
|---|--:|---|---|
| REX 直後の F0 (`4x f0`) | 16 | 0x1c2c150・0x1f81999・0x285b735・0x2abbe48 ほか | **未確認**。closure は #UD、objdump は受理、実機は非 #UD (§2) |
| REX→F2→F0 (`41 f2 f0`) | 1 | 0x1a2b67a | **未確認**。REP と LOCK の併用に加え REX。実機の対照は `rex_f2_lock` (非 #UD) |
| capstone 不正・objdump 受理 (`57 ff c4 62`) | 1 | 0x81a740 | 先頭 `57` (push rdi) は復号できるが、先頭ブロック内のどこかで capstone が不正 (失敗位置は未特定)。後続の EVEX `62` の形が疑わしい |
| EVEX 形 (`62 02 41 b8`) | 2 | 0x2486788・0x2486bc8 | capstone 不正 (復号不能)。objdump は受理 |
| `0f ff` (ud0) | 1 | 0x32c176a | capstone は `ud0` として受理 (#UD を示す命令)。objdump は受理 |
| 連続 REX (`4e 4e 4e …`) | 1 | 0x35cd1ff | capstone 不正・objdump 受理。REX が連続する形は SDM 上の 1 命令ではない |
| 境界ずれの疑い (先頭 `00 00 00`) | 1 | 0x2abfc59 | 途中から始まる番地。入口候補の根拠が無い |
| `(bad)`/rex2 (`02 f9 fb 46`) | 1 | 0x2470627 | capstone 受理 (`add bh, cl`)・objdump `(bad)`。表データの可能性 |

合計 16 + 1 + 1 + 2 + 1 + 1 + 1 + 1 = 24。

### 注意 (issue 本文・前回停止報告との差)

- issue 本文は「capstone 不正 6 件 (EVEX 2・`0f ff`/`57 ff` 2・連続 REX 1・REP+LOCK 1)」とする。実測では REP+LOCK の 0x1a2b67a は capstone が受理するため、capstone 不正は 5 件。残る 1 件は前回 run と同じく REX→F2→F0 として数えた。
- 前回停止報告の内訳 (REX 直後 F0 16・REX→F2→F0 1・capstone 不正 5・境界ずれ 1・(bad) 1) と本表は同じ。

## 4. 判定できない理由

- SDM Vol.2 §2.2.1 (REX 節) の本文を、この run で取得できなかった。web 検索はキャンセル、sandpile.org は本文が取れず、Intel の PDF は 403 だった (前回 run と同じ)。
- 規則番号を付けずに「正しい」と書くと推定になる。そのため REX 直後 F0 17 件は「未確認」のまま残す。
- 実機の観測は AMD の CPU で 1 機種だけ。Intel の挙動と同じとは限らない。

## 5. 残件 (追跡先)

| 残件 | 受入 | 起票先 |
|---|---|---|
| REX 直後 F0 17 件の規則番号付き判定 (SDM REX 節の本文が必要) | 1 | 本 issue #5399 (受入 1 のまま) |
| capstone LOCK 規則の残件・capstone 不正 6 件の capstone 側修正 | 1 | #4068 [MX-44] (既存の子) |
| mx_closure.py の REX 規則を変えるか | 2 | PM 判断 (SDM 本文の取得後) |
