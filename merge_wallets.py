#!/usr/bin/env python3
"""
Скрипт для объединения всех JSON файлов из папки json/ 
без повторений адресов в wallets.json
"""

import json
import os
from pathlib import Path


def merge_wallets():
    """Объединяет все JSON файлы из папки json/ без дубликатов адресов"""
    
    json_dir = Path("json")
    output_file = Path("wallets.json")
    
    if not json_dir.exists():
        print(f"Ошибка: папка {json_dir} не найдена!")
        return
    
    all_wallets = []
    seen_addresses = set()
    processed_files = 0
    total_wallets = 0
    duplicates = 0
    
    # Получаем все JSON файлы из папки json/
    json_files = sorted(json_dir.glob("*.json"))
    
    if not json_files:
        print(f"Ошибка: в папке {json_dir} не найдено JSON файлов!")
        return
    
    print(f"Найдено {len(json_files)} JSON файлов для обработки...")
    
    # Обрабатываем каждый файл
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Проверяем, что это список
            if not isinstance(data, list):
                print(f"Предупреждение: {json_file.name} не является массивом, пропускаем")
                continue
            
            # Добавляем кошельки без дубликатов
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
            print(f"Обработан: {json_file.name} ({len(data)} кошельков)")
            
        except json.JSONDecodeError as e:
            print(f"Ошибка при чтении {json_file.name}: {e}")
        except Exception as e:
            print(f"Ошибка при обработке {json_file.name}: {e}")
    
    # Сортируем по дате создания (если есть)
    try:
        all_wallets.sort(key=lambda x: x.get('created_at', ''))
    except:
        pass
    
    # Сохраняем результат
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_wallets, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*50}")
        print(f"Объединение завершено!")
        print(f"Обработано файлов: {processed_files}")
        print(f"Всего уникальных кошельков: {total_wallets}")
        print(f"Найдено дубликатов: {duplicates}")
        print(f"Результат сохранен в: {output_file}")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"Ошибка при сохранении результата: {e}")


if __name__ == "__main__":
    merge_wallets()

