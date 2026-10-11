# REPORT (CAB-271 / SHX-T11) — pathreg `pathreg_set_paths()` 直後の初回 `pathreg_map()` が既定マウント表で上書きするバグの根本修正

preflight: RULES_SHA=ff4999169333
日付: 2026-10-11 / 親: **CAB-168** (Done) / 発見元: **CAB-101** (startup-glue 検収 §5.1, Done) / dir: `tools/shimx/pathreg/` / milestone: ブラウザ初回起動 (654c816c-07d2-401b-bd9b-8a52cf056b0a)
既知類型 (DEFECTS.md) との関係: **該当なし** (本 ticket は shimx インタフェース層の C 修正。lift/逆アセ/IR pass を扱わない)
書込範囲: `tools/shimx/pathreg/` **のみ** (`tools/shimx/` 既存ファイル・`tools/startup/` は 0 行・読取のみ。以下 §3 で実測)

## 0. 結論

1. **原因**: `pathreg_map()` / `pathreg_add_mount()` / `pathreg_remove_mount()` / `pathreg_mount_count()` の頭の
   `pr_ensure_defaults()` は `g_defaults_loaded` だけを見ており、`pathreg_set_paths()` がこのフラグを
   **立てていなかった**。`g_defaults_loaded == 0` のとき既定 `pathreg_paths_init()` + `pathreg_set_paths()`
   を実行して既定 (`C:\Users\webstudio`) 表を作り直すため、set_paths の**後**で初回照合が走ると
   呼出側の表が消える (CAB-101 §5.1 の観測と同一)。
2. **修正** (`src/pathmap.c` +17 行, `include/pathreg.h` 契約コメント +5 行): `g_defaults_blocked` (新設 static) を
   `pathreg_set_paths()` が 1 にし、`pr_ensure_defaults()` は `if (g_defaults_loaded || g_defaults_blocked) return;`
   とする。**既定表は `pathreg_set_paths()` を一度も呼ばない経路でのみ遅延ロードされる**。
3. **検証 (全て実測・数え方は §5)**: ① `set_paths` → `map` で上書きされない (C 単体 ST/MT PASS) ② 既定経路は
   従来どおり既定表がロードされる (別プロセスの C 単体 ST/MT PASS) ③ pathreg e2e **6 groups PASS** ④ glue e2e
   (CAB-101) 無劣化 (**66/66**・**49**・SIGKILL 跨ぎ mismatch **0**) ⑤ 既存 fixture **16 件不変**
   ⑥ 既定表 **8 本**・module 構成 (EXPORTED_FUNCTIONS) 非変更。
4. **ネガティブコントロール (規則 41)**: 修正を 1 つずつ外した ablate 2 件を build して **2 件とも FAIL** を実測
   (nc1 → `test_pathreg.c:70: nAlpha == 6` / nc2 → `test_defaults.c:14: pathreg_mount_count() == 8`)。
   → ①は nc1 で、②は nc2 で空振りでないことを確認した。
5. **所要 (規則 38・実測)**: `bash tools/shimx/pathreg/scripts/e2e.sh` = **12.9〜15.4 秒** (n=7・全 exit 0)。
   `bash tools/startup/glue/glue.sh` = **4.0〜5.7 秒** (n=2)。load average は §4。

## 1. 変更したファイル (`tools/shimx/pathreg/` のみ)

| ファイル | 変更 | 行数差分 |
|---|---|---|
| `src/pathmap.c` | `g_defaults_blocked` 追加・`pr_ensure_defaults()` の条件追加・`pathreg_set_paths()` にフラグ設定 (コメント付き) | +17 / -2 |
| `include/pathreg.h` | `pathreg_set_paths()` の契約コメントに既定ロード抑制を明記 | +5 / -1 |
| `test/test_pathreg.c` | §1.5 `test_defaults_vs_explicit()` (CHECK 23 件) を追加。`main()` の**最初**に呼ぶ (pristine 前提) | +61 |
| `test/test_defaults.c` | **新規** — 既定経路専用 C 単体 (`pathreg_set_paths()` を一度も呼ばない) | 72 行 |
| `test/pathmap.test.mjs` | JS ミラーの明示設定テスト (C と同一契約) を追加 (4→**5** 件) | +16 |
| `scripts/build.sh` | `test` に `test_defaults` ST/MT を追加・`nc` (ネガティブコントロール) ターゲットを新設 | +37 |
| `scripts/e2e.sh` | 4 phase 化 (C 単体 → ネガコン → module ビルド → JS 単体 + e2e) | +11 / -5 |
| `scripts/accept_recount.mjs` | LOC 集計に対応 + CAB-271 節 (binary 再実行) を追加 | 全面改訂 |
| `README.md` | 検収コマンド・既定ロード抑制の注記・`test_defaults.c` を追記 | +9 / -4 |

