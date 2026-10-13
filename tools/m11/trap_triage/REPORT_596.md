# #596: OOB 他分類の最上位 frame・原因と #307 (LD-7) の OOB との突合

**判定: 受入条件 1 は部分達成 (全 21 unit を最上位 frame で分類、原因特定は一部のみ)、受入条件 2 は達成 (jsonl 基準で同じ定義の数値突合。TSV 基準 222 との重なりも併記)。Closes しない (Refs #596)。**
測定基準 = `work-m11` スナップショット (IR 生成条件は未固定、#680)。**検証起点 = `97eaf2a`** (本 run の HEAD。build + survey を再実行、§7)。tools の動作は `f77f050` で最後に変更 (`probe_entry.sh` の不具合修正・`oob_cross307.py` の TSV 基準追記)。`f77f050` 以降の差分は本 REPORT の文言と `probe_entry.py` の docstring のみ。
変更はすべて `tools/m11/trap_triage/` の診断ツール追加で、`m11_ov.c`・IR・survey の判定は不変。
既知類型との関係 (`docs/DEFECTS.md`): 4f9f40 系 (5 unit のうち 291・296) は **D4 の新事例** (書込み元 `47b260` の `[rbx]`・`[rsi]` の deref 脱落。#706 で特定・修復、**未マージ**。§3)。304・555・923 は #714。`414ad0` 系 4 unit は `tools/liftdiff/REPORT_APPENDIX.md` §9 (LD-7 / #307) の「入口 rcx の `[rbx]` 1 段 deref 脱落」と**同じ欠陥** (§4 で IR を突合)。

## 1. 前提の訂正: OOB は 44 ではなく 21 (snapshot 基準)

#419 / PR #446 の「OOB 44」は #414 HEAD `fa918df` 時点の値。`work-m11` スナップショットから build し直した survey は
`ok 818 / halt0 56 / miss 46 / oob 21 / noproc 1` (942 unit。`m11_build.sh` 13.2 s → `survey_units.mjs` 16.2 s、1 並列)。
#446 で挙がった 410730 ×6 / 904190 ×4 / 47d460 ×4 / 409470 ×4 は、この snapshot 基準では **oob ではない** (410730 と 47d460 は 0 unit、904190 は 1 unit、409470 は 0 unit)。

**現 main との関係 (未解決・#680)**: 本 REPORT の「現 main」は `8d883c3` (#446 merge) 時点を指す (現 main は別時点)。#680 の記録では、work-m11 スナップショットの IR は現 main の生成手順と一致せず、IR の生成条件で `ok 818 / oob 21` ↔ `ok 828 / oob 13` が変わる。#596 の PM 追記は現 main の分母を 13 件としている。本 REPORT の 21 は snapshot 基準の値で、現 main の値ではない。差の扱いは #680 で固定する。現 main の再測は本 run では行っていない。

## 2. 最上位 frame の再集計 (`oob_top.mjs`)

`survey_units.mjs` は非 halt0 の frames を `.slice(1)` し **最上位 frame (実際に trap した関数) を落とす** (REPORT_495 §7 の疑いを実測で確認)。
`oob_top.mjs` は同じ survey を frames の先頭を残して実行する複製 (`top_off` = trap 位置の wasm offset も記録)。942 unit の kind は `survey_units.mjs` と**全件一致** (`python3 -c` で base.json と top.json の `kind` を unit 順に比較して `all(...)` = True、1 回)。

| 最上位 frame (真の trap 関数) | unit | 数 | trap 位置 (wasm offset) | 原因の状態 |
|---|---|--:|---|---|
| `417b70` ← `417fc0` ← `8cbb00` ← `8cbcb0` | 56 58 59 60 61 62 63 | 7 | 0x354227 | snapshot では oob。58–63 (6 unit) は `417b70` の `Q(a)` の D17 型 (#664 の解析) で、#552 (merged `191ed7b8`) の head で ok (#664 の記載、本 REPORT では未再測)。56 (1 unit) は別原因 `8c7710` の D4 型 → `8c5eb0` (#662)。旧表の「`417fc0` ×7」は 1 段上 |
| `4f9f40` ← `4f9ff0` ← `4faae0`/`4fad10` ← `4fb910`/`4fb8a0` | 291 296 304 555 923 | 5 | 0x193d4f / 0x193cc3 | **§3**: レジストリ (`[0x11f26a0]`) の TList の items 配列が破損。書込み元 `47b260` は #706 で特定 (未マージ) |
| `414ad0` ← `414bb0` ← `652500` ← `653660` | 149 158 280 659 | 4 | 0xbc575 | **§4**: `414ad0` 自身の `[arg1]` deref 脱落 (#307 と同一欠陥)。加えて `652500` の入口 arg1 は非ゼロ (§4 の表) |
| `418190` ← `59f9a0` | 87 | 1 | 0x353397 | 既知 (REPORT_483 §4b: #411 の `418190` 転記との組合せ) |
| `47ad70` ← `536da0` ← `4fe150` ← `5d2680` | 95 | 1 | 0x18f8d3 | 未特定 (§5) |
| `864fe0` ← `80e040` ← `80e140` | 275 | 1 | 0x935b7 | 未特定。`80e040` が rcx=0 で入る (§5) |
| `903d20` ← `904190` ← `abfd60` | 477 | 1 | 0x2775b0 | 未調査 |
| `40ff70` ← `40ffe0` ← `60a270` | 895 | 1 | 0x149cad | 未調査 (`[rax-0x90]` の deref。VMT 走査の `FindMethod` 系と推定) |

分母 = survey の `kind=oob` 21 unit。数え方: `oob_top.mjs` の JSON の `frames[0]` を集計 (`annotate.py` は `frames[0]` を使うので、同じ JSON を食わせると旧基準 = 1 段上の表になる)。

## 3. 4f9f40 系 (5 unit): レジストリ TList の items 配列が shadow stack を指す

機構 (機械語と実測):
- `4faae0` / `4f9f40` は `[[g+8]+0x10]` (Count) と `[[g+8]+8]` (items 配列) を読む TList 走査。`g = [0x11f26a0]` (LVA、グローバルのレジストリオブジェクト)。
- probe 入口値 (`probe_entry.sh p2 4f9f40,4faae0,414ad0,652500,653660`, 全 unit の `[pe]` 行 118 件): unit 291/296/304/555/923 の `4faae0` は a1 = `0x10bcc0c0`、`[[a1+8]+8]` = `0x10a9f8e8`、`[[a1+8]+0x10]` = `0x10a9f941`。**どちらも wasm の shadow stack (0x10a9f8xx) のアドレスと推定** (根拠は `m11_build.sh` の `-sGLOBAL_BASE=0x10000000 -sSTACK_SIZE=8MB` からの位置の見当のみで、stack ポインタの実測との突合は未実施)。本来は heap 上の items 配列ポインタと Count と**推定**。`a1 = 0x10bcc0c0` は非 probe の SV_WATCH で読んだ `g` (下記) と一致する。
- **値は build (probe の有無) とサンプリング点に依存する** (実測):
  - 非 probe build・unit 境界 (`SV_WATCH=11f26a0:8:8 node trap_triage/oob_top.mjs`): `g = [0x11f26a0]` は unit 46 から `0x10bcc0c0`、`[[g+8]+8]` は `0x10a9f888` で、unit 46・142〜159・290〜305・550〜556・922〜924 の全件で一定。
  - probe build・全関数入口 (`PROBE_WATCH=11f26a0:8:8 probe_entry.sh …`): `[[g+8]+8]` が `dead → 0x10a9f948` に変わるのは unit 45 内 (直前の入口 fn = `410360` = AfterConstruction stub、直後 = `536c20`)。非 probe と比べて `0xC0` ずれる。
  - **「unit 144 で `[[g+8]+8]` が消える」は非 probe build では再現しなかった** (142〜159 で `0x10a9f888` のまま)。この主張は削除した。
- `536c20` = TList 系のコンストラクタ (`call 0x410320` ClassCreate → `40f9e0` TObject.Create → `5373f0` で `[self+8]` に items を設定、`410360` で AfterConstruction)。`410360` (AfterConstruction) の IR は `ret arg1` だけの関数で VMT 間接 call が脱落している (#419 / PR #446 REPORT §8.2 の観測。本 run では未再確認)。直前の入口が `410360` であることと、この脱落が items 破損の原因かどうかは別 (**推定**、未検証)。
- 判定の実測: 単体 `SV_ONLY=291,296,304,555,923` は 5 unit とも **halt0 (oob ではない)**。unit 45 を前置すると 45 だけ oob に変わり、5 unit は halt0 のまま (n=1)。つまり oob になる条件は「前の unit 群が積んだ状態」。本 REPORT の probe (入口単位) では書込み命令までは特定できていない。

書込み元 (#706、**未マージ・本 REPORT では再測していない**): `function_47b260` (TList の Add 系, VA 0x47b260)。呼出元 `function_4f9f10` が渡す `T+8` (FItems 欄) に、呼出元 stack 局所の番地を書いていた。機械語の `mov rax,[rbx]` と `mov rcx,[rsi]` (disp=0) の deref 2 点が IR で落ちていた = D4 の新事例。C 転記で修復すると、5 unit 中 291・296 が ok (#706 の実測)。304・555 は closure 外の `function_535c2e` 呼出し (fail-fast abort、#714)、923 は `410b10` の OOB (#714)。
値 (probe build では `0x10a9f948`、非 probe では `0x10a9f888`) は build 依存。

## 4. 414ad0 系 (4 unit) と #307 の OOB との突合

survey の 4 unit (149 158 280 659) は同じ連鎖 `414ad0 ← 414bb0 ← 652500 ← 653660 ← 6539e0`。trap 位置 wasm offset 0xbc575 は IR `dec_label_pc_414b6c` の `load i32, ptr (%37 - 4)` (`%37 = arg2 & 0xffffffff`)。
機械語 (`414b64: mov rax,[rbx]` → `414b6c: mov r13d,[rax-4]`) は `[arg1]` を 1 段 deref して**文字列本体**の長さを読む。本 run で fl-win64 の PE (`block00031_PE.bin`、ImageBase `0x400000`) を `objdump -d` して、この 2 命令を確認した。IR は deref を落とし **長さ引数 (`arg2`)** を本体ポインタとして `[arg2-4]` を読む。probe の入口値 (`[pe]` 行) は unit 別に次のとおり (a2 は 4 unit とも `2`):

| unit | `414ad0(a1, a2, a3, a4)` 入口 | `[a1]` 入口 | `652500(a1, a2, a3, a4)` 入口 |
|---|---|---|---|
| 149 | `0x10a9f918, 2, 0, 0` | 0 | `0x10a9f918, 0, 0, 0` |
| 158 | `0x10a9f918, 2, 0, 0` | 0 | `0x10a9f918, 0, 0, 0` |
| 280 | `0x10a9f8d8, 2, 0, 0` | 0 | `0x10a9f8d8, 0, 0, 0` |
| 659 | `0x10a9f8f8, 2, 0, 0` | 0 | `0x10a9f8f8, 0, 0, 0` |

`[2-4]` = 負アドレスの読出し → OOB。
= **`tools/liftdiff/REPORT_APPENDIX.md` §9 (LD-7 / #307) と同一の欠陥** (`414ad0` の `[rbx]` deref 脱落。IR の `%arg1` を ptr とする load は offset 0 の `[arg1]` に限って 0 件。`arg1-8` / `arg1-4` の load は IR にある)。#307 の 68 関数と m11 の 4 unit は同じ `414ad0` を別経路から踏んでいる。
入口の `[a1] = 0` について: 機械語では `414b64` の `[rbx]` が 0 なら `je 0x414b9c` で `[rax-4]` を読まずに抜けるはず。IR はこの分岐を持たず `414b6c` を通る。ただし `414b64` 時点の `[rbx]` は実測していない (入口値のみ、**推定**)。
別の観測: `652500` の入口 arg1 は unit 別の非ゼロ値 (上表)、arg2〜4 は 0 (`653660` の arg2 は `264208` 等)。`652500` の IR が呼出側から引数を正しく受けていない疑いだが、`653660` の機械語と IR の call は未突合 (**推定**)。`414ad0` の deref 脱落を直せばこの 4 unit の OOB が消えるかは未検証 (`414ad0` の転記は未実施)。

#307 (LD-7) との突合 (比較軸を揃えた数値、`oob_cross307.py`):

**「同じ定義」は jsonl 基準で同じ定義という意味** (`oob_414ad0.py` と同じ: 関数ごとの「最初の `wasm_trap` case」が `memory access out of bounds` のもの)。
#307 本文と `tools/liftdiff/REPORT_APPENDIX.md` §8 の「OOB 222・71 種」は別の集計 `results/m11_wasm_trap_triage.md` (verdicts TSV の tags に `wasm_trap` があり、最初の wasm_trap case の kind が oob) で、batch jsonl 基準の 239 とは **別 run の結果** (REPORT_APPENDIX §8 と `results/m11_wasm_trap_triage.md` §5: wasm_trap 関数は TSV 578 / jsonl 582 で、共通 511・TSV のみ 67・jsonl のみ 71)。
TSV 基準では `414ad0` 68・`40ff70` 2 (下表) で、jsonl 基準と同じ件数。TSV 222 は jsonl 239 の部分集合 (TSV のみ 0 / jsonl のみ 17)、jsonl のみの 17 関数はいずれも TSV の tags に `wasm_trap` が無い (`oob_cross307.py` の出力)。

| 軸 | #307 liftdiff (jsonl 基準 / TSV 基準) | 本件 m11 survey |
|---|---|---|
| 対象 | 関数単位。jsonl 基準 **239** / TSV 基準 **222** (`results/m11_wasm_trap_triage.md`) | unit 単位 (InitUnits の 942 unit)。`kind=oob` **21** |
| 最上位 frame の種類 | jsonl 84 / TSV 71 | 8 |
| `414ad0` | 68 関数 / 68 関数 | 4 unit |
| `40ff70` | 2 関数 / 2 関数 | 1 unit (895) |
| 他の 6 種 (`417b70` `4f9f40` `418190` `47ad70` `864fe0` `903d20`) | **0 関数** / 0 関数 | 16 unit (7 + 5 + 1 + 1 + 1 + 1) |

- survey の最上位 frame 8 種のうち liftdiff にも現れるのは **2 種 (`414ad0` `40ff70`) のみ** (両基準で同じ)。#446 §6.3 の「同一欠陥の別症状の可能性が高い」は **`414ad0` について成立** (同じ関数・同じ deref 脱落で OOB。IR 突合は上記)。残りの 16 unit は #307 の OOB と**重ならない**。
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
SV_WATCH=11f26a0:8:8 node trap_triage/oob_top.mjs work/trap_triage/watch.json 2> watch.err  # 非 probe build で unit 境界の [[g+8]+8] を出す (`[watch]` 行)
```
`probe_entry.sh` は probe 版 build の後に元の boot.o を再生成する (trap restore)。`work-m11` 展開直後は `m11_post.py` の mtime が新しく、`m11_build.sh` が probe 版 boot.o を非 probe 版で上書きして `[pe]` が 0 件になる。本 run で `probe_entry.sh` に `touch work/boot_final3.ll` を入れて回避し、修正前 (`p1`: `[pe]` 0 件) と修正後 (`p2`: 118 件) を比べた。

## 7. ネガコン (実測)

- `oob_cross307.py`: survey JSON の unit 149 だけ `ok` に書換 → oob 21→**20**、`414ad0` 4→**3** (入力が結果に効く)。
- `oob_top.mjs` の frames 先頭残し: 旧 `survey_units.mjs` の `frames[0]` 集計は `417fc0` ×7 / `4f9ff0` ×5 / `414bb0` ×4 (1 段上) だが、`oob_top.mjs` は `417b70` / `4f9f40` / `414ad0` (`annotate.py` 出力と本 §2 の表を比較)。
- probe build の透過性: probe 無し (復元後) の survey JSON が `base.json` と **byte 一致** (`cmp`)。復元は `probe_entry.sh` の `trap restore EXIT`。
- **限界**: batch の 1 行 (414ad0 の 1 関数) の OOB 文字列を壊した変異では、正規表現版 (238) と raw 走査版 (238 / 414ad0 67) が**両方とも**変化し `--verify` は一致のまま。= `--verify` は「2 つの数え方が同じ入力で一致するか」を見るもので、入力の改変そのものの検出力は無い (改変の検出は上の survey 側ネガコンが担う)。
- 所要 (実測): `probe_entry.sh` 1 回 20.5 s (11 関数)〜41.2 s (36 関数。build + survey + 元 boot.o の再生成を含む `time`)。load average 0.4〜1.2、1 並列。
- 本 run の追加確認: fl-win64 の PE (`block00031_PE.bin`) は §4 の機械語 (`414b64` / `414b6c`) の `objdump` 確認にだけ使った。`TSV 基準` の 222 / 68 / 2 は `oob_cross307.py` の出力 (本 run、`--verify` 通過)。
- 再実行 (HEAD `97eaf2a`、worktree `ws-596`、work-m11 を repo 内 `tools/m11/work/` に展開、`m11_build.sh` → `survey_units.mjs`、1 並列、開始時 load average 0.74): `m11_build.sh` rc=0 (12.8 s wall、`wasm-ld signature mismatch: 0, undefined symbol: 0`)。`survey_units.mjs` rc=0 (16.7 s wall) **ok 818 / halt0 56 / miss 46 / oob 21 / noproc 1** (§1 と一致)。
- 再実行 (検証起点 `129e85a`、1 並列、開始時 load average 0.41): `m11_build.sh` 成功 (30.4 s wall。初回の survey は出力先 `work/trap_triage/` 未作成で失敗したため作成して再実行)。`survey_units.mjs` **ok 818 / halt0 56 / miss 46 / oob 21 / noproc 1** (17.3 s wall)。`oob_top.mjs` (16.4 s wall) は 942 unit の kind が `survey_units.mjs` と全件一致 (True)、oob 21 の最上位 frame は 417b70 ×7 / 4f9f40 ×5 / 414ad0 ×4 / 418190・47ad70・864fe0・903d20・40ff70 各 ×1 (§2 の表と一致)。`oob_cross307.py --verify` は exit 0 (jsonl 239 関数 / 84 種、TSV 222 / 71 種、共通 222、TSV のみ 0、jsonl のみ 17、検算 239 / 68)。
- 未実施: `m11_e2e.sh` 全体 (本 run は work-m11 のスナップショットで build+survey のみ)、現 main `8d883c3` での再測 (#680)、`oob_top.mjs` の n≥3 再現 (HEAD で 1 回再実行: 942 unit の kind 一致・oob 21 unit の frames 名一致。JSON の byte 一致はしない = 末尾 frame の `oob_top.mjs:<行>:19` (ハーネス自身の行番号) が SV_WATCH 追加で動いたため。frame 名・kind は同一)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `414ad0` の C 転記 (または ldfix の `[arg1]` deref 復元) で 4 unit (149 158 280 659) が ok になるか。`652500` の入口 arg1 が非ゼロ・arg2〜4 が 0 となる理由 (`653660` の call 引数の突合) を含む | oob 4 unit。#307 の 68 関数も同じ関数 | **#683** (#307 と共通) |
| 4f9f40 系 5 unit: 書込み元 `47b260` (§3)。291・296 は修復で ok、304・555・923 は別原因 | oob 5 unit | 291・296: **#706** (未マージ)。304・555・923: **#714** |
| 95 / 275 / 477 / 895 の個別原因 (各 1 unit) | oob 4 unit | **#684** (本 REPORT §5) |
| `oob_top.mjs` は `survey_units.mjs` の複製 (frames 処理・SV_WATCH など)。乖離リスクがあるので 1 本に統合する | 2 系統の harness | **未起票** (PM 判断: #683 は統合の受入条件を持たない。新規起票か既存への追記を PM に依頼) |
| 現 main `8d883c3` と本 REPORT の測定基準の差 (分母 13 と 21) | §1 | #680 (測定基準の固定化) |
| 58–63 (6 unit) の snapshot 基準の oob。#552 head では ok (#664 の記載)。snapshot と main の差は §1 | 測定基準 (§1) | 解析済み (#664)・main は #552 で解消。snapshot 側の扱いは #680 |
| unit 56: `8c7710` の D4 型 → `8c5eb0` の OOB (§2) | oob 1 unit | **#662** |
| `survey_units.mjs` の `.slice(1)` を直す (oob の frames 基準が 1 段変わる) | `annotate.py` / `survey_diff.py` の基準変更 | **#663** (OPEN。#495 は CLOSED で `.slice(1)` の記述なし) |
