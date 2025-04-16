import os
import argparse
from models.models import init_db, get_session_factory
from data.data_importer import FarmDataImporter
from services.farm_control_service import FarmControlService

def main():
    parser = argparse.ArgumentParser(description='Farm Control System')
    parser.add_argument('--import', dest='import_file', 
                        help='Import data from JSON file')
    parser.add_argument('--db', dest='db_file', default='farm_control.db',
                        help='SQLite database file path')
    
    args = parser.parse_args()
    
    # Initialize database
    engine = init_db(args.db_file)
    SessionFactory = get_session_factory(engine)
    
    # Import data if requested
    if args.import_file:
        if not os.path.exists(args.import_file):
            print(f"Error: File {args.import_file} not found")
            return
        
        print(f"Importing data from {args.import_file}...")
        importer = FarmDataImporter(args.db_file)
        importer.import_from_json(args.import_file)
        print("Import complete")
    
    # Start FastAPI server
    import uvicorn
    print("Starting API server...")
    uvicorn.run("api:app", host="0.0.0.0", port=8060, reload=True)

if __name__ == "__main__":
    main()