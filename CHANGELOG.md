## [0.3.8](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.7...v0.3.8) (2025-02-11)


### Bug Fixes

* profile use for ec2 operations ([3b0c23f](https://github.com/easytocloud/cloudX-proxy/commit/3b0c23f6e6fd2b782ed3e17a8606133435d8f676))

## [0.3.7](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.6...v0.3.7) (2025-02-11)


### Bug Fixes

* removed 1Password support and improved instance monitoring ([c01009a](https://github.com/easytocloud/cloudX-proxy/commit/c01009afb6d90f43768dece909351a8c3ca597ce))

## [0.3.6](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.5...v0.3.6) (2025-02-11)


### Bug Fixes

* 1Password integration repaired ([b8fd8eb](https://github.com/easytocloud/cloudX-proxy/commit/b8fd8eb445e2ccae107b01c796bc5bec1a9fa1d3))

## [0.3.5](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.4...v0.3.5) (2025-02-11)


### Bug Fixes

* repaired 1Password integration and ssh perms ([69f6a24](https://github.com/easytocloud/cloudX-proxy/commit/69f6a249c941044c4dc689c787c12c1a0d0e093a))

## [0.3.4](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.3...v0.3.4) (2025-02-09)

## [0.3.3](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.2...v0.3.3) (2025-02-09)

## [0.3.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.1...v0.3.2) (2025-02-09)

## [0.3.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.0...v0.3.1) (2025-02-09)


### Bug Fixes

* align ssh key parameter name in core module ([e121280](https://github.com/easytocloud/cloudX-proxy/commit/e121280213e9c762677882283324a382250b2a79))

# [0.3.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.2.0...v0.3.0) (2025-02-09)


### Bug Fixes

* improve SSH key message and config header ([94dd9b6](https://github.com/easytocloud/cloudX-proxy/commit/94dd9b6bd42b2b23e2e732470adf0096aa98e0fb))
* improve UI formatting and progress tracking ([570a0de](https://github.com/easytocloud/cloudX-proxy/commit/570a0deab309f42ee8c961062596189f8d5d6a91))
* only include non-default parameters in ProxyCommand ([e1ecae9](https://github.com/easytocloud/cloudX-proxy/commit/e1ecae9fd91ae1bbed92d60ed384a0e405269a35))
* simplify setup UI and improve error handling ([613cba3](https://github.com/easytocloud/cloudX-proxy/commit/613cba3596c5631d7125c814f0f829c7171ff529))
* update branding to cloudx-proxy ([b354d84](https://github.com/easytocloud/cloudX-proxy/commit/b354d84d99005d11f51212ce70d40c0d36ea47dd))


### Features

* add status indicators to instance setup check ([dfb3624](https://github.com/easytocloud/cloudX-proxy/commit/dfb36240583b46a54742306f9eae24e592d65fbe))
* enhance setup UI with progress bar, colors, and summary ([f72efd1](https://github.com/easytocloud/cloudX-proxy/commit/f72efd175c7805cfd41605f33d5056e714911972))
* extract default env from IAM user and improve SSH config handling ([25fa9c9](https://github.com/easytocloud/cloudX-proxy/commit/25fa9c976d4ae992e5217680405cd407e613eac3))

# [0.2.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.1.1...v0.2.0) (2025-02-09)


### Features

* add setup checklist and make all steps optional ([46016b8](https://github.com/easytocloud/cloudX-proxy/commit/46016b8fd7f1a1ae42fb34a7ff35365279883ab0))

## [0.1.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.1.0...v0.1.1) (2025-02-09)

# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0](https://github.com/easytocloud/cloudX-proxy/releases/tag/v0.1.0) (2025-02-09)

Initial release with core functionality:

### Features

* SSH proxy command for connecting VSCode to EC2 instances via SSM
* AWS profile configuration with cloudX-{env}-{user} format
* SSH key management with 1Password integration
* Environment-specific SSH config generation
* Instance setup status verification
* Cross-platform support (Windows, macOS, Linux)
* Automatic instance startup if stopped
* SSH key distribution via EC2 Instance Connect
* SSH tunneling through AWS Systems Manager
