FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt

COPY . .

ENV DB_MODE=auto
ENV MONGO_URI=mongodb://mongo:27017
ENV MONGO_DB=satquery_dev
ENV DEMO_MODE=auto
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["python", "run.py"]
