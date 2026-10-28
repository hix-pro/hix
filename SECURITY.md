# Security policy

## Supported versions

`hix` is pre-1.0. Security fixes land on the latest release line.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Use GitHub's private reporting:

<https://github.com/hix-pro/hix/security/advisories/new>

Include:

- The `hix` version and Python version
- The command you ran
- The smallest config and repository layout that reproduces the issue
- What you expected and what happened

You should get an acknowledgement within a few days. Please give a reasonable window to ship a fix before publishing details.

## Scope

`hix` starts local processes and prints their output. Relevant reports include command injection through config values, path traversal in config discovery, terminal escape injection in report output, and crashes that expose environment variables.

`hix` has no backend, account system, or telemetry. It does not transmit repository contents anywhere. The tools it runs have their own security policies; report issues in those repositories when the root cause is inside the tool.

## Handling secrets in reports

Some tools intentionally redact secret values. If a report includes a live credential, rotate it first, then report the redaction bug with the value removed. Never paste a working secret into an issue or advisory.
