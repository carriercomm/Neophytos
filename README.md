![neophytos-logo](http://kmcg3413.net/rdss.png)
=====

Dependancies
=====

The dependancies are very minimal and this is intentional. I try to use only what
is included in the Python standard library. Also, for the server I try to only use
what is the Golang standard library. If try to implement everything in pure Python,
but when performance suffers I will include support for native code while keeping
the pure Python implementation around if possible.

* server requires Golang to build or compile with - i am looking at providing prebuilt binaries
* client requires Python 3.x (prefer latest version especially on Windows)
* client GUI requires PyQt4 (GUI is work in progress)

I choose Go because it provided the needed performance. I did not know much about Rust at the
time, but I could in the future port to Rust as I research the language more. There are a lot
of design decisions to make regarding either one.

I prefer to use Python as it provides rapid application development and is easy to use with
an assortment of libraries, but when it comes to performance it is not always so great.

I use PyQt4 for the GUI because it is a stable, modern, mature, cross-platform, simple, and
powerful.

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
* [ ] broken; GUI frontend (client changes have broken the once partially working GUI)
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

Filters
=====

For those less inclined to delve into the source code and implement your own filter system there
is one provided that is fairly powerful in design, and easy to understand. First let us take a
look at a common filter.

    dir       reject      ^test$
    any       accept      .*

This would be located in a file of your choice in naming. For this example let us pretend it was saved
under `test-filter` located in the working directory of the client. You load this file you would issue
the option `--filter-file=test-filter`. Notice the filename comes after the equal sign. You can also
specify relative and absolute paths such as `/home/dave/myfilters/onlysource` or `../myfilters/nomedia`.

Each line is a filter rule. You can insert tabs or spaces between the elements of a filter rule. The
filter rule has three elements. The first is the type of rule, the second is what to do if it matches,
and the third is the regular expression (pattern) to do the matching with. The tabs and spaces do not
have to be the same on each rule however it may look nicer and be easier to read if you do maintain 
equal spacing.

That filter will accept all files and directories _except_ any directory named `test`. 
To do this the filter is executed 
from top to bottom for each file and directory. It first evaluates `dir reject ^test$`. If this rule
matches it rejects it. But, for it to even evaluate it has to be a `dir`. If it was a file it woud just
skip down to the next line. So essentially each rule is evaluated and if it matches it either accepts
or rejects. You can make rules for `dir`, `file`, `path`, or `any`. When a file or dires orctory is tested
only the top level portion of the path is used. For example for `/home/dave/test/apple.png` only `apple.png`
is checked _except if you use the `path` type. The `path` type checks the entire path.

What happens when it reaches the end of the filter file and has no matches? Well, by default it rejects. You
can have an unlimited amount of rules. _I hope to one day add more functionality such as forward jumps so you
can create individual sections for specific things with some basic flow control.


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

Technical Limitations Of Client And Server
=====
_When I refer to stashing I am refering to the ability to create an one or more alternative data
streams each with meta-data._

_When I refer to meta-data I am refering to the ability to tag a file with an variable sized byte
header._

If you use the byte 0xff as the first byte
in a directory name you will be unable to use the stashing features of the client. 
The stashing is implemented completely by the client. The server is unaware of stashing. You can
however modify the client and circumvent this limitation. I implemented it this way to balance between
performance, or so I intended to do so. It is possible to make this limitation only apply to the very
first directory of a path but it requires a little work which I have not done quite yet.

The server at this time is expected to support a filename of at least a length of 255 bytes. 
If you use UTF-16 that means you can have a filename length of 128 bytes. If you use UTF-8 it can vary. 
This is the maximum supported filename length of the EXT4 file system on linux. The server does not 
enforce this limitation, but instead the OS and file system that the server is running on and 
manipulating files on does. If your OS has no limitation then it is solely dependant on the 
file system you are using such as NTFS, NFS, EXT, and any other. The server places no maximum
length on filenames or paths but it does place a limitation on the maximum message size at 
around 4MB currently. This means if your filename is 3MB in length then you only have 1MB left 
for data and that might slighlty impact uploading speed.

The client using stashing expects the very first directory to be 253 bytes at most. The
larger the stash identifier (no matter numeric or byte string) the more is subtracted from the
255 limit (unless your OS and FS supports longer directory names). The standard client currently
uses a 64-bit big endian integer to represent the revision identifier which is unix time 
in seconds. This is done by not using the value 255 in any byte position.

Let us talk about the first directory name as it means something different that what would
normaly be expected. When you push files you can specify the `--rpath`. This means just
what you would imagine. It is a prefix to the remote path. So for example if you use
`--lpath=/home/dave/documents` and `/home/dave/documents` looks like this:

    /home/dave/documents
        /workstuff/...
        /homestuff/...
        /manuals/...
        /armx86x64/..
        /companyreport.pdf

If you use `--rpath=dave-documents` then the client will do this:

    /dave-documents/workstuff/...
    /dave-documents/homestuff/...
    /dave-documents/manuals/...
    /dave-documents/arm86x64/...
    /dave-documents/companyreport.pdf

This is very useful as it allows you to not only prefix a path, but it can also be used
to only pull from certain remote paths. The `--rpath` serves as a target identifier and
a remote path prefix. You can treat `--rpath` like a path, group name, target name, or
whatever you like.

The client implements stashing (alternative data streams) by prefixing something this to the path once
the `--rpath` prefix is added. This something is the byte `0xff`. It only does it for the very first
directory. The client also uses a 64-bit big-endian unix time in seconds after the `0xff`. So if you
stashed a file like `/dave-documents/armx86x64/intelmanual.pdf` it will be turned into something
like this `/\xff\x34\xe3\x23\x87dave-documents/armx86x64/intelmanual.pdf`. As you can see now the
exact same file is stored but under a prefix.

So you say that seems easy right? Well, if you dont use `--rpath` you do not get a prefix so instead
the remote server directory would look like this:

        /workstuff/...
        /homestuff/...
        /manuals/...
        /armx86x64/..
        /companyreport.pdf

Which is not the greatest idea in the world, but it will work. But, how will it stash a file? Well,
a stashed file would look like this:

    \xff\x34\xe3\x23\x32\xff/companyreport.pdf
    \xff\x34\xe3\x24\x32workstuff/...
    \xff\x34\xe3\x24\x32homestuff/...
    \xff\x34\xe3\x24\x32manuals/...
    \xff\x34\xe3\x24\x32armx86x64/...

It treated the base directories like you would expect, but for the base files it prefixed them
with the directory name `\xff`. So it essentially named the directory `\xff`. 

The major point here is that it is a great idea to use `--rpath` even if you only do things like
`--rpath=dave-documents`, `--rpath=companypc-0392`, or `--rpath=serverpc-9382`. However, in order
to keep flexibility in place you can if you so desire to omit any `--rpath` but you will actually
limit future flexibility. There are times with an omitted `--rpath` can be quite useful such as
downloading/pulling the entire repository of files or other things (and along with filters).

Let us talk a moment about meta data and how it works. The meta data is really just data except
it describes one or more things about a file. The meta data support is partially implemented by
the server but only for the dir list command. Other than the directory list command the server
is completely unaware of meta data even existing. It sees each file as a sequence of bytes that
can be read and writen to. Support for meta data for the dir list command was added to increase
performance. You can implement meta data support with out using the dir list command. When the
client issues a dir list command it tells the server what directory to list and it tells it how
many bytes to read from the beginning of each file. This is as far as the server is concerned, and
really it can be used for non meta data purposes. How this is used to up to the client software.
The standard client uses it as meta data. At this time a directory has no meta data, but maybe
in the future it may. This support is entirely up to the client.

One example of meta-data is support for compression and client side encryption. Your communications
with the server is protected by SSL/TLS and how ever that is configured. However, the client may
support the ability to encrypt files locally outside of SSL/TLS in order to protect their integrity
on the server. A good example is to prevent a system administrator from prying into your files
which might contain sensitive data. If you encrypt the files with the client then they can be stored
encrypted on the server. So what does this have to do with meta data? Well, meta data can help by
allowing the client to tag this file as encrypted and even the algorithm. This can make decrypting
the files an automated process when they are downloaded/pulled from the server. The client can inspect
the meta data bytes and determine if the file is encrypted (or compressed) and reverse this process
is supplied with the proper password.

Also worth noting is that it is likely a good idea for your client to by default support at least
one byte of meta data in order to signify that further meta data exists. The standard client uses
the 7th bit of the first byte of each file to signify if valid meta data exists. Then it uses the
next 6th through 0th bits to specify the type of meta data. The standard client uses b0000000 which
is 7 zero bits for version one. _At this time this has not matured and the number of bytes following
may changes. _I think I have it set to 128 bytes of meta-data per file in the latest commit._

_So meta data is really helpful for the client where client means both software and user._

Client Side Isolated Encryption
=====
I call it client side isolated because the only place encryption or decryption ever takes place is on the client. I hope to have a decent plugin system in place to provide encryption. The standard client also supports mixing of encryption using filters. You can specify encryption using one of these two ways or both where one will override the other.

The first way is using the command line option `--def-crypt=<algorithm>,<parameters>`. This causes the standard client to look for the encryption plugin specified by algorithm. Then pass the parameters to it that are specified and encrypt any file using this.

The second way can be used in conjunction with the first way, or used alone. This way uses a filter to select the files to apply the specified encryption on. You can use this to apply more expensive encryption to more sensitive data, and at the same time apply lesser encryption or no encryption at all the some files. The filter works the same way as the filter inclusion filter. If a file match the filter that encryption with its optionions is applied to the file. An example file looks like this:

    #apple,scrypt,0,0.125,5.0,mypassword
    file        accept      .*\.doc
    file        accept      .*\.jpg
    file        accept      .*\.png
    file        accept      .*\.bmp
    file        accept      .*\.avi
    file        accept      .*\.mov
    file        accept      .*\.mpg
    #grape,scrypt,0,0.5,30.0,file:/home/dave/script.password
    path        accept      /home/dave/work
    #square,xor,file:/home/dave/xordata
    path        accept      /home/dave/pictures

The scrypt plugin handles all the options, and in the example above it supports providing
the password directly in the option or you can provide a file that contains the password. 
The password can be any sequence of bytes except `,` if provided in the filter file or it
can be any sequence of bytes if provided as a file. 

You should also notice the words `apple`, `grape`, and `square`. These tag the file to help
reassociate it with the options needed to decrypt it. The options can be considered part of
the password and therefore are not stored with the file unless specified to do so. In that
case you would not want to use non-file passwords because they would be stored along with
the file. It is up to you as to how much information you include in the tag. For example
if you are using `scrypt,mypassword,0,0.125,5.0` and you name your tag `scrypt-apple`
you have given the attacker that information. Indeed it may help you remember or determine
how to decrypt the file but it comes at a potential cost of security. I am not a cryptography
expert so it is hard for me to say just how this could turn out, but you should be aware of
how the encrypted file is tagged. This system makes your encryption filter very important
as it is the link to decrypting your files once encrypted unless you can rebuild it.

To review - when using client side encryption the server never sees the encryption key. The
entire process happens on the client. The files are stored in their encrypted state. The encryption
filter includes one or more filters that select the files to apply the specified encryption on. By
being able to apply different encryption you can use slower but highly secure algorithms on
sensitive data and faster but less secure algorithms on files that are not very sensitive.
