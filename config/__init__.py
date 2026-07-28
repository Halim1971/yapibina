from config.settings import (
    BaseConfig,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
)

CONFIGURATIONS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str) -> type[BaseConfig]:
    try:
        return CONFIGURATIONS[config_name.lower()]
    except KeyError as error:
        supported = ", ".join(sorted(CONFIGURATIONS))
        raise ValueError(
            f"Unknown APP_ENV '{config_name}'. Supported values: {supported}."
        ) from error


__all__ = [
    "BaseConfig",
    "DevelopmentConfig",
    "ProductionConfig",
    "TestingConfig",
    "get_config",
]
