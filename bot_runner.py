from requests.packages.urllib3.exceptions import InsecureRequestWarning
import requests
import telebot
import re
import logging
import os
from phabbot.config import Config
from phabbot.task_getter import TaskGetter
from time import strftime, localtime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

logger = telebot.logger
telebot.logger.setLevel(logging.WARNING)

CHAT_STATE_SET_SERVER = "set_server"
CHAT_STATE_SET_PHABAPI = "set_phab_api"
CHAT_STATE_SET_BOARDS = "set_boards"
CHAT_STATE_REMOVE_BOARDS = "remove_boards"
CHAT_STATE_SET_FREQUENCY = "set_frequency"
CHAT_STATE_WATCHTYPES = "set_watchtypes"
CHAT_STATE_SET_IGNORED_BOARDS = "set_ignored_boards"
CHAT_STATE_REMOVE_IGNORED_BOARDS = "remove_ignored_boards"
CHAT_STATE_SET_IGNORED_COLUMNS = "set_ignored_columns"
CHAT_STATE_REMOVE_IGNORED_USERS = "remove_ignored_users"
CHAT_STATE_REMOVE_IGNORED_COLUMS = "remove_ignored_columns"
CHAT_STATE_IGNORED_USERS = "set_ignored_users"
CHAT_STATE_GET_PROJECT_ID = "get_project_id"
CHAT_STATE_BACK = "back"


config = Config.load()
assert isinstance(config, Config)
tg_api = config.get('tg_api')
assert isinstance(tg_api, str)
bot = telebot.AsyncTeleBot(tg_api)
state = {}


def __extract_args(command_text: str):
    args = command_text.split()[1:]
    if not args:
        return None
    return args


def getname(message):
    title = message.chat.title
    if not title:
        title = r"%s %s (@%s)" % (message.chat.first_name, message.chat.last_name, message.chat.username)
    config.set_name(message.chat.id, title)


@bot.message_handler(commands=['start'])
def start(message):
    menu(message)
    bot.send_message(message.chat.id, 'Для начала работы бота вам необходимо сконфигурировать бота.'
                                      '\nНеобходимые для конфигурации настройки помечены в главном меню звёздочкой, '
                                      'остальные настраиваются по желанию'
                                      '\nПосле окончания конфигурации введите <b>"/schedule"</b>, чтобы '
                                      'начать отслеживание', parse_mode="HTML")


@bot.message_handler(commands=['help'])
def help_message(message):
    bot.send_message(message.chat.id,
                     'Привет! Я оповещаю об обновленях задач в фабрикаторе.'
                     '\n\n<b>Основные команды:</b>'
                     '\n/help - показать доступные команды (Текущее сообщение)'
                     '\n/project_id Название - получить PHID борда для дальнейшей конфигурации'
                     '\n/status - статус мониторинга'
                     '\n/schedule - запустить мониторинг'
                     '\n/unschedule - приостановить мониторинг'
                     '\n/where_apitoken - инструкция по получению API-Токена'
                     '\n\n<b>Показать текущие настройки:</b>'
                     '\n/menu - отобразить главное меню'
                     '\n/phab_api - отобразить текущий API-Токен'
                     '\n/frequency - отобразить текущую частоту обращения к серверу (в минутах)'
                     '\n/boards - отобразить борды, которые мониторятся'
                     '\n/ignored_boards - отобразить список идентификаторов бордов, '
                     'обновления в которых игнорируются'
                     '\n/ignored_columns - отобразить список названий колонок, '
                     'перемещения в которые игнорируются'
                     '\n\n<b>Настройка:</b>'
                     '\n/reset_ignored_boards - сбросить список игнорируемых бордов '
                     '\n/reset_ignored_boards - сбросить список игнорируемых колонок '
                     '\n\n<b>Диагностика:</b>'
                     '\n/last_check - штампы времени последней проверки', parse_mode='HTML')


@bot.message_handler(commands=['schedule'])
def schedule(message):
    getname(message)
    if checkconfig(message, "check"):
        TaskGetter.schedule(message.chat.id)


@bot.message_handler(commands=['unschedule'])
def unschedule(message):
    TaskGetter.unschedule(message.chat.id)


@bot.message_handler(commands=['reset'])
def reset():
    pass


@bot.message_handler(commands=['sudo'])
def sudo(message):
    if message.from_user.id not in config.superusers:
        bot.send_message(message.chat.id, "Вы не являетесь администратором. Забудьте эту команду.")
        return
    args = __extract_args(message.text)
    if not args:
        return

    if args[0] == 'send_message':
        send_message(' '.join(args[1:]))
    if args[0] == 'get_board':
        bot.send_message(message.chat.id, getptojectname(message, "phids", args[1:]), parse_mode='HTML')
    if args[0] == 'users':
        get_users(message)
    if args[0] == 'checknow':
        TaskGetter.schedule(message.chat.id, sudo=True)
    if args[0] == 'send_message_anons':
        send_message_anons(' '.join(args[1:]), message.chat.id)


def send_message(message):
    [bot.send_message(chat['chat_id'], message) for chat in config.get('chats')]


def send_message_anons(message, chat_id):
    count = 0
    for chat in config.get('chats'):
        if not chat.get('name'):
            bot.send_message(chat['chat_id'], message)
            count += 1
    bot.send_message(chat_id, "Сообщение *%s* отправлено %s людям" % (message, count), parse_mode='Markdown')


def get_users(message):
    userslist = "<b>Список пользователей:</b>\n"
    count = 0
    for chat in config.get('chats'):
        count += 1
        userslist += "<b>%s</b>: %s\n" % (count, chat.get('name') or chat['chat_id'])
    bot.send_message(message.chat.id, userslist, parse_mode='HTML')


@bot.message_handler(commands=['status'])
def status(message):
    activestr = "Активен" if config.active(message.chat.id) else "Отдыхает"
    emoji = "\u2705" if config.active(message.chat.id) else "\u274C"
    bot.send_message(message.chat.id, "%s Статус мониторинга: %s" % (emoji, activestr))


@bot.message_handler(commands=['checkconfig'])
def checkconf(message):
    checkconfig(message, "check")


