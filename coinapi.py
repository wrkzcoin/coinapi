from fastapi import FastAPI, Response, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
import secrets

from pydantic import BaseModel
import asyncio
from hashlib import sha256
import aiohttp
import time
from datetime import datetime
import traceback, sys
import uvicorn
import os
from typing import Union, List, Dict
import random
import redis
import pickle
import json
import uuid
import aiomysql
import math
from aiomysql.cursors import DictCursor
from cachetools import TTLCache
from discord_webhook import AsyncDiscordWebhook

from config import load_config

app = FastAPI(
    title="CoinAPI",
    version="0.0.1",
    contact={
        "name": "Pluton",
        "url": "http://chat.wrkz.work/",
        "email": "team@bot.tips",
    },
    docs_url="/manual"
)
config = load_config()
pool = None
api_ttlcache = TTLCache(maxsize=1024, ttl=10.0)

## make random paymentid:
def paymentid(length=None):
    if length is None:
        length = 32
    return secrets.token_hex(length)

def round_amount(amount: float, places: int):
    return math.floor(amount *10**places)/10**places

async def log_to_discord(content: str, webhook: str=None) -> None:
    try:
        if webhook is None:
            url = config['log']['discord_webhook_default']
        else:
            url = webhook
        webhook = AsyncDiscordWebhook(
            url=url,
            content=content[:1000],
        )
        await webhook.execute()
    except Exception as e:
        traceback.print_exc(file=sys.stdout)

async def open_connection():
    global pool
    try:
        if pool is None:
            pool = await aiomysql.create_pool(
                host=config['mysql']['host'], port=3306, minsize=4, maxsize=8,
                user=config['mysql']['user'], password=config['mysql']['password'],
                db=config['mysql']['db'], cursorclass=DictCursor, autocommit=True
            )
    except:
        print("ERROR: Unexpected error: Could not connect to MySql instance.")
        traceback.print_exc(file=sys.stdout)

