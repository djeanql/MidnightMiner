import sys
import time
import threading
import logging
from datetime import datetime, timezone
from multiprocessing import Process, Manager

from miner.config import VERSION, API_BASE, FALLBACK_DEVELOPER_WALLETS, parse_arguments
from miner.logging_config import setup_logging
from miner import api_client
from miner.api_client import load_developer_addresses, fetch_developer_addresses
from miner.file_utils import load_latest_balance_snapshot, save_balance_snapshot
from miner.wallet_manager import WalletManager
from miner.challenge_tracker import ChallengeTracker
from miner.statistics import fetch_total_night_balance
from miner.dashboard import display_dashboard
from miner.worker_process import worker_process

def display_consolidation_warning(token_name="NIGHT"):
    print()
    print("="*70)
    print("⚠ IMPORTANT: Wallet Consolidation Recommended ⚠")
    print("="*70)
    print("This miner uses multiple wallets to mine efficiently.")
    print(f"To avoid transaction fees you need to consolidate your {token_name}")
    print("into a single wallet (if you have not already done so).")
    print("Check the README for instructions.")
    print()

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

    # Parse command-line arguments
    config = parse_arguments()
    num_workers = config['num_workers']
    wallets_file = config['wallets_file']
    challenges_file = config['challenges_file']
    donation_enabled = config['donation_enabled']
    wallets_count = config['wallets_count']
    log_api_requests = config['log_api_requests']
    use_defensio_api = config['use_defensio_api']
    consolidate_address = config['consolidate_address']

    # Enable API request logging if flag is set
    if log_api_requests:
        api_client.LOG_API_REQUESTS = True

    print(f"Configuration:")
    print(f"  Workers: {num_workers}")
    print(f"  Wallets to ensure: {wallets_count}")
    print(f"  Wallets file: {wallets_file}")
    print(f"  Challenges file: {challenges_file}")
    print(f"  Developer donations: {'Enabled (5%)' if donation_enabled else 'Disabled'}")
    if consolidate_address:
        print(f"  Consolidate to: {consolidate_address}")
    if log_api_requests:
        print(f"  API request logging: Enabled")
    if use_defensio_api:
        print(f"  API Base: https://mine.defensio.io/api (Defensio)")
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
                dev_addresses = FALLBACK_DEVELOPER_WALLETS
        else:
            print(f"✓ Loaded {len(dev_addresses)} developer addresses from cache")
    else:
        if not dev_addresses:
            dev_addresses = FALLBACK_DEVELOPER_WALLETS

    wallet_manager = WalletManager(wallets_file, use_defensio_api, consolidate_address)
    api_base = API_BASE

    if use_defensio_api:
        api_base = "https://mine.defensio.io/api"
        api_client.API_BASE = api_base

    # Load existing wallets or create enough for specified wallet count
    wallets = wallet_manager.load_or_create_wallets(wallets_count, api_base, donation_enabled)
    logger.info(f"Loaded/created {len(wallets)} wallet(s)")

    # Determine token name based on API
    token_name = "DFO" if use_defensio_api else "NIGHT"

    # Fetch initial statistics
    print("\nFetching initial statistics...")
    challenge_tracker = ChallengeTracker(challenges_file)

    # Try to load balance from snapshot first (for fast startup)
    snapshot_balance, snapshot_timestamp = load_latest_balance_snapshot()

    # Try to fetch fresh balance
    fresh_balance = fetch_total_night_balance(wallet_manager, api_base, use_defensio_api)

    if fresh_balance is not None:
        # Fresh balance fetched successfully (even if 0.0)
        initial_night = fresh_balance
        print(f"✓ Initial {token_name} balance: {initial_night:.2f}")
        # Save balance snapshot if it's different from snapshot (or if no snapshot exists)
        if snapshot_balance is None or abs(fresh_balance - snapshot_balance) > 0.01:
            save_balance_snapshot(fresh_balance)
    elif snapshot_balance is not None:
        # Use snapshot as fallback
        initial_night = snapshot_balance
        print(f"✓ Loaded {token_name} balance from snapshot: {initial_night:.2f} (from {snapshot_timestamp})")
        print("  (Failed to fetch fresh balance, using cached snapshot)")
    else:
        # No balance available
        initial_night = 0.0
        print(f"⚠ Could not load {token_name} balance (no snapshot and fetch failed)")

    initial_completed = wallet_manager.count_total_challenges(challenge_tracker)
    print(f"✓ Initial challenges completed: {initial_completed}")

    # Verify we can fetch challenges from API before starting workers
    print("\nVerifying API connectivity...")
    test_challenge = api_client.get_current_challenge(api_base)
    if test_challenge is None:
        print()
        print("="*70)
        print("ERROR: Cannot retrieve current challenge from API")
        print("="*70)
        print(f"API Base: {api_base}")
        print("\nThe API may be down or unreachable.")
        print("Please check your internet connection and try again later.")
        print("="*70)
        logger.error("Failed to retrieve current challenge on startup - API unavailable")
        return 1

    print(f"✓ API connectivity verified (challenge: {test_challenge['challenge_id'][:20]}...)")

    print()
    print("="*70)
    print("STARTING MINERS")
    print("="*70)
    print()

    # Track start time for uptime display
    start_time = datetime.now(timezone.utc)

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
                # No available wallet found - check if API is accessible before creating new wallet
                # This prevents infinite wallet creation when API is down
                api_challenge = api_client.get_current_challenge(api_base)
                if api_challenge is None:
                    logger.warning(f"Worker {worker_id}: Cannot spawn - API unreachable and no available wallets with unsolved challenges")
                    return None

                # API is accessible, safe to create a new wallet
                logger.info(f"No available wallets for worker {worker_id}, creating new wallet")
                wallet = wallet_manager.create_new_wallet(api_base)
                logger.info(f"Created new wallet {wallet['address'][:20]}... for worker {worker_id}")

            # Assign dev address statically based on worker_id
            dev_address = dev_addresses[worker_id % len(dev_addresses)]

            p = Process(target=worker_process, args=(wallet, worker_id, status_dict, challenges_file, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled, api_base))
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
        display_dashboard(status_dict, num_workers, wallet_manager, challenge_tracker, initial_completed, night_balance_dict, api_base, start_time, use_defensio_api)
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

    # Calculate uptime
    end_time = datetime.now(timezone.utc)
    uptime_seconds = (end_time - start_time).total_seconds()
    uptime_hours = int(uptime_seconds // 3600)
    uptime_minutes = int((uptime_seconds % 3600) // 60)
    uptime_secs = int(uptime_seconds % 60)

    print(f"\nSession Statistics:")
    print(f"  Uptime: {uptime_hours}h {uptime_minutes}m {uptime_secs}s")
    print(f"  New challenges solved: {session_total_completed}")

    if failed_solutions_count.value > 0:
        print()
        print(f"[WARNING] Found {failed_solutions_count.value} solution(s) that failed to submit.")
        print("Run 'python resubmit_solutions.py' to try submitting them again.\n")

    logger.info(f"Session statistics: {session_total_completed} new challenges solved")
    logger.info("Midnight Miner shutdown complete\n\n")

    display_consolidation_warning(token_name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
