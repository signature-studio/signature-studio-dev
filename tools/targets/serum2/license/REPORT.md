# Serum2 認可機構 呼出点マップ (CAB-71 / SR-2)

- 解析日: 2026-10-10 / 対象: Win x64 `Serum2.vst3` (19,236,864B, .text 10,593,334B, .pdata 33,791 関数) / 方針: `docs/LEGAL.md` §6.0 (ライセンス機構無力化・無条件アクティベーション・ライセンス状態データはユーザ承認の下で配置/合成可)
- 本タスクは **特定まで** (stub 実装は下流)。再現: `python3 license/scripts/authmap.py work/Serum2_win64.vst3 license/work` → `python3 license/scripts/zone.py license/work/graph.pkl <VA>` → `bash license/scripts/ghidra_auth.sh` (Ghidra light でターゲット 167 関数を decompile, 約3分)。
- 断定の凡例: confidence **high** = デコンパイル実測 / **med** = 静的照合 (xref・vtable・定数) / **low** = 推定 (明記)。

## 0. 結論 (先出し)

1. **demo/license 判定は音声経路 (`process`) に無く、状態の入出力 (VST3 setState/getState) と GUI overlay で効く**。`SerumDSP::process` 相当 (0x180056670, 16,558B — ProcessData 読み出しを実測) 内に demo/license フラグ参照を確認できず (med)。デモ制限の本体は「**ホストセッションへの保存/復元の抑止**」(デコード済み文言: "Sorry, the demo does not save or recall state with a host DAW session.") で、音の無音化・ノイズ挿入の証拠は無し (high)。
2. demo 状態の実体は **SerumController オブジェクト +0x22790 / +0x22792 (demo bit) / +0x22b70 bit4** と、保存先 state 内のマーカ (**JSON キー `demoVersion`**, controller 側マーカはキー `kAudioUnitParameterFlag_IsHighResolution` 値 4) (high)。
3. 認可検証の暗号実装は **静的リンクの Ed25519 + SHA-512** (固定定数で実測): verify/sign primitive 0x180432f20, SHA-512 0x180432e20/0x180432300/0x180432700/0x180432cd0, 群順位 L @ 0x180aa1ee0, "SigEd25519 no Ed25519 collisions" @ 0x180a711a0 (high)。
4. オンライン認可は **ブラウザ認可 + ローカル callback サーバ** 型 (実測): WININET 0x1801bb8d0/0x1801bc630/0x1801bca00, ShellExecuteExA 0x1801bc300, ソケットサーバ 0x180429290→0x18042dc20, ハンドラ 0x18042a950 (challenge 64B→SHA-512→"%02x" を実測)。エンドポイント path は **XOR 難読化で平文に無い** (§5, 復元は下流)。
5. オフライン license ファイルの入口は "**Locate License**" ダイアログ 0x18089ea80 (high)。選択後の parse/verify 呼出鎖は std::function 経由で静的未到達 (§6 未解決)。
6. 状態保存先: host session state (VST3) / `Serum2Prefs.json` (グローバル prefs, 0x1800211a0 singleton) / `\Xfer\Serum\SerumPrefs.json` / registry `Software\XferRecords\Serum2InstallerPrefs` / `\Xfer\Serumpresetdb.dat` (SQLite, preset DB) (high)。
7. **中性化方針 (§6.0) への写像**: demo 判定 3 点 (§2) を「常に licensed 経路」に通し、ネットワーク群 (§4) は shim 側 no-op/fail-fast、GUI overlay (§3) は非表示、license 状態データはユーザ承認の下で合成配置 (§7)。実装は下流チケット (§8)。

## 1. クラス構造と vtable (呼出点の座標系)