def checkconfig(message, act, skip=None):
    chatid = message.chat.id
    if skip is None:
        skip = []
    if act == "check":
        if not config.get('server') or not config.server(chatid):
            if "msg" not in skip:
                bot.send_message(chatid, "Для начала работы бота необходимо ввести "
                                         "адрес сервера в главном меню (/menu)", parse_mode='HTML')
            return False
        if not config.phab_api(chatid):
            if "msg" not in skip:
                bot.send_message(chatid, "Для начала работы бота необходимо ввести API-токен в "
                                         "главном меню (/menu).\n"
                                         "Чтобы узнать, как получить API-Токен введите "
                                         "команду <b>/where_apitoken</b>", parse_mode='HTML')
            return False
        if "boards" not in skip:
            if not config.boards(chatid) and config.watchtype(chatid) != 2:
                if "msg" not in skip:
                    bot.send_message(chatid, "Для начала работы бота необходимо ввести PHIDы "
                                             "бордов которые необходимо мониторить "
                                             "в главном меню (/menu) "
                                             "\nДля того, чтобы узнать ID борда "
                                             "введите команду пройдите в меню "
                                             "\"Борды\" - \"Узнать PHID\"", parse_mode='HTML')
                return False
        try:
            url = config.get('server') + '/api/user.whoami'
            data = {
                "api.token": config.phab_api(chatid)
            }
            result = requests.post(url, params=data, allow_redirects=False, verify=False)
            if not result:
                if "msg" not in skip:
                    bot.send_message(chatid, "Проверьте правильность указания адреса фабрикатора")
                return False
            if result.headers['Content-Type'] != 'application/json':
                if "msg" not in skip:
                    bot.send_message(chatid, "Проверьте правильность указания адреса фабрикатора")
                return False
            json = result.json()
            if json['error_code'] == 'ERR-INVALID-AUTH':
                err = json['error_info']
                if "msg" not in skip:
                    bot.send_message(chatid, "Произошла ошибка: " + err +
                                     "\n\n*Проверьте правильнfость введенного API-Токена и повторите попытку*",
                                     parse_mode="Markdown")
                return False
            if "activated" in json['result']['roles']:
                return True
        except requests.exceptions.ConnectionError:
            if "msg" not in skip:
                bot.send_message(chatid, "Проверьте правильность введенного адреса сервера")
            return False
        except Exception as e:
            if "msg" not in skip:
                bot.send_message(chatid, "При попытке подключиться к серверу произошла ошибка: " + str(e) +
                                         "\n\n*Проверьте правильность указания адреса фабрикатора*",
                                 parse_mode="Markdown")
            return False

    if act == "add":
        if config.active(chatid):
            return
        if (config.boards(chatid) or (config.watchtype(chatid) == 2)) and \
                config.server(chatid) and config.phab_api(chatid):
            bot.send_message(chatid, "\u2705 <b>Вы ввели необходимые настройки для запуска бота, "
                                     "производится запуск бота."
                                     "\nТак-же, вы можете продолжить более тонкую "
                                     "настройку бота в главном меню (/menu)",
                             parse_mode='HTML')
            schedule(message)


def whoami(message):
    if not checkconfig(message, "check"):
        return False
    url = config.get('server') + '/api/user.whoami'
    data = {
        "api.token": config.phab_api(message.chat.id)
    }
    result = requests.post(url, params=data, allow_redirects=False, verify=False)
    json = result.json()
    phid = json['result']
    return phid


def getcolumns(chatid):
    columns_list = config.ignored_columns(chatid)
    result_list = str()
    if len(columns_list) > 0:
        for i in range(len(columns_list)):
            result_list += "%s. *%s* \n" % (i + 1, columns_list[i])
        return result_list
    else:
        return "Список пуст\n"


def getptojectname(message, act, phids):
    chatid = message.chat.id
    if phids and len(phids) > 0:
        defaultstr = str()
        for phid in phids:
            defaultstr += "\n*Неизвестен:* `" + phid + "`"
        if not checkconfig(message, "check"):
            return defaultstr
        result = str()
        count = 1
        for phid in phids:
            url = '{0}/api/project.search'.format(config.server(chatid))
            data = {
                "api.token": config.phab_api(chatid),
                "constraints[phids][0]": phid
            }
            r = requests.post(url, params=data, verify=False)
            json = r.json()
            name = json['result']['data'][0]['fields']['name'] if len(json['result']['data']) else "Неизвестен"
            myname = "Неизвестен"
            if not phid.startswith('PHID'):
                who = whoami(message)
                if who['userName'] == phid:
                    myname = "Задачи на мне"
            if len(json) > 0:
                if act == "phids":
                    if phid.startswith('PHID'):
                        result += "*%s. %s:* `%s`\n" % (count, name, phid)
                    else:
                        result += "*%s. %s* \n" % (count, myname)
                    count += 1
                if act == "ts":
                    time = strftime("%H:%M:%S", localtime(phids[phid]))
                    if phid.startswith('PHID'):
                        result += "*%s:* %s\n" % (name, time)
                    else:
                        result += "*%s:* %s\n" % (myname, time)
        if len(result) > 0:
            return result
    return "Список пуст\n"


def getusername(message, phids):
    chatid = message.chat.id
    if phids and len(phids) > 0:
        defaultstr = str()
        for phid in phids:
            defaultstr += "\n*Неизвестен: * `" + phid + "`"
        if not checkconfig(message, "check"):
            return defaultstr
        result = str()
        count = 1
        for phid in phids:
            url = '{0}/api/user.search'.format(config.server(chatid))
            data = {
                "api.token": config.phab_api(chatid),
                "constraints[phids][0]": phid
            }
            r = requests.post(url, params=data, verify=False)
            json = r.json()
            name = json['result']['data'][0]['fields']['realName'] if len(json['result']['data']) else "Неизвестен"
            if len(json) > 0:
                result += "%s. *%s:* `%s`\n" % (count, name, phid)
                count += 1
        if len(result) > 0:
            return result
    return "Список пуст\n"


