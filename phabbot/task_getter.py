from datetime import datetime
from email import utils
from threading import Thread
from time import strftime, localtime
import re
import requests
import schedule
import telebot
import time
import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from .config import Config

logging.basicConfig(filename="bot.log", level=logging.DEBUG)


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

    def full_markup(self, task_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Полная информация", callback_data="info" + str(task_id)),
                   InlineKeyboardButton("Открыть задачу", url="%s/T%s" % (self.server, task_id)))
        return markup

    @staticmethod
    def __timenow():
        return strftime("%H:%M:%S", localtime(TaskGetter.__timestamp()))

    @property
    def server(self) -> str:
        return TaskGetter.__config.get('server') or self.__chat_config.get('server')

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
    def watchtype(self) -> int:
        return self.__chat_config.get('watchtype')

    @property
    def boards(self) -> list:
        return self.__chat_config.get('boards')

    @property
    def settings(self) -> list:
        return self.__chat_config.get('settings', [])

    @property
    def priorities(self) -> list:
        return self.__chat_config.get('priorities', [])

    @boards.setter
    def boards(self, value: list):
        assert value is not None
        self.__chat_config['boards'] = [{v: self.__getproject(v, "id")} for v in value]

    @property
    def ignored_boards(self) -> list:
        return self.__chat_config.get('ignored_boards', [])

    @property
    def ignored_columns(self) -> list:
        return self.__chat_config.get('ignored_columns', [])

    @ignored_boards.setter
    def ignored_boards(self, value: list):
        assert value is not None
        self.__chat_config['ignore_list'] = value

    @property
    def ignored_users(self) -> list:
        return self.__chat_config.get('ignored_users', [])

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

    def __whoaim(self):
        try:
                url = '{0}/api/user.whoami'.format(self.server)
                data = {
                    "api.token": self.phab_api
                }
                r = requests.post(url, params=data, verify=False)
                json_dict = r.json()
                username = json_dict['result']['userName']
                return username
        except Exception as e:
            print('При получении имени пользователя произошла ошибка: ', e)
            return None

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
                telegram = json_dict['result']['data'][0]['fields']['custom.Telegram']
                return {'username': username, 'realname': realname, 'telegram': telegram}
            else:
                return {'username': "Не определен", 'realname': "Не определен", 'telegram': None}
        except Exception as e:
            print('При получении имени пользователя произошла ошибка: ', e)
            return None

    def __gettaskname(self, task_id, act):
        try:
            if task_id is not None:
                constraint = {
                    'phid': "constraints[phids][0]"
                }.get(act, "constraints[ids][0]")

                url = '{0}/api/maniphest.search'.format(self.server)
                data = {
                    "api.token": self.phab_api,
                    constraint: task_id,
                }
                r = requests.post(url, params=data, verify=False)
                json_dict = r.json()
                task_name = json_dict['result']['data'][0]['fields']['name']
                task_id = json_dict['result']['data'][0]['id']
                return {"name": task_name, "id": task_id}
            else:
                return "Неизвестен"
        except Exception as e:
            print('При получении имени задачи произошла ошибка: ', e)
            return None

    def __gettaskinfo(self, value, act=None):
        try:
            if value is not None:
                url = '{0}/api/maniphest.search'.format(self.server)
                data = {
                    "api.token": self.phab_api,
                    "constraints[ids][0]": value,
                    "attachments[projects]": "true"
                }
                r = requests.post(url, params=data, verify=False)
                json_dict = r.json()
                if len(json_dict['result']['data']) > 0:
                    if act == "prioritycheck":
                        priority = json_dict['result']['data'][0]['fields']['priority']['value']
                        return priority
                    name = json_dict['result']['data'][0]['fields']['name']
                    desc = json_dict['result']['data'][0]['fields']['description']['raw']
                    if desc is None:
                        desc = "Не установлен"
                    priority = self.__getpriority(json_dict['result']['data'][0]['fields']['priority']['value'])[0]
                    status = self.__getstatus(json_dict['result']['data'][0]['fields']['status']['value'])
                    author = self.__whois(json_dict['result']['data'][0]['fields']['authorPHID'])['realname']
                    owner = self.__whois(json_dict['result']['data'][0]['fields']['ownerPHID'])['realname']
                    if owner is None:
                        owner = "Не установлен"
                    created = datetime.fromtimestamp(json_dict['result']['data'][0]['fields']['dateCreated'])
                    projects_phids = json_dict['result']['data'][0]['attachments']['projects']['projectPHIDs']
                    projects_list = list()
                    for project in projects_phids:
                        projectsumm = self.__getproject(project, "id")
                        projectstr = ("%s (%s)" % (projectsumm['project'], projectsumm['board'])
                                      ) if projectsumm['project'] is not None else projectsumm['board']
                        projects_list.append(projectstr)
                    projects = ", ".join(projects_list)
                    if projects is None:
                        projects = "Не установлены"
                    summary = {
                                  "name": name,
                                  "desc": desc,
                                  "priority": priority,
                                  "projects": projects,
                                  "status": status,
                                  "author": author,
                                  "owner": owner,
                                  "created": created
                    }
                    return summary
                else:
                    return None
            else:
                return None
        except Exception as e:
            print('При получении информации о задаче произошла ошибка: ', e)
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
            phboard = None if act != "id" else "Restricted project"
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

    def __getcommit(self, commit_id):
        if commit_id is None:
            return "Неизвестен"
        url = '{0}/api/diffusion.commit.search'.format(self.server)
        try:
            data = {
                "api.token": self.phab_api,
                "constraints[phids][0]": commit_id
            }

            comm_r = requests.post(url, params=data, verify=False)
            json_dict = comm_r.json()
            author = None
            message = None
            if len(json_dict['result']['data']) > 0:
                authorphid = json_dict['result']['data'][0]['fields']['author']['userPHID']
                author = self.__whois(authorphid)
                messagetext = json_dict['result']['data'][0]['fields']['message']
                messagescreen = (messagetext.replace("_", "\\_")
                                            .replace("*", "\\*")
                                            .replace("[", "\\[")
                                            .replace("`", "\\`")
                                            .replace("|", "\n")
                                            .replace(">", "\\>")
                                            .replace("\n\n", "\n")
                                            .replace("\n\n\n", "\n"))
                message = messagescreen[0:200] + '...' if (len(messagescreen) > 200) else messagescreen
            return {"author": author, "message": message}
        except Exception as e:
            print('При получении коммита произошла ошибка: ', e)
            return None

    @staticmethod
    def __getpriority(value):
        try:
            task_prior = {
                10: ("Whishlist", "wishlist", "wishlist"),
                25: ("Низкий", "низким", "низкого"),
                50: ("Средний", "средним", "среднего"),
                80: ("Высокий", "высоким", "высокого"),
                90: ("Срочный", "срочным", "срочного"),
                100: ("Наивысший", "наивысшим", "наивысшего")
            }.get(value, ("Неопределенный", "неопределенным", "неопределенного"))
            return task_prior
        except Exception as e:
            print('При получении приоритета произошла ошибка: ', e)
            return None

    @staticmethod
    def __getstatus(value):
        try:
            task_status = {"open": "Открыт",
                           "resolved": "Решен",
                           "wontfix": "Wontfix",
                           "invalid": "Некорректен",
                           "spite": "Spite",
                           "analytics": "Аналитика",
                           "testing": "Тестирование",
                           "todo": "TODO",
                           "verified": "Верифицирован",
                           "projecting": "Проектирование",
                           "inprogress": "В работе",
                           "stalled": "Затянут",
                           "complete": "Завершен"
                           }.get(value, "неопределенный")
            return task_status
        except Exception as e:
            print('При получении статуса произошла ошибка: ', e)
            return None

    def __parse_results(self, json_dict, act, board):
        try:
            if act == "new":
                new_tasks = {}
                if 1 not in self.settings:
                    if len(json_dict['result']['data']) > 0:
                        for i in range(len(json_dict['result']['data'])):
                            author = json_dict['result']['data'][i]['fields']['authorPHID']
                            if author in self.ignored_users:
                                new_tasks[i] = None
                                continue
                            board = self.__getproject(board, "id")['board']
                            project = self.__getproject(board, "id")['project']
                            task_id = json_dict['result']['data'][i]['id']
                            task_name = json_dict['result']['data'][i]['fields']['name']
                            prior = int(json_dict['result']['data'][i]['fields']['priority']['value'])
                            if prior in self.priorities:
                                continue
                            task_prior = TaskGetter.__getpriority(prior)[1]
                            owner = json_dict['result']['data'][i]['fields']['ownerPHID']
                            task_owner = self.__whois(owner)
                            task_owner_tg = TaskGetter.gentglink(task_owner['telegram'])
                            task_owner_str = task_owner['realname'] + task_owner_tg
                            task_author = self.__whois(author)
                            task_author_tg = TaskGetter.gentglink(task_author['telegram'])
                            task_author_str = task_author['realname'] + task_author_tg
                            task_summary = {"task_id": task_id,
                                            "board": board,
                                            "project": project,
                                            "name": task_name,
                                            "priority": task_prior,
                                            "owner": task_owner_str,
                                            "author": task_author_str
                                            }
                            new_tasks[i] = task_summary
                        return new_tasks
                    else:
                        return None
                else:
                    return None

            elif act == "upd":
                upd_tasks = {}
                if len(json_dict['result']['data']) > 0:
                    for i in range(len(json_dict['result']['data'])):
                        task_id = json_dict['result']['data'][i]['id']
                        task_prior = self.__gettaskinfo(task_id, "prioritycheck")
                        if task_prior in self.priorities:
                            continue
                        upd_tasks[i] = task_id
                    return upd_tasks
                else:
                    return None
        except Exception as e:
            print('При парсинге результатов произошла ошибка: ', e)
            return None

    @staticmethod
    def gentglink(tgstr):
        if tgstr is None:
            return ""
        if tgstr.endswith("/"):
            tgstr = tgstr[0:-1]
        remove_tme = re.split(r'/', tgstr)[-1]
        atsymb = "" if remove_tme.startswith("@") else "@"
        telegramstr = " (%s%s)" % (atsymb, remove_tme)
        return telegramstr

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
                        if int(task['result'][curr_id][j]['dateCreated']) < task_time:
                            continue
                        if task['result'][curr_id][j]['authorPHID'] in self.ignored_users:
                            continue
                        name = self.__gettaskname(task['result'][curr_id][j]['taskID'], "id")
                        if task['result'][curr_id][j]['transactionType'] == "reassign":
                            if 3 not in self.settings:
                                task_id = task['result'][curr_id][j]['taskID']
                                oldowner = self.__whois(task['result'][curr_id][j]['oldValue'])
                                oldownerstr = oldowner['realname'] + TaskGetter.gentglink(oldowner['telegram'])
                                newowner = self.__whois(task['result'][curr_id][j]['newValue'])
                                newownerstr = newowner['realname'] + TaskGetter.gentglink(newowner['telegram'])
                                upd_summary[curr_num] = {"action": "reassign",
                                                         "name": name['name'],
                                                         "task_id": task_id,
                                                         "oldowner": oldownerstr,
                                                         "newowner": newownerstr}
                                curr_num += 1
                        if task['result'][curr_id][j]['transactionType'] == "core:columns":
                            if 2 not in self.settings:
                                board = task['result'][curr_id][j]['newValue'][0]['boardPHID']
                                columnphid = task['result'][curr_id][j]['newValue'][0]['columnPHID']
                                column = self.__getcolname(columnphid)
                                if (board not in self.ignored_boards) and \
                                        (column['column'] not in self.ignored_columns):
                                    task_id = task['result'][curr_id][j]['taskID']
                                    upd_summary[curr_num] = {"action": "move",
                                                             "name": name['name'],
                                                             "task_id": task_id,
                                                             "column": column['column'],
                                                             "board": column['board'],
                                                             "project": column['project']}
                                    curr_num += 1
                        if task['result'][curr_id][j]['transactionType'] == "priority":
                            if 4 not in self.settings:
                                task_id = task['result'][curr_id][j]['taskID']
                                old_value = int(task['result'][curr_id][j]['oldValue'])
                                new_value = int(task['result'][curr_id][j]['newValue'])
                                old_prior = TaskGetter.__getpriority(old_value)[2]
                                new_prior = TaskGetter.__getpriority(new_value)[2]
                                subject = "повышен" if old_value < new_value else "понижен"
                                upd_summary[curr_num] = {"action": "priority",
                                                         "name": name['name'],
                                                         "task_id": task_id,
                                                         "subject": subject,
                                                         "old_prior": old_prior,
                                                         "new_prior": new_prior}
                                curr_num += 1
                        if task['result'][curr_id][j]['transactionType'] == "core:comment":
                            if 5 not in self.settings:
                                task_id = task['result'][curr_id][j]['taskID']
                                if task['result'][curr_id][j]['comments'] is not None:
                                    replace_attach = re.sub(r'{([\s\S]+?)}', '(Вложение)',
                                                            task['result'][curr_id][j]['comments'])
                                    quote_author = re.findall(r'@(.*?)\s', replace_attach)
                                    linktext = re.findall(r'\[\[.*\|\s(.*?)]]', replace_attach)
                                    replace_links = re.sub(r'\[\[(.*?)]]',
                                                           linktext[0] if len(linktext) > 0
                                                           else "ссылка", replace_attach)
                                    comment_screen = (replace_links.replace("_", "\\_")
                                                                   .replace("*", "\\*")
                                                                   .replace("[", "\\[")
                                                                   .replace("`", "\\`")
                                                                   .replace("|", "\n")
                                                                   .replace(">", "")
                                                                   .replace("\n\n", "\n")
                                                                   .replace("\n\n\n", "\n"))
                                    bold_text = comment_screen.replace("\\*\\*", "*")
                                    comment = re.sub(r'^(^>).*', 'Цитата\n> : ' +
                                                                 quote_author[0] if len(quote_author) > 0 else
                                                                 "Неизвестный" + ' писал:', bold_text)
                                else:
                                    comment = "Комментарий удален"
                                author = self.__whois(task['result'][curr_id][j]['authorPHID'])
                                authorstr = author['realname'] + TaskGetter.gentglink(author['telegram'])
                                upd_summary[curr_num] = {"action": "comment",
                                                         "name": name['name'],
                                                         "task_id": task_id,
                                                         "comment": comment[0:200] + '...' if
                                                         (len(comment) > 200) else comment,
                                                         "author": authorstr}
                                curr_num += 1
                        if task['result'][curr_id][j]['transactionType'] == "status":
                            if 6 not in self.settings:
                                task_id = task['result'][curr_id][j]['taskID']
                                author = task['result'][curr_id][j]['authorPHID']
                                old_value = task['result'][curr_id][j]['oldValue']
                                new_value = task['result'][curr_id][j]['newValue']
                                closed_statuses = ["invalid", "resolved", "wontfix", "spite"]
                                upd_summary[curr_num] = {"action": "status",
                                                         "author": author,
                                                         "name": name['name'],
                                                         "task_id": task_id,
                                                         "old_value": old_value,
                                                         "new_value": new_value,
                                                         "closed_statuses": closed_statuses,
                                                         "rus_old_value": self.__getstatus(old_value),
                                                         "rus_new_value": self.__getstatus(new_value)
                                                         }
                                curr_num += 1
                        if task['result'][curr_id][j]['transactionType'] == "core:edge":
                            task_id = task['result'][curr_id][j]['taskID']
                            new_values = task['result'][curr_id][j]['newValue']
                            old_values = task['result'][curr_id][j]['oldValue']
                            added = list()
                            removed = list()
                            subaction = None
                            for value in new_values:
                                if 7 not in self.settings and value.split("-")[1] == "PROJ":
                                    subaction = "proj"
                                    board = self.__getproject(value, "id")
                                    added.append("*%s%s*" % (board['project'] + " - " if
                                                             board['project'] is not None
                                                             else "", board['board']))
                                if 8 not in self.settings and value.split("-")[1] == "CMIT":
                                    subaction = "cmit"
                                    commit = self.__getcommit(value)
                                    added.append("*%s*" % commit['message'])
                                if 9 not in self.settings and value.split("-")[1] == "TASK":
                                    subaction = "task"
                                    taskname = self.__gettaskname(value, "phid")
                                    added.append("[%s](%s/T%s)" % (taskname['name'], self.server, taskname['id']))
                            for value in old_values:
                                if 7 not in self.settings:
                                    if value.split("-")[1] == "PROJ":
                                        subaction = "proj"
                                        board = self.__getproject(value, "id")
                                        removed.append("*%s%s*" % (board['project'] + " - " if
                                                                   board['project'] is not None
                                                                   else "", board['board']))
                                if 9 not in self.settings:
                                    if value.split("-")[1] == "TASK":
                                        subaction = "task"
                                        taskname = self.__gettaskname(value, "phid")
                                        removed.append("[%s](%s/T%s)" % (taskname['name'], self.server, taskname['id']))
                            if subaction is not None:
                                upd_summary[curr_num] = {"action": "edge",
                                                         "subaction": subaction,
                                                         "name": name['name'],
                                                         "task_id": task_id,
                                                         "added": added,
                                                         "removed": removed}
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
                if result is None:
                    continue
                print(TaskGetter.__timenow() + ': Для чата ' + str(self.name) +
                      ' обнаружена новая задача - T' + str(result['task_id']))
                resultstr = 'На борде *{}* появилась новая задача ' \
                            'с *{}* приоритетом: \n\U0001F4CA *T{} - {}* \n' \
                            '\U0001F425 Инициатор: *{}*\n' \
                            '\U0001F425 Исполнитель: *{}*\n'.format(result['board'],
                                                                    result['priority'],
                                                                    result['task_id'],
                                                                    result['name'],
                                                                    result['author'],
                                                                    result['owner']
                                                                    )
                TaskGetter.__bot.send_message(self.chat_id, resultstr, parse_mode='Markdown',
                                              reply_markup=self.full_markup(result['task_id']))
                self.__new_ids.append(int(result['task_id']))

        elif act == "upd":
            def sendupd(head, body):
                if res_dict[result['task_id']] > 1:
                    result_messages[result['task_id']]['message'].append(
                        "\n\U0001F4DD " + body[0].upper() + body[1:]
                    )
                else:
                    print(self.__timenow() + ': Для чата ' + str(self.name) +
                          ' обнаружена обновленная задача - T' + result['task_id'])
                    TaskGetter.__bot.send_message(self.chat_id, head + body, parse_mode='Markdown',
                                                  reply_markup=self.full_markup(result['task_id']))

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
                    headstr = '\U0001F4CA В задаче *T{} - {}* '.format(result['task_id'], result['name'])
                    resultstr = 'был изменен исполнитель: \n' \
                                '\U0001F425 Предыдущий исполнитель: *{}*\n' \
                                '\U0001F425 Новый исполнитель: *{}*\n'.format(result['oldowner'],
                                                                              result['newowner'])
                    sendupd(headstr, resultstr)

                if result['action'] == "move":

                    projstr = result['project'] is not None and (result['project'] + " - ") or ""

                    headstr = '\U0001F4CA Задача *T{} - {}* '.format(result['task_id'], result['name'])
                    resultstr = 'перемещена в колонку ' \
                                '*{0}* на борде *{1}{2}*\n'.format(result['column'],
                                                                   projstr,
                                                                   result['board']
                                                                   )
                    sendupd(headstr, resultstr)

                if result['action'] == "priority":
                    headstr = '\U0001F4CA В задаче *T{} - {}* '.format(result['task_id'], result['name'])
                    resultstr = '{} приоритет ' \
                                'с *{}* до *{}*\n'.format(result['subject'],
                                                          result['old_prior'],
                                                          result['new_prior'],
                                                          )
                    sendupd(headstr, resultstr)

                if result['action'] == "comment":
                    resultstr = '\n\U0001F4AC {0} добавил(-а) комментарий: \n{1}\n'.format(result['author'],
                                                                                           result['comment']
                                                                                           )
                    if res_dict[result['task_id']] > 1:
                        result_messages[result['task_id']]['message'].append(resultstr)

                if result['action'] == "status":
                    if (result['new_value'] in result['closed_statuses'] and result['old_value'] in
                        result['closed_statuses']) or (result['new_value'] not in result['closed_statuses'] and
                                                       result['old_value'] not in result['closed_statuses']):
                        headstr = '\U0001F4CA В задаче *T{} - {}* '.format(result['task_id'], result['name'])
                        resultstr = 'изменился статус с *{}* на *{}*\n'.format(result['rus_old_value'],
                                                                               result['rus_new_value'])

                    elif result['new_value'] in result['closed_statuses'] and \
                            result['old_value'] not in result['closed_statuses']:
                        headstr = '\U0001F4CA Задача *T{} - {}* '.format(result['task_id'], result['name'])
                        resultstr = 'закрыта со статусом *{0}* \n'.format(result['rus_new_value'])

                    elif result['new_value'] not in result['closed_statuses'] and \
                            result['old_value'] in result['closed_statuses']:
                        headstr = '\U0001F4CA Задача *T{} - {}* '.format(result['task_id'], result['name'])
                        resultstr = 'переоткрыта со статусом *{0}* \n'.format(result['rus_new_value'])

                    else:
                        headstr = '\U0001F4CA В задаче *T{} - {}* '.format(result['task_id'], result['name'])
                        resultstr = 'изменился статус с *{0}* на *{1}*\n'.format(result['rus_old_value'],
                                                                                 result['rus_new_value'])

                    sendupd(headstr, resultstr)

                if result['action'] == "edge":
                    if len(result['added']) > 0 or len(result['removed']) > 0:
                        headstr = '\U0001F4CA В задаче *T{} - {}* '.format(result['task_id'], result['name'])
                        added_str = str()
                        removed_str = str()
                        subaction_word = {
                            "proj": ["тег", "теги"],
                            "cmit": ["коммит", "коммиты"],
                            "task": ["связанная задача", "связанные задачи"]
                        }.get(result['subaction'], None)
                        if len(result['added']) > 0:
                            if len(result['added']) == 1:
                                added = "добавлена" if result['subaction'] == "task" else "добавлен"
                                added_str = '%s %s: %s' % (added, subaction_word[0], ', '.join(result['added']))
                            else:
                                added_str = 'добавлены %s: %s' % (subaction_word[1], ', '.join(result['added']))
                        if len(result['removed']) > 0:
                            if len(result['removed']) == 1:
                                removed_str = 'удален %s: %s' % (subaction_word[0], ', '.join(result['removed']))
                            else:
                                removed_str = 'удалены %s: %s' % (subaction_word[1], ', '.join(result['removed']))
                        resultstr = added_str + (", " if (len(added_str) > 0 and
                                                          len(removed_str) > 0) else "") + removed_str + "\n"
                        sendupd(headstr, resultstr)

            for message in result_messages.values():
                messagestr = ""
                for actions in message['message']:
                    messagestr += actions
                print(TaskGetter.__timenow() + ': Для чата ' + str(self.name) +
                      ' обнаружена обновленная задача - T' + message['id'])
                resultstr = '\U0001F4CA В задаче *T{} - {}* произошли изменения:\n ' \
                            '{} \n'.format(message['id'],
                                           message['name'],
                                           messagestr)
                TaskGetter.__bot.send_message(self.chat_id, resultstr, parse_mode='Markdown',
                                              reply_markup=self.full_markup(message['id']))

    def __tasks_search(self):
        def search_worker(board, watchtype):
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
            }

            if watchtype == 1:
                data.update({"constraints[projects][0]": board})
            elif watchtype == 2:
                data.update({"constraints[assigned][0]": board})
            else:
                data.update({"constraints[projects][0]": board})

            data.update({"constraints[createdStart]": last_new})
            new_r = search()
            data.pop("constraints[createdStart]")
            data.update({"constraints[modifiedStart]": last_update})

            upd_r = search()

            self.last_new_check[board] = TaskGetter.__serverdate_to_timestamp(new_r.headers['date'])
            self.last_update_check[board] = TaskGetter.__serverdate_to_timestamp(upd_r.headers['date'])
            TaskGetter.__config.dump()

            new_parsed = self.__parse_results(new_r.json(), "new", board)
            upd_parsed = self.__parse_results(upd_r.json(), "upd", board)

            if new_parsed is not None:
                self.__send_results(new_parsed, "new")

            if upd_parsed is not None:
                if upd_parsed not in self.__sended_ids:
                    self.__sended_ids.append(upd_parsed)
                    updated_tasks = self.__getupdates(upd_parsed, last_update)
                    if updated_tasks is not None:
                        self.__send_results(updated_tasks, "upd")

        self.__sended_ids.clear()

        if self.watchtype is None:
            for board in self.boards:
                search_worker(board, 1)
        elif self.watchtype == 1:
            for board in self.boards:
                search_worker(board, 1)
        elif self.watchtype == 2:
            search_worker(self.__whoaim(), 2)
        else:
            for board in self.boards:
                search_worker(board, 1)
            search_worker(self.__whoaim(), 2)

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
    def schedule(chat_id: int or None = None, sudo=False):
        def schedule_task(config):
            if not config.get('active'):
                return
            task_getter = TaskGetter(config)
            assert task_getter.chat_id is not None
            if TaskGetter.__active_tasks.get(task_getter.chat_id):
                return
            task_getter.tasks_search()
            TaskGetter.__active_tasks[task_getter.chat_id] = \
                schedule.every(task_getter.frequency or 2).minutes.do(task_getter.tasks_search)

        if chat_id is not None:
            chat_config = TaskGetter.__config.chat(chat_id)
            if not sudo:
                TaskGetter.__bot.send_message(chat_config.get('chat_id'), "\u2705 Мониторинг запущен"
                                              if not chat_config.get('active') else "\u26A1 Мониторинг уже запущен")
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
    def info(chat_id: int or None = None, value=False):
        def get_info(config):
            task_getter = TaskGetter(config)
            assert task_getter.chat_id is not None
            info = task_getter.__gettaskinfo(value)
            return info
        if chat_id is not None:
            return get_info(TaskGetter.__config.chat(chat_id))
        else:
            pass

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
