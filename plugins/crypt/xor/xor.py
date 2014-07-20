'''
    This implements a very simple XOR encryption using either an
    UTF8 string passed or a file passed by file path. It can handles
    random access of the file for reading and writing.
'''
import os
import ctypes
import time
import shutil

from io import BytesIO
from lib import libload

import lib.flycatcher as flycatcher
logger = flycatcher.getLogger('crypt.xor')

class XorFileEncryptObject:
    def __init__(self, lpath, xpath, gstate):
        self.lpath = lpath
        self.xpath = xpath
        self.state = _callinit(self.lpath, 0, gstate, 0)

    def read(self, offset, length):
        return _callread(self.state, offset, length)

    def finish(self):
        _callfinish(self.state)

# yeah.. i used inheritance.. it reduced copy and paste
class XorFileDecryptObject:
    def __init__(self, lpath, xpath, gstate):
        self.lpath = lpath
        self.xpath = xpath
        self.state = _callinit(self.lpath, 0, gstate, 1)

    def write(self, offset, data):
        return _callwrite(self.state, offset, data)

    def finish(self):
        _callfinish(self.state)

hdll = None
hstart = None
hread = None
hwrite = None
hfinish = None

def _loadlibrary():
    global hdll
    global hstart
    global hread
    global hwrite
    global hfinish
    
    if hdll is None:
        hdll = libload.loadLibrary('./plugins/crypt/xor/', 'cryptxor')
        hstart = libload.getExportFunction(hdll, 'cryptxor_start')
        hread = libload.getExportFunction(hdll, 'cryptxor_read')
        hwrite = libload.getExportFunction(hdll, 'cryptxor_write')
        hfinish = libload.getExportFunction(hdll, 'cryptxor_finish')

# initialize the state
def _callinit(fpath, xfpath, gstate = None, write = 0):
    global hstart
    # made it a little bigger than needed.. room to grow
    if gstate is None:
        gstate = ctypes.c_void_p(0)
    state = ctypes.create_string_buffer(32)
    # it seems sometimes the file is created but the library fails
    # to open it but if you try a few times it finally opens the
    # file
    logger.debug('_callinit: fpath:%s xfpath:%s' % (fpath, xfpath))
    if fpath is not None:
        fpath = ctypes.c_char_p(fpath)
    else:
        fpath = ctypes.c_void_p(0)

    ret = hstart(state, fpath, ctypes.c_char_p(xfpath), gstate, ctypes.c_uint8(write))
    if ret == 0:
        raise Exception('XOR INIT EXCEPTION')
    return state

def _callread(state, offset, length):
    global hread
    obuf = ctypes.create_string_buffer(length)
    logger.debug('state:%s offset:%s length:%s' % (state, offset, length))
    hread(state, ctypes.c_uint64(offset), ctypes.c_uint64(length), obuf)
    obuf = bytes(obuf)
    return obuf

def _callwrite(state, offset, data):
    global hwrite
    hwrite(state, ctypes.c_uint64(offset), ctypes.c_char_p(data), ctypes.c_uint64(len(data)))
    
def _callfinish(state):
    global hfinish
    hfinish(state, ctypes.c_void_p(0));

class Xor:
    '''
        This is called to initialize the plugin module. It is called
        for each client session.
    '''
    def __init__(self, client, options):
        options = options.split(',')

        for option in options:
            kv = option.split(':')
            if len(kv) < 2:
                continue
            k = kv[0]
            v = ':'.join(kv[1]) 

            if k == 'file':
                self.fod = ('file', v)
                continue
            if k == 'data':
                self.fod = ('data', v)
                continue

            logger.warn('ignore option "%s"' % k)

        # the C library expects a file containing the XOR
        # data to keep everything simple, so here we create
        # a temporary file with a unique name if needed
        # and go from there
        if self.fod[0] == 'data':
            try:
                os.makedirs('./temp/cryptxor')
            except:
                pass
            lxtemp = './temp/crypxor/%s.xor' % (int(time.time() * 1000))
            lxtemp = bytes(lxtemp, 'utf8')
            fo = open(lxtemp, 'wb')
            fo.write(bytes(self.fod[1], 'utf8'))
            fo.close()
            self.xpath = lxtemp
            self.usedtemp = True
        else:
            self.xpath = fod[1]
            self.usedtemp = False

        # initialize global state (pass None for global state and zero for lpath)
        self.state = _callinit(None, self.xpath, None)

    def getencryptedsize(self, lpath, opts = None):
        """ Return the bytes in size of the encrypted file. """
        return os.stat(lpath).st_size

    def beginread(self, lpath):
        """ Return a read object. """
        return XorFileEncryptObject(lpath, self.xpath, self.state)

    def beginwrite(self, lpath):
        """ Return a write object. """
        return XorFileDecryptObject(lpath, self.xpath, self.state)


def getplugins():
    # ensure that the class can load properly, and if so then
    # add it to the list of plugins we are exportings
    try:
        _loadlibrary()
    except Exception as e:
        # return nothing
        raise e
        return tuple()

    return (
        ('crypt.xor', Xor),
    )