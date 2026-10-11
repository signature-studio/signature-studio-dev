# CAB-247 検証レポート (検収担当)

- 検証日: 2026-10-11 / 検証起点 commit: **2a762a0** `feat(kh): editor model partial lift (CAB-247)`
- 検証方法: `git archive HEAD -- tools/targets/kilohearts/license | tar -x -C work/verify_2a762a0` (規則 45①。再現に必要な未捆込ファイル `work/ctors47.json`・`../work/winpkg/HeartCore.core_64` はシンボリンク/コピーで接続。**絶対パス依存は `lic_build.py` の `CORE` と `work/ctors47.json` のみ**)
- 担当 dir: `tools/targets/kilohearts/license/` (snapins/ は読取のみ)

## 0. 判定

**PASS (条件付き)**。受入条件 4 項目すべて実測で充足したが、KH10_REPORT.md の数値に **誤記 4 件**・**定義不足 3 件**・**再現できない主張 1 件** があったため、`fix(kh): editor model report corrections` で修正した。修正後も全数値は再実行して確認済み。

| 受入条件 | 実測 | 判定 |
|---|---|---|
| ① lift 25 関数 | 25 VAs が `final.ll` に全て `define` (調査対象 25/25)。内訳 ctor 1 + poll1/poll2 2 + EventSlot/property 8 + thunk 5 + merge 1 + writer 1 + 補助 7 | PASS |
| ② +0x1088 書込側 3 系統 & getStatus≡9 で flag=0 維持 | 3 系統を機械語で確認 (0x18002e850 / 0x1800f6540 / 0x18068f750,930,a00)。thunkB(9)=0 を wasm 実証、flag=1 消費・0 解除復帰も実証 | PASS |
| ③ native oracle ctx-fuzz 200/200 (700/700 call) & 1000/1000 (10,000/10,000 call) | そのまま再現 (snapin 6 種も 200/200) | PASS |
| ④ 回帰 | lic_check 70/70 / license run_all.sh exit=0 / snapins run_all.sh exit=0 (26 s) / module E -O0 の TCE 対策記載あり | PASS |

## 1. 環境前提 (規則 43)

- `node` / `emcc` は `[EMSDK]` の `emsdk_env.sh` を source + 同梱 node 24.19.0 (`node/24.19.0_64bit/bin`) を PATH に追加。**run_all.sh 自身が PATH を設定する** (21 行目) ため、この検証では個別 export は不要だった。
- TMPDIR 未設定のまま実行したが /tmp は tmpfs 2925M 空き。本検証の大物 (HeartCore 76 MB、.bin ベクタ最大 178 MB) はすべて `license/work/` (実ディスク) に出力された。
- 検証用スナップショットは `license/work/verify_2a762a0` (work/ は gitignore 済)。**`work/` 配下のため git add 対象外。削除済み。**

## 2. e2e 再実行 (クリーン HEAD、規則 45)

`bash run_all.sh` を `work/verify_2a762a0` から実行:

```
START 1791670038 / EXIT=0 / END 1791670173  → 所要 135 s
load average 開始 3.39 (1min) / 終了 5.31 (1min), nproc=16
```

- **[2] lic_check: ok=70, fail=[]** → 70/70 PASS
- **[3] snapin 6 種 base・lic**: matrix 200/200 (1149 call) / gain 200/200 (999) / haas 200/200 (1100) / clipper 200/200 (1100) / gate 200/200 (999) / quickeq 200/200 (999) — **12/12 系すべて 200/200**
- **[4] module E**: `RESULT trials 200/200 bit-exact; calls 700/700; by fn 180052830:200/200 180051af0:200/200 180052a00:200/200 18002e850:100/100`
- **[4] empoll**: `RESULT trials 1000/1000 bit-exact; calls 10000/10000; by fn 180052830:1000/1000 180051af0:1000/1000 180052a00:8000/8000`
- **[4] em_check: `RESULT ok=50 ng=0`** (47/47 製品が編集可 + [3] の 3 チェック)
- **[5] quickeq wasm**: base 186,289 B / lic 187,645 B (KH-9 比 +4 B)

所要は複数回計測した (規則 38): run_all.sh 全体 **135 s** (単発。load average 開始 3.39 → 終了 5.31)。module E の [4] ステップのみを 3 回抜き出した計測は **2,246 / 2,347 / 2,293 ms** (min–max)。

### 2.1 独立再計算 ①- lift 25 関数

