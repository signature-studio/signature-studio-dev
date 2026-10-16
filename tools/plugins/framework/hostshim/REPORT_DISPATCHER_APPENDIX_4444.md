# PLG-P0b-49 (#4444) — global 0x15e4790 の null 連鎖と 8 件の即値格納 gate

親 #4130。前提は `REPORT_DISPATCHER_APPENDIX_4130.md` §3 (8 件の即値格納は、gate 0x13280c9・0x132815f で `je 0x13281af` により分岐し、到達しない)。

## 1. 結論

- `0x15e4790` は `.data` (初期化済み) のスロットで、初期値は `0x141d6b8`。`*(0x141d6b8)` は `0`。この連鎖の先頭は PE 内の初期値では null。
- `0x15e4790`・`0x141d6b8` を rip 相対・絶対値で指す命令は、全 PE ブロックの `.text*` セクション (311 区間、測定 commit `88f0813e1`) を `hs_glob_alltext.py` で走査して 0 件 (STORE・REF・ABS 全て 0)。STORE はメモリ宛先を持つ全 mnemonic (`cmp`・`test`・`lea` を除く) を数える。計算アドレス経由は見ていない。データ域は全 313 PE ブロック (`*_PE.bin`) で検索し、`0x141d6b8` を指す qword は `block00031_PE.bin` の `0x15e4790` だけ。
- 受入 1 の判定: 書込み元 (VA) は静的に確定できない。書込みは (a) PE 外のランタイム、または (b) 計算アドレス経由の間接書込み、のどちらかと考えられるが、上記の範囲の走査では PE 内の書込み VA を列挙できなかった。
- 受入 2 の判定: `[rbp+0x89f]` の書込み元 `0x1326c34`・`0x1327f9a` は、基準 run の 256 ID のどれにも現れない。8 件を実行させる gate 側の入力は、この基準 run では与えられない。
- 受入 3 の判定: `hostshim.c` の応答表には反映しない。8 件の値は確定したが、到達させる gate の入力 (null 連鎖の先の値) が未確定で、表に入れても実行されない。Phase A 回帰は未実施 (§5)。

## 2. 測定条件

- 測定 commit は 2 つ。
  - 基準 run (`hs_disp_emu.py`): `151625a41`。`origin/main` `2e3c6d554` でも測り、同じ集計を得た。
  - 全 `.text*` 走査 (`hs_glob_alltext.py`・§3): `88f0813e1` (`hs_glob_alltext.py` 追加を含む最後の commit)。
- 素材: `fl-win64` の `extracted/*_PE.bin` (313 ブロック)。`block00031_PE.bin` (22,227,016 B) が Dispatcher を含む。Python venv に `unicorn 2.1.4`・`pefile`・`capstone 5.0.7`。
- 実測 (基準 run・測定 commit `151625a41`): 全 256 ID・既定・`HS_DISP_PATH=1`、real 72.3 秒、load 0.78 (uptime)。集計 (distinct (rax, path)・unmapped・組・ページ) は `REPORT_DISPATCHER_APPENDIX_4130.md` §1 と一致。`hs_glob_writers.py` の結果は §3。
- 実測 (全 `.text*` 走査・測定 commit `88f0813e1`): `FL_WIN64_DIR=<展開先> python3 hs_glob_alltext.py` → `text sections scanned: 311 (PE blocks: 313)`、STORE 0 / REF 0 / ABS 0。real 26.8 秒 (2 回目の再実行で同じ出力。load 0.68→0.80)。
- コード差分 (`hs_glob_alltext.py` 以外の実行コードが変わっていないこと):
  - `git diff --stat 151625a41 88f0813e1 -- tools/plugins/framework/hostshim/ ':!*.md'` → `hs_glob_alltext.py | 72 +` のみ。
  - `git diff 151625a41 88f0813e1 -- tools/plugins/framework/hostshim/hs_disp_emu.py tools/plugins/framework/hostshim/hostshim.c` → 0 行。基準 run の `151625a41` は有効。
  - `git diff 88f0813e1 HEAD -- tools/plugins/framework/hostshim/` → 0 行 (その後の commit は REPORT のみ)。

## 3. 受入 1: `0x15e4790` の連鎖

