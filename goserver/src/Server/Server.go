package Server

import             "fmt"
import tls         "crypto/tls"
import             "net"
import             "sync"
import ioutil      "io/ioutil"
import             "bytes"
import             "strconv"
import             "os"
import pprof       "runtime/pprof"
import             "strings"
import             "time"
import             "io"

// unused imports
//import           "math"
//import           "zlib"
//import           "runtime"
//import rsa       "crypto/rsa"
//import crand     "crypto/rand"

const (
    CmdClientDirList                = 0
    CmdClientFileRead               = 1
    CmdClientFileWrite              = 2
    CmdClientFileSize               = 3
    CmdClientFileTrun               = 4
    CmdClientFileDel                = 5
    CmdClientFileCopy               = 6
    CmdClientFileMove               = 7
    CmdClientFileHash               = 8
    CmdClientGetPublicKey           = 11
    CmdClientSetupCrypt             = 12
    CmdClientEncrypted              = 13
    CmdClientLogin                  = 14
    CmdClientFileTime               = 15
    CmdClientFileSetTime            = 16
    CmdClientEcho                   = 17
    ////////////////////////////////////
    CmdServerDirList                = 0
    CmdServerFileRead               = 1
    CmdServerFileWrite              = 2
    CmdServerFileSize               = 3
    CmdServerFileTrun               = 4
    CmdServerFileDel                = 5
    CmdServerFileCopy               = 6
    CmdServerFileMove               = 7
    CmdServerFileHash               = 8
    CmdServerPublicKey              = 11
    CmdServerSetupCrypt             = 12
    CmdServerEncrypted              = 13
    CmdServerLogin                  = 14
    CmdServerLoginResult            = 16
    CmdServerFileTime               = 17
    CmdServerSetCompressionLevel    = 18
    CmdServerFileSetTime            = 19
    CmdServerEcho                   = 20
    ////////////////////////////////////
    FileHeaderReserve               = 32
)

// account configuration structure
type AccountConfig struct {
    lock                *sync.Mutex           // protects structure access
    spaceQuota          int64                 // maximum bytes that can be used
    spaceUsed           int64                 // bytes used in total file data
    spacePerFile        int64                 // bytes consumed for file creation
    spacePerDir         int64                 // bytes consumed for each directory created
    DiskPath            string                // the base disk path for this account
    RefCount            int16                 // once at zero it can be flushed to disk
    AccountName         string                // name of account
}

// lock protected object member access; will add mod to current value and return new value
func (self *AccountConfig) SpaceQuota(mod int64) (out int64) {
    self.lock.Lock()
    self.spaceQuota += mod
    out = self.spaceQuota
    self.lock.Unlock()
    return
}

// lock protected object member access; will add mod to current value and return new value
func (self *AccountConfig) SpaceUsed(mod int64) (out int64) {
    defer self.lock.Unlock()
    self.lock.Lock()
    self.spaceUsed += mod
    return self.spaceUsed
}

// lock protected object member access; will add mod to current value and return new value
func (self *AccountConfig) SpacePerFile(mod int64) (int64) {
    defer self.lock.Unlock()
    self.lock.Lock()
    self.spacePerFile += mod
    return self.spacePerFile
}

// lock protected object member access; will add mod to current value and return new value
func (self *AccountConfig) SpacePerDir(mod int64) (int64) {
    defer self.lock.Unlock()
    self.lock.Lock()
    self.spacePerDir += mod
    return self.spacePerDir
}

// server client state object
type ServerClient struct {
    config                *AccountConfig        // pointer to account configuration
    server                *Server                // pointer to server structure
    conn                 net.Conn              // connection object for client
    vector                uint64                // current valid vector
    msgbuf                *bytes.Buffer        // byte buffer
    msgin                []byte                // try to reuse message buffers when possible
}

// server state object
type Server struct {
    accountConfigsLock    *sync.Mutex
    accountConfigs        map[string]*AccountConfig
}

/*
    BYTE ARRAY INTEGER READING ROUTINES
*/

// read unsigned 16-bit big endian integer
func read16MSB(buf []byte, off uint32) (uint16) {
    return uint16(buf[off + 0]) << 8 | uint16(buf[off + 1])
}

// read unsigned 32-bit big endian integer
func read32MSB(buf []byte, off uint32) (uint32) {
    return uint32(read16MSB(buf, off)) << 16 | uint32(read16MSB(buf, off + 2))
}

