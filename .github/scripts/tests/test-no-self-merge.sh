#!/bin/bash
# test-no-self-merge.sh — 実装者が自分の PR を merge する指示 (Auto Merge を含む) が prompt / 文書に戻っていないことを検査する (#2600)。
# implementer.md 規範 9 が `gh pr merge --auto --merge` を指示していた間、実装 App が PR の作成から数十秒で自己 merge し、
# 独立した review を迂回していた。規範 9 は「実装者は自分の PR を merge しない」の禁止だけを書き、merge の指示は
# どこにも置かない。旧版の文面と、指示を足した改変版 (ネガティブコントロール) が落ちることも確かめる。
# 実行: bash .github/scripts/tests/test-no-self-merge.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
IMPL="$ROOT/.github/prompts/implementer.md"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0 fail=0
ok() { pass=$((pass + 1)); printf 'ok   %s\n' "$1"; }
ng() { fail=$((fail + 1)); printf 'FAIL %s\n' "$1"; }
expect() { if [ "$2" = 0 ]; then ok "$1"; else ng "$1"; fi; }

# 規範 9 (行頭 "9. " から次の "N. " の直前まで)
rule9() { awk '/^9\. /{f=1; print; next} /^[0-9]+\. /{f=0} f' "$1"; }
# 規範 9 の外側
outside9() { awk '/^9\. /{f=1; next} /^[0-9]+\. /{f=0} !f' "$1"; }

# check_prompt <implementer.md 相当のファイル>: 0 = 合格。違反は stderr に出す
check_prompt() {
  local f="$1" rc=0 block
  block="$(rule9 "$f")"
  if [ -z "$block" ]; then
    echo "規範 9 が無い" >&2
    return 1
  fi
  grep -qF '自分の PR を merge しない' <<< "$block" || { echo "規範 9 に『自分の PR を merge しない』が無い" >&2; rc=1; }
  grep -qF 'してはならない' <<< "$block" || { echo "規範 9 に禁止の文 (してはならない) が無い" >&2; rc=1; }
  local k
  for k in 'gh pr merge' '--auto' 'pulls/N/merge' 'enablePullRequestAutoMerge'; do
    grep -qF -- "$k" <<< "$block" || { echo "規範 9 の禁止対象に $k が無い" >&2; rc=1; }
  done
  # 規範 9 の外では、merge の手段にも Auto Merge にも触れない (指示を足せない)
  if outside9 "$f" | grep -n -i -E 'gh pr merge|pulls/[^ ]*/merge|enablePullRequestAutoMerge|auto[ -]?merge' >&2; then
    echo "規範 9 の外に merge / Auto Merge の記述がある" >&2
    rc=1
  fi
  # どこにも、flag 付きの gh pr merge と『有効化する』の指示が無い
  if grep -n -E 'gh pr merge +(-|[0-9<])|で有効化する|--auto --merge' "$f" >&2; then
    echo "gh pr merge の実行指示 / Auto Merge の有効化指示がある" >&2
    rc=1
  fi
  return "$rc"
}

# 1. 現行の implementer.md は合格する
check_prompt "$IMPL" 2> "$TMP/err"
expect "implementer.md: 実装者は自分の PR を merge しない (禁止だけを書き、merge の指示が無い)" $?
[ -s "$TMP/err" ] && sed 's/^/  | /' "$TMP/err"

# 2. ネガティブコントロール: 旧版の規範 9 (8e4b343d で追加) は落ちる
cat > "$TMP/old.md" <<'EOF'
8. **ブランチ/PR**: 作業は `N-<slug>` ブランチで行い、push 後 `gh pr create` (`--base main`)。
9. **マージ方法**: このリポジトリは merge commit のみ許可されている
   (`allow_squash_merge: false` / `allow_rebase_merge: false`)。Auto Merge は
   `gh pr merge --auto --merge` で有効化する。`--squash` / `--rebase` は必ず失敗する。
10. **sleep による 10 秒以上の待機は禁止**。
EOF
check_prompt "$TMP/old.md" 2> /dev/null
[ $? -ne 0 ]
expect "ネガコン: 旧版の規範 9 (gh pr merge --auto --merge で有効化する) は検出される" $?

