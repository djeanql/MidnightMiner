"""Display and UI for Midnight Miner"""
import os
import time
import logging
from datetime import datetime, timezone

from .config import VERSION
from .statistics import fetch_total_night_balance
from .file_utils import load_latest_balance_snapshot, save_balance_snapshot

# Terminal colors
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"


def color_text(text, color):
    return f"{color}{text}{RESET}"


def display_dashboard(status_dict, num_workers, wallet_manager, challenge_tracker, initial_completed, night_balance_dict, api_base, start_time):
    """Display live dashboard - worker-centric view"""
    while True:
        try:
            time.sleep(5)

            # Calculate uptime
            uptime_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
            uptime_hours = int(uptime_seconds // 3600)
            uptime_minutes = int((uptime_seconds % 3600) // 60)
            uptime_secs = int(uptime_seconds % 60)
            uptime_str = f"{uptime_hours}h {uptime_minutes}m {uptime_secs}s"

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
            print(f"{BOLD}Active Workers: {num_workers} | Uptime: {uptime_str} | Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
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
