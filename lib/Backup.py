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

def GetConfigPath(account):
	# build base path (without file)
	base = GetConfigBase()
	# add on file
	path = '%s/%s.py' % (base, account)
	return path

def GetConfigBase():
	base = '%s/.neophytos/accounts' % os.path.expanduser('~')
	if os.path.exists(base) is False:
		os.makedirs(base)
	return base
	
def DeleteConfig(cfgname):
	base = GetConfigBase()
	os.delete('%s/%s.py' % (base, cfgname))
	
def GetConfigs():
	base = GetConfigBase()
	nodes = os.listdir(base)
	_nodes = []
	for node in nodes:
		node = node[0:node.rfind('.')]
		_nodes.append(node)
	return _nodes
	
def __LoadConfig(account):
	path = GetConfigPath(account = account)
	if os.path.exists(path) is False:
		return {}
	fd = open(path, 'r')
	try:
		cfg = eval(fd.read())
	except:
		cfg = {}
	fd.close()
	return cfg
	
def LoadConfig(account):
	cfg = __LoadConfig(account = account)
	if 'remote-host' not in cfg:
		cfg['remote-host'] = 'kmcg3413.net'
	if 'remote-port' not in cfg:
		cfg['remote-port'] = 4322
	if 'storage-auth-code' not in cfg:
		cfg['storage-auth-code'] = None
	if 'paths' not in cfg:
		cfg['paths'] = {}
	if 'ssl' not in cfg:
		cfg['ssl'] = True
	return cfg

def GetClientForAccount(account):
	# load account information
	cfg = LoadConfig(account = account)
	print('remote-host:%s remote-port:%s auth:%s' % (cfg['remote-host'], cfg['remote-port'], cfg['storage-auth-code']))
	c = Client2(cfg['remote-host'], cfg['remote-port'], bytes(cfg['storage-auth-code'], 'utf8'))
	c.Connect(essl = cfg['ssl'])
	return c
	
