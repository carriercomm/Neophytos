'''
'''
from ctypes import c_char_p
from ctypes import create_string_buffer
from ctypes import c_size_t
from ctypes import c_double
from ctypes import c_uint8

from lib import libload

import struct
import os
import math
import time

import lib.flycatcher as flycatcher
logger = flycatcher.getLogger('plugin.crypt.scryptaesctr')

gvector = 0

'''
    THIS SECTION BUILDS THE INTERFACE TO THE NATIVE LIBRARY
'''
_hdll = libload.loadLibrary('./plugins/crypt/scryptaesctr/', 'scryptaesctr')
if _hdll is not None:
    _hscryptenc_buf = libload.getExportFunction(_hdll, 'scryptenc_buf')
    _hscryptdec_buf = libload.getExportFunction(_hdll, 'scryptdec_buf')
    _hscryptenc_file = libload.getExportFunction(_hdll, 'scryptenc_file')
    _hscryptdec_file = libload.getExportFunction(_hdll, 'scryptdec_file')
    _hscryptenc_path = libload.getExportFunction(_hdll, 'scryptenc_path')
    _hscryptdec_path = libload.getExportFunction(_hdll, 'scryptdec_path')
    _hscryptkdf = libload.getExportFunction(_hdll, 'scryptkdf')
    _hgetparamsize = libload.getExportFunction(_hdll, 'getparamsize')
    _aes256ctr_init = libload.getExportFunction(_hdll, 'aes256ctr_init')
    _aes256ctr_crypt = libload.getExportFunction(_hdll, 'aes256ctr_crypt')
    _aes256ctr_done = libload.getExportFunction(_hdll, 'aes256ctr_done')
    _aes256ctr_getcontextsize = libload.getExportFunction(_hdll, 'aes256ctr_getcontextsize')
else:
    raise Exception('OOPS - DEBUGGING')

'''
    int exp_crypto_aesctr_free(uint8_t *AESptr) {
    int exp_crypto_aesctr_stream(uint8_t *AESptr, uint8 *ibuf, uint8 *obuf, size_t buflen) {
    int exp_crypto_aesctr_init(uint8_t *AESptr, AES_KEY *aeskey) {
    int exp_getpointersize() {
    int exp_AES_set_encrypt_key(uint8_t *key_enc, size_t keysz, AES_KEY *aeskey) {
'''

def aes256ctr_init(key, nonce = None):
    if len(key) < 32:
        raise Exception('The key must be 256-bit in length at least!')
    if nonce is not None and len(nonce) < 32:
        raise Exception('The nonce must be 256-bit in length at least!')
    ctx = create_string_buffer(_aes256ctr_getcontextsize())
    if _aes256ctr_init(ctx, c_char_p(key), c_char_p(nonce)) != 0:
        return None
    return ctx

def aes256ctr_crypt(ctx, xin):
    out = create_string_buffer(len(xin))
    _aes256ctr_crypt(ctx, c_char_p(xin), out, c_size_t(len(xin)))
    return bytes(out)

def aes256ctr_done(ctx):
    _aes256ctr_done(ctx)

'''
    static int
    scryptkdf(
        uint8_t *passwd, size_t passwdlen, uint8_t *dk, size_t dklen,
        double maxmem, double maxmemfrac, double maxtime
    )
'''
def hscryptkdf(password, dklen, maxmem, maxmemfrac, maxtime, params = None, saltsz = 32):
    dk = create_string_buffer(dklen)

    # get lib's param size
    psz = _hgetparamsize()
    # check length of params
    if params is not None and len(params) < (psz + saltsz):
        raise Exception('For this build of the scrypt lib params must be at least %s bytes! The salt size is %s.' % (psz, saltsz))
    if params is None:
        print('creating param bytes')
        params = create_string_buffer(psz + saltsz)
        recover = 0
    else:
        print('using param bytes')
        params = c_char_p(params)
        recover = 1

    rcode = _hscryptkdf(
        c_char_p(password), c_size_t(len(password)), dk, c_size_t(dklen),
        c_size_t(saltsz),
        c_double(maxmem), c_double(maxmemfrac), c_double(maxtime), params,
        c_uint8(recover)
    )

    if recover == 0:
        # convert from string buffer into bytes object
        params = bytes(params)

    return (rcode, bytes(dk), params)
'''
    int
    scryptenc_buf(const uint8_t * inbuf, size_t inbuflen, uint8_t * outbuf,
        const uint8_t * passwd, size_t passwdlen,
        size_t maxmem, double maxmemfrac, double maxtime,
        uint8_t *dk, uint8_t gendk)
'''
def hscryptenc_buf(buf, password, maxmem, maxmemfrac, maxtime, dk):
    outbuf = create_string_buffer(len(buf) + 128)

    # if dk is None, then create a fresh dk buffer
    if dk is None:
        dk = create_string_buffer(64);
        dkgen = 1
    else:
        dkgen = 0

    ret = _hscryptenc_buf(
        c_char_p(buf), c_size_t(len(buf)), outbuf, c_char_p(password), c_size_t(len(password)),
        c_size_t(maxmem), c_double(maxmemfrac), c_double(maxtime), dk, c_uint8(dkgen)
    )

    outbuf = bytes(outbuf)
    return (ret, outbuf, dk)
