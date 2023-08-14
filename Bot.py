import asyncio
import datetime
import time

from init import init
from admin import *
from games import *
import logging
import os
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Dice, Bot
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler, MessageHandler, filters, TypeHandler, BaseHandler,
)
from MenuHandle import *
from MyCommandHandler import *
from Config import config
from games import gambling
from keyboard import start_keyboard, start_keyboard_admin
from v2board import _bind, _checkin, _traffic, _lucky, _addtime
from models import Db, BotDb, BotUser
from Utils import START_ROUTES, END_ROUTES
from threading import Thread

# 加载不需要热加载的配置项
TOKEN = config.TELEGRAM.token
HTTP_PROXY = config.TELEGRAM.http_proxy
HTTPS_PROXY = config.TELEGRAM.https_proxy

if HTTP_PROXY.find('未配置') == -1:
    os.environ['HTTP_PROXY'] = HTTP_PROXY
if HTTPS_PROXY.find('未配置') == -1:
    os.environ['HTTPS_PROXY'] = HTTPS_PROXY

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_telegram_id = config.TELEGRAM.admin_telegram_id
    if type(admin_telegram_id) == str:
        config.TELEGRAM.admin_telegram_id = update.effective_user.id
        admin_telegram_id = config.TELEGRAM.admin_telegram_id
        config.save()
    if update.effective_user.id == admin_telegram_id and update.effective_message.chat.type == 'private':
        reply_markup = InlineKeyboardMarkup(start_keyboard_admin)
    else:
        reply_markup = InlineKeyboardMarkup(start_keyboard)
    # await context.bot.send_message(chat_id=update.effective_chat.id, text='my Bot', reply_markup=reply_markup)
    await update.message.reply_text(config.TELEGRAM.title, reply_markup=reply_markup, disable_web_page_preview=True)
    return START_ROUTES


async def start_over(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admin_telegram_id = config.TELEGRAM.admin_telegram_id
    if update.effective_user.id == admin_telegram_id and update.effective_message.chat.type == 'private':
        reply_markup = InlineKeyboardMarkup(start_keyboard_admin)
    else:
        reply_markup = InlineKeyboardMarkup(start_keyboard)
    # await context.bot.send_message(chat_id=update.effective_chat.id, text='my Bot', reply_markup=reply_markup)
    await query.edit_message_text(config.TELEGRAM.title, reply_markup=reply_markup, disable_web_page_preview=True)
    return START_ROUTES


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="欢迎下次光临！")
    return ConversationHandler.END


# 获取电报id
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_user.id, text=update.effective_chat.id)


async def handle_input_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    try:
        text = _addtime(int(user_input))
    except:
        text = '输入有误，请输入整数'
    await update.message.reply_text(text)
    return ConversationHandler.END


