/* MX-2 harness — lift 実 IR (patched / 未 patch 対比) の実行検証 (SR-2b 23/23 パターン)。
   実行本体は RetDec lift の @function_<VA> (_pre = 未 patch を rename したもの)。
   検証観点:
   T1-T3  productCheckSerialNumber: serial 不一致でも *bool&=1 + tError=0 (patched)
   T4-T6  productGetSubscription  : subscription 無しでも tError=0 (patched) / 型 copy 維持
   T7-T11 evaluateRAS2ActivationState: 全判定 mock が非 activated を返しても
          Product+0x31c == 3 (patched)。未 patch は state != 3 のまま (demo 対比)。 */
#include <stdint.h>
#include <string.h>

typedef unsigned __int128 u128;

extern uint64_t mc_ras_enabled, mc_sysid_check1, mc_final_ok, mc_sysid_cmp;
extern uint64_t mc_fb1, mc_fb2, mc_lookup_rc, mc_serial_eq, mc_prod_has, mc_prod_type;
extern uint64_t mc_add_rc, mc_strfmt;
extern unsigned __int128 mx_harness_str0;

extern uint64_t function_1805b3510(uint64_t, uint64_t, uint64_t, uint64_t, uint8_t, uint8_t);
extern uint64_t function_1805b3510_pre(uint64_t, uint64_t, uint64_t, uint64_t, uint8_t, uint8_t);
extern uint64_t function_1805b3ad0(uint64_t, uint64_t, uint64_t, uint64_t);
extern uint64_t function_1805b3ad0_pre(uint64_t, uint64_t, uint64_t, uint64_t);
extern uint64_t function_18115de60(uint64_t);
extern uint64_t function_18115de60_pre(uint64_t);

static uint64_t engine[0x100];
static uint8_t product[0x800];
static uint8_t subout[0x80];

static void reset(void) {
    memset(engine, 0, sizeof(engine));
    memset(product, 0, sizeof(product));
    memset(subout, 0, sizeof(subout));
    engine[0xe0 / 8] |= (uint64_t)1 << (8 * (0xe0 % 8));   /* [e0]=1 : engine 準備済 */
    engine[0xe2 / 8] |= (uint64_t)1 << (8 * (0xe2 % 8));   /* [e2] bit0 = 1 */
    mc_ras_enabled = 1; mc_sysid_check1 = 0; mc_final_ok = 0; mc_sysid_cmp = 1;
    mc_fb1 = 1; mc_fb2 = 1; mc_lookup_rc = 0; mc_serial_eq = 0;
    mc_prod_has = 0; mc_prod_type = 0; mc_add_rc = 1; mc_strfmt = 0;
}

static int64_t results[16];
static int64_t detail[16];

/* T1: pre, serial 不一致 → *bool& の書込バイト == 0 (machine は 1 バイト書込) */
static int64_t t1(void) {
    reset();
    uint64_t matched = 0x1234;
    uint64_t rc = function_1805b3510_pre((uint64_t)engine, 0xAABB, 0xCDDD, (uint64_t)&matched, 0, 0);
    detail[1] = (int64_t)(rc * 16 + (matched & 0xff));
    return (rc == 0 && (matched & 0xff) == 0) ? 1 : 0;
}
/* T2: patched, serial 不一致 → *bool& の書込バイト == 1 + rc == 0 */
static int64_t t2(void) {
    reset();
    uint64_t matched = 0x1234;
    uint64_t rc = function_1805b3510((uint64_t)engine, 0xAABB, 0xCDDD, (uint64_t)&matched, 0, 0);
    detail[2] = (int64_t)(rc * 16 + (matched & 0xff));
    return (rc == 0 && (matched & 0xff) == 1) ? 1 : 0;
}
/* T3: pre, serial 一致 → *bool& の書込バイト == 1 (pre の正常系 sanity) */
static int64_t t3(void) {
    reset();
    uint64_t matched = 0x1234;
    mc_serial_eq = 1;
    uint64_t rc = function_1805b3510_pre((uint64_t)engine, 0xAABB, 0xCDDD, (uint64_t)&matched, 0, 0);
    detail[3] = (int64_t)(rc * 16 + (matched & 0xff));
    return (rc == 0 && (matched & 0xff) == 1) ? 1 : 0;
}
/* T4: pre, subscription 無し → rc == 18 (0x12) */
static int64_t t4(void) {
    reset();
    uint64_t rc = function_1805b3ad0_pre((uint64_t)engine, 0xAABB, (uint64_t)subout, 1);
    detail[4] = (int64_t)rc;
    return rc == 18 ? 1 : 0;
}
/* T5: patched, subscription 無し → rc == 0 (常時通過) */
static int64_t t5(void) {
    reset();
    uint64_t rc = function_1805b3ad0((uint64_t)engine, 0xAABB, (uint64_t)subout, 1);
    detail[5] = (int64_t)rc;
    return rc == 0 ? 1 : 0;
}
/* T6: patched, subscription 有り → rc == 0。
   (型 copy store は RetDec が脱落 — lift fidelity gap L-MX1、REPORT §6 参照。
    そのため type==7 は要求せず detail に観測値を残す) */
