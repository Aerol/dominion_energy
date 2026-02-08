# Dominion Energy Virginia Integration - Implementation Guide

## ✅ COMPLETION STATUS

**The integration has been updated with actual API endpoints!** The reverse-engineering work has been completed and the following has been implemented:

### Completed ✅
- Gigya authentication flow
- Account and meter information retrieval  
- Monthly usage data
- Hourly usage data (available through API)
- Billing information
- All major API endpoints documented

### Needs Work ⚠️
- **JWT Token Generation**: The exact method for obtaining the Dominion-specific JWT bearer token (different from Gigya id_token) is unclear. The current implementation uses the Gigya id_token, which may need to be replaced with the proper Dominion JWT.
- **Error Handling**: Could be more robust
- **Multi-account Support**: Currently single account only

### Reference Documentation

See `API_DOCUMENTATION.md` for complete details on all discovered API endpoints, request/response formats, and authentication flows.

---

## Overview (Historical - for reference)

This guide will help you complete the integration by reverse-engineering the Dominion Energy API.

**NOTE:** Most of this work has already been done! The integration now uses the actual Dominion Energy API endpoints. However, the JWT token generation mechanism still needs refinement.

## Step 1: Reverse-Engineer the API

### Tools Needed
- Chrome, Firefox, or Edge browser
- Developer Tools (press F12)
- Your Dominion Energy account credentials

### Process

1. **Open Developer Tools**
   - Press F12 in your browser
   - Go to the "Network" tab
   - Make sure "Preserve log" is checked

2. **Capture Login Requests**
   - Go to https://www.dominionenergy.com/virginia
   - Click "Sign In" or "My Account"
   - Enter your credentials and log in
   - Watch the Network tab for API calls

3. **Find Key Information**
   Look for requests that contain:
   - **Login endpoint**: Usually contains "login", "auth", or "authenticate" in the URL
   - **Authentication method**: Check if they use tokens, cookies, or sessions
   - **Request format**: Note the JSON structure sent during login
   - **Response format**: Note what data is returned (token, session ID, etc.)

4. **Capture Usage Data Requests**
   - Once logged in, navigate to your usage dashboard
   - Look for requests that fetch your energy usage data
   - These often contain "usage", "consumption", or "meter" in the URL
   - Note the request parameters (date ranges, account numbers, etc.)

### Example: What to Look For

```
POST https://api.dominionenergy.com/auth/login
Request:
{
  "username": "your_username",
  "password": "your_password",
  "grant_type": "password"
}

Response:
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "account_id": "123456789"
}
```

## Step 2: Update the Integration Code

### Update `const.py`

Replace the placeholder URLs with the actual endpoints:

```python
# Example - update with actual URLs you discovered
BASE_URL = "https://api.dominionenergy.com"  # or whatever you found
LOGIN_URL = f"{BASE_URL}/auth/login"
USAGE_URL = f"{BASE_URL}/v1/usage"
```

### Update `api.py`

#### Update the `async_login()` method:

```python
async def async_login(self) -> bool:
    """Login to Dominion Energy and obtain session token."""
    try:
        # Update this structure based on what you discovered
        login_data = {
            "username": self.username,
            "password": self.password,
            # Add any other required fields
            # "grant_type": "password",
            # "client_id": "web_app",
        }
        
        # Update headers if needed
        headers = {
            "Content-Type": "application/json",
            # Add any other required headers
            # "X-Client-Version": "1.0",
        }
        
        async with self.session.post(
            LOGIN_URL,
            json=login_data,
            headers=headers
        ) as response:
            if response.status == 200:
                data = await response.json()
                # Update based on actual response structure
                self._token = data.get("access_token")  # or "token", "sessionId", etc.
                self._account_number = data.get("account_id")  # update field name
                return True
            else:
                _LOGGER.error("Login failed with status %s", response.status)
                return False
                
    except aiohttp.ClientError as err:
        _LOGGER.error("Error during login: %s", err)
        raise DominionEnergyAPIError(f"Login failed: {err}") from err
```

#### Update the `async_get_usage_data()` method:

```python
async def async_get_usage_data(self) -> dict[str, Any]:
    """Fetch energy usage data from Dominion Energy."""
    if not self._token:
        await self.async_login()
    
    try:
        # Update based on actual authentication method
        headers = {
            "Authorization": f"Bearer {self._token}",  # or however they do auth
            "Content-Type": "application/json",
        }
        
        # Update parameters based on actual API requirements
        params = {
            "accountId": self._account_number,
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            # Add any other required parameters
        }
        
        async with self.session.get(
            USAGE_URL,
            headers=headers,
            params=params
        ) as response:
            if response.status == 200:
                data = await response.json()
                return self._parse_usage_data(data)
            # ... rest of error handling
```