async def get_coin_setting():
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                coin_list = {}
                sql = """
                SELECT * FROM `coin_settings` 
                WHERE `enable`=1
                """
                await cur.execute(sql, ())
                result = await cur.fetchall()
                if result and len(result) > 0:
                    for each in result:
                        coin_list[each['coin_name']] = each
                    return coin_list
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def get_coin_deposits():
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                coin_addresses = []
                coin_list_key = {}
                sql = """
                SELECT * FROM `deposit_addresses` 
                """
                await cur.execute(sql,)
                result = await cur.fetchall()
                if result and len(result) > 0:
                    for each in result:
                        coin_list_key["{}_{}".format(each['coin_name'], each['address'])] = each
                        coin_addresses.append(each['address'])
                    return {"by_key": coin_list_key, "addresses": coin_addresses}
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def get_api_by_key(key: str):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                SELECT * FROM `api_users` 
                WHERE `api_key`=%s
                """
                await cur.execute(sql, key)
                result = await cur.fetchone()
                if result:
                    return result
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def update_top_block(coin_name: str, height: int):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                UPDATE `coin_settings` SET `chain_height`=%s, `chain_height_set_time`=%s
                WHERE `coin_name`=%s LIMIT 1;
                """
                await cur.execute(sql, (height, int(time.time()), coin_name))
                await conn.commit()
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def insert_address(
    api_id: int, coin_name: str, address: str, extra: str, priv_key: str, tag: str, second_tag: str = None
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                INSERT INTO `deposit_addresses` (`api_id`, `coin_name`, `created_date`, `address`, `address_extra`, `private_key`, `tag`, `second_tag`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                await cur.execute(sql, (api_id, coin_name, int(time.time()), address, extra, priv_key, tag, second_tag))
                await conn.commit()
                return cur.lastrowid
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def get_balance_coin_address(
    api_id: int, coin_name: str, address: str
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                SELECT * FROM `deposit_addresses` 
                WHERE `api_id`=%s AND `coin_name`=%s AND `address`=%s LIMIT 1;
                """
                await cur.execute(sql, (api_id, coin_name, address))
                result = await cur.fetchone()
                if result:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None

async def transfer_records(
    records
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                INSERT INTO `transfer_records` (`api_id`, `from_address`, `to_address`, `amount`, `coin_name`, `purpose`, `timestamp`, `ref_uuid`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                await cur.executemany(sql, records)
                await conn.commit()
                return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False

async def insert_hold_address(coin_name: str, api_id: int, deposit_id: int, address: str, amount: float, time_expiring: int, purpose: str):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                INSERT INTO `balance_holds` (`coin_name`, `api_id`, `deposit_id`, `address`, `hold_amount`, `time_insert`, `time_expiring`, `purpose`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                await cur.execute(sql, (coin_name, api_id, deposit_id, address, amount, int(time.time()), time_expiring, purpose))
                await conn.commit()
                return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False

async def delete_hold_address():
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                DELETE FROM `balance_holds` WHERE `time_expiring`<UNIX_TIMESTAMP()
                """
                await cur.execute(sql,)
                await conn.commit()
                return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False

async def insert_api_log(api_id: int, method: str, data: str, result: str):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                INSERT INTO `api_logs` (`api_id`, `method`, `data`, `result`, `time`)
                VALUES (%s, %s, %s, %s, %s)
                """
                await cur.execute(sql, (api_id, method, data, result, int(time.time())))
                await conn.commit()
                return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False

async def insert_api_failed_log(api_id: int, method: str, data: str, result: str):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                INSERT INTO `api_logs_failed` (`api_id`, `method`, `data`, `result`, `time`)
                VALUES (%s, %s, %s, %s, %s)
                """
                await cur.execute(sql, (api_id, method, data, result, int(time.time())))
                await conn.commit()
                return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False

async def find_tx_coin(
    coin_name: str, tx: str, api_id: int
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                SELECT * FROM `deposits` 
                WHERE `api_id`=%s AND `coin_name`=%s AND `txid`=%s LIMIT 1;
                """
                await cur.execute(sql, (api_id, coin_name, tx))
                result = await cur.fetchone()
                if result:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None

async def note_tx_coin(
    coin_name: str, tx: str, api_id: int, depost_id: int
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                UPDATE `deposits`
                SET `already_noted`=%s, `noted_time`=%s
                WHERE `api_id`=%s AND `coin_name`=%s AND `txid`=%s AND `depost_id`=%s LIMIT 1;
                """
                await cur.execute(sql, (1, int(time.time()), api_id, coin_name, tx, depost_id))
                await conn.commit()
                return True
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return False

async def update_second_tag(
    coin_name: str, dep_id: int, second_tag: str
):
    global pool
    try:
        if second_tag is None:
            return False
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                UPDATE `deposit_addresses`
                SET `second_tag`=%s
                WHERE `coin_name`=%s AND `id`=%s LIMIT 1;
                """
                await cur.execute(sql, (second_tag, coin_name, dep_id))
                await conn.commit()
                return True
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return False

async def find_address_coin_tag(
    coin_name: str, tag: str, api_id: int
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                SELECT * FROM `deposit_addresses` 
                WHERE `api_id`=%s AND `coin_name`=%s AND `tag`=%s LIMIT 1;
                """
                await cur.execute(sql, (api_id, coin_name, tag))
                result = await cur.fetchone()
                if result:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return None

async def get_addresses_coin_api(
    coin_name: str, api_id: int
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                SELECT `coin_name`, `created_date`, `address`, `address_extra`, `tag`, `total_deposited`, `numb_deposit`, 
                `total_received`, `numb_received`, `total_sent`, `numb_sent`, `total_withdrew`, `numb_withdrew` FROM `deposit_addresses` 
                WHERE `api_id`=%s AND `coin_name`=%s
                """
                await cur.execute(sql, (api_id, coin_name))
                result = await cur.fetchall()
                if result:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return []

async def get_txes_address_coin_api(
    coin_name: str, api_id: int, address: str = None, limit: int = 1000
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql_addr = ""
                data_rows = [api_id, coin_name]
                if address is not None:
                    sql_addr = " AND `deposits`.`address`=%s"
                    data_rows.append(address)
                sql = """
                SELECT `deposits`.*, `deposit_addresses`.`tag`, `deposit_addresses`.`second_tag` FROM `deposits` 
                INNER JOIN  `deposit_addresses` ON `deposit_addresses`.`id`=`deposits`.`depost_id` 
                WHERE `deposits`.`api_id`=%s AND `deposits`.`coin_name`=%s 
                """ +sql_addr+ """
                ORDER BY `deposits`.`time_insert` DESC
                LIMIT %s
                """
                data_rows.append(limit)
                await cur.execute(sql, tuple(data_rows))
                result = await cur.fetchall()
                if result:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return []

async def get_withdraws_address_coin_api(
    coin_name: str, api_id: int, address: str = None, limit: int = 1000
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql_addr = ""
                data_rows = [api_id, coin_name]
                if address is not None:
                    sql_addr = " AND `withdraws`.`from_address`=%s"
                    data_rows.append(address)
                sql = """
                SELECT `withdraws`.*, `deposit_addresses`.`tag`, `deposit_addresses`.`second_tag` FROM `withdraws` 
                INNER JOIN  `deposit_addresses` ON `deposit_addresses`.`address`=`withdraws`.`from_address` 
                WHERE `withdraws`.`api_id`=%s AND `withdraws`.`coin_name`=%s 
                """ +sql_addr+ """
                ORDER BY `withdraws`.`timestamp` DESC
                LIMIT %s
                """
                data_rows.append(limit)
                await cur.execute(sql, tuple(data_rows))
                result = await cur.fetchall()
                if result:
                    return result
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
    return []

async def insert_withdraw_success(
    api_id: int, coin_name: str, from_address: str, amount: float, fee_and_tax: float, from_deposit_id: int,
    to_address: str, txid: str, tx_key: str, remark: str, ref_uuid: str
):
    global pool
    try:
        await open_connection()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                sql = """
                INSERT INTO `withdraws` (`api_id`, `coin_name`, `from_address`, `amount`, `fee_and_tax`, `from_deposit_id`,
                `to_address`, `txid`, `tx_key`, `timestamp`, `remark`, `ref_uuid`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                await cur.execute(sql, (
                    api_id, coin_name, from_address, amount, fee_and_tax, from_deposit_id, to_address,
                    txid, tx_key, int(time.time()), remark, ref_uuid
                ))
                await conn.commit()
                return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False
# End of database

async def xmr_make_integrate(
    url: str, main_address: str
):
    try:
        headers = {
            'Content-Type': 'application/json'
        }
        json_data = {
            "jsonrpc": "2.0",
            "id":"0",
            "method":"make_integrated_address",
            "params":{
                "standard_address": main_address
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers, timeout=15) as response:
                if response.status == 200:
                    res_data = await response.read()
                    return json.loads(res_data.decode('utf-8'))
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def wrkz_make_integrate(
    url: str, address: str, payment_id: str, key: str
):
    try:
        headers = {
            'X-API-KEY': key,
            'Content-Type': 'application/json'
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url + "/addresses/{}/{}".format(address, payment_id), headers=headers, timeout=8) as response:
                print(response)
                if response.status == 200:
                    res_data = await response.read()
                    print(res_data)
                    return json.loads(res_data.decode('utf-8'))
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def call_doge(url: str, method_name: str, coin: str, payload: str = None) -> Dict:
    timeout = 150
    coin_name = coin.upper()
    if payload is None:
        data = '{"jsonrpc": "1.0", "id":"' + str(
            uuid.uuid4()) + '", "method": "' + method_name + '", "params": [] }'
    else:
        data = '{"jsonrpc": "1.0", "id":"' + str(
            uuid.uuid4()) + '", "method": "' + method_name + '", "params": [' + payload + '] }'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=timeout) as response:
                if response.status == 200:
                    res_data = await response.read()
                    res_data = res_data.decode('utf-8')
                    decoded_data = json.loads(res_data)
                    return decoded_data['result']
                else:
                    print(f'Call {coin_name} returns {str(response.status)} with method {method_name}')
                    print(data)
    except (aiohttp.client_exceptions.ServerDisconnectedError, aiohttp.client_exceptions.ClientOSError):
        print("call_doge: got disconnected for coin: {}".format(coin_name))
    except asyncio.TimeoutError:
        print('TIMEOUT: method_name: {} - COIN: {} - timeout {}'.format(method_name, coin.upper(), timeout))
    except Exception:
        traceback.print_exc(file=sys.stdout)

async def send_external_doge(
    url: str, coment_from: str, amount: float, to_address: str, coin: str, has_pos: int = 0
):
    coin_name = coin.upper()
    try:
        comment_to = to_address
        payload = f'"{to_address}", {amount}, "{coment_from}", "{comment_to}", false'
        if has_pos == 1:
            payload = f'"{to_address}", {amount}, "{coment_from}", "{comment_to}"'
        tx_hash = await call_doge(url, 'sendtoaddress', coin_name, payload=payload)
        if tx_hash:
            return tx_hash
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

async def send_external_xmr(
    runner_app, type_coin: str, from_address: str, amount: float, to_address: str,
    coin: str, coin_decimal: int, tx_fee: float, is_fee_per_byte: int,
    get_mixin: int, wallet_api_url: str, wallet_api_header: str
):
    coin_name = coin.upper()
    time_out = 150
    if coin_name == "DEGO":
        time_out = 300
    try:
        if type_coin == "XMR":
            acc_index = 0
            payload = {
                "destinations": [{'amount': int(amount * 10 ** coin_decimal), 'address': to_address}],
                "account_index": acc_index,
                "subaddr_indices": [],
                "priority": 1,
                "unlock_time": 0,
                "get_tx_key": True,
                "get_tx_hex": False,
                "get_tx_metadata": False
            }
            if coin_name == "UPX":
                payload = {
                    "destinations": [{'amount': int(amount * 10 ** coin_decimal), 'address': to_address}],
                    "account_index": acc_index,
                    "subaddr_indices": [],
                    "ring_size": 11,
                    "get_tx_key": True,
                    "get_tx_hex": False,
                    "get_tx_metadata": False
                }

            result = await runner_app.call_aiohttp_wallet_xmr_bcn(
                runner_app.coin_list[coin_name]['wallet_address'], 'transfer', runner_app.coin_list[coin_name]['type'], coin_name, payload=payload
            )
            if result and 'tx_hash' in result and 'tx_key' in result:
                return {"hash": result['tx_hash'], "key": result['tx_key']}
        elif type_coin == "TRTL-SERVICE" or type_coin == "BCN":
            if is_fee_per_byte != 1:
                payload = {
                    'addresses': [from_address],
                    'transfers': [{
                        "amount": int(amount * 10 ** coin_decimal),
                        "address": to_address
                    }],
                    'fee': int(tx_fee * 10 ** coin_decimal),
                    'anonymity': get_mixin
                }
            else:
                payload = {
                    'addresses': [from_address],
                    'transfers': [{
                        "amount": int(amount * 10 ** coin_decimal),
                        "address": to_address
                    }],
                    'anonymity': get_mixin
                }

            result = await runner_app.call_aiohttp_wallet_xmr_bcn(
                runner_app.coin_list[coin_name]['wallet_address'], 'sendTransaction', runner_app.coin_list[coin_name]['type'], coin_name, payload=payload
            )

            if result and 'transactionHash' in result:
                return {"hash": result['transactionHash'], "key": None}
        elif type_coin == "TRTL-API":
            if is_fee_per_byte != 1:
                json_data = {
                    "destinations": [{"address": to_address, "amount": int(amount * 10 ** coin_decimal)}],
                    "mixin": get_mixin,
                    "fee": int(tx_fee * 10 ** coin_decimal),
                    "sourceAddresses": [
                        from_address
                    ],
                    "paymentID": "",
                    "changeAddress": from_address
                }
            else:
                json_data = {
                    "destinations": [{"address": to_address, "amount": int(amount * 10 ** coin_decimal)}],
                    "mixin": get_mixin,
                    "sourceAddresses": [
                        from_address
                    ],
                    "paymentID": "",
                    "changeAddress": from_address
                }
            method = "/transactions/send/advanced"
            try:
                headers = {
                    'X-API-KEY': wallet_api_header,
                    'Content-Type': 'application/json'
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        wallet_api_url + method,
                        headers=headers,
                        json=json_data,
                        timeout=time_out
                    ) as response:
                        json_resp = await response.json()
                        if response.status == 200 or response.status == 201:
                            return {"hash": json_resp['transactionHash'], "key": None}
            except Exception:
                traceback.print_exc(file=sys.stdout)
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

def print_color(prt, color: str):
    if color == "red":
        print(f"\033[91m{prt}\033[00m")
    elif color == "green":
        print(f"\033[92m{prt}\033[00m")
    elif color == "yellow":
        print(f"\033[93m{prt}\033[00m")
    elif color == "lightpurple":
        print(f"\033[94m{prt}\033[00m")
    elif color == "purple":
        print(f"\033[95m{prt}\033[00m")
    elif color == "cyan":
        print(f"\033[96m{prt}\033[00m")
    elif color == "lightgray":
        print(f"\033[97m{prt}\033[00m")
    elif color == "black":
        print(f"\033[98m{prt}\033[00m")
    else:
        print(f"\033[0m{prt}\033[00m")


# start of background
class BackgroundRunner:
    def __init__(self, app_main):
        self.app_main = app_main
        self.pool = pool
        self.config = config

    async def open_connection(self):
        try:
            if self.pool is None:
                self.pool = await aiomysql.create_pool(
                    host=config['mysql']['host'], port=3306, minsize=4, maxsize=8,
                    user=config['mysql']['user'], password=config['mysql']['password'],
                    db=config['mysql']['db'], cursorclass=DictCursor, autocommit=True
                )
        except:
            print("ERROR: Unexpected error: Could not connect to MySql instance.")
            traceback.print_exc(file=sys.stdout)

    async def get_userwallet_by_extra(self, paymentid: str, coin: str, coin_family: str):
        coin_name = coin.upper()
        try:
            await self.open_connection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    result = None
                    if coin_family in ["TRTL-API", "TRTL-SERVICE", "BCN", "XMR"]:
                        sql = """
                        SELECT * FROM `deposit_addresses` 
                        WHERE `address_extra`=%s AND `coin_name`=%s LIMIT 1;
                        """
                        await cur.execute(sql, (paymentid, coin_name))
                        result = await cur.fetchone()
                    elif coin_family in ["BTC", "NANO"]:
                        # if doge family, address is paymentid
                        sql = """
                        SELECT * FROM `deposit_addresses` 
                        WHERE `address`=%s AND `coin_name`=%s LIMIT 1;
                        """
                        await cur.execute(sql, (paymentid, coin_name))
                        result = await cur.fetchone()
                    return result
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
        return None

    async def gettopblock(self, daemon_url: str, coin_type: str, coin: str, time_out: int = 15):
        coin_name = coin.upper()
        if coin_type in ["BCN", "TRTL-API", "TRTL-SERVICE"]:
            method_name = "getblockcount"
            full_payload = {
                'params': {},
                'jsonrpc': '2.0',
                'id': str(uuid.uuid4()),
                'method': f'{method_name}'
            }
            try:

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        daemon_url + '/json_rpc',
                        json=full_payload,
                        timeout=time_out
                    ) as response:
                        if response.status == 200:
                            res_data = await response.json()
                            result = None
                            if res_data and 'result' in res_data:
                                result = res_data['result']
                            else:
                                result = res_data
                            if result:
                                full_payload = {
                                    'jsonrpc': '2.0',
                                    'method': 'getblockheaderbyheight',
                                    'params': {'height': result['count'] - 1}
                                }
                                try:
                                    async with aiohttp.ClientSession() as session:
                                        async with session.post(
                                            daemon_url + '/json_rpc',
                                            json=full_payload,
                                            timeout=time_out
                                        ) as response:
                                            if response.status == 200:
                                                res_data = await response.json()
                                                if 'result' in res_data:
                                                    return res_data['result']
                                                else:
                                                    print("Couldn't get result for coin: {}".format(coin_name))
                                            else:
                                                print("Coin {} got response status: {}".format(coin_name, response.status))
                                except asyncio.TimeoutError:
                                    traceback.print_exc(file=sys.stdout)
                                except Exception:
                                    traceback.print_exc(file=sys.stdout)
                            return None
            except Exception:
                traceback.print_exc(file=sys.stdout)
            return None
        elif coin_type == "XMR":
            method_name = "get_block_count"
            full_payload = {
                'params': {},
                'jsonrpc': '2.0',
                'id': str(uuid.uuid4()),
                'method': f'{method_name}'
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        daemon_url + '/json_rpc',
                        json=full_payload,
                        timeout=time_out
                    ) as response:
                        if response.status == 200:
                            try:
                                res_data = await response.json()
                            except Exception:
                                res_data = await response.read()
                                res_data = res_data.decode('utf-8')
                                res_data = json.loads(res_data)
                            result = None
                            if res_data and 'result' in res_data:
                                result = res_data['result']
                            else:
                                result = res_data
                            if result:
                                full_payload = {
                                    'jsonrpc': '2.0',
                                    'method': 'get_block_header_by_height',
                                    'params': {'height': result['count'] - 1}
                                }
                                try:
                                    async with aiohttp.ClientSession() as session:
                                        async with session.post(
                                            daemon_url + '/json_rpc',
                                            json=full_payload,
                                            timeout=time_out
                                        ) as response:
                                            if response.status == 200:
                                                res_data = await response.json()
                                                if res_data and 'result' in res_data:
                                                    return res_data['result']
                                                else:
                                                    return res_data
                                except Exception:
                                    traceback.print_exc(file=sys.stdout)
                            return None
            except Exception:
                traceback.print_exc(file=sys.stdout)
            return None

    async def call_aiohttp_wallet_xmr_bcn(
        self, wallet_url: str, method_name: str, coin_type: str, coin: str,
        payload: Dict = None
    ) -> Dict:
        coin_name = coin.upper()
        full_payload = {
            'params': payload or {},
            'jsonrpc': '2.0',
            'id': str(uuid.uuid4()),
            'method': f'{method_name}'
        }
        timeout = 30
        if method_name == "save" or method_name == "store":
            timeout = 300
        elif method_name == "sendTransaction":
            timeout = 180
        elif method_name == "createAddress" or method_name == "getSpendKeys":
            timeout = 60
        try:
            if coin_type == "XMR":
                try:
                    async with aiohttp.ClientSession(headers={'Content-Type': 'application/json'}) as session:
                        async with session.post(wallet_url, json=full_payload, timeout=timeout) as response:
                            # sometimes => "message": "Not enough unlocked money" for checking fee
                            if method_name == "transfer":
                                print('{} - transfer'.format(coin_name))
                                # print(full_payload)
                            if response.status == 200:
                                res_data = await response.read()
                                res_data = res_data.decode('utf-8')
                                if method_name == "transfer":
                                    print(res_data)

                                decoded_data = json.loads(res_data)
                                if 'result' in decoded_data:
                                    return decoded_data['result']
                                else:
                                    return None
                except asyncio.TimeoutError:
                    print('TIMEOUT: {} coin_name {} - timeout {}'.format(method_name, coin_name, timeout))
                    return None
                except Exception:
                    traceback.print_exc(file=sys.stdout)
                    return None
            elif coin_type in ["TRTL-SERVICE", "BCN"]:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(wallet_url, json=full_payload, timeout=timeout) as response:
                            if response.status == 200 or response.status == 201:
                                res_data = await response.read()
                                res_data = res_data.decode('utf-8')

                                decoded_data = json.loads(res_data)
                                if 'result' in decoded_data:
                                    return decoded_data['result']
                            return None
                except asyncio.TimeoutError:
                    print('TIMEOUT: {} coin_name {} - timeout {}'.format(method_name, coin_name, timeout))
                    return None
                except Exception:
                    traceback.print_exc(file=sys.stdout)
                    return None
        except asyncio.TimeoutError:
            print('TIMEOUT: method_name: {} - coin_family: {} - timeout {}'.format(method_name, coin_type, timeout))
        except Exception:
            traceback.print_exc(file=sys.stdout)

    async def update_balance_xmr(self, timer: float=10.0):
        while True:
            try:
                if len(config['coinapi']['list_bcn_xmr']) > 0:
                    tasks = []
                    for coin_name in config['coinapi']['list_bcn_xmr']:
                        if runner.coin_list.get(coin_name) is not None:
                            tasks.append(self.update_balance_tasks_xmr(coin_name, False))
                    completed = 0
                    for task in asyncio.as_completed(tasks):
                        fetch_updates = await task
                        if fetch_updates is True:
                            completed += 1
            except Exception:
                traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(timer)

    # To use with update_balance_xmr()
    async def update_balance_tasks_xmr(self, coin_name: str, debug: bool):
        if debug is True:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} Check balance {coin_name}", color="yellow")
        top_block = await self.gettopblock(self.coin_list[coin_name]['daemon_address'], self.coin_list[coin_name]['type'], coin_name, time_out=60)
        if top_block is None:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} Got None for top block {coin_name}", color="yellow")
            return
        height = int(top_block['block_header']['height'])
        try:
            set_cache_kv(
                self.app_main,
                "block",
                self.config['coinapi']['kv_prefix'] + coin_name,
                height
            )
            await update_top_block(
                coin_name, height
            )
        except Exception:
            traceback.print_exc(file=sys.stdout)

        get_confirm_depth = self.coin_list[coin_name]['confirmation_depth']
        min_deposit = self.coin_list[coin_name]['min_deposit']
        coin_decimal = self.coin_list[coin_name]['decimal']
        payload = {
            "in": True,
            "out": True,
            "pending": False,
            "failed": False,
            "pool": False,
            "filter_by_height": True,
            "min_height": height - 2000,
            "max_height": height
        }
        
        get_transfers = await self.call_aiohttp_wallet_xmr_bcn(
            self.coin_list[coin_name]['wallet_address'], 'get_transfers', self.coin_list[coin_name]['type'], coin_name, payload=payload
        )
        if get_transfers and len(get_transfers) >= 1 and 'in' in get_transfers:
            try:
                await self.open_connection()
                async with self.pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        sql = """ SELECT * FROM `deposits` WHERE `coin_name`=%s """
                        await cur.execute(sql, (coin_name,))
                        result = await cur.fetchall()
                        d = [i['txid'] for i in result]
                        # print('=================='+coin_name+'===========')
                        # print(d)
                        # print('=================='+coin_name+'===========')
                        list_balance_user = {}
                        for tx in get_transfers['in']:
                            # add to balance only confirmation depth meet
                            if height >= int(tx['height']) + get_confirm_depth and tx['amount'] >= int(min_deposit * 10 ** coin_decimal) and 'payment_id' in tx:
                                if 'payment_id' in tx and tx['payment_id'] in list_balance_user:
                                    list_balance_user[tx['payment_id']] += tx['amount']
                                elif 'payment_id' in tx and tx['payment_id'] not in list_balance_user:
                                    list_balance_user[tx['payment_id']] = tx['amount']
                                try:
                                    if tx['txid'] not in d:
                                        user_paymentId = await self.get_userwallet_by_extra(
                                            tx['payment_id'], coin_name,
                                            self.coin_list[coin_name]['type']
                                        )
                                        app_id = None
                                        if user_paymentId:
                                            app_id = user_paymentId['api_id']
                                        if app_id is None:
                                            # Skipped for None
                                            continue
                                        sql = """
                                        INSERT IGNORE INTO `deposits` 
                                        (`coin_name`, `api_id`, `depost_id`, `txid`, `blockhash`, `address`, `extra`, `height`, `amount`, `confirmations`, `time_insert`) 
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                        """
                                        await cur.execute(sql, (
                                            coin_name, app_id, user_paymentId['id'], tx['txid'], None, user_paymentId['address'], tx['payment_id'], tx['height'],
                                            float(tx['amount'] / 10 ** coin_decimal), height - tx['height'], int(time.time())
                                        ))
                                        await conn.commit()
                                        try:
                                            await log_to_discord(
                                                "API: {} / ⏳ PENDING DEPOSIT {} {} to {}. Height: {}".format(app_id, float(tx['amount'] / 10 ** coin_decimal), coin_name, user_paymentId['address'], tx['height']),
                                                config['log']['discord_webhook_default']
                                            )
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout)
                                except Exception:
                                    traceback.print_exc(file=sys.stdout)
            except Exception:
                traceback.print_exc(file=sys.stdout)
        if debug is True:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} End check balance {coin_name}", color="green")
        return True

    async def wrkz_api_get_transfers(
        self, url: str, key: str,
        height_start: int = None, height_end: int = None
    ):
        time_out = 30
        method = "/transactions"
        headers = {
            'X-API-KEY': key,
            'Content-Type': 'application/json'
        }
        if (height_start is None) or (height_end is None):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url + method, headers=headers, timeout=time_out) as response:
                        json_resp = await response.json()
                        if response.status == 200 or response.status == 201:
                            return json_resp['transactions']
            except Exception:
                traceback.format_exc()
        elif height_start and height_end:
            method += '/' + str(height_start) + '/' + str(height_end)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url + method, headers=headers, timeout=time_out) as response:
                        json_resp = await response.json()
                        if response.status == 200 or response.status == 201:
                            return json_resp['transactions']
            except Exception:
                traceback.format_exc()

    async def update_balance_tasks_wrkz(self, coin_name: str, debug: bool):
        if debug is True:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} Check balance {coin_name}", color="yellow")
        top_block = await self.gettopblock(self.coin_list[coin_name]['daemon_address'], self.coin_list[coin_name]['type'], coin_name, time_out=60)
        if top_block is None:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} Got None for top block {coin_name}", color="yellow")
            return
        height = int(top_block['block_header']['height'])
        try:
            set_cache_kv(
                self.app_main,
                "block",
                self.config['coinapi']['kv_prefix'] + coin_name,
                height
            )
            await update_top_block(
                coin_name, height
            )
        except Exception:
            traceback.print_exc(file=sys.stdout)

        get_confirm_depth = self.coin_list[coin_name]['confirmation_depth']
        coin_decimal = self.coin_list[coin_name]['decimal']
        min_deposit = self.coin_list[coin_name]['min_deposit']
        get_min_deposit_amount = int(min_deposit * 10 ** coin_decimal)

        get_transfers = await self.wrkz_api_get_transfers(
            runner.coin_list[coin_name]['wallet_address'],
            runner.coin_list[coin_name]['header'],
            height - 2000,
            height
        )
        list_balance_user = {}
        if get_transfers and len(get_transfers) >= 1:
            await self.open_connection()
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = """
                    SELECT * FROM `deposits` 
                    WHERE `coin_name`=%s
                    """
                    await cur.execute(sql, (coin_name))
                    result = await cur.fetchall()
                    d = [i['txid'] for i in result]
                    # print('=================='+coin_name+'===========')
                    # print(d)
                    # print('=================='+coin_name+'===========')
                    for tx in get_transfers:
                        # Could be one block has two or more tx with different payment ID
                        # add to balance only confirmation depth meet
                        if len(tx['transfers']) > 0 and height >= int(tx['blockHeight']) + get_confirm_depth and \
                            tx['transfers'][0]['amount'] >= get_min_deposit_amount and 'paymentID' in tx:
                            if 'paymentID' in tx and tx['paymentID'] in list_balance_user:
                                if tx['transfers'][0]['amount'] > 0:
                                    list_balance_user[tx['paymentID']] += tx['transfers'][0]['amount']
                            elif 'paymentID' in tx and tx['paymentID'] not in list_balance_user:
                                if tx['transfers'][0]['amount'] > 0:
                                    list_balance_user[tx['paymentID']] = tx['transfers'][0]['amount']
                            try:
                                if tx['hash'] not in d:
                                    address = None
                                    for each_add in tx['transfers']:
                                        if len(each_add['address']) > 0 and runner.coin_list[coin_name]['main_address'] == each_add['address']:
                                            address = runner.coin_list[coin_name]['main_address']
                                            break
                                    if address is None:
                                        continue
                                    if 'paymentID' in tx and len(tx['paymentID']) > 0:
                                        try:
                                            user_paymentId = await self.get_userwallet_by_extra(
                                                tx['paymentID'], coin_name,
                                                self.coin_list[coin_name]['type']
                                            )
                                            app_id = None
                                            if user_paymentId:
                                                app_id = user_paymentId['api_id']
                                            if app_id is None:
                                                # Skipped for None
                                                continue

                                            sql = """
                                            INSERT IGNORE INTO `deposits` 
                                            (`coin_name`, `api_id`, `depost_id`, `txid`, `blockhash`, `address`, `extra`, `height`, `amount`, `confirmations`, `time_insert`) 
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                            """
                                            await cur.execute(sql, (
                                                coin_name, app_id, user_paymentId['id'], tx['hash'], None, user_paymentId['address'], tx['paymentID'], tx['blockHeight'],
                                                float(int(tx['transfers'][0]['amount']) / 10 ** coin_decimal), height - tx['blockHeight'], int(time.time())
                                            ))
                                            await conn.commit()
                                            try:
                                                await log_to_discord(
                                                    "API: {} / ⏳ PENDING DEPOSIT {} {} to {}. Height: {}".format(app_id, float(int(tx['transfers'][0]['amount']) / 10 ** coin_decimal), coin_name, user_paymentId['address'], tx['blockHeight']),
                                                    config['log']['discord_webhook_default']
                                                )
                                            except Exception:
                                                traceback.print_exc(file=sys.stdout)
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout)
                            except Exception:
                                traceback.print_exc(file=sys.stdout)
        if debug is True:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} End check balance {coin_name}", color="green")
        return True

    async def update_balance_wrkz(self, timer: float=10.0):
        while True:
            try:
                if len(config['coinapi']['list_wrkz_api']) > 0:
                    tasks = []
                    for coin_name in config['coinapi']['list_wrkz_api']:
                        if runner.coin_list.get(coin_name) is not None:
                            tasks.append(self.update_balance_tasks_wrkz(coin_name, False))
                    completed = 0
                    for task in asyncio.as_completed(tasks):
                        fetch_updates = await task
                        if fetch_updates is True:
                            completed += 1
            except Exception:
                traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(timer)

    async def update_balance_btc(self, timer: float=10.0):
        while True:
            if len(config['coinapi']['list_btc']) > 0:
                try:
                    tasks = []
                    for coin_name in config['coinapi']['list_btc']:
                        tasks.append(self.update_balance_tasks_btc(coin_name, False))
                    completed = 0
                    for task in asyncio.as_completed(tasks):
                        fetch_updates = await task
                        if fetch_updates is True:
                            completed += 1
                except Exception:
                    traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(timer)

    # to use with update_balance_btc()
    async def update_balance_tasks_btc(self, coin_name: str, debug: bool):
        if debug is True:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} Check balance {coin_name}", color="yellow")
        url = self.coin_list[coin_name]['daemon_address']
        method_info = "getblockchaininfo"
        if runner.coin_list[coin_name]['use_getinfo_btc'] == 1:
            method_info = "getinfo"
        gettopblock = await call_doge(url, method_info, coin_name)
        if gettopblock is None:
            return False
        height = int(gettopblock['blocks'])
        try:
            set_cache_kv(
                self.app_main,
                "block",
                self.config['coinapi']['kv_prefix'] + coin_name,
                height
            )
            await update_top_block(
                coin_name, height
            )
        except Exception:
            traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(1.0)
            return False

        get_confirm_depth = self.coin_list[coin_name]['confirmation_depth']
        coin_decimal = self.coin_list[coin_name]['decimal']
        min_deposit = self.coin_list[coin_name]['min_deposit']
        payload = '"*", 100, 0'
        get_transfers = await call_doge(url, 'listtransactions', coin_name, payload=payload)
        if get_transfers and len(get_transfers) >= 1:
            try:
                await self.open_connection()
                async with self.pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        sql = """
                        SELECT * FROM `deposits` 
                        WHERE `coin_name`=%s
                        """
                        await cur.execute(sql, (coin_name))
                        result = await cur.fetchall()
                        d = ["{}_{}".format(i['txid'], i['address']) for i in result]
                        # print('=================='+coin_name+'===========')
                        # print(d)
                        # print('=================='+coin_name+'===========')
                        list_balance_user = {}
                        for tx in get_transfers:
                            # add to balance only confirmation depth meet
                            if get_confirm_depth <= int(tx['confirmations']) and tx['amount'] >= min_deposit:
                                if 'address' in tx and tx['address'] in list_balance_user and tx['amount'] > 0:
                                    list_balance_user[tx['address']] += tx['amount']
                                elif 'address' in tx and tx['address'] not in list_balance_user and tx['amount'] > 0:
                                    list_balance_user[tx['address']] = tx['amount']
                                try:
                                    if tx.get('address') is None and tx.get('category') and tx['category'] == "send":
                                        continue
                                    if "{}_{}".format(tx['txid'], tx['address']) not in d:
                                        user_paymentId = await self.get_userwallet_by_extra(
                                            tx['address'], coin_name,
                                            self.coin_list[coin_name]['type']
                                        )
                                        app_id = None
                                        if user_paymentId:
                                            app_id = user_paymentId['api_id']
                                        if app_id is None:
                                            # Skipped for None
                                            continue
                                        if tx['category'] == 'receive':
                                            sql = """
                                            INSERT IGNORE INTO `deposits` 
                                            (`coin_name`, `api_id`, `depost_id`, `txid`, `blockhash`, `address`, `amount`, `confirmations`, `time_insert`) 
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                            """
                                            await cur.execute(sql, (
                                                coin_name, app_id, user_paymentId['id'], tx['txid'], tx['blockhash'], tx['address'],
                                                float(tx['amount']), tx['confirmations'], int(time.time())
                                            ))
                                            await conn.commit()
                                            try:
                                                await log_to_discord(
                                                    "API: {} / ⏳ PENDING DEPOSIT {} {} to {}. Tx: {}".format(app_id, float(tx['amount']), coin_name, tx['address'], tx['txid']),
                                                    config['log']['discord_webhook_default']
                                                )
                                            except Exception:
                                                traceback.print_exc(file=sys.stdout) 
                                except Exception:
                                    traceback.print_exc(file=sys.stdout)
            except Exception:
                traceback.print_exc(file=sys.stdout)
        if debug is True:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} End check balance {coin_name}", color="green")

    async def unlock_deposit(self, timer: float=10.0):
        while True:
            try:
                await self.open_connection()
                async with self.pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        sql = """
                        SELECT * FROM `deposits` 
                        WHERE `can_credit`=%s
                        """
                        await cur.execute(sql, ("NO"))
                        result = await cur.fetchall()
                        if result:
                            for ea in result:
                                try:
                                    coin_name = ea['coin_name']
                                    get_confirm_depth = self.coin_list[coin_name]['confirmation_depth']
                                    height = get_cache_kv(
                                        self.app_main,
                                        "block",
                                        self.config['coinapi']['kv_prefix'] + coin_name,
                                    )
                                    if ea['confirmations'] >= get_confirm_depth or (ea['height'] is not None and height - ea['height'] >= get_confirm_depth):
                                        sql_update = """
                                        UPDATE `deposits`
                                        SET `can_credit`=%s
                                        WHERE `id`=%s
                                        """
                                        await cur.execute(sql_update, ("YES", ea['id']))
                                        await conn.commit()
                                        try:
                                            await log_to_discord(
                                                "API: {} / ✅ UNLOCKED {} {} to {}. Tx: {}".format(ea['api_id'], ea['amount'], ea['coin_name'], ea['address'], ea['txid']),
                                                config['log']['discord_webhook_default']
                                            )
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout) 
                                except Exception:
                                    traceback.print_exc(file=sys.stdout)
            except Exception:
                traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(timer)


    async def bg_reload_coin_settings(self, timer: float=15.0):
        while True:
            try:
                runner.coin_list = await get_coin_setting()
            except Exception:
                traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(timer)

    async def bg_amount_holding(self, timer: float=30.0):
        while True:
            try:
                await delete_hold_address()
            except Exception:
                traceback.print_exc(file=sys.stdout)
            await asyncio.sleep(timer)