| オブジェクト | 証拠 |
|---|---|
| `SerumDSP` (AudioEffect 側) | RTTI `.?AVSerumDSP@@`, ctor **0x18003dcf0** が 8 個の vtable を obj+0x00/0x10/0x18/0x30/0x110/0x118/0x140/0x1d0 に設定 (0xa23f58/0xa23fd8/0xa24008/0xa24048/0xa240c8/0xa24128/0xa24158/0xa241c8) (high) |
| `SerumController` (EditController 側) | ctor **0x1800a9f40**, 主 vtable 0xa2bb98 (104 slots) + 0xa2bf58 (18 slots) ほか (high) |
| `SpliceController` (Splice RTO UI) | RTTI `.?AVSpliceController@@`, vtable 0x180ae31f8 (34 slots), VSTGUI FObject 系 (med) |

- VST3 ABI スロット名と実アドレスの対応は下表のとおり (関数セマンティクスはデコンパイル実測 / スロット番号→インタフェース名の厳密対応は med: 最小 host 実装時に実測確認を推奨)。

## 2. デモ判定 / demo フラグ (呼出点)

| VA | 関数 (semantics) | 根拠 | conf |
|---|---|---|---|
| **0x18004fad0** | `SerumDSP::setState` 相当 (vtable 0xa24048 slot 12, obj+0x30)。IBStream→JSON parse → tag `component`/`processor` → **キー `demoVersion` 検出でダイアログ表示し復元を打ち切り**。非 demo 経路はキー `version` (double) を 0.0 ≤ v ≤ **11.00001** (@0x180a21b60) で判定し DSP 内容を再ロード (0x1800506b0) | デコンパイル + XOR 文字列復元 (下表) | high |
| **0x18004ffc0** | setState の EH funclet (catch)。例外時 "An internal error occurred, please report this to Xfer Support." + "Unable to restore session state" | caller=0 空だが 0x18004fad0 を呼ぶ (MSVC funclet 特徴) + 復元文字列 | high |
| **0x1800c2b50** | `SerumController::setState` 相当 (vtable 0xa2bf58 slot 6)。tag `component`/`controller` → **`demoVersion` 検出でデモ状態ロード 0x1800c3080 → host へ restart 通知 0x800010** (`(**(code**)(*plVar2+0x30))(plVar2,0x800010)`)。JSON bool キー 0xfc8950 から **+0x22792 = ¬値**、`productVersion` と "**2.0.20**" (0xfd631e) 比較 <0 で +0x22792=1、+0x22790==1 なら +0x22b70 |= 0x10 | デコンパイル | high |
| **0x1800c6090** | `SerumController::getState` 相当 (同 vtable slot 7)。preset メタ (presetName/Author/Comment/Description) を書き出し、**+0x22792==1 のとき demo マーカ (キー 0xfc8950, 値 4) を controller セクションに書込** | デコンパイル | high |
| 0x1800c3080 | controller デモ/状態セクションの JSON ローダ (modMatrixLocked / scalarCurvesLocked / product 等)。呼出元: 0x1800c2b50 / 0x1800d5c00 / 0x1800d68b0 (preset ロード "Are You Sure?") | xref + decomp | high |
| 0x1800a9f40 / 0x1800ac190 | SerumController ctor / dtor — +0x22790 初期化と解放 | member disp 走査 (全 .text で +0x22790/92/22b70 を触るのは 5 関数 9 命令のみ: ctor 0x1800a9f40 / dtor 0x1800ac190 / 0x1800b9530 / 0x1800c2b50 / 0x1800c6090) | high |

**XOR 難読化文字列プール 0x180a21827–0x180a21940** (実測・復元済み。スキーム: `dec[i] = ((step*i)&0xff ^ ((i&7)+add7) ^ enc[i]) ^ xor8` / `dec[i] = enc[i] ^ ((i+add)&0xff)`):

| 位置 | 長 | 復元結果 | 使用箇所 |
|---|---:|---|---|
| 0xa21827 | 70 | `Sorry, the demo does not save or recall state with a host DAW session.` | 0x18004fad0 demo 分岐 |
| 0xa2186e | 18 | `Serum Demo Version` | 同上 (タイトル) |
| 0xa21881 | 64 | `An internal error occurred, please report this to Xfer Support.\n` | 0x18004ffc0 |
| 0xa218c2 | 31 | `Unable to restore session state` | 同上 |
| 0xa218e2 | 53 | `The host provided invalid data to the Audio Processor` | 0x18004fad0 非demo異常系 |
| 0xa21918 | 31 | `Unable to restore session state` | 同上 |

