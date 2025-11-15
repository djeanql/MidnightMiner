#!/usr/bin/env python3
"""
Consolidate Script - Send NIGHT from all wallets to a single address
                     or undo consolidation with --undo
"""

import requests
import json
import sys
import os
from pycardano import PaymentSigningKey, Address
import cbor2


def load_wallets(wallet_file="wallets.json"):
    """Load wallets from JSON file"""
    if not os.path.exists(wallet_file):
        print(f"Error: {wallet_file} not found")
        return None

    with open(wallet_file, 'r') as f:
        wallets = json.load(f)

    if not wallets:
        print(f"Error: No wallets found in {wallet_file}")
        return None

    return wallets


def create_donation_signature(wallet_data, destination_address):
    """Create CIP 8/30 signature for donation message"""
    try:
        # Construct the message
        message = f"Assign accumulated Scavenger rights to: {destination_address}"

        # Load signing key
        signing_key_bytes = bytes.fromhex(wallet_data['signing_key'])
        signing_key = PaymentSigningKey.from_primitive(signing_key_bytes)

        # Load address
        address = Address.from_primitive(wallet_data['address'])
        address_bytes = bytes(address.to_primitive())

        # Build COSE_Sign1 structure
        protected = {1: -8, "address": address_bytes}
        protected_encoded = cbor2.dumps(protected)
        unprotected = {"hashed": False}
        payload = message.encode('utf-8')

        # Create signature structure
        sig_structure = ["Signature1", protected_encoded, b'', payload]
        to_sign = cbor2.dumps(sig_structure)
        signature_bytes = signing_key.sign(to_sign)

        # Encode as COSE_Sign1
        cose_sign1 = [protected_encoded, unprotected, payload, signature_bytes]
        signature_hex = cbor2.dumps(cose_sign1).hex()

        return signature_hex
    except Exception as e:
        print(f"Error creating signature for {wallet_data['address'][:20]}...: {e}")
        return None


