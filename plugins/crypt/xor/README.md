This implements the XOR operation to try to encrypt data. This
algorithm can be very insecure and is mainly included for light
security, or a reference implementation for a developer.

If you use this for light security your key length directly effects
the level of security. You should if possible use a key file containing
random data. Also, the more files the same key is applied the easier
it can be for the attacker to deduce the key. Also, long series of
zeros in file data or such can reveal the key especially if the attacker
can deduce that these are zeros.

Ultimately any data the attacker can guess will reveal that part of the key
which is enough is revealed will yeild the entire key eventually. So this
algorithm is really very insecure and should only be used to prevent casual
browsing of the data because it will require someone with technical knowledge
more than likely to reverse it.

_If you use it then keep in mind it only helps to prevent your common user
from reading the data. It will not prevent someone with the knowledge and
skills from recovering not only the data but also the key._

_Do not use this key for XOR and use the same key for other algorithms as
if an attacker recovers this key he could use it for the key to your other
algorithsm._