# Password hashing/verification helpers (bcrypt).
import bcrypt

# The obvious ones people actually pick. Kept short on purpose — this is a
# lenient guard, not a strict policy.
_COMMON_WEAK = frozenset(
    {
        "password",
        "password1",
        "passw0rd",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty",
        "qwerty123",
        "qwertyuiop",
        "iloveyou",
        "letmein",
        "welcome",
        "welcome1",
        "admin123",
        "changeme",
        "abc12345",
        "football",
        "monkey123",
    }
)


def validate_password_strength(password: str) -> str:
    """Reject only clearly weak passwords; passphrases and normal ones pass.

    Length itself is enforced by the schema field; this adds a few cheap sanity
    checks so no one signs up with '12345678' or 'aaaaaaaa'.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if password.isdigit():
        raise ValueError("Password must not be only digits")
    if len(set(password)) < 4:
        raise ValueError("Password is too repetitive")
    if password.lower() in _COMMON_WEAK:
        raise ValueError("Password is too common — please choose a less obvious one")
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
