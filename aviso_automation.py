#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aviso YouTube Tasks Automation Script - ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ
ИСПРАВЛЕНИЯ:
- Убраны ВСЕ мосты Tor - только прямое соединение
- Упрощена конфигурация Tor
- Добавлен fallback без Tor если не работает
- ТОЧЕЧНЫЕ ИСПРАВЛЕНИЯ:
- Увеличен таймаут Tor до 20 минут
- Убраны проверки URL вкладок
- Исправлены координаты мыши
- ВОССТАНОВЛЕНА оригинальная логика авторизации
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
    """Класс для управления User-Agent для каждого аккаунта - ТОЛЬКО ANDROID И IPAD"""
    
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
    
    def generate_android_user_agent(self) -> str:
        """Генерация рандомного Android User-Agent"""
        # Рандомные версии Android
        android_versions = [
            "10", "11", "12", "13", "14", "15"
        ]
        
        # Рандомные модели Android устройств
        android_devices = [
            "SM-G991B", "SM-G996B", "SM-G998B",  # Samsung Galaxy S21 серия
            "SM-A515F", "SM-A525F", "SM-A536B",  # Samsung Galaxy A серия
            "Pixel 6", "Pixel 7", "Pixel 8", "Pixel 9",  # Google Pixel
            "CPH2451", "CPH2455", "CPH2459",  # OnePlus
            "M2101K9G", "M2102K1AC", "M2103K19G",  # Xiaomi
            "RMX3085", "RMX3241", "RMX3506",  # Realme
            "LM-G900", "LM-V600", "LM-K520",  # LG
        ]
        
        # Рандомные версии Chrome Mobile
        chrome_versions = [
            "119.0.6045.193", "120.0.6099.144", "121.0.6167.165",
            "122.0.6261.105", "123.0.6312.118", "124.0.6367.207",
            "125.0.6422.165", "126.0.6478.122", "127.0.6533.107"
        ]
        
        android_version = random.choice(android_versions)
        device_model = random.choice(android_devices)
        chrome_version = random.choice(chrome_versions)
        webkit_version = f"{random.randint(530, 537)}.{random.randint(1, 36)}"
        
        user_agent = (
            f"Mozilla/5.0 (Linux; Android {android_version}; {device_model}) "
            f"AppleWebKit/{webkit_version} (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Mobile Safari/{webkit_version}"
        )
        
        return user_agent
    
    def generate_ipad_user_agent(self) -> str:
        """Генерация рандомного iPad User-Agent"""
        # Рандомные версии iOS для iPad
        ios_versions = [
            "15_7", "16_1", "16_2", "16_3", "16_4", "16_5", "16_6", "16_7",
            "17_0", "17_1", "17_2", "17_3", "17_4", "17_5", "17_6",
            "18_0", "18_1", "18_2"
        ]
        
        # Рандомные модели iPad
        ipad_models = [
            "iPad13,1", "iPad13,2",  # iPad Air 4th gen
            "iPad13,4", "iPad13,5", "iPad13,6", "iPad13,7",  # iPad Pro 11" 5th gen
            "iPad13,8", "iPad13,9", "iPad13,10", "iPad13,11",  # iPad Pro 12.9" 5th gen
            "iPad14,1", "iPad14,2",  # iPad mini 6th gen
            "iPad14,3", "iPad14,4",  # iPad Air 5th gen
            "iPad14,5", "iPad14,6",  # iPad Pro 11" 6th gen
            "iPad16,3", "iPad16,4", "iPad16,5", "iPad16,6",  # iPad Pro M4
        ]
        
        # Рандомные версии Safari
        safari_versions = [
            "604.1", "605.1.15", "612.1.6", "613.2.7", "614.1.25",
            "615.1.26", "616.1.27", "617.2.4", "618.1.15"
        ]
        
        ios_version = random.choice(ios_versions)
        ipad_model = random.choice(ipad_models)
        safari_version = random.choice(safari_versions)
        webkit_version = f"{random.randint(612, 618)}.{random.randint(1, 5)}.{random.randint(1, 30)}"
        
        user_agent = (
            f"Mozilla/5.0 ({ipad_model}; U; CPU OS {ios_version} like Mac OS X) "
            f"AppleWebKit/{webkit_version} (KHTML, like Gecko) "
            f"Version/{safari_version} Mobile/15E148 Safari/{safari_version}"
        )
        
        return user_agent
    
    def get_user_agent(self, username: str) -> str:
        """Получение User-Agent для конкретного пользователя - ТОЛЬКО ANDROID ИЛИ IPAD"""
        # Создаем уникальный ключ для пользователя
        user_key = hashlib.md5(username.encode()).hexdigest()
        
        if user_key not in self.user_agents:
            # Рандомно выбираем между Android и iPad (50/50)
            device_type = random.choice(['android', 'ipad'])
            
            if device_type == 'android':
                mobile_ua = self.generate_android_user_agent()
                device_name = "Android"
            else:
                mobile_ua = self.generate_ipad_user_agent()
                device_name = "iPad"
            
            self.user_agents[user_key] = mobile_ua
            self.save_user_agents()
            logging.info(f"🎭 Создан новый {device_name} User-Agent для пользователя {username}")
        
        user_agent = self.user_agents[user_key]
        device_type = "Android" if "Android" in user_agent else "iPad"
        logging.info(f"🎭 Используется {device_type} User-Agent для {username}: {user_agent[:50]}...")
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
            
            # ИСПРАВЛЕНО: Ждем запуска Tor - УВЕЛИЧЕН ТАЙМАУТ ДО 20 МИНУТ
            logging.info("⏳ ОЖИДАНИЕ ЗАПУСКА TOR (до 20 минут)...")
            port_ready = False
            bootstrap_complete = False
            
            for i in range(600):  # 600 попыток по 2 секунды = 20 минут (было 60)
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
                
                # Показываем прогресс каждые 60 секунд (было 20)
                if i % 30 == 0:  # Каждые 60 секунд
                    elapsed_minutes = (i * 2) / 60
                    logging.info(f"⏳ Ожидание Tor... ({elapsed_minutes:.1f}/20 минут)")
            
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
        self.tor_manager = SimpleTorManager()
        self.ua_manager = UserAgentManager()
        self.gecko_manager = GeckoDriverManager()
        self.cookies_file = "aviso_cookies.pkl"
        self.original_ip = None
        self.use_tor = True
        
        # Данные для авторизации
        self.username = "Aleksey83692"
        self.password = "123456"
        self.base_url = "https://aviso.bz"
        
        logging.info("🚀 Запуск Aviso Bot")
        
    def setup_logging(self):
        """Настройка логирования"""
        log_filename = f"aviso_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_format = "%(asctime)s [%(levelname)s] %(message)s"
        
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_filename, encoding='utf-8')
            ]
        )

    def get_current_ip_without_proxy(self) -> Optional[str]:
        """Получение внешнего IP без прокси"""
        test_services = [
            'https://api.ipify.org?format=text',
            'https://icanhazip.com/',
            'https://checkip.amazonaws.com/'
        ]
        
        for service in test_services:
            try:
                response = requests.get(service, timeout=10)
                response.raise_for_status()
                external_ip = response.text.strip()
                
                import re
                if re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', external_ip):
                    return external_ip
            except:
                continue
        
        return None

    def verify_ip_change_via_2ip(self) -> bool:
        """Проверка смены IP через 2ip.ru"""
        try:
            self.driver.get("https://2ip.ru")
            time.sleep(5)
            
            ip_element = self.driver.find_element(By.CSS_SELECTOR, "div.ip span")
            current_ip = ip_element.text.strip()
            
            logging.info(f"🔍 IP: {current_ip}")
            
            if self.original_ip and current_ip == self.original_ip:
                logging.error("❌ IP не сменился! Tor не работает!")
                return False
            else:
                logging.info("✅ IP сменился")
                return True
                
        except Exception as e:
            logging.error(f"❌ Ошибка проверки IP: {e}")
            return False

    def find_firefox_binary(self) -> Optional[str]:
        """Поиск Firefox"""
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
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path
        
        if self.tor_manager.command_exists('firefox'):
            return 'firefox'
        
        return None

    def setup_driver(self) -> bool:
        """Настройка Firefox"""
        logging.info("🌐 Настройка браузера...")
        
        self.original_ip = self.get_current_ip_without_proxy()
        
        if self.tor_manager.start_tor():
            logging.info("✅ Tor запущен")
            self.use_tor = True
        else:
            logging.warning("⚠ Tor не запущен, работаем без прокси")
            self.use_tor = False
        
        try:
            user_agent = self.ua_manager.get_user_agent(self.username)
            geckodriver_path = self.gecko_manager.get_driver_path()
            
            firefox_options = Options()
            
            if self.use_tor:
                firefox_options.set_preference("network.proxy.type", 1)
                firefox_options.set_preference("network.proxy.socks", "127.0.0.1")
                firefox_options.set_preference("network.proxy.socks_port", self.tor_manager.tor_port)
                firefox_options.set_preference("network.proxy.socks_version", 5)
                firefox_options.set_preference("network.proxy.socks_remote_dns", True)
                firefox_options.set_preference("network.proxy.http", "")
                firefox_options.set_preference("network.proxy.http_port", 0)
                firefox_options.set_preference("network.proxy.ssl", "")
                firefox_options.set_preference("network.proxy.ssl_port", 0)
            else:
                firefox_options.set_preference("network.proxy.type", 0)
            
            firefox_options.set_preference("general.useragent.override", user_agent)
            firefox_options.set_preference("dom.webdriver.enabled", False)
            firefox_options.set_preference("useAutomationExtension", False)
            firefox_options.set_preference("network.http.use-cache", False)
            
            if "Android" in user_agent:
                firefox_options.set_preference("layout.css.devPixelRatio", "2.0")
                firefox_options.set_preference("dom.w3c_touch_events.enabled", 1)
            else:
                firefox_options.set_preference("layout.css.devPixelRatio", "2.0")
                firefox_options.set_preference("dom.w3c_touch_events.enabled", 1)
                firefox_options.set_preference("general.appname.override", "Netscape")
                firefox_options.set_preference("general.appversion.override", "5.0 (Mobile; rv:68.0)")
            
            firefox_options.set_preference("media.peerconnection.enabled", False)
            firefox_options.set_preference("media.navigator.enabled", False)
            firefox_options.set_preference("privacy.resistFingerprinting", False)
            firefox_options.set_preference("privacy.trackingprotection.enabled", True)
            firefox_options.set_preference("geo.enabled", False)
            firefox_options.set_preference("browser.safebrowsing.downloads.remote.enabled", False)
            firefox_options.set_preference("app.update.enabled", False)
            firefox_options.set_preference("toolkit.telemetry.enabled", False)
            firefox_options.set_preference("datareporting.healthreport.uploadEnabled", False)
            
            if self.tor_manager.is_termux:
                firefox_options.add_argument("--no-sandbox")
                firefox_options.add_argument("--disable-dev-shm-usage")
            
            firefox_binary = self.find_firefox_binary()
            if firefox_binary and firefox_binary != 'firefox':
                firefox_options.binary_location = firefox_binary
            
            service = Service(executable_path=geckodriver_path)
            self.driver = webdriver.Firefox(options=firefox_options, service=service)
            
            self.driver.set_page_load_timeout(120)
            self.driver.implicitly_wait(20)
            
            if "Android" in user_agent:
                mobile_sizes = [(360, 640), (375, 667), (414, 896), (393, 851)]
                width, height = random.choice(mobile_sizes)
            else:
                ipad_sizes = [(768, 1024), (834, 1112), (1024, 1366)]
                width, height = random.choice(ipad_sizes)
            
            self.driver.set_window_size(width, height)
            logging.info("✅ Браузер запущен")
            
            if self.use_tor:
                return self.verify_ip_change_via_2ip()
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка браузера: {e}")
            return False

    def save_cookies(self):
        """Сохранение cookies"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения cookies: {e}")
    
    def load_cookies(self) -> bool:
        """Загрузка cookies"""
        try:
            if os.path.exists(self.cookies_file):
                self.driver.get(self.base_url)
                time.sleep(3)
                
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)
                
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass
                
                return True
        except:
            pass
        
        return False
    
    def check_authorization(self) -> bool:
        """Проверка авторизации"""
        try:
            login_forms = self.driver.find_elements(By.NAME, "username")
            return len(login_forms) == 0
        except:
            return False
    
    def login(self) -> bool:
        """Авторизация"""
        logging.info("🔐 Авторизация...")
        
        try:
            self.driver.get(f"{self.base_url}/login")
            time.sleep(5)
            
            wait = WebDriverWait(self.driver, 30)
            
            username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            username_field.click()
            HumanBehaviorSimulator.human_like_typing(username_field, self.username, self.driver)
            
            password_field = self.driver.find_element(By.NAME, "password")
            password_field.click()
            HumanBehaviorSimulator.human_like_typing(password_field, self.password, self.driver)
            
            login_button = self.driver.find_element(By.ID, "button-login")
            time.sleep(2)
            login_button.click()
            
            time.sleep(8)
            
            # Проверка 2FA
            current_url = self.driver.current_url
            if "/2fa" in current_url:
                logging.info("🔐 Требуется 2FA код")
                
                try:
                    code_field = wait.until(EC.presence_of_element_located((By.NAME, "code")))
                    
                    verification_code = input("Введите 2FA код: ").strip()
                    
                    if verification_code and verification_code.isdigit():
                        code_field.click()
                        HumanBehaviorSimulator.human_like_typing(code_field, verification_code, self.driver)
                        
                        confirm_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.button_theme_blue")
                        if confirm_buttons:
                            confirm_buttons[0].click()
                        
                        time.sleep(8)
                    
                except Exception as e:
                    logging.error(f"❌ Ошибка 2FA: {e}")
                    return False
            
            # Проверка результата
            login_forms = self.driver.find_elements(By.NAME, "username")
            if not login_forms:
                logging.info("✅ Авторизация успешна")
                self.save_cookies()
                return True
            else:
                logging.error("❌ Авторизация не удалась")
                return False
                
        except Exception as e:
            logging.error(f"❌ Ошибка авторизации: {e}")
            return False
    
    def random_mouse_movement(self):
        """Движение мыши"""
        try:
            viewport_size = self.driver.get_window_size()
            max_width = max(100, viewport_size['width'] - 100)
            max_height = max(100, viewport_size['height'] - 100)
            
            current_pos = (random.randint(50, max_width), random.randint(50, max_height))
            new_pos = (random.randint(50, max_width), random.randint(50, max_height))
            
            curve_points = HumanBehaviorSimulator.generate_bezier_curve(current_pos, new_pos)
            actions = ActionChains(self.driver)
            
            for i, point in enumerate(curve_points):
                if i == 0:
                    continue
                prev_point = curve_points[i-1]
                offset_x = max(-50, min(50, int(point[0] - prev_point[0])))
                offset_y = max(-50, min(50, int(point[1] - prev_point[1])))
                actions.move_by_offset(offset_x, offset_y)
                time.sleep(random.uniform(0.01, 0.05))
            
            actions.perform()
        except:
            pass
    
    def random_scroll(self):
        """Прокрутка"""
        try:
            scroll_direction = random.choice(['up', 'down'])
            scroll_amount = random.randint(100, 500)
            
            if scroll_direction == 'down':
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            else:
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
            
            time.sleep(random.uniform(0.5, 2.0))
        except:
            pass
    
    def get_youtube_tasks(self) -> List[Dict]:
        """ЭФФЕКТИВНЫЙ поиск заданий - JavaScript вместо цикла по элементам"""
        logging.info("📋 Поиск заданий...")
        
        try:
            self.driver.get(f"{self.base_url}/tasks-youtube")
            time.sleep(5)
            
            # ЭФФЕКТИВНО: JavaScript парсинг ВСЕХ заданий за 1 запрос
            tasks_data = self.driver.execute_script("""
                var tasks = [];
                var rows = document.querySelectorAll("tr[class^='ads_']");
                
                for (var i = 0; i < rows.length; i++) {
                    try {
                        var row = rows[i];
                        var className = row.className;
                        var taskIdMatch = className.match(/ads_(\d+)/);
                        
                        if (taskIdMatch) {
                            var taskId = taskIdMatch[1];
                            var startButton = row.querySelector("span[id='link_ads_start_" + taskId + "']");
                            
                            if (startButton) {
                                var onclick = startButton.getAttribute('onclick');
                                var timeMatch = onclick ? onclick.match(/start_youtube_new\(\d+,\s*'(\d+)'\)/) : null;
                                var watchTime = timeMatch ? parseInt(timeMatch[1]) : 10;
                                var videoUrl = startButton.getAttribute('title') || 'unknown';
                                
                                tasks.push({
                                    id: taskId,
                                    watch_time: watchTime,
                                    video_url: videoUrl,
                                    button_selector: "span[id='link_ads_start_" + taskId + "']",
                                    row_class: className
                                });
                            }
                        }
                    } catch (e) {
                        // Пропускаем ошибочные элементы
                    }
                }
                
                return tasks;
            """)
            
            # Конвертируем в нужный формат с реальными элементами
            tasks = []
            for task_data in tasks_data:
                try:
                    task_row = self.driver.find_element(By.CSS_SELECTOR, f"tr.{task_data['row_class']}")
                    start_button = self.driver.find_element(By.CSS_SELECTOR, task_data['button_selector'])
                    
                    task_info = {
                        'id': task_data['id'],
                        'element': start_button,
                        'watch_time': task_data['watch_time'],
                        'video_url': task_data['video_url'],
                        'row': task_row
                    }
                    
                    tasks.append(task_info)
                except:
                    continue
            
            logging.info(f"📊 Найдено заданий: {len(tasks)}")
            return tasks
            
        except Exception as e:
            logging.error(f"❌ Ошибка получения заданий: {e}")
            return []
    
    def handle_youtube_ads(self) -> bool:
        """ЭФФЕКТИВНАЯ проверка рекламы - JavaScript вместо поиска элементов"""
        logging.info("📺 Проверка рекламы...")
        
        try:
            time.sleep(3)
            
            # ЭФФЕКТИВНО: JavaScript проверка рекламы за 1 запрос
            ad_status = self.driver.execute_script("""
                // Проверяем наличие рекламы
                var adBadges = document.querySelectorAll('span.ytp-ad-badge--clean-player, [id*="ad-badge"], .ytp-ad-badge');
                var hasAd = false;
                
                for (var i = 0; i < adBadges.length; i++) {
                    if (adBadges[i].offsetParent !== null) { // Элемент видимый
                        hasAd = true;
                        break;
                    }
                }
                
                if (!hasAd) {
                    return {status: 'no_ad'};
                }
                
                // Есть реклама - ищем кнопку skip
                var skipButtons = document.querySelectorAll('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, [class*="skip"]');
                for (var i = 0; i < skipButtons.length; i++) {
                    if (skipButtons[i].offsetParent !== null && !skipButtons[i].disabled) {
                        return {status: 'skip_available', element: skipButtons[i]};
                    }
                }
                
                return {status: 'wait_ad'};
            """)
            
            if ad_status['status'] == 'no_ad':
                return True
            
            if ad_status['status'] == 'skip_available':
                # Кликаем кнопку skip через JavaScript
                self.driver.execute_script("arguments[0].click();", ad_status['element'])
                logging.info("⏭ Реклама пропущена")
                time.sleep(2)
                return True
            
            # Ждем завершения рекламы ЭФФЕКТИВНО
            logging.info("📺 Ждем завершения рекламы...")
            
            for attempt in range(120):  # 2 минуты максимум
                # ЭФФЕКТИВНАЯ проверка через JavaScript
                ad_finished = self.driver.execute_script("""
                    // Проверяем исчезла ли реклама
                    var adBadges = document.querySelectorAll('span.ytp-ad-badge--clean-player, [id*="ad-badge"], .ytp-ad-badge');
                    for (var i = 0; i < adBadges.length; i++) {
                        if (adBadges[i].offsetParent !== null) {
                            return false; // Реклама еще есть
                        }
                    }
                    
                    // Проверяем появилась ли кнопка skip
                    var skipButtons = document.querySelectorAll('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, [class*="skip"]');
                    for (var i = 0; i < skipButtons.length; i++) {
                        if (skipButtons[i].offsetParent !== null && !skipButtons[i].disabled) {
                            skipButtons[i].click();
                            return true;
                        }
                    }
                    
                    return true; // Реклама закончилась
                """)
                
                if ad_finished:
                    logging.info("✅ Реклама завершилась")
                    return True
                
                time.sleep(1)
            
            logging.info("✅ Реклама обработана")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка рекламы: {e}")
            return True

    def click_center_screen(self):
        """ИСПРАВЛЕННЫЙ метод - работа с IFRAME и физические клики"""
        try:
            logging.info("🖱 Запуск видео...")
            
            # 1. СНАЧАЛА ПРОБУЕМ ПЕРЕКЛЮЧИТЬСЯ НА IFRAME
            iframe_switched = False
            try:
                # Ищем все iframe'ы
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                logging.info(f"🔍 Найдено iframe'ов: {len(iframes)}")
                
                for i, iframe in enumerate(iframes):
                    try:
                        # Переключаемся на iframe
                        self.driver.switch_to.frame(iframe)
                        iframe_switched = True
                        logging.info(f"✅ Переключились на iframe {i}")
                        
                        # Пробуем найти и запустить видео внутри iframe
                        success = self.driver.execute_script("""
                            var attempts = [];
                            
                            // Ищем видео внутри iframe
                            var videos = document.getElementsByTagName('video');
                            attempts.push('Videos found in iframe: ' + videos.length);
                            
                            for (var i = 0; i < videos.length; i++) {
                                try {
                                    var video = videos[i];
                                    
                                    // Настройки для запуска
                                    video.muted = false;
                                    video.volume = 0.1;
                                    video.controls = true;
                                    video.autoplay = true;
                                    
                                    // Принудительный запуск
                                    var playPromise = video.play();
                                    if (playPromise && typeof playPromise.then === 'function') {
                                        playPromise.then(function() {
                                            attempts.push('IFRAME Video ' + i + ' STARTED!');
                                        }).catch(function(error) {
                                            // Пробуем с muted
                                            video.muted = true;
                                            video.play().then(function() {
                                                attempts.push('IFRAME Video ' + i + ' started muted');
                                                setTimeout(function() { video.muted = false; }, 1000);
                                            });
                                        });
                                    }
                                    
                                    // Клик по видео в iframe
                                    var rect = video.getBoundingClientRect();
                                    if (rect.width > 0 && rect.height > 0) {
                                        var clickEvent = new MouseEvent('click', {
                                            view: window,
                                            bubbles: true,
                                            cancelable: true,
                                            clientX: rect.left + rect.width / 2,
                                            clientY: rect.top + rect.height / 2
                                        });
                                        video.dispatchEvent(clickEvent);
                                        attempts.push('Clicked iframe video ' + i);
                                    }
                                    
                                } catch (e) {
                                    attempts.push('IFRAME Video ' + i + ' error: ' + e.message);
                                }
                            }
                            
                            // Ищем кнопки воспроизведения внутри iframe
                            var playButtons = document.querySelectorAll(
                                '.ytp-large-play-button, .ytp-play-button, [aria-label*="Play"], [aria-label*="Воспроизвести"]'
                            );
                            
                            for (var i = 0; i < playButtons.length; i++) {
                                try {
                                    var button = playButtons[i];
                                    if (button.offsetParent !== null) {
                                        button.click();
                                        attempts.push('IFRAME Play button clicked: ' + i);
                                    }
                                } catch (e) {
                                    attempts.push('IFRAME Button error: ' + e.message);
                                }
                            }
                            
                            return attempts;
                        """)
                        
                        logging.info(f"🎬 IFRAME попытки: {success}")
                        
                        # Возвращаемся к основному документу
                        self.driver.switch_to.default_content()
                        break
                        
                    except Exception as e:
                        # Если не удалось переключиться на этот iframe, пробуем следующий
                        self.driver.switch_to.default_content()
                        continue
                        
            except Exception as e:
                logging.info(f"⚠ Не удалось работать с iframe: {e}")
                if iframe_switched:
                    self.driver.switch_to.default_content()
            
            # 2. ФИЗИЧЕСКИЕ КЛИКИ SELENIUM - САМОЕ ВАЖНОЕ
            try:
                logging.info("🖱 Выполняем физические клики...")
                
                # Получаем размеры окна
                viewport_size = self.driver.get_window_size()
                
                # Множественные точки для клика (включая где находится iframe)
                click_points = [
                    (382, 456),  # Точка где был iframe по логам
                    (viewport_size['width'] // 2, viewport_size['height'] // 2),  # Центр
                    (viewport_size['width'] // 2, viewport_size['height'] // 3),  # Верх центр
                    (viewport_size['width'] // 2, viewport_size['height'] * 2 // 3),  # Низ центр
                    (viewport_size['width'] // 3, viewport_size['height'] // 2),  # Лево центр
                    (viewport_size['width'] * 2 // 3, viewport_size['height'] // 2),  # Право центр
                ]
                
                for i, (x, y) in enumerate(click_points):
                    try:
                        # Убеждаемся что координаты в пределах экрана
                        x = max(10, min(viewport_size['width'] - 10, x))
                        y = max(10, min(viewport_size['height'] - 10, y))
                        
                        logging.info(f"🖱 Клик {i+1}: ({x}, {y})")
                        
                        # ActionChains клик
                        actions = ActionChains(self.driver)
                        actions.move_by_offset(x - viewport_size['width']//2, y - viewport_size['height']//2)
                        actions.click()
                        actions.perform()
                        time.sleep(0.3)
                        
                        # Сброс позиции
                        actions = ActionChains(self.driver)
                        actions.move_by_offset(-(x - viewport_size['width']//2), -(y - viewport_size['height']//2))
                        actions.perform()
                        
                        # JavaScript клик в ту же точку
                        self.driver.execute_script(f"""
                            var element = document.elementFromPoint({x}, {y});
                            if (element) {{
                                var clickEvent = new MouseEvent('click', {{
                                    view: window,
                                    bubbles: true,
                                    cancelable: true,
                                    clientX: {x},
                                    clientY: {y}
                                }});
                                element.dispatchEvent(clickEvent);
                                element.click();
                            }}
                        """)
                        
                    except Exception as e:
                        logging.info(f"⚠ Ошибка клика {i+1}: {e}")
                        
            except Exception as e:
                logging.info(f"⚠ Ошибка физических кликов: {e}")
            
            # 3. КЛАВИАТУРНЫЕ КОМАНДЫ
            try:
                from selenium.webdriver.common.keys import Keys
                body = self.driver.find_element(By.TAG_NAME, "body")
                
                # Различные клавиши для запуска видео
                keys_to_try = [Keys.SPACE, Keys.ENTER, 'k', 'p', Keys.ARROW_RIGHT]
                for key in keys_to_try:
                    try:
                        body.send_keys(key)
                        time.sleep(0.2)
                        logging.info(f"⌨ Нажата клавиша: {key}")
                    except:
                        pass
            except:
                pass
            
            # 4. СПЕЦИАЛЬНЫЙ МЕТОД ДЛЯ YOUTUBE В IFRAME
            time.sleep(1)
            self.driver.execute_script("""
                // Пробуем достучаться до YouTube через postMessage
                var iframes = document.getElementsByTagName('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    try {
                        var iframe = iframes[i];
                        
                        // Пробуем отправить команду воспроизведения
                        iframe.contentWindow.postMessage('{"event":"command","func":"playVideo","args":""}', '*');
                        iframe.contentWindow.postMessage('{"event":"command","func":"unMute","args":""}', '*');
                        
                        // Симулируем клик по iframe
                        var rect = iframe.getBoundingClientRect();
                        var x = rect.left + rect.width / 2;
                        var y = rect.top + rect.height / 2;
                        
                        var clickEvent = new MouseEvent('click', {
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: x,
                            clientY: y
                        });
                        
                        iframe.dispatchEvent(clickEvent);
                        
                        console.log('Sent postMessage and click to iframe', i);
                        
                    } catch (e) {
                        console.log('iframe', i, 'error:', e);
                    }
                }
                
                // Глобальная активация
                document.dispatchEvent(new Event('click'));
                window.focus();
                document.body.focus();
            """)
            
            # 5. ПРОВЕРКА РЕЗУЛЬТАТА
            time.sleep(2)
            
            # Проверяем через JavaScript все возможные признаки воспроизведения
            status = self.driver.execute_script("""
                var result = {
                    videos_found: 0,
                    videos_playing: 0,
                    iframes_found: 0,
                    audio_context: false
                };
                
                // Проверяем видео в основном документе
                var videos = document.getElementsByTagName('video');
                result.videos_found = videos.length;
                
                for (var i = 0; i < videos.length; i++) {
                    if (!videos[i].paused && videos[i].currentTime > 0) {
                        result.videos_playing++;
                    }
                }
                
                // Считаем iframe'ы
                result.iframes_found = document.getElementsByTagName('iframe').length;
                
                // Проверяем AudioContext (признак активного аудио)
                try {
                    if (window.AudioContext || window.webkitAudioContext) {
                        result.audio_context = true;
                    }
                } catch (e) {}
                
                return result;
            """)
            
            logging.info(f"📊 Статус: {status}")
            
            if status['videos_playing'] > 0:
                logging.info(f"✅ Видео запущено! Играющих: {status['videos_playing']}")
            else:
                logging.warning("⚠ Видео в iframe может быть не запущено")
                
                # ПОСЛЕДНЯЯ АГРЕССИВНАЯ ПОПЫТКА - множественные клики по iframe
                self.driver.execute_script("""
                    setTimeout(function() {
                        var iframes = document.getElementsByTagName('iframe');
                        for (var i = 0; i < iframes.length; i++) {
                            var iframe = iframes[i];
                            var rect = iframe.getBoundingClientRect();
                            
                            // Много кликов по iframe
                            for (var j = 0; j < 5; j++) {
                                setTimeout(function() {
                                    var x = rect.left + rect.width / 2;
                                    var y = rect.top + rect.height / 2;
                                    
                                    var clickEvent = new MouseEvent('click', {
                                        view: window,
                                        bubbles: true,
                                        cancelable: true,
                                        clientX: x,
                                        clientY: y
                                    });
                                    
                                    iframe.dispatchEvent(clickEvent);
                                    document.elementFromPoint(x, y).click();
                                    
                                }, j * 100);
                            }
                        }
                    }, 100);
                """)
            
            logging.info("🎮 Попытки запуска завершены")
            
        except Exception as e:
            logging.error(f"❌ Ошибка запуска видео: {e}")
            # Всегда возвращаемся к основному документу
            try:
                self.driver.switch_to.default_content()
            except:
                pass

    def wait_for_aviso_timer_completion(self) -> bool:
        """УЛУЧШЕННОЕ ожидание таймера с контролем воспроизведения"""
        logging.info("⏱ Ожидание таймера Aviso...")
        
        try:
            last_timer_value = None
            same_value_counter = 0
            check_count = 0
            video_was_playing = False  # Флаг что видео когда-то работало
            restart_attempts = 0  # Счетчик попыток перезапуска ПОСЛЕ остановки
            video_started_logged = False  # Флаг что уже залогировали запуск
            
            while True:
                check_count += 1
                
                # ЭФФЕКТИВНЫЙ поиск таймера и завершения за 1 запрос
                timer_status = self.driver.execute_script("""
                    // Ищем таймер
                    var timerElement = document.querySelector('span.timer#tmr');
                    if (timerElement) {
                        var timerText = timerElement.textContent.trim();
                        if (/^\d+$/.test(timerText)) {
                            return {status: 'timer_found', value: parseInt(timerText)};
                        }
                    }
                    
                    // Ищем сообщение о завершении
                    var completionElements = document.querySelectorAll('span');
                    for (var i = 0; i < completionElements.length; i++) {
                        var text = completionElements[i].textContent;
                        if (text.includes('Задача выполнена') && text.includes('начислено')) {
                            return {status: 'completed', message: text.trim()};
                        }
                    }
                    
                    return {status: 'not_found'};
                """)
                
                if timer_status['status'] == 'completed':
                    logging.info(f"✅ Задание завершено: {timer_status['message']}")
                    return True
                
                if timer_status['status'] == 'timer_found':
                    current_timer_value = timer_status['value']
                    
                    # Логируем таймер каждые 10 секунд
                    if check_count % 20 == 0:
                        logging.info(f"⏰ Таймер: {current_timer_value}с")
                    
                    if last_timer_value is not None:
                        if current_timer_value == last_timer_value:
                            same_value_counter += 1
                            
                            # Видео застряло на 5+ секунд
                            if same_value_counter >= 10:  # 5 секунд
                                
                                # Если видео УЖЕ работало раньше, но теперь застряло
                                if video_was_playing:
                                    restart_attempts += 1
                                    logging.warning(f"⏸ Видео остановилось! Попытка перезапуска {restart_attempts}/3")
                                    
                                    # После 3 попыток перезапуска - обновляем страницу
                                    if restart_attempts >= 3:
                                        logging.error("💥 Видео не перезапускается! Обновляем страницу...")
                                        self.driver.refresh()
                                        time.sleep(5)
                                        
                                        # Обрабатываем рекламу после обновления
                                        self.handle_youtube_ads()
                                        
                                        # Сбрасываем счетчики
                                        restart_attempts = 0
                                        video_was_playing = False
                                        video_started_logged = False
                                        last_timer_value = None
                                        same_value_counter = 0
                                        continue
                                else:
                                    # Видео еще не запускалось
                                    if not video_started_logged:
                                        logging.warning("⏸ Видео на паузе! Запускаем...")
                                
                                self.click_center_screen()
                                same_value_counter = 0  # СБРОС!
                        else:
                            # Таймер изменился - видео работает!
                            if same_value_counter > 0:
                                # Логируем запуск только ОДИН раз
                                if not video_started_logged:
                                    logging.info("▶ Видео запустилось")
                                    video_started_logged = True
                                video_was_playing = True  # Помечаем что видео работало
                                restart_attempts = 0  # Сбрасываем попытки перезапуска
                            same_value_counter = 0
                    
                    last_timer_value = current_timer_value
                    
                    if current_timer_value <= 0:
                        logging.info("✅ Таймер достиг нуля")
                        break
                
                time.sleep(0.5)
                
                if check_count > 1200:  # 10 минут максимум
                    logging.warning("⏰ Превышено время ожидания")
                    return False
            
            # Финальная проверка завершения
            time.sleep(2)
            final_check = self.driver.execute_script("""
                var completionElements = document.querySelectorAll('span');
                for (var i = 0; i < completionElements.length; i++) {
                    var text = completionElements[i].textContent;
                    if (text.includes('Задача выполнена') && text.includes('начислено')) {
                        return text.trim();
                    }
                }
                return null;
            """)
            
            if final_check:
                logging.info(f"✅ Подтверждение: {final_check}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка таймера: {e}")
            return False
    
    def execute_youtube_task(self, task: Dict) -> bool:
        """Выполнение задания YouTube"""
        task_id = task['id']
        
        logging.info(f"🎯 Задание {task_id}")
        
        original_window = self.driver.current_window_handle
        
        try:
            ActionChains(self.driver).move_to_element(task['row']).perform()
            time.sleep(random.uniform(1, 3))
            
            # Пауза перед кликом
            pause = random.uniform(2, 15)
            logging.info(f"⏳ Пауза {pause:.1f}с")
            time.sleep(pause)
            
            start_button = task['element']
            
            # Клик по заданию
            try:
                viewport_size = self.driver.get_window_size()
                current_pos = (viewport_size['width'] // 2, viewport_size['height'] // 2)
                button_rect = start_button.rect
                
                target_x = max(10, min(viewport_size['width'] - 10, int(button_rect['x'] + button_rect['width'] // 2)))
                target_y = max(10, min(viewport_size['height'] - 10, int(button_rect['y'] + button_rect['height'] // 2)))
                target_pos = (target_x, target_y)
                
                curve_points = HumanBehaviorSimulator.generate_bezier_curve(current_pos, target_pos)
                actions = ActionChains(self.driver)
                
                for i, point in enumerate(curve_points[1:], 1):
                    prev_point = curve_points[i-1]
                    offset_x = max(-50, min(50, int(point[0] - prev_point[0])))
                    offset_y = max(-50, min(50, int(point[1] - prev_point[1])))
                    actions.move_by_offset(offset_x, offset_y)
                    time.sleep(random.uniform(0.01, 0.03))
                
                actions.click(start_button).perform()
            except:
                start_button.click()
            
            time.sleep(5)
            
            # Переключение на новую вкладку
            all_windows = self.driver.window_handles
            
            new_window = None
            for window in all_windows:
                if window != original_window:
                    self.driver.switch_to.window(window)
                    new_window = window
                    break
            
            if not new_window:
                logging.error("❌ Новая вкладка не найдена")
                return False
            
            # Обработка рекламы
            self.handle_youtube_ads()
            
            # Ожидание по таймеру Aviso
            if self.wait_for_aviso_timer_completion():
                logging.info("✅ Задание завершено!")
                
                time.sleep(random.uniform(2, 8))
                
                # Возврат на исходную вкладку
                self.driver.close()
                self.driver.switch_to.window(original_window)
                
                # Обновление страницы
                logging.info("🔄 Обновление страницы...")
                self.driver.refresh()
                time.sleep(5)
                
                return True
            else:
                logging.error(f"❌ Задание {task_id} не завершено")
                return False
                
        except Exception as e:
            logging.error(f"❌ Ошибка задания {task_id}: {e}")
            
            # Очистка окон
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
            except:
                pass
            
            return False
    
    def execute_all_tasks(self) -> int:
        """Выполнение всех заданий"""
        logging.info("🚀 Выполнение заданий...")
        
        tasks = self.get_youtube_tasks()
        if not tasks:
            logging.info("📭 Нет заданий")
            return 0
        
        completed_tasks = 0
        random.shuffle(tasks)
        
        for i, task in enumerate(tasks):
            logging.info(f"📝 {i+1}/{len(tasks)}")
            
            try:
                if self.execute_youtube_task(task):
                    completed_tasks += 1
                    logging.info(f"✅ Выполнено {completed_tasks}/{len(tasks)}")
                
                # Пауза между заданиями
                if i < len(tasks) - 1:
                    pause_time = random.uniform(1, 25)
                    logging.info(f"⏳ Пауза {pause_time:.1f}с")
                    
                    for _ in range(int(pause_time // 12)):
                        if random.random() < 0.5:
                            self.random_mouse_movement()
                        if random.random() < 0.3:
                            self.random_scroll()
                        time.sleep(random.uniform(10, 15))
                
            except Exception as e:
                logging.error(f"❌ Критическая ошибка: {e}")
                continue
        
        logging.info(f"🏁 Завершено: {completed_tasks}/{len(tasks)}")
        return completed_tasks
    
    def cleanup(self):
        """Очистка"""
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass
        
        try:
            if self.use_tor:
                self.tor_manager.stop_tor()
        except:
            pass
    
    def run_cycle(self) -> bool:
        """Один цикл работы"""
        logging.info("🔄 Начало цикла")
        
        try:
            if not self.setup_driver():
                logging.error("❌ Ошибка браузера")
                return False
            
            cookies_loaded = self.load_cookies()
            
            if cookies_loaded:
                logging.info("🔄 Применение cookies...")
                self.driver.refresh()
                time.sleep(8)
                
                if self.check_authorization():
                    logging.info("✅ Авторизован через cookies")
                else:
                    if not self.login():
                        return False
            else:
                if not self.login():
                    return False
            
            completed_tasks = self.execute_all_tasks()
            
            if completed_tasks > 0:
                logging.info(f"✅ Цикл завершен: {completed_tasks} заданий")
            else:
                logging.info("ℹ Нет заданий")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка цикла: {e}")
            return False
        finally:
            self.cleanup()
    
    def run(self):
        """Основной цикл"""
        logging.info("🤖 ЗАПУСК ЭФФЕКТИВНОГО AVISO BOT")
        
        cycle_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        try:
            while True:
                cycle_count += 1
                logging.info(f"🔄 ЦИКЛ #{cycle_count}")
                
                success = self.run_cycle()
                
                if success:
                    consecutive_failures = 0
                    
                    pause_minutes = random.uniform(1, 120)
                    pause_seconds = pause_minutes * 60
                    
                    next_run_time = datetime.now() + timedelta(seconds=pause_seconds)
                    
                    logging.info(f"😴 Пауза {pause_minutes:.1f} минут")
                    logging.info(f"⏰ Следующий: {next_run_time.strftime('%H:%M:%S')}")
                    
                    pause_intervals = max(1, int(pause_seconds // 60))
                    interval_duration = pause_seconds / pause_intervals
                    
                    for i in range(pause_intervals):
                        time.sleep(interval_duration)
                else:
                    consecutive_failures += 1
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logging.error("💥 Много ошибок подряд - остановка")
                        break
                    else:
                        pause_minutes = random.uniform(5, 15)
                    
                    logging.warning(f"⚠ Ошибка цикла, пауза {pause_minutes:.1f} минут")
                    time.sleep(pause_minutes * 60)
        
        except KeyboardInterrupt:
            logging.info("🛑 Остановка (Ctrl+C)")
        except Exception as e:
            logging.error(f"💥 Критическая ошибка: {e}")
        finally:
            self.cleanup()
            logging.info("👋 Завершение работы")

def main():
    """Точка входа в программу"""
    print("🤖 Aviso YouTube Tasks Automation Bot - ИСПРАВЛЕННАЯ ВЕРСИЯ")
    print("=" * 80)
    print("🚀 Автоматический запуск...")
    print("⚠  ВНИМАНИЕ: Используйте бота ответственно!")
    print("🔧 ИСПРАВЛЕНИЯ:")
    print("   ✅ Увеличен таймаут Tor с 2 до 20 минут")
    print("   ✅ ВОССТАНОВЛЕНА проверка IP через 2ip.ru")
    print("   ✅ Убраны проверки URL новых вкладок")
    print("   ✅ ИСПРАВЛЕНЫ ошибки координат мыши")
    print("   ✅ ВОССТАНОВЛЕНА оригинальная логика авторизации")
    print("📋 Функции:")
    print("   - Автоматическая авторизация на aviso.bz")
    print("   - Выполнение заданий по просмотру YouTube")
    print("   - Имитация человеческого поведения")
    print("   - Работа через Tor прокси ИЛИ БЕЗ прокси (fallback)")
    print("   - ПРОВЕРКА СМЕНЫ IP через 2ip.ru")
    print("   - Автоматическая установка geckodriver")
    print("   - Фиксированный User-Agent для аккаунта")
    print("   - Улучшенная имитация опечаток при вводе")
    print("   - Улучшенная поддержка Termux/Android")
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