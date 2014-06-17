'''
	This implements a client GUI.
'''
import os
import sys
import backup
from PyQt4 import QtGui
from PyQt4 import QtCore
import io
import os.path
import pprint
import status
import threading
import time

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
		ca = backup.ConsoleApplication()
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

class QCompactLayout():
	def __init__(self, parent, horizontal = True):
		self.parent = parent
		self.widgets = []
		self.horizontal = horizontal

	def __GetTextWidth(text, font = 'Monospace', size = 10):
		font = QtGui.QFont(font, size)
		fm = QtGui.QFontMetrics(font)
		return fm.width(text)
		
	def AddWidget(self, widget):
		self.widgets.append(widget)
	
	def Do(self):
		i = 0
		cx = 0
		cy = 0
		mx = 0
		my = 0
		while i < len(self.widgets):
			w = self.widgets[i]
			if hasattr(w, 'xlayout'):
				w.xlayout.Do()
			
			#f_family = w.font().family()
			#f_size = w.font().pointSize()
			#if isinstance(w, QtGui.QLabel):
			#	w_w = QCompactLayout.__GetTextWidth(w.text(), font = f_family, size = f_size)
			#	w.resize(w_w, w.height())
			w.move(cx, w.y())
			if self.horizontal:
				if hasattr(w, 'xpadding'):
					cx = cx + w.xpadding
				cx = cx + w.width()
				if w.height() > my:
					my = w.height()
			else:
				cy = cy + w.height()
				if w.width() > mx:
					mx = w.width()
			i = i + 1
		if self.horizontal:
			return (cx, my)
		return (mx, cy)
		
class QBackupEntryStatus(QtGui.QFrame):
	def __init__(self, parent, account, target):
		super().__init__(parent)
		self.account = account
		self.target = target
		
		self.lbacc = QtGui.QLabel('Account:', self)
		self.lbacc.xpadding = 5
		self.lbacc.setObjectName('AccountLabel')
		self.lbaccval = QtGui.QLabel(account, self)
		self.lbaccval.xpadding = 10
		self.lbaccval.setObjectName('AccountLabelValue')
		self.lbtar = QtGui.QLabel('Target:', self)
		self.lbtar.xpadding = 5
		self.lbtar.setObjectName('TargetLabel')
		self.lbtarval = QtGui.QLabel(target, self)
		self.lbtarval.xpadding = 10
		self.lbtarval.setObjectName('TargetLabelValue')
		
		self.lbbo = QtGui.QLabel('Bytes-Out(MB):', self)
		self.lbbo.xpadding = 5
		self.lbbo.setObjectName('BytesOutLabel')
		self.lbboval = QtGui.QLabel('0', self)
		self.lbboval.xpadding = 10
		self.lbboval.setObjectName('BytesOutLabelValue')

		self.lbbi = QtGui.QLabel('Bytes-In(MB):', self)
		self.lbbi.xpadding = 5
		self.lbbi.setObjectName('BytesInLabel')
		self.lbbival = QtGui.QLabel('0', self)
		self.lbbival.xpadding = 10
		self.lbbival.setObjectName('BytesInLabelValue')
		
		self.pb = QtGui.QProgressBar(self)
		self.pb.setRange(0, 1)
		self.pb.setValue(0.5)
		self.pb.move(0, 5)
		self.pb.resize(200, 20)
		self.pb.xpadding = 5
		
		self.xlayout = QCompactLayout(self, horizontal = True)
		self.xlayout.AddWidget(self.lbacc)
		self.xlayout.AddWidget(self.lbaccval)
		self.xlayout.AddWidget(self.lbtar)
		self.xlayout.AddWidget(self.lbtarval)
		self.xlayout.AddWidget(self.pb)
		self.xlayout.AddWidget(self.lbbo)
		self.xlayout.AddWidget(self.lbboval)
		self.xlayout.AddWidget(self.lbbi)
		self.xlayout.AddWidget(self.lbbival)
		
	def resize(self, w, h):
		pass
	
	def Update(self):
		pass
		
def DumpObjectTree(obj, space = ''):
	print('%s%s [%s]' % (space, obj, obj.objectName()))
	for child in obj.children():
		if isinstance(obj, QtGui.QWidget):
			DumpObjectTree(child, space = '%s ' % space)
		
