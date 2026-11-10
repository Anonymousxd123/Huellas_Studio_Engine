import json
from huellas_engine.asset_manager import catalog_projects

if __name__ == "__main__":
    result = catalog_projects()

    print("\nHUELLAS ASSET CATALOG")
    print(json.dumps(result, indent=2))