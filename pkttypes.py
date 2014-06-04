class ClientType:
	DirList 		= 0
	FileRead 		= 1
	FileWrite 		= 2
	FileSize 		= 3
	FileTrun 		= 4
	FileDel 		= 5
	FileCopy 		= 6
	FileMove 		= 7
	FileHash 		= 8
	FileStash 		= 9
	FileGetStashes 	= 10
	GetPublicKey	= 11
	SetupCrypt		= 12
	Encrypted		= 13
	Login			= 14
	
class ServerType:
	DirList 		= 0
	FileRead 		= 1
	FileWrite 		= 2
	FileSize 		= 3
	FileTrun 		= 4
	FileDel 		= 5
	FileCopy 		= 6
	FileMove		= 7
	FileHash 		= 8
	FileStash 		= 9
	FileGetStashes 	= 10
	PublicKey		= 11
	SetupCrypt		= 12
	Encrypted		= 13
	Login			= 14
	LoginRequired	= 15
	LoginResult		= 16
