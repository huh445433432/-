#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading
import time
import logging
import requests
import json
import base64
from datetime import datetime, timedelta
from flask import Flask, jsonify
import vk_api
from vk_api.exceptions import ApiError

app = Flask(__name__)

TOKEN = os.environ.get('VK_TOKEN', '')
GROUP_IDS = os.environ.get('GROUP_IDS', '-123456789,-987654321').split(',')
INTERVAL_HOURS = int(os.environ.get('INTERVAL_HOURS', '5'))
PHOTO_DIR = os.path.join(os.path.dirname(__file__), 'photos')

 # ==== НАСТРОЙКИ ПРОДЛЕНИЯ ТОКЕНА ====
CLIENT_ID = os.environ.get('VK_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('VK_CLIENT_SECRET', '')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')
REFRESH_INTERVAL_DAYS = 20

GROUP_SCREEN_NAMES = ['dosska_obyavlenij', '165412523','doskamskrus' , 'boardbest',
        '4u.baraholka','announcementin.krasnodar','bryansk_doska']


POSTS = [
    {
        "photo": "i.webp",
        "text": "Автоматизирую процессы и делаю ботов на Python под ключ."

        "• Боты (Telegram, ВК): меню, кнопки, логика, БД."
        "• Парсеры: сбор и выгрузка данных, защита от блокировок."
        "• Скрипты: рутина, отчёты, уведомления."
        
        "Никакой магии: только рабочий код, понятный план и честные сроки."
        
        "📩 Напишите задачу в личку — разберу и предложу решение."

    }

]

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Флаг остановки потока
running = True
post_index = 0
last_refresh_time = None


# ========== РАБОТА С ТОКЕНОМ ==========
def save_token(token):
    """Сохраняет токен в файл"""
    global TOKEN
    TOKEN = token
    try:
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump({'token': token, 'saved_at': datetime.now().isoformat()}, f)
        logger.info("✅ Токен сохранён в файл")
    except Exception as e:
        logger.warning(f"Не удалось сохранить токен в файл: {e}")


def load_token():
    """Загружает токен из файла или переменной окружения"""
    global TOKEN
    try:
        # Сначала пробуем из файла (там может быть продленный токен)
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('token'):
                    TOKEN = data['token']
                    logger.info(f"✅ Токен загружен из файла (сохранён: {data['saved_at']})")
                    return TOKEN
    except Exception as e:
        logger.warning(f"Не удалось загрузить токен из файла: {e}")

    # Если нет файла или ошибка - используем токен из окружения
    if TOKEN:
        logger.info("✅ Токен загружен из переменной окружения")
    return TOKEN


def check_token_validity():
    """Проверяет валидность токена"""
    try:
        vk_session = vk_api.VkApi(token=TOKEN)
        vk = vk_session.get_api()
        vk.users.get()
        return True
    except ApiError as e:
        if e.code == 5:  # Ошибка авторизации
            return False
        # Другие ошибки API могут быть временными
        return True
    except Exception:
        return False


