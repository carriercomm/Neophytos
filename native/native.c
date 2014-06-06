#include <stdlib.h>
#include <stdio.h>
#include <string.h>

typedef unsigned char		uint8;

int crypt(uint8 *xkey, int xkeysz, uint8 *mkey,  int mkeysz, uint8 *data, int dsz) {
	uint8		bv, kv;
	int			tondx;
	int			x, y;
	
	//printf("CRYPT\n");
	
	// XOR the data with the key
	for (x = 0, y = 0; y < dsz; ++y) {
		
		//printf("data[y]:%x\n", xkey[x]);
		data[y] = data[y] ^ xkey[x];
		
		x++;
		if (x == xkeysz) {
			x = 0;
		}
	}
	
	// MIX the data with the key
	for (x = 0, y = 0; y < dsz; ++y) {
		bv = data[y];
		kv = mkey[x];
		
		// kv of zero not allowed (i forgot why i did this)
		// but it has to sync with the python code in the 
		// event that someone is emulating this in Python
		if (kv == 0) {
			kv = 1;
		}
	
		//printf("result:%i\n", 15 % 10);
	
		//printf("...a kv:%i dsz-1:%i\n", kv, dsz - 1);
		// calculate target index
		tondx = (dsz - 1) % kv; 
		//printf("...b\n");
		
		//printf("dsz:%x kv:%x tondx:%i fromndx:%i\n", dsz, kv, tondx, y);
		
		// swap bytes
		data[y] = data[tondx];
		data[tondx] = bv;
	
		x++;
		if (x == mkeysz) {
			x = 0;
		}
	}
	
	return 0;
}

int decrypt(uint8 *xkey, int xkeysz, uint8 *mkey,  int mkeysz, uint8 *data, int dsz) {
	uint8		kv, bv;
	int			tondx;
	int			x, y;
	int			t, r;
	//printf("DECRYPT\n");
	
	t = (dsz - 1) / mkeysz;
	r = (dsz - 1) - (t * mkeysz);
	
	// UNMIX the data with the key (FIRST)
	for (x = r, y = dsz - 1; y > -1; --y) {
		kv = mkey[x];
		bv = data[y];
		
		if (kv == 0) {
			kv = 1;
		}
		
		tondx =  (dsz - 1) % kv; 
		
		//printf("dsz:%x kv:%x tondx:%i fromndx:%i\n", dsz, kv, tondx, y);
		
		data[y] = data[tondx];
		data[tondx] = bv;
	
		x--;
		if (x == -1) {
			x = mkeysz - 1;
		}
	}

	// XOR the data with the key (LAST)
	for (x = 0, y = 0; y < dsz; ++y) {
		
		data[y] = data[y] ^ xkey[x];
		
		x++;
		if (x == xkeysz) {
			x = 0;
		}
	}
	return 0;
}

int main(int argc, char *argv[]) {
	//char		*_data = "hello world here i am standing here looking dumb";
	char		*mkey = "34aekmx329930";
	char		*xkey = "dek3";
	uint8		*data;
	int			dsz;
	
	char		*_data;
	
	_data = (char*)malloc(1024 * 1024);
	dsz = 1024 * 1024;
	
	// allocate room for and copy null terminator just for printing at the end
	//dsz = strlen(_data);
	data = (uint8*)malloc(dsz + 1);
	memcpy(data, _data, dsz + 1);
	
	// encrypt data in buffer
	crypt(xkey, strlen(xkey), mkey, strlen(mkey), data, dsz);
	// decrypt data in buffer
	decrypt(xkey, strlen(xkey), mkey, strlen(mkey), data, dsz);
	// verify data in buffer
	printf("%s\n", data);
	return 0;
}