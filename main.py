#!/usr/bin/env python3
"""
ZapretDeck Main Entry Point

Handles CLI arguments, logging setup, and application initialization.
"""
import os
import sys
import argparse
import logging
import locale
import subprocess
import getpass
from typing import Optional

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QLocale

from ui import ZapretGUI
from monitor import SiteTester
from utils import BASE_DIR
import warp
import config
import sys_utils



CURRENT_VERSION = "0.2.1"


def setup_logging(debug: bool = False) -> None:
    """
    Setup logging configuration.
    
    Args:
        debug: If True, enable debug logging to console
    """
    level = logging.DEBUG if debug else logging.INFO
    format_str = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    
    # Remove existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(format_str))
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level)
    
    if debug:
        logging.info("Debug mode enabled - logging to console")


def setup_translator(app: QApplication) -> QTranslator:
    """
    Setup QTranslator based on system locale.

    Args:
        app: QApplication instance

    Returns:
        QTranslator instance
    """
    translator = QTranslator()

    # Get system locale
    try:
        system_locale = locale.getdefaultlocale()[0] or 'en'
    except:
        system_locale = locale.getlocale()[0] or 'en'
    
    lang_code = system_locale.split('_')[0].lower()

    # Default to Russian if not ru or en
    if lang_code not in ['ru', 'en']:
        lang_code = 'ru'

    i18n_dir = os.path.join(BASE_DIR, "i18n")
    qm_file = os.path.join(i18n_dir, f"zapretdeck_{lang_code}.qm")

    if os.path.exists(qm_file):
        try:
            if translator.load(qm_file):
                app.installTranslator(translator)
                logging.info(f"Loaded translation: {lang_code}")
            else:
                logging.warning(f"Failed to load translation file: {qm_file}")
        except Exception as e:
            logging.warning(f"Exception while loading translation {lang_code}: {e}")
    else:
        logging.info(f"Translation file not found: {qm_file}, using default (Russian)")

    return translator