def donate_wallet(destination_address, wallet_data, api_base):
    """Donate a single wallet's earnings to destination address"""
    original_address = wallet_data['address']

    # Create signature
    signature = create_donation_signature(wallet_data, destination_address)
    if not signature:
        return False

    # Make API call
    url = f"{api_base}/donate_to/{destination_address}/{original_address}/{signature}"

    try:
        response = requests.post(url, json={}, timeout=15)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        # Check for unregistered destination address error
        if e.response.status_code == 404:
            try:
                error_json = e.response.json()
                error_msg = error_json.get("message", "")
                if "is not registered" in error_msg or "not accepted Terms and Conditions" in error_msg:
                    print(f"  ✗ Destination address is not registered")
                    print(f"  → Register at: https://sm.midnight.gd")
                    return False
            except:
                pass

        # Check for already donated to this address (409 Conflict)
        if e.response.status_code == 409:
            try:
                error_json = e.response.json()
                error_msg = error_json.get("message", "")
                if "already has an active donation assignment" in error_msg:
                    print(f"  ✓ Already consolidated to this address")
                    return True
            except:
                pass

        error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
        print(f"  ✗ HTTP Error {e.response.status_code}: {error_detail}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Network error: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def undo_wallet(wallet_data, api_base):
    """Undo donation by registering wallet to itself"""
    original_address = wallet_data['address']

    # For undo, destination is the wallet itself
    destination_address = original_address

    # Create signature
    signature = create_donation_signature(wallet_data, destination_address)
    if not signature:
        return False

    # Make API call
    url = f"{api_base}/donate_to/{destination_address}/{original_address}/{signature}"

    try:
        response = requests.post(url, json={}, timeout=15)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        # Treat 404 "No active donation" as success (wallet already not donated)
        if e.response.status_code == 404:
            try:
                error_json = e.response.json()
                if "No active donation assignment found" in error_json.get("message", ""):
                    print(f"  ✓ Already not consolidated (no action needed)")
                    return True
            except:
                pass

        error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
        print(f"  ✗ HTTP Error {e.response.status_code}: {error_detail}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Network error: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Main consolidation script"""
    print("="*70)
    print("MIDNIGHT MINER - WALLET CONSOLIDATION")
    print("="*70)
    print()

    # Parse command line arguments
    wallet_file = "wallets.json"
    destination_address = None
    api_base = "https://scavenger.prod.gd.midnighttge.io"
    undo_mode = False

    for i, arg in enumerate(sys.argv):
        if arg == '--wallets-file' and i + 1 < len(sys.argv):
            wallet_file = sys.argv[i + 1]
        elif arg == '--destination' and i + 1 < len(sys.argv):
            destination_address = sys.argv[i + 1]
        elif arg == '--undo':
            undo_mode = True
        elif arg == '--help' or arg == '-h':
            print("Usage: python consolidate.py [--destination <address> | --undo] [--wallets-file <file>]")
            print()
            print("Options:")
            print("  --destination <address>     Cardano address to receive all earnings")
            print("                              (must be registered at https://sm.midnight.gd)")
            print("  --undo                      Undo donations by registering each wallet to itself")
            print("  --wallets-file <file>       Wallet file to use (default: wallets.json)")
            print()
            return 0

    # Handle undo mode
    if undo_mode:
        print("UNDO MODE: Registering each wallet to itself")
        print(f"Wallet file: {wallet_file}")
        print()

        # Load wallets
        wallets = load_wallets(wallet_file)
        if not wallets:
            return 1

        print(f"Found {len(wallets)} wallet(s)")
        print()

        # Confirm operation
        print("="*70)
        print("This will register each wallet to itself, undoing any donations.")
        print("="*70)
        print()
        confirm = input("Type 'CONFIRM' to proceed: ").strip()
        if confirm != 'CONFIRM':
            print("Aborted")
            return 1

        print()
        print("="*70)
        print("PROCESSING UNDO")
        print("="*70)
        print()

        # Process each wallet
        success_count = 0
        fail_count = 0

        for i, wallet in enumerate(wallets, 1):
            short_addr = wallet['address'][:20] + "..."
            print(f"[{i}/{len(wallets)}] {short_addr}")

            if undo_wallet(wallet, api_base):
                print(f"  ✓ Successfully registered to self")
                success_count += 1
            else:
                print(f"  ✗ Failed to register")
                fail_count += 1
            print()

        # Summary
        print("="*70)
        print("UNDO COMPLETE")
        print("="*70)
        print(f"Successful: {success_count}/{len(wallets)}")
        print(f"Failed: {fail_count}/{len(wallets)}")
        print()

        if fail_count > 0:
            print("Some undo operations failed. You can run this script again to retry.")

        return 0

    # Normal donation mode
    # Get destination address if not provided
    if not destination_address:
        print("Enter destination address (MUST be registered, use the scavenger hunt portal):")
        destination_address = input("> ").strip()
        if not destination_address:
            print("Error: Destination address is required")
            return 1

    # Validate destination address format
    if not destination_address.startswith("addr1"):
        print(f"Warning: Address doesn't start with 'addr1' - may be invalid")
        confirm = input("Continue anyway? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Aborted")
            return 1

    print()
    print(f"Destination address: {destination_address}")
    print(f"Wallet file: {wallet_file}")
    print()

    # Load wallets
    wallets = load_wallets(wallet_file)
    if not wallets:
        return 1

    print(f"Found {len(wallets)} wallet(s)")
    print()

    # Confirm operation
    print("="*70)
    print("WARNING: This will donate ALL earnings from ALL wallets to the")
    print("         destination address.")
    print()
    print("NOTE: The destination address MUST be registered at:")
    print("      https://sm.midnight.gd")
    print("="*70)
    print()
    confirm = input("Type 'CONFIRM' to proceed: ").strip()
    if confirm != 'CONFIRM':
        print("Aborted")
        return 1

    print()
    print("="*70)
    print("PROCESSING DONATIONS")
    print("="*70)
    print()

    # Process each wallet
    success_count = 0
    fail_count = 0

    for i, wallet in enumerate(wallets, 1):
        short_addr = wallet['address'][:20] + "..."
        print(f"[{i}/{len(wallets)}] {short_addr}")

        if donate_wallet(destination_address, wallet, api_base):
            print(f"  ✓ Successfully consolidated")
            success_count += 1
        else:
            print(f"  ✗ Failed to consolidate")
            fail_count += 1
        print()

    # Summary
    print("="*70)
    print("CONSOLIDATION COMPLETE")
    print("="*70)
    print(f"Successful: {success_count}/{len(wallets)}")
    print(f"Failed: {fail_count}/{len(wallets)}")
    print()

    if fail_count > 0:
        print("Some donations failed. You can run this script again to retry.")
        print()
        print("If you received 'not registered' errors, make sure your")
        print("destination address is registered at: https://sm.midnight.gd")
    else:
        print(f"All NIGHT rewards from currently active wallets will be redeemable from: {destination_address}.")
        print("Run this script again at the end of the scavenger hunt to consolidate any newly generated wallets.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
