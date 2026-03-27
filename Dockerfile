FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

ARG GIT_HASH=unknown
ENV GIT_HASH=$GIT_HASH

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p instance uploads

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
