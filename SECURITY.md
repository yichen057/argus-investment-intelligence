# Security Policy

Argus is a local-first research and decision-support project. It does not place
trades and should not be treated as a brokerage execution system.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting when it is enabled for the
repository. Do not include credentials, brokerage tokens, portfolio exports,
or other personal financial data in a public issue.

If private reporting is not available, open a public issue containing only a
high-level description and request a private contact channel.

## Secret handling

Keep all local secrets in ignored files such as `.env` or `configs/local/`.
Use `.env.example` for documented variable names and synthetic values only.
Before publishing changes, verify that API keys, OAuth credentials, Terraform
state, and real portfolio data are absent from both the working tree and Git
history.