`tools/shimx/` 既存ファイル・`tools/startup/` は **0 行** (git status / diff で確認。§6)。
20 MiB 超 blob **0 個** (最大 = `module_a.mjs` 204,729 B)。

## 2. 修正の中身 (`src/pathmap.c`)

```c
static int g_defaults_loaded;    /* 既定マウント表をロード済み */
static int g_defaults_blocked;   /* pathreg_set_paths() で明示設定済み = 以降の既定ロードを禁止 */

static void pr_ensure_defaults(void) {
    if (g_defaults_loaded || g_defaults_blocked) return;   /* ← g_defaults_blocked を追加 (CAB-271) */
    g_defaults_loaded = 1;
    PathRegPaths p;
    pathreg_paths_init(&p);
    pathreg_set_paths(&p);
}

int pathreg_set_paths(const PathRegPaths* p) {
    if (!p) return -1;
    g_paths = *p;
    g_defaults_blocked = 1;      /* ← 追加 (CAB-271)。clear_mounts() の前 */
    pathreg_clear_mounts();
    ...
}
```

`g_defaults_blocked` を `pathreg_clear_mounts()` の**前**に置くのは、既定ロード経路 (`pr_ensure_defaults` →
`pathreg_set_paths`) からの再入を防ぐため。この経路では `g_defaults_loaded` が既に 1 なので
`pr_ensure_defaults` は再入しない (実際に ST/MT で無限再入なく完了することを実測)。

## 3. 書込範囲の検証 (他 dir 0 行)

```console
$ git status --porcelain -uall | grep -v '^?? tools/shimx/pathreg/' | grep pathreg
(出力なし = 担当 dir 外に本 ticket の変更 0 件)
$ git diff --stat -- tools/shimx tools/startup
 tools/shimx/pathreg/README.md                  |  9 +++-
 ... (以下すべて tools/shimx/pathreg/ 配下)
$ git diff --stat -- tools/shimx/src tools/shimx/*.sh tools/startup
(出力なし = shimx 既存ファイル・tools/startup は 0 行)
```

## 4. 検証結果 (実測・数え方は §5)

