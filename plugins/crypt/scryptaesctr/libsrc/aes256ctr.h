#ifndef H_AES256CTR
#define H_AES256CTR
#include "aes256.h"
#include "export.h"

typedef struct _AES256CTR_CONTEXT {
   aes256_context          ctx;
   uint8_t                 *key;
   uint8_t                 nonce[32];
   uint8_t                 stream[32];
   uint8_t                 streami;
} AES256CTR_CONTEXT;

int EXPORT aes256ctr_init(AES256CTR_CONTEXT *ctx, const uint8_t *key, const uint8_t *nonce);
int EXPORT aes256ctr_crypt(AES256CTR_CONTEXT *ctx, const uint8_t *in, uint8_t *out, size_t sz);
int EXPORT aes256ctr_done(AES256CTR_CONTEXT *ctx);
#endif