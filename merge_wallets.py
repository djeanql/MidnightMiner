#!/usr/bin/env python3
"""
Script to merge all JSON files from json/ folder
into wallets.json without duplicate addresses
"""

import json
import os
from pathlib import Path


def merge_wallets():
    """Merges all JSON files from json/ folder without duplicate addresses"""
    
    json_dir = Path("json")
    output_file = Path("wallets.json")
    
    if not json_dir.exists():
        print(f"Error: folder {json_dir} not found!")
        return
    
    all_wallets = []
    seen_addresses = set()
    processed_files = 0
    total_wallets = 0
    duplicates = 0
    
    # Get all JSON files from json/ folder
    json_files = sorted(json_dir.glob("*.json"))
    
    if not json_files:
        print(f"Error: no JSON files found in {json_dir} folder!")
        return
    
    print(f"Found {len(json_files)} JSON files to process...")
    
    # Process each file
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check that it's a list
            if not isinstance(data, list):
                print(f"Warning: {json_file.name} is not an array, skipping")
                continue
            
            # Add wallets without duplicates
            for wallet in data:
                if not isinstance(wallet, dict) or 'address' not in wallet:
                    continue
                
                address = wallet['address']
                if address not in seen_addresses:
                    seen_addresses.add(address)
                    all_wallets.append(wallet)
                    total_wallets += 1
                else:
                    duplicates += 1
            
            processed_files += 1
            print(f"Processed: {json_file.name} ({len(data)} wallets)")
            
        except json.JSONDecodeError as e:
            print(f"Error reading {json_file.name}: {e}")
        except Exception as e:
            print(f"Error processing {json_file.name}: {e}")
    
    # Sort by creation date (if available)
    try:
        all_wallets.sort(key=lambda x: x.get('created_at', ''))
    except:
        pass
    
    # Save result
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_wallets, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*50}")
        print(f"Merge completed!")
        print(f"Processed files: {processed_files}")
        print(f"Total unique wallets: {total_wallets}")
        print(f"Found duplicates: {duplicates}")
        print(f"Result saved to: {output_file}")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"Error saving result: {e}")


if __name__ == "__main__":
    merge_wallets()

