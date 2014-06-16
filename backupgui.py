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
		
	def SetTableRow(self, row, items):
		for x in range(0, len(items)):
			# just skip this column (dont update it)
			if items[x] is None:
				continue
			item = self.table.item(row, x)
			# this should be an QTableWidgetItem
			if type(items[x]) is not str:
				print('not str')
				# treat it is QTableWidgetItem
				self.table.setItem(row, x, items[x])
				continue
			if item is None:
				item = QtGui.QTableWidgetItem()
				self.table.setItem(row, x, item)
			# should be a string type
			item.setText(items[x])
	
	def Create(self):
		accounts = ClientInterface.GetAccounts()
		
		self.panels = {}
		
		self.xlayout = QCompactLayout(self, horizontal = False)
	
		table = QtGui.QTableWidget(self)
		self.table = table
		
		table.setObjectName('StatusTable')
		
		#DumpObjectTree(self)
		
		# enabled, account, target, path, bytesout, bytesin, status, progress
		table.setColumnCount(9)
		table.setHorizontalHeaderLabels(['Enabled', 'Account', 'Target', 'Path', 'Out/KB/Second', 'In/KB/Second', 'Status', 'Progress', 'Next Run'])
		
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
				self.SetTableRow(0, (
					cfg['enabled'],
					account, target,
					cfg['disk-path'],
					'0',
					'0',
					'',
					'',
					nrt
				))
				
				pb = QtGui.QProgressBar()
				pb.setObjectName('StatusCellProgressBar')
				pb.setValue(50)
				table.setCellWidget(0, 7, pb)
		
		table.setVerticalHeaderLabels(['', ''])
		table.resizeColumnsToContents()
				
		self.show()
		
	def resizeEvent(self, event):
		table = self.table
			
		rect = table.visualItemRect(table.item(0, table.columnCount() - 1))
		
		w = rect.x() + rect.width() + 20

		table.resize(self.width(), self.height())
	
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