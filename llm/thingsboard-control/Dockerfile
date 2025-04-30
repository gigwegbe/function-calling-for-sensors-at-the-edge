FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
COPY app.py .
COPY templates/ templates/
COPY models.joblib .
COPY scalers_X.joblib .
COPY scalers_y.joblib .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python3", "app.py"]