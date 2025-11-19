
# Thank You for using Midnight Miner

With the Midnight scavenger hunt now closed, I want to thank everyone who reported issues, made pull requests, and donated their NIGHT. Without your support, this would not have been possible!

**Important:** Make sure you have consolidated your rewards with the consolidation script! Soon, the claim portal will be up and you will be able to claim NIGHT with the address you consolidated to.

## Defensio Scavenger Hunt

[Defensio](https://defensio.io/), a DEX building on Midnight, is using a scavenger hunt to distribute their token. The API is compatible with the Midnight scavenger hunt API, so you can use this miner for it.

**To mine DFO:** Run `python miner.py --defensio ....`

**Important:** You MUST use a fresh directory for Defensio mining. If you previously mined for Midnight, either re-download this repository to a new location or delete your existing `challenges.json`, `developer-addresses.json` and `wallets.json` files.

Additionally, you must consolidate to a DIFFERENT address to where you consolidated your NIGHT.

**Disclaimer:** MidnightMiner is NOT AFFILIATED with the Defensio project. Engage at your own risk. The tokens may be worth nothing.

---
<br><br>



# Midnight Miner

A Python-based mining bot for the Midnight Network's scavenger hunt, allowing users to automatically mine for NIGHT tokens with multiple wallets.

**Supported Platforms:** Windows (x64), Linux (x64, ARM64), macOS (Intel, Apple Silicon)

If you are unfamiliar with python, and/or using windows, check out the [Easy Guide](EasyGuide.md).

## Disclaimer

This is an unofficial tool, and has not been properly tested. Use it at your own risk.

I will be updating and improving this software regularly. Please keep up to date by re-downloading from this repository and copying over your `wallets.json` and `challenges.json` files, or simply by running `git pull`.

## How It Works

The miner operates by performing the following steps:
1.  **Wallet Setup**: It creates or loads Cardano wallets to be used for mining. These wallets are stored in `wallets.json`.
2.  **Registration**: The bot registers the wallets with the Midnight Scavenger Mine API and agrees to the terms and conditions.
3.  **Challenge Loop**: It continuously polls the API for new mining challenges. Challenges are stored in `challenges.json` so they can be resumed later.
4.  **Mining**: When a new challenge is received, the bot uses the provided parameters to build a large proof-of-work table (ROM). It then rapidly searches for a valid nonce that solves the challenge's difficulty requirement. The core hashing logic is performed by a native Rust library for optimal performance.
5.  **Submission**: Once a solution is found, it is submitted to the API to earn NIGHT tokens.
6.  **Worker Rotation**: When a worker completes all available challenges for its wallet, it automatically exits and respawns with a different wallet. New wallets are generated automatically as needed.

## Prerequisites

Before running the miner, ensure you have the following:

1.  **Python 3**: The script is written in Python (version 3.13 or higher required).
2.  **Python venv module**: Usually included with Python 3.3+, but can be installed separately if needed.
3.  **Required Python Libraries**: The following packages are required and will be installed automatically when setting up the virtual environment:
    - `pycardano` - Cardano wallet functionality
    - `wasmtime` - WebAssembly runtime
    - `requests` - HTTP requests
    - `cbor2` - CBOR encoding/decoding
    - `portalocker` - Cross-platform file locking

    These are listed in `requirements.txt` and will be installed automatically when you set up the virtual environment.
4. **Git**: Use Git to download and update your Miner easily.

## Download

Run this command to download MidnightMiner
```
git clone https://github.com/djeanql/MidnightMiner && cd MidnightMiner
```

## Usage

### Manual Setup (Recommended for First-Time Users)

1. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   ```

2. **Activate the virtual environment**:

   All future steps will assume you are in the virtual environment. It is optional, but highly recommended.

   - On Linux/macOS:
     ```bash
     source venv/bin/activate
     ```
   - On Windows (CMD):
     ```bash
     venv\Scripts\activate
   
   - On Windows Powershell: (may need to escalate permission: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser)
     ```bash
     .\venv\Scripts\Activate.ps1
     ```

3. **Install required dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the miner**:
   -   **Start mining**:
       This command will either load an existing wallet from `wallets.json` or create a new one if it doesn't exist.
       ```bash
       python miner.py
       ```

   -   **Multiple workers**:
       To mine with multiple workers, use:
       ```bash
       python miner.py --workers <number of workers>
       ```
       Each worker uses one CPU core and 1GB of RAM. The miner will automatically create enough wallets for all workers and rotate through them as challenges are completed. Each worker always mines to a unique wallet. Do not run more workers than your system is capable of.

### Running as a Systemd Service (Linux Only)

For Linux users, you can run the miner as a systemd service, which allows it to:

- Start automatically on boot
- Restart automatically if it crashes
- Automatically pull the latest code from git before starting
- Run in the background without a terminal

Please refer to [SYSTEMD.md](SYSTEMD.md) for setup instructions.

## Resubmitting Failed Solutions

If solutions fail to submit due to network issues or API errors, they are automatically saved to `solutions.csv`. To resubmit them, run:

```bash
python resubmit_solutions.py
```

The script automatically removes successfully submitted solutions and keeps any that still failed for retry.
You should run this once a day, as solutions can no longer be submitted after 24 hours.

## ⚠️ Update Regularly

This software will be updated frequently, so it is VERY important you update it to earn the highest rewards.

Update by running this command in the MidnightMiner directory:
```
git pull
```

I suggest checking for updates once a day to make sure your miner is up-to-date.

**Systemd Users**: If you are running MidnightMiner as a `systemd` service, please check [here](SYSTEMD.md) for update instructions.

## Proxy Support

The miner and utility scripts read proxy settings from `proxy.json`. You can provide either a single proxy object or a list of proxies (for rotation). Use the sample file `proxy.json.example` as a starting point:

```json
[
  {
    "server": "127.0.0.1",
    "port": 3128,
    "user": "user1",
    "password": "example-password-1"
  }
]
```

Copy the example, edit the credentials to match your environment, and rename it to `proxy.json`. When multiple entries are supplied, the miner automatically rotates between them if a proxy becomes unavailable or returns HTTP 407/5xx responses.

You can verify the proxy is working correctly by running the miner with the `--log-api-requests` flag.

## Developer Donations

This miner includes an **optional 5% donation system** to support ongoing development and maintenance. By default, approximately 1 in 20 (5%) of solved challenges will be mined for the developer's address.

Thank you for considering supporting this project!

To disable donations, add the `--no-donation` flag:
```bash
python miner.py --no-donation
```

### Checking Wallet Balances and Solutions

To quickly check NIGHT token balances and completed solutions for your wallets, use the `check_earnings.py` utility:

```bash
# Check all wallets
python check_earnings.py --wallets-path wallets.json --proxy-count 30 --proxy-config proxy.json

# Check a specific wallet address
python check_earnings.py --address addr1vxask5vpp8p4xddsc3qd63luy4ecf...
```

- `--wallets-path` accepts one or more files or directories containing wallet JSON definitions.
- `--address` checks a specific wallet address directly (ignores --wallets-path).
- `--proxy-count` limits how many proxy-backed sessions are created simultaneously. For faster results, prepare at least that many proxy entries in `proxy.json`.
- `--proxy-config` points to the proxy configuration file; if omitted, the script will fall back to direct connections.

> **Tip:** Supplying a rich proxy pool dramatically reduces the chance of hitting rate limits while the script queries the statistics API.

## Consolidating NIGHT Earnings

You can consolidate all NIGHT earnings to a single wallet using `consolidate.py`. This registers a destination address where your NIGHT tokens will be sent during future distributions.

Consolidation is like setting up mail forwarding - it tells the network where to send your NIGHT, but doesn't immediately move anything. Your miner wallet balances will remain unchanged, and your destination wallet balance won't increase until the Midnight Network actually distributes tokens.

The destination address **must be registered** at https://sm.midnight.gd before consolidation. It is recommended to not use a wallet from wallets.json as your destination address for security reasons. It's safer to use an address from a wallet extension such as Eternl or Lace, after registering it with the online portal.


**Run the script:**
```bash
python consolidate.py
```

The script will prompt for confirmation before proceeding. Successfully consolidated wallets will redirect all their earnings (past and future) to the destination address when distributions occur.

**To undo consolidation:**
```bash
python consolidate.py --undo
```

This registers each wallet back to itself, reversing any previous donations.

## Exporting Wallets Individually

If you don't want to use the consolidation script, you can manually export all your wallets and claim from each of them. You will need to import your wallets' signing keys (`.skey` files) into a Cardano wallet like Eternl. The `export_skeys.py` script helps with this process.


1.  **Run the export script**:
    ```bash
    python export_skeys.py
    ```
    This will create a directory named `skeys/` (if it doesn't exist) and export each wallet's signing key from `wallets.json` into a separate `.skey` file.

2.  **Import into Eternl (or other Cardano wallet)**:
    *   Open your Eternl wallet.
    *   Go to `Add Wallet` -> `More` -> `CLI Signing Keys`.
    *   Import the `.skey` files generated in the `skeys/` directory.

## Dashboard

The dashboard displays important information about the status of each worker. Each row represents a worker (not a wallet) - workers automatically rotate through different wallets as they complete challenges.

The `Challenge` column shows which challenge ID the worker is currently solving, or status messages like "Waiting" if all known challenges have been completed. The `Attempts` and `H/s` columns show mining progress and hash rate for each worker.

At the bottom, you'll see totals across all wallets:
- **Total Hash Rate**: Combined hash rate of all workers
- **Total Completed**: Total challenges solved by all wallets. The number in brackets shows how many were solved in this session.
- **Total NIGHT**: Estimated NIGHT token rewards across all wallets (fetched once at startup)

If developer donations are enabled (default), when a worker is mining for the developer, the `Address` field for that worker will temporarily show **"developer (thank you!)"** instead of the wallet address.

```
==============================================================================================================
                                          MIDNIGHT MINER - v0.3
==============================================================================================================
Active Workers: 4 | Last Update: 2025-11-05 14:32:18
==============================================================================================================

ID   Address                                      Challenge                  Attempts      H/s
--------------------------------------------------------------------------------------------------------------
0    addr1vxask5vpp8p4xddsc3qd63luy4ecf...        **D05C02                   470,000       2,040
1    developer (thank you!)                       **D05C19                   471,000       2,035
2    addr1v9hcpxeevkks7g4mvyls029yuvvsm0d...      Building ROM               0             0
3    addr1vx64c8703ketwnjtxkjcqzsktwkcvh...      **D05C20                   154,000       2,028
--------------------------------------------------------------------------------------------------------------

Total Hash Rate:     6,103 H/s
Total Completed:     127 (+15)
Total NIGHT:         45.32
==============================================================================================================

Press Ctrl+C to stop all miners
```

## Platform Support

The miner uses a native Rust library (`ashmaize_py`) for high-performance hashing. Pre-compiled binaries are included for all major platforms:

| Platform | Architecture | Status |
|----------|--------------|--------|
| Windows | x64 | ✓ Supported |
| Linux | x64 | ✓ Supported |
| Linux | ARM64 (Raspberry Pi, etc.) | ✓ Supported |
| macOS | Intel (x64) | ✓ Supported |
| macOS | Apple Silicon (ARM64) | ✓ Supported |

The miner automatically detects your operating system and CPU architecture, loading the appropriate binary from the `libs/` directory.

## Visualise Challenge Data

A script `plot_challenges.py` is included to visualize the number of solved challenges over time.

### Prerequisites

This script requires `matplotlib`. 

```bash
pip install matplotlib
```

### Usage

To generate the plot, run the following command:

```bash
python3 plot_challenges.py
```

The script will read the `challenges.json` file and generate a plot named `solved_challenges_over_time.png`.

> **Note:** The graph uses the challenge's discovery time as an approximation for when solutions were found, as individual solution times are not stored.

## Ashmaize Rust Library Source Code

This miner uses the [Ashmaize](https://github.com/input-output-hk/ce-ashmaize) hashing algorithm, developed by IOHK. Included in this repository are binaries for my python bindings module. You can find the code [here](https://github.com/djeanql/ashmaize-py)

## Stars

If you like MidnightMiner, why not star the repository?

[![Star History Chart](https://api.star-history.com/svg?repos=djeanql/MidnightMiner&type=date&legend=top-left)](https://www.star-history.com/#djeanql/MidnightMiner&type=date&legend=top-left)
