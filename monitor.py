#!/usr/bin/env python3
"""
ZapretDeck Monitoring Module

Handles status checking and site connectivity testing.
"""
import subprocess
import requests
import logging
from typing import Optional, Tuple, Dict
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class StatusChecker(QThread):
    """Thread for monitoring session and service status."""
    
    session_changed = pyqtSignal(bool)
    service_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        self._running = True
    
    def stop(self) -> None:
        """Stop the monitoring thread."""
        self._running = False
    
    def run(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                # Check session (nfqws process)
                running = subprocess.run(
                    ["pgrep", "-f", "nfqws"],
                    capture_output=True
                ).returncode == 0
                self.session_changed.emit(running)
                
                # Check service
                enabled = subprocess.run(
                    ["systemctl", "is-enabled", "--quiet", "zapretdeck.service"],
                    check=False,
                    capture_output=True
                ).returncode == 0
                
                active = subprocess.run(
                    ["systemctl", "is-active", "--quiet", "zapretdeck.service"],
                    check=False,
                    capture_output=True
                ).returncode == 0
                
                self.service_changed.emit(enabled and active)
                
                self.msleep(1500)
            except Exception as e:
                logger.error(f"StatusChecker error: {e}")
                self.msleep(2000)


class SiteTester:
    """Tests connectivity to key sites (YouTube, Discord)."""
    
    TEST_SITES = {
        "YouTube": "https://www.youtube.com",
        "Discord": "https://discord.com",
    }
    
    def __init__(self, timeout: int = 5):
        """
        Initialize site tester.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
    
    def test_site(self, name: str, url: str) -> Tuple[bool, Optional[str]]:
        """
        Test connectivity to a single site.
        
        Args:
            name: Site name for logging
            url: Site URL to test
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code == 200:
                logger.info(f"✓ {name} ({url}): OK")
                return True, None
            else:
                error = f"HTTP {response.status_code}"
                logger.warning(f"✗ {name} ({url}): {error}")
                return False, error
        except requests.exceptions.Timeout:
            error = "Timeout"
            logger.warning(f"✗ {name} ({url}): {error}")
            return False, error
        except requests.exceptions.ConnectionError as e:
            error = f"Connection error: {str(e)}"
            logger.warning(f"✗ {name} ({url}): {error}")
            return False, error
        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            logger.error(f"✗ {name} ({url}): {error}")
            return False, error
    
    def test_all(self) -> Dict[str, Tuple[bool, Optional[str]]]:
        """
        Test all configured sites.
        
        Returns:
            Dictionary mapping site names to (success, error) tuples
        """
        results = {}
        logger.info("=== Testing site connectivity ===")
        
        for name, url in self.TEST_SITES.items():
            success, error = self.test_site(name, url)
            results[name] = (success, error)
        
        logger.info("=== Site connectivity test complete ===")
        return results
    
    def print_results(self, results: Optional[Dict[str, Tuple[bool, Optional[str]]]] = None) -> None:
        """
        Print test results to console.
        
        Args:
            results: Test results dictionary. If None, runs tests first.
        """
        if results is None:
            results = self.test_all()
        
        print("\n" + "=" * 50)
        print("Site Connectivity Test Results")
        print("=" * 50)
        
        all_ok = True
        for name, (success, error) in results.items():
            status = "✓ OK" if success else f"✗ FAILED ({error})"
            print(f"{name:15} {status}")
            if not success:
                all_ok = False
        
        print("=" * 50)
        if all_ok:
            print("All sites accessible")
        else:
            print("Some sites are not accessible")
        print()

