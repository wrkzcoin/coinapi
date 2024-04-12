from toml import load


def load_config(config_file: str):
    with open(config_file) as f:
        return load(f)
