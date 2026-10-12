# KH-9 — Kilohearts ライセンス stub 実装 (lift パイプライン収録・CAB-236 / 親 CAB-59)

- 解析日: 2026-10-10 / 担当 dir: `tools/targets/kilohearts/license/` (本報告は `KH9_REPORT.md`。CAB-59 の `REPORT.md` は追記節 §8 のみ)
- 1 コマンド再現: `bash tools/targets/kilohearts/license/run_all.sh` (work キャッシュ有り ≈ 3 分 / 初回 + RetDec ≈ 5 分)
- 方針 (ユーザ確定 bc07970): **全ライセンス機構を無力化・アクティベーション無条件通過・KH は常に「登録済み/ライセンス済み」として振る舞う**

## 0. 結論 (先出し)

| 項目 | 結果 |
|---|---|
| stub 方式 | **lift IR 後処理 pass** (`lic_stub.py`): kh_lower+ir_normalize 後の .ll に対し `@function_<VA>` (ms_abi 入口) と `@kh_<VA>` (lift 本体) の **両面を定数返し・短絡に置換** (外部 export 経路と lift 内部呼出経路の両方を同じ定数に揃える) |
| stub 対象 | **14 関数** (getStatus / getStatusAndDaysLeft / hasTag / getPending / 分類 thunk 5 種 / isMasterKey / 鍵ホワイトリスト検証 / 鍵適用 / 鍵状態初期化 / KHSUnlock export) + 状態マージ 0x1800b4b10 は**実 IR のまま保持** (純関数、優先度テーブル検証に使用) — §2 |
| ライセンス済み定数 | **getStatus ≡ 9** (UI バナー解除・機能ゲート許可・poll 編集可の実測値。§3 enum 表) |
| 検証 ①DSP 無関係 | snapin 6 種の lift IR にライセンス関数参照 **0 件** (base census)。stub 適用版 (stub 14 関数を同一 wasm に合成) でも **ctx-fuzz 200/200 bit-exact × 6/6** (計 6,346 call / 1,200 trial) — 前後で DSP 出力 bit 一致 (両系とも同一 native 参照と bit 一致) |
| 検証 ②47 呼出箇所 | EditorModel ctor **47 個所とも** 唯一のライセンス消費が poll2 (0x180052a00) のみ → getStatus≡9 → thunk ac0(9)=1 (実 IR で実行検証) → 許可側。47 site 一覧は `work/ctors47.json` |
| 検証 ③既存 e2e | `bash tools/targets/kilohearts/snapins/run_all.sh` **exit=0** — 既存 6 種 200/200 bit-exact (wasm サイズも REPORT 通り 23,206/23,054/35,967/37,457/45,754/186,285 B)、Path A 対照・qemath 50/50 も増減なし (CAB-224/225 の追記分 --tol は既定 off で無干渉) |
| stub モジュール実行検証 | `lic_check.mjs` **70/70 PASS** (stub 定数 11 種 × 引数 3 種 / メモリ書込形状 3 種 / 実マージ 18 ケース対 / 実 thunk@9 ≡ stub 定数 5 種 / thunk 全状態スイープ 2 種 / 実マージ全状態 29 種 × 2 順) |
| wasm | stub モジュール A: **19,575 B** (undefined import 0) / B: 23,436 B (同 0) |

## 1. 実装 (`tools/targets/kilohearts/license/`)

| ファイル | 役割 |
|---|---|
| `lic_config.json` | stub 表 (VA・kind・定数値・根拠) + モジュール A/B 構成 |
| `lic_stub.py` | **IR 後処理 pass**。kind: `ret`(定数返し) / `store2`(out 構造体 2 値 store) / `apply_key`(状態=0x1a 設定) / `key_init`(実 0x180021490 の初期化再現 + found=1)。lift 範囲外の対象 (名前付き export の KHSUnlock 等) は定型 define を合成 |
| `lic_build.py` | build driver (`--module A/B` / `--dsp <snapin> [--no-stub]`)。snapins の Path B (RetDec stage-0 + kh_lower) を license/ 側で再実行し、ir_normalize 後に lic_stub.py を挟む。**snapins/ へは書込なし** |
| `lic_check.mjs` | stub モジュール A/B の node 実行検証 (70 項目) |
| `run_all.sh` | 1 コマンド E2E ([1] モジュール A/B → [2] 実行検証 → [3] snapin 6 種 base/lic → [4] まとめ) |
| `lift/`, `harness/`, `scripts/{fnscan,pe_dis}.py`, `snapins_head.json` | snapins (CAB-53, commit HEAD) 由来の**参照コピー** (lift pass 群 / ctx-fuzz harness / 設定) |
| `work/` (gitignore) | `ctors47.json` (47 site 一覧) / decomp_kh9.txt (新規逆コンパイル 6 関数) / モジュール・snapin 成果物 |

