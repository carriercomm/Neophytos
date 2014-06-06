import os
import sys
import socket
import struct
import hashlib
import math

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
			#print('processed message sc:%s v:%s lookfor:%s msg:%s' % (sv, v, lookfor, msg))
			if lookfor == v:
				return msg
			if v in self.keepresult:
				self.keepresult[v] = msg
			continue
		return
		
	# processes any message and produces output in usable form
	def ProcessMessage(self, svector, vector, data):
		type = data[0]
		
		#print('got type %s' % type)
		
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
		#print('reading message')
		self.sock.settimeout(timeout)
		sz, svector, vector = struct.unpack('>IQQ', self.sock.recv(4 + 8 + 8))
		#print('read header')
		data = self.sock.recv(sz)
		#print('read data', data)
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
				#print('encrypting message:[%s]' % (data))
				data = bytes([ClientType.Encrypted]) + self.crypter.crypt(data)
		
		self.sock.send(struct.pack('>IQ', len(data), vector))
		self.sock.send(data)
		if block:
			#print('blocking by handling messages')
			res = self.HandleMessages(None, lookfor = vector)
			#print('	returned with res:%s' % (res,))
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

class Client2(Client):
	def __HashLocalFile(self, fd, offset, length):
		fd.seek(offset)
		data = fd.read(length)
		#print('ldata', data)
		return hashlib.sha512(data).digest()

	def UploadFile(self, fid, fd, lsz):
		max = 1024 * 1024
		x = 0
		c = math.ceil(lsz / max)
		fd.seek(0)
		while x < c:
			if x * max + max > lsz:
				_sz = lsz - (x * max)
			else:
				_sz = max
			off = x * max
			print('  uploading offset:%x/%x size:%x' % (off, lsz, _sz))
			self.FileWrite(fid, off, fd.read(_sz))
			x = x + 1
	
	def __FilePatch(self, lfd, rfd, offset, sz, match, info):
		tfsz = info['total-size']
		unet = info.get('net-traffic', 0)
		gbytes = info.get('good-bytes', 0)
		
		# at this point it is completely pointless to continue
		# as we have already consumed enough net traffic to have
		# uploading the file whole (so we are just wasting time
		# and bandwidth to continue onward)
		if unet >= tfsz - gbytes:
			return
			
		# at this point in time we should likely consider giving
		# up and exclude the good range we have found if ny
		#if unet >= (tfsz - gbytes) / 4:
		if unet >= tfsz / 4:
			return
		
		# dont do larger than 1MB chunk
		divide = sz / (1024 * 1024)
		# change it up if we have less than 20
		if divide < 20:
			divide = 20
			# if the size is less than 4096 then change that
			# to a minimum of 4096
			if sz / divide < 4096:
				divide = math.ceil(sz / 4096)
		
		print('divide:%s sz:%s' % (divide, sz))
		
		# calculate actual chunk size to hash and count
		# with remainder either as a separate chunk or
		# combined with last
		pasz = sz / divide
		pasz = math.floor(pasz)
		rem = sz - (pasz * divide)
		
		go = []
		# build the primary checks
		x = 0
		while x < divide - 1:
			go.append((offset + x * pasz, pasz))
			x = x + 1
		if rem > pasz / 2:
			# split it into two separate checks
			go.append((offset + x * pasz, pasz))
			go.append((offset + x * pasz + pasz, rem))
		else:
			# combine into one
			go.append((offset + x * pasz, pasz + rem))
		
		# iterate through checks
		for c in go:
			rhash = self.FileHash(rfd, c[0], c[1])[1]
			lhash = self.__HashLocalFile(lfd, c[0], c[1])
			info['net-traffic'] = info.get('net-traffic', 0) + 200
			
			# debug message
			print('    unet:%x gbytes:%x hashing offset:%x length:%x' % (unet, gbytes, c[0], c[1]))
			
			# should we go deeper
			if c[1] < 4096:
				continue
				
			if rhash != lhash:
				# go deeper
				self.__FilePatch(lfd, rfd, c[0], c[1], match, info)
			else:
				# record parts that do not need to be updated
				info['good-bytes'] = info.get('good-bytes', 0) + sz
				match.append((offset, sz))
				print('found good area offset:%s sz:%s' % (c[0], c[1]))
		return
	'''
		@sdescription:		Will upload or update the remote file with this local
							file by trying to patch it instead of uploading it all.
	'''
	def FilePatch(self, fid, lfile):
		try:
			fd = open(lfile, 'rb')
		except IOError as e:
			# for some reason we are unable to access
			# the file so just print an exception and
			# skip this file
			print(e)
			return 
		# get length of local file
		fd.seek(0, 2)
		lsz = fd.tell()
		fd.seek(0)
		print('patching remote file %s with local file %s' % (fid[0], lfile))
		print('	setup')
		# get length of remote file if it exists
		rsz = self.FileSize(fid)[1]
		# either make remote smaller or bigger
		print('rsz:%s lsz:%s' % (rsz, lsz))
			
		if rsz != lsz:
			self.FileTrun(fid, lsz)

		if rsz < lsz / 2:
			# just upload it whole
			self.UploadFile(fid, fd, lsz)
			fd.close()
			return
			
		#self.FileWrite(fid, 0, b'hello world')
		#exit()
			
		#rhash = self.FileHash(fid, 25, 25)[1]
		#lhash = self.__HashLocalFile(fd, 25, 25)
		#print(rhash)
		#print(lhash)
		
		#print(self.FileRead(fid, 25, 25))
		#exit()
			
		# prepare structures
		match = []
		info = {
			'total-size':		lsz
		}
		# build match list
		print(' hash scanning')
		
		# break it into maximum sized chunks
		# in order to prevent oversized buffer
		# on the server (done on server to prevent
		# some DoS attacks)
		max = 1024 * 1024
		pcnt = math.ceil(lsz / max)
		x = 0
		while x < pcnt:
			if x * max + max > lsz:
				_sz = lsz - (x * max)
			else:
				_sz = max
			off = x * max
				
			self.__FilePatch(fd, fid, off, _sz, match, info)
			x = x + 1
		# we need to invert the match list to
		# determine what regions we need to write
		# to bring the file up to date
		print('	inverting')
		invert = []
		invert.append((0, info['total-size']))
		for good in match:
			gx = good[0]
			gw = good[1]
			for bad in invert:
				bx = bad[0]
				bw = bad[1]
				chg = False
				if gx == bx and gx + gw == bx + bw:
					#print('whole')
					bw = 0
					chg = True
				else:
					if gx == bx and gx + gw < bx + bw:
						#print('left side')
						# left side
						bx = gx + gw
						bw = bw - gw
						chg = True
					if gx > bx and gx + gw == bx + bw:
						# right side
						#print('right side')
						bw = bw - gw
						chg = True
					if gx > bx and gx + gw < bx + bw:
						# middle (left side)
						#print('middle')
						_bw = bw
						bw = gx - bx
						# middle (right side)
						_bx = gx + gw
						_bw = _bw - (bw + gw)
						invert.append((_bx, _bw))
						chg = True
				if chg:
					# remove old one and add new one
					invert.remove(bad)
					if bw > 0:
						invert.append((bx, bw))
					# exit out if found it
					break
			# invert iteration
		# match iteration
	
		# now only upload the bad parts
		for bad in invert:
			bx = bad[0]
			bw = bad[1]
			
			# cut it into max sized pieces
			divide = math.ceil(bw / (1024 * 1024))
			rem = int(bw - (divide * 1024 * 1024))
			
			x = 0
			while x < divide:
				o = x * 1024 * 1024
				fd.seek(bx + o)
				data = fd.read(1024 * 1024)
				print('writing bad (%s:%s)' % (bx + o, 1024 * 1024))
				self.FileWrite(fid, bx + o, data)
				x = x + 1
			if rem > 0:
				o = x * 1024 * 1024
				fd.seek(bx + o)
				data = fd.read(rem)
				print('writing bad (%s:%s)' % (bx + o, rem))
				self.FileWrite(fid, bx + o, data)

		fd.close()
		
def main():
	client = Client2('localhost', 4322, b'Kdje493FMncSxZs')
	print('setup connection')
	client.Connect()
	print('	setup connection done')
	
	'''
	print('requesting directory list')
	list = client.DirList(b'/')
	
	print('truncating file')
	result = client.FileTrun((b'test', 0), 1024)
	print('FileTrun.result:%s' % result)
	
	result = client.FileWrite((b'test', 0), 0, b'hello world')
	print('FileWrite.result:%s' % result)
	
	result = client.FileRead((b'test', 0), 0, 11)
	print('FileRead.result:%s' % (result,))
	
	result = client.FileHash((b'test', 0), 0, 11)
	print('SZ', len(result[1]))
	'''
	
	#result = client.FilePatch((b'sample', 0), './sample')
	
	while True:
		continue

if __name__ == '__main__':
	main()