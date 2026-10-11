# KH-11 — subscribe 経路の実 IR 化 + module E -O1 化 (CAB-247 残スコープ, 親 CAB-59/CAB-13)

- 1 コマンド再現: `bash tools/targets/kilohearts/license/run_all.sh` (実測 33〜36 s 単発・load average 2.79→2.90 (nproc=16)、`--zero-stack` はデフォルトで compare に付与済み)
- 独立再計算: `python3 scripts/kh11_audit.py` (出力は §4 に転記)
- 検証起点: HEAD `0d589e6` (feat(liftlib): leaf region phi synthesis) + 本変更。作業ツリー変更のみで clean HEAD 検証は §5 の手順参照
- 既知類型との関係 (規則 44): **DEFECTS.md D15 に該当** (stage-0 のメモリ間接 call 脱落 = functor vtable call)。tools/icall REPORT §4 系の **D1 とも同型** (別体系、RULES 44 の 2 系統表記)。thunk size 表は .pdata 非連続 (DEFECTS.md) D13 同型の隣 begin 近似

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| subscribe 経路 | **実 IR 化して bit-exact 達成**: `em` 200/200 trial (700/700 call)・`empoll` 1000/1000 trial (10,000/10,000 call)。c-tor→subscribe 0x1800526f0 が manager EventSlot へ poll1 functor を実登録する経路が wasm で native とビット一致 |
| 修復方式 | (a) **kh_lower [icall] pass を snapins 5d30dff から移植** (D15 修復)、(b) functor 経路 5 関数 + manager slot 起火 2 関数 + vtable dispatch thunk 4 本 + vector-compact 3 本を module E lift に追加 (25→44 関数)、(c) functor clone の offset qword コピーによる未初期化読みを native image パッチ + wasm IR の対称修正で 0 確定 |
| module E -O1 | **-O1 採用**: -O0/-O1 × `--volatile-ret` 有無の 4 組合せすべてが**回帰全項目 PASS** (exit=0)。-O1 = wasm **364,770 B** (-O0 439,208 B 比 **83.0%**、74,438 B 削減)。`--volatile-ret` は保険として維持 (同条件で 364,770/364,425 B 差 345 B) |
| 回帰 | run_all.sh **exit=0** (33 s)・lic_check **70/70**・em_check **ok=52 ng=0**・snapin 6 種 base/lic **200/200** bit-exact (12 系)・[4] em/empoll 上記 |
| 未解決 | emfire (manager slot 起火 E2E) は wasm 側の未 lift thunk (0x180003360・尾 `jmp rax`) で bit 不一致 → 起票先 (a) 本節 / (b) 親 CAB-13 に次タスク提案。0x1800f6540 lift・listener [sub+0x1170] 通知検証は未実施 → 起票先 (b) 親 CAB-13 |

## 1. subscribe 経路の実 IR 化 (残スコープ 1)

### 1.1 何が壊れていたか
V28 検収時点で subscribe 0x1800526f0 は `ret` no-op seam (scen_em.h の image パッチ)・lic_config の shims にも no-op 実装。functor 経路 (0x18001bf70/0x18001c0b0/0x18001c1d0 → 0x180024bd0/0x180025080) の **メモリ間接 call (vtable dispatch) が stage-0 で空ブロック** に落ちる (DEFECTS.md D15)。

