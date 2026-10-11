FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system simpars && adduser --system --ingroup simpars simpars

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=simpars:simpars . .
RUN python -m compileall -q . && mkdir -p /app/data && chown -R simpars:simpars /app/data

USER simpars
EXPOSE 8080

CMD ["python", "bot.py"]
