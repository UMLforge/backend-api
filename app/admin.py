"""Admin CLI: the ONLY way to create monitoring accounts. Run it on the server.

  python -m app.admin create-user NAME        prompts for a password (or --password-stdin)
  python -m app.admin reset-password NAME
  python -m app.admin delete-user NAME
  python -m app.admin list-users
  python -m app.admin logout-all              ends every admin session
  python -m app.admin stats                   storage + system snapshot as JSON
  python -m app.admin purge-expired           delete expired published links (e.g. a daily scheduled task)

Docker:          docker compose exec backend python -m app.admin create-user alice
PythonAnywhere:  cd ~/umlcreator/backend && workon umlforge && python -m app.admin create-user alice
(The CLI reads the same DATABASE_URL / DB_PATH as the app; on PythonAnywhere load deploy/pythonanywhere/.env first,
 see docs/DEPLOY_FREE.md.)
"""
import argparse
import getpass
import json
import sys
import time
from pathlib import Path

from .auth import AdminStore
from .config import settings
from .db import Database
from . import monitoring


def _password(args) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password (min 10 characters): ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords don't match.")
    return first


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description="UMLforge admin accounts (monitoring only).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("create-user", "reset-password"):
        p = sub.add_parser(name)
        p.add_argument("username")
        p.add_argument("--password-stdin", action="store_true", help="read the password from stdin (for scripts)")
    sub.add_parser("delete-user").add_argument("username")
    sub.add_parser("list-users")
    sub.add_parser("logout-all")
    sub.add_parser("stats")
    sub.add_parser("purge-expired")
    args = parser.parse_args(argv)

    db = Database(settings.db_url)
    store = AdminStore(db)
    try:
        if args.cmd == "create-user":
            store.create_user(args.username, _password(args))
            print(f"Created admin '{args.username}'. Sign in at <your site>/admin.html")
        elif args.cmd == "reset-password":
            if not store.set_password(args.username, _password(args)):
                sys.exit(f"No admin called '{args.username}'.")
            print(f"Password changed; '{args.username}' was signed out everywhere.")
        elif args.cmd == "delete-user":
            print("Deleted." if store.delete_user(args.username) else f"No admin called '{args.username}'.")
        elif args.cmd == "list-users":
            for u in store.list_users() or [{"username": "(none)", "created_at": None}]:
                created = time.strftime("%Y-%m-%d %H:%M", time.localtime(u["created_at"])) if u["created_at"] else ""
                print(f"{u['username']:24} {created}")
        elif args.cmd == "logout-all":
            print(f"Ended {store.logout_all()} session(s).")
        elif args.cmd == "purge-expired":
            _, removed = db.run("DELETE FROM shares WHERE expires_at < ?", (time.time(),))
            print(f"Removed {removed} expired link(s).")
        elif args.cmd == "stats":
            data_dir = str(Path(db.path).parent) if not db.postgres else "/"
            monitoring.system(data_dir)  # first CPU reading
            time.sleep(0.5)
            print(json.dumps({"storage": monitoring.storage(db, data_dir), "system": monitoring.system(data_dir)}, indent=2))
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
