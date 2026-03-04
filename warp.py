#!/usr/bin/env python3
"""
ZapretDeck WARP Module

Handles Cloudflare WARP client operations.
"""
import subprocess
import logging
import time
import atexit
import signal
from typing import Tuple

logger = logging.getLogger(__name__)

# Global flag to track if WARP was activated by this process
_warp_activated_by_us = False
_cleanup_registered = False


def is_warp_installed() -> bool:
    """
    Check if Cloudflare WARP is installed on the system.
    
    Returns:
        True if WARP is installed, False otherwise
    """
    try:
        # Проверка через pacman (Arch/Steam Deck)
        result = subprocess.run(
            ["pacman", "-Qs", "cloudflare-warp"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except Exception:
        pass
    
    # Альтернативная проверка — наличие warp-cli
    try:
        result = subprocess.run(
            ["which", "warp-cli"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except Exception:
        pass
    
    return False


def is_installed() -> bool:
    """
    Backwards-compatible alias for is_warp_installed().
    
    The CLI code in main.py expects warp.is_installed(), while the GUI
    uses warp.is_warp_installed(). This alias keeps both call sites
    working without duplicating installation logic.
    """
    return is_warp_installed()


def get_warp_status(timeout: int = 5) -> Tuple[bool, str]:
    """
    Get current WARP connection status.

    ВАЖНО: эта функция **только читает** состояние через `warp-cli status`
    и не выполняет никаких изменяющих команд. Она может возвращать `False`
    как для реально отключённого состояния, так и для переходных состояний
    (например, \"Status update: Updating\" или ошибки вида
    \"Failed to perform happy eyeballs\"), поэтому вызывающая сторона не
    должна использовать единичный `False` сразу после успешного подключения
    для немедленного переопределения доверенного результата операции.

    Returns:
        Tuple of (is_connected: bool, status_message: str)
    """
    try:
        result = subprocess.run(
            ["warp-cli", "status"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = result.stdout.strip()
        logger.debug(f"WARP status output: {output}")
        
        if "Status update: Connected" in output:
            return True, output
        if "Status update: Disconnected" in output or "Status update: Updating" in output:
            return False, output
        if "Disconnected" in output or "Not connected" in output:
            return False, output
        
        # Дополнительные проверки на случай нестандартного вывода
        if "Success" in output and "Connected" in output:
            return True, output
        
        return False, output
    
    except subprocess.TimeoutExpired:
        logger.warning("WARP status check timed out")
        return False, "Timeout"
    except Exception as e:
        logger.error(f"Error checking WARP status: {e}")
        return False, str(e)


def verify_warp_registration(timeout: int = 15, retries: int = 3) -> Tuple[bool, str]:
    """
    Verify that WARP is properly registered and ready to use.
    Includes internal retries to handle transient empty outputs from the daemon.
    """
    for attempt in range(1, retries + 1):
        try:
            logger.debug(f"Verifying WARP registration (attempt {attempt}/{retries})...")
            # Clear output before running to be safe
            output = ""
            result = subprocess.run(
                ["warp-cli", "registration", "show"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Check both stdout and stderr for keywords
            output = (result.stdout or "").strip()
            error_out = (result.stderr or "").strip()
            combined = (output + "\n" + error_out).strip()

            # If we see any of these, we are registered.
            if any(k in combined for k in ["Account type", "Device ID", "License key", "Account ID"]):
                 logger.debug("WARP registration verified via output keywords")
                 return True, "Registered"

            # Check for IPC timeout - this means daemon is stuck
            if "IPC call hit a timeout" in combined:
                logger.error("WARP daemon IPC timeout detected. Service might need a restart.")
                return False, "IPC Timeout"

            # If output is empty or says not registered, wait and retry
            if not combined or "not registered" in combined.lower():
                if attempt < retries:
                    logger.debug(f"Registration check result empty or 'not registered'. Retrying in {(attempt * 2)}s...")
                    time.sleep(attempt * 2) # Exponential backoff
                    continue
            
            # Final failure log
            logger.warning(f"WARP registration verification failed after {retries} attempts. Combined Output: '{combined[:100]}'")
            return False, "Not registered"
            
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(2)
                continue
            return False, "Timeout"
        except Exception as e:
            logger.error(f"Error verifying WARP registration: {e}")
            return False, str(e)
    return False, "Verification failed"


def start_warp_service(sudo_password: str, timeout: int = 30) -> Tuple[bool, str]:
    """
    Start the WARP service (warp-svc) if not already active.
    """
    try:
        # Check if already active to avoid redundant sudo calls and potential GUI focus
        check = subprocess.run(
            ["systemctl", "is-active", "--quiet", "warp-svc"],
            timeout=5
        )
        if check.returncode == 0:
            logger.debug("WARP service is already active, skipping start")
            return True, "Service already active"

        logger.info("Starting WARP service via systemctl...")
        result = subprocess.run(
            ["sudo", "-S", "systemctl", "start", "warp-svc"],
            input=sudo_password + "\n",
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            logger.info("WARP service started successfully")
            time.sleep(6)  # Увеличена пауза до 6 секунд для полной инициализации daemon
            return True, "Service started"
        else:
            error_msg = result.stderr.strip()[:200]
            logger.error(f"Failed to start WARP service: {error_msg}")
            return False, error_msg or "Failed to start service"
    except subprocess.TimeoutExpired:
        logger.warning("Start WARP service timed out")
        return False, "Timeout"
    except Exception as e:
        logger.error(f"Error starting WARP service: {e}")
        return False, str(e)


def _registration_delete(timeout: int = 15) -> Tuple[bool, str]:
    """
    Run warp-cli registration delete with Y confirmation for ToS/prompts.
    """
    try:
        logger.info("Executing: warp-cli registration delete")
        result = subprocess.run(
            ["warp-cli", "registration", "delete"],
            input="y\n",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        logger.debug(f"registration delete returncode={result.returncode}, out={out[:200]}, err={err[:200]}")
        if result.returncode == 0:
            return True, "Deleted"
        return False, err or out or "Delete failed"
    except Exception as e:
        logger.debug(f"registration delete error: {e}")
        return False, str(e)


def _registration_new(timeout: int = 15) -> Tuple[bool, str]:
    """
    Run warp-cli registration new. For new devices/accounts, this prompts for
    ToS acceptance. We automatically provide 'y' as input.
    """
    try:
        logger.info("Executing: warp-cli registration new")
        result = subprocess.run(
            ["warp-cli", "registration", "new"],
            input="y\n",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        combined = (out + "\n" + err).strip()
        logger.debug(f"registration new returncode={result.returncode}, out={out[:200]}, err={err[:200]}")
        
        # Success is returncode 0 OR output explicitly saying success
        if result.returncode == 0 or "Success" in combined:
            logger.info("WARP registration new successful")
            return True, "Registered"
        
        return False, err or out or "Registration failed"
    except Exception as e:
        logger.debug(f"registration new error: {e}")
        return False, str(e)


def register_warp(timeout: int = 15) -> Tuple[bool, str]:
    """
    Register a new WARP device/account.
    For registration with automatic delete/new alternation and verification,
    use register_warp_with_verification() instead.
    """
    return _registration_new(timeout)


def register_warp_with_verification(max_retries: int = 3, timeout: int = 15, sudo_password: str = None) -> Tuple[bool, str]:
    """
    Register WARP following the sequence that proven successful for the user:
    1. Try 'new' (might show ToS)
    2. Try 'delete' (Success)
    3. Try 'new' (Success)
    
    This handles cases where the daemon is in a weird state or ToS needs recycling.

    Args:
        max_retries: Number of registration sequence attempts
        timeout: Timeout for each registration command
        sudo_password: Sudo password to start the WARP service if needed
    """
    # 0. Ensure WARP service is running before any registration attempt
    if sudo_password:
        logger.info("Ensuring WARP service is running before registration...")
        service_ok, service_msg = start_warp_service(sudo_password)
        if not service_ok:
            logger.error(f"Failed to start WARP service: {service_msg}")
            # Continue anyway - maybe it's already running but check failed
        else:
            logger.info("WARP service is running")
    
    attempt = 0
    actual_max = 3 if max_retries == -1 else max_retries
    
    while attempt < actual_max:
        attempt += 1
        logger.info(f"WARP registration attempt {attempt}/{actual_max}")

        # 0. Quick check - maybe it's already fine?
        is_verified, _ = verify_warp_registration(retries=2)
        if is_verified:
            return True, "Already registered"

        # 1. First 'new' attempt (User log showed this as first step)
        logger.info("Registration sequence step 1: Trying 'new'...")
        _registration_new(timeout)
        time.sleep(5)
        
        # 2. 'delete' attempt (User log showed this as second step)
        logger.info("Registration sequence step 2: Trying 'delete'...")
        _registration_delete(timeout)
        time.sleep(5)

        # 3. Final 'new' attempt (User log showed this as third step)
        logger.info("Registration sequence step 3: Trying 'new' again...")
        ok_final, msg_final = _registration_new(timeout)
        
        # Wait for daemon to settle
        time.sleep(8)
        
        # Final verification
        is_verified, verify_msg = verify_warp_registration(retries=3)
        if is_verified:
            logger.info("WARP registration successful and verified (sequence completed)")
            global _warp_activated_by_us
            _warp_activated_by_us = True
            register_warp_cleanup()
            return True, "Registered"
        
        logger.warning(f"Registration sequence failed (attempt {attempt}): {verify_msg}")
        
        if attempt < actual_max:
             logger.info("Waiting 10s before next sequence retry...")
             time.sleep(10)
        
    return False, f"Registration failed after {actual_max} sequence attempts"


def set_warp_mode(timeout: int = 10) -> Tuple[bool, str]:
    """
    Set WARP mode to warp+doh (рекомендуемый для обхода).
    """
    try:
        result = subprocess.run(
            ["warp-cli", "mode", "warp+doh"],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0:
            logger.info("WARP mode set to warp+doh")
            return True, "Mode set"
        else:
            error_msg = result.stderr.strip()[:200]
            logger.error(f"Failed to set WARP mode: {error_msg}")
            return False, error_msg or "Failed to set mode"
    except Exception as e:
        logger.error(f"Error setting WARP mode: {e}")
        return False, str(e)


def connect_warp(timeout: int = 25) -> Tuple[bool, str]:
    """
    Connect to WARP.
    """
    try:
        result = subprocess.run(
            ["warp-cli", "connect"],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0:
            logger.info("WARP connected successfully")
            time.sleep(4)  # даём больше времени на установление соединения
            return True, "Connected"
        else:
            error_msg = result.stderr.strip()[:200]
            logger.error(f"Failed to connect WARP: {error_msg}")
            return False, error_msg or "Failed to connect"
    except Exception as e:
        logger.error(f"Error connecting WARP: {e}")
        return False, str(e)


def disconnect_warp(timeout: int = 15) -> Tuple[bool, str]:
    """
    Disconnect from WARP and delete registration.
    """
    global _warp_activated_by_us
    
    try:
        # Сначала отключаемся
        subprocess.run(
            ["warp-cli", "disconnect"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        # Затем удаляем регистрацию (подтверждение Y для ToS при необходимости)
        result = subprocess.run(
            ["warp-cli", "registration", "delete"],
            input="y\n",
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            # Clear the flag since we manually disconnected
            _warp_activated_by_us = False
            logger.info("WARP disconnected and registration deleted")
            return True, "Disconnected"
        else:
            error_msg = result.stderr.strip()[:200]
            logger.error(f"Failed to delete WARP registration: {error_msg}")
            return False, error_msg or "Failed to disconnect"
    except Exception as e:
        logger.error(f"Error disconnecting WARP: {e}")
        return False, str(e)


def _cleanup_warp() -> None:
    """
    Internal cleanup function called on exit.
    Automatically disconnects WARP if it was activated by this process.
    """
    global _warp_activated_by_us
    
    if not _warp_activated_by_us:
        logger.debug("WARP cleanup skipped - not activated by this process")
        return
    
    logger.info("Performing automatic WARP cleanup on exit...")
    try:
        # Disconnect WARP without checking result - best effort cleanup
        subprocess.run(
            ["warp-cli", "disconnect"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Delete registration (Y for any prompt)
        subprocess.run(
            ["warp-cli", "registration", "delete"],
            input="y\n",
            capture_output=True,
            text=True,
            timeout=10
        )
        
        logger.info("WARP cleanup completed successfully")
        _warp_activated_by_us = False
    except Exception as e:
        logger.error(f"Error during WARP cleanup: {e}")


def _signal_handler(signum, frame):
    """
    Signal handler for graceful shutdown.
    """
    logger.info(f"Received signal {signum}, cleaning up WARP...")
    _cleanup_warp()
    # Re-raise the signal to allow normal termination
    signal.signal(signum, signal.SIG_DFL)
    signal.raise_signal(signum)


def register_warp_cleanup() -> None:
    """
    Register cleanup handlers for automatic WARP shutdown.
    This function is called automatically after successful WARP activation.
    """
    global _cleanup_registered
    
    if _cleanup_registered:
        logger.debug("WARP cleanup handlers already registered")
        return
    
    # Register atexit handler
    atexit.register(_cleanup_warp)
    logger.debug("Registered atexit handler for WARP cleanup")
    
    # Register signal handlers for graceful shutdown
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
        logger.debug("Registered signal handlers (SIGTERM, SIGINT) for WARP cleanup")
    except Exception as e:
        logger.warning(f"Could not register signal handlers: {e}")
    
    _cleanup_registered = True


def activate_warp(sudo_password: str) -> Tuple[bool, str]:
    """
    Perform WARP registration sequence (not connection).
    
    This function prepares WARP for use by:
    1. Starting the WARP service
    2. Registering with automatic verification retry
    3. Setting the mode to warp+doh (preparation for connection)
    
    Note: This does NOT connect WARP. Use connect_warp() separately.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # 1. Запуск сервиса (с паузой 6 секунд внутри)
        logger.info("Starting WARP service...")
        success, msg = start_warp_service(sudo_password)
        if not success:
            return False, f"Service start failed: {msg}"

        # 2. Регистрация с автоматическим ретраем и верификацией
        logger.info("Registering WARP with verification retry...")
        success, msg = register_warp_with_verification(max_retries=3, sudo_password=sudo_password)
        if not success:
            return False, f"Registration failed: {msg}"
        
        logger.info(f"WARP registration successful: {msg}")

        # 3. Установка режима (подготовка к подключению)
        logger.info("Setting WARP mode to warp+doh...")
        success, msg = set_warp_mode()
        if not success:
            logger.warning(f"Mode setting failed (non-fatal): {msg}")
            # Don't fail here - mode can be set later during connection

        # 4. Установить флаг и зарегистрировать обработчики очистки
        global _warp_activated_by_us
        _warp_activated_by_us = True
        register_warp_cleanup()

        logger.info("WARP registration completed successfully")
        return True, "WARP registered and ready"
    
    except Exception as e:
        logger.error(f"WARP registration sequence failed: {e}")
        return False, str(e)


# WARP status after operation: False
# WARP status changed: False -> True  (через 7 секунд)
def reset_warp_registration(sudo_password: str) -> Tuple[bool, str]:
    """
    Complete WARP registration reset: stop service, delete reg, clean files, start, new reg.
    """
    try:
        logger.info("RESET: Stopping WARP service...")
        subprocess.run(["sudo", "-S", "systemctl", "stop", "warp-svc"], input=sudo_password + "\n", text=True, check=False)
        time.sleep(2)

        logger.info("RESET: Deleting registration...")
        _registration_delete()
        time.sleep(2)

        logger.info("RESET: Cleaning /var/lib/cloudflare-warp/* ...")
        # Removing specific files instead of the whole directory to avoid potential issues
        subprocess.run(["sudo", "-S", "rm", "-f", "/var/lib/cloudflare-warp/at_pro.json", "/var/lib/cloudflare-warp/reg.json", "/var/lib/cloudflare-warp/settings.json"], input=sudo_password + "\n", text=True, check=False)
        time.sleep(1)

        logger.info("RESET: Starting WARP service...")
        success, msg = start_warp_service(sudo_password)
        if not success:
            return False, f"Failed to restart service: {msg}"
        
        # Service start has 6s sleep inside, but let's be sure
        time.sleep(2)

        logger.info("RESET: Creating new registration...")
        success, msg = _registration_new()
        if not success:
             # Try one more time with delete then new if it says "Old registration"
             if "Old registration" in msg:
                 _registration_delete()
                 time.sleep(3)
                 success, msg = _registration_new()
        
        if success:
            time.sleep(5)
            is_verified, _ = verify_warp_registration()
            if is_verified:
                return True, "Registration reset successfully"
            return False, "Reset completed but verification failed"
        
        return False, f"Reset failed: {msg}"

    except Exception as e:
        logger.error(f"Reset WARP error: {e}")
        return False, str(e)
