#include <stdlib.h>
#include <stdio.h>

typedef unsigned long long  uint64;
typedef unsigned char       uint8;
typedef long long           int64;

typedef struct _CRYPTXOR {
    FILE        *fo;
    FILE        *xfo;
    uint64      xfosz;
} CRYPTXOR;

int cryptxor_start(CRYPTXOR *s, char *file, char *xfile) {
    s->fo = fopen(file, "rb");
    s->xfo = fopen(xfile, "rb");

    fseek(s->xfo, 0, 2);
    s->xfosz = ftell(s->xfo);
}

/* 
    reads the data from the file and encryptions it and hands
    the encrypted data back to the caller using `out`
*/
int cryptxor_read(CRYPTXOR *s, uint64 o, uint64 l, char *out) {
    uint8       *buf;
    uint64      rem;
    uint8       *xbuf;
    uint64      x, y;
    int64       cnt;

    /* read target data into memory from the file */
    fseek(s->fo, o, 0);
    fread(out, l, 1, s->fo);

    /* offset into our xor stream */
    fseek(s->xfo, o - ((o / s->xfosz) * s->xfosz), 0);

    xbuf = (uint8*)malloc(l);
    rem = l;
    x = 0;
    while (rem > 0) {
        /* read the biggest chunk we can from the xor stream */
        cnt = fread(xbuf, rem, 1, s->xfo);

        if (cnt == 0) {
            /* seek back to the beginning of the file */
            fseek(s->xfo, 0, 0);
            continue;
        }

        /* encrypt the data */
        for (y = 0; x < cnt; ++x, ++y) {
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
int cryptxor_write(CRYPTXOR *s, uint64 o, uint8 *data, uint64 dsz) {
    uint64      rem;
    uint8       *xbuf;
    uint8       *obuf;
    uint64      x, lx;
    int64       cnt;

    /* seek to position in our output file */
    fseek(s->fo, o, 0);

    /* offset into our xor stream */
    fseek(s->xfo, o - ((o / s->xfosz) * s->xfosz), 0);

    /* allocate a buffer to hold XOR key stream */
    xbuf = (uint8*)malloc(dsz);
    obuf = (uint8*)malloc(dsz);

    /* set local offset */
    lx = 0;
    /* set remaining data */
    rem = dsz;
    while (rem > 0) {
        cnt = fread(xbuf, rem, 1, s->xfo);

        if (cnt < 1) {
            /* seek back to the beginning of the file */
            fseek(s->xfo, 0, 0);
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
}

int cryptxor_finish(CRYPTXOR *s) {
    fclose(s->fo);
    fclose(s->xfo);
}