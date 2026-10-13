/* advapi32 CryptoAPI のハッシュ部分 (MD5 / SHA-1 / SHA-256)。Serum2 が使う 5 API:
 *   CryptAcquireContextA / CryptCreateHash / CryptHashData / CryptGetHashParam / CryptDestroyHash (+ CryptReleaseContext)
 * 鍵・暗号化・署名は非対応 (CryptCreateHash の key != 0 / 未対応 ALG_ID は NTE_BAD_KEY / NTE_BAD_ALGID)。
 * CryptAcquireContextA のキーセット操作 (CRYPT_NEWKEYSET / CRYPT_DELETEKEYSET) は永続キーストアを持たないため
 * 成功を返すだけの no-op。ハッシュ用途の VERIFYCONTEXT 相当として扱う。
 *
 * ハンドル: 256 スロットの表 + 世代カウンタ (解放済みハンドルの再利用を検出)。値は 0x5C000000 | gen<<8 | idx。
 * out パラメータは shimx 既存 API (RegOpenKeyExW 等) と同じ LPHANDLE (wasm32 の 4B)。署名は shimx.h の宣言に一致。
 */
#include "shimx_internal.h"
#include <math.h>

#define CALG_MD5_      0x8003u
#define CALG_SHA1_     0x8004u
#define CALG_SHA256_   0x800Cu
#define HP_ALGID_      1u
#define HP_HASHVAL_    2u
#define HP_HASHSIZE_   4u
#define PROV_RSA_FULL_ 1u
#define PROV_RSA_AES_  24u
#define CRYPT_DELETEKEYSET_ 0x10u

#define NTE_BAD_UID_        0x80090001u
#define NTE_BAD_HASH_       0x80090002u
#define NTE_BAD_KEY_        0x80090003u
#define NTE_BAD_ALGID_      0x80090008u
#define NTE_BAD_FLAGS_      0x80090009u
#define NTE_BAD_HASH_STATE_ 0x8009000Cu
#define NTE_NO_MEMORY_      0x8009000Eu
#define NTE_BAD_PROV_TYPE_  0x80090014u

typedef struct { uint32_t h[8]; uint64_t total; uint8_t buf[64]; uint32_t fill; } HCtx;

static inline uint32_t rol(uint32_t x, int n) { return (x << n) | (x >> (32 - n)); }
static inline uint32_t ror(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

/* ---- MD5 ---- */
static uint32_t g_md5_k[64];
static int g_md5_k_init;
static void md5_block(HCtx* c, const uint8_t* p) {
    static const int S[64] = { 7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22, 5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,
                               4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23, 6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21 };
    if (!g_md5_k_init) { for (int i = 0; i < 64; i++) g_md5_k[i] = (uint32_t)(fabs(sin((double)(i + 1))) * 4294967296.0); g_md5_k_init = 1; }
    uint32_t m[16];
    for (int i = 0; i < 16; i++) m[i] = (uint32_t)p[i*4] | (uint32_t)p[i*4+1] << 8 | (uint32_t)p[i*4+2] << 16 | (uint32_t)p[i*4+3] << 24;
    uint32_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3];
    for (int i = 0; i < 64; i++) {
        uint32_t f; int g;
        if (i < 16)      { f = (b & cc) | (~b & d); g = i; }
        else if (i < 32) { f = (d & b) | (~d & cc); g = (5 * i + 1) & 15; }
        else if (i < 48) { f = b ^ cc ^ d;          g = (3 * i + 5) & 15; }
        else             { f = cc ^ (b | ~d);       g = (7 * i) & 15; }
        uint32_t t = d; d = cc; cc = b;
        b = b + rol(a + f + g_md5_k[i] + m[g], S[i]);
        a = t;
    }
    c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d;
}

/* ---- SHA-1 ---- */
static void sha1_block(HCtx* c, const uint8_t* p) {
    uint32_t w[80];
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[i*4] << 24 | (uint32_t)p[i*4+1] << 16 | (uint32_t)p[i*4+2] << 8 | p[i*4+3];
    for (int i = 16; i < 80; i++) w[i] = rol(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1);
    uint32_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3], e = c->h[4];
    for (int i = 0; i < 80; i++) {
        uint32_t f, k;
        if (i < 20)      { f = (b & cc) | (~b & d);           k = 0x5A827999u; }
        else if (i < 40) { f = b ^ cc ^ d;                    k = 0x6ED9EBA1u; }
        else if (i < 60) { f = (b & cc) | (b & d) | (cc & d); k = 0x8F1BBCDCu; }
        else             { f = b ^ cc ^ d;                    k = 0xCA62C1D6u; }
        uint32_t t = rol(a, 5) + f + e + k + w[i];
        e = d; d = cc; cc = rol(b, 30); b = a; a = t;
    }
    c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d; c->h[4] += e;
}

