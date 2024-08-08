# Chọn image python phù hợp
FROM python:3.9.19-slim-bookworm

# Thiết lập thư mục làm việc
WORKDIR /app

# Sao chép các file cần thiết vào container
COPY requirements.txt /app/
COPY monitor.py /app/

# Cài đặt các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# Thiết lập lệnh mặc định để chạy script
CMD ["python", "monitor.py"]
