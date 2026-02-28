FROM python:3.12-slim

# Avoid generation of .pyc files and force standard output without buffer to see logs in real time
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Default command and file to run
CMD ["python", "src/main.py"]