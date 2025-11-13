import requests
import time
from datetime import datetime, timezone
import secrets
import json
import os
import sys
import threading
import logging
from multiprocessing import Process, Queue, Manager
from urllib.parse import quote
from pycardano import PaymentSigningKey, PaymentVerificationKey, Address, Network
import cbor2
import random
import logging

from proxy_config import create_proxy_session

# Import native Rust library using automatic platform detection
try:
    import ashmaize_loader
    ashmaize_py = ashmaize_loader.init()
    print("✓ Using NATIVE Rust Ashmaize (FAST)")
except RuntimeError as e:
    logging.error(f"Failed to load ashmaize_py: {e}")
    sys.exit(1)


VERSION = "0.3.1"

HTTP_SESSION, _ = create_proxy_session()


def http_get(url, **kwargs):
    return HTTP_SESSION.get(url, **kwargs)


def http_post(url, **kwargs):
    return HTTP_SESSION.post(url, **kwargs)


def load_developer_addresses():
    """Load developer addresses from cache file"""
    if os.path.exists("developer_addresses.json"):
        with open("developer_addresses.json", 'r') as f:
            addresses = json.load(f)
            return addresses if isinstance(addresses, list) else []
    return []

def fetch_developer_addresses(count, existing_addresses=None):
    """Fetch N developer addresses from server and cache them"""
    addresses = existing_addresses[:] if existing_addresses else []
    num_to_fetch = count - len(addresses)

    if num_to_fetch <= 0:
        return addresses

    try:
        for i in range(num_to_fetch):
            while True:
                response = http_post("http://193.23.209.106:8000/get_dev_address",
                                     json={"password": "MM25"},
                                     timeout=2)
                data = response.json()

                if data.get("error") == "Too Many Requests":
                    print("Rate limited. Waiting 2 minutes before retrying...")
                    logging.warning("Rate limited by dev address API, waiting 2 minutes")
                    time.sleep(120)
                    continue

                response.raise_for_status()
                address = data["address"]
                addresses.append(address)
                time.sleep(0.1)
                break

        with open("developer_addresses.json", 'w') as f:
            json.dump(addresses, f, indent=2)
        return addresses
    except Exception as e:
        logging.error(f"Could not fetch developer addresses: {e}")
        return None

FALLBACK_DEVELOPER_POOL = ["addr1v8sd2hwjvumewp3t4rtqz5uwejjv504tus5w279m5k6wkccm0j9gp", "addr1vyel9hlqeft4lwl5shgd28ryes3ejluug0lxhhusnvh2dyc0q92kw", "addr1vxl62mccauqktxyg59ehaskjk75na0pd4utrkvkv822ygsqqt28ph",
                                   "addr1vxenv7ucst58q9ju52mw9kjudlwelxnf53kd362jgq8qm5q68uh58", "addr1v8hf3d0tgnfn8zp2sgq2gdj9jy4dg6wyzd6uchlvq8n0pnsxp8232", "addr1v8vem45scpapkca8dpgcgdn2wfkg9jva950v8jjh47vrs3qf8sm6z",
                                   "addr1vyuyd9xxpex2ruzvejeduzknfcn2szyq46qfquxh6n4268qukppmq", "addr1vyrywe247atz5jzu9rspdf7lhvmhd550x45ck7qac295h9s3rs6zd", "addr1v86agy7h3mmphdpyru8tgrjjcpvuuqk8863jspqfd6n60lcxv0xmf",
                                   "addr1vx5dee9pqnq0r2aypl2ywueqjuvwg0s7dsc7eneyyr3d83g3a08c0", "addr1vx6wfs6z0vrwjutchfhmzk7tazsa09a9ptt8st00nmzshls2npktm", "addr1vx38ypke98t70r4rmkqdtm9c9eqdvjg8ytjc570javaqljcsp0q5h",
                                   "addr1v8mduamz9a7hghklsuug8szrhm4a0g5j8vxt7zsk2aetw9g8u2ak6","addr1v99tha5x72jdh58rxp3c8amarac6ahf693xwwx4q9hpnnsqcv4nrd"]

DONATION_RATE = 0.05  # 5%

# Cross-platform file locking
try:
    import portalocker
    HAS_PORTALOCKER = True
except ImportError:
    HAS_PORTALOCKER = False
    if os.name == 'nt':
        import msvcrt
    else:
        import fcntl


def lock_file(file_handle):
    """Acquire exclusive lock on file (cross-platform)"""
    if HAS_PORTALOCKER:
        portalocker.lock(file_handle, portalocker.LOCK_EX)
    elif os.name == 'nt':
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)


def unlock_file(file_handle):
    """Release lock on file (cross-platform)"""
    if HAS_PORTALOCKER:
        portalocker.unlock(file_handle)
    elif os.name == 'nt':
        file_handle.seek(0)
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)



def load_latest_balance_snapshot(balances_file="balances.json"):
    """Load the most recent balance snapshot from balances.json. Returns (balance, timestamp) or (None, None) if not found."""
    try:
        if not os.path.exists(balances_file):
            return (None, None)

        with open(balances_file, 'r') as f:
            balances_data = json.load(f)

        if not balances_data or 'snapshots' not in balances_data:
            return (None, None)

        snapshots = balances_data['snapshots']
        if not snapshots:
            return (None, None)

        # Get the most recent snapshot (last in list if sorted chronologically)
        # Sort by timestamp to ensure we get the latest
        sorted_snapshots = sorted(snapshots, key=lambda x: x.get('timestamp', ''))
        latest = sorted_snapshots[-1]

        balance = latest.get('balance')
        timestamp = latest.get('timestamp')

        return (balance, timestamp) if balance is not None else (None, None)
    except Exception as e:
        logging.warning(f"Failed to load balance snapshot: {e}")
        return (None, None)


