"""Include external resources in the sdist so the wheel can be built without a clone."""
from pathlib import Path
import tomllib

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        config = tomllib.loads((Path(self.root) / "pyproject.toml").read_text())
        mappings = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
        if self.target_name == "sdist":
            build_data["force_include"].update({source: f"src/{dest}" for source, dest in mappings.items()})
        elif self.target_name == "wheel":
            for source, dest in list(self.build_config.force_include.items()):
                if not Path(source).exists():
                    if not (Path(self.root) / "src" / dest).exists():
                        raise FileNotFoundError(source)
                    del self.build_config.force_include[source]
