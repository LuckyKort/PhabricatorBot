# PhabricatorBot
Phabricator notifications telegram bot

## Requirements
- pyTelegramBotAPI
- requests>=2.7.0
- schedule

## Before use
Add config.json file into the source folder. Minimal structure for config.json: 
```
{
    "tg_api": "TELEGRAM_API_TOKEN",
    "chats": []
}
```
