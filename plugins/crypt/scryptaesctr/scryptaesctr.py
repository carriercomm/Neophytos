'''
'''
from ctypes import c_char_p
from ctypes import create_string_buffer
from ctypes import c_size_t
from ctypes import c_double
from ctypes import c_uint8

from lib import libload

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
    _hexp_crypto_aesctr_free = libload.getExportFunction(_hdll, 'exp_crypto_aesctr_free')
    _hexp_crypto_aesctr_stream = libload.getExportFunction(_hdll, 'exp_crypto_aesctr_stream')
    _hexp_crypto_aesctr_init = libload.getExportFunction(_hdll, 'exp_crypto_aesctr_init')
    _hexp_getpointersize = libload.getExportFunction(_hdll, 'exp_getpointersize')
    _hexp_AES_set_encrypt_key = libload.getExportFunction(_hdll, 'exp_AES_set_encrypt_key')
    _hexp_getaeskeysize = libload.getExportFunction(_hdll, 'exp_getaeskeysize')
else:
    raise Exception('OOPS - DEBUGGING')

'''
    int exp_crypto_aesctr_free(uint8_t *AESptr) {
    int exp_crypto_aesctr_stream(uint8_t *AESptr, uint8 *ibuf, uint8 *obuf, size_t buflen) {
    int exp_crypto_aesctr_init(uint8_t *AESptr, AES_KEY *aeskey) {
    int exp_getpointersize() {
    int exp_AES_set_encrypt_key(uint8_t *key_enc, size_t keysz, AES_KEY *aeskey) {
'''
def hcrypto_aesctr_free(aesptr):
    return _hexp_crypto_aesctr_free(aesptr)

def hcrypto_aesctr_stream(aesptr, buf):
    obuf = create_string_buffer(len(buf))
    rcode = _hexp_crypto_aesctr_stream(aesptr, c_char_p(buf), obuf, c_size_t(len(buf)))
    return (rcode, bytes(obuf))

def hcrypto_aesctr_init(aeskey):
    ptrsize = _hexp_getpointersize()
    aesptr = create_string_buffer(ptrsize)

    return (_hexp_crypto_aesctr_init(aesptr, aeskey), aesptr)

def hAES_set_encrypt_key(key):
    aeskey = create_string_buffer(_hexp_getaeskeysize())

    return (_hexp_AES_set_encrypt_key(c_char_p(key), c_size_t(len(key) * 8), aeskey), aeskey)

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
        return self.readfunc(offset, length)

    def write(self, offset, data):
        return self.writefunc(offset, data)

    def finish(self):
        return self.finishfunc()

'''
    THIS SECTION IMPLEMENTS THE PLUGIN OBJECTS
'''
class Scrypt:
    def __init__(self, client, options):
        options = options.split(',')

        for option in options:
            kv = option.split(':')
            if len(kv) < 2:
                continue
            k = kv[0]
            v = ':'.join(kv[1]) 

            if k == 'file':
                fo = open(v, 'rb')
                self.pw = fo.read()
                fo.close()
                continue
            if k == 'data':
                self.pw = bytes(v, 'utf8')
                continue

            logger.warn('ignore option "%s"' % k)

    def beginRead(self, lpath):
        # encrypt the file and store it in a temporary file then
        # read that data from the temporary file and delete it
        # when done
        try:
            os.makedirs('./temp/scryptaesctr')
        except:
            pass
        lxtemp = './temp/scryparesctr/%s.xor' % (int(time.time() * 1000))
        lxtemp = bytes(lxtemp, 'utf8')

        hscryptenc_path(bytes(lpath, 'utf8'), lxtemp, self.pw, 1024 * 1024 * 512, 0.5, 3, None)

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

    def beginWrite(xself, lpath):
        # build an object to read the data into a temporary file
        # and when done decrypt it and create the decrypted file
        # or truncate the existing
        try:
            os.makedirs('./temp/scryptaesctr')
        except:
            pass

        lxtemp = './temp/scryparesctr/%s.xor' % (int(time.time() * 1000))
        lxtemp = bytes(lxtemp, 'utf8')

        fo = open(lxtemp, 'wb')

        def _write(self, offset, data):
            fo.seek(offset)
            return fo.write(data)

        def _finish(self):
            fo.close()
            # decrypt the file into the local file specified
            hscryptdec_path(lxtemp, lpath, xself.pw, 1024 * 1024 * 512, 0.5, 6, None)
            os.remove(lxtemp)

