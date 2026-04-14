FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

RUN pip install fastapi uvicorn aiohttp python-dotenv

COPY poster_server.py .

EXPOSE 8000

CMD ["python", "poster_server.py"]