| # | 受入条件 | 結果 | 実測内容 |
|---|---|---|---|
| ① | `set_paths` → `map` で上書きされない (C 単体, ST/MT) | **PASS** | `test_pathreg.c` §1.5 (CHECK 23 件): pristine で `set_paths({userProfile:"C:\Users\alpha", vfsHome:"/home/alpha", vfsInstall:"/fl-alpha"})` → alpha 表 **6 本** / webstudio 残存 **0** / `map("C:\Users\alpha\Desktop\x.txt")` → `/home/alpha/Desktop/x.txt` / `unmap` 一致 / `shimx_path_to_posix` も alpha / `pathreg_mount_count()==8`。ST/MT 両方 `OK pathreg: defaults vs explicit set_paths (CAB-271)` |
| ② | 既定経路 (set_paths 未使用) は従来どおり既定表がロードされる (ネガコン) | **PASS** | `test_defaults.c` (CHECK 22 件・map 9 例): `pathreg_mount_count()==8`・既定 6 写像・未登録 4 件は <0・flags (0=RO / 7=`C:\`)・逆写先が webstudio・add/remove で 8→9→8。ST/MT 両方 `PATHREG DEFAULTS ALL PASS` |
| ③ | pathreg e2e 6 groups | **PASS** | `E2E PASS: 6 groups` / `[pathreg] ALL PASS (e2e.sh exit 0)` (n=7 全 exit 0) |
| ④ | glue e2e (CAB-101) 無劣化 | **PASS** | `bash tools/startup/glue/glue.sh` exit 0 / `ALL PASS`。C 単体 **66/66 fail 0** (ST/MT 同数)・TS 単体 **49 fail 0**・SIGKILL 跨ぎ `checked=3 mismatches=0 regOk=true` (対照 `regOk=false`)・trace 監査 `C:\Users\user` **0** / `/c/Users/` **0** / 順序違反 **0** / stage **10** |
| ⑤ | 既存 fixture 16 件不変 | **PASS** | `test/e2e.mjs` の `fixtures[]` は本 ticket で **0 行変更** (git diff で確認)。C↔JS 全 **16 件**一致 + 逆写像一致 + 追加マウント一致 + 表件数 **8** 一致 |
| ⑥ | 既定表・module 構成の非変更 | **PASS** | `defaultMounts()` **8 本** (win/target/flags 全一致)・C `pathreg_mount_count()==8`・EXPORTED_FUNCTIONS は module-a/b とも **0 変更** |

### 4.1 既定経路と明示設定経路の対比 (C 実測)

| 経路 | `C:\Users\webstudio\Documents\Image-Line\x.txt` | `C:\Users\alpha\Desktop\x.txt` |
|---|---|---|
| 既定 (set_paths 未使用) | `/c/home/Documents/Image-Line/x.txt` | `/c/Users/alpha/Desktop/x.txt` (残余 `C:`) |
| 明示 (`set_paths` alpha) | `/c/Users/webstudio/Documents/Image-Line/x.txt` (残余 `C:`) | `/home/alpha/Desktop/x.txt` |

旧実装では「明示」行が「既定」行と同じになっていた (上書き)。

### 4.2 所要・負荷 (規則 38)

| 項目 | 実測 | 数え方 |
|---|---|---|
| `scripts/e2e.sh` | **12.9〜15.4 秒** (n=7: 13.89 / 15.40 / 14.30 / 13.10 / 13.13 / 13.26 / 12.95) | `date +%s.%N` の前後差。全 runs exit 0 |
| `glue/glue.sh` | **4.0〜5.7 秒** (n=2: 修正前 4.007 / 修正後 5.666) | 同左 |
| load average | e2e 7 runs: 開始 **4.12/3.39/3.20** → 各 run 後 4.02〜4.46 / 3.39〜3.54 / 3.20〜3.27 | `/proc/loadavg` (1/5/15 分)。並列数 1 (逐次実行) |

e2e が旧 8 秒から増えたのは `test_defaults` 2 build とネガコン 2 build の追加分 (同一 16 コア共有)。

### 4.3 ネガティブコントロール (規則 41)

`bash tools/shimx/pathreg/scripts/build.sh nc` → exit 0。修正を 1 つずつ外した ablate 版を emcc で build して実行:

| ablate | 外したもの | 対象 | 実測 |
|---|---|---|---|
| **nc1** | `pathreg_set_paths()` の `g_defaults_blocked = 1` (= 修正のみ取消) | `test_pathreg` | **FAIL** `test_pathreg.c:70: nAlpha == 6` |
| **nc2** | `pr_ensure_defaults()` の既定ロード本体 (`if (1) return;`) | `test_defaults` | **FAIL** `test_defaults.c:14: pathreg_mount_count() == 8` |

両方 `FAIL as expected` を出力し `nc OK (2 ablations が FAIL を検出)`。ablate が PASS した場合は
`UNEXPECTED PASS — 照合が空振りしています` として exit 1 (空振り検出)。

## 5. 数え方の定義・独立再計算 (規則 36・37)

| 数値 | 定義 | 実測 |
|---|---|---|
| fixture N | `test/e2e.mjs` の `fixtures[]` 要素数 | **16** |
| CAB-271 CHECK N 件 | `test_pathreg.c` `test_defaults_vs_explicit()` 本文の `CHECK(` 出現数 (同一行 2 個は 2) | **23** |
| `test_pathreg.c` CHECK 総数 | ファイル本文の `CHECK(` 出現数 | **90** |
| `test_defaults.c` CHECK 総数 | 同左 | **22** |
| 既定経路 N 例 | `test_defaults.c` `main()` の `cases[]` 要素数 (fallback 3 含む) | **9** |
| ablate N 件 | `build.sh nc` が build・実行する ablation 数 | **2** |
| 既定マウント表 N 本 | C `pathreg_mount_count()` = JS `defaultMounts().length` | **8** |

独立再計算 (別アルゴリズム・規則 37): `bash tools/shimx/pathreg/scripts/build.sh all` 後に

```console
$ node tools/shimx/pathreg/scripts/accept_recount.mjs
mount table: JS defaultMounts()=8  C pathreg_mount_count()=8  -> MATCH(8)
C<->JS fixtures: e2e.mjs array entries=16  (REPORT claims 16) -> ACTUAL=16
normalize cases=18 (REPORT: 18) -> MATCH
extra CHECK pathreg_normalize=4 (REPORT: 4) -> MATCH
test_map cases=8 (REPORT: 8) -> MATCH
test_defaults map cases=9 (REPORT: 9) -> MATCH
CAB-271 explicit-paths (test_pathreg_st 再実行): -> PASS
CAB-271 default-path   (test_defaults_st 再実行): -> PASS
CAB-271 test body: CHECK(=23 / webstudio 残存 0 のガード=true
LOC: C=474 JS=461 TEST=654 SCRIPT=120 TOTAL=1709
    include/pathreg.h = 137 / src/pathmap.c = 279 / src/regpersist.c = 48 / src/pathreg_internal.h = 10
    js/pathmap.mjs = 109 / js/regbridge.mjs = 352
    test/test_pathreg.c = 295 / test/test_defaults.c = 72 / test/pathmap.test.mjs = 105 / test/e2e.mjs = 182
    scripts/build.sh = 94 / scripts/e2e.sh = 23
LOC C=474 (REPORT: 474) -> MATCH / LOC JS=461 -> MATCH / LOC TEST=654 -> MATCH / LOC SCRIPT=120 -> MATCH
accept_recount: MATCH (mounts 8 / fixtures 16 / CAB-271 PASS / LOC 1709)
```

`accept_recount.mjs` は e2e.mjs とは別系統に「REPORT が主張する数」を、①ソースのテキスト解析
(関数名で囲んだ `cases[]`・`CHECK(`) ②`defaultMounts()` と build 済み module の生 export ③**C 単体 binary の
再実行** (`execFileSync` で `build/test_{pathreg,defaults}_st.cjs` を起動) の 3 経路で数え直す。

### 5.1 行数の定義 (変更・除外)

「行数 N」= `wc -l` で README・REPORT・`scripts/accept_recount.mjs` を除く **12 ファイル**の改行数。
C=`include/`+`src/`、JS=`js/`、テスト=`test/` (`test_common.h` を除く)、スクリプト=`scripts/{build,e2e}.sh`。
`test_common.h` と `accept_recount.mjs` は CAB-168 以来の除外定義を維持。

## 6. 検証起点とクリーン HEAD 再現 (規則 45)

- 検証起点 commit: **5bfe20a** (`fix(shimx): pathreg explicit paths not overridden by defaults`) +
  **382ecb9** (`fix(shimx): report corrections`)。§4・§5 の数値は 5bfe20a を作る作業ツリーで計測。
- 報告前に同一ツリーで e2e.sh を n=3 再実行 (13.44 / 13.30 / 13.66 秒・全 exit 0) して確認。

```sh
# クリーン HEAD 再現 (別ツリー・リポジトリ非破壊。tools/shimx/pathreg/work/verify_<hash>・gitignore 済)
git archive HEAD -- tools/startup/glue tools/assets/wvfs tools/assets/vfs tools/shimx \
    tools/startup/vreg tools/startup/pump tools/startup/winstubs src/runtime tools/startup/keyfix | tar -x -C <tmp>
ln -s <repo>/node_modules <tmp>/node_modules      # vreg の JS 資産のみ import
bash <tmp>/tools/shimx/pathreg/scripts/e2e.sh     # → exit 0 / E2E PASS: 6 groups
bash <tmp>/tools/startup/glue/glue.sh             # → exit 0 / ALL PASS (CAB-101 無劣化)
node <tmp>/tools/shimx/pathreg/scripts/accept_recount.mjs   # → accept_recount: MATCH
```

**再現結果 (commit 382ecb9 の clean snapshot、実測)**:

| コマンド | 結果 | 所要 / load average (1/5/15 分) |
|---|---|---|
| `scripts/e2e.sh` | **exit 0** / `E2E PASS: 6 groups` / `ALL PASS` / C 単体 4 build OK (test st・defaults st・test mt・defaults mt)・`nc OK (2 ablations が FAIL を検出)` | **12.9 秒** (load 3.03/3.70/3.89 → 3.31/3.73/3.90) |
| `startup/glue/glue.sh` | **exit 0** / `ALL PASS` ・C 単体 ST **66/66 fail 0**・MT **66/66 fail 0**・TS 単体 **49 fail 0**・SIGKILL 跨ぎ `checked=3 mismatches=0 regOk=true` (対照 `regOk=false`)・trace `C:\Users\user` 0・`/c/Users/` 0・順序違反 0・stage 10 | **6.1 秒** (load 2.46/3.33/3.74 → 2.69/3.35/3.75) |
| `scripts/accept_recount.mjs` | **exit 0** / `accept_recount: MATCH (mounts 8 / fixtures 16 / CAB-271 PASS / LOC 1709)` | 0.5 秒未満 |

絶対パスで他 dir を参照するスクリプトは無し (`HERE` は pathreg dir からの相対解決。shimx は `$HERE/..`、
vreg は `$HERE/../../startup/vreg`)。**注意**: snapshot に `tools/assets/wvfs`・`src/runtime` を含めないと
glue e2e が `ERR_MODULE_NOT_FOUND` で失敗する (本 § の archive コマンドの一覧が必要)。

## 7. コミット・Linear

- コミット: `fix(shimx): pathreg explicit paths not overridden by defaults`。
  `flock /tmp/opencode/git.lock git add tools/shimx/pathreg && flock ... git commit -m ... -- tools/shimx/pathreg`
  (`git add -A` は不使用)。変更は `tools/shimx/pathreg/` のみ。20 MiB 超 blob 0 個。
- 重複確認 (規則 42・46): `list_issues(team, parentId=CAB-168)` → 子 **0 件**。
  `query="pathreg"/"set_paths"/"pathmap"/"マウント表"/"既定表"` を走査 → 本 bug の根本修正を扱う issue **0 件**。
  `list_issues(state="In Progress")` 15 件を走査 → 同 dir を触る稼働 **0 件**。
- Linear: **CAB-271** を起票 (title `[SHX-T11] pathreg_set_paths() 直後の初回 pathreg_map() が既定マウント表で上書きするバグの根本修正`,
  parent=**CAB-168** / project=**signature-studio** / team=Cabbagelettuse→Cabbagelettuce /
  assignee=me / milestone=**ブラウザ初回起動** 654c816c-07d2-401b-bd9b-8a52cf056b0a)。
  状態遷移: Backlog → **In Progress** (着手コメント) → **In Review** (完了コメント)。CAB-168・CAB-101 にもコメント。

## 8. 未解決・起票先 (規則 42)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `tools/startup/glue/src/glue.c` L178 の回避 (`pathreg_set_paths()` 前に `pathreg_mount_count()` を 1 回呼ぶ) が**冗長**になった | 動作に影響なし (既定ロードが先に行われるだけ)。削除には glue 側の変更が必要で本 ticket の書込範囲外 | (c) 親 **CAB-168** と **CAB-101** にコメント済 |
| `pathreg_clear_mounts()` 後に既定表が再ロードされない (1 度だけロードする設計) | 明示設定経路では clear 後に add_mount で明示構築する運用 (既存挙動を維持)。既定表が必要なら `pathreg_paths_init()` + `pathreg_set_paths()` | (c) 親 **CAB-168** にコメント (契約を `include/pathreg.h` に明記済) |
| `bash tools/shimx/test.sh --quick` は pathreg をリンクしない (PATH/無影響確認のみ) | shimx 本体の退行は本 ticket の対象外。`bash tools/shimx/test.sh --quick` → exit 0 / 27.2 秒で影響 0 は確認済 | 該当なし (対象外であることを本 REPORT に明記) |
| 実 FL バイナリを通した検証は未了 | 本 ticket はインタフェース層の C 修正。実 FL 結線は別 ticket | (c) 親 **CAB-168** / **CAB-101** の既存未解決に同じ |

## 9. ユーザ依頼事項

なし (~/ダウンロード・既存抽出物とも未使用。素材・認証は不要)。規則 49-4 の確認:
`ls ~/ダウンロード/`・`ls analysis/win64/extracted`・`ls analysis/mac/pkg_extract` はいずれも本 ticket で不要なため未参照。

## 10. 次タスク提案 (下流チケット案)

| # | チケット | 要点 |
|---|---|---|
| 1 | glue 側の回避削除 | `tools/startup/glue/src/glue.c` L178 の `pathreg_mount_count()` 先呼びを削除し、`pathreg_set_paths()` 直後に `pathreg_map()` しても表が保持されることを glue 単体で確認 (本修正で不要になった回避) |
| 2 | 明示設定経路の e2e 化 | `module-a/b` に `_pathreg_set_paths` / `_pathreg_paths_init` を export し、JS から struct を組んで protocol 切り替えを e2e 化する (現状は C 単体でのみ検証。export 追加は module 構成の変更を伴うため本 ticket では見送り) |
