import csv
import hashlib
import json
import logging
import pathlib
import random
import re
import time
from pathlib import Path

import pyrogram
import scrapy
from itemadapter import ItemAdapter
from pyrogram import Client
from pyrogram.errors.exceptions import RPCError
from scrapy.dupefilters import BaseDupeFilter
from scrapy.http import FormRequest, Request
from scrapy.http.response import Response

import proxy

tg_base_link = 'https://my.telegram.org'
app_title_nouns = ['client', 'testbot', 'soft', 'piece of sw', 'software', 'idea', 'project', 'work', 'crap']
app_title_adjs = ['cool', 'testing', 'test', 'little', 'nice', 'user', 'practice', 'pure', 'api', 'useful', 'bright',
                  '']
app_title_pronouns = ['my', 'our', 'My', 'Our', "Mike's", 'Adam', 'QC', 'ro', '', '']
app_title_adverbs = ['just', 'quite', '', '']
app_title_parts = [app_title_adverbs, app_title_pronouns, app_title_adjs, app_title_nouns]


def make_title():
    def get_part(parts: list, min_count: int, max_count: int):
        rnd_count = random.randint(min_count, max_count)
        return random.choices(parts, k=rnd_count)

    title = []
    title.extend(get_part(app_title_adverbs, 0, 1))
    title.extend(get_part(app_title_pronouns, 1, 1))
    title.extend(get_part(app_title_adjs, 1, 2))
    title.extend(get_part(app_title_nouns, 1, 1))
    return ' '.join(title).strip().replace('  ', ' ').replace('  ', ' ')


class UserData(scrapy.Item):
    ordered_fields = ['phone', 'app_id', 'app_hash', 'title', 'shortname']
    client = scrapy.Field()
    phone = scrapy.Field()
    app_id = scrapy.Field()
    app_hash = scrapy.Field()
    title = scrapy.Field()
    shortname = scrapy.Field()


DOWNLOADER_MIDDLEWARES = {proxy.ProxyMiddleware: 200}


