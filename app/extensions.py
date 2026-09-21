"""Shared singletons: Flask app + TeleBot instance."""

import requests
import telebot
from flask import Flask

from app.config import TELEGRAM_TOKEN

app = Flask(__name__)

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()
