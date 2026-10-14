# modulation 付録 (#527 PLG-F5-2 engine gate)

本体 `REPORT.md` の §4 (engine 4 本) の到達性 gate。判定は `engine_judge.py` (exit code 化)。

## I. engine 到達性 gate (受入 1 の exit code 化)

- 判定: `engine_judge.py <outdir>` (`engine_lift.sh` の出力 `summary.csv` と `engine_name_gap.py` の名前照合)。
  - 合格: `lift_rc == 0` かつ `erc3 == 0` かつ define 無し range (名前照合後) が 0 件 (0 B)。exit 0。
  - 不合格: 上記のどれかが欠ける。exit 1。
  - 入力不正 (summary.csv の欠落・列数・非整数、名前照合の失敗)。exit 2。
- 出力行には `stub=` (未実装 helper 数) を必ず併記する。stub を含む `emcc -c` 通過は正しさを示さない (bit-exact は #197 で未検証)。
- ネガティブコントロール: `engine_judge.py --selftest` (合成入力 8 ケース、全て期待 exit と理由文字列を確認)。

### I.1 NC (selftest、HEAD の commit で実行)

| ケース | 期待 exit | 実測 exit | 理由の文字列 |
|---|--:|--:|---|
| 無改変 (good) | 0 | 0 | PASS |
| `lift_rc=1` | 1 | 1 | `lift_rc=1` |
| `erc3=1` | 1 | 1 | `emcc_c_rc(erc3)=1` |
| `function_2000` の define を除去 (名前照合で解決不可) | 1 | 1 | `define 無し range 1 件` |
| 同名 `entry_point` の欠落 range 2 件 (define 1 件) | 1 | 1 | `define 無し range 2 件` |
| 列数不足 (16 → 15 列) | 2 | 2 | `列数` |
| 非整数 (`x`) | 2 | 2 | `整数` |
| summary.csv 無し | 2 | 2 | `summary.csv` |

`selftest: OK` (exit 0)。

### I.2 実測 (4 本、`engine_lift.sh <block> 300` の順次実行、`engine_judge.py` で判定)

- 測定値の正本は `REPORT.md` §4 の表 (lift_rc・define 数・未実装 helper・erc3)。ここには持たない。
- 判定結果 (前 run の記録。本 PR では未再現): 4 本とも `define 無し (名前照合後)` 0 件 (0 B)、judge PASS (exit 0)。REPORT.md §4 の「4 本すべて `emcc -c` rc 0」も同じ前 run の記録。
  - 名前照合の内訳 (define 無し 2 件の解決先): 18977 `dispatch` + `entry_point` / 19143 `DispatchToEngine` + `entry_point` / 19266 `VSTPluginMain` + `entry_point` / 19268 `entry_point` + `VSTPluginMain`。
- 測定 commit: origin/main 2b99366a の上に `engine_judge.py` を追加した worktree (`ws-527`)。lift 本体は未変更。

#### I.2.1 生データの所在 (未取得の項目)

本 run では 4 本の lift を再実行できない (`toolchain-retdec`・`toolchain-emsdk`・`work-liftlib`・`work-fw-stage1` 未取得。`/opt/emsdk` 無し)。上記の判定結果は前 run の記録で、本 PR では再現していない。

| 項目 | 状態 |
|---|---|
| `summary.csv` の 4 行 (`engine_lift.sh` の出力) | 未取得 (`work/` は gitignore。raw が残っていない) |
| `engine_name_gap.py` の出力 4 行 (`named,rest,rest_bytes,unresolved`) | 未取得 (同上) |
| 測定の run 日時・終了時 loadavg・並列数 | 未記録 (順次実行。loadavg は取っていない) |
| 測定 commit の `git rev-parse` 確認 | 本 run では `ws-527` を確認できず未確認 |

上の 4 項目が揃うまで、「名前照合で 4 本とも define 無し 0」は実測として扱わない。
- 注意: この gate は到達性のみ。stub (未実装 helper) を含み、bit-exact は未検証 (#197・#534・#779)。
- 受入 1 の残り: judge 相当の exit code gate は本 PR で追加。bit-exact は #197 依存のため未達。

## J. 殻の動的ロード呼出の静的特定 (受入 5 の残り)

対象 4 殻 (18978 / 19144 / 19265 / 19267、fl-win64 の `extracted/` を pefile + capstone で解析)。スクリプトは `engine_shell_gpa.py`。

- KERNEL32 の import thunk (`jmp qword ptr [rip+…]`) を経由する呼出を列挙。thunk は殻ごとに求め直す (アドレスは殻で異なる)。
- `LoadLibraryExW` の呼出は 4 本とも 1 箇所 (FS 0x415b7b / HC・VC・VP 0x4158ab)。`LoadLibraryW` は 4 本とも 9 箇所、`LoadLibraryA` は 1 箇所。
- `GetProcAddress` の呼出は 4 本とも 10 箇所。そのうち `GetLogicalProcessorInformation` / `GetThreadPreferredUILanguages` / `GetLongPathNameW` など 6 箇所は引数の文字列を取れた (エンジン関係ではない)。残り 4 箇所は引数が中継関数 (FS 0x41d450 は KERNEL32 の `GetProcAddress` import thunk、0x418350 など。VC 0x41d1a0 / 0x4180d0 なども同様に中継) 経由で、文字列を静的に取れていない。中継関数のアドレスは `engine_shell_gpa.py` の出力には含まれず、出典 (手作業の逆アセンブルか否か) は未記録のため、未検証の値として扱う。
- 殻内の engine export 名は UTF-16 で入る (ASCII は無し)。FS: `dispatch` 0x2dda92、HC: `DispatchToEngine` 0x2e9722、VC / VP: `VSTPluginMain` 0x2d9dd8 / 0x2db668。engine 名 `Engine_x64.dll` (FS, 0x1a2b58) / `engine_x64.dll` (HC 0x2e9704, VC 0x2e9da4, VP 0x2ecfc4)。
- 結論 (推定): 殻は `LoadLibraryExW` を 1 箇所で呼び (スクリプトで確認)、その引数が `engine_x64.dll` であること (推定。LoadLibraryExW 行の引数は未取得)、`GetProcAddress` のラッパー経由で export 名を引く、という構造と推定する。ラッパーに渡る引数の実値 (どの export 名を引くか) と、VST2 engine の `VSTPluginMain` 呼出箇所は未了。受入 5 は未達のまま #527 に残す。

## K. 殻の engine 名参照と呼出経路 (受入 5 の続き、`engine_shell_entry.py`)

測定 commit: `c5627440` (コード差分の最終 commit)。`git diff c5627440 HEAD -- tools/plugins/modulation/ ':(exclude)*.md'` の出力: 空 (コード・データの差分 0)。`*.md` を含めた差分は本付録の文書修正 (76a434aa 以降) のみ。
用語: 「thunk」= KERNEL32 の import thunk (`jmp [rip+…]`)、「ラッパー」= thunk を呼ぶ関数 (§J と統一)。

測定: `python3 modulation/engine_shell_entry.py <block_PE.bin>` (fl-win64 extracted の殻 4 本、静的のみ)。

| 殻 | engine 名の lea 参照 (VA) | 直後の call 先 (ラッパー) | 所見 |
|--:|---|---|---|
| 18978 (FS) | `Engine_x64.dll` 0x6de5b3 → `0x4106d0` / `dispatch` 0x6de5df → `0x41d460` | `0x41d460` (ラッパー) → `0x41d450` (`GetProcAddress` の thunk) | 同一関数内で DLL 名を `0x4106d0` に渡し (呼出先の同定は未了)、続けて `dispatch` を `0x41d460` 経由で解決 |
| 19144 (HC) | `engine_x64.dll` 0x6ea244 → `0x410400` / `DispatchToEngine` 0x6ea270 → `0x41d1e0` | `0x41d1e0` (ラッパー) → `0x41d1d0` (`GetProcAddress` の thunk) | FS と同型 |
| 19265 (VC) | `engine_x64.dll` 0x6ea7ff → `0x410400` | 名前 `VSTPluginMain` の lea 参照は本スクリプトでは見つからず | 未確定 |
| 19267 (VP) | `engine_x64.dll` 0x6eda1f → `0x410400` | 同上 | 未確定 |

- FS・HC は「DLL 名 → ラッパー」の直後に export 名を解決する形で、殻が engine を動的ロードして名前で関数を引く推定と整合する (静的な推定。ラッパーの内部で `GetProcAddress` が実際に呼ばれることは未確認)。
- VC・VP は `VSTPluginMain` の文字列の直接参照が見つからない。VST 系の名前は別経路 (間接・連結・別の文字列表現) の可能性があり、未解析。
- 殻の `GetProcAddress` 10 箇所のうち、ラッパー経由の 4 箇所 (今回検証した FS の呼出 `0x41d48e` / `0x41d4b9` を含む) の引数の実値はこれで取れていない。上記の名前参照は、その呼出の一部に対応する。

## L. 殻の engine export 名の lea 参照と呼出先 (受入 5、`engine_shell_chain.py`)

測定: `python3 modulation/engine_shell_chain.py <block_PE.bin>` (fl-win64 extracted の殻 4 本、静的のみ、rip 相対 lea のみ列挙)。
§K (`engine_shell_entry.py`) と §L (`engine_shell_chain.py`) は、どちらも文字列の全出現を `find` の繰り返しで走査する (`engine_shell_entry.py` は VA ごとに `setdefault` で登録)。殻 4 本で両スクリプトの lea 参照と直後の call 先を突き合わせ、一致を確認した。§L は §K の表を呼出先の確認も含めて再確認したもので、置換ではない (§K は履歴として残す)。VC/VP の `VSTPluginMain` は両スクリプトとも rip 相対 lea を検出しない。

| 殻 | 文字列 (VA) | lea 元 → 直後の call | 所見 |
|--:|---|---|---|
| 18978 (FS) | `Engine_x64.dll` (0x6de674) | 0x6de5b3 → `call 0x4106d0` → `call 0x4409d0` (LoadLibraryW thunk 0x41d6d0 を含む) | DLL 名を読み込む経路 |
| 18978 (FS) | `dispatch` (0x6de692) | 0x6de5df → `call 0x41d460` | `0x41d460` は `GetProcAddress` thunk 0x41d450 を呼ぶラッパー。引数は `rcx=module`、`rdx=name` |
| 19144 (HC) | `engine_x64.dll` (0x6ea304) | 0x6ea244 → `call 0x410400` | DLL 名 |
| 19144 (HC) | `DispatchToEngine` (0x6ea322) | 0x6ea270 → `call 0x41d1e0` | `0x41d1e0` は GetProcAddress thunk 0x41d1d0 を呼ぶラッパー。FS と同型 |
| 19265 (VC) | `engine_x64.dll` (0x6ea9a4) | 0x6ea7ff → `call 0x410400` | DLL 名 |
| 19265 (VC) | `VSTPluginMain` (0x6da9d8) | rip 相対 lea なし | `.data` (0x73e448 / 0x73e4d8) に絶対アドレスの pointer が 2 件。呼出箇所は未特定 |
| 19267 (VP) | `engine_x64.dll` (0x6edbc4) | 0x6eda1f → `call 0x410400` | DLL 名 |
| 19267 (VP) | `VSTPluginMain` (0x6dc268) | rip 相対 lea なし | `.data` (0x741720 / 0x7417b0) に絶対 pointer 2 件。呼出箇所は未特定 |

- FS・HC は「DLL 名 → 読込」「export 名 → GetProcAddress ラッパー」の 2 段で、殻が engine を名前で動的ロードする推定と整合する。
- ラッパーの実引数 (`rdx`) は `lea` の対象文字列であることをバイト列で確認 (FS: `dispatch`、HC: `DispatchToEngine`)。
- VC・VP の `VSTPluginMain` は rip 相対の lea が無く、`.data` 内の絶対 pointer 2 件だけが一致した。その pointer を読む箇所は未特定 (`.data` の値が文字列 VA と一致することの確認まで)。受入 5 の VST2 部分は未達。

判定: 受入 5 のうち FS・HC の export 名取得経路は実測で確定。VC・VP の呼出経路と、殻との結合方式全体の確定は未了 (本 issue に残す)。

## M. VC / VP の VST 名参照経路 (受入 5 の続き、`engine_shell_vst.py`)

測定: `python3 modulation/engine_shell_vst.py <block_PE.bin> <string_va>` (静的のみ、fl-win64 extracted の殻)。測定 commit: `1efae651` (スクリプト追加のみ。殻の解析結果は本付録の記録)。

- **VC (19265)**: `VSTPluginMain` (0x6da9d8) を指す `.data` の 8 バイト slot は 2 件 (0x73e448 / 0x73e4d8)。どちらも 26 要素の名前表 (0x73e440〜0x73e4f0、各要素は文字列 VA) の中にある。表を読む参照は rip 相対で 0x73e428 / 0x73e430 / 0x73e438 / 0x73e440 の 4 箇所。
- 表を読む解決関数は `0x6db460`。0x6db488 の `lea rbx, [rip+0x62fb1]` で表を取り、`0x1a` (26) 件を反復して `0x6db430` (名前 → モジュール解決) を呼ぶ。`0x6db460` の唯一の呼出元は `0x6df130`。
- `0x6df110` (呼出元 `0x6df130` を含む) は `0x6db430` で解決し、失敗時に `0x6db460` (名前表の総当たり) へ進む。`0x6df110` への direct call は無い (関数ポインタ経由と推定)。`.text` 0x6da390 に `0x6df110` を値とする 8 バイト slot が 1 件あり (0x6da180 には `0x6df190` の slot)、その slot を読む rip 相対参照は検出していない (未確定)。
- **VP (19267)**: `VSTPluginMain` (0x6dc268) の slot は 2 件 (0x741720 / 0x7417b0)。近傍 0x741700〜0x741718 の表を lea/rip で参照する。VP の解決関数は未追跡。
- 判定: VC の名前表 → 解決関数 `0x6db460` → `0x6df110` までは静的に確定。`0x6df110` を実際に呼ぶ経路 (間接呼出の読み手) と、VP の解決関数は未了。殻と engine の結合方式全体は未確定のまま、受入 5 は本 issue に残す。

## N. VST 入口解決の経路 (受入 5 の続き、本 run の測定)

測定 commit: `f3c97305` (`engine_shell_ripref.py` の修正。コード差分の最終 commit。修正前は `8505816a`)。`git diff f3c97305 HEAD -- tools/plugins/modulation/ ':(exclude)*.md'` の出力: 空 (以後の差分は本付録の文書のみ)。
測定対象は fl-win64 素材の殻 2 本 (`$ARTIFACTS_DIR/fl-win64.tar.zst` の `extracted/block19265_PE.bin` = VC、`block19267_PE.bin` = VP)。静的のみ。測定コマンドは §N.6。
スクリプト: `engine_shell_ripref.py` (全バイト位置の総当たりで rip 相対・rel32・abs32 の参照を列挙)、`engine_shell_func.py` (.pdata 範囲・直接呼出元・関数ポインタ slot・逆アセンブル、IAT の import 名を付与)、`engine_shell_names.py` (名前表の復元)、`engine_shell_vst.py` (§M)。
負の対照 (`engine_shell_ripref.py` の取りこぼし検出、§N.6 の 1・2): VC の `0x75158c` を `-n 1` で引くと、修正前 (`8505816a` と同一のスクリプト) は 0 件、修正後 (`f3c97305`) は 4 件 (`0x6e60f9` add・`0x6e6100` cmp・`0x6e6160` sub・`0x6e6167` cmp)。`-n 0` は修正前後とも同じ 4 件。
正の対照: 既知の参照 (`0x6df130`→`0x6db460`、`0x6db488` の `lea`→`0x73e440`、`0x6dcd18` の `lea`→`0x741718`) を全て検出 (§N.6 の 3・5)。

### N.1 名前表 (VC 0x73e440 / VP 0x741718、各 26 件)

- 26 件は全て UTF-16 文字列へのポインタで、VC と VP で同一の並び。
- 内訳: `main` の大文字小文字違い 16 通り (index 2〜17) と、`VSTPluginMain` の大文字小文字違い 9 通り (index 0・1・18〜25)。index 1 と 19 は同じ文字列 (`VSTPluginMain`) の重複。
- 解釈 (推定): 殻は VST2 入口を GetProcAddress の大文字小文字違いで総当たりする。engine 側の export は `VSTPluginMain` / `main` (§J・REPORT §4)。

### N.2 名前表の読み手 (rip 相対 lea を全位置から総当たりで列挙)

| 殻 | 表 VA | lea 元 | 関数 (.pdata 範囲) | 役割 | 呼出 |
|---|--:|--:|---|---|---|
| VC | 0x73e440 | 0x6db488 | 0x6db460 (size 0x79) | 26 件を反復し、各名前を 0x6db430 に渡して非 0 の結果を返す | 直接: 0x6df130 (0x6df110 の内側) のみ |
| VC | 0x73e440 | 0x6e6121 | 0x6e60f0 (size 0x51) | 初期化らしき分岐 (推定): counter (0x75158c) を `add` (0x6e60f9) し、加算後の値が 0 のとき (`cmp` 0x6e6100 の後、`jne` 0x6e6107 で分岐しないとき) 0x40e720 を 2 回呼んでから 0x411680 を r8=26 で呼ぶ。0x40e720・0x411680 の役割は未確認 | 間接: .text 関数ポインタ slot 0x6eff28 のみ |
| VP | 0x741718 | 0x6dcd18 | 0x6dccf0 (size 0x79) | VC の 0x6db460 と同型 | 直接: 0x6e09c0 (thunk 0x6e09a0 の内側) のみ |
| VP | 0x741718 | 0x6e79f1 | 0x6e79c0 (size 0x51) | VC の 0x6e60f0 と同型 (命令列を照合済み) | 間接: .text 関数ポインタ slot 0x6f3668 のみ |

- VC の 0x6e60f0 は本 run で初めて確認した読み手 (§M までは 0x6db488 のみ)。

### N.3 入口 thunk と .text 内の関数ポインタ表

- 入口 thunk: VC `0x6df110` (size 0x2b) / VP `0x6e09a0` (size 0x2b)。引数 rdx = module、r8 = 名前。r8 ≠ 0 なら GetProcAddress ラッパーで名前を解決し、失敗時と r8 = 0 のときは名前表の総当たり (0x6db460 / 0x6dccf0) へ進む。
- 入口 thunk は直接 call・rip 相対参照・abs32 のいずれでも参照されない (§N.6 の 3・5)。.text 内に 8 バイトの値として 1 件だけ存在する (VC slot `0x6da390`、VP slot `0x6dbc20`)。
- その slot は 136 件の関数ポインタ表の中にある (VC 0x6d9f60〜0x6da3a0、VP 0x6db7f0〜0x6dbc30。いずれも末尾は排他的上限)。136 件は全て `.text` 内の値で、互いに異なる (§N.6 の 8)。入口はどちらも表の index 134。
- 表を指す参照 (±0x220、§N.6 の 4・6。引数は表の先頭・中央・終端の 3 点):
  - 表の外側から始まる命令のうち、表の内側を指すものは 0 件 (VC・VP とも)。
  - 表の内側から始まる命令は VC 4 命令 (出力 6 行)、VP 2 命令 (出力 2 行)。いずれも表のバイト列 (関数ポインタ) を命令として誤デコードしたもの。その出力行のうち表の内側を指すものは VC 5 行 (`0x6da0a8`・`0x6da0b8`・`0x6da221`)、VP 2 行 (`0x6db928`・`0x6db970`)。
  - 表の終端 (排他的上限) と等しい 8 バイト値が .text に 1 件ずつある (VC slot `0x6d9f28` = `0x6da3a0`、VP slot `0x6db7b8` = `0x6dbc30`)。表の先頭 (`0x6d9f60` / `0x6db7f0`) と等しい値は無い。終端値の読み手は未確認。
- 結論: 入口 thunk を呼ぶ読み手 (= VST2 入口の呼出元) は静的には未特定。読み手は基点を計算で作る間接参照と推定 (未検証)。VC の PE ファイル内の `e8 00 00 00 00` (call 次命令) は 49 件 (§N.6 の 9)。位置取りの可能性は未検証。

### N.4 GetProcAddress の経路 (推定を含む)

- VC: 0x6db430 → 0x40ffe0 → 0x41d1b0 → 0x41d1a0。0x41d1a0 は `jmp qword ptr [rip+…]` で、IAT の `kernel32!GetProcAddress` を指す (`engine_shell_func.py` で確認)。
- VP: 0x6dccc0 → 0x40ffe0 → 0x41d1d0 → 0x41d1c0 (IAT `kernel32!GetProcAddress`)。
- 確認済み: 0x6db430 の `call 0x40ffe0` (0x6db444) と `call 0x41d1b0` (0x6db44f)、0x6dccc0 の `call 0x40ffe0` と `call 0x41d1d0` (§N.6 の 7)。
- 確認済み: 0x41d1b0 は `shr rax,0x10; test rax,rax; jne` で `rdx` の上位 48 bit を見る。0 (序数) なら 0x41d1a0 へ `rdx` のまま渡し、非 0 (名前) なら 0x40f340・0x40f820 を経由してから 0x41d1a0 へ渡す (0x41d1d0 も同じ形で、序数側は 0x41d1c0 へ渡す)。
- 推定を含む: 0x40ffe0 は `rcx` が非 0 ならそのまま返し、0 なら `[rip+0x2f4c31]+0x10` を返す (4 命令)。この関数の役割 (名前の変換など) と 0x40f340・0x40f820 の役割は未確認。

### N.5 判定

- 確定: 名前表 26 件の内容、名前表の読み手 (各殻 2 件)、入口 thunk の構造、GetProcAddress の経路 (IAT まで。0x40ffe0 の役割を除く)。
- 未確定: 入口 thunk (VC 0x6df110 / VP 0x6e09a0) を呼ぶ箇所、すなわち VST2 engine の `VSTPluginMain` 呼出元。関数ポインタ表の読み手も未特定。表の終端値 (§N.3) の読み手も未特定。
- 受入 5 のうち VC/VP の呼出元は未達のまま #527 に残す。

### N.6 測定コマンド (測定 commit `f3c97305`)

`<VC>` = `extracted/block19265_PE.bin`、`<VP>` = `extracted/block19267_PE.bin` (`$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf` で展開したもの)。作業ディレクトリは `tools/plugins/modulation/`。値は全て 16 進 (`-n` の値も 16 進)。

1. `python3 engine_shell_ripref.py <VC> -n 1 75158c` → ref 4 行 (負の対照)。修正前 (`8505816a`、スクリプトは同一) は 0 行。
2. `python3 engine_shell_ripref.py <VC> -n 0 75158c` → ref 4 行 (同上)。
3. `python3 engine_shell_ripref.py <VC> -n 0 6db460 6df110 6e60f0 73e440` → 出力 11 行。`0x6db460` は `0x6df130` の call のみ、`0x6df110` は slot `0x6da390` (abs32 も同じ位置) のみ、`0x6e60f0` は slot `0x6eff28` のみ、`0x73e440` は `0x6db488`・`0x6e6121` の lea の 2 件。
4. `python3 engine_shell_ripref.py <VC> -n 220 6d9f60 6da180 6da3a0` → 出力 31 行。§N.3 の分類 (表の内側から始まる命令 4 件・6 行、外側から内側を指す参照 0 件、終端値 slot `0x6d9f28`)。
5. `python3 engine_shell_ripref.py <VP> -n 0 6dccf0 6e09a0 6e79c0 741718` → 出力 11 行。`0x6dccf0` は `0x6e09c0` の call のみ、`0x6e09a0` は slot `0x6dbc20` のみ、`0x6e79c0` は slot `0x6f3668` のみ、`0x741718` は `0x6dcd18`・`0x6e79f1` の lea の 2 件。
6. `python3 engine_shell_ripref.py <VP> -n 220 6db7f0 6dba10 6dbc30` → 出力 25 行。表の内側から始まる命令 2 件 (2 行)、外側から内側を指す参照 0 件、終端値 slot `0x6db7b8`。
7. `python3 engine_shell_func.py <VC> <va> --dump` (`va` = 6db430・6e60f0・40ffe0・41d1b0)、`python3 engine_shell_func.py <VP> <va> --dump` (`va` = 6dccc0・6e79c0・41d1d0)。§N.2・§N.4 の逆アセンブルの根拠。
8. 表の 136 要素: 表の範囲を 8 バイトずつ読み、値が `.text` 内にあり (VC・VP とも 136/136)、互いに異なる (136 種) ことを、インラインの python (`struct.unpack_from('<Q', ...)`) で確認。
9. `python3 -c "import sys;print(open(sys.argv[1],'rb').read().count(b'\xe8\x00\x00\x00\x00'))" <VC>` → 49。