| 項目 | 値 | 根拠 |
|---|---|---|
| `G = 0x15e4790` の section | `.data` | `pefile` の section 範囲 |
| `*G` | `0x141d6b8` | `block00031_PE.bin` の memory image |
| `*(*G)` | `0x0` | 同上 (null) |
| `G` を含む qword (データ域) | `block00031_PE.bin` file+0x11e3190 の `0x141d6b8` が `G` の内容 | 全 313 ブロックの raw 検索 |
| rip 相対のメモリ宛先の書込み候補 (全 mnemonic、cmp/test/lea を除く、`G`・`P0` の ±0x40、全 311 `.text*` 区間、測定 commit `88f0813e1`) | 0 件 | `hs_glob_alltext.py` |
| 他の PE ブロックで `0x15e4790`・`0x141d6b8` を指す qword | 0 件 (`0x141d6b8` の qword は `block00031_PE.bin` にのみ存在) | `hs_glob_writers.py` (raw 検索) |

全 PE の `.text*` セクション走査 (`hs_glob_alltext.py`・測定 commit `88f0813e1`・全 313 PE ブロックのうち `.text*` を持つ 311 区間。`.text*` 以外のセクション名は確認していない):

| 種別 | 件数 | 意味 |
|---|---|---|
| STORE (rip 相対・メモリ宛先を持つ全 mnemonic (cmp/test/lea を除く)・G/P0 ±0x40) | 0 | 書込み候補 |
| REF (rip 相対・その他・G/P0 ±0x40) | 0 | 読み出し・lea |
| ABS (オペランドに G/P0 の絶対値) | 0 | 即値・絶対アドレス |

`block24418_PE.bin`・`block24751_PE.bin` は `.text*` セクションを持たない。

未確定 (受入 1 の列挙):
- `G` の初期化の書込み元: PE 内の VA として列挙できるものは無い (全 .text の走査で 0 件)。ランタイム (PE 外) で書かれると判断するのが妥当。
- 計算アドレス経由の書込みの有無: 全件の逆解析はしていない。`G` 自体の絶対値・rip 相対の直接参照だけを見ている。

## 4. 受入 2: 8 件の即値格納と `[rbp+0x89f]`

基準 run の path 上の出現 (IDs は 10 進、`base.json` の `path`):

| VA | 役割 | 基準 run で通る ID |
|---|---|---|
| 0x1326c34 | `[rbp+0x89f]` の書込み元 1 | 0 件 |
| 0x1327f9a | `[rbp+0x89f]` の書込み元 2 | 0 件 |
| 0x13280c9 | gate (`je 0x13281af`) | ID 108 のみ |
| 0x132815f | gate (`je 0x13281af`) | ID 109 のみ |
| 0x13280e1 | al の供給元 (0x1328104〜0x1328131 の入力) | 0 件 |
| 0x13280cf | `0x13280c9` 系の読み出し | 0 件 |
| 0x1328161 | `0x132815f` 系の読み出し | 0 件 |
| 0x1328098 | 即値 1 の格納 | 0 件 |
| 0x13281af | 分岐先 (gate 閉) | 229 ID |

- 8 件の即値格納 (0x1328098・0x1328104・0x1328114・0x1328124・0x1328131・0x132818a・0x1328197・0x13281a4) は、基準 run の 256 ID で一度も実行されない。
- 3 件の call 戻り値格納 (0x1320e23・0x13213f3・0x1322971) は REPORT_4130 §2 の通り。0x1322971 は ID 98 が 0x132296f まで届くが、格納には届かない。

## 5. 受入 3: hostshim.c への反映と Phase A

- `hostshim.c` の応答表への反映: しない。理由は §1 の通り (gate 入力が未確定。表に入れても実行されない)。
- Phase A (`hs_e2e.sh`) の回帰 `dispatch=38 ff=0`: **未実施**。`work-fw-stage1` (12 件) には `hs_e2e.sh` の前提 8 件が無い。8 件は `fw_stage2.sh` が emsdk で作る。emsdk は runner に無い (`which emcc` 無し)。本 PR は `hostshim.c` を変えていないため応答表は変わらないが、実測はしていない (REPORT_4130 §4 と同じ)。

## 6. 再現手順

```
FL_WIN64_DIR=<fl-win64 の展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_disp_emu.py  # 基準 (HS_DISP_PATH=1 HS_DISP_OUT=base.json)
FL_WIN64_DIR=<展開先> python3 hs_glob_writers.py   # §3 の qword 検索と block00031 の .text 走査
FL_WIN64_DIR=<展開先> python3 hs_glob_alltext.py   # §3 の全 PE の `.text*` 走査 (STORE/REF/ABS 全 0)
FL_WIN64_DIR=<展開先> python3 hs_store_supplier.py # REPORT_4130 §2 の 11 件 (再現)
```

