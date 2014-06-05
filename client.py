import os
import sys
import socket
import struct

import pubcrypt

from pkttypes import *
from misc import *

'''
	0 - whole file (fixed size)
	1 - sparse file (non-fixed size)
	2 - change file (linked to another file and stores differences)
	
	file are identified with two parts
		1. name
		2. revision
		
	revision 0 always means current
	revision 1 is oldest revision
	revision 2 is newer revision
	revision X is newer than X - 1 and older than X + 1 but older than 0
	
	files are stored in the following format
	<type>.<stash>.<encoded-name>
	whole.0.c%43rk%%.txt			- whole
	sparse.0.c%43rk%%.txt			- sparse
	meta.c%43rk%%.txt				- meta file (listing of revisions) + dependancies for change files
	
	encoded-name suppots the usage of any character
	
	directory names use encoded-name so it can use any character
	
	the slash is a special character and if used represents a directory
'''

class UnknownMessageTypeException(Exception):
	pass
	
class Client:
	def __init__(self, rhost, rport, aid):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.keepresult = {}
		self.vector = 0
		self.rhost = rhost
		self.rport = rport
		self.aid = aid
	
	def Connect(self):
		# try to establish a connection
		self.sock.connect((self.rhost, self.rport))
		# get public key
		print('requesting public key')
		self.WriteMessage(struct.pack('>B', ClientType.GetPublicKey), False, True)
		# wait for packet
		s, v, pubkey = self.ReadMessage()
		type, esz = struct.unpack_from('>BH', pubkey)
		print('esz:%s' % (esz))
		e = pubkey[3:3 + esz]
		p = pubkey[3 + esz:]
		self.pubkey = (e, p)
		print(self.pubkey)
		# setup encryption
		key = IDGen.gen(10)
		print('key:%s' % key)
		self.crypter = SymCrypt(key)
		self.WriteMessage(struct.pack('>B', ClientType.SetupCrypt) + key, False, True)
		# wait for reply
		print('waiting for setup crypt reply')
		self.ReadMessage()
		print('logging into the system')
		data = struct.pack('>B', ClientType.Login) + self.aid
		print('writing-message:[%s]' % data)
		self.WriteMessage(data, False, True)
		result = self.ProcessMessage(0, 0, self.ReadMessage()[2])
		if result:
			print('login good')
			return True
		else:
			print('login bad')
			exit() 
			return False
		
	# processes any incoming messages and exits after specified time
	def HandleMessages(self, timeout, lookfor = None):
		if timeout is not None:
			st = time.time()
			et = st + timeout
		while timeout is None or timeout < 0 or et - time.time() > 0:
			if timeout is not None:
				to = et - time.time()
				if to < 0:
					to = 0
			else:
				to = None
			sv, v, d = self.ReadMessage(to)
			msg = self.ProcessMessage(sv, v, d)
			print('processed message sc:%s v:%s lookfor:%s msg:%s' % (sv, v, lookfor, msg))
			if lookfor == v:
				return msg
			if v in self.keepresult:
				self.keepresult[v] = msg
			continue
		return
		
	# processes any message and produces output in usable form
	def ProcessMessage(self, svector, vector, data):
		type = data[0]
		
		print('got type %s' % type)
		
		# only process encrypted messages
		if type != ServerType.Encrypted:
			return None
			
		# decrypt message (drop off encrypted type field)
		data = self.crypter.decrypt(data[1:])
		type = data[0]
		data = data[1:]
		
		# process message based on type
		if type == ServerType.LoginResult:
			print('login result data:[%s]' % data)
			if data[0] == ord('y'):
				return True
			return False
		if type == ServerType.DirList:
			# i hate to chop strings but...later make more efficient
			print('parsing DirList results')
			list = []
			while len(data) > 0:
				# parse header
				fnamesz, frev = struct.unpack_from('>HI', data)
				# grab out name
				fname = data[2 + 4: 2 + 4 + fnamesz]
				# chop off part we just read
				data = data[2 + 4 + fnamesz:]
				# build list
				list.append((fname, frev))
			# return list
			return list
		if type == ServerType.FileRead:
			return (struct.unpack_from('>B', data)[0], data[1:])
		if type == ServerType.FileWrite:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileSize:
			return struct.unpack_from('>BQ', data)
		if type == ServerType.FileTrun:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileDel:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileCopy:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileMove:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileHash:
			return (struct.unpack_from('>B', data)[0], data[1:])
		if type == ServerType.FileStash:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileGetStashes:
			parts =  data.split('.')
			out = []
			for part in parts:
				out.append(int(part))
			return out
		raise UnknownMessageTypeException('%s' % type)
	
	# read a single message from the stream and exits after specified time
	def ReadMessage(self, timeout = None):
		print('reading message')
		self.sock.settimeout(timeout)
		sz, svector, vector = struct.unpack('>IQQ', self.sock.recv(4 + 8 + 8))
		print('read header')
		data = self.sock.recv(sz)
		print('read data', data)
		return svector, vector, data
		
	def WriteMessage(self, data, block, discard):
		vector = self.vector
		self.vector = self.vector + 1
		
		# get type
		type = data[0]
		
		# leave get public key and setup crypt unaltered
		if type == ClientType.GetPublicKey:
			# do not encrypt at all
			pass
		else:
			if type == ClientType.SetupCrypt:
				# public key crypt
				data = data[0:1] + pubcrypt.crypt(data[1:], self.pubkey)
			else:
				# normal encrypt (keep type field unencrypted)
				print('encrypting message:[%s]' % (data))
				data = bytes([ClientType.Encrypted]) + self.crypter.crypt(data)
		
		self.sock.send(struct.pack('>IQ', len(data), vector))
		self.sock.send(data)
		if block:
			print('blocking by handling messages')
			res = self.HandleMessages(None, lookfor = vector)
			print('	returned with res:%s' % (res,))
			return res
		if discard:
			return vector
		self.keepresult[vector] = None
		return None
		
	def DirList(self, dir, block = True, discard = True):
		return self.WriteMessage(struct.pack('>B', ClientType.DirList) + dir, block, discard)
	def FileRead(self, fid, offset, length, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BHQQ', ClientType.FileRead, fid[1], offset, length) + fid[0], block, discard)
	def FileWrite(self, fid, offset, data, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BHQH', ClientType.FileWrite, fid[1], offset, len(fid[0])) + fid[0] + data, block, discard)
	def FileSize(self, fid, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileSize, fid[1]) + fid[0], block, discard)
	def FileTrun(self, fid, newsize, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BHQ', ClientType.FileTrun, fid[1], newsize) + fid[0], block, discard)
	def FileDel(self, fid, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileDel, fid[1]) + fid[0], block, discard)
	def FileCopy(self, srcfid, dstfid, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BHHH', ClientType.FileCopy, srcfid[1], dstfid[1], len(srcfid[0])) + srcfid[0] + dstfid[0], block, discard)
	def FileMove(self, fid, newfile, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BHHH', ClientType.FileMove, srcfid[1], dstfid[1], len(srcfid[0])) + srcfid[0] + dstfid[0], block, discard)
	def FileHash(self, fid, offset, length, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BHQQ', ClientType.FileHash, fid[1], offset, length) + fid[0], block, discard)
	def FileStash(self, fid, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileStash, fid[1]) + fid[0])
	def FileGetStashes(self, fid, block = True, discard = True):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileGetStashes, fid[1]) + fid[0])
		
		
def main():
	client = Client('localhost', 4322, b'Kdje493FMncSxZs')
	print('setup connection')
	client.Connect()
	print('	setup connection done')
	
	print('requesting directory list')
	list = client.DirList(b'/')
	
	print('truncating file')
	result = client.FileTrun((b'test', 0), 1024)
	print('FileTrun.result:%s' % result)
	
	result = client.FileWrite((b'test', 0), 0, b'hello world')
	print('FileWrite.result:%s' % result)
	
	result = client.FileRead((b'test', 0), 0, 11)
	print('FileRead.result:%s' % (result,))
	
	result = client.GetHash((b'test', 0), 0, 11)
	
	while True:
		continue
	
main()