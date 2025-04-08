import subprocess
import sys
import os


def main():
    """Entry point for the dqm-dashboard command."""
    try:
        # Find app.py relative to this cli.py file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        app_file_path = os.path.join(current_dir, "app.py")

        if not os.path.exists(app_file_path):
            print(
                f"Error: Could not find app.py next to cli.py at {app_file_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Construct the command to run streamlit
        command = [sys.executable, "-m", "streamlit", "run", app_file_path]
        try:
            subprocess.run(command, check=True)
        except KeyboardInterrupt:
            sys.exit(0)

    except subprocess.CalledProcessError as e:
        print(
            f"Error: Streamlit process exited with status {e.returncode}.",
            file=sys.stderr,
        )
        sys.exit(e.returncode)
    except Exception as e:
        print(
            f"An unexpected error occurred while trying to run the Streamlit app: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
