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
- **決定**: REPORT 冒頭の preflight 読了証跡 (ハッシュ 1 行) と、外部 `analysis/SUBAGENT_RULES.md` の
  ハッシュ運用は**廃止**。ルールの正本は repo 内 `docs/WORKFLOW.md` に一本化した。
- **理由**: rules を更新するたびに全 REPORT (15 箇所以上) の証跡行が陳腐化し、全面修正の労力が
  肥大化していた。原本 repo 外・repo に存在しないため新しい参加者が読めない問題もあった。
- **影響**: 各 `REPORT.md` の証跡行は削除済み。検証手順は `docs/WORKFLOW.md` を参照。

