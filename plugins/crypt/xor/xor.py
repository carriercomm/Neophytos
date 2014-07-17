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

        # the init routine will copy the gstate into
        # the local state when we pass it in like this
        self.state = _callInit(self.lpath, 0, gstate)

    def read(self, offset, length):
        return _callRead(self.state, offset, length)

    def finish(self):
        # let the library code cleanup anything it needs to cleanup
        # mainly for XOR it should just be closing the files that it
        # has opened
        _callFinish(self.state)

# yeah.. i used inheritance.. it reduced copy and paste
class XorFileDecryptObject(XorFileEncryptObject):
    # override this method and throw an exception to
    # prevent programmer error..
    def read(self):
        raise Exception('Not Supported')
    # implement new method
    def write(self, offset, data):
        return _callWrite(self.state, offset, data)

hdll = None
hstart = None
hread = None
hwrite = None
hfinish = None

def _loadLibrary():
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
def _callInit(fpath, xfpath, gstate = None):
    global hstart
    # made it a little bigger than needed.. room to grow
    if gstate is None:
        gstate = ctypes.c_void_p(0)
    state = ctypes.create_string_buffer(32)
    # it seems sometimes the file is created but the library fails
    # to open it but if you try a few times it finally opens the
    # file
    logger.debug('fpath:%s xfpath:%s' % (fpath, xfpath))
    if fpath is not None:
        fpath = ctypes.c_char_p(fpath)
    else:
        fpath = ctypes.c_void_p(0)

    ret = hstart(state, fpath, ctypes.c_char_p(xfpath), gstate)
    if ret == 0:
        raise Exception('XOR INIT EXCEPTION')
    return state

def _callRead(state, offset, length):
    global hread
    obuf = ctypes.create_string_buffer(length)
    logger.debug('state:%s offset:%s length:%s' % (state, offset, length))
    hread(state, ctypes.c_uint64(offset), ctypes.c_uint64(length), obuf)
    obuf = bytes(obuf)
    return obuf

def _callWrite(state, offset, data):
    global hwrite
    hwrite(state, ctypes.c_uint64(offset), ctypes.c_char_p(data), ctypes.c_uint64(len(data)))
    
def _callFinish(state):
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
            os.makedirs('./temp/cryptxor')
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
        self.state = _callInit(None, self.xpath, None)

    '''
        Called when the operation on the file specified
        with `lpath` begins an encryption operation.
    '''
    def beginRead(self, lpath):
        return XorFileEncryptObject(lpath, self.xpath, self.state)
    '''
        Called when the operation on the file specified
        with 'lpath' begins an decryption operation.
    '''
    def beginWrite(self, lpath):
        return XorFileDecryptObject(lpath, self.xpath, self.state)


def getPlugins():
    # clear out temp directory files
    try:
        shutil.rmtree('./temp/cryptxor/')
        os.makedirs('./temp/crypxor/')
    except:
        pass

    # ensure that the class can load properly, and if so then
    # add it to the list of plugins we are exportings
    try:
        _loadLibrary()
    except:
        # return nothing
        return (,)

    return (
        ('crypt.xor', Xor),
    )