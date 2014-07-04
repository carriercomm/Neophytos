//#include <stdio.h>

// windows: __declspec(dllexport) _stdcall

typedef unsigned char       uint8;
typedef unsigned int        uint32;

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

/*
int main(int argc, char *argv[]) {
    uint8    data[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    int      sz;
    int      x;

    sz = hash(&data[0], sizeof(data), 4);

    for (x = 0; x < sz; ++x) {
        printf("%d ", data[x]);
    }
    printf("\n");

    return 0;
}
*/