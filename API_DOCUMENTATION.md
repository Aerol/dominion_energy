# Dominion Energy API Documentation

This document contains the complete API structure reverse-engineered from the Dominion Energy Virginia web portal.

## Authentication Flow

### 1. Gigya Login

**Endpoint:** `POST https://auth.dominionenergy.com/accounts.login`

**Content-Type:** `application/x-www-form-urlencoded`

**Required Parameters:**
```
loginID={email}
password={password}
sessionExpiration=3600
targetEnv=jssdk
include=profile,data,emails,subscriptions,preferences,id_token,groups,loginIDs,
includeUserInfo=true
loginMode=standard
lang=en
APIKey=4_6zEg-HY_0eqpgdSONYkJkQ
source=showScreenSet
sdk=js_latest
authMode=cookie
pageURL=https://login.dominionenergy.com/CommonLogin?SelectedAppName=Electric
format=json
```

**Response:**
```json
{
  "errorCode": 0,
  "statusCode": 200,
  "UID": "3ada564e9dfc42648adc8cf49b63a4a2",
  "id_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
  "sessionInfo": {
    "login_token": "st2.s.AtLtCKVfcg...",
    "expires_in": "3600"
  },
  "profile": {
    "firstName": "Jonathon",
    "lastName": "Saul",
    "email": "jonsaul@puppetmaster.lol"
  },
  "data": {
    "entitlements": {
      "Electric": {
        "EMYA": true
      }
    }
  }
}
```

**Important Fields:**
- `UID`: User ID from Gigya
- `id_token`: JWT token for authentication
- `login_token`: Session token

### 2. Dominion Token Exchange

**Endpoint:** `POST https://prodsvc-dominioncip.smartcmobile.com/UsermanagementAPI/api/1/Login/auth`

**Headers:**
```
Authorization: Bearer {gigya_id_token}
Content-Type: application/json
ST: PL
PT: 
uid: 1
ReferenceId: CL-{uuid}
```

**Request Body:**
```json
{
  "username": "",
  "password": "",
  "guestToken": "{gigya_id_token}",
  "customattributes": {
    "client": "",
    "version": "",
    "deviceId": "",
    "deviceName": "",
    "os": ""
  }
}
```

**Response:**
- Status: 200 OK
- Body: (Empty or contains JWT - needs investigation)

**Note:** The actual Dominion Energy JWT Bearer token used in subsequent API calls is different from the Gigya id_token. The exact mechanism for obtaining it needs further investigation.

## Standard Headers for All API Calls

All requests to `prodsvc-dominioncip.smartcmobile.com` require these headers:

```
Authorization: Bearer {jwt_token}
Content-Type: application/json
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET,PUT,POST,DELETE,PATCH,OPTIONS
uid: 1
pt: 1
ReferenceId: MM-{uuid}
customerNumber: *****{last5}
accountNumber: *****{last7}
channel: WEB
```

## API Endpoints

### Usage Data

#### Monthly Electric Usage

**Endpoint:** `GET https://prodsvc-dominioncip.smartcmobile.com/Usageapi/api/V1/Electric`

**Parameters:**
```
AccountNumber=210018858444
MeterNumber=000000000200099983
From=2025-02-01
To=2026-03-01
Uom=kWh
Periodicity=MO
```

**Periodicity Options:**
- `MO` - Monthly
- `DA` - Daily
- `HH` - Hourly (possibly)

**Response:**
```json
{
  "StatusCode": 200,
  "Message": "Request successful.",
  "Result": {
    "electricUsages": [
      {
        "accountNumber": "210018858444",
        "meterNumber": "000000000200099983",
        "readingFrom": "2025-07-07T00:00:00+00:00",
        "readingTo": "2025-07-16T00:00:00+00:00",
        "amount": 14.39,
        "consumption": 84,
        "uom": "kWh"
      }
    ]
  }
}
```

#### Hourly Usage Data

**Endpoint:** `GET https://prodsvc-dominioncip.smartcmobile.com/Service/api/1/Usage/UsageData`

**Parameters:**
```
accountNumber=210018858444
ActionCode=4
StartDate=2026-02-05
EndDate=2026-02-06
```

**Action Codes:**
- `3` - Monthly/Historical detail
- `4` - Hourly data

**Response:**
```json
{
  "status": {
    "type": "success",
    "code": 200
  },
  "data": {
    "electricUsages": [
      {
        "accountNumber": "210018858444",
        "meterNumber": "000000000200099983",
        "consumption": "1.061",
        "readDate": "2/6/2026 12:00:00 AM",
        "demandKW": "0"
      }
    ]
  }
}
```

#### Historical Usage Detail

**Endpoint:** `GET https://prodsvc-dominioncip.smartcmobile.com/Service/api/1/Usage/GetUsageHistoryDetail`

**Parameters:**
```
AccountNumber=210018858444
Contract=3008896652
StartDate=03/01/2025
EndDate=02/01/2026
ActionCode=3
```

**Response:** Contains detailed daily weather data and temperature correlations.

### Account Information

#### Account Details

**Endpoint:** `GET https://prodsvc-dominioncip.smartcmobile.com/Service/api/1/FromDb/GetAccountDetailsFromSSA`

**Parameters:**
```
accountnumber=210018858444
```

**Response:**
```json
{
  "status": {
    "type": "success",
    "code": 200
  },
  "data": [
    {
      "meterNumber": "000000000200099983",
      "meterType": "Smart Meter (AMI)",
      "meterStatus": "Active",
      "meterLocation": "BASEMENT",
      "lastUpdated": "2026-02-07T23:51:24.639123"
    }
  ]
}
```

