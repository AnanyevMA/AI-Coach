from typing import Optional
from pydantic import BaseModel, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "athlete"  # "athlete" or "coach"
    
    # 152-FZ Mandatory Consents
    consent_personal_data: bool = True
    consent_health_data: bool = True
    legal_document_version: str = "v1.0"


class UserLogin(BaseModel):
    email: str
    password: str


class ConsentLogCreate(BaseModel):
    consent_type: str
    is_granted: bool = True
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    legal_document_version: str = "v1.0"


class ConsentLogOut(BaseModel):
    id: int
    user_id: int
    consent_type: str
    is_granted: bool
    legal_document_version: str
    timestamp: str

    model_config = ConfigDict(from_attributes=True)
