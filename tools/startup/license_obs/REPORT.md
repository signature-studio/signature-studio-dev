# REPORT — ST-T11 (#107) / ST-T15 (#525): 登録フラグ `byte[0x14f84a8]` / gradeChar と Trial 制限の観測

日付: 2026-10-13 (ST-T15 追補 §3.4 を同日追加) / 書込範囲: `tools/startup/license_obs/`・`tools/startup/GATES.md` (G04)・`docs/DOC_MAP.md` (索引 2 行) /
再現: `bash tools/startup/license_obs/license_obs.sh` (要 `FL_WIN64_DIR` = 素材 fl-win64 の展開先。venv は `uv` で自動作成)
既知類型との関係 (DEFECTS.md / icall §4): 該当なし (lift の silent miscompile は扱わない。静的読解と実機械語の観測)。
検証起点: ST-T11 は `0a0b631`、ST-T15 (#525) は `920f837` (§4)。

## 0. 結論 (数値は全て実測。推定は「推定」と明記)

1. **#107 の題意「lift 後観測」は未達**。FLEngine の boot は `InitUnits` の unit 209/942 で止まっており (`tools/flelift/boot/REPORT.md`)、
   登録パーサ `0x10c7cd0` (caller `0x10d50d0`・`0x11cde20`) には lift 経路からは到達できない。代替として **実機械語 (FLEngine_x64.dll 無改変) を
   unicorn で直接実行**して観測した (§3.3)。→ 本 PR は `Refs #107` (Closes しない)。
2. **Trial 判定の本体は `byte[0x14f84a8]` ではなく gradeChar** (`[[[0x15e4790]]+0xd0]` の 1 byte; `0x40`='@'=未登録・`0x41`–`0x43`='A'–'C'=登録 tier・`0x3f`='?'=期限切れ)。
   「Trial mode」文言を出す箇所 (FL Cloud バックアップ警告・`(disabled in Trial mode)` 等) は **gradeChar ≤ 0x40** で分岐する (§3.2)。
   gradeChar の列挙は `[[var]]+0xd0` を連続形で辿る **196 ロード/89 関数 (下限)** であり網羅ではない (次項)。
   **旧記述 (GATES G04・startup REPORT §4-1) の「bit0 = Trial 解釈」は反証**: bit0 は登録リマインダ系 UI の分岐であり、しかも bit0 を立てる経路は実行されない (§3.1・§3.3 N2)。
3. **フラグ byte**: 全バイナリで `0x14f84a8` を参照する命令は **直接参照 0 件・ポインタ `0x15e0698` 経由 44 ロード (read 38 / write 6)**。write は全て `0x10c7cd0` 内。
   静的初期値 `0x00`。read は bit2 (0x04) 20 ロード/18 関数・bit0 (0x01) 12/12・bit1 (0x02) 5/5・その他 1 (§3.1)。
4. **実機械語の観測 (ILRegKey 無し/空)**: 5 入力 (A1–A4, D2) の全てで 終了 ok・**flag = 0x00・gradeChar = 0x40**。MachineGuid・ComputerName・AppData を変えても不変 (A1/A3/A4)。
   ネガティブコントロール 3 件 (N1–N3) は期待どおりに値が変わる (§3.3・§4)。
5. **ILRegKey 非空 (vreg seed のプレースホルダ・非正規 16 進) を観測 (#525)**: unit 初期化節 11 関数を無改変で先に実行すると復号 VM のハンドラ表が出来、
   5 入力 (B1/B2/B3 = プレースホルダ, D1/D3 = 非正規 16 進) の全てが **ok・flag = 0x00・gradeChar = 0x40・button ID 3 ("Update registration")** で終了する (§3.4)。
   ilreg の静的予測「プレースホルダは全ティア grade 0 → gradeChar 0x40・flag 0」は**動的に確認**された。ただし tier 判定は 3 tier とも最初の marker ゲート (`0x10cae5c`) で
   skip されており、record 検索・tier 適用には到達していない (§3.4)。
   **規約との関係**: §0-3 の旧記述 (LEGAL §0-3「正規データをローカルに入れる形に限る」) は、2026-10-10 のユーザ指示による LEGAL §6.0 (運用規程) で上書きされている。本 REPORT の手段選定は §6.0 を正本とする。
6. **プロジェクト方針 (常に登録済み) との関係**: 「登録済み」の状態は gradeChar > 0x40 であって、flag byte の bit ではない (推定: 有効な primary tier 鍵は flag を 0 のまま gradeChar だけを `A`–`C` にする。§3.2)。
   vreg のプレースホルダ単体では gradeChar > 0x40 にならない (動的に確認, §3.4)。→ 対策案は §6 (別 issue)。
   **手段の選定 (§8)**: ユーザ自身の正規 .reg を #116 経由で投入する案 (a) を第一候補とする (子 #785)。合成 (c) は却下、ホスト側後処理 (b) は gradeChar のポインタ張り替えにより保留 (子 #786)。
7. **gradeChar の列挙は下限**: 連続形 196 ロード/89 関数に加え、レジスタ追跡 (§3.2) で `lea reg,[obj+0xd0]` (バイトのポインタフィールドのアドレスを取る形) 69 ロードと
   フィールドへのポインタ書込 1 ロードが見つかった (追跡形 266 ロード/102 関数。連続形の 89 関数に無い関数が 13)。アドレスを退避した後の間接アクセスは追っていない。
   よって `== 0x40` 判定を持つ関数は 89 より多い可能性が高く (§3.2 の 13 関数の比較命令は推定)、Trial 制限範囲 (§5)・`?` 書換え経路の列挙 (§3.2 write 3 関数) も下限である。

## 1. 範囲と素材

| 項目 | 内容 |
|---|---|
| 対象 | `FLEngine_x64.dll` 26.1.7 win64 (`extracted/block00031_PE.bin`, 22,227,016 B, ImageBase `0x400000`)。VA は絶対 VA (ilreg REPORT と同表記) |
| 素材 | `fl-win64` のみ使用 (`toolchain-*`・`work-m11` は取得済みだが未使用: m11 の RetDec lift は間接 call 全滅のため 0x10c7cd0 の観測に使えない — `tools/m11/REPORT.md` §2)。#525 の judge 突合は repo 内の `tools/startup/vreg/ilreg/verify/reader.mjs` (node) |
| 方針 | 観測のみ。ライセンスの生成・偽造はしない (入力は vreg seed の既存プレースホルダと、意図的な非正規値) |
| ツール | python 3.14・pefile・capstone 5.0.7・unicorn 2.1.4 (`license_obs.sh` が `uv pip install`) |

## 2. 成果物

| パス | 内容 |
|---|---|
| `license_obs.sh` / `env.sh` | 1 コマンド e2e (scan → run_cases → verify) |
| `peidx.py` | `.pdata` の関数境界ごとの capstone 逆アセンブル共通部品 |
| `scan_consumers.py` | フラグ byte の全 read/write サイト列挙 + gradeChar の連続形 (下限)・レジスタ追跡形の列挙 → `results/flag_sites.json`・`results/FLAG_SITES.md` (自動生成)。`--no-track` / `--no-redef-stop` はネガコン用 (ファイルを書かず件数だけ出す) |
| `emu_reg.py` | unicorn による `0x10c7cd0` 実行環境 (後述 §3.3) |
| `judge_xcheck.mjs` | `cases.json` の各ケースを ilreg `reader.mjs` の `judge()` に通して突合 (`--neg` = 突合が形骸でないことを示すネガコン)。verify.py が呼ぶ (#525) |
| `run_cases.py` | 入力ケース実行 (unit 初期化を先に実行) → `results/cases.json`・`results/CASES.md` (自動生成) |
| `verify.py` | 検算 (capstone 非依存の生バイト走査・gradeChar 追跡の別算法・不変条件・ケース期待値・unit 初期化節の独立導出・ILRegKey 非空ケースと judge 突合・ネガコン) |
| `probe_786.py` / `REPORT_786.md` | #786: 0x10d3a30・0x11cb000・0x10d50d0 の呼出し元・参照元・ループ条件 (読取専用)。付録 `REPORT_786.md` |
| `probe_1492.py` / `REPORT_786.md` §13 | #1492: 基本ブロック追跡 (分岐合流・callee 越し) で退避経由 gradeChar を再計数。線形走査と一致 (207/69/20)。付録 `REPORT_786.md` §13 |
| `probe_1414.py` / `REPORT_786.md` §12 | #1414: 0x10c7cd0 の間接 call を通常経路 6 入力で観測 (9 ターゲット・0x11cb000/0x10d50d0 は未到達)、0x10d3a30 の強制実行 (g1/g2 を書換え・F1 は書込み無し、F2/F3 は 0x10c7850 内で停止)。付録 `REPORT_786.md` §12 |
| `probe_1221.py` / `REPORT_786.md` §8 | #1221: unicorn code hook で 0x11cb000・0x10d50d0・0x10d3a30 の到達を観測 (6 入力とも未到達)、g1〜g8 の実行後の値、0x10c7850 の戻り値 (0x7fffffff)。付録 `REPORT_786.md` §8 |

## 3. 結果

### 3.1 フラグ byte `0x14f84a8` の全サイト (`scan_consumers.py`; 一覧 `results/FLAG_SITES.md`)

走査: `.pdata` 関数 57,816 / 命令 2,580,490 (n=1, 5.8 秒)。`0x14f84a8` への RIP 相対直接参照 **0**。唯一のポインタ `0x15e0698` (中身 `0x14f84a8`) のロード **44**。

| 種別 | ロード数 | 関数 | 内容 |
|---|---:|---|---|
| write | 6 | `0x10c7cd0` のみ | `0x10c876d` 初期化 (元値 `0x10d08d8` = 0) / `and 0xfd` `0x10cbb14` / `and 0xfb` `0x10cbb1e` / `or 2` `0x10cd0b8` / `or 4` `0x10cd0fe` / `or 1` `0x10cf4e6` |
| read bit2 (0x04) | 20 | 18 | 下表 |
| read bit0 (0x01) | 12 | 12 | 下表 (うち 1 は `0x10c7cd0` 自身の `0x10cf4f0`) |
| read bit1 (0x02) | 5 | 5 | 下表 |
| read その他 | 1 | 1 | `0x1005820` (`and al,[rip+..]` でマスクを外部から取る) |

bit ごとの利用箇所 (文字列は各分岐の線形 45 命令以内に現れるリテラルで、**目安**。極性は `jcc` から機械的に決定):

| bit | 立っているときの分岐 / 立っていないときの分岐 (代表) | 意味 (推定) |
|---|---|---|
| bit0 | `0x11be0a0`: 立つ→"Please remember to register"、立たない→"Registered to: "。`0x10d5980`: 立つ→`BoxEdition.txt`、立たない→`NotReggedTxt.txt`/`DemoTxt.txt`。`0x10d5cf0` `BoxRegReminder`。`0x124dd00` "Create account"/"My account" | 未登録リマインダ UI。**このビルドでは立つ経路が実行されない** (`or 1` は `Pos("Please remember to register", S)` が正の時のみで、S は `0x10c7cd0` 内で nil のまま。§3.3 の N2 で nop 化すると立つ) |
| bit1 | `0x1375990`: 立つ→"Fire edition"。`0x11c2d80`: 立つ→"Upgrade to Producer edition for more features..."。`0x10d1340`: 立たない→"Your license has expired" | Fire edition |
| bit2 | `0xc225d0`: 立つ→"Upgrade Fire to Producer Edition"。`0xc33690`/`0xc33c10`: 立つ→"…is in trial mode. You can save this project but you must connect your Fire controller…"。**`0xecec70`/`0x1363af0`/`0xf1f1f0`: 立たない→"Project backups to FL Cloud are not available in Trial mode."、`0xecf240`/`0x135b3a0`: 立たない→"(disabled in Trial mode)"** | Fire 系鍵 (second tier, `or 4`) を持つときの免除ビット。立たない側の "Trial mode" 文言は §3.2 のとおり **gradeChar ≤ 0x40 も要求** |

### 3.2 gradeChar `[[[0x15e4790]]+0xd0]` のサイト (同スクリプト; 一覧は `results/FLAG_SITES.md` 後半。**連続形は下限**)

**連続形** = `mov r1,[0x15e4790]` → `mov r2,[r1]` → `mov r3,[r2+0xd0]` を 3 命令連続で辿る形 (`grade_site`)。`0x15e4790` → 変数 → オブジェクト → `+0xd0` の byte ポインタ、
という経路のロードが **196** (read 189 / write 7)、**89 関数 (下限)**。`0x15e4790` を読む `mov r64,[rip+..]` の生ロードは 2,422 (分母)。

| 分類 | ロード数 / 関数数 | 備考 |
|---|---|---|
| write (連続形のみ = 下限) | 7 / 3 関数 | `0x10c7cd0` ×5 (`0x40` 初期化 `0x10ca56d`・tier 確定 `0x10cbb12`/`0x10cd0db` (値=ループ添字 `0x41`–`0x43`)・期限切れ `0x3f` `0x10cf4c6`・`0x40` `0x10cf621`) / `0x10d3a30` (`0x3f`) / `0x11cb000` (`0x3f`) |
| read `== 0x40` | 62 / 34 | 同型の inline コード (24 関数 family を含むと推定) |
| read `== 0x3f` | 27 / 26 | この 26 関数は全て `== 0x40` も比較。ilreg/GATES の「24 関数」との差 2 は未照合 → §6 |
| read `> 0x40` | 50 / 41 | 登録済みのとき通る側 (下記 Trial 文言サイトを含む) |
| read `>= 0x41`〜`0x44` (4) / `== 0x42` (3) | 7 | tier 別分岐 (A/B/C) |
| read 条件未復元 (`setcc` 等) | 43 | 一覧に生の命令を記載 |

**レジスタ追跡形** (`track_grade`): ロード直後が `mov r2,[r1]` のとき r2 を 13 命令追い (`ret`/`jmp` または r2 の書換えで打切り)、`[r2+0xd0]` を使う最初の命令を拾う。
追跡形は **266 ロード/102 関数** = 連続形 196 (89 関数) + 追加 70。追加の内訳は `lea reg,[obj+0xd0]` 69 ロード/20 関数 (バイトのポインタフィールドの**アドレス**を取る形)・
`mov qword ptr [rcx+0xd0],rax` 1 ロード (`0x10d52ed`, 関数 `0x10d50d0` = フィールドへのポインタ書込)。追加 70 は 21 関数に分布し、**13 関数が連続形の 89 関数の外**:
`0xe7a470` `0xf51fd0` `0xfeffe0` `0xffbff0` `0x103ca70` `0x1183130` `0x11d9340` `0x11fc770` `0x1231170` `0x12875a0` `0x13582c0` `0x1358870` `0x1366190`
(一覧は `results/FLAG_SITES.md` 末尾)。この 266 / 13 関数はレビュワーの独立実測 (HEAD `43aa592` に対する指摘) と一致する。
この 13 関数はいずれも関数内に `cmp ?, 0x40` / `cmp ?, 0x3f` を 1–9 命令 (計 59 命令; 例 `cmp dword ptr [rbp+0x394], 0x40`) 持つ。gradeChar をスタックに写して比較する形の**推定**で、命令数の集計のみ (関数ごとのデータフローは未確認)。
`lea` で得たアドレスは別の場所 (例 `0xe7a470`: `[rbp+0x3a8]`) に退避され、その先で `movzx` による読出し・`GetMem` 相当での 1 byte 再確保・`FreeMem` 相当での旧領域解放・`[obj+0xd0] := 新` が行われる。
この「確保・コピー・解放・スロット := 新」の簡易パターン一致 71 箇所/20 関数はレビュワー実測で、**本 PR では再現していない**。メモリ管理関数の同定とアンチタンパ目的という解釈も**推定**。
**追跡形も下限**: 退避先経由の間接アクセス、`0x15e4790` 経路以外 (引数で渡されたオブジェクト等) から来る `+0xd0` は追っていない。

**Trial 文言サイトの共通点**: `gradeChar > 0x40` の偽側 (= `@`/`?`) が "Trial" 文言。13 ロードで確認 — `0xecec70`・`0xf1f1f0`・`0x1363af0` ("Project backups to FL Cloud are not available in Trial mode.")、
`0xecf240`・`0x135b3a0` ("(disabled in Trial mode)")、`0x1105e40` ("Undo tests are disabled in Trial mode")、`0x11d8f30` ("(Trial)")、`0x1146190`・`0x1146850` (" trial")、`0x10a9170` (`welcome_window_trial`)、`0x10a7270`/`0x10aaae0` (`free` / "Free for customers")。
`0xecec70` ほか 3 箇所は **`gradeChar ≤ 0x40` かつ bit2 クリア** の両条件 (逆アセンブル: `cmp byte [gradeChar],0x40; ja skip; test flag,4; jne skip`)。

### 3.3 実機械語の実行 (`emu_reg.py` / `run_cases.py`; 結果 `results/CASES.md`)

方法: PE を ImageBase に敷設 (再配置不要)、Delphi RTL は無改変。差し替えは ①メモリマネージャ表 `0x13a5c90` の 4 関数 (bump allocator) ②IAT の 738 インポート (+ 動的取得 API) を `ret` スタブにして Win32 API を Python で実装
(registry は辞書、`GetComputerNameExW`・`SHFolder.dll!SHGetFolderPathW` 等) ③ Delphi の翻訳関数 `0x8da350` を「出力文字列 := リテラル」に差し替え ④ gs:[0x58] の TLS と `0x13a9388` (threadvar 添字) の初期値 0。
入力の license 群は vreg seed (`tools/startup/vreg/data/seed.json` の license 群 apply=true) をそのまま使用。呼出は `0x10c7cd0(cl)` (`cl`=0: `0x10d531b` と同じ / 1: `0x11ce565` の Fire check と同じ)。

| case | 入力 | 終了 | flag | gradeChar |
|---|---|---|---|---|
| A1 | ILRegKey 無し (cl=0) | ok | 0x00 | 0x40 |
| A2 | ILRegKey 無し (cl=1) | ok | 0x00 | 0x40 |
| A3 | ILRegKey 無し + 別 MachineGuid/ComputerName/AppData | ok | 0x00 | 0x40 |
| A4 | ILRegKey 無し + MachineGuid 取得失敗 | ok | 0x00 | 0x40 |
| D2 | ILRegKey = 空文字列 | ok | 0x00 | 0x40 |
| B1/B2 | vreg seed のプレースホルダ (cl=0/1) | ok (unit 初期化あり; §3.4) | 0x00 | 0x40 |
| D1 | 16 進 128 文字の非正規値 | ok (同) | 0x00 | 0x40 |
| NB0 | B1 から unit 初期化を除く (#107 時点の条件) | **停止** (`0x8c9d7c` null deref) | — | — |
| N1 | A1 + gradeChar 初期値 imm `0x40`→`0x42` に改変 | ok | 0x00 | **0x42** |
| N2 | A1 + `or flag,1` 直前の `jle` を nop 化 | ok | **0x01** | 0x40 |
| N3 | A1 + flag 初期化の元値 `0x10d08d8` を `0x04` に改変 | ok | **0x04** | 0x40 |

読み取った registry 値 (A1; 実行トレース): `HKCU\Software\Image-Line\Registrations` の `FL Studio license plate`/`FL Studio user name`/`FL Studio webpass`/`FLS Info`、`HKLM\SOFTWARE\Microsoft\Cryptography` の `MachineGuid`
(`RegOpenKeyExA`, access `0x20019`)。続いて `…\Registrations\FL Studio 26.1` を HKCU・HKLM の順に開こうとする (無いので ILRegKey は読まない)。
**MachineGuid・ComputerName・AppData は ILRegKey の有無に関わらず先に取得される** (A1 の API 呼出順: `LoadLibraryW(SHFolder)` → `GetComputerNameExW` → `RegOpenKeyExA(HKLM Cryptography)`)。ただし ILRegKey 無しでは結果に影響しない (A1=A3=A4)。
unit 初期化なしの B 系 (NB0) の停止点: ILRegKey を読んだ後の復号 (`0x8d0380` 系, ilreg FORMAT §5) で、`0x8c5c90` が返す singleton の byte 添字表 (`[obj+8+idx*8]`, `0x8c7820`) が null。表は unit の初期化節で作られる → §3.4 で解消。

### 3.4 unit 初期化節の実行と ILRegKey 非空の観測 (#525; `Emu.init_units()` / `results/CASES.md` / `results/cases.json`)

**何を実行したか**: ハンドラ登録 `0x8c5cc0(classRef, id)` (`0x8c5c90` の singleton の `[obj+8+id*8]` へ登録) の呼び出し元は 11 関数 (call rel32 の生バイト走査; 呼び出し箇所 118)。
全て `sub [cnt],1; cmp [cnt],-1; jne` の 1 回限りガード付きの unit 初期化節で、unit 表 `0x1376be0..` の init 側エントリと一致する
(`0x558e20 0x5658e0 0x56fde0 0x577290 0x577fd0 0x579610 0x57fd50 0x580970 0x582230 0x8b2080 0x8cb690`)。
これを `0x10c7cd0` の前に順に **無改変で** 実行した (unit 全部 (942) ではなく必要部分のみ)。各回 ok 終了 (11 関数実行後の `api_log` 累計 657 件、`mm!` 含む)。追加した API スタブは `InitializeCriticalSection` 系 (戻り 0) のみ。
後続の `0x10c7cd0` で復号 VM `0x8d0380` の入口は 1 回通り、完走して head が得られる (NB0 は入口には届くが VM 内部 `0x8c9d7c` で停止し head に届かない: 到達 head 0 回)。

| case | 入力 | 終了 | flag | gradeChar | button ID | 到達 (VM / head / machine 突合 / record 検索 / tier 適用 / tier skip) |
|---|---|---|---|---|---|---|
| B1 / B2 | プレースホルダ (cl=0 / 1) | ok | 0x00 | 0x40 | 3 | 1 / 3 / 0 / 0 / 0 / 3 |
| B3 | プレースホルダ + 別 MachineGuid / ComputerName / AppData | ok | 0x00 | 0x40 | 3 | 同 |
| D1 | 16 進 128 文字 | ok | 0x00 | 0x40 | 3 | 同 |
| D3 | 16 進 8 文字 | ok | 0x00 | 0x40 | 3 | 同 |

読み方 (実測): ①復号結果の head (`0x8e6770` の先頭グループ。`0x10cad6e`) は B1/B2/B3 で同一 (`ab00 3400 8100 1800 …` の UTF-16 コードユニット列)、D1・D3 とも別の値
→ 入力に応じて VM が実際に動いている。②3 tier とも marker ゲート `je 0x10cb991` (`0x10cae5c`; head 非空 = ':' 始まりでない) で skip。復号結果は正規書式の平文ではないので、
machine 突合 (`0x10cb728`)・record 検索 (`0x10cb741`)・tier 適用 (`0x10cbaf0`) のいずれにも到達しない。③マシン情報 (B3) と cl (B2) は結果に影響しない。
④ILRegKey 非空では button ID が 3 になる (無し/空は 0 のまま。差の原因となる経路は未調査)。

**ネガティブコントロール (非空経路)**:

| case | 改変 (B1 の入力) | 結果 |
|---|---|---|
| NB0 | unit 初期化を行わない | 停止 (`0x8c9d7c`)。ハンドラ表が必要であること |
| NB1 | `0x8d0380` (復号 VM 入口) を `ret` | head の先頭 8 B が `ab003400…` → `12356b8c…` に変わる。復号 VM の出力が判定入力になっている |
| NB2 | tier の 4 ゲート (`0x10cae5c` marker・`0x10cae9a` charsum・`0x10cb72f` machine・`0x10cb795` record) を nop 化 | tier 適用が 3 回実行され **gradeChar 0x43**・button 1。実機械語の tier 適用が観測値に反映される |
| NB3 | 上記のうち 3 ゲート (record を除く) のみ nop 化 | record 検索には届くが tier 適用に届かず gradeChar 0x40 のまま |

(NB2/NB3 は「ゲートを潰すと値が変わる」ことの確認であり、有効なライセンスの生成ではない。)

**別実装との突合** (`judge_xcheck.mjs`): 同じ入力 (MachineGuid・ComputerName・AppData・復号 head) を ilreg `reader.mjs` の `judge()` (FORMAT.md 移植) に与え、
A1/A3/A4/D2/B1/B3/D1/D3 の 8 ケースで gradeChar・flag (非空 ILRegKey は button ID も) が実機械語の観測と全一致。`--neg`: B1 の観測に対し、正規書式の合成平文
(`:F0:20991231:|id:<機械文字列>|31000:20991231:`) を judge() へ与えると gradeChar 0x41・button 1 で**不一致を検出**する。突合が常に match を返す形骸でないことの確認。

## 4. 検証 (ST-T11: HEAD `0a0b631` / ST-T15 #525: HEAD `920f837` をクリーン worktree に展開して実行)

| 項目 | 実測 |
|---|---|
| `bash license_obs.sh` (venv 作成済み) | 55.42 / 55.64 / 55.86 秒 (n=3 直列, 4 コア runner, 開始時の load average 1 分値 0.81 / 0.92 / 0.97)。内訳 (n=1, 開始時 load average 0.75): scan_consumers 2.97 秒・run_cases 47.06 秒 (11 ケース × PE 敷設)・verify 6.05 秒 |
| #525: `bash license_obs.sh` (HEAD `920f837`, クリーン worktree, venv 作成済み) | 116.45 / 115.49 / 114.64 秒 (n=3 直列, 4 コア runner, 開始時 load average 1 分値 0.70 / 0.96 / 1.05)。いずれも終了コード 0・`ALL OK`・verify 38 項目 PASS / FAIL 0 (`grep -c '^PASS'`)・再生成した `results/*` の差分なし (`git status --porcelain` 0 行, 3/3 回)。run_cases は 20 ケース (旧 11) で、旧 55 秒から増えた分は unit 初期化と追加ケース |
| 結果 | 3/3 回 `ALL OK` (verify 22 項目 PASS)。再生成した `results/*` はコミット内容と差分なし (`git status --porcelain` 空, 3/3 回)。`run_cases` の出力に含まれていた実行時間 (0.01 秒単位で 0.01–0.03 に揺れ、`7350c28` の検証では 3/3 回差分が出た) を `0a0b631` で除いて決定的にした |
| 別アルゴリズム検算 1 (フラグ) | capstone 非依存の生バイト走査 (`REX.W 8B /r` + `rip` 相対 rel32 から実効アドレスを逆算) が、スロット `0x15e0698` のロード 44 件を capstone 結果と **集合として完全一致** (差 0) |
| 別アルゴリズム検算 2 (gradeChar) | `verify.py` V1d/V1e: 生バイト走査の `0x15e4790` ロード 2,422 件を起点に、`.pdata` の関数境界を使わず capstone の detail モード (オペランド構造 base/index/disp・`regs_access` の書込レジスタ・call の volatile 破壊) で窓を直接デコードして追跡。追跡形 **266 ロード/102 関数** を scan と **集合として完全一致** (差 0, 使用命令 VA も 266 件一致, `lea` 69)、連続形 196 ⊆ 追跡形、連続形の外 13 関数。V1b (連続形 196 ⊆ 生ロード 2,422) は部分集合検査で**取りこぼしを検出しない** |
| ネガティブコントロール (ケース) | N1 (gradeChar 初期値改変) → 0x42 / N2 (jle 無効化) → flag 0x01 / N3 (初期化元値改変) → flag 0x04。いずれも **実行された機械語の書込が観測値に反映される**ことを示す |
| ネガティブコントロール (追跡) | V5a: 追跡を無効にすると **196 に戻る** (`scan_consumers.py --no-track`: 追跡形 196 ロード/89 関数 = 連続形, 追加 0)。V5b: r2 書換えでの打切りを外すと **279** (≠266; 13 ロード多い。r2 が別の値に書き換わった後の `[r2+0xd0]` を拾う誤検出で、例は vtable 呼出 `call [rax+0xd0]` と次のロードの使用の二重計上) |
| #525 ネガコン | 非空経路: NB0 (unit 初期化なし → 停止)・NB1 (VM 入口 ret → head 変化)・NB2 (4 ゲート nop → gradeChar 0x43)・NB3 (3 ゲート nop → 0x40 のまま)。突合: V7j (8 ケース一致)・V7k (合成平文で不一致を検出)。unit 初期化節: V6a (0x8c5cc0 呼び出し元の独立導出と 11 関数が集合一致) |
| 規約チェック | `git status --porcelain -- tools/startup/license_obs` 空・`find tools/startup/license_obs -type f -size +20M` 空 |

検証範囲: ILRegKey 無し/空での 0x10c7cd0 の終状態 (flag・gradeChar)、フラグ byte `0x14f84a8` の全サイト (直接参照 0・ポインタ `0x15e0698` 経由 44 ロード; 生バイト走査で検算済み)、
gradeChar の連続形 196 ロード/89 関数 (**下限**) とレジスタ追跡形 266 ロード/102 関数 (**下限**; 13 関数は連続形の外)。
#525 の検証範囲: ILRegKey 非空 (プレースホルダ・非正規 16 進) の `0x10c7cd0` 終状態 (flag・gradeChar・button ID)。
範囲外: **有効書式の ILRegKey** の判定結果 (本調査は生成・偽造しない)、unit 初期化の残り (11 関数以外)、実エンジンの boot 経由の呼出、bit の意味ラベルの確定 (文字列からの**推定**)、
**gradeChar の網羅**: 退避アドレス (`lea reg,[obj+0xd0]`) 経由の間接アクセスとポインタ張り替え (レビュワー実測: `+0xd0` 使用 266 件、うち 13 関数は 89 関数の外。本 PR のレジスタ追跡で 266/13 を再現したが、退避先経由のアクセスは追っていない)。

## 5. 問い (issue 範囲) への回答

| issue の項目 | 回答 | 確度 |
|---|---|---|
| bit0/bit1 の実測 | bit0・bit1 とも ILRegKey 無し/空では 0 (実機械語)。bit0 を立てる経路は実行されない。bit0=Trial は **反証** (§3.1) | 実測 (A1–A4, D2) / 意味ラベルは推定 |
| ILRegKey 無しの挙動 | 例外なく終了。flag 0x00・gradeChar 0x40 → Trial 文言サイトの偽側 (§3.2) に入る。起動は継続 | 実測 (flag/gradeChar) / UI 帰結は静的 |
| Trial 制限範囲 | gradeChar を `[[var]]+0xd0` の連続形で辿る 196 ロード/89 関数 (**下限**; 条件を復元できた read 146 ロード) のうち、"Trial" 文言を持つ 13 ロードを列挙 (§3.2)。連続形の外に 13 関数あり (追跡形 102 関数)。FL Cloud バックアップ、Undo テスト、ようこそ画面ほか。制限の**機能的全容**は文字列で見える範囲のみ | 静的 (線形パスの文字列; 目安) |
| MachineGuid 依存 | ILRegKey の有無に関わらず MachineGuid/ComputerName/AppData を取得するが、ILRegKey 無しの結果には影響しない (A1=A3=A4)。非空 ILRegKey での依存は ilreg の静的結論 (SHA-256 マシン束縛) のまま | 実測 (無鍵) / 静的 (有鍵) |
| GATES.md G04 の確定 | 反映済み (同 PR)。確定できない部分は「未確定」と明記 | — |

## 6. 未解決・次の一手

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lift 経路 (flelift/boot) で `0x10c7cd0` が実行されたときの観測 (本題 #107) | boot が unit 209/942 で停止中のため不可 | #107 に残 (boot 突破後に `license_obs/emu_reg.py` の期待値と突合) |
| ~~ILRegKey 非空の判定結果の動的確認~~ | **解消 (#525, §3.4)**: プレースホルダ・非正規値とも gradeChar 0x40・flag 0x00 | — |
| 復号結果 head が非空のため marker ゲートで全 tier が skip され、record 検索・tier 適用は非空経路でも未観測 (ネガコン NB2 でゲートを潰したときのみ到達)。正規書式の平文が入ったときの機械語の挙動は有効ライセンス無しには観測できない | #526 の設計 (有効書式の鍵を用意する案) の前提 | #526 にコメント |
| ILRegKey 非空で button ID が 3 になる経路 (無し/空は 0) の原因 | UI 表示分岐の理解 | #107 コメント |
| 「常に登録済み」を満たす手段の設計: gradeChar を `A` 以上に確定させる (有効書式の ILRegKey は #116 のユーザ .reg / ホスト側後処理 / vreg での合成) と、期限切れ `?` への書換え 2 経路 (`0x10d3a30`・`0x11cb000`) の抑止 | 現 seed のままでは Trial 扱い (推定) | **#526** `[ST-T16]` (+ #116 へコメント) |
| gradeChar の参照サイトの網羅: 退避アドレス (`lea reg,[obj+0xd0]`) 経由の間接アクセスとポインタ張り替え (追跡形 266 ロード/102 関数、うち 13 関数は連続形の 89 関数の外)。`== 0x40` 判定を持つ関数は 89 より多い可能性が高く、`?` 書込み経路の列挙 (3 関数) も下限 | Trial 制限範囲 (§5) と #526 の範囲 2・選択肢 (b) が下限の上に立つ | **#526** (2026-10-13 コメントで追記済み: ポインタ張り替え 71 箇所/20 関数 (レビュワー実測)・`?` 書込み経路は 3 関数分のみ)。退避アドレスのデータフロー追跡による網羅は #107 に残 |
| ~~`== 0x3f` を比較する inline 関数が 26 (本調査) と 24 (GATES/ilreg) で不一致~~ | **解消 (§9)**: 26 は gradeChar の比較、24 は HWID コードで母集団が違う (重なり 3)。SHGetFolderPathW は 24 と同一関数で共起しない | — |
| bit の意味ラベル (bit1=Fire、bit2=Fire 鍵免除) と tier キー 31000/31005/31010/31020 の製品対応 | G04 の記述は「推定」止まり | #107 コメント (#213 は closed。後継の ST-T14 番号は #39 に使用済みのため新規番号は PM 確定) |
| 経路ごとの機能的な Trial 制限の全容 (文字列を持たない分岐 43 ロード等) | Trial 制限範囲は「見える範囲」 | #525 + FLEngine boot 後の動的観測 (#107 に残) |

ユーザ依頼事項: なし (素材は `fl-win64` で足りた)。

## 7. 事前推定と実測の差

- 事前推定 (GATES G04 / startup REPORT): 「bit0 = Trial/未登録」→ **反証** (§3.1)。Trial 文言は gradeChar と bit2 で決まる。
- 事前推定 (issue): 「T1 待ち」(#102 glue 完了待ち) → glue は完了済みだが、実行経路の律速は FLEngine boot (unit 209/942)。

## 8. 手段の選定 (ST-T16 #526; 設計のみ・コード変更なし)

**結論**: 「常に登録済み」(§6.0) を満たす手段は **(a) ユーザ自身の正規 .reg を #116 の取り込み口経由で投入し、本物の `0x10c7cd0` に gradeChar を確定させる** を第一候補とする。(b) はポインタ張り替えのため成立が未確認、(c) は採らない。実装は子 issue に分ける。

| 案 | 判定 | 根拠 |
|---|---|---|
| (a) 正規 .reg を #116 経由で投入 | **採用 (第一候補)** | gradeChar は本物パーサ `0x10c7cd0` の出力で、入力を自作しない。ライセンス状態データの配置は LEGAL §6.0-4 (「ユーザ (正規保有者) の承認の下で配置・合成してよい」) の範囲。ただし有効書式の鍵の判定は未観測 (§3.4 は非正規値のみ)。→ 子 #785 |
| (b) パーサ後のホスト側後処理で gradeChar を書く | **不採用 (保留)** | gradeChar は `[[0x15e4790]+0xd0]` の**ポインタ先**で、実行中に確保・コピー・解放でスロットごと張り替えられる (§3.2 レジスタ追跡 266 ロード/102 関数、うち連続形の外 13 関数)。固定アドレスへの書込みは成立しない。書換え 2 経路 (`0x10d3a30`・`0x11cb000`) の抑止も前提になる。→ 子 #786 の結果を見て再判断 |
| (c) vreg での合成 (有効書式の鍵を作る) | **却下 (技術上の理由)** | (1) 有効書式の鍵の形式は本 REPORT で未観測 (§3.4 は非正規値のみ)。形式を知らずに合成した鍵が `0x10c7cd0` の tier 判定まで届くかは実測していない。(2) §0-5・§3.4 のとおり、非正規書式は最初の marker ゲート `0x10cae5c` で skip され、record 検索・tier 適用に到達しない。合成の成否を事前に確かめる手段がない。(3) 本 issue の方針は観測のみ (§1)。合成は別の検証 issue の範囲。本 issue では鍵を生成しない。規約上の可否は本節では判断しない (LEGAL §6.0-4 は配置・合成を許容する方針) |

**`?` (0x3f) 書換えの抑止**: 書換え経路は `0x10d3a30`・`0x11cb000` (write 1 件ずつ・連続形で確認) と、`0x10c7cd0` 内 `0x10cf4a4`–`0x10cf4c6` (残日数 ≤ 0 の判定)。
- 残日数の判定は、有効な .reg の期限が未来なら通らないと**推定**する。未確認。
- `0x10d3a30`・`0x11cb000` の発火条件は未確認。アドレス経由の書込みは §3.2 の追跡の外。→ 子 #786。

**`0x10d50d0` のループ** (`0x10d52f9`–`0x10d531b`): **訂正 (#786)**: gradeChar == 0x40 のときだけ再実行する、は誤り。関数は gradeChar を新領域に作り直して 0 から 0x40 まで count-up し、登録パーサ `0x10c7cd0` を 1 回呼ぶ (再実行の分岐は無い)。詳細と未解決は `REPORT_786.md` §3。

**子 issue**:
- #785 — 正規 .reg 取り込みで `0x10c7cd0` を実行し、終状態・tier 到達を記録する (ブロッカー: ユーザの正規 .reg と #116 の実装)。
- #786 — gradeChar の読み書きを退避アドレス経由も含めて網羅し、`?` 書込みの発火条件と `0x10d50d0` のループを確認する。

**本 issue の範囲外として残すもの**: 有効書式の鍵の判定結果 (#785)、退避アドレス経由の網羅 (#786)、有効鍵の下での `?` 抑止の要否 (#785・#786 の結果による)。

## 9. #107 残項目: 「inline HWID ×24」と「`== 0x3f` 比較 26」の突合 (`probe_hwid.py`; 結果 `results/probe_hwid.json`)

目的: §6 の未解決「`== 0x3f` 26 (本調査) と 24 (GATES/ilreg) の不一致」を解消し、GATES G04 の「MachineGuid+GetComputerNameExW+SHGetFolderPathW を読む同型コード ×24」の定義を機械的に確認する。
定義 (プローブ内): API = 関数内の call 先の import 名 (直接 call は宛先の thunk `jmp qword ptr [rip+IAT]` を 1 段たどる。`call [rip+IAT]` は IAT を直接指すときだけ解決)。STR = rip 相対で `MachineGuid`・`SOFTWARE\Microsoft\Cryptography` の ASCII 文字列を指す命令を持つ。G3f = gradeChar を `cmp ..., 0x3f` で比較する関数 (`results/flag_sites.json`)。

| 定義 | 関数数 n | G3f (26) との重なり |
|---|---:|---:|
| H1 GetComputerNameExW と SHGetFolderPathW を同一関数で呼ぶ | 0 | 0 |
| H2 GetComputerNameExW と RegOpenKeyExA/W・RegQueryValueExW を同一関数で呼ぶ | 24 | 3 |
| H3 MachineGuid / Cryptography 文字列を参照する | 24 | 3 |
| H4 GetComputerNameExW を呼ぶ | 25 | 3 |
| H5 SHGetFolderPathW を呼ぶ | 4 | 0 |

- **H2 = H3 (同一集合 24 件・差 0)**。API と文字列の独立な 2 定義が一致した。0x10c7cd0・0xf2dbb0・0x11dd800 は 24 に入る。0x10c7530 は 24 に入らない (GATES が別項目で挙げる関数で、HWID 側の所属は未確認)。
- **「SHGetFolderPathW との共起」は成立しない (H1 = 0)**。SHGetFolderPathW を呼ぶ 4 関数 (0x5a09f0・0x5a0c90・0x63b880・0x81bca0) は 24 のいずれにも入らない。よって GATES G04 補足・startup REPORT §1 の「MachineGuid+GetComputerNameExW+SHGetFolderPathW を読む同型コード ×24」は、同一関数内の共起としては誤り。24 の構成は GetComputerNameExW + Reg 系 (+ MachineGuid 文字列) である。文書を訂正した (GATES.md 補足・startup REPORT §1)。
- **「26 vs 24」は数の食い違いではなく母集団の違い**。26 は gradeChar (`[[[0x15e4790]]+0xd0]`) の `== 0x3f` 比較関数 (§3.2)、24 は HWID コードである。重なりは 3 件 (0xf2dbb0・0x11dd800・0x11a57c0) のみ。§6 の該当行は解消。

限界 (未解決): (a) 関数ポインタ表 (`.data` 内の関数アドレス) 経由の call は解決していない (493 件の `call [rip+..]` の大半が該当し、IAT 直接はその一部)。よって H1・H5 の 0 件・4 件は下限。(b) SHGetFolderPathW の呼出元 (AppData 取得) は未特定。
検証: 測定 commit `3d615fc3` (コードを変えた最後の commit)。`FL_WIN64_DIR=<fl-win64 展開先> python3 tools/startup/license_obs/probe_hwid.py` を commit 済み HEAD で実行: 6.6 s (実行直前の load average 0.52/0.34/0.17)、`results/probe_hwid.json` は再実行で cmp 一致。出力: functions=57,816・IAT 解決 738 名・STR 参照 VA 24・G3f=26。
