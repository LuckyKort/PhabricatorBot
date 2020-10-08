import requests
import time
import telebot
import schedule
from time import strftime, localtime
from threading import Thread
from datetime import datetime
from pytz import timezone
from tzlocal import get_localzone
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from lxml import etree

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

xml_file = etree.parse('config.xml')
config = xml_file.getroot()
tgkey = config[0].text
phkey = config[1].text
chatid = config[2].text
server = config[3].text
board = config[4].text
ignoredphid = config[6].text


bot = telebot.AsyncTeleBot(tgkey)

_timestamp = None
stop_threads = False

# @bot.message_handler(commands=['config'])
# def configuration(message):
#     markup = telebot.types.ReplyKeyboardMarkup(row_width=3)
#     markup.add(telebot.types.InlineKeyboardButton("Ввести ключ API для Phabricator", callback_data="phabkey"))
#     markup.add(telebot.types.InlineKeyboardButton("Ввести ID чата", callback_data="chatid"))
#     markup.add(telebot.types.InlineKeyboardButton("Ввести ID борда", callback_data="boardid"))
#     bot.send_message(message.chat.id, 'Привет! Выбери действие:', reply_markup=markup)
#
#
# @bot.callback_query_handler(func=lambda call: True)
# def query_handler(call):
#     if call == "phabkey":
#         conf = etree.open('config.xml')
#         conf[1].text = call
#     if call == "chatid":
#         conf = etree.open('config.xml')
#         conf[2].text = call
#     if call == "boardid":
#         conf = etree.open('config.xml')
#         conf[3].text = call


@bot.message_handler(commands=['getchatid'])
def setup(message):
    bot.send_message(message.chat.id, 'ID чата: ' + str(message.chat.id))