runner = BackgroundRunner(app)

try:
    app.redis_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
    app.r = redis.Redis(connection_pool=app.redis_pool)
except Exception:
    traceback.print_exc(file=sys.stdout)

def set_cache_kv(appr, table: str, key: str, value):
    try:
        p_mydict = pickle.dumps(value)
        appr.r.set(table + "_" + key, p_mydict, ex=60)
        return True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return False

def get_cache_kv(appr, table: str, key: str):
    try:
        res = appr.r.get(table + "_" + key)
        result = pickle.loads(res)
        if result is not None:
            return result
    except TypeError:
        pass
    except Exception:
        traceback.print_exc(file=sys.stdout)
    return None

@app.on_event('startup')
async def app_startup():
    runner.coin_list = await get_coin_setting()
    print("Loading {} coin(s)".format(len(runner.coin_list)))
    collect_address = await get_coin_deposits()
    if collect_address:
        runner.addresses = collect_address['addresses']
        runner.by_key = collect_address['by_key']
        print("Loading {} address(es).".format(len(runner.addresses)))
    asyncio.create_task(runner.update_balance_btc(timer=10.0))
    asyncio.create_task(runner.update_balance_xmr(timer=10.0))
    asyncio.create_task(runner.update_balance_wrkz(timer=10.0))
    asyncio.create_task(runner.unlock_deposit(timer=10.0))
    asyncio.create_task(runner.bg_reload_coin_settings(timer=10.0))
    asyncio.create_task(runner.bg_amount_holding(timer=30.0))