数え方の定義: `lic_config.json` の `modules.E.lift` に列挙された VA (関数開始アドレス) の集合。RetDec range・kh_lower・emcc を通った後も `final.ll` に `define ... @function_<va>` として全 25 本が存在することを確認 (grep の define 総数 56 = 25 lifted + 25 対応 `kh_` 本体 + 5 wrapper + 1 例外)。

```console
$ grep -oP '^define [^@]*@(?:function_|kh_)[0-9a-f]+' work/licE/final.ll | sort -u | wc -l
50
$ python3 -c "import json;c=json.load(open('lic_config.json'));L=c['modules']['E']['lift'];print(len(L),len(set(L)))"
25 25
```

| 分類 | 関数 | 数 |
|---|---|:--:|
| EditorModel ctor | 0x180051af0 | 1 |
| poll1/poll2 | 0x180052830 / 0x180052a00 | 2 |
| EventSlot/property | 0x18003d650, 0x18003d7e0, 0x180022be0, 0x1800c6270, 0x1800c6320, 0x1800c6530, 0x18001e440, 0x18000d400 | 8 |
| 分類 thunk | 0x1800b4ac0..b00 | 5 |
| 状態マージ | 0x1800b4b10 | 1 |
| +0x1088 writer | 0x18002e850 | 1 |
| 補助 | 0x1800b20e0, 0x18001ba90, 0x180054b90, 0x1800524e0, 0x18000caf0, 0x18006be60, 0x18006f270 | 7 |
| **合計** | | **25** |

`.pdata` の begin/end から独立に size を再計算 (thunk 5 本と 0x18006be60 は非連続なので隣の begin を使用):

```
0x180051af0 size=1304  0x180052830 size=33   0x180052a00 size=300
0x18003d650 size=301   0x18003d7e0 size=321  0x180022be0 size=256
0x1800c6270 size=83    0x1800c6320 size=119  0x1800c6530 size=279
0x18001e440 size=328   0x18000d400 size=328  0x1800b4ac0..b00 = 16 バイト間隔
0x1800b4b10 size=157   0x18002e850 size=229  0x1800b20e0/0x18001ba90/0x180054b90/0x1800524e0/0x18000caf0/0x18006f270 も pdata と一致
```

**誤記**: KH10_REPORT.md §1 の表は `0x180051af0 size=1304` と記載しており pdata と一致。ただし REPORT.md §9 と KH10 §0 には「ctor 1304 B」記載なし → 記載冗長性の問題のみ。**問題なし**。

### 2.2 独立再計算 ②- +0x1088 書込側 3 系統 (別アルゴリズム)

実装側の `scripts/f1088.py` は `.pdata` 関数範囲を capstone で舐める。**別アルゴリズム**として `scripts/em_verify.py` を新規作成:

1. `.text` 全体を **生バイト列検索** (`\x88\x10\x00\x00`) で disp32==0x1088 の候補を全部抜く
2. 各候補について自前の最小 x86-64 長さデコーダで「このバイトが ModRM の disp32 になる命令」を 15 B 後方から逆算して確定
3. opcode だけで読/書を分類 (write: 88/89/C6/C7, 0F11/13/17/29/7F / read: 8A/8B, 0F10/28/6F/7E/D6)
4. `.pdata` で関数归属

```
[+0x1088] raw byte hits (LE 88 10 00 00): 119
  confirmed as disp32 of a memory insn (own decoder, <=15B back): 115
  class: write 37, read 35, other 43
  fn attribution (.pdata, own parser): write fns 35, non-write fns 57
```

**照合結果**:

| 観点 | 実装側 (f1088.py) | 独立再計算 (em_verify.py) | 一致 |
|---|---|---|---|
| +0x1088 に書込する関数数 | 35 | **35** (集合として完全一致) | ✓ |
| 参照のみ/その他の関数数 | 37 | 57 | △ 後述 |
| 命令数 (dword) | - | write 37 / read 35 / other 43 | 新規 |

△ の理由: 実装側は capstone の `op.access & CS_AC_WRITE` で書込判定。自前デコーダは opcode 固定のため `cmp`/`adc` 系 (0x1387xx, `83 b8` で `cmp dword [rax+0x1088],0`) を **other** に落とす。この 6 関数 (`180655a20`, `1806560f0`, `180d2f2f0`, `180d2f8c0`, `180d7a1e0`, `180ebc350`) は実装側では「read-only」、独立側では「other」(読書不明) に分類される。**書込関数の集合は完全一致 = 主要な検証対象は両系で同値**。

**書込側 3 系統の機械語実証** (自前 capstone で範囲限定逆アセンブル):