'''
    int
    scryptdec_buf(const uint8_t * inbuf, size_t inbuflen, uint8_t * outbuf,
        size_t * outlen, const uint8_t * passwd, size_t passwdlen,
        size_t maxmem, double maxmemfrac, double maxtime,
        uint8_t *dk, uint8_t gendk)
'''
def hscryptdec_buf(buf, password, maxmem, maxmemfrac, maxtime, dk):
    # yeah not good because if the lib code changes this screws up
    # but it will work for now
    outbuf = create_string_buffer(len(buf) - 128)

    # if dk is None, then create a fresh dk buffer
    if dk is None:
        dk = create_string_buffer(64);
        dkgen = 1
    else:
        dkgen = 0

    outlen = create_string_buffer(8)

    ret = _hscryptdec_buf(
        c_char_p(buf), c_size_t(len(buf)), outbuf, outlen, c_char_p(password), c_size_t(len(password)),
        c_size_t(maxmem), c_double(maxmemfrac), c_double(maxtime), dk, c_uint8(dkgen)
    )

    outbuf = bytes(outbuf)
    return (ret, outbuf, dk)
def hscryptenc_file(info, outfo, password, maxmem, maxmemfrac, maxtime, dk):
    raise Exception('Not Implemented')
    return (1, dk)
def hscryptdec_file(info, outfo, password, maxmem, maxmemfrac, maxtime, dk):
    raise Exception('Not Implemented')
    return (1, dk)

def haes_crypt_buf(buf, key):
    rcode, aeskey = haes_set_encrypt_key(key)
    if rcode != 0:
        raise Exception('It looks like there was an error setting the AES encryption key.')
    rcode, aesptr = hcrypto_aesctr_init(aeskey)
    _, ebuf = hcrypto_aesctr_stream(aesptr, buf)
    hcrypto_aesctr_free(aesptr)
    return ebuf


'''
    int
    scryptenc_path(uint8_t *inpath, uint8_t *outpath
        const uint8_t * passwd, size_t passwdlen,
        size_t maxmem, double maxmemfrac, double maxtime,
        uint8_t *dk, uint8_t gendk)


    int
    scryptdec_path(uint8_t *inpath, uint8_t *outpath
        const uint8_t * passwd, size_t passwdlen,
        size_t maxmem, double maxmemfrac, double maxtime,
        uint8_t *dk, uint8_t gendk)
'''
def hscryptenc_path(inpath, outpath, password, maxmem, maxmemfrac, maxtime, dk):
    if dk is None:
        dk = create_string_buffer(64);
        dkgen = 1
    else:
        dkgen = 0

    return _hscryptenc_path(
        c_char_p(inpath), c_char_p(outpath),
        c_char_p(password), c_size_t(len(password)),
        c_size_t(maxmem), c_double(maxmemfrac), c_double(maxtime),
        dk,
        c_uint8(dkgen)
    )

def hscryptdec_path(inpath, outpath, password, maxmem, maxmemfrac, maxtime, dk):
    if dk is None:
        dk = create_string_buffer(64);
        dkgen = 1
    else:
        dkgen = 0

    return _hscryptdec_path(
        c_char_p(inpath), c_char_p(outpath),
        c_char_p(password), c_size_t(len(password)),
        c_size_t(maxmem), c_double(maxmemfrac), c_double(maxtime),
        dk,
        c_uint8(dkgen)
    )

class ReadWriteObject():
    def __init__(self, readfunc, writefunc, finishfunc):
        self.readfunc = readfunc
        self.writefunc = writefunc
        self.finishfunc = finishfunc

    def read(self, offset, length):
        return self.readfunc(self, offset, length)

    def write(self, offset, data):
        return self.writefunc(self, offset, data)

    def finish(self):
        return self.finishfunc(self)

'''
    THIS SECTION IMPLEMENTS THE PLUGIN OBJECTS
'''

