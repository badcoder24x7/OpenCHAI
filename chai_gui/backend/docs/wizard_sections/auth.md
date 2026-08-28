# Registry Authentication

This step sets the credentials the wizard uses to talk to the HPC Sangrah
registry for the rest of the run.

**SSL verification** — leave this **off** if the registry uses a
self-signed certificate (the default for most on-prem installs). Turn it
on only once a certificate issued by a trusted CA is installed on the
registry server.

**Auth types**

- **None** — for a registry that allows anonymous read access.
- **Basic** — username + password, sent as an HTTP `Authorization: Basic`
  header on every registry request.
- **Bearer Token** — a pre-issued API token, sent as
  `Authorization: Bearer <token>`.

Clicking **Apply Auth & Load Registry** does a real round trip to the
registry to confirm the credentials are accepted — it no longer just
stores whatever was typed.

**If authentication fails**, you'll see the exact reason (wrong
password, registry unreachable, etc.) and a button to **skip
authentication and continue with local releases only**. That path jumps
straight to the Version step and only shows OpenCHAI versions that are
already downloaded and installed on this machine, so you can still
finish setting up the environment without registry access.
