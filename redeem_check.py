#!/usr/bin/env python3
"""
Redeem Check Script - Check token allocation via new API
                         and filter invalid addresses
"""

import requests
import json
import sys
import os
import shutil
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

try:
    from proxy_config import create_proxy_session, load_proxy_config
except ImportError:
    print("⚠ proxy_config.py not found, proxies will not be used")
    create_proxy_session = None
    load_proxy_config = None


def create_backup(wallet_file: str) -> str:
    """Creates backup of wallets.json file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{wallet_file}.backup_{timestamp}"
    
    try:
        shutil.copy2(wallet_file, backup_file)
        print(f"✓ Backup created: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"✗ Error creating backup: {e}")
        return None


def load_wallets(wallet_file: str = "wallets.json") -> Optional[List[Dict]]:
    """Loads wallets from JSON file"""
    if not os.path.exists(wallet_file):
        print(f"Error: {wallet_file} not found")
        return None

    with open(wallet_file, 'r', encoding='utf-8') as f:
        wallets = json.load(f)

    if not wallets:
        print(f"Error: No wallets found in {wallet_file}")
        return None

    return wallets


def get_api_headers() -> Dict[str, str]:
    """Returns headers for API requests"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Priority": "u=1, i",
        "sec-ch-ua": '"Brave";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "sec-gpc": "1",
        "Referer": "https://redeem.midnight.gd/",
        "Origin": "https://redeem.midnight.gd",
    }


def check_api_status(api_base: str, session: Union[requests.Session, None] = None) -> bool:
    """Checks API availability via /status"""
    if session is None:
        session = requests.Session()
    
    try:
        url = f"{api_base}/status"
        headers = get_api_headers()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        print(f"⚠ Warning: HTTP {e.response.status_code} when checking API status")
        if e.response.status_code == 403:
            print("  → Proxies or other headers may be required")
        try:
            print(f"  Response: {e.response.text[:200]}")
        except:
            pass
        return False
    except Exception as e:
        print(f"⚠ Warning: Failed to check API status: {e}")
        return False


def check_redeem_allocation(address: str, api_base: str, session: Union[requests.Session, None] = None, verbose: bool = False, retry_count: int = 2) -> Tuple[bool, Optional[float], Optional[Dict]]:
    """
    Checks token allocation for address via /thaws/{address}/schedule
    
    Returns:
        (is_valid, token_amount, response_data)
    """
    if session is None:
        session = requests.Session()
    
    url = f"{api_base}/thaws/{address}/schedule"
    headers = get_api_headers()
    
    # Retry attempts on 403 error
    for attempt in range(retry_count + 1):
        try:
            response = session.get(url, headers=headers, timeout=15, allow_redirects=True)
            
            # If 404 - address has no allocation
            if response.status_code == 404:
                return False, 0.0, None
            
            # If 403 - access error, retry with delay
            if response.status_code == 403:
                if attempt < retry_count:
                    if verbose:
                        print(f"    ⚠ 403 Forbidden, attempt {attempt + 1}/{retry_count + 1}, retry in 1 sec...")
                    time.sleep(1)
                    continue
                else:
                    if verbose:
                        print(f"    ✗ 403 Forbidden after {retry_count + 1} attempts. Response: {response.text[:300]}")
                    return False, 0.0, None
            
            # Check that response is JSON
            try:
                data = response.json()
            except json.JSONDecodeError:
                if verbose:
                    print(f"    ✗ Response is not JSON. Status: {response.status_code}")
                    print(f"    Content: {response.text[:300]}")
                return False, 0.0, None
            
            # If 400 error with type no_redeemable_thaws - address has no allocation
            if response.status_code == 400:
                if isinstance(data, dict) and data.get('type') == 'no_redeemable_thaws':
                    return False, 0.0, None
                # Other 400 errors - retry
                if attempt < retry_count:
                    if verbose:
                        print(f"    ⚠ HTTP 400, attempt {attempt + 1}/{retry_count + 1}, retry in 1 sec...")
                    time.sleep(1)
                    continue
                else:
                    return False, 0.0, None
            
            # Check other errors
            if response.status_code != 200:
                response.raise_for_status()
            
            if verbose:
                print(f"    API Response: {json.dumps(data, indent=2, ensure_ascii=False)[:300]}...")
            
            # Parse allocation data
            # Response format: {"numberOfClaimedAllocations": 0, "thaws": [{"amount": 48638662, ...}, ...]}
            token_amount = 0.0
            
            if isinstance(data, dict):
                # Sum all amounts from thaws array
                if 'thaws' in data and isinstance(data['thaws'], list):
                    for thaw in data['thaws']:
                        if isinstance(thaw, dict) and 'amount' in thaw:
                            amount_value = thaw['amount']
                            if isinstance(amount_value, (int, float)):
                                token_amount += float(amount_value) / 1_000_000.0  # Convert from lovelace
                            elif isinstance(amount_value, str):
                                try:
                                    token_amount += float(amount_value) / 1_000_000.0
                                except ValueError:
                                    pass
            
            # Address is valid if there is data (even if tokens are 0, but response is not 404)
            is_valid = response.status_code == 200
            
            return is_valid, token_amount, data
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return False, 0.0, None
            
            # Handle 400 error with type no_redeemable_thaws
            if e.response.status_code == 400:
                try:
                    error_data = e.response.json()
                    if isinstance(error_data, dict) and error_data.get('type') == 'no_redeemable_thaws':
                        return False, 0.0, None
                except:
                    pass
            
            if e.response.status_code == 403:
                if attempt < retry_count:
                    if verbose:
                        print(f"    ⚠ HTTP 403, attempt {attempt + 1}/{retry_count + 1}, retry in 1 sec...")
                    time.sleep(1)
                    continue
                else:
                    if verbose:
                        try:
                            error_text = e.response.text[:200]
                            print(f"  ✗ HTTP 403 Forbidden for {address[:20]}... after {retry_count + 1} attempts")
                            print(f"    Response: {error_text}")
                        except:
                            print(f"  ✗ HTTP 403 Forbidden for {address[:20]}... after {retry_count + 1} attempts")
                    else:
                        print(f"  ✗ HTTP 403 Forbidden for {address[:20]}...")
                    return False, 0.0, None
            
            # For other errors, retry
            if attempt < retry_count:
                if verbose:
                    print(f"    ⚠ HTTP {e.response.status_code}, attempt {attempt + 1}/{retry_count + 1}, retry in 1 sec...")
                time.sleep(1)
                continue
            
            print(f"  ✗ HTTP error {e.response.status_code} for {address[:20]}...")
            if verbose:
                try:
                    print(f"    Response: {e.response.text[:200]}")
                except:
                    pass
            return False, 0.0, None
        except requests.exceptions.RequestException as e:
            if attempt < retry_count:
                if verbose:
                    print(f"    ⚠ Network error, attempt {attempt + 1}/{retry_count + 1}, retry in 1 sec...")
                time.sleep(1)
                continue
            print(f"  ✗ Network error for {address[:20]}...: {e}")
            return False, 0.0, None
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parsing error for {address[:20]}...: {e}")
            return False, 0.0, None
        except Exception as e:
            print(f"  ✗ Unexpected error for {address[:20]}...: {e}")
            return False, 0.0, None
    
    # If all attempts exhausted
    return False, 0.0, None