# End of background

@app.get("/reload", include_in_schema=False)
async def reload_configuration(
    request: Request, Authorization: Union[str, None] = Header(default=None)
):
    """
    Master to reload configuration on the fly without restarting
    """
    if 'Authorization' not in request.headers:
        return {
            "success": False,
            "data": None,
            "message": "This is not where you need to do!",
            "time": int(time.time())
        }
    else:
        # let's reload
        config = load_config()
        # get who own that key
        if request.headers['Authorization'] != config['coinapi']['master_key']:
            return {
                "success": False,
                "data": None,
                "message": "Wrong API key!",
                "time": int(time.time())
            }
        else:
            print_color(f"{datetime.now():%Y-%m-%d %H:%M:%S} reloaded configuration done!", color="yellow")
            try:
                await log_to_discord(
                    "Configuration reloaded",
                    config['log']['discord_webhook_default']
                )
            except Exception:
                traceback.print_exc(file=sys.stdout)

@app.get("/status/{coin_name}")
async def system_and_status(
    coin_name: str
):
    """
    Get system or coin status

    coin_name: coin name
    """
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    # refresh coin list
    if api_ttlcache.get('/status/' + coin_name):
        return {
            "success": True,
            "data": api_ttlcache['/status/' + coin_name],
            "message": None,
            "time": int(time.time())
        }
    else:
        runner.coin_list = await get_coin_setting()
        result_data = {
            "coin": coin_name,
            "min_transfer": runner.coin_list[coin_name]['min_transfer'],
            "max_transfer": runner.coin_list[coin_name]['max_transfer'],
            "min_withdraw": runner.coin_list[coin_name]['min_withdraw'],
            "max_withdraw": runner.coin_list[coin_name]['max_withdraw'],
            "tx_fee": runner.coin_list[coin_name]['fee_withdraw'],
            "chain_height": runner.coin_list[coin_name]['chain_height'],
            "enable_create": runner.coin_list[coin_name]['enable_create'],
            "enable_deposit": runner.coin_list[coin_name]['enable_deposit'],
            "enable_withdraw": runner.coin_list[coin_name]['enable_withdraw'],
            "time": int(time.time()),
        }
        api_ttlcache['/status/' + coin_name] = result_data
        return {
            "success": True,
            "data": result_data,
            "message": None,
            "time": int(time.time())
        }