class TelegramApiScraper(scrapy.Spider):
    name = 'my.telegram'
    base_url = tg_base_link
    custom_settings = {'DUPEFILTER_CLASS': BaseDupeFilter,
                       'CONCURRENT_REQUESTS': 1,
                       'DOWNLOADER_MIDDLEWARES': DOWNLOADER_MIDDLEWARES}

    curr_users: list[UserData] = []
    curr_count = 0
    password = None
    main_api_id = None
    main_api_hash = None
    filename = ''
    file = None
    writer = None
    sessions: list[Path] = []

    get_headers = {
        b'Accept': [b'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'],
        b'Accept-Language': [b'en'],
        b'User-Agent': [b'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0'],
        b'Accept-Encoding': [b'gzip, deflate'],
        b'DNT': 1}

    post_headers = {b'Content-Type': [b'application/x-www-form-urlencoded; charset=UTF-8'],
                    b'Accept': [b'application/json, text/javascript, */*; q=0.01'],
                    b'Accept-Language': [b'en'],
                    b'User-Agent': [b'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0'],
                    b'Accept-Encoding': [b'gzip, deflate'],
                    b'DNT': 1}

    def open_spider(self):
        sub_folder = pathlib.Path('output_data')
        sub_folder.mkdir(exist_ok=True)
        self.filename = f'output_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}.csv'
        self.file = open(sub_folder / self.filename, 'w', newline='')
        self.writer = csv.writer(self.file)
        self.writer.writerow(UserData.ordered_fields)

    def close_spider(self):
        self.file.close()

    def process_item(self, item: scrapy.item.Item):
        adapter = ItemAdapter(item)
        self.writer.writerow([adapter.get(x, '') for x in UserData.ordered_fields])

    def start_requests(self):
        with open('config.json', 'a+') as file_config:
            try:
                file_config.seek(0)
                config = json.load(file_config)
                self.main_api_id = config.get('api_id', None)
                self.main_api_hash = config.get('api_hash', '')
                print(f'ID/HASH - {self.main_api_id}, {self.main_api_hash}')
            except json.decoder.JSONDecodeError:
                print('No config.json file or bad format')
                return []
        if not (self.main_api_id and self.main_api_hash):
            print('No master api_id or api_hash found in config.json file')
            return []
        root_path = Path(input(r'Enter address of a folder with .session file (Ex. C:\Documents\sessions): '))
        if root_path == Path():
            print('Error: bad input')
            return []
        if not root_path.exists():
            print('Error: folder not found')
            return []
        for file in root_path.iterdir():
            if file.is_file() and str(file).endswith('.session'):
                self.sessions.append(file)
            else:
                continue
        if not self.sessions:
            print(f'No session files found, stopping')
            return []
        self.open_spider()
        request = self.my_start()
        return [request] if request else []

    def my_start(self, last=None):
        if last:
            self.curr_users[last]['client'].stop()
        while self.sessions:
            file = self.sessions.pop()
            client = pyrogram.Client(file.parts[-1].rstrip('.session'), api_id=self.main_api_id,
                                     proxy=proxy.SocksProxy.get_proxy(),
                                     api_hash=self.main_api_hash, workdir=str(file.parent))
            try:
                client.start()
            except (OSError, TimeoutError, RPCError) as e:
                print(f'Got bad client - {e}, {client.session_name}')
                continue

            self.curr_users.append(UserData())
            self.curr_users[len(self.curr_users) - 1]['client'] = client
            print(f'Processing {len(self.curr_users)} session file')

            return Request(self.base_url, headers=self.get_headers,
                           meta={'cookiejar': len(self.curr_users) - 1})
        else:
            self.close_spider()

    def receive_code(self, message):
        search = re.search(r':\s(\w{9,11})\s\s', message.text)
        if search:
            code = search.groups()[0]
        else:
            code = None
        self.password = code
        print(f'Got verification code: {code}')

    def parse(self, response: Response, **kwargs):
        if 'auth' in response.url:
            return self.send_code(response)
        elif response.url.endswith(tg_base_link):
            return response.follow('/apps', callback=self.open_apps,
                                   meta={'cookiejar': response.meta['cookiejar']})

    def send_code(self, response: Response):
        user_num = response.meta['cookiejar']
        client = self.curr_users[user_num]['client']
        me = client.get_me()
        phone = me.phone_number
        if not phone:
            return self.my_start(user_num)
        else:
            phone = '+' + phone
        self.curr_users[user_num]['phone'] = phone
        return FormRequest(tg_base_link + '/auth/send_password',
                           meta={'cookiejar': user_num},
                           formdata={'phone': phone}, callback=self.auth_user, headers=self.post_headers)

    async def auth_user(self, response: Response):
        if isinstance(response, scrapy.http.TextResponse):
            user_num = response.meta['cookiejar']
            client: Client = self.curr_users[user_num]['client']
            history = await client.get_history(chat_id=777000, limit=1)
            if not history:
                print('Got 0 messages from Telegram chat')
                return self.my_start(user_num)
            try:
                random_hash = response.json().get('random_hash', '')
            except json.decoder.JSONDecodeError:
                print(f'Got bad response')
                return self.my_start(user_num)
            if not random_hash:
                print('Bad response from telegram for "send_password" request')
                return self.my_start(user_num)
            self.receive_code(history[0])
            password = self.password
            print(f'got password {password}')
            if not password:
                return self.my_start(user_num)
            user_num = response.meta['cookiejar']
            return FormRequest(tg_base_link + '/auth/login', headers=self.post_headers,
                               meta={'cookiejar': response.meta['cookiejar']},
                               formdata={
                                   'phone': self.curr_users[user_num].get('phone'),
                                   'random_hash': random_hash,
                                   'password': password
                               }, callback=self.finish_auth)
        else:
            print(f'Got bad response')
            return self.my_start(response.meta['cookiejar'])

    def finish_auth(self, response: Response):
        user_num = response.meta['cookiejar']
        if isinstance(response, scrapy.http.TextResponse):
            if response.text == 'true':
                return Request(tg_base_link, headers=self.get_headers, meta={'cookiejar': response.meta['cookiejar']})
        print(f'Could not finish auth for {self.curr_users[user_num]}')
        return self.my_start(user_num)

    def open_apps(self, response: Response):
        user_num = response.meta['cookiejar']
        if 'app configuration' in response.css('title::text').get().lower():
            return self.fetch_data(response)
        elif 'new application' in response.css('title::text').get().lower():
            return self.register_app(response)
        else:
            print(f'Could not scrape data for {self.curr_users[user_num]}')

    def register_app(self, response: Response):
        hidden_hash = response.css('input[name=hash]::attr(value)').get().strip()
        title = make_title()
        if len(title) < 6:
            title += str(random.randint(10, 99))
        shortname = title.lower().replace("'", '')
        if 5 < len(shortname) or random.randint(0, 12) < 2:
            shortname += random.choice(['7', '777', '69', '42', '1999', '2000', '1', '2', '3'])
        if len(shortname) > 32:
            shortname = shortname[0:32]

        data = {'hash': hidden_hash,
                'app_title': title,
                'app_shortname': shortname,
                'app_url': random.choice(['no url', 'none', 'no', 'None']),
                'app_platform': 'desktop',
                'app_desc': ''}
        return FormRequest(tg_base_link + '/apps/create', meta={'cookiejar': response.meta['cookiejar']},
                           callback=self.finish_register, headers=self.post_headers, formdata=data)

    def finish_register(self, response: Response):
        user_num = response.meta['cookiejar']
        if isinstance(response, scrapy.http.TextResponse):
            if not response.text:
                return Request(tg_base_link + '/apps', meta={'cookiejar': user_num},
                               callback=self.open_apps, headers=self.get_headers)
            else:
                print(f'Could not finish app register, response not empty: {response.text}')
                print(f'Probably your proxy was banned', logging.ERROR)
                print(f'Query data was: {response.request.body}')
                return Request(tg_base_link + '/auth/logout',
                               headers=self.get_headers, meta={'cookiejar': user_num,
                                                               'proxy_banned': True})
                # return self.my_start()
        print(f'Could not finish app register: {str(response.body)}')
        return self.my_start(user_num)

    def fetch_data(self, response: Response):
        user_num = response.meta['cookiejar']
        self.curr_users[user_num]['app_id'] = response.css('label[for=app_id] ~ div > span > strong::text').get()
        self.curr_users[user_num]['app_hash'] = response.css('label[for=app_hash] ~ div > span::text').get()
        self.curr_users[user_num]['title'] = response.css('label[for=app_title] ~ div > input::attr(value)').get()
        self.curr_users[user_num]['shortname'] = response.css(
            'label[for=app_shortname] ~ div > input::attr(value)').get()
        print(f'scraped user data: {self.curr_users[user_num]}')
        self.process_item(self.curr_users[user_num])
        return self.my_start(user_num)