### 1.2 修正
1. **`lift/kh_lower.py` に [icall] pass を移植** (snapins 5d30dff と同型): stage-0 空ブロック × 機械語 `call qword [reg+disp]` を検出し `kh_icall(slot)`  dispatch に置換。slot < 0x10000000 (アリーナ) は vtable entry 値で switch、それ以外は PE .rdata slot アドレスで switch (未知は fail-fast、メッセージに slot を出力)。加えて **callret fixup のリターンアドレスを `store i64 0` → 実call 直後 VA** に変更 (native の `call` push と同内容。未初期化スタック読みの bit 一致用)。
2. **module E lift を 25→44 関数に拡張**: subscribe 0x1800526f0 / メモリ間接参照经路 0x18001bf70・0x18001c0b0・0x18001c1d0 / slot push 0x180024bd0・0x180025080・0x18001efc0 / observer 登録 0x18002e710 / **manager slot 起火 0x18010b180・0x18010c010** / vtable dispatch thunk 0x18005b390・0x180003310・0x18005b430・0x18003f7f0・0x18003f810・**0x18003f7d0** / vector-compact 内部 0x18001e5d0 他。
3. **ARENA_CLEAR 導入** (harness/ctxfuzz.h): trial 冒頭の zero 化を `used` 累積から固定 0x10000 窓に変更 (subscribe が manager 側アドレス 0x0400F020 を使うため、累積 `used` 外の slot 状態が trial 間で残留すると両系で不一致)。
4. **functor offset 字段の 0 確定化**: FL コードは functor +0x18 を dword 部分的に初期化し (`mov dword [rbp-0x48], r15d`)、clone (0x18005b430/0x18003f7d0) が +0x18 を **qword** コピーするため、native 実スタックの call リターンアドレス残骸が invoke thunk (0x18003f7f0 の `movsxd rcx,[rcx+0x18]`) の rcx に漏れてワイルドポインタ化 → 0x180022be0 の `incl 0x30(%rcx)` で SIGSEGV を実測。本 closure の全 functor は offset=0 と機械語から確認できるため、(a) native image パッチで clone の `mov rcx,[rcx+0x18]` (48 8B 49 18) → `xor ecx,ecx; nop; nop` (同 4B)・functor 構築の dword store → qword store (44 89 7D B8 → 4D 89 7D B8, 同 4B)、(b) wasm 側は kh_lower で同機械語ブロックの rcx store を 0 に置換 (`clone_zero_offset: 2`) — 機能等価 (invoke は movsxd dword で読む) で両系 0 確定。
5. **fail-fast メッセージ改善** (gen_stubs_sigs.py): 未 lift callee 呼出で `unlifted callee 0x<VA>` を例外出力 (旧は無言 abort)。

### 1.3 結果 (bit-exact)
| scenario | trial | call 内訳 | 結果 |
|---|---:|---|---|
| `em` (ctor→poll1→poll2→writer) | 200 | ctor 200 + poll1 200 + poll2 200 + writer 100 = 700 | **200/200 bit-exact (700/700)** |
| `empoll` (状態注入 8 状態 sweep) | 1000 | ctor 1000 + poll1 1000 + poll2 8000 = 10,000 | **1000/1000 bit-exact (10,000/10,000)** |

## 2. manager slot 起火 E2E (残スコープ 2) — 部分達成・未解決

- `emfire` scenario を新設 (harness/scen_em.h・scenarios.c): ctor (subscribe 実登録) → register 0x18002e710 (editor document ctor 0x18002dc30 と同: [doc+0x100]+0x1b0 = **EM+0x1b0** に writer functor 登録) → **status 10 状態を fire/poll 前に注入** → 0x18010b180 (LicenseManager notify 0x18010a740 の EventSlot 起火部分) → poll1 → poll2 × 4。
- native oracle は完走。ctor・register の 2 call は **bit-exact (200/200)**。
- **fire (0x18010b180) の post-state が不一致** (例: trial 0 = PM+0xdf0/+0xe00 の 2 B、trial 1 = SUB+0x1088/+0x1108 他 4 B)。原因: fire 末尾の vector-compact (0x18001e440→0x18001e5d0) が ctrl vtable の delete thunk **0x180003360** (`mov rax,[rcx]; mov rax,[rax]; mov edx,1; jmp rax` = **尾の間接 jmp**) を dispatch する。kh_lower の [icall] pass は `call` 形のみ対象で `jmp` 形は未対応 (DEFECTS.md D15 の jmp 変異・tools/icall §4 体系の D9 相当)。
- run_all.sh では emfire を**情報提供** (exit code 非影響・WARN 出力) として実行。

## 3. 0x1800f6540 lift / listener 通知検証 (残スコープ 3・4) — 未実施

- **0x1800f6540 (editor content setup, 3,926 B)**: 未 lift。29 か所のメモリ間接 call (仮想 dispatch 24 + 共有ポインタ制御 5) を持ち、書込経路 `[+0x1088] = !thunkA(status)` (0x1800f6bfd `xor al,1`) の到達には editor content オブジェクト群の構築が前提。本ラウンドの時間内では収束せず。
- **listener あり property 通知** ([sub+0x630]/[sub+0x1170] 非 null): listener を非 null にした notification 経路の検証は未実施。listener 側の vtable dispatch (vtbl+0x20) も [icall] pass の対象になる見込み。
- いずれも**起票先 (b) 親 CAB-13 に次タスク提案コメント** (本 REPORT §6 を根拠に main が Linear に投稿)。

