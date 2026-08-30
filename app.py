from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Union
import base64
import json
import math
import os
import re
import secrets
import uuid
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pwdlib import PasswordHash
import jwt
from sqlalchemy import Column, Integer, String, Boolean, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# 1. DATABASE CONFIGURATION
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./messages.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Dependency to manage database session lifecycle per API request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 2. SQLALCHEMY DATABASE MODEL
class MessagesDB(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, index=True, nullable=False)
    username = Column(String(50), index=True, nullable=True)
    tags = Column(String, nullable=True)
    image_data = Column(String, nullable=True)
    created_at = Column(String, nullable=True)
    views = Column(Integer, default=0, nullable=True)


class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_guest = Column(Boolean, default=False, nullable=False)


# Generate database tables automatically
Base.metadata.create_all(bind=engine)


def ensure_message_columns():
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        columns = conn.execute(text("PRAGMA table_info(messages)")).fetchall()
        names = {column[1] for column in columns}
        if "image_data" not in names:
            conn.execute(
                text("ALTER TABLE messages ADD COLUMN image_data VARCHAR")
            )
        if "created_at" not in names:
            conn.execute(
                text("ALTER TABLE messages ADD COLUMN created_at VARCHAR")
            )
        if "views" not in names:
            conn.execute(
                text(
                    "ALTER TABLE messages ADD COLUMN views INTEGER DEFAULT 0"
                )
            )


ensure_message_columns()


# 3. PYDANTIC SCHEMAS (Data Validation & Serialization)
class MessageBase(BaseModel):
    text: str
    username: Optional[str] = None
    tags: Optional[List[str]] = None
    image_data: Optional[str] = None
    created_at: Optional[str] = None
    views: Optional[int] = 0
    reply_count: Optional[int] = 0
    replies_count: Optional[int] = 0


class MessageCreate(MessageBase):
    pass


