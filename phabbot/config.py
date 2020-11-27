import json
import os.path


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

        with open(path, 'r') as config:
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

    def active(self, chat_id):
        chat = self.chat(chat_id, False)
        return bool(chat.get('active'))

    def server(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('server')

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

    def boards(self, chat_id) -> list:
        chat = self.chat(chat_id, False)
        return chat.get('boards')

    def set_boards(self, chat_id, boards: list):
        chat = self.chat(chat_id, False)
        chat['boards'] = boards
        self.dump()

    def ignored_boards(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('ignored_boards')

    def set_ignored_boards(self, chat_id, ignored_boards):
        chat = self.chat(chat_id, False)
        chat['ignored_boards'] = ignored_boards
        self.dump()

    def unset_ignored_boards(self, chat_id):
        chat = self.chat(chat_id, False)
        chat['ignored_boards'] = []
        self.dump()

    def ignored_columns(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('ignored_columns')

    def set_ignored_columns(self, chat_id, ignored_columns):
        chat = self.chat(chat_id, False)
        chat['ignored_columns'] = ignored_columns
        self.dump()

    def unset_ignored_columns(self, chat_id):
        chat = self.chat(chat_id, False)
        chat['ignored_columns'] = []
        self.dump()

    def last_new_check(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('last_new_check')

    def last_update_check(self, chat_id):
        chat = self.chat(chat_id, False)
        return chat.get('last_update_check')

    def dump(self):
        with open(self.path, 'w') as config:
            json.dump(self, config, indent=4)
