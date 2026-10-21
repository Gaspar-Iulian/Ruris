FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY requirements-container.lock ./
RUN pip install --no-cache-dir -r requirements-container.lock \
    && groupadd --gid 10001 ruris \
    && useradd --uid 10001 --gid ruris --no-create-home ruris \
    && mkdir -p /data/attachments \
    && chown ruris:ruris /data/attachments

COPY app ./app
COPY migrations ./migrations
COPY gunicorn.conf.py ./
USER ruris
EXPOSE 8000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]
