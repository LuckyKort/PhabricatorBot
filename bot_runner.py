from requests.packages.urllib3.exceptions import InsecureRequestWarning
import requests
import telebot
from phabbot.config import Config
from phabbot.task_getter import TaskGetter

config = Config.load()
assert isinstance(config, Config)
tg_api = config.get('tg_api')
assert isinstance(tg_api, str)
bot = telebot.AsyncTeleBot(tg_api)


def __extract_args(command_text: str):
    args = command_text.split()[1:]
    if not args:
        return None
    return args


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 'Для начала работы бота вам необходимо сконфигурировать бота.'
                                      '\nДоступные команды для конфигурации бота описаны в <b>"/help"</b>'
                                      '\nНеобходимые к конфигурации команды помечены звездочкой, остальные по желанию'
                                      '\nПосле окончания конфигурации введите <b>"/schedule"</b>, чтобы '
                                      'начать отслеживание', parse_mode="HTML")


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
                     '\n\n<b>Показать текущие настройки:</b>'
                     '\n/settings - отобразить все настройки одним сообщением'
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
    bot.send_message(message.chat.id, "\u2705 Мониторинг запущен" if
                     not config.active(message.chat.id) else "\u26A1 Мониторинг уже запущен")
    TaskGetter.schedule(message.chat.id)


@bot.message_handler(commands=['unschedule'])
def unschedule(message):
    TaskGetter.unschedule(message.chat.id)


@bot.message_handler(commands=['reset'])
def reset():
    pass


@bot.message_handler(commands=['status'])
def status(message):
    activestr = "Активен" if config.active(message.chat.id) else "Отдыхает"
    emoji = "\u2705" if config.active(message.chat.id) else "\u274C"
    bot.send_message(message.chat.id, "%s Статус мониторинга: %s" % (emoji, activestr))


def getptojectname(chatid, phids):
    defaultstr = str()
    for phid in phids:
        defaultstr += "\n<b>Неизвестен: </b> " + phid
    if not config.boards(chatid):
        return defaultstr
    if not config.server(chatid):
        return defaultstr
    if not config.phab_api(chatid):
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
            result += "<b>%s:</b> %s\n" % (name, phid)
    if len(result) > 0:
        return result
    return defaultstr


@bot.message_handler(commands=['project_id'])
def get_project(message):
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


@bot.message_handler(commands=['settings'])
def settings(message):
    bot.send_message(message.chat.id,
                     ("\U0001F3E0 Адрес сервера: %s\n" 
                      "\n\u23F0 Частота опроса сервера (минуты): %s\n" 
                      "\n\U0001F440 Отслеживаемые борды: \n%s" 
                      "\n\U0001F648 Борды, перемещения по которым игнорируются: \n%s" 
                      "\n\U0001F648 Колонки, перемещения в которые игнорируются: \n%s\n") % (
                      config.server(message.chat.id) or "Не установлен",
                      config.frequency(message.chat.id) or "2 (Стандартное значение)",
                      getptojectname(message.chat.id, config.boards(message.chat.id)) or "Список пуст\n",
                      getptojectname(message.chat.id, config.ignored_boards(message.chat.id)) or "Список пуст\n",
                      (', '.join(config.ignored_columns(message.chat.id))) or "Список пуст"
                     ), parse_mode='HTML')


@bot.message_handler(commands=['server'])
def server(message):
    args = __extract_args(message.text)
    if args:
        config.set_server(message.chat.id, args[0])
    bot.send_message(message.chat.id, "\U0001F3E0 Адрес сервера: %s" % config.server(message.chat.id))


@bot.message_handler(commands=['phab_api'])
def phab_api(message):
    args = __extract_args(message.text)
    if args:
        config.set_phab_api(message.chat.id, args[0])
        bot.delete_message(message.chat.id, message.message_id)
        bot.send_message(message.chat.id, "API токен установлен, сообщение с токеном удалено")
    elif config.phab_api(message.chat.id) is not None:
        bot.send_message(message.chat.id, "API токен установлен, но в целях безопасноти отображен не будет")
    else:
        bot.send_message(message.chat.id, "API токен не установлен")


@bot.message_handler(commands=['frequency'])
def frequency(message):
    args = __extract_args(message.text)
    if args:
        if int(args[0]) > 1:
            config.set_frequency(message.chat.id, int(args[0]))
        else:
            bot.send_message(message.chat.id, "Давайте уважать фабрикатор "
                                              "и не задалбывать его частыми запросами \U0001F609")
    bot.send_message(message.chat.id,
                     "\u23F0 Частота опроса сервера (минуты): %d" % (config.frequency(message.chat.id) or 2))


@bot.message_handler(commands=['boards'])
def boards(message):
    args = __extract_args(message.text)
    if args:
        config.set_boards(message.chat.id, args)
    bot.send_message(message.chat.id, "\U0001F440 Отслеживаемые борды: \n%s" %
                     (getptojectname(message.chat.id, config.boards(message.chat.id))) or
                     "Список пуст", parse_mode='HTML')


@bot.message_handler(commands=['ignored_boards'])
def ignored_boards(message):
    args = __extract_args(message.text)
    if args:
        config.set_ignored_boards(message.chat.id, args)
    bot.send_message(message.chat.id, "\U0001F648 Борды, перемещения по которым игнорируются: \n%s" %
                     (getptojectname(message.chat.id, config.ignored_boards(message.chat.id)) or "Список пуст\n"),
                     parse_mode='HTML')


@bot.message_handler(commands=['reset_ignored_boards'])
def ignored_boards(message):
    config.unset_ignored_boards(message.chat.id)
    bot.send_message(message.chat.id, "\u2705 Игнорируемые борды сброшены")


@bot.message_handler(commands=['ignored_columns'])
def ignored_columns(message):
    args = __extract_args(message.text)
    if args:
        args = ' '.join(args).split(',')
        config.set_ignored_columns(message.chat.id, args)
    bot.send_message(message.chat.id, "\U0001F648 Колонки, перемещения в которые игнорируются: \n%s" %
                     (', '.join(config.ignored_columns(message.chat.id)) or "Список пуст"))


@bot.message_handler(commands=['reset_ignored_columns'])
def ignored_boards(message):
    config.unset_ignored_columns(message.chat.id)
    bot.send_message(message.chat.id, "\u2705 Игнорируемые колонки сброшены")


@bot.message_handler(commands=['last_check'])
def last_check(message):
    bot.send_message(message.chat.id,
                     "Время последней проверки на наличие новых тасков: %s\n"
                     "Время последней проверки на наличие обновленных тасков: %s" % (
                        config.last_new_check(message.chat.id), 
                        config.last_update_check(message.chat.id)))


if __name__ == '__main__':
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    TaskGetter.configure(config, bot)
    TaskGetter.main_loop()