class MessageResponse(MessageBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# 4. FASTAPI APPLICATION INITIALIZATION
app = FastAPI(title="FastAPI Auth + Messages API")
ROOT = Path(__file__).resolve().parent
app.mount(
    "/static", StaticFiles(directory=str(ROOT / "frontend")), name="static"
)


@app.get("/")
async def serve_frontend():
    frontend_path = ROOT / "frontend" / "index.html"
    return FileResponse(frontend_path)


@app.get("/info")
async def serve_info():
    frontend_path = ROOT / "frontend" / "index.html"
    return FileResponse(frontend_path)


BASE_URL = os.getenv(
    "BASE_URL", "https://adam-network.up.railway.app"
).rstrip("/")
SITEMAP_PAGE_SIZE = int(os.getenv("SITEMAP_PAGE_SIZE", "1000"))


def xml_escape(val: str) -> str:
    if not val:
        return ""
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_iso_timestamp(ts: Optional[str]) -> str:
    if not ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        if len(ts) >= 10 and ts[:10].count("-") == 2:
            return ts[:10]
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_all_unique_tags_with_metadata(db: Session) -> List[dict]:
    records = (
        db.query(MessagesDB.tags, MessagesDB.created_at)
        .filter(MessagesDB.tags.isnot(None), MessagesDB.tags != "")
        .all()
    )
    tag_map: Dict[str, dict] = {}
    for tags_val, created_at in records:
        tag_list = serialize_tags(tags_val)
        if not tag_list:
            continue
        for tag in tag_list:
            if not isinstance(tag, str):
                continue
            clean_tag = tag.strip()
            if not clean_tag:
                continue
            if clean_tag not in tag_map:
                tag_map[clean_tag] = {
                    "tag": clean_tag,
                    "lastmod": created_at,
                    "count": 1,
                }
            else:
                tag_map[clean_tag]["count"] += 1
                if created_at and (
                    not tag_map[clean_tag]["lastmod"]
                    or str(created_at) > str(tag_map[clean_tag]["lastmod"])
                ):
                    tag_map[clean_tag]["lastmod"] = created_at

    return sorted(tag_map.values(), key=lambda x: x["tag"].lower())


def get_latest_message_date(db: Session) -> Optional[str]:
    latest = (
        db.query(MessagesDB.created_at)
        .filter(MessagesDB.created_at.isnot(None))
        .order_by(MessagesDB.id.desc())
        .first()
    )
    return latest[0] if latest else None


@app.get("/robots.txt", response_class=PlainTextResponse)
def serve_robots():
    return f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"


@app.get("/sitemap.xml", response_class=Response)
@app.get("/sitemap_index.xml", response_class=Response)
def serve_sitemap_index(db: Session = Depends(get_db)):
    latest_msg_date = get_latest_message_date(db)
    now_iso = format_iso_timestamp(latest_msg_date)

    all_tags = get_all_unique_tags_with_metadata(db)
    total_tags = len(all_tags)
    tag_pages = max(1, math.ceil(total_tags / SITEMAP_PAGE_SIZE))

    total_messages = db.query(MessagesDB.id).count()
    message_pages = max(1, math.ceil(total_messages / SITEMAP_PAGE_SIZE))

    sitemaps_xml = [
        f"""  <sitemap>
    <loc>{xml_escape(f"{BASE_URL}/sitemap-pages.xml")}</loc>
    <lastmod>{now_iso}</lastmod>
  </sitemap>"""
    ]

    if tag_pages == 1:
        latest_tag_mod = now_iso
        if all_tags:
            tag_dates = [t["lastmod"] for t in all_tags if t["lastmod"]]
            if tag_dates:
                latest_tag_mod = format_iso_timestamp(max(tag_dates))
        sitemaps_xml.append(
            f"""  <sitemap>
    <loc>{xml_escape(f"{BASE_URL}/sitemap-tags.xml")}</loc>
    <lastmod>{latest_tag_mod}</lastmod>
  </sitemap>"""
        )
    else:
        for p in range(1, tag_pages + 1):
            sitemaps_xml.append(
                f"""  <sitemap>
    <loc>{xml_escape(f"{BASE_URL}/sitemap-tags-{p}.xml")}</loc>
    <lastmod>{now_iso}</lastmod>
  </sitemap>"""
            )

    if message_pages == 1:
        sitemaps_xml.append(
            f"""  <sitemap>
    <loc>{xml_escape(f"{BASE_URL}/sitemap-messages.xml")}</loc>
    <lastmod>{now_iso}</lastmod>
  </sitemap>"""
        )
    else:
        for p in range(1, message_pages + 1):
            sitemaps_xml.append(
                f"""  <sitemap>
    <loc>{xml_escape(f"{BASE_URL}/sitemap-messages-{p}.xml")}</loc>
    <lastmod>{now_iso}</lastmod>
  </sitemap>"""
            )

    sitemaps_content = "\n".join(sitemaps_xml)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{sitemaps_content}
</sitemapindex>"""
    return Response(content=content, media_type="application/xml")


@app.get("/sitemap-pages.xml", response_class=Response)
@app.get("/sitemaps/pages.xml", response_class=Response)
def serve_sitemap_pages(db: Session = Depends(get_db)):
    latest_msg_date = get_latest_message_date(db)
    now_iso = format_iso_timestamp(latest_msg_date)

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{xml_escape(f"{BASE_URL}/")}</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{xml_escape(f"{BASE_URL}/info")}</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>"""
    return Response(content=content, media_type="application/xml")


@app.get("/sitemap-tags.xml", response_class=Response)
@app.get("/sitemap-tags-{page}.xml", response_class=Response)
@app.get("/sitemaps/tags.xml", response_class=Response)
def serve_sitemap_tags(
    page: Optional[int] = None,
    p: Optional[int] = Query(default=None, alias="page", ge=1),
    db: Session = Depends(get_db),
):
    page_num = page or p or 1
    all_tags = get_all_unique_tags_with_metadata(db)
    total_tags = len(all_tags)
    total_pages = max(1, math.ceil(total_tags / SITEMAP_PAGE_SIZE))

    if page_num > total_pages and total_tags > 0:
        raise HTTPException(
            status_code=404,
            detail=f"Tag sitemap page {page_num} not found. Total pages: {total_pages}",
        )

    start_idx = (page_num - 1) * SITEMAP_PAGE_SIZE
    end_idx = start_idx + SITEMAP_PAGE_SIZE
    page_tags = all_tags[start_idx:end_idx]

    urls_xml = []
    for item in page_tags:
        tag_name = item["tag"]
        tag_encoded = quote(tag_name, safe="")
        loc = f"{BASE_URL}/?tags={tag_encoded}"
        lastmod = format_iso_timestamp(item["lastmod"])
        urls_xml.append(
            f"""  <url>
    <loc>{xml_escape(loc)}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>"""
        )

    urls_content = "\n".join(urls_xml)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_content}
