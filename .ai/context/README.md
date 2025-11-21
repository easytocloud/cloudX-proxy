# cloudX

## Background

**cloudX** (spelled as cloudX - 'cloud' always lowercase, even at start of sentence - followed by capital X)

### Previous Version

The original cloudX included:

- cloudX-proxy (bash and PowerShell scripts) distributed via GitHub and/or Homebrew
- Backend AWS CloudFormation templates for environment, user, and instance
- Instructions for setting up cloudX-proxy

### Modernized Version

The current version includes everything from the previous version, plus:

- **New Python-based proxy** (separate repository: [cloudX-proxy](https://github.com/easytocloud/cloudx-proxy))
  - Automated setup
  - Written in Python, published on PyPI
  - Works on Mac and Windows
  - Install or run with `uvx`

- Backend AWS CloudFormation templates in original cloudX repository
- Documentation at [easytocloud.github.io](https://easytocloud.github.io) (GitHub Pages)
- Also works with SSO profile
