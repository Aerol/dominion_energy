# Dominion Energy Virginia Integration for Home Assistant

This custom integration allows you to monitor your Dominion Energy Virginia account directly in Home Assistant.

## ⚠️ Important Notes

This integration has been **reverse-engineered** from the Dominion Energy web portal and uses **unofficial APIs**. Key points:

- **Authentication**: Uses Gigya (SAP Customer Data Cloud) for initial login
- **API Endpoints**: All endpoints are on `prodsvc-dominioncip.smartcmobile.com`
- **JWT Token**: The integration currently uses the Gigya id_token. There appears to be an additional Dominion-specific JWT that is generated client-side or in a way that wasn't captured during reverse engineering. This may need refinement.
- **Stability**: Dominion Energy may change their APIs at any time without notice
- **Rate Limiting**: Be respectful of API usage to avoid account restrictions

## Features

- **Daily Usage**: Energy consumed today (kWh)
- **Monthly Usage**: Energy consumed this month (kWh) 
- **Estimated Cost**: Current month's estimated bill ($)
- **Account Info**: Account number and meter number
- **Hourly Data**: Available through service calls (see advanced usage)

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations → ⋮ (top right) → Custom repositories
   - Add URL: `https://github.com/yourusername/dominion_energy`
   - Category: Integration
3. Click "Install" on the Dominion Energy Virginia integration
4. Restart Home Assistant

### Manual Installation

1. Copy the `dominion_energy` folder to your `config/custom_components` directory
2. If the `custom_components` directory doesn't exist, create it first
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Dominion Energy Virginia"
4. Enter your Dominion Energy account credentials:
   - **Username**: Your Dominion Energy login email
   - **Password**: Your Dominion Energy login password
5. Click **Submit**

## How It Works

### Authentication Flow

1. **Gigya Login**: Authenticates with Gigya using your credentials
   - Endpoint: `https://auth.dominionenergy.com/accounts.login`
   - Returns: `id_token` (JWT), `UID`, `login_token`

2. **Token Exchange**: (Implementation detail TBD)
   - Endpoint: `https://prodsvc-dominioncip.smartcmobile.com/UsermanagementAPI/api/1/Login/auth`
   - The final Dominion JWT token generation method needs further investigation

3. **API Calls**: Uses JWT bearer token for all subsequent requests

### Available Data

The integration polls the following endpoints:

- **Electric Usage**: `/Usageapi/api/V1/Electric` - Monthly consumption and cost data
- **Hourly Usage**: `/Service/api/1/Usage/UsageData` - Hourly breakdown (optional)
- **Account Details**: `/Service/api/1/FromDb/GetAccountDetailsFromSSA` - Meter information
- **Billing Info**: `/Service/api/1/bill/GetBillandInvoiceHistory` - Bill history

## Data Update Frequency

The integration polls Dominion Energy every **30 minutes** by default. You can adjust this in `__init__.py` by modifying the `UPDATE_INTERVAL` value.

## Advanced Usage

### Service Calls

You can call additional services to get more detailed data:

```yaml
# Get hourly usage for a specific date
service: dominion_energy.get_hourly_usage
data:
  date: "2026-02-07"
```

### Template Sensors

Create additional sensors based on the data:

```yaml
template:
  - sensor:
      - name: "Daily Energy Cost"
        unit_of_measurement: "$"
        state: >
          {% set usage = states('sensor.dominion_energy_account_daily_usage') | float(0) %}
          {% set rate = 0.11 %}  # Your rate per kWh
          {{ (usage * rate) | round(2) }}
```

## Known Limitations

1. **JWT Token Generation**: The exact method for obtaining the Dominion-specific JWT bearer token (different from Gigya id_token) is unclear and may need client-side JavaScript implementation
2. **Real-time Usage**: Current/instantaneous power usage is not available through the API
3. **Billing Details**: Only basic billing info is retrieved; detailed bill breakdown requires additional implementation
4. **Multiple Accounts**: Currently supports one account per integration instance
5. **No Historical Data**: Integration doesn't store historical data (use Home Assistant's Recorder for that)

## Troubleshooting

### Integration not appearing

- Ensure the files are in the correct directory: `config/custom_components/dominion_energy/`
- Restart Home Assistant
- Check the logs for errors: **Settings** → **System** → **Logs**

### Authentication errors

- Verify your username and password are correct
- Check if Dominion Energy has changed their login process
- Look at the Home Assistant logs for specific error messages

### No data appearing

- The API endpoints may need to be updated
- Check the logs for API errors
- Verify your account has active service with Dominion Energy

## Development

### Testing the API

You can test the API connection manually:

```python
import aiohttp
import asyncio
from custom_components.dominion_energy.api import DominionEnergyAPI

async def test():
    async with aiohttp.ClientSession() as session:
        api = DominionEnergyAPI("username", "password", session)
        await api.async_login()
        data = await api.async_get_usage_data()
        print(data)

asyncio.run(test())
```

### Logging

Enable debug logging by adding to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.dominion_energy: debug
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by Dominion Energy. Use at your own risk.

## License

MIT License - See LICENSE file for details

## Support

If you encounter issues:

1. Check the [Issues](https://github.com/yourusername/dominion_energy/issues) page
2. Enable debug logging and include relevant logs in your issue report
3. Describe your Home Assistant version and setup

## Acknowledgments

- Home Assistant community for integration examples
- Dominion Energy customers who helped test

## Future Enhancements

Potential features for future releases:

- [ ] Hourly usage breakdown
- [ ] Historical usage charts
- [ ] Bill projection
- [ ] Usage alerts and notifications
- [ ] Multiple account support
- [ ] Time-of-use rate information
- [ ] Carbon footprint tracking
