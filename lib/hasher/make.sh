#!/bin/sh
gcc hasher.c -nostdlib --freestanding -fPIC -shared -nostdlib -o hasher64.so
