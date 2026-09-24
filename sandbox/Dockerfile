FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.52.4 docker==7.1.0
COPY worker.py .
CMD ["uvicorn","worker:app","--host","0.0.0.0","--port","8090"]
