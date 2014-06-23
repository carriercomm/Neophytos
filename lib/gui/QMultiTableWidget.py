from PyQt4 import QtGui
from PyQt4 import QtCore

class QMultiTableWidgetRow:
	def __init__(self, owner):
		self.cols = {}				# backing columns
		self.colchanged = False		# have columns changed
		self.ready = False			# is ready to be displayed
		self.hastable = None		# has table assigned
		# yes, this is a bi-directional dependency..
		self.owner = owner			# set owner for callback
		self.drop = False			# set to have it removed
		
		# QTableWidget specific
		self.__colitems = {}		# mapping of column to item
		self.__rowindex = None
	
	def SetTable(self, table):
		if self.hastable is not None:
			# remove row from table
			self.hastable.removeRow(self__rowindex)
			# reset column items
			self.__colitems = {}
		self.hastable = table
		# add row to table
		self.hastable.insertRow(0)
		# set row index
		self.__rowindex = 0
		# add items to row
		ci = 0
		for col in self.cols:
			# create item if one does not exist
			if col not in self.__colitems:
				self.__colitems[col] = QtGui.QTableWidgetItem()
			# set text to items
			self.__colitems[col].setText(self.cols[col])
			# find table column
			goti = None
			for i in range(0, self.hastable.columnCount()):
				if self.hastable.horizontalHeaderItem(i).text() == col:
					goti = i
					break
			# set item to table row and col
			self.hastable.setItem(0, goti, self.__colitems[col])
	
	def Drop(self):
		# set this so it will be dropped and not placed
		# into a table even if something is updated
		self.drop = True
		# remove row from table
		if self.hastable is not None:
			self.hastable.removeRow(self.__rowindex)
			self.hastable = None
			self.__rowindex = None
	
	def Ready(self):
		if self.ready is False:
			self.ready = True
			self.owner.Update()
	
	def Update(self):
		if self.owner is not None:
			self.owner.Update()
	
	def SetCol(self, key, value):
		if key not in self.cols and self.ready is True:
			# just set the key to value and try to update
			self.colchanged = True
			self.cols[key] = value
			# alert the owner it needs to update
			self.owner.Update()
			return
		self.cols[key] = value
		if self.hastable and self.ready is True:
			# QTableWidget specific
			self.__colitems[key].setText(value)
	
	def GetCols(self):
		return self.cols
	
class QMultiTableWidget(QtGui.QWidget):
	def __init__(self, parent = None):
		super().__init__(parent)
		self.rows = []
		self.tables = []
		self.splitter = QtGui.QSplitter(self)
	
	def resizeEvent(self, event):
		self.splitter.resize(self.width(), self.height())
		
	def AddRow(self):
		row = QMultiTableWidgetRow(self)
		self.rows.append(row)
		return row
	
	# go through and figure out what tables we need
	def Update(self):
		headers = []
		
		toremove = []
		
		for row in toremove:
			self.rows.remove(row)
		
		# see what headers we need
		for row in self.rows:
			if row.drop:
				toremove.append(row)
			# do not mess with a row that has not be set as ready
			if not row.ready:
				continue
			# do not mess with rows that have not changed and have a table
			if not row.colchanged and row.hastable:
				continue
			cols = row.GetCols()
			
			# look for a table which contains all of our columns
			gotall = False
			for table in self.tables:
				if table.columnCount() != len(cols):
					# need exact number of columns
					continue
				for col in cols:
					hasit = False
					for ci in range(0, table.columnCount()):
						if table.horizontalHeaderItem(ci).text() == col:
							hasit = True
							break
					if not hasit:
						break
				if hasit:
					# this table has all the needed columns
					gotall = True
					break
			
			if gotall:
				# we found a table with all the needed columns so attach
				# the row to this table
				row.SetTable(table)
				continue
			
			# we need to create a new table
			table = QtGui.QTableWidget(self)
			table.setColumnCount(len(cols))
			table.setHorizontalHeaderLabels(list(cols.keys()))
			self.tables.append(table)
			row.SetTable(table)
			continue
			
		# remove tables that have no rows
		for table in self.tables:
			if table.rowCount() < 1:
				# i hope this unlinks it from the splitter
				self.table.setParent(None)
				self.tables.remove(table)
				
		# make sure all tables are assigned into the splitter
		for table in self.tables:
			if self.splitter.indexOf(table) < 0:
				# add the table
				self.splitter.addWidget(table)
		# <end-of-function>
