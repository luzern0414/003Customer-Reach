"""账号、登录会话与使用次数。密码用 PBKDF2-SHA256 加盐保存，会话令牌只存哈希。"""
import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from .config import ADMIN_PASSWORD, ADMIN_USERNAME, DEFAULT_QUOTA, SESSION_DAYS
from .db import Conversation, Session, User, UserSession, now

COOKIE = 'dealradar_session'
ITERATIONS = 240_000
USERNAME = re.compile(r'^[A-Za-z0-9_一-鿿]{3,20}$')
# 节流（单进程内存）：同一用户名 10 分钟内失败 5 次锁定；同一 IP 每小时最多注册 5 个账号
_FAILURES: dict[str, list[float]] = {}
_WINDOW, _MAX_FAILURES = 600, 5
_REGISTRATIONS: dict[str, list[float]] = {}
_REGISTER_WINDOW, _MAX_REGISTRATIONS = 3600, 5
# 用户名不存在时也做一次同成本的哈希比对，避免按响应时间判断用户名是否存在
_DUMMY_HASH = ''


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}'


def check_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def view(user: User) -> dict:
    unlimited = user.quota is None
    return {'id': user.id, 'username': user.username, 'is_admin': bool(user.is_admin), 'unlimited': unlimited,
            'quota': user.quota, 'used': user.used, 'remaining': None if unlimited else max(user.quota - user.used, 0)}


def ensure_admin() -> None:
    """首次启动创建管理员账号；已存在时保持其权限与不限次数，不改密码。"""
    with Session.begin() as db:
        admin = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
        if admin:
            admin.is_admin, admin.quota = 1, None
        else:
            admin = User(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD), is_admin=1, quota=None)
            db.add(admin)
            db.flush()
        # 启用账号前创建的对话归管理员
        db.execute(update(Conversation).where(Conversation.user_id.is_(None)).values(user_id=admin.id))


def _new_session(db, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat()
    db.add(UserSession(token_hash=_token_hash(token), user_id=user.id, expires_at=expires))
    user.last_login_at = now()
    return token


def _recent(store: dict[str, list[float]], key: str, window: int) -> list[float]:
    store[key] = [t for t in store.get(key, []) if time.time() - t < window]
    return store[key]


def register(username: str, password: str, client: str = '') -> tuple[dict, str]:
    username = username.strip()
    registrations = _recent(_REGISTRATIONS, client, _REGISTER_WINDOW)
    if len(registrations) >= _MAX_REGISTRATIONS:
        raise AuthError('注册过于频繁，请 1 小时后再试', 429)
    if not USERNAME.match(username):
        raise AuthError('用户名为 3–20 位中文、字母、数字或下划线')
    if len(password) < 6 or len(password) > 64:
        raise AuthError('密码长度为 6–64 位')
    with Session.begin() as db:
        if db.scalar(select(User.id).where(User.username == username)):
            raise AuthError('用户名已被注册', 409)
        user = User(username=username, password_hash=hash_password(password), quota=DEFAULT_QUOTA)
        db.add(user)
        db.flush()
        registrations.append(time.time())
        return view(user), _new_session(db, user)


def login(username: str, password: str) -> tuple[dict, str]:
    global _DUMMY_HASH
    username = username.strip()
    failures = _recent(_FAILURES, username, _WINDOW)
    if len(failures) >= _MAX_FAILURES:
        minutes = max(1, round((failures[0] + _WINDOW - time.time()) / 60))
        raise AuthError(f'登录失败次数过多，请 {minutes} 分钟后再试', 429)
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.username == username))
        if not user:
            _DUMMY_HASH = _DUMMY_HASH or hash_password(secrets.token_hex(8))
            check_password(password, _DUMMY_HASH)
        if not user or not check_password(password, user.password_hash):
            failures.append(time.time())
            raise AuthError('账号或密码错误', 401)
        _FAILURES.pop(username, None)
        return view(user), _new_session(db, user)


def logout(token: str) -> None:
    with Session.begin() as db:
        db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))


def user_for(token: str | None) -> dict | None:
    if not token:
        return None
    with Session() as db:
        session = db.get(UserSession, _token_hash(token))
        if not session:
            return None
        if session.expires_at < now():
            db.delete(session)
            db.commit()
            return None
        user = db.get(User, session.user_id)
        return view(user) if user else None


def consume(db, user_id: str) -> None:
    """在发起研究的同一事务内扣减一次；次数用完时整个提交回滚。"""
    result = db.execute(update(User).where(User.id == user_id, (User.quota.is_(None)) | (User.used < User.quota))
                        .values(used=User.used + 1))
    if result.rowcount == 0:
        raise AuthError('使用次数已用完', 403)
