# containers/su2-v8.Dockerfile — SU2 v8 source build for the aero SU2 SIF.
#
# Stage 06 — the platform's second concrete solver. The unprivileged
# `aero-build` LXC cannot open sockets inside an Apptainer `%post` build
# sandbox (Stage 02 §6), but rootless `buildah`/`podman` (slirp4netns) on the
# same LXC can — so the SU2 source compile runs *here* with full network
# access, and the Apptainer `.def` bootstraps from the resulting OCI image
# filesystem-only (ADR-006). The OpenFOAM SIF uses the same two-step pattern
# (it bootstrapped from a prebuilt upstream image); SU2 needs flags upstream
# images may lack (autodiff, Mutation++, pysu2), hence the source build.
#
# Build (on a host with rootless buildah/podman + network):
#   buildah bud -f containers/su2-v8.Dockerfile -t localhost/aero/su2-v8:v8.1.0 \
#               --build-arg SU2_VERSION=v8.1.0 containers/
#   buildah push localhost/aero/su2-v8:v8.1.0 oci-archive:/tmp/su2-v8-oci.tar
#   # then `scripts/build_su2_sif.sh` apptainer-builds the SIF from that archive.
#
# Base image pinned by digest (Hard Rule 8); the exact SU2 git tag + commit SHA
# are captured in ADR-006 after a build.

ARG SU2_VERSION=v8.1.0

FROM ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b AS build
ARG SU2_VERSION

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

# Build toolchain + MPI + OpenBLAS (no Intel MKL — Stage-06 guardrail 6 /
# Constitution Invariant 5: GPL-3 / Apache-2.0 / BSD only).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        g++ \
        gfortran \
        git \
        libopenblas-dev \
        libopenmpi-dev \
        libtool \
        meson \
        ninja-build \
        openmpi-bin \
        pkg-config \
        python3 \
        python3-dev \
        python3-mpi4py \
        python3-numpy \
        python3-pip \
        swig \
    && rm -rf /var/lib/apt/lists/*

# Fetch the pinned SU2 source. The exact commit SHA is captured at build time
# and labelled into the image (`org.aero.su2.commit_sha`) for the ADR record.
WORKDIR /src
RUN git clone --depth 1 --branch "${SU2_VERSION}" https://github.com/su2code/SU2.git su2 \
    && (cd su2 && git submodule update --init --recursive) \
    && echo "SU2_COMMIT_SHA=$(cd su2 && git rev-parse HEAD)" > /src/.su2-commit

# Configure + build SU2 with the platform's required flags:
#   * enable-pywrapper  — pysu2 Python bindings
#   * enable-autodiff   — discrete adjoint (SU2_CFD_AD)
#   * enable-mpp        — Mutation++ (the future-hypersonic path; built, not
#                         yet exercised in Stage 06)
RUN cd /src/su2 \
    && ./meson.py build \
        --buildtype=release \
        --prefix=/opt/su2 \
        -Dwith-mpi=enabled \
        -Denable-pywrapper=true \
        -Denable-autodiff=true \
        -Denable-mpp=true \
    && ./ninja -C build install -j"$(nproc)"

# --- runtime image ---------------------------------------------------------
FROM ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b AS runtime
ARG SU2_VERSION

LABEL org.aero.component=su2 \
      org.aero.solver="SU2 v8" \
      org.aero.su2.version=${SU2_VERSION} \
      org.aero.stage=06 \
      org.aero.base-image=ubuntu:24.04 \
      org.aero.maintainer=aero-research-platform

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    SU2_HOME=/opt/su2 \
    SU2_RUN=/opt/su2/bin \
    PATH=/opt/su2/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/su2/bin \
    LD_LIBRARY_PATH=/opt/su2/lib

# Minimal runtime deps: OpenMPI, OpenBLAS, Python + numpy + mpi4py.
# `libpython3.12` (not pulled by python3 alone) is needed at runtime because
# SU2 v8's _pysu2.so links libpython3.12.so.1.0 directly — without it the
# `import pysu2` smoke check fails with a missing-shared-object ImportError.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopenblas0 \
        libopenmpi3 \
        libpython3.12 \
        openmpi-bin \
        python3 \
        python3-mpi4py \
        python3-numpy \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/su2 /opt/su2
COPY --from=build /src/.su2-commit /opt/su2/.su2-commit
# Mutationpp's libmutation__.so is built as a meson subproject *for linking*
# but never `install`-ed by SU2 v8 — it only exists under /src/su2/build/.
# Stage 1's pysu2 shared object links it; without it on the runtime image
# `import pysu2` fails with `libmutation__.so: cannot open shared object file`.
# Copy it explicitly into /opt/su2/lib so the ld.so.conf.d entry below resolves.
COPY --from=build /src/su2/build/subprojects/Mutationpp/libmutation__.so /opt/su2/lib/libmutation__.so

# Bind-mount targets baked in (filesystem-only, identical to the OpenFOAM SIF).
# Register /opt/su2/lib with the dynamic loader so pysu2's transitive link to
# libmutation__.so resolves at import time without needing LD_LIBRARY_PATH set
# by the caller. The ENV LD_LIBRARY_PATH above is the belt; ldconfig is the
# braces (some shells reset LD_LIBRARY_PATH, e.g. `bash -lc` may not inherit
# from the ENV reliably across Apptainer's environment shim).
RUN mkdir -p /case /work /opt/aero \
    && echo "/opt/su2/lib" >/etc/ld.so.conf.d/aero-su2.conf \
    && /sbin/ldconfig

# Smoke check — `SU2_CFD` resolves and pysu2 imports. Print the libmutation
# location to the build log so any future relocation surfaces immediately.
# `ldconfig` lives in /sbin which isn't on the minimal-image $PATH.
RUN command -v SU2_CFD \
    && find /opt/su2 -name 'libmutation*' -print \
    && /sbin/ldconfig -p | grep -i mutation \
    && python3 -c "import pysu2" \
    && cat /opt/su2/.su2-commit

ENTRYPOINT []
CMD ["/bin/bash"]
