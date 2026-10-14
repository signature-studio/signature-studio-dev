# DECISIONS — 設計決定記録 (ADR)

プロジェクトの方式決定と理由・日付を残す。**決定の事実のみ**。測定値は各 `REPORT.md` を参照。

書式: `D## / 状態 / 日付 / 決定 / 理由 / 影響`

---

## D1 — Workers Static Assets「案 S」の採用

- **状態**: 採用 (2026-10-10)
- **決定**: Worker コード無しの **Workers Static Assets 1 本**に全資産を載せ、`_headers` で COOP/COEP/CORP を `/*` 一括付与。
  Cloudflare Access は `worker` 型 (`destinations:[{type:"worker"}]`)、`preview_urls: false`。
  **R2 / zone Transform Rules は不要** (静的アセットへのリクエストは無料・無制限)。
- **理由**: 既定ホスト名 (workers.dev) だけで COOP/COEP を成立させる必要があり、R2+Transform Rules 構成は
  自前ゾーンが前提で使えなかった。静的アセット配信を Worker でプロキシするとリクエスト課金・
  レスポンスサイズ上限・キャッシュ管理が別途必要になる。
- **影響**: 旧構成 (R2 バケット + カスタムドメイン + ゾーン Transform/Cache/Compression Rules + hostname 型 Access)
  は `deploy/legacy-r2/` に退避。25MiB 超・Range リクエスト・2 万ファイル超が必要になった時の次点。

## D2 — ライセンス無力化方針

- **状態**: 確定 (2026-10-10 ユーザ指示)
- **決定**: FL 本体・同梱プラグインの**全ライセンス/アクティベーション機構を無力化**する。ライセンス状態は常に
  「アクティブ済み/登録済み」として振る舞う (無条件アクティベーション)。ライセンス状態データ
  (レジストリ値・ライセンスファイル等) は、正規保有者であるユーザの承認の下で配置・合成してよい
  (「必要であれば cracked リソースを配置可能」を含む)。オンライン認証通信は行わない。
- **理由**: ユーザ確定方針。条項上の論点の事実整理は `docs/LEGAL.md` §0-3・§6.0 に残す。
- **影響**: ライセンス系 stub (`tools/targets/*/license`, `tools/startup/vreg`, `tools/startup/keyfix`) の設計原則。
  OSS 再配布ライセンスの論点は別件・未回答 (`docs/LEGAL.md` §6.0-7)。

## D3 — 外部通信機能は対象外

- **状態**: 確定
- **決定**: Gopher AI / FL Cloud / 認証・ログイン・更新確認など**オンライン通信を要する機能は実装対象外**。
- **理由**: プロジェクト目的が「ブラウザ上でのローカル的な完全動作」であり、通信機能は検証不能・法理論点も増える。

## D4 — worktree + PR 運用

- **状態**: 確定 (2026-10-12 ユーザ指示)
- **決定**: `master`/`main` には変更を加えない。**ブランチを切る → worktree 作成 → 実装 subagent →
  レビュー subagent → PM がマージ**。全作業は subagent 委任、1 チケット = 1 subagent。
- **理由**: 共有ワークツリーで `git reset` により他セッションのコミットが失われる実事故が 2 件発生したため。
- **影響**: `docs/WORKFLOW.md`・`AGENTS.md`。

## D5 — x64c 主役化・RetDec の位置づけ

- **状態**: 確定 (2026-10-12 時点)
- **決定**: 主力 lifter は**自作 x86-64 → C lifter `x64c`** (`tools/flelift`, `tools/liftlib`) と
  Repair基盤 `liftlib`。**RetDec は過去の試験的手段**として位置づける。
  旧 RetDec 路線 (`tools/m6`〜`tools/m10`, `tools/m11` の大枠) は履歴として保持するが、
  新規の lift は x64c / flelift / liftlib を使う。
- **理由**: RetDec 路線の構造欠陥 (間接 call 脱落・小さすぎる global 宣言・stack 引数脱落・
  証明不能な lift) が判明し、修復コストが x64c 自作を上回った (`tools/ott/REPORT.md` §2)。
