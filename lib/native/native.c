#include <stdio.h>
#include <string.h>

#include "aes.h"

/* windows: __declspec(dllexport) _stdcall */

typedef unsigned char       uint8;
typedef unsigned int        uint32;

void _memset(void *dst, uint8 v, uint32 sz) {
    uint32      x;

    for (x = 0; x < sz; ++x) {
        ((uint8*)dst)[x] = v;
    }
}

int hash(void *_data, int length, int max) {
    uint32      seed;
    int         sz;
    uint32      x;
    uint32      c;
    uint32      a;
    uint32      b;
    uint8       *data;

    data = (uint8*)_data;

    seed = 0;
    sz = length;
    while (sz > max) {
        x = 0;
        c = 0;
        while (x * 2 < sz) {
            if (x * 2 + 1 < sz) {
                a = data[x * 2 + 0];
                b = data[x * 2 + 1];
                c = a + b + (x * 2) + c + seed;
                data[x] = (uint8)c;
            } else {
                seed = data[x * 2];
            }
            x++;
        }
        sz = x;
    }
    return sz;
}

int main(int argc, char *argv[]) {
}