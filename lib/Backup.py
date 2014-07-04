'''
    This implements the backup interface which directly supports command line type arguments. However,
    it may be called with arguments supplied from somewhere different. It is just instead of a function
    with arguments you call the main function.
'''
import os
import sys
import os.path
import re
import lib.output as output
import threading
import time
import math

from lib.client import Client2
from lib.client import Client

import lib.buops

def DoFilter(filters, fpath, allownonexistant = False):
    try:
        mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(fpath)
    except:
        # just say the filter failed since we can not access it
        # to event do a stat more than likely, or something has
        # gone wrong
        if allownonexistant is False:
            return False
        # just set the mode to zero.. until i figure
        # out something better
        mode = 0
        size = 0
    
    for f in filters:
        notmatch = False
        
        finvert = f[0]
        ftype = f[1]
        farg = f[2]
        
        # do regular expression matching
        if ftype == 'repattern':
            base = fpath[0:fpath.rfind('/') + 1]
            _fpath = fpath[len(base):]
            result = re.match(farg, _fpath)
            if result is not None:
                result = True
            else:
                result = False
            
        if ftype == 'sizegreater':
            result = False
            if size > farg:
                result = True
        
        if ftype == 'sizelesser':
            result = False
            if size < farg:
                result = True
        
        if ftype == 'mode':
            result = False
            if mode == farg:
                result = True
        
        if finvert:
            # if match exclude file
            if result:
                return False
        else:
            # if match include file
            if result:
                return True
    # if no match on anything then exclude file by default
    return False

    
class Backup:                                
    def EnumRemoteFileCount(self, client, base, lastreport = 0, initial = True):
        nodes = client.DirList(base, Client.IOMode.Block)
        count = 0
        for node in nodes:
            nodename = node[0]
            nodetype = node[1]

            # get stash id 
            try:
                nodestashid = int(nodename[0:nodename.find(b'.')])
            except:
                # just skip it.. non-conforming to stash format or non-numeric stash id
                # maybe even a special file..
                continue
                
            if nodestashid != 0:
                # skip it (directory or file)
                continue
        
            if nodetype != 1:
                # count as file
                count = count + 1
                continue
            
            # drop stash id
            nodename = nodename[nodename.find(b'.') + 1:]
            
            # it is a directory
            _base = base + b'/' + nodename
            _count, lastreport = self.__enumfilesandreport_remote(client, _base, lastreport, initial = False)
            count = count + _count
            
            ct = time.time()
            if ct - lastreport > 5:
                lastreport = ct
                output.SetTitle('filecount', count)
                
        if initial:
            output.SetTitle('filecount', count)
            return count
        return count, lastreport
    
    def EnumLocalFileCount(self, base, lastreport = 0, initial = True, prevcount = 0):
        nodes = os.listdir(base)
        count = 0
        for node in nodes:
            fpath = '%s/%s' % (base, node)
            if os.path.isdir(fpath):
                _count, lastreport = self.__enumfilesandreport(fpath, lastreport = lastreport, initial = False, prevcount = count)
                count = count + _count
            else:
                count = count + 1
            ct = time.time()
            if ct - lastreport > 10:
                lastreport = ct
                output.SetTitle('filecount', count + prevcount)
                
        if initial:
            output.SetTitle('filecount', count)
            return count
        return count, lastreport            
        