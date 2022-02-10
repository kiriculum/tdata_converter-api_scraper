import asyncio

from scrapy.crawler import CrawlerProcess

from converter import converter
from telegram_spider import TelegramApiScraper


def main():
    intro = '''Welcome to telegram api id/hash scraper tool.
Choose method:
1 - Mass convert(extract) tdata folders to .session files (without user checking)
2 - Scrape api id/hashes for existing .session files
3 - Exit'''
    print(intro)

    menu = input()
    if not menu.isdigit():
        print('Bad input')
        return
    match menu:
        case '1':
            asyncio.run(converter.main())
            return
        case '2':
            process = CrawlerProcess(settings={'LOG_LEVEL': 'WARNING'})
            process.crawl(TelegramApiScraper)
            process.start()
            return
        case '3':
            return


if __name__ == '__main__':
    main()
