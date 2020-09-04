# -*- coding:UTF-8 -*-
import time
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.header import Header
from school_api import SchoolClient
from retry import retry
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR
from configparser import ConfigParser


class Bot:
    def __init__(self, from_addr, auth_code, to_addr, smtp_server):
        self.from_addr = from_addr
        self.auth_code = auth_code
        self.to_addr = to_addr
        self.smtp_server = smtp_server
        self.msg = None

    def set_email(self, title, content):
        self.msg = MIMEText(u'%s\n\n%s' % (content, time.strftime('%Y-%m-%d %H:%M:%S %A', time.localtime())), 'plain',
                            'utf-8')
        self.msg['From'] = Header(self.from_addr)
        self.msg['To'] = Header(self.to_addr)
        self.msg['Subject'] = Header(title)

    def send_email(self):
        # 开启发信服务，这里使用的是加密传输
        server = smtplib.SMTP_SSL(host=self.smtp_server)
        server.connect(host=self.smtp_server, port=465)  # SMTP服务器端口号
        server.login(self.from_addr, self.auth_code)
        server.sendmail(self.from_addr, self.to_addr, self.msg.as_string())
        self.msg = None
        server.quit()


config = ConfigParser()
config.read('config.conf')
USERNAME = config['DEFAULT']['USERNAME']
PASSWORD = config['DEFAULT']['PASSWORD']
ZHENGFANG_URL = config['DEFAULT']['ZHENGFANG_URL']
CURRENT_YEAR = config['DEFAULT']['CURRENT_YEAR']
CURRENT_TERM = config['DEFAULT']['CURRENT_TERM']
FROM_ADDR = config['DEFAULT']['FROM_ADDR']
AUTH_CODE = config['DEFAULT']['AUTH_CODE']
TO_ADDR = config['DEFAULT']['TO_ADDR']
SMTP_SERVER = config['DEFAULT']['SMTP_SERVER']
SEC_INTERVAL = config['DEFAULT']['SEC_INTERVAL']
MEMBERS = list(map(str.strip, config['GROUP']['MEMBERS'].split(',')))

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s-%(name)s-%(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    filename=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'error.log')
                    )
rootLogger = logging.getLogger()

bot = Bot(from_addr=FROM_ADDR, auth_code=AUTH_CODE, to_addr=TO_ADDR, smtp_server=SMTP_SERVER)
school = SchoolClient(url=ZHENGFANG_URL)
user = school.user_login(USERNAME, PASSWORD)
total_lesson = []  # [{'lesson_name': '创业与投融资', 'credit': 2.0, 'point': 4.0, 'score': 90.0}]


def send_to_members(title, content):
    for add in MEMBERS:
        member_bot = Bot(from_addr=FROM_ADDR, auth_code=AUTH_CODE, to_addr=add, smtp_server=SMTP_SERVER)
        member_bot.set_email(title=title, content=content)
        member_bot.send_email()


def err_listener(ev):
    err_title, err_content = u'【期末】程序异常！', str(ev.exception) + '\n' + str(ev.traceback)
    bot.set_email(title=err_title, content=err_content)
    bot.send_email()


@retry(Exception, tries=10, delay=5, backoff=2, max_delay=60)
def main():
    global school, user, total_lesson
    try:
        score_data = user.get_score()
        lesson = score_data[CURRENT_YEAR][CURRENT_TERM]
        if not total_lesson:
            total_lesson = lesson
        elif len(lesson) > len(total_lesson):
            diff = [item for item in lesson if item not in total_lesson]
            total_lesson = lesson
            title, content, mem_content = u'【期末】出新的成绩了！', u'', u'课程名：'
            for item in diff:
                content += u'课程名：%s，学分：%s，绩点：%s，成绩：%s.\n' % \
                           (item['lesson_name'], item['credit'], item['point'], item['score'])
                mem_content += u'%s、' % item['lesson_name']
            mem_content = mem_content.rstrip(u'、') + u'\n已经出分了，快去查看吧！'
            bot.set_email(title=title, content=content)
            bot.send_email()
            send_to_members(title=title, content=mem_content)
        elif len(lesson) < len(total_lesson):
            diff = [item for item in total_lesson if item not in lesson]
            total_lesson = lesson
            title, content, mem_content = u'【期末】有成绩被撤回了！', u'', u'课程名：'
            for item in diff:
                content += u'课程名：%s，学分：%s，绩点：%s，成绩：%s.\n' % \
                           (item['lesson_name'], item['credit'], item['point'], item['score'])
                mem_content += u'%s、' % item['lesson_name']
            mem_content = mem_content.rstrip(u'、') + u'\n以上课程成绩被老师撤回了！'
            bot.set_email(title=title, content=content)
            bot.send_email()
            send_to_members(title=title, content=mem_content)
        else:
            pass
    except Exception as e:
        school = SchoolClient(url=ZHENGFANG_URL)
        user = school.user_login(USERNAME, PASSWORD)
        rootLogger.error(str(e))
        raise Exception


if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(main, 'interval', seconds=int(SEC_INTERVAL))
    scheduler.add_listener(err_listener, EVENT_JOB_ERROR)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