class AESCTRMULTI:
    """ Implements the AES-CTR-MULTI algorithm. 

    This works by using a master key. The master key is made from:
        #1 the first 32 bytes of a specified file
        #2 from a password passed to the scrypt KDF that produces 32 bytes
    
    Each file that is encrypted has a 256-bit key randomly generated known
    as the sub-key. The file data is encrypted using the sub-key and
    AES-CTR using a zeroed nonce which is incremented every X number of 
    bytes.

    Then the sub-key is encrypted using AES with the master key and placed
    as the first 32 bytes of the encrypted file.

    """
    def __init__(self, client, options):
        """ Initialize the AES-CTR-MULTI algorithm. """
        options = options.split(',')

        self.mk = None

        for option in options:
            kv = option.split(':')
            if len(kv) < 2:
                continue

            k = kv[0]
            v = kv[1]

            if k == 'file':
                # read in key
                kfo = open(v, 'rb')
                self.mk = kfo.read(32)
                kfo.close()
                if len(self.mk) < 32:
                    raise Exception('The key file must contain at least 32-bytes!')
                continue

            if k == 'pass':
                # use the scrypt KDF to generate 32 bytes for a key
                pass

            logger.warn('ignore option "%s"' % k)

        if self.mk is None:
            raise Exception('No key specified')

    def beginread(xself, lpath):
        """ Return read object for file specified by path. """
        global gvector
        try:
            os.makedirs('./temp/')
        except:
            pass

        global gvector
        lxtemp = './temp/%s.tmp' % (gvector)
        lxtemp = bytes(lxtemp, 'utf8')
        gvector = gvector + 1

        # do encryption first ahead of time
        xself.aesctrencmultipath(lpath, lxtemp)

        fo = open(lxtemp, 'rb')

        #scryptaesctr.hscryptenc_path(b'input', b'output', b'mypassword', 1024 * 1024 * 512, 0.5, 3, None)
        #scryptaesctr.hscryptdec_path(b'output', b'output2', b'mypassword', 1024 * 1024 * 512, 0.5, 3, None)
        def _read(self, offset, length):
            fo.seek(offset)
            return fo.read(length)

        def _finish(self):
            fo.close()
            os.remove(lxtemp)

        return ReadWriteObject(_read, None, _finish)

    def getencryptedsize(self, lpath):
        """ Return the expected encrypted size. """
        return os.stat(lpath).st_size + 32

    def beginwrite(xself, lpath):
        global gvector
        """ Return write object for file specified by path. """
        try:
            os.makedirs('./temp/')
        except:
            pass

        lxtemp = './temp/%s.tmp' % (gvector)
        lxtemp = bytes(lxtemp, 'utf8')
        gvector = gvector + 1

        fo = open(lxtemp, 'wb')

        def _write(self, offset, data):
            fo.seek(offset)
            return fo.write(data)

        def _finish(self):
            fo.close()
            # do decryption
            xself.aesctrdecmultipath(lxtemp, lpath)
            os.remove(lxtemp)

        return ReadWriteObject(None, _write, _finish)

    def aesctrencmultipath(self, ifile, ofile):
        """ Return no value but encrypts ifile and writes output to ofile. """
        mk = self.mk

        # generate random sub-key
        sk = os.urandom(32)

        # encrypt file data with sub-key
        ret = self.aesctrencpath(ifile, ofile, key = sk, iseek = 0, oseek = 32)

        # encrypt random sub-key
        ctx = aes256ctr_init(mk)
        skh = aes256ctr_crypt(ctx, sk)
        aes256ctr_done(ctx)

        # write the index used at the beginning of the file in
        # the space we reserved for it
        fo = open(ofile, 'r+b')
        fo.seek(0)
        fo.write(skh)
        fo.close()

    def aesctrdecmultipath(self, ifile, ofile):
        """ Return no value but decrypts ifile and writes output to ofile. """
        # read the sub-key header
        fo = open(ifile, 'rb')
        skh = fo.read(32)
        fo.close()

        # read the master key
        mk = self.mk

        # decrypt the sub-key
        ctx = aes256ctr_init(mk)
        sk = aes256ctr_crypt(ctx, skh)
        aes256ctr_done(ctx)

        # decrypt the file data (start reading 32 byte)
        self.aesctrencpath(ifile, ofile, key = sk, iseek = 32, oseek = 0)

    def aesctrencpath(self, ifile, ofile, key = None, iseek = 0, oseek = 0):
        """Encrypt ifile writing output to ofile.

        Arguments:
        self -- owning object
        ifile -- input file bytes or string path
        ofile -- output file bytes or string path
        Keywork arguments:
        key -- the key in the supported byte length (8-64bit, 16-128bit, 32-256bit)
        iseek -- the offset to start reading in the input file (default 0)
        oseek -- the offset to start writing in the output file (default 0)
        """
        fi = open(ifile, 'rb')
        fo = open(ofile, 'wb')

        fi.seek(iseek)
        fo.seek(oseek)

        if key is None:
            key = self.key

        ksz = len(key)

        # drop excess key size
        if ksz >= 32:
            key = key[0:32]
        elif ksz >= 16:
            key = key[0:16]
        elif ksz >= 8:
            key = key[0:8]
        else:
            raise Exception('The AES key must be at least 64 bits in length.')

        ctx = aes256ctr_init(key)

        # loop through file data in multiples of key sizes
        while True:
            # 4MB reads seem decent enough in memory usage and performance
            pdata = fi.read(1024 * 1024 * 4)
            # read data until we reach EOF
            if not pdata:
                # exit at EOF
                break
            edata = aes256ctr_crypt(ctx, pdata)
            # write encrypted data to the file
            fo.write(edata)

        aes256ctr_done(ctx)
        fi.close()
        fo.close()



def getplugins():
    """Return tuple or list of tuples of plugin reference name and type.

    This will return a tuple of tuples. The inner tuples contain two elements.
    The first element is the plugin reference name, and the second element is
    the plugin type object in order to create an instance of it.
    """
    if _hdll is None:
        return tuple()          # no valid library then no plugins

    return (
        ('crypt.aesctrmulti',   AESCTRMULTI),       # aes-ctr-multi (my implementation)
    )