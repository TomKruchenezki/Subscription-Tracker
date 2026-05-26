"""
Entry point: python main.py [--mock] [--debug] [--delete-all]

--mock     Force mock mode regardless of USE_MOCK env var (default: true)
--debug    Enable uvicorn auto-reload and DEBUG logging
--delete-all  Wipe the database, token, and all cached state, then exit
"""
import argparse
import logging
import os
import sys
from pathlib import Path


def _parse_args():
    parser = argparse.ArgumentParser(description="Subscription Tracker API server")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and auto-reload")
    parser.add_argument("--delete-all", action="store_true", dest="delete_all",
                        help="Delete all local data and exit")
    return parser.parse_args()


def _delete_all():
    db_path = Path(os.getenv("DB_PATH", "data/subscriptions.db"))
    deleted = []

    if db_path.exists():
        db_path.unlink()
        deleted.append(str(db_path))

    # Remove token files if they exist
    for token_path in [Path("token.json"), Path("data/token.json"), Path(".token"),
                        Path("backend/auth/token.json")]:
        if token_path.exists():
            token_path.unlink()
            deleted.append(str(token_path))

    if deleted:
        print("Deleted:", ", ".join(deleted))
    else:
        print("Nothing to delete — already clean.")

    print("App reset to freshly installed state.")


def main():
    from dotenv import load_dotenv
    load_dotenv()

    args = _parse_args()

    if args.delete_all:
        _delete_all()
        sys.exit(0)

    if args.mock:
        os.environ["USE_MOCK"] = "true"

    log_level = "DEBUG" if args.debug else os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

    # Ensure the database is initialized before starting the server
    db_path = os.getenv("DB_PATH", "data/subscriptions.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    from backend.db.setup import init_db
    init_db(db_path)

    import uvicorn
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run(
        "backend.api.app:app",
        host=host,
        port=port,
        reload=args.debug,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