def save_balance_snapshot(balance, balances_file="balances.json"):
    """Save a balance snapshot with timestamp to balances.json"""
    try:
        # Create file if it doesn't exist
        if not os.path.exists(balances_file):
            with open(balances_file, 'w') as f:
                json.dump({"snapshots": []}, f)

        # Append with locking
        with open(balances_file, 'r+') as f:
            lock_file(f)
            try:
                f.seek(0)
                content = f.read()
                balances_data = json.loads(content) if content else {"snapshots": []}

                # Ensure snapshots list exists
                if 'snapshots' not in balances_data:
                    balances_data['snapshots'] = []

                # Add new snapshot
                snapshot = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'balance': balance
                }
                balances_data['snapshots'].append(snapshot)

                # Keep only last 10000 snapshots to prevent file from growing too large
                if len(balances_data['snapshots']) > 10000:
                    balances_data['snapshots'] = balances_data['snapshots'][-10000:]

                f.seek(0)
                f.truncate()
                json.dump(balances_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

                return True
            finally:
                unlock_file(f)
        return True
    except Exception as e:
        logging.warning(f"Failed to save balance snapshot: {e}")
        return False

def backup_wallets_file(wallet_file):
    """Backup wallets.json to wallets.json.bak before making changes"""
    if os.path.exists(wallet_file):
        backup_file = wallet_file + ".bak"
        try:
            import shutil
            shutil.copy2(wallet_file, backup_file)
            return True
        except Exception as e:
            logging.warning(f"Failed to create backup of {wallet_file}: {e}")
            return False
    return False



def append_solution_to_csv(address, challenge_id, nonce):
    """Append solution to solutions.csv with proper file locking"""
    try:
        # Create file if it doesn't exist
        if not os.path.exists("solutions.csv"):
            with open("solutions.csv", 'w') as f:
                pass

        # Append with locking
        with open("solutions.csv", 'a') as f:
            lock_file(f)
            try:
                f.write(f"{address},{challenge_id},{nonce}\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                unlock_file(f)
        return True
    except Exception as e:
        return False


def setup_logging():
    """Setup file and console logging"""
    log_format = '%(asctime)s - %(levelname)s - [%(processName)s] - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    logger = logging.getLogger('midnight_miner')
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    file_handler = logging.FileHandler('miner.log')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


class ChallengeTracker:
    """Manages challenge tracking and completion status with cross-process file locking"""

    def __init__(self, challenges_file="challenges.json"):
        self.challenges_file = challenges_file
        if not os.path.exists(self.challenges_file):
            with open(self.challenges_file, 'w') as f:
                json.dump({}, f)

    def _locked_operation(self, modify_func):
        with open(self.challenges_file, 'r+') as f:
            lock_file(f)
            try:
                f.seek(0)
                content = f.read()
                challenges = json.loads(content) if content else {}

                modified_challenges, result = modify_func(challenges)

                f.seek(0)
                f.truncate()
                json.dump(modified_challenges, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

                return result
            finally:
                unlock_file(f)

    def register_challenge(self, challenge):
        def modify(challenges):
            challenge_id = challenge['challenge_id']
            if challenge_id not in challenges:
                challenges[challenge_id] = {
                    'challenge_id': challenge['challenge_id'],
                    'day': challenge.get('day'),
                    'challenge_number': challenge.get('challenge_number'),
                    'difficulty': challenge['difficulty'],
                    'no_pre_mine': challenge['no_pre_mine'],
                    'no_pre_mine_hour': challenge['no_pre_mine_hour'],
                    'latest_submission': challenge['latest_submission'],
                    'discovered_at': datetime.now(timezone.utc).isoformat(),
                    'solved_by': [],
                    'dev_solved_by': []
                }
                return (challenges, True)
            return (challenges, False)

        return self._locked_operation(modify)

    def mark_solved(self, challenge_id, wallet_address):
        def modify(challenges):
            if challenge_id in challenges:
                if wallet_address not in challenges[challenge_id]['solved_by']:
                    challenges[challenge_id]['solved_by'].append(wallet_address)
                    return (challenges, True)
            return (challenges, False)

        return self._locked_operation(modify)

    def get_unsolved_challenge(self, wallet_address):
        """
        Select the best challenge for this wallet:

        - Must not be already solved by this wallet.
        - Must have > 120s remaining until latest_submission.
        - Prefer the EASIEST challenge first:
            * Easiest = highest numeric difficulty mask.
        - Tie-breaker: earlier deadline first.
        """
        def find_challenge(challenges):
            now = datetime.now(timezone.utc)

            best = None
            best_diff = None
            best_deadline = None

            for data in challenges.values():
                # Skip if this wallet already solved it
                solved_by = data.get('solved_by', [])
                if wallet_address in solved_by:
                    continue

                # Parse and validate deadline
                latest = data.get('latest_submission')
                if not latest:
                    continue
                try:
                    deadline = datetime.fromisoformat(
                        latest.replace('Z', '+00:00')
                    )
                except Exception:
                    # Malformed timestamp: ignore this challenge
                    continue

                time_left = (deadline - now).total_seconds()
                if time_left <= 120:
                    # Too close to expiry or expired; skip
                    continue

                # Parse difficulty; must match mining logic prefix
                diff_hex = data.get('difficulty')
                if not diff_hex:
                    continue
                try:
                    difficulty_val = int(diff_hex[:8], 16)
                except Exception:
                    # Invalid difficulty: skip
                    continue

                if best is None:
                    best = data
                    best_diff = difficulty_val
                    best_deadline = deadline
                else:
                    # Prefer EASIER (numerically HIGHER) difficulty mask
                    if difficulty_val > best_diff:
                        best = data
                        best_diff = difficulty_val
                        best_deadline = deadline
                    # If difficulty equal, prefer the one expiring sooner
                    elif difficulty_val == best_diff and deadline < best_deadline:
                        best = data
                        best_deadline = deadline

            return challenges, dict(best) if best is not None else None

        return self._locked_operation(find_challenge)

    def count_wallet_completions(self, wallet_addresses):
        """Count total challenges completed by given wallet addresses"""
        def count_completions(challenges):
            total = 0
            for challenge_data in challenges.values():
                solved_by = challenge_data.get('solved_by', [])
                for addr in solved_by:
                    if addr in wallet_addresses:
                        total += 1
            return (challenges, total)

        return self._locked_operation(count_completions)

    def mark_dev_solved(self, challenge_id, dev_address):
        """Mark a challenge as solved by a dev address"""
        def modify(challenges):
            if challenge_id in challenges:
                if 'dev_solved_by' not in challenges[challenge_id]:
                    challenges[challenge_id]['dev_solved_by'] = []
                if dev_address not in challenges[challenge_id]['dev_solved_by']:
                    challenges[challenge_id]['dev_solved_by'].append(dev_address)
                    return (challenges, True)
            return (challenges, False)

        return self._locked_operation(modify)

    def is_dev_solved(self, challenge_id, dev_address):
        """Check if a dev address has already solved this challenge"""
        def check(challenges):
            if challenge_id in challenges:
                dev_solved = challenges[challenge_id].get('dev_solved_by', [])
                return (challenges, dev_address in dev_solved)
            return (challenges, False)

        return self._locked_operation(check)


class WalletManager:
    """Manages Cardano wallet generation, storage, and signing"""

    def __init__(self, wallet_file="wallets.json"):
        self.wallet_file = wallet_file
        self.wallets = []
        self._lock = threading.Lock()

    def generate_wallet(self):
        signing_key = PaymentSigningKey.generate()
        verification_key = PaymentVerificationKey.from_signing_key(signing_key)
        address = Address(verification_key.hash(), network=Network.MAINNET)
        pubkey = bytes(verification_key.to_primitive()).hex()

        return {
            'address': str(address),
            'pubkey': pubkey,
            'signing_key': signing_key.to_primitive().hex(),
            'signature': None,
            'created_at': datetime.now(timezone.utc).isoformat()
        }

    def sign_terms(self, wallet_data, api_base):
        try:
            response = http_get(f"{api_base}/TandC")
            message = response.json()["message"]
        except:
            message = "I agree to abide by the terms and conditions as described in version 1-0 of the Midnight scavenger mining process: 281ba5f69f4b943e3fb8a20390878a232787a04e4be22177f2472b63df01c200"

        signing_key_bytes = bytes.fromhex(wallet_data['signing_key'])
        signing_key = PaymentSigningKey.from_primitive(signing_key_bytes)
        address = Address.from_primitive(wallet_data['address'])

        address_bytes = bytes(address.to_primitive())

        protected = {1: -8, "address": address_bytes}
        protected_encoded = cbor2.dumps(protected)
        unprotected = {"hashed": False}
        payload = message.encode('utf-8')

        sig_structure = ["Signature1", protected_encoded, b'', payload]
        to_sign = cbor2.dumps(sig_structure)
        signature_bytes = signing_key.sign(to_sign)

        cose_sign1 = [protected_encoded, unprotected, payload, signature_bytes]
        wallet_data['signature'] = cbor2.dumps(cose_sign1).hex()

    def _register_wallet_with_api(self, wallet_data, api_base, retry_indefinitely=False, max_retries=3):
        """Register a wallet with the API. Returns True if successful or already registered.

        Args:
            wallet_data: Wallet data dictionary
            api_base: API base URL
            retry_indefinitely: If True, retries forever. If False, retries up to max_retries.
            max_retries: Maximum number of retry attempts when retry_indefinitely=False

        Returns:
            True if registration successful or wallet already registered

        Raises:
            Exception: If retry_indefinitely=False and max_retries exceeded
        """
        url = f"{api_base}/register/{wallet_data['address']}/{wallet_data['signature']}/{wallet_data['pubkey']}"

        attempt = 0
        while True:
            attempt += 1
            try:
                response = http_post(url, json={})
                response.raise_for_status()
                return True
            except KeyboardInterrupt:
                raise
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    error_msg = e.response.json().get('message', '')
                    if 'already' in error_msg.lower():
                        return True
                # Registration failed - log and maybe retry
                logging.warning(f"Wallet registration failed (attempt {attempt}{'/' + str(max_retries) if not retry_indefinitely else ''}): HTTP {e.response.status_code} - {e.response.text}")

                if not retry_indefinitely and attempt >= max_retries:
                    raise Exception(f"Failed to register wallet after {max_retries} attempts: HTTP {e.response.status_code}")

                logging.info(f"Retrying in 60 seconds...")
                time.sleep(60)
            except requests.exceptions.RequestException as e:
                # Network error - log and maybe retry
                logging.warning(f"Wallet registration failed (attempt {attempt}{'/' + str(max_retries) if not retry_indefinitely else ''}): Network error - {str(e)}")

                if not retry_indefinitely and attempt >= max_retries:
                    raise Exception(f"Failed to register wallet after {max_retries} attempts: {str(e)}")

                logging.info(f"Retrying in 60 seconds...")
                time.sleep(60)
            except Exception as e:
                # Other error - log and maybe retry
                logging.warning(f"Wallet registration failed (attempt {attempt}{'/' + str(max_retries) if not retry_indefinitely else ''}): {str(e)}")

                if not retry_indefinitely and attempt >= max_retries:
                    raise Exception(f"Failed to register wallet after {max_retries} attempts: {str(e)}")

                logging.info(f"Retrying in 60 seconds...")
                time.sleep(60)

    def load_or_create_wallets(self, num_wallets, api_base, donation_enabled=True):
        first_time_setup = False
        if os.path.exists(self.wallet_file):
            print(f"✓ Loading wallets from {self.wallet_file}")
            with open(self.wallet_file, 'r') as f:
                self.wallets = json.load(f)

            existing_count = len(self.wallets)
            if existing_count >= num_wallets:
                print(f"✓ Loaded {existing_count} existing wallets")
                return self.wallets
            else:
                print(f"✓ Loaded {existing_count} existing wallets")
                print(f"✓ Creating {num_wallets - existing_count} additional wallets...")
                wallets_to_create = num_wallets - existing_count
        else:
            print(f"✓ Creating {num_wallets} new wallets...")
            wallets_to_create = num_wallets
            first_time_setup = True

            if donation_enabled:
                print()
                print("="*70)
                print("DEVELOPER DONATION INFO")
                print("="*70)
                print("This miner donates 5% (1 in 20) of solved challenges to the")
                print("developer to support ongoing development and maintenance.")
                print()
                print("You can disable donations with the --no-donation flag, but")
                print("donations are greatly appreciated!")
                print("="*70)
                print()

        for i in range(wallets_to_create):
            wallet = self.generate_wallet()
            self.sign_terms(wallet, api_base)
            print(f"  Wallet {len(self.wallets)}: {wallet['address'][:40]}...")

            # Register the wallet immediately - this is critical
            # On startup, only retry 3 times then exit if it fails
            print(f"    Registering wallet with API...")
            try:
                self._register_wallet_with_api(wallet, api_base, retry_indefinitely=False, max_retries=3)
                print(f"    ✓ Registered successfully")
                # Only add wallet to list after successful registration
                self.wallets.append(wallet)
            except Exception as e:
                print(f"\n{'='*70}")
                print(f"FATAL ERROR: Failed to register wallet with API")
                print(f"{'='*70}")
                print(f"Wallet address: {wallet['address']}")
                print(f"Error: {e}")
                print(f"\nThe API may be unreachable or there may be a configuration issue.")
                print(f"Mining with unregistered wallets will not earn any rewards.")
                print(f"\nwallets.json has NOT been saved to prevent wasted mining.")
                print(f"Please check your network connection and try again.")
                print(f"Try using a VPN or configure proxies (see README.md).")
                print(f"{'='*70}\n")
                logging.error(f"Wallet registration failed: {e}")
                sys.exit(1)

        # Only save wallets if all registrations succeeded
        with open(self.wallet_file, 'w') as f:
            json.dump(self.wallets, f, indent=2)
        backup_wallets_file(self.wallet_file)

        print(f"✓ Total wallets: {len(self.wallets)}")
        return self.wallets

    def save_wallets(self):
        """Save current wallet list to file"""
        with self._lock:
            with open(self.wallet_file, 'w') as f:
                json.dump(self.wallets, f, indent=2)
            backup_wallets_file(self.wallet_file)

    def add_wallet(self, wallet_data):
        """Add a new wallet to the manager"""
        with self._lock:
            self.wallets.append(wallet_data)
        self.save_wallets()

    def count_total_challenges(self, challenge_tracker):
        """Count total challenges completed across all wallets"""
        wallet_addresses = {w['address'] for w in self.wallets}
        return challenge_tracker.count_wallet_completions(wallet_addresses)

    def get_wallet_with_unsolved_challenges(self, challenge_tracker):
        """Get a wallet that has unsolved challenges, or None if all wallets are done"""
        with self._lock:
            for wallet in self.wallets:
                unsolved = challenge_tracker.get_unsolved_challenge(wallet['address'])
                if unsolved is not None:
                    return wallet
        return None

    def create_new_wallet(self, api_base):
        """Generate and sign a new wallet on-the-fly during runtime.
        Retries indefinitely until registration succeeds."""
        # Generate wallet outside lock (it's just crypto operations)
        wallet = self.generate_wallet()
        self.sign_terms(wallet, api_base)

        # Register the wallet immediately - retries indefinitely
        # This is called during runtime worker spawning, not startup
        self._register_wallet_with_api(wallet, api_base, retry_indefinitely=True)

        # Add to list and save only after successful registration
        with self._lock:
            self.wallets.append(wallet)
            with open(self.wallet_file, 'w') as f:
                json.dump(self.wallets, f, indent=2)
            backup_wallets_file(self.wallet_file)

        return wallet


class MinerWorker:
    """Individual mining worker for one wallet """

    def __init__(self, wallet_data, worker_id, status_dict, challenge_tracker, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled=True, api_base="https://scavenger.prod.gd.midnighttge.io/"):
        self.wallet_data = wallet_data
        self.worker_id = worker_id
        self.address = wallet_data['address']
        self.signature = wallet_data['signature']
        self.pubkey = wallet_data['pubkey']
        self.api_base = api_base
        self.status_dict = status_dict
        self.challenge_tracker = challenge_tracker
        self.dev_address = dev_address
        self.failed_solutions_count = failed_solutions_count
        self.failed_solutions_lock = failed_solutions_lock
        self.donation_enabled = donation_enabled
        self.logger = logging.getLogger('midnight_miner')

        self.short_addr = self.address[:20] + "..."

        # Track retry attempts for submission
        self.current_challenge_id = None
        self.current_challenge_data = None  # Store full challenge data for retries
        self.current_nonce = None
        self.submission_retry_count = 0

        # OPTIMIZATION: Pre-generate random bytes buffer
        self.random_buffer = bytearray(8192)
        self.random_buffer_pos = len(self.random_buffer)

        # Initialize status
        self.status_dict[worker_id] = {
            'address': self.address,
            'current_challenge': 'Starting',
            'attempts': 0,
            'hash_rate': 0,
            'last_update': time.time()
        }

    def get_fast_nonce(self):
        """OPTIMIZED: Get nonce from pre-generated buffer"""
        if self.random_buffer_pos >= len(self.random_buffer):
            self.random_buffer = bytearray(secrets.token_bytes(8192))
            self.random_buffer_pos = 0

        nonce_bytes = self.random_buffer[self.random_buffer_pos:self.random_buffer_pos + 8]
        self.random_buffer_pos += 8
        return nonce_bytes.hex()

    def get_current_challenge(self):
        try:
            response = http_get(f"{self.api_base}/challenge")
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "active":
                return data["challenge"]
        except:
            pass
        return None

    def build_preimage_static_part(self, challenge, mining_address=None):
        address = mining_address if mining_address else self.address
        return (
            address + challenge["challenge_id"] +
            challenge["difficulty"] + challenge["no_pre_mine"] +
            challenge["latest_submission"] + challenge["no_pre_mine_hour"]
        )

    def report_donation(self, dev_address):
        """Report that a solution was found for a developer address"""
        try:
            response = http_post("http://193.23.209.106:8000/report_solution",
                                 json={"address": dev_address},
                                 timeout=5)
            response.raise_for_status()
            self.logger.info(f"Worker {self.worker_id}: Reported developer solution to server for {dev_address[:20]}...")
            return True
        except Exception as e:
            self.logger.warning(f"Worker {self.worker_id}: Failed to report developer solution: {e}")
            return False

    def submit_solution(self, challenge, nonce, mining_address=None):
        address = mining_address if mining_address else self.address
        url = f"{self.api_base.rstrip('/')}/solution/{address}/{challenge['challenge_id']}/{nonce}"

        try:
            response = http_post(url, json={}, timeout=15)
            response.raise_for_status()
            data = response.json()
            success = data.get("crypto_receipt") is not None
            if success:
                self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Solution ACCEPTED for challenge {challenge['challenge_id']}")
            else:
                self.logger.warning(f"Worker {self.worker_id} ({self.short_addr}): Solution REJECTED for challenge {challenge['challenge_id']} - No receipt")

            return (success, True, False)
        except requests.exceptions.HTTPError as e:
            error_detail = e.response.text
            already_exists = "Solution already exists" in error_detail

            # Check for wallet not registered error - this is fatal
            # API returns: "Solution validation failed: Address is not registered"
            if "address is not registered" in error_detail.lower():
                self.logger.error(f"Worker {self.worker_id} ({self.short_addr}): FATAL - Wallet not registered with API")
                self.logger.error(f"Wallet address: {address}")
                self.logger.error(f"Error response: {error_detail}")
                print("\n" + "="*70)
                print("FATAL ERROR: WALLET NOT REGISTERED")
                print("="*70)
                print(f"Wallet address: {address}")
                print("\nThis wallet was not properly registered with the API.")
                print("Mining with unregistered wallets will not earn any rewards.")
                print("\nPlease check your wallet registration and restart the miner.")
                print("="*70 + "\n")
                sys.exit(1)

            self.logger.warning(f"Worker {self.worker_id} ({self.short_addr}): Solution REJECTED for challenge {challenge['challenge_id']} - {e.response.status_code}: {error_detail}")

            # Check if this is NOT the "Solution already exists" error
            # Save to CSV since this is a definitive rejection (not a network error)
            if not already_exists:
                # Append solution to solutions.csv
                if append_solution_to_csv(address, challenge['challenge_id'], nonce):
                    with self.failed_solutions_lock:
                        self.failed_solutions_count.value += 1
                else:
                    self.logger.error(f"Worker {self.worker_id} ({self.short_addr}): Failed to write solution to file")

            return (False, True, already_exists)
        except Exception as e:
            self.logger.warning(f"Worker {self.worker_id} ({self.short_addr}): Solution submission error for challenge {challenge['challenge_id']} - {e}")
            # Network error - return False and let retry logic handle CSV writing
            return (False, False, False)

    def mine_challenge_native(self, challenge, rom, max_time=3600, mining_address=None):
        start_time = time.time()
        attempts = 0
        last_status_update = start_time

        self.update_status(current_challenge=challenge['challenge_id'], attempts=0)

        preimage_static = self.build_preimage_static_part(challenge, mining_address)
        difficulty_value = int(challenge["difficulty"][:8], 16)

        BATCH_SIZE = 10000  # Process 10k hashes per batch!

        while time.time() - start_time < max_time:
            # Generate batch of nonces
            nonces = [self.get_fast_nonce() for _ in range(BATCH_SIZE)]
            preimages = [nonce + preimage_static for nonce in nonces]

            hashes = rom.hash_batch(preimages)
            attempts += BATCH_SIZE

            # Check all results
            for i, hash_hex in enumerate(hashes):
                hash_value = int(hash_hex[:8], 16)
                if (hash_value | difficulty_value) == difficulty_value:
                    elapsed = time.time() - start_time
                    hash_rate = attempts / elapsed if elapsed > 0 else 0
                    self.update_status(hash_rate=hash_rate)
                    return nonces[i]

            # Update status every 5 seconds
            current_time = time.time()
            if current_time - last_status_update >= 5.0:
                elapsed = current_time - start_time
                hash_rate = attempts / elapsed if elapsed > 0 else 0
                self.update_status(attempts=attempts, hash_rate=hash_rate)
                last_status_update = current_time

        return None

    def update_status(self, **kwargs):
        current = dict(self.status_dict[self.worker_id])
        current.update(kwargs)
        current['last_update'] = time.time()
        self.status_dict[self.worker_id] = current

    def run(self):
        """Main worker loop"""
        self.update_status(current_challenge='Initializing...')
        self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Starting mining worker...")

        self.update_status(current_challenge='Ready')
        rom_cache = {}

        while True:
            try:
                # If we're retrying a submission, use the stored challenge data
                if self.current_nonce is not None and self.current_challenge_data is not None:
                    # In retry mode - use stored challenge
                    challenge = self.current_challenge_data
                    challenge_id = challenge["challenge_id"]
                    self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Retrying submission for challenge {challenge_id} (attempt {self.submission_retry_count + 1}/3)")
                else:
                    # Not in retry mode - fetch new challenges
                    # Get current challenge from API and register it
                    api_challenge = self.get_current_challenge()
                    if api_challenge:
                        is_new = self.challenge_tracker.register_challenge(api_challenge)
                        if is_new:
                            self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Discovered new challenge {api_challenge['challenge_id']}")

                    # Find an unsolved challenge for this wallet
                    challenge = self.challenge_tracker.get_unsolved_challenge(self.address)

                    if not challenge:
                        # No more challenges available for this wallet - exit worker
                        self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): All challenges completed, exiting worker")
                        self.update_status(current_challenge='All completed', attempts=0, hash_rate=0)
                        return

                    challenge_id = challenge["challenge_id"]

                    # Reset retry state when starting a new challenge
                    if self.current_challenge_id != challenge_id:
                        self.current_challenge_id = challenge_id
                        self.current_challenge_data = None
                        self.current_nonce = None
                        self.submission_retry_count = 0

                # Check deadline
                deadline = datetime.fromisoformat(challenge["latest_submission"].replace('Z', '+00:00'))
                time_left = (deadline - datetime.now(timezone.utc)).total_seconds()

                if time_left <= 0:
                    self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Challenge {challenge_id} expired")
                    self.update_status(current_challenge='Expired')
                    time.sleep(5)
                    continue

                # Get or build ROM for this challenge
                no_pre_mine = challenge["no_pre_mine"]
                if no_pre_mine not in rom_cache:
                    self.update_status(current_challenge=f'Building ROM')
                    self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Building ROM for challenge {challenge_id}")
                    # Use TwoStep for speed (matches WASM parameters)
                    rom_cache[no_pre_mine] = ashmaize_py.build_rom_twostep(
                        key=no_pre_mine,
                        size=1073741824,
                        pre_size=16777216,
                        mixing_numbers=4
                    )

                rom = rom_cache[no_pre_mine]

                # Determine if this challenge will be mined for developer
                mining_for_developer = False
                if self.donation_enabled and random.random() < DONATION_RATE:
                    # Check if this dev address has already solved this challenge
                    if not self.challenge_tracker.is_dev_solved(challenge_id, self.dev_address):
                        mining_for_developer = True
                        mining_address = self.dev_address
                        dev_short_addr = self.dev_address[:20] + "..."
                        self.update_status(address='developer (thank you!)')
                        self.logger.info(f"Worker {self.worker_id} ({dev_short_addr}): Mining challenge {challenge_id} for DEVELOPER (donation)")
                    else:
                        # Dev address already solved this challenge, mine for user instead
                        mining_address = None
                        self.update_status(address=self.address)
                        self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Dev address already solved {challenge_id}, mining for user instead")
                else:
                    mining_address = None
                    self.update_status(address=self.address)

                if not mining_for_developer:
                    self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Starting work on challenge {challenge_id} (time left: {time_left/3600:.1f}h)")

                # Mine the challenge (or reuse nonce if retrying)
                if self.current_nonce is None:
                    # Use 99% of remaining time, reserving 1% for submission overhead
                    max_mine_time = time_left * 0.99
                    nonce = self.mine_challenge_native(challenge, rom, max_time=max_mine_time, mining_address=mining_address)
                    if nonce:
                        # Store both nonce and challenge data for retry
                        self.current_nonce = nonce
                        self.current_challenge_data = challenge
                else:
                    # Retrying with previously found nonce
                    nonce = self.current_nonce

                if nonce:
                    if mining_for_developer:
                        self.logger.info(f"Worker {self.worker_id} ({dev_short_addr}): Found solution for challenge {challenge_id} (DEVELOPER DONATION), submitting...")
                    else:
                        self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Found solution for challenge {challenge_id}, submitting...")
                    self.update_status(current_challenge='Submitting solution...')
                    success, should_mark_solved, already_exists = self.submit_solution(challenge, nonce, mining_address=mining_address)

                    # Special handling: if mining for dev and solution already exists, wait for next challenge
                    if mining_for_developer and already_exists:
                        self.logger.info(f"Worker {self.worker_id} ({dev_short_addr}): Dev address already solved this challenge, marking as complete and waiting for next challenge...")

                        # Mark dev address as having solved this challenge globally
                        self.challenge_tracker.mark_dev_solved(challenge_id, self.dev_address)
                        # Mark this challenge as solved for this worker so we don't try it again
                        self.challenge_tracker.mark_solved(challenge_id, self.address)

                        self.update_status(current_challenge='Waiting for next challenge')
                        self.current_nonce = None
                        self.current_challenge_data = None
                        self.submission_retry_count = 0
                        self.update_status(address=self.address)

                        # Wait for a new challenge to appear
                        while True:
                            time.sleep(30)
                            api_challenge = self.get_current_challenge()
                            if api_challenge and api_challenge['challenge_id'] != challenge_id:
                                self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): New challenge detected, resuming mining")
                                self.challenge_tracker.register_challenge(api_challenge)
                                break
                        continue

                    if success:
                        # Mark as solved for user wallet
                        self.challenge_tracker.mark_solved(challenge_id, self.address)
                        # If mining for dev, also mark dev address as having solved it
                        if mining_for_developer:
                            self.challenge_tracker.mark_dev_solved(challenge_id, self.dev_address)
                            # Report the developer solution to the server
                            self.report_donation(mining_address)
                        self.update_status(current_challenge='Solution accepted!')
                        self.current_nonce = None
                        self.current_challenge_data = None
                        self.submission_retry_count = 0
                        time.sleep(5)
                    elif should_mark_solved:
                        self.challenge_tracker.mark_solved(challenge_id, self.address)
                        self.update_status(current_challenge='Solution rejected - moving on')
                        self.current_nonce = None
                        self.current_challenge_data = None
                        self.submission_retry_count = 0
                        time.sleep(5)
                    else:
                        # Network error - check retry count
                        self.submission_retry_count += 1
                        if self.submission_retry_count >= 2:
                            # Max retries (2) reached, save to CSV and move on
                            self.logger.warning(f"Worker {self.worker_id} ({self.short_addr}): Max retries (2) reached for challenge {challenge_id}, saving to solutions.csv and moving on")
                            submission_address = mining_address if mining_address else self.address
                            if append_solution_to_csv(submission_address, challenge_id, nonce):
                                with self.failed_solutions_lock:
                                    self.failed_solutions_count.value += 1
                            else:
                                self.logger.error(f"Worker {self.worker_id} ({self.short_addr}): Failed to save solution to CSV")

                            self.challenge_tracker.mark_solved(challenge_id, self.address)
                            self.update_status(current_challenge='Saved to CSV, moving on')
                            self.current_nonce = None
                            self.current_challenge_data = None
                            self.submission_retry_count = 0
                            time.sleep(5)
                        else:
                            # Retry again (will retry on next loop iteration)
                            self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Submission failed, will retry (attempt {self.submission_retry_count + 1}/3)")
                            self.update_status(current_challenge=f'Submission error, retrying...')
                            time.sleep(15)

                    if mining_for_developer:
                        self.update_status(address=self.address)
                else:
                    # No solution found - DON'T mark as solved (that inflates completion count)
                    self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): No solution found for challenge {challenge_id} in mining session")
                    self.update_status(current_challenge='No solution, checking next...')
                    self.current_nonce = None
                    self.current_challenge_data = None
                    self.submission_retry_count = 0

                    if mining_for_developer:
                        self.update_status(address=self.address)

                    time.sleep(5)

            except KeyboardInterrupt:
                self.logger.info(f"Worker {self.worker_id} ({self.short_addr}): Received stop signal")
                break
            except Exception as e:
                self.logger.error(f"Worker {self.worker_id} ({self.short_addr}): Error - {e}")
                self.update_status(current_challenge=f'Error: {str(e)[:30]}')
                time.sleep(60)


