FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY config ./config
RUN pip install --no-cache-dir -e .

EXPOSE 8765
VOLUME ["/app/data", "/app/outputs"]

CMD ["tmtrans", "serve", "--host", "0.0.0.0", "--port", "8765"]
