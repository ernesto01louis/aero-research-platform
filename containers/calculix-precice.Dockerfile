# containers/calculix-precice.Dockerfile — CalculiX + preCICE adapter (Stage 19, ADR-035).
#
# The APPLICATION solid solver, built here so Stage 20's flexible flapping wing does not
# block on container work. ADR-016 keeps two solid solvers on purpose: the coupling
# verification rides the supported Turek-Hron tutorial (Nutils), while the application
# needs shell/membrane elements that CalculiX supports and Nutils does not. Those are
# deliberately DISTINCT claims.
#
# CalculiX is GPL-2-or-later, which Invariant 5's line ("GPL-3 / LGPL-3 / Apache-2.0 /
# BSD-3") does not name. ADR-035 records the disposition: the list states a copyleft-
# friendly posture rather than an exhaustive whitelist, "or later" makes it GPL-3
# compatible, and it ships as a separate container invoked as a subprocess, never linked
# into aero/.
#
# Built by scripts/build_calculix_sif.sh (buildah on aero-build), then bootstrapped into
# a SIF by containers/calculix-precice.def with a filesystem-only %post.

ARG PRECICE_VERSION=3.4.1
ARG CALCULIX_VERSION=2.20
ARG CALCULIX_ADAPTER_REF=v2.20.1

# Same Ubuntu 24.04 digest the SU2 image uses.
FROM docker.io/library/ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b AS build

ARG PRECICE_VERSION
ARG CALCULIX_VERSION
ARG CALCULIX_ADAPTER_REF

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget git make patch \
        build-essential gfortran \
        libarpack2-dev libspooles-dev libyaml-cpp-dev \
        libopenmpi-dev openmpi-bin pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q "https://github.com/precice/precice/releases/download/v${PRECICE_VERSION}/libprecice3_${PRECICE_VERSION}_noble.deb" \
    && echo "3a36a40254acae06409d067381df1b68c309cc4ffb1b1d15590e1fa5359be888  libprecice3_${PRECICE_VERSION}_noble.deb" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends "./libprecice3_${PRECICE_VERSION}_noble.deb" \
    && rm -f "libprecice3_${PRECICE_VERSION}_noble.deb" \
    && rm -rf /var/lib/apt/lists/*

# CalculiX sources come from dhondt.de over plain HTTP (upstream's own recipe does the
# same). The digest pin, not the transport, is what makes this reproducible — record it
# and verify, and the source cannot change under us.
ARG CCX_SHA256=63bf6ea09e7edcae93e0145b1bb0579ea7ae82e046f6075a27c8145b72761bcf
RUN mkdir -p /src && cd /src \
    && wget -q "http://www.dhondt.de/ccx_${CALCULIX_VERSION}.src.tar.bz2" \
    && (echo "${CCX_SHA256}  ccx_${CALCULIX_VERSION}.src.tar.bz2" | sha256sum -c - \
        || { echo "REFUSING: ccx source digest mismatch — record the new digest deliberately"; \
             sha256sum "ccx_${CALCULIX_VERSION}.src.tar.bz2"; exit 1; }) \
    && tar xjf "ccx_${CALCULIX_VERSION}.src.tar.bz2"

# gfortran >= 10 rejects the argument-type mismatches in CalculiX's legacy Fortran
# without -fallow-argument-mismatch.
RUN git clone https://github.com/precice/calculix-adapter.git /src/calculix-adapter \
    && cd /src/calculix-adapter \
    && git checkout "${CALCULIX_ADAPTER_REF}" \
    && mkdir -p /opt/aero \
    && git rev-parse HEAD > /opt/aero/calculix-adapter.commit \
    && make CCX="/src/CalculiX/ccx_${CALCULIX_VERSION}/src" \
            SPOOLES_INCLUDE="-I/usr/include/spooles" \
            ADDITIONAL_FFLAGS="-fallow-argument-mismatch" \
            -j "$(nproc)" \
    && mkdir -p /opt/calculix/bin \
    && cp bin/ccx_preCICE /opt/calculix/bin/

FROM docker.io/library/ubuntu@sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b AS runtime

ARG PRECICE_VERSION

LABEL org.aero.component   ="calculix-precice"
LABEL org.aero.stage       ="19"
LABEL org.aero.solver      ="CalculiX 2.20 + preCICE adapter v2.20.1"
LABEL org.aero.maintainer  ="aero-research-platform"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget \
        libarpack2t64 libspooles2.2 libyaml-cpp0.8 \
        libgfortran5 libgomp1 openmpi-bin \
    && wget -q "https://github.com/precice/precice/releases/download/v${PRECICE_VERSION}/libprecice3_${PRECICE_VERSION}_noble.deb" \
    && apt-get install -y --no-install-recommends "./libprecice3_${PRECICE_VERSION}_noble.deb" \
    && rm -f "libprecice3_${PRECICE_VERSION}_noble.deb" \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/calculix /opt/calculix
COPY --from=build /opt/aero/calculix-adapter.commit /opt/aero/calculix-adapter.commit

ENV PATH=/opt/calculix/bin:$PATH
ENV OMP_NUM_THREADS=1

RUN mkdir -p /case /work /opt/aero && ldconfig

RUN ccx_preCICE -v || true

ENTRYPOINT []
CMD ["/bin/bash"]
