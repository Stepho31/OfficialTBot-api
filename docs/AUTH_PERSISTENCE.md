# Authentication Persistence Across Deployments

## Overview

The AutoPip AI authentication system uses **stateless JWT tokens** stored client-side in `localStorage`. This design ensures users remain logged in across Vercel deployments without requiring database-backed sessions.

## Architecture

### Backend (FastAPI)
- **Token Type**: Stateless JWT tokens (HS256 algorithm)
- **Storage**: None (tokens are self-contained)
- **Secret**: `JWT_SECRET` from environment variables
- **Expiration**: 7 days (configurable in `app/security.py`)

### Frontend (Next.js)
- **Storage**: `localStorage.getItem('autopip_jwt')`
- **Persistence**: Browser localStorage persists across deployments
- **No server-side sessions**: All auth state is client-side

## Critical Requirements

### JWT_SECRET Stability

**⚠️ CRITICAL**: The `JWT_SECRET` environment variable **MUST** be stable across all deployments. 

- **DO**: Set `JWT_SECRET` to a fixed, secure value in your Vercel environment variables
- **DON'T**: Auto-generate, regenerate, or change `JWT_SECRET` between deployments
- **DON'T**: Use random secrets that change on each deploy

**Why?** If `JWT_SECRET` changes, all existing JWT tokens become invalid, forcing users to log in again.

### Setting JWT_SECRET in Vercel

1. Go to your Vercel project settings
2. Navigate to "Environment Variables"
3. Add `JWT_SECRET` with a secure, random value (at least 32 characters)
4. **Important**: Use the same value for all environments (Production, Preview, Development)
5. Never change this value after setting it

**Generate a secure secret:**
```bash
# Generate a secure 64-character secret
openssl rand -hex 32
```

## Token Lifecycle

1. **Login**: User authenticates → Backend creates JWT → Frontend stores in `localStorage`
2. **Request**: Frontend reads token from `localStorage` → Sends in `Authorization: Bearer <token>` header
3. **Validation**: Backend verifies token signature using `JWT_SECRET`
4. **Persistence**: Token remains valid as long as:
   - Token hasn't expired (7 days)
   - `JWT_SECRET` hasn't changed
   - User hasn't explicitly logged out

## Deployment Behavior

### ✅ What Persists
- JWT tokens in browser `localStorage` (client-side)
- User authentication state (as long as token is valid)

### ❌ What Doesn't Persist
- No server-side session storage (by design - stateless)
- No in-memory session cache (none exists)

### 🔄 After Deployment
- Users remain logged in if:
  - Token is still valid (not expired)
  - `JWT_SECRET` matches the secret used to sign the token
- Users are logged out if:
  - Token has expired (after 7 days)
  - `JWT_SECRET` was changed
  - User explicitly logs out

## Security Considerations

### Token Security
- Tokens are signed with HS256 (HMAC-SHA256)
- Tokens contain user ID (`sub` claim) and expiration (`exp` claim)
- Tokens are validated on every request
- No sensitive data is stored in tokens

### localStorage Security
- Tokens are stored in browser `localStorage`
- `localStorage` is accessible to JavaScript (XSS risk)
- Mitigation: Use HTTPS, implement CSP headers, sanitize user input

### Secret Management
- `JWT_SECRET` must be at least 32 characters
- Never commit `JWT_SECRET` to version control
- Use environment variables for all environments
- Rotate secrets only when necessary (will invalidate all tokens)

## Troubleshooting

### Users Getting Logged Out After Deployment

**Symptom**: Users are logged out after a Vercel deployment

**Possible Causes**:
1. `JWT_SECRET` was changed → **Fix**: Restore the original secret or accept that users need to re-login
2. Token expired → **Fix**: User needs to log in again (expected after 7 days)
3. Frontend code changed localStorage key → **Fix**: Check if `autopip_jwt` key is still used

**Prevention**:
- Always use the same `JWT_SECRET` across deployments
- Document the secret value in a secure password manager
- Never auto-generate secrets in deployment scripts

### Token Validation Failing

**Symptom**: Valid tokens are rejected by the backend

**Check**:
1. Verify `JWT_SECRET` matches the secret used to sign tokens
2. Check token expiration (`exp` claim)
3. Verify token format (should be valid JWT)

## Migration Notes

If you need to change `JWT_SECRET` (e.g., security incident):

1. **Plan**: Notify users that they'll need to log in again
2. **Deploy**: Update `JWT_SECRET` in environment variables
3. **Result**: All existing tokens become invalid
4. **Recovery**: Users log in again to get new tokens

## Code References

- **Token Creation**: `app/security.py::create_jwt()`
- **Token Verification**: `app/security.py::verify_jwt()`
- **Settings**: `app/settings.py::Settings.JWT_SECRET`
- **Frontend Storage**: `lib/auth-context.tsx::readJwt()`
- **Auth Endpoints**: `app/auth.py::login()`, `app/auth.py::register()`

