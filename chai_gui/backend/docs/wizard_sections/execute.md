# Execute — Download & Configure

This step downloads the selected tarball (if it isn't already local),
extracts it, and optionally updates `group_vars/all.yml` and
`ansible.cfg` to point at the newly installed version.

Review the summary table before starting — architecture, OS
distribution, version, and tarball name are all locked in from the
previous steps and cannot be changed without going back.

If **"Update configs"** is enabled, the wizard rewrites the Ansible
config files so subsequent playbook runs use this version automatically.
Turn this off if you want to install a version side-by-side without
switching the active configuration yet.

Progress streams live below once you click **Install OpenCHAI**. If the
job fails, use **Retry** to attempt it again without re-entering any of
the previous steps.




Hehehhehehehe
