FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home app && mkdir -p /app/var /app/staticfiles && chown -R app:app /app
USER app
RUN DATA_DIR=/tmp/build-state DEBUG=1 python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh","scripts/container-start.sh"]
