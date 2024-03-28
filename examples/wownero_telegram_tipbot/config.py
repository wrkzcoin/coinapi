from toml import load


def load_config():
    with open("tipbot_config.toml") as f:
        return load(f)
