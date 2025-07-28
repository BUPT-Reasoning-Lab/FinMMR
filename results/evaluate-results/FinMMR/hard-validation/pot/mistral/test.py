import json

# Load the original JSON file
file_path = '/home/lirongjin/FinanceBench/finance-reasoning-master/results/MultiFinance/hard/pot/test/mistral/inference.json'

# Open and load the JSON data
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract the 'ground_truth' from each entry in the JSON and add it as a separate key-value pair
for entry in data:
    if 'original_data' in entry and 'ground_truth' in entry['original_data']:
        # Extract the ground_truth and create a new key for it in the main dictionary
        entry['ground_truth_value'] = entry['original_data']['ground_truth']

# Save the modified JSON data back to the same file
with open(file_path, 'w') as file:
    json.dump(data, file, indent=4)

print(f"Updated JSON saved to {file_path}")
