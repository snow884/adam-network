from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Union
import base64
import json
import os
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException, status
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


@app.get("/robots.txt", response_class=PlainTextResponse)
def serve_robots():
    return "User-agent: *\nAllow: /\nSitemap: https://adam-network.up.railway.app/sitemap.xml\n"


@app.get("/sitemap.xml")
def serve_sitemap():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://adam-network.up.railway.app/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://adam-network.up.railway.app/info</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
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


def ensure_guest_user(db: Session) -> dict:
    guest = db.query(UserDB).filter(UserDB.username == "guest").first()
    if guest is None:
        guest = UserDB(
            username="guest",
            email="guest@example.com",
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
    db: Session = Depends(get_db),
) -> dict:
    """Return the current user; if no token is provided, use the guest account."""
    if token is None:
        return ensure_guest_user(db)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            return ensure_guest_user(db)
    except jwt.PyJWTError:
        return ensure_guest_user(db)

    user = db.query(UserDB).filter(UserDB.username == username).first()
    if user is None:
        return ensure_guest_user(db)
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
    if user is None or user.username == "guest":
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
    db_item = MessagesDB(
        text=item.text,
        username=current_user["username"],
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
