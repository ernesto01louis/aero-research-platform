# containers/pyfr.Dockerfile — PyFR + CUDA 12 build for the aero PyFR SIF.
#
# Stage 07 — the platform's third concrete solver (ADR-007). PyFR is the
# high-order flux-reconstruction GPU-resident scale-resolving code; this image
# wraps the upstream PyFR PyPI release on an NVIDIA CUDA base so `pyfr run -b
# cuda` resolves at runtime.
#
# Two-step build pattern (inherited from ADR-006): rootless `buildah` runs the
# pip install with network access; the SIF then bootstraps from the resulting
# OCI archive filesystem-only (the unprivileged-LXC %post sandbox cannot open
# sockets). Stage 06's SU2 SIF used the same flow; Stage 07 inherits it.
#
# GPU drivers are NOT in this image — Apptainer `exec --nv` (Stage 07's
# `build_apptainer_exec(gpu=True)`) injects the host driver at runtime.
# This is required: bundling a driver would lock the SIF to one specific
# NVIDIA driver version on the host.
#
# Build (on a host with rootless buildah + network):
#   buildah bud -f containers/pyfr.Dockerfile -t localhost/aero/pyfr:v1.15.0 \
#               --build-arg PYFR_VERSION=1.15.0 containers/
#   buildah push localhost/aero/pyfr:v1.15.0 oci-archive:/tmp/pyfr-oci.tar
#   # then `scripts/build_pyfr_sif.sh` apptainer-builds the SIF from that archive.

ARG CUDA_VERSION=12.4.1
ARG PYFR_VERSION=1.15.0

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 AS build
ARG PYFR_VERSION

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

# Build/runtime toolchain. PyFR needs: a real Python 3.12 (no system python
# in CUDA-on-jammy by default), MPI, HDF5, OpenBLAS, gmsh (for `pyfr import`
# of native gmsh meshes), and pkg-config for h5py/mpi4py wheels to find their
# native deps. OpenBLAS not Intel MKL — Constitution Invariant 5.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        gmsh \
        libhdf5-dev \
        libopenblas-dev \
        libopenmpi-dev \
        openmpi-bin \
        pkg-config \
        python3.10 \
        python3.10-dev \
        python3.10-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Self-contained venv at /opt/pyfr-venv. PyFR pulls pytools, mako, h5py,
# mpi4py and (for the CUDA backend) pycuda. Pinned versions live in this
# Dockerfile so the OCI image's labels record the resolved build.
RUN python3.10 -m venv /opt/pyfr-venv \
    && /opt/pyfr-venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools

# Build mpi4py against the system OpenMPI; pycuda against the CUDA-base toolkit.
ENV CC=mpicc \
    CXX=mpicxx \
    PATH=/opt/pyfr-venv/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    CUDA_HOME=/usr/local/cuda \
    LIBRARY_PATH=/usr/local/cuda/lib64/stubs:/usr/local/cuda/lib64

# pkg_resources is required by pyfr 1.15.x (its quadrules loader imports it
# unconditionally). setuptools 70+ removed pkg_resources from the default
# distribution; pin <70 so it stays bundled. Python 3.10's venv does not
# include pkg_resources/setuptools out of the box.
RUN /opt/pyfr-venv/bin/pip install --no-cache-dir \
        "setuptools<70" \
        "numpy>=1.26,<2.1" \
        "mpi4py>=4.0" \
        "h5py>=3.10" \
        "mako>=1.3" \
        "pytools>=2024.1" \
        "pycuda>=2024.1" \
        "pyfr==${PYFR_VERSION}"

# --- runtime image ---------------------------------------------------------
FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 AS runtime
ARG CUDA_VERSION
ARG PYFR_VERSION

LABEL org.aero.component=pyfr \
      org.aero.solver="PyFR" \
      org.aero.pyfr.version=${PYFR_VERSION} \
      org.aero.cuda.version=${CUDA_VERSION} \
      org.aero.stage=07 \
      org.aero.base-image=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 \
      org.aero.maintainer=aero-research-platform

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PATH=/opt/pyfr-venv/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/pyfr-venv/lib/python3.10/site-packages \
    CUDA_HOME=/usr/local/cuda \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/opt/pyfr-venv/lib

# Minimal runtime deps for the venv: Python 3.10, OpenMPI, HDF5, OpenBLAS,
# gmsh. PyCUDA at runtime needs the CUDA toolkit's libcuda — the host
# driver supplies it via apptainer --nv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gmsh \
        libhdf5-103 \
        libopenblas0 \
        libopenmpi3 \
        openmpi-bin \
        python3.10 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/pyfr-venv /opt/pyfr-venv

# Bind-mount targets baked in (filesystem-only, identical to OpenFOAM/SU2).
RUN mkdir -p /case /work /opt/aero

# Smoke check at build time (does not need an actual GPU — only the toolkit).
# The CUDA runtime smoke requires --nv at exec time, so we don't try here.
RUN /opt/pyfr-venv/bin/pyfr --help >/dev/null \
    && /opt/pyfr-venv/bin/python -c "import pyfr, mpi4py, h5py, mako" \
    && /opt/pyfr-venv/bin/pyfr --version

ENTRYPOINT []
CMD ["/bin/bash"]
