'''
	This contains things not worthy of their own module, but
	used by lots of other modules.
'''
from PyQt4 import QtGui
from PyQt4 import QtCore

def CloneComboBox(w):
	n = QtGui.QComboBox()
	for i in range(0, w.count()):
		text = w.itemText(i)
		# insert onto end of list to maintain same index
		n.insertItem(n.count(), text)
	# select the same item as the original
	n.setCurrentIndex(w.currentIndex())
	return n
	
def ChangeStyle(widget, name):
	widget.setObjectName(name)
	widget.style().polish(widget)

'''
	I just like this style of making a menu item. It lets
	me do everything on one line of code, instead of two.
'''	
class HandlerAction(QtGui.QAction):
	def __init__(self, icon, text, parent, handler, arg):
		QtGui.QAction.__init__(self, icon, text, parent)
		self.triggered.connect(lambda : handler(*arg))