// read unsigned 64-bit big endian integer
func read64MSB(buf []byte, off uint32) (uint64) {
    return uint64(read32MSB(buf, off)) << 32 | uint64(read32MSB(buf, off + 4))
}

// read message from buffer and remove it from the buffer
func (self *ServerClient) getMessageFromBuffer(buf []byte, top uint32, maxsz uint32) (v uint64, msg []byte, btop uint32, err error) {
    var sz            uint32


    // read message length
    if top < (4 + 8) {
        return 0, nil, top, nil
    }
    
    sz = read32MSB(buf, 0)
    
    if sz > maxsz {
        // maximum message size prevents DoS by creating very large messages
        return 0, nil, top, fmt.Errorf("The message exceeds maximum specified size of %I.", maxsz) 
    }
    
    if (4 + 8 + sz > top) {
        // not enough data in buffer to read all of it
        return 0, nil, top, nil
    }
    
    
    v = read64MSB(buf, 4)
    
    // resize our main message buffer to hold the contents of this message
    // if it is too small or never been allocated; we do this to keep from
    // allocating new message buffers each time but the problem is you cant
    // use the message buffer across calls to this function because you will
    // get overwritten - this showed a significant decrease in cpu burn and
    // i suspect that was from the GC collecting all the short lived message
    // buffers
    if sz > uint32(len(self.msgin)) {
        fmt.Printf("expanding internal msg buffer\n")
        self.msgin = make([]byte, sz)
    }

    // get a slice of our main buffer (points into main buffer)
    msg = self.msgin[0:sz]

    // copy message into buffer
    copy(msg, buf[4 + 8:4 + 8 + sz])
    
    // shift all data down in incoming buffer
    copy(buf, buf[4 + 8 + sz:top])
    // reset buffer top
    btop = top - (4 + 8 + sz)
    return v, msg, btop, nil
}

// initializes internal message buffer and write basic fields
func (self *ServerClient) MsgStart(rvector uint64) {
    self.msgbuf.Reset()

    self.MsgWrite64MSB(self.vector)        // write server vector
    self.vector = self.vector + 1        // increment server vector
    self.MsgWrite64MSB(rvector)            // write reply vector
    /*
        I feel that I need to explain this. Back in the old days I did not
        use SSL and instead any packet that was encrypted and needed to be
        decrypted was prefixed with this. Many of the commands were required
        to be encrypted. The current build of the client does not do any 
        encrypted outside of SSL. So this is just left from those old days. I do
        not remove it because I might want employ some extra encryption one day and
        all the code is still in place (just disabled)..

        I could one day make it where commands are not forced to be encrypted and
        in that case I could leave this prefix off. -- kmcguire
    */
    self.MsgWrite8(CmdServerEncrypted)    // prefix encrypted command (doesnt really do anything)
}

// sends message to remote
func (self *ServerClient) MsgEnd() {
    // length does not consider the two vector fields
    l := self.msgbuf.Len() - (8 * 2)
    out := self.msgbuf.Bytes()

    hdr := []byte {byte(l >> 24), byte(l >> 16), byte(l >> 8), byte(l)} 

    self.conn.Write(hdr)
    self.conn.Write(out)
}

func Read16MSB(buf []byte, off uint32) (uint16) {
    return     (uint16(buf[off + 0]) << 8) | uint16(buf[off + 1])
}

func Read32MSB(buf []byte, off uint32) (uint32) {
    return (uint32(Read16MSB(buf, off + 0)) << 16) | uint32(Read16MSB(buf, off + 2))
}

func Read64MSB(buf []byte, off uint32) (uint64) {
    return (uint64(Read32MSB(buf, off + 0)) << 32) | uint64(Read32MSB(buf, off + 4))    
}

func (self *ServerClient) MsgWrite8(v uint8) {
    self.msgbuf.Write([]byte {v})
}

func (self *ServerClient) MsgWrite16MSB(v uint16) {
    self.msgbuf.Write([]byte {byte((v >> 8) & 0xff), byte(v & 0xff)})
}

func (self *ServerClient) MsgWrite32MSB(v uint32) {
    self.msgbuf.Write([]byte {byte(v >> 24 & 0xff), byte(v >> 16 & 0xff), byte(v >> 8 & 0xff), byte(v & 0xff)})
}