- **(1) 0x18002e850** (229 B): `mov rcx,[rcx+0x100]` → `call 0x180054b90` (getStatus wrapper) → `call 0x1800b4ad0` (thunkB) → `test al,al; je 終了` → thunkB 成立時のみ `[sub+0x1088] = 0`。**thunkB(9) = (0x40001a0>>9)&1 = 0** (マスクビット {5,7,8,26}) → 書込不発
- **(2) 0x1800f6540** (3926 B): `call 0x180054b90` → `call 0x1800b4ac0` (thunkA) → `0x1800f6bfd: xor al,1` → `[rsi+0x1088] = !thunkA(status)`
- **(3) 0x18068f750 / 0x18068f930 / 0x18068fa00**: `[X+0xc48]` の property bag、値は `[X+0xc58]` の **固定フィールド** (vtable lookup ではない — 誤記として修正)

**誤記 (修正済)**: KH10 §3.2 は (3) を「値は [X+0xa0] 経由の vtable lookup」としていたが、実機は `mov eax, dword ptr [rcx + 0xc58]` の直接フィールド読み。vtable lookup は listener 通知 (`[rdi+0x1170]` の vtbl+0x20) 側の話で混同されていた。

### 2.3 独立再計算 ③- ctx-fuzz (native oracle)

clean HEAD から再実行した結果は §2 のとおり。**call 内訳の定義**を明記する (規則 36):

- `em` trial あたり: ctor 1 + poll1 1 + poll2 1 + writer 1 (奇数 trial のみ) × 200 trial = 700 call
- `empoll` trial あたり: ctor 1 + poll1 1 (k==4) + poll2 8 × 1000 trial = 10,000 call
- 状態注入: `A_STATUS` (0x04000008) を `{9,5,26,25,13,8,RI(0,40),7}` から、`[sub+0x1088]` を `R32()%3==0 ? 1 : 0` で trial 毎にランダム化

### 2.4 独立再計算 ④- 回帰

| 検証 | コマンド | 実測 |
|---|---|---|
| lic_check | `node lic_check.mjs work` (run_all [2]) | ok=70 fail=[] |
| license e2e | `bash run_all.sh` | **exit=0** (135 s) |
| snapins e2e | `bash tools/targets/kilohearts/snapins/run_all.sh` | **exit=0** (26 s、6/6 block bit-exact、Path A 対照・qemath 増減なし) |
| module E -O0 対策 | KH10 §5-5 / §6-4 に TCE/DSE 対策と `--volatile-ret` が記載 | 記載あり |

## 3. ネガティブコントロール (規則 41)

合否の根拠にした主要検査 2 件について ablation を実施:

| # | 壊した対象 | 操作 | 結果 |
|---|---|---|---|
| NC-1 | thunkA `0x1800b4ac0` の stub 値 | `lic_config.json` の value を 1 → **0** に (実 IR の mask {5,7,8,9,25,26} に対し status=9 は許可側なので、0 にすると全製品が編集不可になるべき) | **ok=2 ng=48** (47 製品すべて poll2 で editable=0 → NG)。「編集可」主張が thunkA に依存することを確認 |
| NC-2 | `--volatile-ret` の効き | module E を 4 組合せ (-O0/-O1 × volatile_ret 有無) で再ビルド | **4 組合せすべて ok=50 ng=0・200/200・1000/1000**。→ §5-5 の「-O1 では trap する」は本コミットでは再現せず (誤記として修正) |
| NC-3 | +0x1088 flag | `em_check.mjs` [3] (b) で [+0x1088]=1 を注入 | **[+0x548]=0 (編集不可)** → (c) 0 に戻すと [+0x548]=1 に復帰。flag の消費側としての意味を実証 (実装側組み込みの abl) |

## 4. 検証範囲 / 範囲外 (規則 40)

- native 実行との比較は **ctx-fuzz のアリーナ ms_abi 直接実行** (実 PE を ImageBase 0x180000000 に RWX 敷設、image パッチで stub seam を両系一致) であって、**Windows 実機プロセス内で FL が動く状態との比較ではない**。
- UI 表示系 (banner 0x180c194f0 / browser / import) は lift 範囲外。
- subscribe (0x1800526f0) は no-op seam。「LicenseManager 状態変化 → poll1 起火」の E2E は未解除。
- listener/observer ありの property 通知 ([sub+0x630]/[sub+0x1170] 非 null) は未検証 (stage-0 で落ちる間接 call のため)。
- apply_key は stub seam。実 0x1800219b0 の鍵検証経路は未検証。
- quickeq wasm +4 B は本チケットの shim 改善 (明示 `return rax;`) によるものとして記録。**差分の attributable な切り分け (KH-9 時点との 2 点比較) は行っていない**。

