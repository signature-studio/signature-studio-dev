# REPORT — ST-T11 (#107): 登録フラグ `byte[0x14f84a8]` / gradeChar と Trial 制限の観測

日付: 2026-10-13 / 書込範囲: `tools/startup/license_obs/`・`tools/startup/GATES.md` (G04)・`docs/DOC_MAP.md` (索引 2 行) /
再現: `bash tools/startup/license_obs/license_obs.sh` (要 `FL_WIN64_DIR` = 素材 fl-win64 の展開先。venv は `uv` で自動作成)
既知類型との関係 (DEFECTS.md / icall §4): 該当なし (lift の silent miscompile は扱わない。静的読解と実機械語の観測)。
検証起点: コミット済み HEAD `56e0379` (§4)。

## 0. 結論 (数値は全て実測。推定は「推定」と明記)

1. **#107 の題意「lift 後観測」は未達**。FLEngine の boot は `InitUnits` の unit 209/942 で止まっており (`tools/flelift/boot/REPORT.md`)、
   登録パーサ `0x10c7cd0` (caller `0x10d50d0`・`0x11cde20`) には lift 経路からは到達できない。代替として **実機械語 (FLEngine_x64.dll 無改変) を
   unicorn で直接実行**して観測した (§3.3)。→ 本 PR は `Refs #107` (Closes しない)。
2. **Trial 判定の本体は `byte[0x14f84a8]` ではなく gradeChar** (`[[[0x15e4790]]+0xd0]` の 1 byte; `0x40`='@'=未登録・`0x41`–`0x43`='A'–'C'=登録 tier・`0x3f`='?'=期限切れ)。
   「Trial mode」文言を出す箇所 (FL Cloud バックアップ警告・`(disabled in Trial mode)` 等) は **gradeChar ≤ 0x40** で分岐する (§3.2)。
   **旧記述 (GATES G04・startup REPORT §4-1) の「bit0 = Trial 解釈」は反証**: bit0 は登録リマインダ系 UI の分岐であり、しかも bit0 を立てる経路は実行されない (§3.1・§3.3 N2)。
3. **フラグ byte**: 全バイナリで `0x14f84a8` を参照する命令は **直接参照 0 件・ポインタ `0x15e0698` 経由 44 ロード (read 38 / write 6)**。write は全て `0x10c7cd0` 内。
   静的初期値 `0x00`。read は bit2 (0x04) 20 ロード/18 関数・bit0 (0x01) 12/12・bit1 (0x02) 5/5・その他 1 (§3.1)。
4. **実機械語の観測 (ILRegKey 無し/空)**: 5 入力 (A1–A4, D2) の全てで 終了 ok・**flag = 0x00・gradeChar = 0x40**。MachineGuid・ComputerName・AppData を変えても不変 (A1/A3/A4)。
   ネガティブコントロール 3 件 (N1–N3) は期待どおりに値が変わる (§3.3・§4)。
5. **ILRegKey 非空 (vreg seed のプレースホルダ・非正規 16 進) は未観測**: 復号 VM のハンドラ表 (unit 初期化で作られる) が無く null deref で停止 (3 入力: B1/B2/D1)。
   ilreg の静的予測「プレースホルダは全ティア grade 0 → gradeChar 0x40・flag 0」は**動的には未確認** (§5・§6)。
6. **プロジェクト方針 (常に登録済み) との関係**: 「登録済み」の状態は gradeChar > 0x40 であって、flag byte の bit ではない (推定: 有効な primary tier 鍵は flag を 0 のまま gradeChar だけを `A`–`C` にする。§3.2)。
   vreg のプレースホルダ単体で gradeChar > 0x40 になる根拠は静的にも動的にも無い。→ 対策案は §6 (別 issue)。

## 1. 範囲と素材

| 項目 | 内容 |
|---|---|
| 対象 | `FLEngine_x64.dll` 26.1.7 win64 (`extracted/block00031_PE.bin`, 22,227,016 B, ImageBase `0x400000`)。VA は絶対 VA (ilreg REPORT と同表記) |
| 素材 | `fl-win64` のみ使用 (`toolchain-*`・`work-m11` は取得済みだが未使用: m11 の RetDec lift は間接 call 全滅のため 0x10c7cd0 の観測に使えない — `tools/m11/REPORT.md` §2) |
| 方針 | 観測のみ。ライセンスの生成・偽造はしない (入力は vreg seed の既存プレースホルダと、意図的な非正規値) |
| ツール | python 3.14・pefile・capstone 5.0.7・unicorn 2.1.4 (`license_obs.sh` が `uv pip install`) |

## 2. 成果物

