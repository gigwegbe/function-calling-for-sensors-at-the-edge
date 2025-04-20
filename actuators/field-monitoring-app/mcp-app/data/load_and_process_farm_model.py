import json

class LoadAndProcessFarmModel:
    def __init__(self):
        self.farm_data = None
        self.field_map = {}

    def load_from_json(self, file_path: str):
        with open(file_path, 'r') as f:
            self.farm_data = json.load(f)

    def inspect_hierarchy(self, data=None, indent=0):
        if data is None:
            data = self.farm_data

        if isinstance(data, dict):
            for key, value in data.items():
                print("  " * indent + f"{key}: {type(value).__name__}")
                self.inspect_hierarchy(value, indent + 1)
        elif isinstance(data, list):
            print("  " * indent + f"List[{len(data)}]")
            if len(data) > 0:
                self.inspect_hierarchy(data[0], indent + 1)
        else:
            print("  " * indent + f"{type(data).__name__}")


if __name__ == "__main__":
    loader = LoadAndProcessFarmModel()
    loader.load_from_json("farm_model.json")
    loader.inspect_hierarchy()
    