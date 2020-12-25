import json
import os.path
import codecs


class Config(dict):
    __default_path = "./config.json"

    def __init__(self, path=None, **kwargs):
        self.path = path and path or Config.__default_path
        super().__init__(self, **kwargs)

    @staticmethod
    def load(path: str or None = None):
        if not path:
            path = Config.__default_path

        if not os.path.isfile(path):
            return Config()

        with codecs.open(path, 'r', 'utf-8') as config:
            return Config(**json.load(config), path=path)

    def chat(self, chat_id, update=True):
        chats = self.get('chats', [])
        for chat in chats:
            if chat_id == chat.get('chat_id'):
                return chat
        chat = {'chat_id': chat_id}
        chats.append(chat)
        update and self.dump()
        return chat

    def name(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('name')

    def set_name(self, chat_id, name):
        chat = self.chat(chat_id, False)
        chat['name'] = name
        self.dump()

    def active(self, chat_id):
        chat = self.chat(chat_id, False)
        return bool(chat.get('active', False))

    def server(self, chat_id):
        chat = self.chat(chat_id, False)
        return self.get('server')

    def set_server(self, chat_id, server):
        chat = self.chat(chat_id, False)
        chat['server'] = server
        self.dump()

    def phab_api(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('phab_api')

    def set_phab_api(self, chat_id, phab_api):
        chat = self.chat(chat_id, False)
        chat['phab_api'] = phab_api
        self.dump()

    def frequency(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('frequency')

    def set_frequency(self, chat_id, frequency):
        chat = self.chat(chat_id, False)
        chat['frequency'] = frequency
        self.dump()

    def settings(self, chat_id) -> list:
        chat = self.chat(chat_id, False)
        return chat.get('settings', [])

    def add_to_settings(self, chat_id, settings: list):
        chat = self.chat(chat_id, False)
        if 'settings' not in chat:
            chat['settings'] = [settings]
        else:
            chat['settings'] += [settings]
        self.dump()

    def remove_from_settings(self, chat_id, settings: list):
        chat = self.chat(chat_id, False)
        chat['settings'].remove(settings)
        self.dump()

    def priorities(self, chat_id) -> list:
        chat = self.chat(chat_id, False)
        return chat.get('priorities', [])

    def add_to_priorities(self, chat_id, priorities: list):
        chat = self.chat(chat_id, False)
        if 'priorities' not in chat:
            chat['priorities'] = [priorities]
        else:
            chat['priorities'] += [priorities]
        self.dump()

    def remove_from_settings(self, chat_id, settings: list):
        chat = self.chat(chat_id, False)
        chat['settings'].remove(settings)
        self.dump()

    def boards(self, chat_id) -> list:
        chat = self.chat(chat_id, False)
        return chat.get('boards', [])

    def set_boards(self, chat_id, boards: list):
        chat = self.chat(chat_id, False)
        if 'boards' not in chat:
            chat['boards'] = [boards]
        elif boards not in chat['boards']:
            chat['boards'] += [boards]
        else:
            return
        self.dump()

    def unset_boards(self, chat_id, phid):
        chat = self.chat(chat_id, False)
        chat['boards'].remove(phid)
        chat['last_new_check'].pop(phid)
        chat['last_update_check'].pop(phid)
        self.dump()

    def ignored_boards(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('ignored_boards', [])

    def set_ignored_boards(self, chat_id, ignored_boards: list):
        chat = self.chat(chat_id, False)
        if 'ignored_boards' not in chat:
            chat['ignored_boards'] = [ignored_boards]
        elif ignored_boards not in chat['ignored_boards']:
            chat['ignored_boards'] += [ignored_boards]
        else:
            return
        self.dump()

    def unset_ignored_boards(self, chat_id, phid):
        chat = self.chat(chat_id, False)
        chat['ignored_boards'].remove(phid)
        self.dump()

    def ignored_users(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('ignored_users', [])

    def set_ignored_users(self, chat_id, ignored_users: list):
        chat = self.chat(chat_id, False)
        if 'ignored_users' not in chat:
            chat['ignored_users'] = [ignored_users]
        elif ignored_users not in chat['ignored_users']:
            chat['ignored_users'] += [ignored_users]
        else:
            return
        self.dump()

    def unset_ignored_users(self, chat_id, phid):
        chat = self.chat(chat_id, False)
        chat['ignored_users'].remove(phid)
        self.dump()

    def ignored_columns(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('ignored_columns', [])

    def set_ignored_columns(self, chat_id, ignored_columns: list):
        chat = self.chat(chat_id, False)
        if 'ignored_columns' not in chat:
            chat['ignored_columns'] = [ignored_columns]
        elif ignored_columns not in chat['ignored_columns']:
            chat['ignored_columns'] += [ignored_columns]
        else:
            return
        self.dump()

    def unset_ignored_columns(self, chat_id, value):
        chat = self.chat(chat_id, False)
        chat['ignored_columns'].remove(value)
        self.dump()

    def last_new_check(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('last_new_check')

    def last_update_check(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('last_update_check')

    @property
    def superusers(self) -> list:
        return self.get('superusers')

    def dump(self):
        with codecs.open(self.path, 'w', encoding='utf-8') as config:
            json.dump(self, config, indent=4, ensure_ascii=False)