func (self *ServerClient) MsgWrite64MSB(v uint64) {
    self.MsgWrite32MSB(uint32(v >> 32))
    self.MsgWrite32MSB(uint32(v & 0xffffffff))
}

func (self *ServerClient) MsgWrite(b []byte) {
    self.msgbuf.Write(b)
}

func (self *ServerClient) MsgWriteString(b string) {
    self.msgbuf.WriteString(b)
}

func FileCopy(dst string, src string, move bool) error {
    in, err := os.Open(src)
    if err != nil { 
        return err 
    }
    defer in.Close()
    out, err := os.Create(dst)
    if err != nil {
        return err
    }
    defer out.Close()
    _, err = io.Copy(out, in)
    os.Remove(src)
    return err
}

func HashKmc(data []byte, max int) ([]byte) {
    var x      int
    var sz     int
    var seed   uint32
    var c      uint32

    seed = 0
    sz = len(data)
    for sz > max {
        c = 0
        for x = 0; x * 2 < sz; x++ {
            if x * 2 + 1 < sz {
                c = uint32(data[x * 2]) + uint32(data[x * 2 + 1]) + (uint32(x) * 2) + c + seed
                data[x] = byte(c)
            } else {
                seed = uint32(data[x * 2])
            }
        }
        sz = x
    }

    // return slice
    return data[0:sz]
}