@bot.message_handler(commands=['project_id'])
def get_project(message):
    if checkconfig(message, "check", "boards"):
        markup = InlineKeyboardMarkup()
        markup.row_width = 1
        markup.add(InlineKeyboardButton("Ввести другое название", callback_data='project_id'),
                   InlineKeyboardButton("Вернуться в главное меню", callback_data=CHAT_STATE_BACK)
                   )
        args = message.text
        if args is not None:
            url = '{0}/api/project.search'.format(config.server(message.chat.id))
            data = {
                "api.token": config.phab_api(message.chat.id),
                "constraints[name]": args,
            }
            r = requests.post(url, params=data, verify=False)
            result = r.json()
            if len(result['result']['data']) > 0:
                resultstr = 'Результат поиска:\n'
                count = 1
                for i in range(len(result['result']['data'])):
                    if result['result']['data'][i]['fields']['color']['key'] != "disabled":
                        if count > 50:
                            resultstr += "\nВнимание! Показаны первые 50 результатов. " \
                                         "Если искомого борда нет в списке уточните запрос\n"
                            break
                        phid = result['result']['data'][i]['phid']
                        depth = result['result']['data'][i]['fields']['depth']
                        pname = (result['result']['data'][i]['fields']['parent']['name']) if depth != 0 else None
                        name = result['result']['data'][i]['fields']['name']
                        resultname = ((pname.replace("*", "'") + " - ") if int(depth) >= 1 else
                                      "") + name.replace("*", "'")
                        resultstr += "%s. *%s:* `%s`\n" % (count, resultname, phid)
                        count += 1
                footer = "\nСкопируйте этот PHID и введите его в главном меню в " \
                         "разделе *\"Борды\"* или в меню *\"Исключения\"*"
                bot.send_message(message.chat.id, resultstr + footer, parse_mode='Markdown',
                                 reply_markup=back_boards_markup())
            else:
                bot.send_message(message.chat.id, "Проекты с таким именем не найдены", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Введите название проекта", reply_markup=markup)


def get_images(chat_id, ids):
    links = list()
    imgnames = list()
    imgids = list()
    imglist = list()
    url = '{0}/api/file.search'.format(config.server(chat_id))
    data = {
        "api.token": config.phab_api(chat_id),
    }
    for imgid in range(len(ids)):
        data['constraints[ids][' + str(imgid) + ']'] = ids[imgid]
    r = requests.post(url, params=data, verify=False)
    result = r.json()
    result['result']['data'].reverse()
    imgformats = {".png", ".jpg", ".jpeg", ".gif", ".tiff", ".bmp"}
    for i in range(len(result['result']['data'])):
        for imgformat in imgformats:
            if result['result']['data'][i]['fields']['name'].lower().endswith(imgformat):
                imgids.append(result['result']['data'][i]['id'])
                imgnames.append(result['result']['data'][i]['fields']['name'])
                links.append(result['result']['data'][i]['fields']['dataURI'])
    media = []
    for link in range(len(links)):
        url = links[link]
        r = requests.get(url, allow_redirects=True, verify=False)
        filename = '%s-%s-%s' % (chat_id, link, imgnames[link])
        open(filename, 'wb').write(r.content)
        media.append(InputMediaPhoto(open(filename, 'rb'), caption="Изображение " + str(link + 1)))
        imglist.append(filename)
    return {"imglist": imglist, "imgids": imgids,  "media": media}


@bot.message_handler(commands=['info'])
def get_info(message):
    if checkconfig(message, "check", "boards"):
        args = [message.text]
        if args[0].lower().startswith('t'):
            args[0] = args[0][1:]
        if args[0] is not None:
            info = TaskGetter.info(message.chat.id, args[0])
            if info is not None:
                file_ids = re.findall(r'{F([\s\S]+?)}', info['desc'])
                images = get_images(message.chat.id, file_ids)
                replace_imgs = (info['desc'].replace("_", "\\_")
                                            .replace("*", "\\*")
                                            .replace("[", "\\[")
                                            .replace("`", "\\`")
                                            .replace("|", "\n")
                                            .replace(">", "")
                                            .replace("\n\n", "\n")
                                            .replace("\n\n\n", "\n"))
                projectstr = (info['projects'].replace("_", "\\_")
                                              .replace("*", "\\*")
                                              .replace("[", "\\[")
                                              .replace("`", "\\`"))
                namestr = (info['name'].replace("_", "\\_")
                                       .replace("*", "\\*")
                                       .replace("[", "\\[")
                                       .replace("`", "\\`"))
                for imgid in range(len(images['imglist'])):
                    replace_imgs = re.sub(r'{F' + str(images['imgids'][imgid]) + '}',
                                          '*(Изображение ' + str(imgid + 1) + ')*',
                                          replace_imgs)
                replace_attach = re.sub(r'{F([\s\S]+?)}', '*(Вложение)*', replace_imgs)
                result_desc = replace_attach.replace("\\*\\*", "*")
                if len(result_desc) > 1000:
                    result_desc = result_desc[0:1000]
                    result_desc = result_desc + "... *текст обрезан, полная версия по ссылке ниже*"
                if result_desc.count('*') % 2 != 0:
                    result_desc = result_desc + "*"
                str_message = ("\U0001F4CA *Задача Т%s:* %s \n\n"
                               "\U0001F4C5 *Дата создания:* %s \n\n"
                               "\U0001F4C8 *Приоритет:* %s \n\n"
                               "\U0001F4CC *Статус:* %s \n\n"
                               "\U0001F425 *Автор:* %s \n\n"
                               "\U0001F425 *Исполнитель:* %s \n\n"
                               "\U0001F3E2 *Теги:* %s \n\n"
                               "\U0001F4CB *Описание:* \n%s \n\n") % (args[0],
                                                                      namestr,
                                                                      info['created'].strftime("%d.%m.%Y %H:%M"),
                                                                      info['priority'],
                                                                      info['status'],
                                                                      info['author'],
                                                                      info['owner'],
                                                                      projectstr,
                                                                      result_desc)
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("Открыть задачу",
                                                url="%s/T%s" % (config.server(message.chat.id), args[0])))

                bot.send_chat_action(message.chat.id, 'typing')
                bot.send_message(message.chat.id, str_message, parse_mode='Markdown', reply_markup=markup)
                bot.send_chat_action(message.chat.id, 'upload_photo')
                bot.send_media_group(message.chat.id, images['media'])
                for img in images['imglist']:
                    if os.path.exists(img):
                        os.remove(img)

            else:
                bot.send_message(message.chat.id, "Задачи с таким ID не найдены или у вас нет к ним доступа")
        else:
            bot.send_message(message.chat.id, "Задачи с таким ID не найдены или у вас нет к ним доступа")


