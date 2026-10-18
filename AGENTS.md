# Personal Tapo source and validation

- Private VM300 hallyaus/Tapo, SSH2222 with the personal key, is origin.
  Preserve default branch claude/hacs-home-assistant-devices-fbx5bj, all other refs, tags and dirty local work.
  Push completed source to Gitea first, then identical public GitHub recovery.
  GitHub Actions stay disabled; recovery must not build, deploy or publish.
- The personal runner retains the original official hassfest gate and adds
  static Python/JSON checks plus an exact-source private candidate. There were
  no original automated unit tests; syntax is not runtime/device validation.
- Never perform cloud sign-in/2FA, LAN discovery or switch/light/device commands as migration tests.
  Do not install/reload the integration or restart Home Assistant. Preserve
  component code, advertised minimum, manifest version and published tags.
- Existing public HACS source URLs remain compatibility hosting. Official
  HACS validation is a separate manual exact-public-source gate, requiring
  the approved repository-only HACS_PUBLIC_READ_TOKEN; no ignored checks or
  borrowed Gitea/M4T token. Do not expose the private primary or publish assets.
- Restore the original Monday04UTC cadence only after complete initial proof
  and inert recovery. No physical safety or release certification follows
  from CI. Keep M4T, Proxmox.99 and Kidde untouched; existing allowances only.
