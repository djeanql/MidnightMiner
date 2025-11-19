"""Wallet operations for Midnight Miner"""
import os
import json
import sys
import time
import threading
import logging
from datetime import datetime, timezone
import requests
from pycardano import PaymentSigningKey, PaymentVerificationKey, Address, Network
import cbor2

from .api_client import http_get, http_post, get_terms_and_conditions
from .file_utils import backup_wallets_file


class WalletManager:
    """Manages Cardano wallet generation, storage, and signing"""

    def __init__(self, wallet_file="wallets.json", use_defensio_api=False):
        self.wallet_file = wallet_file
        self.wallets = []
        self._lock = threading.Lock()
        self.use_defensio_api = use_defensio_api

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
        message = get_terms_and_conditions(api_base, self.use_defensio_api)

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
