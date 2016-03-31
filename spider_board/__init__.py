from urllib.parse import urljoin
import sys
import base64
import re
import requests
from bs4 import BeautifulSoup
import logging
import os
from collections import namedtuple
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, wait


LOG_FILE = os.path.abspath('scraper_log.log')

# Create the logging handlers and attach them
logger = logging.getLogger(__name__)

stream_handler = logging.StreamHandler()

file_handler = logging.FileHandler(LOG_FILE)
formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s: %(message)s",
        datefmt='%Y/%m/%d %I:%M:%S %p')

file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

logger.setLevel(logging.DEBUG)


Attachment = namedtuple('Attachment', ['title', 'url'])


class Section:
    def __init__(self, unit, title, url):
        self.unit = unit
        self.title = title
        self.url = url

    def __repr__(self):
        return '<Section: {}>'.format(self.title)

class Unit:
    def __init__(self, name, url, code):
        self.code = code
        self.url = url.strip()
        self.name = name
        self.sections = Queue()
        self.documents = Queue()

    def __repr__(self):
        return '<Unit: name="{}">'.format(self.name)
        

class Browser:
    SKIP_FOLDERS = [
            'Discussion Board',
            'Contacts',
            'Tools',
            'iPortfolio',
            'Communication',
            'Announcements',
            'My Grades',
            'Help for Students',
            ]

    def __init__(self, username, password, blackboard_url=None):
        logger.info('Initiating')

        self.blackboard_url = blackboard_url or 'https://lms.curtin.edu.au/'
        self.login_url = self.blackboard_url + 'webapps/login/'

        self.username = username
        self.password = base64.b64encode(password.encode('utf-8')) 
        self.b = requests.session() 
        self.units = []

        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        self.futures = []

    def login(self):
        logger.info('Logging in')
        payload = {
                'login': 'Login',
                'action': 'login',
                'user_id': self.username,
                'encoded_pw': self.password,
                }

        # Do the login
        r = self.b.post(self.login_url, data=payload)

        if 'You are being redirected to another page' in r.text:
            logger.info('Login was successful')
        else:
            logger.error('Login failed')
            self.quit()

    def get_units(self):
        url = self.blackboard_url + 'webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_3_1'

        r = self.b.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')

        course_links = []
        for link in soup.find_all('a'):
            # Because Blackboard is shit, you need to do a hack in order to
            # find all unit names
            href = link.get('href')
            course = re.search(r'\?type=Course&id=_(.*)_1&url', href)

            if course is None:
                continue
            else:
                name = link.text
                code = course.group(1)
                l = urljoin(self.blackboard_url, href.strip()) 

                new_unit = Unit(name=name, url=l, code=code)
                logger.debug('Unit found: {}'.format(new_unit))

                self.units.append(new_unit)

    def _scrape_unit(self, unit):
        logger.info('Scraping all documents for unit: {}'.format(unit))
        
        r = self.b.get(unit.url)
        soup = BeautifulSoup(r.text, 'html.parser')

        sidebar = soup.find(id='courseMenuPalette_contents')
        links = sidebar.find_all('a')

        for link in links:
            title = link.span['title']
            
            if title in Browser.SKIP_FOLDERS:
                continue

            # Skip ilectures
            if 'echo' in title.lower():
                continue

            link = urljoin(self.blackboard_url, link['href'])
            new_section = Section(unit, title, link)
            logger.debug('Adding section: {}'.format(new_section))
            unit.sections.put(new_section)

    def _scrape_section(self, section):
        logger.info('Scraping section: {}'.format(section))

        r = self.b.get(section.url)
        soup = BeautifulSoup(r.text, 'html.parser')

        section_files = self._files_in_section(soup)

        for f in section_files:
            section.unit.documents.put(f)
            
        # Find any folders that may be in this one
        items = container.find_all(class_='item')

    def _files_in_section(self, soup):
        container = soup.find(id='containerdiv')

        files = container.find_all(alt='File')

        # Check if there are any documents in this folder
        attached_files = container.find_all(class_='attachments')

        file_list = []
        for attachment_list in attached_files:
            attachments = attachment_list.find_all('a')

            for attachment in attachments:
                url = urljoin(self.blackboard_url, attachment['href'])
                title = attachment.text.strip()
                new_attachment = Attachment(title, url)

                logger.debug('File discovered: {}'.format(title))
                file_list.append(new_attachment)

        return file_list


    def find_documents(self, unit):
        # Get the initial folders to check
        self._scrape_unit(unit)

        while not unit.sections.empty():
            section = unit.sections.get()

            # Tell the thread pool to scrape that section
            fut = self.thread_pool.submit(self._scrape_section, section)
            self.futures.append(fut)

    def start(self):
        self.login()
        self.get_units()

        for unit in self.units:
            if '[' not in unit.name:
                self.find_documents(unit)

        wait(self.futures)


    def quit(self):
        sys.exit(1)

