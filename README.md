![neophytos-logo](http://kmcg3413.net/logo.png)
=====

The Neophytos system has the following features:
* secure communication from client to server
* multiple backup targets per account
* multiple sub-accounts with different permissions if desired (read/write)
* delta uploading/downloading (only uploads/downloads changed portion of file)
* file stashing (supports versions and recovery of deleted files if desired)
* open source client and server
* cross-platform (Linux, Windows, ARM, or anywhere Python 3.x will run)
* files can be encrypted client side (in memory) before being sent (sensitive data protected on server)
* service provided for customers (currently in development)

The communication from the client to server by default uses SSL which is same technology
used over HTTPS. There is also a built in much less secure encryption that can maximize your bandwidth when uploading or downloading data. Even though the client and server is open source you will still need access to a server in order to incorporate your own encryption. You can however implement your own encryption for the actual file data that is stored on the server thus encrypting your file data over the internet.

Each account can support an unlimited number of targets on the server. This allows you to say backup your documents to the _documents_ target on the server, and also backup your work files to _work_. The target is basically like a sub-directory on the server. Also account can be created that reference into other accounts so that you could create an additional account that references into a sub-folder called _presentations_ in your _documents_ target that only has read permission. This allows you to provide access to other users with out allowing them to write to certain files or see certain files.

The client and server currently support a primitive delta patching algorithm that only transmits changes between files which further reduces the time and bandwidth needed when backing up or restoring data. The
algorithm is designed so that most of it resides client side so you have a wide range of opportunities for
improving or tailoring it to your specific situations.

The file stashing allows you to store the same file multiple times on the server. This allows you to store different versions. Perhaps you may wish to keep the original copy of a file, or always keep the most recent version from backup to backup. It can even allow you to keep a copy around of a deleted file. You can have an unlimited number of versions however they all consume space on the server.

Because the client and server are open source you can change it to suit your needs, add features, or change existing features. It also allows you a more secure installation on your machine because you can verify what the client does, has access too, and what is transmitted.

The client and server are cross-platform. They will run anywhere that Python 3.x will run. This allows you to have clients on various platforms using the same data. It also allows the server to run on any system although it has been tailored to Linux. There can be some problems for example between Windows and Linux with case-sensitive files where Linux supports case-sensitive file names and Windows does not. So the server is tailored for a Linux platform, but it can run on any platform and support could be easily added for Windows to become case-sensitive by encoding the file names where needed.

Your files can be encrypted locally (client side) before being transmitted. Your actual file on your disk is not encrypted but rather it is encrypted as it is transmitted, and decrypted as it is received from the server and restored. This ensures highly sensitive data is not vulnerable server side in the event someone was able to access the data. This is completely client implemented allowing complete control.

_Currently, the customer service is in development along with the software._ For those of you who do not wish, need, or have the capability to run your own server a service is provided for a charge that is competitive with current backup solutions to store your data.

Current State
=====
The software is currently in development. It is not officially released as stable. It is not completely usable because it does lack some features described above. It however is very close to being finished. This is a list of things and their progress.

* client command line interface (85% complete; _usable_)
* file stashing (50% complete; implemented server side but not used client side)
* file encryption (0% complete; implemented server side but client does not provide this functionality yet)
* encrypted communication between client and server over the internet (SSL and XORMIX) (100% complete)
* delta uploading/downloading (100% complete; client side needs more testing and tweaking)
* graphical front-end (0% complete; will provide a graphical front end for X11 and Windows)

Client Tutorial
=====
_Will be added later._

Server Tutorial
=====
_Will be added later._