# Auth Testing Playbook (bill4pe)

Auth: JWT httpOnly cookies (access 15min + refresh 7d), bcrypt hashing, brute-force lockout (5 attempts / 15 min, keyed by ip:email), admin seeded on startup.

## Credentials
See /app/memory/test_credentials.md. Admin: meland@mhem.in (role: admin).

## Step 1: MongoDB Verification
```
mongosh
use test_database
db.users.find({role: "admin"}).pretty()
db.users.findOne({role: "admin"}, {password_hash: 1})
```
Verify: bcrypt hash starts with `$2b$`; indexes exist on users.email (unique), login_attempts.identifier, password_reset_tokens.expires_at (TTL).

## Step 2: API Testing
```
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
curl -c cookies.txt -X POST "$API_URL/api/auth/login" -H "Content-Type: application/json" -d '{"email":"meland@mhem.in","password":"Bill4pe@123"}'
cat cookies.txt
curl -b cookies.txt "$API_URL/api/auth/me"
```
Login returns the user object and sets `access_token` + `refresh_token` cookies. `/me` returns the same user with those cookies.

## Step 3: Negative tests
- Wrong password 5 times → 429 lockout on 6th attempt.
- GET /api/auth/me without cookies → 401.
- Register with duplicate email → 400.
- Register new user via POST /api/auth/register (name/email/password/role) → cookies set, role "owner" or "staff".

## Step 4: Refresh
- POST /api/auth/refresh with refresh_token cookie → new access_token cookie.
