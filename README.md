# Midnight Miner

A Python-based mining bot for the Midnight Network's scavenger hunt, allowing users to automatically mine for NIGHT tokens with multiple wallets.

Works on Windows and Linux. Only partial support for MacOS with apple silicone (see below).

If you are unfamiliar with python, check out the [Easy Guide](EasyGuide.md).

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

1.  **Python 3**: The script is written in Python (version 3.8 or higher recommended).
2.  **Required Libraries**: Install the necessary Python packages using pip:
    ```bash
    pip install requests pycardano cbor2 portalocker
    ```
3. **Git**: Use Git to download and update your Miner easily.

## Download

Run this command to download MidnightMiner
```
git clone https://github.com/djeanql/MidnightMiner && cd MidnightMiner
```

### Mac OS

If you are on MacOS, you need to delete `ashmaize_py.so`, and rename `ashmaize_py_mac.so` to `ashmaize_py.so`.

## Usage

You can run the miner from your terminal.

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


## Resubmitting Failed Solutions

If solutions fail to submit due to network issues or API errors, they are automatically saved to `solutions.csv`. To resubmit them:
```bash
python resubmit_solutions.py
```
The script automatically removes successfully submitted solutions and keeps any that still failed for retry.

## ⚠️ Update Regularly

This software will be updated frequently, so it is VERY important you update it to earn the highest rewards. To update, run this command in the MidnightMiner directory:
```
git pull
```

I suggest running this once a day to make sure your miner is up-to-date.


## Developer Donations

This miner includes an **optional 5% donation system** to support ongoing development and maintenance. By default, approximately 1 in 20 (5%) of solved challenges will be mined for the developer's address.

Thank you for considering supporting this project!

To disable donations, add the `--no-donation` flag:
```bash
python miner.py --no-donation
```


## Exporting Wallets

To claim your earned NIGHT tokens (when they are distributed), you will need to import your wallets' signing keys (`.skey` files) into a Cardano wallet like Eternl. The `export_skeys.py` script helps with this process.

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

