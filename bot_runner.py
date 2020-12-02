from requests.packages.urllib3.exceptions import InsecureRequestWarning
import requests
import telebot
from phabbot.config import Config
from phabbot.task_getter import TaskGetter
from time import strftime, localtime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

config = Config.load()
assert isinstance(config, Config)
tg_api = config.get('tg_api')
assert isinstance(tg_api, str)
bot = telebot.AsyncTeleBot(tg_api)
state = None


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
    bot.send_message(message.chat.id, 'Для начала работы бота вам необходимо сконфигурировать бота.'
                                      '\nНеобходимые для конфигурации настройки помечены в главном меню звёздочкой, '
                                      'остальные настраиваются по желанию'
                                      '\nПосле окончания конфигурации введите <b>"/schedule"</b>, чтобы '
                                      'начать отслеживание', parse_mode="HTML")
    settings(message)


@bot.message_handler(commands=['help'])
def help_message(message):
    bot.send_message(message.chat.id,
                     'Привет! Я оповещаю об обновленях задач в фабрикаторе.'
                     '\n\n<b>Основные команды:</b>'
                     '\n/start - отобразить текущее сообщение'
                     '\n/help - инструкция по применению'
                     '\n/project_id Название - получить PHID борда для дальнейшей конфигурации'
                     '\n/status - статус мониторинга (true - активен | false - приостановлен)'
                     '\n/schedule - запустить задачу по поиску задач'
                     '\n/unschedule - приостановить поиск задач'
                     '\n/reset - остановить поиск задач и удалить настройки'
                     '\n/where_apitoken - инструкция по получению API Token-а'
                     '\n\n<b>Показать текущие настройки:</b>'
                     '\n/main - отобразить главное меню'
                     '\n/server - отобразить текущий адрес сервера,'
                     '\n/phab_api - отобразить текущий токен'
                     '\n/frequency - отобразить текущую частоту обращения к серверу (в минутах)'
                     '\n/boards - отобразить имя борды, за которой нужно следить'
                     '\n/ignored_boards - отобразить список идентификаторов бордов, '
                     '\nобновления в которых стоит игнорировать'
                     '\n/ignored_columns - отобразить список названий колонок, '
                     '\nперемещения по которым стоит игнорировать'
                     '\n\n<b>Настройка:</b>'
                     '\n<b>*</b> /server link - задать адрес сервера (в формате http://some.adress)'
                     '\n<b>*</b> /phab_api token - задать API-токен, выданный фабрикатором'
                     '\n/frequency minutes - задать частоту обращения к серверу (в минутах)'
                     '\n<b>*</b> /boards id1 id2 - задать список бордов, за которыми необходимо следить'
                     '\n/ignored_boards id1 id2 ... - задать список идентификаторов бордов, '
                     '\nперемещения по которым стоит игнорировать'
                     '\n/reset_ignored_boards - сбросить список игнорируемых бордов '
                     '\n/ignored_columns name name ... - задать список названий колонок, '
                     '\nперемещения в которые стоит игнорировать '
                     '\n/reset_ignored_boards - сбросить список игнорируемых колонок '
                     '\n\n<b>Диагностика:</b>'
                     '\n/last_check - штампы времени последней проверки', parse_mode='HTML')


@bot.message_handler(commands=['schedule'])
def schedule(message):
    getname(message)
    if config.server(message.chat.id) and config.phab_api(message.chat.id) and config.boards(message.chat.id):
        bot.send_message(message.chat.id, "\u2705 Мониторинг запущен" if not config.active(message.chat.id) else
                         "\u26A1 Мониторинг уже запущен")
        TaskGetter.schedule(message.chat.id)
    else:
        bot.send_message(message.chat.id, "\u26A1 Для начала мониторинга сконфигурируйте бота!")


@bot.message_handler(commands=['unschedule'])
def unschedule(message):
    TaskGetter.unschedule(message.chat.id)


@bot.message_handler(commands=['reset'])
def reset():
    pass


@bot.message_handler(commands=['sudo'])
def sudo(message):
    if message.chat.id not in config.superusers:
        bot.send_message(message.chat.id, "Вы не являетесь администратором. Забудьте эту команду =)")
        return
    args = __extract_args(message.text)
    if not args:
        return

    if args[0] == 'send_message':
        send_message(' '.join(args[1:]))
    if args[0] == 'get_board':
        bot.send_message(message.chat.id, getptojectname(message.chat.id, "phids", args[1:]), parse_mode='HTML')


def send_message(message):
    [bot.send_message(chat['chat_id'], message) for chat in config.get('chats')]