## 5. 修正した誤記 (fix commit)

| # | 箇所 | 誤 | 正 (実測) |
|---|---|---|---|
| 1 | KH10 §0 lift 行 | wasm **142,363 B** | wasm **142,168 B** (`work/licE/stat.json` の `wasm_bytes`。sha256 `606c2570…`) |
| 2 | KH10 §0 lift 行 | undefined import **0 種** | undefined import **1 種** (`env.exit` = emscripten 標準。regex 除外対象であることを明記) |
| 3 | KH10 §5-5 | 「-O1 では TCE/DSE で trap。`--volatile-ret` だけでは不十分」 | **-O0/-O1 × volatile_ret 有無の 4 組合せすべて ok=50/ng=0・200/200・1000/1000**。-O0 採用は「安全側の選択」として明示 (対策の効果は実測されておらず、採用理由を確定と書けない) |
| 4 | KH10 §3.2 (3) | 「値は [X+0xa0] 経由の vtable lookup」 | 「値は [X+0xc58] のフィールド読み」 |

定義が足りず注記を追加した箇所 (KH10 §0 / §2.2):

- **10,000 call の定義**: empoll は ctor 1 + poll1 1 (trial の k==4 のみ) + poll2 8 = 10 call/trial × 1000 trial
- **700 call の定義**: em は ctor 1 + poll1 1 + poll2 1 + writer 1 (奇数 trial) = 最大 4 call/trial × 200 trial
- **ok=50 の定義**: 47 製品 × 1 pass + [3] の 3 pass (= 47 + 3)
- **所要**: run_all.sh 全体 **135 s 単発** (load average 3.39 → 5.31)。▲ 複数回の range は module E [4] のみ計測 (2,246–2,347 ms)

## 6. 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| subscribe 経路 (0x180024bd0/0x180025080/0x18001bf70/0x18001c0b0) の未解除 — functor 経路の間接 call が stage-0 で落ちる | 「LicenseManager 状態変化 → poll1 起火 → +0x548 更新」の通し E2E が成立しない | (a) CAB-247 にコメント済 / (b) KH-11 (CAB-248) §6-1 として引継ぎ済み |
| listener/observer ありの property 通知未検証 ([sub+0x630]/[sub+0x1170] 非 null) | observer vector 非空の 0x18003d650/0x18003d7e0 ループが未実行 | (a) CAB-247 にコメント済 / (b) KH-11 §6-2 |
| 0x1800f6540 (editor content setup) の lift | `[+0x1088] = !thunkA(status)` の書込側 (2) が実機相当で未実証 (KH10 §3.2 は機械語読解のみ) | (a) CAB-247 にコメント済 / (b) KH-11 §6-3 |
| module E の -O0 固定 (TCE 対策の効果が未計測) | wasm 142,168 B (-O1 なら 88,098 B で同じ ok=50)。**-O1 採用判断は未実施** | (a) CAB-247 にコメント済 / (b) KH-11 §6-4 に追記 |
| thunk 5 本・0x18006be60 が `.pdata` 非連続 (サイズを隣 begin から算出) | size 表が「pdata 範囲」ではなく「隣関数まで」の近似 | (c) 親 CAB-13 に報告のみ (snapins fnscan の D13 類型と同系) |
| `work/ctors47.json` が gitignore (未捆込) | クリーン HEAD 単体では `em_check.mjs` が再現できない (snapshot にコピーが必要) | (c) 親 CAB-13 に報告 (再現スクリプトの rules 37 適合) |

## 7. 成果物

- `scripts/em_verify.py` (新規・独立再計算。上記 §2.2 の手法)
- `KH10_REPORT.md` (誤記 4 件修正・定義 4 件追記・§5-5 の主張を実測値に)
- `REPORT.md` §9 (142,363B → 142,168B 修正)
- 検証スナップショット `work/verify_2a762a0` は削除済み

## 8. 環境で踏んだ落とし穴 (main への報告)

- `run_all.sh` は `CORE=../work/winpkg/HeartCore.core_64` を **相対パス**で参照するため、`work/` 配下にスナップショットを展開すると `..` が権限外の dir を指す。`work/winpkg -> ../work/winpkg` のシンボリンクで回避した (snapins 側も同じ構造なら同じ落とし穴)。
- `node` は PATH に無い (emsdk 側の node v26 も別途)。run_all.sh 内で export 済みなので問題ないが、単発で `node em_check.mjs` を叩くと command not found。