/* ---- SHA-256 ---- */
static const uint32_t k256[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2 };
static void sha256_block(HCtx* c, const uint8_t* p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[i*4] << 24 | (uint32_t)p[i*4+1] << 16 | (uint32_t)p[i*4+2] << 8 | p[i*4+3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror(w[i-15], 7) ^ ror(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t s1 = ror(w[i-2], 17) ^ ror(w[i-2], 19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t v[8];
    for (int i = 0; i < 8; i++) v[i] = c->h[i];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = ror(v[4], 6) ^ ror(v[4], 11) ^ ror(v[4], 25);
        uint32_t ch = (v[4] & v[5]) ^ (~v[4] & v[6]);
        uint32_t t1 = v[7] + S1 + ch + k256[i] + w[i];
        uint32_t S0 = ror(v[0], 2) ^ ror(v[0], 13) ^ ror(v[0], 22);
        uint32_t mj = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
        uint32_t t2 = S0 + mj;
        v[7] = v[6]; v[6] = v[5]; v[5] = v[4]; v[4] = v[3] + t1; v[3] = v[2]; v[2] = v[1]; v[1] = v[0]; v[0] = t1 + t2;
    }
    for (int i = 0; i < 8; i++) c->h[i] += v[i];
}

typedef struct { DWORD alg; unsigned size; void (*blk)(HCtx*, const uint8_t*); int big_endian; } HAlg;
static const HAlg* alg_of(DWORD alg) {
    static const HAlg k[] = {
        { CALG_MD5_,    16, md5_block,    0 },
        { CALG_SHA1_,   20, sha1_block,   1 },
        { CALG_SHA256_, 32, sha256_block, 1 },
    };
    for (unsigned i = 0; i < sizeof k / sizeof k[0]; i++) if (k[i].alg == alg) return &k[i];
    return NULL;
}
static void h_init(HCtx* c, DWORD alg) {
    static const uint32_t i_md5[4] = { 0x67452301u, 0xefcdab89u, 0x98badcfeu, 0x10325476u };
    static const uint32_t i_sha1[5] = { 0x67452301u, 0xEFCDAB89u, 0x98BADCFEu, 0x10325476u, 0xC3D2E1F0u };
    static const uint32_t i_sha256[8] = { 0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au, 0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u };
    memset(c, 0, sizeof *c);
    if (alg == CALG_MD5_) memcpy(c->h, i_md5, sizeof i_md5);
    else if (alg == CALG_SHA1_) memcpy(c->h, i_sha1, sizeof i_sha1);
    else memcpy(c->h, i_sha256, sizeof i_sha256);
}
static void h_update(HCtx* c, const HAlg* a, const uint8_t* p, size_t n) {
    c->total += n;
    while (n) {
        size_t take = 64 - c->fill; if (take > n) take = n;
        memcpy(c->buf + c->fill, p, take);
        c->fill += (uint32_t)take; p += take; n -= take;
        if (c->fill == 64) { a->blk(c, c->buf); c->fill = 0; }
    }
}
static void h_final(HCtx* c, const HAlg* a, uint8_t* out) {
    uint64_t bits = c->total * 8;
    uint8_t pad[72] = { 0x80 };
    size_t padn = (c->fill < 56) ? 56 - c->fill : 120 - c->fill;
    uint8_t lenb[8];
    for (int i = 0; i < 8; i++) lenb[i] = (uint8_t)(bits >> (a->big_endian ? 56 - 8 * i : 8 * i));
    h_update(c, a, pad, padn);
    h_update(c, a, lenb, 8);
    unsigned words = a->size / 4;
    for (unsigned i = 0; i < words; i++)
        for (int j = 0; j < 4; j++) out[i*4+j] = (uint8_t)(c->h[i] >> (a->big_endian ? 24 - 8 * j : 8 * j));
}

/* ---- ハンドル表 ---- */
enum { K_NONE = 0, K_PROV = 1, K_HASH = 2 };
typedef struct { int kind; uint32_t gen; const HAlg* alg; HCtx ctx; int done; uint8_t val[32]; } Slot;
#define NSLOT 256
static Slot g_slot[NSLOT];
static shx_mutex_t g_lk;

static uint32_t make_h(int idx) { return 0x5C000000u | ((g_slot[idx].gen & 0xFFFFu) << 8) | (uint32_t)idx; }
static Slot* find(HANDLE h, int kind) {          /* g_lk 保持下で呼ぶ */
    if (((uint32_t)h & 0xFF000000u) != 0x5C000000u) return NULL;
    int idx = (int)((uint32_t)h & 0xFF);
    Slot* s = &g_slot[idx];
    if (s->kind != kind || ((s->gen & 0xFFFFu) != (((uint32_t)h >> 8) & 0xFFFFu))) return NULL;
    return s;
}
static int alloc_slot(int kind) {                /* g_lk 保持下 */
    for (int i = 0; i < NSLOT; i++) if (g_slot[i].kind == K_NONE) { g_slot[i].kind = kind; g_slot[i].gen++; return i; }
    return -1;
}
static BOOL fail(DWORD e) { SetLastError(e); return FALSE; }

BOOL CryptAcquireContextA(LPHANDLE prov, LPCSTR cont, LPCSTR name, DWORD type, DWORD flags) {
    (void)cont; (void)name;
    if (!prov) return fail(ERROR_INVALID_PARAMETER);
    if (type != PROV_RSA_FULL_ && type != PROV_RSA_AES_) { *prov = 0; return fail(NTE_BAD_PROV_TYPE_); }
    shx_mutex_lock(&g_lk);
    int i = alloc_slot(K_PROV);
    uint32_t h = i < 0 ? 0 : make_h(i);
    shx_mutex_unlock(&g_lk);
    if (i < 0) { *prov = 0; return fail(NTE_NO_MEMORY_); }
    (void)(flags & CRYPT_DELETEKEYSET_);        /* DELETEKEYSET: キーストア無し → 成功のみ (ハンドルは返す) */
    *prov = h;
    return TRUE;
}
BOOL CryptReleaseContext(HANDLE prov, DWORD flags) {
    if (flags) return fail(NTE_BAD_FLAGS_);
    shx_mutex_lock(&g_lk);
    Slot* s = find(prov, K_PROV);
    if (s) s->kind = K_NONE;
    shx_mutex_unlock(&g_lk);
    return s ? TRUE : fail(NTE_BAD_UID_);
}
BOOL CryptCreateHash(HANDLE prov, DWORD alg, HANDLE key, DWORD flags, LPHANDLE hash) {
    if (!hash) return fail(ERROR_INVALID_PARAMETER);
    *hash = 0;
    shx_mutex_lock(&g_lk);
    if (!find(prov, K_PROV)) { shx_mutex_unlock(&g_lk); return fail(NTE_BAD_UID_); }
    const HAlg* a = alg_of(alg);
    if (!a)    { shx_mutex_unlock(&g_lk); return fail(NTE_BAD_ALGID_); }
    if (flags) { shx_mutex_unlock(&g_lk); return fail(NTE_BAD_FLAGS_); }
    if (key)   { shx_mutex_unlock(&g_lk); return fail(NTE_BAD_KEY_); }
    int i = alloc_slot(K_HASH);
    if (i < 0) { shx_mutex_unlock(&g_lk); return fail(NTE_NO_MEMORY_); }
    g_slot[i].alg = a; g_slot[i].done = 0; h_init(&g_slot[i].ctx, alg);
    uint32_t h = make_h(i);
    shx_mutex_unlock(&g_lk);
    *hash = h;
    return TRUE;
}
BOOL CryptHashData(HANDLE h, const BYTE* d, DWORD n, DWORD flags) {
    if (flags) return fail(NTE_BAD_FLAGS_);
    shx_mutex_lock(&g_lk);
    Slot* s = find(h, K_HASH);
    DWORD err = 0;
    if (!s) err = NTE_BAD_HASH_;
    else if (s->done) err = NTE_BAD_HASH_STATE_;
    else if (n && !d) err = ERROR_INVALID_PARAMETER;
    else if (n) h_update(&s->ctx, s->alg, d, n);
    shx_mutex_unlock(&g_lk);
    return err ? fail(err) : TRUE;
}
BOOL CryptGetHashParam(HANDLE h, DWORD p, BYTE* d, LPDWORD n, DWORD flags) {
    if (flags) return fail(NTE_BAD_FLAGS_);
    if (!n) return fail(ERROR_INVALID_PARAMETER);
    shx_mutex_lock(&g_lk);
    Slot* s = find(h, K_HASH);
    if (!s) { shx_mutex_unlock(&g_lk); return fail(NTE_BAD_HASH_); }
    DWORD need, err = 0; uint8_t tmp[32];
    if (p == HP_ALGID_)          { need = 4; memcpy(tmp, &s->alg->alg, 4); }
    else if (p == HP_HASHSIZE_)  { need = 4; DWORD sz = s->alg->size; memcpy(tmp, &sz, 4); }
    else if (p == HP_HASHVAL_)   { need = s->alg->size; }
    else { shx_mutex_unlock(&g_lk); return fail(ERROR_INVALID_PARAMETER); }
    if (!d) { *n = need; }                                   /* サイズ問合せ: 確定 (finalize) しない */
    else if (*n < need) { *n = need; err = ERROR_MORE_DATA; }
    else {
        if (p == HP_HASHVAL_) {
            if (!s->done) { h_final(&s->ctx, s->alg, s->val); s->done = 1; }
            memcpy(d, s->val, need);
        } else memcpy(d, tmp, need);
        *n = need;
    }
    shx_mutex_unlock(&g_lk);
    return err ? fail(err) : TRUE;
}
BOOL CryptDestroyHash(HANDLE h) {
    shx_mutex_lock(&g_lk);
    Slot* s = find(h, K_HASH);
    if (s) { uint32_t g = s->gen; memset(s, 0, sizeof *s); s->gen = g; }
    shx_mutex_unlock(&g_lk);
    return s ? TRUE : fail(NTE_BAD_HASH_);
}