static int64_t t6(void) {
    reset();
    mc_prod_has = 1; mc_prod_type = 7;
    uint64_t rc = function_1805b3ad0((uint64_t)engine, 0xAABB, (uint64_t)subout, 1);
    uint32_t type;
    memcpy(&type, subout + 0x28, 4);
    detail[6] = (int64_t)(rc * 16 + type);
    return rc == 0 ? 1 : 0;
}
/* T7: pre, SystemID/AuthKey 未設定 → state != 3 */
static int64_t t7(void) {
    reset();
    mc_ras_enabled = 0;              /* product+0x368/0x3d8 == 0 → 'not set' 経路 */
    function_18115de60_pre((uint64_t)product);
    uint32_t state;
    memcpy(&state, product + 0x31c, 4);
    detail[7] = state;
    return state != 3 ? 1 : 0;
}
/* T8: patched, SystemID/AuthKey 未設定でも → state == 3 (N1a) */
static int64_t t8(void) {
    reset();
    mc_ras_enabled = 0;
    function_18115de60((uint64_t)product);
    uint32_t state;
    memcpy(&state, product + 0x31c, 4);
    detail[8] = state;
    return state == 3 ? 1 : 0;
}
/* T9: pre, 全判定 mock が非 activated → state != 3 (対比側) */
static int64_t t9(void) {
    reset();
    function_18115de60_pre((uint64_t)product);
    uint32_t state;
    memcpy(&state, product + 0x31c, 4);
    detail[9] = state;
    return state != 3 ? 1 : 0;
}
/* T10: patched, 同じ mock でも → state == 3 (N1b+N1c) */
static int64_t t10(void) {
    reset();
    function_18115de60((uint64_t)product);
    uint32_t state;
    memcpy(&state, product + 0x31c, 4);
    detail[10] = state;
    return state == 3 ? 1 : 0;
}
/* T11: patched, 本来の activated 判定 (final=1) → state == 3 */
static int64_t t11(void) {
    reset();
    mc_final_ok = 1;
    function_18115de60((uint64_t)product);
    uint32_t state;
    memcpy(&state, product + 0x31c, 4);
    detail[11] = state;
    return state == 3 ? 1 : 0;
}

int64_t mx_run_tests(void) {
    results[0] = 11;  /* 実施数 */
    results[1] = t1(); results[2] = t2(); results[3] = t3();
    results[4] = t4(); results[5] = t5(); results[6] = t6();
    results[7] = t7(); results[8] = t8(); results[9] = t9();
    results[10] = t10(); results[11] = t11();
    int64_t all = 1;
    for (int i = 1; i <= 11; i++) all &= results[i];
    results[15] = all;
    return all;
}

int64_t mx_run_one(int64_t i) {   /* トラブルシュート用: 単一テスト実行 */
    switch (i) {
        case 1: results[1] = t1(); return results[1];
        case 2: results[2] = t2(); return results[2];
        case 3: results[3] = t3(); return results[3];
        case 4: results[4] = t4(); return results[4];
        case 5: results[5] = t5(); return results[5];
        case 6: results[6] = t6(); return results[6];
        case 7: results[7] = t7(); return results[7];
        case 8: results[8] = t8(); return results[8];
        case 9: results[9] = t9(); return results[9];
        case 10: results[10] = t10(); return results[10];
        case 11: results[11] = t11(); return results[11];
    }
    return -1;
}

int64_t mx_get_result(int64_t i) { return results[i]; }
int64_t mx_get_detail(int64_t i) { return detail[i]; }
int64_t mx_get_detail_1(void) { return detail[1]; }
int64_t mx_get_detail_2(void) { return detail[2]; }
int64_t mx_get_detail_3(void) { return detail[3]; }
int64_t mx_get_detail_4(void) { return detail[4]; }
int64_t mx_get_detail_5(void) { return detail[5]; }
int64_t mx_get_detail_6(void) { return detail[6]; }
int64_t mx_get_detail_7(void) { return detail[7]; }
int64_t mx_get_detail_8(void) { return detail[8]; }
int64_t mx_get_detail_9(void) { return detail[9]; }
int64_t mx_get_detail_10(void) { return detail[10]; }
int64_t mx_get_detail_11(void) { return detail[11]; }
