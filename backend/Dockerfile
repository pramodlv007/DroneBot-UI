FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV DEPLOYMENT_MODE=SIMULATION \
    ROBOTS_CONFIG_PATH=/config/robots.yaml \
    MISSION_CONFIG_PATH=/config/mission.yaml \
    SYSTEM_CONFIG_PATH=/config/system.yaml

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
