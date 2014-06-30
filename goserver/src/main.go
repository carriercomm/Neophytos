package main

import 			"fmt"
import 			"Server"

/*
*/

type Apple struct {
	f1 uint32
	f2 uint32
	f3 uint32
}

func (this *Apple) mm1(x uint32) (uint32) {
	return x + this.f1;
}

func test(a Apple) (Apple) {
	a.f1 = 10
	return a
}

func tryit(buf []byte, sz uint32) {
	var x			uint32
	
	for x = 0; x < sz; x++ {
		buf[x] = (byte)(x + x)
	}
}

func main() {
	var signal 		chan uint32
	var server 		Server.Server
	//var buf			[24]byte
	//var x			uint32
	signal = make(chan uint32)
	//var c			[]byte
	//c = buf[0:5]
	//tryit(buf[1:24], 10)
	var a			[10]byte
	var b			[]byte
	
	b = make([]byte, 10)
	
	a[0] = 0xdd
	b[0] = 0xbb

	fmt.Println(len(b))
	
	//copy(buf[0:], buf[10:10+14])
	
	//fmt.Print("buf")
	//fmt.Println(c)

	go server.ServerEntry(signal)
	<- signal
}