@app.get("/status")
async def status(
) -> Dict:
    return {
        "success": True,
        "data": [i for i in config['coinapi']['list_btc'] + config['coinapi']['list_bcn_xmr'] + config['coinapi']['list_wrkz_api'] if runner.coin_list.get(i) is not None],
        "message": None,
        "time": int(time.time())
    }

class newaddress_data(BaseModel):
    coin: str
    tag: str
    second_tag: str=None

@app.post("/newaddress")
async def create_new_coin_address(
    request: Request, item: newaddress_data, Authorization: Union[str, None] = Header(default=None)
):
    """
    Create a new coin address

    coin: coin name

    tag: optional with tag or remark
    """
    method_call = "/newaddress"
    coin_name = item.coin.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }
            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            # check if enable_create != 1
            if runner.coin_list[coin_name]['enable_create'] != 1:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Currently, {coin_name} not enable for new address generation. Try again later!",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            
            if item.tag and len(item.tag) >= 100:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"tag '{item.tag}' is too long.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                tag = item.tag.strip()
                # if tag of that coin and api_id exist
                find_tag = await find_address_coin_tag(
                    coin_name, tag, get_api['id']
                )
                if find_tag is not None:
                    result_data = {
                        "success": True,
                        "data": find_tag['address'],
                        "message": f"Tag: '{tag}' already exist for coin {coin_name} within your API.",
                        "second_tag": find_tag['second_tag'],
                        "time": int(time.time())
                    }
                    # if second_tag is None, and there is second_tag
                    if hasattr(item, "second_tag") and item.second_tag is not None and find_tag['second_tag'] is None:
                        # update tag
                        await update_second_tag(
                            coin_name, find_tag['id'], item.second_tag.strip()
                        )
                    try:
                        await insert_api_log(get_api['id'], method_call, str(item), json.dumps(result_data))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return result_data

        if coin_name in config['coinapi']['list_wrkz_api']:
            payment_id = paymentid()
            make_addr = await wrkz_make_integrate(
                runner.coin_list[coin_name]['wallet_address'],
                runner.coin_list[coin_name]['main_address'],
                payment_id,
                runner.coin_list[coin_name]['header']    
            )
            if make_addr is None:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "internal error.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                inserting = await insert_address(
                    get_api['id'], coin_name, make_addr['integratedAddress'],
                    payment_id, None, tag
                )
                if inserting is not None:
                    collect_address = await get_coin_deposits()
                    if collect_address:
                        runner.addresses = collect_address['addresses']
                        runner.by_key = collect_address['by_key']
                        print("Reloading {} address(es).".format(len(runner.addresses)))
                    data_call = json.dumps({"coin": coin_name, "tag": item.tag})
                    result_data = {
                        "success": True,
                        "data": make_addr['integratedAddress'],
                        "message": None,
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data
                else:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "internal error during inserting to DB.",
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result
        elif coin_name in config['coinapi']['list_bcn_xmr']:
            make_addr = await xmr_make_integrate(
                runner.coin_list[coin_name]['wallet_address'],
                runner.coin_list[coin_name]['main_address']
            )
            if make_addr is None:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "internal error.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                inserting = await insert_address(
                    get_api['id'], coin_name, make_addr['result']['integrated_address'],
                    make_addr['result']['payment_id'], None, tag
                )
                if inserting is not None:
                    collect_address = await get_coin_deposits()
                    if collect_address:
                        runner.addresses = collect_address['addresses']
                        runner.by_key = collect_address['by_key']
                        print("Reloading {} address(es).".format(len(runner.addresses)))
                    data_call = json.dumps({"coin": coin_name, "tag": item.tag})
                    result_data = {
                        "success": True,
                        "data": make_addr['result']['integrated_address'],
                        "message": None,
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data
                else:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "internal error during inserting to DB.",
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result
        elif coin_name in config['coinapi']['list_btc']:
            url = runner.coin_list[coin_name]['daemon_address']
            address_call = await call_doge(url, 'getnewaddress', coin_name, payload='')
            reg_address = {}
            reg_address['address'] = address_call
            key_call = await call_doge(url, 'dumpprivkey', coin_name, payload=f'"{address_call}"')
            reg_address['privateKey'] = key_call
            if reg_address['address'] and reg_address['privateKey']:
                inserting = await insert_address(
                    get_api['id'], coin_name, reg_address['address'],
                    None, reg_address['privateKey'], item.tag
                )
                if inserting is not None:
                    collect_address = await get_coin_deposits()
                    if collect_address:
                        runner.addresses = collect_address['addresses']
                        runner.by_key = collect_address['by_key']
                        print("Reloading {} address(es).".format(len(runner.addresses)))
                    data_call = json.dumps({"coin": coin_name, "tag": item.tag})
                    result_data = {
                        "success": True,
                        "data": reg_address['address'],
                        "message": None,
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data
                else:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "internal error during inserting to DB.",
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result

class balance_coin(BaseModel):
    coin: str
    address: str

@app.post("/balance")
async def get_a_balance(
    request: Request, item: balance_coin, Authorization: Union[str, None] = Header(default=None)
):
    """
    Get a balance of an address of a coin

    item: {coin, address}
    """
    method_call = "/balance"
    coin_name = item.coin.upper()
    address = item.address
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            get_balance = await get_balance_coin_address(
                get_api['id'], coin_name, address
            )
            if get_balance is None:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "{}, address not found {}!".format(coin_name, address),
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                round_places = runner.coin_list[coin_name]['round_places']
                data_call = json.dumps({"coin": coin_name, "address": address})
                result_data = {
                    "success": True,
                    "data": {
                        "coin": coin_name,
                        "address": address,
                        "balance": round_amount(get_balance['total_deposited'] + get_balance['total_received'] - get_balance['total_sent'] - get_balance['total_withdrew'] - get_balance['amount_hold'], round_places),
                        "amount_hold": get_balance['amount_hold'], 
                        "deposit": round_amount(get_balance['total_deposited'], round_places),
                        "withdrew": round_amount(get_balance['total_withdrew'], round_places),
                        "received": round_amount(get_balance['total_received'], round_places),
                        "sent": round_amount(get_balance['total_sent'], round_places)
                    },
                    "message": None,
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data

class withdraw_data(BaseModel):
    coin: str
    from_address: str
    to_address: str
    amount: float
    remark: str

@app.post("/withdraw")
async def withdraw_coin(
    request: Request, item: withdraw_data, Authorization: Union[str, None] = Header(default=None)
):
    """
    Withdraw from a coin address to an external wallet through blockchain

    item: transfer data
    """
    method_call = "/withdraw"
    coin_name = item.coin.upper()
    from_address = item.from_address
    to_address = item.to_address
    amount = item.amount
    remark = item.remark

    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }

    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            # check if enable_withdraw != 1
            if runner.coin_list[coin_name]['enable_withdraw'] != 1:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Currently, {coin_name} not enable for withdraw. Try again later!",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            # check if that API own that address
            if from_address not in runner.addresses:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "{}, address {}.. not in our database.".format(coin_name, from_address),
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                if get_api['id'] != runner.by_key["{}_{}".format(coin_name, from_address)]['api_id']:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "{}, address {}.. permission denied.".format(coin_name, from_address),
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result
                else:
                    # check if the receiving address insides API
                    if to_address in runner.addresses:
                        failed_result = {
                            "success": False,
                            "data": "{}, you can not send to address {}. You might need to call /transfer instead".format(coin_name, to_address),
                            "message": "{}, you can not send to address {}. You might need to call /transfer instead".format(coin_name, to_address),
                            "time": int(time.time())
                        }
                        try:
                            await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                        except Exception:
                            traceback.print_exc(file=sys.stdout)
                        try:
                            await log_to_discord(
                                "API: {} / 🔴 ATTEMPT TO WITHDRAW {} {} from {} to {} in our API database.".format(get_api['id'], amount, coin_name, from_address, to_address),
                                config['log']['discord_webhook_default']
                            )
                        except Exception:
                            traceback.print_exc(file=sys.stdout)
                        return failed_result
                    # he owns it, check amount, balance
                    # truncate amount
                    if amount < runner.coin_list[coin_name]['min_withdraw'] or amount > runner.coin_list[coin_name]['max_withdraw']:
                        failed_result = {
                            "success": False,
                            "data": None,
                            "message": "{}, withdraw amount out of range {}-{}.".format(coin_name, runner.coin_list[coin_name]['min_withdraw'], runner.coin_list[coin_name]['max_withdraw']),
                            "time": int(time.time())
                        }
                        try:
                            await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                        except Exception:
                            traceback.print_exc(file=sys.stdout) 
                        return failed_result
                    else:
                        # check balance
                        get_balance = await get_balance_coin_address(
                            get_api['id'], coin_name, from_address
                        )
                        if get_balance is None:
                            failed_result = {
                                "success": False,
                                "data": None,
                                "message": "{}, address not found {}!".format(coin_name, from_address),
                                "time": int(time.time())
                            }
                            try:
                                await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                            except Exception:
                                traceback.print_exc(file=sys.stdout) 
                            return failed_result
                        else:
                            # remark length
                            if len(remark) > 100:
                                failed_result = {
                                    "success": False,
                                    "data": None,
                                    "message": "{}, remark is too long {}.".format(coin_name, item.remark),
                                    "time": int(time.time())
                                }
                                try:
                                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                                except Exception:
                                    traceback.print_exc(file=sys.stdout) 
                                return failed_result
                            round_places = runner.coin_list[coin_name]['round_places']
                            tx_fee = runner.coin_list[coin_name]['fee_withdraw']
                            has_pos = runner.coin_list[coin_name]['has_pos']
                            balance = round_amount(get_balance['total_deposited'] + get_balance['total_received'] - get_balance['total_sent'] - get_balance['total_withdrew'] - get_balance['amount_hold'], round_places)
                            if amount + tx_fee > balance:
                                failed_result = {
                                    "success": False,
                                    "data": None,
                                    "message": "{}, insufficient balance to withdraw for {}! Fee: {} {}. Having {} {}.".format(coin_name, from_address, tx_fee, coin_name, balance, coin_name),
                                    "time": int(time.time())
                                }
                                try:
                                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                                except Exception:
                                    traceback.print_exc(file=sys.stdout) 
                                return failed_result
                            else:
                                # enough balance to withdraw
                                wallet_address = runner.coin_list[coin_name]['wallet_address']
                                mixin = runner.coin_list[coin_name]['mixin']
                                header = runner.coin_list[coin_name]['header']
                                is_fee_per_byte = runner.coin_list[coin_name]['is_fee_per_byte']
                                main_address = runner.coin_list[coin_name]['main_address']
                                if coin_name in config['coinapi']['list_bcn_xmr'] + config['coinapi']['list_wrkz_api']:
                                    sending_tx = await send_external_xmr(
                                        runner, runner.coin_list[coin_name]['type'], main_address, amount, to_address, coin_name,
                                        runner.coin_list[coin_name]['decimal'], tx_fee, is_fee_per_byte, mixin, wallet_address, header
                                    )
                                    if sending_tx is None:
                                        failed_result = {
                                            "success": False,
                                            "data": None,
                                            "message": "{}, failed to send {} {} to {}.".format(coin_name, amount, coin_name, to_address),
                                            "time": int(time.time())
                                        }
                                        try:
                                            await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout)
                                        try:
                                            await log_to_discord(
                                                "API: {} / 🔴 FAILED TO WITHDRAW {} {} to {}.".format(get_api['id'], amount, coin_name, to_address),
                                                config['log']['discord_webhook_default']
                                            )
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout)
                                        return failed_result
                                    else:
                                        ref_uuid = str(uuid.uuid4())
                                        await insert_withdraw_success(
                                            get_api['id'], coin_name, from_address, amount, tx_fee, runner.by_key["{}_{}".format(coin_name, from_address)]['id'],
                                            to_address, sending_tx['hash'], sending_tx['key'], remark, ref_uuid
                                        )
                                        result_data = {
                                            "success": True,
                                            "data": sending_tx['hash'],
                                            "message": "{}, successfully sent {} {} to {}. Tx: {}, Ref: {}".format(coin_name, amount, coin_name, to_address, sending_tx['hash'], ref_uuid),
                                            "time": int(time.time())
                                        }
                                        collect_address = await get_coin_deposits()
                                        if collect_address:
                                            runner.addresses = collect_address['addresses']
                                            runner.by_key = collect_address['by_key']
                                            print("Reloading {} address(es).".format(len(runner.addresses)))
                                        await insert_api_log(get_api['id'], method_call, str(item), json.dumps(result_data))
                                        try:
                                            await log_to_discord(
                                                "API: {} / ✈️ WITHDRAW {} {} to {}. Tx: {}".format(get_api['id'], amount, coin_name, to_address, sending_tx['hash']),
                                                config['log']['discord_webhook_default']
                                            )
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout) 
                                        return result_data
                                elif coin_name in config['coinapi']['list_btc']:
                                    url = runner.coin_list[coin_name]['daemon_address']
                                    sending_tx = await send_external_doge(
                                        url, from_address, amount, to_address, coin_name, has_pos
                                    )
                                    if sending_tx is None:
                                        failed_result = {
                                            "success": False,
                                            "data": None,
                                            "message": "{}, failed to send {} {} to {}.".format(coin_name, amount, coin_name, to_address),
                                            "time": int(time.time())
                                        }
                                        try:
                                            await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout) 
                                        try:
                                            await log_to_discord(
                                                "API: {} / 🔴 FAILED TO WITHDRAW {} {} to {}.".format(get_api['id'], amount, coin_name, to_address),
                                                config['log']['discord_webhook_default']
                                            )
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout) 
                                        return failed_result
                                    else:
                                        ref_uuid = str(uuid.uuid4())
                                        await insert_withdraw_success(
                                            get_api['id'], coin_name, from_address, amount, tx_fee, runner.by_key["{}_{}".format(coin_name, from_address)]['id'],
                                            to_address, sending_tx, None, remark, ref_uuid
                                        )
                                        result_data = {
                                            "success": True,
                                            "data": sending_tx,
                                            "message": "{}, successfully sent {} {} to {}. Tx: {}, Ref: {}".format(coin_name, amount, coin_name, to_address, sending_tx, ref_uuid),
                                            "time": int(time.time())
                                        }
                                        collect_address = await get_coin_deposits()
                                        if collect_address:
                                            runner.addresses = collect_address['addresses']
                                            runner.by_key = collect_address['by_key']
                                            print("Reloading {} address(es).".format(len(runner.addresses)))
                                        await insert_api_log(get_api['id'], method_call, str(item), json.dumps(result_data))
                                        try:
                                            await log_to_discord(
                                                "API: {} / ✈️ WITHDRAW {} {} to {}. Tx: {}".format(get_api['id'], amount, coin_name, to_address, sending_tx),
                                                config['log']['discord_webhook_default']
                                            )
                                        except Exception:
                                            traceback.print_exc(file=sys.stdout) 
                                        return result_data

