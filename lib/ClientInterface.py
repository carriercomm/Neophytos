import sys
import os
import io

from lib.Backup import Backup

class ClientInterface:
	'''
		The following functions form an textual stream interface between the
		backup command line utility. I got down and thought hard about making
		a more Python interface since I am importing backup, but I decided this
		might actually be more flexible in allowing us to interface with things
		not written in Python. We would of course be unable to import it and have
		to call it directly using subprocess, but we could still parse it's
		output like we do below.
		
		I am considering moving this section into a separate module that could be
		dynamically specified by the client we are using. So backup.py would specify
		a backup_comm.py file which including doing everything needed to return
		the data. Basically, backup_comm.py would implement the interface below.
	'''
	def GetTargets(account):
		out = ClientInterface.ConsoleCommand([account, 'list'])
		lines = out.split('\n')
		targets = {}
		for line in lines:
			if line.find('==') == 0:
				name = line[line.find(' ') + 1:line.rfind(' ')]
				target = {}
				filters = []
				
				targets[name] = target
				target['filter'] = filters
			if line.find('    ') == 0:
				line = line.strip()
				if line.find('disk-path:') == 0:
					diskpath = line[line.find(' ') + 1:]
					target['disk-path'] = diskpath
				elif line.find('enabled:') == 0:
					target['enabled'] = line[line.find(':') + 1:].strip()
				else:
					filterndx = int(line[0:line.find(':')])
					filter = eval(line[line.find('[') + 1:line.find(']')])
					filters.append(filter)
		return targets
	
	def GetAccounts():
		out = ClientInterface.ConsoleCommand(['list'])
		lines = out.split('\n')
		accounts = []
		for line in lines:
			if line.find('    ') == 0:
				accounts.append(line.strip())
		return accounts
		
	def ConsoleCommand(cmd):
		ca = Backup()
		oldstdout = sys.stdout
		buf = io.StringIO()
		sys.stdout = buf
		ca.main(cmd)
		sys.stdout = oldstdout
		buf.seek(0)
		return buf.read()
		
	def GetConfigPath(self):
		# build base path (without file)
		base = self.GetConfigBase()
		# add on file
		path = '%s/%s.py' % (base, self.accountname)
		return path
		
	def GetConfigBase():
		base = '%s/.neophytos/accounts' % os.path.expanduser('~')
		if os.path.exists(base) is False:
			os.makedirs(base)
		return base

	def GetServiceConfig(account):
		base = ClientInterface.GetConfigBase()
		fpath = '%s/%s.service.py' % (base, account)
		if os.path.exists(fpath) is False:
			return None
		fd = open(fpath, 'r')
		py = fd.read()
		fd.close()
		return eval(py)
		
	def SaveServiceConfig(account, cfg):
		base = ClientInterface.GetConfigBase()
		fpath = '%s/%s.service.py' % (base, account)
		fd = open(fpath, 'w')
		pprint.pprint(fd, cfg)
		fd.close()
