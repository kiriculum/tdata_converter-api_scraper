import asyncio
import hashlib
import io
import json
import logging
import os
from itertools import chain
from pathlib import Path
from typing import BinaryIO

import pyrogram
import tgcrypto
from pyrogram.errors import UserMigrate, RPCError

from converter.consts import *
from converter.tools import *
from proxy import socks_proxy

FILEOPTION_SAFE = 1
FILEOPTION_USER = 2
CONSOLIDATE = True
device_model = 'Sony Xperia 1'
app_version = 'BGram 1.9'
system_version = 'Android 10.2'

with open('config.json', 'r') as file_config:
    try:
        config = json.load(file_config)
        main_api_id = config.get('api_id', None)
        main_api_hash = config.get('api_hash', '')
        password = config.get('2fa_password', '')
        hint = config.get('password_hint', '')
        email = config.get('email', None)
    except json.decoder.JSONDecodeError:
        raise AttributeError('No config.json file or bad format')


def telegram_md5(data: str):
    md5_hash = hashlib.md5(data.encode()).hexdigest()
    return ''.join(chain(*map(reversed, zip(*[iter(md5_hash)] * 2))))


def tdesktop_read_bytearray(file: BinaryIO, as_string: bool = False):
    length = unpack_signed_int(bytes(reversed(file.read(4))))
    logging.debug(f'bytes length is {length}')
    data = file.read(length) if length > 0 else b''
    if as_string:
        return data
    else:
        return io.BytesIO(data)


def tdesktop_decrypt(data: BinaryIO, auth_key):
    message_key = data.read(16)
    encrypted_data = data.read()

    aes_key, aes_iv = old_aes_calculate(message_key, auth_key, False)
    decrypted_data = tgcrypto.ige256_decrypt(encrypted_data, aes_key, aes_iv)

    if message_key != hashlib.sha1(decrypted_data).digest()[:16]:
        raise Exception(f'Message key does not match, {message_key} != {hashlib.sha1(decrypted_data).digest()[:16]}')
    return io.BytesIO(decrypted_data)