class AESCTR256:
    def __init__(self, client, options):
        options = options.split(',')

        for option in options:
            kv = option.split(':')
            if len(kv) < 2:
                continue
            k = kv[0]
            v = kv[1]

            if k == 'file':
                fo = open(v, 'rb')
                self.key = fo.read()
                fo.close()
                continue

            logger.warn('ignore option "%s"' % k)

    def beginRead(xself, lpath):
        # encrypt the file and store it in a temporary file then
        # read that data from the temporary file and delete it
        # when done
        try:
            os.makedirs('./temp/scryptaesctr')
        except:
            pass
        lxtemp = './temp/scryparesctr/%s.xor' % (int(time.time() * 1000))
        lxtemp = bytes(lxtemp, 'utf8')

        # do encryption first ahead of time
        xself.aesctrencpath(bytes(lpath, 'utf8'), lxtemp)

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

    def beginWrite(xself, lpath):
        # build an object to read the data into a temporary file
        # and when done decrypt it and create the decrypted file
        # or truncate the existing
        try:
            os.makedirs('./temp/scryptaesctr')
        except:
            pass

        lxtemp = './temp/scryparesctr/%s.xor' % (int(time.time() * 1000))
        lxtemp = bytes(lxtemp, 'utf8')

        fo = open(lxtemp, 'wb')

        def _write(self, offset, data):
            fo.seek(offset)
            return fo.write(data)

        def _finish(self):
            fo.close()
            # do decryption
            xself.aesctrencpath(lxtemp, lpath)
            os.remove(lxtemp)
    '''
        This takes two files. One is input, and the other
        is output. The output file is created or truncated.
        The input file is NOT modified. It will either 
        encrypt an unencrypted file, or decrypt an encrypted
        file. It works both ways with the same key.

        aesctrincpath('myfile', 'myencryptedfile') <--- encryption
        aesctrincpath('myencryptedfile', 'myfile') <--- decryption
    '''
    def aesctrencpath(self, ifile, ofile):
        fi = open(ifile, 'rb')
        fo = open(ofile, 'wb')

        ksz = len(self.key)

        # drop excess key size
        if ksz >= 32:
            key = self.key[0:32]
        elif ksz >= 16:
            key = self.key[0:16]
        elif ksz >= 8:
            key = self.key[0:8]
        else:
            raise Exception('The AES key must be at least 64 bits in length.')

        rcode, aeskey = hAES_set_encrypt_key(key)
        if rcode != 0:
            raise Exception('It looks like there was an error setting the AES encryption key.')
        rcode, aesptr = hcrypto_aesctr_init(aeskey)

        # loop through file data in multiples of key sizes
        while True:
            # 4MB reads seem decent enough in memory usage and performance
            pdata = fi.read(1024 * 1024 * 4)
            # read data until we reach EOF
            if not pdata:
                # exit at EOF
                break
            _, edata = hcrypto_aesctr_stream(aesptr, pdata)
            # write encrypted data to the file
            fo.write(edata)

        hcrypto_aesctr_free(aesptr)
        fi.close()
        fo.close()

def getPlugins():
    # if the library could not be loaded then we have no support
    # for the plugins and could not make them avaliable
    if _hdll is None:
        return tuple()

    return (
        ('crypt.scrypt',    Scrypt),
        ('crypt.aesctr256', AESCTR256)
    )