@bot.message_handler(commands=['status'])
def status(message):
    activestr = "Активен" if config.active(message.chat.id) else "Отдыхает"
    emoji = "\u2705" if config.active(message.chat.id) else "\u274C"
    bot.send_message(message.chat.id, "%s Статус мониторинга: %s" % (emoji, activestr))


def checkconfig(chatid, act):
    if act == "check":
        if not config.server(chatid):
            bot.send_message(chatid, "Для начала работы бота необходимо ввести "
                                     "адрес сервера в главном меню (/main)", parse_mode='HTML')
            return False
        if not config.phab_api(chatid):
            bot.send_message(chatid, "Для начала работы бота необходимо ввести API-токен в главном меню (/main). \n"
                                     "Чтобы узнать, как получить API Token введите команду <b>/where_apitoken</b>",
                             parse_mode='HTML')
            return False
        return True
    if act == "add":
        if config.boards(chatid) and config.server(chatid) and config.phab_api(chatid):
            bot.send_message(chatid, "Бот готов к работе. Можете сконфигурировать остальные "
                                     "настройки или начать мониторинг командой <b>/schedule</b>", parse_mode='HTML')


def getptojectname(chatid, act, phids):
    if len(phids) > 0:
        defaultstr = str()
        for phid in phids:
            defaultstr += "\n<b>Неизвестен: </b> " + phid
        if not checkconfig(chatid, "check"):
            return defaultstr
        result = str()
        for phid in phids:
            url = '{0}/api/project.search'.format(config.server(chatid))
            data = {
                "api.token": config.phab_api(chatid),
                "constraints[phids][0]": phid
            }
            r = requests.post(url, params=data, verify=False)
            json = r.json()
            name = json['result']['data'][0]['fields']['name'] if len(json['result']['data']) else "Неизвестен"

            if len(json) > 0:
                if act == "phids":
                    result += "<b>%s:</b> %s\n" % (name, phid)
                if act == "ts":
                    time = strftime("%H:%M:%S", localtime(phids[phid]))
                    result += "<b>%s:</b> %s\n" % (name, time)
        if len(result) > 0:
            return result
    return "Список пуст\n"


@bot.message_handler(commands=['project_id'])
def get_project(message):
    if checkconfig(message.chat.id, "check"):
        args = __extract_args(message.text)
        if args is not None:
            args = ' '.join(args)
            url = '{0}/api/project.search'.format(config.server(message.chat.id))
            data = {
                "api.token": config.phab_api(message.chat.id),
                "constraints[name]": args,
            }
            r = requests.post(url, params=data, verify=False)
            result = r.json()
            if len(result['result']['data']) > 0:
                resultstr = 'Результат поиска:\n'
                for i in range(len(result['result']['data'])):
                    if result['result']['data'][i]['fields']['color']['key'] != "disabled":
                        phid = result['result']['data'][i]['phid']
                        depth = result['result']['data'][i]['fields']['depth']
                        pname = (result['result']['data'][i]['fields']['parent']['name']) if depth != 0 else None
                        name = result['result']['data'][i]['fields']['name']
                        resultname = ((pname + " - ") if int(depth) > 1 else "") + name
                        resultstr += "* <b>" + resultname + ":</b> " + phid + "\n"
                bot.send_message(message.chat.id, resultstr, parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, "Проекты с таким именем не найдены")
        else:
            bot.send_message(message.chat.id, "Введите название проекта!")


def ignore_markup():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton("Игноровать борды", callback_data="ignored_boards"),
               InlineKeyboardButton("Игноровать колонки", callback_data="ignored_columns"),
               InlineKeyboardButton("Вернуться в меню", callback_data="back")
               )
    return markup


def back_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Вернуться в меню", callback_data="back"))
    return markup