class QAccountsAndTargetSystem(QtGui.QFrame):
	def __init__(self, parent):
		QtGui.QFrame.__init__(self, parent)
		self.Create()
	
	def GetTableRow(self, row):
		out = []
		colcnt = self.table.columnCount()
		for x in range(0, colcnt):
			item = self.table.item(row, x)
			out.append(item)
		return out
		
	def SetTableRow(self, table, row, items):
		for x in range(0, len(items)):
			# just skip this column (dont update it)
			if items[x] is None:
				continue
			item = table.item(row, x)
			# this should be an QTableWidgetItem
			if type(items[x]) is not str:
				print('not str')
				# treat it is QTableWidgetItem
				table.setItem(row, x, items[x])
				continue
			if item is None:
				item = QtGui.QTableWidgetItem()
				table.setItem(row, x, item)
			# should be a string type
			item.setText(items[x])
	
	def Create(self):
		accounts = ClientInterface.GetAccounts()
		
		self.panels = {}
		
		self.xlayout = QCompactLayout(self, horizontal = False)
	
		table = QtGui.QTableWidget(self)
		self.table = table
		
		table.setObjectName('StatusTable')
		
		split = QtGui.QSplitter(self)
		self.split = split
		
		#DumpObjectTree(self)
		
		# enabled, account, target, path, bytesout, bytesin, status, progress
		table.setColumnCount(5)
		table.setHorizontalHeaderLabels(['Enabled', 'Account', 'Target', 'Path', 'Next Run'])
		
		for account in accounts:
			targets = ClientInterface.GetTargets(account)
			for target in targets:
				cfg = targets[target]
				acctarname = '%s.%s' % (account, target)
				
				scfg = ClientInterface.GetServiceConfig(account)
				if scfg is not None and target in scfg:
					nrt = '8hrs 5min'
				else:
					nrt = 'Manual Only'
				
				table.insertRow(0)
				self.SetTableRow(table, 0, (
					cfg['enabled'],
					account, target,
					cfg['disk-path'],
					nrt
				))
		
		stable = QtGui.QTableWidget(self)
		self.stable = stable
		stable.setObjectName('StatusTable')
		stable.setColumnCount(6)
		stable.setHorizontalHeaderLabels(['User', 'Account', 'Target', 'Queue', 'Up/MB/Sec', 'Complete'])
		stable.setVerticalHeaderLabels(['', ''])
		stable.resizeColumnsToContents()
		
		table.setVerticalHeaderLabels(['', ''])
		table.resizeColumnsToContents()
		
		
		split.setOrientation(2)
		split.addWidget(table)
		split.addWidget(stable)
				
		self.show()
		
		scantimer = QtCore.QTimer(self)
		self.scantimer = scantimer
		scantimer.timeout.connect(lambda : QAccountsAndTargetSystem.PeriodicScanUpdate(self))
		scantimer.start(5000)
		
		scanthread = threading.Thread(target = QAccountsAndTargetSystem.PeriodicScanThreadEntry, args = (self,))
		scanthread.daemon = True
		self.scanthread = scanthread
		scanthread.start()
	
	'''
		This uses the data maintained by the periodic scan thread
		to keep the table up to date.
	'''
	def PeriodicScanUpdate(self):
		# access copy of services dict, the thread
		# will create a new dict and set it then
		# never touch it so this should be quite
		# safe and does not need a lock
		services = self.services
		stable = self.stable
		
		for port in services:
			service = services[port]
			title = service['title']
			work = service['work']
			# just ignore it if it does not report the account
			if 'account' not in title:
				continue
			user = title['user']
			account = title['account']
			target = title['target']
			filecount = float(title['filecount'])
			donecount = float(title['filedonecount'])
			
			# find row if it exists and update it
			frow = None
			for row in range(0, stable.rowCount()):
				t_user = stable.item(row, 0).text()
				t_account = stable.item(row, 1).text()
				t_target = stable.item(row, 2).text()
				
				if t_user == user and t_account == account and t_target == target:
					frow = row
					break
			
			# if row does not exist then create it
			if frow is None:
				frow = 0
				stable.insertRow(0)
				self.SetTableRow(stable, 0, (
					user,
					account, target,
					'',				# work item count
					''				# throughput
				))
				
				# create a progress bar for eye candy
				pb = QtGui.QProgressBar()
				pb.setObjectName('StatusCellProgressBar')
				pb.setRange(0.0, 100.0)
				pb.setValue(0.0)
				stable.setCellWidget(0, 5, pb)
				
			workcount = 0
			for wname in work:
				witem = work[wname]
				if 'old' in witem and witem['old'] is False:
					workcount = workcount + 1
					
			stable.item(frow, 3).setText('%s' % workcount)
			stable.item(frow, 4).setText('%.03f:%.03f' % (float(title['outmb']), float(title['totoutmb'])))
			stable.cellWidget(frow, 5).setValue((donecount / filecount) * 100.0)
			# if we are dealing with LOTS of rows this might 
			# get slow and CPU hungry, but I doubt 99% of
			# the things using this will be that hungry..
			stable.resizeColumnsToContents()
		
	def PeriodicScanThreadEntry(self):
		# initial the status query object
		q = status.StatusQuery()
		while True:
			# scan for running services
			#print('scanning')
			services = q.Scan()
			self.services = services
			#print('done scanning')
			# iterate through services found
			for port in services:
				service = services[port]
				title = service['title']
				if 'account' not in title:
					continue
				title = service['title']
				account = title['account']
				target = title['target']
				# try to find the row that matches this running service, we might
				# not find one if it is running under a different user account and
				# if so we can just add a row
				#print(title, account)
			time.sleep(5)
		
	def resizeEvent(self, event):
		#table = self.table	
		#rect = table.visualItemRect(table.item(0, table.columnCount() - 1))
		#w = rect.x() + rect.width() + 20
		#table.resize(self.width(), self.height())
		split = self.split
		
		self.split.resize(self.width(), self.height())
	
	def resize(self, w, h):
		super().resize(w, h)
		
	def show(self):
		super().show()
				
				
class QStatusWindow(QtGui.QMainWindow):
	def resizeEvent(self, event):
		self.fAccountsAndTargets.resize(self.width(), self.height())

	def resize(self, w, h):
		super().resize(w, h)
		
	def __init__(self):
		QtGui.QMainWindow.__init__(self)
		
		fd = open('./media/client.css', 'r')
		cssdata = fd.read()
		fd.close()
		self.setStyleSheet(cssdata)
		
		icon = QtGui.QIcon('./media/book.ico')
		self.setWindowIcon(icon)
	
		self.fAccountsAndTargets = QAccountsAndTargetSystem(self)
		self.fAccountsAndTargets.resize(self.width(), self.height())

		self.resize(700, 340)
		self.move(400, 20)
		self.setWindowTitle('Neophytos Backup Status')
		self.show()

		
def main():
	app = QtGui.QApplication(sys.argv)
	# Cleanlooks
	# Plastique
	# Motfif
	# CDE
	style = QtGui.QStyleFactory.create('Plastique')
	app.setStyle(style)

	w = QStatusWindow()
				
	sys.exit(app.exec_())
	
main()