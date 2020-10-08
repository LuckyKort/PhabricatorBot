# PhabricatorBot
Phabricator notifications telegram bot

Requires pyTelegramBotAPI module installed

Uses config file config.xml with structure:

```
<?xml version="1.0" encoding="windows-1251"?>
<keys>
   <tgapi> telegram api key </tgapi>
   <phapi> phabricator api key </phapi>
   <chatid> telegram chat id </chatid>
   <server> phabricator link </server>
   <board> phabricator board name </board>
   <last_time> key to store last check time </last_time>
   <move_ignore> PHIDs of board to be ignored when checking movement between columns </move_ignore>
</keys>
```
