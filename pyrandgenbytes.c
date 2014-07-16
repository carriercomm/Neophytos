#include <stdlib.h>

int pyrandgenbytes(unsigned char *buf, unsigned int sz) {
    unsigned int        x;

    for (x = 0; x < sz; ++x) {
        buf[x] = rand() >> 8;        
    }

    return 1;
}