class transfer_data(BaseModel):
    coin: str
    from_address: str
    to_address: str
    amount: float
    remark: str

@app.post("/transfer")
async def transfer_balances(
    request: Request, items: List[transfer_data], Authorization: Union[str, None] = Header(default=None)
):
    """
    Internal transfer between internal addresses

    item: list of transfers
    """
    method_call = "/transfer"
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if len(items) == 0:
        return {
            "success": False,
            "data": None,
            "message": "list of transfer can't be empty.",
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            has_error = False
            error_list = []
            records = []
            ref_id = str(uuid.uuid4())
            records_coins = {}
            temp_balances = {}
            for ea in items:
                try:
                    coin_name = ea.coin.upper()
                    if ea.from_address not in runner.addresses:
                        continue
                    if ea.to_address not in runner.addresses:
                        continue

                    temp_balances["{}_{}".format(coin_name, ea.from_address)] = runner.by_key["{}_{}".format(coin_name, ea.from_address)]['total_deposited'] + runner.by_key["{}_{}".format(coin_name, ea.from_address)]['total_received'] - \
                    runner.by_key["{}_{}".format(coin_name, ea.from_address)]['total_sent'] - runner.by_key["{}_{}".format(coin_name, ea.from_address)]['total_withdrew']
                    
                    temp_balances["{}_{}".format(coin_name, ea.to_address)] = runner.by_key["{}_{}".format(coin_name, ea.to_address)]['total_deposited'] + runner.by_key["{}_{}".format(coin_name, ea.to_address)]['total_received'] - \
                    runner.by_key["{}_{}".format(coin_name, ea.to_address)]['total_sent'] - runner.by_key["{}_{}".format(coin_name, ea.to_address)]['total_withdrew']
                except Exception:
                    traceback.print_exc(file=sys.stdout) 

            for ea in items:
                ea_error = False
                try:
                    coin_name = ea.coin.upper()
                    # check permission
                    if get_api['id'] != runner.by_key["{}_{}".format(coin_name, ea.from_address)]['api_id']:
                        has_error = True
                        ea_error = True
                        error_list.append("{}/address: {} is not within your API!".format(coin_name, ea.from_address))

                    if coin_name not in runner.coin_list.keys():
                        has_error = True
                        ea_error = True
                        error_list.append("{} is not in the supported list!".format(coin_name))
                    elif ea.amount < runner.coin_list[coin_name]['min_transfer'] or ea.amount > runner.coin_list[coin_name]['max_transfer']:
                        has_error = True
                        ea_error = True
                        error_list.append("{} {} is out of range transfer.".format(ea.amount, coin_name))
                    if ea.remark and len(ea.remark) >= 100:
                        has_error = True
                        ea_error = True
                        error_list.append("{}, remark {}.. is too long.".format(coin_name, ea.remark[0:90]))
                    if ea.from_address == ea.to_address:
                        has_error = True
                        ea_error = True
                        error_list.append("{}, same address from and to.".format(coin_name))
                    if ea.from_address not in runner.addresses:
                        has_error = True
                        ea_error = True
                        error_list.append("{}, address {}.. not in our database.".format(coin_name, ea.from_address[0:30]))
                    else:
                        # in database
                        # check loop transfer
                        if coin_name not in records_coins:
                            records_coins[coin_name] = []
                        if ea.from_address + ea.to_address in records_coins[coin_name]:
                            has_error = True
                            ea_error = True
                            error_list.append(f"{coin_name}, loop transfer detected.")
                        else:
                            records_coins[coin_name].append("{}{}".format(ea.to_address, ea.from_address))

                        if runner.by_key.get("{}_{}".format(coin_name, ea.from_address)) is None:
                            has_error = True
                            ea_error = True
                            error_list.append("{}, address {}.. not in our API.".format(coin_name, ea.from_address[0:30]))
                        else:
                            temp_balances["{}_{}".format(coin_name, ea.from_address)] -= ea.amount
                            # check balance
                            if temp_balances["{}_{}".format(coin_name, ea.from_address)] < 0:
                                has_error = True
                                ea_error = True
                                error_list.append("{}, address {}.. not sufficient balance.".format(coin_name, ea.from_address[0:30]))

                    # to_address no need to check API
                    if ea.to_address not in runner.addresses:
                        has_error = True
                        ea_error = True
                        error_list.append("{}, address {}.. not in our database.".format(coin_name, ea.to_address[0:30]))
                    else:
                        temp_balances["{}_{}".format(coin_name, ea.to_address)] += ea.amount

                    if ea_error is False:
                        round_places = runner.coin_list[coin_name]['round_places']
                        print("{}, preparing transfer from: {}.., to: {}.., amount: {}".format(
                            coin_name, ea.from_address[0:30], ea.to_address[0:30], round_amount(ea.amount, round_places)
                        ))
                        records.append((
                            get_api['id'], ea.from_address, ea.to_address, round_amount(ea.amount, round_places), coin_name, ea.remark, int(time.time()), ref_id
                        ))
                except Exception:
                    traceback.print_exc(file=sys.stdout)        
            if has_error is True:
                failed_result = {
                    "success": False,
                    "data": error_list,
                    "message": "there is one or more error(s)!",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(items), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                if len(records) > 0:
                    # check fofr loop transfer
                    inserting = await transfer_records(records)
                    if inserting:
                        collect_address = await get_coin_deposits()
                        if collect_address:
                            runner.addresses = collect_address['addresses']
                            runner.by_key = collect_address['by_key']
                            print("Reloading {} address(es).".format(len(runner.addresses)))
                        result_data = {
                            "success": True,
                            "data": ref_id,
                            "message": "processed {} transfer(s).".format(len(records)),
                            "time": int(time.time())
                        }
                        await insert_api_log(get_api['id'], method_call, json.dumps(records), json.dumps(result_data))
                        return result_data
                    else:
                        failed_result = {
                            "success": False,
                            "data": None,
                            "message": "internal error.",
                            "time": int(time.time())
                        }
                        try:
                            await insert_api_failed_log(get_api['id'], method_call, str(items), json.dumps(failed_result))
                        except Exception:
                            traceback.print_exc(file=sys.stdout) 
                        return failed_result
                else:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "no transfer records!",
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(items), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result

@app.get("/noted/{coin_name}/{tx}")
async def remark_noted_a_tx(
    request: Request, coin_name: str, tx: str, Authorization: Union[str, None] = Header(default=None)
):
    """
    Put a note tag for a tx deposit and remark you took note already.

    coin_name: coin name
    tx: transaction hash
    """
    method_call = "/noted/"
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }
            find_tx = await find_tx_coin(
                coin_name, tx, get_api['id']
            )
            data_call = json.dumps({"coin_name": coin_name, "api_id": get_api['id'], "tx": tx})
            if find_tx is None:
                result_data = {
                    "success": True,
                    "data": None,
                    "message": f"no such transaction for {coin_name}.",
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data
            else:
                noted = await note_tx_coin(
                    coin_name, tx, get_api['id'], find_tx['depost_id']
                )
                if noted is True:
                    result_data = {
                        "success": True,
                        "data": None,
                        "message": f"noted for tx {tx}.",
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data
                else:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "{}, internal error noting tx: {}.".format(coin_name, tx),
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, json.dumps(data_call), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result

@app.get("/list_transactions/{coin_name}/{address}")
async def list_transactions(
    request: Request, coin_name: str, address: str, Authorization: Union[str, None] = Header(default=None)
):
    """
    Get list of transactions for a coin, address

    coin_name: coin name
    address: address of deposited coin
    """
    method_call = "/list_transactions/"
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            data_call = json.dumps({"coin_name": coin_name, "api_id": get_api['id'], "address": address})
            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, data_call, json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            if address not in runner.addresses:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "{}, address: {} not within your API.".format(coin_name, address),
                    "time": int(time.time())
                }
                data_call = {"coin_name": coin_name, "address": address}
                try:
                    await insert_api_failed_log(get_api['id'], method_call, json.dumps(data_call), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                get_txes = await get_txes_address_coin_api(
                    coin_name, get_api['id'], address, 500
                )
                
                if len(get_txes) == 0:
                    result_data = {
                        "success": True,
                        "data": [],
                        "message": "no transactions.",
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data
                else:
                    result_data = {
                        "success": True,
                        "data": [{
                            "coin_name": coin_name,
                            "txid": i['txid'],
                            "amount": i['amount'],
                            "address": i['address'],
                            "time": i['time_insert'],
                            "tag": i['tag'],
                            "second_tag": i['second_tag'],
                            "noted": i['already_noted'],
                            "noted_time": i['noted_time']
                            } for i in get_txes
                        ],
                        "message": None,
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data

@app.get("/list_transactions/{coin_name}")
async def list_transactions_coin(
    request: Request, coin_name: str, Authorization: Union[str, None] = Header(default=None)
):
    """
    Get list of transactions for a coin, address

    coin_name: coin name
    """
    method_call = "/list_transactions/"
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            data_call = json.dumps({"coin_name": coin_name, "api_id": get_api['id']})
            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, data_call, json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            get_txes = await get_txes_address_coin_api(
                coin_name, get_api['id'], None, 500
            )
            if len(get_txes) == 0:
                result_data = {
                    "success": True,
                    "data": [],
                    "message": "no transactions.",
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data
            else:
                result_data = {
                    "success": True,
                    "data": [{
                        "coin_name": coin_name,
                        "txid": i['txid'],
                        "amount": i['amount'],
                        "address": i['address'],
                        "time": i['time_insert'],
                        "tag": i['tag'],
                        "second_tag": i['second_tag'],
                        "noted": i['already_noted'],
                        "noted_time": i['noted_time']
                        } for i in get_txes
                    ],
                    "message": None,
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data

@app.get("/list_withdraws/{coin_name}/{address}")
async def list_withdraws(
    request: Request, coin_name: str, address: str, Authorization: Union[str, None] = Header(default=None)
):
    """
    Get list of withdraws for a coin, address

    coin_name: coin name
    address: address of deposited coin
    """
    method_call = "/list_withdraws/"
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            data_call = json.dumps({"coin_name": coin_name, "api_id": get_api['id'], "address": address})
            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, data_call, json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            if address not in runner.addresses:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "{}, address: {} not within your API.".format(coin_name, address),
                    "time": int(time.time())
                }
                data_call = {"coin_name": coin_name, "address": address}
                try:
                    await insert_api_failed_log(get_api['id'], method_call, json.dumps(data_call), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                get_txes = await get_withdraws_address_coin_api(
                    coin_name, get_api['id'], address, 500
                )
                
                if len(get_txes) == 0:
                    result_data = {
                        "success": True,
                        "data": [],
                        "message": "no transactions.",
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data
                else:
                    result_data = {
                        "success": True,
                        "data": [{
                            "coin_name": coin_name,
                            "txid": i['txid'],
                            "amount": i['amount'],
                            "to_address": i['to_address'],
                            "time": i['timestamp'],
                            "tag": i['tag'],
                            "second_tag": i['second_tag']
                            } for i in get_txes
                        ],
                        "message": None,
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    return result_data

@app.get("/list_withdraws/{coin_name}")
async def list_withdraws_coin(
    request: Request, coin_name: str, Authorization: Union[str, None] = Header(default=None)
):
    """
    Get list of withdraws for a coin, address

    coin_name: coin name
    """
    method_call = "/list_withdraws/"
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            data_call = json.dumps({"coin_name": coin_name, "api_id": get_api['id']})
            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, data_call, json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            get_txes = await get_withdraws_address_coin_api(
                coin_name, get_api['id'], None, 500
            )
            if len(get_txes) == 0:
                result_data = {
                    "success": True,
                    "data": [],
                    "message": "no transactions.",
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data
            else:
                result_data = {
                    "success": True,
                    "data": [{
                        "coin_name": coin_name,
                        "txid": i['txid'],
                        "amount": i['amount'],
                        "to_address": i['to_address'],
                        "time": i['timestamp'],
                        "tag": i['tag'],
                        "second_tag": i['second_tag']
                        } for i in get_txes
                    ],
                    "message": None,
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data

@app.get("/list_address/{coin_name}")
async def list_addresses(
    request: Request, coin_name: str, Authorization: Union[str, None] = Header(default=None)
):
    """
    Get list of addresses of a coin with tag

    coin_name: coin name
    """
    method_call = "/list_address/"
    coin_name = coin_name.upper()
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            data_call = json.dumps({"coin_name": coin_name, "api_id": get_api['id']})
            # check if that API can use that coin
            if coin_name not in get_api['allowed_coin'].replace(" ","").split(","):
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": f"Your API is limited to these coins: {get_api['allowed_coin']}! If you need, please request additional access.",
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, data_call, json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            get_addresses = await get_addresses_coin_api(
                coin_name, get_api['id']
            )
            if len(get_addresses) == 0:
                result_data = {
                    "success": True,
                    "data": [],
                    "message": "no address.",
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data
            else:
                result_data = {
                    "success": True,
                    "data": [{"coin_name": coin_name, "address": i['address'], "created": i['created_date'], "tag": i['tag']} for i in get_addresses],
                    "message": None,
                    "time": int(time.time())
                }
                await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                return result_data


class hold_balance_coin(BaseModel):
    coin: str
    address: str
    amount: float
    expiring: int = 3600
    purpose: str = None

@app.post("/hold_alance")
async def hold_a_balance(
    request: Request, item: hold_balance_coin, Authorization: Union[str, None] = Header(default=None)
):
    """
    Hold a balance of an address of a coin

    item: {coin, address, amount}
    """
    method_call = "/hold_balance"
    coin_name = item.coin.upper()
    address = item.address
    if runner.coin_list is None or len(runner.coin_list) == 0:
        return {
            "success": False,
            "data": None,
            "message": "internal error.",
            "time": int(time.time())
        }
    if coin_name not in runner.coin_list.keys():
        return {
            "success": False,
            "data": None,
            "message": "coin {} not in the supported list!".format(coin_name),
            "time": int(time.time())
        }
    else:
        if 'Authorization' not in request.headers:
            return {
                "success": False,
                "data": None,
                "message": "You need Authorization key in header!",
                "time": int(time.time())
            }
        else:
            # get who own that key
            get_api = await get_api_by_key(request.headers['Authorization'])
            if get_api is None:
                return {
                    "success": False,
                    "data": None,
                    "message": "Wrong API key!",
                    "time": int(time.time())
                }
            elif get_api['is_suspended'] != 0:
                return {
                    "success": False,
                    "data": None,
                    "message": "We suspended your API key, please contact us!",
                    "time": int(time.time())
                }

            if get_api['id'] != runner.by_key["{}_{}".format(coin_name, item.address)]['api_id']:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "{}, address {}.. permission denied.".format(coin_name, item.address),
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result

            get_balance = await get_balance_coin_address(
                get_api['id'], coin_name, address
            )
            if get_balance is None:
                failed_result = {
                    "success": False,
                    "data": None,
                    "message": "{}, address not found {}!".format(coin_name, address),
                    "time": int(time.time())
                }
                try:
                    await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                except Exception:
                    traceback.print_exc(file=sys.stdout) 
                return failed_result
            else:
                if item.amount < 0:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "{}, invalid amount {}!".format(coin_name, item.amount),
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result
                
                round_places = runner.coin_list[coin_name]['round_places']
                balance = round_amount(get_balance['total_deposited'] + get_balance['total_received'] - get_balance['total_sent'] - get_balance['total_withdrew'] - get_balance['amount_hold'], round_places)
                hold_amount = round_amount(item.amount, round_places)
                purpose = ""
                if hasattr(item, "purpose") and len(item.purpose) > 256:
                    purpose = item.purpose.strip()[0:255]
                elif hasattr(item, "purpose") and len(item.purpose) > 0:
                    purpose = item.purpose.strip()
                if hasattr(item, "expiring") and item.expiring > 30*24*3600:
                    expiring = 30*24*3600
                elif hasattr(item, "expiring") and item.expiring <= 30:
                    expiring = 30
                if hold_amount > balance:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "{}, insufficient balance to hold amount {}! Having {}!".format(coin_name, hold_amount, balance),
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout)
                    try:
                        await log_to_discord(
                            "🔴 API: {} / {} - trying to hold {} {} but having {} {}.".format(get_api['id'], item.address, hold_amount, coin_name, balance, coin_name),
                            config['log']['discord_webhook_default']
                        )
                    except Exception:
                        traceback.print_exc(file=sys.stdout)
                    return failed_result
                holding = await insert_hold_address(
                    coin_name, get_api['id'], runner.by_key["{}_{}".format(coin_name, item.address)]['id'], item.address,
                    hold_amount, int(time.time()) + expiring, item.purpose
                )
                if holding is True:
                    data_call = json.dumps({"coin": coin_name, "address": address, "hold_balance": hold_amount, "expiring": int(time.time()) + expiring, "purpose": purpose})
                    result_data = {
                        "success": True,
                        "data": {
                            "coin": coin_name,
                            "address": address,
                            "hold_amount": hold_amount,
                            "expiring": int(time.time()) + expiring,
                            "purpose": purpose
                        },
                        "message": None,
                        "time": int(time.time())
                    }
                    await insert_api_log(get_api['id'], method_call, data_call, json.dumps(result_data))
                    try:
                        await log_to_discord(
                            "🗃️ API: {} / {} - HOLDING {} {} and expiring: <t:{}:f>.".format(get_api['id'], item.address, hold_amount, coin_name, int(time.time()) + expiring),
                            config['log']['discord_webhook_default']
                        )
                    except Exception:
                        traceback.print_exc(file=sys.stdout)
                    return result_data
                else:
                    failed_result = {
                        "success": False,
                        "data": None,
                        "message": "{}, internal error for holding {} of address {}".format(coin_name, hold_amount, item.address),
                        "time": int(time.time())
                    }
                    try:
                        await insert_api_failed_log(get_api['id'], method_call, str(item), json.dumps(failed_result))
                    except Exception:
                        traceback.print_exc(file=sys.stdout) 
                    return failed_result

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config['coinapi']['api_bind'],
        headers=[("server", config['coinapi']['api_name'])],
        port=config['coinapi']['api_port'],
        access_log=False
    )
