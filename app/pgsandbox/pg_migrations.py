"""Strict SQL migration parser and guarded PostgreSQL sandbox installer.

Only the repository-bundled migration 004 is accepted. It is never executed
against a remote database and no arbitrary SQL is accepted from an API caller.
The migration can be rehearsed twice to prove repeatability in disposable CI.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from sqlalchemy.engine import Engine
from .errors import InvalidValue, UnauthorizedEnvironment, InvariantError

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "004_pg_sandbox_cycle002.sql"


@dataclass(frozen=True)
class MigrationProof:
    version: str
    statement_count: int
    sha256: str
    dialect: str
    applied_on_sandbox: bool
    financial_production: bool = False


def split_sql(source: str) -> tuple[str, ...]:
    """Split trusted local PostgreSQL migration at unquoted statement boundaries.

    Supports SQL single/double quotes, doubled quote escapes, line and block
    comments, and PostgreSQL dollar-quoted function bodies. Rejects unfinished
    quotes and dollar blocks; never use this as a generic untrusted SQL parser.
    """
    if not isinstance(source, str) or not source or len(source) > 1_000_000:
        raise InvalidValue("Migration SQL has invalid size")
    output: list[str] = []
    current: list[str] = []
    quote: str | None = None
    dollar: str | None = None
    line_comment = False
    block_depth = 0
    i = 0
    while i < len(source):
        ch=source[i]
        next_char=source[i+1] if i+1 < len(source) else ""
        if line_comment:
            current.append(ch)
            if ch=="\n":
                line_comment=False
            i+=1
            continue
        if block_depth:
            current.append(ch)
            if ch=="/" and next_char=="*":
                current.append(next_char)
                block_depth+=1
                i+=2
                continue
            if ch=="*" and next_char=="/":
                current.append(next_char)
                block_depth-=1
                i+=2
                continue
            i+=1
            continue
        if dollar is not None:
            if source.startswith(dollar,i):
                current.append(dollar)
                i+=len(dollar)
                dollar=None
                continue
            current.append(ch)
            i+=1
            continue
        if quote is not None:
            current.append(ch)
            if ch==quote:
                if next_char==quote:
                    current.append(next_char)
                    i+=2
                    continue
                quote=None
            i+=1
            continue
        if ch=="-" and next_char=="-":
            current.append("--")
            line_comment=True
            i+=2
            continue
        if ch=="/" and next_char=="*":
            current.append("/*")
            block_depth+=1
            i+=2
            continue
        if ch in ("'",'"'):
            quote=ch
            current.append(ch)
            i+=1
            continue
        if ch=="$":
            end=source.find("$",i+1)
            if end!=-1:
                tag=source[i:end+1]
                interior=tag[1:-1]
                if interior=="" or (interior[0].isalpha() and interior.replace("_","").isalnum()):
                    dollar=tag
                    current.append(tag)
                    i=end+1
                    continue
        if ch==";":
            candidate="".join(current).strip()
            if candidate:
                output.append(candidate)
            current=[]
            i+=1
            continue
        current.append(ch)
        i+=1
    if quote is not None or dollar is not None or block_depth:
        raise InvalidValue("Unterminated migration literal/comment")
    candidate="".join(current).strip()
    if candidate:
        output.append(candidate)
    if not output or len(output)>500:
        raise InvalidValue("Invalid number of schema statements")
    return tuple(output)


def migration_content() -> str:
    if not MIGRATION_PATH.is_file() or MIGRATION_PATH.stat().st_size > 1_000_000:
        raise UnauthorizedEnvironment("Bundled sandbox SQL migration is missing")
    source=MIGRATION_PATH.read_text(encoding="utf-8")
    if "Slickk Pay Cycle 002" not in source:
        raise UnauthorizedEnvironment("Unexpected sandbox migration signature")
    return source


def sandbox_migration_proof() -> MigrationProof:
    source=migration_content()
    return MigrationProof("004_sandbox_pg_v2",len(split_sql(source)),
                          sha256(source.encode()).hexdigest(),"postgresql",False)


def install_pg_sandbox(engine: Engine) -> MigrationProof:
    if engine.dialect.name != "postgresql":
        raise UnauthorizedEnvironment("Migration 004 is PostgreSQL-only")
    if engine.url.host not in ("localhost","127.0.0.1","::1") or engine.url.database!="slickk_ci_test":
        raise UnauthorizedEnvironment("Migration target is not the disposable database")
    source=migration_content()
    statements=split_sql(source)
    # Every statement executes inside a single SQLAlchemy transaction. SQL
    # file BEGIN/COMMIT wrappers are skipped; only the scoped app controls tx.
    with engine.begin() as db:
        selected=db.exec_driver_sql("SELECT current_database()").scalar_one()
        if selected!="slickk_ci_test":
            raise UnauthorizedEnvironment("Server identity does not match guarded target")
        for statement in statements:
            stripped=statement.strip().upper()
            if stripped in ("BEGIN","COMMIT"):
                continue
            db.exec_driver_sql(statement)
    return MigrationProof("004_sandbox_pg_v2",len(statements),
                          sha256(source.encode()).hexdigest(),"postgresql",True)
