#!/usr/bin/env python3
"""
Crowd Heatmap & Business Intelligence Platform - CLI Runner
Single entrypoint to start, configure, test, and manage both frontend and backend.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# Fix Windows console unicode encoding issues
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent

# ANSI Colors for terminal output
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
======================================================================
   CROWD HEATMAP & BUSINESS INTELLIGENCE PLATFORM (BI)
======================================================================{Colors.RESET}
  {Colors.DIM}* Django 6.0+ | Daphne ASGI | WebSockets | Scikit-Learn | Leaflet{Colors.RESET}
"""
    print(banner)


def find_venv_python() -> Path:
    """Detect virtual environment python executable or fall back to sys.executable."""
    venv_candidates = [
        BASE_DIR / ".venv" / "bin" / "python",
        BASE_DIR / "venv" / "bin" / "python",
        BASE_DIR / ".venv" / "bin" / "python3",
        BASE_DIR / "venv" / "bin" / "python3",
        BASE_DIR / ".venv" / "Scripts" / "python.exe",
        BASE_DIR / "venv" / "Scripts" / "python.exe",
        BASE_DIR / "env" / "bin" / "python",
        BASE_DIR / "env" / "Scripts" / "python.exe",
    ]
    for candidate in venv_candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return Path(sys.executable)


def is_port_in_use(host: str, port: int) -> bool:
    """Check if a given network port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def ensure_env_file():
    """Ensure .env exists with standard sensible development defaults."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        default_env = (
            "DEBUG=True\n"
            "SECRET_KEY=django-insecure-dev-key-change-in-production-1234567890\n"
            "GEMINI_API_KEY=\n"
            "GEMINI_MODEL_NAME=gemini-2.5-flash\n"
        )
        env_path.write_text(default_env)
        print(f"{Colors.GREEN}[INFO]{Colors.RESET} Created default .env file.")


def run_command_in_venv(args: list[str], env: dict | None = None) -> int:
    """Run a command using the detected virtualenv python."""
    py_exec = find_venv_python()
    cmd = [str(py_exec)] + args
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    # Ensure BASE_DIR is in PYTHONPATH
    existing_pp = merged_env.get("PYTHONPATH", "")
    merged_env["PYTHONPATH"] = f"{BASE_DIR}:{existing_pp}" if existing_pp else str(BASE_DIR)

    try:
        proc = subprocess.run(cmd, cwd=str(BASE_DIR), env=merged_env)
        return proc.returncode
    except KeyboardInterrupt:
        return 0


def cmd_setup(args):
    """Set up the project virtual environment, dependencies, and database."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Running complete project setup...{Colors.RESET}\n")

    ensure_env_file()

    venv_dir = BASE_DIR / ".venv"
    if not venv_dir.exists():
        print(f"{Colors.YELLOW}[1/4]{Colors.RESET} Creating virtual environment in .venv...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    else:
        print(f"{Colors.GREEN}[1/4]{Colors.RESET} Virtual environment found at .venv")

    py_exec = find_venv_python()
    print(f"{Colors.YELLOW}[2/4]{Colors.RESET} Installing dependencies from requirements.txt...")
    subprocess.run([str(py_exec), "-m", "pip", "install", "-r", "requirements.txt"], check=True)

    print(f"{Colors.YELLOW}[3/4]{Colors.RESET} Running database migrations...")
    run_command_in_venv(["manage.py", "migrate"])

    model_file = BASE_DIR / "crowd_heatmap_project" / "business_model.pkl"
    if not model_file.exists():
        print(f"{Colors.YELLOW}[4/4]{Colors.RESET} Training ML decision tree recommendation model...")
        run_command_in_venv(["crowd_heatmap_project/train_model.py"])
    else:
        print(f"{Colors.GREEN}[4/4]{Colors.RESET} ML recommendation model is ready.")

    print(f"\n{Colors.GREEN}{Colors.BOLD}Setup complete! Run `{Colors.CYAN}./run.sh{Colors.GREEN}` or `{Colors.CYAN}python3 run.py{Colors.GREEN}` to launch the application.{Colors.RESET}")


def cmd_migrate(args):
    """Run database migrations."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Applying database migrations...{Colors.RESET}")
    ensure_env_file()
    run_command_in_venv(["manage.py", "makemigrations"])
    code = run_command_in_venv(["manage.py", "migrate"])
    if code == 0:
        print(f"{Colors.GREEN}Database is up to date.{Colors.RESET}")


def cmd_test(args):
    """Run unit and integration tests."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Running test suite...{Colors.RESET}")
    ensure_env_file()
    test_args = ["manage.py", "test"]
    if args.app:
        test_args.append(args.app)
    if args.verbosity:
        test_args.extend(["-v", str(args.verbosity)])
    sys.exit(run_command_in_venv(test_args))


def cmd_train(args):
    """Train or retrain the Scikit-Learn recommendation model."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Training recommendation model...{Colors.RESET}")
    sys.exit(run_command_in_venv(["crowd_heatmap_project/train_model.py"]))


def cmd_superuser(args):
    """Create Django admin superuser."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Creating admin superuser...{Colors.RESET}")
    ensure_env_file()
    sys.exit(run_command_in_venv(["manage.py", "createsuperuser"]))


def cmd_check(args):
    """Run Django system check."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Running system check...{Colors.RESET}")
    ensure_env_file()
    sys.exit(run_command_in_venv(["manage.py", "check"]))