def refresh_token():
    """Продлевает токен через API ВКонтакте"""
    global TOKEN
    global last_refresh_time

    logger.info("🔄 Проверяем необходимость продления токена...")

    # Проверяем валидность токена
    if check_token_validity():
        logger.info("✅ Токен работает, продление не требуется")
        last_refresh_time = datetime.now()
        return True

    # Если токен не работает, пробуем продлить
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("❌ Для продления токена нужны VK_CLIENT_ID и VK_CLIENT_SECRET")
        return False

    try:
        # Метод 1: Продление через oauth.vk.com (для официальных приложений)
        logger.info("🔄 Пытаемся продлить токен через API...")

        # Так как у нас нет возможности пройти интерактивную авторизацию,
        # используем долгосрочный способ - проверяем и сообщаем о необходимости обновления

        # Пытаемся обновить токен через silent token (если поддерживается)
        response = requests.post(
            'https://api.vk.com/method/oauth.vk.com/token',
            data={
                'grant_type': 'client_credentials',
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'v': '5.131'
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if 'access_token' in data:
                new_token = data['access_token']
                save_token(new_token)
                last_refresh_time = datetime.now()
                logger.info(f"✅ Токен успешно продлён: {datetime.now()}")
                return True

        logger.error("❌ Не удалось продлить токен автоматически")
        logger.info("⚠️ Токен истёк. Требуется ручное обновление в переменной окружения VK_TOKEN на Render")
        logger.info("📝 Инструкция: https://vk.com/editapp?id=ваш_id&section=options")
        return False

    except Exception as e:
        logger.error(f"❌ Ошибка при попытке продления токена: {e}")
        return False


def check_and_refresh_token_periodic():
    """Периодическая проверка и продление токена"""
    global last_refresh_time

    while running:
        try:
            if last_refresh_time is None:
                last_refresh_time = datetime.now()
                logger.info(f"📅 Токен проверен: {last_refresh_time}")

            # Проверяем каждые REFRESH_INTERVAL_DAYS дней
            if datetime.now() - last_refresh_time >= timedelta(days=REFRESH_INTERVAL_DAYS):
                logger.info("🔍 Плановая проверка токена...")
                if not check_token_validity():
                    refresh_token()
                else:
                    logger.info("✅ Токен всё ещё валиден")
                last_refresh_time = datetime.now()

            # Проверяем каждый час, но продлеваем только раз в REFRESH_INTERVAL_DAYS
            time.sleep(3600)  # 1 час

        except Exception as e:
            logger.error(f"Ошибка в проверке токена: {e}")
            time.sleep(3600)


# ========== ФУНКЦИИ ПОСТИНГА ==========
def upload_photo_to_group(vk, group_id, photo_path):
    """Загружает фото в группу"""
    try:
        if not os.path.exists(photo_path):
            logger.error(f"Файл {photo_path} не найден")
            return None

        upload = vk_api.VkUpload(vk)
        photo = upload.photo_wall(photo_path, group_id=abs(int(group_id)))
        return f"photo{photo[0]['owner_id']}_{photo[0]['id']}"
    except Exception as e:
        logger.error(f"Ошибка загрузки фото: {e}")
        return None


def post_to_all_groups():
    """Постит в каждую группу"""
    global post_index

    # Проверяем токен перед каждым постом
    if not check_token_validity():
        logger.warning("⚠️ Токен не валиден, пробуем продлить...")
        if not refresh_token():
            logger.error("❌ Не удалось продлить токен, пропускаем пост")
            return False

    try:
        vk_session = vk_api.VkApi(token=TOKEN)
        vk = vk_session.get_api()

        # Получаем текущий пост
        post_data = POSTS[post_index % len(POSTS)]
        photo_path = os.path.join(PHOTO_DIR, post_data["photo"])

        # Проверяем фото
        if not os.path.exists(photo_path):
            logger.error(f"Фото {photo_path} не существует")
            return False

        success = True

        # Постим во все группы
        for group_id in GROUP_IDS:
            group_id = group_id.strip()
            try:
                attachment = upload_photo_to_group(vk, int(group_id), photo_path)
                if attachment:
                    vk.wall.post(
                        owner_id=int(group_id),
                        message=post_data["text"],
                        attachments=attachment,
                        from_group=1
                    )
                    logger.info(f"✅ Пост в группу {group_id}: {post_data['photo']} - {datetime.now()}")
                else:
                    success = False
            except ApiError as e:
                if e.code == 5:
                    logger.error(f"❌ Токен невалиден при посте в {group_id}")
                    if refresh_token():
                        logger.info("🔄 Токен продлён, повторяем попытку через 10 секунд...")
                        time.sleep(10)
                        # Повторная попытка
                        try:
                            vk_session = vk_api.VkApi(token=TOKEN)
                            vk = vk_session.get_api()
                            attachment = upload_photo_to_group(vk, int(group_id), photo_path)
                            if attachment:
                                vk.wall.post(
                                    owner_id=int(group_id),
                                    message=post_data["text"],
                                    attachments=attachment,
                                    from_group=1
                                )
                                logger.info(f"✅ Пост в группу {group_id} после продления токена")
                                continue
                        except Exception as retry_error:
                            logger.error(f"❌ Ошибка при повторной попытке: {retry_error}")
                    success = False
                else:
                    logger.error(f"API ошибка в группе {group_id}: {e}")
                    success = False
            except Exception as e:
                logger.error(f"Ошибка в группе {group_id}: {e}")
                success = False

        if success:
            post_index += 1  # Следующий пост при следующем запуске

        return success

    except Exception as e:
        logger.error(f"Ошибка авторизации или постинга: {e}")
        return False


def run_poster():
    """Фоновый поток для автопостинга"""
    global running
    global last_refresh_time

    logger.info(f"🚀 Автопостинг запущен. Интервал: {INTERVAL_HOURS} часов")
    logger.info(f"Группы: {GROUP_IDS}")
    logger.info(f"Постов в ротации: {len(POSTS)}")

    # Инициализируем токен
    load_token()
    last_refresh_time = datetime.now()

    # Первый пост через 1 минуту после старта
    time.sleep(60)

    while running:
        try:
            # Проверяем токен раз в сутки
            if datetime.now() - last_refresh_time >= timedelta(days=1):
                check_token_validity()
                last_refresh_time = datetime.now()

            if post_to_all_groups():
                next_time = datetime.now().timestamp() + INTERVAL_HOURS * 3600
                next_str = datetime.fromtimestamp(next_time).strftime('%Y-%m-%d %H:%M:%S')
                         logger.info(f"⏳ Следующий пост в {next_str}")

          # Ждём с проверкой флага
            for _ in range(INTERVAL_HOURS * 60):
                if not running:
                    break
                time.sleep(60)

    except Exception as e:
    logger.error(f"Ошибка в основном цикле: {e}")
    time.sleep(300)  # 5 минут


# ========== ФЛЭСК РОУТЫ ==========
@app.route('/')
def home():
    return '''
        <h1>✅ VK Auto Poster работает!</h1>
        <p>Скрипт активен и публикует посты каждые {} часов.</p>
        <p><a href="/status">Проверить статус</a></p>
        '''.format(INTERVAL_HOURS)


@app.route('/status')
def status():
    token_valid = check_token_validity()
    return jsonify({
        'status': 'running',
        'groups': GROUP_IDS,
        'interval_hours': INTERVAL_HOURS,
        'total_posts': len(POSTS),
        'last_post_index': post_index,
        'token_valid': token_valid,
        'token_expires': 'Бессрочный' if token_valid else 'Истёк',
        'last_token_check': last_refresh_time.isoformat() if last_refresh_time else None,
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/refresh-token', methods=['POST'])
def manual_refresh():
    """Ручное продление токена через API"""
    success = refresh_token()
    return jsonify({
        'status': 'success' if success else 'error',
        'message': 'Токен обновлён' if success else 'Не удалось обновить токен',
        'current_token': TOKEN[:20] + '...' if TOKEN else 'Нет токена'
    })


@app.route('/health')
def health():
    return jsonify({
        'status': 'OK',
        'token_valid': check_token_validity()
    })


# ========== ЗАПУСК ==========
if __name__ == '__main__':
    # Загружаем токен
    load_token()

    # Запускаем автопостинг в фоне
    poster_thread = threading.Thread(target=run_poster, daemon=True)
    poster_thread.start()

    # Запускаем периодическую проверку токена
    token_thread = threading.Thread(target=check_and_refresh_token_periodic, daemon=True)
    token_thread.start()

    logger.info("Flask сервер запущен")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
else:
    # Для gunicorn
    logger.info("Запуск под gunicorn, стартуем автопостинг...")

    # Загружаем токен
    load_token()

    # Запускаем автопостинг в фоне
    poster_thread = threading.Thread(target=run_poster, daemon=True)
    poster_thread.start()

    # Запускаем периодическую проверку токена
    token_thread = threading.Thread(target=check_and_refresh_token_periodic, daemon=True)
    token_thread.start()