#### Update the `_parse_usage_data()` method:

```python
def _parse_usage_data(self, raw_data: dict) -> dict[str, Any]:
    """Parse the raw API response into usable data."""
    # Update field names based on actual API response
    
    # Example if API returns:
    # {
    #   "usage": {
    #     "current": 2.5,
    #     "daily": 45.2,
    #     "monthly": 850.3
    #   },
    #   "cost": {
    #     "estimated": 95.23
    #   }
    # }
    
    usage = raw_data.get("usage", {})
    cost = raw_data.get("cost", {})
    
    return {
        "current_usage": usage.get("current", 0),
        "daily_usage": usage.get("daily", 0),
        "monthly_usage": usage.get("monthly", 0),
        "estimated_cost": cost.get("estimated", 0),
        "peak_demand": usage.get("peak", 0),
        "last_updated": datetime.now().isoformat(),
    }
```

## Step 3: Test the Integration

### Using the Debug Script

```bash
cd /path/to/dominion_energy
python debug_api.py --username YOUR_USERNAME --password YOUR_PASSWORD --discover
```

This will help you:
- Test the login endpoint
- Verify API responses
- Debug authentication issues

### Install in Home Assistant

1. Copy the `dominion_energy` folder to `config/custom_components/`
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "Dominion Energy Virginia"
5. Enter your credentials

### Check Logs

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.dominion_energy: debug
```

Then check Settings → System → Logs for any errors.

## Step 4: Customize Sensors (Optional)

You may want to add or remove sensors based on what data is available. Edit `sensor.py`:

### Add a New Sensor

```python
class DominionEnergyYourNewSensor(DominionEnergySensorBase):
    """Sensor for your custom metric."""

    _attr_name = "Your Metric Name"
    _attr_device_class = SensorDeviceClass.ENERGY  # or POWER, MONETARY, etc.
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def unique_id(self) -> str:
        return f"{self._config_entry.entry_id}_your_metric"

    @property
    def native_value(self):
        if self.coordinator.data:
            return self.coordinator.data.get("your_field_name")
        return None
```

Don't forget to add it to the sensors list in `async_setup_entry()`.

## Common Issues and Solutions

### Issue: "Cannot connect" error
**Solution**: Check the API endpoints in `const.py`. Make sure they match what you found in the browser.

### Issue: Login successful but no data
**Solution**: Check the `_parse_usage_data()` method. The field names probably don't match the actual API response.

### Issue: Data appears but is wrong
**Solution**: Verify the units. The API might return watts instead of kilowatts, or vice versa.

### Issue: Authentication expires frequently
**Solution**: You may need to implement token refresh logic in the API client.

## Advanced Features

### Add Token Refresh

```python
async def async_refresh_token(self) -> bool:
    """Refresh the authentication token."""
    # Implement based on Dominion's refresh mechanism
    # Some APIs provide a refresh token, others require re-login
    pass
```

### Add Multiple Accounts

Modify `config_flow.py` to allow multiple accounts:

```python
async def async_step_user(self, user_input=None):
    # Remove or modify the unique_id check to allow multiple accounts
    # Or use a combination of username + account number
    await self.async_set_unique_id(
        f"{user_input[CONF_USERNAME]}_{account_number}"
    )
```

### Add Historical Data

Create additional sensors or attributes for historical usage:

```python
@property
def extra_state_attributes(self):
    """Return additional attributes."""
    if self.coordinator.data:
        return {
            "last_week_usage": self.coordinator.data.get("last_week"),
            "last_month_usage": self.coordinator.data.get("last_month"),
        }
    return {}
```

## Publishing Your Integration

Once working:

1. **Create a GitHub repository**
2. **Add proper documentation**
3. **Submit to HACS** (optional but recommended)
4. **Share with the community**

## Legal Considerations

- This integration uses unofficial API endpoints
- Dominion Energy may change their API at any time
- Use responsibly and don't overload their servers
- Consider the Terms of Service

## Getting Help

If you get stuck:

1. Check Home Assistant logs for detailed error messages
2. Use the debug script to test API calls
3. Ask on the Home Assistant community forums
4. Review other utility integrations for examples

## Example Integrations to Study

Similar utility integrations for reference:
- OhmConnect
- Sense Energy
- Tesla Powerwall
- Utilities component

Look at these in the Home Assistant core repository for patterns and best practices.

## Next Steps

1. Reverse-engineer the API using browser dev tools
2. Update the code with actual endpoints and data structures
3. Test thoroughly with your account
4. Consider sharing with other Dominion Energy customers
5. Maintain the integration as Dominion updates their website

Good luck! This integration will be incredibly useful once completed.
