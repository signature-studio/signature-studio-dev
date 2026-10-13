/*
 * pe_image_app.c — GUI-12 (#566) 用: PE の data 実体化 (`__pe_image` + .reloc DIR64 補正) の回帰テスト対象。
 * mingw で PE32+ (--dynamicbase = .reloc 有り) にビルド → RetDec lift → gui_lift_post.py → gcc。
 * 同じソースを host gcc でも直接ビルドし、戻り値が一致することを pe_image_e2e.sh が検査する。
 *
 * data 側に「イメージ内ポインタ」(文字列ポインタ表 / 配列要素へのポインタ / 連結リスト / 関数ポインタ表) を置く。
 * 関数ポインタ表は DIR64 が .text を指す例 (補正してはいけない側; 呼ばない) として置く。
 * 構造体は static 大域 (RetDec が stack 上の構造体フィールド store を落とすため; PROTOCOL §10-1)。
 */
static const char s1[] = "wxyz";
static int arr[4] = {7, 8, 9, 10};
static const char *names[3] = {s1, s1 + 2, s1 + 1};
static int *pa[2] = {&arr[1], &arr[3]};
struct node { struct node *next; int v; };
static struct node n3 = {0, 5};
static struct node n2 = {&n3, 4};
static struct node n1 = {&n2, 3};
static int twice(int x) { return x * 2; }
static int thrice(int x) { return x * 3; }
static int (*fps[2])(int) = {twice, thrice};
volatile int sel = 1;
volatile int unused_sel = 0;

int entry(void) {
  int s = names[sel][1] * 1000;
  s += *pa[sel];
  struct node *p = &n1;
  int t = 0;
  while (p) { t = t * 10 + p->v; p = p->next; }
  if (unused_sel) s += fps[sel](4);
  return s + t * 100000;
}
