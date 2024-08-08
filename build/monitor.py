import os
import time
import docker
import requests
import socket
import logging

# Thông tin Telegram từ biến môi trường
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# Đọc danh sách các dịch vụ và cổng dịch vụ từ biến môi trường
def get_service_checks():
    service_checks = []
    index = 1
    while True:
        service_check = os.getenv(f'SERVICE_{index}_NAME')
        if not service_check:
            break
        parts = service_check.split()
        if len(parts) >= 3:
            container_name = parts[0]
            port = int(parts[1])
            service_type = parts[2]
            service_checks.append((container_name, port, service_type))
        index += 1
    return service_checks

service_checks = get_service_checks()

client = docker.from_env()

# Cấu hình logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s', filename='/var/log/container_monitor.log')

# Caching trạng thái dịch vụ
service_cache = {}
cache_ttl = 10  # Thời gian sống của cache (giây)
check_interval = 1  # Thời gian kiểm tra (giây)

# Caching tin nhắn Telegram đã gửi
telegram_message_cache = {}
message_cache_ttl = 10  # Thời gian sống của cache tin nhắn (giây)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    headers = {
        'Accept-Encoding': 'gzip',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=5)
        response.raise_for_status()  # Raise an exception for HTTP errors
        logging.info(f"Đã gửi tin nhắn Telegram: {message}")
    except requests.RequestException as e:
        logging.error(f"Không thể gửi tin nhắn Telegram: {e}")

def is_service_responding(container_name, port, service_type):
    cache_key = (container_name, port, service_type)
    current_time = time.time()
    
    # Xoá cache nếu quá thời gian sống của cache hoặc nếu dịch vụ không phản hồi
    if cache_key in service_cache and (current_time - service_cache[cache_key]['timestamp']) < cache_ttl:
        service_status = service_cache[cache_key]['status']
    else:
        try:
            with socket.create_connection((container_name, port), timeout=2) as conn:
                conn.settimeout(2)
                service_status = True
        except (socket.timeout, ConnectionRefusedError, socket.gaierror) as e:
            service_status = False
            logging.warning(f"Dịch vụ `{service_type}` tại `{container_name}`:{port} không phản hồi: {e}")
        except Exception as e:
            service_status = False
            logging.error(f"Lỗi khi kiểm tra dịch vụ `{service_type}` tại `{container_name}`:{port}: {e}")
        
        service_cache[cache_key] = {'status': service_status, 'timestamp': current_time}
    
    return service_status

def check_and_restart_service(container, port, service_type):
    if not is_service_responding(container.name, port, service_type):
        cache_key = (container.name, port, service_type)
        current_time = time.time()
        
        # Xoá cache tin nhắn nếu quá thời gian sống của cache tin nhắn
        if cache_key in telegram_message_cache and (current_time - telegram_message_cache[cache_key]['timestamp']) < message_cache_ttl:
            return None

        try:
            container.restart()
            message = f"🔄 Dịch vụ *{service_type}* trong container *{container.name}* không hoạt động và đã được khởi động lại."
            logging.error(message)
            telegram_message_cache[cache_key] = {'timestamp': current_time}
            return message
        except Exception as e:
            logging.error(f"Không thể khởi động lại container `{container.name}`: {e}")
            return None

def main():
    containers = {}
    for container_name, _, _ in service_checks:
        try:
            container = client.containers.get(container_name)
            containers[container_name] = container
        except docker.errors.NotFound:
            logging.error(f"Không tìm thấy container `{container_name}`.")
        except Exception as e:
            logging.error(f"Lỗi khi lấy container `{container_name}`: {e}")

    while True:
        start_time = time.time()
        messages = []

        # Kiểm tra và khởi động lại dịch vụ nếu cần
        for container_name, port, service_type in service_checks:
            container = containers.get(container_name)
            if container and container.status == 'running':
                message = check_and_restart_service(container, port, service_type)
                if message:
                    messages.append(message)

        # Gửi tất cả các thông báo cùng một lúc
        if messages:
            for message in messages:
                send_telegram_message(message)

        # Tính toán thời gian để kiểm tra tiếp theo
        elapsed_time = time.time() - start_time
        sleep_time = max(check_interval - elapsed_time, 0)  # Kiểm tra mỗi giây
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()