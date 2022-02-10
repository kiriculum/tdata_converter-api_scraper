import random
from itertools import cycle
from pathlib import Path

from scrapy import Request

proxy_queue: list = []
banned_proxies: list[str] = []
next_request: str = ''


class ProxyMiddleware:
    def __init__(self):
        self.existing_proxies: dict[int, str] = {}

    def process_request(self, request: Request, *_, **__):
        session = request.meta['cookiejar']
        if session in self.existing_proxies:
            if request.meta.get('proxy_banned', False):
                banned_proxies.append(self.existing_proxies[session])
                del self.existing_proxies[session]
            else:
                request.meta['proxy'] = self.existing_proxies[session]
                return

        new_proxy = http_proxy.get_proxy_url()
        self.existing_proxies[session] = new_proxy
        request.meta['proxy'] = new_proxy
        return

    @classmethod
    def from_crawler(cls, _):
        return cls()


class Proxy:
    def __init__(self, proxy_list):
        path = Path(proxy_list)
        if not path.exists():
            raise ValueError('Proxies list file not found', proxy_list)
        with open(path) as file:
            self.lines = file.readlines()
        if not self.lines:
            raise ValueError('No proxies in the proxy list file')
        random.shuffle(self.lines)
        self.gen = self.generator()

    def generator(self):
        if not self.lines:
            return
        for line in cycle(self.lines):
            yield line.strip().split(':')

    def get_proxy_dict(self):
        hostname, port, username, pswd = next(self.gen)
        return {'username': username, 'password': pswd, 'hostname': hostname, 'port': int(port)}

    def get_proxy_url(self):
        proxy = self.get_proxy_dict()
        cred_str = f'{proxy["username"]}:{proxy["password"]}@' if proxy['username'] else ''
        return f'http://{cred_str}{proxy["hostname"]}:{proxy["port"]}'


socks_proxy = Proxy('proxies/socks_proxy_list.csv')
http_proxy = Proxy('proxies/http_proxy_list.csv')
