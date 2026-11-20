# Derived from the original Lab 3 Dockerfile; old lab files stay unchanged.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 90 -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "15", "--graceful-timeout", "5", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
