from datetime import timedelta

import yaml
from typing import Optional

from pydantic import BaseModel


class HTTPServerConfig(BaseModel):
    host: str
    port: int


class AdministrationApiConfig(HTTPServerConfig):
    host: str = "localhost"
    port: int = 8081


class TerminalApiConfig(HTTPServerConfig):
    host: str = "localhost"
    port: int = 8080


class DatabaseConfig(BaseModel):
    user: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = 5432
    dbname: str


class CoreConfig(BaseModel):
    secret_key: str
    jwt_token_algorithm: str = "HS256"


class Config(BaseModel):
    # in case all params are optional this is needed to make the whole section optional
    administration: AdministrationApiConfig = AdministrationApiConfig()
    terminalserver: TerminalApiConfig = TerminalApiConfig()
    database: DatabaseConfig
    core: CoreConfig


def read_config(config_path: str) -> Config:
    with open(config_path, "r") as config_file:
        content = yaml.safe_load(config_file)
        config = Config(**content)
        return config