def create_sessions(proxy_config_path: str, desired_workers: int) -> List[Tuple[requests.Session, str]]:
    """Creates multiple sessions with proxies for parallel processing"""
    if not load_proxy_config:
        # If no proxy_config, create direct sessions
        sessions = []
        for idx in range(desired_workers):
            session = requests.Session()
            session.trust_env = False
            sessions.append((session, f"direct#{idx + 1}"))
        return sessions
    
    proxies = load_proxy_config(proxy_config_path)
    sessions: List[Tuple[requests.Session, str]] = []
    
    if proxies:
        for entry in proxies[:desired_workers]:
            session = requests.Session()
            session.trust_env = False
            session.proxies.update(entry["proxies"])
            if entry["auth_header"]:
                session.headers["Proxy-Authorization"] = entry["auth_header"]
            display = entry["display"]
            sessions.append((session, display))
    else:
        for idx in range(desired_workers):
            session = requests.Session()
            session.trust_env = False
            sessions.append((session, f"direct#{idx + 1}"))
    
    return sessions


def process_wallet_chunk(session: requests.Session, label: str, wallets_chunk: List[Dict], 
                         api_base: str, verbose: bool, delay: float) -> List[Tuple[Dict, bool, float, Optional[Dict]]]:
    """
    Processes a chunk of wallets in one thread
    
    Returns:
        List of (wallet, is_valid, token_amount, response_data)
    """
    results = []
    for i, wallet in enumerate(wallets_chunk):
        address = wallet['address']
        
        # Small delay between requests in thread
        if i > 0 and delay > 0:
            time.sleep(delay)
        
        is_valid, token_amount, response_data = check_redeem_allocation(
            address, api_base, session, verbose
        )
        results.append((wallet, is_valid, token_amount, response_data))
    
    return results


def save_wallets(wallets: List[Dict], wallet_file: str) -> bool:
    """Saves wallets to JSON file"""
    try:
        with open(wallet_file, 'w', encoding='utf-8') as f:
            json.dump(wallets, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"✗ Error saving {wallet_file}: {e}")
        return False