## 4. module E -O1 判断 (残スコープ 5) — 採用

4 組合せ (-O0/-O1 × `--volatile-ret` 有無) で**回帰全項目** (run_all.sh = lic_check・snapin 12 系・em・empoll・em_check) を実行:

| emcc_opt | volatile_ret | exit | em | empoll | em_check | wasm (module E) |
|---|---|---|---|---|---|---:|
| -O0 | true | 0 | 200/700 | 1000/10000 | ok=52 | 439,208 B |
| -O0 | false | 0 | 200/700 | 1000/10000 | ok=52 | 439,208 B |
| -O1 | true | 0 | 200/700 | 1000/10000 | ok=52 | 364,770 B |
| -O1 | false | 0 | 200/700 | 1000/10000 | ok=52 | 364,425 B |

**判断: -O1 を採用** (lic_config.json `modules.E.emcc_opt = "-O1"`)。根拠: (1) V28 再測・本マトリックスの 4/4 で KH-10 REPORT §5-5 の 「-O1 では TCE/DSE で ctor 半ばで trap」は**再現しない** (断定できないため KH-10 側も「再現せず」に修正済み)、(2) 74,438 B (17.0%) 削減、(3) `--volatile-ret` は TailCallElim 保険として継続 (345 B)。切替後の全回帰も exit=0 で再検証済み (§5)。

## 5. 検証 (規則 36〜41・45)

### 5.1 独立再計算 (`scripts/kh11_audit.py`)
数え方の定義: lift 関数数 = `lic_config.json modules.E.lift` VA 数 (関数 = .pdata 範囲) / icall サイト = 機械語 `call qword [reg+disp]` サイト (raw) とそのうち stage-0 空ブロックのもの / slot map = .rdata 中身が lift 済 VA の qword スロット / size = .pdata begin/end 差 (thunk は D13 同型近似)。
```
[1] lift 関数数 = 44 (lic_config.json modules.E.lift)
    .pdata 範囲あり 32 / なし 12 ['0x1800b4ac0','0x1800b4ad0','0x1800b4ae0','0x1800b4af0','0x1800b4b00','0x1800b20e0','0x18001ba90','0x18006be60','0x18005b430','0x18003f7f0','0x18003f810','0x18003f7d0']
    .pdata size 合計 = 10935 B
[2] icall サイト (別アルゴリズム: 機械語 call qword [reg+disp] 全scan、fnscan 範囲) = 97
    kh_lower 集計 (stage-0 空ブロックで絞込) = 77, 部分集合=True (kh_lower∖本scan=0, 本scan∖kh_lower=20 = 非空でないブロック)
[3] icall slot map (別アルゴリズム) = 4934, kh_lower = 4934, 一致 = True
[5] 既知類型: DEFECTS.md D15 に該当 = raw 97 サイト (空ブロック=77)。tools/icall REPORT §4 系 D1 とも同型 (別体系)
```
別アルゴリズム: pefile 生バイト + 自前 capstone scan + fnscan extent (kh_lower と同じ) / .rdata qword 全スキャン (kh_lower は numpy searchsorted)。

### 5.2 ネガティブコントロール (規則 41)
| # | 操作 | 結果 |
|---|---|---|
| 1 | clone offset の image パッチを外す (native) | subscribe 後の functor offset にリターンアドレス残骸 → invoke rcx ワイルド → emfire で SIGSEGV (0x180022be0 `incl 0x30(%rcx)`) |
| 2 | `--zero-stack` を外す (旧挙動) | functor clone の qword コピーで wasm スタック残骸が写り bit 不一致 (kh_stack と native C スタックの座標系差) |
| 3 | thunkA stub 値を 1→0 (lic_config の 0x1800b4ac0) | ok=2 ng=48 (47 製品すべて編集不可) — V28 検収と同型 |
| 4 | [icall] pass を `--skip icall` で無効化 | subscribe 経路の functor vtable call が空ブロックに戻り em が call 0 で不一致 (D15 再現) |

