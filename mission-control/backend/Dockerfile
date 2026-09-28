FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MC_HOST=0.0.0.0
ENV MC_PORT=8100

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]