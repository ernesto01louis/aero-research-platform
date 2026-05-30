# containers/surrogate-smoke.Dockerfile — Torch + PyG smoke environment for
# the three Stage-08 surrogate baselines (MLP, FNO, MeshGraphNet).
#
# Stage 08 (ADR-008). Lives separately from the jax-fluids SIF: the platform
# does NOT install Torch and JAX in the same SIF (the version matrix +
# memory footprint don't justify the maintenance burden — ADR-008 guardrail).
# Cross-environment data flows via xarray / NumPy / parquet on disk.
#
# Two-step build pattern (inherited from ADR-006/007):
#   1. `buildah bud -f containers/surrogate-smoke.Dockerfile ...`
#   2. `containers/surrogate-smoke.def` bootstraps from the OCI archive.
#
# GPU drivers are NOT in this image — `apptainer exec --nv` at runtime.

ARG CUDA_VERSION=12.4.1
ARG TORCH_VERSION=2.5.1
ARG PYG_VERSION=2.6.1

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS build
ARG TORCH_VERSION
ARG PYG_VERSION

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        python3 \
        python3-dev \
        python3-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/surrogate-venv \
    && /opt/surrogate-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools

ENV PATH=/opt/surrogate-venv/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    CUDA_HOME=/usr/local/cuda

# Torch + CUDA 12.4 wheels (the official PyTorch index for cu124). The
# torch-scatter / torch-sparse companions must match the torch version
# exactly; we pull from PyG's pre-built wheel index.
RUN /opt/surrogate-venv/bin/pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu124 \
        "torch==${TORCH_VERSION}"

# PyG + its CUDA-extension companions. PyG itself is on PyPI; scatter/sparse
# live on PyG's own wheel index.
RUN /opt/surrogate-venv/bin/pip install --no-cache-dir \
        "torch-geometric==${PYG_VERSION}" \
        -f https://data.pyg.org/whl/torch-${TORCH_VERSION}+cu124.html

# Numerics + ML provenance + the surrogate-baseline accessories.
RUN /opt/surrogate-venv/bin/pip install --no-cache-dir \
        "numpy>=1.26,<2.1" \
        "einops>=0.8" \
        "mlflow>=2.20" \
        "h5py>=3.10" \
        "scipy>=1.14"

# --- runtime image ---------------------------------------------------------
FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS runtime
ARG CUDA_VERSION
ARG TORCH_VERSION
ARG PYG_VERSION

LABEL org.aero.component=surrogate-smoke \
      org.aero.purpose="Torch + PyG smoke baselines (MLP / FNO / MeshGraphNet)" \
      org.aero.torch.version=${TORCH_VERSION} \
      org.aero.pyg.version=${PYG_VERSION} \
      org.aero.cuda.version=${CUDA_VERSION} \
      org.aero.stage=08 \
      org.aero.base-image=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 \
      org.aero.maintainer=aero-research-platform

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PATH=/opt/surrogate-venv/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/surrogate-venv/lib/python3.12/site-packages \
    CUDA_HOME=/usr/local/cuda \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/opt/surrogate-venv/lib

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/surrogate-venv /opt/surrogate-venv

RUN mkdir -p /case /work /opt/aero

# Smoke check at build time — imports + version resolution.
RUN /opt/surrogate-venv/bin/python -c \
    "import torch, torch_geometric, einops, mlflow, h5py; print('torch', torch.__version__, 'pyg', torch_geometric.__version__)"

ENTRYPOINT []
CMD ["/bin/bash"]
