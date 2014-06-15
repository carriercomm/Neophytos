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

		
class QAccountsAndTargetSystem(QtGui.QFrame):
	def __init__(self, parent):
		QtGui.QFrame.__init__(self, parent)
		self.Create()
	
	def Create(self):
		accounts = ClientInterface.GetAccounts()

		table = QtGui.QTableWidget(self)
		table.resize(self.width(), self.height())
		self.table = table
		
		table.setColumnCount(5)
		table.setHorizontalHeaderLabels(('Account', 'Target', 'Path', 'Enabled', 'Status'))
		
		for account in accounts:
			targets = ClientInterface.GetTargets(account)
			for target in targets:
				acctarname = '%s.%s' % (account, target)
				
				table.insertRow(0)
				
				item = QtGui.QTableWidgetItem()
				item.setText(account)
				table.setItem(0, 0, item)
				item = QtGui.QTableWidgetItem()
				item.setText(target)
				table.setItem(0, 1, item)
				item = QtGui.QTableWidgetItem()
				item.setText(targets[target]['disk-path'])
				table.setItem(0, 2, item)
				# create new frame to hold information
				#self.apanel[acctarname] = QtGui.QFrame(self)
				# create account name and target name fields
				#self.apanel[acctarname].setLayout(lo)
				#lo.setContentsMargin(0, 0, 0, 0)
				
				print(acctarname)
		
		#self.setLayout(vlo)
		self.show()
	
	def resize(self, w, h):
		super().resize(w, h)
		self.table.resize(w, h)
				
				
class QStatusWindow(QtGui.QMainWindow):
	def resizeEvent(self, event):
		self.fAccountsAndTargets.resize(self.width(), self.height())

	def resize(self, w, h):
		super().resize(w, h)
		
	def __init__(self):
		QtGui.QMainWindow.__init__(self)
		
		self.setStyleSheet('')
		
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