import client
import os
import os.path
import sys
import pprint
import re

def GetConfigPath():
	# build base path (without file)
	base = '%s/.neophytos' % os.path.expanduser('~')
	# ensure it is created
	if os.path.exists(base) is False:
		os.makedirs(base)
	# add on file
	path = '%s/config.py' % base
	return path
	
def __LoadConfig():
	path = GetConfigPath()
	if os.path.exists(path) is False:
		return {}
	fd = open(path, 'r')
	cfg = eval(fd.read())
	fd.close()
	return cfg
	
def LoadConfig():
	cfg = __LoadConfig()
	if cfg.get('remote-host', None) is None:
		cfg['remote-host'] = 'localhost'
		cfg['remote-port'] = 4322
		cfg['storage-auth-code'] = None
	cfg['paths'] = cfg.get('paths', {})
	return cfg

def cmd_config(args):
	if len(args) < 1:
		print('not enough arguments: <server-auth-code>')
		return
	
	sac = args[0]
	
	cfg = LoadConfig()
	cfg['storage-auth-code'] = sac
	SaveConfig(cfg)
	
def SaveConfig(cfg):
	path = GetConfigPath()
	fd = open(path, 'w')
	pprint.pprint(cfg, fd)
	fd.close()

def cmd_add(args):
	if len(args) < 2:
		print('not enough arguments: <name> <path>')
		return
		
	name = args[0]
	path = args[1]
	
	if os.path.exists(path) is False:
		print('path [%s] does not exist' % path)
	cfg = LoadConfig()
	
	if name in cfg['paths']:
		print('name [%s] already exists' % name)
		return
		
	cfg['paths'][name] = {}
	cfg['paths'][name]['disk-path'] = path
	cfg['paths'][name]['enabled'] = True
	cfg['paths'][name]['filter'] = ['.*']
	
	SaveConfig(cfg)
	
	print('added name [%s] with path [%s]' % (name, path))
	return
	
def cmd_del(args):
	if len(args) < 1:
		print('not enough arguments: <name>')
		return
	
	name = args[0]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
	
	path = cfg['paths'][name].get('disk-path', '<error>')
	
	del cfg['paths'][name]
	
	SaveConfig(cfg)
	
	print('deleted name [%s] with path [%s]' % (name, path))
	return
	
def cmd_disable(args):
	if len(args) < 1:
		print('not enough arguments: <name>')
		return
	
	name = args[0]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
		
	path = cfg['paths'][name].get('disk-path', '<error>')
		
	cfg['paths'][name]['enabled'] = False

	SaveConfig(cfg)
	
	print('disabled name [%s] with path [%s]' % (name, path))
	return
	
def cmd_enable(args):
	if len(args) < 1:
		print('not enough arguments: <name>')
		return
		
	name = args[0]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
		
	path = cfg['paths'][name].get('disk-path', '<error>')
	
	cfg['paths'][name]['enabled'] = True
	
	SaveConfig(cfg)
	
	print('enabled name [%s] with path [%s]' % (name, path))
	return
	
def cmd_addfilter(args):
	if len(args) < 2:
		print('not enough arguments: <name> <pattern>')
		return
	
	name = args[0]
	pattern = args[1]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
	
	cfg['paths'][name]['filter'].append(pattern)
	
	SaveConfig(cfg)
	print('added to name [%s] pattern [%s]' % (name, pattern))
	return
	
def cmd_delfilter(args):
	if len(args) < 1:
		print('not enough arguments:')
		print('		<name>				- will list pattern with index')
		print('		<name> <index>		- will delete pattern at index')
		return
		
	cfg = LoadConfig()
		
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
			SaveConfig(cfg)
			return
		ndx = ndx + 1
	print('could not find index [%s]' % index)
	return
	
def dopull(name, rhost, rport, sac, cfg, rpath, lpath, filter, base = None, c = None, erpath = None, dry = True):
	if c is None:
		print('CONNECTING TO REMOTE SERVER')
		c = client.Client2(rhost, rport, bytes(sac, 'utf8'))
		c.Connect()
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
		dopull(name, rhost, rport, sac, cfg, rpath, '%s/%s' % (lpath, dir), filter, base = base, c = c, erpath = '%s/%s' % (erpath, dir), dry = dry)
	
def dopush(name, rhost, rport, sac, cfg, dpath, rpath, filter, base = None, c = None, dry = True):
	if c is None:
		print('CONNECTING TO REMOTE SERVER')
		c = client.Client2(rhost, rport, bytes(sac, 'utf8'))
		c.Connect()
		print('CONNECTION ESTABLISHED, SECURED, AND AUTHENTICATED')
		
	if rpath is None:
		rpath = ''
		
	if base is None:
		base = dpath
	nodes = os.listdir(dpath)
	for node in nodes:
		fpath = '%s/%s' % (dpath, node)
		# if directory..
		if os.path.isdir(fpath):
			dopush(name, rhost, rport, sac, cfg, fpath, rpath, filter, base = base, c = c)
			continue
		# run filters
		for f in filter:
			notmatch = False
			if f[0] == '!':
				# match if does not match filter
				notmatch = True
				f = f[1:]
			# do regular expression matching
			_fpath = fpath[len(base):]
			result = re.match(f, _fpath)
			if notmatch:
				if result is not None:
					continue
			else:
				if result is None:
					continue
			# backup the file
			print('PROCESSING [%s]' % _fpath)
			# fpath
			lfile = fpath
			fid = (bytes('%s/%s/%s' % (name, rpath, _fpath), 'utf8'), 0)
			if dry is False:
				c.FilePush(fid, lfile)
	
