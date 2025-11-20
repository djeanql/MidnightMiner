"""Worker process entry point for Midnight Miner"""
import logging
import traceback

from .logging_config import setup_logging
from .challenge_tracker import ChallengeTracker
from .worker import MinerWorker


def worker_process(wallet_data, worker_id, status_dict, challenges_file, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled=True, api_base="https://scavenger.prod.gd.midnighttge.io"):
    """Process entry point for worker"""
    try:
        setup_logging()
        challenge_tracker = ChallengeTracker(challenges_file)
        worker = MinerWorker(wallet_data, worker_id, status_dict, challenge_tracker, dev_address, failed_solutions_count, failed_solutions_lock, donation_enabled=donation_enabled, api_base=api_base)
        worker.run()
    except Exception as e:
        logger = logging.getLogger('midnight_miner')
        logger.error(f"Worker {worker_id}: Fatal error - {e}")
        traceback.print_exc()
