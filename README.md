![neophytos-logo](http://kmcg3413.net/rdss.png)
=====

Dependancies
=====

The dependancies are very minimal and this is intentional. I try to use only what
is included in the Python standard library. Also, for the server I try to only use
what is the Golang standard library.

* server requires Golang to build or compile with - i am looking at providing prebuilt binaries
* client requires Python 3.x (prefer latest version especially on Windows)
* client GUI requires PyQt4 (GUI is work in progress)

I choose Go because it provided the needed performance. I did not know much about Rust at the
time, but I could in the future port to Rust as I research the language more. There are a lot
of design decisions to make regarding either one.

I prefer to use Python as it provides rapid application development and is easy to use with
an assortment of libraries, but when it comes to performance it is not always so great.

Current State
=====

The [X] means it has been implemented, while [ ] means still in development.

* [X] secure communication from client to server
* [X] multiple backup targets per account
* [X] multiple sub-accounts with different permissions if desired (read/write)
* [X] delta uploading/downloading (only uploads/downloads changed portion of file)
* [X] _(50% implemented)_ file stashing (supports versions and recovery of deleted files if desired)
* [X] open source client and server
* [X] cross-platform client (Linux, Windows, ARM, or anywhere Python 3.x will run)
* [X] cross-platform server (Anywhere golang will run, or can target.)
* [ ] files can be encrypted client side (in memory) before being sent (sensitive data protected on server)
* [X] client command line interface (95% complete; _very much usable_)
* [ ] filter system (disabled at the moment but 90% of the support is there)
* [ ] GUI frontend
* [X] delta uploading (patching) - only changed parts of file are uploaded

Client Tutorial
=====
To run the client use:

    python3 backup.py

Some of the options are:

    --lpath=<local path>                              local machine absolute path
    --rpath=<remote path>                             remote server relative path 
    --password=<authorization code>                   specifies the authorization code
    --push                                            will push files to the server
    --pull                                            will pull files from the server
    --sync-rdel                                       will synchronize remote for locally deleted files
    --host                                (optional)  the hostname or address (default to kmcg3413.net)
    --port                                (optional)  the port (default 4322)
    --cipher                              (optional)  SSL cipher string (RC4, RSA, DSA, ..)
    --filter-file                         (optional)  file with one filter entry per line
    --make-sample-filter-file                         produces example filter file as filter.example
    --authcode=<authorization code>                   SAME AS --password
    --no-ssl                                          uses non-SSL socket (could be buggy)
    --debug                                           enables debug output
    --no-sformat                                      disables using stash format on server

For example to push all files in a directory to the server under the name `peach`.

    python3 backup.py --push --lpath=/mnt/kmcguire --rpath=peach --host=myserver --password=e3xample

To pull files from server under the name `peach`.

    python3 backup.py --pull --lpath=/temp --rpath=peach --host=myserver --password=e3xample

To pull all targets (including peach and any others).

    python3 backup.py --pull --lpath=/mnt/kmcguire/temp --host=myserver --password=e3xample
	
If you are pushing to something where the files will be used directly which is more like `rsync` then
you should also add the `--no-sformat` option to any operation. This will ensure that the client does
not try to interpret the files like they are in a stash format. I think a `--pull` operation may work
fine with out it but the correct way is to use the `--no-sformat` option.

    python3 backup.py --push --lpath=/mnt/kmcguire --rpath=rsynclike --no-sformat

The files placed on the server will be named exactly like they are locally using the `--no-sformat` option. If
you omit this you will end up with a revision (or stash identifier) prefixed to every file and directory. This
is useful when your just trying to synchronize two paths between two machines. You can actually do all the 
synchronization from one machine with.

    python3 backup.py --pull --lpath=/mnt/kmcguire --rpath=rsynclike --no-sformat
    python3 backup.py --push --lpath=/mnt/kmcguire --rpath=rsynclike --no-sformat

The only problem is this will delete nothing locally or remotely which can be desired, but due to
technical limitations it is not easy to infer if a file has been deleted from the server because
that would require storing this information. And, for how long should this be stored? _This type
of a situation would likely better lend it's self other solutions that I have in mind but need
more time to actually put together._

Server Tutorial
=====

_I rewrote the server in Go (golang) to have lower CPU usage, but I have not fully added back in
 support for the quota! And, what code has been added has not been well tested!_

First we need to generate a certificate and an RSA private/public key pair. The certificate is used with SSL and the private/public RSA key pair are used by both SSL and other supported communication link encryptions.

    openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout cert.pem --newkey rsa:8192

_This will generate a 8192-bit key pair which should be decently secure. You should be able to generate and use any size._

	
This file should be named _cert.pem_ in the server's working directory. The server can now be started if desired, or you can wait.

The next step is creating an account. There should be a sub-directory created called _accounts_ in the server's working directory. Inside create a file named exactly _hdk392Ej_. This will be the authorization code used to access this account. The _accounts_ directory should be kept **SECRET**. Anyone with access to it will know the authorization code for any account. I suspect if they have access to this directory then they likely have access to any data for the accounts. We will discuss data in a moment.

Once the file _hdk392Ej_ is created open it with an editor. Place these contents inside:

    SpaceQuota:   100000000
    SpaceUsed:    0
    SpacePerFile: 4096
    SpacePerDir:  4096
    DiskPath:     /home/kmcguire/data/ok493L3Dx92Xs029W

The _disk-used_ represents the bytes used by the account. The _disk-used-perfile_ represents the bytes to subtract for each file created and tries to sort of serve to account for an account with lots of small or empty files.

The server has now been configured and setup for the account _hdk392Ej_. The _hdk392Ej_ serves as the username and password combination. I recommend using something much longer. If you are intent on using something resembling more of a username and password combination then you could do something along the lines of _username.password_ and replace each with the respective username and password.

_I would like to add support in later for a more securish (at least looking) account database. At the moment the server and client are still in development and this is not by any means the final form but simply represents a roughed in system._

To start the server you will need to issue the following commands for Golang.

    GOPATH="/home/kmcguire/project/goserver"
    export GOPATH
    go run ./src/main.go

Where `GOPATH` specifies the directory `goserver` included when you download the project repository. You can
also build an executable using `go`, but I will leave that as an excercise for you for now!