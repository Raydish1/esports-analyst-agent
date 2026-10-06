"""Why a build stopped: problems the builder can't work around, listed for a person to fix. The live
build stays as it was."""


class BuildStop(Exception):
    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = problems


class CurationError(BuildStop):
    """A curated file is wrong: fix it and build again."""
