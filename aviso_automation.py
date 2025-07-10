#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aviso YouTube Tasks Automation Script - ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ
ИСПРАВЛЕНИЯ:
- Убраны ВСЕ мосты Tor - только прямое соединение
- Упрощена конфигурация Tor
- Добавлен fallback без Tor если не работает
"""

import os
import sys
import time
import random
import json
import logging
import subprocess
import platform
import re
import pickle
import hashlib
import shutil
import zipfile
import stat
import socket
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import math

# Попытка импорта необходимых библиотек с автоустановкой
def install_requirements():
    """Автоматическая установка необходимых зависимостей"""
    required_packages = [
        'selenium',
        'requests',
        'beautifulsoup4',
        'fake-useragent',
        'webdriver-manager'
    ]
    
    logging.info("📦 Проверка и установка зависимостей...")
    
    for package in required_packages:
        try:
            package_name = package.split('[')[0].replace('-', '_')
            __import__(package_name)
            logging.info(f"✓ Пакет {package} уже установлен")
        except ImportError:
            logging.info(f"⚠ Устанавливаю пакет {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package], 
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logging.info(f"✓ Пакет {package} успешно установлен")
            except subprocess.CalledProcessError as e:
                logging.error(f"✗ Ошибка установки пакета {package}: {e}")
                try:
                    logging.info(f"🔄 Попытка альтернативной установки {package}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", package],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logging.info(f"✓ Пакет {package} установлен через --user")
                except subprocess.CalledProcessError:
                    logging.warning(f"⚠ Не удалось установить {package}, но продолжаем...")

# Настройка базового логирования до установки зависимостей
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Установка зависимостей
install_requirements()

# Импорт после установки
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.common.exceptions import *
    from selenium.webdriver.common.keys import Keys
    try:
        from webdriver_manager.firefox import GeckoDriverManager as WDMGeckoDriverManager
    except ImportError:
        WDMGeckoDriverManager = None
    import requests
    from bs4 import BeautifulSoup
    from fake_useragent import UserAgent
except ImportError as e:
    logging.error(f"❌ Критическая ошибка импорта: {e}")
    logging.error("📋 Попробуйте установить зависимости вручную:")
    logging.error("pip install selenium requests beautifulsoup4 fake-useragent webdriver-manager")
    sys.exit(1)

def kill_existing_tor_processes():
    """Убиваем все существующие процессы Tor"""
    try:
        logging.info("🔄 Очистка существующих процессов Tor...")
        
        system = platform.system().lower()
        is_termux = 'com.termux' in os.environ.get('PREFIX', '') or '/data/data/com.termux' in os.environ.get('HOME', '')
        
        if is_termux or system == 'linux':
            # Убиваем все процессы tor
            try:
                subprocess.run(['pkill', '-f', 'tor'], capture_output=True, timeout=10)
                time.sleep(2)
            except:
                pass
            
            # Дополнительная очистка через killall
            try:
                subprocess.run(['killall', 'tor'], capture_output=True, timeout=10)
                time.sleep(2)
            except:
                pass
                
        elif system == 'windows':
            try:
                subprocess.run(['taskkill', '/F', '/IM', 'tor.exe'], capture_output=True, timeout=10)
                time.sleep(2)
            except:
                pass
        
        logging.info("✓ Очистка процессов Tor завершена")
        
    except Exception as e:
        logging.debug(f"⚠ Ошибка очистки процессов Tor: {e}")

def find_free_port_range(start_port: int, count: int = 2) -> List[int]:
    """Поиск нескольких свободных портов подряд"""
    free_ports = []
    
    for port in range(start_port, start_port + 1000):
        if len(free_ports) >= count:
            break
            
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', port))
                free_ports.append(port)
        except OSError:
            free_ports = []  # Начинаем поиск заново
            continue
    
    if len(free_ports) >= count:
        return free_ports[:count]
    
    # Если не нашли подряд, берем случайные
    import random
    fallback_ports = []
    for _ in range(count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            fallback_ports.append(s.getsockname()[1])
    
    return fallback_ports

class GeckoDriverManager:
    """Класс для управления geckodriver"""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.is_termux = self.detect_termux()
        self.driver_path = None
        
    def detect_termux(self) -> bool:
        """Определение запуска в Termux"""
        return 'com.termux' in os.environ.get('PREFIX', '') or \
               '/data/data/com.termux' in os.environ.get('HOME', '')
    
    def get_latest_geckodriver_version(self) -> str:
        """Получение последней версии geckodriver"""
        try:
            response = requests.get('https://api.github.com/repos/mozilla/geckodriver/releases/latest', timeout=10)
            response.raise_for_status()
            data = response.json()
            return data['tag_name'].lstrip('v')
        except Exception as e:
            logging.warning(f"⚠ Не удалось получить версию geckodriver: {e}")
            return "0.33.0"  # Фоллбэк версия
    
    def download_geckodriver(self, version: str) -> Optional[str]:
        """Скачивание geckodriver"""
        try:
            # Определяем архитектуру и платформу
            if self.is_termux:
                platform_name = "linux-aarch64"
                if "aarch64" not in platform.machine():
                    platform_name = "linux32"
            elif self.system == 'linux':
                arch = platform.machine()
                if arch == 'x86_64':
                    platform_name = "linux64"
                elif arch == 'aarch64':
                    platform_name = "linux-aarch64"
                else:
                    platform_name = "linux32"
            elif self.system == 'windows':
                arch = platform.machine()
                if arch == 'AMD64':
                    platform_name = "win64"
                else:
                    platform_name = "win32"
            elif self.system == 'darwin':
                arch = platform.machine()
                if arch == 'arm64':
                    platform_name = "macos-aarch64"
                else:
                    platform_name = "macos"
            else:
                logging.error(f"✗ Неподдерживаемая платформа: {self.system}")
                return None
            
            # URL для скачивания
            if self.system == 'windows':
                filename = f"geckodriver-v{version}-{platform_name}.zip"
                executable_name = "geckodriver.exe"
            else:
                filename = f"geckodriver-v{version}-{platform_name}.tar.gz"
                executable_name = "geckodriver"
            
            url = f"https://github.com/mozilla/geckodriver/releases/download/v{version}/{filename}"
            
            logging.info(f"📥 Скачивание geckodriver v{version} для {platform_name}...")
            
            # Создаем директорию для драйверов
            drivers_dir = os.path.join(os.path.expanduser("~"), ".webdrivers")
            os.makedirs(drivers_dir, exist_ok=True)
            
            # Скачиваем файл
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            archive_path = os.path.join(drivers_dir, filename)
            with open(archive_path, 'wb') as f:
                f.write(response.content)
            
            logging.info(f"✓ Geckodriver скачан: {archive_path}")
            
            # Извлекаем архив
            extract_dir = os.path.join(drivers_dir, f"geckodriver-{version}")
            os.makedirs(extract_dir, exist_ok=True)
            
            if filename.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            else:
                import tarfile
                with tarfile.open(archive_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(extract_dir)
            
            # Находим исполняемый файл
            driver_path = os.path.join(extract_dir, executable_name)
            
            if not os.path.exists(driver_path):
                # Ищем в подпапках
                for root, dirs, files in os.walk(extract_dir):
                    if executable_name in files:
                        driver_path = os.path.join(root, executable_name)
                        break
            
            if os.path.exists(driver_path):
                # Делаем исполняемым на Unix системах
                if self.system != 'windows':
                    st = os.stat(driver_path)
                    os.chmod(driver_path, st.st_mode | stat.S_IEXEC)
                
                logging.info(f"✅ Geckodriver установлен: {driver_path}")
                
                # Удаляем архив
                try:
                    os.remove(archive_path)
                except:
                    pass
                
                return driver_path
            else:
                logging.error(f"✗ Не найден исполняемый файл geckodriver в {extract_dir}")
                return None
                
        except Exception as e:
            logging.error(f"✗ Ошибка скачивания geckodriver: {e}")
            return None
    
    def find_geckodriver(self) -> Optional[str]:
        """Поиск geckodriver в системе"""
        # Проверяем в PATH
        try:
            if self.system == 'windows':
                result = subprocess.run(['where', 'geckodriver'], capture_output=True, text=True)
            else:
                result = subprocess.run(['which', 'geckodriver'], capture_output=True, text=True)
            
            if result.returncode == 0:
                driver_path = result.stdout.strip()
                if os.path.exists(driver_path):
                    logging.info(f"✓ Найден geckodriver в PATH: {driver_path}")
                    return driver_path
        except:
            pass
        
        # Проверяем в стандартных местах
        possible_paths = []
        
        if self.is_termux:
            possible_paths = [
                '/data/data/com.termux/files/usr/bin/geckodriver',
                f"{os.environ.get('PREFIX', '')}/bin/geckodriver"
            ]
        elif self.system == 'linux':
            possible_paths = [
                '/usr/bin/geckodriver',
                '/usr/local/bin/geckodriver',
                '/opt/geckodriver/geckodriver',
                '/snap/bin/geckodriver'
            ]
        elif self.system == 'windows':
            possible_paths = [
                r"C:\Program Files\geckodriver\geckodriver.exe",
                r"C:\Program Files (x86)\geckodriver\geckodriver.exe",
                r"C:\geckodriver\geckodriver.exe"
            ]
        elif self.system == 'darwin':
            possible_paths = [
                '/usr/local/bin/geckodriver',
                '/opt/homebrew/bin/geckodriver'
            ]
        
        # Проверяем в домашней директории
        home_drivers = os.path.join(os.path.expanduser("~"), ".webdrivers")
        if os.path.exists(home_drivers):
            for root, dirs, files in os.walk(home_drivers):
                for file in files:
                    if file.startswith('geckodriver'):
                        possible_paths.append(os.path.join(root, file))
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logging.info(f"✓ Найден geckodriver: {path}")
                return path
        
        return None
    
    def get_driver_path(self) -> str:
        """Получение пути к geckodriver с автоматической установкой"""
        if self.driver_path:
            return self.driver_path
        
        # Сначала ищем существующий
        driver_path = self.find_geckodriver()
        
        if not driver_path:
            logging.info("📦 Geckodriver не найден, начинаю автоматическую установку...")
            
            # Пробуем использовать webdriver-manager
            if WDMGeckoDriverManager:
                try:
                    logging.info("🔄 Попытка использования webdriver-manager...")
                    driver_path = WDMGeckoDriverManager().install()
                    if driver_path and os.path.exists(driver_path):
                        logging.info(f"✅ Geckodriver установлен через webdriver-manager: {driver_path}")
                        self.driver_path = driver_path
                        return driver_path
                except Exception as e:
                    logging.warning(f"⚠ Webdriver-manager не удался: {e}")
            
            # Скачиваем вручную
            version = self.get_latest_geckodriver_version()
            driver_path = self.download_geckodriver(version)
            
            if not driver_path:
                raise Exception("Не удалось установить geckodriver автоматически")
        
        self.driver_path = driver_path
        return driver_path

class UserAgentManager:
    """Класс для управления User-Agent для каждого аккаунта"""
    
    def __init__(self):
        self.ua_file = "user_agents.json"
        self.user_agents = self.load_user_agents()
        
    def load_user_agents(self) -> Dict[str, str]:
        """Загрузка сохраненных User-Agent'ов"""
        try:
            if os.path.exists(self.ua_file):
                with open(self.ua_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logging.debug(f"⚠ Ошибка загрузки User-Agent'ов: {e}")
        
        return {}
    
    def save_user_agents(self):
        """Сохранение User-Agent'ов"""
        try:
            with open(self.ua_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_agents, f, indent=2, ensure_ascii=False)
            logging.debug("💾 User-Agent'ы сохранены")
        except Exception as e:
            logging.error(f"✗ Ошибка сохранения User-Agent'ов: {e}")
    
    def get_user_agent(self, username: str) -> str:
        """Получение User-Agent для конкретного пользователя"""
        # Создаем уникальный ключ для пользователя
        user_key = hashlib.md5(username.encode()).hexdigest()
        
        if user_key not in self.user_agents:
            # Генерируем новый User-Agent для Firefox
            try:
                ua = UserAgent()
                # Получаем Firefox User-Agent
                firefox_ua = ua.firefox
                self.user_agents[user_key] = firefox_ua
                self.save_user_agents()
                logging.info(f"🎭 Создан новый User-Agent для пользователя {username}")
            except Exception as e:
                logging.warning(f"⚠ Ошибка генерации User-Agent: {e}")
                # Фоллбэк User-Agent для Firefox
                self.user_agents[user_key] = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0"
        
        user_agent = self.user_agents[user_key]
        logging.info(f"🎭 Используется User-Agent для {username}: {user_agent[:50]}...")
        return user_agent

class HumanBehaviorSimulator:
    """Класс для имитации человеческого поведения"""
    
    @staticmethod
    def random_sleep(min_seconds: float = 0.5, max_seconds: float = 3.0):
        """Случайная пауза"""
        sleep_time = random.uniform(min_seconds, max_seconds)
        logging.debug(f"💤 Пауза {sleep_time:.2f} секунд")
        time.sleep(sleep_time)
    
    @staticmethod
    def generate_bezier_curve(start: Tuple[int, int], end: Tuple[int, int], 
                            control_points: int = 3) -> List[Tuple[int, int]]:
        """Генерация кривой Безье для движения мыши"""
        def bezier_point(t: float, points: List[Tuple[int, int]]) -> Tuple[int, int]:
            n = len(points) - 1
            x = sum(math.comb(n, i) * (1-t)**(n-i) * t**i * points[i][0] for i in range(n+1))
            y = sum(math.comb(n, i) * (1-t)**(n-i) * t**i * points[i][1] for i in range(n+1))
            return int(x), int(y)
        
        # Создаем контрольные точки
        control_pts = [start]
        for _ in range(control_points):
            x = random.randint(min(start[0], end[0]), max(start[0], end[0]))
            y = random.randint(min(start[1], end[1]), max(start[1], end[1]))
            control_pts.append((x, y))
        control_pts.append(end)
        
        # Генерируем точки кривой
        curve_points = []
        steps = random.randint(20, 50)
        for i in range(steps + 1):
            t = i / steps
            point = bezier_point(t, control_pts)
            curve_points.append(point)
        
        return curve_points
    
    @staticmethod
    def human_like_typing(element, text: str, driver):
        """Улучшенная имитация человеческого набора текста с опечатками"""
        element.clear()
        HumanBehaviorSimulator.random_sleep(0.3, 1.0)
        
        # Раскладки клавиатуры для имитации опечаток
        qwerty_neighbors = {
            'q': ['w', 'a'], 'w': ['q', 'e', 's'], 'e': ['w', 'r', 'd'], 'r': ['e', 't', 'f'],
            't': ['r', 'y', 'g'], 'y': ['t', 'u', 'h'], 'u': ['y', 'i', 'j'], 'i': ['u', 'o', 'k'],
            'o': ['i', 'p', 'l'], 'p': ['o', 'l'], 'a': ['q', 's', 'z'], 's': ['w', 'a', 'd', 'x'],
            'd': ['e', 's', 'f', 'c'], 'f': ['r', 'd', 'g', 'v'], 'g': ['t', 'f', 'h', 'b'],
            'h': ['y', 'g', 'j', 'n'], 'j': ['u', 'h', 'k', 'm'], 'k': ['i', 'j', 'l'],
            'l': ['o', 'k', 'p'], 'z': ['a', 's', 'x'], 'x': ['z', 's', 'd', 'c'],
            'c': ['x', 'd', 'f', 'v'], 'v': ['c', 'f', 'g', 'b'], 'b': ['v', 'g', 'h', 'n'],
            'n': ['b', 'h', 'j', 'm'], 'm': ['n', 'j', 'k'],
            '1': ['2', 'q'], '2': ['1', '3', 'q', 'w'], '3': ['2', '4', 'w', 'e'],
            '4': ['3', '5', 'e', 'r'], '5': ['4', '6', 'r', 't'], '6': ['5', '7', 't', 'y'],
            '7': ['6', '8', 'y', 'u'], '8': ['7', '9', 'u', 'i'], '9': ['8', '0', 'i', 'o'],
            '0': ['9', 'o', 'p']
        }
        
        typed_text = ""
        i = 0
        
        while i < len(text):
            char = text[i].lower()
            
            # Случайные паузы между символами (более реалистичные)
            if char == ' ':
                pause = random.uniform(0.1, 0.4)  # Длиннее пауза для пробелов
            elif char.isdigit():
                pause = random.uniform(0.08, 0.25)  # Цифры печатаем медленнее
            else:
                pause = random.uniform(0.05, 0.2)
            
            time.sleep(pause)
            
            # Имитация опечаток (8% вероятность)
            if random.random() < 0.08 and char in qwerty_neighbors:
                # Делаем опечатку
                wrong_char = random.choice(qwerty_neighbors[char])
                element.send_keys(wrong_char)
                typed_text += wrong_char
                logging.debug(f"🔤 Опечатка: '{wrong_char}' вместо '{char}'")
                
                # Пауза перед исправлением (как будто заметили ошибку)
                time.sleep(random.uniform(0.2, 0.8))
                
                # Исправляем опечатку
                element.send_keys(Keys.BACKSPACE)
                typed_text = typed_text[:-1]
                time.sleep(random.uniform(0.1, 0.3))
                
                # Печатаем правильный символ
                element.send_keys(text[i])
                typed_text += text[i]
                logging.debug(f"🔤 Исправлено на: '{text[i]}'")
                
            # Имитация двойного нажатия (3% вероятность)
            elif random.random() < 0.03:
                element.send_keys(text[i])
                element.send_keys(text[i])  # Двойное нажатие
                typed_text += text[i] + text[i]
                logging.debug(f"🔤 Двойное нажатие: '{text[i]}'")
                
                # Пауза и исправление
                time.sleep(random.uniform(0.3, 0.7))
                element.send_keys(Keys.BACKSPACE)
                typed_text = typed_text[:-1]
                
            # Имитация случайного caps lock (только для букв, 2% вероятность)
            elif random.random() < 0.02 and char.isalpha():
                if random.choice([True, False]):
                    wrong_case = text[i].upper() if text[i].islower() else text[i].lower()
                else:
                    wrong_case = text[i].upper()
                
                element.send_keys(wrong_case)
                typed_text += wrong_case
                logging.debug(f"🔤 Неправильный регистр: '{wrong_case}' вместо '{text[i]}'")
                
                # Пауза и исправление
                time.sleep(random.uniform(0.4, 1.0))
                element.send_keys(Keys.BACKSPACE)
                typed_text = typed_text[:-1]
                time.sleep(random.uniform(0.1, 0.3))
                element.send_keys(text[i])
                typed_text += text[i]
                
            else:
                # Обычное нажатие
                element.send_keys(text[i])
                typed_text += text[i]
            
            # Случайные более длинные паузы (как будто думаем)
            if random.random() < 0.05:  # 5% вероятность
                thinking_pause = random.uniform(0.5, 2.0)
                logging.debug(f"🤔 Пауза для размышления: {thinking_pause:.2f}с")
                time.sleep(thinking_pause)
            
            i += 1
        
        # Финальная пауза после ввода
        HumanBehaviorSimulator.random_sleep(0.5, 1.5)

class SimpleTorManager:
    """УПРОЩЕННЫЙ класс для управления Tor соединением ТОЛЬКО с прямым подключением"""
    
    def __init__(self):
        self.tor_port = None
        self.control_port = None
        self.tor_process = None
        self.system = platform.system().lower()
        self.is_termux = self.detect_termux()
        
        # Пути к временным файлам
        self.tor_data_dir = None
        self.torrc_path = None
        self.stdout_log = None
        self.stderr_log = None
        
    def detect_termux(self) -> bool:
        """Определение запуска в Termux"""
        return 'com.termux' in os.environ.get('PREFIX', '') or \
               '/data/data/com.termux' in os.environ.get('HOME', '')
    
    def command_exists(self, cmd: str) -> bool:
        """Проверка существования команды"""
        try:
            if self.is_termux or self.system == 'linux':
                result = subprocess.run(['command', '-v', cmd], 
                                      capture_output=True, text=True, shell=True)
                return result.returncode == 0
            elif self.system == 'windows':
                result = subprocess.run(['where', cmd], 
                                      capture_output=True, text=True)
                return result.returncode == 0
            else:  # macOS
                result = subprocess.run(['which', cmd], 
                                      capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    def install_tor_termux(self) -> bool:
        """Установка Tor в Termux"""
        try:
            logging.info("📱 Установка Tor в Termux...")
            
            # Обновление пакетов
            logging.info("🔄 Обновление списка пакетов...")
            subprocess.run(['pkg', 'update'], check=True, 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Установка Tor
            logging.info("📦 Установка Tor...")
            subprocess.run(['pkg', 'install', '-y', 'tor'], check=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            logging.info("✓ Tor успешно установлен в Termux")
            return True
            
        except subprocess.CalledProcessError as e:
            logging.error(f"✗ Ошибка установки Tor в Termux: {e}")
            return False
        except Exception as e:
            logging.error(f"✗ Неожиданная ошибка установки Tor в Termux: {e}")
            return False
    
    def install_tor(self) -> bool:
        """Автоматическая установка Tor"""
        if self.is_termux:
            return self.install_tor_termux()
        else:
            logging.warning("⚠ Автоустановка Tor поддерживается только в Termux")
            logging.info("💡 Установите Tor вручную для вашей системы")
            return False
    
    def find_tor_executable(self) -> Optional[str]:
        """Поиск исполняемого файла Tor"""
        possible_paths = []
        
        if self.is_termux:
            possible_paths = [
                '/data/data/com.termux/files/usr/bin/tor',
                f"{os.environ.get('PREFIX', '')}/bin/tor"
            ]
        elif self.system == 'linux':
            possible_paths = [
                '/usr/bin/tor',
                '/usr/local/bin/tor',
                '/opt/tor/bin/tor'
            ]
        elif self.system == 'windows':
            username = os.getenv('USERNAME', 'User')
            possible_paths = [
                f"C:\\Users\\{username}\\Desktop\\Tor Browser\\Browser\\TorBrowser\\Tor\\tor.exe",
                r"C:\Program Files\Tor Browser\Browser\TorBrowser\Tor\tor.exe",
                r"C:\Program Files (x86)\Tor Browser\Browser\TorBrowser\Tor\tor.exe",
                r"C:\Tor\tor.exe"
            ]
        elif self.system == 'darwin':
            possible_paths = [
                '/usr/local/bin/tor',
                '/opt/homebrew/bin/tor',
                '/Applications/Tor Browser.app/Contents/MacOS/Tor/tor'
            ]
        
        # Проверяем каждый путь
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logging.info(f"✓ Найден Tor: {path}")
                return path
        
        # Проверяем через PATH
        if self.command_exists('tor'):
            logging.info("✓ Tor найден в PATH")
            return 'tor'
        
        return None
    
    def check_tor_port(self) -> bool:
        """Быстрая проверка доступности порта Tor"""
        if not self.tor_port:
            return False
            
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                result = s.connect_ex(('127.0.0.1', self.tor_port))
                is_open = result == 0
                logging.debug(f"🔌 Проверка порта Tor {self.tor_port}: {'открыт' if is_open else 'закрыт'}")
                return is_open
        except Exception as e:
            logging.debug(f"⚠ Ошибка проверки порта Tor: {e}")
            return False

    def test_tor_connection(self) -> bool:
        """Простое тестирование соединения через Tor"""
        logging.info("🚀 ТЕСТИРОВАНИЕ TOR СОЕДИНЕНИЯ")
        
        try:
            import requests
            
            proxies = {
                'http': f'socks5://127.0.0.1:{self.tor_port}',
                'https': f'socks5://127.0.0.1:{self.tor_port}'
            }
            
            response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=30)
            
            if response.status_code == 200:
                content = response.text.strip()
                logging.info(f"✅ TOR РАБОТАЕТ! IP: {content}")
                return True
            else:
                logging.error(f"❌ Неверный статус код: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Ошибка тестирования Tor: {e}")
            return False

    def start_tor(self) -> bool:
        """Запуск Tor с ПРОСТОЙ конфигурацией БЕЗ мостов"""
        logging.info("🚀 ЗАПУСК TOR С ПРОСТОЙ КОНФИГУРАЦИЕЙ")
        
        try:
            # Полная очистка всех процессов Tor
            kill_existing_tor_processes()
            time.sleep(3)
            
            # Поиск Tor если не найден
            tor_executable = self.find_tor_executable()
            if not tor_executable:
                logging.info("⚠ Tor не найден, попытка установки...")
                if not self.install_tor():
                    logging.error("❌ Не удалось установить Tor")
                    return False
                tor_executable = self.find_tor_executable()
                if not tor_executable:
                    logging.error("❌ Tor все еще не найден после установки")
                    return False
            
            # Находим свободные порты
            free_ports = find_free_port_range(9050, 2)
            if len(free_ports) < 2:
                logging.error("❌ Не удалось найти 2 свободных порта")
                return False
            
            self.tor_port = free_ports[0]      # SOCKS порт
            self.control_port = free_ports[1]  # Control порт
            
            logging.info(f"🔌 Используем порты: SOCKS={self.tor_port}, Control={self.control_port}")
            
            # Создаем временную директорию для данных Tor
            import tempfile
            import getpass
            
            try:
                current_user = getpass.getuser()
            except:
                current_user = "user"
            
            temp_dir = tempfile.gettempdir()
            tor_data_dir = os.path.join(temp_dir, f"tor_data_{current_user}_{os.getpid()}")
            
            # Полностью удаляем старую директорию если существует
            if os.path.exists(tor_data_dir):
                shutil.rmtree(tor_data_dir, ignore_errors=True)
            
            # Создаем новую директорию
            os.makedirs(tor_data_dir, mode=0o700, exist_ok=True)
            
            logging.info(f"📁 Директория данных Tor: {tor_data_dir}")
            
            # ПРОСТАЯ конфигурация Tor БЕЗ мостов
            tor_config = f"""SocksPort {self.tor_port}
ControlPort {self.control_port}
DataDirectory {tor_data_dir}
Log notice stdout
"""
            
            # Записываем конфиг во временную директорию
            torrc_path = os.path.join(temp_dir, f"torrc_temp_{os.getpid()}")
            with open(torrc_path, "w") as f:
                f.write(tor_config)
            
            logging.debug(f"📄 Конфиг Tor сохранен в: {torrc_path}")
            logging.info("📄 Конфигурация Tor (ПРОСТАЯ, БЕЗ МОСТОВ):")
            logging.info(tor_config)
            
            # Запускаем Tor
            cmd = [tor_executable, "-f", torrc_path]
            
            logging.info(f"🚀 Команда запуска Tor: {' '.join(cmd)}")
            
            # Создаем файлы для логов
            stdout_log = os.path.join(temp_dir, f"tor_stdout_{os.getpid()}.log")
            stderr_log = os.path.join(temp_dir, f"tor_stderr_{os.getpid()}.log")
            
            with open(stdout_log, "w") as stdout_file, \
                 open(stderr_log, "w") as stderr_file:
                
                if self.system == 'windows':
                    self.tor_process = subprocess.Popen(
                        cmd,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    self.tor_process = subprocess.Popen(
                        cmd,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        preexec_fn=os.setsid
                    )
            
            # Сохраняем пути для очистки
            self.tor_data_dir = tor_data_dir
            self.torrc_path = torrc_path
            self.stdout_log = stdout_log
            self.stderr_log = stderr_log
            
            logging.info(f"🔄 PID процесса Tor: {self.tor_process.pid}")
            
            # Ждем запуска Tor
            logging.info("⏳ ОЖИДАНИЕ ЗАПУСКА TOR...")
            port_ready = False
            bootstrap_complete = False
            
            for i in range(60):  # 60 попыток по 2 секунды = 2 минуты
                time.sleep(2)
                
                # Проверяем что процесс еще жив
                if self.tor_process.poll() is not None:
                    logging.error(f"❌ Процесс Tor завершился с кодом {self.tor_process.poll()}")
                    self.log_tor_errors()
                    return False
                
                # Проверяем порт
                if not port_ready and self.check_tor_port():
                    logging.info("✅ Tor порт готов")
                    port_ready = True
                
                # Проверяем логи на предмет bootstrap
                if port_ready and not bootstrap_complete:
                    try:
                        if os.path.exists(stdout_log):
                            with open(stdout_log, "r") as f:
                                log_content = f.read()
                                if "Bootstrapped 100%" in log_content:
                                    logging.info("✅ Tor bootstrap завершен на 100%")
                                    bootstrap_complete = True
                                    break
                                elif "Bootstrapped" in log_content:
                                    # Показываем прогресс
                                    import re
                                    matches = re.findall(r'Bootstrapped (\d+)%', log_content)
                                    if matches:
                                        last_percent = matches[-1]
                                        logging.info(f"🔄 Tor bootstrap: {last_percent}%")
                    except:
                        pass
                
                # Показываем прогресс каждые 20 секунд
                if i % 10 == 0:  # Каждые 20 секунд
                    logging.info(f"⏳ Ожидание Tor... ({i*2}/120 секунд)")
            
            if not port_ready:
                logging.error("❌ Tor порт не запустился в течение отведенного времени")
                self.log_tor_errors()
                return False
            
            # Тестирование соединения
            logging.info("🔍 ТЕСТИРОВАНИЕ СОЕДИНЕНИЯ...")
            if self.test_tor_connection():
                logging.info("✅ TOR УСПЕШНО ЗАПУЩЕН И РАБОТАЕТ!")
                return True
            else:
                logging.error("❌ Tor запущен, но соединение не работает")
                self.log_tor_errors()
                return False
            
        except Exception as e:
            logging.error(f"❌ Ошибка запуска Tor: {e}")
            return False

    def log_tor_errors(self):
        """Вывод ошибок Tor из логов"""
        logging.info("📋 АНАЛИЗ ЛОГОВ TOR...")
        
        try:
            stderr_log = getattr(self, 'stderr_log', './tor_stderr.log')
            stdout_log = getattr(self, 'stdout_log', './tor_stdout.log')
            
            if stderr_log and os.path.exists(stderr_log):
                with open(stderr_log, "r") as f:
                    stderr_content = f.read().strip()
                    if stderr_content:
                        logging.error(f"🚨 ОШИБКИ TOR:\n{stderr_content}")
                    else:
                        logging.info("📝 Ошибки Tor отсутствуют")
            
            if stdout_log and os.path.exists(stdout_log):
                with open(stdout_log, "r") as f:
                    stdout_content = f.read().strip()
                    if stdout_content:
                        logging.info(f"📄 ВЫВОД TOR:\n{stdout_content}")
                        
                        # Анализ состояния
                        if "Bootstrapped 100%" in stdout_content:
                            logging.info("✅ Tor успешно загрузился на 100%")
                        elif "Bootstrapped" in stdout_content:
                            # Ищем последний процент загрузки
                            import re
                            matches = re.findall(r'Bootstrapped (\d+)%', stdout_content)
                            if matches:
                                last_percent = matches[-1]
                                logging.warning(f"⚠ Tor загружен только на {last_percent}%")
                        
                        if "Opening Socks listener" in stdout_content:
                            logging.info("✅ SOCKS прокси запущен")
                    else:
                        logging.warning("📝 Вывод Tor пуст")
                        
        except Exception as e:
            logging.debug(f"⚠ Ошибка чтения логов Tor: {e}")
    
    def stop_tor(self):
        """Остановка Tor"""
        try:
            if self.tor_process:
                logging.info("🛑 Остановка Tor...")
                
                if self.system == 'windows':
                    self.tor_process.terminate()
                else:
                    try:
                        os.killpg(os.getpgid(self.tor_process.pid), 15)  # SIGTERM
                    except:
                        self.tor_process.terminate()
                
                # Ждем завершения
                try:
                    self.tor_process.wait(timeout=5)
                    logging.info("✓ Tor остановлен корректно")
                except subprocess.TimeoutExpired:
                    logging.warning("⚠ Принудительное завершение Tor...")
                    if self.system == 'windows':
                        self.tor_process.kill()
                    else:
                        try:
                            os.killpg(os.getpgid(self.tor_process.pid), 9)  # SIGKILL
                        except:
                            self.tor_process.kill()
                    
                    self.tor_process.wait(timeout=3)
                    logging.info("✓ Tor принудительно остановлен")
                
                self.tor_process = None
                
            # Очистка временных файлов
            temp_files = [
                getattr(self, 'torrc_path', None),
                getattr(self, 'stdout_log', None),
                getattr(self, 'stderr_log', None)
            ]
            
            for temp_file in temp_files:
                try:
                    if temp_file and os.path.exists(temp_file):
                        os.remove(temp_file)
                        logging.debug(f"🗑 Удален файл: {temp_file}")
                except Exception as e:
                    logging.debug(f"⚠ Ошибка удаления {temp_file}: {e}")
            
            # Очистка директории данных
            tor_data_dir = getattr(self, 'tor_data_dir', None)
            try:
                if tor_data_dir and os.path.exists(tor_data_dir):
                    shutil.rmtree(tor_data_dir, ignore_errors=True)
                    logging.debug(f"🗑 Удалена директория: {tor_data_dir}")
            except Exception as e:
                logging.debug(f"⚠ Ошибка удаления директории {tor_data_dir}: {e}")
                    
        except Exception as e:
            logging.debug(f"⚠ Ошибка остановки Tor: {e}")

class AvisoAutomation:
    """Основной класс автоматизации Aviso"""
    
    def __init__(self):
        self.setup_logging()
        self.driver = None
        self.tor_manager = SimpleTorManager()  # УПРОЩЕННЫЙ Tor менеджер
        self.ua_manager = UserAgentManager()
        self.gecko_manager = GeckoDriverManager()
        self.cookies_file = "aviso_cookies.pkl"
        self.original_ip = None  # Сохраняем оригинальный IP
        self.use_tor = True  # Флаг использования Tor
        
        # ИСПРАВЛЕННЫЙ логин из системы
        self.username = "Aleksey345"
        self.password = "123456"
        self.base_url = "https://aviso.bz"
        
        logging.info("🚀 Инициализация Aviso Automation Bot")
        
    def setup_logging(self):
        """Настройка детального логирования"""
        # Создаем имя файла с текущей датой и временем
        log_filename = f"aviso_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # Настраиваем логирование
        log_format = "%(asctime)s [%(levelname)s] %(message)s"
        
        # Удаляем существующие обработчики
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Добавляем новые обработчики
        logging.basicConfig(
            level=logging.DEBUG,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_filename, encoding='utf-8')
            ]
        )
        
        logging.info(f"📝 Логирование настроено: {log_filename}")

    def get_current_ip_without_proxy(self) -> Optional[str]:
        """Получение ВНЕШНЕГО IP адреса БЕЗ прокси"""
        logging.info("🔍 ПОЛУЧЕНИЕ ВНЕШНЕГО IP БЕЗ ПРОКСИ...")
        
        test_services = [
            'https://api.ipify.org?format=text',
            'https://icanhazip.com/',
            'https://checkip.amazonaws.com/'
        ]
        
        for i, service in enumerate(test_services, 1):
            try:
                logging.info(f"🔍 Попытка {i}/{len(test_services)}: {service}")
                
                response = requests.get(service, timeout=10)
                response.raise_for_status()
                
                external_ip = response.text.strip()
                
                # Проверяем что IP валидный
                import re
                ip_pattern = r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$'
                if re.match(ip_pattern, external_ip):
                    logging.info(f"✅ Внешний IP получен: {external_ip}")
                    return external_ip
                else:
                    logging.warning(f"⚠ Неверный формат IP: {external_ip}")
                    continue
                    
            except requests.exceptions.Timeout:
                logging.warning(f"⚠ Таймаут для сервиса {service}")
                continue
            except Exception as e:
                logging.warning(f"⚠ Ошибка получения IP от {service}: {e}")
                continue
        
        logging.warning("⚠ Не удалось получить внешний IP, но продолжаем...")
        return None

    def find_firefox_binary(self) -> Optional[str]:
        """Поиск исполняемого файла Firefox"""
        possible_paths = []
        
        if self.tor_manager.is_termux:
            possible_paths = [
                '/data/data/com.termux/files/usr/bin/firefox',
                f"{os.environ.get('PREFIX', '')}/bin/firefox"
            ]
        elif self.tor_manager.system == 'linux':
            possible_paths = [
                '/usr/bin/firefox',
                '/usr/local/bin/firefox',
                '/opt/firefox/firefox',
                '/snap/bin/firefox'
            ]
        elif self.tor_manager.system == 'windows':
            possible_paths = [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
            ]
        elif self.tor_manager.system == 'darwin':
            possible_paths = [
                '/Applications/Firefox.app/Contents/MacOS/firefox'
            ]
        
        # Проверяем каждый путь
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logging.info(f"✓ Найден Firefox: {path}")
                return path
        
        # Проверяем через PATH
        if self.tor_manager.command_exists('firefox'):
            logging.info("✓ Firefox найден в PATH")
            return 'firefox'
        
        return None

    def setup_driver(self) -> bool:
        """Настройка и запуск Firefox с или без Tor"""
        logging.info("🌐 НАСТРОЙКА БРАУЗЕРА FIREFOX...")
        
        # Получаем ВНЕШНИЙ IP БЕЗ прокси
        logging.info("🔍 Получение внешнего IP адреса без прокси...")
        self.original_ip = self.get_current_ip_without_proxy()
        
        # Пытаемся запустить Tor
        logging.info("🔄 Попытка запуска Tor...")
        if self.tor_manager.start_tor():
            logging.info("✅ Tor запущен успешно! Используем Tor прокси.")
            self.use_tor = True
        else:
            logging.warning("⚠ Tor не удалось запустить. Работаем БЕЗ прокси.")
            self.use_tor = False
        
        try:
            # Получаем User-Agent для Firefox
            user_agent = self.ua_manager.get_user_agent(self.username)
            
            # Получаем путь к geckodriver
            logging.info("🔧 Настройка geckodriver...")
            geckodriver_path = self.gecko_manager.get_driver_path()
            logging.info(f"✓ Geckodriver: {geckodriver_path}")
            
            # Настройка Firefox
            firefox_options = Options()
            
            if self.use_tor:
                # Настройки прокси для Firefox с Tor
                logging.info(f"🔌 Настройка прокси Firefox: SOCKS5 127.0.0.1:{self.tor_manager.tor_port}")
                firefox_options.set_preference("network.proxy.type", 1)  # Ручная настройка прокси
                firefox_options.set_preference("network.proxy.socks", "127.0.0.1")
                firefox_options.set_preference("network.proxy.socks_port", self.tor_manager.tor_port)
                firefox_options.set_preference("network.proxy.socks_version", 5)
                firefox_options.set_preference("network.proxy.socks_remote_dns", True)  # DNS через Tor
                
                # Отключаем HTTP и HTTPS прокси (используем только SOCKS)
                firefox_options.set_preference("network.proxy.http", "")
                firefox_options.set_preference("network.proxy.http_port", 0)
                firefox_options.set_preference("network.proxy.ssl", "")
                firefox_options.set_preference("network.proxy.ssl_port", 0)
            else:
                logging.info("🌐 Настройка Firefox БЕЗ прокси")
                # Прямое соединение без прокси
                firefox_options.set_preference("network.proxy.type", 0)  # Без прокси
            
            # Общие настройки Firefox
            firefox_options.set_preference("general.useragent.override", user_agent)
            firefox_options.set_preference("dom.webdriver.enabled", False)
            firefox_options.set_preference("useAutomationExtension", False)
            firefox_options.set_preference("network.http.use-cache", False)
            
            # Отключаем WebRTC для предотвращения утечки IP
            firefox_options.set_preference("media.peerconnection.enabled", False)
            firefox_options.set_preference("media.navigator.enabled", False)
            
            # Настройки для лучшей приватности
            firefox_options.set_preference("privacy.resistFingerprinting", True)
            firefox_options.set_preference("privacy.trackingprotection.enabled", True)
            firefox_options.set_preference("geo.enabled", False)
            firefox_options.set_preference("browser.safebrowsing.downloads.remote.enabled", False)
            
            # Отключаем автообновления и телеметрию
            firefox_options.set_preference("app.update.enabled", False)
            firefox_options.set_preference("toolkit.telemetry.enabled", False)
            firefox_options.set_preference("datareporting.healthreport.uploadEnabled", False)
            
            # Для Termux
            if self.tor_manager.is_termux:
                firefox_options.add_argument("--no-sandbox")
                firefox_options.add_argument("--disable-dev-shm-usage")
            
            # Поиск Firefox
            firefox_binary = self.find_firefox_binary()
            if firefox_binary and firefox_binary != 'firefox':
                firefox_options.binary_location = firefox_binary
            
            logging.info("🚀 Запуск Firefox...")
            
            # Создание сервиса с указанным путем к geckodriver
            service = Service(executable_path=geckodriver_path)
            
            # Создание драйвера Firefox
            self.driver = webdriver.Firefox(options=firefox_options, service=service)
            
            # Таймауты
            self.driver.set_page_load_timeout(120)
            self.driver.implicitly_wait(20)
            
            logging.info("✅ Firefox запущен!")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка настройки Firefox: {e}")
            return False

    def save_cookies(self):
        """Сохранение cookies"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            logging.info(f"💾 Cookies сохранены в {self.cookies_file}")
        except Exception as e:
            logging.error(f"✗ Ошибка сохранения cookies: {e}")
    
    def load_cookies(self) -> bool:
        """Загрузка cookies"""
        try:
            if os.path.exists(self.cookies_file):
                self.driver.get(self.base_url)
                HumanBehaviorSimulator.random_sleep(2, 4)
                
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)
                
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        logging.debug(f"⚠ Ошибка добавления cookie: {e}")
                
                logging.info("✓ Cookies загружены")
                return True
        except Exception as e:
            logging.error(f"✗ Ошибка загрузки cookies: {e}")
        
        return False
    
    def check_authorization(self) -> bool:
        """Простая проверка авторизации"""
        try:
            # Просто проверяем есть ли форма логина на ТЕКУЩЕЙ странице
            login_forms = self.driver.find_elements(By.NAME, "username")
            if login_forms:
                logging.info("🔐 Требуется авторизация")
                return False
            else:
                logging.info("✓ Пользователь авторизован")
                return True
                
        except Exception as e:
            logging.error(f"✗ Ошибка проверки авторизации: {e}")
            return False
    
    def login(self) -> bool:
        """Авторизация"""
        logging.info("🔐 НАЧАЛО АВТОРИЗАЦИИ...")
        
        try:
            # Переход на страницу логина
            logging.info("🌐 Переход на страницу логина...")
            self.driver.get(f"{self.base_url}/login")
            HumanBehaviorSimulator.random_sleep(3, 8)
            
            wait = WebDriverWait(self.driver, 30)
            
            # Ввод логина с улучшенной имитацией
            logging.info("🔍 Поиск поля логина...")
            username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            ActionChains(self.driver).move_to_element(username_field).click().perform()
            HumanBehaviorSimulator.human_like_typing(username_field, self.username, self.driver)
            logging.info(f"✓ Логин '{self.username}' введен")
            
            # Ввод пароля с улучшенной имитацией
            password_field = self.driver.find_element(By.NAME, "password")
            ActionChains(self.driver).move_to_element(password_field).click().perform()
            HumanBehaviorSimulator.human_like_typing(password_field, self.password, self.driver)
            logging.info("✓ Пароль введен")
            
            # Нажатие кнопки входа
            login_button = self.driver.find_element(By.ID, "button-login")
            HumanBehaviorSimulator.random_sleep(1, 4)
            ActionChains(self.driver).move_to_element(login_button).click().perform()
            logging.info("✓ Кнопка входа нажата")
            
            # Ждем для возможных переадресаций
            HumanBehaviorSimulator.random_sleep(5, 12)
            
            # Проверяем 2FA ТОЛЬКО если мы на странице 2FA
            current_url = self.driver.current_url
            if "/2fa" in current_url:
                logging.info("🔐 Обнаружена страница 2FA")
                
                try:
                    code_field = wait.until(EC.presence_of_element_located((By.NAME, "code")))
                    
                    print("\n" + "="*50)
                    print("🔐 ТРЕБУЕТСЯ КОД ПОДТВЕРЖДЕНИЯ")
                    print("📧 Проверьте почту и введите код")
                    print("="*50)
                    
                    verification_code = input("Введите код: ").strip()
                    
                    if verification_code and verification_code.isdigit():
                        ActionChains(self.driver).move_to_element(code_field).click().perform()
                        HumanBehaviorSimulator.human_like_typing(code_field, verification_code, self.driver)
                        
                        # Нажатие кнопки подтверждения
                        confirm_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.button_theme_blue")
                        if confirm_buttons:
                            ActionChains(self.driver).move_to_element(confirm_buttons[0]).click().perform()
                            logging.info("✓ Код подтверждения отправлен")
                        
                        # Ждем после 2FA
                        HumanBehaviorSimulator.random_sleep(5, 12)
                    
                except Exception as e:
                    logging.error(f"❌ Ошибка обработки 2FA: {e}")
                    return False
            
            # Простая проверка результата - есть ли форма логина
            login_forms = self.driver.find_elements(By.NAME, "username")
            if not login_forms:
                logging.info("✅ Авторизация успешна!")
                self.save_cookies()
                return True
            else:
                logging.error("❌ Авторизация не удалась")
                return False
                
        except Exception as e:
            logging.error(f"❌ Ошибка авторизации: {e}")
            return False
    
    def random_mouse_movement(self):
        """Случайные движения мыши"""
        try:
            viewport_size = self.driver.get_window_size()
            
            current_position = (
                random.randint(50, viewport_size['width'] - 50),
                random.randint(50, viewport_size['height'] - 50)
            )
            
            new_position = (
                random.randint(50, viewport_size['width'] - 50),
                random.randint(50, viewport_size['height'] - 50)
            )
            
            curve_points = HumanBehaviorSimulator.generate_bezier_curve(
                current_position, new_position
            )
            
            actions = ActionChains(self.driver)
            for i, point in enumerate(curve_points):
                if i == 0:
                    continue
                    
                prev_point = curve_points[i-1]
                offset_x = point[0] - prev_point[0]
                offset_y = point[1] - prev_point[1]
                
                actions.move_by_offset(offset_x, offset_y)
                time.sleep(random.uniform(0.01, 0.05))
            
            actions.perform()
            logging.debug(f"🖱 Движение мыши: {current_position} → {new_position}")
            
        except Exception as e:
            logging.debug(f"⚠ Ошибка движения мыши: {e}")
    
    def random_scroll(self):
        """Случайная прокрутка страницы"""
        try:
            scroll_direction = random.choice(['up', 'down'])
            scroll_amount = random.randint(100, 500)
            
            if scroll_direction == 'down':
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                logging.debug(f"📜 Прокрутка вниз: {scroll_amount}px")
            else:
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
                logging.debug(f"📜 Прокрутка вверх: {scroll_amount}px")
            
            HumanBehaviorSimulator.random_sleep(0.5, 2.0)
            
        except Exception as e:
            logging.debug(f"⚠ Ошибка прокрутки: {e}")
    
    def get_youtube_tasks(self) -> List[Dict]:
        """Получение списка заданий YouTube"""
        logging.info("📋 Поиск заданий YouTube...")
        
        try:
            # Переход на страницу заданий
            logging.info("🌐 Переход на страницу заданий YouTube...")
            self.driver.get(f"{self.base_url}/tasks-youtube")
            HumanBehaviorSimulator.random_sleep(3, 8)
            
            # Имитация чтения страницы
            for _ in range(random.randint(2, 4)):
                self.random_scroll()
                HumanBehaviorSimulator.random_sleep(1, 4)
                self.random_mouse_movement()
            
            # Поиск всех заданий
            task_rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[class^='ads_']")
            tasks = []
            
            for i, row in enumerate(task_rows):
                try:
                    # Извлечение ID задания
                    class_name = row.get_attribute('class')
                    task_id_match = re.search(r'ads_(\d+)', class_name)
                    if not task_id_match:
                        continue
                    
                    task_id = task_id_match.group(1)
                    
                    # Поиск кнопки "Посмотреть видео"
                    start_button = row.find_element(
                        By.CSS_SELECTOR, 
                        f"span[id='link_ads_start_{task_id}']"
                    )
                    
                    # Извлечение времени просмотра из onclick
                    onclick_attr = start_button.get_attribute('onclick')
                    time_match = re.search(r"start_youtube_new\(\d+,\s*'(\d+)'\)", onclick_attr)
                    watch_time = int(time_match.group(1)) if time_match else 10
                    
                    # Извлечение URL видео
                    video_url = start_button.get_attribute('title') or "unknown"
                    
                    task_info = {
                        'id': task_id,
                        'element': start_button,
                        'watch_time': watch_time,
                        'video_url': video_url,
                        'row': row
                    }
                    
                    tasks.append(task_info)
                    logging.info(f"✓ Найдено задание {task_id}: {watch_time}с, {video_url}")
                    
                    # Имитация чтения задания
                    if random.random() < 0.3:  # 30% вероятность
                        ActionChains(self.driver).move_to_element(row).perform()
                        HumanBehaviorSimulator.random_sleep(1, 3)
                
                except Exception as e:
                    logging.debug(f"⚠ Ошибка обработки задания {i}: {e}")
                    continue
            
            logging.info(f"📊 Найдено заданий: {len(tasks)}")
            return tasks
            
        except Exception as e:
            logging.error(f"❌ Ошибка получения заданий: {e}")
            return []
    
    def wait_for_element(self, by: By, value: str, timeout: int = 20) -> Optional[object]:
        """Ожидание появления элемента"""
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located((by, value)))
            logging.debug(f"✓ Элемент найден: {value}")
            return element
        except TimeoutException:
            logging.debug(f"⏰ Элемент не найден в течение {timeout}с: {value}")
            return None
        except Exception as e:
            logging.debug(f"⚠ Ошибка ожидания элемента {value}: {e}")
            return None
    
    def handle_youtube_ads(self) -> bool:
        """Обработка рекламы на YouTube"""
        logging.info("📺 Проверка рекламы на YouTube...")
        
        try:
            # Ожидание загрузки страницы
            HumanBehaviorSimulator.random_sleep(3, 8)
            
            # Проверка наличия рекламы
            ad_indicators = [
                "ytp-ad-badge",
                "[id*='ad-badge']",
                ".ytp-ad-text",
                "[aria-label*='реклама']",
                "[aria-label*='Реклама']",
                "[aria-label*='Ad']",
                "[aria-label*='advertisement']"
            ]
            
            ad_found = False
            for selector in ad_indicators:
                try:
                    ad_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if ad_elements and any(el.is_displayed() for el in ad_elements):
                        ad_found = True
                        logging.info("📺 Обнаружена реклама")
                        break
                except:
                    continue
            
            if ad_found:
                # Ожидание кнопки пропуска или автозапуска
                skip_found = False
                auto_start_found = False
                
                for attempt in range(45):
                    # Проверка кнопки пропуска
                    skip_selectors = [
                        ".ytp-ad-skip-button",
                        ".ytp-ad-skip-button-modern",
                        "[class*='skip']",
                        "button[class*='skip']"
                    ]
                    
                    for selector in skip_selectors:
                        try:
                            skip_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for button in skip_buttons:
                                if button.is_displayed() and button.is_enabled():
                                    logging.info("⏭ Нажатие кнопки пропуска рекламы")
                                    ActionChains(self.driver).move_to_element(button).click().perform()
                                    skip_found = True
                                    HumanBehaviorSimulator.random_sleep(2, 5)
                                    break
                            if skip_found:
                                break
                        except:
                            continue
                    
                    if skip_found:
                        break
                    
                    # Проверка автозапуска видео (появление таймера)
                    timer_selectors = [
                        ".ytwPlayerTimeDisplayTime",
                        "[class*='time-display']",
                        ".ytp-time-current"
                    ]
                    
                    for selector in timer_selectors:
                        try:
                            timers = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            if timers and any(t.is_displayed() and t.text.strip() for t in timers):
                                logging.info("⏰ Видео запустилось автоматически")
                                auto_start_found = True
                                break
                        except:
                            continue
                    
                    if auto_start_found:
                        break
                    
                    # Случайные движения во время ожидания
                    if random.random() < 0.3:
                        self.random_mouse_movement()
                    
                    time.sleep(1)
                
                if not skip_found and not auto_start_found:
                    logging.warning("⚠ Реклама не обработана корректно")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка обработки рекламы: {e}")
            return False
    
    def wait_for_video_time(self, required_seconds: int) -> bool:
        """Ожидание достижения требуемого времени просмотра"""
        logging.info(f"⏱ ОЖИДАНИЕ {required_seconds} СЕКУНД ПРОСМОТРА...")
        
        try:
            last_time = 0
            pause_counter = 0
            no_timer_counter = 0
            start_wait_time = time.time()
            max_wait_time = required_seconds + 90
            
            while True:
                current_wait_time = time.time() - start_wait_time
                
                # Проверка максимального времени ожидания
                if current_wait_time > max_wait_time:
                    logging.warning(f"⏰ Превышено максимальное время ожидания ({max_wait_time}с)")
                    return True  # Считаем что время достигнуто
                
                # Поиск элементов таймера
                timer_selectors = [
                    ".ytwPlayerTimeDisplayTime",
                    "[class*='time-display']",
                    ".ytp-time-current",
                    "[role='text'][aria-label*='Продолжительность']"
                ]
                
                current_time_seconds = 0
                timer_found = False
                
                for selector in timer_selectors:
                    try:
                        timers = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for timer in timers:
                            if timer.is_displayed():
                                timer_text = timer.text.strip()
                                if ':' in timer_text:
                                    try:
                                        # Парсинг времени (mm:ss или hh:mm:ss)
                                        time_parts = timer_text.split(':')
                                        if len(time_parts) == 2:  # mm:ss
                                            minutes, seconds = map(int, time_parts)
                                            current_time_seconds = minutes * 60 + seconds
                                        elif len(time_parts) == 3:  # hh:mm:ss
                                            hours, minutes, seconds = map(int, time_parts)
                                            current_time_seconds = hours * 3600 + minutes * 60 + seconds
                                        
                                        timer_found = True
                                        no_timer_counter = 0
                                        break
                                    except (ValueError, IndexError):
                                        continue
                        
                        if timer_found:
                            break
                    except:
                        continue
                
                if timer_found:
                    logging.debug(f"⏰ Текущее время: {current_time_seconds}с (требуется: {required_seconds}с)")
                    
                    # Проверка на паузу
                    if current_time_seconds == last_time:
                        pause_counter += 1
                        if pause_counter >= 5:  # 5 секунд без изменений
                            logging.info("⏸ Видео на паузе, попытка запуска...")
                            self.try_play_video()
                            pause_counter = 0
                    else:
                        pause_counter = 0
                    
                    last_time = current_time_seconds
                    
                    # Проверка достижения требуемого времени
                    if current_time_seconds >= required_seconds:
                        logging.info(f"✅ Достигнуто время просмотра: {current_time_seconds}с")
                        return True
                else:
                    no_timer_counter += 1
                    logging.debug(f"⚠ Таймер не найден (попытка {no_timer_counter})")
                    
                    # Если долго нет таймера, пробуем запустить видео
                    if no_timer_counter >= 8:
                        logging.info("🎬 Попытка запуска видео (таймер не найден)")
                        self.try_play_video()
                        no_timer_counter = 0
                
                # Случайные действия во время просмотра
                if random.random() < 0.1:  # 10% вероятность
                    self.random_mouse_movement()
                
                if random.random() < 0.05:  # 5% вероятность
                    self.random_scroll()
                
                time.sleep(1)
            
        except Exception as e:
            logging.error(f"❌ Ошибка ожидания времени: {e}")
            return False
    
    def try_play_video(self):
        """Попытка запуска видео если оно на паузе"""
        try:
            # Поиск кнопки play
            play_selectors = [
                ".yt-icon-shape svg[viewBox*='24']",
                "button[title*='воспроизвести']",
                "button[title*='Play']",
                ".ytp-play-button",
                "[aria-label*='воспроизведение']",
                "[aria-label*='Play']"
            ]
            
            for selector in play_selectors:
                try:
                    play_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in play_buttons:
                        if button.is_displayed():
                            try:
                                # Проверяем, что это именно кнопка play (треугольник)
                                svg_path = button.find_elements(By.TAG_NAME, "path")
                                for path in svg_path:
                                    path_d = path.get_attribute("d")
                                    if path_d and ("m7 4 12 8-12 8V4z" in path_d or "M8 5v14l11-7z" in path_d):
                                        logging.info("▶ Нажатие кнопки воспроизведения")
                                        ActionChains(self.driver).move_to_element(button).click().perform()
                                        HumanBehaviorSimulator.random_sleep(1, 3)
                                        return
                            except:
                                continue
                except:
                    continue
            
            # Если кнопка не найдена, пробуем кликнуть по видео
            try:
                video_elements = self.driver.find_elements(By.TAG_NAME, "video")
                if video_elements:
                    video = video_elements[0]
                    if video.is_displayed():
                        logging.info("🎬 Клик по видео для запуска")
                        ActionChains(self.driver).move_to_element(video).click().perform()
                        HumanBehaviorSimulator.random_sleep(1, 3)
            except:
                pass
            
        except Exception as e:
            logging.debug(f"⚠ Ошибка запуска видео: {e}")
    
    def execute_youtube_task(self, task: Dict) -> bool:
        """Выполнение одного задания YouTube"""
        task_id = task['id']
        watch_time = task['watch_time']
        video_url = task['video_url']
        
        logging.info(f"🎯 Выполнение задания {task_id}: {watch_time}с")
        
        original_window = self.driver.current_window_handle
        
        try:
            # Прокрутка к заданию
            ActionChains(self.driver).move_to_element(task['row']).perform()
            HumanBehaviorSimulator.random_sleep(1, 4)
            
            # Случайная пауза перед кликом
            random_delay = random.uniform(2, 15)
            logging.info(f"⏳ Случайная пауза {random_delay:.1f}с перед выполнением")
            time.sleep(random_delay)
            
            # Клик по кнопке "Посмотреть видео"
            start_button = task['element']
            
            # Движение к кнопке по кривой
            try:
                viewport_size = self.driver.get_window_size()
                current_pos = (viewport_size['width'] // 2, viewport_size['height'] // 2)
                button_rect = start_button.rect
                target_pos = (
                    button_rect['x'] + button_rect['width'] // 2,
                    button_rect['y'] + button_rect['height'] // 2
                )
                
                curve_points = HumanBehaviorSimulator.generate_bezier_curve(current_pos, target_pos)
                actions = ActionChains(self.driver)
                
                for i, point in enumerate(curve_points[1:], 1):  # Пропускаем первую точку
                    prev_point = curve_points[i-1]
                    offset_x = point[0] - prev_point[0]
                    offset_y = point[1] - prev_point[1]
                    actions.move_by_offset(offset_x, offset_y)
                    time.sleep(random.uniform(0.01, 0.03))
                
                actions.click(start_button).perform()
            except Exception as e:
                logging.debug(f"⚠ Ошибка движения мыши, обычный клик: {e}")
                ActionChains(self.driver).move_to_element(start_button).click().perform()
            
            logging.info(f"🖱 Клик по заданию {task_id}")
            
            # Ожидание открытия YouTube
            HumanBehaviorSimulator.random_sleep(5, 12)
            
            # Переключение на новую вкладку YouTube
            all_windows = self.driver.window_handles
            
            youtube_window = None
            for window in all_windows:
                if window != original_window:
                    self.driver.switch_to.window(window)
                    if "youtube.com" in self.driver.current_url.lower():
                        youtube_window = window
                        break
            
            if not youtube_window:
                logging.error("❌ Не удалось найти вкладку YouTube")
                return False
            
            logging.info("📺 Переключение на вкладку YouTube")
            
            # Обработка рекламы
            self.handle_youtube_ads()
            
            # Ожидание требуемого времени просмотра
            if self.wait_for_video_time(watch_time):
                # Дополнительная случайная пауза
                extra_delay = random.uniform(3, 30)
                logging.info(f"⏳ Дополнительная пауза {extra_delay:.1f}с")
                
                # Случайные действия во время паузы
                for _ in range(int(extra_delay // 4)):
                    self.random_mouse_movement()
                    time.sleep(random.uniform(2, 4))
                
                # Возврат на исходную вкладку
                self.driver.close()  # Закрываем YouTube
                self.driver.switch_to.window(original_window)
                logging.info("🔙 Возврат на страницу заданий")
                
                HumanBehaviorSimulator.random_sleep(3, 8)
                
                # Поиск и нажатие кнопки подтверждения
                confirm_button_id = f"ads_btn_confirm_{task_id}"
                confirm_button = self.wait_for_element(By.ID, confirm_button_id, 20)
                
                if confirm_button and confirm_button.is_displayed():
                    ActionChains(self.driver).move_to_element(confirm_button).click().perform()
                    logging.info(f"✅ Подтверждение просмотра задания {task_id}")
                    HumanBehaviorSimulator.random_sleep(3, 8)
                    return True
                else:
                    logging.error(f"❌ Кнопка подтверждения не найдена для задания {task_id}")
                    return False
            else:
                logging.error(f"❌ Не удалось дождаться времени просмотра для задания {task_id}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Ошибка выполнения задания {task_id}: {e}")
            
            # Попытка вернуться на исходную вкладку
            try:
                all_windows = self.driver.window_handles
                if len(all_windows) > 1:
                    for window in all_windows:
                        if window != original_window:
                            self.driver.switch_to.window(window)
                            self.driver.close()
                    self.driver.switch_to.window(original_window)
                else:
                    self.driver.switch_to.window(original_window)
            except Exception as cleanup_error:
                logging.debug(f"⚠ Ошибка очистки окон: {cleanup_error}")
            
            return False
    
    def execute_all_tasks(self) -> int:
        """Выполнение всех доступных заданий"""
        logging.info("🚀 Начало выполнения всех заданий...")
        
        tasks = self.get_youtube_tasks()
        if not tasks:
            logging.info("📭 Нет доступных заданий")
            return 0
        
        completed_tasks = 0
        
        # Перемешиваем задания для случайности
        random.shuffle(tasks)
        
        for i, task in enumerate(tasks):
            logging.info(f"📝 Задание {i+1}/{len(tasks)}")
            
            try:
                if self.execute_youtube_task(task):
                    completed_tasks += 1
                    logging.info(f"✅ Задание {task['id']} выполнено ({completed_tasks}/{len(tasks)})")
                else:
                    logging.warning(f"⚠ Задание {task['id']} не выполнено")
                
                # Пауза между заданиями
                if i < len(tasks) - 1:  # Не делаем паузу после последнего задания
                    pause_time = random.uniform(45, 120)
                    logging.info(f"⏳ Пауза между заданиями: {pause_time:.1f}с")
                    
                    # Случайные действия во время паузы
                    for _ in range(int(pause_time // 12)):
                        if random.random() < 0.5:
                            self.random_mouse_movement()
                        if random.random() < 0.3:
                            self.random_scroll()
                        time.sleep(random.uniform(10, 15))
                
            except Exception as e:
                logging.error(f"❌ Критическая ошибка при выполнении задания {task['id']}: {e}")
                continue
        
        logging.info(f"🏁 Завершено выполнение заданий: {completed_tasks}/{len(tasks)}")
        return completed_tasks
    
    def cleanup(self):
        """Очистка ресурсов"""
        try:
            if self.driver:
                self.driver.quit()
                logging.info("🚪 Браузер закрыт")
        except Exception as e:
            logging.debug(f"⚠ Ошибка закрытия браузера: {e}")
        
        try:
            if self.use_tor:
                self.tor_manager.stop_tor()
        except Exception as e:
            logging.debug(f"⚠ Ошибка остановки Tor: {e}")
    
    def run_cycle(self) -> bool:
        """Выполнение одного цикла работы"""
        logging.info("🔄 НАЧАЛО ЦИКЛА ВЫПОЛНЕНИЯ ЗАДАНИЙ")
        
        try:
            # Настройка браузера
            if not self.setup_driver():
                logging.error("❌ Не удалось настроить браузер")
                return False
            
            # Попытка использовать сохраненные cookies
            cookies_loaded = self.load_cookies()
            
            # Проверка авторизации
            if not cookies_loaded or not self.check_authorization():
                # Требуется авторизация
                if not self.login():
                    logging.error("❌ Не удалось авторизоваться")
                    return False
            
            # Выполнение заданий
            completed_tasks = self.execute_all_tasks()
            
            if completed_tasks > 0:
                logging.info(f"✅ Цикл завершен успешно: выполнено {completed_tasks} заданий")
            else:
                logging.info("ℹ Цикл завершен: нет заданий для выполнения")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка в цикле выполнения: {e}")
            return False
        finally:
            self.cleanup()
    
    def run(self):
        """Основной цикл работы бота"""
        logging.info("🤖 ЗАПУСК AVISO AUTOMATION BOT - ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ")
        
        cycle_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        try:
            while True:
                cycle_count += 1
                logging.info(f"🔄 ЦИКЛ #{cycle_count}")
                
                # Выполнение цикла
                success = self.run_cycle()
                
                if success:
                    consecutive_failures = 0
                    
                    # Случайная пауза между циклами (1 минута - 2 часа)
                    pause_minutes = random.uniform(1, 120)
                    pause_seconds = pause_minutes * 60
                    
                    next_run_time = datetime.now() + timedelta(seconds=pause_seconds)
                    
                    logging.info(f"😴 Пауза до следующего цикла: {pause_minutes:.1f} минут")
                    logging.info(f"⏰ Следующий запуск: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # Разбиваем паузу на части для возможности прерывания
                    pause_intervals = max(1, int(pause_seconds // 60))  # Проверяем каждую минуту
                    interval_duration = pause_seconds / pause_intervals
                    
                    for i in range(pause_intervals):
                        time.sleep(interval_duration)
                        remaining_minutes = pause_minutes - ((i + 1) * interval_duration / 60)
                        if remaining_minutes > 1:
                            logging.debug(f"⏳ Осталось до следующего цикла: {remaining_minutes:.1f} минут")
                else:
                    consecutive_failures += 1
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logging.error(f"💥 Слишком много неудачных попыток подряд ({consecutive_failures})")
                        logging.error("❌ КРИТИЧЕСКАЯ ОШИБКА - ОСТАНОВКА РАБОТЫ")
                        break
                    else:
                        # При ошибке пауза короче
                        pause_minutes = random.uniform(5, 15)
                    
                    logging.warning(f"⚠ Ошибка в цикле #{cycle_count}, пауза {pause_minutes:.1f} минут")
                    time.sleep(pause_minutes * 60)
        
        except KeyboardInterrupt:
            logging.info("🛑 Получен сигнал остановки (Ctrl+C)")
        except Exception as e:
            logging.error(f"💥 Критическая ошибка в главном цикле: {e}")
        finally:
            self.cleanup()
            logging.info("👋 Работа бота завершена")

def main():
    """Точка входа в программу"""
    print("🤖 Aviso YouTube Tasks Automation Bot - ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ")
    print("=" * 80)
    print("🚀 Автоматический запуск...")
    print("⚠  ВНИМАНИЕ: Используйте бота ответственно!")
    print("🔧 ФИНАЛЬНЫЕ ИСПРАВЛЕНИЯ:")
    print("   ✅ УБРАНЫ ВСЕ МОСТЫ TOR - только прямое соединение")
    print("   ✅ Упрощена конфигурация Tor до минимума")
    print("   ✅ Fallback режим: работа БЕЗ Tor если не запускается")
    print("   ✅ Полная очистка процессов перед запуском")
    print("   ✅ Исправлена логика поиска свободных портов")
    print("   ✅ Детальное логирование конфигурации Tor")
    print("📋 Функции:")
    print("   - Автоматическая авторизация на aviso.bz")
    print("   - Выполнение заданий по просмотру YouTube")
    print("   - Имитация человеческого поведения")
    print("   - Работа через Tor прокси ИЛИ БЕЗ прокси (fallback)")
    print("   - Автоматическая установка geckodriver")
    print("   - Фиксированный User-Agent для аккаунта")
    print("   - Улучшенная имитация опечаток при вводе")
    print("   - Улучшенная поддержка Termux/Android")
    print("   - ПРОСТОЕ И НАДЕЖНОЕ логирование")
    print("=" * 80)
    print()
    
    # Создание и запуск бота без подтверждения
    bot = AvisoAutomation()
    
    try:
        bot.run()
    except Exception as e:
        logging.error(f"💥 Критическая ошибка при запуске: {e}")
        print(f"\n❌ Критическая ошибка: {e}")
        print("📋 Проверьте логи для подробной информации")
        sys.exit(1)
    finally:
        print("\n👋 До свидания!")

if __name__ == "__main__":
    main()