def run_strategy_auto(password: str) -> int:
    """
    Run auto strategy logic with provided password.
    
    Args:
        password: Sudo password
        
    Returns:
        0 on success, 1 on failure
    """
    logger = logging.getLogger(__name__)
    try:
        # Run main script with auto mode
        result = subprocess.run(
            ["sudo", "-S", "bash", os.path.join(BASE_DIR, "main_script.sh"), "auto"],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            logger.info("Auto strategy activated successfully")
            return 0
        else:
            logger.error(f"Failed to activate auto strategy: {result.stderr}")
            return 1
    except Exception as e:
        logger.error(f"Error executing auto strategy: {e}")
        return 1


def cmd_strategy_auto(args) -> int:
    """Activate auto strategy."""
    logger = logging.getLogger(__name__)
    logger.info("Setting auto strategy...")
    
    try:
        # Get sudo password
        password = getpass.getpass("Enter sudo password: ")
        return run_strategy_auto(password)
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1



def cmd_start(args) -> int:
    """Start ZapretDeck with configured strategy."""
    logger = logging.getLogger(__name__)
    logger.info("Starting ZapretDeck...")
    
    try:
        # Get sudo password
        password = getpass.getpass("Enter sudo password: ")

        logger.info("Press Ctrl+C to stop.")
        
        # Run sudo -S bash main_script.sh
        proc = subprocess.Popen(
            ["sudo", "-S", "bash", os.path.join(BASE_DIR, "main_script.sh")],
            stdin=subprocess.PIPE,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True
        )
        
        try:
            # Write password and close stdin so sudo reads it
            if proc.stdin:
                proc.stdin.write(password + "\n")
                proc.stdin.flush()
                proc.stdin.close()
            
            # Wait for process
            proc.wait()
            return proc.returncode
            
        except KeyboardInterrupt:
            logger.info("\nStopping...")
            # Send SIGTERM to the sudo process
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return 0
            
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_stop(args) -> int:
    """Stop ZapretDeck and all related services."""
    logger = logging.getLogger(__name__)
    logger.info("Performing full stop of ZapretDeck...")

    try:
        # Get sudo password
        password = getpass.getpass("Enter sudo password: ")

        # 1. Deactivate WARP if installed
        if warp.is_installed():
            logger.info(">>> Step 1/4: Deactivating WARP")
            # disconnect_warp returns (success, msg)
            success, msg = warp.disconnect_warp()
            if not success:
                logger.warning(f"WARP deactivation message: {msg}")
        else:
            logger.info(">>> Step 1/4: WARP is not installed, skipping")

        # 2. Disable and stop background service
        logger.info(">>> Step 2/4: Disabling and stopping background service")
        svc_result = subprocess.run(
            ["sudo", "-S", "bash", os.path.join(BASE_DIR, "service.sh"), "remove"],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=30
        )
        if svc_result.returncode != 0:
            logger.warning(f"Note: Service removal returned non-zero (already removed?): {svc_result.stderr}")

        # 3. Final cleanup (nfqws and nftables)
        logger.info(">>> Step 3/4: Final cleanup of processes and rules")
        result = subprocess.run(
            ["sudo", "-S", "bash", os.path.join(BASE_DIR, "stop_and_clean_nft.sh")],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=30
        )

        # 4. Disable game filter
        logger.info(">>> Step 4/4: Disabling game filter")
        try:
            cfg = config.Config()
            cfg.set_game_filter(False)
        except Exception as e:
            logger.warning(f"Failed to update game filter config: {e}")

        if result.returncode == 0:
            logger.info("ZapretDeck stopped successfully")
            return 0
        else:
            logger.error(f"Failed to perform final cleanup: {result.stderr}")
            return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_status(args) -> int:
    """Check ZapretDeck status."""
    logger = logging.getLogger(__name__)

    try:
        # Load config
        cfg = config.Config()
        strategy = cfg.get_strategy()

        # Check if nfqws is running
        result = subprocess.run(
            ["pgrep", "-f", "nfqws"],
            capture_output=True,
            text=True
        )
        is_running = result.returncode == 0

        print("\n=== ZapretDeck Status ===")
        print(f"Strategy: {strategy}")
        print(f"Status: {'Running' if is_running else 'Stopped'}")
        print(f"Game Filter: {'Enabled' if cfg.get_game_filter() else 'Disabled'}")
        print()

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def run_service_enable(password: str) -> int:
    """
    Enable background service with provided password.
    
    Args:
        password: Sudo password
        
    Returns:
        0 on success, 1 on failure
    """
    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            ["sudo", "-S", "bash", os.path.join(BASE_DIR, "service.sh"), "install"],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info("Service enabled successfully")
            print(result.stdout)
            return 0
        else:
            logger.error(f"Failed to enable service: {result.stderr}")
            return 1
    except Exception as e:
        logger.error(f"Error enabling service: {e}")
        return 1


def cmd_service_enable(args) -> int:
    """Enable background service."""
    logger = logging.getLogger(__name__)
    logger.info("Enabling ZapretDeck service...")

    try:
        # Use service.sh to install/enable the service
        # We need sudo for this
        password = getpass.getpass("Enter sudo password: ")
        return run_service_enable(password)
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_service_disable(args) -> int:
    """Disable background service."""
    logger = logging.getLogger(__name__)
    logger.info("Disabling ZapretDeck service...")

    try:
        # Use service.sh to remove/disable the service
        password = getpass.getpass("Enter sudo password: ")
        
        result = subprocess.run(
            ["sudo", "-S", "bash", os.path.join(BASE_DIR, "service.sh"), "remove"],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info("Service disabled successfully")
            print(result.stdout)
            return 0
        else:
            logger.error(f"Failed to disable service: {result.stderr}")
            return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_service_status(args) -> int:
    """Check background service status."""
    logger = logging.getLogger(__name__)

    try:
        result = subprocess.run(
            ["systemctl", "is-active", "zapretdeck.service"],
            capture_output=True,
            text=True
        )

        status = result.stdout.strip()

        print("\n=== ZapretDeck Service Status ===")
        print(f"Service: {status}")
        print()

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_warp_on(args) -> int:
    """Activate WARP."""
    logger = logging.getLogger(__name__)
    logger.info("Activating WARP...")

    if not warp.is_installed():
        logger.error("WARP is not installed")
        return 1

    try:
        password = getpass.getpass("Enter sudo password: ")
        success, msg = warp.activate_warp(password)

        if success:
            logger.info(f"WARP activated: {msg}")
            return 0
        else:
            logger.error(f"Failed to activate WARP: {msg}")
            return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_warp_off(args) -> int:
    """Deactivate WARP."""
    logger = logging.getLogger(__name__)
    logger.info("Deactivating WARP...")

    if not warp.is_installed():
        logger.error("WARP is not installed")
        return 1

    try:
        success, msg = warp.disconnect_warp()

        if success:
            logger.info(f"WARP deactivated: {msg}")
            return 0
        else:
            logger.error(f"Failed to deactivate WARP: {msg}")
            return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_warp_status(args) -> int:
    """Check WARP status."""
    logger = logging.getLogger(__name__)

    if not warp.is_installed():
        print("\n=== WARP Status ===")
        print("WARP is not installed")
        print()
        return 1

    try:
        is_connected, status_output = warp.get_warp_status()

        print("\n=== WARP Status ===")
        print(f"Status: {'Connected' if is_connected else 'Disconnected'}")
        print(f"Details: {status_output}")
        print()

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def cmd_full_start(args) -> int:
    """
    Execute full start sequence:
    1. Auto strategy
    2. Start ZapretDeck (via service enable)
    3. Service enable (already done in step 2 if we consider start as enablement)
       Wait, 'zapretdeck start' runs main_script.sh directly, not service.
       'zapretdeck service enable' installs systemd unit.
       User requested:
       - strategy auto
       - start (Start ZapretDeck with configured strategy) - usually this means running it now? 
         But 'service enable' also starts it. 
         If we enable service, it starts automatically.
         Let's clarify: 'zapretdeck start' runs in foreground?
         The user said: "zapretdeck start Start ZapretDeck with configured strategy"
         And "zapretdeck service enable"
         If we enable service, we don't need 'start' if 'start' just runs it.
         However, let's follow the user's list:
         1. zapretdeck strategy auto
         2. zapretdeck start OR zapretdeck service enable?
         Actually, usually 'start' might just run it temporarily. 
         But if we do 'service enable', that persists it.
         Let's assumes 'full start' means "Configure everything and make it permanent and running".
         
         Sequence:
         1. Ask password.
         2. Run strategy auto.
         3. Enable service (this installs AND starts it).
         4. Activate WARP.
         
         We don't need separate 'zapretdeck start' if 'service enable' starts it.
         Let's stick to enabling service as it covers "ensure it's running".
    """
    logger = logging.getLogger(__name__)
    logger.info("Executing full start sequence...")
    
    try:
        password = getpass.getpass("Enter sudo password: ")
        
        # 1. Strategy Auto
        logger.info(">>> Step 1/3: Auto Strategy")
        if run_strategy_auto(password) != 0:
            logger.error("Failed to set auto strategy")
            return 1
            
        # 2. Service Enable (starts ZapretDeck as service)
        logger.info(">>> Step 2/3: Enable Service")
        if run_service_enable(password) != 0:
            logger.error("Failed to enable service")
            return 1
            
        # 3. WARP On
        logger.info(">>> Step 3/3: Activate WARP")
        if warp.is_installed():
            success, msg = warp.activate_warp(password)
            if not success:
                logger.error(f"Failed to activate WARP: {msg}")
                return 1
        else:
            logger.warning("WARP is not installed, skipping Step 3")
            
        logger.info("Full start completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Error during full start: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    # Ensure strict venv checks if we are NOT just printing help
    if "--help" not in sys.argv and "-h" not in sys.argv:
        sys_utils.ensure_venv(BASE_DIR)

    parser = argparse.ArgumentParser(
        description="ZapretDeck - Network bypass tool for Steam Deck and Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  zapretdeck                    Launch GUI
  zapretdeck strategy auto      Activate auto strategy
  zapretdeck stop               Stop ZapretDeck
  zapretdeck status             Check status
  zapretdeck service enable     Enable background service
  zapretdeck service disable    Disable background service
  zapretdeck warp on            Activate WARP
  zapretdeck warp off           Deactivate WARP
  zapretdeck warp status        Check WARP status
  zapretdeck full start         Configure auto strategy, enable service, and activate WARP
        """
    )

    # Global options
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ZapretDeck {CURRENT_VERSION}"
    )
    parser.add_argument(
        "--test-sites",
        action="store_true",
        help="Test connectivity to key sites and exit"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # strategy command
    strategy_parser = subparsers.add_parser('strategy', help='Manage strategies')
    strategy_subparsers = strategy_parser.add_subparsers(dest='strategy_action')

    auto_parser = strategy_subparsers.add_parser('auto', help='Activate auto strategy')
    auto_parser.set_defaults(func=cmd_strategy_auto)

    # start command
    start_parser = subparsers.add_parser('start', help='Start ZapretDeck with configured strategy')
    start_parser.set_defaults(func=cmd_start)

    # stop command
    stop_parser = subparsers.add_parser('stop', help='Stop ZapretDeck')
    stop_parser.set_defaults(func=cmd_stop)

    # status command
    status_parser = subparsers.add_parser('status', help='Check ZapretDeck status')
    status_parser.set_defaults(func=cmd_status)

    # service command
    service_parser = subparsers.add_parser('service', help='Manage background service')
    service_subparsers = service_parser.add_subparsers(dest='service_action')

    service_enable_parser = service_subparsers.add_parser('enable', help='Enable background service')
    service_enable_parser.set_defaults(func=cmd_service_enable)

    service_disable_parser = service_subparsers.add_parser('disable', help='Disable background service')
    service_disable_parser.set_defaults(func=cmd_service_disable)

    service_status_parser = service_subparsers.add_parser('status', help='Check service status')
    service_status_parser.set_defaults(func=cmd_service_status)

    # warp command
    warp_parser = subparsers.add_parser('warp', help='Manage WARP')
    warp_subparsers = warp_parser.add_subparsers(dest='warp_action')

    warp_on_parser = warp_subparsers.add_parser('on', help='Activate WARP')
    warp_on_parser.set_defaults(func=cmd_warp_on)

    warp_off_parser = warp_subparsers.add_parser('off', help='Deactivate WARP')
    warp_off_parser.set_defaults(func=cmd_warp_off)

    warp_status_parser = warp_subparsers.add_parser('status', help='Check WARP status')
    warp_status_parser.set_defaults(func=cmd_warp_status)

    # full command
    full_parser = subparsers.add_parser('full', help='Combined commands')
    full_subparsers = full_parser.add_subparsers(dest='full_action')

    full_start_parser = full_subparsers.add_parser('start', help='Configure auto strategy, enable service, and activate WARP')
    full_start_parser.set_defaults(func=cmd_full_start)

    args = parser.parse_args()

    # Setup logging
    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    # Test sites mode
    if args.test_sites:
        logger.info("Running site connectivity test...")
        tester = SiteTester()
        results = tester.test_all()
        tester.print_results(results)
        
        all_ok = all(success for success, _ in results.values())
        return 0 if all_ok else 1
    
    # Execute command if specified
    if hasattr(args, 'func'):
        return args.func(args)

    # GUI mode (no command specified)
    os.environ.setdefault("QT_PLUGIN_PATH", "/usr/lib/qt6/plugins")
    # Auto-detect platform theme
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    hyprland = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    gtk_desktops = ["GNOME", "XFCE", "COSMIC", "PANTHEON", "MATE", "LXDE", "BUDGIE", "UBUNTU:GNOME", "CINNAMON", "UNITY"]
    
    if hyprland:
        # Check for specific theme managers in Hyprland
        if subprocess.run(["which", "nwg-look"], capture_output=True).returncode == 0:
            os.environ.setdefault("QT_QPA_PLATFORMTHEME", "gtk3")
        elif subprocess.run(["which", "kvantummanager"], capture_output=True).returncode == 0:
            os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kvantum")
        elif subprocess.run(["which", "qt6ct"], capture_output=True).returncode == 0:
            os.environ.setdefault("QT_QPA_PLATFORMTHEME", "qt6ct")
        else:
            os.environ.setdefault("QT_QPA_PLATFORMTHEME", "qt6ct") # Default fallback for Hyprland
    elif any(de in desktop for de in gtk_desktops):
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "gtk3")
    else:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "qt6ct")
    
    app = QApplication(sys.argv)
    app.setApplicationName("zapretdeck")
    app.setDesktopFileName("zapretdeck")
    
    logger.info(f"Starting ZapretDeck v{CURRENT_VERSION}")
    logger.info(f"Base directory: {BASE_DIR}")
    
    # Setup translations
    translator = setup_translator(app)


    
    # Create and show window
    window = ZapretGUI(translator=translator)
    window.showMaximized()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())