


package main

import 			"fmt"
import 			"Server"
import			"time"
import			"os"

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
	var err			error
	var cnt			int
	var x			int
	var top			int

	if len(os.Args) > 1 {
		if os.Args[1] == "testunit-hash" {
			// read data from stdin
			buf := make([]byte, 1024 * 1024 * 25)
			// read hash size
			for top = 0; top < 3; {
				cnt, err = os.Stdin.Read(buf[top:3])
				top += cnt
			}
			hsz := int(buf[0]) << 16 | int(buf[1]) << 8 | int(buf[2])
			// read header
			for top = 0; top < 3; {
				cnt, err = os.Stdin.Read(buf[top:3])
				top += cnt
			}
			// parse header			
			sz := int(buf[0]) << 16 | int(buf[1]) << 8 | int(buf[2])
			// read data
			fmt.Errorf("[go] sz:%d", sz)
			for top = 0; top < sz; {
				fmt.Errorf("[go] writing to %d with max %d", top, sz)
				cnt, err = os.Stdin.Read(buf[top:sz])
				top += cnt
			}
			// hash data
			buf = Server.HashKmc(buf[0:sz], hsz)
			// write output
			for x = 0; x < len(buf); {
				cnt, err = os.Stdout.Write(buf[x:len(buf)])
				x += cnt
			}
			// exit
			if err == nil {
				err = nil
			}
			return
		}
		return
	}

	//buf := HashKmc([]byte{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}, 4)
	//for x := 0; x < len(buf); x++ {
	//	fmt.Printf("%d ", buf[x])
	//}
	//fmt.Printf("\n")
	//return

	signal = make(chan uint32)
	go server.ServerEntry(signal)
	<- signal
}