</urlset>"""
    return Response(content=content, media_type="application/xml")


@app.get("/sitemap-messages.xml", response_class=Response)
@app.get("/sitemap-messages-{page}.xml", response_class=Response)
@app.get("/sitemaps/messages.xml", response_class=Response)
def serve_sitemap_messages(
    page: Optional[int] = None,
    p: Optional[int] = Query(default=None, alias="page", ge=1),
    db: Session = Depends(get_db),
):
    page_num = page or p or 1
    total_messages = db.query(MessagesDB.id).count()
    total_pages = max(1, math.ceil(total_messages / SITEMAP_PAGE_SIZE))

    if page_num > total_pages and total_messages > 0:
        raise HTTPException(
            status_code=404,
            detail=f"Message sitemap page {page_num} not found. Total pages: {total_pages}",
        )

    start_idx = (page_num - 1) * SITEMAP_PAGE_SIZE
    messages = (
        db.query(MessagesDB.id, MessagesDB.created_at)
        .order_by(MessagesDB.id.desc())
        .offset(start_idx)
        .limit(SITEMAP_PAGE_SIZE)
        .all()
    )

    urls_xml = []
    for msg_id, created_at in messages:
        loc = f"{BASE_URL}/?tags=message_reply_{msg_id}"
        lastmod = format_iso_timestamp(created_at)
        urls_xml.append(
            f"""  <url>
    <loc>{xml_escape(loc)}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>"""
        )

    urls_content = "\n".join(urls_xml)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_content}
</urlset>"""
    return Response(content=content, media_type="application/xml")


@app.get("/sitemap-all.xml", response_class=Response)
def serve_sitemap_all(db: Session = Depends(get_db)):
    latest_msg_date = get_latest_message_date(db)
    now_iso = format_iso_timestamp(latest_msg_date)

    urls_xml = [
        f"""  <url>
    <loc>{xml_escape(f"{BASE_URL}/")}</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""",
        f"""  <url>
    <loc>{xml_escape(f"{BASE_URL}/info")}</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""",
    ]

    all_tags = get_all_unique_tags_with_metadata(db)
    for item in all_tags:
        tag_encoded = quote(item["tag"], safe="")
        loc = f"{BASE_URL}/?tags={tag_encoded}"
        lastmod = format_iso_timestamp(item["lastmod"])
        urls_xml.append(
            f"""  <url>
    <loc>{xml_escape(loc)}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>"""
        )

    messages = (
        db.query(MessagesDB.id, MessagesDB.created_at)
        .order_by(MessagesDB.id.desc())
        .limit(SITEMAP_PAGE_SIZE)
        .all()
    )
    for msg_id, created_at in messages:
        loc = f"{BASE_URL}/?tags=message_reply_{msg_id}"
        lastmod = format_iso_timestamp(created_at)
        urls_xml.append(
            f"""  <url>
    <loc>{xml_escape(loc)}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>"""
        )

    urls_content = "\n".join(urls_xml)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_content}