def tdesktop(path: Path, settings: dict):
    def tdesktop_fopen(filename: str, options: int = FILEOPTION_SAFE | FILEOPTION_USER):
        base_path = tdesktop_user_base_path if options & FILEOPTION_USER else tdesktop_base_path
        totry = []
        for x in ['0', '1', 's']:
            if base_path.joinpath(filename + x).exists():
                totry.append(open(base_path.joinpath(filename + x), 'rb'))
        for file in totry:
            temp = file.read(4)
            if temp != b'TDF$':
                logging.error(f'Wrong magic word, got {temp}')
                continue
            version_bytes = file.read(4)
            version = unpack_signed_int(version_bytes, True)
            logging.debug(f'Version {version}')
            local_data = file.read()
            md5 = local_data[-16:]
            local_data = local_data[:-16]
            length = len(local_data).to_bytes(4, 'little', signed=True)
            calc_md5 = hashlib.md5(b''.join([local_data, length, version_bytes, b'TDF$'])).digest()[:16]
            if calc_md5 != md5:
                logging.error(f'Md5 does not match, {calc_md5} != {md5}')

            return io.BytesIO(local_data)
        raise Exception(f'Could not open {filename}')

    def tdesktop_fopen_encrypted(filename: str, options: int = 3):
        file = tdesktop_fopen(filename, options)
        local_data = tdesktop_read_bytearray(file)
        res = tdesktop_decrypt(local_data, tdesktop_key)
        res_length = len(res.read())
        res.seek(0)
        length = unpack_signed_int(res.read(4), True)

        if length > res_length or length < 4:
            raise Exception('Wrong length')

        return res

    def from_serialized(hash_filename: str):
        main_stream = tdesktop_fopen_encrypted(hash_filename, FILEOPTION_SAFE)
        auth_keys = {}
        user_id = None
        main_dc_id = b''

        for magic in iter(lambda: bytes(reversed(main_stream.read(4))), b''):
            magic = unpack_signed_int(magic)
            if magic == [dbiDcOptionOldOld]:
                main_stream.read(4)
                tdesktop_read_bytearray(main_stream)
                tdesktop_read_bytearray(main_stream)
                main_stream.read(4)
            elif magic == dbiDcOptionOld:
                main_stream.read(8)
                tdesktop_read_bytearray(main_stream)
                main_stream.read(4)
            elif magic == dbiDcOptions:
                tdesktop_read_bytearray(main_stream)
            elif magic == dbiUser:
                main_stream.read(4)
                main_dc_id = unpack_signed_int(bytes(reversed(main_stream.read(4))))
            elif magic == dbiKey:
                auth_keys[unpack_signed_int(bytes(reversed(main_stream.read(4))))] = main_stream.read(256)
            elif magic == dbiMtpAuthorization:
                temp = tdesktop_read_bytearray(main_stream)
                # main.read(4)
                legacy_user_id = unpack_signed_int(bytes(reversed(temp.read(4))))
                legacy_main_dc_id = unpack_signed_int(bytes(reversed(temp.read(4))))
                if legacy_user_id == legacy_main_dc_id == (-1 << 31) + 1:
                    user_id = unpack_signed_long_int(bytes(reversed(temp.read(8))))
                    main_dc_id = unpack_signed_int(bytes(reversed(temp.read(4))))
                else:
                    user_id = legacy_user_id
                    main_dc_id = legacy_main_dc_id
                length = unpack_signed_int(bytes(reversed(temp.read(4))))
                for x in range(length):
                    dc = unpack_signed_int(bytes(reversed(temp.read(4))))
                    auth_key = temp.read(256)
                    if dc <= 5:
                        auth_keys[dc] = auth_key
                return {'user_id': user_id, 'data': [auth_keys, main_dc_id]}
            elif magic == dbiAutoDownload:
                main_stream.read(12)
            elif magic == dbiDialogsMode:
                main_stream.read(8)
            elif magic == dbiAuthSessionSettings:
                tdesktop_read_bytearray(main_stream)
            elif magic == dbiConnectionTypeOld:
                res = unpack_signed_int(bytes(reversed(main_stream.read(4))))
                if res == 3:
                    tdesktop_read_bytearray(main_stream)
                    main_stream.read(4)
                    tdesktop_read_bytearray(main_stream)
                    tdesktop_read_bytearray(main_stream)
            elif magic == dbiConnectionType:
                main_stream.read(8)

                tdesktop_read_bytearray(main_stream)
                main_stream.read(4)
                tdesktop_read_bytearray(main_stream)
                tdesktop_read_bytearray(main_stream)

            elif magic == dbiThemeKey:
                pass
            elif magic == dbiLangPackKey:
                pass
            elif magic == dbiMutePeer:
                main_stream.read(8)
            elif magic == dbiWindowPosition:
                main_stream.read(24)
            elif magic == dbiLoggedPhoneNumber:
                tdesktop_read_bytearray(main_stream)
            elif magic == dbiMutedPeers:
                length = unpack_signed_int(bytes(reversed(main_stream.read(4))))
                for x in range(length):
                    main_stream.read(8)
            elif magic == dbiDownloadPathOld:
                tdesktop_read_bytearray(main_stream)
            elif magic == dbiDialogLastPath:
                tdesktop_read_bytearray(main_stream)
            elif magic == dbiDownloadPath:
                tdesktop_read_bytearray(main_stream)
                tdesktop_read_bytearray(main_stream)
            else:
                raise Exception(f"Unknown type {magic}")

        if user_id:
            return {'user_id': user_id, 'data': [auth_keys, main_dc_id]}
        else:
            return None

    settings.setdefault('old_session_key', 'data')
    settings.setdefault('old_session_passcode', '')

    if not path.exists():
        raise Exception('Session does not exist')
    if path.parts[-1] != 'tdata':
        path /= 'tdata'

    part_one_md5 = telegram_md5(settings['old_session_key'])[:16]

    tdesktop_base_path = path
    tdesktop_user_base_path = path / part_one_md5

    data = tdesktop_fopen('map')

    salt = tdesktop_read_bytearray(data, True)
    encrypted_key = tdesktop_read_bytearray(data)

    if len(salt):
        key_iter_count = 4000 if len(settings['old_session_passcode']) else 4

        passkey = hashlib.pbkdf2_hmac('sha1', settings['old_session_passcode'].encode(), salt, key_iter_count, 256)

        tdesktop_key = tdesktop_read_bytearray(tdesktop_decrypt(encrypted_key, passkey))
    else:
        key = 'key_' + settings['old_session_key']
        data = tdesktop_fopen(key, FILEOPTION_SAFE)

        salt = tdesktop_read_bytearray(data, True)
        if len(salt) != 32:
            raise Exception('Bad salt length')

        enc_key = tdesktop_read_bytearray(data)
        enc_info = tdesktop_read_bytearray(data)

        res_hash = hashlib.sha512(salt + settings['old_session_passcode'].encode() + salt).digest()
        iter_count = 100000 if len(settings['old_session_passcode']) else 1

        passkey = hashlib.pbkdf2_hmac('sha512', res_hash, salt, iter_count, 256)

        key = tdesktop_read_bytearray(tdesktop_decrypt(enc_key, passkey), True)
        info = tdesktop_read_bytearray(tdesktop_decrypt(enc_info, key))

        tdesktop_key = key

        count = unpack_signed_int(bytes(reversed(info.read(4))))
        logging.info(f'Tdata contains number of accounts: {count}')
        if count > 0:
            users = [from_serialized(part_one_md5)]
            for user in range(2, count + 1):
                next_session = telegram_md5(settings['old_session_key'] + f'#{user}')[:16]
                data = from_serialized(next_session)
                users.append(data) if data else None
            return users
        else:
            return []


