class ParameterVerifyTool:
    def verify(self, params: dict, required: tuple[str, ...]):
        missing = [key for key in required if key not in params]
        return {'ok': not missing, 'missing': missing}


def main(args=None) -> None:
    _ = args
    ParameterVerifyTool()

