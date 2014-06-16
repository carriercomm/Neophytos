'''
	This implements a client GUI.
'''
import os
import sys
import backup
from PyQt4 import QtGui
from PyQt4 import QtCore
import io

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
			
			f_family = w.font().family()
			f_size = w.font().pointSize()
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
		
class QAccountsAndTargetSystem(QtGui.QFrame):
	def __init__(self, parent):
		QtGui.QFrame.__init__(self, parent)
		self.Create()
	
	def Create(self):
		accounts = ClientInterface.GetAccounts()
		
		self.panels = {}
		
		self.xlayout = QCompactLayout(self, horizontal = False)
		
		for account in accounts:
			targets = ClientInterface.GetTargets(account)
			for target in targets:
				acctarname = '%s.%s' % (account, target)				
				panel = QBackupEntryStatus(self, account, target)
				self.panels[acctarname] = panel
				self.xlayout.AddWidget(panel)
				panel.setStyleSheet('QBackupEntryStatus { border-style: inset; border-width: 1px; }')
				#panel.setFrameStyle(QtGui.QFrame.Raised)
		
		#self.setLayout(vlo)
		self.show()
	
	def resize(self, w, h):
		super().resize(w, h)
		
		self.xlayout.Do()
				
				
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
		print('@', cssdata)
		
		icon = QtGui.QIcon('./media/book.ico')
		self.setWindowIcon(icon)
	
		self.fAccountsAndTargets = QAccountsAndTargetSystem(self)
		self.fAccountsAndTargets.resize(self.width(), self.height())

		self.resize(400, 340)
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