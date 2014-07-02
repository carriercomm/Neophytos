#!/bin/sh
gcc hasher.c -fPIC -shared -nostdlib -o hasher64.so
