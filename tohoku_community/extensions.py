"""Flask 拡張機能のインスタンスをまとめるモジュール。
circular import を避けるため、db や login_manager はここで生成し、
app.py 側で init_app() する。
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "続けるにはログインしてください。"
login_manager.login_message_category = "info"
