FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Bot_TG.py database.py payments.py utilities.py ./

CMD ["python", "Bot_TG.py"]
