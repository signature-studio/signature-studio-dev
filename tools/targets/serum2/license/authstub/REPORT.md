# SR-2b — Serum2 authorization stub 設計・実装 (CAB-237)

- 日付: 2026-10-10 / 親: CAB-13 (アプリケーション完成 マイルストーン) / 前段: CAB-71 (5012887, REPORT §7 の N1–N8 が入力)
- 方針根拠: `docs/LEGAL.md` §6.0-4 (bc07970: 全ライセンス機構無力化・アクティベーション無条件通過・ライセンス状態データの配置/合成はユーザ承認済み)
- 範囲: 本 dir (`tools/targets/serum2/license/authstub/`) のみ新設。CAB-71 既存ファイルは無変更 (license/REPORT.md への §10 追記のみ)。
- 再現: `bash tools/targets/serum2/license/authstub/e2e.sh` (1 コマンド, lift キャッシュ利用時 約 25 秒)

## 0. 結論 (先出し)

1. **中性化は 6 IR ルール / 機械語パッチ 6 箇所で完結する (バイト差分 15B)** (CAB-71 予想より小さい)。全 .text 走査 (33,791 関数) の結果、demo bit (obj+0x22792) の writer は `SerumController::setState` (0x1800c2b50) の 2 store のみ、host 通知即値 0x800010 も同関数 2 箇所のみ、demo マーカ判定も同関数 + `SerumController::getState` (0x1800c6090) の 1 分岐のみ。**demo 状態は host session state 経由でしか発生しない** (prefs/registry 由来の demo 判定は存在しない)。
2. IR pass (`authstub_irpass.py`) を RetDec raw .ll に適用し、**適用後の到達性を機械検証まで実施**: demo bit store 2/2 が定数 0、0x800010 通知ブロックが到達不能、getState の demo マーカ書込ブロックが到達不能、DSP setState の demo ダイアログブロックが到達不能 (version 復元経路は到達可能)。N4: `SerumDSP::process` (0x180056670) と funclet (0x18004ffc0) は **1 行も非変更** (assert 込み)。
3. **wasm 実行ハーネス 23/23 PASS**: lift 実 IR (patched / 未 patch の両方) を emcc → wasm → node で実行し、demo bit 常時 0・0x800010 通知抑止・demoVersion 無視で復元続行 (N1)・version 範囲判定の維持を実測。callee は IR の declare 契約どおりの mock (分岐駆動)。
4. ライセンス状態データ合成 (`synth_state.py`): 5 保存先に対する licensed 形を **決定論的** (2 回実行でバイト一致, MANIFEST.sha256 付き) に生成。鍵となる事実: **マーカキーの不在が licensed 形** (demo 判定は「有る/無い」で読む)。
5. 受口: ネットワーク群 (N5) は呼ばない設計 (wasm shim で WININET/WS2_32 を no-op/fail-fast, vreg seed 断片を同梱)。**Locate License (N6) は「常に成功または非表示」ではなく「表示のまま・選択結果は license 状態に影響しない」を採用** (根拠 §4)。GUI overlay (N7) は uidesc 側実体化が 0 参照でコード側のため保留 (§4)。
6. lift fidelity gap を 5 件同定 (L1–L6, §6) — Serum2 本 lift (SR-3) への引継事項。うち L1 (0x1800c2b50 の直接 vtable 通知 call が raw IR から脱落) は本 stub とは逆方向 (偶然有利) だが修正必須。

## 1. 差し替え点一覧 (CAB-71 §7 N1–N8 × 実施/保留)