@bot.message_handler(commands=['user_id'])
def get_user(message):
    if checkconfig(message, "check", "boards"):
        args = __extract_args(message.text)
        if args is not None:
            args = ' '.join(args)
            url = '{0}/api/user.search'.format(config.server(message.chat.id))
            data = {
                "api.token": config.phab_api(message.chat.id),
                "constraints[nameLike]": args,
            }
            r = requests.post(url, params=data, verify=False)
            result = r.json()
            if len(result['result']['data']) > 0:
                resultstr = 'Результат поиска:\n'
                for i in range(len(result['result']['data'])):
                    if "activated" in result['result']['data'][i]['fields']['roles']:
                        phid = result['result']['data'][i]['phid']
                        name = result['result']['data'][i]['fields']['realName']
                        resultstr += "*" + name + ":* `" + phid + "`\n"
                footer = "\n\nВведите этот PHID в меню *\"Исключения\"*"
                bot.send_message(message.chat.id, resultstr + footer, parse_mode='Markdown',
                                 reply_markup=back_ignore_markup())
            else:
                bot.send_message(message.chat.id, "Пользователи с таким именем не найдены")
        else:
            bot.send_message(message.chat.id, "Введите имя пользователя")


def ignore_markup():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton("Добавить борды", callback_data=CHAT_STATE_SET_IGNORED_BOARDS),
               InlineKeyboardButton("Удалить борды", callback_data=CHAT_STATE_REMOVE_IGNORED_BOARDS),
               InlineKeyboardButton("Добавить колонки", callback_data=CHAT_STATE_SET_IGNORED_COLUMNS),
               InlineKeyboardButton("Удалить колонки", callback_data=CHAT_STATE_REMOVE_IGNORED_COLUMS),
               InlineKeyboardButton("Добавить юзеров", callback_data=CHAT_STATE_IGNORED_USERS),
               InlineKeyboardButton("Удалить юзеров", callback_data=CHAT_STATE_REMOVE_IGNORED_USERS),
               InlineKeyboardButton("Вернуться в главное меню", callback_data=CHAT_STATE_BACK)
               )
    return markup


def back_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Вернуться в главное меню", callback_data=CHAT_STATE_BACK))
    return markup


def back_usrignore_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("В \"исключения\"", callback_data="ignored"),
               InlineKeyboardButton("Добавить себя", callback_data="ignoremyself")
               )
    return markup


def back_ignore_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("В меню", callback_data=CHAT_STATE_BACK),
               InlineKeyboardButton("В \"исключения\"", callback_data="ignored")
               )
    return markup


def back_boards_markup():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton("В \"борды\"", callback_data=CHAT_STATE_SET_BOARDS),
               InlineKeyboardButton("В \"исключения\"", callback_data="ignored"),
               InlineKeyboardButton("Найти другой проект", callback_data="project_id")
               )
    return markup


