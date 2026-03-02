# app/commands.py
import click
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, Role, AccountStatus

@click.command("create-first-admin")
@click.option("--name", prompt=True)
@click.option("--username", prompt=True)
@click.option("--email", prompt=True)
@click.option("--phone", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_first_admin(name, username, email, phone, password):
    # if an admin already exists, stop
    exists = User.query.filter_by(role=Role.ADMIN.value).first()
    if exists:
        click.echo("Admin already exists. Aborting.")
        return

    u = User(
        name=name.strip(),
        role=Role.ADMIN.value,
        username=username.strip(),
        email=email.strip(),
        phone=phone.strip(),
        status=AccountStatus.ACTIVE.value,
        address=""
    )
    u.set_password(password)

    try:
        db.session.add(u)
        db.session.commit()
        click.echo(f"✅ First admin created (id={u.id}, username={u.username})")
    except IntegrityError:
        db.session.rollback()
        click.echo("❌ username/email/phone already exists.")