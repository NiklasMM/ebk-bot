# Dockerimage for the ebk-bot
#
# This Dockerfile adheres to the best practices for Dockerfiles please consider
# this when modifying the file
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/

FROM python:3.8.6-alpine3.12

COPY requirements.txt /ebk-bot/requirements.txt
WORKDIR /ebk-bot
# Install temporary packages
RUN apk update && apk add --no-cache --virtual .build-deps \
    gcc \
    libffi-dev \
    libressl-dev \
    musl-dev \
    && pip install -r ./requirements.txt \
    && apk del .build-deps

COPY bot.py /ebk-bot/bot.py

CMD ["python", "bot.py"]