- 認可・demo 関連の UI 文言・URL path はこの方式の XOR 難読化が基本 (親 REPORT §5.2「平文に見当たらない」の正体)。`"%02x"` も 4 バイト即値 0xeaa3a0aa ^ (i-0x71) で場内生成される (0x18042a950 実測)。

## 3. GUI / demo overlay 呼出点

| 呼出点 | 内容 | conf |
|---|---|---|
| uidesc (`.rsrc` zstd → `work/serum2_uidesc.xml` 2,093,822B) | テンプレート **`overlay_demo_version` ×2 / `overlay_demo_version_mini` ×2** (デモ透かし), **`SpliceRTO`** ("Click \"Authorize\" to log into your Xfer account."), **`SpliceExpired`** (全画面 overlay 1190x740, sub-controller **`SpliceController`**), **`SpliceMaxLimit`** | high (uidesc 実測) |
| 0x180796320 / 0x180796090 / 0x180542a20 | SpliceController vtable メソッド ([1]/[10]/[15])。0x180796320 は HTTP executor 0x18042b240 と 0x1800cbb90 を呼む | med |
| 0x1804989d0 (13,072B) | ダイアログ統括 (dialog hub)。8 本の実行時生成 XOR 文字列 (0x7a=122B, step+0x4f/xor 0x74) を持つ — license 関連メッセージ群と推定 (low: 実行時生成のため未復元) | med |
| 表示判断の正確な分岐 | editor 側でどの state が overlay 選択を決めるかは **未特定** (GUI lift 界隈, 下流確認) | - |

## 4. オンライン認可 / ネットワーク呼出点 (対象外領域の座標)

| VA | 機能 | 根拠 | conf |
|---|---|---|---|
| 0x1801bb8d0 | `InternetOpenA` ラッパ ← 0x1801bb2b0 (UA "juce") ← {0x1800ce920, 0x18042b750, 0x180557b40 (FL wrapper 連携)} | IAT xref | high |
| 0x1801bc630 / 0x1801bca00 | `InternetOpenUrlA` / `HttpQueryInfoW+InternetReadFile` | 同上 | high |
| 0x1801bc300 | `ShellExecuteExA` (ブラウザ起動), 直接呼出 10 関数 | 同上 | high |
| 0x180429290 → 0x180430bd0 → **0x18042a950** | ローカル callback サーバ構築 (socket/bind/listen) → ハンドラ。0x18042a950 は要求 64B を **SHA-512 (0x180432e20)** → hex 化 ("%02x" を場内生成) — challenge/response 実装 | IAT xref + decomp | high |
| 0x18042dc20 / 0x18042fa30 | サーバループ (WSAPoll/accept/recv/send) + 送信。0x18042dbd0 (68B) がループから SHA-512 を呼ぶ | 同上 | high |
| **0x18042b240** | HTTP 要求実行器 (auth 共通)。呼出元: 0x180796320 (Splice), 0x1804989d0 (dialog), 0x1805ce4e0 (preset DB 26,434B "Found N presets"), 0x1800b61b0 ("IConnectionPoint" "SerumDSPSharedData"), 非同期 worker 0x1800cd270 / 0x1800fc1e0 / 0x1800fe930 (各 self-rec = thread entry), 0x18042dc20 | xref | high |
| 0x180427ef0 | HTTP 要求ビルダ — **Ed25519 primitive 0x180432f20 を呼ぶ** (メッセージ長 0x5b=91B を実測) | decomp | high |
| 0x180432f20 | Ed25519 primitive: SHA-512 init (IV 定数実測 0x6a09e667...) → update(32)+update(32)+update(M) → finalize → **reduce (0x1805f76e0) → scalarmult (0x1805f7f90)**。verify または keygen/sign の核 | decomp + 定数 | high (役割判定 med) |
| 0x1805f76e0–0x18060a2c0 帯 | Ed25519 群演算 (モンゴメリー/スカラー)。定数ブロック 0x180aa1e80–0x180aa1f40 に **L (群位数, 0x180aa1ee0 実測)**, p 系定数 | 定数照合 | high |
| 0x1801bee30 | CryptoAPI MD5 → hex (0x180007710 は snprintf 型書式ヘルパ) | decomp | high |
| 0x180001120 | 初期化時に URL 定数 + prefs singleton で 0x1e8B オブジェクト構築 (更新/アカウント状態の起動時フェッチと推定) | decomp | med |
| 0x180726ff0 / 0x1806fd740 | "Update Available from Your Account on xferrecords.com: " / "Download Update" — 更新確認 UI (認可ではなく更新) | 文字列 xref | high |

