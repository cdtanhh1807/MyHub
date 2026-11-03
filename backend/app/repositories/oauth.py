"""OAuth provider adapter, không phụ thuộc Request/Response của FastAPI."""
import base64
import hashlib
from authlib.integrations.httpx_client import AsyncOAuth2Client
from app.core.errors import AppError


class OAuthRepository:
    """Đổi code và đọc profile từ endpoint cố định của nhà cung cấp."""
    def __init__(self, settings, http):
        """Nhận cấu hình và HTTP pool do lifespan quản lý."""
        self.settings, self.http = settings, http

    def client(self, provider, redirect_uri):
        """Chọn client tương ứng; thiếu credentials thì báo rõ trước redirect."""
        google = provider in ('google', 'drive')
        client_id = self.settings.google_client_id if google else self.settings.github_client_id
        secret = self.settings.google_client_secret if google else self.settings.github_client_secret
        if not client_id or not secret:
            raise AppError('oauth_not_configured', 503)
        return AsyncOAuth2Client(client_id, secret, redirect_uri=redirect_uri, token_endpoint_auth_method='client_secret_post')

    async def authorization_url(self, provider, redirect_uri, state, verifier):
        """Tạo URL có state + PKCE; Drive yêu cầu offline và consent riêng."""
        google = provider in ('google', 'drive')
        endpoint = 'https://accounts.google.com/o/oauth2/v2/auth' if google else 'https://github.com/login/oauth/authorize'
        scope = 'openid email profile' if google else 'read:user'
        if provider == 'drive':
            scope += ' https://www.googleapis.com/auth/drive'
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        extra = {'access_type': 'offline', 'prompt': 'consent', 'login_hint': self.settings.allowed_google_email} if provider == 'drive' else {}
        async with self.client(provider, redirect_uri) as client:
            url, _ = client.create_authorization_url(endpoint, state=state, scope=scope, code_challenge=challenge, code_challenge_method='S256', **extra)
        return url

    async def exchange(self, provider, redirect_uri, code, verifier):
        """Code một lần → token → profile HTTPS; không dùng email từ trình duyệt."""
        google = provider in ('google', 'drive')
        endpoint = 'https://oauth2.googleapis.com/token' if google else 'https://github.com/login/oauth/access_token'
        try:
            async with self.client(provider, redirect_uri) as client:
                token = await client.fetch_token(endpoint, code=code, code_verifier=verifier)
            profile = await self.http.get('https://openidconnect.googleapis.com/v1/userinfo' if google else 'https://api.github.com/user',
                headers={'Authorization': f"Bearer {token['access_token']}", 'Accept': 'application/json'})
            profile.raise_for_status()
            return token, profile.json()
        except (AppError,):
            raise
        except Exception:
            raise AppError('oauth_failed', 401) from None
