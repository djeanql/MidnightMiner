# Easy Guide to Running Midnight Miner on Windows

This guide will help you start mining NIGHT tokens on Windows with MidnightMiner. If you have any questions, you can create an [Issue](https://github.com/djeanql/MidnightMiner/issues) or message @zeno_ql on X/Twitter.

## What This Software Does

Midnight Miner automatically solves puzzles to earn NIGHT tokens. It runs on your computer using multiple workers that rotate through different wallets to earn more rewards. Each worker uses its own unique wallet, and new wallets are created automatically as needed.

## Step 1: Install Python

Python is the programming language this software runs on.

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download python installation manager for windows (64 bit)
3. Open the installation manager from start menu. Then press Y on each step.
4. Reboot

Alternatively, you can install [Python 3.13](https://apps.microsoft.com/detail/9pnrbtzxmb4z) from the Microsoft store.

## Step 2: Install Git

Git allows for the miner to be easily downloaded and updated from the terminal.

1. Go to [git-scm.com/install/windows](https://git-scm.com/install/windows)
2. Download the standalone installer (x64)
3. Run the installer and click through steps, leave all the configuration options as-is

## Step 3: Download MidnightMiner

1. Open Command Prompt:
   - Press `Windows`
   - Type `cmd` and press Enter
2. Type `git clone https://github.com/djeanql/MidnightMiner`
3. Then enter the folder with `cd MidnightMiner`

## Step 4: Install Dependencies


Install the required dependencies by typing:
   ```
   py -m pip install requests pycardano cbor2 portalocker
   ```
Press Enter and wait for installation to finish

If you get a command not found error, you can try using `python` instead of `py`

## Step 5: Start Mining

**For a single worker** (good for testing):
```
py miner.py
```

**For multiple workers** (recommended for better earnings):
```
py miner.py --workers 4
```

Replace `4` with the number of workers you want to use. Each worker uses roughly one CPU core and about 1GB of memory. The miner will automatically create enough wallets for all workers and rotate through them as puzzles are completed.

> **Tip**: If you have a 6-core processor, try `--workers 6`.

## ⚠️ Update Regularly

This software will be updated very frequently, so it is important you update it to earn the highest rewards. To update, run this command while in the MidnightMiner folder:
```
git pull
```

This will fetch any changes made in this repository. If you have edited files locally, you will need to delete them first, or move the file out of the miner folder.

## Back Up Your Wallet File

It is important that you back up `wallets.json`, which is in the same folder as the miner. Copy it to a safe location. The miner automatically creates new wallets as needed, so you should back up this file regularly to ensure you don't lose access to any earned tokens.

## The Dashboard

Once running, you'll see a dashboard that updates automatically. Each row shows one worker (workers rotate through different wallets automatically):

- **ID**: Worker number
- **Address**: The wallet address currently being used by this worker
- **Challenge**: The puzzle being solved (or status like "Building ROM" or "Waiting")
- **Attempts**: How many guesses have been tried
- **H/s**: Guesses per second (hash rate)

At the bottom, you'll see totals across all your wallets:
- **Total Hash Rate**: Combined speed of all workers
- **Total Completed**: Total puzzles solved (number in brackets shows puzzles solved this session)
- **Total NIGHT**: Estimated token rewards across all wallets (fetched once at startup)

Press `Ctrl+C` to stop the miner anytime.

## Resubmitting Failed Solutions

If solutions fail to submit (network issues, API errors), they're saved to `solutions.csv`. To retry them:
```
py resubmit_solutions.py
```
Successfully submitted solutions are automatically removed from the file.
You should run this once a day, as solutions can no longer be submitted after 24 hours.

## Claiming NIGHT

To make claiming easier, you can consolidate all earnings to a single address using `consolidate.py`. This registers where your NIGHT tokens will be sent when the Midnight Network distributes them.

Consolidation is like setting up mail forwarding - it tells the system where to send your NIGHT, but doesn't immediately move anything. Your miner wallet balances stay the same, and your destination wallet won't show any NIGHT until the network actually distributes tokens.

The destination address must be registered at https://sm.midnight.gd first! It is recommended to not use a wallet from wallets.json as your destination address for security reasons. It's safer to use an address from a wallet extension such as Eternl or Lace, after registering it with the online portal.

Since the miner generates new wallets while mining, it is best to run this script again at the end of the scavenger hunt to make sure all wallets are consolidated.

You can run the miner with `--consolidate <destination address>` to automatically consolidate new wallets generated by the miner. All future earnings allocated to that wallet will be consolidated. It is still recommended to run the above script at the end of the scavenger hunt to make sure all wallets have consolidated properly.

**To consolidate:**
```
py consolidate.py
```

Paste a destination address when prompted (the one that you will claim all consolidated NIGHT from). Type `CONFIRM` when prompted to proceed.


**To undo consolidation:**
```
py consolidate.py --undo
```

This reverses the consolidation and registers each wallet back to itself.

## Visualising Mining Speed

A script `plot_challenges.py` is included to visualize the number of solved challenges over time.

### Setup

This script requires `matplotlib`. You can install it using pip:

```bash
py -m pip install matplotlib
```

### Usage

To generate the plot, run the following command:

```bash
py plot_challenges.py
```

The script will read the `challenges.json` file and generate a plot named `solved_challenges_over_time.png`.

> **Note:** The graph uses the challenge's discovery time as an approximation for when solutions were found, as individual solution times are not stored.