@bot.message_handler(commands=['menu'])
def menu(message):
    global state
    state[message.chat.id] = None
    markup = InlineKeyboardMarkup()
    api_star = " *" if not config.phab_api(message.chat.id) else ""
    boards_star = " *" if not config.boards(message.chat.id) and config.watchtype(message.chat.id) != 2 else ""
    markup.add(InlineKeyboardButton("API-Токен" + api_star, callback_data=CHAT_STATE_SET_PHABAPI),
               InlineKeyboardButton("Борды" + boards_star, callback_data=CHAT_STATE_SET_BOARDS),
               InlineKeyboardButton("Что отслеживать", callback_data=CHAT_STATE_WATCHTYPES),
               InlineKeyboardButton("Частота опроса", callback_data=CHAT_STATE_SET_FREQUENCY),
               InlineKeyboardButton("Исключения", callback_data="ignored"),
               InlineKeyboardButton("Настройки", callback_data="settings")
               )

    bot.send_message(message.chat.id,
                     ("*Главное меню бота*\n\n"
                      "%s Статус мониторинга: %s\n"
                      "%s"
                      "\n\U0001F3E0 Адрес фабрикатора: %s\n" 
                      "\n\u23F0 Частота опроса сервера (минуты): %s\n"
                      "\n\U0001F4CC Отслеживаются: %s\n"
                      "%s" 
                      "\nВ меню *\"Исключения\"* вы можете настроить игнорирование пользователей, "
                      "перемещений по определенным бордам или колонкам\n"
                      "\nВ меню *\"Настройки\"* вы можете выбрать уведомления каких типов хотите получать\n"
                      "\n*Выберите, что вы хотите настроить:* ") % (
                      "\u2705" if config.active(message.chat.id) else "\u274C",
                      "Активен (Остановить: /unschedule)" if config.active(message.chat.id) else
                      "Отдыхает (Запустить: /schedule)",
                      "\n\U0001F534 *Для начала работы установите настройки, помеченные звездочками*\n" if
                      (not config.phab_api(message.chat.id) or not config.boards(message.chat.id)) and
                      config.watchtype(message.chat.id) != 2 else "",
                      config.server(message.chat.id) if checkconfig(message, "check", ["boards", "msg"]) else
                      "Скрыт",
                      config.frequency(message.chat.id) or "2 (Стандартное значение)",
                      {
                          1: "Задачи на бордах",
                          2: "Задачи на мне",
                          3: "Задачи на бордах и на мне"
                      }.get(config.watchtype(message.chat.id), "Задачи на бордах"),
                      ("\n\U0001F440 Отслеживаемые борды: \n" + (getptojectname(message, "phids",
                                                                                config.boards(message.chat.id)) or
                                                                 "Список пуст\n")) if
                      config.watchtype(message.chat.id) != 2 else ""
                     ), parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    def set_chat_state(chat_state):
        global state
        assert state is not None
        state[call.message.chat.id] = chat_state
    if call.data == CHAT_STATE_SET_SERVER:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите адрес фабрикатора в формате <b>"https://some.adress"</b>:',
                         parse_mode='HTML', reply_markup=back_markup())
        set_chat_state(CHAT_STATE_SET_SERVER)
    elif call.data == CHAT_STATE_SET_PHABAPI:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите ваш API-Токен. Чтобы узнать, как его '
                                               'получить введите /where_apitoken:',
                         parse_mode='HTML', reply_markup=back_markup())
        set_chat_state(CHAT_STATE_SET_PHABAPI)
    elif call.data == CHAT_STATE_SET_BOARDS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Вернуться в меню", callback_data=CHAT_STATE_BACK),
                   InlineKeyboardButton("Удалить борды", callback_data=CHAT_STATE_REMOVE_BOARDS),
                   InlineKeyboardButton("Узнать PHID", callback_data='project_id')
                   )
        bot.send_message(call.message.chat.id, 'Отправьте в чат через пробел PHIDы бордов, за которыми хотите '
                                               'наблюдать.\nPHIDы бордов можно узнать, '
                                               'нажав на кнопку \"Узнать PHID\"\n\n',
                         parse_mode='HTML', reply_markup=markup)
        set_chat_state(CHAT_STATE_SET_BOARDS)
    elif call.data == CHAT_STATE_REMOVE_BOARDS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "\U0001F648 Борды, которые подключены к мониторингу: \n%s"
                                               "\nОтправьте в чат номер борда, который хотите удалить из списка:" %
                         (getptojectname(call.message, "phids", config.boards(call.message.chat.id)) or
                          "Список пуст\n"), parse_mode='Markdown', reply_markup=back_markup())
        set_chat_state(CHAT_STATE_REMOVE_BOARDS)
    elif call.data == CHAT_STATE_WATCHTYPES:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        if call.message.chat.type == "private":
            watchtypes(call.message)
        else:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Вернуться в главное меню", callback_data=CHAT_STATE_BACK))
            bot.send_message(call.message.chat.id, 'Изменение типа отслеживания поддерживается только в личных чатах',
                             parse_mode='HTML', reply_markup=markup)
    elif call.data == 'project_id':
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Отправьте в чат название борда для "
                                               "которого необходимо узнать PHID. \n"
                                               "\n_Название не обязательно вводить точь-в-точь_",
                         parse_mode='Markdown', reply_markup=back_markup())
        set_chat_state(CHAT_STATE_GET_PROJECT_ID)
    elif call.data == CHAT_STATE_SET_FREQUENCY:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите частоту проверки обновлений в минутах:',
                         parse_mode='HTML', reply_markup=back_markup())
        set_chat_state(CHAT_STATE_SET_FREQUENCY)
    elif call.data == "ignored":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Исключения позволяют игнорировать перемещения '
                                               'в определенных бордах или колонках.\n'
                                               'Это может быть полезно, в случае если вы подписаны на задачи, но не'
                                               'хотите получать оповещения о событиях которые происходят, например, '
                                               'на борде который к вам не относится, но указан в задаче.\n'
                                               'Например, вы менеджер, и не хотите получать оповещения о движении '
                                               'задачи на борде разработчиков. \n'
                                               '\n\U0001F648 Борды, перемещения по которым игнорируются: \n%s'
                                               '\n\U0001F648 Колонки, перемещения в которые игнорируются: \n%s'
                                               '\n\U0001F648 Пользователи, действия которых игнорируются: \n%s\n'
                                               '\nВыберите, что вы хотите игнорировать:' % (
                                                getptojectname(call.message, "phids",
                                                               config.ignored_boards(call.message.chat.id)) or
                                                "Список пуст\n",
                                                getcolumns(call.message.chat.id),
                                                getusername(call.message,
                                                            config.ignored_users(call.message.chat.id)) or
                                                "Список пуст\n"),
                         parse_mode='Markdown', reply_markup=ignore_markup())
    elif call.data == CHAT_STATE_SET_IGNORED_BOARDS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите PHIDы бордов, перемещения по которым необходимо игнорировать:',
                         parse_mode='HTML', reply_markup=back_ignore_markup())
        set_chat_state(CHAT_STATE_SET_IGNORED_BOARDS)
    elif call.data == CHAT_STATE_REMOVE_IGNORED_BOARDS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "\U0001F648 Борды, перемещения по которым игнорируются: \n%s"
                                               "\nВведите номер борда, который хотите удалить из списка:" %
                         (getptojectname(call.message, "phids", config.ignored_boards(call.message.chat.id)) or
                          "Список пуст\n"), parse_mode='Markdown', reply_markup=back_ignore_markup())
        set_chat_state(CHAT_STATE_REMOVE_IGNORED_BOARDS)
    elif call.data == CHAT_STATE_SET_IGNORED_COLUMNS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите названия колонок, перемещения '
                                               'в которые необходимо игнорировать:',
                         parse_mode='HTML', reply_markup=back_ignore_markup())
        set_chat_state(CHAT_STATE_SET_IGNORED_COLUMNS)
    elif call.data == CHAT_STATE_REMOVE_IGNORED_USERS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "\U0001F648 Пользователи, действия которых игнорируются: \n%s"
                                               "\nВведите номер пользователя, который хотите удалить из списка:" %
                         getusername(call.message, config.ignored_users(call.message.chat.id)) or
                         "Список пуст\n", parse_mode='Markdown', reply_markup=back_ignore_markup())
        set_chat_state(CHAT_STATE_REMOVE_IGNORED_USERS)
    elif call.data == CHAT_STATE_REMOVE_IGNORED_COLUMS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "\U0001F648 Колонки, перемещения по которым игнорируются: \n%s"
                                               "\nОтправьте в чат номер колонки, которую хотите удалить из списка:" %
                         getcolumns(call.message.chat.id), parse_mode='Markdown',
                         reply_markup=back_ignore_markup())
        set_chat_state(CHAT_STATE_REMOVE_IGNORED_COLUMS)
    elif call.data == CHAT_STATE_IGNORED_USERS:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Отправьте в чат PHIDы пользователей, действия которых вы хотите '
                                               'игнорировать, или выберите себя нажав на кнопку ниже. '
                                               'Узнать PHID пользователя можно с помощью команды /user_id',
                         parse_mode='HTML', reply_markup=back_usrignore_markup())
        set_chat_state(CHAT_STATE_IGNORED_USERS)
    elif call.data == "ignoremyself":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        myphid = whoami(call.message)
        ignored_users(call.message, myphid['phid'])
    elif call.data == "settings":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        settings(call.message)
    elif call.data == "set_priorities":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        priorities(call.message)
    elif call.data == CHAT_STATE_BACK:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        menu(call.message)
        set_chat_state(None)
    elif call.data.startswith('info'):
        task_id = call.data.replace("info", "")
        call.message.text = task_id
        get_info(call.message)
    elif call.data.startswith('open'):
        task_id = call.data.replace("open", "")
        print("Открыта задача %s" % task_id)
    elif call.data.startswith('settings'):
        setting = call.data.replace("settings", "")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        set_settings(call.message, setting)
        settings(call.message)
    elif call.data.startswith('priority'):
        priority = call.data.replace("priority", "")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        set_priorities(call.message, priority)
        priorities(call.message)
    elif call.data.startswith('watchtype'):
        watchtype = call.data.replace("watchtype", "")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        set_watchtype(call.message, int(watchtype))
        watchtypes(call.message)