- **影響**: 旧 README の「x64 ELF/PE → RetDec → emcc」という記述は削除された (現状と不一致)。

## D6 — ルール読了証跡 (preflight ハッシュ転記) 運用の廃止

- **状態**: 廃止 (2026-10-12)
- **決定**: REPORT 冒頭の preflight 読了証跡 (ハッシュ 1 行) と、外部 `[SUBAGENT-RULES]` (`docs/REFERENCES.md`) の
  ハッシュ運用は**廃止**。ルールの正本は repo 内 `docs/WORKFLOW.md` に一本化した。
- **理由**: rules を更新するたびに全 REPORT (15 箇所以上) の証跡行が陳腐化し、全面修正の労力が
  肥大化していた。原本 repo 外・repo に存在しないため新しい参加者が読めない問題もあった。
- **影響**: 各 `REPORT.md` の証跡行は削除済み。検証手順は `docs/WORKFLOW.md` を参照。


## D7 — Fresh Air UI は lift 対象外・素材は非同梱 (HUD 方針に合流)

- **状態**: 採用 (2026-10-13, issue #53 [FA-6])
- **決定**: Fresh Air の UI (Skia 静的リンク・`.rsrc` 内 PNG/vec 等) は **lift 対象外**とし、DSP のみ wasm 化する。
  UI 素材はリポジトリ・配信物に**同梱せず**、ユーザ手元の正規インストーラから抽出して使う非同梱運用とする。
  Canvas/WebGL による UI 表示は M7 HUD 方針 ([GUI-10] #10, `tools/gui/`) に合流させ、Fresh Air 専用の UI 実装系は作らない。
- **理由**: UI/Skia はコアの大半で、DSP (Filter/Compressor/Gain の合成) とは別 vtable・別経路のため分離できる。
  素材の非同梱は `docs/LEGAL.md` §6 の緩和策 1 (再配布物にバイナリを含めない) と整合する。
  根拠の実測値は `tools/targets/freshair/REPORT.md` §1・§2・§6 B6・§7 FA-6。
- **影響**: lift 作業 (`tools/targets/freshair/lift2` 等) は GUI/エディタ層を対象にしない。UI 素材の抽出・配置の
  具体実装は HUD 側 (#10) の範囲。法的な可否の結論は含まない (Slate/Audiotonix ToS の論点は `docs/LEGAL.md` §4.3)。

## D8 — FreeType 2.7 は wasm32 (FORCE_INT64 + ftgrays_lp64.patch) を本採用、wasm64 は退避路

- **状態**: 採用 (2026-10-13, issue #145 [T-SH-01])
- **決定**: FL 同梱 FreeType 2.7 の wasm 再ビルドは **wasm32 + `FT_CONFIG_OPTION_FORCE_INT64` + `oss/freetype/ftgrays_lp64.patch` (2 行)** を既定とする。
  wasm64 (無改変) は退避路として `oss/freetype/build.sh` で常時 native との一致を確認する。素の wasm32 (patch 無し) は使わない。
- **理由**: メモリモデルが wasm32 + LVA 既定 (`tools/runtime/DESIGN.md` D1) で、wasm64 は Memory 個数上限が半分になる。
  wasm32 + patch は native と bit 一致する。FreeType 側に 4GiB 超の要求は無い。
  実測は `tools/shared/REPORT.md` §3.1。
- **影響**: 退避トリガは RT D1 と同じ (wasm64 へ切替える時は FreeType も無改変の wasm64 ビルドを使う)。
  win freetype.dll は別 version のため、この決定は mac 2.7 の再ビルドにのみ適用する (version は未特定)。

## D9 — 大物 (>24MiB) wasm は事前非圧縮 part + `chunked.mjs` で配信 (br 事前圧縮 part は採らない)

- **状態**: 採用 (2026-10-13, issue #952 [PERF-P13])
- **決定**: 25MiB を超える wasm は `deploy/scripts/05-stage.mjs` が 16MiB の**事前非圧縮 part** + `index.json` に分割し、
  クライアントは `deploy/client/chunked.mjs` で連結 ReadableStream にして `WebAssembly.compileStreaming` に渡す。
  `src/runtime/loader_boot.ts` `fetchCompile` は URL が `*.parts/index.json` のとき、この経路に分岐する。
- **比較した方式**: (a) part ごとの brotli 事前圧縮 + JS デコード、(b) 事前非圧縮 part (採用)、(c) 単一 URL を Range で取得。
- **理由**: (a) は Chrome 154 の `DecompressionStream` が brotli/zstd 非対応のため JS brotli デコーダが必要になり、
  展開が compile 前の律速になる。Static Assets は Range 非対応 (200 全体のみ) のため (c) は使えない。
  (b) は実エッジで 314MB・19 part の連結 compileStreaming を実証済み (`deploy/REPORT.md`)。
  part は sha256 検証 + 順序保証 + 背圧を持つ。帯域節約の利得は br の 36% 程度 (`tools/perf/REPORT.md` §10) で、
  大物を JS 展開する CPU コストと引き替えになるため採らない。
- **影響**: 大物の wire サイズは非圧縮のまま。帯域が律速の回線では不利になる (実測は `tools/perf/results/chunked.json`)。
  `cacheapi` モードは単一 URL 前提のため descriptor 経路では使わず、HTTP キャッシュに任せる。
  R2 再移行時 (D1 の退避路) に part 単位の br を再検討する。

## D10 — 実 OTT の Chrome Memory 本数上限 (124〜125) への対応: 同一 Memory への処理オブジェクト畳み込み

- **状態**: 採用 (2026-10-13, issue #990 [PERF-P15])
- **決定**: plugin 数が 124 を超える構成は、plugin ごとに Memory を 1 本ずつ持つ方式 (PERF-P8 の plugin 別 instance) を拡張せず、**1 instance (Memory 1 本) の中に処理オブジェクトを畳み込む**。`OBJ`・入出力・buffer を obj ごとに別 VA に置く。
- **比較した方式**: (a) 同一 Memory への畳み込み (採用)、(b) Worker を分けて Memory 上限を Worker ごとに持つ、(c) 低位 base・小 Memory 化 (#91)。
- **理由**: (b) は Chrome 154 の上限が renderer プロセス単位で、Worker 分割では合計本数が 124〜253 とばらつき、N=130 を確実に通せない (`tools/perf/REPORT_P15.md` §1)。(c) は #91 の完了が前提で本 issue 単独では成立しない。(a) は Chrome Dedicated Worker で M=130 を Memory 1 本に畳み、instantiate 失敗なし・全 obj の署名が既知値と一致 (同 §3)。定常コストは obj 数に依らず平坦 (M=1 と M=130 で +1.5% 以内)。
- **影響**: 同一 binary の複数 state に限って検証済み。異なる plugin を同居させる場合の VA 衝突・共有 static の扱いは未検証 (REPORT_P15 §4、子 issue で扱う)。setup は M=130 で約 0.8〜1.0 s かかるため、起動時の一括 pre-warm が前提。

## D11 — release guard の deny-list は CI に置かず、テストは `--skip-release-guard` で fixture を stage する

- **状態**: 採用 (2026-10-14, issue #1151 [PERF-P17])
- **決定**: `tools/legal/release-guard/work/denylist` (素材由来の指紋) は gitignore で commit しない。CI の既定 job は deny-list を持たず、release guard は fail-closed (exit 4) のまま維持する。`deploy/client/chunked.test.mjs` の fixture stage (`05-stage.mjs`) だけ `--skip-release-guard` を明示する。fixture は `tools/e2e/fixtures/add.wasm` + 合成 padding + `index.html` のみで、FL/プラグイン由来バイトを含まないため、バイパスの前提が成立する。
- **比較した方式**: (a) CI で R2 素材 (`fl-win64`) から deny-list を毎回生成 (約 34 s + 素材取得が必要で、テスト 1 本のために素材を要求する)、(b) テストで `--skip-release-guard` (採用)、(c) deny-list を commit (素材由来の指紋を repo に置くことになるため不可)。
- **理由**: (a) は素材取得に依存し、素材の無い run でテストが落ちる。(b) は fixture が素材由来でないことを前提に、テストに限ってゲートを外す。本番 stage (`deploy.sh`・`20-worker --phase release`) は従来どおり `--skip-release-guard` を渡さない。
- **影響**: 本番 stage でこのフラグを使うと LGL-2 のゲートを通過するため、`deploy.sh` の呼び出し元はフラグを付けない。テストの fixture を素材由来に差し替える場合は、この決定を見直す。

## D12 — ldfix の修復前 wasm / 修復後 wasm の作り方 (fail-closed gate は弱めない)

- **状態**: 採用 (2026-10-14, issue #1290 [LD-43])
- **決定**: 修復前 wasm は、`M11_LDFIX=0` で作った IR (`ir_conditions.json` の `ldfix=disabled`) を既存の明示 opt-in `M11_ALLOW_LDFIX_DISABLED=1` (#1165) だけで build する。修復後 wasm は、修復前 IR に `ldfix/ldfix.py --pe` (m11_gen_ir2.sh と同じ正規 pass) を適用し、`ldfix=applied` を記録して `--bind` で指紋を更新してから既定 gate で build する。手で作った overlay IR (`--passes f3c` の出力) は build に渡さない。
- **比較した方式**: (a) gate を外す (`M11_ALLOW_LDFIX_DISABLED` を既定化・指紋検査の省略) — fail-closed を弱めるため不採用。(b) 修復後 IR を `--passes f3c` で重ねた overlay を build する — 正規 pass を経ず指紋 (`ir_sha256`) が一致しないため gate で拒否される。(c) e2e を修復後 wasm 単独に縮める — 修復前比較 (survey 突合・dyn の before 値) が取れなくなるため不採用。(d) 採用: 既存 opt-in と正規 pass のみを使う。
- **理由**: opt-in は `ldfix=disabled` の記録を残すため、測定時の IR 条件が REPORT と成果物から読める。正規 pass 経由の IR は既定 gate をそのまま通る。`ldfix_img.py` (PE 無し) の出力は正規 pass の代用にならないため、修復後 wasm の入力に使わない。
- **影響**: `ldfix_509_e2e.sh` の 6/7 は fl-win64 の PE (`FL_WIN64_DIR`) が要る (従来の「PE 無し」の前提を外す)。他の e2e (`ldfix_e2e.sh` 等) の PE 要件は変わらない。

## D13 — liftdiff の既定 batch 状態は units のまま据え置く (hybrid への切替は根拠待ち)

- **状態**: 保留 (2026-10-13, issue #1248 [LD-42]。子 issue #1464 [LD-50] で判断)
- **決定**: `liftdiff_e2e.sh` [4/4] の既定 batch 状態は `units` のまま変えない。InitTable 充足の `hybrid` は `--state` で明示したときだけ使う。
- **比較した方式**: (a) 既定を hybrid に切替 (InitUnits が実際に走り、空振り一致が 0 件になる)、(b) units のまま据え置き (採用・保留)。
- **理由**: hybrid にすると sample:800 の判定が変わる (件数は `tools/liftdiff/REPORT_APPENDIX_LD42.md` §1・§3)。どちらが正しいかは関数ごとの差分根拠が無いと決まらないため、根拠無しに基準値を動かさない。units の InitUnits 空振り一致は `check_initunits.py` で検出済み (LD-25) で、この検出は hybrid 側でのみ成立する。
- **影響**: 既定 batch の一致数は「InitUnits が呼ばれない状態での一致」である (件数の測定値は `tools/liftdiff/REPORT_APPENDIX_LD42.md` §1)。この数値を外部へ「実行初期化済みの一致」として出さない。

## D14 — スカラー FMA3 (vfmadd/vfmsub/vfnmadd/vfnmsub の sd 形) は ヘッダの式 + IR 引数順で実装する

- **状態**: 採用 (2026-10-14, issue #1408 [PLG-F3-8])
- **決定**: `vf[n]m{add,sub}{132,213,231}sd` の 3 引数形を `m11_simd2.py` で `msimd11_core.h` の `_[f|fn]m{a|s}{132|213|231}sd(a, b, c)` へ委譲する。第 3 引数は i64 なら `asd(c)`、i128 なら `lane0_d(c)` で double に変換する。`a` = dst (第 1 引数)。
- **比較した方式**: (a) ヘッダの式をそのまま使う (採用)、(b) IR 側の引数順を並べ替えて 132 形に統一する。
- **根拠**: 実機 FMA3 との照合で 12 形すべての値が一致。ただし fnm/fnms の 6 形は ±0 と NaN の符号が実機と異なる。 検証手順と数値は `tools/plugins/dynamics/REPORT.md` §4 を参照。
- **影響**: 両 engine の FMA 残件は unimpl から消えた (件数は REPORT §4)。 符号差は未解決。 movntps・vmovsd store・ucomis/comis の flag は未対応で、子 issue に分割した。

## D15 — VEX の comis/ucomis (vcomisd / vucomisd / vucomiss) の flag は SSE 形へ委譲せず、IR 側で反映する

- **状態**: 採用 (2026-10-14, issue #1582 [PLG-F3-12])
- **決定**: `__asm_v{,u}comis*` を `m11_simd2.py` の SSE 形 (no-op) へ委譲しない。 flag (CF/ZF/PF) は IR 側で反映する。 反映方式は子 issue [PLG-F3-14] で決める。
- **比較した方式**: (a) VEX 形を SSE 形の `(void)a; (void)b;` へ委譲して `unimpl` から消す (不採用)、(b) 既存 `lift/passes/ir6_pass.py` ([P1]) を lift 鎖に入れる (単独では不足。 19252 の comis 76 箇所中 insert 3 箇所のみ)、(c) `icall_rewrite.py` の comis 経路 (stub + sahf) を plugins 側に移植する (未評価)。
- **理由**: (a) は flag を反映しないまま stub を消すため、`declares_unimpl` が 0 になっても silent な flag 欠落が検出できなくなる。 `lift/passes/m11_simd2.py` の既存コメントも同じ方針 (「委譲せず stub のまま残す」)。 実測は `tools/plugins/sampler/REPORT_APPENDIX_1582.md` §7b。
- **影響**: 19252 / 19048 の unimpl に `vcomisd` / `vucomisd` / `vucomiss` が残る。 これを消すには flag 反映の実装が要るため、子 issue に分割した。

## D16 — 残 helper `__asm_vmovsd` (store 形) は宛先を定数で埋めず、spill 領域の写像を上流で直す

- **状態**: 採用 (2026-10-14, issue #1778 [PLG-F3-15])
- **決定**: `__asm_vmovsd(i64,i128)` の宛先を `xor i64 0, 0` のまま store 化しない。 宛先は RetDec の spill 領域の写像 (store の無い `alloca`) と、B1 (`ir5_patch.py` `patch_uninit_alloca`) の 0 埋めを直して復元する。 この修正は子 issue #2017 ([PLG-F3-18]) で行う。
- **比較した方式**: (a) `vmovsd` を store 化する (宛先 0 への誤 store で不採用)、(b) B1 の 0 埋めを止める (共有 lift 鎖の全 plugin に影響するため範囲外)、(c) 委譲や abort で unimpl から消す (silent miscompile を隠すため不採用)。
- **理由**: 機械語は `[rsp+0x20]` への spill で、宛先は定数 0 ではない。 宛先 0 のまま store を作ると誤った番地へ書く。 同じ宛先値は分岐・演算にも使われるため、stub で隠すと誤りが検出できなくなる。 実測は `tools/plugins/dynamics/REPORT_APPENDIX.md` §E。
- **影響**: 19252 の unimpl に `vmovsd` store が残る (5 件のうち 1 件)。 `emcc -c` は rc 0 のまま。 正しさは未確認。
