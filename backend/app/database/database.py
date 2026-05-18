"""
Database connection and session management
"""

from contextvars import ContextVar
from sqlalchemy import event, create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base, with_loader_criteria, Mapper
from config import settings
import logging

logger = logging.getLogger(__name__)

# Multi-tenancy context
current_tenant_id = ContextVar("current_tenant_id", default=None)

# Create Base here
Base = declarative_base()

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

@event.listens_for(Session, "do_orm_execute")
def _add_tenant_criteria(execute_state):
    tenant_id = current_tenant_id.get()
    if not tenant_id:
        return
        
    if execute_state.is_select and not execute_state.is_column_load and not execute_state.is_relationship_load:
        from sqlalchemy import bindparam
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                Base,
                lambda cls: cls.user_id == bindparam("current_tenant_id", callable_=lambda: current_tenant_id.get()) if hasattr(cls, "user_id") and cls.__name__ != "User" else True,
                include_aliases=True
            )
        )

@event.listens_for(Mapper, 'before_insert')
def _set_tenant_id_before_insert(mapper, connection, target):
    tenant_id = current_tenant_id.get()
    if tenant_id and hasattr(target, 'user_id') and type(target).__name__ != 'User':
        target.user_id = tenant_id


def init_db():
    """Initialize database tables"""
    try:
        # Import models INSIDE function to avoid circular import
        from app.database import models

        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")

    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()