# PhabricatorBot
Phabricator notifications telegram bot

## Requirements
- pyTelegramBotAPI
- requests>=2.7.0
- schedule

## Before use
- Run setup.py script to install all requirements
- Register bot in telegram via @BotFather if you haven't done it already
- Add config.json file into the source folder. Minimal structure for config.json: 
```
{
    "tg_api": "TELEGRAM_API_TOKEN",
    "chats": []
}
```

## Usage
- Check [Before use part](#before-use) first. Run bot_runner.py script to start the bot
- Find bot in Telegram and click start or add it in group chat
- Enter `/menu` command to get the bot's main menu
- Follow bot's instructions to setup

Test
