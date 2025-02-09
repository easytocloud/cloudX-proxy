# [2026.0.0](https://github.com/easytocloud/cloudX-proxy/compare/2025.3.0...2026.0.0) (2025-02-09)


* "feat!: add setup command and restructure CLI ([0ad983e](https://github.com/easytocloud/cloudX-proxy/commit/0ad983e42da10856e420f207bec069aa523fc314))


### BREAKING CHANGES

* The main command now requires connect subcommand for connections.
Previous: uvx cloudx-proxy i-1234567890
New: uvx cloudx-proxy connect i-1234567890

Added setup command that automates:
- AWS profile configuration with cloudX-{env}-{user} format
- SSH key management with 1Password integration
- Environment-specific SSH config generation
- Instance setup status verification"

# [2025.3.0](https://github.com/easytocloud/cloudX-proxy/compare/2025.2.4...2025.3.0) (2025-02-08)


### Bug Fixes

* set explicit repository URL in semantic-release config ([8b4f941](https://github.com/easytocloud/cloudX-proxy/commit/8b4f94194ce28a7f3830ef279d390dea4814251a))
* update semantic-release config to ensure releases ([6c51d01](https://github.com/easytocloud/cloudX-proxy/commit/6c51d014438f035176ecf8171ff0ee0b21948f6e))


### Features

* force new release for cloudx-proxy ([3cf3996](https://github.com/easytocloud/cloudX-proxy/commit/3cf3996f59533012f64261b2f593927fee7855b3))
* prepare initial release as cloudx-proxy ([986f1b7](https://github.com/easytocloud/cloudX-proxy/commit/986f1b7791ce4a6d213e743e5e2e902149639fdf))
* rename package to cloudx-proxy for PyPI publishing ([b1ffcc6](https://github.com/easytocloud/cloudX-proxy/commit/b1ffcc62b10f259fb42fb10cb9b5ecc0acc48d1b))
* trigger release with correct repository configuration ([45adbf1](https://github.com/easytocloud/cloudX-proxy/commit/45adbf13522f6352bb86fac8a9d51c4644892c1d))

## [2025.2.4](https://github.com/easytocloud/cloudX-client/compare/2025.2.3...2025.2.4) (2025-02-08)


### Bug Fixes

* proper stdin/stdout handling for SSH ProxyCommand ([760808c](https://github.com/easytocloud/cloudX-client/commit/760808c0498e865681795d5125b80c0808432ef3))

## [2025.2.3](https://github.com/easytocloud/cloudX-client/compare/2025.2.2...2025.2.3) (2025-02-08)


### Bug Fixes

* add Windows compatibility for SSH ProxyCommand ([e0e798d](https://github.com/easytocloud/cloudX-client/commit/e0e798d16b64d59c3dfb3493d30b590019b25855))

## [2025.2.2](https://github.com/easytocloud/cloudX-client/compare/2025.2.1...2025.2.2) (2025-02-08)


### Bug Fixes

* use AWS CLI for session start to handle SSH ProxyCommand data transfer ([49cb9c8](https://github.com/easytocloud/cloudX-client/commit/49cb9c86d3a4d25b893d8baea181df229ccabb0d))

## [2025.2.1](https://github.com/easytocloud/cloudX-client/compare/2025.2.0...2025.2.1) (2025-02-08)


### Bug Fixes

* redirect all logging to stderr for SSH ProxyCommand compatibility ([e84035c](https://github.com/easytocloud/cloudX-client/commit/e84035ca81c0cf59adc4d9ce9378da25fe28b367))

# [2025.2.0](https://github.com/easytocloud/cloudX-client/compare/2025.1.0...2025.2.0) (2025-02-08)


### Features

* trigger initial release 2025.1.0 ([3954646](https://github.com/easytocloud/cloudX-client/commit/395464622a3369c11391a64f7f6ce52a1bba2c17))
