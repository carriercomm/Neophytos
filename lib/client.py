import os
import sys
import socket
import struct
import hashlib
import math
import threading
import zlib
import ssl
import traceback
import base64
import select

from io import BytesIO
from ctypes import *

from lib import output
from lib import pubcrypt
from lib.pkttypes import *
from lib.misc import *

class UnknownMessageTypeException(Exception):
    pass

class QuotaLimitReachedException(Exception):
    pass
    
class ConnectionDeadException(Exception):
    pass
    
class BadLoginException(Exception):
    pass
        
class Client:
    FileHeaderReserve        = 32

    class IOMode:
        Block         = 1        # Wait for the results.
        Async         = 2        # Return, and will check for results.
        Callback     = 3        # Execute callback on arrival.
        Discard        = 4        # Async, but do not keep results.
        
    def __init__(self, rhost, rport, aid, sformat):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.keepresult = {}
        self.callback = {}
        self.vector = 0
        self.rhost = rhost
        self.rport = rport
        self.aid = aid
        self.sockreadgate = threading.Condition()
        self.socklockread = threading.Lock()
        self.socklockwrite = threading.Lock()
        self.bytesout = 0                    # includes just actual data bytes
        self.bytesoutst = time.time()
        self.bz2compression = 0
        self.allbytesout = 0                # includes control bytes and data
        self.workerfailure = False
        self.workeralivecount = 0
        self.lasttitleupdated = 0
        self.workerpool = None
        self.workpool = None

        # enable or disable stash/revision format
        self.revformat = sformat

        # determine if we are running in 32-bit or 64-bit mode
        is64 = sys.maxsize > 2 ** 32

        # load library appropriate for the operating system, if the
        # system is not supported we will use our Python implemented
        # although it is *much* slower..
        if sys.platform.find('linux') > -1:
            self.hentry = None
            # linux supports two architectures the x86 and x86_64
            if is64:
                libpath = './lib/hasher/hasher64.so'
            else:
                libpath = './lib/hasher/hasher32.so'

            if os.path.exists(libpath):
                try:
                    self.hdll = cdll.LoadLibrary(libpath)
                    self.hentry = CFUNCTYPE(c_int)(('hash', self.hdll))
                except:
                    print('WARNING: FAILED LOADING SHARED LIBRARY')
        else:
            print('WARNING: NATIVE HASH LIBRARY NOT SUPPORTED (EXPECT SLOW HASHING)')
        
        self.lastpushedlfile = ''
        
        self.conntimeout = 60
        self.lastactivity = time.time()
        
        self.data = BytesIO()
        self.datasz = None
        self.datatosend = []
        self.bytestosend = 0
        
        self.dbgl = time.time()
        self.dbgv = 0
        self.dbgc = 0
    
    def SetRevFormat(self, b):
        self.revformat = b

    def Shutdown(self):
        self.sock.close()
    
    def close(self):
        self.sock.close()
    
    def Connect(self, essl = False):
        # try to establish a connection
        if essl:
            self.sock = ssl.wrap_socket(self.sock, ciphers = 'RC4')
        
        if essl:
            self.sock.connect((self.rhost, self.rport + 1))
            output.SetTitle('ssl-cipher', self.sock.cipher())
        else:
            self.sock.connect((self.rhost, self.rport))
        
        self.ssl = essl
        
        if not self.ssl:
            # get public key
            vector = self.WriteMessage(struct.pack('>B', ClientType.GetPublicKey), Client.IOMode.Async)
            s, v, pubkey = self.HandleMessages(lookfor = vector)
            type, esz = struct.unpack_from('>BH', pubkey)
            e = pubkey[3:3 + esz]
            p = pubkey[3 + esz:]
            self.pubkey = (e, p)
            # kinda been disabled... but still left in
            key = IDGen.gen(10)
            self.crypter = SymCrypt(key)
            self.WriteMessage(struct.pack('>B', ClientType.SetupCrypt) + key, Client.IOMode.Discard)

        data = struct.pack('>B', ClientType.Login) + self.aid
        vector = self.WriteMessage(data, Client.IOMode.Async)
        result = self.HandleMessages(lookfor = vector)
        
        # initialize the time we starting recording the number of bytes sent
        self.bytesoutst = time.time()
        if result:
            return True
        else:
            raise BadLoginException()

    def GetStoredMessage(self, vector):
        with self.socklockread:
            if vector in self.keepresult and self.keepresult[vector] is not None:
                ret = self.keepresult[vector]
                del self.keepresult[vector]
                return ret
        return None
    
    def waitCount(self):
        return len(self.keepresult) + len(self.callback)

    def dbgdump(self):
        for v in self.keepresult:
            print('keepresult:%s' % v)
        for v in self.callback:
            print('callback:%s' % v)
    
    # processes any incoming messages and exits after specified time
    def HandleMessages(self, lookfor = None):
        # TODO: we are modifying a dictionary with out holding a lock for it...
        while not self.socklockread.acquire(False):
            # check if vector has arrived
            if lookfor in self.keepresult and self.keepresult[lookfor] is not None:
                # okay return it and release the lock
                ret = self.keepresult[lookfor]
                # remove it
                del self.keepresult[lookfor]
                return ret
            # sleep for a bit then check again
            time.sleep(0.001)

        while True:
            sv, v, d = self.ReadMessage()
            # if no more messages..
            if sv is None:
                # if not looking for a message..
                if lookfor is None:
                    break
                # if looking for a specific reply then
                # let us block and wait for a message
                # to arrive or we can send anything out
                # if needed
                print('looking for.. blocking on select')
                if self.getBytesToSend() > 0:
                    w = [self.sock]
                else:
                    w = []
                r, w, e = select.select([self.sock], w, [self.sock], 1)
                print(r, w, e)
                if w:
                    # send any data while waiting if buffered up
                    self.send()
                continue
            msg = self.ProcessMessage(sv, v, d)
            # BLOCK
            if lookfor == v:
                if v in self.keepresult:
                    del self.keepresult[v]
                self.socklockread.release()
                return msg
            # ASYNC
            if v in self.keepresult:
                self.keepresult[v] = msg
            # CALLBACK
            if v in self.callback:
                cb = self.callback[v]
                del self.callback[v]
                cb[0](cb[1], msg, v)
            # DISCARD (do nothing)
            continue
        self.socklockread.release()
        return
    
    # processes any message and produces output in usable form
    def ProcessMessage(self, svector, vector, data):
        type = data[0]
        
        #print('got type %s' % type)
        
        # only process encrypted messages
        if type != ServerType.Encrypted:
            #print('NOT ENCRYPTED')
            return None
            
        # decrypt message (drop off encrypted type field)
        if False and not self.ssl:
            #print('DECRYPTING')
            data = self.crypter.decrypt(data[1:])
        else:
            #print('NOT DECRYPTING')
            data = data[1:]
            
        type = data[0]
        data = data[1:]

        # set compression level (can be sent by server at any time
        # and client does not *have* to respect it, but the server
        # could kick the client off if it did not)
        if type == ServerType.SetCompressionLevel:
            self.bz2compression = data[0]
            return
        # process message based on type
        if type == ServerType.LoginResult:
            if data[0] == ord('y'):
                return True
            return False
            
        if type == ServerType.DirList:
            result = struct.unpack_from('>B', data)[0]
            
            # path could not be accessed
            if result == 0:
                return None
            
            data = data[1:]

            list = []
            while len(data) > 0:
                # parse header
                fnamesz, ftype = struct.unpack_from('>HB', data)
                # grab out name
                fname = data[3: 3 + fnamesz]
                # decode it back to what we expect
                fname = self.FSDecodeBytes(fname)
                # chop off part we just read
                data = data[3 + fnamesz:]
                # build list
                list.append((fname, ftype))
            # return list
            return list
        if type == ServerType.FileTime:
            return struct.unpack_from('>Q', data)[0]
        if type == ServerType.FileRead:
            return (struct.unpack_from('>B', data)[0], data[1:])
        if type == ServerType.FileWrite:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.FileSize:
            return struct.unpack_from('>BQ', data)
        if type == ServerType.FileTrun:
            code = struct.unpack_from('>B', data)[0]
            # this is a special situation where they have reached their quota
            if code == 9:
                # i want to force this to be handled which is unhandled
                # should terminate the client ending the push to the server
                # which will get the users attention; do not want this to
                # end up silently happening and the users not noticing or
                # the developer who modified the client accidentally ignoring
                # it since it is an issue that needs to be addressed
                print('WARNING: QUOTA LIMIT REACHED THROWING EXCEPTION')
                raise QuotaLimitReachedException()
            return code
        if type == ServerType.FileDel:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.FileCopy:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.FileMove:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.FileHash:
            return (struct.unpack_from('>B', data)[0], data[1:])
        if type == ServerType.FileStash:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.Echo:
            return True
        if type == ServerType.FileSetTime:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.FileGetStashes:
            parts =  data.split('.')
            out = []
            for part in parts:
                out.append(int(part))
            return out
        raise UnknownMessageTypeException('%s' % type)
    
    def ifDead(self):
        tdelta = (time.time() - self.lastactivity)
        if tdelta > self.conntimeout:
            raise ConnectionDeadException()
    
    def recv(self, sz):
        data = self.data

        self.sock.settimeout(0)
        try:
            _data = self.sock.recv(4096)
            if not _data:
                raise ConnectionDeadException()
            data.write(_data)
        except Exception as e:
            # TODO: improve this.. what if socket died?
            pass

        # only return with data if its of the specified length
        if data.tell() >= sz:
            # read out the data
            data.seek(0)
            _data = data.read(sz)
            self.data = BytesIO()
            self.data.write(data.read())
            return _data
        return None
    
    # read a single message from the stream and exits after specified time
    def ReadMessage(self, timeout = 0):
        self.sock.settimeout(timeout)
        
        # if no size set then we need to read the header
        if self.datasz is None:
            data = self.recv(4 + 8 + 8)
            if data is None:
                return None, None, None
            sz, svector, vector = struct.unpack('>IQQ', data)
            self.datasz = sz
            self.datasv = svector
            self.datav = vector
        
        # try to read the remaining data
        data = self.recv(self.datasz)
        if data is None:
            # not enough data read
            return None, None, None
        
        # ensure the next reads tries to get the header
        self.datasz = None

        print('M', end='')
        # return the data
        return self.datasv, self.datav, data
        
    def WriteMessage(self, data, mode, callback = None):
        with self.socklockwrite:
            vector = self.vector
            self.vector = self.vector + 1
        
        # get type
        type = data[0]
        
        # leave get public key and setup crypt unaltered
        if type == ClientType.GetPublicKey:
            # do not encrypt at all
            pass
        else:
            if type == ClientType.SetupCrypt:
                # public key crypt
                if not self.ssl:
                    data = data[0:1] + pubcrypt.crypt(data[1:], self.pubkey)
            else:
                # if not SSL then use our built-in encryption
                if False and not self.ssl:
                    data = bytes([ClientType.Encrypted]) + self.crypter.crypt(data)
                else:
                    # we just pretend its encrypted when really its not, however
                    # since we are using SSL the individual messages are not encrypted
                    # but the entire socket stream is.. so just prepend this header
                    
                    # lets encryption the login if we are not using SSL
                    if not self.ssl and type == ClientType.Login:
                        data = data[0:1] + pubcrypt.crypt(data[1:], self.pubkey)
                    data = bytes([ClientType.Encrypted]) + data
        
        # lock to ensure this entire message is placed
        # into the stream, then unlock so any other
        # thread can also place a message into the stream
        #print('waiting at write lock')
        with self.socklockwrite:
            #print('inside write lock')
            # setup to save message so it is not thrown away
            if mode == Client.IOMode.Callback:
                self.callback[vector] = callback
            if mode == Client.IOMode.Async:
                self.keepresult[vector] = None
         
            print('S', end='')   
            self.send(struct.pack('>IQ', len(data), vector))
            self.send(data)
            # track the total bytes out
            self.allbytesout = self.allbytesout + 4 + 8 + len(data)
            #print('sent data for vector:%s' % vector)
            
        if mode == Client.IOMode.Block:
            #print('blocking by handling messages')
            #print('blocking for vector:%s' % vector)
            res = self.HandleMessages(None, lookfor = vector)
            #print('    returned with res:%s' % (res,))
            return res
        return vector
    
    def canSend(self):
        return len(self.datatosend) > 0
    
    def getBytesToSend(self):
        return self.bytestosend
    
    def handleOrSend(self, lookfor = None):
        # wait until the socket can read or write
        read, write, exp = select.select([self.sock], [self.sock], [])

        if read:
            # it will block by default so force
            # it to not block/wait
            self.HandleMessages(lookfor = lookfor)
        if write:
            # dump some of the buffers if any
            self.send()
    
    def send(self, data = None, timeout = 0):
        if data is not None:
            self.datatosend.append(data)
            self.bytestosend = self.bytestosend + len(data)
        
        self.sock.settimeout(timeout)
        
        # check there is data to send
        while len(self.datatosend) > 0:
            # pop from the beginning of the queue
            data = self.datatosend.pop(0)
            
            # try to send it
            totalsent = 0
            while totalsent < len(data):
                try:
                    sent = self.sock.send(data[totalsent:])
                except socket.error:
                    # non-ssl socket likes to throw this exception instead
                    # of returning zero bytes sent it seems
                    self.datatosend.insert(0, data[totalsent:])
                    return False
                
                if sent == 0:
                    # place remaining data back at front of queue and
                    # we will try to send it next time
                    self.datatosend.insert(0, data[totalsent:])
                    return False
                #print('@sent', sent)
                totalsent = totalsent + sent
            self.bytestosend = self.bytestosend - totalsent
        return True
    
    '''
        The client can use any format of a path, but in order to support
        file stashing and any characters in the path we convert it into
        a stashing format and encode the parts. Therefore it makes it possible
        to use any character for a directory name or file name. This function
        however reserves the character `/` and `\x00` as special and neither
        are usable as an or part of a file or directory name.
        
        You can freely reimplement this method as long as the server supports
        the characters you use. The output of the base 64 encoded shall always
        be supported by the server for directory and file names.
    '''
    def GetServerPathForm(self, path):
        # 1. prevent security hole (helps reduce server CPU load if these exist)
        while path.find(b'..') > -1:
            path = path.replace(b'..', b'.')
        # remove duplicate path separators
        while path.find(b'//') > -1:
            path = path.replace(b'//', b'/')
        # if not using revision format then dont 
        if not self.revformat:
            return path
        # 2. convert entries into stash format
        parts = path.split(b'/')
        _parts = []
        for part in parts:
            if len(part) == 0:
                continue
            # see if it is already in stash format
            if part.find(b'\x00') < 0:
                # convert into stash format
                part = b'0.' + part
            else:
                # replace it with a dot
                part = part.replace(b'\x00', b'.')
            # 3. encode it (any stash value can be used)
            part = self.FSEncodeBytes(part)
            _parts.append(part)
        path = b'/'.join(_parts)
        return path
        
    def FSEncodeBytes(self, s):
        out = []
        
        valids = (
            (ord('a'), ord('z')),
            (ord('A'), ord('Z')),
            (ord('0'), ord('9')),
        )
        
        dotord = ord('.')
        dashord = ord('-')
        uscoreord = ord('_')
        
        for c in s:
            was = False
            for valid in valids:
                if c >= valid[0] and c <= valid[1]:
                    was = True
                    break
            if was or c == dotord or c == dashord or c == uscoreord:
                out.append(c)
                continue
            # encode byte value as %XXX where XXX is decimal value since
            # i think it is faster to decode the decimal value than a hex
            # value even though the hex will look nicer
            out.append(ord('%'))
            v = int(c / 100)
            out.append(ord('0') + v)
            c = c - (v * 100)
            v = int(c / 10)
            out.append(ord('0') + v)
            c = c - (v * 10)
            out.append(ord('0') + c)
        
        return bytes(out)
                            
    def FSDecodeBytes(self, s):
        out = []
        
        x = 0
        po = ord('%')
        while x < len(s):
            c = s[x]
            if c != po:
                out.append(c)
                x = x + 1
                continue
            zo = ord('0')
            v = (s[x + 1] - zo) * 100 + (s[x + 2] - zo) * 10 + (s[x + 3] - zo) 
            out.append(v)
            x = x + 4
        
        return bytes(out)
        
    def DirList(self, dir, mode, callback = None):
        dir = self.GetServerPathForm(dir)
        return self.WriteMessage(struct.pack('>B', ClientType.DirList) + dir, mode, callback)
    def FileRead(self, fid, offset, length, mode, callback = None):
        _fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileRead, offset, length) + _fid, mode, callback)
    def FileWrite(self, fid, offset, data, mode, callback = None):
        if self.bz2compression > 0:
            data = zlib.compress(data, self.bz2compression)
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>BQHB', ClientType.FileWrite, offset, len(fid), self.bz2compression) + fid + data, mode, callback)
    def FileSetTime(self, fid, atime, mtime, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileSetTime, atime, mtime) + fid, mode, callback)
    def FileSize(self, fid, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>B', ClientType.FileSize) + fid, mode, callback)
    def FileTrun(self, fid, newsize, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>BQ', ClientType.FileTrun, newsize) + fid, mode, callback)
    def Echo(self, mode, callback = None):
        return self.WriteMessage(struct.pack('>B', ClientType.Echo), mode, callback)
    def FileDel(self, fid, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>B', ClientType.FileDel) + fid, mode, callback)
    def FileCopy(self, srcfid, dstfid, mode, callback = None):
        srcfid = self.GetServerPathForm(srcfid)
        dstfid = self.GetServerPathForm(dstfid)
        return self.WriteMessage(struct.pack('>BH', ClientType.FileCopy, len(srcfid)) + srcfid + dstfid, mode, callback)
    def FileMove(self, srcfid, dstfid, mode, callback = None):
        srcfid = self.GetServerPathForm(srcfid)
        dstfid = self.GetServerPathForm(dstfid)
        return self.WriteMessage(struct.pack('>BH', ClientType.FileMove, len(srcfid)) + srcfid + dstfid, mode, callback)
    def FileHash(self, fid, offset, length, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileHash, offset, length) + fid, mode, callback)
    def FileTime(self, fid, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>B', ClientType.FileTime) + fid, mode, callback)
    def HashKmc(self, data, max):
        #out = create_string_buffer(w * h * 2)
        if self.hentry is not None:
            sz = self.hentry(c_char_p(data), c_uint(len(data)), max)
            return data[0:sz]

        data = list(data)

        seed = 0
        sz = len(data)
        while sz > max:
            out = []

            x = 0
            c = 0
            while x * 2 < sz:
                if x * 2 + 1 < sz:
                    # get inputs
                    a = data[x * 2 + 0]
                    b = data[x * 2 + 1]
                    # perform computation
                    c = a + b + (x * 2) + c + seed
                    # throw back into list
                    data[x] = c & 0xff
                else:
                    # save for new seed
                    seed = data[x]
                x = x + 1
            sz = x
        return bytes(data[0:sz])

class Client2(Client):
    def __init__(self, rhost, rport, aid, sformat):
        Client.__init__(self, rhost, rport, aid, sformat)