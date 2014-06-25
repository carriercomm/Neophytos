'''
	This will query for any local operations being performed and return their results. The
	backupgui.py essentially does the exact same thing to track current operations except
	this program only monitors for just enough information to print the result and then
	exit.
'''
import time
import socket
import struct
from io import BytesIO

class StatusQuery:
	def __init__(self):
		# this is used by the ProcessData method and is persistent to hold the buffer data
		self.data = BytesIO()

	'''
		A helper function that breaks the incoming data stream into packets. Each time
		it is called it will try to return a message from the buffer. It should be called
		until it returns None which means no messages reside in the buffer. The data parameter
		is optional and can be None meaning do not place any more data into the buffer.
	'''
	def ProcessData(self, data):
		if data is not None:
			self.data.write(data)
		
		# do we need to read a message header and can we?
		if self.wsz is None and self.data.tell() >= 4:
			self.data.seek(0)
			sz = struct.unpack_from('>I', self.data.read(4))[0]
			self.wsz = sz
			self.data.seek(0, 2)
		
		if self.wsz is None or self.data.tell() - 4 < self.wsz:
			return None
			
		# place remaining data into new buffer
		self.data.seek(4)
		_ret = self.data.read(self.wsz)
		ndata = BytesIO()
		ndata.write(self.data.read())
		self.data = ndata
		
		# return the message and vector
		self.wsz = None
		return _ret
	'''
		This just reads until [uptodate] so it gets a current status of the operation. For long
		term monitoring one could continue to read from the socket and would recieve updates.
	'''
	def Fetch(self, sock):
		self.wsz = None
	
		info = {}
		info['work'] = {}
		info['title'] = {}
		st = time.time()
		anydata = False
		while True:
			# TODO: maybe need some way of detecting if it is the right service
			#       instead of just waiting but instead look for a hello or even
			#       drop on invalid messages and invalid lengths; i see this causing
			#       potentially lengthy waits for certain users
			
			# after so long just consider it dead or not the right service..
			sock.settimeout(6)
			# read data if any
			data = sock.recv(1024)
			# if we been doing this too long or socket is closed
			if time.time() - st > 6 or not data:
				if anydata:
					return info
				return None
			# process data into messages
			msg = True
			while msg is not None:
				msg = self.ProcessData(data)
				data = None
				if msg is None:
					break
				# turn message into UTF8 string
				msg = msg.decode('utf8', 'ignore')
				parts = msg.split(':')
				# okay we have been brought up to date
				if parts[0] == '[uptodate]':
					anydata = True
					return info
				# update the info structure
				if parts[0] == '[title]':
					info['title'][parts[1]] = parts[2]
					anydata = True
				if parts[0] == '[add]':
					info['work'][parts[1]] = {}
					anydata = True
				if parts[0] == '[rem]':
					del info['work'][parts[1]]
					anydata = True
				if parts[0] == '[old]':
					info['work'][parts[1]]['old'] = False
					anydata = True
				if parts[0] == '[wkey]':
					info['work'][parts[1]][parts[2]] = parts[3]
					anydata = True
				# old way (replaced with [wkey])
				if parts[0] == '[status]':
					info['work'][parts[1]]['status'] = parts[2]
					anydata = True
				# old way (replaced with [wkey])
				if parts[0] == '[progress]':
					info['work'][parts[1]]['progress'] = parts[2]
					anydata = True
	def Scan(self):	
			services = {}
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			for x in range(41000, 41100):
				try:
					try:
						dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
						dummy.bind(('localhost', x))
						dummy.close()
						continue
					except Exception as e:
						pass
					# try to connect
					sock.connect(('localhost', x))
					# fetch information (just the current)
					info = self.Fetch(sock)
					if info is not None:
						services[x] = info
					sock.sendall(b'terminate')
					sock.close()
					sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				except Exception as e:
					print(e)
					pass
			return services
	
def main():
	ca = StatusQuery()
	services = ca.Scan()
	for port in services:
		info = services[port]
		if 'account' in info['title']:
			print('port:%s account:%s target:%s work:%s' % (port, info['title']['account'], info['title']['target'], len(info['work'])))
		else:
			# account for services that return nothing..
			print('port:%s appears to something else or dead..' % port)
	
if __name__ == '__main__':
	main()