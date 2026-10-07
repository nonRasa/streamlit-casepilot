FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8765
CMD ["python", "run.py", "serve", "--host", "0.0.0.0", "--port", "8765"]
