import logging
import random
from dataclasses import dataclass, field
from pathlib import Path

from scrapy import Request

# provider = 'https://proxy.webshare.io/api/proxy/list/'
# token = '478e6011614b28936d6d4d5225a758772f9c5207'
proxy_queue: list = []
banned_proxies: list[str] = []
next_request: str = ''
socks_proxy_list = 'socks_proxy_list.txt'


class ProxyMiddleware:
    def __init__(self):
        self.existing_proxies: dict[int, Proxy] = {}

    def process_request(self, request: Request, *_, **__):
        session = request.meta['cookiejar']
        if session in self.existing_proxies:
            if request.meta.get('proxy_banned', False):
                banned_proxies.append(self.existing_proxies[session].proxy_address)
                del self.existing_proxies[session]
            else:
                request.meta['proxy'] = self.existing_proxies[session].get_http_string()
                return

        new_proxy = get_proxy()
        self.existing_proxies[session] = new_proxy
        request.meta['proxy'] = new_proxy.get_http_string()
        return

    @classmethod
    def from_crawler(cls, _):
        return cls()


@dataclass
class Proxy:
    username: str = ''
    password: str = ''
    proxy_address: str = ''
    ports: dict = field(default_factory={})
    valid: bool = True
    country_code: str = ''
    country_code_confidence: float = -1.0

    def get_http_string(self) -> str:
        port = self.ports.get('http', '')
        if not self.valid:
            logging.log(logging.WARNING, f'This proxy is not valid: {self}')
            return ''
        if not port:
            logging.log(logging.WARNING, f'No http port defined for this proxy: {self}')
            return ''
        cred_str = f'{self.username}:{self.password}@' if self.username else ''
        return f'http://{cred_str}{self.proxy_address}:{port}'

    @staticmethod
    def make_proxy(proxy: dict):
        return Proxy(username=proxy.get('username', ''),
                     password=proxy.get('password', ''),
                     proxy_address=proxy.get('proxy_address', ''),
                     ports=proxy.get('ports', {'http': 80}),
                     valid=proxy.get('valid', True),
                     country_code=proxy.get('country_code', ''),
                     country_code_confidence=proxy.get('country_code_confidence', -1))


# def fetch_proxies():
#     global next_request
#     if not next_request:
#         resp = requests.get(url=provider, headers={'Authorization': token})
#     else:
#         resp = requests.get(url=next_request, headers={'Authorization': token})
#     if resp.status_code != 200:
#         raise ValueError('Got bad response from proxy provider')
#     result = resp.json()
#     proxies = result.get('results', [])
#     next_request = result.get('next', '')
#     if proxies:
#         return proxies
#     else:
#         raise ValueError('Got empty proxy list from provider')

def fetch_proxies():
    if hasattr(fetch_proxies, 'count'):
        count = fetch_proxies.count
        if count > 50:
            count = 0
    else:
        count = 0
    fetch_proxies.count = count + 1
    proxies = [{
        'username': 'user-kiriltest1',
        'password': 'b5650e39',
        'proxy_address': 'gate.dc.smartproxy.com',
        'ports': {'http': 20001 + x},
        'valid': True,
        'country_code': ''
    } for x in range(count * 100, (count + 1) * 100)]
    random.shuffle(proxies)
    return proxies


def get_proxy() -> Proxy:
    if not proxy_queue:
        try:
            proxies = list(filter(lambda x: x['proxy_address'] not in banned_proxies, fetch_proxies()))
            if not proxies:
                raise ValueError('All returned proxies are banned')
            proxy_queue.extend(proxies)
        except ValueError as e:
            logging.log(logging.ERROR, str(e))
            return Proxy()
    return Proxy.make_proxy(proxy_queue.pop(0))


class SocksProxy:
    path = Path(socks_proxy_list)
    if not path.exists():
        raise AttributeError('Proxies list file not found', socks_proxy_list)
    with open(path) as file:
        lines = file.readlines()
        random.shuffle(lines)
    if not lines:
        raise ValueError('No proxies in the proxy list file')
    gen = None

    @classmethod
    def generator(cls):
        if not cls.lines:
            raise GeneratorExit
        for line in cls.lines:
            line = line.strip()
            # if '@' in line:
            #     userinfo, path = line.split('@')
            #     username, pswd = userinfo.split(':')
            #     hostname, port = path.split(':')
            #     yield username, pswd, hostname, int(port)
            # proxy = line.strip().split(':')
            # yield '', '', proxy[0], int(proxy[1])
            yield line.split(':')
        yield from cls.generator()

    @classmethod
    def get_proxy(cls):
        # return {}
        if not cls.gen:
            cls.gen = cls.generator()
        hostname, port, username, pswd = next(cls.gen)

        return {'username': username, 'password': pswd, 'hostname': hostname, 'port': int(port)}
