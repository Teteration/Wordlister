# Security Policy

## Supported versions

Security fixes are applied to the latest version on the `main` branch. Tagged release support will be documented when the first stable release is published.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature for this repository when available. If it is unavailable, contact the maintainer through the profile associated with the repository and request a private reporting channel.

Do not include exploit details, target data, credentials, or assessment artifacts in a public GitHub issue.

Include a concise impact description, a minimal reproduction using non-sensitive data, affected versions or commits, and a suggested mitigation if known. You should receive an acknowledgement within seven days.

## Scope

Relevant reports include:

- Unexpected disclosure of credentials or secret values in output or diagnostics.
- Redirect, URL-validation, or response-limit bypasses.
- Unsafe file handling or command execution.
- Dependency vulnerabilities with a reachable impact on Wordlister.

Wordlister is an authorized testing utility. Reports about using it against systems without permission are not product vulnerabilities.