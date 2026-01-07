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
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTranslator, QLocale

from ui import ZapretGUI
from monitor import SiteTester
from utils import BASE_DIR

CURRENT_VERSION = "0.1.6"


def setup_logging(debug: bool = False) -> None:
    """
    Setup logging configuration.
    
    Args:
        debug: If True, enable debug logging to console
    """
    level = logging.DEBUG if debug else logging.INFO
    format_str = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    
    # Remove file handler if exists
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
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
    system_locale = locale.getdefaultlocale()[0] or 'en'
    lang_code = system_locale.split('_')[0].lower()
    
    # Default to Russian, fallback to English
    if lang_code not in ['ru', 'en']:
        lang_code = 'ru'  # Default to Russian
    
    # Try to load translation file
    i18n_dir = os.path.join(BASE_DIR, "i18n")
    ts_file = os.path.join(i18n_dir, f"zapretdeck_{lang_code}.qm")
    
    if os.path.exists(ts_file):
        if translator.load(ts_file):
            app.installTranslator(translator)
            logging.info(f"Loaded translation: {lang_code}")
        else:
            logging.warning(f"Failed to load translation: {lang_code}")
    else:
        logging.info(f"Translation file not found: {ts_file}, using default (Russian)")
    
    return translator


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ZapretDeck - Network bypass tool for Steam Deck and Linux"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to console"
    )
    parser.add_argument(
        "--test-sites",
        action="store_true",
        help="Test connectivity to key sites (YouTube, Discord) and exit"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ZapretDeck {CURRENT_VERSION}"
    )
    
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
        
        # Exit with error code if any site failed
        all_ok = all(success for success, _ in results.values())
        return 0 if all_ok else 1
    
    # GUI mode
    os.environ.setdefault("QT_PLUGIN_PATH", "/usr/lib/qt6/plugins")
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "qt6ct")
    
    app = QApplication(sys.argv)
    app.setApplicationName("zapretdeck")
    app.setDesktopFileName("zapretdeck.desktop")
    
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

