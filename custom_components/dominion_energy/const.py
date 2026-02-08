"""Constants for the Dominion Energy Virginia integration."""

DOMAIN = "dominion_energy"

# Gigya authentication
GIGYA_API_KEY = "4_6zEg-HY_0eqpgdSONYkJkQ"
GIGYA_LOGIN_URL = "https://auth.dominionenergy.com/accounts.login"

# Dominion Energy API base
API_BASE_URL = "https://prodsvc-dominioncip.smartcmobile.com"

# API endpoints
TOKEN_URL = f"{API_BASE_URL}/UsermanagementAPI/api/1/Login/auth"
USAGE_ELECTRIC_URL = f"{API_BASE_URL}/Usageapi/api/V1/Electric"
USAGE_HOURLY_URL = f"{API_BASE_URL}/Service/api/1/Usage/UsageData"
ACCOUNT_DETAILS_URL = f"{API_BASE_URL}/Service/api/1/FromDb/GetAccountDetailsFromSSA"
ACCOUNT_INFO_URL = f"{API_BASE_URL}/AccountManagementapi/api/1/Accounts/Account"
BILLING_URL = f"{API_BASE_URL}/Service/api/1/bill/GetBillandInvoiceHistory"

# Configuration
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_MANUAL_TOKEN = "manual_token"