/*
    This will process a message by executing what it commands 
    under the ServerClient context. 

    DEVELOPMENT: It will panic, but this is only to aid in debugging. In 
                 production version all panics will be removed and instead
                 it will be ensured that a failure code is sent to the client
                 and we can let the client do what ever it likes
*/
func (self *ServerClient) ProcessMessage(vector uint64, msg []byte) (err error) {
    var cmd            byte

    cmd = msg[0]
    
    // self.LoadAccountConfig("ok45JeXm3")

    switch (cmd) {
        case 11: // GetPublicKey
            panic("not impemented: GetPublicKey")
        case 12: // SetupCrypt
            panic("not impemented: SetupCrypt")
    }
    
    // encrypted check (must be of type encrypted)
    if cmd != 13 {
        // bad message obviously
        return fmt.Errorf("unknown message type (looking for encrypted)")
    }
    
    // get sub-type
    cmd = msg[1]
    msg = msg[2:]

    // check if login mesage
    if cmd == CmdClientLogin {
        // load account configuration
        self.config = self.server.LoadAccountConfig(string(msg))
        fmt.Printf("config:%p account:%s\n", self.config, string(msg))
        self.MsgStart(vector)
        self.MsgWrite8(CmdServerLoginResult)
        if self.config == nil {
            self.MsgWrite8('n')
            return
        }
        self.MsgWrite8('y')
        self.MsgEnd()
    }

    if self.config == nil {
        // oops.. either no login command issues or account was invalid
        // because we were unable to load the file or any other issue so
        // go ahead and terminate the connection here
        panic("client configuration not loaded")
    }

    switch (cmd) {
        case CmdClientDirList:
            metaSize := Read16MSB(msg, 0)
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg[8:]))
            //fmt.Printf("DirList:%s\n", path)
            nodes, err := ioutil.ReadDir(path)

            metaBuf := make([]byte, metaSize)

            self.MsgStart(vector)
            self.MsgWrite8(CmdServerDirList)
            if err != nil {
                // could not access directory because it does not exist.. or other things..
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }

            // write success code
            self.MsgWrite8(1)
            // write meta size we are using
            self.MsgWrite16MSB(metaSize)
            for _, n := range nodes {
                // write length of name
                self.MsgWrite16MSB(uint16(len(n.Name())))
                // write if directory or not
                if n.IsDir() {
                    self.MsgWrite8(1)
                } else {
                    self.MsgWrite8(0)
                }
                // consists of one byte repsenting succes or error
                // then the remaining bytes of what is considered
                // metadata
                if !n.IsDir() && metaSize > 0 {
                    fd, err := os.OpenFile(n.Name(), os.O_RDWR, 0)
                    if err == nil {
                        _, err := fd.Read(metaBuf)
                        if err == nil {
                            self.MsgWrite8(1)
                            self.MsgWrite(metaBuf)
                        } else {
                            self.MsgWrite8(0)
                            self.MsgWrite(metaBuf)
                        }
                        fd.Close()
                    } else {
                        self.MsgWrite8(0)
                        self.MsgWrite(metaBuf)
                    }
                } else {
                    // a directory has no meta-data so just
                    // set it as invalid but write some meta
                    // data just to fill the space and keep
                    // the protocol simple
                    if metaSize > 0 {
                        self.MsgWrite8(0)
                        self.MsgWrite(metaBuf)
                    }
                }
                // write name
                //self.MsgWrite([]byte(n.Name()))
                self.MsgWriteString(n.Name())
            }
            // send message to remote
            self.MsgEnd()
            return nil
        case CmdClientEcho:
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerEcho)
            self.MsgEnd()
            return nil
        case CmdClientFileRead:
            off := Read64MSB(msg, 0)
            rsz := Read64MSB(msg, 8)
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg[16:]))
            fo, err := os.OpenFile(path, os.O_RDWR, 0)
            defer fo.Close()
            if err != nil {
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            // TODO: might want to look at reusing the buffer
            //       to prevent loading the GC with garbage 
            //       that it will have to collect
            buf := make([]byte, rsz)
            fo.Seek(int64(off), 0)
            _, err = fo.Read(buf)
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileRead)
            if err != nil {
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            self.MsgWrite8(1)
            self.MsgWrite(buf)
            self.MsgEnd()
            return nil
        case CmdClientFileWrite:
            off := Read64MSB(msg, 0)
            fnamesz := Read16MSB(msg, 8)
            compression := byte(msg[10])
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg[11:11 + fnamesz]))
            fmt.Printf("write:%s\n", path)
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileWrite)
            if compression > 0 {
                panic("compression not implemented")
                //breader := bytes.NewReader(msg[11 + fnamesz:])
                //zreader, err := zlib.NewReader(breader)
                //if err != nil {
                //    self.MsgWrite8(0)
                //    self.MsgEnd()
                //    break
                //}
                // set msg to output
                //zreader.Read(msg)
            } else {
                // create slice
                msg = msg[11 + fnamesz:]
            }
            // c:\Users\kmcguire\Desktop\armos\sortix_0.8_i486.iso
            // redundant check.. just let os.OpenFile fail..
            //if _, _err := os.Stat(path); _err != nil {
            //    panic("write to non-existant file")
            //    self.MsgWrite8(0)
            //    self.MsgEnd()
            //    return nil
            //}

            fo, err := os.OpenFile(path, os.O_RDWR, 0700)
            defer fo.Close()
            if err != nil {
                panic(fmt.Sprintf("error opening path (%s)", err))
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }

            // disallow writes past end of file
            csz, err := fo.Seek(0, 2)
            if (uint64(off) + uint64(len(msg))) > uint64(csz) {
                panic(fmt.Sprintf("error: writing past end of file off:%x len(msg):%x csz:%x", off, len(msg), csz))
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }

            fo.Seek(int64(off), 0)
            // write the data to the file at the specified offset
            fo.Write(msg)

            // just reset the file so its the oldest of the old, this
            // protects the file from having a recent timestamp but not
            // actually being fully updated.. if a file is left with
            // this time it is because the client bugged out or crashed
            // and could not finish the job so the next pass the client
            // makes will consider this file old and update it either by
            // uploading or patching (client's decision); i really hate
            // how this might cost a lot of CPU time maybe.. but i see
            // no other way to do it and maintain the file to being
            // seen as out of date when a time request is issued
            os.Chtimes(path, time.Unix(0, 0), time.Unix(0, 0))
            self.MsgWrite8(1)
            self.MsgEnd()
            return nil
        case CmdClientFileSize:
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg))
            stat, err := os.Stat(path)
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileSize)    // reply
            if err != nil || stat == nil {
                // path is not accessible for whatever reason
                self.MsgWrite8(0)                    // failure code
                self.MsgWrite64MSB(0)                // size
                self.MsgEnd()
                return nil
            }
            // return the file size in a reply message
            self.MsgWrite8(1)
            self.MsgWrite64MSB(uint64(stat.Size()))
            self.MsgEnd()
            return nil
        case CmdClientFileTrun:
            var cfsz        int64

            sz := Read64MSB(msg, 0)
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg[8:]))
            fmt.Printf("trun:(%d):%s\n", sz, path)
            stat, err := os.Stat(path)
            fmt.Printf("stat:%p err:%p\n", stat, err)
            if err != nil {
                base := path[0:strings.LastIndex(path, "/")]
                // try to make the directory path just to be sure
                os.MkdirAll(base, 0700)
                // create the file
                fo, err := os.OpenFile(path, os.O_RDWR | os.O_CREATE, 0700)
                defer fo.Close()
                if err != nil {
                    panic(fmt.Sprintf("during trun: %s", err))
                }
                cfsz = 0
            } else {
                cfsz = stat.Size()
            }

            // enforce quota (if file even exists)
            fmt.Printf("SpaceUsed:%x cfsz:%x sz:%x SpaceQuota:%x\n", self.config.SpaceUsed(0), cfsz, sz, self.config.SpaceQuota(0))
            if (self.config.SpaceUsed(0) - cfsz) + int64(sz) > self.config.SpaceQuota(0) {
                panic("quota exceeded")
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            err = os.Truncate(path, int64(sz))
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileTrun)
            // check for error condition first
            if err != nil {
                panic(fmt.Sprintf("truncate: failed on %s (%s)", path, err))
                self.MsgWrite8(0)            // failure code
                self.MsgEnd()
                return nil
            }
           	// decrement the amount of space used by old size
            if stat != nil {
                self.config.SpaceUsed(-stat.Size())
            }
            // increment the amount of space used by new size
            self.config.SpaceUsed(int64(sz))
            self.MsgWrite8(1)
            self.MsgEnd()
            return nil
        case CmdClientFileDel:
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg))
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileDel)
			stat, err := os.Stat(path)
			if err != nil {
				self.MsgWrite8(0)
				self.MsgEnd()
				return nil
			}
            err = os.RemoveAll(path)
            if err != nil {
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            // the removal was a success now see if the directory
            // that contained this file or directory is empty and
            // if so let us delete the base directory
            base := path[0:strings.Index(path, "/")]
            nodes, err := ioutil.ReadDir(base)
            if len(nodes) < 1 {
                // just ignore any error for now
                os.RemoveAll(base)
            }
            // adjust space used to account for deleted file
            self.config.SpaceUsed(-stat.Size())
            self.MsgWrite8(1)
            self.MsgEnd()
            return nil
        case CmdClientFileCopy:
            srclen := Read16MSB(msg, 0)
            src := string(msg[2:2 + srclen])
            dst := string(msg[2 + srclen:])
            stat, err := os.Stat(src)
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileCopy)
            if err != nil {
            	self.MsgWrite8(0)
            	self.MsgEnd()
            	return nil
            }
            err = FileCopy(dst, src, false)
            if err != nil {
            	self.MsgWrite8(0)
            	self.MsgEnd()
            	return nil
            }
            self.config.SpaceUsed(stat.Size())
            self.MsgWrite8(1)
            self.MsgEnd()
            return nil
        case CmdClientFileMove:
            srclen := Read16MSB(msg, 0)
            src := string(msg[2:2 + srclen])
            dst := string(msg[2 + srclen:])

            err := FileCopy(dst, src, true)
            if err != nil {
            	self.MsgWrite8(0)
            	self.MsgEnd()
            	return nil
            }

            self.MsgStart(vector)
            self.MsgWrite8(1)
            self.MsgEnd()
            return nil
        case CmdClientFileHash:
            off := Read64MSB(msg, 0)
            rsz := Read64MSB(msg, 8)
            if rsz > 1024 * 1024 * 128 {
                self.MsgStart(vector)
                self.MsgWrite8(CmdServerFileHash)
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }

            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg[16:]))
            fo, err := os.OpenFile(path, os.O_RDWR, 0)
            defer fo.Close()
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileHash)
            if err != nil {
                panic(fmt.Sprintf("during hash error:%s", err))
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            // TODO: might want to look at reusing the buffer
            //       to prevent loading the GC with garbage 
            //       that it will have to collect

            buf := make([]byte, rsz)
            fo.Seek(int64(off), 0)
            cnt, err := fo.Read(buf)
            if err != nil {
                fmt.Printf("read failed on [%s] at [%x] for sz:%x with [%s]\n", path, off, rsz, err)
                panic(fmt.Sprintf("during hash error:%s", err))
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            fmt.Printf("buf[0]:%x cnt:%x\n", buf[0], cnt)
            // hash
            buf = HashKmc(buf, 128)
            self.MsgWrite8(1)
            self.MsgWrite(buf)
            self.MsgEnd()
            fmt.Printf("hash:%s:%x:%x\n", path, off, rsz)
            return nil
        case CmdClientFileTime: 
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg))
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileTime)
            stat, err := os.Stat(path)
            if err != nil {
                self.MsgWrite64MSB(0)
                self.MsgEnd()
                return nil
            }
            self.MsgWrite64MSB(uint64(stat.ModTime().Unix()))
            self.MsgEnd()
            return nil
        case CmdClientFileSetTime: 
            atime := Read64MSB(msg, 0)
            mtime := Read64MSB(msg, 8)
            path := fmt.Sprintf("%s/%s", self.config.DiskPath, string(msg[16:]))

            fmt.Printf("path:%s atime:%d mtime:%d\n", path, atime, mtime)

            err := os.Chtimes(path, time.Unix(int64(atime), 0), time.Unix(int64(mtime), 0))
            self.MsgStart(vector)
            self.MsgWrite8(CmdServerFileSetTime)
            if err != nil {
                panic(fmt.Sprintf("error setting time (%s)", err))
                self.MsgWrite8(0)
                self.MsgEnd()
                return nil
            }
            self.MsgWrite8(1)
            self.MsgEnd()
            return nil
    }
    
    return nil
}