async def convert(path: Path):
    try:
        users = tdesktop(path, dict())
        if not users:
            print(f'No user sessions were extracted from {path}')
            return
        for ind, user in enumerate(users):
            user_id = user['user_id']
            keys = user['data'][0]
            main_dc_id = user['data'][1]
            dc_id = main_dc_id if main_dc_id in keys else \
                2 if 2 in keys else next(iter(keys))
            workdir = Path('output_sessions')
            session_name = f'session_{path.parts[-1]}_{user_id}'
            if not CONSOLIDATE:
                workdir = workdir / path.parts[-1]
                session_name = f'session__{path.parts[-1]}_{ind + 1}_{user_id}'
            workdir.mkdir(parents=True, exist_ok=True)

            client = pyrogram.Client(session_name, workdir=str(workdir), proxy=socks_proxy.get_proxy_dict(),
                                     api_id=main_api_id, api_hash=main_api_hash, device_model=device_model,
                                     system_version=system_version, app_version=app_version)
            client.load_config()
            await client.load_session()

            await client.storage.dc_id(dc_id)
            await client.storage.auth_key(keys[dc_id])
            await client.storage.user_id(user_id)
            await client.storage.is_bot(False)
            try:
                await client.start()
            # Catches Migrate tg event to switch to another DC and save corresponding auth key
            except UserMigrate as e:
                await client.load_session()
                await client.storage.dc_id(e.x)
                await client.storage.auth_key(keys[e.x])
                try:
                    await client.start()
                except (OSError, TimeoutError, RPCError) as e:
                    print(f'Error after UserMigrate - {e}, {client.session_name}')
                    os.remove(workdir / f'{session_name}.session')
                    continue
            except (OSError, TimeoutError, RPCError) as e:
                print(f'Got bad client - {e}, {session_name}')
                os.remove(workdir / f'{session_name}.session')
                continue
            try:
                if password:
                    await client.enable_cloud_password(password, hint, email)
            except ValueError:
                print(f'Could not set 2fa for client {session_name} - password is already set')

    except Exception as e:
        print(f'Error: {e}, in {path}')


async def main():
    root_path = Path(input(r'Enter address of a folder with tdatas collection (Ex. C:\Documents\tdatas): '))
    if root_path == Path():
        print('Error: bad input')
        return
    if not root_path.exists():
        print('Error: folder not found')
        return
    for ind, folder in enumerate(root_path.iterdir()):
        if folder.is_dir():
            await convert(folder)
        if ind and ind % 25 == 0:
            print(f'Processed {ind} folders')


if __name__ == '__main__':
    asyncio.run(main())
