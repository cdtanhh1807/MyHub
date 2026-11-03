"""Nghiệp vụ whitelist, PKCE/state, phiên JWT và Drive credential dùng chung."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from cryptography.fernet import Fernet
from app.core.errors import AppError
from app.dtos.contracts import ResultDTO


def digest(value):
    """Chỉ lưu hash của token ngẫu nhiên, không lưu bearer secret dạng rõ."""
    return hashlib.sha256(value.encode()).hexdigest()


class AuthService:
    """Service độc lập HTTP; Controller phụ trách cookie/redirect/header."""
    def __init__(self, settings, mongo, oauth, drive):
        """Ghép các repository để xử lý auth và kết nối Drive riêng biệt."""
        self.settings, self.mongo, self.oauth, self.drive = settings, mongo, oauth, drive

    def allowed(self, provider, profile):
        """Google cần email verified; GitHub chỉ đối chiếu login, không dùng numeric ID."""
        if provider in ('google', 'drive'):
            return profile.get('email', '').lower() == self.settings.allowed_google_email.lower() and profile.get('email_verified') is True
        return profile.get('login', '').lower() == self.settings.allowed_github_username.lower()

    def callback_uri(self, provider):
        """Một nguồn redirect URI dùng cho cả authorize lẫn token exchange."""
        return f'{self.settings.backend_url}/api/v1/auth/{provider}/callback'

    async def begin(self, provider, user=None):
        """Tạo state + bí mật trình duyệt + PKCE, lưu state có TTL trong MongoDB."""
        if provider not in ('google', 'github', 'drive'):
            raise AppError('unknown_provider', 404)
        if provider == 'drive' and not user:
            raise AppError('unauthorized', 401)
        state, browser, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        url = await self.oauth.authorization_url(provider, self.callback_uri(provider), state, verifier)
        await self.mongo.put('oauth_states', digest(state), {'provider': provider, 'browser': digest(browser), 'verifier': verifier,
            'user_id': user['id'] if user else None, 'expires_at': datetime.now(timezone.utc) + timedelta(minutes=10)})
        return ResultDTO(data={'url': url, 'browser': browser})

    async def callback(self, provider, state, browser, code, current_user=None):
        """Consume state nguyên tử → đối chiếu browser/provider → đổi code → whitelist."""
        record = await self.mongo.consume('oauth_states', digest(state))
        if not record or record['provider'] != provider or not secrets.compare_digest(record['browser'], digest(browser)):
            raise AppError('invalid_oauth_state', 401)
        if provider == 'drive' and (not current_user or current_user['id'] != record['user_id']):
            raise AppError('unauthorized', 401)
        token, profile = await self.oauth.exchange(provider, self.callback_uri(provider), code, record['verifier'])
        if not self.allowed(provider, profile):
            raise AppError('account_not_allowed', 403)
        if provider == 'drive':
            if token.get('scope') and 'https://www.googleapis.com/auth/drive' not in token['scope'].split():
                raise AppError('drive_scope_missing', 409)
            if not token.get('refresh_token'):
                raise AppError('drive_refresh_token_missing', 409)
            encrypted = Fernet(self.settings.encryption_key.encode()).encrypt(token['refresh_token'].encode()).decode()
            await self.mongo.put('drive_credentials', 'owner', {'email': profile['email'], 'encrypted_token': encrypted})
            self.drive._token, self.drive._expires = '', 0
            return ResultDTO(data={'drive_connected': True})
        identity = profile['email'] if provider == 'google' else profile['login']
        user = {'id': f'{provider}:{identity.lower()}', 'provider': provider, 'identity': identity,
            'name': profile.get('name') or identity, 'avatar': profile.get('picture') or profile.get('avatar_url'),
            'last_login': datetime.now(timezone.utc)}
        await self.mongo.put('users', user['id'], user)
        return await self.create_session(user)

    async def create_session(self, user):
        """Phiên lưu hash refresh token → JWT ngắn hạn trỏ tới phiên có thể thu hồi."""
        refresh = secrets.token_urlsafe(48)
        session_id = digest(refresh)
        now = datetime.now(timezone.utc)
        await self.mongo.put('refresh_sessions', session_id, {'user_id': user['id'], 'expires_at': now + timedelta(days=self.settings.refresh_token_expire_days)})
        access = jwt.encode({'sub': user['id'], 'sid': session_id, 'type': 'access', 'iat': now,
            'exp': now + timedelta(minutes=self.settings.access_token_expire_minutes), 'iss': 'myhub', 'aud': 'myhub-api'}, self.settings.jwt_secret_key, algorithm='HS256')
        return ResultDTO(data={'access_token': access, 'refresh_token': refresh, 'user': {k: v for k, v in user.items() if k not in ('_id', 'last_login')}})

    async def user_for_session(self, session_id):
        """TTL Mongo xóa trễ vẫn an toàn vì luôn kiểm tra expires_at trước khi nhận phiên."""
        session = await self.mongo.get('refresh_sessions', session_id)
        if not session or session['expires_at'] <= datetime.now(timezone.utc):
            raise AppError('unauthorized', 401)
        user = await self.mongo.get('users', session['user_id'])
        if not user:
            raise AppError('unauthorized', 401)
        return user

    async def authenticate(self, access):
        """Verify thuật toán/issuer/audience/expiry → kiểm tra phiên còn hoạt động."""
        try:
            payload = jwt.decode(access, self.settings.jwt_secret_key, algorithms=['HS256'], issuer='myhub', audience='myhub-api', options={'require': ['exp', 'iat', 'sub', 'sid', 'type']})
            if payload['type'] != 'access':
                raise jwt.InvalidTokenError()
        except jwt.PyJWTError:
            raise AppError('unauthorized', 401) from None
        user = await self.user_for_session(payload['sid'])
        if user['id'] != payload['sub']:
            raise AppError('unauthorized', 401)
        return user

    async def refresh(self, refresh):
        """Xoay refresh một lần bằng consume nguyên tử, token cũ không tái sử dụng được."""
        session = await self.mongo.consume('refresh_sessions', digest(refresh))
        if not session:
            raise AppError('unauthorized', 401)
        user = await self.mongo.get('users', session['user_id'])
        if not user:
            raise AppError('unauthorized', 401)
        return await self.create_session(user)

    async def logout(self, refresh):
        """Thu hồi session tương ứng nên access JWT liên quan cũng mất hiệu lực."""
        if refresh:
            await self.mongo.remove('refresh_sessions', digest(refresh))
        return ResultDTO(data={'logged_out': True})

    async def connection(self):
        """Kiểm tra token thực tế, không chỉ kiểm tra có document credential."""
        try:
            await self.drive.access_token()
            root = await self.drive.get(self.settings.google_drive_root_folder_id)
            if root['mimeType'] != 'application/vnd.google-apps.folder' or root.get('trashed'):
                raise AppError('invalid_drive_root', 409)
            return ResultDTO(data={'connected': True})
        except AppError as error:
            return ResultDTO(data={'connected': False, 'reason': error.code})

    async def profile(self, user):
        """Service tạo DTO profile công khai, không để Controller tự tạo dữ liệu phản hồi."""
        return ResultDTO(data={k: v for k, v in user.items() if k not in ('_id', 'last_login')})

    async def media_grant(self, access, workspace_id, file_id):
        """Cấp cookie media ngắn hạn theo một file để video/download không cần buffer Blob."""
        user = await self.authenticate(access)
        payload = jwt.decode(access, self.settings.jwt_secret_key, algorithms=['HS256'], issuer='myhub', audience='myhub-api')
        now = datetime.now(timezone.utc)
        token = jwt.encode({'sub': user['id'], 'sid': payload['sid'], 'workspace': workspace_id, 'file': file_id,
            'type': 'media', 'iat': now, 'exp': now + timedelta(minutes=30), 'iss': 'myhub', 'aud': 'myhub-media'}, self.settings.jwt_secret_key, algorithm='HS256')
        return ResultDTO(data={'token': token})

    async def media_user(self, token, workspace_id, file_id):
        """Chỉ cookie đúng Workspace/file và phiên đang hoạt động mới đọc được media."""
        try:
            payload = jwt.decode(token, self.settings.jwt_secret_key, algorithms=['HS256'], issuer='myhub', audience='myhub-media')
            if payload.get('type') != 'media' or payload.get('workspace') != workspace_id or payload.get('file') != file_id:
                raise jwt.InvalidTokenError()
        except jwt.PyJWTError:
            raise AppError('unauthorized', 401) from None
        user = await self.user_for_session(payload['sid'])
        if user['id'] != payload['sub']:
            raise AppError('unauthorized', 401)
        return user
