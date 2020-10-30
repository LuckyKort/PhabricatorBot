import requests
import time
import telebot
import schedule
import os
from time import strftime, localtime
from threading import Thread
from datetime import datetime
from pytz import timezone
from tzlocal import get_localzone
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from lxml import etree
from shutil import copyfile

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
new_ids = []


@bot.message_handler(commands=['getchatid'])
def setup(message):
    bot.send_message(message.chat.id, 'ID чата: ' + str(message.chat.id))


def copy_logs():
    if os.path.isfile("logs_old.txt"):
        os.remove("logs_old.txt")
    copyfile("logs.txt", "logs_old.txt")
    if os.path.isfile("logs.txt"):
        os.remove("logs.txt")
    open("logs.txt", 'a').close()
    return


class GetTasks:
    def __init__(self):
        self.__last_time = config[5].text
        return

    @staticmethod
    def __timestamp():
        try:
            now_utc = datetime.now(timezone('UTC'))
            now_local = now_utc.astimezone(get_localzone())
            ts = int(datetime.timestamp(now_local)) - 5
            return ts
        except Exception as e:
            print("Произошла ошибка при получении времени: ", e)
            return None

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
                return {'username': "Не установлен", 'realname': "Не установлен"}
        except Exception as e:
            print('При получении имени пользователя произошла ошибка: ', e)
            return None

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
            print('При получении имени таска произошла ошибка: ', e)
            return None

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
                project_phid = json_dict['result']['data'][0]['fields']['project']['phid']
                phboard = GetTasks.__getproject(project_phid, "phid")['board']
                phproject = GetTasks.__getproject(project_phid, "phid")['project']

                return {'column': col, 'board': phboard, 'project': phproject}
            else:
                return "Неизвестен"
        except Exception as e:
            print('При получении имени колонки произошла ошибка: ', e)
            return None

    @staticmethod
    def __getproject(board_id, act):
        try:
            if board_id is not None:
                if act == "phid":
                    url = '{0}/api/project.search'.format(server)
                    data = {
                        "api.token": phkey,
                        "constraints[phids][0]": board_id,
                    }

                else:
                    url = '{0}/api/project.search'.format(server)
                    data = {
                        "api.token": phkey,
                        "constraints[name]": board_id,
                    }

                proj_r = requests.post(url, params=data, verify=False)
                json_dict = proj_r.json()
                phboard = json_dict['result']['data'][0]['fields']['name']
                phproject = None
                if json_dict['result']['data'][0]['fields']['milestone'] is not None:
                    if int(json_dict['result']['data'][0]['fields']['milestone']) == 2:
                        phproject = json_dict['result']['data'][0]['fields']['parent']['name']

                return {'board': phboard, 'project': phproject}

            else:
                return "Неизвестен"
        except Exception as e:
            print('При получении имени проекта произошла ошибка: ', e)
            return None

    @staticmethod
    def __getpriority(value):
        try:
            task_prior = {
                10: ("интересный", "интересным", "интересного"),
                25: ("низкий", "низким", "низкого"),
                50: ("средний", "средним", "среднего"),
                80: ("высокий", "высоким", "высокого"),
                90: ("требующий уточнения", "требующим уточнения", "требущего уточнения"),
                100: ("срочный", "срочным", "срочного")
            }.get(value, ("неопределенный", "неопределенным", "неопределенного"))
            return task_prior
        except Exception as e:
            print('При получении приоритета произошла ошибка: ', e)
            return None

    @staticmethod
    def __parse_results(json_dict, act):
        try:
            if act == "new":
                new_tasks = {}
                if len(json_dict['result']['data']) > 0:
                    for i in range(len(json_dict['result']['data'])):
                        global board
                        board = GetTasks.__getproject(board, "id")['board']
                        project = GetTasks.__getproject(board, "id")['project']
                        task_id = json_dict['result']['data'][i]['id']
                        task_name = json_dict['result']['data'][i]['fields']['name']
                        prior = int(json_dict['result']['data'][i]['fields']['priority']['value'])
                        task_prior = GetTasks.__getpriority(prior)[1]
                        owner = json_dict['result']['data'][i]['fields']['ownerPHID']
                        author = json_dict['result']['data'][i]['fields']['authorPHID']
                        task_owner = GetTasks.__whois(owner)['realname']
                        task_author = GetTasks.__whois(author)['realname']
                        task_summary = {"task_id": task_id,
                                        "board": board,
                                        "project": project,
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
        except Exception as e:
            print('При парсинге результатов произошла ошибка: ', e)
            return None

    @staticmethod
    def __getupdates(ids, task_time):
        try:
            if len(ids) > 0:
                upd_summary = {}
                curr_num = 0
                for i in ids:
                    url = '{0}/api/maniphest.gettasktransactions'.format(server)
                    data = {
                        "api.token": phkey,
                        "ids[0]": ids[i],
                    }
                    r = requests.post(url, params=data, verify=False)
                    task = r.json()
                    curr_id = str(ids[i])
                    for j in range(len(task['result'][curr_id])):
                        if task['result'][curr_id][j]['dateCreated'] > task_time:
                            if task['result'][curr_id][j]['transactionType'] == "reassign":
                                task_id = task['result'][curr_id][j]['taskID']
                                oldowner = GetTasks.__whois(task['result'][curr_id][j]['oldValue'])['realname']
                                newowner = GetTasks.__whois(task['result'][curr_id][j]['newValue'])['realname']
                                name = GetTasks.__gettaskname(task['result'][curr_id][j]['taskID'])
                                upd_summary[curr_num] = {"action": "reassign",
                                                         "name": name,
                                                         "task_id": task_id,
                                                         "oldowner": oldowner,
                                                         "newowner": newowner}
                                curr_num += 1

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
                                                             "board": column['board'],
                                                             "project": column['project']}
                                    curr_num += 1

                            if task['result'][curr_id][j]['transactionType'] == "priority":
                                task_id = task['result'][curr_id][j]['taskID']
                                old_value = int(task['result'][curr_id][j]['oldValue'])
                                new_value = int(task['result'][curr_id][j]['newValue'])
                                old_prior = GetTasks.__getpriority(old_value)[2]
                                new_prior = GetTasks.__getpriority(new_value)[2]
                                name = GetTasks.__gettaskname(task['result'][curr_id][j]['taskID'])
                                subject = "повышен" if old_value < new_value else "понижен"
                                upd_summary[curr_num] = {"action": "priority",
                                                         "name": name,
                                                         "task_id": task_id,
                                                         "subject": subject,
                                                         "old_prior": old_prior,
                                                         "new_prior": new_prior}
                                curr_num += 1

                            if task['result'][curr_id][j]['transactionType'] == "core:comment":
                                task_id = task['result'][curr_id][j]['taskID']
                                name = GetTasks.__gettaskname(task['result'][curr_id][j]['taskID'])
                                comment = task['result'][curr_id][j]['comments']
                                author = GetTasks.__whois(task['result'][curr_id][j]['authorPHID'])['realname']
                                upd_summary[curr_num] = {"action": "comment",
                                                         "name": name,
                                                         "task_id": task_id,
                                                         "comment": comment[0:100] + '..' if
                                                         (len(comment) > 100) else comment,
                                                         "author": author}
                                curr_num += 1

                if len(upd_summary) > 0:
                    return upd_summary
                else:
                    return None
            else:
                return None
        except Exception as e:
            print('При получении обновлений произошла ошибка: ', e)
            return None

    @staticmethod
    def __send_results(results, chat_id, act):
        global new_ids
        assert (results and len(results))
        if act == "new":
            for result in results.values():
                print('Обнаружен новый таск!')
                resultstr = 'На борде <b>{0}</b> появился новый таск ' \
                            'с <b>{1}</b> приоритетом: \n \U0001F4CA <b>"{2}"</b> \n' \
                            '\U0001F425 Инициатор: <b>{3}</b>\n' \
                            '\U0001F425 Исполнитель: <b>{4}</b>\n' \
                            '\U0001F449 <a href ="{5}/T{6}">Открыть таск</a>'.format(result['board'],
                                                                                     result['priority'],
                                                                                     result['name'],
                                                                                     result['author'],
                                                                                     result['owner'],
                                                                                     server,
                                                                                     result['task_id']
                                                                                     )
                bot.send_message(chat_id, resultstr, parse_mode='HTML')
                new_ids.append(int(result['task_id']))

        elif act == "upd":
            result_list = [res for res in results.values() if int(res['task_id']) not in new_ids]
            if len(result_list) == 0:
                print('Обновленных тасков нет')

            res_dict = {}
            for result in result_list:
                if res_dict.get(result['task_id']):
                    res_dict[result['task_id']] += 1
                else:
                    res_dict[result['task_id']] = 1

            result_messages = {}

            for result in result_list[::-1]:
                print('Обнаружен обновленный таск!')

                if res_dict[result['task_id']] > 1:
                    if result_messages.get(result['task_id']) is None:
                        result_messages[result['task_id']] = {}
                        result_messages[result['task_id']].update({'name': result['name']})
                        result_messages[result['task_id']].update({'id': result['task_id']})
                        result_messages[result['task_id']]['message'] = []

                footerstr = '\n\U0001F449 <a href ="{0}/T{1}">Открыть таск</a>'.format(server,
                                                                                       result['task_id'])

                if result['action'] == "reassign":
                    headstr = '\U0001F4CA В таске <b>{0}</b> '.format(result['name'])
                    resultstr = 'был изменен исполнитель: \n' \
                                '\U0001F425 Предыдущий исполнитель: <b>{0}</b>\n' \
                                '\U0001F425 Новый исполнитель: <b>{1}</b>\n'.format(result['oldowner'],
                                                                                    result['newowner'],
                                                                                    )
                    if res_dict[result['task_id']] > 1:
                        result_messages[result['task_id']]['message'].append(
                            "\n\U0001F4DD " + resultstr[0].upper() + resultstr[1:]
                        )
                    else:
                        bot.send_message(chat_id, headstr + resultstr + footerstr, parse_mode='HTML')

                if result['action'] == "move":

                    projstr = result['project'] is not None and (result['project'] + " - ") or ""

                    headstr = '\U0001F4CA Таск <b>{0}</b> '.format(result['name'])
                    resultstr = 'перемещен в колонку ' \
                                '<b>{0}</b> на борде <b>{1}{2}</b>\n'.format(result['column'],
                                                                                 projstr,
                                                                                 result['board'],
                                                                                 server,
                                                                                 result['task_id']
                                                                                 )
                    if res_dict[result['task_id']] > 1:
                        result_messages[result['task_id']]['message'].append(
                            "\n\U0001F4DD " + resultstr[0].upper() + resultstr[1:]
                        )
                    else:
                        bot.send_message(chat_id, headstr + resultstr + footerstr, parse_mode='HTML')

                if result['action'] == "priority":
                    headstr = '\U0001F4CA В таске <b>{0}</b> '.format(result['name'])
                    resultstr = '{0} приоритет ' \
                                'с <b>{1}</b> до <b>{2}</b>\n'.format(result['subject'],
                                                                      result['old_prior'],
                                                                      result['new_prior'],
                                                                      )
                    if res_dict[result['task_id']] > 1:
                        result_messages[result['task_id']]['message'].append(
                            "\n\U0001F4DD " + resultstr[0].upper() + resultstr[1:]
                        )
                    else:
                        bot.send_message(chat_id, headstr + resultstr + footerstr, parse_mode='HTML')

                if result['action'] == "comment":
                    resultstr = '\n\U0001F4AC {0} добавил(-а) комментарий: \n<b>{1}</b>\n'.format(result['author'],
                                                                                                    result['comment']
                                                                                                    )
                    if res_dict[result['task_id']] > 1:
                        result_messages[result['task_id']]['message'].append(resultstr)

            for message in result_messages.values():
                messagestr = ""
                for actions in message['message']:
                    messagestr += actions
                resultstr = '\U0001F4CA В таске <b>{0}</b> произошли изменения:\n ' \
                            '{1} \n' \
                            '\U0001F449 <a href ="{2}/T{3}">Открыть таск</a>'.format(message['name'],
                                                                                     messagestr,
                                                                                     server,
                                                                                     message['id'])
                bot.send_message(chat_id, resultstr, parse_mode='HTML')

    def tasks_search(self, chat_id):
        if not self.__last_time:
            self.__last_time = self.__timestamp()

        url = '{0}/api/maniphest.search'.format(server)

        print(strftime("%H:%M:%S", localtime(self.__timestamp())),
              '- Проверяю обновления в промежутке с ', self.__last_time, ' до ', self.__timestamp())

        data = {
            "api.token": phkey,
            "queryKey": "open",
            "constraints[projects][0]": board,
        }

        data.update({"constraints[createdStart]": self.__last_time})
        new_r = requests.post(url, params=data, verify=False)
        data.pop("constraints[createdStart]")
        data.update({"constraints[modifiedStart]": self.__last_time})
        upd_r = requests.post(url, params=data, verify=False)

        new_parsed = self.__parse_results(new_r.json(), "new")
        upd_parsed = self.__parse_results(upd_r.json(), "upd")

        log_item = "\n------" \
                   "\nFrom: {0}" \
                   "\nTo: {1}" \
                   "\nNew: {2}" \
                   "\nUpd: {3}" \
                   "\nNewParsed: {4}" \
                   "\nUpdParsed: {5}".format(self.__last_time, self.__timestamp(), new_r.json(), upd_r.json(),
                                             new_parsed, upd_parsed)
        with open('logs.txt', 'a') as file:
            file.write(log_item)

        if new_parsed is not None:
            self.__send_results(new_parsed, chat_id, "new")
        else:
            print('Новых тасков нет')

        if upd_parsed is not None:
            updated_tasks = self.__getupdates(upd_parsed, self.__last_time)
            if updated_tasks is not None:
                self.__send_results(updated_tasks, chat_id, "upd")
                updated_tasks_logline = "\nUpdated_tasks: {0}".format(updated_tasks)
                with open('logs.txt', 'a') as file:
                    file.write(updated_tasks_logline)
            else:
                print('Обновленных тасков нет')
        else:
            print('Обновленных тасков нет')

        self.__last_time = str(self.__timestamp())

        print("Проверка закончена, записанный timestamp:", self.__last_time)
        config[5].text = self.__last_time
        xml_file.write('config.xml')

    @staticmethod
    def do_schedule():
        task_getter = GetTasks()
        GetTasks().tasks_search(chatid)
        schedule.every().day.at("05:00").do(copy_logs)
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
