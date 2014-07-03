import os
import os.path
import sys
import pprint
import re
import threading
import time

from lib import misc
from lib import output

import lib.buops                        # backup operations
import lib.flycatcher as flycatcher     # debugging tool

def main(args):            
    '''
        --lpath=<path>
        --rpath=<path>
        --password=<text>  or --authcode=<text>
        --push or --pull or --sync-remote-to-local
        --host=<host>
        --port=<port>
        --cipher=<ssl-cipher-string>
        --filter-file=<file>
        --make-sample-filter-file                   : creates a sample filter file
        --debug
    '''

    # parse command line arguments

    opts = (
        'lpath', 'rpath', 'password', 'push', 'pull', 'sync-rdel',
        'host', 'port', 'cipher', 'filter-file', 'make-sample-filter-file',
        'password', 'authcode', 'auth-code', 'no-ssl', 'debug'
    )

    setopts = {}

    for arg in args:
        for opt in opts:
            _opt = '--%s' % opt
            if arg.find(_opt) == 0:
                val = arg[len(_opt):]
                if len(val)> 0 and val[0] == '=':
                    val = val[1:] 
                setopts[opt] = val

    # enable debugging output if specified
    if 'debug' in setopts:
        flycatcher.enable()

    # fill in any missing arguments 
    if 'host' not in setopts:
        setopts['host'] = 'kmcg3413.net'
    if 'port' not in setopts:
        setopts['port'] = '4322'

    if 'authcode' in setopts:
        setopts['password'] = setopts['authcode']
    if 'auth-code' in setopts:
        setopts['password'] = setopts['auth-code']

    if 'rpath' not in setopts:
        setopts['rpath'] = '/'
    if 'lpath' not in setopts:
        print('--lpath=<path> must be specified')
    if 'no-ssl' not in setopts:
        setopts['ssl'] = True
    else:
        setopts['ssl'] = False

    # load filter file if specified
    filter = None
    if 'filter-file' in setopts:
        fpath = setopts['filter-file']
        raise Exception('not implemented')

    # convert certain arguments needed into proper types
    if 'port' in setopts:
        try:
            setopts['port'] = int(setopts['port'])
        except ValueError:
            print('the port must be an integer value not "%s"' % setopts[opt])
            return

    if 'host' not in setopts or 'port' not in setopts:
        print('the --host=<host> and --port=<port> must be specified')
        return

    if 'push' not in setopts and 'pull' not in setopts and 'sync-rdel' not in setopts and 'sync-ldel' not in setopts:
        print('you must specify an operation of push, pull, sync-rdel, or sync-ldel')
        return

    if 'push' in setopts:
        lib.buops.Push(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], filter, setopts['ssl']
        )
        return 
    if 'pull' in setopts:
        lib.buops.Pull(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], filter, setopts['ssl']
        )
        return
    if 'sync-rdel' in setopts:
        lib.buops.SyncRemoteWithDeleted(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], filter, setopts['stash'], setopts['ssl']
        )
        return
    if 'sync-ldel' in setopts:
        raise Exception('not implemented')
    return

# only execute this if we are the primary
# script file being executed by Python
if __name__ == '__main__':
    # set ourselves to idle unless specified to run as normal
    misc.setProcessPriorityIdle()
    # setup standard outputs (run TCP server)
    output.Configure(tcpserver = True)
    main(sys.argv[1:])