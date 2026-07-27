# Operator runbook — IP sockets inside Apptainer containers on the aero LXCs

**Status:** applied to `aero-dev` (CT 211) on 2026-07-27, Stage 19.
**Applies to:** every aero LXC that runs solver SIFs. Only `aero-dev` has been changed.

## The symptom

Any process inside `apptainer exec` fails to create an AF_INET or AF_INET6 socket:

```
PermissionError: [Errno 13] Permission denied      # python
opal_ifinit: socket() failed with errno=13         # OpenMPI
The interface "lo" does not have an IP address.    # preCICE socket m2n
```

The same operation succeeds in a plain shell on the same host. AF_UNIX sockets work
inside the container; only IP sockets are refused.

## The cause

Not seccomp, not the LXC, and not the SIF. It is an **AppArmor** denial, visible on the
Proxmox host:

```
apparmor="DENIED" operation="create" class="net" info="failed af match" error=-13
namespace="root//lxc-211_<-var-lib-lxc>" profile="apptainer" comm="python3"
family="inet" sock_type="stream" requested="create" denied="create"
```

Ubuntu 24.04 ships `/etc/apparmor.d/apptainer`, a stub profile whose only stated job is
to permit unprivileged user-namespace creation for the Apptainer starter:

```
profile apptainer /usr/libexec/apptainer/bin/starter{,-suid} flags=(unconfined) {
  include if exists <local/apptainer>
}
```

Because it is a *real* profile, AppArmor network mediation applies to everything running
under it — and the stub lists no `network` rules, so IP socket creation is denied.
`flags=(unconfined)` does not exempt it. Confirmed by elimination:

- the Apptainer seccomp profile at `/etc/apptainer/seccomp-profiles/default.json` lists
  `socket` under `SCMP_ACT_ALLOW` with no argument filter — seccomp is not the cause;
- `su2-v8.sif` is affected identically, so it is not specific to any image;
- `--keep-privs`, `--userns` and `BUILDAH_ISOLATION`-style workarounds make no difference.

**This is the actual mechanism behind the platform note "MPI is blocked in the aero
LXCs"**, carried since Stage 10. It was never an LXC capability limit.

## The change

Written through the profile's own documented site-local hook:

```sh
# on the LXC, as root
cat > /etc/apparmor.d/local/apptainer <<'EOF'
network inet stream,
network inet dgram,
network inet6 stream,
network inet6 dgram,
EOF
apparmor_parser -r /etc/apparmor.d/apptainer
```

Deliberately narrower than a blanket `network,`: raw and packet sockets stay denied. The
file persists across reboots (`apparmor.service` re-parses `/etc/apparmor.d/` at boot).

Verify:

```sh
apptainer exec --no-home /opt/aero/containers/precice-fsi.sif python3 -c \
  'import socket; s=socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.bind(("127.0.0.1",0)); print(s.getsockname())'
```

To revert: `rm /etc/apparmor.d/local/apptainer && apparmor_parser -r /etc/apparmor.d/apptainer`.

## What it does and does not enable

**Enables.** preCICE socket m2n between coupled participants — without it the Stage-19
FSI3 campaign cannot run at all, since the tutorial's `<m2n:sockets>` has no `network`
attribute and preCICE therefore defaults to `lo`.

**Does not enable.** MPI *across hosts*. This restores socket creation inside a
container; it says nothing about the cluster's MPI fabric, and the platform's
serial-only posture on aero-dev is unchanged. If a future stage wants real MPI, that is
a separate investigation — but it should start here rather than re-deriving "MPI is
blocked".

## Security note for the operator

This widens what containerised processes on `aero-dev` may do: any SIF can now open TCP
and UDP sockets. In an unprivileged LXC on a trusted LAN, running only signed
digest-recorded images, that is a reasonable trade for making coupled simulation
possible at all — but it is a real change to the security posture and is recorded here
rather than buried in a commit. It has **not** been applied to any other guest.
