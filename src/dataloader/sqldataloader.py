import pandas as pd
import sqlalchemy
import os
import sys

def get_sql_data(client_name):
    """
    Extracts data from an SQL database and saves it as a CSV for FlowGuard training.
    """
    # Replace these with your actual connection details or environment variables
    db_type = os.getenv('DB_TYPE', 'postgresql') # or 'mysql', 'sqlite', etc.
    user = os.getenv('DB_USER', 'your_user')
    password = os.getenv('DB_PASS', 'your_password')
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'your_db')

    # Create the connection string
    # Engines: 
    #   PostgreSQL: 'postgresql://user:pass@host/db'
    #   MySQL:      'mysql+pymysql://user:pass@host/db'
    if db_type == 'postgresql':
        conn_str = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    elif db_type == 'mysql':
        conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"
    else:
        print(f"Unsupported DB type: {db_type}")
        return

    try:
        engine = sqlalchemy.create_engine(conn_str)
        
        # Define your query here. 
        # Ensure the columns match the sensors expected by your model.
        query = "SELECT * FROM telemetry_data ORDER BY timestamp DESC LIMIT 10000"
        
        print(f"Executing query on {db_type}...")
        df = pd.read_sql(query, engine)
        
        # Pre-process if necessary (e.g., dropping timestamp if it's there)
        if 'timestamp' in df.columns:
            df = df.drop(columns=['timestamp'])
            
        # Target directory
        output_dir = f"src/data/{client_name}_RETRAIN"
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, "data.csv")
        df.to_csv(output_file, index=False)
        
        print(f"Data successfully saved to {output_file}")
        print(f"Shape: {df.shape}")
        
    except Exception as e:
        print(f"Error extracting data from SQL: {e}")

if __name__ == "__main__":
    client = os.getenv('CLIENT', 'ESAMUR')
    get_sql_data(client)
