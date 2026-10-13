# REPORT 付録 B — nfo §13〜§14 (CAB-216 / HB-H4' 結線 e2e + 検収)

> 本体: `tools/hostbridge/nfo/REPORT.md`。本書は REPORT.md の §13〜§14.6 (元 391 行版の 228〜372 行) を
> **無変更で分割移動**したもの (250 行上限のため・#437)。節番号は元のまま。

## 13. 追記 (CAB-216 / HB-H4', 2026-10-11): generateDb() → pathreg → 仮想 FS (wvfs) 結線の実行検証

**結論**: `generateDb()` の出力を `createPathRouter().route()` 経由で wvfs (`/c/home`) に書き、仮想 FS から読み戻して FL 側 reader 模型 + tools/flp 独立パーサで監査する結線を実装した。**node (NodeBackend) と Chrome 154 (OPFS, 実ディスクプロファイル) の両方で全項目 PASS**。FL 側コードは無改変 (FL 自身の reader が読む)。起動時 vs ビルド時の択はいったん保留とする (両者で決定的バイト列は同一なので運用側の決定事項 / 下流チケット案 §14-H4'' に記載)。

### 13.1 結線手順 (実装)

1. **DB root を vreg seed から導出** (`h4/virtual_fs_seed.ts` `pluginDbRootWin(seed)`): HKCU `Software\Image-Line\Shared\Paths\Shared data` = `C:\Users\webstudio\Documents\Image-Line\` → `…\FL Studio\Presets\Plugin database`。
   **既定 `DEFAULT_DB_PATH` (`C:\Users\Public\…`) は pathreg の書込対象外** (`route()` = null) — 生成器に `dbPath` を渡さないと仮想 FS に置けない (負の所見・陰性制御 1 §13.5)。
2. **生成**: `generateDb(specs, { dbPath })` → `Map<rel, Uint8Array>` (決定的)。
3. **経路**: `createPathRouter().route('<dbRootWin>\Installed\…')` → `{mount:'home', path:'/Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/…'}`。
4. **書込**: `mkdirpSync(dirname)` + `writeFileSync(path, bytes)`。102 ファイル全て route 成功。
5. **flush 点**: `onYield()` (ポンプ yield 点) / `onPageHide()` (pagehide・visibilitychange) — vreg / pathreg RegBridge と同名の契約。e2e は `onPageHide()` を明示呼出。
6. **FL 側の探索**: `.NFO` / `.FST` 大文字探索定数に対して wvfs の case-insensitive lookup が吸収 (元ケース保持 + 比較 lower)。e2e は全 102 ファイルを大文字化パスで読み直して一致を確認。

### 13.2 数え方の定義 (規則 36) と実測値

| 数値 | 定義 | 実測 |
|---|---|---|
| entry | 1 つの `.nfo` (+ 対応 `.fst`)。同名 32/64bit は 1 エントリ 2 ファイル (本 spec 集合には無し) | **50** |
| ファイル | `Installed` 配下の実ファイル数 (`.nfo`/`.fst`/`.Plugins.ini`/`VerifiedIDs.nfo` を含む) | **102** |
| spec 内訳 | specs/wasm_plugins.json 5 + Kilohearts index 展開 45 (= 実測 `formats` に 'vst2' かつ `id` 4 文字) | 50 |
| nfo 受理 | 独立パーサで `ps_files≥1` かつ全 `ps_file_plugclass_<i>` が slot 表で有効 かつ `ps_file_type_<i>` ∈ {1,2} | **50/50** |
| fst 分解 | 自前 FLhd/FLdt 分解で 199/201/203/212/213 が全て存在 | **50/50** |
| family | `Effects/VST` 46 / `Generators/VST3` 2 / `Effects/VST3` 1 / `Generators/VST` 1 (Phase Plant) | 実測 |
| journal | レコード 216 (PUT 204 + MKDIR 12) / distinct ファイル 102 / torn 0 | 実測 |
| 831/831 | 同梱 corpus の `.nfo` round-trip (nfo_e2e.sh 側、本 e2e では非再計算) | **維持** |

生成物の実機適応状況: spec 値 (OTT magic `XfTT` / KH magic product id 45/45 / Serum 2・Massive X CID) は CAB-219/§12 で実機 `.Plugins.ini`・`VerifiedIDs.nfo` と突合済み。本節は「その spec を仮想 FS のどこに書くか・読み戻して受理されるか」を検証したもので、**実機 FL への読み込み検証ではない** (§13.6)。

### 13.3 検証 5 段 + α (全 PASS、実測)

| 段 | 内容 | 実測結果 |
|---|---|---|
| ① | 生成 (OTT + Serum 2 gen/FX + Massive X + KH 45 + Fresh Air) | 50 entry / 102 ファイル / 70,571 B (live) |
| ② | pathreg → wvfs 書込 | route 失敗 0、`root = home:/Documents/…/Plugin database` |
| ③ | nfo reader + flp 監査 | 受理 50/50・rejected 0・`.fst` parse 50 + writeFlp byte-exact 50・wrapper path 50・203 name 50・ini セクション 50 verbatim 50・VerifiedIDs キー 50 |
| ④ | 仮想 FS 再読込一致 | sha256 不一致 0、大小変え読み一致 102/102、余剰ファイル 0、`Installed` 直下 = `.Plugins.ini, Effects, Generators, VerifiedIDs.nfo` |
| ⑤ | kill/reload 永続 | 別プロセスで書込み flush → SIGKILL → 再 open 後 不一致 0 / 102 大小変え一致 / audit 50/50 |
| ⑥ | レジストリ整合 | `Shared data` → `home` mount・`USERPROFILE`/`CSIDL_PERSONAL` が pathreg 既定 profile (`C:\Users\webstudio`) と一致 |
| ⑦ | Chrome OPFS (実機) | seed → SIGKILL → verify (別プロセス) で **不一致 0 / 102 一致 / node 側 manifest と OPFS 実物の sha256 102/102 一致** / torn 0 |
| ⑧ | 独立再計算 | `h4_recount.mjs` (別アルゴリズム) も 102/50/50/50/50・problems 0 |

所要: **3 回連続 5.25 s / 5.31 s / 4.4 s** (node + Chrome 2 起動 + 独立再計算込み。`nfo_e2e.sh` 経由の実行を含む)。load average: 開始 3.21–4.21 / 終了 3.27–4.21 (16 コア共有、他 subagent 稼働中)。起動ごとに実ディスクの Chrome プロファイルを新規作成 (tmpfs プロファイルは CAB-21/wvfs 実績で禁止)。

### 13.4 成果物 (すべて tools/hostbridge/nfo 内・追加のみ)

| パス | 内容 |
|---|---|
| `h4/virtual_fs_seed.ts` | 結線本体 (browser-safe: `node:` import 無し)。`seedPluginDb` / `readBackPluginDb` / `auditReadBack` / `registryConsistency` / `bytesInvariantToDbPath` / `pluginDbRootWin` |
| `h4/specs.ts` | spec 集合構築 (node/browser 共通。cli/gen.ts と同一の Kilohearts 展開規則) |
| `h4/seed_worker.ts` | Chrome/OPFS worker (seed / verify / probe-noflush) |
| `h4/seed_page.ts` `h4/index.html` | ページ雛形 |
| `h4/bundle.mjs` | esbuild bundle (esbuild は tools/assets/node_modules にのみ存在 → 絶対パス import) |
| `h4/h4_e2e.ts` | node + Chrome e2e ドライバ (kill/reload 子プロース生成を含む) |
| `h4_e2e.sh` | 1 コマンド入口 (`SKIP_H4=1` で nfo_e2e.sh から外せる) |
| `h4/tsconfig.json` | h4 専用 typecheck (assets 側の既存警告を巻き込まないため) |
| `h4_recount.mjs` | **独立再計算 (規則 37)**: ジャーナル自前デコード + 自前 `.nfo` パーサ + 自前 FLhd/FLdt 分解 + vreg seed × pathreg 写映射。実装側スクリトを import しない |
| `h4_accept_check.mjs` `h4_accept_chrome.mjs` | **検収側 独立再計算 (§14)**: CLI 別プロセス生成木・pathreg JS ミラー・正規表現パーサ・自前 SIGKILL 子プロセス・Chrome プロファイル LevelDB 実 journal の自前デコード |
| `nfo_e2e.sh` `package.json` `tsconfig.json` | h4 step 追加 / `e2e:h4`・`typecheck:h4` script 追加 (tsconfig の include は変更なし — §13.7) |

### 13.5 陰性制御 (規則 41、実測)

1. **dbPath 未上書き** (既定 `C:\Users\Public\…`): `route()` = null → `seedPluginDb` が `書込対象外` で失敗、仮想 FS にファイル **0 件** (raw 写映射 = `/c/Users/Public/…` = PERSIST でない)。→ **dbPath 上書きが必須**であることを実測で確認。
2. **flush 点を飛ばす** (node バックエンド): flush 呼び出し 0 のまま SIGKILL しても **102/102 読める**。理由 = `NodeBackend` の `write` は `fs.writeSync` = OS page cache 書込のため。**node 側では陰性制御として成立しない**。
3. **flush 点を飛ばす** (OPFS 実機): 1 ファイルだけ書いて `flushes=0` のまま SIGKILL → 別プロセスで**読める** (16 B `H4-NOFLUSH-PROBE` / store files=1)。noflush 店舗 (102 ファイル) も SIGKILL 後 **files=102**。→ **Chrome 154 の `SyncAccessHandle.write()` は `flush()` を待たずに SIGKILL を跨いだ** (wvfs REPORT の「flush 点前に死ぬと未 flush 分は失われる」という契約記述とは異なる実測)。主張は実測に合わせて「未 flush 書込も SIGKILL を跨いだ」と報告する (契約バグの疑いは tools/assets 側の課題として起票)。

### 13.6 検証範囲 / 範囲外 (規則 40)

- **範囲内**: 生成 → pathreg 経路 → wvfs 書込 → 読み戻し → FL reader 模型 (`fle:0x910cd0` 準拠) + tools/flp 独立パーサでの受理・往復・仮想 FS 永続・vreg seed とのパス整合。
- **範囲外 (未実行)**: ① **lift 済み FL の PluginManager 経路 (`fle:0x910cd0` / `0xaba430`) に生成 DB を読ませる実行検証** — boot 貫通後 (CAB-252 [FLE-2] x64c M11 boot chain) に段階分離して実施する (本節の「受理 50/50」は reader **模型**の判定であり FL 実物の判定ではない)。② Fruity Wrapper が生成 `.fst` を読んで VST2/VST3 を起動できるか (§6-2 / H10)。③ `ps_file_filename` の実バイナリ存在 (モジュール本体は asset VFS / H4 スタブ側)。④ 32bit・AU・CLAP 系 (本 spec 集合に無し)。⑤ Firefox/Safari (OPFS SyncAccessHandle 非対応)。
- **クリーン HEAD**: 本節の数値は commit `4b162ce` (`feat(nfo): generate db to virtual fs (CAB-216)`) から再現。検証方法: ① コミット済み HEAD の実ディレクトリで `bash h4_e2e.sh` (3 回連続 PASS) ② `git archive HEAD` のスナップショット (`work/verify_4b162ce/`、物置に symlink で node_modules を接続) では **node 側 5 段 + 独立再計算は全 PASS、Chrome フェーズのみ `report timeout`** (spawn-server の URL 解決が入れ子 `work/verify_*/` パスで失敗するハーネス側の事象。実ディレクトリでは 3 回連続で PASS)。③ 既存 `nfo_e2e.sh` にも exit 0 で通る。

### 13.7 規約・注意

- `tsconfig.json` の `include` は **変更なし** (`src, cli, test` のまま)。`h4` を入れると読み取り専用 `tools/assets/wvfs` の既存型エラー (OPFS 系 lib 不足 / `wvfs.ts:177` の未使用 local) が既存 `nfo_e2e.sh` の typecheck step を壊すため、h4 は `h4/tsconfig.json` (ES2023/WebWorker lib) で別検査する。
- 書込は `tools/hostbridge/nfo/` のみ。`tools/assets` / `tools/shimx` / `tools/startup` は読取のみ (import・fetch はするが無改変)。`work/` は gitignore 済み (Chrome プロファイル・OPFS store を含む)。
- 既存 `nfo_e2e.sh` に h4 step を追加したが、**既存 step の数値は不変** (round-trip 831/831、tests 40/40、実機照合 21+20+19 checks、生成 50 entry/102 ファイル)。

### 13.8 未解決 (起票先付き、規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| lift 済み FL の `fle:0x910cd0` / `0xaba430` に生成 DB を読ませる実行検証が未了 (reader 模型 50/50 で代替) | 「FL が実物で受理する」最終確認が残る | (b) 新規子チケット (boot 貫通後。重複確認済み) |
| Chrome 154 OPFS で `write()` 後の `flush()` 無しでも SIGKILL を跨ぐ (wvfs 契約記述と不一致) | flush 点設計の過剰/不足の評価 | (a) CAB-123 (RT-5/wvfs) にコメント済 (読取専用のため修正はしない) |
| 起動時 vs ビルド時の DB 書込択 | 起動時刻・初回起動体験 | (c) 親チケット CAB-98 に提案コメント |
| `ps_file_filename` の実バイナリ存在 (VST2/VST3 モジュール本体) | DB は読めても LoadLibrary 先が無いと plugin 起動しない | 既存 CAB-93 (HB-H4) にコメント済 |

### 13.9 ユーザ依頼事項

今回はなし (spec 元データは全て揃っている)。任意: Windows 実機の `Installed\` 単体 `.nfo` (VST2 側) があると writer の byte 直比較が完了する (§7 継続)。

---

## 14. 検収 (CAB-216 / HB-H4') — 検収側 独立再計算・別アルゴリズム検算

### 14.1 検収側 独立再計算スクリプト (規則 37: 実装側とは別アルゴリズム)

| スクリプト | 別アルゴリズムの要点 | 実行 |
|---|---|---|
| `h4_accept_check.mjs` | 生成基準は `cli/gen.ts` を**別プロセスで実ディスクに書いた木** (`h4/specs.ts` 非 import。集計は `readdirSync(withFileTypes)` 再帰) / Win→VFS 写 Mapping は pathreg **JS ミラー** `shimx/pathreg/js/pathmap.mjs` の `createMapper` で `/c/home` を自前 strip (`pathlink.ts` の `route()` は本編不使用・末尾 cross-check のみ) / 書込は `seedPluginDb` を呼ばず自前ループ / `.nfo` 受理は**正規表現** (`^key=(.*)$`) で判定 (src/entry.ts の map 先勝ちパーサとは別コード) / SIGKILL は自前子プロセス (flush 0 のまま自殺) | `node h4_accept_check.mjs` |
| `h4_accept_chrome.mjs` | Chrome プロファイル配下の **LevelDB (実ディスク) のジャーナル実ファイル**を直接読み自前レコードデコーダでツリー復元 (wvfs の Journal/Wvfs 非 import)。照合相手は `cli/gen.ts` の実ディスク出力 | `node h4_accept_chrome.mjs work/h4/chrome-profiles/h4-e2e-XXX` |

**実行順**: `bash nfo_e2e.sh` (または `bash h4_e2e.sh`) → `node h4_accept_check.mjs` (`work/h4-accept/cli-out` を生成) → `node h4_accept_chrome.mjs work/h4/chrome-profiles/h4-e2e-XXX`。3 本とも exit 0。

所要: `h4_accept_check.mjs` **0.36 s × 3 → 最終実行 exit 0 / 45 ok** / `h4_accept_chrome.mjs` exit 0 / 12 ok。load average 開始 2.14–36.87 / 終了 2.88–36.87 (他 subagent 稼働中)。`nfo_e2e.sh` 最終実行 exit 0 / 7.60 s (load 2.14→2.88)。

### 14.2 照合表 (実装側 REPORT §13 の主張 vs 検収側 独立再計算)

| 受入条件 | 実装側主張 | 検収側 実測 | 判定 |
|---|---|---|---|
| 生成 | 50 entry / 102 ファイル / 70,571 B | 50 / 102 / 70,571 B (CLI 別プロセス + 再帰 walk) | PASS |
| 仮想 FS 書込 | route 失敗 0 | 0/102 (pathreg JS ミラー)。pathlink.route と一致 | PASS |
| round-trip nfo 受理 | 50/50 | 50/50 (正規表現パーサ)、drop 0・rejected 0・重複キー 0 | PASS |
| round-trip fst | parse 50 / writeFlp byte-exact 50 / wrapper path 50 / 203 name 50 | 50 / 50 / **50 (`.nfo` の `ps_file_filename_0` と 213 照合 = 検収側独自)** / 50 | PASS |
| ini / VerifiedIDs | セクション 50 verbatim 50 / キー 50 | 50 / 50 verbatim / 50 (全 entry `.NFO` 参照 50) | PASS |
| 仮想 FS 再読込一致 | sha256 不一致 0・大小変え 102/102・余剰 0 | 0 / 102 / 0 | PASS |
| SIGKILL/reload 永続 | 不一致 0 | flush 0・自前子プロセス SIGKILL → 不一致 0・大小変え 102/102 | PASS |
| レジストリ整合 | `Shared data` → home mount | `/Documents/Image-Line` (createMapper)。USERPROFILE/CSIDL_PERSONAL 一致 | PASS |
| Chrome OPFS 実機 | sha256 102/102 一致・torn 0 | 実ディスク LevelDB ジャーナル 2 store (216 rec / 624 rec) 各 **102/102 sha256 一致・torn 0** | PASS |
| 独立再計算 (実装側) | 102/50/50/50/50・problems 0 | `h4_recount.mjs` exit 0 で同値 (worktree でも再現) | PASS |

### 14.3 ネガティブコントロール・アブレーション (規則 41、検収側)

1. **dbPath 未上書き** (`DEFAULT_DB_PATH` = `C:\Users\Public\…`): createMapper → `/c/Users/Public/…` = **HOME 外** → 102/102 が書込対象外・**書込 0 件**。→ dbPath 上書きが必須 (実装側 ⑤b-1 と一致)。
2. **1 バイト改変** (OTT.nfo の `ps_file_plugclass_0=0`→`1` = DX): 受理 usable **1→0**。別改変 (`ps_file_filename_0` の `C`→`Z`): 213 wrapper path と**不一致**。→ round-trip 監査は改変を検出する (PASS のみの検査ではない)。
3. **no-flush probe** (OPFS 実機): ジャーナル自前デコードで `op=1 path=/probe/unflushed.bin data(16)="H4-NOFLUSH-PROBE"` を SIGKILL 後の実ディスクに確認 → 実装側 ⑤b-3 と一致。

### 14.4 検収で見つかった誤記 (本 commit で修正)

§0・§3・§4・§5 の数値が Massive X 追加 (§12.5) ・tests 増 (§12.2) 以前の値のままだった: 生成 **49→50 entry / 100→102 ファイル**、reader **49/49→50/50**、Kilohearts **(46)→45**、テスト **29/29→40/40**、§3 の「e2e 全体 1.7 s」を実測に置換、§5 の生成量 **69,342→70,571 B**、§5 Massive X 行「未取得」→§12.5 確定値、§6-6/§7 の Massive X 依頼を取下げ、§8 H4' を完了扱いに修正。ヘッダの「約 8 s」は**定義付き実測値** (min–max・n=3・load average) に置換 (規則 38)。

### 14.5 未解決 (起票先付き・規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `cli/metrics.ts` の Kilohearts 展開規則が `cli/gen.ts` / `h4/specs.ts` と不一致 (Phase Plant を `kind:"effect"` / `category:"Kilohearts"` で `Effects\VST\` に置く。正は `Generators\VST\`) | `work/metrics.json` の `generatedBytes` が 70,921 B (正は 70,571 B)。entry/ファイル数と reader 受理は不変のため **REPORT の見出し数値・e2e 出力には影響なし** (nfo_e2e.sh は generatedBytes を印字しない) | (b) 新規子チケット (CAB-216 配下・重複確認済) |
| REPORT.md が 315 行 (規則の上限 200 行。CAB-216 の §13 追加で 214→307) | 可読性・保守性 | (c) 親 CAB-98 に提案コメント |
| 起動時 vs ビルド時の DB 書込択 | 起動時刻・初回起動体験 | (c) 親 CAB-98 (§13.8 と同) |
| lift 済み FL の `fle:0x910cd0` / `0xaba430` に生成 DB を読ませる実行検証 | 本節の 50/50 は reader 模型の判定 | (b) 子チケット (§13.8 と同) |

### 14.6 検証範囲 / 範囲外 (規則 40)

- **範囲内**: コミット範囲の検査・担当 dir のみの書込・`nfo_e2e.sh` / `h4_e2e.sh` の実ディスク再実行 (exit 0・tests 40/40・round-trip 831/831・実機照合 21+20+19)・検収側 独立再計算 2 本・ネガコン 3 件・`git archive` / `git worktree` でのクリーン HEAD 再現。
- **範囲外 (未実行)**: lift 済み FL 実物 reader への読み込み検証 (boot 貫通後・§13.6)・Fruity Wrapper の生成 `.fst` 受入 (§6-2/H10)・32bit/AU/CLAP・Firefox/Safari・FL 実機 (Windows) での起動確認。
- **クリーン HEAD**: `git worktree add --detach work/wt_h4 HEAD` で `h4_e2e.sh` を再実行 → node 側 42 ok / 0 FAIL・`h4_recount.mjs` exit 0。**Chrome フェーズのみ `report timeout`** (入れ子 `work/wt_*` パスで spawn-server の URL 解決が失敗するハーネス事象。実装側 §13.6 の記載と一致。実ディレクトリでは 3 回連続 exit 0)。検証後の worktree は撤去済。
