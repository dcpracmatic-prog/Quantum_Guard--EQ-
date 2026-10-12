FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt README.md ./
COPY src/ ./src/
COPY main.py ./main.py
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --no-deps -e . \
    && apt-get purge -y --auto-remove gcc \
    && rm -rf /root/.cache/pip

RUN mkdir -p /app/outputs
VOLUME ["/app/outputs"]

ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "sim"]
