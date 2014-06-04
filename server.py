import os
import sys
import socket
import select
import struct

from pkttypes import *
from misc import *

import pubcrypt

class ServerClient:
	def __init__(self, sock, addr, kpub, kpri):
		self.sock = sock
		self.addr = addr
		self.hdr = b''
		
		self.kpub = kpub
		self.kpri = kpri
		
		self.wsz = None
		self.wmsg = b''
		
		self.data = b''
		
		self.info = None
		
		self.sock.settimeout(0)
	
	def GetAddr(self):
		return self.addr
	
	def GetSock(self):
		return self.sock
		
	def HandleData(self, data):
		# process data for a message
		msg, vector = self.ProcessData(data)
		
		# exit if no message
		if msg is None:
			return
			
		# process the message
		self.ProcessMessage(msg, vector)
		
	def ProcessMessage(self, msg, vector):
		type = msg[0]
		msg = msg[1:]
		
		# unencrypted messages
		if type == ClientType.GetPublicKey:
			self.WriteMessage(struct.pack('>BH', ServerType.PublicKey, len(self.kpub[0])) + self.kpub[0] + self.kpub[1])
			print('len(kpub[0]):%s' % (len(self.kpub[0])))
			return
		if type == ClientType.SetupCrypt:
			key = pubcrypt.decrypt(msg, self.kpri)
			print('key:%s' % key)
			self.crypter = SymCrypt(key)
			self.WriteMessage(struct.pack('>B', ServerType.SetupCrypt))
			return
		# anything else must be encrypted
		if type != ClientType.Encrypted:
			return
		
		print('processing encrypted message')
		
		# decrypt message
		msg = self.crypter.decrypt(msg)
		type = msg[0]
		msg = msg[1:]
		
		print('	type:%s' % type)
		print('	msg:%s' % msg)
		
		# will associate client with an account
		if type == ClientType.Login:
			print('got login message', msg)
			aid = msg.decode('utf8', 'ignore')
			# check that account exists
			if os.path.exists('./accounts/%s' % aid) is False:
				print('account does not exist')
				self.WriteMessage(struct.pack('>B', ServerType.LoginResult) + b'n')
				return
			# load account information
			fd = open('./accounts/%s' % aid, 'r')
			self.info = eval(fd.read())
			fd.close()
			# ensure directory exists
			diskpath = self.info['disk-path']
			if os.path.exists(diskpath) is False:
				os.makedirs(diskpath)
			print('login good')
			self.WriteMessage(struct.pack('>B', ServerType.LoginResult) + b'y')
			return
			
		# anything past this point needs to
		# be logged into the system
		if self.info is None:
			self.WriteMessage(struct.pack('>B', ServerType.LoginRequired))
			return
			
		# return a list of nodes in directory
		if type == ClientType.DirList:
			cpath = msg
			
		if type == ClientType.FileRead:
			return
		if type == ClientType.FileWrite:
			return
		if type == ClientType.FileSize:
			pass
		if type == ClientType.FileTrun:
			pass
		if type == ClientType.FileDel:
			pass
		if type == ClientType.FileCopy:
			pass
		if type == ClientType.FileMove:
			pass
		if type == ClientType.FileHash:
			pass
		if type == ClientType.FileStash:
			pass
		if type == ClientType.FileGetStashes:
			pass
		
	def WriteMessage(self, data, vector = 0):		
		# get type
		type = data[0]
		
		# leave get public key and setup crypt unaltered
		if type == ServerType.PublicKey:
			pass
		else:
			print('encrypting type:%s' % type)
			# normal encrypt	
			data = bytes((ServerType.Encrypted,)) + self.crypter.crypt(data)
		
		# at the moment i do not use server-vector
		# so it is hard coded as zero
		self.sock.send(struct.pack('>IQQ', len(data), 0, vector))
		self.sock.send(data)
		return
	
	def GetBufferSize(self):
		return len(self.wmsg)
	
	def ProcessData(self, data):
		self.data = self.data + data
		
		print('processing data', len(self.data))
		# do we need to read a message header and can we?
		if self.wsz is None and len(self.data) >= 8 + 4:
			print('reading sz and vector')
			sz, vector = struct.unpack_from('>IQ', self.data)
			print('sz:%s vector:%x' % (sz, vector))
			self.wsz = sz
			self.wvector = vector
			self.data = self.data[8 + 4:]
		
		print('checking for enough data (%s of %s)' % (len(self.data), self.wsz))
		# not enough data to read message portion
		if len(self.data) < self.wsz:
			return (None, None)
		
		# get message and leave remaining data
		# in the buffer for the next call
		_ret = self.data[0:self.wsz]
		self.data = self.data[self.wsz:]
		
		# return the message and vector
		self.wsz = None
		self.wvector = None
		return (_ret, self.wvector)
		
class Server:
	def __init__(self):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sock.bind(('0.0.0.0', 4322))
		self.sock.listen(20)
		self.sc = {}
		self.socktosc = {}
		self.maxclientbuffer = 4096
	
		# read the public and private keys
		pub = pubcrypt.readSSHPublicKey('id_rsa.pub')
		pri = pubcrypt.readSSHPrivateKey('id_rsa')
		
		# fixup the keys 
		self.keypub = (pubcrypt.fromi256(pubcrypt.toi256r(pub[0])), pubcrypt.fromi256(pubcrypt.toi256r(pub[1])))
		self.keypri = (pubcrypt.fromi256(pubcrypt.toi256r(pri[0])), pubcrypt.fromi256(pubcrypt.toi256r(pri[1])))
	
	def HandleMessages(self):
		# client, addr = sock.accept()
		while True:
			input = [self.sock]
			for scaddr in self.sc:
				tsc = self.sc[scaddr]
				input.append(tsc.GetSock())
		
			readable, writable, exc = select.select(input, input, input)
			
			# accept incoming connections
			if self.sock in readable:
				nsock, caddr = self.sock.accept()
				nsc = ServerClient(nsock, caddr, self.keypub, self.keypri)
				self.sc[caddr] = nsc
				self.socktosc[nsock] = nsc
				readable.remove(self.sock)
			
			# read any pending data (and process it)
			for sock in readable:
				sc = self.socktosc[sock]
				if sc.GetBufferSize() < self.maxclientbuffer:
					data = sock.recv(self.maxclientbuffer - sc.GetBufferSize())
					if not data:
						# connection closed, drop it
						print('dropped connection %s' % (sc.GetAddr(),))
						del self.sc[sc.GetAddr()]
						del self.socktosc[sock]
					else:
						sc.HandleData(data)
			
			# handle any exceptions
			for sock in exc:
				sc = self.socktosc[sock]
				del self.sc[sc.GetAddr()]
				del self.socktosc[sock]
				
			# continue main loop
			continue

def main():
	server = Server()
	server.HandleMessages()
	
main()