- 素材: `fl-win64` の `extracted/*_PE.bin` (`tar --zstd -xf` で 313 件)。`block00031_PE.bin` が Dispatcher と `0x15e4790` を含む。
- 基準 JSON はリポジトリに入れない (`$RUNNER_TEMP/hs4444/base.json`)。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x15e4790` の初期化の書込み元 (PE 外のランタイム、または計算アドレス経由) | 8 件の gate 入力が未確定。8 件を実行させる条件が決まらない | #4444 (親) のチェックリストへ追記。PE 外の実行時の観測 (`hs_dbg_trace.py` 系) が必要。次に実施できる条件: ランタイムの書込みを計装する run |
| 3 件の間接 call の受け手 VA | 応答表への反映の可否 | #4443 (PLG-P0b-48) |
| Phase A 回帰 `dispatch=38 ff=0` の実測 | 応答表は未変更で影響なし。回帰の確認のみ | 本 PR の未解決。emsdk 6.0.12 の導入と `fw_stage2.sh` が走る run |

## 8. #5547 (PLG-P0b-60) の追記: 生バイト検索と再測定

測定 commit: `4a70740b7` (`hs_glob_bytes.py` の docstring のみ変更。`git diff 9364022b4 4a70740b7 -- tools/plugins/framework/hostshim/ ':!*.md'` は docstring 1 行。`hs_disp_emu.py`・`hostshim.c` は変更なし)。素材: `fl-win64` (`extracted/*_PE.bin` 313 件)。`work-fw-stage1` は展開したが、本測定では使わない (`fw_stage2.sh` の前提で、emsdk は未使用)。

- `hs_glob_bytes.py` (生バイト検索): `G = 0x15e4790` と `P0 = 0x141d6b8` の 4 バイト LE を全 313 PE ブロックの全セクションで検索 → 0x15e4790 の hit は `block00031_PE.bin` の `.data` (0x15e4790 自身の値 `P0`) の 1 件だけ。`.text` 内の hit は 0 件。実測 real 1.8 秒。
- 相対形式 (`G - ImageBase` 等) の検索: 未検証 (本 run では実施していない。受入 1 の根拠に使わない)。
- `hs_glob_alltext.py` を HEAD で再実行: `text sections scanned: 311 (PE blocks: 313)`、STORE 0 / REF 0 / ABS 0。real 23.6 秒、load 1.75→0.67。
- 基準 run (`hs_disp_emu.py`・`HS_DISP_PATH=1`・全 256 ID): real 49.7 秒、load 0.62。`distinct (rax, path) = 109 / IDs = 256`。§4 の表を本 run で再現した。

### 判定 (#5547 の受入)

- 受入 1 (`0x15e4790` の初期化元の VA): **未達**。PE 内の書込み VA は、生バイト検索 (`.text` 内 0 件) と `.text` の rip 相対 / 絶対の走査で 0 件。書込みは PE 外のランタイム、または計算アドレス経由と判断する。PE 外の書込み VA の列挙には、FL 本体の初期化を走らせて書込みを計装する必要がある。`hs_disp_emu.py` は dispatcher の 1 呼出しだけを走らせるため、この初期化は観測できない。
- 受入 2 (8 件のうち基準 run で実行されうる格納と、`[rbp+0x89f]` の経路): **未達**。基準 run の 256 ID では 8 件・`[rbp+0x89f]` 書込み元のどれも実行されない (gate 0x13280c9・0x132815f は 1 件ずつ、いずれも `je` で分岐して閉じる)。gate の入力 (`G` の連鎖の先の値) が未確定のため、8 件を実行させる条件を決められない。
- `hostshim.c` の応答表: 変更なし (受入 2 の結論どおり、到達しない値は入れない)。

### 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| PE 外の `G` 初期化の書込み VA (ランタイム計装) | 受入 1 の列挙が未完。gate 入力が決まらない | #4444 (親) のチェックリストへ追記。FL 本体の初期化を走らせる計装が必要 (dispatcher 単体の emulator では観測不可) |
| `[rbp+0x89f]` の書込み元の経路 (0x1326c34・0x1327f9a) | 基準 run で 0 件。gate 入力が決まらないと実行できない | 同上 |
| Phase A 回帰 `dispatch=38 ff=0` | 応答表は未変更のため影響なし。回帰の確認のみ | 本 PR の未解決。emsdk を使う `fw_stage2.sh` が走る run (#5185 の範囲) |