</urlset>"""
    return Response(content=content, media_type="application/xml")


def sign_data(message: str, private_key_pem: bytes) -> str:
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem, password=None
        )
        data_bytes = message.encode("utf-8")
        signature = private_key.sign(
            data_bytes, padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Signing failed: {str(exc)}") from exc


# --- CONFIGURATION & SECURITY CONSTANTS ---
SECRET_KEY = os.getenv(
    "SECRET_KEY", "your-super-secret-key-change-this-in-production"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Initialize secure modern password hashing (Argon2 ID)
password_hash = PasswordHash.recommended()

# OAuth2 scheme redirects Swagger UI login to the /login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login", auto_error=False
)


# --- USER STORAGE ---
db_users: Dict[str, dict] = {}


def generate_guest_slug() -> str:
    """Generate a unique random alphanumeric slug for guest users."""
    return uuid.uuid4().hex[:6]


def ensure_guest_user(db: Session, username: Optional[str] = None) -> dict:
    """Ensure a guest user exists with a custom unique slug, e.g. 'guest-a1b2c3'."""
    clean_username = username.strip() if username else None
    if not clean_username or clean_username == "guest":
        clean_username = f"guest-{generate_guest_slug()}"

    guest = db.query(UserDB).filter(UserDB.username == clean_username).first()
    if guest is None:
        email = f"{clean_username}@example.com"
        while (
            db.query(UserDB)
            .filter(
                (UserDB.username == clean_username) | (UserDB.email == email)
            )
            .first()
        ):
            clean_username = f"guest-{generate_guest_slug()}"
            email = f"{clean_username}@example.com"

        guest = UserDB(
            username=clean_username,
            email=email,
            hashed_password=password_hash.hash("guest-password"),
            is_guest=True,
        )
        db.add(guest)
        db.commit()
        db.refresh(guest)
    return {
        "username": guest.username,
        "email": guest.email,
        "hashed_password": guest.hashed_password,
        "is_guest": guest.is_guest,
    }


def serialize_tags(
    tags_value: Optional[Union[str, List[str]]]
) -> Optional[List[str]]:
    if tags_value is None:
        return None
    if isinstance(tags_value, list):
        return tags_value
    try:
        parsed = json.loads(tags_value)
        if isinstance(parsed, list):
            return parsed
        return [str(parsed)]
    except (TypeError, ValueError):
        return [str(tags_value)]


def get_reply_count(db: Session, message_id: int) -> int:
    candidates = (
        db.query(MessagesDB.tags)
        .filter(
            (MessagesDB.tags.like(f"%message_reply_{message_id}%"))
            | (MessagesDB.tags.like(f"%messsage_reply_{message_id}%")),
            MessagesDB.id != message_id,
        )
        .all()
    )
    count = 0
    target1 = f"message_reply_{message_id}"
    target2 = f"messsage_reply_{message_id}"
    for (tags_val,) in candidates:
        tags_list = serialize_tags(tags_val)
        if tags_list and (target1 in tags_list or target2 in tags_list):
            count += 1
    return count


def normalize_message(
    item: MessagesDB,
    db: Optional[Session] = None,
    reply_count: Optional[int] = None,
) -> dict:
    if reply_count is None:
        if db is not None:
            reply_count = get_reply_count(db, item.id)
        else:
            reply_count = 0
    return {
        "id": item.id,
        "text": item.text,
        "username": item.username,
        "tags": serialize_tags(item.tags),
        "image_data": item.image_data,
        "created_at": item.created_at,
        "views": item.views if item.views is not None else 0,
        "reply_count": reply_count,
        "replies_count": reply_count,
    }


# --- PYDANTIC SCHEMAS (Data Validation) ---
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    username: str
    email: EmailStr
    is_guest: Optional[bool] = False


class LogoutResponse(BaseModel):
    message: str


class Token(BaseModel):
    access_token: str
    token_type: str


# --- UTILITY FUNCTIONS ---
def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """Generates a secure JSON Web Token (JWT)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=15)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: Annotated[Optional[str], Depends(optional_oauth2_scheme)],
    x_guest_name: Annotated[
        Optional[str], Header(alias="X-Guest-Name")
    ] = None,
    db: Session = Depends(get_db),
) -> dict:
    """Return the current user; if no token is provided, use the guest account with unique slug."""
    if token is None:
        return ensure_guest_user(db, username=x_guest_name)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            return ensure_guest_user(db, username=x_guest_name)
    except jwt.PyJWTError:
        return ensure_guest_user(db, username=x_guest_name)

    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user is None:
        return ensure_guest_user(db, username=x_guest_name)
    return {
        "username": user.username,
        "email": user.email,
        "hashed_password": user.hashed_password,
        "is_guest": user.is_guest,
    }


def get_db_user_by_username(db: Session, username: str) -> Optional[dict]:
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user is None:
        return None
    return {
        "username": user.username,
        "email": user.email,
        "hashed_password": user.hashed_password,
        "is_guest": user.is_guest,
    }


async def get_current_user_required(
    token: Annotated[Optional[str], Depends(optional_oauth2_scheme)],
    db: Session = Depends(get_db),
) -> dict:
    """Require a real authenticated user for mutating routes."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required to create messages",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login required to create messages",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required to create messages",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(UserDB).filter(UserDB.username == username).first()
    if (
        user is None
        or user.username == "guest"
        or user.is_guest
        or user.username.startswith("guest-")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required to create messages",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "username": user.username,
        "email": user.email,
        "hashed_password": user.hashed_password,
        "is_guest": user.is_guest,
    }


# --- API ROUTING ENDPOINTS ---
@app.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """Handles new user sign-ups and securely hashes their password."""
    if user_in.password != user_in.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    existing_username = (
        db.query(UserDB).filter(UserDB.username == user_in.username).first()
    )
    if existing_username:
        raise HTTPException(
            status_code=400, detail="Username already registered"
        )

    existing_email = (
        db.query(UserDB).filter(UserDB.email == user_in.email).first()
    )
    if existing_email:
        raise HTTPException(
            status_code=400, detail="Email already registered"
        )

    hashed_password = password_hash.hash(user_in.password)
    new_user = UserDB(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_password,
        is_guest=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    db_users[user_in.username] = {
        "username": new_user.username,
        "email": new_user.email,
        "hashed_password": new_user.hashed_password,
        "is_guest": new_user.is_guest,
    }
    return {"username": new_user.username, "email": new_user.email}


@app.post("/logout", response_model=LogoutResponse)
async def logout(current_user: Annotated[dict, Depends(get_current_user)]):
    """Logs a user out by returning a clear message; the client should discard the token."""
    if current_user.get("is_guest"):
        return {"message": "Guest session ended."}
    return {
        "message": f"User {current_user['username']} logged out successfully."
    }


@app.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """Authenticates credentials against the database and returns a bearer JWT."""
    user = get_db_user_by_username(db, form_data.username)
    if not user:
        raise HTTPException(
            status_code=400, detail="Incorrect username or password"
        )

    if not password_hash.verify(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=400, detail="Incorrect username or password"
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=UserResponse)
async def read_users_me(
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Return the currently authenticated user or guest profile."""
    return current_user