func (self *ServerClient) Finalize() {
    // decrement the ref count on account configuration object
    // so that it can be unload and dumped to disk
    if self.config != nil {
        self.server.FinalizeAccountConfig(self.config)
    }
}

// handles a single client connection
func (self *ServerClient) ClientEntry(conn net.Conn) {
    var buf            []byte
    var btop        uint32
    var err            error
    var count        int
    var vector        uint64
    var msg            []byte

    // extra 128 bytes for header
    const maxmsgsz  uint32 = 1024 * 1024 * 4 + 128
    
    defer self.Finalize()

    f, _ := os.Create("prof")
   	//pprof.StartCPUProfile(f)
    //defer pprof.StopCPUProfile()
    defer pprof.WriteHeapProfile(f)
    defer func () {
        // prevent panic from shutting entire server down
        p := recover()
        fmt.Printf("error: %s\n", p)
    } ()
    defer conn.Close()

    self.conn = conn

    // message buffer
    buf = make([]byte, maxmsgsz)
    btop = 0

    // loop
    for {
        // read data from connection
        count, err = conn.Read(buf[btop:])
        if count == 0 {
            // connection is dropped (just exit)
            fmt.Printf("btop:%x cap(buf):%x len(buf):%x\n", btop, cap(buf), len(buf))
            fmt.Printf("client connection dropped (%s)\n", err)
            conn.Close()
            return
        }
        //fmt.Printf("read bytes (%d)\n", count)
        
        btop = btop + uint32(count)
        
        // message fetch loop
        for vector, msg, btop, err = self.getMessageFromBuffer(buf, btop, maxmsgsz); 
            msg != nil && err == nil; 
            vector, msg, btop, err = self.getMessageFromBuffer(buf, btop, maxmsgsz) {
            // process message
            self.ProcessMessage(vector, msg)
        }
    }
    return
}

