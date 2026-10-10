# REPORT — CAB-101 startup-glue (THostInstance + CreateFruityInstance 呼出 + 終了処理 / ST-T1, 親 CAB-22)

preflight: RULES_SHA=ae9c6d414f7d ／ 書込範囲: `tools/startup/glue/`(新規) のみ。`tools/shimx/`・`tools/startup/{vreg,pump,winstubs}/`・`tools/assets/wvfs/`・`src/runtime/` は **読取のみ** (include / import / コンパイル参照のみ・変更 0 行)。
既知類型 (DEFECTS.md) との関係: **該当なし** (本 ticket は glue/結線規約で、lift/逆アセ/IR pass を扱わない)。
検証起点: 本 REPORT 記載の commit (HEAD 化後に `git archive` で再現・下記 §7)。

## 0. 結論 (数値は全て実測・数え方は §6)

1. **初期化順序規約を 10 段階の独立 API として実装**した (C: `glue_stage_*` / TS: `GlueHost.stage*`)。規約順は
   `paths → registry → pump → vfs → pre_dllmain → dllmain → host → boot → post → shutdown`。順序違反は
   **C 側 (`GLUE_EORDER`=-100) と TS 側ガードの二重で検出**され、違反した段階は done にならない (単体 §[2])。
2. **THostInstance (0x38 B) と vtbl 3 slot を逐語実装**し、`offsetof` で全フィールドを win64 実物と同じ
   オフセットに固定した (+0x08 version=1 / +0x0c flags / +0x10 hwnd_parent / +0x18 "FL Studio" / +0x30 cmdline])。
   CreateFruityInstance はハンドシェイク `0xC0 / 0xEDE95A` を検証して呼ぶ規約関数と、未達時のスタブを置いた。
3. **1 コマンド e2e `bash tools/startup/glue/glue.sh`** = exit 0。C 単体 **66 チェック** (ST/MT 同数)、TS 単体 **49 チェック**、
   SIGKILL 跨ぎ検証 (3 ファイル / 0 mismatch / レジストリ一致)、trace 監査 **4 項目**、陰性対照 2 件を **4.2 秒**で通す。
4. **SIGKILL 跨ぎ e2e を実装** (wvfs REPORT/既存方式を再利用): seed プロセスは onYield/onPageHide だけで flush して
   close せず親から `kill -9` (プロセスグループ)、別プロセスが Wvfs を開き直して全ファイルの sha256 を照合する。
5. **trace 監査**: username=webstudio で `C:\Users\user` 残存 **0 件**、写像残差 `/c/Users/` **0 件**、
   `stage=` の enter/ok 順が規約順と完全一致 (**10/10**)。
6. **発見 (1 件)**: pathreg の `pathreg_set_paths()` は、直後の初回 `pathreg_map()` が走らせる
   `pr_ensure_defaults()` で **既定 (webstudio) 表を作り直して上書きする** (実測・§5.1)。
   glue 側は set_paths の前に `pathreg_mount_count()` を 1 回呼んで既定ロードを先済ませて回避。**修正は pathreg 側に起票** (§9)。

## 1. 結線図 (本 ticket の範囲)

```
 main thread (JS/TS: tools/startup/glue/host/glue_host.ts)      engine Worker / wasm (glue.c)
 ───────────────────────────────────────────────────      ────────────────────────────────────
 ① glue_stage_paths("webstudio")  ── C ──►  pathreg_paths_init/set_paths + pathreg_install
                                           マウント表 8 件 (/fl /c/home /c/tmp /c) を構築
 ② glue_stage_registry()          ── JS ──►  RegBridge.create (seed.json import + flush フック)
                                       ── C ──►  pathreg_reg_hash + mark_saved
 ③ glue_stage_pump(-1)            ── C ──►  pump_set_wait_mode + リング初期化済み検査 (magic/cap)
                                       ── JS ──►  new PumpRing(memory, pump_ring_addr())
                                                時計較正: node=直接差 / browser=page ping-pong
 ④ glue_stage_vfs()               ── JS ──►  Wvfs.open(home/tmp) + FS.mount(/c/home,/c/tmp)
                                       ── C ──►  pathreg_map で home/tmp/fl の 3 目標が一致することを確認
 ⑤ pre_dllmain(cmdline)           ── C ──►  cmdline を host+0x30 バッファに投入 (URL クエリ由来)
 ⑥ dllmain()                      ── C ──►  規約上の位置のみ記録 (m11 closure は未結線)
 ⑦ glue_stage_host()              ── C ──►  THostInstance{vtbl 3slot, ver=1, flags=0, title, cmdline} 生成
 ⑧ glue_stage_boot()              ── C ──►  CreateFruityInstance(0xC0,0xEDE95A,&host,&iface)  (スタブ)
                                       ── C ──►  差し替え口: glue_set_create_fruity_instance (FL boot 貫通後に m11 export)
 ⑨ glue_stage_post()              ── C ──►  *iface 検証 + iface->vtbl[0]() Destroy
 ⑩ glue_stage_shutdown()          ── JS ──►  regbridge.onPageHide() → wvfs onYield/onPageHide → FS.syncfs
                                       ── C ──►  reg hash/mark_saved + trace dump
```