def worker_process(wallet_data, worker_id, status_dict, challenges_file, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled=True):
    """Process entry point for worker"""
    try:
        setup_logging()
        challenge_tracker = ChallengeTracker(challenges_file)
        worker = MinerWorker(wallet_data, worker_id, status_dict, challenge_tracker, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled=donation_enabled)
        worker.run()
    except Exception as e:
        logger = logging.getLogger('midnight_miner')
        logger.error(f"Worker {worker_id}: Fatal error - {e}")
        import traceback
        traceback.print_exc()

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"


def color_text(text, color):
    return f"{color}{text}{RESET}"

def display_dashboard(status_dict, num_workers, wallet_manager, challenge_tracker, initial_completed, night_balance_dict, api_base):
    """Display live dashboard - worker-centric view"""
    while True:
        try:
            time.sleep(5)

            # Check if we should update NIGHT balance (once per day after 2am UTC)
            now_utc = datetime.now(timezone.utc)
            last_update_str = night_balance_dict.get('last_update_date')
            current_date = now_utc.date().isoformat()

            # Update if: different date AND current time is after 2am UTC AND we haven't updated today
            if now_utc.hour >= 2 and last_update_str != current_date:
                new_balance = fetch_total_night_balance(wallet_manager, api_base)
                if new_balance is not None:
                    night_balance_dict['balance'] = new_balance
                    night_balance_dict['last_update_date'] = current_date
                    # Save balance snapshot for tracking over time
                    save_balance_snapshot(new_balance)
            # If no balance is set yet, try loading from snapshot
            elif 'balance' not in night_balance_dict or night_balance_dict.get('balance') is None:
                snapshot_balance, _ = load_latest_balance_snapshot()
                if snapshot_balance is not None:
                    night_balance_dict['balance'] = snapshot_balance

            os.system('clear' if os.name == 'posix' else 'cls')

            print("="*110)
            print(f"{BOLD}{CYAN}{f'MIDNIGHT MINER - v{VERSION}':^110}{RESET}")
            print("="*110)
            print(f"{BOLD}Active Workers: {num_workers} | Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
            print("="*110)
            print()

            header = f"{'ID':<4} {'Address':<44} {'Challenge':<25} {'Attempts':<12} {'H/s':<10}"
            print(color_text(header, CYAN))
            print("-"*110)

            total_hashrate = 0

            for worker_id in range(num_workers):
                if worker_id not in status_dict:
                    row = f"{worker_id:<4} {'Starting...':<44} {'N/A':<25} {0:<12} {0:<10}"
                    print(row)
                    continue

                status = status_dict[worker_id]
                address = status.get('address', 'N/A')
                if len(address) > 42:
                    address = address[:39] + "..."

                challenge = status.get('current_challenge')
                if challenge is None:
                    challenge_display = "Waiting"
                elif len(str(challenge)) > 23:
                    challenge_display = str(challenge)[:20] + "..."
                else:
                    challenge_display = str(challenge)

                challenge_display_padded = f"{challenge_display:<25}"

                attempts = status.get('attempts', 0) or 0
                hash_rate = status.get('hash_rate', 0) or 0

                total_hashrate += hash_rate

                print(f"{worker_id:<4} {address:<44} {challenge_display_padded} {attempts:<12,} {hash_rate:<10.0f}")

            # Calculate total challenges from wallet manager
            total_completed = wallet_manager.count_total_challenges(challenge_tracker)
            session_completed = total_completed - initial_completed

            if session_completed > 0:
                completed_str = f"{total_completed} (+{session_completed})"
            else:
                completed_str = str(total_completed)

            print(color_text("-"*110, CYAN))
            print()
            print(color_text(f"{'Total Hash Rate:':<20} {total_hashrate:.0f} H/s", CYAN))
            print(color_text(f"{'Total Completed:':<20} {completed_str}", CYAN))
            balance_display = night_balance_dict.get('balance')
            if balance_display is not None:
                print(color_text(f"{'Total NIGHT*:':<20} {balance_display:.2f}", GREEN))
            else:
                print(color_text(f"{'Total NIGHT*:':<20} Loading...", GREEN))
            print("="*110)
            print("*Night balance updates every 24h")
            print("\nPress Ctrl+C to stop all miners")

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Error displaying dashboard: {e}")
            time.sleep(5)


def get_wallet_statistics(wallet_address, api_base):
    """Fetch statistics for a single wallet"""
    try:
        response = http_get(f"{api_base}/statistics/{wallet_address}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def fetch_total_night_balance(wallet_manager, api_base):
    """Fetch total NIGHT balance across all wallets once at startup. Returns balance or None if fetch failed."""
    total_night = 0.0
    failed = False

    for wallet in wallet_manager.wallets:
        stats = get_wallet_statistics(wallet['address'], api_base)
        if stats:
            local = stats.get('local', {})
            night = local.get('night_allocation', 0) / 1000000.0
            total_night += night
        else:
            failed = True
            break

    if failed:
        logging.warning("Some wallet statistics could not be fetched.")
        return None  # Return None to indicate failure

    return total_night


def main():
    """Main entry point with continuous worker spawning"""
    logger = setup_logging()

    print("="*70)
    print(f"MIDNIGHT MINER - v{VERSION}")
    print("="*70)
    print()

    logger.info("="*70)
    logger.info("Midnight Miner starting up ...")
    logger.info("="*70)

    num_workers = 1
    wallets_file = "wallets.json"
    challenges_file = "challenges.json"
    donation_enabled = True
    wallets_count = None

    for i, arg in enumerate(sys.argv):
        if arg == '--workers' and i + 1 < len(sys.argv):
            num_workers = int(sys.argv[i + 1])
        elif arg == '--wallets-file' and i + 1 < len(sys.argv):
            wallets_file = sys.argv[i + 1]
        elif arg == '--challenges-file' and i + 1 < len(sys.argv):
            challenges_file = sys.argv[i + 1]
        elif arg == '--no-donation':
            donation_enabled = False
        elif arg == '--wallets' and i + 1 < len(sys.argv):
            wallets_count = int(sys.argv[i + 1])

    if num_workers < 1:
        print("Error: --workers must be at least 1")
        return 1

    # If --wallets not specified, default to num_workers
    if wallets_count is None:
        wallets_count = num_workers
    elif wallets_count < 1:
        print("Error: --wallets must be at least 1")
        return 1

    print(f"Configuration:")
    print(f"  Workers: {num_workers}")
    print(f"  Wallets to ensure: {wallets_count}")
    print(f"  Wallets file: {wallets_file}")
    print(f"  Challenges file: {challenges_file}")
    print(f"  Developer donations: {'Enabled (5%)' if donation_enabled else 'Disabled'}")
    print()

    logger.info(f"Configuration: workers={num_workers}, wallets_to_ensure={wallets_count}")

    # Load or fetch developer addresses
    dev_addresses = load_developer_addresses()

    if donation_enabled:
        if len(dev_addresses) < num_workers:
            # Need more addresses
            num_needed = num_workers - len(dev_addresses)
            if dev_addresses:
                print(f"✓ Loaded {len(dev_addresses)} developer addresses from cache")
                print(f"Fetching {num_needed} additional developer addresses...")
            else:
                print(f"Fetching {num_workers} developer addresses...")

            dev_addresses = fetch_developer_addresses(num_workers, dev_addresses)
            if dev_addresses:
                print(f"✓ Now have {len(dev_addresses)} developer addresses")
            else:
                print("⚠ Failed to fetch developer addresses, using fallback pool")
                dev_addresses = FALLBACK_DEVELOPER_POOL
        else:
            print(f"✓ Loaded {len(dev_addresses)} developer addresses from cache")
    else:
        if not dev_addresses:
            dev_addresses = FALLBACK_DEVELOPER_POOL

    wallet_manager = WalletManager(wallets_file)
    api_base = "https://scavenger.prod.gd.midnighttge.io/"

    # Load existing wallets or create enough for specified wallet count
    wallets = wallet_manager.load_or_create_wallets(wallets_count, api_base, donation_enabled)
    logger.info(f"Loaded/created {len(wallets)} wallet(s)")

    # Fetch initial statistics
    print("\nFetching initial statistics...")
    challenge_tracker = ChallengeTracker(challenges_file)

    # Try to load balance from snapshot first (for fast startup)
    snapshot_balance, snapshot_timestamp = load_latest_balance_snapshot()

    # Try to fetch fresh balance
    fresh_balance = fetch_total_night_balance(wallet_manager, api_base)

    if fresh_balance is not None:
        # Fresh balance fetched successfully (even if 0.0)
        initial_night = fresh_balance
        print(f"✓ Initial NIGHT balance: {initial_night:.2f}")
        # Save balance snapshot if it's different from snapshot (or if no snapshot exists)
        if snapshot_balance is None or abs(fresh_balance - snapshot_balance) > 0.01:
            save_balance_snapshot(fresh_balance)
    elif snapshot_balance is not None:
        # Use snapshot as fallback
        initial_night = snapshot_balance
        print(f"✓ Loaded NIGHT balance from snapshot: {initial_night:.2f} (from {snapshot_timestamp})")
        print("  (Failed to fetch fresh balance, using cached snapshot)")
    else:
        # No balance available
        initial_night = 0.0
        print("⚠ Could not load NIGHT balance (no snapshot and fetch failed)")

    initial_completed = wallet_manager.count_total_challenges(challenge_tracker)
    print(f"✓ Initial challenges completed: {initial_completed}")

    print()
    print("="*70)
    print("STARTING MINERS")
    print("="*70)
    print()

    manager = Manager()
    status_dict = manager.dict()
    failed_solutions_count = manager.Value('i', 0)
    failed_solutions_lock = manager.Lock()

    # NIGHT balance tracking with daily updates
    night_balance_dict = manager.dict()
    night_balance_dict['balance'] = initial_night
    night_balance_dict['last_update_date'] = datetime.now(timezone.utc).date().isoformat()

    # Worker tracking: worker_id -> (process, wallet_data)
    workers = {}
    shutdown_event = threading.Event()
    worker_lock = threading.Lock()

    def get_currently_used_wallets():
        """Get set of wallet addresses currently in use by workers"""
        used_addresses = set()
        for worker_id, (process, wallet) in workers.items():
            if process.is_alive():
                used_addresses.add(wallet['address'])
        return used_addresses

    def spawn_worker(worker_id):
        """Spawn a new worker with a unique wallet"""
        with worker_lock:
            # Get wallets currently in use
            used_addresses = get_currently_used_wallets()

            # Try to find a wallet with unsolved challenges that's not currently in use
            wallet = None
            with wallet_manager._lock:
                for w in wallet_manager.wallets:
                    if w['address'] not in used_addresses:
                        unsolved = challenge_tracker.get_unsolved_challenge(w['address'])
                        if unsolved is not None:
                            wallet = w
                            break

            if wallet is None:
                # No available wallet found, create a new one
                logger.info(f"No available wallets for worker {worker_id}, creating new wallet")
                wallet = wallet_manager.create_new_wallet(api_base)
                logger.info(f"Created new wallet {wallet['address'][:20]}... for worker {worker_id}")

            # Assign dev address statically based on worker_id
            dev_address = dev_addresses[worker_id % len(dev_addresses)]

            p = Process(target=worker_process, args=(wallet, worker_id, status_dict, challenges_file, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled))
            p.start()
            workers[worker_id] = (p, wallet)
            logger.info(f"Started worker {worker_id} with wallet {wallet['address'][:20]}...")
            return wallet

    def worker_manager():
        """Monitor and respawn workers as they complete"""
        while not shutdown_event.is_set():
            try:
                time.sleep(10)  # Check every 10 seconds

                # Check each worker
                for worker_id in range(num_workers):
                    if worker_id not in workers:
                        # Worker needs to be started
                        spawn_worker(worker_id)
                    else:
                        process, wallet = workers[worker_id]
                        if not process.is_alive():
                            # Worker has exited, respawn with different wallet
                            logger.info(f"Worker {worker_id} (wallet {wallet['address'][:20]}...) has exited, respawning...")
                            process.join(timeout=1)
                            spawn_worker(worker_id)

            except Exception as e:
                logger.error(f"Error in worker manager: {e}")
                time.sleep(5)

    # Start initial workers
    for i in range(num_workers):
        spawn_worker(i)
        time.sleep(1)

    # Start worker manager thread
    manager_thread = threading.Thread(target=worker_manager, daemon=True)
    manager_thread.start()

    print("\n" + "="*70)
    print("All workers started. Starting dashboard...")
    print("="*70)
    logger.info(f"All {num_workers} workers started successfully")

    try:
        display_dashboard(status_dict, num_workers, wallet_manager, challenge_tracker, initial_completed, night_balance_dict, api_base)
    except KeyboardInterrupt:
        print("\n\nStopping all miners...")
        logger.info("Received shutdown signal, stopping all workers...")

    # Signal shutdown
    shutdown_event.set()

    # Terminate all workers
    for worker_id, (process, wallet) in workers.items():
        process.terminate()

    # Wait for workers to finish
    for worker_id, (process, wallet) in workers.items():
        process.join(timeout=5)

    print("\n✓ All miners stopped")
    logger.info("All workers stopped")

    # Calculate session statistics
    final_completed = wallet_manager.count_total_challenges(challenge_tracker)
    session_total_completed = final_completed - initial_completed

    print(f"\nSession Statistics:")
    print(f"  New challenges solved: {session_total_completed}")

    if failed_solutions_count.value > 0:
        print()
        print(f"[WARNING] Found {failed_solutions_count.value} solution(s) that failed to submit.")
        print("Run 'python resubmit_solutions.py' to try submitting them again.\n")

    logger.info(f"Session statistics: {session_total_completed} new challenges solved")
    logger.info("Midnight Miner shutdown complete")

    return 0


if __name__ == "__main__":
    sys.exit(main())