// create a ServerClient object
func (self *Server) NewClient() (sc *ServerClient) {
    sc = new(ServerClient)
    sc.server = self
    sc.vector = 0
    sc.msgbuf = new(bytes.Buffer)
    return
}

// called by ServerClient to load/get account configuration
func (self *Server) LoadAccountConfig(account string) (*AccountConfig) {
    // check if it is already loaded
    //ioutil.ReadFile(filename) ([]byte, error)
    var config            *AccountConfig

    // make sure it is unlocked on function exit or panic
    defer self.accountConfigsLock.Unlock()

    // try to lock
    self.accountConfigsLock.Lock()
    
    if _, ok := self.accountConfigs[account]; !ok {
        // load configuration from disk if it can be found
        data, err := ioutil.ReadFile(fmt.Sprintf("./accounts/%s", account))
        if err != nil {
            // an error occured trying to load the config
            return nil
        }
        // break data into lines and then parse each line
        lines := bytes.Split(data, []byte {10})

        config = new(AccountConfig)

        config.lock = &sync.Mutex{}
        config.AccountName = account
        
        for index := range lines {
            // trip off white space and line endings
            line := bytes.Trim(lines[index], "     \n\r")
            fmt.Printf("line:%s\n", line)
            // break into key and value pair
            colon := bytes.IndexByte(line, 58)
            if colon < 0 {
                continue
            }
            key := string(bytes.Trim(line[0:colon], "     \n\r"))
            val := string(bytes.Trim(line[colon + 1:], "     \n\r"))
            // store value properly.. if known
            switch (key) {
                case "DiskPath":
                    config.DiskPath = val
                case "SpaceQuota":
                    nval, err := strconv.ParseInt(val, 10, 64)
                    if err != nil {
                        fmt.Printf("value %s for account config key [%s] is not an integer!\n", val, key)
                    } else {
                        config.SpaceQuota(nval)
                    }
                case "SpaceUsed":
                    nval, err := strconv.ParseInt(val, 10, 64)
                    if err != nil {
                        fmt.Printf("value [%s] for account config key [%s] is not an integer!\n", val, key)
                    } else {
                        config.SpaceUsed(nval)
                    }
                case "SpacePerFile":
                    nval, err := strconv.ParseInt(val, 10, 64)
                    if err != nil {
                        fmt.Printf("value [%s] for account config key [%s] is not an integer!\n", val, key)
                    } else {                    
                        config.SpacePerFile(nval)
                    }
                case "SpacePerDir":
                    nval, err := strconv.ParseInt(val, 10, 64)
                    if err != nil {
                        fmt.Printf("value [%s] for account config key [%s] is not an integer!\n", val, key)
                    } else {
                        config.SpacePerDir(nval)
                    }
                default:
                    fmt.Printf("unknown key in account configurtion as [%s]\n", key)
            }
        }

        self.accountConfigs[account] = config
    } else {
        config = self.accountConfigs[account]
    }
    
    config.RefCount++

    return config
}