## 2. stub 適用点一覧 (関数 VA・置換内容・根拠)

| VA | 関数 (CAB-59 §2 同定) | 置換 | 根拠 (呼出文脈の実測) |
|---|---|---|---|
| 0x180054bd0 | `LicenseManagerHelper::getStatus` | **ret 9** | CAB-59 案B (推奨無力化点)。9 = バナー 0x180c194f0 の「バナー無し」条件・thunk 0x60003a0 許可側・poll 0x180052a00 編集可条件 (§3) |
| 0x1800549c0 | `getStatusAndDaysLeft` | store2 {9, 0} | {status=9, daysLeft=0} = ライセンス済み (期限なし)。manager null 時 0x16 フォールバックも消滅 |
| 0x1800548a0 | `hasTag` | ret 1 | tags vector 走査 (0x18010b6d0) の短絡。直接呼出 0 (間接のみ) だが「登録済み = 全 tag 保持」 |
| 0x180054ac0 | `getPending` | ret 0 | [mgr+0x488] (PACE==0x1c flag) の短絡。wrapper 0x180054ab0 は尾跳びなので結果も 0。バナーの「Click to open product page」系 UI 不発 |
| 0x1800b4ac0 | 分類 thunk A (0x60003a0>>s) | ret 1 | 機能ゲート (Import 0x180d5e820 / ブラウザ 0x180ef7fc0 / poll 0x180052a00・0x180052830) の常時通過。許可集合 {5,7,8,9,25,26} |
| 0x1800b4ad0 | 分類 thunk B (0x40001a0>>s) | ret 0 | バナーの {5,7,8,26} 判定。getStatus≡9 に対する実値 false と等価 (9 は後続 ==9 分岐でバナー解除) |
| 0x1800b4ae0 | 分類 thunk C (s==0x19) | ret 0 | s==25 (No license・編集不可) 判定 → 常時偽 |
| 0x1800b4af0 | 分類 thunk D (s==9) | ret 1 | s==9 判定 → getStatus≡9 に対する実値 true と等価 |
| 0x1800b4b00 | 分類 thunk E (s==0xd) | ret 0 | s==13 (License has expired.) 判定 → 期限切れバナー不発 |
| 0x180021d50 | isMasterKey | ret 1 | 鍵バッファ 0x182a2d5f0→40hex==f6e53827…1654 の照合を常時成立。unlock適用 0x18010a1e0 / 状態計算 0x18010aa20 / 通知 0x18010a740 の全ゲートが「鍵済み」経路 → ソース再計算 (boost FileWatcher 0x18010a3c0 / PACE) を回避 (CAB-59 案C の効果を定数で実現) |
| 0x180021bd0 | 鍵ホワイトリスト検証 | ret 26 (0x1a) | 検証戻り値を「unlocked」に固定 (正規鍵 2 系統の戻り値)。transform 0x180021f60 (salt `as0d789f6g` + 未同定ハッシュ) と 40hex 照合 5 個 (0x1813d0a40..b2f) を短絡 |
| 0x1800219b0 | unlock 鍵適用 | apply_key | [state]=0x1a を書込み 1 (成功) を返す。鍵文字列保持 (+8) は getStatus / 0x180054150 が読まないため省略 |
| 0x180021490 | 鍵状態初期化 | key_init | 実関数の初期化 (state=0x17・std::string SSO リセット {ptr,size}=0, cap=0xf) を再現し、製品順序表 (0x1813d08a0 `<ksqe><ksbc>…`) 検索を短絡して **found=1 (登録済み)** |
| 0x180002780 | `KHSUnlock` (export) | ret 0 (no-op) | アクティベーション入口の短絡 (strncpy_s 相当 0x180fb5a50(0x182a2d5f0,0x101,key) を廃止)。戻り値 void |
| 0x1800b4b10 | 状態マージ (保持) | **置換しない** | 入力が定数になるため実 IR のまま。29 エントリ優先度テーブルの挙動を wasm 実行で検証可能 (lic_check 18+58 ケース全一致)。※ CAB-59 REPORT §2 の「idx 24/25→2」は誤りで実機械語は **T[24]=0, T[25]=2, T[28]=0** (disasm + Ghidra decompile の両方で確認) |