def SaveConfig(self, account, cfg):
	path = self.GetConfigPath(account)
	fd = open(path, 'w')
	pprint.pprint(cfg, fd)
	fd.close()

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
	def cmd_config(self, args):
		if len(args) < 1:
			print('not enough arguments: <server-auth-code>')
			return
		
		sac = args[0]
		
		cfg = LoadConfig(self.accountname)
		cfg['storage-auth-code'] = sac
		SaveConfig(self.accountname, cfg)

	def cmd_add(self, args):
		if len(args) < 2:
			print('not enough arguments: <name> <path>')
			return
			
		name = args[0]
		path = args[1]
		
		if os.path.exists(path) is False:
			print('path [%s] does not exist' % path)
		cfg = LoadConfig(self.accountname)
		
		if name in cfg['paths']:
			print('name [%s] already exists' % name)
			return
			
		cfg['paths'][name] = {}
		cfg['paths'][name]['disk-path'] = path
		cfg['paths'][name]['enabled'] = True
		cfg['paths'][name]['filter'] = [(False, 'repattern', '.*')]
		
		SaveConfig(self.accountname, cfg)
		
		print('added name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_del(self, args):
		if len(args) < 1:
			print('not enough arguments: <name>')
			return
		
		name = args[0]
		
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		path = cfg['paths'][name].get('disk-path', '<error>')
		
		del cfg['paths'][name]
		
		SaveConfig(self.accountname, cfg)
		
		print('deleted name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_disable(self, args):
		if len(args) < 1:
			print('not enough arguments: <name>')
			return
		
		name = args[0]
		
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
			
		path = cfg['paths'][name].get('disk-path', '<error>')
			
		cfg['paths'][name]['enabled'] = False

		SaveConfig(self.accountname, cfg)
		
		print('disabled name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_enable(args):
		if len(args) < 1:
			print('not enough arguments: <name>')
			return
			
		name = args[0]
		
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
			
		path = cfg['paths'][name].get('disk-path', '<error>')
		
		cfg['paths'][name]['enabled'] = True
		
		SaveConfig(self.accountname, cfg)
		
		print('enabled name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_filter(self, args):
		if len(args) < 2:
			print('<target-name> <command>')
			print('commands: add, del, move, clear')
			print('* to list targets use the command list instead of filter')
			return
		
		name = args[0]
		cmd = args[1].lower()
		
		if cmd == 'add':
			return self.cmd_addfilter(name, args[2:])
		if cmd == 'del':
			return self.cmd_delfilter(name, args[2:])
		if cmd == 'move':
			return self.cmd_movfilter(name, args[2:])
		if cmd == 'list':
			return self.cmd_listfilter(name, args[2:])
		if cmd == 'clear':
			return self.cmd_clearfilter(name, args[2:])
		
		print('the command [%s] is not a valid command' % cmd)
		print('use: add, del, move')
		return
	
	def cmd_clearfilter(self, name, args):
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return

		cfg['paths'][name]['filter'] = []
		
		print('the filter has been cleared for target [%s]' % name)
		
		SaveConfig(self.accountnamecfg)
	
	def cmd_listfilter(self, name, args):
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return

		filter = cfg['paths'][name]['filter']

		print('==== FILTER LIST FOR [%s] ====' % name)
		return self.__cmd_list_showfilter(filter)
		
	def cmd_movfilter(self, name, args):
		#filter move <index> down
		#filter move <index> up
		#filter move <index> +1
		#filter move <index> -1
		#filter move <index> <absolute-index>
		#filter move <index> swap <absolute-index>
		if len(args) < 2:
			print('the following commands are valid:')
			print('  move <index> down              - same as -1')
			print('  move <index> up                - same as +1')
			print('  move <index> +1                - can be any number')
			print('  move <index> -1                - can by any number')
			print('  move <index> <absolute-index>  - removes and inserts')
			print('  move <index> swap ...          - swaps')
			return
		
		index = args[0]
		
		try:
			index = int(index)
		except:
			print('...the value [%s] is not an number' % index)
			return
		
		op = args[1].lower()
		
		if op == 'swap':
			swap = True
			op = args[2]
		else:
			swap = False
		
		if op == 'down':
			op = '-1'
		if op == 'up':
			op = '+2'
		
		if op[0] == '+':
			op = index + 1
		elif op[0] == '-':
			op = index - 1
		else:
			# check for numeric
			try:
				op = int(op)
			except:
				print('...expected number for [%s] if not + or - or swap' % op)
				return
		
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		filter = cfg['paths'][name]['filter']
		
		if index >= len(filter) or index < 0:
			print('..the index %s does not exist' % index)
			return
		if op >= len(filter) or op < 0:
			print('..the index %s does not exist' % index)
			return
		
		# basically, just move from 'index' to 'op'
		if swap:
			a = filter[index]
			b = filter[op]
			filter[index] = b
			filter[op] = b
		else:
			f = filter.pop(index)
			filter.insert(op, f)
		
		SaveConfig(self.accountname, cfg)
		return
		
	def cmd_addfilter(self, name, args):
		validtypes = ('repattern', 'sizegreater', 'sizelesser', 'mode')
		inttypes = ('sizegreater', 'sizelesser', 'mode')
		yestxt = ('true', 'yes', 't', 'y', 'ok')
		
		if len(args) < 3:
			print('not enough arguments: <invert> <type> <pattern>')
			print('possible values for <invert> are: %s' % ', '.join(yestxt))
			print('possible values for <type> are: %s' % ', '.join(validtypes))
			print('<pattern> must be numeric for: %s' % ', '.join(inttypes))
			return
		
		invert = args[0].lower()
		type = args[1].lower()
		pattern = args[2]
		
		if type in inttypes:
			try:
				pattern = int(pattern)
			except:
				print('value [%s] must be integer/number for type [%s]' % (pattern, type))
				return
		
		if invert in yestxt:
			invert = True
		else:
			invert = False
		
		if type not in validtypes:
			print('type [%s] is not valid' % type)
			print('the following are valid:')
			print('  %s' % ', '.join(validtypes))
			return
		
		cfg = LoadConfig(self.accountname)
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		cfg['paths'][name]['filter'].append((invert, type, pattern))
		
		SaveConfig(self.accountname, cfg)
		print('added to name [%s] invert:[%s] type:[%s] pattern [%s]' % (name, invert, type, pattern))
		return
		
	def cmd_delfilter(self, name, args):
		if len(args) < 1:
			print('not enough arguments:')
			print('		<index>		- will delete pattern at index')
			return
			
		cfg = self.LoadConfig()
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		try:
			index = int(args[0])
		except:
			print('..index must be a number but was [%s]' % index)
			return
		
		removed = False
		ndx = 0
		for p in cfg['paths'][name]['filter']:
			if ndx == index:
				cfg['paths'][name]['filter'].remove(p)
				print('removed from name [%s] pattern [%s] at index [%s]' % (name, p, index))
				self.SaveConfig(cfg)
				return
			ndx = ndx + 1
		print('could not find index [%s]' % index)
		return
			
	def enumfilecount(self, base, count = 0, dcount = 0, depth = 0):
		nodes = os.listdir(base)
		for node in nodes:
			fpath = '%s/%s' % (base, node)
			if os.path.isdir(fpath):
				_count, _dcount = self.enumfilecount(fpath, count = 0, dcount = 0, depth = depth + 1)
				count = count + _count
				dcount = dcount + _dcount + 1
			else:
				count = count + 1
		return count, dcount
	
	'''
		This will do a remote synchronization for locally deleted files. By default
		it will stash deleted files. If specified it will delete them.
	'''
	def cmd_sync_rdel(self, args):
		# check if we are deleting or stashing
		stash = True
		for arg in args:
			if arg == '--delete':
				args.remove(arg)
				stash = False
				break
	
		if len(args) > 0:
			# treat as list of targets to run (run them even if they are disabled)
			targets = []
			for target in args:
				targets.append(target)
		else:
			targets = cfg['paths']
			
		for target in targets:
			output.SetTitle('operation', 'sync-rdel %s:%s' % (self.accountname, target))
			# this is the old recursive single request style
			#self.syncdel(self.accountname, target, stash = stash)
			# this is the non-recursive multiple asynchronous request style
			self.syncdel_async(self.accountname, target, stash = stash)
	
	'''
	'''
	def dopull_async(self, account, target, lpath = None, rpath = None):
		cfg = LoadConfig(account = account)
		tcfg = cfg['paths'][target]
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = bytes(cfg['storage-auth-code'], 'utf8')
		c = Client2(rhost, rport, sac)
		c.Connect(essl = cfg['ssl'])
		# produce remote and local paths
		if lpath is None:
			lpath = tcfg['disk-path']
		if rpath is None:
			rpath = bytes(target, 'utf8')
		else:
			rpath = bytes(target, 'utf8') + b'/' + rpath
		rpbsz = len(rpath)
		
		jobFileTime = []
		jobFileSize = []
		jobDownload = []
		
		'''
			Transform each node into it's full remote path, then
			place it into the master node list for processing.
		'''
		def __eventDirEnum(pkg, result, vector):
			rpath = pkg[0]
			nodes = pkg[1]
			if result is None:
				return
			for node in result:
				name = node[0]
				
				rev = name[0:name.find(b'.')].decode('utf8')
				if int(rev) != 0:
					continue
				
				name = name[name.find(b'.') + 1:]
				name = rpath + b'/' + name
				
				nodes.append((name, node[1]))
		def __eventFileTime(pkg, result, vector):
			jobFileTime.append((pkg, result))
		
		def __eventFileSize(pkg, result, vector):
			jobFileSize.append((pkg, result))
		
		def __eventFileRead(pkg, result, vector):
			success = result[0]
			if success != 1:
				# for now.. just let someone know shit screwed up.. if they
				# really need it to work they can come edit the code and skip
				# this and continue onward..
				raise Exception('Error On Read From Remote For [%s] At Offset [%x]' % (_lpath, _off))
				return
			data = result[1]
			_lpath = pkg[0]
			_off = pkg[1]
			print('write:%s:%x' % (_lpath, _off))
			# hey.. just keep on moving..
			try:
				fd = open(_lpath, 'r+b')
				fd.seek(_off)
				fd.write(data)
				fd.close()
			except Exception as e:
				print('exception writing to %s' % (_lpath))
				print(e)
				exit()
			
		echo = { 'echo': False }
			
		def __eventEcho(pkg, result, vector):
			pkg['echo'] = True
		
		# first enumerate the remote directory
		_nodes = c.DirList(rpath, Client.IOMode.Block)
		
		nodes = []
		__eventDirEnum((rpath, nodes), _nodes, 0)
		
		sentEcho = False
		while echo['echo'] is False:
			c.HandleMessages(0, None)

			quecount = len(nodes) + len(jobFileTime) + len(jobFileSize) + len(jobDownload)
			if quecount == 0 and c.waitCount() == 0 and sentEcho is False:
				sentEcho = True
				c.Echo(Client.IOMode.Callback, (__eventEcho, echo))
			
			# iterate through files
			for x in range(0, min(100, len(nodes))):
				# might be faste to pop from end of list
				# but this will ensure more expected order
				# of operations..
				node = nodes.pop(0)
				
				_rpath = node[0]
				_lpath = '%s/%s' % (lpath,node[0][rpbsz:].decode('utf8'))
				# if directory issue enumerate call
				if node[1] == 1:
					print('requestingdirenum', _rpath)
					pkg = (_rpath, nodes)
					c.DirList(_rpath, Client.IOMode.Callback, (__eventDirEnum, pkg))
					continue
				# if file issue time check
				pkg = (_rpath, _lpath)
				c.FileTime(_rpath, Client.IOMode.Callback, (__eventFileTime, pkg))
			
			# iterate time responses
			for job in jobFileTime:
				_rpath = job[0][0]
				_lpath = job[0][1]
				_rmtime = job[1]
				if os.path.exists(_lpath):
					stat = os.stat(_lpath)
					_lsize = stat.st_size
					_lmtime = stat.st_mtime
				else:
					_lsize = -1
					_lmtime = 0
					# create the local file (0 sized)
				# if newer then get file size so we can
				# truncate the local file
				if _rmtime >= _lmtime:
					print('date failed for %s with local:%s remote:%s' % (_lpath, _lmtime, _rmtime))
					pkg = (_rpath, _lpath, _lsize)
					c.FileSize(_rpath, Client.IOMode.Callback, (__eventFileSize, pkg))
			jobFileTime = []
			
			# iterate size responses
			for job in jobFileSize:
				_rpath = job[0][0]
				_lpath = job[0][1]
				_lsize = job[0][2]
				_rsize = job[1]
				# if size different truncate local file to match
				if _rsize[0] != 1:
					raise Exception('_rsize for %s failed' % _rpath)
				print('[size] %s lsize:%s rsize:%s' % (_lpath, _lsize, _rsize))
				_rsize = _rsize[1]
				if _lsize != _rsize:
					# truncate local file
					self.truncateFile(_lpath, _rsize)
				# queue a download operation
				pkg = [_rpath, _lpath, _rsize, 0]
				jobDownload.append(pkg)
			jobFileSize = []
			
			# iterate download operations
			tr = []
			chunksize = 1024 * 1024 * 4
			for job in jobDownload:
				_rpath = job[0]
				_lpath = job[1]
				_rsize = job[2]
				_curoff = job[3]
				# determine amount we can read and choose maximum
				_rem = _rsize - _curoff
				if _rem > chunksize:
					_rem = chunksize
				#print('read', _rpath, _rem, _curoff, _rsize)
				pkg = (_lpath, _curoff)
				c.FileRead(_rpath, _curoff, chunksize, Client.IOMode.Callback, (__eventFileRead, pkg))
				if _curoff + _rem >= _rsize:
					tr.append(job)
					print('finish:%s' % (_lpath))
				job[3] = _curoff + _rem
			# remove completed jobs
			for t in tr:
				jobDownload.remove(t)
			# <end-of-loop>
	
	def truncateFile(self, lpath, size):
		if os.path.exists(lpath) is False:
			# get base path and ensure directory structure is created
			base = lpath[0:lpath.rfind('/')]
			if os.path.exists(base) is False:
				os.makedirs(base)
			
			fd = os.open(lpath, os.O_CREAT)
			os.close(fd)
		fd = os.open(lpath, os.O_RDWR)
		os.ftruncate(fd, size)
		os.close(fd)
		print('<trun>:%s' % lpath)
	'''
		I originally started with a threaded model because of the complexity of the entire
		process per file. This gave me a straight forward way to write code and further my
		prototype. Next, after noticing the overhead of threads I decided to do an asynchronous
		polling model. This yielded improved performance but was still eating a lot of CPU. The
		final design here is partially polling (much LESS than before), and it is quite efficient.
		
		I use callbacks to prevent polling for many of the operations.
	'''
	def dopush_async(self, account, target):
		cfg = LoadConfig(account = account)
		tcfg = cfg['paths'][target]
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = bytes(cfg['storage-auth-code'], 'utf8')
		c = Client2(rhost, rport, sac)
		c.Connect(essl = cfg['ssl'])
		# produce remote and local paths
		lpath = tcfg['disk-path']
		lpbsz = len(lpath)
		rpath = bytes(target, 'utf8')
		
		jobDirEnum = []				# stage 1
		jobGetRemoteSize = []		# stage 2
		jobGetModifiedDate = []		# stage 3 (optional)
		jobPatch = []				# stage 4.A
		jobUpload = []				# stage 4.B
		
		jobDirEnum.append(lpath)

		echo = { 'echo': False }
		sentEcho = False
		
		'''
			These turn the async polling model into a async callback model, at
			least to some extent. We still poll but we do not poll individual
			objects which reduces polling time (CPU burn)..
		'''
		def __eventFileSize(pkg, result, vector):
			jobGetRemoteSize.append((pkg, result))
		def __eventFileTime(pkg, result, vector):
			jobGetModifiedDate.append((pkg, result)) 
		def __eventEcho(pkg, result, vector):
			pkg['echo'] = True
		
		# statistics
		databytesout = 0
		stat_uptodate = 0
		stat_uploaded = 0
		stat_patched = 0
		stat_checked = 0
		
		dd = time.time()
		
		# the soft limit for application level buffer size
		buflimit = 1024 * 1024 * 4
		
		# keep going until we get the echo 
		while echo['echo'] is False:
			# read any messages
			c.HandleMessages(0, None)
			
			#if time.time() - dd > 20:
			#	c.dbgdump()
			#	exit()
			
			# do this after handle messages because there may be some added; if quecount
			# is zero it means no pending operations
			quecount = len(jobDirEnum) + len(jobGetRemoteSize) + len(jobGetModifiedDate) + len(jobPatch) + len(jobUpload)
			
			output.SetTitle('WaitingVectors', c.waitCount())
			# if we are not waiting on anything from the client then we could close
			# the connection *except* it might cause the remote to drop packets that
			# are not waiting on a result from.. so since we can determine that we
			# will never generate any more packets we can send an echo which will
			# get a reply and once that happens we can shut down the connection
			if quecount == 0 and c.waitCount() == 0 and sentEcho is False:
				sentEcho = True
				c.Echo(Client.IOMode.Callback, (__eventEcho, echo))
			
			# i do this after handle messages because it will be calling
			# the callbacks which will update the job lists and if we call
			# it before only jobUpload and jobPatch will likely be over zero
			# because the other jobs execute right as they are received
			dt = time.time() - c.bytesoutst
			outdata = '%.03f' % (databytesout / 1024 / 1024 / dt)
			outcontrol = '%.03f' % ((c.allbytesout - databytesout) / 1024 / 1024 / dt)
			output.SetTitle('DataOutMB', outdata)
			output.SetTitle('ControlOutMB', outcontrol)
			output.SetTitle('Jobs[DirEnum]', len(jobDirEnum))
			output.SetTitle('Jobs[GetRemoteSize]', len(jobGetRemoteSize))
			output.SetTitle('Jobs[GetModDate]', len(jobGetModifiedDate))
			output.SetTitle('Jobs[Patch]', len(jobPatch))
			output.SetTitle('Jobs[Upload]', len(jobUpload))
			output.SetTitle('UpToDate', stat_uptodate)
			output.SetTitle('Uploaded', stat_uploaded)
			output.SetTitle('Checked', stat_checked)
			output.SetTitle('Patched', stat_patched)

			# send if can send
			boutbuf = c.getBytesToSend()
			# just hold here until we get the buffer down; this
			# is mainly going to be caused by upload operations
			# throwing megabytes of data into the buffer
			if boutbuf > buflimit:
				print('emptying outbound buffer..')
				# just empty the out going buffer completely.. then of course
				# fill it up again; having the buffer fill up is not actually
				# a bad thing as it means we are exceeding the network throughput
				# which is good because our CPU wont be running wide open
				while c.getBytesToSend() > 0:
					# pull data out of network driver buffers into our own buffers or
					# process it if it has callbacks and essentially place it into
					# our own buffers just processed <humor intended> ...
					# OR/AND
					# flush data from our buffers
					c.handleOrSend()
					#print('left:%s' % c.getBytesToSend())
					
					# keep the status updated
					dt = time.time() - c.bytesoutst
					outdata = '%.03f' % (databytesout / 1024 / 1024 / dt)
					outcontrol = '%.03f' % ((c.allbytesout - databytesout) / 1024 / 1024 / dt)
					output.SetTitle('DataOutMB', outdata)
					output.SetTitle('ControlOutMB', outcontrol)
					output.SetTitle('OutBuffer', c.getBytesToSend())
				#print('continuing..')
			else:
				# just send what we can right now
				c.send()

			# enum directories and create tadjobs
			quecount = len(jobGetRemoteSize) + len(jobGetModifiedDate) + len(jobPatch) + len(jobUpload)
			# just an effort to keep from eating too much memory with jobs, if we are here
			# we are likely way ahead of the network in terms of throughput so just wait a
			# bit before adding more jobs..
			if quecount < 2000:
				delayedjobDirEnum = []
				for dej in jobDirEnum:
					#print('<enuming-dir>:%s' % dej)
					nodes = os.listdir(dej)
					for node in nodes:
						_lpath = '%s/%s' % (dej, node)
						if os.path.isdir(_lpath):
							# delay this..
							delayedjobDirEnum.append(_lpath)
							continue
						stat = os.stat(_lpath)
						# send request and create job entry
						_lsize = stat.st_size
						_rpath = rpath + bytes(_lpath[lpbsz:], 'utf8')
						#print('<getting-size>:%s' % _rpath)
						if _lsize > 1024 * 1024 * 200:
							continue
						stat_checked = stat_checked + 1
						pkg = (_rpath, _lpath, _lsize, None, int(stat.st_mtime))
						c.FileSize(_rpath, Client.IOMode.Callback, (__eventFileSize, pkg))
					
					# just do one directory each time; want this to
					# stay as a loop so it can be adjusted; also remove
					# it so it is not done over and over..
					output.SetTitle('LastDir', dej)
					jobDirEnum.remove(dej)
					break
				# we can not add them as we are iterating or
				# we will never stop iterating
				for delayed in delayedjobDirEnum:
					jobDirEnum.append(delayed)

			# look for replies on remote sizes and create next job
			tr = []
			for rsj in jobGetRemoteSize:
				pkg = rsj[0]
				_result = rsj[1]
				_rpath = pkg[0]
				_lpath = pkg[1]
				_lsize = pkg[2]
				_vector = pkg[3]
				_lmtime = pkg[4]
				# result[0] = success code is non-zero and result[1] = size (0 on failure code)
				_rsize = _result[1]
				# if file does not exist go trun/upload route.. if it does
				# exist and the size is the same then check the file modified
				# date and go from there
				if _lsize != _rsize:
					print('[size] file:%s local:%s remote:%s' % (_lpath, _lsize, _rsize))
				if _lsize == _rsize and _result[0] == 1:
					# need to check modified date
					#print('<getting-time>:%s' % _lpath)
					pkg = (_rpath, _lpath, _rsize, _lsize, _vector, _lmtime)
					c.FileTime(_rpath, Client.IOMode.Callback, (__eventFileTime, pkg))
				else:
					# first make the remote size match the local size
					#print('<trun>:%s' % _lpath)
					c.FileTrun(_rpath, _lsize, Client.IOMode.Discard)
					# need to decide if we want to upload or patch
					if True or (math.min(_rsize, _lsize) / math.max(_rsize, _lsize) < 0.5):
						# make upload job
						print('<upload>:%s' % _lpath)
						jobUpload.append([_rpath, _lpath, _rsize, _lsize, 0])
					else:
						# make patch job
						jobPatch.append([_rpath, _lpath, _rsize, _lsize])
			jobGetRemoteSize = []
			
			# iterate
			tr = []
			for rtj in jobGetModifiedDate:
				pkg = rtj[0]
				_rmtime = rtj[1]
				_rpath = pkg[0]
				_lpath = pkg[1]
				_rsize = pkg[2]
				_lsize = pkg[3]
				_vector = pkg[4]
				_lmtime = pkg[5]
				if _rmtime < _lmtime:
					# need to decide if we want to upload or patch
					if True or math.min(_rsize, _lsize) / math.max(_rsize, _lsize) < 0.5:
						# make upload job
						print('<upload>:%s' % _lpath)
						jobUpload.append([_rpath, _lpath, _rsize, _lsize, 0])
					else:
						# make patch job
						jobPatch.append([_rpath, _lpath, _rsize, _lsize])
				else:
					# just drop it since its either up to date or newer
					#print('<up-to-date>:%s' % _lpath)
					stat_uptodate = stat_uptodate + 1
				continue
			jobGetModifiedDate = []
			
			# 
			tr = []
			cjc = 0
			for uj in jobUpload:
				_rpath = uj[0]
				_lpath = uj[1]
				_rsize = uj[2]
				_lsize = uj[3]
				_curoff = uj[4]
				_chunksize = 1024 * 1024
				# see what we can send
				_rem = _lsize - _curoff
				if _rem > _chunksize:
					_rem = _chunksize
				else:
					tr.append(uj)
				# open local file and read chunk
				_fd = open(_lpath, 'rb')
				_fd.seek(_curoff)
				_data = _fd.read(_rem)
				_fd.close()
				print('<wrote>:%s:%x' % (_lpath, _curoff))
				c.FileWrite(_rpath, _curoff, _data, Client.IOMode.Discard)
				# help track statistics for data out in bytes (non-control data)
				databytesout = databytesout + _rem
				if c.getBytesToSend() > buflimit:
					break
				# just a kinda safe upper limit in the case something
				# happens and we have tons of super small files i dont
				# want that the overload memory
				if cjc > 10000:
					break
				# advance our current offset
				uj[4] = _curoff + _rem
				cjc = cjc + 1
			# remove finished jobs
			ct = time.time()
			for uj in tr:
				# set the modified time on the file to the current
				# time to represent it is up to date
				_rpath = uj[0]
				c.FileSetTime(_rpath, int(ct), int(ct), Client.IOMode.Discard)
				jobUpload.remove(uj)
				stat_uploaded = stat_uploaded + 1
			continue
		c.close()
	'''
		I originally started with an recursive model which was slow because of the
		net latency between the client and server where i waited for each reply to
		each request. This new model is asynchronous and tries to max out the net
		and cpu if possible. I might add in a throttle later, but for now it just
		shovels packets out as fast as possible.
	'''
	def syncdel_async(self, account, target, stash = True):
		cfg = LoadConfig(account = account)
		tcfg = cfg['paths'][target]
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = bytes(cfg['storage-auth-code'], 'utf8')
		c = Client2(rhost, rport, sac)
		c.Connect(essl = cfg['ssl'])
		# produce remote and local paths
		lpath = tcfg['disk-path']
		rpath = bytes(target, 'utf8') + b'/'
		
		# initialize our wait list
		waitlist = {}
		waitlist[c.DirList(rpath, block = False, discard = False)] = (lpath, rpath)
		
		output.SetTitle('account', account)
		output.SetTitle('target', target)
		
		donecount = 0
		stashfilecount = 0
		stashdircount = 0
		
		# keep going until nothing is left in the wait list
		while len(waitlist) > 0:
			dt = time.time() - c.bytesoutst
			
			outdata = '%.03f' % (c.bytesout / 1024 / 1024 / dt)
			outcontrol = '%.03f' % ((c.allbytesout - c.bytesout) / 1024 / 1024 / dt)
			
			output.SetTitle('DataOutMB', outdata)
			output.SetTitle('ControlOutMB', outcontrol)
			output.SetTitle('PendingRequests', len(waitlist))
			output.SetTitle('FileDoneCount', donecount)
			output.SetTitle('StashedFiles', stashfilecount)
			output.SetTitle('StashedDirs', stashdircount)
		
			# process any incoming messages; the 0 means
			# wait 0 seconds which is non-blocking; if
			# it was None we would block for a message
			#print('handling messages')
			c.HandleMessages(0, None)
			
			# do we have pending data to be sent
			if c.canSend():
				# send it.. we can eventually stall out
				# waiting for data when there is data to
				# send and the server's incoming buffer is
				# empty
				c.send()
			
			# see if anything has arrived
			toremove = []
			toadd = []
			#print('checking for arrived requests')
			for v in waitlist:
				#print('checking for %s' % v)
				# check if it has arrived
				nodes = c.GetStoredMessage(v)
				# okay remove it from waitlist
				if nodes is None:
					#print('    not arrived')
					continue
				toremove.append(v)
				# yes, so process it
				subdirs = []
				for node in nodes:
					lpath = waitlist[v][0]
					rpath = waitlist[v][1]
				
					nodename = node[0]
					nodetype = node[1]
					
					donecount = donecount + 1
					
					# get stash id 
					try:
						nodestashid = int(nodename[0:nodename.find(b'.')])
					except:
						# just skip it.. non-conforming to stash format or non-numeric stash id
						continue
					
					# check if current
					if nodestashid != 0:
						# it is a stashed version (skip it)
						continue
					
					# drop stash id
					nodename = nodename[nodename.find(b'.') + 1:]
					
					# build remote path as bytes type
					remote = rpath + b'/' + nodename
					
					# build local path as string
					local = '%s/%s' % (lpath, nodename.decode('utf8'))
					
					# determine if local resource exists
					lexist = os.path.exists(local) 
					rexist = True
					
					#print('checking remote:[%s] for local:[%s]' % (remote, local))
					
					# determine if remote is directory
					if nodetype == 1:
						risdir = True
					else:
						risdir = False
					
					# determine if local is a directory
					if lexist:
						lisdir = os.path.isdir(local)
					else:
						lisdir = False

					#remote = b'%s/%s.%s' % (rpath, nodestashid, nodename)				# bytes  (including stash id)
					remote = rpath + b'/' + bytes('%s' % nodestashid, 'utf8') + b'\x00' + nodename
					
					# local exist and both local and remote is a directory
					if lexist and risdir and lisdir:
						# go into remote directory and check deeper
						# delay this..
						_lpath = '%s/%s' % (lpath, nodename.decode('utf8'))							# string
						#print('[pushing for sub-directory]:%s' % _lpath)
						subdirs.append((_lpath, remote))
						continue
					
					# local exist and remote is a directory but local is a file
					if lexist and risdir and not lisdir:
						print('[stashing remote directory]:%s' % local)
						# stash remote directory, use time.time() as the stash id since it
						# should be unique and also easily serves to identify the latest stashed
						# remote since zero/0 is reserved for current working version
						stashdircount = stashdircount + 1
						t = int(time.time() * 1000000.0)
						_newremote = rpath + b'/' + bytes('%s' % t, 'utf8') + b'\x00' + nodename
						# one problem is the remote directory could contain a lot of files that
						# are were actually moved or copied somewhere else - i am thinking of
						# using another algorithm to pass over and link up clones saving server
						# space
						c.FileMove(remote, _newremote, Client.IOMode.Discard)
						# let push function update local file to remote
						continue
						
					# local exist and remote is a file but local is a directory
					if lexist and not risdir and lisdir:
						print('[stashing remote file]:%s' % local)
						# stash remote file
						stashfilecount = stashfilecount + 1
						#_newremote = b'%s/%s.%s' % (rpath, time.time(), nodename)
						t = int(time.time() * 1000000.0)
						_newremote = rpath + b'/' + bytes('%s' % t, 'utf8') + b'\x00' + nodename
						c.FileMove(remote, _newremote, Client.IOMode.Discard)
						# let push function update local directory to remote
						continue
						
					# local does not exist
					if not lexist:
						print('[stashing deleted]:%s' % local)
						if risdir:
							stashdircount = stashdircount + 1
						else:
							stashfilecount = stashfilecount + 1
						#_newremote = b'%s/%s.%s' % (rpath, time.time(), nodename)
						t = int(time.time() * 1000000.0)
						_newremote = rpath + b'/' + bytes('%s' % t, 'utf8') + b'\x00' + nodename
						c.FileMove(remote, _newremote, Client.IOMode.Discard)
						continue
					continue
					# <end-of-node-loop> (looping over results of request)
				# create requests for any sub-directories
				for subdir in subdirs:
					_lpath = subdir[0]
					_rpath = subdir[1]
					#print('[requesting]:%s' % _rpath)
					output.SetTitle('RecentDir', _lpath)
					toadd.append((c.DirList(_rpath, block = False, discard = False), _lpath, _rpath))
				# <end-of-wait-list-loop> (looping over waiting vectors)
			
			# add anything we got
			for p in toadd:
				waitlist[p[0]] = (p[1], p[2])
			# remove anything we got from the wait list
			for v in toremove:
				del waitlist[v]
			
			# if we just fly by we will end up burning
			# like 100% CPU *maybe* so lets delay a bit in
			#time.sleep(0.01)
					
	def __cmd_pull_target(self, account, target, lpath = None, rpath = None):
		print('pulling [%s] of [%s]' % (target, account))
		
		output.SetTitle('operation', 'pulling')
		
		#def dopull(name, rhost, rport, sac, cfg, rpath, lpath, filter, base = None, c = None, erpath = None, dry = True):
		#return self.dopull(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, rpath = rpath, lpath = lpath, filter = filter, dry = dry)
		#def dopull_async(self, account, target, lpath = None):
		self.dopull_async(account, target, lpath, rpath)
	
	def __enumfilesandreport_remote(self, client, base, lastreport = 0, initial = True):
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
	
	def __enumfilesandreport(self, base, lastreport = 0, initial = True, prevcount = 0):
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
			
	
	def __cmd_push_target(self, cfg, name, target, rpath = None, lpath = None, dry = True):
		print('pushing [%s]' % name)
		
		output.SetTitle('account', self.accountname)
		output.SetTitle('target', name)
		
		dpath = target['disk-path']
		#filter = target['filter']
		
		#rhost = cfg['remote-host']
		#rport = cfg['remote-port']
		#sac = cfg['storage-auth-code']
		
		# enumerate all files and directories
		# using a separate thread so we can
		# report total count and anything reading
		# the status can compute a percentage, i hate
		# using a thread but I am hoping this is somewhat
		# I/O bound therefore it should work nicer with
		# the other threads, the good thing being it will
		# eventually terminate all on it's own
		tfscan = threading.Thread(target = Backup.__enumfilesandreport, args = (self, dpath))
		tfscan.daemon = True
		self.tfscan = tfscan
		tfscan.start()
		
		ret = self.dopush_async(self.accountname, name)
		#def dopush_async(self, account, target):
		#ret = self.dopush(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, dpath = dpath, rpath = rpath, filter = filter, dry = dry)
		print('DONE')
		return ret
		
	'''	
		@sdescription:		Used to disable or enable SSL.
	'''
	def cmd_ssl(self, args):
		if len(args) < 1:
			print('    You must provide a case-insensitive Yes, No, True, or False.')
			return
		
		arg = args[0].lower()
		
		cfg = LoadConfig(self.accountname)
		
		if arg in ('yes', 'y', 'true', 't', 'enable', 'activate'):
			cfg['ssl'] = True
			SaveConfig(self.accountname, cfg)
			print('    SSL has been enabled!')
			return
		cfg['ssl'] = False
		SaveConfig(self.accountname, cfg)
		print('    SLL has been DISabled')
		return
		
	def cmd_pull(self, args, dry = True):
		cfg = LoadConfig(self.accountname)
		
		if cfg['storage-auth-code'] is None:
			print('   Opps.. you need to do <program> config <server-auth-code>')
			print('')
			print('   The server auth code serves as your username and password.')
			print('')
			print('   You can get one from: http://www.kmcg341.net/neophytos')
			return

		# check for and remove any arguments
		lpath = None
		rpath = None
		_args = args
		args = []
		for arg in _args:
			if arg.startswith('--rpath='):
				rpath = arg[8:]
				continue
			if arg.startswith('--lpath='):
				lpath = arg[8:]
				continue
			args.append(arg)
		
		if lpath is None:
			print('please use --lpath=/path/to/download/to')
			print('to specify the path to restore to; this')
			print('is to prevent accidental overwrite of')
			print('original data by mistake; you must specify')
			print('the path to restore to!')
			return
		
		dotargets = []
		if len(args) > 0:
			for target in args:
				dotargets.append(target)
		else:
			for target in cfg['paths']:
				dotargets.append(target)
				
		for target in dotargets:
			self.__cmd_pull_target(self.accountname, target, lpath = '%s/%s' % (lpath, target), rpath = rpath)
		
	def __cmd_chksize_target(self, cfg, name, target):
		dpath = target['disk-path']
		
		total = 0
		doing = []
		todo = []
		
		doing.append(dpath)
		while len(doing) > 0:
			for path in doing:
				nodes = os.listdir(path)
				sys.stdout.flush()
				for node in nodes:
					fpath = '%s/%s' % (path, node)
					if os.path.isdir(fpath):
						todo.append(fpath)
						continue
					# see if one of the filters marks it as valid
					if DoFilter(target['filter'], fpath):
						# get file size
						mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(fpath)
						total = total + size
				
			# swap
			doing = todo
			todo = []
		print('target:[%s] %sMB %sGB' % (name, total / 1024 / 1024, total / 1024 / 1024 / 1024))
		return
		
	def cmd_chksize(self, args):
		cfg = LoadConfig(self.accountname)

		if len(args) > 0:
			# treat as list of targets to run (run them even if they are disabled)
			for target in args:
				if target not in cfg['paths']:
					print('    target by name [%s] not found' % target)
				else:
					self.__cmd_chksize_target(cfg, target, cfg['paths'][target])
			return
			
		# run all that are enabled
		for k in cfg['paths']:
			self.__cmd_chksize_target(cfg, k, cfg['paths'][k])
		
	def cmd_push(self, args, dry = True):
		cfg = LoadConfig(self.accountname)

		if cfg['storage-auth-code'] is None:
			print('   Opps.. you need to do <program> config <server-auth-code>')
			print('')
			print('   The server auth code serves as your username and password.')
			print('')
			print('   You can get one from: http://www.kmcg341.net/neophytos')
			return
		
		# check for --rpath=xxx and set rpath then
		# remove the argument from the list of targets
		rpath = ''
		for arg in args:
			if arg.startswith('--rpath='):
				rpath = arg[8:]
				args.remove(arg)
				break
				
		if len(args) > 0:
			# treat as list of targets to run (run them even if they are disabled)
			for target in args:
				if target not in cfg['paths']:
					print('    target by name [%s] not found' % target)
				else:
					self.__cmd_push_target(cfg, target, cfg['paths'][target], rpath = rpath, dry = dry)
			return
		# run all that are enabled
		for k in cfg['paths']:
			self.__cmd_push_target(cfg, k, cfg['paths'][k], dry = dry)
		return
		
	def __cmd_list_showfilter(self, filter):
		ndx = 0
		for p in filter:
			print('    %02i: [%s]' % (ndx, p))
			ndx = ndx + 1
		
	def cmd_list(self, args):
		if len(args) > 0:
			name = args[0]
		else:
			name = None
		
		cfg = LoadConfig(self.accountname)
		
		if name is not None:
			# display information about name		
			print('== %s ==' % name)
			print('    enabled: %s' % cfg[name]['enabled'])
			print('    disk-path: %s' % cfg[name]['disk-path'])
			self.__cmd_list_showfilter(cfg['paths'][name]['filter'])

		if len(cfg['paths']) < 1:
			print('nothing to list, try:')
			print('  add a new backup path:    <program> add <name> <path>')
			print('  display help:             <program>')
			return
		
		for k in cfg['paths']:
			print('== %s ==' % k)
			print('    enabled: %s' % cfg['paths'][k]['enabled'])
			print('    disk-path: %s' % cfg['paths'][k]['disk-path'])
			self.__cmd_list_showfilter(cfg['paths'][k]['filter'])		
		return

	def showhelp(self):
		print('Neophytos Standard Backup Client')
		print('Leonard Kevin McGuire Jr 2014')
		print('-------------------------------------')
		print('add                   - add account')
		print('del                   - del account')
		print('list                  - list accounts')
		print('-------------------------------------')
		print('<account> config      - configures the remote server')
		print('<account> add         - add backup path')
		print('<account> del         - delete backup path')
		print('<account> disable     - disable backup path')
		print('<account> enable      - enable backup path')
		print('<account> filter      - lists filter commands')
		print('<account> dry-push	 - pretend to do push')
		print('<account> push        - push (backup) all enabled or specified backup')
		print('<account> sync-rdel	 - stash/delete locally deleted files and directories')
		print('<account> reduce      - find copies and link them together')
		print('<account> dry-pull    - pretend to do pull')
		print('<account> pull        - pull (restore) all enabled or specified backup')
		print('<account> list        - list backup paths or filters for specified')
		print('<account> chksize     - will process all local files and display the total size')
		print(' Example:')
		print('    <program> <account> add <name> <path>')
		print('    <program> <account> del <name>')
		print('    <program> <account> disable <name>')
		print('    <program> <account> enable <name>')
		print('    <program> <account> filter [displays help]')
		print('    <program> <account> sync-rdel <(optional)name> ...')
		print('    <program> <account> dry-push <(optional)name> <(optional)name> ...')
		print('    <program> <account> push <(optional)name> <(optional)name> ...')
		print('    <program> <account> dry-pull <(optional)name> <(optional)name> ...')
		print('    <program> <account> pull <(optional)name> <(optional)name> ...')
		print('    <program> <account> list <(optional)name>')
		
	def main(self, args):
		specialnames = (
			'add', 'del', 'list', 'config', 'disable', 'enable', 'add-filter', 'del-filter', 
			'dry-push', 'push', 'dry-pull', 'pull', 'list', 'chksize'
		)

		if len(args) < 1:
			return self.showhelp()
			
		output.SetTitle('user', os.getlogin())
		
		# a very easy and conservative number of threads; i wish i had used an
		# asynchronous model but i ended up using threads to keep from rewriting
		# what i should have rewrote, but it ended up working well; they are 
		# mainly used to counter being I/O bound by the latency of the server; in
		# python these do not actually run in parallel but rather in series
		self.maxthread = 10
		# look for max-thread argument
		for arg in args:
			if arg.find('--max-thread=') == 0:
				# parse it and remove it from arguments
				self.maxthread = int(arg[13:])
				args.remove(arg)
				print('max threads set to [%s]' % self.maxthread)
				break
		
		if args[0] == 'add':
			args = args[1:]
			if len(args) < 2:
				print('add <account-name> <remote-host> <remote-port(optional)')
				return
			self.accountname = args[0]
			# will create the configuration file also
			cfg = LoadConfig(self.accountname)
			cfg['remote-host'] = args[1]
			if len(args) > 2:
				cfg['remote-port'] = int(args[2])
			SaveConfig(self.accountname, cfg)
			return
			
		if args[0] == 'del':
			args = args[1:]
			if len(args) < 1:
				print('del <account-name>')
			configs = GetConfigs()
			if args[0] not in configs:
				print('The account name [%s] was not found.' % args[0])
				return
			DeleteConfig(args[0])
			return
		
		if args[0] == 'list':
			configs = GetConfigs()
			print('=== ACCOUNT NAMES ===')
			for config in configs:
				print('    %s' % config)
			return
		
		# must be account name (check its not special)
		if args[0] in specialnames:
			print('The account name can not be a special name. The following are special:')
			print(', '.join(specialnames))
			return
			
		# set global class member variable
		self.accountname = args[0]
		
		# make sure account name exists
		if os.path.exists(GetConfigPath(self.accountname)) is False:
			print('The account name [%s] does not exist. Try the list command.' % self.accountname)
			return
		
		# process remaining arguments
		args = args[1:]
		
		if len(args) < 1:
			# must have command after account name
			return self.showhelp()
		
		if args[0] == 'sync-rdel':
			return self.cmd_sync_rdel(args[1:])
		if args[0] == 'add':
			return self.cmd_add(args[1:])
		if args[0] == 'del':
			return self.cmd_del(args[1:])
		if args[0] == 'disable':
			return self.cmd_disable(args[1:])
		if args[0] == 'enable':
			return self.cmd_enable(args[1:])
		if args[0] == 'filter':
			return self.cmd_filter(args[1:])
		if args[0] == 'dry-push':
			return self.cmd_push(args[1:], dry = True)
		if args[0] == 'chksize':
			return self.cmd_chksize(args[1:])
		if args[0] == 'push':
			return self.cmd_push(args[1:], dry = False)
		if args[0] == 'dry-pull':
			return self.cmd_pull(args[1:], dry = True)
		if args[0] == 'pull':
			return self.cmd_pull(args[1:], dry = False)
		if args[0] == 'list':
			return self.cmd_list(args[1:])
		if args[0] == 'config':
			return self.cmd_config(args[1:])
		if args[0] == 'ssl':
			return self.cmd_ssl(args[1:])
		print('unknown command')