def main():
    """Main script function"""
    print("="*70)
    print("MIDNIGHT MINER - REDEEM CHECK")
    print("Token allocation check and invalid address filtering")
    print("="*70)
    print()
    
    # Parameters
    wallet_file = "wallets.json"
    api_base = "https://mainnet.prod.gd.midnighttge.io"
    proxy_config = "proxy.json"
    verbose = False
    report_file = None
    use_proxy = True
    delay_between_requests = 0.5
    auto_remove = False
    threads_count = 10
    
    # Parse command line arguments
    for i, arg in enumerate(sys.argv):
        if arg == '--wallets-file' and i + 1 < len(sys.argv):
            wallet_file = sys.argv[i + 1]
        elif arg == '--api-base' and i + 1 < len(sys.argv):
            api_base = sys.argv[i + 1]
        elif arg == '--proxy-config' and i + 1 < len(sys.argv):
            proxy_config = sys.argv[i + 1]
        elif arg == '--no-proxy':
            use_proxy = False
        elif arg == '--verbose' or arg == '-v':
            verbose = True
        elif arg == '--report' and i + 1 < len(sys.argv):
            report_file = sys.argv[i + 1]
        elif arg == '--delay' and i + 1 < len(sys.argv):
            try:
                delay_between_requests = float(sys.argv[i + 1])
            except ValueError:
                print(f"Error: --delay must be a number")
                return 1
        elif arg == '--auto-remove':
            auto_remove = True
        elif arg == '--threads' and i + 1 < len(sys.argv):
            try:
                threads_count = int(sys.argv[i + 1])
                if threads_count < 1:
                    print("Error: --threads must be >= 1")
                    return 1
            except ValueError:
                print(f"Error: --threads must be a number")
                return 1
        elif arg == '--help' or arg == '-h':
            print("Usage: python redeem_check.py [options]")
            print()
            print("Options:")
            print("  --wallets-file <file>   Wallet file (default: wallets.json)")
            print("  --api-base <url>        API base URL (default: https://mainnet.prod.gd.midnighttge.io)")
            print("  --proxy-config <file>  Proxy configuration file (default: proxy.json)")
            print("  --no-proxy              Don't use proxies")
            print("  --verbose, -v           Verbose API response output")
            print("  --report <file>         Save report to file (JSON)")
            print("  --delay <seconds>       Delay between requests (default: 0.5)")
            print("  --threads <count>       Number of threads for parallel processing (default: 10)")
            print("  --auto-remove           Automatically remove invalid addresses without confirmation")
            print()
            return 0
    
    # Create sessions with proxies for multithreading
    print(f"Setting up {threads_count} threads...")
    if use_proxy:
        try:
            sessions = create_sessions(proxy_config, threads_count)
            if sessions:
                proxy_count = len([s for s in sessions if not s[1].startswith("direct")])
                if proxy_count > 0:
                    print(f"✓ Created {len(sessions)} sessions ({proxy_count} with proxies)")
                else:
                    print(f"✓ Created {len(sessions)} direct sessions (without proxies)")
            else:
                print("⚠ Failed to create sessions, using one session")
                sessions = [(requests.Session(), "direct")]
        except Exception as e:
            print(f"⚠ Error setting up proxies: {e}")
            print("  Using one direct session")
            sessions = [(requests.Session(), "direct")]
    else:
        sessions = [(requests.Session(), "direct")]
    
    # Check API status (using first session)
    print("Checking API availability...")
    if check_api_status(api_base, sessions[0][0]):
        print("✓ API is available")
    else:
        print("⚠ API may be unavailable, continuing...")
    print()
    
    # Load wallets
    print(f"Loading wallets from {wallet_file}...")
    wallets = load_wallets(wallet_file)
    if not wallets:
        return 1
    
    print(f"✓ Loaded {len(wallets)} wallets")
    print()
    
    # Create backup
    print("Creating backup...")
    backup_file = create_backup(wallet_file)
    if not backup_file:
        print("⚠ Continuing without backup...")
    print()
    
    # Check allocation for each address (multithreaded processing)
    print("="*70)
    print("ALLOCATION CHECK")
    print(f"Using {len(sessions)} threads")
    print("="*70)
    print()
    
    valid_wallets = []
    invalid_addresses = []
    total_tokens = 0.0
    wallet_stats = []
    
    # Split wallets into chunks for each thread
    chunks: List[Tuple[requests.Session, str, List[Dict]]] = []
    session_count = len(sessions)
    for index, (session, label) in enumerate(sessions):
        assigned = wallets[index::session_count]
        if assigned:
            chunks.append((session, label, assigned))
    
    # Progress counter
    processed_count = 0
    total_count = len(wallets)
    progress_lock = Lock()
    
    def update_progress(wallet, is_valid, token_amount):
        nonlocal processed_count, total_tokens
        with progress_lock:
            processed_count += 1
            address = wallet['address']
            short_addr = address[:20] + "..."
            
            print(f"[{processed_count}/{total_count}] {short_addr}")
            
            if is_valid:
                valid_wallets.append(wallet)
                total_tokens += token_amount
                wallet_stats.append({
                    'address': address,
                    'tokens': token_amount,
                    'valid': True
                })
                print(f"  ✓ Valid address, tokens: {token_amount:.6f} NIGHT")
            else:
                invalid_addresses.append(address)
                wallet_stats.append({
                    'address': address,
                    'tokens': 0.0,
                    'valid': False
                })
                print(f"  ✗ Invalid address (no allocation)")
            print()
    
    # Start parallel processing
    with ThreadPoolExecutor(max_workers=len(chunks) or 1) as executor:
        futures = [
            executor.submit(process_wallet_chunk, session, label, chunk, api_base, verbose, delay_between_requests)
            for session, label, chunk in chunks
        ]
        
        for future in as_completed(futures):
            try:
                chunk_results = future.result()
                for wallet, is_valid, token_amount, response_data in chunk_results:
                    update_progress(wallet, is_valid, token_amount)
            except Exception as e:
                print(f"✗ Error processing chunk: {e}")
    
    # Report
    print("="*70)
    print("REPORT")
    print("="*70)
    print()
    print(f"Total wallets: {len(wallets)}")
    print(f"Valid addresses: {len(valid_wallets)}")
    print(f"Invalid addresses: {len(invalid_addresses)}")
    print()
    print("="*70)
    print(f"TOTAL (total allocation for claim): {total_tokens:.6f} NIGHT")
    print("="*70)
    print()
    
    # Detailed token statistics
    if wallet_stats:
        print("Detailed statistics:")
        print("-" * 70)
        valid_with_tokens = [w for w in wallet_stats if w['valid'] and w['tokens'] > 0]
        valid_without_tokens = [w for w in wallet_stats if w['valid'] and w['tokens'] == 0]
        
        if valid_with_tokens:
            print(f"\nAddresses with tokens ({len(valid_with_tokens)}):")
            for w in sorted(valid_with_tokens, key=lambda x: x['tokens'], reverse=True):
                print(f"  {w['address'][:20]}... : {w['tokens']:.6f} NIGHT")
        
        if valid_without_tokens:
            print(f"\nValid addresses without tokens ({len(valid_without_tokens)}):")
            for w in valid_without_tokens[:10]:  # Show first 10
                print(f"  {w['address'][:20]}...")
            if len(valid_without_tokens) > 10:
                print(f"  ... and {len(valid_without_tokens) - 10} more addresses")
        
        if invalid_addresses:
            print(f"\nInvalid addresses ({len(invalid_addresses)}):")
            for addr in invalid_addresses[:10]:  # Show first 10
                print(f"  {addr[:20]}...")
            if len(invalid_addresses) > 10:
                print(f"  ... and {len(invalid_addresses) - 10} more addresses")
    
    print()
    print("="*70)
    
    # Save report to file
    if report_file:
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'total_wallets': len(wallets),
            'valid_wallets': len(valid_wallets),
            'invalid_wallets': len(invalid_addresses),
            'total_tokens': total_tokens,
            'total_allocation_night': total_tokens,
            'wallet_stats': wallet_stats,
            'invalid_addresses': invalid_addresses
        }
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            print(f"✓ Report saved to {report_file}")
        except Exception as e:
            print(f"✗ Error saving report: {e}")
        print()
    
    # Save filtered wallets
    if invalid_addresses:
        print()
        print(f"Found {len(invalid_addresses)} invalid addresses (empty wallets).")
        
        if auto_remove:
            # Automatic removal without confirmation
            if save_wallets(valid_wallets, wallet_file):
                print(f"✓ Automatically removed {len(invalid_addresses)} invalid addresses")
                print(f"✓ Saved {len(valid_wallets)} valid wallets to {wallet_file}")
                if backup_file:
                    print(f"  Backup saved to: {backup_file}")
            else:
                print("✗ Error saving")
                return 1
        else:
            # With confirmation
            print("Remove them from wallets.json? (yes/no): ", end='')
            confirm = input().strip().lower()
            
            if confirm in ['yes', 'y']:
                if save_wallets(valid_wallets, wallet_file):
                    print(f"✓ Saved {len(valid_wallets)} valid wallets to {wallet_file}")
                    print(f"✓ Removed {len(invalid_addresses)} invalid addresses")
                    if backup_file:
                        print(f"  Backup saved to: {backup_file}")
                else:
                    print("✗ Error saving")
                    return 1
            else:
                print("Addresses not removed. Original file saved.")
                if backup_file:
                    print(f"  Backup: {backup_file}")
    else:
        print()
        print("✓ All addresses are valid!")
    
    # Close all sessions
    for session, _ in sessions:
        try:
            if hasattr(session, 'close'):
                session.close()
        except:
            pass
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

