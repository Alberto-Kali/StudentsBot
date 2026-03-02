from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, UUID
from clickhouse_sqlalchemy import engines, types
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid

Base = declarative_base()


def gen_uuid_str() -> str:
    return str(uuid.uuid4())


class UserRatings(Base):
    __tablename__ = 'user_ratings'

    id = Column(types.UUID, primary_key=True, default=gen_uuid_str)
    rater_telegram_id = Column(types.UInt64, nullable=False)   # кто оценивает
    target_telegram_id = Column(types.UInt64, nullable=False)  # кого оценивают
    value = Column(types.Int64, nullable=False)  # 1 = лайк, -1 = дизлайк
    created_at = Column(types.DateTime, default=datetime.utcnow)
    updated_at = Column(types.DateTime, default=datetime.utcnow)

    __table_args__ = (
        engines.MergeTree(order_by=['id']),
    )

    def __repr__(self):
        return f"<UserRatings(rater={self.rater_telegram_id}, target={self.target_telegram_id}, value={self.value})>"



class Photos(Base):
    __tablename__ = 'photos'
    
    id = Column(types.UUID, primary_key=True, default=gen_uuid_str)
    user_id = Column(types.UUID, ForeignKey('users.id'), nullable=False)
    raw_png = Column(types.String, nullable=False)
    description = Column(types.String, nullable=True)
    created_at = Column(types.DateTime, default=datetime.utcnow)

    __table_args__ = (
        engines.MergeTree(order_by=['id']),
    )

    def __repr__(self):
        return f"<Photos(user_id='{self.user_id}', url='{self.url}')>"
    
class Tags(Base):
    __tablename__ = 'tags'
    
    id = Column(types.UUID, primary_key=True, default=gen_uuid_str)
    name = Column(types.String, nullable=False)
    description = Column(types.String, nullable=True)
    author_user_id = Column(types.UUID, ForeignKey('users.id'), primary_key=True, nullable=False)
    created_at = Column(types.DateTime, default=datetime.utcnow)
    updated_at = Column(types.DateTime, default=datetime.utcnow)

    __table_args__ = (
        engines.MergeTree(order_by=['id']),
    )

    def __repr__(self):
        return f"<Tags(name='{self.name}', description='{self.description}')>"

class UsersTags(Base):
    __tablename__ = 'users_tags'
    
    id = Column(types.UUID, primary_key=True, default=gen_uuid_str)
    user_id = Column(types.UUID, ForeignKey('users.id'), primary_key=True, nullable=False)
    tag_id = Column(types.UUID, ForeignKey('tags.id'), primary_key=True, nullable=False)
    created_at = Column(types.DateTime, default=datetime.utcnow)

    __table_args__ = (
        engines.MergeTree(order_by=['id']),
    )

    def __repr__(self):
        return f"<UsersTags(user_id='{self.user_id}', tag_id='{self.tag_id}')>"



class UserReviewedUser(Base):
    __tablename__ = 'user_reviewed_user'
    
    id = Column(types.UUID, primary_key=True, default=gen_uuid_str)
    user_id = Column(types.UUID, ForeignKey('users.id'), primary_key=True, nullable=False)
    reviewed = Column(types.UUID, ForeignKey('users.id'), primary_key=True, nullable=False)
    created_at = Column(types.DateTime, default=datetime.utcnow)

    __table_args__ = (
        engines.MergeTree(order_by=['id']),
    )

    def __repr__(self):
        return f"<UserReviewedUser(user_id='{self.user_id}', reviewed='{self.reviewed}')>"



class Users(Base):
    __tablename__ = 'users'
    
    id = Column(types.UUID, primary_key=True, default=gen_uuid_str)
    name = Column(types.String, nullable=False)
    telegram_id = Column(types.UInt64, nullable=False)
    telegram_uname = Column(types.String, nullable=True)
    biography = Column(types.String, nullable=True)
    balance = Column(types.UInt64, default=10)
    liked = Column(types.UInt64, default=0)
    disliked = Column(types.UInt64, default=0)
    skips = Column(types.UInt64, default=0)
    published = Column(types.UInt64, default=0)
    visited = Column(types.UInt64, default=0)
    banned = Column(types.UInt64, default=0)
    username_hidden = Column(types.UInt64, default=1)
    created_at = Column(types.DateTime, default=datetime.utcnow)

    __table_args__ = (
        engines.MergeTree(order_by=['id']),
    )

    def __repr__(self):
        return f"<Users(name='{self.name}', telegram_id='{self.telegram_id}')>"

def init_db(db_uri=None):
    """
    Initialize ClickHouse database connection with fallback hosts
    
    Args:
        db_uri: Custom connection URI. If None, uses configured hosts with fallback
    """
    if db_uri is None:
        # Try primary host first
        db_uri = 'clickhouse://default:TupayaFrigitnaya12312@192.168.2.237:18123/uebki39bot'
    
    try:
        engine = create_engine(db_uri)
        # Test connection
        with engine.connect() as conn:
            print("Successfully connected to primary ClickHouse host")
    except Exception as e:
        # Fallback to localhost
        print(f"Primary host connection failed: {e}")
        print("Falling back to localhost...")
        db_uri = 'clickhouse://default:TupayaFrigitnaya12312@127.0.0.1:18123/uebki39bot'
        try:
            engine = create_engine(db_uri)
            with engine.connect() as conn:
                print("Successfully connected to fallback ClickHouse host")
        except Exception as fallback_error:
            print(f"Fallback host also failed: {fallback_error}")
            raise fallback_error
    
    # Create tables
    Base.metadata.create_all(engine)
    print("Database tables created successfully")
    return engine

# Utility function to create session
def create_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()