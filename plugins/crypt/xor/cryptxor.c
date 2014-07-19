#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <string.h>

typedef unsigned long long  uint64;
typedef unsigned int        uint32;
typedef int                 int32;
typedef unsigned char       uint8;
typedef long long           int64;

/* MSVC support for Windows DLL builds */
#ifdef _WINDOWS
#define EXPORT __declspec(dllexport) __cdecl
#else
#define EXPORT
#endif

/* optimization to support small keys and what is considered a small key */
#define SMALLKEYSUPPORT
#define SMALLKEY        (1024 * 1024 * 4)

typedef struct _CRYPTXOR {
    FILE        *fo;
    FILE        *xfo;
    uint64      xfosz;
} CRYPTXOR;

int EXPORT cryptxor_start(CRYPTXOR *s, char *file, char *xfile, CRYPTXOR  *g, uint8 write) {
    memset(s, 0, sizeof(CRYPTXOR));

    /* if global exist copy onto local */
    if (g) {
        printf("copying global to local\n");
        memcpy(s, g, sizeof(CRYPTXOR));
    }

    if (file) {
        printf("opening file:%s\n", file);
        if (write) {
            s->fo = fopen(file, "wb");
        } else {
            s->fo = fopen(file, "rb");
        }
    }

    /* for global init we just want to open xfile */
    if (file && !s->fo) {
       printf("fo:failed to open '%s'\n", file);
       return 0;
    }

    /* is it already open? */
    if (!s->xfo) {
        printf("opening xfile:%s\n", xfile);
        s->xfo = fopen(xfile, "rb");
        fseek(s->xfo, 0, SEEK_END);
        s->xfosz = ftell(s->xfo);
        fseek(s->xfo, 0, SEEK_SET);
    }

    if (!s->xfo) {
       printf("xfo:failed to open '%s'\n", xfile);
       fclose(s->fo);
       return 0;
    }

    return 1;
}

#define min(a, b) ((a) < (b) ? (a) : (b))

/* 
    reads the data from the file and encryptions it and hands
    the encrypted data back to the caller using `out`
*/
int EXPORT cryptxor_read(CRYPTXOR *s, uint64 o, uint64 l, uint8 *out) {
    uint64      rem;
    uint8       *xbuf;
    uint64      x, y;
    int64       cnt;

    /* read target data into memory from the file */
    fseek(s->fo, o, SEEK_SET);
    fread(out, l, 1, s->fo);

    /* offset into our xor stream */
    fseek(s->xfo, o - ((o / s->xfosz) * s->xfosz), SEEK_SET);

    #ifdef SMALLKEYSUPPORT
    /* this is an optimization for when our key data is fairly small */
    if (s->xfosz < SMALLKEY) { /* 4MB is threshold for considering a small key */
        /* this can be further optimized by storing xbuf in our state! */
        xbuf = (uint8*)malloc(s->xfosz);
        fread(xbuf, 1, s->xfosz, s->xfo);

        rem = l;
        x = 0;
        while (rem > 0) {
            /* loop our key over the data stopping before
               the end of our key OR the end of the data */
            for (y = 0; y < s->xfosz && y < rem; ++x, ++y) {
                out[x] = out[x] ^ xbuf[y];
            }
            /* subtract the amount we processed */
            rem -= y;
        }
        free(xbuf);
        return 1;
    }
    #endif

    /* a key could be VERY large.. and this should handle it decently well by
       not loading the entire key into memory but only a enough of it to work
       on the data we have..

       if you use this on a small key it will be SLOW because of the continous
       calling of fseek to go back to the beginning which eats a lot of CPU, so
       make sure to use SMALLKEYSUPPORT and set SMALLKEY to something reasonably
       large
    */

    /* it can only be s->xfosz in size at maximum */
    xbuf = (uint8*)malloc(SMALLKEY);
    rem = l;
    x = 0;
    cnt = 1;
    while (rem > 0) {
        /* read the biggest chunk we can from the xor stream (no more than 4MB at a time) */
        cnt = fread(xbuf, 1, min(rem, SMALLKEY), s->xfo);

        if (cnt < 1) {
            /* seek back to the beginning of the file */
            fseek(s->xfo, 0, SEEK_SET);
            continue;
        }

        /* encrypt the data */
        for (y = 0; y < cnt; ++x, ++y) {
            out[x] = out[x] ^ xbuf[y];
        }

        /* subtract what we processed */
        rem -= cnt;
    }

    free(xbuf);
    return 1;
}

/*
    writes the data to the file after decrypting it (some algorithms
    are unable to decrypt until all has been written but this one
    has a byte:byte relationship)
*/
int EXPORT cryptxor_write(CRYPTXOR *s, uint64 o, uint8 *data, uint64 dsz) {
    uint64      rem;
    uint8       *xbuf;
    uint8       *obuf;
    uint64      x, lx, y;
    int64       cnt;

    /* seek to position in our output file */
    fseek(s->fo, o, SEEK_SET);

    /* offset into our xor stream */
    fseek(s->xfo, o - ((o / s->xfosz) * s->xfosz), SEEK_SET);

    /* allocate a buffer to hold XOR key stream */
    xbuf = (uint8*)malloc(SMALLKEY);
    obuf = (uint8*)malloc(dsz);

    #ifdef SMALLKEYSUPPORT
    /* this is an optimization for when our key data is fairly small */
    if (s->xfosz < SMALLKEY) { /* 4MB is threshold for considering a small key */
        /* this can be further optimized by storing xbuf in our state! */
        xbuf = (uint8*)malloc(s->xfosz);
        fread(xbuf, 1, s->xfosz, s->xfo);

        rem = dsz;
        x = 0;
        while (rem > 0) {
            /* loop our key over the data stopping before
               the end of our key OR the end of the data */
            for (y = 0; y < s->xfosz && y < rem; ++x, ++y) {
                obuf[x] = data[x] ^ xbuf[y];
            }
            /* subtract the amount we processed */
            rem -= y;
        }

        x = fwrite(obuf, 1, dsz, s->fo);
        printf("WROTE %x bytes\n", x);

        free(obuf);
        free(xbuf);
        return 1;
    }
    #endif


    /* set local offset */
    lx = 0;
    /* set remaining data */
    rem = dsz;
    while (rem > 0) {
        cnt = fread(xbuf, 1, SMALLKEY, s->xfo);

        if (cnt < 1) {
            /* seek back to the beginning of the file */
            fseek(s->xfo, 0, SEEK_SET);
            continue;
        }

        for (x = 0; x < cnt; ++x) {
            obuf[lx + x] = data[lx + x] ^ xbuf[x];
        }

        lx += cnt;
        rem -= cnt;
    }

    /* write decrypted chunk to the file specified by the offset */
    fwrite(obuf, dsz, 1, s->fo);

    /* free the buffers used */
    free(xbuf);
    free(obuf);

    return 1;
}

int EXPORT cryptxor_finish(CRYPTXOR *s, CRYPTXOR *g) {
    fclose(s->fo);
    if (g) {
        fclose(s->xfo);
    }
    return 1;
}