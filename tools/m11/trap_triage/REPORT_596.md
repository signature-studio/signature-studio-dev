# #596: OOB 他分類の最上位 frame・原因と #307 (LD-7) の OOB との突合

**判定: 受入条件 1 は部分達成 (全 21 unit を最上位 frame で分類、原因特定は一部のみ)、受入条件 2 は達成 (同じ定義で数値突合)。Closes しない (Refs #596)。**
検証起点 = `0865903` (main)。変更はすべて `tools/m11/trap_triage/` の診断ツール追加で、`m11_ov.c`・IR・survey の判定は不変。
既知類型との関係 (`docs/DEFECTS.md`): 4f9f40 系は **該当なし** (レジストリ TList の items が壊れる = 書込み側の別症状。D4/D15 かは未確認)。`414ad0` 系 4 unit は #307 §9 の「入口 rcx の `[rbx]` 1 段 deref 脱落」と**同じ欠陥** (§4 で IR を突合)。

## 1. 前提の訂正: OOB は 44 ではなく 21

#419 / PR #446 の「OOB 44」は #414 HEAD `fa918df` 時点の値。現 main (`0865903`) を work-m11 から build し直した survey は
`ok 818 / halt0 56 / miss 46 / oob 21 / noproc 1` (942 unit。`m11_build.sh` 13.2 s → `survey_units.mjs` 16.2 s、load average 1.0〜1.2、1 並列)。
#446 で挙がった 410730 ×6 / 904190 ×4 / 47d460 ×4 / 409470 ×4 は、現 main では **oob ではない** (410730 と 47d460 は 0 unit、904190 は 1 unit、409470 は 0 unit)。

## 2. 最上位 frame の再集計 (`oob_top.mjs`)

`survey_units.mjs` は非 halt0 の frames を `.slice(1)` し **最上位 frame (実際に trap した関数) を落とす** (REPORT_495 §7 の疑いを実測で確認)。
`oob_top.mjs` は同じ survey を frames の先頭を残して実行する複製 (`top_off` = trap 位置の wasm offset も記録)。942 unit の kind は `survey_units.mjs` と**全件一致** (`python3 -c` で base.json と top.json の `kind` を unit 順に比較して `all(...)` = True、1 回)。

| 最上位 frame (真の trap 関数) | unit | 数 | trap 位置 (wasm offset) | 原因の状態 |
|---|---|--:|---|---|
| `417b70` ← `417fc0` ← `8cbb00` ← `8cbcb0` | 56 58 59 60 61 62 63 | 7 | 0x354227 | 既知 (REPORT_483 §4b: `8cbb00` SetCapacity が IR のまま。`exp8cbb00` で ok、採用は PM 判断)。旧表の「`417fc0` ×7」は 1 段上 |
| `4f9f40` ← `4f9ff0` ← `4faae0`/`4fad10` ← `4fb910`/`4fb8a0` | 291 296 304 555 923 | 5 | 0x193d4f / 0x193cc3 | **§3 で一部特定**: レジストリ (`[0x11f26a0]`) の TList の items 配列が破損 |
| `414ad0` ← `414bb0` ← `652500` ← `653660` | 149 158 280 659 | 4 | 0xbc575 | **§4**: `414ad0` 自身の `[arg1]` deref 脱落 (#307 と同一欠陥)。加えて `652500` が rcx=0 で呼ばれる別の観測 |
| `418190` ← `59f9a0` | 87 | 1 | 0x353397 | 既知 (REPORT_483 §4b: #411 の `418190` 転記との組合せ) |
| `47ad70` ← `536da0` ← `4fe150` ← `5d2680` | 95 | 1 | 0x18f8d3 | 未特定 (§5) |
| `864fe0` ← `80e040` ← `80e140` | 275 | 1 | 0x935b7 | 未特定。`80e040` が rcx=0 で入る (§5) |
| `903d20` ← `904190` ← `abfd60` | 477 | 1 | 0x2775b0 | 未調査 |
| `40ff70` ← `40ffe0` ← `60a270` | 895 | 1 | 0x149cad | 未調査 (`[rax-0x90]` の deref。VMT 走査の `FindMethod` 系と推定) |

分母 = survey の `kind=oob` 21 unit。数え方: `oob_top.mjs` の JSON の `frames[0]` を集計 (`annotate.py` は `frames[0]` を使うので、同じ JSON を食わせると旧基準 = 1 段上の表になる)。

## 3. 4f9f40 系 (5 unit): レジストリ TList の items 配列が shadow stack を指す

機構 (機械語と実測):
- `4faae0` / `4f9f40` は `[[g+8]+0x10]` (Count) と `[[g+8]+8]` (items 配列) を読む TList 走査。`g = [0x11f26a0]` (LVA、グローバルのレジストリオブジェクト)。
- IR の入口 probe (`probe_entry.sh`, 引数 + `[a1+8]`) で、trap 直前の `4faae0` の `[[a1+8]+8]` = `0x10a9f8e8`、`[[a1+8]+0x10]` = `0x10a9f941`。**どちらも wasm の shadow stack (0x10a9f8xx) のアドレス** (本来は heap 上の items 配列ポインタと Count)。
- 変化点の計測 (全 261 関数中 257 関数の入口で `[[g+8]+8]` を読み、値が変わった所を出力。`PROBE_WATCH=11f26a0:8:8 probe_entry.sh w2 …`): `[[g+8]+8]` は unit 45 で `0x10a9f948` (shadow stack) に変わり (直前の入口 fn = `410360` = AfterConstruction stub、直後 = `536c20`)、unit 144 で消える。
- `536c20` = TList 系のコンストラクタ (`call 0x410320` ClassCreate → `40f9e0` TObject.Create → `5373f0` で `[self+8]` に items を設定、`410360` で AfterConstruction)。`410360` (AfterConstruction) の IR は `ret arg1` だけの関数で VMT 間接 call が脱落している (#419 / PR #446 REPORT §8.2 の観測。本 run では未再確認)。直前の入口が `410360` であることと、この脱落が items 破損の原因かどうかは別 (**推定**、未検証)。
- 判定の実測: 単体 `SV_ONLY=291,296,304,555,923` は 5 unit とも **halt0 (oob ではない)**。unit 45 を前置すると 45 だけ oob に変わり、5 unit は halt0 のまま (n=1)。つまり oob になる条件は「前の unit 群が積んだ状態」。**書き込み元の関数までは特定できていない** (probe は入口単位で、関数内の書込み命令は見ていない)。

未特定: `0x10a9f948` が items として書かれる経路。次の一手は `[g+8]` への store を wasm の watchpoint 相当 (IR の store に probe) で捕える。

## 4. 414ad0 系 (4 unit) と #307 の OOB との突合

survey の 4 unit (149 158 280 659) は同じ連鎖 `414ad0 ← 414bb0 ← 652500 ← 653660 ← 6539e0`。trap 位置 wasm offset 0xbc575 は IR `dec_label_pc_414b6c` の `load i32, ptr (%37 - 4)` (`%37 = arg2 & 0xffffffff`)。
機械語 (`414b64: mov rax,[rbx]` → `414b6c: mov r13d,[rax-4]`) は `[arg1]` を 1 段 deref して**文字列本体**の長さを読むが、IR は deref を落とし **長さ引数 (`arg2`)** を本体ポインタとして `[arg2-4]` を読む。probe の入口値は `414ad0(a1=0x10a9f8e8, a2=2)` で、`[2-4]` = 負アドレスの読出し → OOB。
= **#307 §9 (`414ad0` の `[rbx]` deref 脱落、IR の `%arg1` を ptr とする load 0 件) と同一の欠陥**。#307 の 68 関数と m11 の 4 unit は同じ `414ad0` を別経路から踏んでいる。
別の観測: `652500` が全 4 unit で rcx=0 (arg1..4 = 0 0 0 0) で呼ばれる (`653660` の引数は `264208` 等の正常値)。`652500` の IR が呼出側から引数を受けていない疑いだが、`653660` の機械語と IR の call は未突合 (**推定**)。`414ad0` の deref 脱落を直せばこの 4 unit の OOB が消えるかは未検証 (`414ad0` の転記は未実施)。

#307 (LD-7) との突合 (比較軸を揃えた数値、`oob_cross307.py`):

| 軸 | #307 liftdiff | 本件 m11 survey |
|---|---|---|
| 対象 | 関数単位。batch 7421 行のうち「最初の `wasm_trap` case が OOB」の関数 **239** (#307 の 222 とは数が違う。差の原因は未調査: 同じ `oob_414ad0.py` の定義で現 jsonl を数えると `414ad0` は 68 で一致し、全体は 239) | unit 単位 (InitUnits の 942 unit)。`kind=oob` **21** |
| 最上位 frame の種類 | 84 | 8 |
| `414ad0` | 68 関数 | 4 unit |
| `40ff70` | 2 関数 | 1 unit (895) |
| 他の 6 種 (`417b70` `4f9f40` `418190` `47ad70` `864fe0` `903d20`) | **0 関数** | 15 unit |

- survey の最上位 frame 8 種のうち liftdiff にも現れるのは **2 種 (`414ad0` `40ff70`) のみ**。#446 §6.3 の「同一欠陥の別症状の可能性が高い」は **`414ad0` について成立** (同じ関数・同じ deref 脱落で OOB。IR 突合は上記)。残りの 15 unit は #307 の OOB と**重ならない**。
- liftdiff は関数を単体 (state auto / 合成入力) で動かすため、survey の「前の unit が積んだ状態」依存の OOB (4f9f40 系) は出ない。逆に liftdiff の 68 件の `414ad0` は合成引数 (`q0` `p1` 等) 由来で、survey では 4 unit しか到達しない。
- 検算 (別アルゴリズム): `--verify` は jsonl を JSON パースせず raw 文字列走査で「最初の `wasm_trap` の後 400 字以内に OOB 文字列」を数え、239 関数・`414ad0` 68 で正規表現版と一致。

## 5. 単発 (95 / 275 / 477 / 895) の観測

- unit 95 (`47ad70`): 直前の `536da0` に `a1=10bcc0f0 a2=10bcc6c0` で入り、`47ad70(10bb6768, 10a9f8c0)` が TList 風の `[a1]` を読む。`[a1]=0` を含む。原因は未特定 (4f9f40 系と同じ TList 破損かは未検証)。
- unit 275 (`864fe0`): `80e040` が rcx=0 で入り、`864fe0(a1=0x3069d0, …)` は `[a1]` に機械語バイト列 (`0xcb894820ec834853`) を見ている (= a1 が VA の定数 0x3069d0 = コード領域)。IR の `80e040` が入力オブジェクトを渡していない疑い (**推定**)。
- unit 477 / 895: probe 未取得 (時間切れ)。

## 6. 再現手順 (すべて `tools/m11` で。work/ = work-m11 展開済み、emsdk が要る。`capstone` は disasm_img.py 用)

```sh
bash m11_build.sh && node trap_triage/survey_units.mjs work/trap_triage/base.json   # ok 818 / oob 21 / halt0 56 / miss 46
node trap_triage/oob_top.mjs work/trap_triage/top.json                              # 同じ kind (942 unit 一致) + frames[0] = 真の trap 関数
python3 trap_triage/oob_cross307.py work/trap_triage/top.json --verify              # #307 との突合表 + 別算法検算 (不一致は exit 1)
bash trap_triage/probe_entry.sh p1 4f9f40,4faae0,414ad0,652500 [unit,...]           # IR 入口に引数 dump を入れた build で survey (終了時に元の boot.o を再生成)
PROBE_WATCH=11f26a0:8:8 bash trap_triage/probe_entry.sh w2 <fn,fn,...>              # 指定 chain の値が変わった入口を出す
```

## 7. ネガコン (実測)

- `oob_cross307.py`: survey JSON の unit 149 だけ `ok` に書換 → oob 21→**20**、`414ad0` 4→**3** (入力が結果に効く)。
- `oob_top.mjs` の frames 先頭残し: 旧 `survey_units.mjs` の `frames[0]` 集計は `417fc0` ×7 / `4f9ff0` ×5 / `414bb0` ×4 (1 段上) だが、`oob_top.mjs` は `417b70` / `4f9f40` / `414ad0` (`annotate.py` 出力と本 §2 の表を比較)。
- probe build の透過性: probe 無し (復元後) の survey JSON が `base.json` と **byte 一致** (`cmp`)。復元は `probe_entry.sh` の `trap restore EXIT`。
- **限界**: batch の 1 行 (414ad0 の 1 関数) の OOB 文字列を壊した変異では、正規表現版 (238) と raw 走査版 (238 / 414ad0 67) が**両方とも**変化し `--verify` は一致のまま。= `--verify` は「2 つの数え方が同じ入力で一致するか」を見るもので、入力の改変そのものの検出力は無い (改変の検出は上の survey 側ネガコンが担う)。
- 所要 (実測): `probe_entry.sh` 1 回 20.5 s (11 関数)〜41.2 s (36 関数。build + survey + 元 boot.o の再生成を含む `time`)。load average 0.4〜1.2、1 並列。
- 未実施: `m11_e2e.sh` 全体 (PE = fl-win64 の展開が必要。本 run は work-m11 のスナップショットで build+survey のみ)、`oob_top.mjs` の n≥3 再現 (HEAD で 1 回再実行: 942 unit の kind 一致・oob 21 unit の frames 名一致。JSON の byte 一致はしない = 末尾 frame の `oob_top.mjs:<行>:19` (ハーネス自身の行番号) が SV_WATCH 追加で動いたため。frame 名・kind は同一)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `414ad0` の C 転記 (または ldfix の `[arg1]` deref 復元) で 4 unit (149 158 280 659) が ok になるか | oob 4 unit。#307 の 68 関数も同じ関数 | 新規子チケット [M11-N27] (#307 と共通) |
| 4f9f40 系 5 unit: `[g+8]` の items が shadow stack を指す経路 (unit 45 の `536c20` 以降) の書込み命令 | oob 5 unit | 新規子チケット [M11-N26] (IR の store に probe。`PROBE_WATCH` の拡張) |
| `653660` → `652500` が rcx=0 で呼ばれる理由 (機械語と IR の call の突合) | 414ad0 を直した後に残る可能性 | 上の [M11-N27] に併記 |
| 95 / 275 / 477 / 895 の個別原因 (各 1 unit) | oob 4 unit | #596 にコメント (本 REPORT §5) |
| `8cbb00` (7 unit) の採用可否 | oob 7 unit | REPORT_483 §6 の既存起票先 |
| `survey_units.mjs` の `.slice(1)` を直す (oob の frames 基準が 1 段変わる) | `annotate.py` / `survey_diff.py` の基準変更 | PM 判断 (#495 の既起票) |