| # | 呼出点 (実測座標) | 処置 | 実装 | 検証 |
|---|---|---|---|---|
| N1 | 0x18004fad0 (DSP setState) 内 `demoVersion` キー検出分岐 **0x18004fbdd** (`je 0x18004fe1c`) | 検出時も無視して復元続行 (防御案を採用) | IR: br_force !37 / 機械語: `0f 84…`→`e9…90` (6B) | wasm: dialog 非実行 + 復元実行 (3 ケース) |
| N2a | 0x1800c2b50 内 demo bit store **0x1800c2cfe** (`mov [rsi+0x22792],al`) と **0x1800c2d42** (`mov …,1`) | 常時 0 を store | IR: store_const !2624/!2630 / 機械語: N2a-1 は `34 01` (xor al,1)→`b0 00` (mov al,0) 2B に変更 (#623。旧 `34 00` は lookup 値を残すため定数 0 にならなかった), N2a-2 は `01`→`00` | wasm: bit≡0 (marker 0/1 両方) |
| N2b | 0x1800c2b50 内 0x800010 通知分岐 **0x1800c2d04** (jne→d5f) と **0x1800c2d59** (je→f08) | licensed 側に固定 (通知ブロック到達不能化) | IR: br_force !2625/!2633 / 機械語: `75 59`→`90 90`, `0f 84…`→`e9…90` | wasm: deferred flags 0x0 (pre は 0x800010 発火を実測) |
| N3 | 0x1800c6090 (getState) の demo マーカ書込分岐 **0x1800c687b** (`jne +0x3d`) | 書込 skip 常時化 | IR: br_force !3004 / 機械語: `75`→`eb` (1B) | IR: マーカ書込 block 到達不能 |
| N4 | 0x180056670 (`SerumDSP::process`) | **無変更** (CAB-71 実測どおり音声経路に demo 参照無し) | pass は対象外 | IR diff 0 行 + 前方呼出閉包 842 関数が patch 対象と非交差 |
| N5 | ネットワーク群 (§4 全面: WININET/WS2_32/ShellExecuteEx) | **呼ばない** (wasm shim 側 no-op/fail-fast 受口) | 設計 + vreg seed 断片 (`work/…/vreg_seed_serum2.json` は §3 出力) | 実機結合は shim 結合タスクで実施 (§8) |
| N6 | 0x18089ea80 (Locate License) | **非表示にしない** (表示のまま)。選択→parse/verify は未解明だが demo bit への writer は無い (全 .text 実測) ので状態は不変 | 判断のみ (§4) | — |
| N7 | GUI overlay (SpliceRTO/SpliceExpired/SpliceMaxLimit/overlay_demo_version) | **保留** (設計確定)。uidesc 内の Splice 3 テンプレートは定義のみで実体化参照 0 → エディタコード側で実体化 (CAB-71 未解決 #4)。demo bit ≡ 0 により表示条件が偽になる可能性が高いが GUI lift まで実測不能 | 設計記載 (§4) | uidesc 実測 (参照数 0) |
| N8 | prefs singleton (0x1800211a0) | 実ファイル読書のまま (vreg/仮想FS 整合)。ライセンス関連キーは XOR 復元未解決につき空オブジェクト合成 | `synth_state.py` | 決定論検証 (2 run hash 一致) |

- funclet 0x18004ffc0 (CAB-71 が「判定 3点」に数えた EH catch) は demo ロジックを持たないため **patch 不要** (N4 check で identical を確認)。
- +0x22b70 bit4 (`or …,0x10`) は +0x22790==1 が条件だが、+0x22790 への 1 書込は全 .text に存在しない (ctor の 0 初期化のみ, walk 実測) → 不活性のまま無変更。

## 2. 実装 — IR pass と機械語参照パッチ

| ファイル | 内容 |
|---|---|
| `authstub_irpass.py` | 本体。`!insn.addr` (機械語 VA) を鍵に RetDec raw .ll を書換。6 ルール (上表)。`--check` で CFG 到達性検証まで実施 |
| `mpatch.py` | 機械語参照パッチ。原 bytes 照合 6/6 OK → 適用済み PE 出力 (`work/Serum2_win64.authstub.vst3`)。capstone で逆アセンブル再確認済み |
| `e2e.sh` | lift → pass → base 修復 → liftfix → wasm ハーネス → 検証の 1 コマンド直列化 |
| `mkrun_merge.py` / `data_globals_gen.py` / `mkrun_ll.py` | 実行モジュール合成 (関数抽出 + PE 実バイトからの定数領域生成) |

- base 修復は `tools/liftlib` を**ライブラリとして import** (shared infra 無改変; b1_fixed 18 / s1_stores 20 / A9 残存 4)。
- 適用ログ (before→after) は `work/irpatch_report.json`。例: `store i8 %91, i8* %94` → `store i8 0, i8* %94`。

## 3. ライセンス状態データ合成 (`synth_state.py`)

| 出力 | 内容 | 根拠 |
|---|---|---|
| `host/processor_state.json` | `{"component":"processor","productVersion":"2.1.5","version":2.1}` | reader 契約: 0x18004fad0 は tag 値 "processor" (len9), `version` ∈ [0, 11.00001] (@0x180a21b60), `demoVersion` キー**無し**が licensed 形 |
| `host/controller_state.json` | 同形 ("controller", len10) | 0x1800c2b50 実測。`kAudioUnitParameterFlag_IsHighResolution` (0xfc8950, 値 false=DOM 型 4) を**書かない**ことが licensed 形 |
| `prefs/Serum2Prefs.json`, `prefs/SerumPrefs.json` | `{}` | demo 判定は prefs を読まない (walk 実測)。ライセンスキーは XOR 復元未解決 (CAB-71 §8-2) |
| `vreg_seed_serum2.json` | `HKCU\Software\XferRecords\Serum2InstallerPrefs` 空キー作成 (CAB-94 seed 形式) | キー名は 0x180267210 の literal (CAB-71 §6) |
| (`Serumpresetdb.dat` は合成しない) | SQLite 初回生成に任せる | CAB-71: ライセンス依存記述は確認せず |

- `productVersion: "2.1.5"` を含めるのは、**未 patch バイナリでも** `"2.1.5" >= "2.0.20"` の比較で demo store が起きないようにするため (strcmp 結果 jns → store 無し)。
- 決定論: キー順固定・固定値・タイムスタンプ無し。2 回実行の diff 0 + SHA256 manifest。

## 4. 受口設計 (vreg / 仮想FS — N5/N6/N7/N8)

- **N5 (通信系)**: オンライン認可 (ブラウザ認可 + ローカル callback サーバ) と更新確認は stub 適用後も**呼ばれない経路**として維持する (アクティベーション済み状態なので認可 UI への分岐に入らない設計)。wasm shim 側では `InternetOpenA/InternetOpenUrlA/HttpQueryInfoW/InternetReadFile/ShellExecuteExA/socket 系` を tools/shim 流儀の no-op/fail-fast に置く (実装は shimx 結合タスク)。vreg seed 断片 (§3) を CAB-94 の `Vreg.create({seed})` に追加適用するだけで registry 受口は完成 (pinned group=license)。
- **N6 (Locate License)**: 「常に成功」は実装コストが parse/verify 呼出鎖の未解明 (CAB-71 §8-3) に依存し、「非表示」は menu 生成 (0x1807235f0 系) のコード側分岐が未特定。よって **表示は残し、選択されても license 状態 (demo bit) が変化しないことを保証**する (全 .text に +0x22792 writer は setState のみ — 変更しても demo 化しない)。UI 体験への影響は「Already activated 表示相当」で実害無しと判断。
- **N7 (GUI overlay)**: uidesc 実測 — Splice 3 テンプレート (`SpliceRTO`/`SpliceExpired`/`SpliceMaxLimit`, 全て `sub-controller: SpliceController`) は**uidesc 内の実体化参照 0** (定義のみ)。エディタコードが状態を見て実体化するため、demo bit ≡ 0 で表示条件が偽になるのが期待動作だが判定分岐は未特定 (CAB-71 §3)。GUI lift 時に (a) 実体化分岐の確認, (b) 駄目なら uidesc テンプレートの空ビュー置換 (決定論変換) で仕上げる。`overlay_demo_version*` は bitmap 登録のみで実害なし。
- **N8 (prefs)**: vreg/仮想FS 側は `%APPDATA%` 配置 (`Serum2Prefs.json` / `Xfer\Serum\SerumPrefs.json`) を通常ファイルとして読み書きさせる (合成物は §3 の空オブジェクト)。以後の保存はプラグイン自身が行う (determinism は初回配置のみ保証)。

## 5. 検証結果 (全て実測)

| # | 要件 | 方法 | 結果 |
|---|---|---|---|
| ① | demo bit (obj+0x22792) 常時 0 | (a) IR: pass 後 store 2/2 が `store i8 0` (機械検証)。(b) wasm: lift 実 IR を emcc → wasm で実行し marker=0/1 の両方で obj+0x22792 を読み出し | **2/2 store 定数 0, 実行 bit=0/0** (pre/unpatched は bit=1 + 通知 0x800010 発火を実測し差分を対比) |
| ② | save/recall がデモ抑止なしで動作 | recall: wasm 実行で FUN_1800c3080 (状態ロード) 実行 + kResultTrue(0) を marker 0/1 両方で確認。save: getState のマーカ書込 block が到達不能 (IR 検証) + bit≡0 ゆえ保存状態にマーカが載らない | **recall 実測 OK / save IR 検証 OK** |
| ③ | process の音声出力に影響しない | (a) pass 適用 diff で process/funclet 1 行変更なし (assert)。(b) process の前方呼出閉包 (direct call graph, 842 関数) と patch 対象 4 関数の交差 = 0 | **静的実証 OK**。動的 bit 一致は Serum2 DSP lift (SR-3) 以降 (§8) |
| ④ | 既存 Serum2 関連 e2e 非破壊 | 変更は authstub/ 新設のみ (git status 実測)。CAB-71 スクリプト (zone.py) を本タスク中 3 回実行し正常動作。CAB-19 資産は読取のみ | **OK** |

- ハーネス詳細: 23 ケース中 23 OK (`work/harness_report.json`)。pre (未 patch, rename 同梱) との対比で「demo bit 1→0」「0x800010 発火→抑制」を同一入力で実測。
- DSP setState は version 範囲外 (12.0) で復元を正しく skip することも確認 (LF4 復元分岐の動作実証)。

## 6. lift fidelity gap (Serum2 本 lift への引継 — 新規所見)

| ID | 事実 (実測) | 影響 | 本タスクでの扱い |
|---|---|---|---|
| L1 | 0x1800c2b50 の 0x1800c2ef4–f05 (host への**直接** vtable 通知 `call [rax+0x30]`, edx=0x800010) が raw RetDec IR から**脱落** (当該 VA の insn.addr メタが 0 個, 間接 call も 0) | 通知経路の半分が IR に無い (本 stub には有利だが忠実性欠落) | 機械語参照パッチ (mpatch.py) で補完。本 lift 時は再現要確認 |
| L2 | 0x1800c2b50 の tag 文字列 len が callee が書く caller stack なのに undef alloca 読みになり base で 0 fold → tag check が常時偽 | setState が IR 上常に kResultFalse | LF1: len を global 束縛 |
| L3 | 0x18004fad0 の ucomisd 後の分岐が**直前の整数 compare の stale flag** 再読出しになっている | version 範囲判定が誤分岐 | LF3: fcmp uge に置換 |
| L4 | 0x18004fad0 の 2 つ目の ucomisd (v ≤ 11.00001) の分岐が脱落 | 範囲外 version も復元経路に進む | LF4: fcmp ugt + br を挿入 (動作実証済み) |
| L5/L6 | doc/root ポインタが callee 書込み (doc+8) と IR の別 alloca 読みで齟齬 | JSON DOM を伴う実行が不可 | LF5/LF6: root を global 束縛 |
| — | (参考) FP 戻り値 (FUN_180024390 → xmm0) も entry 時の undef alloca 読みに落とされる | version 値が常に 0 | LF2: global 束縛 (呼出後に読む) |

- 教訓: `--select-decode-only` lift では「callee が caller stack / xmm を書く」契約が落ちる。liftlib P1/F7/F2 が整数系を直すのに対し FP/文字列 struct 系は未整備 → SR-3 で pass 化を推奨。

## 7. ABI slot confidence (SR-1 / CAB-68 最小 host で確定する部分)

| 項目 | 現状 | 確定根拠 | SR-1 で確定させること |
|---|---|---|---|
| 0x1800c2b50 / 0x1800c6090 が setState/getState であること | **high** (decompile + 文字列実測: component/controller タグ, demoVersion, preset メタ) | 本タスクで reader/writer 契約まで実測 | — (確定済みとして扱える) |
| vtable 0xa2bf58 の (interface, slot) 番号 | **med** のまま (CAB-71どおり)。ctor 0x180a9f40 が param_1[6] (+0x30) に 0xa2bf58 を設定する事実を追加確認 | zone.py: vtable の data_ref は ctor のみ / RTTI COL 未解決 | 最小 host で GetPluginFactory → class factory → setComponentHandler まで実測し slot 番号を固定 |
| host 通知 `call [obj+0x10 の vtable + 0x30]`, arg 0x800010 | **med**。IComponentHandler::restartComponent (slot 5 = +0x28) とは +8 ずれ → obj+0x10 が host handler 以外の可能性。0x800010 = 0x10 (kIoChanged) + 0x800000 (独自 bit) と推定 | 機械語実測 (0x1800c2ef4–f05) | host 側で 0x800010 受信を観測し slot/意味を確定 |
| deferred 通知 (obj+0x90 先 +8 dword への OR) | **high** (機械語実測)。キュー型フラグの様相 | 本タスク walk | host 実装時に消費側を確認 |

## 8. 制限

1. 動的検証は「判定 3点の関数本体」に限定 (JSON パーサ/DOM/IBStream は mock)。実 JSON 文字列を通した往復 (合成 state → 実パーサ → setState) は JSON パーサ closure の lift が前提 (SR-3)。
2. process の音声 bit 一致は静的証明のみ (実動的 bit 比較は DSP lift 後)。
3. GUI (N7) と Locate License 選択後の parse/verify (N6) はコード側分岐が未特定のまま (CAB-71 未解決 #3/#4 を維持)。
4. mac 版は未実施 (Win を正とする方針どおり)。
5. `work/` 以下 (lift 中間物・適用済み PE・合成物) は gitignore。再生は e2e.sh / synth_state.py / mpatch.py で可能。

## 9. 次タスク提案 (起票はメイン判断)

- **[SR-3] Serum2 DSP/JSON closure lift** (親 CAB-13): 本 REPORT §6 の L1–L6 を入力に lift pass 追補 (FP 戻り値・caller-stack 書込み・文字列 struct)。lift が届けば ③ の動的 bit 一致と ①の実 JSON 往復検証が完結する。
- **[SR-4] 最小 host 結合** (SR-1/CAB-68 の継続): §7 の slot 確定 + 0x800010 受信観測 + 合成 state (§3) を setState に流す E2E。
- **[SHIM-x] Serum2 通信系 no-op 受口**: N5 の WININET/WS2_32/ShellExecuteEx no-op を shimx に追加 (既存 FAIL_FAST 流儀)。
- **[SR-2c] GUI overlay 実体化分岐の特定**: N7 の残部 (エディタ側 state → template 実体化)。

## 10. 再現

```sh
bash tools/targets/serum2/license/authstub/e2e.sh                         # 検証一式 (23/23 PASS を標準出力)
python3 tools/targets/serum2/license/authstub/synth_state.py <outdir>     # ライセンス状態合成 (決定論)
python3 tools/targets/serum2/license/authstub/mpatch.py \
  tools/targets/serum2/work/Serum2_win64.vst3 <out.vst3>                  # 機械語参照パッチ (原 bytes 照合 6/6)
python3 tools/targets/serum2/license/authstub/authstub_irpass.py \
  work/lift/authstub.drc.ll work/patched.ll --check                       # IR pass 単体
```

## 11. LF2〜LF7 束縛の fp_bind 共通プリミティブ化 (PR #778, Refs #250)

- 対象: `tools/liftlib/liftlib/passes/fp_bind.py` (新規。`fn_span` / `replace_lines` / `bind_slot_loads` / `insert_after`、件数 expect で一致を検査) と `authstub_irpass.py` の `apply_liftfix` (fp_bind 経由に変更。束縛内容は不変)。
- 測定 commit: 45f63732 (main 3418333a 取り込み後)。素材: `plugins-serum2.tar.zst` の `Install_Xfer_Serum2_2.1.5.exe` を 7z で展開 → `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` を `tools/targets/serum2/work/Serum2_win64.vst3` に配置。19,236,864 B, sha256 `501e7bb3…5283` (展開前に一致確認)。toolchain-retdec・toolchain-emsdk 使用。Python は pefile 2024.8.26 / capstone / numpy を venv に入れて実行。
- 前提: 旧 PR 本文の転記値 (e2e 30.3 s / 4.0 s 等) は再測定の対象外。下表の「変更前」は未再測定のため空欄。
- 再測定 (`bash e2e.sh`、`rm -rf work` 後の cold 1 回目と、直後の warm 2 回目):

| 項目 | cold (lift 新規生成) | warm (lift キャッシュ利用) |
|---|---|---|
| `e2e.sh` 所要 (`time` real) | 34.9 s | 5.3 s |
| load (`/proc/loadavg` 1 分平均) | 0.44 → 0.69 | 0.71 → 0.71 |
| wasm ハーネス | 23/23 PASS | 23/23 PASS |
| `patched_base_lf.ll` sha256 | `c62d9316…8793` | `c62d9316…8793` |
| `raw_base_lf.ll` sha256 | `79ab30ca…0d20` | `79ab30ca…0d20` |

- 両回とも N4 OK (process / funclet 非変更)、LF1〜LF7 全適用。`patched_base_lf.ll` / `raw_base_lf.ll` の sha256 は旧 PR 本文の値と一致した。
- 注: 最初の試行は venv 未導入で `data_globals_gen.py` が `pefile` 不足により step [6] で停止した (環境要因。コード変更なし)。venv 導入後に上記の cold / warm を取り直した。
- 残: 「変更前 (main 側 authstub 版) の再測定」は未実施。baseline 比較は行わない。

- N4 (process / funclet 無変更) assert OK。変更関数は 18004fad0 / 1800c2b50 / 1800c6090 の 3 件。
- 本束縛の共通化で達成したのは「既存 e2e の再現」と「束縛プリミティブの共通化」まで。L1 の復元 pass と LF 規則の一般化 (RetDec 出力からの規則導出) は未達。追跡 issue は未起票のため PM に起票を依頼する。

## 12. L1 の再現条件 (実測・追跡 #823)

- 測定 commit: origin/main 36edc993 (ws-250b)。素材: plugins-serum2 → `Install_Xfer_Serum2_2.1.5.exe` の `$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3` (19,236,864 B, sha256 `501e7bb3…5283`)。
- baseline `bash e2e.sh` (lift キャッシュ利用): 5.7 s, load 0.92 → 0.35, **23/23 PASS**。cold 再生成は未実施。
- 機械語 (0x1800c2d59–d76): `[rsi+0x90]` が非 0 なら `or dword [rax+8], 0x800010` (deferred 経路)、0 なら `je 0x1800c2ef4` で直接経路 `mov rcx,[rsi+0x10]; mov rax,[rcx]; mov edx,0x800010; call [rax+0x30]` へ分岐する。
- raw IR では `dec_label_pc_1800c2d5f` の `br i1 (icmp eq %109, 0)` の 0 側が機械語の `je 0x1800c2ef4` ではなく `dec_label_pc_1800c2f08` に付け替えられており、`0x1800c2ef4` 相当のブロックは関数内のどの分岐からも到達しない (`insn.addr` 0 件)。
- 結論: 脱落は「`0x1800c2ef4` へ向かう辺が lift 時に `0x1800c2f08` へ付け替わる」形で起きている。raw IR の `0x800010` 即値は `or i32 …, 8388624` (L9878, `0x1800c2d6f` 側の deferred 経路) の 1 箇所のみ。
- 残: 失われた辺を復元する pass の実装と検証は未着手 (#823)。N2b (`0x1800c2d59` → f08 の強制) は deferred 経路除去であり、直接経路の復元とは別問題。
