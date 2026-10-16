FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt pyproject.toml README.md ./
COPY src/ ./src/
COPY main.py ./main.py

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --no-deps -e . \
    && python -m py_compile main.py \
    && mkdir -p /app/outputs

VOLUME ["/app/outputs"]
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "sim", "--smoke", "--output-dir", "/app/outputs/eqg_ablation"]