### 5.3 実行時間・負荷 (規則 38)
| 実行 | 実測 | load average (開始→終了) |
|---|---:|---|
| run_all.sh (-O1 採用後) | **33 s** (単発) | 2.90 → 2.90 (nproc=16) |
| -O1 マトリックス 4 組合せ | 各 33.3〜35.9 s | 同上範囲 |

### 5.4 検証範囲 / 範囲外 (規則 40)
- native 比較は **ctx-fuzz の arena 内 ms_abi 直接実行** (実 PE を ImageBase に RWX 敷設、image パッチで stub seam 両系一致)。**Windows 実機プロセス内で FL が動く状態との比較ではない**。
- manager slot 起火 (0x18010b180) の post-state bit 一致・0x1800f6540・listener [sub+0x1170] 通知・apply_key 実経路・UI 表示系は**未検証** (§2・§3)。
- subscribe no-op 時代の em/empoll との数値比較: call 種別は同一 (ctor/poll1/poll2/writer) だが、subscribe 実 IR 化によりアリーナの bump 割当系列が変化 (native/wasm 間では一致)。

## 6. 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| emfire の fire (0x18010b180) post-state が bit 不一致 (vector-compact の ctrl vtable delete thunk 0x180003360 = 尾 `jmp rax` が未 lift) | 「LicenseManager 状態変化 → slot 起火 → poll1 → writer → [+0x1088] → [+0x548]」の通し E2E が bit-exact で未成立 (ct or・register は一致) | (a) 本 REPORT / (b) 親 CAB-13 に次タスク提案 (jmp 形 [icall] 拡張) |
| 0x1800f6540 (3,926 B, 29 メモリ間接 call) 未 lift | 書込側 (2) `[+0x1088]=!thunkA(status)` の実機相当実証が未達 (機械語読解のみ) | (b) 親 CAB-13 |
| listener [sub+0x630]/[sub+0x1170] 非 null の notification 未検証 | observer vector 非空の 0x18003d650/0x18003d7e0 ループが未実行 | (b) 親 CAB-13 |
| thunk/clone 12 本 + 0x18001ba90 等が .pdata 非連続で size を隣 begin から算出 | size 表が近似 | (c) 親 CAB-13 報告のみ ((DEFECTS.md) D13 同型) |
| `work/ctors47.json` が gitignore (未捆み込み) | clean HEAD 単体では `em_check.mjs` が再現できない | (c) 親 CAB-13 報告のみ (規則 37 の再現スクリプト適合) |
| subscribe 経路有効化に伴う functor offset の未初期化 qword コピー | native image パッチ + wasm IR 対称修正で 0 確定にしたが、FL コード本来の UB (パディング未初期化) | (a) 本 REPORT / (b) 親 CAB-13 |

## 7. 環境前提 (規則 43)
- `run_all.sh` が `[EMSDK]` 同梱 node 24.19.0 (`node/24.19.0_64bit/bin`) を PATH に設定。TMPDIR 未設定 (/tmp tmpfs) だが大物は `license/work/` (gitignore) のみ。
- `CORE=../work/winpkg/HeartCore.core_64` は**相対パス**。work/ 配下に別 snapshot を展開する場合のみ `work/winpkg -> ../winpkg` symlink が必要 (本ラウンドでは未使用)。
- ネイティブ oracle の image パッチ (functor offset 0 確定化) は `patch_em()` 内で毎 run 適用 (bytes 検証付き・不一致時 exit(9))。

## 8. 成果物
`lift/kh_lower.py` ([icall] pass・callret retaddr・clone offset 0 確定) / `lic_config.json` (module E 44 関数・-O1・subscribe shim 削除) / `lic_build.py` (icall.c リンク・kh_stack_ptr export) / `lift/gen_stubs_sigs.py` (fail-fast VA 出力・kh_stack accessor) / `harness/ctxfuzz.h` (ARENA_CLEAR・rec_stack フィールド) / `harness/scen_em.h` (emfire・register 修正・clone/pad image パッチ) / `harness/scenarios.c` / `harness/native_ref.c` / `harness/compare.mjs` / `em_check.mjs` ([4] 追加) / `run_all.sh` (emfire 情報提供) / `scripts/kh11_audit.py` (独立再計算)。