def __cmd_pull_target(cfg, name, target, rpath = None, lpath = None, dry = True):
	print('pulling [%s]' % name)
	
	dpath = target['disk-path']
	filter = target['filter']
	
	rhost = cfg['remote-host']
	rport = cfg['remote-port']
	sac = cfg['storage-auth-code']
	#def dopull(name, rhost, rport, sac, cfg, rpath, lpath, filter, base = None, c = None, erpath = None, dry = True):
	return dopull(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, rpath = rpath, lpath = lpath, filter = filter, dry = dry)
	
def __cmd_push_target(cfg, name, target, rpath = None, lpath = None, dry = True):
	print('pushing [%s]' % name)
	
	dpath = target['disk-path']
	filter = target['filter']
	
	rhost = cfg['remote-host']
	rport = cfg['remote-port']
	sac = cfg['storage-auth-code']
	
	return dopush(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, dpath = dpath, rpath = rpath, filter = filter, dry = dry)
	
def cmd_pull(args, dry = True):
	cfg = LoadConfig()
	
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
				__cmd_pull_target(cfg, target, cfg['paths'][target], rpath = rpath, lpath = '%s/%s' % (lpath, target), dry = dry)
		return
	# run all that are enabled
	for k in cfg['paths']:
		__cmd_pull_target(cfg, k, cfg['paths'][k], rpath = rpath, lpath = lpath, dry = dry)	
	
def cmd_push(args, dry = True):
	cfg = LoadConfig()

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
				__cmd_push_target(cfg, target, cfg['paths'][target], rpath = rpath, dry = dry)
		return
	# run all that are enabled
	for k in cfg['paths']:
		__cmd_push_target(cfg, k, cfg['paths'][k], dry = dry)
	return
	
def __cmd_list_showfilter(filter):
	ndx = 0
	for p in filter:
		print('    %02i: [%s]' % (ndx, p))
		ndx = ndx + 1
	
def cmd_list(args):
	if len(args) > 0:
		name = args[0]
	else:
		name = None
	
	cfg = LoadConfig()
	
	if name is not None:
		# display information about name		
		print('== %s ==' % name)
		print('    disk-path: %s' % cfg[name]['disk-path'])
		__cmd_list_showfilter(cfg['paths'][name]['filter'])

	if len(cfg['paths']) < 1:
		print('nothing to list, try:')
		print('  add a new backup path:    <program> add <name> <path>')
		print('  display help:             <program>')
		return
	
	for k in cfg['paths']:
		print('== %s ==' % k)
		print('    disk-path: %s' % cfg['paths'][k]['disk-path'])
		__cmd_list_showfilter(cfg['paths'][k]['filter'])		
	return

def showhelp():
	print('config      - configures the remote server')
	print('add         - add backup path')
	print('del         - delete backup path')
	print('disable     - disable backup path')
	print('enable      - enable backup path')
	print('add-filter  - add inclusive filter')
	print('del-filter  - delete filter')
	print('dry-push	   - pretend to do push')
	print('push        - push (backup) all enabled or specified backup')
	print('dry-pull    - pretend to do pull')
	print('pull        - pull (restore) all enabled or specified backup')
	print('list        - list backup paths or filters for specified')
	print('	Example:')
	print('		<program> add <name> <path>')
	print('		<program> del <name>')
	print('		<program> disable <name>')
	print('		<program> enable <name>')
	print('		<program> add-filter [displays help]')
	print('		<program> del-filter [displays help]')
	print('		<program> dry-push <(optional)name> <(optional)name> ...')
	print('		<program> push <(optional)name> <(optional)name> ...')
	print('		<program> dry-pull <(optional)name> <(optional)name> ...')
	print('		<program> pull <(optional)name> <(optional)name> ...')
	print('		<program> list <(optional)name>')
	
def main(args):
	if len(args) < 1:
		return showhelp()
	if args[0] == 'add':
		return cmd_add(args[1:])
	if args[0] == 'del':
		return cmd_del(args[1:])
	if args[0] == 'disable':
		return cmd_disable(args[1:])
	if args[0] == 'enable':
		return cmd_enable(args[1:])
	if args[0] == 'add-filter':
		return cmd_addfilter(args[1:])
	if args[0] == 'del-filter':
		return cmd_delfilter(args[1:])
	if args[0] == 'dry-push':
		return cmd_push(args[1:], dry = True)
	if args[0] == 'push':
		return cmd_push(args[1:], dry = False)
	if args[0] == 'dry-pull':
		return cmd_pull(args[1:], dry = True)
	if args[0] == 'pull':
		return cmd_pull(args[1:], dry = False)
	if args[0] == 'list':
		return cmd_list(args[1:])
	if args[0] == 'config':
		return cmd_config(args[1:])
	print('unknown command')
		
main(sys.argv[1:])