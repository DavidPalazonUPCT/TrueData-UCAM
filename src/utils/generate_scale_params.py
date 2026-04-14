import pandas as pd
import numpy as np
import sys

def generate_scale_params(input_file, output_file):
    # Read the dataset, skipping initial lines which are metadata
    try:
        df = pd.read_csv(input_file, skiprows=3)
    except Exception as e:
        print(f"Error reading the input file: {e}")
        sys.exit(1)

    # Drop unnecessary columns like 'Row', 'Date', 'Time' if they exist
    unnecessary_columns = ['Row', 'Date', 'Time']
    df = df.drop([col for col in unnecessary_columns if col in df.columns], axis=1)

    # Rename columns by stripping the long Windows path if needed
    df.columns = df.columns.str.split("\\").str[-1]

    # Calculate min and max values for each sensor column
    min_values = df.min()
    max_values = df.max()

    # Create a DataFrame for scale_params
    scale_params = pd.DataFrame({
        'min': min_values,
        'max': max_values
    }).reset_index()

    # Rename columns for clarity
    scale_params.rename(columns={'index': ''}, inplace=True)

    # Save the scale parameters to a CSV file
    try:
        scale_params.to_csv(output_file, index=False)
        print(f"Scale parameters have been successfully written to {output_file}")
    except Exception as e:
        print(f"Error writing the output file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_scale_params.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    generate_scale_params(input_file, output_file)
