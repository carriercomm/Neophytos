'''
	This implements the backup interface which directly supports command line type arguments. However,
	it may be called with arguments supplied from somewhere different. It is just instead of a function
	with arguments you call the main function.
'''
import os
import sys
import os.path
import re
import lib.client as client
import lib.output as output
import threading
import time

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
	c = client.Client2(cfg['remote-host'], cfg['remote-port'], bytes(cfg['storage-auth-code'], 'utf8'))
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
		
	def dopull(self, name, rhost, rport, sac, cfg, rpath, lpath, filter, base = None, c = None, erpath = None, dry = True):
		if c is None:
			print('CONNECTING TO REMOTE SERVER')
			c = client.Client2(rhost, rport, bytes(sac, 'utf8'))
			cfg = self.LoadConfig()
			c.Connect(essl = cfg['ssl'])
			print('CONNECTION ESTABLISHED, SECURED, AND AUTHENTICATED')
		
		if rpath is None:
			raise Exception('rpath can not be None')
		
		# make sure effective remote path is placed under /name/
		if erpath is None:
			erpath = '%s/%s' % (name, rpath)
		
		if dry is True:
			print('NOPE')
			exit()

		
		# i try to do all files in each directory
		# before diving deeper into sub-directories
		# so i push directories into this list then
		# process them after all the files
		dirstodo = []
		
		# list nodes in directory
		nodes = c.DirList(bytes('%s' % erpath, 'utf8'))
		for node in nodes:
			# is this a directory?
			if node[1] == 0xffffffff:
				# yes, so push it to be transverse`d later
				dirstodo.append(node[0].decode('utf8', 'ignore'))
				print('appended directory %s' % node[0])
				continue
			
			lfile = '%s/%s' % (lpath, node[0].decode('utf8', 'ignore'))
			# build the remote path
			rfile = bytes('%s/%s' % (erpath, node[0].decode('utf8', 'ignore')), 'utf8')
			fid = (rfile, 0)
			# pull the file to our local storage device
			# if destination file exists then check if 
			# source file is newer than destination
			print('thinking about pulling %s' % lfile)
			if os.path.exists(lfile):
				# get remote file time
				smtime = c.FileGetTime(fid)
				# get local file time
				mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(lfile)
				if ctime > mtime:
					mtime = ctime
				if mtime >= smtime:
					# local file is either same time or greater so
					# do not worry about pulling the remote file
					print('local file is same time or greater')
					continue
			print('    pulling %s from %s' % (lfile, fid))
			if dry is False:
				# make sure destination directory structure exists
				base = lfile[0:lfile.rfind('/')]
				if os.path.exists(base) is False:
					os.makedirs(base)
				c.FilePull(lfile, fid)
		
		# go through the directories that we saved
		for dir in dirstodo:
			print('  going into %s' % dir)
			self.dopull(name, rhost, rport, sac, cfg, rpath, '%s/%s' % (lpath, dir), filter, base = base, c = c, erpath = '%s/%s' % (erpath, dir), dry = dry)
	
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
	
	def syncdel_async(self, account, target, stash = True):
		cfg = LoadConfig(account = account)
		tcfg = cfg['paths'][target]
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = bytes(cfg['storage-auth-code'], 'utf8')
		c = client.Client2(rhost, rport, sac)
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
						c.FileMove(remote, _newremote)
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
						c.FileMove(remote, _newremote)
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
						c.FileMove(remote, _newremote)
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
	
	'''
		This will push any local files to the remote, or update existing to match local.
	'''
	def dopush(self, name, rhost, rport, sac, cfg, dpath, rpath, filter, base = None, c = None, dry = True, lastdonereport = 0, _donecount = 0):
		if c is None:
			# only connect if not dry run
			if not dry:
				print('CONNECTING TO REMOTE SERVER')
				c = client.Client2(rhost, rport, bytes(sac, 'utf8'))
				cfg = LoadConfig(self.accountname)
				c.Connect(essl = cfg['ssl'])
				print('CONNECTION ESTABLISHED, SECURED, AND AUTHENTICATED')
			
		if rpath is None:
			rpath = ''
			child = False
		else:
			child = True
			
		if base is None:
			base = dpath
		
		# track how many files we have processed
		donecount = 0
		
		try:
			nodes = os.listdir(dpath)
		except OSError:
			print('    skipping')
			return
		
		# push any locals files to the server
		for node in nodes:
			fpath = '%s/%s' % (dpath, node)
			# if directory..
			if os.path.isdir(fpath):
				if DoFilter(filter, fpath):
					if dry:
						print('[DIR-OK] %s' % fpath)
					# also update donecount along the way
					donecount = donecount + self.dopush(name, rhost, rport, sac, cfg, fpath, '%s/%s' % (rpath, node), filter, base = base, c = c, dry = dry, lastdonereport = lastdonereport, _donecount = donecount + _donecount)
				else:
					if dry:
						print('[DIR-IGNORE] %s' % fpath)
				continue
			# run filters
			if DoFilter(filter, fpath):
				# backup the file
				base = fpath[0:fpath.rfind('/') + 1]
				_fpath = fpath[len(base):]
				#print('PROCESSING [%s]' % _fpath)
				fid = bytes('%s/%s/%s' % (name, rpath, _fpath), 'utf8')
				if dry is False:
					c.FilePush(fid, fpath)
				if dry is True:
					print('[OK] %s' % fpath)
			else:
				if dry is True:
					print('[IGNORED] %s' % fpath)
			donecount = donecount + 1
			ct = time.time()
			if ct - lastdonereport > 10:
				lastdonereport = ct
				# update the title to reflect how many files
				# we have processed since the last update
				output.SetTitle('filedonecount', donecount + _donecount)
		
		# iterate through remote files
		#self.__handle_missingremfiles(
			# delete/stash any remote that no longer exists locally
			
		if not child:
			# allow all workers to finish
			c.WaitUntilWorkersFinish()
			return
		return donecount
				
	def __cmd_pull_target(self, cfg, name, target, rpath = None, lpath = None, dry = True):
		print('pulling [%s]' % name)
		
		output.SetTitle('operation', 'pulling %s:%s' % (name, target))
		
		dpath = target['disk-path']
		filter = target['filter']
		
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = cfg['storage-auth-code']
		#def dopull(name, rhost, rport, sac, cfg, rpath, lpath, filter, base = None, c = None, erpath = None, dry = True):
		return self.dopull(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, rpath = rpath, lpath = lpath, filter = filter, dry = dry)
	
	def __enumfilesandreport_remote(self, client, base, lastreport = 0, initial = True):
		nodes = client.DirList(base)
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
		filter = target['filter']
		
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = cfg['storage-auth-code']
		
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
		
		ret = self.dopush(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, dpath = dpath, rpath = rpath, filter = filter, dry = dry)
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
		rpath = '/'
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
		
		if len(args) > 0:
			# treat as list of targets to run (run them even if they are disabled)
			for target in args:
				if target not in cfg['paths']:
					print('    target by name [%s] not found' % target)
				else:
					self.__cmd_pull_target(cfg, target, cfg['paths'][target], rpath = rpath, lpath = '%s/%s' % (lpath, target), dry = dry)
			return
		# run all that are enabled
		for k in cfg['paths']:
			self.__cmd_pull_target(cfg, k, cfg['paths'][k], rpath = rpath, lpath = lpath, dry = dry)	
		
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