@bot.message_handler(commands=['server'])
def server(message):
    args = [message.text]
    if args:
        config.set_server(message.chat.id, args[0])
        bot.answer_callback_query(message.chat.id, "Сервер установлен!")
        menu(message)
        checkconfig(message, "add")
    else:
        bot.send_message(message.chat.id, "\U0001F3E0 Адрес сервера: %s" % config.server(message.chat.id))


def settings(message):
    newtask_emoji = "\u2705" if 1 not in config.settings(message.chat.id) else "\u274C"
    column_emoji = "\u2705" if 2 not in config.settings(message.chat.id) else "\u274C"
    assign_emoji = "\u2705" if 3 not in config.settings(message.chat.id) else "\u274C"
    prior_emoji = "\u2705" if 4 not in config.settings(message.chat.id) else "\u274C"
    comm_emoji = "\u2705" if 5 not in config.settings(message.chat.id) else "\u274C"
    status_emoji = "\u2705" if 6 not in config.settings(message.chat.id) else "\u274C"
    tags_emoji = "\u2705" if 7 not in config.settings(message.chat.id) else "\u274C"
    cmit_emoji = "\u2705" if 8 not in config.settings(message.chat.id) else "\u274C"
    linked_emoji = "\u2705" if 9 not in config.settings(message.chat.id) else "\u274C"

    settings_markup = InlineKeyboardMarkup()
    settings_markup.row_width = 1
    settings_markup.add(InlineKeyboardButton(newtask_emoji + " Новые задачи",
                                             callback_data='settings1'),
                        InlineKeyboardButton(column_emoji + " Перемещения по колонкам",
                                             callback_data='settings2'),
                        InlineKeyboardButton(assign_emoji + " Изменение исполнителя",
                                             callback_data='settings3'),
                        InlineKeyboardButton(prior_emoji + " Изменение приоритета",
                                             callback_data='settings4'),
                        InlineKeyboardButton(comm_emoji + " Новые комментарии",
                                             callback_data='settings5'),
                        InlineKeyboardButton(status_emoji + " Изменение статуса",
                                             callback_data='settings6'),
                        InlineKeyboardButton(tags_emoji + " Изменение тегов",
                                             callback_data='settings7'),
                        InlineKeyboardButton(cmit_emoji + " Новые коммиты",
                                             callback_data='settings8'),
                        InlineKeyboardButton(linked_emoji + " Связанные задачи",
                                             callback_data='settings9'),
                        InlineKeyboardButton("Настройки приоритетов",
                                             callback_data='set_priorities'),
                        InlineKeyboardButton("Вернуться в главное меню",
                                             callback_data=CHAT_STATE_BACK)
                        )

    bot.send_message(message.chat.id, "Это ваши текущие настройки уведомлений. Нажмите, чтобы переключить состояние.",
                     reply_markup=settings_markup)


def set_settings(message, setting):
    if int(setting) in config.settings(message.chat.id):
        config.remove_from_settings(message.chat.id, setting)
    else:
        config.add_to_settings(message.chat.id, setting)


def priorities(message):
    wishlist_emoji = "\u2705" if 10 not in config.priorities(message.chat.id) else "\u274C"
    low_emoji = "\u2705" if 25 not in config.priorities(message.chat.id) else "\u274C"
    normal_emoji = "\u2705" if 50 not in config.priorities(message.chat.id) else "\u274C"
    high_emoji = "\u2705" if 80 not in config.priorities(message.chat.id) else "\u274C"
    triage_emoji = "\u2705" if 90 not in config.priorities(message.chat.id) else "\u274C"
    unbreak_emoji = "\u2705" if 100 not in config.priorities(message.chat.id) else "\u274C"

    priorities_markup = InlineKeyboardMarkup()
    priorities_markup.row_width = 1
    priorities_markup.add(InlineKeyboardButton(wishlist_emoji + " Wishlist",
                                               callback_data='priority10'),
                          InlineKeyboardButton(low_emoji + " Низкий",
                                               callback_data='priority25'),
                          InlineKeyboardButton(normal_emoji + " Средний",
                                               callback_data='priority50'),
                          InlineKeyboardButton(high_emoji + " Высокий",
                                               callback_data='priority80'),
                          InlineKeyboardButton(triage_emoji + " Срочный",
                                               callback_data='priority90'),
                          InlineKeyboardButton(unbreak_emoji + " Наивысший",
                                               callback_data='priority100'),
                          InlineKeyboardButton("Вернуться в настройки",
                                               callback_data='settings'),
                          InlineKeyboardButton("Вернуться в главное меню",
                                               callback_data=CHAT_STATE_BACK)
                          )

    bot.send_message(message.chat.id, "Это ваши текущие настройки приоритетов. Нажмите, чтобы переключить состояние.",
                     reply_markup=priorities_markup)


def set_priorities(message, priority):
    if int(priority) in config.priorities(message.chat.id):
        config.remove_from_priorities(message.chat.id, priority)
    else:
        config.add_to_priorities(message.chat.id, priority)


