package main

import 			"fmt"
import 			"Server"
import			"time"

func Consumer(in chan uint32) {
	var x		uint32

	for {
		x = <- in
		time.Sleep(1)
		fmt.Printf("sent %d\n", x)
	}
}

func main() {
	var signal 		chan uint32
	var server 		Server.Server

	signal = make(chan uint32)

	go server.ServerEntry(signal)
	<- signal
}