class Mybot(Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message_dict = {}
        thread = Thread(target=self.th_delete_message)
        thread.start()

    def th_delete_message(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.async_delete_message())
        loop.close()

    async def async_delete_message(self):
        while True:
            for chat_id, message_list in self._message_dict.items():
                flag = False
                for idx, message_info in enumerate(message_list):
                    # print(time.time(), message_info['time'], time.time() - message_info['time'])
                    if time.time() - message_info['time'] > config.TELEGRAM.delete_message:
                        try:
                            await self.deleteMessage(message_info['chat_id'], message_id=message_info['user_message_id'],
                                                     pool_timeout=30)
                        except:
                            # print(message_info, '删除失败，可能该消息已经被删除')
                            pass
                        try:
                            await self.deleteMessage(message_info['chat_id'], message_id=message_info['bot_message_id'],
                                                     pool_timeout=30)
                        except:
                            # print(message_info, '删除失败，可能该消息已经被删除')
                            pass
                        self._message_dict[chat_id].pop(idx)
                    else:
                        flag = True
                        break
                if flag:
                    break

            await asyncio.sleep(2)

    async def add_message_dict(self, botmessage):
        if botmessage.reply_to_message:
            chat_id = botmessage.chat.id
            message_info = {
                'chat_id': botmessage.chat.id,
                'bot_message_id': botmessage.id,
                'user_message_id': botmessage.reply_to_message.message_id,
                'time': time.time()
            }
            if self._message_dict.get(chat_id):
                self._message_dict[chat_id].append(message_info)
            else:
                self._message_dict[chat_id] = [message_info]

    async def send_message(self, **kwargs):
        botmessage = await super().send_message(**kwargs)
        await self.add_message_dict(botmessage)
        return botmessage

    async def send_dice(self, **kwargs):
        botmessage = await super().send_dice(**kwargs)
        await self.add_message_dict(botmessage)
        return botmessage


if __name__ == '__main__':
    # 面板数据库连接
    Db.connect()
    if os.path.exists('bot.db'):
        res = BotDb.connect()
    else:
        res = BotDb.connect()
        BotDb.create_tables([BotUser])
    bot = Mybot(token=TOKEN)
    application = Application.builder().bot(bot).build()

    CommandList = [
        CommandHandler("start", start),
        CommandHandler("myid", myid),
        CommandHandler("checkin", command_checkin),  # 处理签到命令
        CommandHandler('bind', command_bind),  # 处理绑定命令
        CommandHandler('unbind', command_unbind),  # 处理解绑命令
        CommandHandler('lucky', command_lucky),  # 处理幸运抽奖命令
        CommandHandler('wallet', command_wallet),  # 处理查看钱包命令
        CommandHandler('traffic', command_traffic),  # 处理查看流量命令
        CallbackQueryHandler(start_over, pattern="^start_over$"),
        MessageHandler(filters.Text(['不玩了', '退出', 'quit']), quit_game),
        MessageHandler(filters.Dice(), gambling),
    ]
    conv_handler = ConversationHandler(
        entry_points=CommandList,
        states={
            START_ROUTES: [
                CallbackQueryHandler(menu_addtime, pattern="^addtime"),
                CallbackQueryHandler(bot_settings, pattern="^bot_settings"),
                CallbackQueryHandler(setting_reload, pattern="^setting_reload"),
                CallbackQueryHandler(game_settings, pattern="^game_settings"),
                CallbackQueryHandler(start_game, pattern="^start_game"),
                CallbackQueryHandler(select_flow, pattern="^[1-9]|10GB|xGB$"),
                # CallbackQueryHandler(menu_gambling, pattern="^gambling"),
                CallbackQueryHandler(menu_wallet, pattern="^wallet"),
                CallbackQueryHandler(menu_checkin, pattern="^checkin$"),
                CallbackQueryHandler(menu_sub, pattern="^sub$"),
                CallbackQueryHandler(menu_mysub, pattern="^mysub"),
                CallbackQueryHandler(menu_traffic, pattern="^traffic$"),
                CallbackQueryHandler(menu_lucky, pattern="^lucky"),
                CallbackQueryHandler(menu_node, pattern="^node"),
                CallbackQueryHandler(end, pattern="^end$"),
                # CallbackQueryHandler(three, pattern="^" + str(THREE) + "$"),
                # CallbackQueryHandler(four, pattern="^" + str(FOUR) + "$"),
            ],
            # WAITING_INPUT: [
            #     MessageHandler(filters.Text(['不玩了', '退出', 'quit']), quit_input),
            #     MessageHandler(filters.Dice(), gambling),
            # ],
            'addtime': [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input_text)
            ],
            'bot_settings': [
                CallbackQueryHandler(settings, pattern="^settings"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings)
            ],
            'game_settings': [
                CallbackQueryHandler(game_switch, pattern="^game_switch"),
                CallbackQueryHandler(select_game, pattern="^select_game"),
                CallbackQueryHandler(game_rate, pattern="^game_rate"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, game_rate)

                # CallbackQueryHandler(game_tiger, pattern="^game_tiger"),  # 已废弃
                # CallbackQueryHandler(tiger_switch, pattern="^tiger_switch$"),  # # 已废弃
                # CallbackQueryHandler(tiger_rate, pattern="^tiger_rate"),  # # 已废弃
            ],
            # 'tiger_rate': [
            #     MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tiger_rate)
            # ],
            'input_betting': [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_flow),
            ]
        },
        fallbacks=CommandList,
    )

    application.add_handler(conv_handler)

    # 异步运行
    application.run_polling()

    # 关闭数据库
    Db.close()
    BotDb.close()