| パス | 内容 |
|---|---|
| `license_obs.sh` / `env.sh` | 1 コマンド e2e (scan → run_cases → verify) |
| `peidx.py` | `.pdata` の関数境界ごとの capstone 逆アセンブル共通部品 |
| `scan_consumers.py` | フラグ byte と gradeChar の全 read/write サイト列挙 → `results/flag_sites.json`・`results/FLAG_SITES.md` (自動生成) |
| `emu_reg.py` | unicorn による `0x10c7cd0` 実行環境 (後述 §3.3) |
| `run_cases.py` | 入力ケース実行 → `results/cases.json`・`results/CASES.md` (自動生成) |
| `verify.py` | 検算 (capstone 非依存の生バイト走査・不変条件・ケース期待値) |

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

### 3.2 gradeChar `[[[0x15e4790]]+0xd0]` の全サイト (同スクリプト; 一覧は `results/FLAG_SITES.md` 後半)

`0x15e4790` → 変数 → オブジェクト → `+0xd0` の byte ポインタ、という経路のロードが **196** (read 189 / write 7)、**89 関数**。

| 分類 | ロード数 / 関数数 | 備考 |
|---|---|---|
| write | 7 / 3 関数 | `0x10c7cd0` ×5 (`0x40` 初期化 `0x10ca56d`・tier 確定 `0x10cbb12`/`0x10cd0db` (値=ループ添字 `0x41`–`0x43`)・期限切れ `0x3f` `0x10cf4c6`・`0x40` `0x10cf621`) / `0x10d3a30` (`0x3f`) / `0x11cb000` (`0x3f`) |
| read `== 0x40` | 62 / 34 | 同型の inline コード (24 関数 family を含むと推定) |
| read `== 0x3f` | 27 / 26 | この 26 関数は全て `== 0x40` も比較。ilreg/GATES の「24 関数」との差 2 は未照合 → §6 |
| read `> 0x40` | 50 / 41 | 登録済みのとき通る側 (下記 Trial 文言サイトを含む) |
| read `>= 0x41`〜`0x44` (4) / `== 0x42` (3) | 7 | tier 別分岐 (A/B/C) |
| read 条件未復元 (`setcc` 等) | 43 | 一覧に生の命令を記載 |

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
| B1/B2 | vreg seed のプレースホルダ (cl=0/1) | **停止** (`0x8c9d7c` null deref) | — | — |
| D1 | 16 進 128 文字の非正規値 | **停止** (同) | — | — |
| N1 | A1 + gradeChar 初期値 imm `0x40`→`0x42` に改変 | ok | 0x00 | **0x42** |
| N2 | A1 + `or flag,1` 直前の `jle` を nop 化 | ok | **0x01** | 0x40 |
| N3 | A1 + flag 初期化の元値 `0x10d08d8` を `0x04` に改変 | ok | **0x04** | 0x40 |

読み取った registry 値 (A1; 実行トレース): `HKCU\Software\Image-Line\Registrations` の `FL Studio license plate`/`FL Studio user name`/`FL Studio webpass`/`FLS Info`、`HKLM\SOFTWARE\Microsoft\Cryptography` の `MachineGuid`
(`RegOpenKeyExA`, access `0x20019`)。続いて `…\Registrations\FL Studio 26.1` を HKCU・HKLM の順に開こうとする (無いので ILRegKey は読まない)。
**MachineGuid・ComputerName・AppData は ILRegKey の有無に関わらず先に取得される** (A1 の API 呼出順: `LoadLibraryW(SHFolder)` → `GetComputerNameExW` → `RegOpenKeyExA(HKLM Cryptography)`)。ただし ILRegKey 無しでは結果に影響しない (A1=A3=A4)。
B/D1 の停止点: ILRegKey を読んだ後の復号 (`0x8d0380` 系, ilreg FORMAT §5) で、`0x8c5c90` が返す singleton の byte 添字表 (`[obj+8+idx*8]`, `0x8c7820`) が null。表は unit の初期化節で作られるため、`InitUnits` を実行しない本環境では空。

## 4. 検証 (コミット済み HEAD `56e0379` をクリーン worktree に展開して実行)

| 項目 | 実測 |
|---|---|
| `bash license_obs.sh` (venv 作成済み) | 68.78 / 68.94 / 69.06 秒 (n=3 直列, 4 コア runner, load average 1 分値 0.89 / 0.97 / 0.99)。内訳: scan 5.8 秒・run_cases 62.5 秒 (11 ケース × PE 敷設)・verify 0.36 秒 |
| 結果 | 3/3 回 `ALL OK` (verify 16 項目 PASS)。再生成した `results/*` はコミット内容と `cmp` 一致 (決定的) |
| 別アルゴリズム検算 | capstone 非依存の生バイト走査 (`REX.W 8B /r` + `rip` 相対 rel32 から実効アドレスを逆算) が、スロット `0x15e0698` のロード 44 件を capstone 結果と **集合として完全一致** (差 0)。`0x15e4790` 経路 196 は生走査 2,422 ロードの部分集合 |
| ネガティブコントロール | N1 (gradeChar 初期値改変) → 0x42 / N2 (jle 無効化) → flag 0x01 / N3 (初期化元値改変) → flag 0x04。いずれも **実行された機械語の書込が観測値に反映される**ことを示す |
| 規約チェック | `git status --porcelain -- tools/startup/license_obs` 空・`find tools/startup/license_obs -type f -size +20M` 空 |

