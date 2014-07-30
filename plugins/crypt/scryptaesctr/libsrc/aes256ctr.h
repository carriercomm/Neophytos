#ifndef H_AES256CTR
#define H_AES256CTR
//#define USEAES_P        /* portable - low memory - 8-bit byte operation implementation */
#define USEAES_O        /* https://code.google.com/p/openaes/ */

/*
    Should be a highly portable and low memory consumption
    version of AES-256, but very slow. About 50KB/sec on
    my current system. --kmcguire

    aes256.c and aes256.h
*/
#ifdef USEAES_P
#include "aes256.h"
#endif

/*
    A faster implementation.

    oaes_lib.c and oaes_lib.h
*/
#ifdef USEAES_O
#include "oaes_lib.h"
#endif

#include "export.h"

typedef struct _AES256CTR_CONTEXT {
   #ifdef USEAES_P
   aes256_context          ctx;
   #endif
   #ifdef USEAES_O
   OAES_CTX                *ctx;
   #endif
   uint8_t                 *key;
   uint8_t                 nonce[16];
   uint8_t                 stream[16];
   uint8_t                 streami;
} AES256CTR_CONTEXT;

int EXPORT aes256ctr_init(AES256CTR_CONTEXT *ctx, const uint8_t *key, const uint8_t *nonce);
int EXPORT aes256ctr_crypt(AES256CTR_CONTEXT *ctx, const uint8_t *in, uint8_t *out, size_t sz);
int EXPORT aes256ctr_done(AES256CTR_CONTEXT *ctx);
#endif