# 5. CRUD ENDPOINTS
@app.post(
    "/messages/",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    current_user: Annotated[dict, Depends(get_current_user)],
    item: MessageCreate,
    db: Session = Depends(get_db),
):
    created_at = item.created_at or datetime.now(timezone.utc).isoformat()
    if current_user.get("is_guest"):
        if (
            item.username
            and item.username.strip()
            and item.username.strip() != "guest"
        ):
            guest_user = ensure_guest_user(db, username=item.username.strip())
            author_username = guest_user["username"]
        else:
            author_username = current_user["username"]
    else:
        author_username = current_user["username"]

    db_item = MessagesDB(
        text=item.text,
        username=author_username,
        tags=json.dumps(item.tags) if item.tags is not None else None,
        image_data=item.image_data,
        created_at=created_at,
        views=0,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return normalize_message(db_item, db=db, reply_count=0)


@app.get("/messages/", response_model=List[MessageResponse])
def read_items(
    current_user: Annotated[dict, Depends(get_current_user)],
    skip: int = 0,
    limit: int = 1000,
    order: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(MessagesDB)
    if order == "desc":
        query = query.order_by(MessagesDB.id.desc())
    messages = query.offset(skip).limit(limit).all()
    for message in messages:
        message.views = (message.views or 0) + 1
    db.commit()
    for message in messages:
        db.refresh(message)
    return [normalize_message(message, db=db) for message in messages]


@app.get("/search_messages/", response_model=List[MessageResponse])
def search_items(
    current_user: Annotated[dict, Depends(get_current_user)],
    skip: int = 0,
    limit: int = 1000,
    tags: Optional[str] = None,
    search_text: Optional[str] = None,
    db: Session = Depends(get_db),
):
    reply_target_id = None
    if tags:
        match = re.search(r"messs?age_reply_(\d+)", tags.strip())
        if match:
            reply_target_id = int(match.group(1))

    query = db.query(MessagesDB)
    if tags:
        if reply_target_id is not None:
            query = query.filter(
                (MessagesDB.tags.like(f"%message_reply_{reply_target_id}%"))
                | (
                    MessagesDB.tags.like(
                        f"%messsage_reply_{reply_target_id}%"
                    )
                )
                | (MessagesDB.tags.like(f"%{tags}%"))
            )
        else:
            query = query.filter(MessagesDB.tags.like(f"%{tags}%"))

    if search_text:
        query = query.filter(MessagesDB.text.contains(search_text))

    messages = query.all()
    if reply_target_id is not None:
        orig = (
            db.query(MessagesDB)
            .filter(MessagesDB.id == reply_target_id)
            .first()
        )
        if orig:
            reply_messages = [m for m in messages if m.id != reply_target_id]
            messages = [orig] + reply_messages

    paged_messages = messages[skip : skip + limit]
    for message in paged_messages:
        message.views = (message.views or 0) + 1
    db.commit()
    for message in paged_messages:
        db.refresh(message)
    return [normalize_message(message, db=db) for message in paged_messages]


@app.get("/messages/{message_id}", response_model=MessageResponse)
def read_item(
    current_user: Annotated[dict, Depends(get_current_user)],
    message_id: int,
    db: Session = Depends(get_db),
):
    db_item = db.query(MessagesDB).filter(MessagesDB.id == message_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Message not found")
    db_item.views = (db_item.views or 0) + 1
    db.commit()
    db.refresh(db_item)
    return normalize_message(db_item, db=db)
