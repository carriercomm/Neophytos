import client
import os
import os.path
import sys
import pprint
import re
import threading
import time

from lib import misc
from lib import output

# only execute this if we are the primary
# script file being executed by Python
if __name__ == '__main__':
	# ourselves to idle unless specified to run as normal
	misc.setProcessPriorityIdle()
	# setup standard outputs (run TCP server)
	output.Configure(tcpserver = True)
	ca = ConsoleApplication()
	ca.main(sys.argv[1:])