## 3. 状態 enum の意味 (status 値 → 意味 対応表)

呼出文脈からの確定 (推定箇所は明記)。分類 class は状態マージ 0x1800b4b10 の優先度テーブル実値。

| status | 意味 | class | 根拠 (実測) |
|---|---|---|---|
| 0x14 (20) | 不正鍵適用済み系 | 0 | 0x1800219b0 長さ>99 → 0x18 と同系の失敗値群 (10..24 はテーブル 0) — 推定 |
| 0x17 (23) | 鍵状態「未初期化」 | 0 | 0x180021490 初期値 `{state=0x17}` |
| 0x18 (24) | 鍵「不正」 | 0 | 0x1800219b0: 鍵 null / 長さ>99 → 0x18。0x180021bd0: ホワイトリスト不一致 → 0x18 |
| **5** | ライセンスソース発見 (ファイル/ksub) | **4** | 0x18010aa20: ソース A (+0x140) / ksub (+0x228) の status getter 0x18017f940 が 5 を明示比較。バナー ad0 mask {5,7,8,26} = バナー無し |
| **7** | ソース C (+0x310) 有効 | **4** | 0x18010aa20: 0x180182c00 が 7 を明示比較。クラス名未同定 (CAB-59 引継 #3 のまま) |
| **8** | PACE (iLok) 有効 | **4** | 0x18010aa20: PACE (+0x3a8) 0x180111150 が 8 を明示比較。通知 0x18010a740 が [+0x488] = (PACE==0x1c) を設定 |
| **9** | ライセンス済み (一般) | **3** | **バナー 0x180c194f0: `status==9 → FUN_180130560` (バナー解除)**。thunk D 専用比較 (s==9)。発生源は 0x18017f950 (ソース A/ksub の第 2 getter) と推定 — 推定 |
| **13 (0xd)** | ライセンス期限切れ | 0 | バナー: thunk E (s==0xd) → **"License has expired. Click to open product page."** / "License has expired." |
| **25 (0x19)** | ライセンス無し (プリセット内では再生可・編集不可) | **2** | バナー: `status==0x19 && [EM+0x1088]==0` → **"You do not have a license for this plugin. It will still work as part of this preset, but can not be edited."** + "No license." + padlock icon。0x180021bd0 はホワイトリスト第 3/4 hash (0x1813d0ad0/0x1813d0a40) 一致時に 0x19 を返す (限定鍵)。Import/ブラウザゲートは thunk ae0 で除外 |
| **26 (0x1a)** | 鍵適用済み (unlocked) | **4** | 0x1800219b0: state==0x1a で即 return (適用済み)。0x180021bd0: ホワイトリスト第 1/2 hash (0x1813d0a70 / 製品一致時 0x1813d0aa0) → 0x1a。バナー ad0 mask 含む = バナー無し |
| 27 (0x1b) | その他 | 1 | マージテーブル class 1 のみ。呼出文脈未確認 — 推定 (予備) |
| 28 (0x1c) | PACE cloud 検証済みマーカー (状態値としては未使用) | 0 | 0x18010a740: `[mgr+0x488] = (PACE status==0x1c)` の bool 化にのみ使用。マージテーブルで 0 (=最下層) |
| 22 (0x16) | manager null / マスター鍵時の空結果 | 0 | getStatus / getStatusAndDaysLeft の null フォールバック。0x18010aa20 マスター鍵経路の戻り値 |

- **「ライセンス済み」として返すべき値 = 9** (根拠): ①バナー 0x180c194f0 が明示 `==9` でバナー解除する唯一の一般値、②thunk A (0x60003a0) 許可側 = poll 編集可 + Import/ブラウザゲート通過、③class 3 は class 4 ({5,7,8,26}) 未満だが**全消費者が 9 と {5,7,8,26} を区別しない** (消費者は thunk A/B + ==9/==25/==13 比較のみ — 実 IR 実行で全状態スイープ確認)、④CAB-59 案B の推奨値。26 でも等価 (lic_check B 系で裏取り済み)。
- ステータス消費者の全数: getStatus 直接呼出 6 (poll 0x180052a00・0x180052830 / wrapper 0x180054b90→バナー / getStatusAndDaysLeft / Import 0x180d5e820 / ブラウザ 0x180ef7fc0) + 0x180d5f190。thunk の全呼出はこの status に連なる (xref 実測)。

## 4. 検証結果

### 4.1 stub モジュールの実行検証 (`lic_check.mjs`, 70/70 PASS)
- モジュール A (stub 14 + 実マージ): getStatus/hasTag/getPending/thunk×5/isMaster/verify/KHSUnlock が**引数非依存**でライセンス済み定数を返す (0 / garbage / 実ポインタの 3 種引数で同値)。getStatusAndDaysLeft → [out]={9,0}・ret==out。keyInit → state=0x17・found=1・SSO リセット。applyKey → state=0x1a・ret 1。
- 実マージ (0x1800b4b10, lift 実 IR): 18 ケース対全一致 (例: merge(9,26)=26, merge(25,9)=9, merge(13,9)=9, merge(22,22)=22)。
- モジュール B (対照: thunk 5 種+マージは**実 IR**, getStatus のみ stub): **実 thunk に 9 を入力した戻り値 ≡ モジュール A の stub 定数** (5 種全部)。実 thunk の全状態スイープ (0..40) で許可集合 = {5,7,8,9,25,26} / {5,7,8,26} を再確認。実マージ merge(9,s) が s=0..28 全域で「class(9) 未満に落ちない」ことを 2 順で確認。

### 4.2 snapin 6 種 — DSP はライセンス層を通らない (検証 ①)
`lic_build.py --dsp <name> [--no-stub]` (base = stub 無し / lic = stub 適用・stub 関数を同一 wasm へ合成):

| snap-in | base: trial bit-exact | lic: trial bit-exact | base wasm | lic wasm | base licFn 参照 | undefined import |
|---|--:|--:|--:|--:|--:|--:|
| Channel Mixer | **200/200** (1149 call) | **200/200** (1149) | 23,206 B | 24,542 B | **0** | 0 |
| Gain | **200/200** (999) | **200/200** (999) | 23,054 B | 24,382 B | **0** | 0 |
| Haas | **200/200** (1100) | **200/200** (1100) | 35,967 B | 37,295 B | **0** | 0 |
| Clipper | **200/200** (1100) | **200/200** (1100) | 37,457 B | 38,793 B | **0** | 0 |
| Gate | **200/200** (999) | **200/200** (999) | 45,754 B | 47,082 B | **0** | 0 |
| 3-Band EQ | **200/200** (999) | **200/200** (999) | 186,285 B | 187,641 B | **0** | 0 |

- seed 1 × 200 trial (RFSPECIAL 含む乱数バッファ/パラメータ/状態、ABI 毒入れ検査内蔵)、base/lic とも**同一 native 参照 (ctx-fuzz vectors)** と bit 一致 → **DSP 出力は stub 適用前後で bit 一致**。
- base の lift IR にライセンス関数参照 0 件 (`lic_va_in_ir` 全 15 VA = 0) = **DSP process はライセンス層を通らないことの lift IR 上の実証** (CAB-59 §4 の静的結論を IR レベルで反証可能な形で確認)。
- lic 版 wasm は stub 14 関数が同一モジュールに合成され +1,328〜1,356 B (DSP 本体は不変)。

### 4.3 EditorModel 47 呼出箇所 (検証 ②)
- xref 実測: 0x180051af0 の直接呼出元 **47 関数** (0x180007a40 … 0x180880550, 各 1 回呼出) = `work/ctors47.json`。
- 47 ctor の callee を全数調査 → ライセンス関数への直接参照は **poll2 (0x180052a00) のみ** (getStatus/thunk/鍵系の直接呼出は 0)。poll2 の判定 = getStatus → thunk A → 編集可プロパティ ([EM+0x270]+0x1088 連動)。
- よって getStatus≡9 + thunk A≡1 の stub で **47 個所すべて「許可」側に分岐**。thunk A(9)=1 は実 IR (モジュール B) で実行確認、getStatus≡9 はモジュール A/B で実行確認。
- バナー (0x180c194f0) は status 9 で FUN_180130560 (バナー解除) へ到達 (decompile 実測)。Import 0x180d5e820 / ブラウザ 0x180ef7fc0 は thunk A(9)=1 かつ thunk C(9)=0 → 機能有効。

### 4.4 既存 snapins e2e (検証 ③)
- `bash tools/targets/kilohearts/snapins/run_all.sh` → **exit=0**。既存 6 種 s0: 200/200 × 6 (wasm サイズ REPORT §1 と一致)、Path A 対照 (matrix/gain/haas 200/200, clipper 0/200 = 既知の負の対照)、qemath 50/50 (4,800 call) — **増減なし**。CAB-224/225 追記の `--tol` (Resonator/Stereo/Disperser 用) は既定 off で既存 6 種の判定に影響しない (compare.mjs の注記どおり)。

## 5. 制限 / lift 範囲外

1. **UI 表示系は lift 範囲外**: バナー 0x180c194f0 / ブラウザ 0x180ef7fc0 / Import 0x180d5e820 自体は lift 対象でなく、stub 定数の正しさは IR 解析 + thunk/マージの実行検証による間接保証。GUI closure の lift は MS7 以降 (`docs/STATUS.md` §2)。
2. **EditorModel+0x1088 (編集可否 flag) の書込側は未解決** (CAB-59 §6-5 引継)。poll の「編集可」は thunk A 通過時に `[+0x1088]==0` を読むため、+0x1088 が非 0 に書かれる経路が残る限り編集不可表示の可能性 — vtable 経由と推定。
3. **ソース再計算の停止** (isMaster≡1) により、ライセンスファイル監視 (boost FileWatcher) / PACE ソースは動かない。外部通信なしで「鍵済み」固定になるのが本 stub の意図だが、`+0x140/+0x310` の実ライセンスファイル読み挙動は未検証 (実機確認は CAB-59 §6-6 引継)。
4. **鍵文字列の +8 保持を省略** (apply_key stub)。getStatus / 0x180054150 は読まないため観測差はないが、将来キー文字列を表示する UI を lift する場合は要保持に拡張。
5. 47 (EditorModel ctor 呼出元) と product_index.json の 46 (45 snapin + core) の差 1 は group/host 系の製品追加と推定 (未確定・CAB-59 の「47 = 製品数 47」の精度に依存)。
6. 0x180021f60 (鍵変換) のハッシュ本体 / +0x140・+0x310 のクラス名は未同定のまま (stub 化により実行不要になったため本チケットでは未解決、CAB-59 §6-2/3 引継)。

## 6. 次タスク提案 (下流チケット案)

1. **EditorModel 層の部分 lift**: 0x180051af0 (helper 初期化) + poll 0x180052830/0x180052a00 + EventSlot 群の lift → stub モジュールと結合して「スナップインが編集可能として立つ」までを wasm で実証 (+0x1088 書込側の解明を含む)。
2. **グループ/ホスト (ksge/ksco/Group) のライセンス経路**: 0x180ef7fc0 のブラウザ分類 (Essential/Premium/Hosts) と 0x180d5f190 周辺の lift — Phase Plant 等 3 呼出元の closure 確認。
3. **KHSUnlock 合成の置き場所**: 本 stub は export を no-op 化したが、将来「鍵入力 UI を動かす」場合は 0x1800219b0 相当の状態遷移を shim 側に復元する設計が必要 (lic_config.json の kind 拡張で対応可能)。
4. **resonator/stereo/disperser への stub pass 適用確認** (CAB-224/225 完了後): lic_stub pass は DSP closure に参照 0 なら no-op なので、6 種と同一の手順で収録確認のみ。

## 7. 成果物
`lic_config.json` / `lic_stub.py` / `lic_build.py` / `lic_check.mjs` / `run_all.sh` / `KH9_REPORT.md` (本文) / `lift/`・`harness/`・`scripts/{fnscan,pe_dis}.py`・`snapins_head.json` (snapins HEAD からの参照コピー) / `REPORT.md` §8 (追記のみ)。`work/` (gitignore): `ctors47.json` / `decomp_kh9.txt` / licA・licB / snapin 6 種 base・lic 成果物 / dsp_run*.log。
