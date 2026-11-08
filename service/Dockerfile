# Build from the repository root: docker build -f service/Dockerfile -t ccproj-parser:latest .
# The image holds no model weights; they are downloaded from object storage at start-up.
FROM python:3.11.10-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /app
COPY service/requirements.txt .
RUN pip install -r requirements.txt
COPY service/app.py training/prompting.py data/schema.json ./
RUN useradd -m -u 1000 app
USER 1000
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
