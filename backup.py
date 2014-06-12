import client
import os
import os.path
import sys
import pprint
import re

class ConsoleApplication:
	def GetConfigPath(self):
		# build base path (without file)
		base = self.GetConfigBase()
		# add on file
		path = '%s/%s.py' % (base, self.accountname)
		return path
		
	def GetConfigBase(self):
		base = '%s/.neophytos/accounts' % os.path.expanduser('~')
		if os.path.exists(base) is False:
			os.makedirs(base)
		return base
		
	def DeleteConfig(self, cfgname):
		base = self.GetConfigBase()
		os.delete('%s/%s.py' % (base, cfgname))
		
	def GetConfigs(self):
		base = self.GetConfigBase()
		nodes = os.listdir(base)
		_nodes = []
		for node in nodes:
			node = node[0:node.rfind('.')]
			_nodes.append(node)
		return _nodes
		
	def __LoadConfig(self):
		path = self.GetConfigPath()
		if os.path.exists(path) is False:
			return {}
		fd = open(path, 'r')
		cfg = eval(fd.read())
		fd.close()
		return cfg
		
	def LoadConfig(self):
		cfg = self.__LoadConfig()
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

	def cmd_config(self, args):
		if len(args) < 1:
			print('not enough arguments: <server-auth-code>')
			return
		
		sac = args[0]
		
		cfg = self.LoadConfig()
		cfg['storage-auth-code'] = sac
		self.SaveConfig(cfg)
		
	def SaveConfig(self, cfg):
		path = self.GetConfigPath()
		fd = open(path, 'w')
		pprint.pprint(cfg, fd)
		fd.close()

	def cmd_add(self, args):
		if len(args) < 2:
			print('not enough arguments: <name> <path>')
			return
			
		name = args[0]
		path = args[1]
		
		if os.path.exists(path) is False:
			print('path [%s] does not exist' % path)
		cfg = self.LoadConfig()
		
		if name in cfg['paths']:
			print('name [%s] already exists' % name)
			return
			
		cfg['paths'][name] = {}
		cfg['paths'][name]['disk-path'] = path
		cfg['paths'][name]['enabled'] = True
		cfg['paths'][name]['filter'] = ['.*']
		
		self.SaveConfig(cfg)
		
		print('added name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_del(self, args):
		if len(args) < 1:
			print('not enough arguments: <name>')
			return
		
		name = args[0]
		
		cfg = self.LoadConfig()
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		path = cfg['paths'][name].get('disk-path', '<error>')
		
		del cfg['paths'][name]
		
		self.SaveConfig(cfg)
		
		print('deleted name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_disable(self, args):
		if len(args) < 1:
			print('not enough arguments: <name>')
			return
		
		name = args[0]
		
		cfg = self.LoadConfig()
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
			
		path = cfg['paths'][name].get('disk-path', '<error>')
			
		cfg['paths'][name]['enabled'] = False

		self.SaveConfig(cfg)
		
		print('disabled name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_enable(args):
		if len(args) < 1:
			print('not enough arguments: <name>')
			return
			
		name = args[0]
		
		cfg = self.LoadConfig()
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
			
		path = cfg['paths'][name].get('disk-path', '<error>')
		
		cfg['paths'][name]['enabled'] = True
		
		self.SaveConfig(cfg)
		
		print('enabled name [%s] with path [%s]' % (name, path))
		return
		
	def cmd_addfilter(self, args):
		if len(args) < 2:
			print('not enough arguments: <name> <pattern>')
			return
		
		name = args[0]
		pattern = args[1]
		
		cfg = self.LoadConfig()
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		cfg['paths'][name]['filter'].append(pattern)
		
		self.SaveConfig(cfg)
		print('added to name [%s] pattern [%s]' % (name, pattern))
		return
		
	def cmd_delfilter(args):
		if len(args) < 1:
			print('not enough arguments:')
			print('		<name>				- will list pattern with index')
			print('		<name> <index>		- will delete pattern at index')
			return
			
		cfg = self.LoadConfig()
			
		name = args[0]
		
		if name not in cfg['paths']:
			print('name [%s] does not exist' % name)
			return
		
		if len(args) < 2:
			print('== LISTING PATTERNS ==')
			# list patterns
			ndx = 0
			for p in cfg['paths'][name]['filter']:
				print('		%02i: [%s]' % (ndx, p))
				ndx = ndx + 1
			return
		
		index = int(args[1])
		
		removed = False
		ndx = 0
		for p in cfg['paths'][name]['filter']:
			if ndx == index:
				cfg['paths'][name]['ipatterns'].remove(p)
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
				#print(fpath)
				_count, _dcount = self.enumfilecount(fpath, count = 0, dcount = 0, depth = depth + 1)
				count = count + _count
				dcount = dcount + _dcount + 1
			else:
				count = count + 1
		return count, dcount
	
	def dopush(self, name, rhost, rport, sac, cfg, dpath, rpath, filter, base = None, c = None, dry = True, totalcount = None):
		if c is None:
			print('CONNECTING TO REMOTE SERVER')
			c = client.Client2(rhost, rport, bytes(sac, 'utf8'))
			cfg = self.LoadConfig()
			c.Connect(essl = cfg['ssl'])
			print('CONNECTION ESTABLISHED, SECURED, AND AUTHENTICATED')
			
		if rpath is None:
			rpath = ''
			
		if base is None:
			base = dpath
			print('SCANNING TARGET DIRECTORY')
			totalcount, tmp = self.enumfilecount(dpath)
			self.curcount = 0
			
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
				self.dopush(name, rhost, rport, sac, cfg, fpath, '%s/%s' % (rpath, node), filter, base = base, c = c, dry = dry, totalcount = totalcount)
				continue
			self.curcount = self.curcount + 1
			print('PERCENTAGE:%.2f' % (self.curcount / totalcount))
			# run filters
			if self.dofilters(filter, fpath):
				# backup the file
				base = fpath[0:fpath.rfind('/') + 1]
				_fpath = fpath[len(base):]
				#print('PROCESSING [%s]' % _fpath)
				lfile = fpath
				fid = (bytes('%s/%s/%s' % (name, rpath, _fpath), 'utf8'), 0)
				if dry is False:
					c.FilePush(fid, lfile)
		# iterate through remote files
			# delete/stash any remote that no longer exists locally
		
	def __cmd_pull_target(self, cfg, name, target, rpath = None, lpath = None, dry = True):
		print('pulling [%s]' % name)
		
		dpath = target['disk-path']
		filter = target['filter']
		
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = cfg['storage-auth-code']
		#def dopull(name, rhost, rport, sac, cfg, rpath, lpath, filter, base = None, c = None, erpath = None, dry = True):
		return self.dopull(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, rpath = rpath, lpath = lpath, filter = filter, dry = dry)
		
	def __cmd_push_target(self, cfg, name, target, rpath = None, lpath = None, dry = True):
		print('pushing [%s]' % name)
		
		dpath = target['disk-path']
		filter = target['filter']
		
		rhost = cfg['remote-host']
		rport = cfg['remote-port']
		sac = cfg['storage-auth-code']
		
		return self.dopush(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, dpath = dpath, rpath = rpath, filter = filter, dry = dry)
		
	'''	
		@sdescription:		Used to disable or enable SSL.
	'''
	def cmd_ssl(self, args):
		if len(args) < 1:
			print('    You must provide a case-insensitive Yes, No, True, or False.')
			return
		
		arg = args[0].lower()
		
		cfg = self.LoadConfig()
		
		if arg in ('yes', 'y', 'true', 't', 'enable', 'activate'):
			cfg['ssl'] = True
			self.SaveConfig(cfg)
			print('    SSL has been enabled!')
			return
		cfg['ssl'] = False
		self.SaveConfig(cfg)
		print('    SLL has been DISabled')
		return
		
	def cmd_pull(self, args, dry = True):
		cfg = self.LoadConfig()
		
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

	'''
	'''		
	def dofilters(self, filters, fpath):
		mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(fpath)
		
		# quick cheat
		if size > 1024 * 1024 * 200:
			return False
		
		for f in filters:
			notmatch = False
			if f[0] == '!':
				# match if does not match filter
				notmatch = True
				f = f[1:]
			# do regular expression matching
			base = fpath[0:fpath.rfind('/') + 1]
			_fpath = fpath[len(base):]
			result = re.match(f, _fpath)
			if notmatch:
				if result is not None:
					return False
			else:
				if result is None:
					return False
			return True
		
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
						print('#', end='')
						continue
					print('.', end='')
					# see if one of the filters marks it as valid
					if dofilters(target['filter'], fpath):
						# get file size
						mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(fpath)
						total = total + size
				
			# swap
			doing = todo
			todo = []
		print('target:[%s] %sMB %sGB' % (name, total / 1024 / 1024, total / 1024 / 1024 / 1024))
		return
		
	def cmd_chksize(self, args):
		cfg = self.LoadConfig()

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
		cfg = self.LoadConfig()

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
		
		cfg = self.LoadConfig()
		
		if name is not None:
			# display information about name		
			print('== %s ==' % name)
			print('    disk-path: %s' % cfg[name]['disk-path'])
			self.__cmd_list_showfilter(cfg['paths'][name]['filter'])

		if len(cfg['paths']) < 1:
			print('nothing to list, try:')
			print('  add a new backup path:    <program> add <name> <path>')
			print('  display help:             <program>')
			return
		
		for k in cfg['paths']:
			print('== %s ==' % k)
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
		print('<account> add-filter  - add inclusive filter')
		print('<account> del-filter  - delete filter')
		print('<account> dry-push	   - pretend to do push')
		print('<account> push        - push (backup) all enabled or specified backup')
		print('<account> dry-pull    - pretend to do pull')
		print('<account> pull        - pull (restore) all enabled or specified backup')
		print('<account> list        - list backup paths or filters for specified')
		print('<account> chksize     - will process all local files and display the total size')
		print(' Example:')
		print('    <program> <account> add <name> <path>')
		print('    <program> <account> del <name>')
		print('    <program> <account> disable <name>')
		print('    <program> <account> enable <name>')
		print('    <program> <account> add-filter [displays help]')
		print('    <program> <account> del-filter [displays help]')
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
		
		if args[0] == 'add':
			args = args[1:]
			if len(args) < 2:
				print('add <account-name> <remote-host> <remote-port(optional)')
				return
			self.accountname = args[0]
			# will create the configuration file also
			cfg = self.LoadConfig()
			cfg['remote-host'] = args[1]
			if len(args) > 2:
				cfg['remote-port'] = int(args[2])
			
		if args[0] == 'del':
			args = args[1:]
			if len(args) < 1:
				print('del <account-name>')
			configs = self.GetConfigs()
			if args[0] not in configs:
				print('The account name [%s] was not found.' % args[0])
				return
			self.DeleteConfig(args[0])
			return
		
		if args[0] == 'list':
			configs = self.GetConfigs()
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
		
		# process remaining arguments
		args = args[1:]
		
		if len(args) < 1:
			# must have command after account name
			return self.showhelp()
		
		if args[0] == 'add':
			return self.cmd_add(args[1:])
		if args[0] == 'del':
			return self.cmd_del(args[1:])
		if args[0] == 'disable':
			return self.cmd_disable(args[1:])
		if args[0] == 'enable':
			return self.cmd_enable(args[1:])
		if args[0] == 'add-filter':
			return self.cmd_addfilter(args[1:])
		if args[0] == 'del-filter':
			return self.cmd_delfilter(args[1:])
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
	
ca = ConsoleApplication()	
ca.main(sys.argv[1:])