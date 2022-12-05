# Two-way tool to work with Telegram user sessions:

## Tdata converter

Works through a bunch of tdata folders (one is usually generated by Telegram Desktop)
retrieving stored user authentication settings to create .session files (Pyrogram/Telethon client auth) for each user.
Tdata may contain several logged in accounts, each one would be converted.

On conversion .session is tested for connection and authentication to Telegram servers,
new DataCenter id is set if Client Migration event arrives and optionally password for 2fa is being set.
It also means that you would need a valid `api_id` and `api_hash` in config.json for such checks.
Leave `2fa_password` empty to skip setting a password.

Tdata client's auth data is encrypted but since [Telegram Desktop](https://github.com/telegramdesktop/tdesktop)
is open source it's possible to collect and decrypt important things to make fully authenticated .session files.
[MadelineProto Converter](https://github.com/danog/MadelineProto/blob/stable/src/danog/MadelineProto/Conversion.php)
helped a lot to make this tool and is referenced a lot.

## API_ID, API_HASH collector

The tool is used to automatically register telegram apps on [my.telegram.org]() with authenticated client .session files
and collect corresponding api_id, api_hash pairs. Based on Scrapy spiders with semi-random fields filling.

### Proxying

For both tools you would need to provide a list of proxies to make it work (It doesn't have a chance without proxying).
Socks proxies are required for *Tdata Converter*, http proxies are for *API_ID, API_HASH collector*. Round Robin is used
to rotate proxies from the lists.