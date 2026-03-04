import sys
import os
import logging
import subprocess

def is_venv():
    """Check if running inside a virtual environment."""
    return (hasattr(sys, 'real_prefix') or
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))

def get_venv_python_path(base_dir):
    """Get the path to the python executable in the venv."""
    return os.path.join(base_dir, "venv", "bin", "python3")

def ensure_venv(base_dir):
    """
    Ensure the script is running inside the virtual environment.
    If not, restart the script using the venv's python.
    """
    if is_venv():
        return

    venv_python = get_venv_python_path(base_dir)
    
    if not os.path.exists(venv_python):
        logging.warning(f"Virtual environment not found at {venv_python}. Continuing with system python, but this may fail.")
        return

    logging.info(f"Restarting script in virtual environment: {venv_python}")
    
    # Re-execute the script with the venv python
    try:
        os.execv(venv_python, [venv_python] + sys.argv)
    except Exception as e:
        logging.error(f"Failed to restart in venv: {e}")
        sys.exit(1)
