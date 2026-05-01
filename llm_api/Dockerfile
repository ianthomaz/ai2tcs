FROM python:3.12-slim

WORKDIR /app

# Install Node.js for Prisma CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm ffmpeg \
    tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pin Prisma 6 (v7 changed datasource config)
RUN npm install prisma@6 --save-dev

EXPOSE 28471

CMD ["sh", "-c", "npx prisma migrate deploy --schema=prisma/schema.prisma && uvicorn app.main:app --host 0.0.0.0 --port 28471"]