@bot.message_handler(commands=['where_apitoken'])
def where_apitoken(message):
    bot.send_message(message.chat.id, "API-Токен можно получить, пройдя по шагам:\n\n"
                                      "1. Зайти в <b>Phabricator</b>\n"
                                      "2. Нажать на свою аваратку в правом верхнем углу экрана\n"
                                      "3. Выбрать <b>'Settings'</b>\n"
                                      "4. Внизу нажать <b>'Conduit API Tokens'</b>\n"
                                      "5. Нажать <b>'Generate Token'</b> и согласиться, нажав "
                                      "синюю кнопку <b>'Generate Token'</b> еще раз\n"
                                      "6. Скопировать все содержимое отобразившегося токена и "
                                      "установить токен в главном меню (/menu)", parse_mode='HTML')


@bot.message_handler(commands=['phab_api'])
def phab_api(message):
    args = message.text
    if args:
        if args.startswith("api-"):
            config.set_phab_api(message.chat.id, args)
            bot.delete_message(message.chat.id, message.message_id)
            bot.send_message(message.chat.id, "API токен установлен, сообщение с токеном удалено")
            menu(message)
            checkconfig(message, "add")
        else:
            bot.send_message(message.chat.id, "\u274C Указанный вами токен <b>%s</b> некорректен и установлен "
                                              "не будет" % args, parse_mode='HTML', reply_markup=back_markup())
    elif config.phab_api(message.chat.id) is not None:
        bot.send_message(message.chat.id, "API токен установлен, но в целях безопасноти отображен не будет",
                         reply_markup=back_markup())
    else:
        bot.send_message(message.chat.id, "API токен не установлен", reply_markup=back_markup())


@bot.message_handler(commands=['frequency'])
def frequency(message):
    args = [message.text]
    if not args:
        bot.send_message(message.chat.id,
                         "\u23F0 Частота опроса сервера (минуты): %d" % (config.frequency(message.chat.id) or 2))
        return
    if not args[0].isnumeric():
        bot.send_message(message.chat.id, "Требуется целочисленное значение!")
        return
    if int(args[0]) >= 1:
        config.set_frequency(message.chat.id, int(args[0]))
        bot.send_message(message.chat.id,
                         "\u23F0 Частота опроса сервера (минуты): %d" % (
                                     config.frequency(message.chat.id) or 2))
        menu(message)
    else:
        bot.send_message(message.chat.id, "Частота опроса не может быть менее минуты \U0001F609",
                         reply_markup=back_markup())


@bot.message_handler(commands=['watchtype'])
def watchtypes(message):
    boards_emojii = "\u2705" if config.watchtype(message.chat.id) == 1 else ""
    assign_emojii = "\u2705" if config.watchtype(message.chat.id) == 2 else ""
    union_emojii = "\u2705" if config.watchtype(message.chat.id) == 3 else ""

    watchtype_markup = InlineKeyboardMarkup()
    watchtype_markup.row_width = 1
    watchtype_markup.add(InlineKeyboardButton(boards_emojii + " Задачи на бордах",
                                              callback_data='watchtype1'),
                         InlineKeyboardButton(assign_emojii + " Задачи на мне",
                                              callback_data='watchtype2'),
                         InlineKeyboardButton(union_emojii + " Задачи на бордах и на мне",
                                              callback_data='watchtype3'),
                         InlineKeyboardButton("Вернуться в главное меню",
                                              callback_data=CHAT_STATE_BACK)
                         )

    bot.send_message(message.chat.id, "Это ваши текущие настройки отслеживания. Нажмите, чтобы выбрать "
                                      "что будет отслеживаться.",
                     reply_markup=watchtype_markup)


def set_watchtype(message, watchtype):
    config.set_watchtype(message.chat.id, watchtype)
    if watchtype == (1 or 3) and not config.boards(message.chat.id) and config.active(message.chat.id):
        unschedule(message)
        bot.send_message(message.chat.id, "\U0001F534 Вы выбрали отслеживание бордов, но они у вас не установлены, "
                                          "по этому работа бота была приостановлена")
    if watchtype == 2:
        checkconfig(message, "add", None)


@bot.message_handler(commands=['boards'])
def boards(message):
    args = message.text.replace('.', '').replace(',', '').split()
    if args:
        for arg in args:
            if not arg.startswith("PHID-PROJ"):
                bot.send_message(message.chat.id, "\u274C Указанный вами PHID <b>%s</b> не является PHID'ом проекта "
                                                  "и добавлен не будет" % arg, parse_mode='HTML')
                continue
            config.set_boards(message.chat.id, arg)
        menu(message)
        checkconfig(message, "add")
    else:
        bot.send_message(message.chat.id, "\U0001F440 Отслеживаемые борды: \n%s" %
                         (getptojectname(message, "phids", config.boards(message.chat.id))) or
                         "Список пуст", parse_mode='Markdown')


