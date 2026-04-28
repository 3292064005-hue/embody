class FrameCheckTool:
    def validate(self, frames):
        return bool(frames and 'base_link' in frames)


def main(args=None) -> None:
    _ = args
    FrameCheckTool()

