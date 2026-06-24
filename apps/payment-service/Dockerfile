FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8082

CMD ["gunicorn", "--bind", "0.0.0.0:8082", "--workers", "2", "--threads", "4", "main:app"]