# 3. ネガティブコントロール: 現行版に merge / Auto Merge の指示を足した改変は落ちる
mutant() { # mutant <name> <追記する行>  現行版の末尾に 1 行足した版を作る
  cp "$IMPL" "$TMP/$1.md"
  printf '%s\n' "$2" >> "$TMP/$1.md"
}
mutant m-cmd 'PR を出したら `gh pr merge --auto --merge` を実行する。'
check_prompt "$TMP/m-cmd.md" 2> /dev/null
[ $? -ne 0 ]
expect "ネガコン: 規範 9 の外に gh pr merge --auto --merge を足した改変は検出される" $?

mutant m-auto 'CI が緑なら Auto Merge を有効にしてよい。'
check_prompt "$TMP/m-auto.md" 2> /dev/null
[ $? -ne 0 ]
expect "ネガコン: Auto Merge を許す一文を足した改変は検出される" $?

mutant m-rest 'REST の `pulls/N/merge` で merge してよい。'
check_prompt "$TMP/m-rest.md" 2> /dev/null
[ $? -ne 0 ]
expect "ネガコン: REST の pulls/N/merge を許す一文を足した改変は検出される" $?

# 4. ネガティブコントロール: 規範 9 から禁止の文を消した改変・規範 9 を消した改変は落ちる
sed 's/自分の PR を merge しない/自分の PR を merge してよい/' "$IMPL" > "$TMP/m-allow.md"
check_prompt "$TMP/m-allow.md" 2> /dev/null
[ $? -ne 0 ]
expect "ネガコン: 『merge しない』を『merge してよい』に変えた改変は検出される" $?

awk '/^9\. /{f=1; next} /^[0-9]+\. /{f=0} !f' "$IMPL" > "$TMP/m-del.md"
check_prompt "$TMP/m-del.md" 2> /dev/null
[ $? -ne 0 ]
expect "ネガコン: 規範 9 を丸ごと消した改変は検出される (禁止が消える)" $?

# 5. 文書: README / WORKFLOW / reviewer に、実装者の Auto Merge 有効化を指示する旧い記述が残っていない
bad=0
for f in .github/README.md docs/WORKFLOW.md .github/prompts/reviewer.md .github/prompts/pm.md; do
  hits="$(grep -n -E 'gh pr merge +--auto|--auto --merge|Auto Merge 有効化' "$ROOT/$f" || true)"
  if [ -n "$hits" ]; then
    printf '%s\n' "$hits" | sed "s#^#  | $f:#"
    bad=1
  fi
done
expect "文書: README / WORKFLOW / reviewer / pm に Auto Merge を有効化する旧い記述が無い" "$bad"

# 6. 文書: README と WORKFLOW が『実装者は自分の PR を merge しない』を明記している
miss=0
for f in .github/README.md docs/WORKFLOW.md; do
  grep -qF '自分の PR を merge しない' "$ROOT/$f" || { echo "  | $f に『自分の PR を merge しない』が無い"; miss=1; }
done
expect "文書: README と WORKFLOW が『実装者は自分の PR を merge しない』を明記している" "$miss"

# 7. 検収の prompt: approve できない立場 (reviewer token 欠落) で approve / merge させる文が無い。旧版の文は検出される
SELF_MERGE_RE='コメント \+ マージ|マージ \(許可されていれば\)|merge directly|if the project allows|同一 App identity の場合は approve をスキップし'
bad=0
for f in .github/prompts/reviewer.md .github/scripts/assemble-reviewer-prompt.sh; do
  hits="$(grep -n -E "$SELF_MERGE_RE" "$ROOT/$f" || true)"
  if [ -n "$hits" ]; then
    printf '%s\n' "$hits" | sed "s#^#  | $f:#"
    bad=1
  fi
done
expect "検収 prompt: approve できない立場で approve / merge させる文が無い (reviewer.md・assemble-reviewer-prompt.sh)" "$bad"
printf '%s\n' '- 自分が approve できない立場 (同一 App identity) の場合は approve をスキップし、' '  コメント + マージ (許可されていれば) を行う。' > "$TMP/old-reviewer.md"
grep -q -E "$SELF_MERGE_RE" "$TMP/old-reviewer.md"
expect "ネガコン: 同一 identity で『コメント + マージ』を行う旧版の注意は検出される" $?

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
