# CI-197 (#4721): [AREA-n] 題名の重複を起票時に検出する

親 #2319。`[AREA-n]` の番号重複を、起票時に bot コメントで知らせる。検出のみ (題名は変えない・ラベルは作らない)。

## 構成

- `.github/scripts/check-title-collision.sh <N>`: issue N の題名の `[AREA-n]` (n の英小文字サフィックスを含む完全一致) と同じタグを持つ **番号の小さい** issue を `#番号 題名` で出す。重複が無ければ何も出さない。取得失敗は終了 2。
- `.github/workflows/title-collision.yaml`: `issues: opened` で上記を実行し、重複があれば `gh issue comment` で知らせる。取得失敗は warning のみ (起票を止めない)。
- `.github/scripts/tests/test-title-collision.sh`: fake gh で 7 件 (検出・誤検知 0・非数値接頭辞 `[HB-H2]` の対象外・サフィックス違い・タグ無し・取得失敗 exit 2・使い方 exit 2)。`scripts-test.yaml` が glob で拾う。

## workflow の追加 (未配置・要人手)

GitHub App の installation token には `workflows` 権限が無く、`.github/workflows/title-collision.yaml` の push が
`refusing to allow a GitHub App to create or update workflow` で拒否された。受入の「実 workflow で検出」を満たすため、
次の内容を `.github/workflows/title-collision.yaml` として人が置く (検出スクリプトは本 PR に含む):

```yaml
name: Title collision
on:
  issues:
    types: [opened]
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Detect [AREA-n] collision
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
          OC_REPO: ${{ github.repository }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
        run: |
          set -uo pipefail
          status=0
          dups="$(bash .github/scripts/check-title-collision.sh "$ISSUE_NUMBER")" || status=$?
          if [ "$status" -ne 0 ]; then
            echo "::warning::title collision check could not run for #$ISSUE_NUMBER (exit $status)"
            exit 0
          fi
          [ -n "$dups" ] || { echo "no [AREA-n] collision for #$ISSUE_NUMBER"; exit 0; }
          {
            echo "この issue の題名の \`[AREA-n]\` が、先行の issue と重複しています。起票者は番号を振り直してください (自動では変えません)。"
            echo ""
            echo "$dups" | sed 's/^/- /'
            echo ""
            echo "次の番号は \`docs/WORKFLOW.md\` §3 ① の確認コマンドで求めてください。"
          } > "$RUNNER_TEMP/collision.md"
          gh issue comment "$ISSUE_NUMBER" --repo "$OC_REPO" --body-file "$RUNNER_TEMP/collision.md"
          echo "::warning::title collision for #$ISSUE_NUMBER: $(echo "$dups" | tr '\n' ' ')"
```

## 再現

```
bash .github/scripts/tests/test-title-collision.sh          # 7 件 PASS, exit 0
OC_REPO=signature-studio/signature-studio-dev bash .github/scripts/check-title-collision.sh 2417
# -> #2416 [CI-84] ...
```

## 実測 (実リポジトリの題名 2400 件・fake gh で `gh issue list` の内容を再現)

- 実在の重複 8 組 (CI-10・CI-12・CI-20・CI-84・CI-8・CI-9・DOCS-5・FA-2c)。後発の issue を検査すると先行を報告する:
  - `#2417` -> `#2416` (CI-84)
  - `#439` -> `#437` (DOCS-5)
  - `#646` -> `#637`・`#338` (CI-12、2 件とも報告)
- 先行の無い issue (`#2416`・`#3595` 等) は何も出さない。
- 誤検知 0 の確認: タグ付き 1564 件のうち 1/40 の標本 39 件で、期待値 (同タグの先行 issue を数える awk) と完全一致 (期待 1 件 = 出力 1 件)。全 1564 件は 1 件 0.9 秒 (fake gh の実測) で回すと run の上限を超えたため未実施。
- 検査時間の実測: fake gh で 0.90 秒 (`time` の real、issue 646)。実 gh で 1 件 18.5 秒 (`check-title-collision.sh 4658`、一覧 2400 件の取得を含む)。

## 未実施・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.github/workflows/title-collision.yaml` の配置 (App に workflows 権限が無く push 拒否) と、実 workflow が 1 件の起票に反応することの確認 | 配置されるまで「起票時に検出して知らせる」は動かない。検出スクリプトは fake gh と実データで確認済み | 人間 (workflows 権限を持つ者) が上記の yaml を置く。受入の未達分として #4721 に残す |
| 全 1564 件の全件突合 | 標本 39 件で一致。全件は未実施 | 本 PR で対応しない (時間制限) |
