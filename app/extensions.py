from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()


@login_manager.user_loader  # type: ignore[untyped-decorator]
def load_user_placeholder(user_id: str) -> None:
    # TODO: Replace this safe placeholder when the real User model is approved.
    del user_id
    return None
