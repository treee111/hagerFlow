# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

A list of unreleased changes can be found [here](https://github.com/treee111/hagerFlow/compare/v1.0.0...HEAD).

<a name="1.0.0"></a>
## 1.0.0 - 2026-08-24
### Features
- Home Assistant integration for Hager flow storage systems via unofficial Portal API [`75fb131`](https://github.com/treee111/hagerFlow/commit/75fb1311747911ed51473521d7193d2b6900c423)
- Translate README to English [`0207fb5`](https://github.com/treee111/hagerFlow/commit/0207fb504889b7e3f8b2c2252186e38ca90973ee)
- Support the official Hager Energy API as a second backend ([#5](https://github.com/treee111/hagerFlow/issues/5)) [`d4b7f82`](https://github.com/treee111/hagerFlow/commit/d4b7f8282d9591d531cfb02e6d4da5de5cfcec0d)
- Expose the PV production forecast from the official API ([#6](https://github.com/treee111/hagerFlow/issues/6)) [`b002859`](https://github.com/treee111/hagerFlow/commit/b0028590cc17d4c46ac3a4b3684ddc440440fd01)
- Add HACS badges and one-click install links ([#8](https://github.com/treee111/hagerFlow/issues/8)) [`d717c01`](https://github.com/treee111/hagerFlow/commit/d717c01adc7584fe867530ffc2e192d1709f5ea7)

### Bug Fixes
- Correct the energy counter mapping ([#3](https://github.com/treee111/hagerFlow/issues/3)) [`e0c7bc0`](https://github.com/treee111/hagerFlow/commit/e0c7bc0c23e26b45516346c9eaa590efcbbd8134)
- Do not register entities a backend can never fill ([#7](https://github.com/treee111/hagerFlow/issues/7)) [`1faa767`](https://github.com/treee111/hagerFlow/commit/1faa767a7fabc9073faeae2d5863b9601dd57c5c)

### Development/Infrastructure/Test/CI
- Fix CI validation failures ([#1](https://github.com/treee111/hagerFlow/issues/1)) [`290ea95`](https://github.com/treee111/hagerFlow/commit/290ea95d045b68aa49eca021675968a6ba76fb70)
- Document verified sign convention and energy counter caveats ([#2](https://github.com/treee111/hagerFlow/issues/2)) [`0bb6633`](https://github.com/treee111/hagerFlow/commit/0bb66330b295cb66399561274d1fd791461c2b8a)
- Explain why power and energy sit on different sides of the inverter ([#4](https://github.com/treee111/hagerFlow/issues/4)) [`290855d`](https://github.com/treee111/hagerFlow/commit/290855d2fef25f0853d30ba40a4a6d838a7594c6)
- Add git-chglog configuration ([#9](https://github.com/treee111/hagerFlow/issues/9)) [`a3e7e08`](https://github.com/treee111/hagerFlow/commit/a3e7e08f31bdffaf2e9b6bd26c1cf30010a42ad3)