- URL 定数は `https://xferrecords.com` / `https://xferrecords.com/` のみ平文 (0x180001120, 0x180023ea0 ほか)。**エンドポイント path・license 形式マーカは XOR 難読化** (§2 方式の一般化)。プレフィックス定義 0x180a70beb–0x180a71170 は auth モジュール専用プール (各 4–16B, 実行時デコード)。

## 5. ライセンスファイル読込 (オフライン認可)

| 呼出点 | 内容 | conf |
|---|---|---|
| **0x18089ea80** (2,648B) | "**Locate License**" (0xfcbcd7) ファイル選択ダイアログ (VSTGUI CFileSelector 系)。文字列 "Help"/"Download"/"Copy"/"Locate" も同所 | high |
| 0x180662050 ← {0x1804989d0, 0x18049e0e0, 0x180661df0} | ダイアログ呼出元 (About/menu 系) | med |
| 選択後の parse/検証 | **未特定** (std::function コールバック内)。Ed25519 verify (0x180432f20 経路) と 0x18042b240 (HTTP) が候補。license ファイルの書式マーカも XOR 難読化で平文無し | - (下流) |

## 6. 状態保存先

| 保存先 | 呼出点 | 内容 | conf |
|---|---|---|---|
| host session state (VST3 setState/getState) | 0x18004fad0 / 0x1800c2b50 / 0x1800c6090 | **demo マーカの要** (§2) | high |
| グローバル prefs singleton | **0x1800211a0** → 0x1811bebc8 (初回 0x18001ea50 でロード, atexit 0x180021250 で保存)。ロード/保存本体 0x18001f500 (`Serum2Prefs.json`) | decomp | high |
| パス構築 | 0x18001f660 (SerumDSP ctor から呼ばれる): `%APPDATA%` 系解決 + registry `Software\XferRecords\Serum2InstallerPrefs` (0x180267210) + junction 0x180268ff0 | decomp | high |
| `\Xfer\Serum\SerumPrefs.json` | 0x180020290 (Serum Presets Path 等) ← 0x18001f660 / 0x18027bfe0 / 0x180313e70 / 0x18072e030 / 0x180777410 | 文字列 xref | high |
| `\Xfer\Serumpresetdb.dat` | 0x18052ed00 / 0x18052f6c0 — SQLite (preset DB)。ライセンス依存の記述は確認せず | 文字列 xref | med |
| GUID / Tick グローバル | init 0x18001e2c0: `CoCreateGuid`→0x1811be318 (44 関数が参照: Parameter/ProgramList/FObject 系), `GetTickCount64`→0x1811be380。**Machine ID の生成源とは断定できず** (親 REPORT B1 の未特定を維持) | daddr 走査 | med |

## 7. 中性化点 (方針 §6.0「無条件アクティベーション」への写像 — 実装はしない)

