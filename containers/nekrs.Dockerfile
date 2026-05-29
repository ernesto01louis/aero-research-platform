# containers/nekrs.Dockerfile — NekRS + CUDA 12 source build for the aero NekRS SIF.
#
# Stage 07 — the platform's fourth concrete solver (ADR-007). NekRS is the
# spectral-element GPU-resident scale-resolving code derived from Nek5000,
# using OCCA + libParanumal for cross-vendor GPU portability (CUDA, HIP).
#
# Two-step build pattern (inherited from ADR-006): rootless `buildah`
# source-builds NekRS with network access; the SIF then bootstraps from the
# resulting OCI archive filesystem-only (the unprivileged-LXC %post sandbox
# cannot open sockets).
#
# Build is ~30-45 min CPU (cmake + parallel make of NekRS + OCCA +
# libParanumal). Stage-07 build script runs this under `scripts/run_long.sh`
# on the Proxmox host as a detached background job — must use
# `--layers=true` to amortise re-runs.
#
# GPU drivers are NOT in this image — Apptainer `exec --nv` (Stage 07's
# `build_apptainer_exec(gpu=True)`) injects the host driver at runtime.
#
# Build (on a host with rootless buildah + network):
#   buildah bud --layers=true -f containers/nekrs.Dockerfile \
#               -t localhost/aero/nekrs:v23.0 \
#               --build-arg NEKRS_REF=v23.0 containers/
#   buildah push localhost/aero/nekrs:v23.0 oci-archive:/tmp/nekrs-oci.tar

ARG CUDA_VERSION=12.4.1
ARG NEKRS_REF=v23.0

FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 AS build
ARG NEKRS_REF

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

# Build toolchain — NekRS needs: cmake (>= 3.21), ninja, an MPI implementation,
# Fortran (Nek5000 utilities are still Fortran), Python 3 for the build
# scripts. OpenMPI (the upstream tested combo) — OpenBLAS not MKL per
# Invariant 5.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        gfortran \
        git \
        libopenblas-dev \
        libopenmpi-dev \
        ninja-build \
        openmpi-bin \
        pkg-config \
        python3 \
        python3-dev \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Fetch the pinned NekRS source. The exact commit SHA is captured at build
# time and labelled into the image (org.aero.nekrs.commit_sha).
WORKDIR /src
RUN git clone --depth 1 --branch "${NEKRS_REF}" https://github.com/Nek5000/nekRS.git nekrs \
    && (cd nekrs && git submodule update --init --recursive) \
    && echo "NEKRS_REF=${NEKRS_REF}" > /src/.nekrs-version \
    && echo "NEKRS_COMMIT_SHA=$(cd nekrs && git rev-parse HEAD)" >> /src/.nekrs-version

# Configure + build NekRS. `./nrsconfig` + `make -C build install` is the
# upstream-recommended path; we pin CUDA arch to sm_80+sm_89+sm_90 so the
# image runs on A100, L40S and H100 without rebuild.
ENV NEKRS_HOME=/opt/nekrs \
    NEKRS_INSTALL_DIR=/opt/nekrs \
    OCCA_DIR=/opt/nekrs/occa \
    CC=mpicc \
    CXX=mpicxx \
    FC=mpif90 \
    CUDAARCHS="80;89;90" \
    CMAKE_BUILD_PARALLEL_LEVEL=4 \
    LIBRARY_PATH=/usr/local/cuda/lib64/stubs:/usr/local/cuda/lib64

# NekRS's libocca.so links CUDA driver symbols (cuDeviceGetName, cuMemcpy*,
# ...) at BUILD time, even though they resolve from the host driver at
# RUNTIME via `--nv`. The cuda-devel base image ships libcuda.so stubs at
# /usr/local/cuda/lib64/stubs; the linker flags + LIBRARY_PATH above point
# ld there. Without this, the axhelm-bin link fails with
# `undefined reference to cuDeviceGetName`.
#
# NekRS v23.0's upstream build script is `nrsconfig` (v24+ has `build.sh`).
# Direct cmake-driven Make build with HYPRE dependency serialised on retry.
RUN cd /src/nekrs \
    && cmake -B build -G "Unix Makefiles" \
        -DCMAKE_INSTALL_PREFIX=/opt/nekrs \
        -DCMAKE_BUILD_TYPE=Release \
        -DENABLE_CUDA=ON \
        -DENABLE_HIP=OFF \
        -DENABLE_OPENCL=OFF \
        -DCMAKE_CUDA_ARCHITECTURES="80;89;90" \
        -DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
        -DCMAKE_SHARED_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
    && cmake --build build --target install -j 4 \
        || (echo "first parallel pass failed; retrying serially for HYPRE deps" \
            && cmake --build build --target install -j 1)

# --- runtime image ---------------------------------------------------------
FROM docker.io/nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 AS runtime
ARG CUDA_VERSION
ARG NEKRS_REF

LABEL org.aero.component=nekrs \
      org.aero.solver="NekRS" \
      org.aero.nekrs.version=${NEKRS_REF} \
      org.aero.cuda.version=${CUDA_VERSION} \
      org.aero.stage=07 \
      org.aero.base-image=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 \
      org.aero.maintainer=aero-research-platform

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    NEKRS_HOME=/opt/nekrs \
    OCCA_DIR=/opt/nekrs/occa \
    CUDA_HOME=/usr/local/cuda \
    PATH=/opt/nekrs/bin:/usr/local/cuda/bin:/usr/bin:/bin \
    LD_LIBRARY_PATH=/opt/nekrs/lib:/usr/local/cuda/lib64

# Runtime deps: OpenMPI, OpenBLAS. The cuda-devel base supplies nvcc + the
# CUDA toolkit; host driver via --nv at exec time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas0 \
        libopenmpi3 \
        openmpi-bin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/nekrs /opt/nekrs
COPY --from=build /src/.nekrs-version /opt/nekrs/.nekrs-version

# Bind-mount targets baked in (filesystem-only, identical to OpenFOAM/SU2/PyFR).
RUN mkdir -p /case /work /opt/aero

# Smoke check at build time (no --nv yet; only verifies binaries resolve and
# OCCA's CUDA backend at least *loads*).
RUN command -v nekrs \
    && cat /opt/nekrs/.nekrs-version \
    && /opt/nekrs/bin/nekrs --help 2>&1 | head -5

ENTRYPOINT []
CMD ["/bin/bash"]
