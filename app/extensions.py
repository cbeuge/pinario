from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Basis(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Basis)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Bitte zuerst anmelden."
# Bewusst "basic" statt "strong": strong wirft die Sitzung weg, sobald sich
# IP oder Browserkennung ändern, und das passiert auf dem Handy bei jedem
# Wechsel zwischen WLAN und Mobilfunk. Abgesichert wird stattdessen über
# User.session_token, den ein Passwortwechsel neu würfelt.
login_manager.session_protection = "basic"
