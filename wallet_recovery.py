import random
import time
import os
import ssl
import certifi
import logging
import asyncio
from mnemonic import Mnemonic
from bitcoinlib.keys import HDKey
import aiohttp
from aiohttp import ClientSession
from colorama import Fore, Style, init

# Инициализация colorama
init(autoreset=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

error_logger = logging.getLogger("error_logger")
error_handler = logging.FileHandler("errors.log")
error_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
error_logger.addHandler(error_handler)

balance_logger = logging.getLogger("balance_logger")
balance_handler = logging.FileHandler("wallets_with_balance.log")
balance_handler.setFormatter(logging.Formatter("%(asctime)s - Фраза: %(message)s"))
balance_logger.addHandler(balance_handler)

# Путь для хранения проверенных адресов
CHECKED_ADDRESSES_FILE = "checked_addresses.txt"
checked_addresses = set()

# Telegram bot settings
TELEGRAM_BOT_TOKEN = "7121433693:AAFRxGttMKcZt92LVUzRYMRWTxPTYCuOkkc"
TELEGRAM_CHAT_ID = "1325291643"

# API URLs
BLOCKSTREAM_API_URL = "https://blockstream.info/api/address/"
BLOCKCHAIN_API_URL = "https://blockchain.info/q/addressbalance/"
BLOCKCHAIR_API_URL = "https://api.blockchair.com/bitcoin/dashboards/address/"

def clear_error_log():
    with open("errors.log", "w"):
        pass  # Открытие с режимом 'w' очищает файл

# Загрузка проверенных адресов
def load_checked_addresses():
    if os.path.exists(CHECKED_ADDRESSES_FILE):
        with open(CHECKED_ADDRESSES_FILE, "r") as file:
            for line in file:
                checked_addresses.add(line.strip())

def save_checked_address(address):
    """Сохранение проверенного адреса"""
    with open(CHECKED_ADDRESSES_FILE, "a") as file:
        file.write(address + "\n")

async def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": message}

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, ssl=ssl_context) as response:
                if response.status != 200:
                    error_logger.error(f"Ошибка отправки сообщения в Telegram: {response.status}")
        except Exception as e:
            error_logger.error(f"Ошибка при запросе к Telegram API: {e}")


def generate_mnemonic():
    """Генерация случайной мнемонической фразы"""
    mnemo = Mnemonic("english")
    return mnemo.generate(strength=128)

def get_address_from_mnemonic(mnemonic_phrase):
    """Создание Bitcoin-адреса P2PKH из мнемонической фразы"""
    try:
        seed = Mnemonic.to_seed(mnemonic_phrase)
        master_key = HDKey.from_seed(seed, network="bitcoin")
        child_key = master_key.subkey_for_path("m/44'/0'/0'/0/0")
        return child_key.address(script_type="p2pkh", encoding="base58")
    except Exception as e:
        error_logger.error(f"Ошибка генерации адреса: {e}")
        return None

async def check_balance_blockstream(address):
    """Проверка баланса через Blockstream API"""
    async with ClientSession() as session:
        try:
            async with session.get(f"{BLOCKSTREAM_API_URL}{address}") as response:
                if response.status == 200:
                    data = await response.json()
                    balance = data.get("chain_stats", {}).get("funded_txo_sum", 0) - data.get("chain_stats", {}).get("spent_txo_sum", 0)
                    return balance
                return 0
        except Exception as e:
            error_logger.error(f"Ошибка при запросе к Blockstream API для адреса {address}: {e}")
            return 0

async def check_balance_blockchain(address):
    """Проверка баланса через Blockchain API"""
    async with ClientSession() as session:
        try:
            async with session.get(f"{BLOCKCHAIN_API_URL}{address}") as response:
                if response.status == 200:
                    balance = int(await response.text())
                    return balance
                return 0
        except Exception as e:
            error_logger.error(f"Ошибка при запросе к Blockchain API для адреса {address}: {e}")
            return 0

async def check_balance_blockchair(address):
    """Проверка баланса через Blockchair API"""
    async with ClientSession() as session:
        try:
            async with session.get(f"{BLOCKCHAIR_API_URL}{address}") as response:
                if response.status == 200:
                    data = await response.json()
                    balance = data["data"][address]["address"]["balance"]
                    return balance
                return 0
        except Exception as e:
            error_logger.error(f"Ошибка при запросе к Blockchair API для адреса {address}: {e}")
            return 0

async def check_balance(address):
    """Объединенная проверка баланса через несколько API"""
    balance = await check_balance_blockstream(address)
    if balance > 0:
        return balance
    balance = await check_balance_blockchain(address)
    if balance > 0:
        return balance
    balance = await check_balance_blockchair(address)
    if balance > 0:
        return balance
    return 0  # Return 0 if no balance found

async def process_mnemonic():
    """Обработка одной мнемонической фразы"""
    mnemonic_phrase = generate_mnemonic()
    address = get_address_from_mnemonic(mnemonic_phrase)

    if address and address not in checked_addresses:
        checked_addresses.add(address)
        save_checked_address(address)
        balance = await check_balance(address)

        if balance > 0:
            # Выводим в консоль информацию о найденном кошельке
            print(Fore.GREEN + Style.BRIGHT + f"!!! Найден кошелёк с балансом: {balance} сатоши !!!")
            balance_logger.info(f"{mnemonic_phrase} -> {address}, Баланс: {balance}")
            message = f"Найден кошелёк с балансом: {balance} сатоши\nАдрес: {address}\nМнемоническая фраза: {mnemonic_phrase}"
            await send_telegram_message(message)
        else:
            # Выводим в консоль информацию о пустом кошельке
            print(Fore.YELLOW + f"Кошелёк с адресом {address} пустой.")

async def main():
    """Основная функция программы"""
    load_checked_addresses()
    await send_telegram_message("Бот работает! Вы получите уведомления, если будет найден кошелёк с балансом.")
    while True:
        tasks = [process_mnemonic() for _ in range(5)]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        clear_error_log()
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Произошла ошибка: {e}")
        input("Нажмите Enter, чтобы закрыть...")
