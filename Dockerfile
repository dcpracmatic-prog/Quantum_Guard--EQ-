FROM rust:1.85-slim AS csg-builder
ARG CSG_REV=62df973d32f30537d1303aeda9d026b1c5b28671
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone https://github.com/dcpracmatic-prog/CSG.git /src/CSG \
    && git -C /src/CSG checkout "$CSG_REV" \
    && test "$(git -C /src/CSG rev-parse HEAD)" = "$CSG_REV"
COPY csg-bridge/ ./csg-bridge/
RUN cargo test --manifest-path /src/CSG/sello-integridad-rust/Cargo.toml --lib \
    && cargo test --manifest-path csg-bridge/Cargo.toml \
    && cargo build --release --manifest-path csg-bridge/Cargo.toml

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY csg-bridge/ ./csg-bridge/
COPY config/ ./config/
COPY main.py ./main.py

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV LD_PRELOAD=libgomp.so.1
COPY --from=csg-builder /src/csg-bridge/target/release/eqg-csg-bridge /usr/local/bin/eqg-csg-bridge

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --no-deps -e . \
    && python -m py_compile main.py \
    && test -x /usr/local/bin/eqg-csg-bridge \
    && mkdir -p /app/outputs

VOLUME ["/app/outputs"]
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "sim", "--smoke", "--output-dir", "/app/outputs/eqg_ablation"]
