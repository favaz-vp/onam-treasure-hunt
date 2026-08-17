"""Authentication endpoints.

These reproduce, path for path and body for body, the subset of djoser +
SimpleJWT that this game actually used, on top of django-bolt's JWT. Clients
cannot tell the difference; only the token internals changed, so tokens minted
by the old stack do not validate here and every client re-logs in once.

What is deliberately not carried over: djoser's activation, password-reset and
username-reset flows. They all send mail, and no EMAIL_BACKEND was ever
configured, so they could not have worked in the first place.
"""
import jwt as pyjwt
import msgspec
from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError

from django_bolt import JSON, Router
from django_bolt.auth import (
    AllowAny,
    InMemoryRevocation,
    TokenRotationError,
    create_token_pair,
    rotate_refresh_token,
)
from django_bolt.exceptions import HTTPException

from config.concurrency import run_db
from config.security import DEFAULT_AUTH, DEFAULT_GUARDS

from .models import User
from .schemas import UserOut, user_out

auth_router = Router(
    prefix="/api/auth", tags=["auth"],
    auth=DEFAULT_AUTH, guards=DEFAULT_GUARDS,
)

# Backs refresh-token rotation: a refresh token stops working the moment it is
# exchanged, which is what ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION
# bought us before. In process memory, and correct for the same reason
# users/sse.py is — the server runs as a single process.
_revocations = InMemoryRevocation()

# SimpleJWT's wording, kept so clients matching on it keep matching.
_INVALID_TOKEN = {"detail": "Token is invalid or expired", "code": "token_not_valid"}


class RegisterIn(msgspec.Struct):
    email: str
    password: str
    re_password: str


class RegisterOut(msgspec.Struct):
    email: str
    id: int


class LoginIn(msgspec.Struct):
    email: str
    password: str


class TokenPairOut(msgspec.Struct):
    access: str
    refresh: str


class RefreshIn(msgspec.Struct):
    refresh: str


class VerifyIn(msgspec.Struct):
    token: str


def _issue_pair(user) -> TokenPairOut:
    pair = create_token_pair(
        user,
        access_ttl=settings.ACCESS_TOKEN_LIFETIME,
        refresh_ttl=settings.REFRESH_TOKEN_LIFETIME,
    )
    return TokenPairOut(access=pair.access_token, refresh=pair.refresh_token)


def _invalid_token() -> JSON:
    """SimpleJWT's 401 body, which carries `code` alongside `detail`.

    Returned rather than raised: Bolt's HTTPException would file the `code`
    under an `extra` key, which is not where clients look for it.
    """
    return JSON(dict(_INVALID_TOKEN), status_code=401)


def _decode(token: str, expect_typ: str | None = None) -> dict | None:
    """Verify a token's signature and expiry, and optionally its type.

    These endpoints take their token from the JSON body rather than a header
    or cookie, so Bolt's Rust validator never sees it and this does the
    cryptographic half itself. rotate_refresh_token() does the stateful half.
    """
    try:
        claims = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        return None
    if expect_typ is not None and claims.get("typ") != expect_typ:
        return None
    return claims


@auth_router.post(
    "/users/",
    guards=[AllowAny()],
    status_code=201,
    summary="Register",
    response_model=RegisterOut,
    # The failure bodies are djoser's bare {field: [messages]} shape, which is
    # not RegisterOut; the model stays for the OpenAPI document only.
    validate_response=False,
)
async def register(payload: RegisterIn):
    """Create an account. The user manager assigns the new user to a team.

    The rejections are returned rather than raised because djoser reported
    field errors as a bare ``{field: [messages]}`` body, and Bolt's exception
    handler would nest them under a ``detail``/``extra`` envelope instead.
    """
    if payload.password != payload.re_password:
        return JSON(
            {"non_field_errors": ["The two password fields didn't match."]},
            status_code=400,
        )
    return await run_db(_create_user, payload)


def _create_user(payload: RegisterIn):
    if User.objects.filter(email__iexact=payload.email).exists():
        return JSON(
            {"email": ["user with this email address already exists."]},
            status_code=400,
        )

    try:
        password_validation.validate_password(payload.password)
    except ValidationError as exc:
        return JSON({"password": list(exc.messages)}, status_code=400)

    user = User.objects.create_user(email=payload.email, password=payload.password)
    return RegisterOut(email=user.email, id=user.id)


@auth_router.post(
    "/jwt/create/",
    guards=[AllowAny()],
    summary="Obtain token pair",
    response_model=TokenPairOut,
)
async def jwt_create(payload: LoginIn):
    return await run_db(_authenticate, payload)


def _authenticate(payload: LoginIn):
    user = authenticate(username=payload.email, password=payload.password)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="No active account found with the given credentials",
        )
    return _issue_pair(user)


@auth_router.post(
    "/jwt/refresh/",
    guards=[AllowAny()],
    summary="Refresh token pair",
    response_model=TokenPairOut,
    validate_response=False,  # the 401 body is SimpleJWT's, not a token pair
)
async def jwt_refresh(payload: RefreshIn):
    """Exchange a refresh token for a fresh pair, invalidating the old one.

    Returns both tokens, not just the access token, because rotation is on —
    the same thing SimpleJWT did under ROTATE_REFRESH_TOKENS.
    """
    claims = _decode(payload.refresh, expect_typ="refresh")
    if claims is None:
        return _invalid_token()
    try:
        pair = await rotate_refresh_token(
            claims,
            store=_revocations,
            access_ttl=settings.ACCESS_TOKEN_LIFETIME,
            refresh_ttl=settings.REFRESH_TOKEN_LIFETIME,
        )
    except TokenRotationError:
        return _invalid_token()
    return TokenPairOut(access=pair.access_token, refresh=pair.refresh_token)


@auth_router.post("/jwt/verify/", guards=[AllowAny()], summary="Verify a token")
def jwt_verify(payload: VerifyIn):
    if _decode(payload.token) is None:
        return _invalid_token()
    return {}


@auth_router.get("/users/me/", summary="Current user")
async def users_me(request) -> UserOut:
    return await run_db(lambda: user_out(request.user))
