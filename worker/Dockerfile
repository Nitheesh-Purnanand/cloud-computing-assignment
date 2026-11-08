FROM python:3.11.10-slim
WORKDIR /app
RUN pip install --no-cache-dir boto3==1.35.76 requests==2.32.3
COPY worker/common.py worker/worker.py ./
COPY prompts/teacher_prompt.txt ./prompts/teacher_prompt.txt
ENV PROMPT_FILE=/app/prompts/teacher_prompt.txt PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]
