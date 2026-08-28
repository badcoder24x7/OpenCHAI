# OpenCHAI Version

Pick the OpenCHAI tarball version to install. Each entry shows:

- **Local** — already downloaded and extracted on this machine. Selecting
  one of these means the Execute step will skip the download entirely and
  only re-apply configuration.
- **Remote** — available on the registry but not yet downloaded here.
  Selecting one of these means the Execute step will download and extract
  it first.
- **Local Only** — present on disk but not found on the registry (for
  example, a version that was manually copied over, or the registry entry
  was later removed). These cannot be re-downloaded if something goes
  wrong with the local copy.

The **size** shown next to each remote version is the tarball's
download size as reported by the registry; for local versions it's the
size already on disk.

If you skipped registry authentication in the Auth step, only **Local**
and **Local Only** versions are shown here — there is nothing to fetch
from a registry you chose not to authenticate against. You can still
complete the full setup using whatever was already downloaded
previously.

Once you select a version, any release-specific assets published for
that exact version on the registry are shown below the version list.