## 2. 規約 (実装した API)

| 段階 | C API (`include/glue.h`) | TS API (`host/glue_host.ts`) | 副作用 / 検証内容 |
|---|---|---|---|
| 0 paths | `glue_stage_paths(const char* username)` | `stagePaths()` | pathreg のマウント表再構築 + `pathreg_install()`、3 パスを map して trace に記録、mount 数 |
| 1 registry | `glue_stage_registry()` | `stageRegistry()` | RegBridge (seed import + flush フック) と C 側 hash/mark_saved |
| 2 pump | `glue_stage_pump(int wait_mode)` | `stagePump()` | wait mode 設定、リング magic/capacity 検査、較正要求、JS に PumpRing を露出 |
| 3 vfs | `glue_stage_vfs()` | `stageVfs()` | Wvfs×2 + FS.mount、C マッパと JS ミラーの一致照合 |
| 4 pre_dllmain | `glue_stage_pre_dllmain(const char*)` | `stagePreDllmain(cmd)` | cmdline を `+0x30` バッファに投入 |
| 5 dllmain | `glue_stage_dllmain()` | `stageDllmain()` | 位置のみ (m11 closure 未結線を trace に明記) |
| 6 host | `glue_stage_host()` | `stageHost()` | THostInstance 生成 (オフセット固定) |
| 7 boot | `glue_stage_boot()` | `stageBoot()` | ハンドシェイク検証 → スタブ/実関数 呼出、iface 記録 |
| 8 post | `glue_stage_post()` | `stagePost()` | iface Destroy 呼出 |
| 9 shutdown | `glue_stage_shutdown()` | `stageShutdown()` | レジストリ mark_saved、host が flush/syncfs/trace dump |

順序規約: `glue_stage_next()` 以外の段階を呼ぶと `GLUE_EORDER` (-100) を返し `glue_order_violations()` が増える。
段階の**再入場は冪等** (2 回目は no-op・違反に数えない)。`glue_reset()` でテスト用に初期化。

THostInstance (win64 実物と同一オフセット・`#pragma pack(1)` + 明示パディング):
`+0x00 vtbl(3slot) / +0x08 version=1 / +0x0c flags / +0x10 hwnd_parent / +0x18 "FL Studio" / +0x20,+0x28=&zero_page / +0x30 cmdline→buf[0x8000]` / size 0x38。
vtbl 逐語仕様 (stub_plan §2): slot0 = slot2 へ forward、slot1 = `ret`、slot2 = `a-=2 後 (a==1 && b<=1) ? 1 : 0`。

## 3. 成果物と実行コマンド

