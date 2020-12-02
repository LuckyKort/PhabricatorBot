from datetime import datetime
from email import utils
from threading import Thread
from time import strftime, localtime
import re
import requests
import schedule
import telebot
import time

from .config import Config


class TaskGetter:
    __config = None  # type: None or Config
    __stop_threads = False  # type: bool
    __bot = None  # type: None or telebot.AsyncTeleBot
    __active_tasks = {}

    def __init__(self, config: dict):
        self.__chat_config = config
        # TODO: Сейчас запоминание идентификаторов новых заданий выглядит как костыль
        self.__new_ids = []
        self.__sended_ids = []
        return

    @staticmethod
    def __timenow():
        return strftime("%H:%M:%S", localtime(TaskGetter.__timestamp()))

    @property
    def server(self) -> str:
        return self.__chat_config.get('server')

    @server.setter
    def server(self, value: str):
        assert value is not None
        self.__chat_config['server'] = value

    @property
    def chat_id(self) -> int:
        return self.__chat_config.get('chat_id')

    @chat_id.setter
    def chat_id(self, value: int):
        assert value is not None
        self.__chat_config['chat_id'] = value

    @property
    def name(self) -> str:
        return self.__chat_config.get('name') or self.chat_id

    @property
    def last_new_check(self) -> dict:
        return self.__chat_config.get('last_new_check')

    @last_new_check.setter
    def last_new_check(self, value: dict):
        assert value is not None
        self.__chat_config['last_new_check'] = value

    @property
    def last_update_check(self) -> dict:
        return self.__chat_config.get('last_update_check')

    @last_update_check.setter
    def last_update_check(self, value: dict):
        assert value is not None
        self.__chat_config['last_update_check'] = value

    @property
    def phab_api(self) -> str:
        return self.__chat_config.get('phab_api')

    @phab_api.setter
    def phab_api(self, value: str):
        assert value is not None
        self.__chat_config['phab_api'] = value

    @property
    def frequency(self) -> int:
        return self.__chat_config.get('frequency')

    @frequency.setter
    def frequency(self, value: int):
        assert value is not None
        self.__chat_config['frequency'] = value

    @property
    def boards(self) -> list:
        return self.__chat_config.get('boards')

    @boards.setter
    def boards(self, value: list):
        assert value is not None
        self.__chat_config['boards'] = [{v: self.__getproject(v, "id")} for v in value]

    @property
    def ignored_boards(self) -> list:
        return self.__chat_config.get('ignored_boards', [])

    @ignored_boards.setter
    def ignored_boards(self, value: list):
        assert value is not None
        self.__chat_config['ignore_list'] = value

    @staticmethod
    def configure(config: Config, bot: telebot.TeleBot or telebot.AsyncTeleBot):
        TaskGetter.__config = config
        TaskGetter.__bot = bot
        assert TaskGetter.__config.get('tg_api') is not None

    @staticmethod
    def __timestamp():
        try:
            return int(datetime.now().astimezone().timestamp())
        except Exception as e:
            return print("Произошла ошибка при получении времени: ", e)

    @staticmethod
    def __serverdate_to_timestamp(date_str: str):
        return int(utils.parsedate_to_datetime(date_str).astimezone().timestamp())

    def __whois(self, phid):
        try:
            if phid is not None:
                url = '{0}/api/user.search'.format(self.server)
                data = {
                    "api.token": self.phab_api,
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
            print('При получении имени пользователя произошла ошибка: ', e)
            return None

    def __gettaskname(self, task_id):
        try:
            if task_id is not None:
                url = '{0}/api/maniphest.search'.format(self.server)
                data = {
                    "api.token": self.phab_api,
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

    def __getcolname(self, phid):
        try:
            if phid is not None:
                url = '{0}/api/project.column.search'.format(self.server)
                data = {
                    "api.token": self.phab_api,
                    "constraints[phids][0]": phid,
                }
                col_r = requests.post(url, params=data, verify=False)
                json_dict = col_r.json()
                col = json_dict['result']['data'][0]['fields']['name']
                project_phid = json_dict['result']['data'][0]['fields']['project']['phid']
                project = self.__getproject(project_phid, 'id')
                phboard = project['board']
                phproject = project['project']

                return {'column': col, 'board': phboard, 'project': phproject}
            else:
                return "Неизвестен"
        except Exception as e:
            print('При получении имени колонки произошла ошибка: ', e)
            return None

    def __getproject(self, board_id, act):
        if board_id is None:
            return "Неизвестен"
        url = '{0}/api/project.search'.format(self.server)
        try:
            constraint = {
                'id': "constraints[phids][0]"
            }.get(act, "constraints[name]")

            data = {
                "api.token": self.phab_api,
                constraint: board_id
            }

            proj_r = requests.post(url, params=data, verify=False)
            json_dict = proj_r.json()
            phboard = None
            phproject = None
            if len(json_dict['result']['data']) > 0:
                phboard = json_dict['result']['data'][0]['fields']['name']
                if json_dict['result']['data'][0]['fields']['milestone'] is not None:
                    if int(json_dict['result']['data'][0]['fields']['depth']) > 0:
                        phproject = json_dict['result']['data'][0]['fields']['parent']['name']
            return {'board': phboard, 'project': phproject}
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

    def __parse_results(self, json_dict, act, board):
        try:
            if act == "new":
                new_tasks = {}
                if len(json_dict['result']['data']) > 0:
                    for i in range(len(json_dict['result']['data'])):
                        board = self.__getproject(board, "id")['board']
                        project = self.__getproject(board, "id")['project']
                        task_id = json_dict['result']['data'][i]['id']
                        task_name = json_dict['result']['data'][i]['fields']['name']
                        prior = int(json_dict['result']['data'][i]['fields']['priority']['value'])
                        task_prior = TaskGetter.__getpriority(prior)[1]
                        owner = json_dict['result']['data'][i]['fields']['ownerPHID']
                        author = json_dict['result']['data'][i]['fields']['authorPHID']
                        task_owner = self.__whois(owner)['realname']
                        task_author = self.__whois(author)['realname']
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

    def __getupdates(self, ids, task_time):
        try:
            if len(ids) > 0:
                upd_summary = {}
                curr_num = 0
                for i in ids:
                    url = '{0}/api/maniphest.gettasktransactions'.format(self.server)
                    data = {
                        "api.token": self.phab_api,
                        "ids[0]": ids[i],
                    }
                    r = requests.post(url, params=data, verify=False)
                    task = r.json()
                    curr_id = str(ids[i])
                    for j in range(len(task['result'][curr_id])):
                        if int(task['result'][curr_id][j]['dateCreated']) > task_time:
                            if task['result'][curr_id][j]['transactionType'] == "reassign":
                                task_id = task['result'][curr_id][j]['taskID']
                                oldowner = self.__whois(task['result'][curr_id][j]['oldValue'])['realname']
                                newowner = self.__whois(task['result'][curr_id][j]['newValue'])['realname']
                                name = self.__gettaskname(task['result'][curr_id][j]['taskID'])
                                upd_summary[curr_num] = {"action": "reassign",
                                                         "name": name,
                                                         "task_id": task_id,
                                                         "oldowner": oldowner,
                                                         "newowner": newowner}
                                curr_num += 1

                            if task['result'][curr_id][j]['transactionType'] == "core:columns":
                                if task['result'][curr_id][j]['newValue'][0]['boardPHID'] not in self.ignored_boards:
                                    task_id = task['result'][curr_id][j]['taskID']
                                    new_col = task['result'][curr_id][j]['newValue'][0]['columnPHID']
                                    column = self.__getcolname(new_col)
                                    name = self.__gettaskname(task['result'][curr_id][j]['taskID'])
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
                                old_prior = TaskGetter.__getpriority(old_value)[2]
                                new_prior = TaskGetter.__getpriority(new_value)[2]
                                name = self.__gettaskname(task['result'][curr_id][j]['taskID'])
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
                                name = self.__gettaskname(task['result'][curr_id][j]['taskID'])
                                if task['result'][curr_id][j]['comments'] is not None:
                                    replace_attach = re.sub(r'{([\s\S]+?)}', '[Вложение]',
                                                            task['result'][curr_id][j]['comments'])
                                    quote_author = re.findall(r'@(.*?)\s', replace_attach)
                                    linktext = re.findall(r'\[\[.*\|\s(.*?)\]\]', replace_attach)
                                    replace_links = re.sub(r'\[\[(.*?)\]\]', linktext[0] if len(linktext) > 0 else
                                                           "ссылка", replace_attach)
                                    comment = re.sub(r'^(^>).*', 'Цитата\n> : ' +
                                                                 quote_author[0] if len(quote_author) > 0 else
                                                                 "Неизвестный" + ' писал:', replace_links)
                                else:
                                    comment = "Комментарий удален"
                                author = self.__whois(task['result'][curr_id][j]['authorPHID'])['realname']
                                upd_summary[curr_num] = {"action": "comment",
                                                         "name": name,
                                                         "task_id": task_id,
                                                         "comment": comment[0:100] + '...' if
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

    def __send_results(self, results, act):
        assert (results and len(results))
        if act == "new":
            for result in results.values():
                print(TaskGetter.__timenow() + ': Для чата ' + str(self.name) +
                      ' обнаружен новый таск - T' + str(result['task_id']))
                resultstr = 'На борде <b>{0}</b> появился новый таск ' \
                            'с <b>{1}</b> приоритетом: \n\U0001F4CA <b>{2}</b> \n' \
                            '\U0001F425 Инициатор: <b>{3}</b>\n' \
                            '\U0001F425 Исполнитель: <b>{4}</b>\n' \
                            '\n\U0001F449 <a href ="{5}/T{6}">Открыть таск</a>'.format(result['board'],
                                                                                       result['priority'],
                                                                                       result['name'],
                                                                                       result['author'],
                                                                                       result['owner'],
                                                                                       self.server,
                                                                                       result['task_id']
                                                                                       )
                TaskGetter.__bot.send_message(self.chat_id, resultstr, parse_mode='HTML')
                self.__new_ids.append(int(result['task_id']))

        elif act == "upd":
            def sendupd(head, body):
                footer = '\n\U0001F449 <a href ="{0}/T{1}">Открыть таск</a>'.format(self.server, result['task_id'])
                if res_dict[result['task_id']] > 1:
                    result_messages[result['task_id']]['message'].append(
                        "\n\U0001F4DD " + body[0].upper() + body[1:]
                    )
                else:
                    print(self.__timenow() + ': Для чата ' + str(self.name) +
                          ' обнаружен обновленный таск - T' + result['task_id'])
                    TaskGetter.__bot.send_message(self.chat_id, head + body + footer, parse_mode='HTML')

            result_list = [res for res in results.values() if int(res['task_id']) not in self.__new_ids]

            res_dict = {}
            for result in result_list:
                if res_dict.get(result['task_id']):
                    res_dict[result['task_id']] += 1
                else:
                    res_dict[result['task_id']] = 1

            result_messages = {}

            for result in result_list[::-1]:

                if res_dict[result['task_id']] > 1:
                    if result_messages.get(result['task_id']) is None:
                        result_messages[result['task_id']] = {}
                        result_messages[result['task_id']].update({'name': result['name']})
                        result_messages[result['task_id']].update({'id': result['task_id']})
                        result_messages[result['task_id']]['message'] = []

                if result['action'] == "reassign":
                    headstr = '\U0001F4CA В таске <b>{0}</b> '.format(result['name'])
                    resultstr = 'был изменен исполнитель: \n' \
                                '\U0001F425 Предыдущий исполнитель: <b>{0}</b>\n' \
                                '\U0001F425 Новый исполнитель: <b>{1}</b>\n'.format(result['oldowner'],
                                                                                    result['newowner'])
                    sendupd(headstr, resultstr)

                if result['action'] == "move":

                    projstr = result['project'] is not None and (result['project'] + " - ") or ""

                    headstr = '\U0001F4CA Таск <b>{0}</b> '.format(result['name'])
                    resultstr = 'перемещен в колонку ' \
                                '<b>{0}</b> на борде <b>{1}{2}</b>\n'.format(result['column'],
                                                                             projstr,
                                                                             result['board'],
                                                                             self.server,
                                                                             result['task_id']
                                                                             )
                    sendupd(headstr, resultstr)

                if result['action'] == "priority":
                    headstr = '\U0001F4CA В таске <b>{0}</b> '.format(result['name'])
                    resultstr = '{0} приоритет ' \
                                'с <b>{1}</b> до <b>{2}</b>\n'.format(result['subject'],
                                                                      result['old_prior'],
                                                                      result['new_prior'],
                                                                      )
                    sendupd(headstr, resultstr)

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
                print(TaskGetter.__timenow() + ': Для чата ' + str(self.chat_id) +
                      ' обнаружен обновленный таск - T' + message['id'])
                resultstr = '\U0001F4CA В таске <b>{0}</b> произошли изменения:\n ' \
                            '{1} \n' \
                            '\U0001F449 <a href ="{2}/T{3}">Открыть таск</a>'.format(message['name'],
                                                                                     messagestr,
                                                                                     self.server,
                                                                                     message['id'])
                TaskGetter.__bot.send_message(self.chat_id, resultstr, parse_mode='HTML')

    def __tasks_search(self):
        for board in self.boards:
            def search():
                return requests.post(url, params=data, verify=False)

            if not self.last_new_check:
                self.last_new_check = {}
            if not self.last_update_check:
                self.last_update_check = {}

            if not self.last_new_check.get(board):
                self.last_new_check[board] = self.__timestamp()
            if not self.last_update_check.get(board):
                self.last_update_check[board] = self.last_new_check[board]

            last_new = self.last_new_check[board]
            last_update = self.last_update_check[board]

            # Проверка последних обновленных задач не может быть раньше проверки новых заданий
            assert last_update >= last_new
            if last_update < last_new:
                self.last_update_check[board] = last_new
                last_update = last_new

            # TODO: Идет сброс костыльного счетчика идентификаторов
            self.__new_ids.clear()

            url = '{0}/api/maniphest.search'.format(self.server)

            data = {
                "api.token": self.phab_api,
                "queryKey": "open",
                "constraints[projects][0]": board
            }

            data.update({"constraints[createdStart]": last_new})
            new_r = search()
            data.pop("constraints[createdStart]")
            data.update({"constraints[modifiedStart]": last_update})

            upd_r = search()

            new_parsed = self.__parse_results(new_r.json(), "new", board)
            upd_parsed = self.__parse_results(upd_r.json(), "upd", board)

            log_item = "\n------" \
                       "\nFrom(New): {0}" \
                       "\nFrom(Updates): {1}" \
                       "\nNew: {2}" \
                       "\nUpd: {3}" \
                       "\nNewParsed: {4}" \
                       "\nUpdParsed: {5}".format(last_new, last_update, new_r.json(), upd_r.json(),
                                                 new_parsed, upd_parsed)
            with open('logs.txt', 'a') as file:
                file.write(log_item)

            if new_parsed is not None:
                self.__send_results(new_parsed, "new")

            if upd_parsed is not None:
                if upd_parsed not in self.__sended_ids:
                    self.__sended_ids.append(upd_parsed)
                    updated_tasks = self.__getupdates(upd_parsed, last_update)
                    if updated_tasks is not None:
                        self.__send_results(updated_tasks, "upd")
                        updated_tasks_logline = "\nUpdated_tasks: {0}".format(updated_tasks)
                        with open('logs.txt', 'a') as file:
                            file.write(updated_tasks_logline)

            self.last_new_check[board] = TaskGetter.__serverdate_to_timestamp(new_r.headers['date'])
            self.last_update_check[board] = TaskGetter.__serverdate_to_timestamp(upd_r.headers['date'])
            TaskGetter.__config.dump()
        self.__sended_ids.clear()

    def tasks_search(self):
        try:
            self.__tasks_search()
        except Exception as e:
            print(e)

    @staticmethod
    def stop():
        TaskGetter.__stop_threads = True

    @staticmethod
    def unschedule(chat_id: int or None):
        if chat_id is None:
            schedule.clear()
            TaskGetter.__active_tasks.clear()
            return
        chat_config = TaskGetter.__config.chat(chat_id)
        chat_config['active'] = False
        TaskGetter.__config.dump()
        task = TaskGetter.__active_tasks.get(chat_id)
        if not task:
            TaskGetter.__bot.send_message(chat_id, "\u26A1 Мониторинг уже приостановлен")
            return
        TaskGetter.__active_tasks.pop(chat_id)
        schedule.cancel_job(task)
        TaskGetter.__bot.send_message(chat_id, "\u2705 Мониторинг приостановлен")

    @staticmethod
    def checkconn(config, task_getter):
        if not config.get('server'):
            TaskGetter.__bot.send_message(task_getter.chat_id, "Для начала работы бота необходимо ввести "
                                                               "адрес сервера в главном меню (/main)",
                                          parse_mode='HTML')
            return False
        if not config.get('phab_api'):
            TaskGetter.__bot.send_message(task_getter.chat_id, "Для начала работы бота необходимо ввести API-токен в "
                                                               "главном меню (/main).\n"
                                                               "Чтобы узнать, как получить API Token введите "
                                                               "команду <b>/where_apitoken</b>", parse_mode='HTML')
            return False
        if not config.get('boards'):
            TaskGetter.__bot.send_message(task_getter.chat_id, "Для начала работы бота необходимо ввести PHIDы "
                                                               "бордов которые необходимо мониторить "
                                                               "в главном меню (/main) "
                                                               "\nДля того, чтобы узнать ID борда "
                                                               "введите команду /project_id Название",
                                          parse_mode='HTML')
            return False
        try:
            url = config.get('server') + '/api/user.whoami'
            data = {
                "api.token": config.get('phab_api')
            }
            result = requests.post(url, params=data, allow_redirects=False, verify=False)
            if not result:
                TaskGetter.__bot.send_message(task_getter.chat_id,
                                              "Проверьте правильность указания адреса фабрикатора")
                return False
            if result.headers['Content-Type'] != 'application/json':
                TaskGetter.__bot.send_message(task_getter.chat_id,
                                              "Проверьте правильность указания адреса фабрикатора")
                return False
            json = result.json()
            if json['error_code'] == 'ERR-INVALID-AUTH':
                err = json['error_info']
                TaskGetter.__bot.send_message(task_getter.chat_id, "Произошла ошибка: " + err)
                return False
            return True
        except requests.exceptions.ConnectionError:
            TaskGetter.__bot.send_message(task_getter.chat_id,
                                          "Проверьте правильность введенного адреса сервера")
            return False
        except Exception as e:
            TaskGetter.__bot.send_message(task_getter.chat_id,
                                          "При попытке подключиться к серверу произошла ошибка: " + str(e))
            return False

    @staticmethod
    def schedule(chat_id: int or None = None):
        def schedule_task(config):
            if not config.get('active'):
                return
            task_getter = TaskGetter(config)
            assert task_getter.chat_id is not None
            if TaskGetter.__active_tasks.get(task_getter.chat_id):
                return
            if not task_getter.checkconn(config, task_getter):
                chat_config['active'] = False
                TaskGetter.__config.dump()
                return
            task_getter.tasks_search()
            TaskGetter.__active_tasks[task_getter.chat_id] = \
                schedule.every(task_getter.frequency or 2).minutes.do(task_getter.tasks_search)

        if chat_id is not None:
            chat_config = TaskGetter.__config.chat(chat_id)
            chat_config['active'] = True
            TaskGetter.__config.dump()
            schedule_task(TaskGetter.__config.chat(chat_id))
        else:
            for chat_config in TaskGetter.__config['chats']:
                schedule_task(chat_config)
            while True:
                if TaskGetter.__stop_threads:
                    schedule.clear()
                    return
                schedule.run_pending()
                time.sleep(1)

    @staticmethod
    def main_loop():
        thread = None
        try:
            if thread is None:
                thread = Thread(target=TaskGetter.schedule)
            thread.start()
            TaskGetter.__bot.polling(True)
        except Exception as e:
            print('Произошла ошибка: ' + str(e))
            TaskGetter.__stop_threads = True
            time.sleep(15)
        finally:
            TaskGetter.__stop_threads = False
            TaskGetter.main_loop()