@bot.message_handler(commands=['main'])
def settings(message):

    markup = InlineKeyboardMarkup()
    server_star = " *" if not config.server(message.chat.id) else ""
    api_star = " *" if not config.phab_api(message.chat.id) else ""
    boards_star = " *" if not config.boards(message.chat.id) else ""
    markup.add(InlineKeyboardButton("Сервер" + server_star, callback_data="server"),
               InlineKeyboardButton("API-Токен" + api_star, callback_data="phab_api"),
               InlineKeyboardButton("Борды" + boards_star, callback_data="boards"),
               InlineKeyboardButton("Частота опроса", callback_data="frequency"),
               InlineKeyboardButton("Исключения", callback_data="ignored")
               )

    bot.send_message(message.chat.id,
                     ("<b>Главное меню бота</b>\n\n"
                      "%s Статус мониторинга: %s\n"
                      "\n\U0001F3E0 Адрес сервера: %s\n" 
                      "\n\u23F0 Частота опроса сервера (минуты): %s\n" 
                      "\n\U0001F440 Отслеживаемые борды: \n%s" 
                      "\n\U0001F648 Борды, перемещения по которым игнорируются: \n%s" 
                      "\n\U0001F648 Колонки, перемещения в которые игнорируются: \n%s\n"
                      "\n<b>Выберите, что вы хотите настроить:</b> ") % (
                      "\u2705" if config.active(message.chat.id) else "\u274C",
                      "Активен (Остановить: /unschedule)" if config.active(message.chat.id) else
                      "Отдыхает (Запустить: /schedule)",
                      config.server(message.chat.id) or "Не установлен",
                      config.frequency(message.chat.id) or "2 (Стандартное значение)",
                      getptojectname(message.chat.id, "phids", config.boards(message.chat.id)) or
                      "Список пуст\n",
                      getptojectname(message.chat.id, "phids", config.ignored_boards(message.chat.id)) or
                      "Список пуст\n",
                      (', '.join(config.ignored_columns(message.chat.id))) or "Список пуст"
                     ), parse_mode='HTML', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global state
    if call.data == "server":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите адрес сервера в формате <b>"https://some.adress"</b>:',
                         parse_mode='HTML', reply_markup=back_markup())
        state = "set_server"
    elif call.data == "phab_api":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите ваш API-Token. Чтобы узнать, как его '
                                               'получить введите /where_apitoken:',
                         parse_mode='HTML', reply_markup=back_markup())
        state = "set_phab_api"
    elif call.data == "boards":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите через пробел PHIDы бордов, за которыми хотите наблюдать.\n'
                                               'PHIDы бордов можно узнать, используя команду \n'
                                               '<b>"/project_id название борда"</b> (Название не обязательно '
                                               'вводить точь-в-точь)\n'
                                               'Так-же, при необходимости вы можете настроить игнорируемые борды, '
                                               'перемещения по которым отслеживаться не будут. \n'
                                               'Для настройки нажмите <b>"Исключения"</b> в главном меню',
                         parse_mode='HTML', reply_markup=back_markup())
        state = "set_boards"
    elif call.data == "frequency":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите частоту проверки обновлений в минутах:',
                         parse_mode='HTML', reply_markup=back_markup())
        state = "set_frequency"
    elif call.data == "ignored":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Исключения позволяют игнорировать перемещения '
                                               'в определенных бордах или колонках.\n'
                                               'Это может быть полезно, в случае если вы подписаны на задачи, но не'
                                               'хотите получать оповещения о событиях которые происходят, например, '
                                               'на борде который к вам не относится, но указан в задаче.\n'
                                               'Например, вы менеджер, и не хотите получать оповещения о движении таска'
                                               'на борде разработчиков. \nВыберите, что вы хотите игнорировать:',
                         parse_mode='HTML', reply_markup=ignore_markup())
    elif call.data == "ignored_boards":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите PHIDы бордов, перемещения по которым необходимо игнорировать:',
                         parse_mode='HTML', reply_markup=back_markup())
        state = "set_ignored_boards"
    elif call.data == "ignored_columns":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, 'Введите названия колонок, перемещения '
                                               'в которые необходимо игнорировать:',
                         parse_mode='HTML', reply_markup=back_markup())
        state = "set_ignored_columns"
    elif call.data == "back":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        settings(call.message)
        state = None


@bot.message_handler(commands=['server'])
def server(message, command=True):
    args = __extract_args(message.text) if command else [message.text]
    if args:
        config.set_server(message.chat.id, args[0])
        checkconfig(message.chat.id, "add")
        bot.answer_callback_query(message.chat.id, "Сервер установлен!")
        settings(message)
    else:
        bot.send_message(message.chat.id, "\U0001F3E0 Адрес сервера: %s" % config.server(message.chat.id))


@bot.message_handler(commands=['where_apitoken'])
def where_apitoken(message):
    bot.send_message(message.chat.id, "API-Token можно получить, пройдя по шагам:\n\n"
                                      "1. Зайти в <b>Phabricator</b>\n"
                                      "2. Нажать на свою аваратку в правом верхнем углу экрана\n"
                                      "3. Выбрать <b>'Settings'</b>\n"
                                      "4. Внизу нажать <b>'Conduit API Tokens'</b>\n"
                                      "5. Нажать <b>'Generate Token'</b> и согласиться, нажав "
                                      "синюю кнопку <b>'Generate Token'</b> еще раз\n"
                                      "6. Скопировать все содержимое отобразившегося токена и "
                                      "установить токен в главном меню (/main)", parse_mode='HTML')


