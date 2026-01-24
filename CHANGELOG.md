## [0.13.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.13.1...v0.13.2) (2026-01-24)

## [0.13.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.13.0...v0.13.1) (2026-01-24)


### Bug Fixes

* use tags when possible to find Environment and hostname ([8dc56d6](https://github.com/easytocloud/cloudX-proxy/commit/8dc56d6d3585e85f61b7bebd5c12a4b3f674b10f))

# [0.13.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.12.0...v0.13.0) (2026-01-16)


### Features

* add consistent colorized output across all commands ([a32a4ee](https://github.com/easytocloud/cloudX-proxy/commit/a32a4ee7a2da210b88ea0b2ce3570c4d8f3550b7))

# [0.12.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.11.1...v0.12.0) (2026-01-09)


### Features

* add EC2 instance ID validation ([25fdba1](https://github.com/easytocloud/cloudX-proxy/commit/25fdba1ea79842d7555b19cdfb9a976823f20487))

## [0.11.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.11.0...v0.11.1) (2026-01-09)


### Bug Fixes

* insert SSH config Include before Host blocks ([005cc07](https://github.com/easytocloud/cloudX-proxy/commit/005cc07de0badfb7bb994792c3d2733ac0f5fbf0))

# [0.11.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.10.2...v0.11.0) (2025-11-22)


### Features

* change default values ([0d6e275](https://github.com/easytocloud/cloudX-proxy/commit/0d6e275173edbf292ffc8879078e104f7b4fd43b))


### BREAKING CHANGES

* change default values for directory, key and profile

## [0.10.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.10.1...v0.10.2) (2025-11-21)


### Bug Fixes

* added reference to cloudX repo for AWS backend ([2c835ef](https://github.com/easytocloud/cloudX-proxy/commit/2c835ef82a44287788003cbf116b24e09509a893))

## [0.10.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.10.0...v0.10.1) (2025-11-21)

# [0.10.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.14...v0.10.0) (2025-11-21)


### Features

* add cloudX-proxy command and restructure documentation ([90b20ec](https://github.com/easytocloud/cloudX-proxy/commit/90b20ec9854fd29b6efc8fc293e05f308c758e0d))

## [0.9.14](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.13...v0.9.14) (2025-11-18)


### Bug Fixes

* improved 1password integration ([5222cd0](https://github.com/easytocloud/cloudX-proxy/commit/5222cd05cd8c629bf88997ec4d398306a60a1209))

## [0.9.13](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.12...v0.9.13) (2025-11-18)

## [0.9.12](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.11...v0.9.12) (2025-11-18)


### Bug Fixes

* handle single .pub file correctly ([1862046](https://github.com/easytocloud/cloudX-proxy/commit/1862046dd14ddc84c2eebf44565fe945cb279b59))

## [0.9.11](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.10...v0.9.11) (2025-11-18)


### Bug Fixes

* empty vault name error ([bf16c6e](https://github.com/easytocloud/cloudX-proxy/commit/bf16c6e03ad1b6216ec17f1fd32ad9ab2c436eff))

## [0.9.10](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.9...v0.9.10) (2025-11-18)


### Bug Fixes

* [1password] default to Private vault ([a394759](https://github.com/easytocloud/cloudX-proxy/commit/a39475909582de2c4b0be1b519a45e58e00607f8))

## [0.9.9](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.8...v0.9.9) (2025-11-18)


### Bug Fixes

* SSO role name check dropped ([63779eb](https://github.com/easytocloud/cloudX-proxy/commit/63779eb42c6a7c2c514ad1307829bcfd5c40f23c))

## [0.9.8](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.7...v0.9.8) (2025-11-17)


### Bug Fixes

* no connection test on Windows ([e58c51e](https://github.com/easytocloud/cloudX-proxy/commit/e58c51e34a9b1c6811da45e07a3e23684ad26a19))

## [0.9.7](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.6...v0.9.7) (2025-11-17)


### Bug Fixes

* added .envrc ([b0f577c](https://github.com/easytocloud/cloudX-proxy/commit/b0f577c002b546c3c395520ff3efff61f31ad91d))
* improve uv sync compatibility and Windows SSH client support ([a4f10cd](https://github.com/easytocloud/cloudX-proxy/commit/a4f10cd1bc2fdb26bf973ed3ccae4e77faa89c3b))

## [Unreleased]

### Fixed
- Fixed uv sync compatibility by removing obsolete setuptools-scm-semver dependency
- Windows SSH client compatibility: Control* directives now commented out by default on Windows
  - Windows' default SSH client doesn't support ControlMaster/ControlPath/ControlPersist
  - Users with alternative SSH clients (e.g., Git for Windows) can uncomment if supported
  - Unix/macOS systems remain unaffected with full multiplexing support

### Changed
- Updated build system to use setuptools_scm>=6.2 without external semver plugin
- Version scheme now uses built-in python-simplified-semver
- `cloudx-proxy setup --1password` now works without a value (defaults to "Private" vault)
- `cloudx-proxy setup --1password VAULT` accepts optional vault name
- 1Password SSH agent socket now uses literal `~/.1password/agent.sock` in SSH config
- Automatic symlink creation on macOS from `~/.1password/agent.sock` to default 1Password location

### Fixed
- Fixed `--1password` option where Click was overwriting the `flag_value` attribute

## [0.9.6](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.5...v0.9.6) (2025-11-14)

## [0.9.5](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.4...v0.9.5) (2025-10-27)

## [0.9.4](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.3...v0.9.4) (2025-09-15)

## [0.9.3](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.2...v0.9.3) (2025-09-12)

## [0.9.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.1...v0.9.2) (2025-09-11)


### Bug Fixes

* PyPI auth ([f6ae22c](https://github.com/easytocloud/cloudX-proxy/commit/f6ae22c6e4b16b8097f509600dd65f4cd4f2a51b))

## [0.9.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.9.0...v0.9.1) (2025-09-11)


### Bug Fixes

* migrated to OIDC for PyPI ([8a698ed](https://github.com/easytocloud/cloudX-proxy/commit/8a698edbfe206d410530b5c89ab55d2230b19a92))

# [0.9.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.8.4...v0.9.0) (2025-09-09)


### Features

* Add --dry-run flag for preview mode across all commands ([72cc2f1](https://github.com/easytocloud/cloudX-proxy/commit/72cc2f1d83f7949cc79595727d6d2a7a5c248a25)), closes [#7](https://github.com/easytocloud/cloudX-proxy/issues/7)

## [0.8.4](https://github.com/easytocloud/cloudX-proxy/compare/v0.8.3...v0.8.4) (2025-09-09)

## [0.8.3](https://github.com/easytocloud/cloudX-proxy/compare/v0.8.2...v0.8.3) (2025-09-09)

## [0.8.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.8.1...v0.8.2) (2025-09-09)


### Bug Fixes

* make cloudx host matching case-insensitive in list command ([9d91945](https://github.com/easytocloud/cloudX-proxy/commit/9d9194533d0ee2d150ed10da8675ef53911f0a16))

## [0.8.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.8.0...v0.8.1) (2025-09-02)


### Bug Fixes

* resolve liccheck pkg_resources compatibility issue ([61ed265](https://github.com/easytocloud/cloudX-proxy/commit/61ed265cabfcfbb36999698add43e118fa917654))

# [0.8.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.7.0...v0.8.0) (2025-09-02)


### Features

* add comprehensive license compliance with liccheck integration ([611e49b](https://github.com/easytocloud/cloudX-proxy/commit/611e49bba0465eb9c4c80bfe2122240479ac3aa4))

# [0.7.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.6.1...v0.7.0) (2025-09-02)


### Features

* add pip-audit security scanning to CI/CD pipeline ([3ded9bb](https://github.com/easytocloud/cloudX-proxy/commit/3ded9bbeaeee0e25cb3ca981ca0204faf4735ca7))

## [0.6.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.6.0...v0.6.1) (2025-08-22)


### Bug Fixes

* clean up versioning configuration and remove unnecessary package.json ([62af606](https://github.com/easytocloud/cloudX-proxy/commit/62af606f57367948845fc16863e196207b92645d))

# [0.6.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.5.3...v0.6.0) (2025-08-22)


### Features

* add project badges and modernize Python version support ([594bb87](https://github.com/easytocloud/cloudX-proxy/commit/594bb870a7a58ef3c99c46e24cf1843249945a77))

## [0.5.3](https://github.com/easytocloud/cloudX-proxy/compare/v0.5.2...v0.5.3) (2025-08-22)

## [0.5.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.5.1...v0.5.2) (2025-08-22)

## [0.5.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.5.0...v0.5.1) (2025-08-22)

# [0.5.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.13...v0.5.0) (2025-08-22)


### Features

* dependabot ([3b78503](https://github.com/easytocloud/cloudX-proxy/commit/3b785034632b5998b6bccf3ca298a70d57f87a30))

## [0.4.13](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.12...v0.4.13) (2025-03-12)


### Bug Fixes

* improve help text formatting using Click's \b character ([3dc4230](https://github.com/easytocloud/cloudX-proxy/commit/3dc4230cfa6fef72eee7521dca77c6717772e782))

## [0.4.12](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.11...v0.4.12) (2025-03-12)


### Bug Fixes

* improve help text formatting for example usage ([7513c51](https://github.com/easytocloud/cloudX-proxy/commit/7513c51b5cfa305f828f54d30d7f26f70a85a0b8))

## [0.4.11](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.10...v0.4.11) (2025-03-12)


### Bug Fixes

* pass --ssh-config in generated connect command and enhance 1Password integration ([1036c2f](https://github.com/easytocloud/cloudX-proxy/commit/1036c2f029c75943328083b9b14787493309f3a1))

## [0.4.10](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.9...v0.4.10) (2025-03-12)


### Bug Fixes

* non-default ssh-config directory passed in connect ([c84963c](https://github.com/easytocloud/cloudX-proxy/commit/c84963c43544bc9de5410a96502469d64ef4bb4f))

## [0.4.9](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.8...v0.4.9) (2025-03-12)


### Bug Fixes

* added list command ([76e43e4](https://github.com/easytocloud/cloudX-proxy/commit/76e43e449ec2f704475014f95d0a345e322be8e8))

## [0.4.8](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.7...v0.4.8) (2025-03-07)

## [0.4.7](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.6...v0.4.7) (2025-03-07)


### Bug Fixes

* added --hostname ([0fb0aa4](https://github.com/easytocloud/cloudX-proxy/commit/0fb0aa4bfa17d58eee958d6e5ade9d9c14a11a6c))

## [0.4.6](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.5...v0.4.6) (2025-03-07)


### Bug Fixes

* added --yes for non-interactive setup ([7e6007f](https://github.com/easytocloud/cloudX-proxy/commit/7e6007f68db3a958d1987a308f20fa85b5f7289f))

## [0.4.5](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.4...v0.4.5) (2025-03-07)


### Bug Fixes

* 1Password key matching ([4583e20](https://github.com/easytocloud/cloudX-proxy/commit/4583e20915b9bf8ab5cb2244676ee735aaa35cfc))

## [0.4.4](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.3...v0.4.4) (2025-03-07)


### Bug Fixes

* improved generated ssh config file for multiple cloudx instances ([11c28d1](https://github.com/easytocloud/cloudX-proxy/commit/11c28d1534bddfbbd7d108a2a961aa21166e899a))

## [0.4.3](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.2...v0.4.3) (2025-03-06)


### Bug Fixes

* improved documentation and simplified ssh config output ([5b5d9a4](https://github.com/easytocloud/cloudX-proxy/commit/5b5d9a496bcba440e4863e8285673e8f97d3c684))

## [0.4.2](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.1...v0.4.2) (2025-03-06)


### Bug Fixes

* added _1password.py ([421a95f](https://github.com/easytocloud/cloudX-proxy/commit/421a95f867c2c2b6ee3eea220d06cf00a5c8228c))

## [0.4.1](https://github.com/easytocloud/cloudX-proxy/compare/v0.4.0...v0.4.1) (2025-03-06)


### Bug Fixes

* improved 1Password key handling ([3269f2d](https://github.com/easytocloud/cloudX-proxy/commit/3269f2dc74ceba422d8c9b2ca0b1f68ad23f0eb2))

# [0.4.0](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.15...v0.4.0) (2025-03-06)


### Features

* added 1password integration ([4ac2340](https://github.com/easytocloud/cloudX-proxy/commit/4ac2340d6174ded129482e0fcd91a9cef0ab136d))

## [0.3.15](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.14...v0.3.15) (2025-03-06)


### Bug Fixes

* added --ssh-config ([893d919](https://github.com/easytocloud/cloudX-proxy/commit/893d919f7ef30dc5fd41a06b2c032d0035180e80))
* added --ssh-config also in connect ([75b7b3b](https://github.com/easytocloud/cloudX-proxy/commit/75b7b3b5ecac5f1a1012ce9d4905bc5aed444915))

## [0.3.14](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.13...v0.3.14) (2025-03-06)


### Bug Fixes

* restricted permissions on generated files and directories ([6b7b057](https://github.com/easytocloud/cloudX-proxy/commit/6b7b057832ab95fc6cb00c759380663eec2960a5))

## [0.3.13](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.12...v0.3.13) (2025-03-06)


### Bug Fixes

* create more stable ssh connection ([606f196](https://github.com/easytocloud/cloudX-proxy/commit/606f196e10b5c3237ea07e45ef80cacdd36af12b))

## [0.3.12](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.11...v0.3.12) (2025-02-14)


### Bug Fixes

* modified wait_for_setup_completion call ([a85be04](https://github.com/easytocloud/cloudX-proxy/commit/a85be04468a5fb3ea2e100c8fe854102df0dd030))

## [0.3.11](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.10...v0.3.11) (2025-02-11)


### Bug Fixes

* removed last references to client in favour of proxy ([cc19cf4](https://github.com/easytocloud/cloudX-proxy/commit/cc19cf4c951daf1bc1e5d69d945133e3d1448a07))

## [0.3.10](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.9...v0.3.10) (2025-02-11)


### Bug Fixes

* remove AWS api calls in favour of ssh ([c3430ea](https://github.com/easytocloud/cloudX-proxy/commit/c3430ea0146c8b814f453dda8db5a5a5db975e09))

## [0.3.9](https://github.com/easytocloud/cloudX-proxy/compare/v0.3.8...v0.3.9) (2025-02-11)


### Bug Fixes

* use ssm for ec2 operations ([e227818](https://github.com/easytocloud/cloudX-proxy/commit/e2278184b443c4051aa355745985543757d980a3))

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