| # | 呼出点 | 現在の挙動 | stub での扱い (案) |
|---|---|---|---|
| N1 | 0x18004fad0 の `demoVersion` 分岐 | demo マーカ検出→ダイアログ+復元打ち切り | demo マーカを書かない (N3) ことで分岐自体が不活性化。防御として demoVersion キー検出時も無視して復元続行に差し替え可 |
| N2 | 0x1800c2b50 の +0x22792 群 | host state から demo bit を復元 | **常に licensed 値** (+0x22792=0 / +0x22790 は実態に応じ 0) を設定。0x800010 通知・0x1800c3080 デモロードを skip |
| N3 | 0x1800c6090 の demo マーカ書込 | demo のときマーカ保存 | 書込抑制 ( licensed として保存)。**ライセンス状態データの合成はユーザ承認の下で可** (§6.0-4) — host state / prefs への「アクティブ済み」値配置はこの枠 |
| N4 | 0x180056670 (`process`) | demo 参照なし | **無変更** (音声経路に手を入れない) |
| N5 | ネットワーク群 (§4 全面) | ブラウザ認可・HTTP・ローカルサーバ | 対象外方針どおり**呼ばない**。wasm shim では WININET/WS2_32 を no-op/fail-fast (`tools/shim` 流儀)。更新確認 UI (0x180726ff0/0x1806fd740) も出さない |
| N6 | 0x18089ea80 (Locate License) | ファイル選択 UI | 既にアクティブ扱いなので**出現させない** (menu 生成 0x1807235f0 系から除外) |
| N7 | GUI overlay (SpliceRTO/SpliceExpired/SpliceMaxLimit/overlay_demo_version) | license 状態で表示 | **非表示固定**。SpliceController は生成しない (uidesc 側 template 参照を外すのが最小) |
| N8 | prefs singleton (0x1800211a0) | 実ファイル読書 | vreg/shim の FS 層で実ファイルを読み書き (tools/startup/vreg と整合)。ライセンス鍵以外の prefs は通常動作させる |

- 補足: preset ファイル保存 (0x1800e9550, "Unable to Save Preset" は I/O エラー文言) に demo 分岐は無く、**保存制限は host session state 側のみ** (N1–N3) で賄える (high)。Serum2 demo の音声は制限無しと実測の範囲で判断 (N4)。

## 8. 未解決 / 下流チケット案

未解決 (本タスク内で特定に至らなかった点):
1. **Machine ID 生成源** — HWID 系 import 無しは親 REPORTどおり。GUID+Tick グローバル (0x1811be318/0x1811be380) と prefs/registry 保存値が候補だが、auth 要求への接続を静的には断定できず。
2. **エンドポイント path / license 書式の XOR 復元** — 実行時生成を含み静的 generalized 復元は未実施。Unicorn エミュレーションか実機観測 (ユーザ協力) が必要。
3. **license ファイル parse/verify の呼出鎖** — 0x18089ea80 のコールバック以降 (std::function)。
4. **GUI overlay 表示分岐** — editor 側の state → template 選択。
5. Ed25519 0x180432f20 の sign/verify 役割判定 (呼ばれる向きから verify 想定だが、検証式の突合まで未実施)。

下流チケット案 (起票はメイン判断):
- **[SR-2b] serum2-auth-stub 設計・実装** (親 CAB-13): 本マップ §7 N1–N8 の実装。入力=本 REPORT。成果=中性化 diff (最小箇所数) + license 状態データ合成スクリプト (ユーザ承認済み運用 §6.0-4) + vreg/shim 側 no-op 受口。目安 1〜2 週 (規模は N1–N3+N7 の 4 点が本体)。
- 依存: SR-1 (CAB-68, 最小 host) の vtable 座標系を実測確認できると N1–N3 の差し替え点が確定する (medium confidence の ABI slot を解消)。

## 9. 再現・成果物

