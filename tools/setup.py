import os, subprocess, sys, shutil

# --- Configuration ---
DEVKIT_URL = "https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit.git"
REMOTE_NAME = "toolkit"
REMOTE_BRANCH = "toolkit-release"

# --- Path Setup ---
SCRIPT_FILE = os.path.abspath(__file__)
SCRIPT_NAME = os.path.basename(SCRIPT_FILE)
ROOT_DIR = os.getcwd()

# --- Functions ---
def run_git(args, cwd=ROOT_DIR, check=True):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=check
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not check:
            return None
        print(f"Git Error: {' '.join(args)}")
        if e.stdout:
            print(e.stdout.strip())
        if e.stderr:
            print(e.stderr.strip())
        sys.exit(1)

def run_pip(args, cwd=ROOT_DIR, check=True):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip"] + args,
            cwd=cwd
        )
        if check and result.returncode != 0:
            print("Error: pip command failed.")
            sys.exit(1)
        return result.returncode
    except Exception as e:
        if not check:
            return None
        print(f"Pip Error: {e}")
        sys.exit(1)

def has_merge_head():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def _env_key_from_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    return key or None

def merge_env_template(template_path, env_path):
    if not os.path.exists(template_path):
        print("Warning: .env-template not found. Skipping .env setup.")
        return

    if not os.path.exists(env_path):
        shutil.copyfile(template_path, env_path)
        print("Created .env from .env-template.")
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        env_lines = env_file.read().splitlines()
    existing_keys = {
        key for key in (_env_key_from_line(line) for line in env_lines) if key
    }

    with open(template_path, "r", encoding="utf-8") as template_file:
        template_lines = template_file.read().splitlines()

    lines_to_add = []
    for line in template_lines:
        key = _env_key_from_line(line)
        if key and key not in existing_keys:
            lines_to_add.append(line)

    if not lines_to_add:
        print(".env already has all entries from .env-template. No changes needed.")
        return

    with open(env_path, "a", encoding="utf-8") as env_file:
        if env_lines and env_lines[-1] != "":
            env_file.write("\n")
        env_file.write("\n".join(lines_to_add))
        env_file.write("\n")
    print(f"Updated .env with {len(lines_to_add)} entr{'y' if len(lines_to_add) == 1 else 'ies'} from .env-template.")

# --- Script ---

# 1. Validation Checks
if not os.path.exists(os.path.join(ROOT_DIR, ".git")):
    print("Error: This directory is not a git repository.")
    print("Please initialize your repository (git init) first.")
    sys.exit(1)

# Check for uncommitted changes (Ignoring this script itself)
status_output = run_git(["status", "--porcelain"])
if status_output:
    # Filter out the running script from the status list
    lines = status_output.splitlines()
    real_changes = [line for line in lines if not line.strip().endswith(SCRIPT_NAME)]

    if real_changes:
        print("Error: You have uncommitted changes in your repository.")
        print("Please Commit or Stash your changes before running this script.")
        print("This ensures your work isn't accidentally overwritten or mixed into the template.")
        print("\nUncommitted files:")
        for line in real_changes:
            print(line)
        sys.exit(1)

current_remotes = run_git(["remote"])
if not current_remotes or "origin" not in current_remotes:
    print("Error: No 'origin' remote found.")
    print("Please link your repository to GitHub (or another remote) before running this script.")
    sys.exit(1)

# 2. Setup Remote
if REMOTE_NAME not in current_remotes:
    run_git(["remote", "add", "-t", REMOTE_BRANCH, REMOTE_NAME, DEVKIT_URL])
else:
    run_git(["remote", "set-branches", REMOTE_NAME, REMOTE_BRANCH])

run_git(["remote", "set-url", "--push", REMOTE_NAME, "no_push"])
run_git(["fetch", REMOTE_NAME])

# 3. Link the repo's history (safe merge).
print(f"\nLinking toolkit history...")

run_git([
    "merge",
    "--no-commit",
    "--allow-unrelated-histories",
    "-s", "recursive",
    "-X", "ours",
    f"{REMOTE_NAME}/{REMOTE_BRANCH}"
])

if has_merge_head():
    # --- CLEANUP STEP 1: Remove temporary files from the merge commit ---
    # 1. Remove the setup script so it isn't committed
    run_git(["rm", "-f", "--ignore-unmatch", "tools/setup.py"], check=False)
    # 2. Remove the dummy file so it isn't committed
    run_git(["rm", "-f", "--ignore-unmatch", "in_game/common/dummy.txt"], check=False)

    # Finalize the commit.
    run_git(["commit", "-m", "Link toolkit history"])
else:
    print("Toolkit history already linked. Skipping history merge commit.")

# Collect final status messages to print at the end so pip output doesn't trail them.
final_messages = []

# 4. Apply toolkit files (staged but not committed for review).
print("Applying toolkit files...")

# Forcefully checkout the release files from the remote.
run_git(["checkout", f"{REMOTE_NAME}/{REMOTE_BRANCH}", "--", "."])

# --- CLEANUP STEP 2: Remove temporary files from the overwrite stage ---
# Remove them again because 'checkout' brought them back from the remote
run_git(["rm", "-f", "--ignore-unmatch", "tools/setup.py"], check=False)
run_git(["rm", "-f", "--ignore-unmatch", "in_game/common/dummy.txt"], check=False)

final_messages.append("--- Toolkit Linked Successfully ---")
final_messages.append("Changes are STAGED but NOT committed. Review them before committing.")

# 5. Merge .env-template into .env
merge_env_template(
    os.path.join(ROOT_DIR, ".env-template"),
    os.path.join(ROOT_DIR, ".env")
)

# 6. Install Python dependencies
requirements_path = os.path.join(ROOT_DIR, "tools", "dependencies", "requirements.txt")
legacy_requirements_path = os.path.join(ROOT_DIR, "tools", "requirements.txt")
if os.path.exists(requirements_path):
    print("\nInstalling Python dependencies...")
    run_pip(["install", "-r", requirements_path])
elif os.path.exists(legacy_requirements_path):
    print("\nInstalling Python dependencies...")
    run_pip(["install", "-r", legacy_requirements_path])
else:
    print("Warning: requirements.txt not found. Skipping dependency install.")

# 7. Final status message (printed last).
if final_messages:
    print("\n" + "\n".join(final_messages))

# 8. Self-Destruct
try:
    os.remove(SCRIPT_FILE)
except Exception:
    pass
