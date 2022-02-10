from hashlib import sha1, sha256


def unpack_signed_int(string: bytes, little_endian=True):
    if len(string) != 4:
        raise ValueError
    if little_endian:
        string = reversed(string)
    res = 0
    mask = (1 << 31) - 1
    for char in string:
        res = (res << 8) | char
    return -(res & mask) if res >> 31 else res & mask


def unpack_signed_long_int(string: bytes, little_endian=True):
    if len(string) != 8:
        raise ValueError
    if little_endian:
        string = reversed(string)
    res = 0
    mask = (1 << 63) - 1
    for char in string:
        res = (res << 8) | char
    return -(res & mask) if res >> 63 else res & mask


def old_aes_calculate(msg_key: bytes, auth_key: bytes, to_server: bool = True):
    x = 0 if to_server else 8
    sha1_a = sha1(msg_key + auth_key[x:x + 32]).digest()
    sha1_b = sha1(auth_key[x + 32:x + 48] + msg_key + auth_key[x + 48:x + 64]).digest()
    sha1_c = sha1(auth_key[x + 64:x + 96] + msg_key).digest()
    sha1_d = sha1(msg_key + auth_key[x + 96:x + 128]).digest()
    aes_key = sha1_a[:8] + sha1_b[8:20] + sha1_c[4:16]
    aes_iv = sha1_a[8:20] + sha1_b[:8] + sha1_c[16:20] + sha1_d[:8]
    return aes_key, aes_iv


def aes_calculate(msg_key: bytes, auth_key: bytes, to_server: bool = True):
    x = 0 if to_server else 8
    sha256_a = sha256(msg_key + auth_key[x:x + 36]).digest()
    sha256_b = sha256(auth_key[x + 40:x + 76] + msg_key).digest()

    aes_key = sha256_a[:8] + sha256_b[8:24] + sha256_a[24:32]
    aes_iv = sha256_b[:8] + sha256_a[8:24] + sha256_b[24:32]
    return aes_key, aes_iv
