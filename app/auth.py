import functools

from flask import (Blueprint, flash, g, redirect, render_template, request, session, url_for)
from app.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=('GET', 'POST'))
def login():
    # REMOTE_USER is an email address in Shibboleth
    email_address = request.environ["REMOTE_USER"]
    username = email_address[:email_address.find('@caltech.edu')]
    # check the email against authorized users
    session.clear()
    session['user_id'] = username
    db = get_db()
    userinfo = db.execute("SELECT username, role FROM user WHERE username = ?;", [email_address]).fetchone()
    if userinfo:
        session['auth'] = True
        session['role'] = userinfo[1]
    else:
        session['auth'] = False
    g.user = session.get('user_id')
    g.role = session.get('role')
    g.auth = session.get('auth')
    return redirect(url_for('oaidp.collections'))

@bp.before_app_request
def load_logged_in_user():
    g.user = session.get('user_id')
    g.role = session.get('role')
    g.auth = session.get('auth')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('oaidp.collections'))

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view