def unset_boards(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(InlineKeyboardButton("Ввести другой номер", callback_data=CHAT_STATE_REMOVE_BOARDS),
               InlineKeyboardButton("Вернуться в главное меню", callback_data=CHAT_STATE_BACK)
               )
    if not message.text.isnumeric():
        bot.send_message(message.chat.id, "\u274C Отправьте номер борда", reply_markup=markup)
        return
    if (int(message.text) > len(config.boards(message.chat.id))) or (int(message.text) < 0):
        bot.send_message(message.chat.id, "\u274C Борда под таким номером нет", reply_markup=markup)
        return
    phid = config.boards(message.chat.id)[int(message.text) - 1]
    config.unset_boards(message.chat.id, phid)
    bot.send_message(message.chat.id, "\u2705 Борд удален из списка", reply_markup=markup)


@bot.message_handler(commands=['ignored_boards'])
def ignored_boards(message):
    args = message.text.split()
    if args:
        for arg in args:
            if not arg.startswith("PHID-PROJ"):
                bot.send_message(message.chat.id, "\u274C Указанный вами PHID <b>%s</b> не является PHID'ом проекта "
                                                  "и добавлен не будет" % arg, parse_mode='HTML')
                continue
            config.set_ignored_boards(message.chat.id, arg)
            bot.send_message(message.chat.id, "\u2705 Борд %s добавлен в игнорируемые" % arg,
                             reply_markup=back_ignore_markup())
    else:
        bot.send_message(message.chat.id, "\U0001F648 Борды, перемещения по которым игнорируются: \n%s" %
                         (getptojectname(message, "phids", config.ignored_boards(message.chat.id)) or
                          "Список пуст\n"), parse_mode='Markdown')


def unset_ignored_boards(message):
    if not message.text.isnumeric():
        bot.send_message(message.chat.id, "\u274C Отправьте номер борда", reply_markup=back_ignore_markup())
        return
    if (int(message.text) > len(config.ignored_boards(message.chat.id))) or (int(message.text) < 0):
        bot.send_message(message.chat.id, "\u274C Борда под таким номером нет", reply_markup=back_ignore_markup())
        return
    phid = config.ignored_boards(message.chat.id)[int(message.text) - 1]
    config.unset_ignored_boards(message.chat.id, phid)
    bot.send_message(message.chat.id, "\u2705 Борд удален из списка", reply_markup=back_ignore_markup())


@bot.message_handler(commands=['ignored_users'])
def ignored_users(message, phid=None):
    arg = message.text if phid is None else phid
    if arg:
        if not arg.startswith("PHID-USER"):
            bot.send_message(message.chat.id, "\u274C Указанный вами PHID <b>%s</b> не является PHID'ом "
                                              "пользователя и добавлен не будет" % arg, parse_mode='HTML',
                             reply_markup=back_ignore_markup())
        else:
            config.set_ignored_users(message.chat.id, arg)
            bot.send_message(message.chat.id, "\u2705 Пользователь добавлен в игнориуемые",
                             reply_markup=back_ignore_markup())
    else:
        bot.send_message(message.chat.id, "\U0001F648 Пользователи, действия которых игнорируются: \n%s" %
                         (getusername(message, config.ignored_users(message.chat.id)) or
                          "Список пуст\n"), parse_mode='Markdown')


def unset_ignored_users(message):
    if not message.text.isnumeric():
        bot.send_message(message.chat.id, "\u274C Отправьте номер пользователя", reply_markup=back_ignore_markup())
        return
    if (int(message.text) > len(config.ignored_users(message.chat.id))) or (int(message.text) < 0):
        bot.send_message(message.chat.id, "\u274C Пользователя под таким номером нет",
                         reply_markup=back_ignore_markup())
        return
    phid = config.ignored_users(message.chat.id)[int(message.text) - 1]
    config.unset_ignored_users(message.chat.id, phid)
    bot.send_message(message.chat.id, "\u2705 Пользователь удален из списка", reply_markup=back_ignore_markup())


@bot.message_handler(commands=['ignored_columns'])
def ignored_columns(message):
    arg = message.text
    if arg:
        config.set_ignored_columns(message.chat.id, arg)
        bot.send_message(message.chat.id, "\u2705 Колонка помещена в игнорируемые",
                         reply_markup=back_ignore_markup())
    else:
        bot.send_message(message.chat.id, "\U0001F648 Колонки, перемещения в которые игнорируются: \n%s" %
                         getcolumns(message.chat.id))


def unset_ignored_columns(message):
    if not message.text.isnumeric():
        bot.send_message(message.chat.id, "\u274C Введите номер колонки", reply_markup=back_ignore_markup())
        return
    if (int(message.text) > len(config.ignored_columns(message.chat.id))) or (int(message.text) < 0):
        bot.send_message(message.chat.id, "\u274C Колонки под таким номером нет", reply_markup=back_ignore_markup())
        return
    value = config.ignored_columns(message.chat.id)[int(message.text) - 1]
    config.unset_ignored_columns(message.chat.id, value)
    bot.send_message(message.chat.id, "\u2705 Колонка удалена из списка", reply_markup=back_ignore_markup())


@bot.message_handler(commands=['last_check'])
def last_check(message):
    bot.send_message(message.chat.id,
                     "Время последней проверки на наличие новых задач: \n%s\n"
                     "Время последней проверки на наличие обновленных задач: \n%s" % (
                         getptojectname(message, "ts", config.last_new_check(message.chat.id)),
                         getptojectname(message, "ts", config.last_update_check(message.chat.id))),
                     parse_mode='Markdown')


@bot.message_handler(func=lambda message: True)
def setter(message):
    global state
    chat_state = state.get(message.chat.id)
    if message.text[:1] == "/":
        state[message.chat.id] = None
        return
    tid = re.match(r'(t\d+)', message.text.lower())
    if tid:
        state[message.chat.id] = None
        if message.chat.type == "private":
            get_info(message)
        else:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Да", callback_data='info' + message.text))
            bot.send_message(message.chat.id, "Хотите получить информацию о задаче *%s*?" % tid.group(0).capitalize(),
                             reply_markup=markup, parse_mode='Markdown')
        return
    if chat_state == CHAT_STATE_SET_SERVER:
        server(message)
    if chat_state == CHAT_STATE_SET_PHABAPI:
        phab_api(message)
    if chat_state == CHAT_STATE_SET_BOARDS:
        boards(message)
    if chat_state == CHAT_STATE_REMOVE_BOARDS:
        unset_boards(message)
    if chat_state == CHAT_STATE_SET_FREQUENCY:
        frequency(message)
    if chat_state == CHAT_STATE_SET_IGNORED_BOARDS:
        ignored_boards(message)
    if chat_state == CHAT_STATE_REMOVE_IGNORED_BOARDS:
        unset_ignored_boards(message)
    if chat_state == CHAT_STATE_SET_IGNORED_COLUMNS:
        ignored_columns(message)
    if chat_state == CHAT_STATE_REMOVE_IGNORED_COLUMS:
        unset_ignored_columns(message)
    if chat_state == CHAT_STATE_IGNORED_USERS:
        ignored_users(message)
    if chat_state == CHAT_STATE_REMOVE_IGNORED_USERS:
        unset_ignored_users(message)
    if chat_state == CHAT_STATE_GET_PROJECT_ID:
        get_project(message)
    state[message.chat.id] = None


if __name__ == '__main__':
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    TaskGetter.configure(config, bot)
    TaskGetter.main_loop()
