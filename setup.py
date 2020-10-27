from setuptools import setup

setup(
    name='PhabricatorBot',
    version='2.0',
    packages=['phabbot'],
    url='https://github.com/LuckyKort/PhabricatorBot',
    license='',
    author='LuckyKort',
    author_email='madkort@icloud.com',
    description='Phabricator notifications telegram bot',
    install_requires=[
        'requests>=2.7.0',
        'pyTelegramBotAPI',
        'schedule',
        'pytz',
        'tzlocal',
        'lxml',
        'json',
        'os'
    ]
)
