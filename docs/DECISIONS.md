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
- **改訂 (2026-10-14, #2600)**: 上の「PM がマージ」は改める。merge の担い手は検収 (approve と同じ run)。PM は merge しない。本文は 2026-10-12 の記録として残す。

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

- **状態**: 採用 (2026-10-13 保留、2026-10-15 issue #1464 [LD-50] で据え置きを確定。hybrid への切替は `tools/liftdiff/REPORT_APPENDIX_LD42.md` §8.2 の条件が揃うまで行わない)
- **決定**: `liftdiff_e2e.sh` [4/4] の既定 batch 状態は `units` のまま変えない。InitTable 充足の `hybrid` は `--state` で明示したときだけ使う。
- **比較した方式**: (a) 既定を hybrid に切替 (InitUnits が実際に走り、空振り一致が 0 件になる)、(b) units のまま据え置き (採用)。(a) は不採用: hybrid の InitUnits は native 側が 11/11 で segv し (子 #3349 LD-153)、TLS の実経路 (flag=1) の充足も未確認 (同)、件数が負荷で揺れる (子 #3350 LD-154)。
- **理由**: hybrid にすると sample:800 の判定が変わる (件数は `tools/liftdiff/REPORT_APPENDIX_LD42.md` §1・§3)。どちらが正しいかは関数ごとの差分根拠が無いと決まらないため、根拠無しに基準値を動かさない。units の InitUnits 空振り一致は `check_initunits.py` で検出済み (LD-25) で、この検出は hybrid 側でのみ成立する。
- **影響**: 既定 batch の一致数は「InitUnits が呼ばれない状態での一致」である (件数の測定値は `tools/liftdiff/REPORT_APPENDIX_LD42.md` §1)。この数値を外部へ「実行初期化済みの一致」として出さない。
- **追記 (2026-10-15, LD-50)**: 遷移 68 件の表 (`REPORT_APPENDIX_LD42.md` §6) で、units 一致 → hybrid 差分の 25 件は全件の主因が callee_divergence で、どちらが誤りかを関数ごとに決められなかった。根拠は §6・§7 (TLS)・§8 (件数の揺れ)。

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
- **実装 (2026-10-14, #2017)**: 宛先の読み戻しを B1 の前に値の転送へ置換する (`ir5_patch.py` `forward_vmovsd_store`)。 19252 の unimpl から `vmovsd` store は消えた。 分岐値は entry の xmm0 を B1 が 0 にする入力モデルに依存し、正しさは未確認のまま。 測定は `tools/plugins/dynamics/REPORT_APPENDIX.md` §H。

## D17 — `movntps` (非テンポラル store) は既存の SSE store 復元 (`lower_asm_store`) に含め、宛先は IR 側から復元する

- **状態**: 採用 (2026-10-14, issue #1581 [PLG-F3-11])
- **決定**: `__asm_movntps(i128,i128)` の呼び出しは `ir5_patch.py` の `lower_asm_store` で `store i128` に復元する (`movups`/`movaps`/`movdqa` と同じ扱い)。 helper 側 (`m11_simd2.py` の `gen_body`) は void 形を movups 系と同じ分岐に入れる。
- **比較した方式**: (a) 宛先を 0 で埋める (誤った番地への store になるため不採用)、(b) helper 側だけで no-op にして呼び出しを残す (store が無音で消えるため不採用)。
- **理由**: 第 1 引数は `%75` 等から `load i128` した値で、そのポインタ (`inttoptr`) が IR に残っている。 issue 本文の「宛先は IR 側に無い」は誤りだった。 `ir5_patch` 後は `movntps` の呼び出しが `e.norm0.ll` 8 件 → `e.lift.ll` 0 件 (19048)。 宣言だけが残り、helper 側の分岐に入る。
- **影響**: 19048・19252 の unimpl から `movntps` が消えた (実測は `tools/plugins/dynamics/REPORT_APPENDIX.md` §F2)。 共有鎖は `lift/lift_ranges.sh` 経由の plugin 群 (reverb_delay / hostx / modulation / synth / p0c / dynamics 等) で、`ir5_patch.py` の変更が効く。 liftlib (OTT) は `tools/liftlib/liftlib/passes/base.py` の独自 `lower_asm_store` を使い `ir5_patch.py` を import しないため、今回の変更は効かない (`ott_lift.ll` では `__asm_movntps` の呼出が 8 件 (すべて `function_1801a30d0`) 残る。宣言は 1 行。これは既存どおり)。 plugin 群の回帰は §F2 の before/after で測定した。

## D18 — IPP の A11 系・NaN 入力・VectorSlope の「規格内の高精度実装による bit 不一致」は許容する

- **状態**: 採用 (2026-10-14, issue #142 [IPP-Q1]。#135 検収時の暫定決定を PM が確定)
- **決定**: 自前 IPP 実装 (`tools/ipp`、親 #38) が実 Intel IPP と bit 一致しないことを、次の 3 群に限って許容する。(1) `ippsSqrt/Exp/Ln…_A11` 系 (実 IPP の A11 系は低精度仕様の関数群。精度の実測は `tools/ipp/REPORT.md`)、(2) NaN 入力の挙動 (`Convert_32f32s_Sfs`・`Threshold_GT/LT`、NaN の仮数ペイロード)、(3) `VectorSlope` (実 IPP はブロック累積で真値から漂う)。許容リストはこの 3 群で閉じる。リスト外の関数が実 IPP と bit 不一致になったら不具合として扱い、リストへの追加には新しい ADR を要する。
- **比較した方式**: (a) 許容 (採用)、(b) 不許容: 特定の ISA 経路 (例 AVX-512) の出力を係数ごと再現する。
- **理由**: 実 IPP 自身が CPU 経路で出力を変える (AVX-512 対 AVX2 で A11 系の出力が経路間で異なる。NaN 入力の Convert/Threshold も経路間で異なる)。ユーザ環境ごとに本物の FL の出力も bit 単位では異なり、bit-exact は定義できない。arm64 Mac 版 FL 自身も Accelerate の高精度実装を使う。決定的な関数は実 IPP と bit 一致済み。(b) は A11 近似多項式の逆解析が要り、工数が大きい割に、どの ISA 経路を正とするかの根拠が無い。経路ごとの差の実測と bit 一致関数の一覧は `tools/ipp/REPORT.md` §4・§8 が正本。
- **影響**: 許容群の関数は bit 一致ではなく、真値に対する誤差が実 IPP の精度仕様以下であることで判定し、NaN の仮数ペイロードは比較から外す。bit 一致の関数群は回帰ゲートとして維持する。退路は (b) (不許容に戻す場合は ISA 経路を 1 つ選んで係数を再現する)。影響チケットは #38 配下の [IPP-2] ipp-fill。

## D19 — 将来 mac 版 FLEngine を lift する場合の基準は x86_64 スライス

- **状態**: 採用 (2026-10-14, issue #143 [IPP-Q2]。#135 検収時の暫定方針を PM が確定)
- **決定**: 現計画の lift 対象は win64 `FLEngine_x64.dll` のまま。将来 mac 版 (FPC 製、universal2) を lift する場合は **x86_64 スライスを基準**にし、arm64 スライスは lift しない。mac 版 lift の優先度は低いままで、着手するかどうかは別途 PM が判断する。
- **比較した方式**: (a) x86_64 (採用)、(b) arm64。
- **理由**: x86_64 スライスは本物の Intel IPP をロードし、既存の lift pass 資産 (x64c / liftlib / flelift) が使える見込みで win64 との差分が小さい (mac 版での再利用は未検証)。arm64 は FL 自作の別 IPP 実装 (Accelerate 依存) をロードし、Accelerate (vDSP/vImage/vForce) 呼出が残るため wasm では結局 C での再実装が要る。lift 器の RetDec 5.0 は arm64 を名目上サポートするだけで未検証。IPP の使用 API 数は 3 基準でほぼ同一なので、自前 IPP 実装 (#38) は基準によらず共通で、本決定は #38 に影響しない。使用 API 数の実測は `tools/ipp/REPORT.md` §2・§3 が正本。
- **影響**: mac を lift する時は、SysV 呼出規約 (rdi, rsi, rdx, rcx, r8, r9 / xmm0-7) 用のブロック版 thunk が別途要る (現 shim は MS x64 規約の `IppBlk`。`tools/ipp/shim/REPORT.md` §7・§9-5)。mac 版は FPC 製なので RTL は FPC RTL (OSS) を扱うことになる (D21)。

## D20 — 第三者の商用・利用制限付き・派生成分 (IPP / GPC / libkio / élastique / REX) は配布 tier で扱いを分ける

- **状態**: 採用 (2026-10-14, issue #163 [T-SH-17])。**法的助言ではなく運用方針**。各社条項の事実整理 (`docs/LEGAL.md`) は変えず、`docs/LEGAL.md` §6.0-7 が「未回答」としていた再配布の論点に、運用として答える。#163 の 2026-10-10 コメント「再配布論点は未回答のまま」は、本 ADR で上書きする (再配布の運用方針はこの ADR が正本)。
- **決定**: 成果物を 2 つの tier に分ける。
  1. **公開 tier** (リポジトリ・無認証で到達できる配信物): 自作コードと、upstream から再ビルドした OSS だけを載せる。FL 由来・第三者プロプラ由来のバイト列と派生物 (下の 5 成分を含む) は一切載せない。release guard (D11) の deny-list で機械的に担保する。
  2. **所有者限定 tier** (Cloudflare Access・運用形態 B・`docs/LEGAL.md` §6.0): 成分ごとに次のとおり。

     | 成分 | 扱い |
     |---|---|
     | Intel IPP 本体 (`dsp_ippv2`) | lift しない。API は自前実装に置換する (#38 の既存方針を確定)。実 IPP の DLL はローカルの差分テストのオラクル専用で、どの tier にも載せない |
     | GPC (非商用条項) | 載せない・使わない。自前実装は GPC に依存しない。FL がその経路を呼ぶ機能が現れたら、許諾の緩い OSS 等への置換を個別 issue で扱う |
     | libkio / DirectWaveCtEngine (NI 派生) | 所有者限定 tier でのみ lift する (T-SH-13・既存 PoC を継続)。単体モジュールとして切り出して配らない |
     | élastique (zplane) | 同上。所有者限定 tier でのみ lift する |
     | REX (Reason Studios) | 同上。優先度は低いまま |

     所有者限定 tier の 3 成分 (libkio・élastique・REX) は FL 本体と別の side module としてビルドし、ビルドフラグ 1 つで除外できる構成にする。
- **比較した方式**: (a) tier 分離 (採用)、(b) 5 成分とも全面除外、(c) 利用者の手元の FL からブラウザ内で動的に取得・変換する (運用形態 C。形態の定義は `docs/LEGAL.md` §6.0)、(d) 成分を区別せず載せる。
- **理由**: 運用形態 B (限定公開・非頒布。D2、`docs/LEGAL.md` §6.0) を前提に、保守側へ倒す。公開 tier には第三者成分を入れず、所有者限定 tier でも、改変を禁じる IPP 本体と非商用条項を持つ GPC は載せない。残る 3 成分は FL 自身が内包する部品で、FL の機能 (DirectWave の読込・タイムストレッチ・REX 読込) に必要なため、所有者限定 tier の範囲で lift を許す。(b) は目標の「FL の完全動作」を損ない、(c) は AOT lift と別のアーキテクチャで設計の作り直しが要るため見送る。(d) はリスクが最も大きい。成分の事実は `tools/shared/REPORT.md`。
- **影響**: #163 を close し、#19・#209・#210 を止めていた blocked_by が解ける。release guard の deny-list への 5 成分の追加は、D11 のとおり手元 (CI の外) で PM が行う。各 side module は除外可能にしておくため、退路は (b) で、(c) は将来の選択肢として残る。

## D21 — Delphi RTL の OSS 差替え (b) は採らず、x64c による再 lift (a) だけで進める

- **状態**: 採用 (2026-10-14, issue #441 [M11-N12]。親 #129 は close 済み)
- **決定**: #129 の案 (b) 「OSS から RTL を wasm ビルドして差し替える」は採らない。RTL 帯は案 (a) の別 lifter (x64c) による再 lift だけで進める。(a) は #253 で実施済みで、RTL 帯の残作業は #410 に切り出して close 済み。
- **比較した方式**: (a) x64c で再 lift (採用)、(b-1) Delphi の toolchain と RTL を使って再ビルドする、(b-2) FPC の RTL (OSS) で差し替える。
- **理由**: win64 の FLEngine は Delphi 製で、その RTL (System/SysUtils 等) は Embarcadero の商用製品の一部であり、OSS として再ビルド・再配布できる形では公開されていない [推定: Embarcadero 側の条件は未確認] ため (b-1) は取れない。(b-2) の FPC RTL は文字列・レコード・クラスのレイアウトや呼出規約が Delphi と互換でなく、FL のコードが前提とする挙動に合わせるには実質的な再実装になる。FL 側のコードを変えずに再 lift する方が工数・リスクが小さい (#441 の判断)。OSS の FastMM4 だけを差し替えても、残りの RTL 帯は再 lift が要るため単独の利益が薄い。(a) の実測は `tools/m11/rtl/REPORT.md`。
- **影響**: toolchain (Delphi / FPC) 選定のユーザ判断は不要になった。mac 版 (FPC 3.2.3 製。将来 lift する場合の基準は D19) を lift する時は FPC RTL のソースが OSS として入手できるため、その時点で (b-2) を再評価する (退路)。

## D22 — PLG-X: Razer Chroma・ReWired・FL Studio Mobile ×3 は対象外、ZGameEditor Visualizer は保留 (#29 待ち)

- **状態**: 採用 (2026-10-14, issues #558 [PLG-X-2] / #559 [PLG-X-3] / #560 [PLG-X-4]。親 #210)
- **決定**:
  - **Razer Chroma (19244)・ReWired (24161)**: 選択肢 A。lift しない。
  - **FL Studio Mobile ×3 (Rack FX 18976 / Rack 23605 / Mobile 22444)**: 選択肢 A。lift しない。
  - **ZGameEditor Visualizer (殻 19304 + 19299/19300/19303/19305/19306)**: 選択肢 B。保留する。#29 (PLG-E2) の GL→WebGL の描画経路が動いた後に、「殻 + ZgeNano / ZgeSkelet / ZGEBullet のみ lift + GL→WebGL shim」で再評価する。NDI / Spout / DMX / Hue / OSC は D3 に従って切り落とす。それまで #210 の lift 対象から外す。
  - 対象外とした plugin が FLP に現れたら「未対応プラグイン」として扱い、状態 (チャンク) は保持して素通しにする。
- **比較した方式**: Razer・ReWired・FL Mobile は A (対象外) / B (no-op の殻として lift、または x64c の測定後に再判断) / C (実機能の提供、または RetDec 鎖で lift)。ZGE は A (対象外) / B (保留) / C (ZGE の実行系を WebGL で再実装)。
- **理由**: Razer は周辺機器の LED 制御、ReWired は別プロセスの ReWire ホストとのルーティングで、どちらもブラウザに相手方がおらず、音声処理も無い (demo 出現なし)。FL Mobile は demo 出現が無く、.NET CLR (`mscoree.dll`)・`ws2_32` (D3 の対象外) を持ち、C++ engine の窓 lift が一部 `emcc -c` に失敗する (追跡は #527)。推定工数に対して利用実績がほぼ無く、élastique・DirectWave を内包する点も D20 の所有者限定 tier の範囲を広げるだけになる。ZGE は demo・preset があってユーザに見えるが、閉包が取れず (`plugin_closure` が vtable 入口を 0 件しか見つけない)、描画も #29 待ちのため、保留が可逆で進捗を止めない。値は `tools/plugins/hostx/REPORT.md` §1・§2・§4。
- **影響**: `tools/plugins/hostx/REPORT.md` §0・§1 の区分を確定に合わせた。#558・#560 は close、#559 は #29 に blocked_by を付けて open のまま。#210 の lift 対象は 6 本 (Wrapper×2 / Patcher×2 / MIDI Out / Video Player)。A とした 5 本を再開する場合は新しい ADR を要する (FL Mobile は x64c 経路 (`tools/flelift`) の測定から)。

## D23 — Serum 2 参照音源の content 条件は installer 全展開を正とし、空 dir は variant に残す

- **状態**: 採用 (2026-10-14, issue #2414 [SR-47]。親 #73)
- **決定**: 参照 WAV の content dir の正は installer 全展開 (Tables・Presets あり) とする。`ref_render.sh` の既定と `ref_manifest.json` の主エントリをこの条件に切り替える。専用の空 dir は variant (`content_empty`) として残す。
- **比較した方式**: (a) 空 dir を正のまま据え置く、(b) 全展開を正とし空 dir を variant に残す (採用)、(c) 両条件を正として判定を 2 通り走らせる。
- **理由**: 同じ DLL・MIDI・サンプルレートでも content dir の中身で参照の出力が変わる。wasm 本体が読む content は SR-6 の設計で導入後の installer の全展開 (Tables を含む) であり、SR-46 の factory preset も全展開の `Presets/` からしか取れない。比較条件を wasm 側の読み方に揃えるため (a) は採らず、(c) は判定基準を二重にするため採らない。根拠と実測は `tools/targets/serum2/host/REPORT_SR5.md` §4。
- **影響**: 参照 pin の主エントリが全展開になる。空 dir 条件は `content_empty` として残る。全展開 content を読む wasm 本体への FS shim 接続は未確認で、#2383 の比較時に確認する (`tools/targets/serum2/host/REPORT_SR5.md` §4.4)。

## D24 — `user_answered` の根拠は人 (MEMBER / OWNER / COLLABORATOR) のコメントだけとし、許可 bot のコメントは含めない

- **状態**: 採用 (2026-10-15, issue #2524 [CI-101]。親 #2461。PM 補助 subagent が依頼者の不在中に代理で判断)
- **決定**: `needs-user-input` の issue で依頼者の回答 (`user_answered`) とみなすのは、`author_association` が `MEMBER` / `OWNER` / `COLLABORATOR` の**人**のコメントだけ。許可 bot (実装 App・reviewer App・PM App) のコメントは根拠にしない。PR #2490 の実装 (`infra/pm-worker/src/webhook.ts` の `userAt`) をそのまま凍結し、#2461 の受入 1 の「か許可 bot」は取り下げる。
- **比較した方式**: (a) 人のコメントだけ (採用)、(b) 実装 App・reviewer App のコメントも含める (#2461 受入 1 の原文)、(c) 人と PM App のコメント。
- **理由**: `user_answered` は「依頼者が答えた」ことを表す印で、答えを書けるのは人だけである。`docs/WORKFLOW.md` §12 と `.github/prompts/pm.md` の `user_answered` の節は、どちらも「依頼者 (人間) が返したコメント」と定めており、(b)(c) はこの定義と合わない。(b) は、`needs-user-input` の issue に実装 agent が run 結果を書くたびに `oc-pm` が起き、同じ ref への 24 時間 3 回の上限を使い切って、後から来る本物の回答を処理できなくする。PM agent が bot の文面を回答と読み、`needs-user-input` を外す誤りも起こしうる。(c) の PM App は PM 自身の出力で、自分の出力で自分を起こす経路になる。人の回答は `MEMBER` / `OWNER` / `COLLABORATOR` のアカウントから入るため、bot を足さなくても取りこぼさない。
- **影響**: Worker・文書の変更は無い。#2524 は close。人の回答の検出は従来どおり。許可 bot を含める要件が将来出たら、新しい ADR を起こして #2461 の受入 1 を取り戻す (ループ抑止を超えないことの確認が要る)。

## D25 — 再投入の意図 `focus=K` の K は受入条件の番号 (1〜9) とし、`pm.md` の記述を実装に合わせる

- **状態**: 採用 (2026-10-15, issue #2575 [CI-105]。親 #2475、PR #2511。PM 補助 subagent が代理で判断)
- **決定**: `<!-- oc-pm-intent: relaunch issue=N arts="..." focus=K -->` の `K` は、再投入する issue の**受入条件の番号** (1〜9 の整数・任意) とする。Worker (#2511) は 1〜9 以外を拒否して `counters.intentRejected.focus` に数える。`.github/prompts/pm.md` の「issue 番号」の説明と `focus=778` の例を、受入条件の番号に直す (#2575 の実装 PR)。`infra/pm-worker/` は変えない。
- **比較した方式**: (a) 受入条件の番号 (採用)、(b) issue 番号。
- **理由**: 親 #2475 の受入 1・2 と、`buildLaunchBody` の固定文 (「この issue の受入条件 K だけを実装して PR を出してください。他の条件は子 issue にしてください」) が受入条件の番号で定義している。`pm.md` の「issue 番号」は初稿 (#2326) の書き方で、実装の契約とずれていた。(b) は、`issue=N` が再投入先を既に指すため `focus` に issue 番号を取る意味が重ならず、別 issue を指す場合は存在・親子関係・open の検査 (REST) と固定文の書き換えが増えて、注入の面も広がる。(a) の検査は定数 1〜9 で済む。これは `.github/prompts/pm.md` の境界 U6 (`AGENTS.md`・`docs/WORKFLOW.md` §1・`docs/pm/DIRECTIVES.md` の改訂) に当たらない。規則を変えず、マーカーの引数の説明を実装に合わせる訂正であり、`.github/prompts/` は実装 App が変更できる (前例 #2433)。
- **影響**: 訂正が merge されるまで、PM は `focus` を付けない (付けると検査で拒否される。focus の無い意図は従来どおり動く)。#2511 の merge を待たずに訂正を進められる。

## D26 — 降格 (二重 `/oc` の検出) は「Worker の投稿」と「Worker 以外の PM ログインの投稿」の組だけを数える

- **状態**: 採用 (2026-10-15, PR #2469 [#2340 の降格と shadow の部分実装]。PM 補助 subagent が代理で判断)
- **決定**: #2340 受入条件 4 の「同じ issue に 30 分以内に 2 回目の `/oc`」の「2 回目」は、Worker (PM App) の `/oc` と、Worker 以外の PM ログイン (個人アカウント。VM と手動の投稿) の `/oc` の組 (先後は問わない) に限る。Worker 同士の組と、個人アカウント同士の組は数えない。受入条件の原文は消さず、読みを #2340 のコメントと PR #2469 に追記する。降格で `oc-watchdog`・`oc-pm` の dispatch も止めること、解除が手動 (`POST /demote/reset`) だけであることは、PM 判断 (R7) のまま変えない。
- **比較した方式**: (a) 現実装: PM のログイン同士の組を全て数える、(b) Worker と Worker 以外の組だけを数える (採用)、(c) 降格をやめて shadow だけにする、(d) (a) のまま relaunch の経路だけ除く。
- **理由**: 降格の目的は、Worker が live の間に、別の投稿者 (VM・PM の手動) と同じ issue を二重に起動する事故を止めることである。(a) は、停止報告の後に素材を足して再投入する Worker 自身の正当な `/oc` (この経路に待ち時間は無い) を二重と数え、最初の再投入で自己降格する。降格すると launch と dispatch が止まり、解除は手動だけなので、依頼者の不在 (最大 2 日。`docs/WORKFLOW.md` §11) の間、自律運転が止まる。個人アカウント同士の組は Worker の挙動と無関係で、降格しても原因を止められない。Worker 自身の投稿頻度は別の上限 (#2475 の同じ issue 24 時間 3 回など) で抑える。(c) は受入条件 4 の安全網を失う。(d) は経路ごとの例外が増えて、新しい経路が足されるたびに漏れる。
- **影響**: PR #2469 に、組の条件の変更と、ネガコン (Worker 同士は降格しない、個人同士は降格しない) を含む回帰テストの追加を依頼する。この変更が入る前の版は、`wrangler.toml` が live のままなので再デプロイしない。昇格 (受入条件 2・3、`LIVE=auto`) は未実装のままで、#2340 に残る。

## D27 — main の merge は承認 1 件以上を必須とし (Ruleset `main-require-review`)、通常の merge は reviewer App が行う

- **状態**: 採用 (2026-10-14, issue #2648 [DOCS-27]。親 #2319。Ruleset は API の作成時刻 2026-10-14 16:03Z に適用済み)
- **決定**: main への merge に APPROVED の承認を 1 件以上必須とする GitHub Ruleset `main-require-review` (id `25094342`、merge commit のみ) を正とする。通常の承認と merge は reviewer App が行い、実装 App の PR は承認が無ければ merge されない。PM の緊急 merge は `docs/WORKFLOW.md` §2 の手順による。
- **比較した方式**: (a) Ruleset で承認 1 件以上を必須にする (採用)、(b) 据え置く (実装 agent の Auto Merge が承認要件なしで通る)、(c) 人の承認を必須にする。
- **理由**: (b) では実装 App の merge が承認なしに main へ入っていた (実測は `tools/pm/REPORT_2648.md`)。規約 (`docs/WORKFLOW.md` §2・§3) は「検収 → merge」だが、守らせるのは workflow と prompt の書き方だけで、GitHub 側では強制されていなかった。Ruleset は GitHub が強制するので、prompt や workflow の書き方に依存しない。(c) は、依頼者の不在 (最大 2 日。`docs/WORKFLOW.md` §11) の間に merge を止めるため採らない。元の設計意図は `docs/pm/DIRECTIVES.md` の 596 行付近 (「1人以上のApproveを必要とするRulesetによってマージはブロックされていますが」) である。
- **影響**:
  - reviewer token が取れないと、実装 App は承認できず、PR が承認されないまま止まる見込み (未検証)。
  - 承認の後の Auto Merge の挙動は未検証。
  - 緊急 merge の Admin bypass の設定の有無は変わりうるため、本書には書かない (確認の手順は `docs/WORKFLOW.md` §2)。PM が設定を確かめるまで bypass は使えないものとして書く。
  - ロールバックは `enforcement` を `disabled` にする (`docs/WORKFLOW.md` §2)。
  - 測定値は `tools/pm/REPORT_2648.md` が正本。

## D28 — ia32 の x87 は f80 を持たず、スタック要素を double で lower する (f80→f64)

- **状態**: 採用 (2026-10-14, issue #1099 [PLG-G2-9]。親 #1098 の x87 unsup の扱い)
- **決定**: x64c の ia32 経路の x87 subset は、ST(i) とメモリ経由の値を `double` で持つ (runtime は `tools/ott/rt/ott_x87.h`)。 f80 は `fld`/`fstp` の m80 変換 (10 B ↔ double) でだけ扱う。 subset 外の x87 命令は従来どおり `ott_unsup`。 x64 の生成 C は変えない。
- **比較した方式**: (a) soft-float80 を実装して f80 を持つ、(b) RetDec 路線 (`tools/plugins/p0c/REPORT.md`) で f80 を扱う。 (c) 採用: f80→f64 (f80 を持たない)。
- **理由**: `tools/plugins/p0c/REPORT.md` §3 の実測で、f32 入出力系は差分が無く、f64 出力の差分は 1 ulp 級に限られ、整数の x87 (fild/fistp) は i64 保持で正確だった。 soft-float80 は不要と判断。 subset の差分試験 (native と lowered の比較) の結果は `tools/plugins/slayer_engine_ia32/REPORT_APPENDIX_1099.md` §1・§3 が正本。
- **制限**: (1) 精度制御 PC は模型化しない (f64 固定)。 (2) `fst m32` の丸めは C の cast (nearest) 固定。 (3) `fild m64` で |v|>2^53 は丸まる。 (4) スタック over/underflow と x87 例外は模型化しない (`fwait` は no-op、FSW の例外フラグ・C1 は持たない)。 (5) RC (FCW bits 10-11) は `fist`/`fistp` の丸めにだけ適用する (算術と `fst m32` には効かない)。
- **影響**: ia32 の x87 unsup は減った (残りは超越関数・`frndint`・`fscale`・`fprem` 等。付録 §8・§9)。 f80→f64 の精度差は `docs/DEFECTS.md` の新規類型の候補 (行案は付録 §6)。 `docs/DEFECTS.md` は編集しない (PM 判断 R8。精度差は本 ADR の帰結として付録 §6 に記録)。
