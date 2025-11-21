"""Configuration and constants for Midnight Miner"""
import sys

VERSION = "0.3.2"

API_BASE = "https://scavenger.prod.gd.midnighttge.io"

DONATION_RATE = 0.05  # 5%

FALLBACK_DEVELOPER_WALLETS = [
    "addr1v8sd2hwjvumewp3t4rtqz5uwejjv504tus5w279m5k6wkccm0j9gp",
    "addr1vyel9hlqeft4lwl5shgd28ryes3ejluug0lxhhusnvh2dyc0q92kw",
    "addr1vxl62mccauqktxyg59ehaskjk75na0pd4utrkvkv822ygsqqt28ph",
    "addr1vxenv7ucst58q9ju52mw9kjudlwelxnf53kd362jgq8qm5q68uh58",
    "addr1v8hf3d0tgnfn8zp2sgq2gdj9jy4dg6wyzd6uchlvq8n0pnsxp8232",
    "addr1v8vem45scpapkca8dpgcgdn2wfkg9jva950v8jjh47vrs3qf8sm6z",
    "addr1vyuyd9xxpex2ruzvejeduzknfcn2szyq46qfquxh6n4268qukppmq",
    "addr1vyrywe247atz5jzu9rspdf7lhvmhd550x45ck7qac295h9s3rs6zd",
    "addr1v86agy7h3mmphdpyru8tgrjjcpvuuqk8863jspqfd6n60lcxv0xmf",
    "addr1vx5dee9pqnq0r2aypl2ywueqjuvwg0s7dsc7eneyyr3d83g3a08c0",
    "addr1vx6wfs6z0vrwjutchfhmzk7tazsa09a9ptt8st00nmzshls2npktm",
    "addr1vx38ypke98t70r4rmkqdtm9c9eqdvjg8ytjc570javaqljcsp0q5h",
    "addr1v8mduamz9a7hghklsuug8szrhm4a0g5j8vxt7zsk2aetw9g8u2ak6",
    "addr1v99tha5x72jdh58rxp3c8amarac6ahf693xwwx4q9hpnnsqcv4nrd"
]


def parse_arguments():
    """Parse command-line arguments and return configuration"""
    num_workers = 1
    wallets_file = "wallets.json"
    challenges_file = "challenges.json"
    donation_enabled = True
    wallets_count = None
    log_api_requests = False
    use_defensio_api = False
    consolidate_address = None

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
        elif arg == '--log-api-requests':
            log_api_requests = True
        elif arg == '--defensio':
            use_defensio_api = True
        elif arg == '--consolidate' and i + 1 < len(sys.argv):
            consolidate_address = sys.argv[i + 1]

    if num_workers < 1:
        print("Error: --workers must be at least 1")
        sys.exit(1)

    # If --wallets not specified, default to num_workers
    if wallets_count is None:
        wallets_count = num_workers
    elif wallets_count < 1:
        print("Error: --wallets must be at least 1")
        sys.exit(1)

    return {
        'num_workers': num_workers,
        'wallets_file': wallets_file,
        'challenges_file': challenges_file,
        'donation_enabled': donation_enabled,
        'wallets_count': wallets_count,
        'log_api_requests': log_api_requests,
        'use_defensio_api': use_defensio_api,
        'consolidate_address': consolidate_address
    }
