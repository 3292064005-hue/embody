class FakeHardwareNode:
    def __init__(self, fake_motion_delay_ms: int = 50) -> None:
        self.fake_motion_delay_ms = fake_motion_delay_ms


def main(args=None) -> None:
    _ = args
    FakeHardwareNode()

