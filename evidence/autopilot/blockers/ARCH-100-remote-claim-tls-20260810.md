# Retained blocker: ARCH-100 remote claim publication

- Category: `remote-authority`
- Cause: the controller's `git ls-remote` inspection failed with
  `CRYPT_E_NO_REVOCATION_CHECK` / `getaddrinfo() thread failed to start` while
  inspecting `origin`.
- Attempted command: `autopilot claim ARCH-100 --owner codex:arch-100 --publish-remote`
- Required fix: restore a trusted network path and certificate revocation
  service so GitHub inspection succeeds under the controller's normal secure
  environment.
- Safe retry condition: `git ls-remote origin refs/heads/autopilot/arch-100`
  succeeds without disabling TLS revocation checks.
- Unsafe workaround rejected: disabling certificate revocation validation.

The architecture candidate remains uncompleted until exactly one retained
remote claim can be published and independently inspected.
