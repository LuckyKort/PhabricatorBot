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


@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.send_message(message.chat.id,
                     'Привет! Я оповещаю об обновленях задач в фабрикаторе.'
                     '\nОсновные команды:'
                     '\n/start - отобразить текущее сообщение'
                     '\n/help - инструкция по применению'
                     '\n/status - статус мониторинга (true - активен | false - приостановлен)'
                     '\n/schedule - запустить задачу по поиску задач'
                     '\n/unschedule - приостановить поиск задач'
                     '\n/reset - остановить поиск задач и удалить настройки'
                     '\nПоказать текущие настройки:'
                     '\n/settings - отобразить все настройки одним сообщением'
                     '\n/server - отобразить текущий адрес сервера,'
                     '\n/phab_api - отобразить текущий токен'
                     '\n/frequency - отобразить текущую частоту обращения к серверу (в минутах)'
                     '\n/board_name - отобразить имя борды, за которой нужно следить'
                     '\n/ignored_boards - отобразить список идентификаторов бордов, '
                     '\nобновления в которых стоит игнорировать'
                     '\nНастройка:'
                     '\n/server АдресСервера - задать адрес сервера'
                     '\n/phab_api API-токен - задать API-токен, выданный фабрикатором'
                     '\n/frequency ЦЕЛОЕ - задать частоту обращения к серверу (в минутах)'
                     '\n/board_name ИмяБорды - задать имя борды, за которой нужно следить'
                     '\n/ignored_boards Ид1 Ид2 ... - задать список идентификаторов бордов, '
                     '\nобновления в которых стоит игнорировать'
                     '\nДиагностика:'
                     '\n/last_check - штампы времени последней проверки')


@bot.message_handler(commands=['schedule'])
def schedule(message):
    TaskGetter.schedule(message.chat.id)


@bot.message_handler(commands=['unschedule'])
def unschedule(message):
    TaskGetter.unschedule(message.chat.id)


@bot.message_handler(commands=['reset'])
def reset(message):
    pass


@bot.message_handler(commands=['status'])
def status(message):
    bot.send_message(message.chat.id, "Статус мониторинга: %r" % config.active(message.chat.id))


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
                phid = result['result']['data'][i]['phid']
                depth = result['result']['data'][i]['fields']['depth']
                pname = (result['result']['data'][i]['fields']['parent']['name']) if depth != 0 else None
                name = result['result']['data'][i]['fields']['name']
                active = result['result']['data'][i]['fields']['color']['key']
                resultname = ((pname + " - ") if int(depth) > 1 else "") + name
                resultstr += (resultname + ", " + phid + "\n") if active != "disabled" else None
                #TODO
            bot.send_message(message.chat.id, resultstr)
        else:
            bot.send_message(message.chat.id, "Проекты с таким именем не найдены")
    else:
        bot.send_message(message.chat.id, "Введите название проекта!")


@bot.message_handler(commands=['settings'])
def settings(message):
    bot.send_message(message.chat.id,
                     ("* Адрес сервера: %s\n" 
                      "* API токен в фабрикаторе: %s\n" 
                      "* Частота опроса сервера (минуты): %s\n" 
                      "* Имя борды: %s\n" 
                      "* Идентификаторы игнорируемых бордов: \n%s\n" 
                      "* Названия игнорируемых колонок: \n%s") % (
                      config.server(message.chat.id),
                      config.phab_api(message.chat.id),
                      config.frequency(message.chat.id),
                      config.board_name(message.chat.id),
                      ','.join(config.ignored_boards(message.chat.id)),
                      ','.join(config.ignored_columns(message.chat.id)),
                     ))


@bot.message_handler(commands=['server'])
def server(message):
    args = __extract_args(message.text)
    if args:
        config.set_server(message.chat.id, args[0])
    bot.send_message(message.chat.id, "Адрес сервера: %s" % config.server(message.chat.id))


@bot.message_handler(commands=['phab_api'])
def phab_api(message):
    args = __extract_args(message.text)
    if args:
        config.set_phab_api(message.chat.id, args[0])
    bot.send_message(message.chat.id, "API токен в фабрикаторе: %s" % config.phab_api(message.chat.id))


@bot.message_handler(commands=['frequency'])
def frequency(message):
    args = __extract_args(message.text)
    if args:
        config.set_frequency(message.chat.id, int(args[0]))
    bot.send_message(message.chat.id, "Частота опроса сервера (минуты): %d" % config.frequency(message.chat.id))


@bot.message_handler(commands=['board_name'])
def board_name(message):
    args = __extract_args(message.text)
    if args:
        config.set_board_name(message.chat.id, args[0])
    bot.send_message(message.chat.id, "Имя борда: %s" % config.board_name(message.chat.id))


@bot.message_handler(commands=['ignored_boards'])
def ignored_boards(message):
    args = __extract_args(message.text)
    if args:
        config.set_ignored_boards(message.chat.id, args)
    if len(config.ignored_boards(message.chat.id)) > 0:
        ignored_boards_list = ','.join(config.ignored_boards(message.chat.id))
    else:
        ignored_boards_list = 'Список пуст'
    bot.send_message(message.chat.id, "Идентификаторы игнорируемых бордов: \n%s" % ignored_boards_list)


@bot.message_handler(commands=['reset_ignored_boards'])
def ignored_boards(message):
    config.unset_ignored_boards(message.chat.id)
    bot.send_message(message.chat.id, "Идентификаторы игнорируемых бордов сброшены")


@bot.message_handler(commands=['ignored_columns'])
def ignored_columns(message):
    args = __extract_args(message.text)
    if args:
        args = ' '.join(args).split(',')
        config.set_ignored_columns(message.chat.id, args)
    if len(config.ignored_columns(message.chat.id)) > 0:
        ignored_columns_list = ','.join(config.ignored_columns(message.chat.id))
    else:
        ignored_columns_list = 'Список пуст'
    bot.send_message(message.chat.id, "Названия игнорируемых колонок: \n%s" % ignored_columns_list)


@bot.message_handler(commands=['reset_ignored_columns'])
def ignored_boards(message):
    config.unset_ignored_columns(message.chat.id)
    bot.send_message(message.chat.id, "Имена игнорируемых бордов сброшены")


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
