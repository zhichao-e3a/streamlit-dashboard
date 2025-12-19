FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    APP_MODE=test

WORKDIR /app

RUN useradd -m -u 10001 appuser

COPY requirements.txt constraints.txt ./
COPY vendor/ ./vendor/

RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY . /app

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "main_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
