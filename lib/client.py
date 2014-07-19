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

import lib.flycatcher as flycatcher
logger = flycatcher.getLogger('client')

'''
    See to8byte7bit.
'''
def from8byte7bit(data):
    val = 0
    x = 7
    y = 0
    while x > -1:
        val |= (data[y] & 0x7f) << (7 * x)
        x = x - 1
        y = y + 1
    return val

'''
    This stores a 56-bit integer into 8 bytes
    using only 7 lower bits of each byte and
    setting the 7th (most significant bit) to
    one to prevent any byte from being zero
'''
def to8byte7bit(val):
    out = []
    for x in range(7, -1, -1):
        out.append(((val >> (x * 7)) & 0x7f) | 0x80)
    return bytes(out)

class UnknownMessageTypeException(Exception):
    pass

class QuotaLimitReachedException(Exception):
    pass
    
class ConnectionDeadException(Exception):
    pass
    
class BadLoginException(Exception):
    pass

class MaxMessageSizeException(Exception):
    pass
        
class Client:
    class IOMode:
        Block          = 1        # Wait for the results.
        Async          = 2        # Return, and will check for results.
        Callback       = 3        # Execute callback on arrival.
        Discard        = 4        # Async, but do not keep results.
        
    def __init__(self, rhost, rport, aid, metasize = 128):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.keepresult = {}
        self.callback = {}
        self.vector = 0
        self.rhost = rhost
        self.rport = rport
        self.aid = aid
        self.socklockread = threading.RLock()
        self.socklockwrite = threading.RLock()
        self.bz2compression = 0                 # not really used anymore
        self.maxmsgsz = 1024 * 1024 * 4

        if metasize is None:
            metasize = 128
        self.metasize = metasize

        # determine if we are running in 32-bit or 64-bit mode
        is64 = sys.maxsize > 2 ** 32


        # REPLACE THIS USING LIB/LIBLOAD MODULE!!
        # load library appropriate for the operating system, if the
        # system is not supported we will use our Python implementation
        # although it is *much* slower..
        self.hentry = None
        if sys.platform.find('linux') > -1:
            self.hentry = None
            # standard linux (x86 and x86_64)
            if is64:
                libpath = './lib/native/native64.so'
            else:
                libpath = './lib/native/native32.so'

            if os.path.exists(libpath):
                try:
                    self.hdll = cdll.LoadLibrary(libpath)
                    #self.hentry = CFUNCTYPE(c_int)(('hash', self.hdll))
                    self.hentry = self.hdll['hash']
                except Exception as e:
                    logger.warm('%s' % e)
                    logger.warn('WARNING: FAILED LOADING SHARED LIBRARY')
            else:
                logger.warn('WARNING: MISSING SHARED LIBRARY AS "%s" (REVERTING TO PURE PYTHON)' % libpath)
        elif sys.platform.find('win') > -1:
            # windows nt (x86 and x86_64)
            if is64:
                libpath = './lib/native/native64.dll'
            else:
                libpath = './lib/native/native32.dll'

            if os.path.exists(libpath):
                try:
                    self.hdll = windll.LoadLibrary(libpath)
                    #self.hentry = self.hdll['hash']
                    self.hentry = CFUNCTYPE(c_int)(('hash', self.hdll))
                except Exception as e:
                    logger.warm('%s' % e)
                    logger.warn('WARNING: FAILED LOADING DLL')
            else:
                logger.warn('WARNING: MISSING DLL AS "%s" (REVERTING TO PURE PYTHON)' % libpath)
        else:
            logger.warn('WARNING: NATIVE LIBRARY NOT SUPPORTED')
        
        self.lastpushedlfile = ''
        
        self.conntimeout = 60
        self.lastactivity = time.time()
        
        self.data = BytesIO()
        self.datasz = None
        self.datatosend = []
        self.bytestosend = 0
        
        self.bytesout = 0                   # just data out
        self.allbytesout = 0                # control and data out
        self.bytesoutst = time.time()
    
    def Shutdown(self):
        self.sock.close()
    
    def close(self):
        self.sock.close()
    
    def Connect(self, essl = False):
        # try to establish a connection
        if essl:
            self.sock = ssl.wrap_socket(self.sock, ciphers = 'AES')
        
        if essl:
            self.sock.connect((self.rhost, self.rport + 1))
            output.SetTitle('ssl-cipher', self.sock.cipher())
        else:
            self.sock.connect((self.rhost, self.rport))

        # set socket to non-blocking for life of our object
        self.sock.settimeout(0)
        
        self.ssl = essl
        
        if not self.ssl:
            '''
                This is a little of a mess. It is basically the support
                for a non-SSL connection. I would like to just have this
                not do any encryption at all for systems that do not for
                some reason support SSL. I am not really going to try to
                implement anything because cryptography is very tough to
                get right so in this case im just providing the framework
                where someone else can come in and fix it up one day whos
                a lot smarter than me. Hence, why this code path still 
                exists. It basically just uses a normal socket.
            '''
            # get public key
            s, v, pubkey = vector = self.WriteMessage(struct.pack('>B', ClientType.GetPublicKey), Client.IOMode.Block)
            type, esz = struct.unpack_from('>BH', pubkey)
            e = pubkey[3:3 + esz]
            p = pubkey[3 + esz:]
            self.pubkey = (e, p)
            # kinda been disabled... but still left in
            key = IDGen.gen(10)
            self.crypter = SymCrypt(key)
            self.WriteMessage(struct.pack('>B', ClientType.SetupCrypt) + key, Client.IOMode.Discard)

        data = struct.pack('>B', ClientType.Login) + self.aid
        result = self.WriteMessage(data, Client.IOMode.Block)
        # initialize the time we starting recording the number of bytes sent
        self.bytesoutst = time.time()
        if result:
            return True
        else:
            # TODO: i do not really like raising an exception here, it is great
            #       for debugging but in a production mode it seems not stylish
            raise BadLoginException()

    '''
        Will get a message if stored. The alternative is to call HandleMessages
        but it will block looking for a message. This method is more like polling
        for something and is generally inefficent for usage except in special
        cases.
    '''
    def GetStoredMessage(self, vector):
        with self.socklockread:
            if vector in self.keepresult and self.keepresult[vector] is not None:
                ret = self.keepresult[vector]
                del self.keepresult[vector]
                return ret
        return None
    
    '''
        Get the number of outstanding requests (waiting for reply).
    '''
    def waitCount(self):
        return len(self.keepresult) + len(self.callback)
    
    '''
        This will block if `lookfor` is set to a vector. It will also read from
        the socket and process messages routing them to where they go.
    '''
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
                if self.getBytesToSend() > 0:
                    w = [self.sock]
                else:
                    w = []
                r, w, e = select.select([self.sock], w, [self.sock], 1)
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
    
    '''
        This will break the message into a usable form.
    '''
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

        # since SSL supports compression i might turn this
        # into something else, maybe even controlling the
        # level of SSL compression... not sure
        if type == ServerType.SetCompressionLevel:
            self.bz2compression = data[0]
            return

        # process message based on type
        if type == ServerType.LoginResult:
            if data[0] == ord('y'):
                return True
            return False
            
        if type == ServerType.DirList:
            result, metasize = struct.unpack_from('>BH', data)
            
            # path could not be accessed
            if result == 0:
                return None
            
            data = data[3:]

            list = []
            while len(data) > 0:
                # parse header
                fnamesz, ftype, metaValid = struct.unpack_from('>HBB', data)

                # grab meta data
                if metaValid:
                    metadata = data[4:4 + metasize]
                else:
                    metadata = None
                # grab out name
                fname = data[4 + metasize: 4 + metasize + fnamesz]
                # see if we are using stash format
                data = data[4 + metasize + fnamesz:]
                # break out revision if it exists
                if ftype == 0 and fname[0] == b'\xff':
                    # we use an 8 byte big endian integer
                    # except we only use the lower 7 bits
                    # of each byte yielding a 56 bit integer
                    # with the 7th bit of each byte set to
                    # one to prevent a zero value since we
                    # expect the FS/OS not support a null
                    # value in the filename
                    revcode = from8byte7bit(fname[1:])
                    fname = fname[9:]
                else:
                    revcode = None
                print('fname:%s metaValid:%s metadata:%s' % (fname, metaValid, metadata))
                # build list
                list.append((fname, ftype, metadata, revcode))
            # return list
            return list
        if type == ServerType.FileTime:
            return struct.unpack_from('>Q', data)[0]
        if type == ServerType.FileRead:
            return (struct.unpack_from('>B', data)[0], data[1:])
        if type == ServerType.FileWrite:
            return struct.unpack_from('>B', data)[0]
        if type == ServerType.FileSize:
            success, size = struct.unpack_from('>BQ', data)
            # our general rule of thumb is to pretend that meta-data
            # does not exist, unless we specifically check for it or
            # access it
            size -= self.metasize
            return (success, size)
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
                logger.warn('WARNING: QUOTA LIMIT REACHED THROWING EXCEPTION')
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
    
    '''
        This just moves data from the network level buffers
        into our application buffers. It will eventually exhaust
        memory if it is never processed.
    '''
    def __recv(self):
        data = self.data

        try:
            _data = self.sock.read(4096)
            if not _data:
                raise ConnectionDeadException()
            data.write(_data)
        except:
            # the socket was not ready to be read
            pass
    '''
        A wrapper around the socket which is used to read incoming into
        our application level buffer. It will only return data if it is
        of the specified size, otherwise it returns None.
    '''
    def recv(self, sz):
        data = self.data

        self.__recv()

        # only return with data if its of the specified length
        if data.tell() >= sz:
            # read out the data
            data.seek(0)
            _data = data.read(sz)
            self.data = BytesIO()
            self.data.write(data.read())
            return _data
        return None
    
    '''
        This will read a message from the application level read buffer. It 
        will either return the message or return None.
    '''
    def ReadMessage(self, timeout = 0):
        #self.sock.settimeout(timeout)
        
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

        # return the data
        return self.datasv, self.datav, data
        
    '''
        This will write a message. It supports four different modes
        which are: Block, Async, Callback, and Discard. These modes
        specify how we shall handle the reply.
    '''
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

            if len(data) + 4 + 8 > self.maxmsgsz:
                raise MaxMessageSizeException('exceeded by %s bytes' % ((len(data) + 4 + 8) - self.maxmsgsz))

            self.send(struct.pack('>IQ', len(data), vector))
            self.send(data)
            
        if mode == Client.IOMode.Block:
            #print('blocking by handling messages')
            #print('blocking for vector:%s' % vector)
            res = self.HandleMessages(lookfor = vector)
            #print('    returned with res:%s' % (res,))
            return res
        return vector
    
    '''
        Returns True if we have data to send in our outgoing buffer.
    '''
    def canSend(self):
        return len(self.datatosend) > 0
    
    '''
        Returns the number of bytes in our outgoing buffer.
    '''
    def getBytesToSend(self):
        return self.bytestosend
    
    '''
        This will read in and process incoming data, and write out
        outgoing data. It will block forever until we can write to
        the socket or we can read from it. This is mainly used when
        trying to dump our outgoing buffer to keep it from getting
        too large and exhausting memory.
    '''
    def handleOrSend(self, lookfor = None):
        # wait until the socket can read or write
        read, write, exp = select.select([self.sock], [self.sock], [self.sock])

        if exp:
            raise ConnectionDeadException()
            sys.stdout.flush()
            sys.stderr.flush()

        if read or True:
            # it will block by default so force
            # it to not block/wait
            self.HandleMessages(lookfor = lookfor)

        if write:
            # dump some of the buffers if any
            self.send()
    
    '''
        This will either send the data specified or buffer in our
        application level outgoing buffer to be sent later. It will
        not block and you can be assured the data will be sent as
        soon as possible.
    '''
    def send(self, data = None, timeout = 0):
        if data is not None:
            self.datatosend.append(data)
            self.bytestosend = self.bytestosend + len(data)
        
        #self.sock.settimeout(timeout)
        

        # check there is data to send
        while len(self.datatosend) > 0:
            # pop from the beginning of the queue
            data = self.datatosend.pop(0)

            self.__recv()
            
            # try to send it
            totalsent = 0
            while totalsent < len(data):
                try:
                    sent = self.sock.write(data[totalsent:])
                    # track all the bytes sent out at this very moment
                    self.allbytesout += sent
                except ssl.SSLWantWriteError:
                    sent = 0
                except:
                    raise ConnectionDeadException()
                
                if sent == 0:
                    # place remaining data back at front of queue and
                    # we will try to send it next time
                    self.bytestosend = self.bytestosend - totalsent
                    self.datatosend.insert(0, data[totalsent:])
                    return False
                #print('@sent', sent)
                totalsent = totalsent + sent
            self.bytestosend = self.bytestosend - totalsent

        return True
    
    '''
        Get our calculated throughput in bytes per second for the
        life time of this client object.
    '''
    def getThroughput(self):
        ct = time.time()
        if ct - self.bytesoutst == 0:
            return 0.0
        return self.allbytesout / (ct - self.bytesoutst)

    '''
    '''
    def GetServerPathForm(self, path):
        # 1. prevent security hole (helps reduce server CPU load if these exist)
        while path.find(b'..') > -1:
            path = path.replace(b'..', b'.')
        # remove duplicate path separators
        while path.find(b'//') > -1:
            path = path.replace(b'//', b'/')
        # if nothing left then just exit
        if len(path) < 1:
            return path
        # remove leading slash if present
        if path[0] == b'/':
            path = path[1:]
        # check the type of path to see if they specified
        # an additional revision parameter, and if so check
        # if it is zero (normal) - if not place it into a
        # revision path
        ptype = type(path)
        if ptype is tuple or ptype is list:
            rev = path[1]
            path = path[0]
            if rev != 0:
                # check if path contains a base directory
                if path.find(b'/') > -1:
                    # grab off the base (hash to be directory)
                    base = path[0:path.find(b'/')]
                    # assign path with out the base
                    path = path[path.find(b'/'):]
                    # create the base using special revision format
                    base = b'\xff'.join(struct.pack('>Q', rev), base)
                    # create the new path
                    path = b'/'.join((base, path))
                else:
                    # no base directory so we have to create one
                    base = b''.join(b'\xff', self.to8byte7bit(rev) , b'\xff/', base)
                    path = b'/'.join((base, path))
        return path
    
    def DirList(self, xdir, mode, callback = None, metasize = None):
        xdir = self.GetServerPathForm(xdir)
        print('xdir', xdir)
        if metasize is None:
            metasize = self.metasize
        return self.WriteMessage(struct.pack('>BH', ClientType.DirList, metasize) + xdir, mode, callback)
    def FileReadMeta(self, fid, offset, length, mode, callback = None):
        _fid = self.GetServerPathForm(fid)
        # notice the difference to FileRead (has meta-data size offset)
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileRead, offset, length) + _fid, mode, callback)
    def FileRead(self, fid, offset, length, mode, callback = None):
        _fid = self.GetServerPathForm(fid)
        # compensate for metadata length
        offset += self.metasize
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileRead, offset, length) + _fid, mode, callback)
    def FileWriteMeta(self, fid, offset, data, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        # notice the difference to FileWrite (has meta-data size offset)
        return self.WriteMessage(struct.pack('>BQHB', ClientType.FileWrite, offset, len(fid), self.bz2compression) + fid + data, mode, callback)
    def FileWrite(self, fid, offset, data, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        # compensate for metadata length
        offset += self.metasize
        return self.WriteMessage(struct.pack('>BQHB', ClientType.FileWrite, offset, len(fid), self.bz2compression) + fid + data, mode, callback)
    def FileSetTime(self, fid, atime, mtime, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileSetTime, atime, mtime) + fid, mode, callback)
    def FileSize(self, fid, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>B', ClientType.FileSize) + fid, mode, callback)
    def FileTrun(self, fid, newsize, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        # compensate for metadata length
        newsize += self.metasize
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
        offset += self.metasize
        return self.WriteMessage(struct.pack('>BQQ', ClientType.FileHash, offset, length) + fid, mode, callback)
    def FileTime(self, fid, mode, callback = None):
        fid = self.GetServerPathForm(fid)
        return self.WriteMessage(struct.pack('>B', ClientType.FileTime) + fid, mode, callback)
    def HashKmc(self, data, max):
        if self.hentry is not None:
            #out = create_string_buffer(len(data))
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
                    seed = data[x * 2]
                x = x + 1
            sz = x
        return bytes(data[0:sz])

class Client2(Client):
    def __init__(self, rhost, rport, aid, sformat, metasize = None):
        Client.__init__(self, rhost, rport, aid, metasize = metasize)

    '''
        We re-implement the FileWrite to enforce the maximum
        message size.
    '''
    def FileWrite(self, fid, offset, data, mode, callback = None):
        # BQHB (compensate for added file write header size)        1+8+2+1
        # IQ   (compensate for added message header size)           4+8
        msgmax = self.maxmsgsz - (1 + 8 + 2 + 1 + 4 + 8 + 1)

        _fid = self.GetServerPathForm(fid)

        # compensate for filename length after transformation
        msgmax -= len(_fid)

        x = 0
        while x * msgmax < len(data):
            _max = len(data) - (x * msgmax)
            _max = min(_max, msgmax)
            _data = data[x * msgmax:x * msgmax + _max]
            super().FileWrite(fid, offset + x * msgmax, _data, mode, callback = callback)
            x = x + 1
        return 


