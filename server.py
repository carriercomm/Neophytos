import os
import sys
import socket
import select
import struct

from pkttypes import *
from misc import *

import pubcrypt

class DoubleTypeOrRevException(Exception):
	pass
	
class NodeTypeUnknownException(Exception):
	pass

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
		
	def SanitizePath(self, path):
		while path.find(b'..') < 0:
			path = path.replace(b'..', b'.')
		return path
		
	def GetPathParts(self, fname)
		# break out base path if specified otherwise consider in root
		pos = fname.rfind(b'/')
		if pos < 0:
			fbase = '/'
		else:
			fbase = fname[0:pos]
			fname = fname[pos + 1:]
		return fbase, fname
			
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
			print('loading account')
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
			# remove any dot dots to prevent backing out of root
			cpath = '%s/%s' % (self.info['disk-path'], self.SanitizePath(msg))
			nodes = os.listdir(cpath)
			objs = []
			for node in nodes:
				# break node into appropriate parts
				frev = node[0:node.find('.')]
				fname = bytes(node[node.find('.') + 1:], 'utf8')
				# there should be only one type of each fname
				if (fname, frev) not in objs:
					# store so we can detect duplicates
					objs.append((fname, frev))
				else:
					# since were in development stage get our attention!
					raise DoubleTypeOrRevException()
					# remove it before it causes more problems
					os.remove('%s/%s' % (cpath, node))
			# serialize output into list of entries
			out = []
			for key in objs:
				out.append(struct.pack('>HI', len(key[0]), key[1]) + key[0])
			out = b''.join(out)
			
			self.WriteMessage(struct.pack('>B', ServerType.DirList) + out)	
			return

		if type == ClientType.FileSize:
			rev = struct.unpack_from('>H', msg)[0]
			fname = msg[2:]
			
			fbase, fname = self.GetPathParts(fname)
			
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
			if os.path.exists(fpath) is False:
				self.WriteMessage(struct.pack('>BBQ', ServerType.FileSize, 0, 0), vector)
				return
			
			fd = open(fpath, 'rb')
			fd.seek(0, 2)
			sz = fd.tell()
			fd.close()
			
			self.WriteMessage(struct.pack('>BBQ', ServerType.FileSize, 1, sz), vector)
			return
			
		if type == ClientType.FileTrun:
			rev, newsize = struct.unpack_from('>HQ', msg)
			fname = msg[2 + 8:]
			
			fbase, fname = self.GetPathParts(fname)
			
			# this will either create the file OR change the size of it
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
			fd = open(fpath, 'wb')
			fd.truncate(newsize)
			fd.close()
			self.WriteMessage(struct.pack('>BB', ServerType.FileTrun, 1), vector)
			return
			
		if type == ClientType.FileRead:
			rev, offset, length = struct.unpack_from('>HQQ', msg)
			fname = msg[2 + 8 + 8:]
			
			# maximum read length default is 1MB (anything bigger must be split into separate requests)
			# OR.. we could spawn a special thread that would lock this client and perform the work
			# in parallel with this main thread
			if length > self.info.get('max-read-length', 1024 * 1024 * 1):
				self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 2), vector)
				return

			# get path parts
			fbase, fname = self.GetPathParts(fname)
			
			# build full path to file (including revision)
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
			if os.path.exists(fpath) is False:
				# oops.. no such file (lets tell them it failed)
				self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 0), vector)
				return
			# okay open the file and read from it
			# later.. i might want to cache file descriptors to increase performance (or even mmap files actually)
			fd = open(fpath, 'rb')
			fd.seek(offset)
			data = fd.read(length)
			fd.close()
			
			self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 1) + data, vector)
			return
		if type == ClientType.FileWrite:
			rev, offset, fnamesz = struct.unpack_from('>HQH', msg)
			fname = msg[2 + 8:2 + 8 + fnamesz]
			data = msg[2 + 8 + fnamesz:]
			
			if length > self.info.get('max-write-length', 1024 * 1024 * 1):
				self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 2), vector)
				return
			
			fbase, fname = self.GetPathParts(fname)
			
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
			if os.path.exists(fpath) is False:
				self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 0), vector)
				return
			
			fd = open(fpath, 'wb')
			fd.seek(0, 2)
			max = fd.tell()
			if offset + len(data) >= max:
				# you can not write past end of the file (use truncate command)
				self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 2), vector)
				return
			fd.seek(offset)
			fd.write(data)
			fd.close()
			self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 1))
			return
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