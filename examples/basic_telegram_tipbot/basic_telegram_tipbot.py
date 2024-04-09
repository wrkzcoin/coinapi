import logging
import typing
import json
import aiohttp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils.markdown import text, bold
from aiogram.utils.markdown import markdown_decoration as markdown
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.filters import (
    Command,
    CommandObject,
    ExceptionMessageFilter,
    ExceptionTypeFilter,
)
from datetime import datetime
from aiogram.types import Message
import asyncio
import sys, traceback
import math
from asyncio import get_event_loop
from config import load_config

config = load_config()

SERVER_BOT = "TELEGRAM"
API_TOKEN = config['telegram']['token']
TX_IN_PROCESS = []
REPLY_TO = {}

# Initialize Bot instance with a default parse mode which will be passed to all API calls
bot = Bot(API_TOKEN)
dp = Dispatcher()  # Initialising event loop for the dispatcher'

def round_amount(amount: float, places: int=5):
    return math.floor(amount *10**places)/10**places

async def logchanbot(content: str) -> None:
    print(content)

async def transfer(
    list_tx, timeout: int=10
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['backend']['url'] + "/transfer",
                headers=headers,
                json=list_tx,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def create_address(
    coin_name: str, tag: str, chat_id: str = None, timeout: int = 8
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        data = {
            "coin": coin_name.upper(),
            "tag": tag.strip()
        }
        if chat_id is not None:
            data = {
                "coin": coin_name.upper(),
                "tag": tag.strip(),
                "second_tag": chat_id
            }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['backend']['url'] + "/newaddress",
                headers=headers,
                json=data,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def get_balance(
    coin_name: str, address: str, timeout: int = 8
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        data = {
            "coin": coin_name.upper(),
            "address": address
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['backend']['url'] + "/balance",
                headers=headers,
                json=data,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def withdraw_coin(
    coin_name: str, from_address: str, to_address: str, amount: float, remark: str, timeout: int = 30
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        data = {
            "coin": coin_name.upper(),
            "from_address": from_address,
            "to_address": to_address,
            "amount": amount,
            "remark": remark
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['backend']['url'] + "/withdraw",
                headers=headers,
                json=data,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def list_address_coins(
    coin_name: str, timeout: int = 30
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config['backend']['url'] + "/list_transactions/" + coin_name,
                headers=headers,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def list_deposit_tx_coin(
    address: str, coin_name: str, timeout: int = 30
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config['backend']['url'] + "/list_transactions/" + coin_name + "/" + address,
                headers=headers,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def list_withdraws_coin(
    address: str, coin_name: str, timeout: int = 30
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config['backend']['url'] + "/list_withdraws/" + coin_name + "/" + address,
                headers=headers,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def noted_tx(
    coin_name: str, tx: str, timeout: int = 30
):
    try:
        headers = {
            'Authorization': config['backend']['api_key'],
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config['backend']['url'] + "/noted/" + coin_name + "/" + tx,
                headers=headers,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def check_coin_status(
    coin_name: str, timeout: int = 30
):
    try:
        headers = {
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config['backend']['url'] + "/status/" + coin_name,
                headers=headers,
                timeout=timeout
            ) as response:
                res_data = await response.read()
                res_data = res_data.decode('utf-8')
                await session.close()
                decoded_data = json.loads(res_data)
                if decoded_data['success'] is True:
                    return decoded_data
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler will be called when user sends `/start` or `/help` command
    """
    if message.chat.type != "private":
        return

    # default row_width is 3, so here we can omit it actually
    # kept for clearness
    await message.reply(
        f"Hello {message.from_user.mention_html()}, Welcome to {config['telegram']['coin_full_name']} TipBot!\n"\
            "Available command: /balance, /withdraw, /tip, /deposit, /coininfo, /withdraws, /deposits\n",
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("deposit"))
async def send_deposit(message: types.Message):
    """
    This handler will be called when user sends `/deposit`
    """
    if message.chat.type != "private":
        reply_text = f"{message.from_user.mention_html()}, please do via direct message with me!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    if message.from_user.username is None:
        reply_text = f"{message.from_user.mention_html()}, I can not get your username. Please set!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return
    
    get_address = await create_address(
        config['telegram']['coin_name'], "{}@{}".format(message.from_user.username, SERVER_BOT), str(message.chat.id), 8
    )
    if get_address is not None:
        message_text = text(
            markdown.bold(f"DEPOSIT {config['telegram']['coin_name']} ADDRESS:\n") + \
            markdown.pre(get_address['data']) + \
            markdown.link("Link to Explorer", config['telegram']['explorer_link'])
        )
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

@dp.message(Command("balance"))
async def send_balance(message: types.Message):
    """
    This handler will be called when user sends `/balance`
    """
    if message.chat.type != "private":
        reply_text = f"{message.from_user.mention_html()}, please do via direct message with me!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    if message.from_user.username is None:
        reply_text = f"{message.from_user.mention_html()}, I can not get your username. Please set!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    get_address = await create_address(
        config['telegram']['coin_name'], "{}@{}".format(message.from_user.username, SERVER_BOT), str(message.chat.id), 8
    )
    if get_address is not None:
        # get balance
        balance = await get_balance(
            config['telegram']['coin_name'], get_address['data'], 10
        )
        message_text = text(
            bold(f"YOUR {config['telegram']['coin_name']} BALANCE:\n") +
            markdown.pre("Username:      " + message.from_user.username + " [Do not change it]") + 
            markdown.pre("Total Balance: " + str(balance['data']['balance']) + " " + config['telegram']['coin_name'])
        )
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        reply_text = f"{message.from_user.mention_html()}, internal error for /balance command. Please report."
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

@dp.message(Command("tip"))
async def send_tip(message: types.Message):
    """
    This handler will be called when user sends `/tip <someone> <amount>`
    """
    if message.from_user.username is None:
        reply_text = f"{message.from_user.mention_html()}, I can not get your username. Please set!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    user_to = None
    extra_message = None
    content = ' '.join(message.text.split())
    args = content.split(" ")

    # Multiple receiers
    receivers = []
    receiver_ids = []
    receiver_addresses = []
    no_wallet_receivers = []
    last_receiver = ""
    comment = ""
    try:
        get_tipper = await create_address(
            config['telegram']['coin_name'], "{}@{}".format(message.from_user.username, SERVER_BOT), None, 8
        )
        # reply to /tip amount @xxx
        if len(args) >= 3 and content.count("@") >= 1:
            for each in args[2:]:
                if each.startswith("@"):
                    last_receiver = each
                    tg_user = each[1:] # remove first @
                    if len(tg_user) == 0:
                        continue
                    if not tg_user.replace('_', '').replace(',', '').isalnum:
                        no_wallet_receivers.append(tg_user)
                    else:
                        # Check user in wallet
                        tg_user = tg_user.replace(',', '')
                        if len(tg_user) < 5:
                            no_wallet_receivers.append(tg_user)
                        else:
                            get_each_user = await create_address(
                                config['telegram']['coin_name'], "{}@{}".format(tg_user, SERVER_BOT), None, 8
                            )
                            if get_each_user is None and tg_user.lower() != config['telegram']['bot_name']:
                                no_wallet_receivers.append(tg_user)
                            elif tg_user.lower() == config['telegram']['bot_name'] or get_each_user is not None:
                                receivers.append(tg_user)
                                if get_each_user.get('second_tag'):
                                    receiver_ids.append(get_each_user['second_tag'])
                                receiver_addresses.append(get_each_user['data'])

        # Check if reply to
        if message.reply_to_message and message.reply_to_message.from_user.username and \
            message.reply_to_message.from_user.username not in receivers:
            receivers.append(message.reply_to_message.from_user.username)

        # Unique: receivers
        receivers = list(set(list(receivers)))
        # Remove author if exist
        if len(receivers) > 0 and message.from_user.username in receivers:
            receivers.remove(message.from_user.username)
            receiver_addresses.remove(get_tipper['data'])

        if len(receiver_addresses) == 0:
            message_text = text(bold('ERROR:'), f"{message.from_user.mention_html()}, there is no one tip to.")
            if len(no_wallet_receivers) > 0:
                message_text += text(bold('USER NO WALLET:'), markdown.pre("{}".format(", ".join(no_wallet_receivers))))
            await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            return
        else:
            try:
                comment = message.text.split(last_receiver)[-1].strip()
            except Exception as e:
                pass

            send_all = False
            amount = args[1].replace(",", "")    
            if get_tipper is None:
                message_text = f"{message.from_user.mention_html()}, internal error, please report!"
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                return

            min_tx = config['telegram']['min_tip']
            max_tx = config['telegram']['max_tip']

            # get balance
            balance = await get_balance(
                config['telegram']['coin_name'], get_tipper['data'], 10
            )
            actual_balance = balance['data']['balance']
            if amount.upper() == "ALL":
                amount = actual_balance
                send_all = True
            try:
                amount = float(amount)
            except ValueError:
                message_text = f"{message.from_user.mention_html()}, invalid amount."
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                return 

            if actual_balance <= 0:
                message_text = f"{message.from_user.mention_html()}, please check your {config['telegram']['coin_name']} balance."
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                # log_invalid_transfer
                return

            if amount < 0:
                message_text = f"{message.from_user.mention_html()}, invalid {config['telegram']['coin_name']} amount."
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                return
            elif amount*len(receiver_addresses) > actual_balance:
                message_text = f"{message.from_user.mention_html()}, insufficient balance to tip out {round_amount(amount)} {config['telegram']['coin_name']}. Having {round_amount(actual_balance)} {config['telegram']['coin_name']}."
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                #log_invalid_transfer
                return
            elif amount < min_tx and send_all == False:
                message_text = f"{message.from_user.mention_html()}, tipping cannot be smaller than {round_amount(min_tx)} {config['telegram']['coin_name']}." 
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                return
            elif amount > max_tx:
                message_text = f"{message.from_user.mention_html()}, tipping cannot be bigger than {round_amount(max_tx)} {config['telegram']['coin_name']}."
                await message.reply(message_text, parse_mode=ParseMode.HTML)
                return
            # OK we can tip
            if message.from_user.username not in TX_IN_PROCESS:
                TX_IN_PROCESS.append(message.from_user.username)
                try:
                    extra_message = comment[:256] if len(comment) > 0 else ""
                    list_tx = []
                    for ea in receiver_addresses:
                        list_tx.append({
                            "coin": config['telegram']['coin_name'],
                            "from_address": get_tipper['data'],
                            "to_address": ea,
                            "amount": amount,
                            "remark": extra_message
                        })
                    tip = await transfer(
                        list_tx
                    )
                    if tip is not None:
                        each_amount = ""
                        if len(receiver_addresses) > 1:
                            each_amount = " / Each got: {} {}".format(round_amount(amount), config['telegram']['coin_name'])
                        message_text = text(bold('TIPPED: {} {}{}'.format( round_amount(amount*len(receiver_addresses)), config['telegram']['coin_name'], each_amount)),
                                            markdown.pre("{}".format(", ".join(receivers))))
                        if len(no_wallet_receivers) > 0:
                            message_text += text(bold('USER NO WALLET:'),
                                                 markdown.pre("{}".format(", ".join(no_wallet_receivers))))
                        if len(extra_message) > 0:
                            message_text += text(bold('MEMO:'),
                                                 markdown.pre(extra_message))
                        to_message_text = text(bold(f"TIP RECEIVED FROM: "), markdown.pre("@{}".format(message.from_user.username)), markdown.pre("Amount: {} {}".format(round_amount(amount), config['telegram']['coin_name'])))
                        if len(extra_message) > 0:
                            to_message_text += text(bold('MEMO:'),
                                                    markdown.pre(extra_message))
                        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
                        receiver_ids = list(set(receiver_ids))
                        if len(receiver_ids) > 0:
                            for each_user in receiver_ids:
                                try:
                                    if each_user.lower() == config['telegram']['bot_name']:
                                        await logchanbot(f"[{SERVER_BOT}] A user tipped {round_amount(amount)} {config['telegram']['coin_name']} to {each_user}")
                                    else:
                                        await bot.send_message(chat_id=each_user, text=to_message_text, parse_mode=ParseMode.MARKDOWN_V2)
                                        print(f"Tip from {message.from_user.username} -> {str(each_user)} - {round_amount(amount)} {config['telegram']['coin_name']}.")
                                except Exception as e:
                                    await logchanbot(traceback.print_exc(file=sys.stdout))
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)
                    await logchanbot(traceback.format_exc())
                TX_IN_PROCESS.remove(message.from_user.username)
            else:
                # reject and tell to wait
                message_text = f"{message.from_user.mention_html()}, you have another tx in process. Please wait it to finish."
                await message.reply(message_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)

@dp.message(Command("withdraw"))
async def send_withdraw(message: types.Message):
    """
    This handler will be called when user sends `/withdraw <amount> <address>`
    """

    if message.chat.type != "private":
        reply_text = f"{message.from_user.mention_html()}, please do via direct message with me!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    if message.from_user.username is None:
        reply_text = f"{message.from_user.mention_html()}, I can not get your username. Please set!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    send_all = False
    content = ' '.join(message.text.split())
    args = content.split(" ")
    if len(args) != 3:
        message_text = text(bold('ERROR:'),
                            markdown.pre("Please use /withdraw amount address"))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        return
    to_address = args[2]
    amount = args[1].replace(",", "")

    min_tx = config['telegram']['min_withdraw']
    max_tx = config['telegram']['max_withdraw']
    tx_fee = config['telegram']['tx_fee']

    get_address = await create_address(
        config['telegram']['coin_name'], "{}@{}".format(message.from_user.username, SERVER_BOT), str(message.chat.id), 8
    )
    # get balance
    balance = await get_balance(
        config['telegram']['coin_name'], get_address['data'], 10
    )
    actual_balance = balance['data']['balance']
    if amount.upper() == "ALL" and actual_balance > tx_fee:
        amount = actual_balance - tx_fee
        send_all = True
    try:
        amount = float(amount)
    except ValueError:
        message_text = text(bold('ERROR:'), markdown.pre("Invalid amount."))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        return

    # If balance 0, no need to check anything
    if actual_balance <= 0:
        message_text = text(bold('ERROR:'), markdown.pre(f"Please check your {config['telegram']['coin_name']} balance."))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        #log_invalid_transfer
        return

    if amount > actual_balance:
        message_text = text(bold('ERROR:'), markdown.pre(f"Insufficient balance to send out {round_amount(amount)} {config['telegram']['coin_name']}. Having {round_amount(actual_balance)} {config['telegram']['coin_name']}."))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        #log_invalid_transfer
        return

    if amount < 0:
        message_text = text(bold('ERROR:'), markdown.pre(f"Invalid {config['telegram']['coin_name']} amount"))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        return
    elif amount + tx_fee > actual_balance:
        message_text = text(bold('ERROR:'),
                            markdown.pre(f"Insufficient balance to send out {round_amount(amount)} {config['telegram']['coin_name']}\nYou need to leave at least fee: {round_amount(tx_fee)} {config['telegram']['coin_name']}. Having {round_amount(actual_balance)} {config['telegram']['coin_name']}."))
        #log_invalid_transfer
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        return
    elif amount < min_tx and send_all == False:
        message_text = text(bold('ERROR:'), markdown.pre(f"Transaction cannot be smaller than {round_amount(min_tx)} {config['telegram']['coin_name']}"))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        return
    elif amount > max_tx:
        message_text = text(bold('ERROR:'), markdown.pre(f"Transaction cannot be bigger than {round_amount(max_tx)} {config['telegram']['coin_name']}"))
        await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        return

    if message.from_user.username not in TX_IN_PROCESS:
        TX_IN_PROCESS.append(message.from_user.username)
        try:
            sending_tx = await withdraw_coin(
                config['telegram']['coin_name'], get_address['data'], to_address, amount, "withdraw by {}@{}".format(message.from_user.username, SERVER_BOT), 30
            )
            if sending_tx is not None:
                await logchanbot(f"[{SERVER_BOT}] A user sucessfully /withdraw {round_amount(amount)} {config['telegram']['coin_name']}")
                message_text = text(bold('SUCCESS:'), markdown.pre(f"You have withdrawn {round_amount(amount)} {config['telegram']['coin_name']} to {to_address}\nTransaction hash: {sending_tx['data']}"))
                await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await logchanbot(f"[{SERVER_BOT}] A user failed to /withdraw {round_amount(amount)} {config['telegram']['coin_name']}")
                message_text = text(bold('FAIL:'), markdown.pre(f"You failed to withdraw {round_amount(amount)} {config['telegram']['coin_name']} to {to_address}. Please report!"))
                await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            message_text = text(bold('ERROR:'), markdown.pre('Internal error. Please report!'))
            await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            await logchanbot(f"[{SERVER_BOT}] A user failed to /withdraw {round_amount(amount)} {config['telegram']['coin_name']}")
            await logchanbot(traceback.format_exc())
        TX_IN_PROCESS.remove(message.from_user.username)
    else:
        # reject and tell to wait
        message_text = f"{message.from_user.mention_html()}, you have another tx in process. Please wait it to finish."
        await message.reply(message_text, parse_mode=ParseMode.HTML)
        return

@dp.message(Command("withdraws"))
async def send_withdraw_list(message: types.Message):
    """
    This handler will be called when user sends `/withdraws`
    """
    if message.chat.type != "private":
        reply_text = f"{message.from_user.mention_html()}, please do via direct message with me!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    if message.from_user.username is None:
        reply_text = f"{message.from_user.mention_html()}, I can not get your username. Please set!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return
    
    get_address = await create_address(
        config['telegram']['coin_name'], "{}@{}".format(message.from_user.username, SERVER_BOT), str(message.chat.id), 8
    )
    if get_address is not None:
        list_withdraws = await list_withdraws_coin(get_address['data'], config['telegram']['coin_name'], 30)
        if list_withdraws is None:
            message_text = text(bold('ERROR:'), markdown.pre("Internal error, please report!"))
            await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            return
        else:
            if len(list_withdraws) == 0:
                message_text = text(bold('INFO:'), markdown.pre("You don't have withdraw history!"))
                await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
                return
            else:
                list_tx = []
                for ea in list_withdraws['data']:
                    list_tx.append("{} {} - tx: {}".format(
                        ea['amount'], ea['coin_name'], ea['txid']
                    ))
                message_text = text(
                    markdown.bold(f"LIST {config['telegram']['coin_name']} WITHDRAWS:\n") + \
                    markdown.pre("\n".join(list_tx))
                )
                await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

@dp.message(Command("deposits"))
async def send_deposit_list(message: types.Message):
    """
    This handler will be called when user sends `/deposits`
    """
    if message.chat.type != "private":
        reply_text = f"{message.from_user.mention_html()}, please do via direct message with me!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return

    if message.from_user.username is None:
        reply_text = f"{message.from_user.mention_html()}, I can not get your username. Please set!"
        await message.reply(reply_text, parse_mode=ParseMode.HTML)
        return
    
    get_address = await create_address(
        config['telegram']['coin_name'], "{}@{}".format(message.from_user.username, SERVER_BOT), str(message.chat.id), 8
    )
    if get_address is not None:
        list_withdraws = await list_deposit_tx_coin(get_address['data'], config['telegram']['coin_name'], 30)
        if list_withdraws is None:
            message_text = text(bold('ERROR:'), markdown.pre("Internal error, please report!"))
            await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
            return
        else:
            if len(list_withdraws) == 0:
                message_text = text(bold('INFO:'), markdown.pre("You don't have withdraw history!"))
                await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
                return
            else:
                list_tx = []
                for ea in list_withdraws['data']:
                    list_tx.append("{} {} - tx: {}".format(
                        ea['amount'], ea['coin_name'], ea['txid']
                    ))
                message_text = text(
                    markdown.bold(f"LIST {config['telegram']['coin_name']} DEPOSITS:\n") + \
                    markdown.pre("\n".join(list_tx))
                )
                await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

@dp.message(Command("coininfo"))
async def send_coininfo(message: types.Message):
    """
    This handler will be called when user sends `/coininfo`
    """
    message_text = text(
        bold(f"COIN NAME {config['telegram']['coin_name']}\n") +
        markdown.pre("Min Tip:      " + str(config['telegram']['min_tip'])) + 
        markdown.pre("Max Tip:      " + str(config['telegram']['max_tip'])) +
        markdown.pre("Min Withdraw: " + str(config['telegram']['min_withdraw'])) + 
        markdown.pre("Max Withdraw: " + str(config['telegram']['max_withdraw'])) +
        markdown.pre("Withdraw Fee: " + str(config['telegram']['tx_fee'])) +
        markdown.pre("Chain Height: " + str(config['telegram']['chain_height']))
    )
    await message.reply(message_text, parse_mode=ParseMode.MARKDOWN_V2)
    return

async def get_coin_status():
    """
    Background task which is created when bot starts
    """
    while True:
        try:
            get_coin_info = await check_coin_status(config['telegram']['coin_name'])
            if get_coin_info is not None:
                if config['telegram']['min_tip'] != get_coin_info['data']['min_transfer']:
                    print("{} Updated setting min_tip from {} to {}.".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config['telegram']['min_tip'], get_coin_info['data']['min_transfer'])
                    )
                    config['telegram']['min_tip'] = get_coin_info['data']['min_transfer']
                if config['telegram']['max_tip'] != get_coin_info['data']['max_transfer']:
                    print("{} Updated setting max_tip from {} to {}.".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config['telegram']['max_tip'], get_coin_info['data']['max_transfer'])
                    )
                    config['telegram']['max_tip'] = get_coin_info['data']['max_transfer']
                if config['telegram']['min_withdraw'] != get_coin_info['data']['min_withdraw']:
                    print("{} Updated setting min_withdraw from {} to {}.".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config['telegram']['min_withdraw'], get_coin_info['data']['min_withdraw'])
                    )
                    config['telegram']['min_withdraw'] = get_coin_info['data']['min_withdraw']
                if config['telegram']['max_withdraw'] != get_coin_info['data']['max_withdraw']:
                    print("{} Updated setting max_withdraw from {} to {}.".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config['telegram']['max_withdraw'], get_coin_info['data']['max_withdraw'])
                    )
                    config['telegram']['max_withdraw'] = get_coin_info['data']['max_withdraw']
                if float(config['telegram']['tx_fee']) != float(get_coin_info['data']['tx_fee']):
                    print("{} Updated setting tx_fee from {} to {}.".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config['telegram']['tx_fee'], get_coin_info['data']['tx_fee'])
                    )
                    config['telegram']['tx_fee'] = get_coin_info['data']['tx_fee']
                if str(config['telegram']['chain_height']) != str(get_coin_info['data']['chain_height']):
                    print("{} Updated setting chain_height from {} to {}.".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), config['telegram']['chain_height'], get_coin_info['data']['chain_height'])
                    )
                    config['telegram']['chain_height'] = get_coin_info['data']['chain_height']
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        await asyncio.sleep(30.0)
    
async def check_deposit():
    """
    Background task which is created when bot starts
    """
    while True:
        collect_deposits = await list_address_coins(config['telegram']['coin_name'])
        if collect_deposits is None or len(collect_deposits['data']) == 0:
            await asyncio.sleep(5.0)
        else:
            for ea in collect_deposits['data']:
                try:
                    if ea.get('noted') is not None and ea['noted'] == 0 and ea.get('second_tag') is not None and ea['second_tag'].isdigit():
                        message_text = text(
                            bold("NEW DEPOSIT\n"),
                            markdown.pre("Amount:  {} {}\nTx:      {}".format(ea['amount'], ea['coin_name'], ea['txid']))
                        )
                        try:
                            operator = Bot(API_TOKEN)
                            await operator.send_message(chat_id=int(ea['second_tag']), text=message_text, parse_mode=ParseMode.MARKDOWN_V2)
                        except Exception as e:
                             traceback.print_exc(file=sys.stdout)
                        # noted tx
                        await noted_tx(
                            ea['coin_name'], ea['txid'], 10
                        )
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)
        await asyncio.sleep(20.0)

async def main() -> None:
    # And the run events dispatching
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    loop = asyncio.new_event_loop()
    loop.create_task(check_deposit())
    loop.create_task(get_coin_status())
    loop.run_until_complete(main())