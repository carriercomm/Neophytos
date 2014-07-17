'''
'''
from ctypes import c_char_p
from ctypes import create_string_buffer
from ctypes import c_size_t
from ctypes import c_double
from ctypes import c_uint8

from lib import libload

class Scrypt:
    pass

class AESCTR256:
    pass

_hdll = libload.loadLibrary('./plugins/crypt/scryptaesctr/', 'scryptaesctr')
if _hdll is not None:
    _hscryptenc_buf = libload.getExportFunction(_hdll, 'scryptenc_buf')
    _hscryptdec_buf = libload.getExportFunction(_hdll, 'scryptdec_buf')
    _hscryptenc_file = libload.getExportFunction(_hdll, 'scryptenc_file')
    _hscryptdec_file = libload.getExportFunction(_hdll, 'scryptdec_file')
    _hscryptkdf = libload.getExportFunction(_hdll, 'scryptkdf')

'''
    static int
    scryptkdf(
        uint8_t *passwd, size_t passwdlen, uint8_t *dk, size_t dklen,
        double maxmem, double maxmemfrac, double maxtime
    )
'''
def hscryptkdf(password, dklen, maxmem, maxmemfrac, maxtime):
    dk = create_string_buffer(dklen)

    _hscryptkdf(
        c_char_p(password), c_size_t(len(password)), dk, c_size_t(dklen),
        c_double(maxmem), c_double(maxmemfrac), c_double(maxtime)
    )

    return bytes(dk)
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
    return (1, dk)
def hscryptdec_file(info, outfo, password, maxmem, maxmemfrac, maxtime, dk):
    return (1, dk)

def getPlugins():
    # if the library could not be loaded then we have no support
    # for the plugins and could not make them avaliable
    if _hdll is None:
        return tuple()

    return (
        ('crypt.scrypt',    Scrypt),
        ('crypt.aesctr256', AESCTR256)
    )