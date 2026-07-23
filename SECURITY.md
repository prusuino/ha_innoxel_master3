# Security Policy

## Supported Versions

Only the latest release receives security fixes. Please update to the most
recent version before reporting an issue.

| Version | Supported |
| ------- | --------- |
| latest release | ✅ |
| older releases | ❌ |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting: go to the
[Security tab](https://github.com/prusuino/ha_innoxel_master3/security) of this
repository and click **"Report a vulnerability"**. You will get a response
within a few days. Once a fix is available, the vulnerability will be
disclosed in the release notes.

## Security Considerations

This integration communicates exclusively with an INNOXEL Master 3 controller
on your **local network** — no cloud services are involved and no data leaves
your network.

Things worth knowing:

- The connection uses HTTP with digest authentication on the port configured
  on the master (default 5001). The SOAP protocol of the INNOXEL Master 3
  does not offer TLS, so traffic is not encrypted in transit. Run it on a
  trusted network.
- The credentials of the Innoxel user account are stored by Home Assistant in
  its config entry storage (`.storage`), like credentials of other
  integrations. Use a dedicated Innoxel user for Home Assistant so it can be
  revoked independently.
- **Never expose the INNOXEL Master 3 web interface or SOAP port directly to
  the internet.** If you need remote access, use a VPN or Home Assistant's
  own remote access mechanisms.
