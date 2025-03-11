import uuid
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError
from sftkit.database import Connection
from sftkit.service import Service, with_db_transaction

from stustapay.core.config import Config
from stustapay.core.schema.customer import Customer
from stustapay.core.schema.terminal import CurrentTerminal, Terminal
from stustapay.core.schema.till import Till
from stustapay.core.schema.user import CurrentUser


class UserTokenMetadata(BaseModel):
    user_id: int
    session_id: int


class CustomerTokenMetadata(BaseModel):
    customer_id: int
    session_id: int


class TerminalTokenMetadata(BaseModel):
    terminal_id: int
    session_uuid: uuid.UUID


class AuthService(Service[Config]):
    """
    Extra service to check login tokens
    It is needed in every service with uses `requires_user_privileges` or `requires_terminal`
    """

    def decode_user_jwt_payload(self, token: str) -> Optional[UserTokenMetadata]:
        try:
            payload = jwt.decode(token, self.config.core.secret_key, algorithms=[self.config.core.jwt_token_algorithm])
            try:
                return UserTokenMetadata.model_validate(payload)
            except ValidationError:
                return None
        except JWTError:
            return None

    def create_user_access_token(self, token_metadata: UserTokenMetadata) -> str:
        to_encode = {"user_id": token_metadata.user_id, "session_id": token_metadata.session_id}
        encoded_jwt = jwt.encode(to_encode, self.config.core.secret_key, algorithm=self.config.core.jwt_token_algorithm)
        return encoded_jwt

    def decode_customer_jwt_payload(self, token: str) -> Optional[CustomerTokenMetadata]:
        try:
            payload = jwt.decode(token, self.config.core.secret_key, algorithms=[self.config.core.jwt_token_algorithm])
            try:
                return CustomerTokenMetadata.model_validate(payload)
            except ValidationError:
                return None
        except JWTError:
            return None

    def create_customer_access_token(self, token_metadata: CustomerTokenMetadata) -> str:
        to_encode = {"customer_id": token_metadata.customer_id, "session_id": token_metadata.session_id}
        encoded_jwt = jwt.encode(to_encode, self.config.core.secret_key, algorithm=self.config.core.jwt_token_algorithm)
        return encoded_jwt

    @with_db_transaction(read_only=True)
    async def get_user_from_token(self, *, conn: Connection, token: str) -> Optional[CurrentUser]:
        token_payload = self.decode_user_jwt_payload(token)
        if token_payload is None:
            return None

        return await conn.fetch_maybe_one(
            CurrentUser,
            "select u.*, null as active_role_id, '{}'::text array as privileges "
            "from user_with_tag u join usr_session s on u.id = s.usr "
            "where u.id = $1 and s.id = $2 ",
            token_payload.user_id,
            token_payload.session_id,
        )

    @with_db_transaction(read_only=True)
    async def get_customer_from_token(self, *, conn: Connection, token: str) -> Optional[Customer]:
        token_payload = self.decode_customer_jwt_payload(token)
        if token_payload is None:
            return None

        return await conn.fetch_maybe_one(
            Customer,
            "select c.*, s.id as session_id "
            "from customer c join customer_session s on c.id = s.customer "
            "where c.id = $1 and s.id = $2",
            token_payload.customer_id,
            token_payload.session_id,
        )

    def decode_terminal_jwt_payload(self, token: str) -> Optional[TerminalTokenMetadata]:
        try:
            payload = jwt.decode(token, self.config.core.secret_key, algorithms=[self.config.core.jwt_token_algorithm])
            try:
                return TerminalTokenMetadata.model_validate(payload)
            except ValidationError:
                return None
        except JWTError:
            return None

    def create_terminal_access_token(self, token_metadata: TerminalTokenMetadata):
        to_encode = {"terminal_id": token_metadata.terminal_id, "session_uuid": str(token_metadata.session_uuid)}
        encoded_jwt = jwt.encode(to_encode, self.config.core.secret_key, algorithm=self.config.core.jwt_token_algorithm)
        return encoded_jwt

    @with_db_transaction(read_only=True)
    async def get_terminal_from_token(self, *, conn: Connection, token: str) -> Optional[CurrentTerminal]:
        token_payload: TerminalTokenMetadata | None = self.decode_terminal_jwt_payload(token)
        if token_payload is None:
            return None

        terminal = await conn.fetch_maybe_one(
            Terminal,
            "select t.*, till.id as till_id "
            "from terminal t "
            "left join till on t.id = till.terminal_id "
            "where t.id = $1 and session_uuid = $2",
            token_payload.terminal_id,
            token_payload.session_uuid,
        )
        if terminal is None:
            return None

        till = await conn.fetch_maybe_one(
            Till,
            "select * from till where terminal_id = $1",
            token_payload.terminal_id,
        )

        return CurrentTerminal(
            id=terminal.id,
            node_id=terminal.node_id,
            name=terminal.name,
            description=terminal.description,
            active_user_id=terminal.active_user_id,
            active_user_role_id=terminal.active_user_role_id,
            till=till,
        )
