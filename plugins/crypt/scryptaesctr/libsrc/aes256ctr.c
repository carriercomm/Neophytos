#include <string.h>
#include <stdio.h>

#include "aes256ctr.h"
#include "export.h"

/*
   I figured it could not hurt, and would be a little
   better than all zeros. But, according to my research
   this should be just as good even if it was all zeros
   but I felt this was akin to passing in a default randomly
   generated nonce. So in this case I just premade one for
   you.
*/
const uint8_t noncesalt[16] = {
   0x9F, 0xe4, 0x32, 0xf8, 0xf8, 0x93, 0x21, 0x11,
   0x44, 0x32, 0xae, 0xdd, 0x9d, 0x12, 0x76, 0x45,
};

/*
   This is used by calling code that does not have access to
   the headers and can not determine the byte length of the
   context structure. It can use this to allocate enough memory
   and the init function will initialize it correctly.
*/
int EXPORT aes256ctr_getcontextsize() {
   return sizeof(AES256CTR_CONTEXT);
}

static int aes256ctr_nonce_inc(AES256CTR_CONTEXT *ctx) {
   int         x;
   uint8_t     *nonce;

   nonce = &ctx->nonce[0];

   for (x = 0; x < 16; ++x) {
      nonce[x]++;
      /* if nonce did not wrap */
      if (nonce[x] != 0) {
         return 0;
      }
   }

   return 0;
}

static int aes256ctr_nonce_stream_more(AES256CTR_CONTEXT *ctx) {
   int         x;

   /* copy nonce so we can encrypt it */
   for (x = 0; x < 16; ++x) {
      ctx->stream[x] = ctx->nonce[x];
   }

   #ifdef USEAES_P
   /* encrypt the nonce and store in stream */
   aes256_encrypt_ecb(&ctx->ctx, &ctx->stream[0]);
   #endif

   #ifdef USAES_O
   oaes_encrypt(ctx->ctx, &ctx->stream[0], 16, &ctx->stream[0], 16);
   #endif

   /* increment the nonce */
   aes256ctr_nonce_inc(ctx);

   /* set stream index to zero */
   ctx->streami = 0;
   return 0;
}

/*
   This will initialize the stream ready for usage as a context.

   The key must be 32 bytes and the nonce must be 16 bytes!
*/
int EXPORT aes256ctr_init(AES256CTR_CONTEXT *ctx, const uint8_t *key, const uint8_t *nonce) {
   #ifdef USEAES_P
   aes256_init(&ctx->ctx, (uint8_t*)key);
   #endif
   #ifdef USEAES_O
   ctx->ctx = oaes_alloc();
   oaes_set_option(ctx->ctx, OAES_OPTION_ECB, NULL);
   oaes_key_import_data(ctx->ctx, key, 32);
   #endif

   /* copy nonce into our local buffer so we can modify it */
   if (nonce) {
      memcpy(&ctx->nonce[0], nonce, 16);
   } else {
      /* if none provided initialize it to zero */
      memcpy(&ctx->nonce[0], &noncesalt[0], 16);
   }

   /* generate first 32 stream bytes */
   aes256ctr_nonce_stream_more(ctx);
   return 0;
}

/*
   This will encrypt some bytes provided and will automatically
   increment the nonce and produce more bytes as needed.
*/
int EXPORT aes256ctr_crypt(AES256CTR_CONTEXT *ctx, const uint8_t *in, uint8_t *out, size_t sz) {
   size_t      x;

   /* use stream bytes */
   x = 0;
   while (1) {
      for (; ctx->streami < 16; ctx->streami++, x++) {
         if (x >= sz) {
            /* we are done so exit, and leave streami where it is.. */
            return 0;
         }
         out[x] = in[x] ^ ctx->stream[ctx->streami];
      }
      /* generate stream bytes if needed */
      aes256ctr_nonce_stream_more(ctx);
   }
}

/*
   This will release any resources used. I mainly use it to allow
   the AES-256 primitive to release anything it has used since all
   of our memory was allocated for us by the calling code and we
   just used that.
*/
int EXPORT aes256ctr_done(AES256CTR_CONTEXT *ctx) {
   #ifdef USEAES_P
   aes256_done(&ctx->ctx);
   #endif
   #ifdef USEAES_O
   oaes_free(&ctx->ctx);
   #endif
   return 0;
}
