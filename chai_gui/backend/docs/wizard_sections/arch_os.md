# Architecture & Distribution

Choose the CPU architecture and OS distribution this node should be set
up for. These two values are used to build every registry path the
wizard queries from this point on — version tarballs, release assets,
and container images are all organized by `{arch}/{os_dist}/...` on the
registry.

**Architecture** — e.g. `x86_64`, `aarch64`. This should match the
actual CPU architecture of the target machine(s).

**OS Distribution** — e.g. `rocky9.6`, `almalinux9.7`. The distribution
list is loaded from the registry once an architecture is selected, so it
only shows builds that actually exist for that architecture.

If a distribution you expect isn't listed, double check the architecture
selection first, or confirm with the registry administrator that a build
exists for that combination.
