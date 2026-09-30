# Security policy

INET is designed as a **local, single-user** service: ports bind to `127.0.0.1` and the API has
no authentication. Do not expose it to the internet without your own authentication and egress controls.

Security boundaries worth reporting issues against:

- SSRF protection in the HTTP client and browser (private and service addresses must be blocked);
- the sandbox service (generated code must not reach the Docker socket, host files, secrets or private networks);
- secret storage (keys must never be returned to the UI or written to logs).

Please report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/JGSnapp/inet/security/advisories/new) rather than public issues.
