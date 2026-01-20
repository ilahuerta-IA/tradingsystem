"""
MT5 Connection Manager.

Single Responsibility: Connect and disconnect from MetaTrader 5.
Does NOT fetch data or execute trades - those are separate modules.

Usage:
    connector = MT5Connector()
    if connector.connect():
        # ... do stuff
        connector.disconnect()
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None


class AccountType(Enum):
    """Account type enumeration for safety checks."""
    DEMO = "demo"
    REAL = "real"
    CONTEST = "contest"


@dataclass
class AccountInfo:
    """Immutable account information."""
    login: int
    server: str
    balance: float
    equity: float
    currency: str
    leverage: int
    trade_mode: int  # 0=demo, 1=contest, 2=real
    
    @property
    def is_demo(self) -> bool:
        """Check if account is demo (safe for testing)."""
        return self.trade_mode == 0
    
    @property
    def is_real(self) -> bool:
        """Check if account is real money."""
        return self.trade_mode == 2


class MT5Connector:
    """
    Manages MT5 terminal connection.
    
    Features:
    - Credentials loaded from JSON file (gitignored)
    - Demo-only mode enforcement for safety
    - Connection health checking
    - Clean disconnect handling
    
    Example:
        connector = MT5Connector(credentials_path="config/credentials/mt5.json")
        
        if connector.connect():
            print(f"Connected to {connector.account.server}")
            print(f"Balance: ${connector.account.balance}")
            
            # Check connection health
            if connector.is_connected():
                # ... trading logic
                pass
                
            connector.disconnect()
    """
    
    # Default paths relative to project root
    DEFAULT_CREDENTIALS_PATH = Path("config/credentials/mt5.json")
    TEMPLATE_PATH = Path("config/credentials/mt5_template.json")
    
    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        demo_only: bool = True,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize connector.
        
        Args:
            credentials_path: Path to credentials JSON file
            demo_only: If True, refuse to connect to real accounts (SAFETY)
            logger: Optional logger instance
        """
        self.credentials_path = credentials_path or self.DEFAULT_CREDENTIALS_PATH
        self.demo_only = demo_only
        self.logger = logger or logging.getLogger(__name__)
        
        self._connected = False
        self._account: Optional[AccountInfo] = None
        self._credentials: Optional[Dict[str, Any]] = None
        
        # Validate MT5 library availability
        if not MT5_AVAILABLE:
            self.logger.error("MetaTrader5 library not installed. Run: pip install MetaTrader5")
    
    @property
    def account(self) -> Optional[AccountInfo]:
        """Get current account info (None if not connected)."""
        return self._account
    
    def _load_credentials(self) -> bool:
        """
        Load credentials from JSON file.
        
        Returns:
            True if credentials loaded successfully
        """
        try:
            # Check if credentials file exists
            if not self.credentials_path.exists():
                self.logger.error(
                    f"Credentials file not found: {self.credentials_path}\n"
                    f"Copy {self.TEMPLATE_PATH} to {self.credentials_path} and fill your credentials."
                )
                return False
            
            with open(self.credentials_path, 'r') as f:
                self._credentials = json.load(f)
            
            # Validate required fields
            required = ['login', 'password', 'server']
            missing = [k for k in required if k not in self._credentials]
            
            if missing:
                self.logger.error(f"Missing credentials fields: {missing}")
                return False
            
            # Check for template values (user forgot to fill)
            if self._credentials['password'] == "YOUR_MT5_PASSWORD":
                self.logger.error("Credentials still have template values. Please fill mt5.json with real credentials.")
                return False
            
            self.logger.info(f"Credentials loaded for login: {self._credentials['login']}")
            return True
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in credentials file: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error loading credentials: {e}")
            return False
    
    def connect(self) -> bool:
        """
        Connect to MT5 terminal.
        
        Returns:
            True if connected successfully
            
        Raises:
            RuntimeError: If demo_only=True and account is real
        """
        if not MT5_AVAILABLE:
            self.logger.error("MT5 library not available")
            return False
        
        if self._connected:
            self.logger.warning("Already connected to MT5")
            return True
        
        # Load credentials
        if not self._load_credentials():
            return False
        
        try:
            # Initialize MT5 terminal with extended timeout
            self.logger.info("Initializing MT5 terminal...")
            
            # Try to find MT5 terminal path
            mt5_paths = [
                Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
                Path(r"C:\Program Files\Darwinex MT5\terminal64.exe"),
                Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe"),
            ]
            
            mt5_path = None
            for path in mt5_paths:
                if path.exists():
                    mt5_path = str(path)
                    break
            
            # Initialize with path if found, otherwise let MT5 find it
            init_kwargs = {"timeout": 120000}  # 2 minutes timeout
            if mt5_path:
                init_kwargs["path"] = mt5_path
                self.logger.info(f"Using MT5 path: {mt5_path}")
            
            if not mt5.initialize(**init_kwargs):
                error = mt5.last_error()
                self.logger.error(f"MT5 initialization failed: {error}")
                self.logger.error("Ensure MT5 terminal is running and logged in")
                return False
            
            self.logger.info("MT5 terminal initialized, attempting login...")
            
            # Clean server string (remove port if present)
            server = str(self._credentials['server'])
            if ':' in server:
                server = server.split(':')[0]
                self.logger.info(f"Server cleaned to: {server}")
            
            # Login to account
            login_result = mt5.login(
                login=int(self._credentials['login']),
                password=str(self._credentials['password']),
                server=server,
                timeout=60000  # 60 seconds for login
            )
            
            if not login_result:
                error = mt5.last_error()
                self.logger.error(f"MT5 login failed: {error}")
                self.logger.error(f"Server: {self._credentials['server']}, Login: {self._credentials['login']}")
                mt5.shutdown()
                return False
            
            # Get account info
            account_info = mt5.account_info()
            if account_info is None:
                self.logger.error("Failed to get account info after login")
                mt5.shutdown()
                return False
            
            # Create immutable account info
            self._account = AccountInfo(
                login=account_info.login,
                server=account_info.server,
                balance=account_info.balance,
                equity=account_info.equity,
                currency=account_info.currency,
                leverage=account_info.leverage,
                trade_mode=account_info.trade_mode
            )
            
            # SAFETY CHECK: Demo only mode
            if self.demo_only and self._account.is_real:
                self.logger.error(
                    "[SAFETY BLOCK] Attempted to connect to REAL account with demo_only=True!\n"
                    f"Account {self._account.login} is a REAL MONEY account.\n"
                    "Set demo_only=False if you really want to trade real money."
                )
                mt5.shutdown()
                self._account = None
                return False
            
            self._connected = True
            
            account_type = "DEMO" if self._account.is_demo else "REAL"
            self.logger.info(
                f"[OK] Connected to MT5 [{account_type}]\n"
                f"   Account: {self._account.login} @ {self._account.server}\n"
                f"   Balance: {self._account.balance:.2f} {self._account.currency}\n"
                f"   Leverage: 1:{self._account.leverage}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            self._cleanup()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from MT5 terminal."""
        if self._connected:
            self._cleanup()
            self.logger.info("Disconnected from MT5")
    
    def _cleanup(self) -> None:
        """Internal cleanup."""
        if MT5_AVAILABLE:
            mt5.shutdown()
        self._connected = False
        self._account = None
    
    def is_connected(self) -> bool:
        """
        Check if connection is alive.
        
        Returns:
            True if connected and terminal is responsive
        """
        if not self._connected or not MT5_AVAILABLE:
            return False
        
        try:
            # Try to get terminal info as health check
            # Retry up to 3 times as terminal_info() can fail intermittently
            for attempt in range(3):
                info = mt5.terminal_info()
                if info is not None:
                    return True
                # Brief pause before retry
                import time
                time.sleep(0.1)
            
            # All retries failed - connection is stale, mark as disconnected
            self.logger.warning("terminal_info() returned None after retries, marking as disconnected")
            self._connected = False
            return False
        except Exception as e:
            self.logger.warning(f"is_connected check failed: {e}")
            self._connected = False
            return False
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect after connection loss.
        
        Forces full reconnection even if _connected flag is True.
        
        Returns:
            True if reconnected successfully
        """
        self.logger.info("Forcing full reconnection...")
        # Always cleanup and reinitialize, regardless of _connected state
        self._cleanup()
        import time
        time.sleep(1)  # Brief pause to ensure MT5 releases resources
        return self.connect()
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol information.
        
        Args:
            symbol: Symbol name (e.g., 'EURUSD')
            
        Returns:
            Dictionary with symbol info or None if not found
        """
        if not self.is_connected():
            return None
        
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                # Try to enable symbol first
                if mt5.symbol_select(symbol, True):
                    info = mt5.symbol_info(symbol)
            
            if info is None:
                self.logger.warning(f"Symbol not found: {symbol}")
                return None
            
            return {
                'name': info.name,
                'digits': info.digits,
                'point': info.point,
                'trade_contract_size': info.trade_contract_size,
                'volume_min': info.volume_min,
                'volume_max': info.volume_max,
                'volume_step': info.volume_step,
                'spread': info.spread,
                'bid': info.bid,
                'ask': info.ask,
            }
            
        except Exception as e:
            self.logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False


# Convenience function for quick testing
def test_connection(credentials_path: Optional[Path] = None) -> bool:
    """
    Quick connection test.
    
    Args:
        credentials_path: Optional path to credentials file
        
    Returns:
        True if connection successful
    """
    logging.basicConfig(level=logging.INFO)
    
    with MT5Connector(credentials_path=credentials_path, demo_only=True) as conn:
        if conn.is_connected():
            print(f"\n[OK] Connection test PASSED")
            print(f"   Account: {conn.account.login}")
            print(f"   Balance: ${conn.account.balance:.2f}")
            
            # Test symbol info
            eurusd = conn.get_symbol_info('EURUSD')
            if eurusd:
                print(f"   EURUSD spread: {eurusd['spread']} points")
            
            return True
        else:
            print("\n[FAIL] Connection test FAILED")
            return False


if __name__ == "__main__":
    # Allow running directly for testing
    test_connection()