def cmd_clean(args):
    """Remove cache files and build artifacts."""
    print_banner()
    print(f"{Colors.BOLD}{Colors.BLUE}==> Cleaning build and cache artifacts...{Colors.RESET}")
    patterns = ["**/__pycache__", "**/*.pyc", "**/*.pyo", ".pytest_cache"]
    removed = 0
    for p in patterns:
        for path in BASE_DIR.glob(p):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
            elif path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
    print(f"{Colors.GREEN}Cleaned {removed} cache items.{Colors.RESET}")


def cmd_dev(args):
    """Start the full-stack development server (Frontend + Backend + WebSockets)."""
    print_banner()
    ensure_env_file()

    host = args.host
    port = args.port

    if is_port_in_use(host, port):
        print(f"{Colors.RED}{Colors.BOLD}[WARNING] Port {port} is already in use!{Colors.RESET}")
        print(f"{Colors.YELLOW}You can specify a different port with: {Colors.CYAN}python3 run.py --port 8080{Colors.RESET}")
        print(f"Or stop the process currently using port {port}.\n")

    # Run auto migrations if requested
    if args.migrate:
        print(f"{Colors.DIM}Checking database migrations...{Colors.RESET}")
        run_command_in_venv(["manage.py", "migrate"])

    url = f"http://{host}:{port}/"
    admin_url = f"http://{host}:{port}/admin/"
    dashboard_url = f"http://{host}:{port}/dashboard/"

    print(f"""{Colors.BOLD}Ready to serve Frontend & Backend:{Colors.RESET}
  {Colors.GREEN}->{Colors.RESET}  {Colors.BOLD}Frontend Home:{Colors.RESET}     {Colors.CYAN}{url}{Colors.RESET}
  {Colors.GREEN}->{Colors.RESET}  {Colors.BOLD}BI Dashboard:{Colors.RESET}      {Colors.CYAN}{dashboard_url}{Colors.RESET}
  {Colors.GREEN}->{Colors.RESET}  {Colors.BOLD}Admin Panel:{Colors.RESET}       {Colors.CYAN}{admin_url}{Colors.RESET}
  {Colors.GREEN}->{Colors.RESET}  {Colors.BOLD}WebSocket Engine:{Colors.RESET}  {Colors.DIM}ws://{host}:{port}/ws/chat/{Colors.RESET}
  {Colors.GREEN}->{Colors.RESET}  {Colors.BOLD}Server Core:{Colors.RESET}       {Colors.DIM}Daphne ASGI (HTTP + WS){Colors.RESET}

{Colors.DIM}Press CTRL+C to stop the server.{Colors.RESET}
----------------------------------------------------------------------
""")

    server_args = ["manage.py", "runserver", f"{host}:{port}"]
    run_command_in_venv(server_args)


def main():
    parser = argparse.ArgumentParser(
        description="Unified CLI runner for Crowd Heatmap & Business Intelligence Platform",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # dev / server command (default)
    dev_parser = subparsers.add_parser("dev", aliases=["server", "start", "run"], help="Start the full development server")
    dev_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    dev_parser.add_argument("-p", "--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    dev_parser.add_argument("--migrate", action="store_true", help="Run migrations before starting")

    # setup command
    subparsers.add_parser("setup", help="Set up virtual environment, dependencies, migrations, and ML model")

    # migrate command
    subparsers.add_parser("migrate", help="Apply database migrations")

    # test command
    test_parser = subparsers.add_parser("test", help="Run project test suite")
    test_parser.add_argument("app", nargs="?", default=None, help="Specific app/test to run (e.g. tracker, business_intelligence)")
    test_parser.add_argument("-v", "--verbosity", type=int, default=1, help="Verbosity level (0, 1, 2, 3)")

    # train command
    subparsers.add_parser("train", help="Train the Scikit-Learn recommendation model")

    # superuser command
    subparsers.add_parser("superuser", help="Create a Django admin superuser")

    # check command
    subparsers.add_parser("check", help="Run Django system checks")

    # clean command
    subparsers.add_parser("clean", help="Remove python cache files and build artifacts")

    # If no subcommand provided, default to dev
    if len(sys.argv) == 1:
        args = parser.parse_args(["dev"])
    else:
        # Check if first arg is an option for dev (e.g., --port 8080)
        first_arg = sys.argv[1]
        valid_cmds = ["dev", "server", "start", "run", "setup", "migrate", "test", "train", "superuser", "check", "clean", "-h", "--help"]
        if first_arg not in valid_cmds and not first_arg.startswith("-"):
            # Let argparse handle unknown command
            args = parser.parse_args()
        elif first_arg.startswith("-") and first_arg not in ["-h", "--help"]:
            args = parser.parse_args(["dev"] + sys.argv[1:])
        else:
            args = parser.parse_args()

    commands = {
        "dev": cmd_dev,
        "server": cmd_dev,
        "start": cmd_dev,
        "run": cmd_dev,
        "setup": cmd_setup,
        "migrate": cmd_migrate,
        "test": cmd_test,
        "train": cmd_train,
        "superuser": cmd_superuser,
        "check": cmd_check,
        "clean": cmd_clean,
    }

    cmd_func = commands.get(args.command, cmd_dev)
    cmd_func(args)


if __name__ == "__main__":
    main()
