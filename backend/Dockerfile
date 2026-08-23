FROM python:3.12-slim

# 베이스 이미지 OS 패키지 보안 패치 (Trivy 게이트 ②: util-linux 계열 HIGH CVE 수정판 반영)
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
