'''
    Using ctypes to load a library is decently straight
    forward, but the code required to decide between:

    PE32, PE64, ELF32, ELF64, X86, X86_64, ARM

    .. well you get the point - so i created this little
    helper that makes all that much easier to do
'''

class UnsupportedPlatformException():
    pass

'''
    TODO:
    It is currently missing support for ARM and
    other architectures. It currently just decides
    between x86 and x86_64 which are the most 
    common, but if this is run under ARM it will
    try to load x86_64 which would be incorrect.
'''
def loadLibrary(basepath, basename):
    is64 = sys.maxsize > 2 ** 32

    isLinux = sys.platform.find('linux') > -1
    isWindow = sys.platform.find('win') > -1

    if not isLinux and not isWindows:
        raise UnsupportedPlatformException()

    if isLinux:
        ext = 'so'
    if iswindows:
        ext = 'dll'

    if is64:
        arch = 'x86_64'
    else:
        arch = 'x86'

    libpath = '%s/%s_%s.%s' % (basepath, basename, arch, ext)

    if isLinux:
        hdll = cdll.LoadLibrary(libpath)
    else:
        hdll = windll.LoadLibrary(libpath)

    # linux:    self.hentry = self.hdll['hash']
    # windows:  self.hentry = CFUNCTYPE(c_int)(('hash', self.hdll))
    return hdll

'''
    If we need to do extra work to properly reference a 
    exported function for a DLL then this is the place
    we will do it. We just need the calling code to not
    have to worry about any differences.
'''
def getExportFunction(hdll, symname):
    return hdll[symname]