```
cd tools/targets/serum2
python3 license/scripts/authmap.py work/Serum2_win64.vst3 license/work   # 呼出/データ/vtable グラフ (~2分)
python3 license/scripts/zone.py license/work/graph.pkl 0x18004fad0 4     # 逆到達
python3 license/scripts/zone.py license/work/graph.pkl --list 0x1800c2b50 0x1800c6090
python3 license/scripts/zone.py license/work/graph.pkl --who 0x180a24048 # vtable 参照者
bash license/scripts/ghidra_auth.sh                                      # 167 関数 decompile → license/work/ghidra_auth/decomp_targets.c
```
- `license/work/` (gitignore): graph.pkl, ghidraProjA/, ghidra_auth/ (decomp_targets.c), tmp/。ターゲット一覧は `license/targets_auth.txt` (167 関数, コミット済み)。
- 新規解析スクリプト: `license/scripts/{authmap.py, zone.py, ghidra_auth.sh}` (+ targets `license/targets_auth.txt`)。
- 制限: ① Ghidra light (noanalysis) のため indirect 呼出は vtable/関数ポインタ経由のみ追跡, ② XOR 文字列は setState/getState 系のみ復元 (実行時生成型は未復元), ③ mac 版は未実施 (Win を正とし lift 対象も Win)。

## 10. SR-2b 実装 (CAB-237, 2026-10-10 追記)

§7 N1–N8 のうち本体 (N1–N3 + N2b 通知経路) を **IR 6 ルール / 機械語パッチ 6 箇所**で実装した (バイト差分 15B / パッチ領域 17B — je→jmp 変換 2 箇所の rel32 再計算・pad 含む)。
実装・検証の詳細は **`authstub/REPORT.md`** (本 dir の authstub/ サブディレクトリ) に分離。

- 差し替え点の確定値: demo bit (+0x22792) writer は全 .text で 0x1800c2b50 の 2 store のみ、0x800010 即値も同関数のみ (全 33,791 関数 walk で再確認)。
- §2 の「判定 3点」のうち funclet 0x18004ffc0 は demo ロジック無し → patch 不要と確定。
- 新規所見: RetDec `--select-decode-only` の lift fidelity gap 5 件 (L1–L6, authstub/REPORT.md §6) — 本 lift 時の pass 追補対象。
- 再現: `bash authstub/e2e.sh` (wasm ハーネス 23/23 PASS) / `python3 authstub/synth_state.py <dir>` (licensed 状態合成, 決定論) / `python3 authstub/mpatch.py <pe> <out>` (機械語参照パッチ, 原 bytes 照合 6/6)。

## 11. SR-1 (CAB-68) 最小 host による実測フィードバック (2026-10-10 メモ追記)

`host/REPORT.md` (CAB-68 成果物) の実測のうち本マップに関係する確定事項 (記述の変更は無し, 追記のみ):

1. **§1/§2 の ABI slot が実測確定** (実 DLL の vtable 実読み): SerumDSP IComponent vtable = 0xa24048 で **slot12 = setState (0x18004fad0)**, IAudioProcessor vtable = 0xa240c8 で slot9 = process (0x180056670)。SerumController IEditController vtable = 0xa2bf58 で **slot6 = setState (0x1800c2b50) / slot7 = getState (0x1800c6090)** — §2 表の「実アドレス」列と一致。CAB-71 §7 の med 項目「0xa2bf58 の (interface, slot) 番号」は解消。
2. **`call [vtbl+0x30]` with 0x800010 = IComponentHandler::restartComponent (slot6)** — IComponentHandler は beginEdit/performEdit/endEdit/restartComponent の 4 メソッド。§7 の「slot5 (+0x28) と +8 ずれ」の疑問は SDK ABI 実測で解消 (restartComponent が slot6)。
3. **host session state の実形式** = `"XferJson\0"` + u64 meta JSON 長 + meta JSON + payload (u32 展開後長 + u32 2 + zstd)。§3 の合成物 (synth_state.py の meta JSON) はこのコンテナで封入する必要がある。meta だけでは setState が S_FALSE (payload は setState 内で実際に展開検証される — corrupt 対照で実証)。
4. **demoVersion による demo 経路の発火は実 DLL 経路では未観測** — meta の demoVersion は 0x18004fad0 / 0x1800c2b50 の分岐に届かず (payload 側 DOM 参照の推定)。controller 側 demo bit / 0x800010 は内部フラグ base+0x10c==1 が前提で headless 構成では 2 のまま。§10 の wasm ハーネス検証 (IR レベル) を引き続き正とし、payload 合成 + +0x10c setter 特定は host/REPORT.md §5 に引継。