| パス | 内容 |
|---|---|
| `include/glue.h` | 公開 API・THostInstance/vtbl・段階 enum・trace 口 |
| `src/glue.c` | 実装 (順序規約・trace・THostInstance・CreateFruityInstance スタブ) |
| `host/glue_host.ts` | TS 側結線規約 (`GlueHost` クラス)。wvfs/pump/pathreg/vreg を import して結線 |
| `host/build.sh` | wasm ビルド (本 dir 専用 `work/`。shimx/winstubs/pump/pathreg/vreg を別 prefix で) |
| `host/glue_e2e.ts` | e2e ドライバ (5 phase) |
| `test/glue_unit.c` | C 単体 (66 チェック) |
| `test/glue_unit.ts` | TS 単体 (49 チェック) |
| `test/glue_child.ts` | SIGKILL 跨ぎ e2e の seed/verify 子プロセス |
| `scripts/count_checks.mjs` | 見出し数値の再計算 (規則 37) |
| `scripts/audit_trace.mjs` | 別アルゴリズムの検算 (trace 突合・規則 37) |
| `env.sh` | 環境前提 (規則 43) |
| `glue.sh` | 1 コマンド検収 |

```sh
bash tools/startup/glue/glue.sh                       # 全部 (exit 0 = ALL PASS)
node tools/startup/glue/scripts/count_checks.mjs      # 数値の再計算
node tools/startup/glue/scripts/audit_trace.mjs       # 別アルゴリズム検算
```

## 4. 実測 (所要は n=7 runs の min–max、load average は `uptime`)
| 項目 | 実測 | 数え方 |
|---|---|---|
| e2e 全体 | **3.8〜7.0 秒** (n=7 / 全 runs exit 0) | `glue.sh` の経過秒表示。7.0s はフル再ビルドを含む run。load average は 2.0〜3.3 (1分) / 2.8〜3.2 (5分) / 4.1〜4.2 (15分)。単発の代表値は採用しない (規則 38) |
| 内訳 (1 run) | build 1.5s / C 単体 ST+MT 0.2s / TS 単体 0.3s / SIGKILL+対照 1.5s / trace 監査 0.2s | e2e の phase 表示 (負荷で変動) |
| C 単体 | ST **66 / MT 66** (fail 0 両方) | `GLUE ALL PASS (pass=X fail=Y)` + stdout の ok 行 66 (56 `ok` + 10 stage done) |
| TS 単体 | **49** (fail 0) | `(pass=X fail=Y)`。ソースの `ok(` 呼出し静的カウント 49 と一致 |
| e2e 検証項目 | **12** | `host/glue_e2e.ts` の `ok(` 呼出し数 (grep ベース) |
| SIGKILL 跨ぎ | ファイル **3** / mismatch **0** / レジストリ値一致 | seed→`kill -9`(プロセスグループ)→verify の `"ok":true,"checked":3,"mismatches":0,"regOk":true` |
| trace | 行数 **40** / stage enter=ok=**10** | `audit_trace.mjs` の集計 |
| マウント表 | **8** 件 | `pathreg_mount_count()` = install + user 6 + `C:` |

## 5. 検証範囲 / 範囲外・発見

### 5.1 発見: pathreg `pathreg_set_paths()` の直後の初回 `pathreg_map()` が既定表で上書きする
- 観測: `glue_stage_paths("alpha")` の直後に `pathreg_map("C:\Users\alpha\Documents\x.txt")` が
  `/c/Users/alpha/...` (既定 `C:` 規則) を返し、`pathreg_get_mount()` は `C:\Users\webstudio` 入りの表を示した。
  原因は `pathreg_map()` 頭の `pr_ensure_defaults()` (`g_defaults_loaded` が false のとき既定 `pathreg_paths_init` +
  `pathreg_set_paths` を実行 = **カスタム表を作り直す**)。
- 対処 (本 dir のみ): `pathreg_set_paths()` の前に `pathreg_mount_count()` (= `pr_ensure_defaults()` の公開口) を
  1 回呼んで既定ロードを先に済ませる。対処後は `alpha` 表が保持され、`webstudio` は `/c/Users/webstudio` に落ちる (単体 ⑩で実測)。
- 起票先: **CAB-168 (pathreg) にコメント** (§9)。根本修正は pathreg 側 (`pathreg_set_paths()` が `g_defaults_loaded=1` を立てる)。

### 5.2 検証範囲 (やったこと)
- C 単体: レイアウト `offsetof` 11 件・規約順 10 段階・順序違反検出・vtbl 3 slot 逐語仕様・ハンドシェイク定数・trace 順序突合・username 上書き。
- TS 単体: JS/C 二重の順序検査・段階の独立呼出・flush フック (vreg 世代/store.save・値の往復)・wvfs mount とファイル書込 (`writeWin` / `FS.writeFile`)・pump RING (host push → `pump_step` で WM_KEYDOWN 受信)・trace 監査と識別対照。
- SIGKILL 跨ぎ: flush 点契約のみ (close なし) での永続。OS クラッシュではなくプロセス kill。