検証範囲: ILRegKey 無し/空での 0x10c7cd0 の終状態 (flag・gradeChar)、フラグ/gradeChar の静的サイト一覧。
範囲外: ILRegKey 非空 (有効書式を含む) の判定結果、unit 初期化後の状態、実エンジンの boot 経由の呼出、bit の意味ラベルの確定 (文字列からの**推定**)。

## 5. 問い (issue 範囲) への回答

| issue の項目 | 回答 | 確度 |
|---|---|---|
| bit0/bit1 の実測 | bit0・bit1 とも ILRegKey 無し/空では 0 (実機械語)。bit0 を立てる経路は実行されない。bit0=Trial は **反証** (§3.1) | 実測 (A1–A4, D2) / 意味ラベルは推定 |
| ILRegKey 無しの挙動 | 例外なく終了。flag 0x00・gradeChar 0x40 → Trial 文言サイトの偽側 (§3.2) に入る。起動は継続 | 実測 (flag/gradeChar) / UI 帰結は静的 |
| Trial 制限範囲 | gradeChar を参照する 89 関数 (条件を復元できた read 146 ロード) のうち、"Trial" 文言を持つ 13 ロードを列挙 (§3.2)。FL Cloud バックアップ、Undo テスト、ようこそ画面ほか。制限の**機能的全容**は文字列で見える範囲のみ | 静的 (線形パスの文字列; 目安) |
| MachineGuid 依存 | ILRegKey の有無に関わらず MachineGuid/ComputerName/AppData を取得するが、ILRegKey 無しの結果には影響しない (A1=A3=A4)。非空 ILRegKey での依存は ilreg の静的結論 (SHA-256 マシン束縛) のまま | 実測 (無鍵) / 静的 (有鍵) |
| GATES.md G04 の確定 | 反映済み (同 PR)。確定できない部分は「未確定」と明記 | — |

## 6. 未解決・次の一手

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lift 経路 (flelift/boot) で `0x10c7cd0` が実行されたときの観測 (本題 #107) | boot が unit 209/942 で停止中のため不可 | #107 に残 (boot 突破後に `license_obs/emu_reg.py` の期待値と突合) |
| ILRegKey 非空の判定結果の動的確認 | プレースホルダが gradeChar 0x40 のままか未確認 (静的予測のみ) | **#525** `[ST-T15]` (unit 初期化節の実行 = VM ハンドラ表の構築を `emu_reg.py` に追加) |
| 「常に登録済み」を満たす手段の設計: gradeChar を `A` 以上に確定させる (有効書式の ILRegKey は #116 のユーザ .reg / ホスト側後処理 / vreg での合成) と、期限切れ `?` への書換え 2 経路 (`0x10d3a30`・`0x11cb000`) の抑止 | 現 seed のままでは Trial 扱い (推定) | **#526** `[ST-T16]` (+ #116 へコメント) |
| `== 0x3f` を比較する inline 関数が 26 (本調査) と 24 (GATES/ilreg) で不一致 | G04 補足の「24 関数」の根拠再確認 | #107 コメント |
| bit の意味ラベル (bit1=Fire、bit2=Fire 鍵免除) と tier キー 31000/31005/31010/31020 の製品対応 | G04 の記述は「推定」止まり | #107 コメント (#213 は closed。後継の ST-T14 番号は #39 に使用済みのため新規番号は PM 確定) |
| 経路ごとの機能的な Trial 制限の全容 (文字列を持たない分岐 43 ロード等) | Trial 制限範囲は「見える範囲」 | #525 + FLEngine boot 後の動的観測 (#107 に残) |

ユーザ依頼事項: なし (素材は `fl-win64` で足りた)。

## 7. 事前推定と実測の差

- 事前推定 (GATES G04 / startup REPORT): 「bit0 = Trial/未登録」→ **反証** (§3.1)。Trial 文言は gradeChar と bit2 で決まる。
- 事前推定 (issue): 「T1 待ち」(#102 glue 完了待ち) → glue は完了済みだが、実行経路の律速は FLEngine boot (unit 209/942)。
