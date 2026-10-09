#!/usr/bin/awk -f
# RetDec decompiler 出力 (.c) から、指定関数の定義ブロックだけを抽出する。
# 使い方: awk -v func=main -f extract_main.awk retdec_output.c > main_block.c#
# RetDec 出力フォーマットの前提:
#   - 関数の定義行はカラム 0 から "<type> func(...) {" (1 行、セミコロンで終わらない)。
#     プロトタイプ宣言行は ";" で終わるため、セミコロンは除外条件で弾く。
#   - 関数定義のシグネチャが複数行に分かれる出力形式には対応しない
#     (現行 RetDec v5.0 のフォーマット前提)。
#   - 関数ブロックの終端は必ず唯一の "}" がカラム 0 の単独行で現れる。
#   - 見つかった最初の一致のみを出力する。見つからなければ stderr にエラーを出し exit 1。

BEGIN {
    found = 0; in_func = 0
    # 例: "int main(int argc, char ** argv) {" / "int64_t main(...) {"
    re_start = "(^|[ \\t])" func "\\([^;]*\\).*\\{[ \\t]*$"
}

!in_func && $0 ~ re_start {
    in_func = 1; found = 1
    print $0
    next
}

in_func && /^}[ \t]*$/ {
    in_func = 0
    print $0
    exit 0   # 最初の一致のみで終了
}

in_func { print $0 }

END {
    if (!found) {
        print "extract_main.awk: function '" func "' not found" > "/dev/stderr"
        exit 1
    }
}