### 5.3 範囲外 (やっていないこと)
- **FL boot 未貫通**: `CreateFruityInstance` は C 側スタブ (host 検証 + iface Destroy のみ)。実 m11 export の呼出・
  DllMain closure・`TApplication.Run` は CAB-252 (unit#17) で貫通後に `glue_set_create_fruity_instance()` へ登録する。
- **Chrome/OPFS 実機**: 本 e2e は node (NodeBackend)。OPFS 実機の `onPageHide` 越えは wvfs の既存検収に委ねる。
- **OS クラッシュ (電源断) 耐性**: SIGKILL は OS ページキャッシュを落とさないため `fsync` の有無で差が出ない
  (陰性対照でファイル側 mismatches=0・レジストリ側 regOk=false を実測・下記)。
- **native 実行との比較**: native FL Studio は未実行 (本環境の検証対象外)。lift コードの実行結果とは別物。
- **ST-T3b 以降の winstubs 結線 (RegisterClass → pump_set_wndproc 等)**: 未接続 (§9)。

## 6. 数え方の定義 (規則 36・37)
- 「C 単体 N チェック」: `test/glue_unit.c` の stdout で `  ok   ` 行 (56) + 段階 10 個の `       stage <name> done=` 行 (10)。
  再計算: `node tools/startup/glue/scripts/count_checks.mjs` (出力: `C unit ST/MT: pass=66 fail=0 okLines=66`)。
- 「TS 単体 N チェック」: `test/glue_unit.ts` の `(pass=X fail=Y)`。同スクリプトがソースの `ok(` 呼出し数を別途数えて
  両者の一致も確認する (`static ok( calls = 49`)。
- 「e2e 検証項目 N」: `host/glue_e2e.ts` の `ok(` 呼出し行数 (12)。実行ごとの成否は `glue.sh` の exit code。
- 再計算 (別アルゴリズム): `node tools/startup/glue/scripts/audit_trace.mjs` — glue の検査 API を**使わず** trace 文字列だけで
  A enter 順一致 / B `C:\Users\user` 0 件 / C `/c/Users/` 残差 0 件 / D stage ok 10 種一致 を検算する。
- 「SIGKILL 跨ぎ N ファイル」: seed が書いた Win パス 3 件 (Manifest.xml / Demo.flp / tmp scratch.bin) で、
  verify が sha256 を照合した件数。

## 7. 検証起点とクリーン HEAD 再現
- 検証起点 commit: `<本コミット hash は preflight --since で確定・コミット後に追記>`。
- 再現: `git archive HEAD -- tools/startup/glue | tar -x -C <tmp>` 後、同梱の `glue.sh` を実行
  (絶対パスで他 dir を参照するスクリプトは無し。`REPO` は glue dir からの相対解決)。

## 8. 未解決・ブロッカー (起票先つき・規則 42)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| pathreg `pathreg_set_paths()` 直後の初回 `pathreg_map()` が既定表で上書き (§5.1) | username を変える Link 構成でマウント表が webstudio に戻る | (a) CAB-168 にコメント済 (§9) |
| `CreateFruityInstance` / DllMain closure が未接線 | 起動全体がこの先。本 ticket の規約は入口だけ用意 | (a) CAB-252 続 (unit#17) にコメント済 (§9) |
| winstubs RegisterClass → `pump_set_wndproc` 結線 (ST-T3b) | SendMessage/Dispatch が fail-soft 0 (`wndproc_miss`) | (c) CAB-101 親 CAB-22 に次タスク提案コメント (§9) |
| ctrl 経由の時計較正は node/直接差・browser page ping-pong の 2 経路のみ検証 | Chrome 実機の OPFS/AudioWorklet 経路は未検証 | (a) CAB-102 (pump) の既知実績を引用してコメント済 (§9) |

## 9. ユーザ依頼事項
なし (~/ダウンロード・既存抽出物とも未使用。素材・認証は不要)。
