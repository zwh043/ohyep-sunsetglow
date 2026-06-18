FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY main.py ./

ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

# 反馈网页端口
EXPOSE 8080

CMD ["python", "main.py"]
