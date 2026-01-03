FROM python:3.13-slim

# Install dependencies
RUN apt-get update && apt-get install -y ffmpeg curl nodejs npm

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
EXPOSE 8080