@bot.message_handler(commands=['phab_api'])
def phab_api(message, command=True):
    args = __extract_args(message.text) if command else [message.text]
    if args:
        config.set_phab_api(message.chat.id, args[0])
        bot.delete_message(message.chat.id, message.message_id)
        bot.send_message(message.chat.id, "API токен установлен, сообщение с токеном удалено")
        checkconfig(message.chat.id, "add")
        settings(message)
    elif config.phab_api(message.chat.id) is not None:
        bot.send_message(message.chat.id, "API токен установлен, но в целях безопасноти отображен не будет")
    else:
        bot.send_message(message.chat.id, "API токен не установлен")


@bot.message_handler(commands=['frequency'])
def frequency(message):
    args = __extract_args(message.text)
    if not args:
        bot.send_message(message.chat.id,
                         "\u23F0 Частота опроса сервера (минуты): %d" % (config.frequency(message.chat.id) or 2))
        return
    if not args[0].isnumeric():
        bot.send_message(message.chat.id, "Введите целочисленное значение!")
        return
    if int(args[0]) > 1:
        config.set_frequency(message.chat.id, int(args[0]))
        bot.send_message(message.chat.id,
                         "\u23F0 Частота опроса сервера (минуты): %d" % (
                                     config.frequency(message.chat.id) or 2))
        settings(message)
    else:
        bot.send_message(message.chat.id, "Давайте уважать фабрикатор "
                                          "и не задалбывать его частыми запросами \U0001F609")


@bot.message_handler(commands=['boards'])
def boards(message, command=True):
    args = __extract_args(message.text) if command else message.text.replace('.', '').replace(',', '').split()
    if args:
        for i in range(len(args)):
            config.set_boards(message.chat.id, args[i])
        checkconfig(message.chat.id, "add")
        settings(message)
    else:
        bot.send_message(message.chat.id, "\U0001F440 Отслеживаемые борды: \n%s" %
                         (getptojectname(message.chat.id, "phids", config.boards(message.chat.id))) or
                         "Список пуст", parse_mode='HTML')


@bot.message_handler(commands=['ignored_boards'])
def ignored_boards(message, command=True):
    args = __extract_args(message.text) if command else [message.text]
    if args:
        config.set_ignored_boards(message.chat.id, args)
        settings(message)
    else:
        bot.send_message(message.chat.id, "\U0001F648 Борды, перемещения по которым игнорируются: \n%s" %
                         (getptojectname(message.chat.id, "phids", config.ignored_boards(message.chat.id)) or
                          "Список пуст\n"), parse_mode='HTML')


@bot.message_handler(commands=['reset_ignored_boards'])
def ignored_boards(message):
    config.unset_ignored_boards(message.chat.id)
    bot.send_message(message.chat.id, "\u2705 Игнорируемые борды сброшены")


@bot.message_handler(commands=['ignored_columns'])
def ignored_columns(message, command=True):
    args = __extract_args(message.text) if command else [message.text]
    if args:
        args = ' '.join(args).split(',')
        config.set_ignored_columns(message.chat.id, args)
        settings(message)
    else:
        bot.send_message(message.chat.id, "\U0001F648 Колонки, перемещения в которые игнорируются: \n%s" %
                         (', '.join(config.ignored_columns(message.chat.id)) or "Список пуст"))


@bot.message_handler(commands=['reset_ignored_columns'])
def ignored_boards(message):
    config.unset_ignored_columns(message.chat.id)
    bot.send_message(message.chat.id, "\u2705 Игнорируемые колонки сброшены")


@bot.message_handler(commands=['last_check'])
def last_check(message):
    bot.send_message(message.chat.id,
                     "Время последней проверки на наличие новых тасков: \n%s\n"
                     "Время последней проверки на наличие обновленных тасков: \n%s" % (
                         getptojectname(message.chat.id, "ts", config.last_new_check(message.chat.id)),
                         getptojectname(message.chat.id, "ts", config.last_update_check(message.chat.id))),
                     parse_mode='HTML')


@bot.message_handler(func=lambda message: True)
def setter(message):
    global state
    if message.text[:1] == "/":
        state = None
        return
    if state == "set_server":
        server(message, False)
    if state == "set_phab_api":
        phab_api(message, False)
    if state == "set_boards":
        boards(message, False)
    if state == "set_frequency":
        frequency(message, False)
    if state == "set_ignored_boards":
        ignored_boards(message, False)
    if state == "set_ignored_columns":
        ignored_columns(message, False)
    state = None


if __name__ == '__main__':
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    TaskGetter.configure(config, bot)
    TaskGetter.main_loop()
