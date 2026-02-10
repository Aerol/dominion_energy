# Dominion Energy Virginia - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/yourusername/dominion-energy-hacs.svg)](https://github.com/yourusername/dominion-energy-hacs/releases)

Home Assistant custom integration for Dominion Energy Virginia customers to monitor their energy usage in real-time.

## Features

- 🔐 **Automatic 2FA Authentication** - Secure login with SMS verification
- 🔄 **Auto Token Refresh** - Tokens refresh automatically every 30 minutes
- 🍪 **Cookie Persistence** - Bypasses 2FA on subsequent logins
- 📊 **Dual Data Sources** - Uses both Excel export and official Green Button XML
- ⚡ **Real-time Usage** - Yesterday's complete usage data
- 📅 **Monthly Tracking** - Month-to-date energy consumption
- 💰 **Cost Estimation** - Automatic cost calculation

## Installation

### HACS (Recommended)

1. Open HACS
2. Click "Integrations"
3. Click the 3 dots in top right → "Custom repositories"
4. Add this repository URL
5. Select "Integration" as category
6. Click "Add"
7. Search for "Dominion Energy Virginia"
8. Click "Download"
9. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy `custom_components/dominion_energy` to your HA `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"Dominion Energy Virginia"**
4. Choose **"Automatic (with 2FA)"**
5. Enter your Dominion Energy credentials
6. Enter the 6-digit SMS code when prompted
7. Enter your account/meter numbers (found at myaccount.dominionenergy.com)

### Finding Your Account Details

Log in to https://myaccount.dominionenergy.com and find:
- **Account Number**: Displayed on your account page (10 digits)
- **Customer Number**: Also called "BP Number" (9 digits)
- **Meter Number**: Your electric meter ID (18 digits)

## Sensors

The integration creates the following sensors:

| Sensor | Description | Unit |
|--------|-------------|------|
| Yesterday Usage | Complete energy usage for previous day | kWh |
| Monthly Usage | Month-to-date energy consumption | kWh |
| Last Hour Usage | Most recent hourly reading | kWh |
| Estimated Cost | Monthly cost estimate ($0.12/kWh) | $ |
| Account Number | Your Dominion account number | - |
| Meter Number | Your meter number | - |

## Data Sources

The integration fetches data from two sources and automatically selects the most accurate:

1. **Green Button XML** (Primary) - Official utility billing data with hourly intervals
2. **Excel Export** (Fallback) - Detailed half-hourly data

### Why Yesterday Instead of Today?

Utility data typically has a 24-48 hour lag. Yesterday's data is complete and accurate, while today's data is incomplete and updates throughout the day.

## Energy Dashboard

Add these sensors to your Home Assistant Energy Dashboard:

1. Go to **Settings** → **Dashboards** → **Energy**
2. Click **"Add Consumption"**
3. Select **"Yesterday Usage"** sensor
4. Set **"Use an entity tracking the total costs"** to **"Estimated Cost"**

## Token Security

- ✅ Tokens are stored securely in Home Assistant's config entry
- ✅ Tokens refresh automatically before expiration
- ✅ Cookies persist to avoid repeated 2FA prompts
- ✅ All API communication uses HTTPS

## Troubleshooting

### Integration won't load
- Check Home Assistant logs: **Settings** → **System** → **Logs**
- Search for "dominion_energy"
- Restart Home Assistant

### No data showing
- Verify account/meter numbers are correct
- Check that you're a Dominion Energy Virginia customer
- Data may take 24-48 hours to appear for new accounts

### 2FA not working
- Ensure your phone number is registered at myaccount.dominionenergy.com
- Check SMS wasn't blocked or delayed
- Try re-adding the integration

### "Account and meter numbers required"
- Delete the integration
- Re-add and enter account details when prompted

## Development

Want to contribute? See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment instructions.

### Running Locally

```bash
# Clone the repository
git clone https://github.com/yourusername/dominion-energy-hacs.git
cd dominion-energy-hacs

# Copy to Home Assistant
cp -r custom_components/dominion_energy /path/to/homeassistant/custom_components/

# Restart Home Assistant
```

## Credits

Based on the excellent [dompower](https://github.com/YeomansIII/dompower) library by YeomansIII.

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Support

- 🐛 **Bug Reports**: [Open an issue](https://github.com/yourusername/dominion-energy-hacs/issues)
- 💡 **Feature Requests**: [Open an issue](https://github.com/yourusername/dominion-energy-hacs/issues)
- ❓ **Questions**: [Open a discussion](https://github.com/yourusername/dominion-energy-hacs/discussions)

## Disclaimer

This integration is not affiliated with, endorsed by, or connected to Dominion Energy. Use at your own risk.