#### Full Account Information

**Endpoint:** `GET https://prodsvc-dominioncip.smartcmobile.com/AccountManagementapi/api/1/Accounts/Account/{accountNumber}/{uid}`

**Example:** `/AccountManagementapi/api/1/Accounts/Account/210018858444/3ada564e-9dfc-4264-8adc-8cf49b63a4a2`

**Response:**
```json
{
  "status": {
    "type": "success",
    "code": 200
  },
  "data": {
    "accountNumber": "210018858444",
    "paperlessFlag": 0,
    "accountType": 1,
    "accountAttribute1": "RS~Residential",
    "mailingAddressVm": {
      "address1": "1255 Elden St",
      "address2": "APT 104",
      "city": "Herndon",
      "state": "VA",
      "postalCode": "20170"
    },
    "serviceAddressVm": {
      "address1": "1255 Elden St",
      "address2": "Apt 104",
      "city": "Herndon",
      "state": "VA",
      "postalCode": "20170"
    },
    "lat": 38.960662258,
    "lon": -77.399332332,
    "customerName": "Jonathon  Saul"
  }
}
```

### Billing Information

#### Bill History

**Endpoint:** `GET https://prodsvc-dominioncip.smartcmobile.com/Service/api/1/bill/GetBillandInvoiceHistory`

**Parameters:**
```
invoiceId=800300969893
accountNumber=210018858444
```

**Response:**
```json
{
  "status": {
    "type": "success",
    "code": 200
  },
  "data": {
    "contractAccount": "210018858444",
    "invoiceId": "800300969893",
    "zBillInvHeadtoItemNav": {
      "results": [
        {
          "invoiceId": "800300969893",
          "invoiceDate": "01/16/2026 00:00:00",
          "billPdStart": "12/16/2025 00:00:00",
          "billPdEnd": "01/15/2026 00:00:00",
          "dueDate": "02/17/2026 00:00:00",
          "previousBalance": "98.580",
          "balanceForward": "98.580",
          "payments": "0.000",
          "totalCurrentCharges": "87.060",
          "amountDue": "185.640",
          "totalAccBalance": "185.640"
        }
      ]
    }
  }
}
```

#### Future Payment Information

**Endpoint:** `POST https://prodsvc-dominioncip.smartcmobile.com/Service/api/1/Payment/FuturePayment`

**Request Body:**
```json
{
  "accountNumber": "210018858444"
}
```

**Response:**
```json
{
  "status": {
    "type": "success",
    "code": 200
  },
  "data": {
    "paymentHistoryResponse": {
      "payment": [
        {
          "header": {
            "referenceNumber": "4737222858",
            "paymentDate": "02172026",
            "paymentAmount": "185.64",
            "paymentStatus": "SCHEDULED",
            "paymentTypeCode": "ELECTRICREG",
            "accountNumber": "210018858444",
            "paymentSource": "AutoPay"
          },
          "paymentMethod": {
            "type": "EF",
            "accountNumber": "*****1635-****9998"
          }
        }
      ]
    }
  }
}
```

### Green Button Data

**Endpoint:** `POST https://prodsvc-dominioncip.smartcmobile.com/ServiceExt/api/1/Usage/GreenButton`

**Request Body:**
```json
{
  "accountNumber": "210018858444",
  "meterNumber": "000000000200099983",
  "startDate": "2025-01-07",
  "endDate": "2026-02-07",
  "periodicity": "HH",
  "serviceAddress": "1255 Elden St, APT 104, Herndon, VA 20170-5513",
  "fullName": "Jonathon Saul",
  "serviceType": "Electric",
  "Uom": "kWh",
  "Format": "Csv"
}
```

**Response:** XML file (despite requesting CSV) in Green Button standard format with hourly interval readings.

## JWT Token Structure

### Gigya ID Token

**Decoded Payload:**
```json
{
  "iss": "https://fidm.gigya.com/jwt/4_6zEg-HY_0eqpgdSONYkJkQ/",
  "sub": "3ada564e9dfc42648adc8cf49b63a4a2",
  "iat": 1770508278,
  "exp": 1770508338,
  "isLoggedIn": true
}
```

### Dominion Energy JWT

**Decoded Payload:**
```json
{
  "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": "jonsaul@puppetmaster.lol",
  "Uuid": "3ada564e-9dfc-4264-8adc-8cf49b63a4a2",
  "Key": "d403f2f8-7b0c-47c4-90b1-dccc cdbb3c5c",
  "exp": 1770510081,
  "iss": "https://mywebapi.com",
  "aud": "https://mywebapi.com"
}
```

**Note:** The method for obtaining this token is still unclear. It may be generated client-side.

## Error Handling

All successful responses return:
```json
{
  "status": {
    "type": "success",
    "code": 200,
    "message": "success",
    "error": false
  },
  "data": { ... }
}
```

Error responses will have:
- `status.error: true`
- `status.code` with error code
- `status.message` with error description

## Rate Limiting

- Responses include Cloudflare headers
- Session cookies expire after 1 hour
- Be respectful with polling frequency (recommend 15-30 minute intervals)

## Security Notes

1. All API calls use HTTPS
2. CORS headers are permissive (`Access-Control-Allow-Origin: *`)
3. JWT tokens expire after 1 hour
4. Account numbers in headers are partially masked
5. Session affinity cookies are used for load balancing