// writes account configuration to disk
func (self *Server) FlushAccountConfig(config *AccountConfig) {
    // convert members to string
    outstr := fmt.Sprintf("SpaceQuota: %d\nSpaceUsed: %d\nSpacePerFile: %d\nSpacePerDir: %d\nDiskPath: %s\n", config.SpaceQuota(0), config.SpaceUsed(0), config.SpacePerFile(0), config.SpacePerDir(0), config.DiskPath)
    // convert to bytes
    out := []byte(outstr)

    // write to disk
    ioutil.WriteFile(fmt.Sprintf("./accounts/%s", config.AccountName), out, 0700)
}

// decrement reference count and flush to disk if no more references
func (self *Server) FinalizeAccountConfig(config *AccountConfig) {
    // make sure it is unlocked on function exit or panic
    defer self.accountConfigsLock.Unlock()

    // try to lock
    self.accountConfigsLock.Lock()

    config.RefCount--

    // if no more references then flush to disk and set to be collected
    if config.RefCount < 1 {
        // remove from map
        delete(self.accountConfigs, config.AccountName)
        // flush to disk
        self.FlushAccountConfig(config)
    }
}

// starts a server and will not return
func (self *Server) ServerEntry(psignal chan uint32) {
    var sc                *ServerClient
    var cert            tls.Certificate
    var config            tls.Config
    
    fmt.Println("Server Started")
    
    // signal caller we are ending
    defer func () { psignal <- 0 } ()

    self.accountConfigsLock = &sync.Mutex{}
    self.accountConfigs = make(map[string]*AccountConfig)

    fmt.Printf("loading certificate\n")
    cert, err := tls.LoadX509KeyPair("cert.pem", "cert.pem")
    fmt.Printf("creating config\n")
    config = tls.Config{Certificates: []tls.Certificate {cert}, InsecureSkipVerify: true}
    
    config.ServerName = "kmcg3413.net"
    
    // create a listening socket
    fmt.Printf("creating listener\n");
    ln, err := tls.Listen("tcp", ":4323", &config)
    
    if err != nil {
        fmt.Printf("Error: %s\n", err)
        return
    }
    
    if ln == nil {
        fmt.Println("There was an error creating the NET/TLS listener.")
        return
    }
    
    fmt.Printf("ready for connections\n")
    // handle connections
    for {
        conn, err := ln.Accept()
        
        if err != nil {
            fmt.Printf("accept-error: %s\n", err)
            continue
        }
        
        if conn == nil {
            fmt.Printf("accept-error: %s\n", err)
            continue
        }
        
        fmt.Printf("new client accepted\n")
        sc = self.NewClient()
        go sc.ClientEntry(conn)
    }

    return
}