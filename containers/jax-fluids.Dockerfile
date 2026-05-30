# containers/jax-fluids.Dockerfile — JAX-Fluids + CUDA 12 build for the
# aero JAX-Fluids SIF.
#
# Stage 08 — the platform's fifth concrete solver, and the FIRST differentiable
# one (ADR-008). JAX-Fluids 2.x (upstream tag `JAX-Fluids-v0.2.1`, MIT-licensed
# — the stage prompt's GPL-3 assumption was incorrect; see ADR-008 §D2) is a
# pure-JAX compressible CFD code; this image wraps the upstream from
# git+https://github.com/tumaer/JAXFLUIDS.git (JAX-Fluids is NOT on PyPI) on
# an NVIDIA CUDA base so jax-with-cuda12 resolves at runtime.
#
# Two-step build pattern (inherited from ADR-006/007): rootless buildah runs
# the pip install with network; the SIF then bootstraps from the OCI archive
# filesystem-only.
#
# GPU drivers are NOT in this image — `apptainer exec --nv` injects the host
# driver at runtime (the Stage-07 `build_apptainer_exec(gpu=True)` extension).
#
# Ubuntu 24.04 base brings Python 3.12 natively — JAX-Fluids requires Python
# >= 3.11; staying on the same Python the rest of the platform uses keeps
# wheel resolution boring.

ARG CUDA_VERSION=12.8.2
ARG JAXFLUIDS_TAG=JAX-Fluids-v0.2.1

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS build
ARG JAXFLUIDS_TAG

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

# Build/runtime toolchain. JAX-Fluids needs: Python 3.12 (Ubuntu 24.04
# default), HDF5 (jax-fluids writes hdf5 outputs the adapter then reads),
# git (the install is from a git URL), and ca-certificates for HTTPS.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        libhdf5-dev \
        pkg-config \
        python3 \
        python3-dev \
        python3-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Self-contained venv at /opt/jaxfluids-venv.
RUN python3 -m venv /opt/jaxfluids-venv \
    && /opt/jaxfluids-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools

ENV PATH=/opt/jaxfluids-venv/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    CUDA_HOME=/usr/local/cuda \
    LIBRARY_PATH=/usr/local/cuda/lib64/stubs:/usr/local/cuda/lib64

# JAX + jaxlib with the CUDA 12 wheel. Pin a known-compatible JAX (latest
# minor on PyPI at session time; jaxlib must match the JAX version). The
# upstream JAX-Fluids declares the supported matrix in its requirements;
# we pin the matrix here for SIF-build reproducibility.
RUN /opt/jaxfluids-venv/bin/pip install --no-cache-dir \
        "jax[cuda12]==0.4.34" \
        "jaxlib==0.4.34" \
        "flax>=0.10" \
        "optax>=0.2.3" \
        "numpy>=1.26,<2.1" \
        "matplotlib>=3.9" \
        "h5py>=3.10" \
        "gitpython>=3.1"

# Install JAX-Fluids from upstream tag. The package name installed is
# `jaxfluids` (per upstream setup.py).
RUN /opt/jaxfluids-venv/bin/pip install --no-cache-dir \
        "jaxfluids @ git+https://github.com/tumaer/JAXFLUIDS.git@${JAXFLUIDS_TAG}"

# --- runtime image ---------------------------------------------------------
FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS runtime
ARG CUDA_VERSION
ARG JAXFLUIDS_TAG

LABEL org.aero.component=jax-fluids \
      org.aero.solver="JAX-Fluids" \
      org.aero.jax-fluids.version=${JAXFLUIDS_TAG} \
      org.aero.cuda.version=${CUDA_VERSION} \
      org.aero.stage=08 \
      org.aero.base-image=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 \
      org.aero.maintainer=aero-research-platform \
      org.aero.license=MIT

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PATH=/opt/jaxfluids-venv/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/jaxfluids-venv/lib/python3.12/site-packages \
    CUDA_HOME=/usr/local/cuda \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/opt/jaxfluids-venv/lib

# Minimal runtime deps for the venv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libhdf5-103-1t64 \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/jaxfluids-venv /opt/jaxfluids-venv

# Bind-mount targets baked in (identical to OpenFOAM / SU2 / PyFR / NekRS).
RUN mkdir -p /case /work /opt/aero

# Smoke check at build time — module import, version resolution. The CUDA
# runtime smoke needs --nv at exec time so we don't try here.
RUN /opt/jaxfluids-venv/bin/python -c "import jaxfluids, jax, jaxlib, flax, optax, h5py; print('jaxfluids', jaxfluids.__version__)"

ENTRYPOINT []
CMD ["/bin/bash"]
