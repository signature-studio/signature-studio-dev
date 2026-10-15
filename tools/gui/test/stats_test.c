/* stats_test.c — headless surface 統計 (gui_hl_stats) と SHA-256 の単体テスト (#3460 受入 2)。
 * 期待値: SHA-256 は FIPS 180-4 の既知値 (abc・448 bit・100 万 a) と境界長 (55/56/64 byte) を Python hashlib で確認した値。
 * 画素の sha256 は RGB 3 バイト列 (alpha なし)。ネガコン: 1 bit 反転で sha が変わる / 全面背景は非自明 FAIL。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gui_headless.h"

static int npass, nfail;
#define CHECK(c, ...) do { if (c) npass++; else { nfail++; fprintf(stderr, "[stats_test] FAIL %s:%d: ", __FILE__, __LINE__); fprintf(stderr, __VA_ARGS__); fprintf(stderr, "\n"); } } while (0)

static void hex(const uint8_t *d, char *out) { for (int i = 0; i < 32; i++) sprintf(out + 2 * i, "%02x", d[i]); out[64] = 0; }
static int sha_is(const uint8_t *d, const char *want) { char g[65]; hex(d, g); return strcmp(g, want) == 0; }
static void sha_of(const char *s, size_t n, uint8_t out[32]) { gui_sha256((const uint8_t *)s, n, out); }

static void sha_vectors(void) {
  uint8_t d[32];
  sha_of("", 0, d);
  CHECK(sha_is(d, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"), "sha256(\"\")");
  sha_of("abc", 3, d);
  CHECK(sha_is(d, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "sha256(abc)");
  const char *m448 = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
  sha_of(m448, strlen(m448), d);
  CHECK(sha_is(d, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"), "sha256(448-bit)");
  char *a = malloc(1000000); memset(a, 'a', 1000000);
  sha_of(a, 1000000, d);
  CHECK(sha_is(d, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"), "sha256(1e6 a)");
  free(a);
  char b[64]; memset(b, 'a', sizeof b);
  sha_of(b, 55, d); CHECK(sha_is(d, "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318"), "sha256(55 a)");
  sha_of(b, 56, d); CHECK(sha_is(d, "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"), "sha256(56 a)");
  sha_of(b, 64, d); CHECK(sha_is(d, "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"), "sha256(64 a)");
}

static void stats_cases(void) {
  uint32_t px[12]; GuiHlStats s;
  const uint32_t BG = 0x182838;   /* RGB(24,40,56) */
  for (int i = 0; i < 12; i++) px[i] = 0xFF000000u | BG;
  gui_hl_stats(px, 4, 3, BG, &s);
  CHECK(s.w == 4 && s.h == 3, "size %ux%u", s.w, s.h);
  CHECK(s.nonbg == 0 && s.colors == 1, "all-bg: nonbg=%llu colors=%u (want 0,1)", (unsigned long long)s.nonbg, s.colors);
  CHECK(!gui_hl_nontrivial(&s), "all-bg must be trivial");
  CHECK(sha_is(s.sha256, "6a64a6d5b2c65a45d245d08b827ddc20b52e540ffdabaae71d168fa248a24fdf"), "all-bg sha");

  px[5] = 0xFF112233u;
  gui_hl_stats(px, 4, 3, BG, &s);
  CHECK(s.nonbg == 1 && s.colors == 2, "1 px: nonbg=%llu colors=%u (want 1,2)", (unsigned long long)s.nonbg, s.colors);
  CHECK(gui_hl_nontrivial(&s), "1 px must be non-trivial");

  for (int i = 0; i < 12; i++) px[i] = 0xFF000000u | BG;
  for (int y = 0; y < 2; y++) for (int x = 0; x < 2; x++) px[y * 4 + x] = 0xFFFF0000u;
  for (int y = 0; y < 3; y++) px[y * 4 + 3] = 0xFF00FF00u;
  gui_hl_stats(px, 4, 3, BG, &s);
  CHECK(s.nonbg == 7 && s.colors == 3, "2 rects: nonbg=%llu colors=%u (want 7,3)", (unsigned long long)s.nonbg, s.colors);

  uint32_t *many = malloc(sizeof(uint32_t) * 1000);
  for (int i = 0; i < 1000; i++) many[i] = (uint32_t)(i + 1);
  gui_hl_stats(many, 1000, 1, 0, &s);
  CHECK(s.colors == 1000 && s.nonbg == 1000, "1000 colors (no cap): colors=%u nonbg=%llu", s.colors, (unsigned long long)s.nonbg);
  free(many);

  uint32_t edge[2] = { 0xFFFFFFFFu, 0xFF000000u };
  gui_hl_stats(edge, 2, 1, 0xFFFFFF, &s);
  CHECK(s.colors == 2 && s.nonbg == 1, "24-bit edge: colors=%u nonbg=%llu (want 2,1)", s.colors, (unsigned long long)s.nonbg);

  uint32_t pat[2] = { 0xFFFF0000u, 0xFF00FF00u };
  gui_hl_stats(pat, 2, 1, 0xFFFF0000u, &s);
  CHECK(s.nonbg == 1 && s.colors == 2, "pattern counts");
  CHECK(sha_is(s.sha256, "0757241fa846855871c4ec6994954cbe0e0e7a8fd7bb3f7487462f6ce4215780"), "pattern sha (RGB bytes FF0000 00FF00)");
  uint32_t pata[2] = { 0x80FF0000u, 0x00FF00u };
  gui_hl_stats(pata, 2, 1, 0xFF0000u, &s);
  CHECK(sha_is(s.sha256, "0757241fa846855871c4ec6994954cbe0e0e7a8fd7bb3f7487462f6ce4215780"), "alpha must not be in the sha");

  for (int i = 0; i < 12; i++) px[i] = 0xFF000000u | BG;
  px[1] ^= 0x01u;   /* 画素 1 の B の 1 bit (RGB バイト列の 6 バイト目) */
  gui_hl_stats(px, 4, 3, BG, &s);
  CHECK(sha_is(s.sha256, "c2b056754ef0cf5a1e8fed15536071ce36b65c97b06ee5befd9b81a2786cbf8c"), "negctl: 1-bit change sha");
  CHECK(!sha_is(s.sha256, "6a64a6d5b2c65a45d245d08b827ddc20b52e540ffdabaae71d168fa248a24fdf"), "negctl: 1-bit change must change sha");
}

int main(void) {
  sha_vectors();
  stats_cases();
  printf("[stats_test] %d passed, %d failed\n", npass, nfail);
  return nfail ? 1 : 0;
}