class GetTasks:
    def __init__(self):
        self.__last_time = None
        __last_time = config[5].text
        return

    @staticmethod
    def __timestamp():
        try:
            now_utc = datetime.now(timezone('UTC'))
            now_local = now_utc.astimezone(get_localzone())
            ts = int(datetime.timestamp(now_local)) - 10
            return ts
        except Exception as e:
            return print("Произошла ошибка при получении времени: ", e)

    @staticmethod
    def __whois(phid):
        try:
            if phid is not None:
                url = '{0}/api/user.search'.format(server)
                data = {
                    "api.token": phkey,
                    "constraints[phids][0]": phid,
                }
                r = requests.post(url, params=data, verify=False)
                json_dict = r.json()
                username = json_dict['result']['data'][0]['fields']['username']
                realname = json_dict['result']['data'][0]['fields']['realName']
                return {'username': username, 'realname': realname}
            else:
                return {'username': "Не определен", 'realname': "Не определен"}
        except Exception as e:
            return 'При получении имени пользователя произошла ошибка: ', e

    @staticmethod
    def __gettaskname(task_id):
        try:
            if task_id is not None:
                url = '{0}/api/maniphest.search'.format(server)
                data = {
                    "api.token": phkey,
                    "constraints[ids][0]": task_id,
                }
                r = requests.post(url, params=data, verify=False)
                json_dict = r.json()
                task_name = json_dict['result']['data'][0]['fields']['name']
                return task_name
            else:
                return "Неизвестен"
        except Exception as e:
            return 'При получении имени пользователя произошла ошибка: ', e

    @staticmethod
    def __getcolname(phid):
        try:
            if phid is not None:
                url = '{0}/api/project.column.search'.format(server)
                data = {
                    "api.token": phkey,
                    "constraints[phids][0]": phid,
                }
                col_r = requests.post(url, params=data, verify=False)
                json_dict = col_r.json()
                col = json_dict['result']['data'][0]['fields']['name']
                project = json_dict['result']['data'][0]['fields']['project']['name']

                return {'column': col, 'project': project}
            else:
                return "Неизвестен"
        except Exception as e:
            return 'При получении имени колонки произошла ошибка: ', e

    @staticmethod
    def __parse_results(json_dict, act):
        if act == "new":
            new_tasks = {}
            if len(json_dict['result']['data']) > 0:
                for i in range(len(json_dict['result']['data'])):
                    task_id = json_dict['result']['data'][i]['id']
                    task_name = json_dict['result']['data'][i]['fields']['name']
                    prior = json_dict['result']['data'][i]['fields']['priority']['name']
                    task_prior = {
                        'Low': "низким",
                        'Normal': "средним",
                        'High': "высоким",
                        'Unbreak Now!': "срочным",
                        'Needs Triage': "требующим уточнения",
                        'Whishlist': "интересным"
                    }.get(prior, "неопределенным")
                    owner = json_dict['result']['data'][i]['fields']['ownerPHID']
                    author = json_dict['result']['data'][i]['fields']['authorPHID']
                    task_owner = GetTasks.__whois(owner)['realname']
                    task_author = GetTasks.__whois(author)['realname']
                    task_summary = {"task_id": task_id,
                                    "name": task_name,
                                    "priority": task_prior,
                                    "owner": task_owner,
                                    "author": task_author
                                    }
                    new_tasks[i] = task_summary
                return new_tasks
            else:
                return None

        elif act == "upd":
            upd_tasks = {}
            if len(json_dict['result']['data']) > 0:
                for i in range(len(json_dict['result']['data'])):
                    task_id = json_dict['result']['data'][i]['id']
                    upd_tasks[i] = task_id
                return upd_tasks
            else:
                return None

    @staticmethod
    def __getupdates(ids, task_time):
        try:
            if len(ids) > 0:
                upd_summary = {}
                for i in ids:
                    url = '{0}/api/maniphest.gettasktransactions'.format(server)
                    data = {
                        "api.token": phkey,
                        "ids[0]": ids[i],
                    }
                    r = requests.post(url, params=data, verify=False)
                    task = r.json()
                    curr_id = str(ids[i])
                    curr_num = 0
                    for j in range(len(task['result'][curr_id])):
                        if int(task['result'][curr_id][j]['dateCreated']) > task_time:
                            if task['result'][curr_id][j]['transactionType'] == "reassign":
                                task_id = task['result'][curr_id][j]['taskID']
                                rfrom = task['result'][curr_id][j]['oldValue']
                                rto = task['result'][curr_id][j]['newValue']
                                oldowner = GetTasks.__whois(rfrom)['realname']
                                newowner = GetTasks.__whois(rto)['realname']
                                name = GetTasks.__gettaskname(task['result'][curr_id][j]['taskID'])
                                upd_summary[curr_num] = {"action": "reassign",
                                                         "name": name,
                                                         "task_id": task_id,
                                                         "oldowner": oldowner,
                                                         "newowner": newowner}
                                curr_num += curr_num

                            if task['result'][curr_id][j]['transactionType'] == "core:columns":
                                if task['result'][curr_id][j]['newValue'][0]['boardPHID'] != ignoredphid:
                                    task_id = task['result'][curr_id][j]['taskID']
                                    new_col = task['result'][curr_id][j]['newValue'][0]['columnPHID']
                                    column = GetTasks.__getcolname(new_col)
                                    name = GetTasks.__gettaskname(task['result'][curr_id][j]['taskID'])
                                    upd_summary[curr_num] = {"action": "move",
                                                             "name": name,
                                                             "task_id": task_id,
                                                             "column": column['column'],
                                                             "project": column['project']}
                                    curr_num += curr_num
                if len(upd_summary) > 0:
                    return upd_summary
                else:
                    return None
            else:
                return None
        except Exception as e:
            return 'При получении обновлений произошла ошибка: ', e

    @staticmethod
    def __send_results(results, chat_id, act):
        assert (results and len(results))
        if act == "new":
            for i in range(len(results)):
                print('Обнаружен новый таск!')
                resultstr = 'На борде появился новый таск с {0} приоритетом: \n \U0001F4CA "{1}" \n' \
                            '\U0001F425 Инициатор: {2}\n' \
                            '\U0001F425 Исполнителем назначен(-а) {3}\n' \
                            '\U0001F449 <a href ="{4}}/T{5}">Открыть таск</a>'.format(
                                                                                                results[i]['priority'],
                                                                                                results[i]['name'],
                                                                                                results[i]['author'],
                                                                                                results[i]['owner'],
                                                                                                server,
                                                                                                results[i]['task_id']
                                                                                                )
                bot.send_message(chat_id, resultstr, parse_mode='HTML')

        elif act == "upd":
            for i in range(len(results)):
                print('Обнаружен обновленный таск!')

                if results[i]['action'] == "reassign":
                    resultstr = 'В таске \U0001F4CA "{0}" был изменен исполнитель: \n' \
                                '\U0001F425 Предыдущий исполнитель: {1}\n' \
                                '\U0001F425 Новый исполнитель: {2}\n' \
                                '\U0001F449 <a href ="{3}/T{4}">Открыть таск</a>'.format(
                                                                                            results[i]['name'],
                                                                                            results[i]['oldowner'],
                                                                                            results[i]['newowner'],
                                                                                            server,
                                                                                            results[i]['task_id']
                                                                                            )
                    bot.send_message(chat_id, resultstr, parse_mode='HTML')

                if results[i]['action'] == "move":
                    resultstr = 'Таск \U0001F4CA "{0}" перемещен в колонку "{1}" на борде "{2}"\n' \
                                '\U0001F449 <a href ="{3}/T{4}">Открыть таск</a>'.format(
                                                                                            results[i]['name'],
                                                                                            results[i]['column'],
                                                                                            results[i]['project'],
                                                                                            server,
                                                                                            results[i]['task_id']
                                                                                            )
                    bot.send_message(chat_id, resultstr, parse_mode='HTML')

    def tasks_search(self, chat_id):
        if not self.__last_time:
            self.__last_time = self.__timestamp()

        url = '{0}/api/maniphest.search'.format(server)

        print(strftime("%H:%M:%S", localtime(self.__timestamp())) + ' - Проверяю новые таски...')
        new_data = {
            "api.token": phkey,
            "queryKey": "open",
            "constraints[projects][0]": board,
            "constraints[createdStart]": self.__last_time
        }

        print(strftime("%H:%M:%S", localtime(self.__timestamp())) + ' - Проверяю обновленные таски...')
        upd_data = {
            "api.token": phkey,
            "queryKey": "open",
            "constraints[projects][0]": board,
            "constraints[modifiedStart]": self.__last_time
        }

        new_r = requests.post(url, params=new_data, verify=False)
        upd_r = requests.post(url, params=upd_data, verify=False)

        new_parsed = self.__parse_results(new_r.json(), "new")
        upd_parsed = self.__parse_results(upd_r.json(), "upd")

        if new_parsed is not None:
            self.__send_results(new_parsed, chat_id, "new")
        else:
            print('Новых тасков нет')

        if upd_parsed is not None:
            updated_tasks = self.__getupdates(upd_parsed, self.__last_time)
            if updated_tasks is not None:
                self.__send_results(updated_tasks, chat_id, "upd")
            else:
                print('Обновленных тасков нет')
        else:
            print('Обновленных тасков нет')

        self.__last_time = self.__timestamp()

        config[5].text = str(self.__last_time + 10)
        xml_file.write('config.xml')

    @staticmethod
    def do_schedule():
        task_getter = GetTasks()
        schedule.every(2).minutes.do(task_getter.tasks_search, chat_id=chatid)

        global stop_threads
        while True:
            if stop_threads:
                return
            schedule.run_pending()
            time.sleep(1)

    @staticmethod
    def main_loop():
        thread = None
        try:
            if thread is None:
                thread = Thread(target=GetTasks.do_schedule)
            thread.start()

            bot.polling(True)
        except Exception as e:
            print('Произошла ошибка: ' + str(e))
            global stop_threads
            stop_threads = True
            time.sleep(15)
        finally:
            stop_threads = False
            GetTasks.main_loop()


if __name__ == '__main__':
    GetTasks.main_loop()
