#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REV="62df973d32f30537d1303aeda9d026b1c5b28671"
CHECKOUT="$ROOT/CSG"
if [[ -d "$CHECKOUT/.git" ]]; then
  actual="$(git -C "$CHECKOUT" rev-parse HEAD)"
  if [[ "$actual" != "$REV" ]]; then
    echo "CSG checkout at $actual; expected pinned revision $REV" >&2
    exit 2
  fi
else
  rm -rf "$CHECKOUT"
  git clone --filter=blob:none https://github.com/dcpracmatic-prog/CSG.git "$CHECKOUT"
  git -C "$CHECKOUT" checkout "$REV"
fi
cargo test --manifest-path "$CHECKOUT/sello-integridad-rust/Cargo.toml" --lib
cargo test --manifest-path "$ROOT/csg-bridge/Cargo.toml"
cargo build --release --manifest-path "$ROOT/csg-bridge/Cargo.toml"
