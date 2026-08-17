![Logo](https://raw.githubusercontent.com/Tasshack/dreame-vacuum/dev/docs/media/logo.png)

# Dreame/MOVA lawn mower integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/bhuebschen/dreame-mower?style=flat-square)](https://github.com/bhuebschen/dreame-mower/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz/)

This is a custom integration for Home Assistant that allows you to control your Dreame lawn mower robot

## (current) Features

- Start/Stop mowing.
- Send back to home.

### Please note: this is a modified version of Tasshack's "Dreame Vacuum" integration to work with the lawn mower, in this state it may causes a lot of error-messages.

### If you are interested in the (original) Vacuum-integration, please take a look at: https://github.com/Tasshack/dreame-vacuum

## Installation

### HACS (Recommended)

1. Ensure that [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bhuebschen&repository=dreame-mower&category=integration)

-- or --

2. Add this repository as a custom repository in HACS:
   - Open HACS in Home Assistant.
   - Go to **Integrations**.
   - Click on the three dots in the top-right corner and select **Custom repositories**.
   - Add the following URL: `https://github.com/bhuebschen/dreame-mower`.
   - Select **Integration** as the category.
3. Search for "Dreame Mower" in the HACS integrations list and install it.

### Manual Installation

1. Download the latest release from the [GitHub Releases page](https://github.com/bhuebschen/dreame-mower/releases).
2. Extract the downloaded archive.
3. Copy the `custom_components/dreame-mower` folder to your Home Assistant `custom_components` directory.
   - Example: `/config/custom_components/dreame-mower`
4. Restart Home Assistant.

## Configuration

<a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=dreame_mower" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>

-- or --

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration**.
3. Search for "Dreame Mower" and select it.
4. Enter the credentials you used in your Dreamehome/MOVAhome App
5. Complete the setup process.

## Usage

Once the integration is configured, your Dreame/MOVA Mower(s) will appear as entities in Home Assistant.

## Troubleshooting

- Ensure your Dreame/MOVA account credentials are correct.
- Check the Home Assistant logs for any errors related to the integration.

## Support

If you encounter any issues or have feature requests, please open an issue on the [GitHub Issues page](https://github.com/bhuebschen/dreame-mower/issues).

## Contributions

Contributions are welcome! Feel free to submit pull requests to improve this integration.

## Development & Testing

This repository includes a local integration testing environment based on Docker, so you can verify code changes against a real Home Assistant instance before installing in your production HA.

### Local Docker test environment

Run a real Home Assistant container with your local code mounted in:

```bash
make install-dev   # optional: creates .venv (used for pytest harness)
make start         # starts Home Assistant on http://localhost:8123
make logs          # tail HA logs in real time
make status        # confirm local code is mounted and version matches
make restart       # after editing code in custom_components/dreame_mower/
make stop
make clean         # wipe test data (storage/, *.db, *.log)
```

The container name is `home-assistant-dreame-mower-test` and the
integration is loaded from `./custom_components/dreame_mower` (not from
HACS). Code changes are picked up by `make restart` — no rebuild
required.

### Why a Docker environment and not just `hass --script`?

`config_flow` exercises real network calls (HTTPS login to the Dreame
cloud, MQTT, vendor-specific token encryption) and real entity
platforms (lawn_mower, camera with PNG/JSON renderers, sensor, number,
select, button, switch, time). Mocking all of those is impractical and
gives low-fidelity tests. A 30-second Docker start gives you the real
integration against the real HA core, which is what you actually care
about.

### Using it to verify a PR

For each of the open PRs (`fix/camera-default-image-seed`,
`fix/siid-piid-reverse-lookup`, `fix/map-isinstance-guards`,
`fix/config-flow-cloud-login-error-handling`):

```bash
git fetch origin
git checkout <branch-name>
make clean && make start
# wait for "Home Assistant is ready!" then open http://localhost:8123
# create admin -> Settings -> Devices & Services -> Add Integration
# search for "Dreame Mower" and run through the config flow
make logs   # watch for the bug pattern the PR fixes
make stop
```

`make restart` after every code change picks up the new file on disk
without rebuilding the container — the integration is loaded from the
bind-mounted host directory.

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/bhuebschen/dreame-mower/blob/main/LICENSE) file for details.

# Thanks / Contributors

- [Tasshack](https://github.com/Tasshack)
- [Laurentiu Tanase](https://github.com/larieu)
- [Josef Kyrian](https://github.com/josef-kyrian)
- [Anton Daubert](https://github.com/antondaubert)
- [Loïc](https://github.com/zoic21)
