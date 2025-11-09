
import json
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# This script requires matplotlib. Please install it using:
# pip install matplotlib

def plot_solved_challenges_over_time():
    """
    Reads challenges.json and wallets.json, and uses matplotlib to display a graph
    of the cumulative number of solutions from the user's wallets over time.
    """
    try:
        with open('wallets.json', 'r') as f:
            wallets_data = json.load(f)
        user_addresses = {wallet['address'] for wallet in wallets_data}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        print("Warning: Could not load user wallets from wallets.json. The plot will show all solutions.")
        user_addresses = set()

    try:
        with open('challenges.json', 'r') as f:
            challenges_data = json.load(f)
    except FileNotFoundError:
        print("Error: challenges.json not found.")
        return
    except json.JSONDecodeError:
        print("Error: Could not decode challenges.json.")
        return

    solutions_by_time = []
    for challenge in challenges_data.values():
        time_str = challenge.get("discovered_at")
        if not time_str:
            continue

        solution_count = 0
        if user_addresses:
            # Count solutions from user's wallets
            user_solutions = [addr for addr in challenge.get('solved_by', []) if addr in user_addresses]
            solution_count = len(user_solutions)
        else:
            # Fallback to counting all solutions if user wallets aren't loaded
            solution_count = len(challenge.get('solved_by', []))

        if solution_count > 0:
            try:
                dt_object = datetime.fromisoformat(time_str)
                solutions_by_time.append((dt_object, solution_count))
            except (ValueError, TypeError):
                print(f"Warning: Could not parse timestamp '{time_str}' for a challenge.")

    if not solutions_by_time:
        print("No solutions found to plot.")
        return

    # Sort by timestamp
    solutions_by_time.sort(key=lambda x: x[0])

    # Create cumulative data for plotting
    plot_times = [item[0] for item in solutions_by_time]
    solution_counts = [item[1] for item in solutions_by_time]
    
    cumulative_solutions = []
    current_total = 0
    for count in solution_counts:
        current_total += count
        cumulative_solutions.append(current_total)

    # Plotting
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(plot_times, cumulative_solutions, marker='o', linestyle='-', color='cyan')

    # Formatting the plot
    ax.set_title('Cumulative Solutions by Your Wallets Over Time', color='white')
    ax.set_xlabel('Date (of Challenge Discovery)', color='white')
    ax.set_ylabel('Cumulative Number of Solutions', color='white')
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='gray')

    # Improve date formatting on the x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45, ha='right', color='white')
    plt.yticks(color='white')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')


    plt.tight_layout()

    # Save the figure
    output_filename = 'solved_challenges_over_time.png'
    plt.savefig(output_filename, facecolor='#222222')
    # Only show the plot if a display is available (e.g., not on a headless server)
    import os
    if os.environ.get('DISPLAY'):
        plt.show()
    else:
        print("No display found. Skipping plot window.")
    print(f"Graph saved to {output_filename}")

if __name__ == "__main__":
    plot_solved_challenges_over_time()
