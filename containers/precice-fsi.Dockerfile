# containers/precice-fsi.Dockerfile — the coupled Turek-Hron FSI3 stack (Stage 19, ADR-035).
#
# One image carrying both participants: OpenFOAM-ESI v2412 (fluid) with the
# preCICE OpenFOAM adapter, and a Nutils solid in its own virtualenv. One image,
# because the four-fold provenance tuple carries exactly one container_sif_sha256
# and a gated coupled run must not silently span two digests (ADR-035).
#
# The base is the SAME digest as openfoam-esi.sif, so pimpleFoam here is byte-identical
# to the platform's already-validated OpenFOAM.
#
# Every version below comes from upstream preCICE's own attested
# tools/tests/reference_versions.yaml at the pinned tutorials commit — the file its CI
# uses to generate the reference results — not from our judgement.
#
# Built by scripts/build_precice_fsi_sif.sh: buildah runs on the PROXMOX HOST (aero-build
# is an unprivileged LXC, where a nested user namespace cannot map the subuid range, so
# buildah's networking never comes up), then containers/precice-fsi.def bootstraps the
# SIF from the resulting OCI archive on aero-build with a %post that does NO network work.

ARG PRECICE_VERSION=3.4.1
ARG PYPRECICE_VERSION=3.4.0
# precice/openfoam-adapter @ develop, 2026-05-27. The last TAGGED release (v1.3.1,
# 2024-06) predates OpenFOAM v2412 and master has not moved since, so a tag would not
# build against this base. This commit is the one upstream's own container recipe builds
# against v2412.
ARG OPENFOAM_ADAPTER_REF=2c3062ce941915616ac763371805c57e15e02466

FROM docker.io/opencfd/openfoam-default@sha256:1ba02114b1c025c370f2e269a07677c16c9bea8d990fcd75ac8378aff9d41b50

ARG PRECICE_VERSION
ARG PYPRECICE_VERSION
ARG OPENFOAM_ADAPTER_REF

LABEL org.aero.component   ="precice-fsi"
LABEL org.aero.stage       ="19"
LABEL org.aero.solver      ="preCICE 3.4.1 (OpenFOAM-ESI v2412 + Nutils)"
LABEL org.aero.base-image  ="opencfd/openfoam-default:2412"
LABEL org.aero.maintainer  ="aero-research-platform"

ENV DEBIAN_FRONTEND=noninteractive

# pkg-config is what the adapter's Allwmake uses to find preCICE; python3-dev and
# libopenmpi-dev are what pyprecice needs to build from sdist (it has no wheels).
# The X/GL libraries are gmsh's runtime dependencies — the solid meshes itself headless
# from solid.geo at start-up.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget git pkg-config build-essential \
        python3 python3-venv python3-dev \
        libopenmpi-dev openmpi-bin \
        libglu1-mesa libxrender1 libxcursor1 libxft2 libxinerama1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# --- preCICE from the official Ubuntu 24.04 ("noble") package ------------------------
# The .deb is self-sufficient: headers (so pyprecice can build), libprecice.pc (so
# Allwmake's pkg-config probe succeeds) and precice-config-validate (gate C3). No
# source build, so no PETSc/Boost/Eigen build dependencies either.
RUN wget -q "https://github.com/precice/precice/releases/download/v${PRECICE_VERSION}/libprecice3_${PRECICE_VERSION}_noble.deb" \
    && echo "3a36a40254acae06409d067381df1b68c309cc4ffb1b1d15590e1fa5359be888  libprecice3_${PRECICE_VERSION}_noble.deb" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends "./libprecice3_${PRECICE_VERSION}_noble.deb" \
    && rm -f "libprecice3_${PRECICE_VERSION}_noble.deb" \
    && rm -rf /var/lib/apt/lists/*

# --- the OpenFOAM-preCICE adapter ----------------------------------------------------
# PRECICE_OPENFOAM_TARGET_DIR=$FOAM_LIBBIN is load-bearing, not tidiness. The adapter's
# default target is $FOAM_USER_LIBBIN, which lives under $HOME — and apptainer
# bind-mounts the HOST $HOME by default, so a host ~/OpenFOAM tree would shadow the
# image's copy and controlDict's `libs (...)` line would fail to load the adapter at RUN
# time, long after the build looked fine. Participants additionally run with --no-home.
RUN git clone https://github.com/precice/openfoam-adapter.git /src/openfoam-adapter \
    && cd /src/openfoam-adapter \
    && git checkout "${OPENFOAM_ADAPTER_REF}" \
    && mkdir -p /opt/aero \
    && git rev-parse HEAD > /opt/aero/openfoam-adapter.commit \
    && bash -lc 'cd /src/openfoam-adapter && PRECICE_OPENFOAM_TARGET_DIR=$FOAM_LIBBIN ./Allwmake -j "$(nproc)"'

# --- the Nutils solid participant, in its own venv -----------------------------------
# nutils 9.x requires numpy<2 while the aero platform core requires numpy>=2, so this
# stack is isolated here and never enters the aero[precice] extra. Versions are
# upstream's own solid-nutils/requirements-reference.txt at the pinned commit.
RUN python3 -m venv /opt/aero/solid-venv \
    && /opt/aero/solid-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/aero/solid-venv/bin/pip install --no-cache-dir \
        "setuptools==83.0.0" \
        "nutils==9.2" \
        "numpy==1.26.4" \
        "pyprecice==${PYPRECICE_VERSION}" \
        "meshio==5.3.5" \
        "gmsh==4.15.2" \
        "matplotlib==3.11.1" \
    && /opt/aero/solid-venv/bin/pip freeze > /opt/aero/solid-venv-freeze.txt

# Upstream's solid-nutils/run.sh calls `python solid.py`; PRECICE_TUTORIALS_NO_VENV
# makes it skip building a venv from the network (which the SIF can neither do nor
# needs to), so the venv's interpreter has to be the one on PATH.
ENV PATH=/opt/aero/solid-venv/bin:$PATH
ENV PRECICE_TUTORIALS_NO_VENV=1
ENV AERO_SOLID_PYTHON=/opt/aero/solid-venv/bin/python

RUN mkdir -p /case /work /opt/aero

# --- build-time smoke: every interface the coupled run actually uses ------------------
RUN precice-version \
    && precice-config-validate --help > /dev/null \
    && bash -lc 'ls "$FOAM_LIBBIN/libpreciceAdapterFunctionObject.so"' \
    && bash -lc 'command -v pimpleFoam blockMesh' \
    && python3 -c "import precice, nutils, numpy, gmsh; print('precice', precice.__version__, 'nutils', nutils.version, 'numpy', numpy.__version__)"

ENTRYPOINT []
CMD ["/bin/bash"]
